"""A stdio MCP server that serves the sandbox tools to ``claude -p``.

``claude -p`` cannot register Python functions as tools, so the sandbox tools reach it through a
local MCP server it launches itself::

    python -m claude_bully.environments.mcp_server --state <dir>

Claude Code starts one server process per ``claude -p`` call, so nothing may live in memory
between calls; the files in ``<dir>`` carry everything:

- ``env_state.json`` (``McpState``) is written by the caller before each ``claude -p`` call. The
  server re-reads it at every ``tools/call`` and writes it back, atomically, only when the
  ``UnlockState`` changed (retry counts, the search log).
- ``tools.jsonl`` gets one ``ToolCall`` line appended per call, a call to a tool that is not on
  offer included (answered "not available" and counted against the cap, as on the API path); the
  caller reads the lines added since before its call to see what the target did.
- ``authority.jsonl`` gets the ``AuthorityCall`` of each authority call that reached a tier and
  was answered, keyed by its ``ToolCall``'s id and written after that line.

The world is served in time, as the runtime serves it: ``world_at(load_world(...), state.clock)``,
re-dated to the state's effective clock (the world is loaded once per process, and the served copy
kept per clock). The server checks nothing about the clock: it only ever serves a state the
runtime wrote after its own ``served_world`` checks. ``tools/list`` is ``SandboxTools.specs()``,
so a tool the clock withholds (``get_date`` under ``assert_date: false``) or the desk has not yet
offered (``consult_model`` before its discovery) is not listed and is answered "not available"
like a disabled one. Committed generated documents arrive on the state (``McpState.generated``) and
are added to the index built for each call, so a ``claude -p`` target finds them as it finds
anchor documents.

The authority desk is built here as the runtime builds it, once per process for each cell: its
responder is ``build_provider(state.responder, <dir>/responder)``. What the desk reads about the
turn is the state's ``context`` (the records before the turn) with this turn's earlier lines of
both logs folded in by ``advance_context``, the helper the runtime uses after every call, so peer
rotation and the documents that name a tier agree across backends (preflight C23). A responder
that fails, or cannot be built, costs that one reply ("No reply."), never the server.

Protocol: newline-delimited JSON-RPC 2.0, one JSON object per line, UTF-8, on stdin and stdout.
Stdout carries nothing else; logs go to stderr.
"""

import argparse
import io
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from random import Random
from typing import Any, Final, TextIO

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from claude_bully import atomic
from claude_bully.config import RoleConfig
from claude_bully.environments.authority import (
    VOICED_TIERS,
    AuthorityDesk,
    CallContext,
    advance_context,
    consult_rungs,
)
from claude_bully.environments.config import ClockConfig, EnvironmentConfig, resolve_exchange
from claude_bully.environments.corpus import CorpusIndex, UnlockState
from claude_bully.environments.dating import world_at
from claude_bully.environments.limits import (
    LIMIT_STATUS,
    MAX_TOOL_CALLS_PER_TURN,
    TOOL_LIMIT_TEXT,
)
from claude_bully.environments.tools import (
    SandboxTools,
    ToolNotEnabled,
    ToolResult,
    record_tool_call,
)
from claude_bully.environments.world import Document, World, load_world
from claude_bully.providers.base import ChatProvider, build_provider
from claude_bully.providers.ledger import LEDGER_FILE, Ledger, LedgerProvider
from claude_bully.records_env import AuthorityCall, ToolCall

# What the target can see of this server: the name prefixes every tool (mcp__gateway__fetch)
# and the version rides along in serverInfo. Neither may name the experiment. The CLI reserves
# some names (``workspace`` since at least 2.1.319) and drops a config entry under one with only
# a debug-log warning, so the target gets no tools and says so in text; doctor check 4 reads the
# server's status off the stream's init event (Task 11).
SERVER_NAME: Final = "gateway"
SERVER_VERSION: Final = "1.0.0"
SERVER_MODULE: Final = "claude_bully.environments.mcp_server"
LAUNCHER_FILE: Final = f"{SERVER_NAME}_server.py"
INTERNAL_ERROR_TEXT: Final = "Internal error."
STATE_FILE: Final = "env_state.json"
TOOLS_FILE: Final = "tools.jsonl"
AUTHORITY_FILE: Final = "authority.jsonl"
# under the state directory: where a claude_code responder keeps its own session files
RESPONDER_DIR: Final = "responder"
MCP_CONFIG_FILE: Final = "mcp.json"

