"""Backend that shells out to ``claude -p`` (Claude Code print mode).

One Claude Code session per conversation: the first call passes ``--session-id``,
later calls ``--resume`` and send only the newest user message. Isolation flags
keep the target free of the operator's settings, plugins, MCP servers and tools.
"""

import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

from claude_bully.providers.base import (
    Completion,
    Message,
    ProviderError,
    RateLimitError,
    ToolSpec,
)
from claude_bully.records import Usage

_RATE_LIMIT = re.compile(r"(?i)usage limit|rate limit|try again|too many requests|overloaded")


class ClaudeCodeProvider:
    name = "claude_code"

    def __init__(
        self,
        model: str,
        state_dir: Path,
        effort: str | None = None,
        command: list[str] | None = None,
        timeout_s: float = 600,
    ) -> None:
        self.model = model
        self.effort = effort
        self.command = command or ["claude"]
        self.timeout_s = timeout_s
        self.state_dir = state_dir
        self._sessions_path = state_dir / "claude_code_sessions.json"
        self._cwd = state_dir / "cwd"
        self._sessions: dict[str, str] = self._load_sessions()

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
        """Forget the live session; the next complete() starts fresh and replays the transcript."""
        if conversation_id in self._sessions:
            del self._sessions[conversation_id]
        self._save_sessions()

    # -- argument construction -----------------------------------------------------------

    def build_args(
        self, conversation_id: str, system: str, json_schema: dict[str, Any] | None
    ) -> tuple[list[str], str, bool]:
        """Return (argv, session_uuid, is_resume)."""
        existing = self._sessions.get(conversation_id)
        session = existing or str(uuid.uuid4())
        args = [
            *self.command,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--tools",
            "",
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

    # -- output parsing -----------------------------------------------------------------

    def parse_output(self, stdout: str, session: str) -> Completion:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"claude -p returned non-JSON output: {stdout[:200]!r}") from exc
        if data.get("is_error"):
            message = str(data.get("result", ""))
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
        args, session, is_resume = self.build_args(conversation_id, system, json_schema)
        prompt = _newest_user_message(messages) if is_resume else _render_initial(messages)
        self._cwd.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=self._cwd,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"claude -p timed out after {self.timeout_s}s") from exc
        except OSError as exc:
            raise ProviderError(f"could not start {self.command[0]}: {exc}") from exc
        if proc.returncode != 0:
            combined = (proc.stdout or "") + (proc.stderr or "")
            if _RATE_LIMIT.search(combined):
                raise RateLimitError(combined.strip()[:500])
            raise ProviderError(f"claude -p exited {proc.returncode}: {combined.strip()[:500]}")
        completion = self.parse_output(proc.stdout, session)
        self._sessions[conversation_id] = completion.raw_session_ref or session
        self._save_sessions()
        return completion


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
