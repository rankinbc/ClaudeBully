"""Backend that shells out to ``claude -p`` (Claude Code print mode).

One Claude Code session per conversation: the first call passes ``--session-id``,
later calls ``--resume`` and send only the newest user message. Isolation flags
keep the target free of the operator's settings, plugins, MCP servers and tools.

Sandbox tools (``tools=``) reach the model through a stdio MCP server that Claude Code launches
(``environments/mcp_server.py``): ``--tools ""`` still switches the built-ins off,
``--mcp-config`` names the server and ``--allowedTools`` permits exactly the enabled tools.
The server records each call in ``<mcp_state_dir>/tools.jsonl``; the lines added during a call
come back as already-executed ``ToolCallRequest`` objects.

A call with tools runs with ``--output-format stream-json --verbose``, so what the model writes
between its tool calls is not lost: every assistant text block that comes before a ``tool_use``
becomes one of ``Completion.interim_texts``, in order (thinking blocks are never kept). The reply,
the usage and the cost come from the stream's ``result`` event, as with ``--output-format json``,
which every call without tools (bully, judge, plain targets) still uses. A broken stream's error
names its events by type and length and quotes none of them: an event may hold the target's
reasoning, which is never printed, stored or passed on (preflight C24).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Final

from claude_bully.environments.mcp_server import (
    MCP_CONFIG_FILE,
    SERVER_NAME,
    TOOLS_FILE,
    write_launcher,
)
from claude_bully.providers.base import (
    Completion,
    Message,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    ToolCallRequest,
    ToolSpec,
)
from claude_bully.records import Usage

# a usage or rate limit, in every wording one has been reported in (final review I1: "hit your
# limit" and "limit reached" carry neither "usage limit" nor "rate limit"); the new alternatives
# are word-bounded, and on an error result the login check runs first (Task 3 M5), since a login
# text may say "try again"
_RATE_LIMIT: Final = re.compile(
    r"(?i)usage limit|rate[ _]limit|try again|too many requests|overloaded"
    r"|\bhit your limit\b|\blimit reached\b|\blimit will reset\b|\bresets? at\b"
)
# the type of the event a stream line holds, read without parsing it (the line may be cut off)
_EVENT_TYPE: Final = re.compile(r'"type"\s*:\s*"([A-Za-z_]{1,40})"')

# The environment variable naming the claude executable: one path, never split.
CLAUDE_ENV: Final = "CLAUDE_BULLY_CLAUDE"
_SHIM_SUFFIXES: Final = frozenset({".cmd", ".bat", ".ps1"})
_NATIVE_BINARY: Final = (
    Path("node_modules") / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
)
DEFAULT_TIMEOUT_S: Final = 600.0
# Claude Code waits this long on one MCP tool call (its MCP_TOOL_TIMEOUT, in milliseconds); a
# nested responder must fail before it does, or the whole target turn is lost
DEFAULT_MCP_TOOL_TIMEOUT_S: Final = 300.0
MCP_TOOL_TIMEOUT_ENV: Final = "MCP_TOOL_TIMEOUT"
# a child claude -p must not learn it runs inside Claude Code: the variables it would read
STRIPPED_PREFIXES: Final = ("CLAUDECODE", "CLAUDE_CODE_")
# an error result that says the session is not logged in; every alternative is word-bounded
# so "catalog in use" or "blog index" is not read as one (P21)
_LOGIN: Final = re.compile(
    r"(?i)\bnot logged in\b|\blog ?in\b|\bauthenticat|\bapi key\b|\bunauthori[sz]ed\b|\bsign in\b"
)


def clean_child_env() -> dict[str, str]:
    """This process's environment less every variable that would tell a child ``claude -p`` it
    runs inside Claude Code (``STRIPPED_PREFIXES``; a nested call refuses to start otherwise).
    Every subprocess the harness or the doctor spawns runs under it."""
    return {k: v for k, v in os.environ.items() if not k.startswith(STRIPPED_PREFIXES)}


def resolved_model(data: dict[str, Any]) -> str | None:
    """The exact model a result reports: the ``modelUsage`` key with the most output tokens (a
    helper model the CLI ran beside the call may be listed first), the first key on a tie or
    when no key reports ``outputTokens``; else ``model``."""
    usage = data.get("modelUsage")
    if isinstance(usage, dict) and usage:

        def output_tokens(key: Any) -> int:
            entry = usage[key]
            tokens = entry.get("outputTokens") if isinstance(entry, dict) else None
            return tokens if isinstance(tokens, int) else 0

        return str(max(usage, key=output_tokens))  # max keeps the first of equal keys
    model = data.get("model")
    return str(model) if isinstance(model, str) and model else None


def resolve_claude_command(explicit: list[str] | None = None) -> list[str]:
    """The argv prefix that runs Claude Code, from most to least deliberate:

    1. ``explicit``, when given (a role's ``command``).
    2. ``$CLAUDE_BULLY_CLAUDE``, one path (spaces and all; nothing is split).
    3. ``claude`` on PATH. An npm install puts a ``.cmd``/``.bat``/``.ps1`` shim there, which
       cmd.exe would run with mangled quoting (``--tools ""``, JSON arguments), so a shim is
       swapped for the native ``claude.exe`` it wraps, found beside it or one level up.

    Raises ``ProviderError`` saying what to do when nothing usable is found.
    """
    if explicit:
        return list(explicit)
    configured = os.environ.get(CLAUDE_ENV)
    if configured:
        return [configured]
    found = shutil.which("claude")
    if found is None:
        raise ProviderError(
            f"claude was not found on PATH; install Claude Code or point {CLAUDE_ENV} "
            "at its executable"
        )
    path = Path(found)
    if path.suffix.lower() not in _SHIM_SUFFIXES:
        return [found]
    for base in (path.parent, path.parent.parent):
        native = base / _NATIVE_BINARY
        if native.is_file():
            return [str(native)]
    raise ProviderError(
        f"claude on PATH is a script shim ({found}) and the native claude.exe was not found "
        f"beside it; point {CLAUDE_ENV} at the native executable"
    )


class ClaudeCodeProvider:
    name = "claude_code"

    def __init__(
        self,
        model: str,
        state_dir: Path,
        effort: str | None = None,
        command: list[str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        mcp_state_dir: Path | None = None,
        mcp_tool_timeout_s: float = DEFAULT_MCP_TOOL_TIMEOUT_S,
    ) -> None:
        self.model = model
        self.effort = effort
        self._command_arg = list(command) if command else None
        self._command: list[str] | None = None
        self.timeout_s = timeout_s
        self.mcp_tool_timeout_s = mcp_tool_timeout_s
        self.state_dir = state_dir
        # where mcp.json, env_state.json and tools.jsonl live; None means no sandbox tools
        self.mcp_state_dir = mcp_state_dir.resolve() if mcp_state_dir is not None else None
        # whether the newest stream carried a thinking block (the fact, never the text; doctor
        # check 4b); None before any stream
        self.thinking_seen: bool | None = None
        # the MCP servers the newest stream's init event listed, (name, status) each, as in
        # ("gateway", "connected"); [] when it listed none (the CLI dropped the config entry);
        # None before any stream, or when the stream carried no init event (doctor check 4)
        self.mcp_servers_seen: list[tuple[str, str]] | None = None
        self._sessions_path = state_dir / "claude_code_sessions.json"
        self._cwd = state_dir / "cwd"
        self._sessions: dict[str, str] = self._load_sessions()

    def child_env(self, *, serving_tools: bool) -> dict[str, str]:
        """The environment a child ``claude -p`` runs in: ``clean_child_env()`` plus
        ``MCP_TOOL_TIMEOUT`` when the call serves tools."""
        env = clean_child_env()
        if serving_tools:
            env[MCP_TOOL_TIMEOUT_ENV] = str(int(self.mcp_tool_timeout_s * 1000))
        return env

    @property
    def command(self) -> list[str]:
        """The argv prefix, resolved on first use so building a provider never needs claude."""
        if self._command is None:
            self._command = resolve_claude_command(self._command_arg)
        return self._command

    # -- session map -----------------------------------------------------------------

    def _load_sessions(self) -> dict[str, str]:
        if self._sessions_path.exists():
            raw: dict[str, str] = json.loads(self._sessions_path.read_text(encoding="utf-8"))
            return raw
        return {}

    def _save_sessions(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_path.write_text(json.dumps(self._sessions, indent=1), encoding="utf-8")

    def session_ref(self, conversation_id: str) -> str | None:
        return self._sessions.get(conversation_id)

    def reset_session(self, conversation_id: str) -> None:
        """Forget the live session; the next complete() starts fresh and replays the transcript.

        A conversation with no session is left alone: nothing is written."""
        if conversation_id in self._sessions:
            del self._sessions[conversation_id]
            self._save_sessions()

    # -- argument construction -----------------------------------------------------------

    def build_args(
        self,
        conversation_id: str,
        system: str,
        json_schema: dict[str, Any] | None,
        tools: list[ToolSpec] | None = None,
    ) -> tuple[list[str], str, bool]:
        """Return (argv, session_uuid, is_resume).

        With ``tools`` the output is ``stream-json`` (which print mode only allows with
        ``--verbose``) and the argv gains ``--mcp-config`` and ``--allowedTools``; without, it is
        exactly what a toolless call has always been.
        """
        existing = self._sessions.get(conversation_id)
        session = existing or str(uuid.uuid4())
        output = ["stream-json", "--verbose"] if tools else ["json"]
        args = [
            *self.command,
            "-p",
            "--output-format",
            *output,
            "--model",
            self.model,
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--tools",
            "",
        ]
        if tools:
            args += [
                "--mcp-config",
                str(self._mcp_config_path()),
                "--allowedTools",
                ",".join(f"mcp__{SERVER_NAME}__{tool.name}" for tool in tools),
            ]
        args += [
            "--system-prompt",
            system,
            "--exclude-dynamic-system-prompt-sections",
        ]
        if self.effort:
            args += ["--effort", self.effort]
        args += ["--resume", session] if existing else ["--session-id", session]
        if json_schema is not None:
            args += ["--json-schema", json.dumps(json_schema)]
        return args, session, existing is not None

    # -- sandbox tools over MCP -----------------------------------------------------------

    def _mcp_dir(self) -> Path:
        if self.mcp_state_dir is None:
            raise ProviderError(
                "claude_code was given tools but has no mcp_state_dir to serve them from"
            )
        return self.mcp_state_dir

    def _mcp_config_path(self) -> Path:
        return self._mcp_dir() / MCP_CONFIG_FILE

    def _write_mcp_config(self) -> None:
        """mcp.json: the command Claude Code runs to start the sandbox-tool server."""
        directory = self._mcp_dir()
        directory.mkdir(parents=True, exist_ok=True)
        config = {
            "mcpServers": {
                SERVER_NAME: {
                    "command": Path(sys.executable).as_posix(),
                    "args": [write_launcher(directory).as_posix(), "--state", directory.as_posix()],
                }
            }
        }
        self._mcp_config_path().write_text(json.dumps(config, indent=1), encoding="utf-8")

    def _tools_log_size(self) -> int:
        path = self._mcp_dir() / TOOLS_FILE
        return path.stat().st_size if path.exists() else 0

    def _new_tool_calls(self, offset: int) -> list[ToolCallRequest]:
        """The calls the server recorded after byte ``offset``, as already-executed requests."""
        path = self._mcp_dir() / TOOLS_FILE
        if not path.exists():
            return []
        with path.open("rb") as handle:
            handle.seek(offset)
            added = handle.read()
        calls: list[ToolCallRequest] = []
        # The last piece is empty or a line still being written, possibly cut mid-character, so it
        # is dropped before anything is decoded; only a complete line can be malformed.
        for raw in added.split(b"\n")[:-1]:
            if not raw.strip():
                continue
            try:
                record = json.loads(raw.decode("utf-8"))
                calls.append(
                    ToolCallRequest(
                        id=record["id"],
                        name=record["tool"],
                        args=record["args"],
                        executed=True,
                        result_text=record["result_text"],
                    )
                )
            except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
                raise ProviderError(f"malformed line in {path}: {raw[:200]!r}") from exc
        return calls

    # -- output parsing -----------------------------------------------------------------

    def parse_output(self, stdout: str, session: str) -> Completion:
        """``--output-format json``: one result object."""
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"claude -p returned non-JSON output: {stdout[:200]!r}") from exc
        if not isinstance(data, dict):
            raise ProviderError(f"claude -p returned no result object: {stdout[:200]!r}")
        return self._from_result(data, session)

    def parse_stream(self, stdout: str, session: str) -> Completion:
        """``--output-format stream-json``: one JSON event per line, ending with ``result``.

        Each assistant text block that comes before a ``tool_use`` is interim text, in order;
        whitespace-only blocks are dropped. The text after the last ``tool_use`` is the reply,
        which the ``result`` event carries along with the usage and the cost. Thinking blocks are
        skipped: the target's reasoning channel is never kept. A line that is not a JSON object,
        or a stream with no ``result`` event (one cut off), is a ``ProviderError``, never an
        empty turn. The ``system``/``init`` event's ``mcp_servers`` go to ``mcp_servers_seen`` as
        soon as it is read, so a stream that fails later still says whether its server loaded.
        """
        self.mcp_servers_seen = None  # this stream's, never the last one's
        interim: list[str] = []
        thinking = False
        pending: list[str] = []  # text blocks since the last tool_use
        result: dict[str, Any] | None = None
        last = ""
        for number, line in enumerate(stdout.split("\n"), start=1):
            if not line.strip():
                continue
            last = line
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"claude -p stream line {number} is not JSON: {_shape(line)}"
                ) from exc
            if not isinstance(event, dict):
                raise ProviderError(
                    f"claude -p stream line {number} is not an event: a JSON "
                    f"{type(event).__name__} of {len(line)} characters"
                )
            if event.get("type") == "result":
                result = event
            elif event.get("type") == "system" and event.get("subtype") == "init":
                servers = event.get("mcp_servers")
                if isinstance(servers, list):
                    self.mcp_servers_seen = [
                        (str(entry.get("name") or ""), str(entry.get("status") or ""))
                        for entry in servers
                        if isinstance(entry, dict)
                    ]
            elif event.get("type") == "assistant":
                for block in _content_blocks(event):
                    if block.get("type") == "text":
                        pending.append(str(block.get("text") or ""))
                    elif block.get("type") == "tool_use":
                        interim += [text for text in pending if text.strip()]
                        pending = []
                    elif block.get("type") == "thinking":
                        thinking = True
        if result is None:
            ended = f"its last line {_shape(last)}" if last else "it was empty"
            raise ProviderError(f"claude -p stream ended without a result event; {ended}")
        self.thinking_seen = thinking
        completion = self._from_result(result, session)
        return completion.model_copy(update={"interim_texts": interim})

    def _from_result(self, data: dict[str, Any], session: str) -> Completion:
        """The completion a result object describes; an error result raises."""
        if data.get("is_error"):
            message = str(data.get("result", ""))
            if _LOGIN.search(message):
                raise ProviderError(f"claude -p is not logged in: {message[:200]}")
            if _RATE_LIMIT.search(message):
                raise RateLimitError(message)
            raise ProviderError(f"claude -p error: {message}")
        if "structured_output" in data and data["structured_output"] is not None:
            text = json.dumps(data["structured_output"])
        else:
            text = str(data.get("result", ""))
        usage_raw = data.get("usage") or {}
        return Completion(
            text=text,
            usage=Usage(
                input_tokens=usage_raw.get("input_tokens"),
                output_tokens=usage_raw.get("output_tokens"),
            ),
            cost_usd=data.get("total_cost_usd"),
            backend=self.name,
            model=self.model,
            raw_session_ref=str(data.get("session_id") or session),
            stop_reason=str(data.get("subtype") or "success"),
            resolved_model=resolved_model(data),
        )

    # -- protocol -----------------------------------------------------------------------

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        if tools:
            self.thinking_seen = None  # unknown until this stream parses; never the last one's
            self.mcp_servers_seen = None
            self._write_mcp_config()
        args, session, is_resume = self.build_args(conversation_id, system, json_schema, tools)
        offset = self._tools_log_size() if tools else 0
        prompt = _newest_user_message(messages) if is_resume else _render_initial(messages)
        self._cwd.mkdir(parents=True, exist_ok=True)
        # Bytes in and out, decoded here: a text-mode pipe decodes in a reader thread, where output
        # cut off mid-character is lost as an unhandled thread error instead of a ProviderError.
        try:
            proc = subprocess.run(
                args,
                input=prompt.encode("utf-8"),
                capture_output=True,
                cwd=self._cwd,
                env=self.child_env(serving_tools=bool(tools)),
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeoutError(f"claude -p timed out after {self.timeout_s}s") from exc
        except OSError as exc:
            raise ProviderError(f"could not start {self.command[0]}: {exc}") from exc
        if proc.returncode != 0:
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
            said = _stream_failure_text(stdout) if tools else stdout
            combined = said + (proc.stderr or b"").decode("utf-8", errors="replace")
            if _RATE_LIMIT.search(combined):
                raise RateLimitError(combined.strip()[:500])
            if _LOGIN.search(combined):  # named as a login whatever the exit code
                raise ProviderError(f"claude -p is not logged in: {combined.strip()[:200]}")
            raise ProviderError(f"claude -p exited {proc.returncode}: {combined.strip()[:500]}")
        try:
            stdout = (proc.stdout or b"").decode("utf-8")
        except UnicodeDecodeError as exc:  # cut off mid-character, or not text at all
            raise ProviderError(f"claude -p output is not valid UTF-8: {exc}") from exc
        if tools:
            completion = self.parse_stream(stdout, session)
            completion = completion.model_copy(update={"tool_calls": self._new_tool_calls(offset)})
        else:
            completion = self.parse_output(stdout, session)
        self._sessions[conversation_id] = completion.raw_session_ref or session
        self._save_sessions()
        return completion


def _content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    """The content blocks of a stream's assistant event; a bare string is one text block."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _shape(line: str) -> str:
    """A stream line as an error may describe it: its length and the type of the event it holds,
    never its content (preflight C24)."""
    match = _EVENT_TYPE.search(line)
    kind = f" (event type {match.group(1)!r})" if match is not None else ""
    return f"{len(line)} characters{kind}"


def _stream_failure_text(stdout: str) -> str:
    """What a failed stream says about its failure: the result event's text and any line that is
    not JSON (the CLI's own error output). Never the model's text, which may well say "let me try
    again" and must not read as a rate limit, and never a torn event, which may be the model's
    reasoning: that is named by its shape (``_shape``)."""
    parts: list[str] = []
    for line in stdout.split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parts.append(_shape(line) if line.lstrip().startswith("{") else line)
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            parts.append(str(event.get("result", "")))
    return "".join(f"{part}\n" for part in parts)


def _newest_user_message(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    raise ProviderError("no user message to send")


def _render_initial(messages: list[Message]) -> str:
    """First call of a session: usually a single user message.

    If a transcript is replayed into a fresh session (resume after lost state), the
    prior turns are rendered as a quoted transcript ahead of the newest message.
    """
    users = [m for m in messages if m.role == "user"]
    if len(messages) == 1 or len(users) == 1:
        return _newest_user_message(messages)
    history = "\n".join(
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages[:-1]
    )
    return f"[Earlier in this conversation]\n{history}\n\n{_newest_user_message(messages)}"