DEFAULT_PROTOCOL: Final = "2025-06-18"
SUPPORTED_PROTOCOLS: Final = ("2025-06-18", "2025-03-26", "2024-11-05")

_PARSE_ERROR: Final = -32700
_INVALID_REQUEST: Final = -32600
_METHOD_NOT_FOUND: Final = -32601
_INVALID_PARAMS: Final = -32602
_INTERNAL_ERROR: Final = -32603


class McpState(BaseModel):
    """What the server needs to run one cell's tools; the caller writes it before each call."""

    model_config = ConfigDict(extra="forbid")

    world: str
    worlds_dir: str
    config: EnvironmentConfig
    # the effective clock: the config's own, else the world sheet's
    clock: ClockConfig
    seed: int
    # the target turn's index: tool-call ids, the rng seed and the per-turn cap count in it
    turn: int
    # the exchange (k-th bully turn) the clock reads; left out (an older file, an older caller), it
    # is ``turn``, filled in before validation, so the default below is never what a state holds
    exchange: int = 0
    unlock: UnlockState
    # what the authority desk reads about the turn as it began: the runtime's ``begin_turn``,
    # from the records before it. The server folds this turn's own lines in.
    context: CallContext = Field(default_factory=CallContext)
    # the role the superior self and the stranger speak through (the runner resolves
    # ``responder_model``); None: they never reply
    responder: RoleConfig | None = None
    # prefixes each responder conversation id: ``<conversation_id>/authority/<call id>``
    conversation_id: str = ""
    # the target's own name, the one real name a responder reply may hold (preflight C18)
    display_name: str | None = None
    # the committed generated documents (Phase 3), served beside the world's
    generated: list[Document] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _exchange_defaults_to_turn(cls, data: Any) -> Any:
        if isinstance(data, dict) and "exchange" not in data and "turn" in data:
            return {**data, "exchange": resolve_exchange(data["turn"])}
        return data


def write_mcp_state(path: Path, state: McpState) -> None:
    """Write ``state`` to ``path`` atomically (``atomic.write_atomic``)."""
    atomic.write_atomic(path, state.model_dump_json(indent=1))


def read_mcp_state(path: Path) -> McpState:
    return McpState.model_validate_json(path.read_bytes())


def _append_line(path: Path, line: bytes) -> None:
    """Append ``line`` and a newline; a torn last line (no newline) is first closed off.

    A writer killed mid-line leaves a fragment with no newline; appending straight after it would
    glue the next record onto the fragment and lose both.
    """
    separator = b""
    if path.exists() and path.stat().st_size:
        with path.open("rb") as handle:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                separator = b"\n"
    with path.open("ab") as handle:
        handle.write(separator + line + b"\n")


# What the decoder stopped at when a record was cut short inside a token it had started, by the
# error it reports there: where a value goes, the start of a literal or a number's sign; after a
# number's digit, its fraction point or its exponent; after a backslash in a string, a
# ``\uXXXX`` escape. Each needs the left context its error names, so a bare ``e`` or ``.`` where
# a value goes is damage, not a cut.
_CUT_VALUE: Final = re.compile(r"t(?:ru?)?|f(?:a(?:ls?)?)?|n(?:ul?)?|-")
_CUT_NUMBER: Final = re.compile(r"\.|[eE][-+]?")
_CUT_ESCAPE: Final = re.compile(r"u[0-9a-fA-F]{0,4}")


