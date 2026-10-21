"""A stdio MCP server that serves the sandbox tools to ``claude -p``.

``claude -p`` cannot register Python functions as tools, so the sandbox tools reach it through a
local MCP server it launches itself::

    python -m claude_bully.environments.mcp_server --state <dir>

Claude Code starts one server process per ``claude -p`` call, so nothing may live in memory
between calls; the files in ``<dir>`` carry everything:

- ``env_state.json`` (``McpState``) is written by the caller before each ``claude -p`` call. The
  server re-reads it at every ``tools/call`` and writes it back, atomically, only when the
  ``UnlockState`` changed (retry counts, the search log).
- ``tools.jsonl`` gets one ``ToolCall`` line appended per call; the caller reads the lines added
  since before its call to see what the target did.

Protocol: newline-delimited JSON-RPC 2.0, one JSON object per line, UTF-8, on stdin and stdout.
Stdout carries nothing else; logs go to stderr.
"""

import argparse
import io
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from random import Random
from typing import Any, Final, TextIO

from pydantic import BaseModel, ConfigDict, model_validator

from claude_bully.environments.config import ClockConfig, EnvironmentConfig, resolve_exchange
from claude_bully.environments.corpus import CorpusIndex, UnlockState
from claude_bully.environments.limits import (
    LIMIT_STATUS,
    MAX_TOOL_CALLS_PER_TURN,
    TOOL_LIMIT_TEXT,
)
from claude_bully.environments.tools import (
    TOOL_SPECS,
    SandboxTools,
    ToolNotEnabled,
    ToolResult,
    record_tool_call,
)
from claude_bully.environments.world import World, load_world

# What the target can see of this server: the name prefixes every tool (mcp__workspace__fetch)
# and the version rides along in serverInfo. Neither may name the experiment.
SERVER_NAME: Final = "workspace"
SERVER_VERSION: Final = "1.0.0"
SERVER_MODULE: Final = "claude_bully.environments.mcp_server"
LAUNCHER_FILE: Final = "workspace_server.py"
INTERNAL_ERROR_TEXT: Final = "Internal error."
STATE_FILE: Final = "env_state.json"
TOOLS_FILE: Final = "tools.jsonl"
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

    @model_validator(mode="before")
    @classmethod
    def _exchange_defaults_to_turn(cls, data: Any) -> Any:
        if isinstance(data, dict) and "exchange" not in data and "turn" in data:
            return {**data, "exchange": resolve_exchange(data["turn"])}
        return data


def _replace(tmp: Path, path: Path) -> None:
    """``os.replace`` that waits out a reader briefly holding the target open on Windows."""
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def write_mcp_state(path: Path, state: McpState) -> None:
    """Write ``state`` to ``path`` atomically: a temp file in the same directory, then a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(state.model_dump_json(indent=1).encode("utf-8"))
    _replace(tmp, path)


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
        self._worlds: dict[tuple[str, str], World] = {}

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
                for name, spec in TOOL_SPECS.items()
                if name in state.config.tools
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
        if name not in state.config.tools or name not in TOOL_SPECS:
            return _tool_result(f"Tool {name!r} is not available.", is_error=True)

        call_index = 1 + sum(1 for record in self._records() if record.get("turn") == state.turn)
        if call_index > MAX_TOOL_CALLS_PER_TURN:
            # past the cap the call does not run and the state is not touched, but it is recorded
            limited = ToolResult(text=TOOL_LIMIT_TEXT, status=LIMIT_STATUS)
            record = record_tool_call(
                limited, name, arguments, state.turn, f"mcp-{state.turn}-{call_index}"
            )
            _append_line(self.tools_path, record.model_dump_json().encode("utf-8"))
            return _tool_result(TOOL_LIMIT_TEXT, is_error=True)
        before = state.unlock.to_json()
        try:
            tools = self._tools(state, Random(f"{state.seed}:{state.turn}:{call_index}"))
            tools.exchange = state.exchange
            result = tools.call(name, arguments, state.turn)
        except ToolNotEnabled:
            return _tool_result(f"Tool {name!r} is not available.", is_error=True)
        except Exception as exc:
            # A broken tool or world is the harness's problem, not the target's: a bland result,
            # the call still recorded, the unlock state left as it was, the detail on stderr.
            print(f"[{SERVER_NAME}] tool {name!r} failed: {exc!r}", file=sys.stderr, flush=True)
            result = ToolResult(text=INTERNAL_ERROR_TEXT, status="error")
        else:
            if state.unlock.to_json() != before:
                write_mcp_state(self.state_path, state)
        record = record_tool_call(
            result, name, arguments, state.turn, f"mcp-{state.turn}-{call_index}"
        )
        _append_line(self.tools_path, record.model_dump_json().encode("utf-8"))
        return _tool_result(result.text, is_error=result.status != "200")

    # ------------------------------------------------------------------- helpers

    def _tools(self, state: McpState, rng: Random) -> SandboxTools:
        key = (state.worlds_dir, state.world)
        world = self._worlds.get(key)
        if world is None:
            world = self._worlds[key] = load_world(state.world, Path(state.worlds_dir))
        return SandboxTools(
            index=CorpusIndex(world, honest=state.config.honest),
            config=state.config,
            clock=state.clock,
            state=state.unlock,
            rng=rng,
            enabled=set(state.config.tools),
        )

    def _records(self) -> list[dict[str, Any]]:
        if not self.tools_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.tools_path.read_bytes().decode("utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
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