def _torn(line: str, exc: json.JSONDecodeError) -> bool:
    """Whether ``line``, which ``exc`` failed to decode, is a record cut short (preflight P27):
    the decoder ran out of line between tokens (nothing left after the error position), inside
    an open string, or inside a token it had started (``_CUT_VALUE``, ``_CUT_NUMBER``,
    ``_CUT_ESCAPE``). Anything else, such as a bare word where a value goes or text after a
    closed record, is damage in the middle of the line."""
    tail = line[exc.pos :].rstrip()
    before = line[exc.pos - 1] if exc.pos else ""
    if not tail or exc.msg.startswith("Unterminated string"):
        return True
    if exc.msg.startswith("Expecting value"):
        return _CUT_VALUE.fullmatch(tail) is not None
    if exc.msg.startswith("Expecting ',' delimiter"):
        return before.isdigit() and _CUT_NUMBER.fullmatch(tail) is not None
    if exc.msg.startswith("Invalid \\uXXXX escape"):
        return before == "\\" and _CUT_ESCAPE.fullmatch(tail) is not None
    return False


def _torn_bytes(raw: bytes, exc: UnicodeDecodeError) -> bool:
    """Whether ``raw``, which ``exc`` failed to decode as UTF-8, is a record cut inside a
    multibyte character: the decoder ran out of bytes at the end of the line, and what came
    before is a record cut inside an open string (the only place such a character can sit). An
    invalid byte anywhere, the end included, is damage."""
    if exc.end != len(raw) or exc.reason != "unexpected end of data":
        return False
    head = raw[: exc.start].decode("utf-8")  # the first error is at ``start``; nothing before
    try:
        json.loads(head)
    except json.JSONDecodeError as cut:
        return cut.msg.startswith("Unterminated string")
    return False


def write_launcher(directory: Path) -> Path:
    """A small script in ``directory`` that starts this server.

    The MCP config names the script instead of ``-m claude_bully...``, so nothing in the config
    spells out the package. The script puts the package's own root on ``sys.path``, because Claude
    Code starts the server in a directory of its choosing.
    """
    root = Path(__file__).resolve().parents[2]
    source = (
        "import sys\n"
        f"sys.path.insert(0, {root.as_posix()!r})\n"
        f"from {SERVER_MODULE} import main\n"
        "raise SystemExit(main())\n"
    )
    path = directory / LAUNCHER_FILE
    directory.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != source:
        path.write_text(source, encoding="utf-8", newline="\n")
    return path


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_result(text: str, is_error: bool) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class McpServer:
    """The request handler. ``handle`` takes one decoded message and returns the reply or None."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_path = state_dir / STATE_FILE
        self.tools_path = state_dir / TOOLS_FILE
        self.authority_path = state_dir / AUTHORITY_FILE
        # the authored world per (worlds_dir, world), and the served one per clock as well
        self._worlds: dict[tuple[str, str], World] = {}
        self._served: dict[tuple[str, str, str], World] = {}
        # the desk per cell state and the responder per role, each built once per process
        self._desks: dict[str, AuthorityDesk] = {}
        self._responders: dict[str, ChatProvider | None] = {}
        self._ledger = Ledger(state_dir / LEDGER_FILE)

    # ------------------------------------------------------------------ dispatch

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return _error(None, _INVALID_REQUEST, "a message must be a JSON object")
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            if "result" in message or "error" in message:
                return None  # a response to something we never asked
            return _error(request_id, _INVALID_REQUEST, "missing method")
        if "id" not in message:
            return None  # a notification: no reply, whatever the method
        try:
            result = self._dispatch(method, message.get("params"))
        except _RpcError as exc:
            return _error(request_id, exc.code, exc.message)
        except Exception as exc:  # keep serving; the caller sees the failure
            # the detail stays on stderr; the client never sees exception text or paths
            print(f"[{SERVER_NAME}] {method} failed: {exc!r}", file=sys.stderr, flush=True)
            return _error(request_id, _INTERNAL_ERROR, INTERNAL_ERROR_TEXT)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: Any) -> dict[str, Any]:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return self._list_tools()
        if method == "tools/call":
            return self._call_tool(params)
        raise _RpcError(_METHOD_NOT_FOUND, f"method not found: {method}")

    # ------------------------------------------------------------------- methods

    def _initialize(self, params: Any) -> dict[str, Any]:
        if params is not None and not isinstance(params, dict):
            raise _RpcError(_INVALID_PARAMS, "params must be an object")
        asked = (params or {}).get("protocolVersion")
        return {
            "protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _list_tools(self) -> dict[str, Any]:
        state = read_mcp_state(self.state_path)
        return {
            "tools": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "inputSchema": spec.input_schema,
                }
                for spec in self._tools(state, Random(0)).specs()
            ]
        }

    def _call_tool(self, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise _RpcError(_INVALID_PARAMS, "params must be an object with a tool name")
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str):
            raise _RpcError(_INVALID_PARAMS, "params.name must be a string")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise _RpcError(_INVALID_PARAMS, "params.arguments must be an object")

        state = read_mcp_state(self.state_path)
        self._ledger.turn = state.turn
        lines = self._lines(self.tools_path)
        call_index = 1 + sum(1 for record in lines if record.get("turn") == state.turn)
        call_id = f"mcp-{state.turn}-{call_index}"
        if call_index > MAX_TOOL_CALLS_PER_TURN:
            # past the cap the call does not run and the state is not touched, but it is recorded
            limited = ToolResult(text=TOOL_LIMIT_TEXT, status=LIMIT_STATUS)
            self._log(record_tool_call(limited, name, arguments, state.turn, call_id))
            return _tool_result(TOOL_LIMIT_TEXT, is_error=True)
        before = state.unlock.to_json()
        try:
            tools = self._tools(state, Random(f"{state.seed}:{state.turn}:{call_index}"))
            tools.exchange = state.exchange
            result = tools.call(name, arguments, state.turn, call_id=call_id)
        except ToolNotEnabled:
            # disabled, unknown or not yet offered: answered, recorded and counted against the
            # cap, as the API path does
            result = ToolResult(text=f"Tool {name!r} is not available.", status="error")
        except Exception as exc:
            # A broken tool or world is the harness's problem, not the target's: a bland result,
            # the call still recorded, the unlock state left as it was, the detail on stderr.
            print(f"[{SERVER_NAME}] tool {name!r} failed: {exc!r}", file=sys.stderr, flush=True)
            result = ToolResult(text=INTERNAL_ERROR_TEXT, status="error")
        else:
            if state.unlock.to_json() != before:
                write_mcp_state(self.state_path, state)
        self._log(record_tool_call(result, name, arguments, state.turn, call_id), result.authority)
        return _tool_result(result.text, is_error=result.status != "200")

    def _log(self, record: ToolCall, authority: AuthorityCall | None = None) -> None:
        """The call's line, then its ``AuthorityCall``'s. In that order: a process killed between
        the two loses the authority line, and never leaves one whose id the next call takes."""
        _append_line(self.tools_path, record.model_dump_json().encode("utf-8"))
        if authority is not None:
            _append_line(self.authority_path, authority.model_dump_json().encode("utf-8"))

    # ------------------------------------------------------------------- helpers

    def _world(self, state: McpState) -> World:
        """The world served under ``state``'s clock: loaded once per (worlds_dir, world), re-dated
        once per clock."""
        key = (state.worlds_dir, state.world)
        served_key = (*key, state.clock.model_dump_json())
        served = self._served.get(served_key)
        if served is None:
            authored = self._worlds.get(key)
            if authored is None:
                authored = self._worlds[key] = load_world(state.world, Path(state.worlds_dir))
            served = self._served[served_key] = world_at(authored, state.clock)
        return served

    def _tools(self, state: McpState, rng: Random) -> SandboxTools:
        """The cell's tools under ``state``, with its desk and this turn's context."""
        world = self._world(state)
        desk = self._desk(state, world)
        index = CorpusIndex(world, honest=state.config.honest, mole=state.config.mole)
        index.add_documents(state.generated)
        tools = SandboxTools(
            index=index,
            config=state.config,
            clock=state.clock,
            state=state.unlock,
            rng=rng,
            enabled=set(state.config.tools),
            authority=desk,
        )
        tools.call_context = self._context(state, desk)
        return tools

    def _desk(self, state: McpState, world: World) -> AuthorityDesk | None:
        """The cell's desk, built once per process for each cell state; None when the cell
        enables no tier."""
        if not state.config.authority.enabled_tiers():
            return None
        key = state.model_dump_json(
            include={
                "world",
                "worlds_dir",
                "config",
                "clock",
                "seed",
                "responder",
                "conversation_id",
                "display_name",
            }
        )
        desk = self._desks.get(key)
        if desk is None:
            desk = self._desks[key] = AuthorityDesk(
                state.config.authority,
                world,
                responder=self._responder(state),
                conversation_id=state.conversation_id,
                seed=state.seed,
                consult_rungs=consult_rungs(world.ladders.get(state.config.ladder)),
                display_name=state.display_name,
            )
        return desk

    def _responder(self, state: McpState) -> ChatProvider | None:
        """The provider for the state's responder role, once per role and only for a tier that
        speaks through it. A role that cannot be built is noted on stderr and read as none: the
        superior self and the stranger then answer "No reply." and the server keeps serving."""
        role = state.responder
        if role is None or not state.config.authority.enabled_tiers() & VOICED_TIERS:
            return None
        key = role.model_dump_json()
        if key not in self._responders:
            try:
                self._responders[key] = LedgerProvider(
                    build_provider(role, self.state_dir / RESPONDER_DIR), self._ledger
                )
            except Exception as exc:
                print(
                    f"[{SERVER_NAME}] the responder could not be built: {exc!r}",
                    file=sys.stderr,
                    flush=True,
                )
                self._responders[key] = None
        return self._responders[key]

    def _context(self, state: McpState, desk: AuthorityDesk | None) -> CallContext:
        """The state's context with this turn's earlier calls folded in, in the order they were
        logged, each with its ``AuthorityCall`` (``advance_context``)."""
        names = desk.tier_names if desk is not None else {}
        answered: dict[str, AuthorityCall] = {}
        for raw in self._lines(self.authority_path):
            if raw.get("turn") == state.turn:
                try:
                    call = AuthorityCall.model_validate(raw)
                except ValidationError:
                    continue
                answered[call.id] = call
        context = state.context
        for raw in self._lines(self.tools_path):
            if raw.get("turn") != state.turn:
                continue
            try:
                record = ToolCall.model_validate(raw)
            except ValidationError:
                continue
            context = advance_context(context, record, answered.get(record.id), names)
        return context

    def _lines(self, path: Path) -> list[dict[str, Any]]:
        """The JSON objects of a log, one per line. A torn line (a record cut short by a writer
        killed mid-line, ``_torn``) is skipped wherever it sits, since ``_append_line`` closes
        one off with a newline before the next record; a malformed line that is not one is
        damage and raises a ``ValueError`` naming the file and the line (m7, preflight P27),
        which ``handle`` answers with the internal error and logs on stderr, so the per-turn cap
        is never counted over it. Each line is decoded strictly: a line cut inside a multibyte
        character at its end is torn (``_torn_bytes``), and an invalid byte is damage."""
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for number, raw in enumerate(path.read_bytes().split(b"\n"), start=1):
            if not raw.strip():
                continue
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                if _torn_bytes(raw, exc):
                    continue
                raise ValueError(
                    f"{path}: line {number} is not valid UTF-8 ({exc}); the server log is damaged"
                ) from exc
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                if _torn(line, exc):
                    continue
                raise ValueError(
                    f"{path}: line {number} is not valid JSON ({exc}); the server log is damaged"
                ) from exc
            if isinstance(record, dict):
                records.append(record)
        return records


def serve(server: McpServer, stdin: TextIO, stdout: TextIO) -> None:
    """Answer one message per input line until EOF."""
    for line in iter(stdin.readline, ""):
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except (ValueError, RecursionError):
            reply: dict[str, Any] | None = _error(None, _PARSE_ERROR, "parse error")
        else:
            reply = server.handle(message)
        if reply is not None:
            # ASCII-escaped, so no byte in the stream depends on a console code page
            stdout.write(json.dumps(reply, ensure_ascii=True) + "\n")
            stdout.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=SERVER_MODULE, description="Serve the claude_bully sandbox tools over MCP on stdio."
    )
    parser.add_argument(
        "--state", required=True, type=Path, help="directory holding env_state.json"
    )
    args = parser.parse_args(argv)
    # The protocol owns the real stdout. Anything else that prints lands on stderr instead.
    wire_out = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", newline="\n", write_through=True
    )
    wire_in = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = sys.stderr
    serve(McpServer(args.state), wire_in, wire_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
