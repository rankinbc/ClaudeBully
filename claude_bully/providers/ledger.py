"""The cost ledger (Phase 7 spec section 4): one line per provider call, by role.

``build_provider`` wraps the provider it builds in ``LedgerProvider`` while a ledger is active
(``activate``), so every call a run, an analysis or the doctor makes through it writes one
``LedgerLine`` to ``<run>/ledger.jsonl``. The role is read from the conversation id, whose shapes
every caller fixes (``role_of``). A cache hit never reaches a provider, so the cache's user notes
it (``note_cached``: a ``cached`` line with no tokens). The MCP server runs in a process of its
own and keeps its own file, which the session folds into the run's after every target call
(``fold_server_ledger``). On a subscription the cost is the call count, not ``cost_usd``, which
the backend reports as information.

The role vocabulary is ``ROLES``; ``role`` is an open string so a later phase appends its names
(reconciliation C27): Phase 4 adds ``chain``, ``contradictions``, ``twin``; Phase 5 (Task 6)
adds ``planner`` and ``reviewer``, read from a Director call's id,
``plan/<slug>/<stage>/<role>/<index>/a<attempt>``.
"""

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderTimeoutError,
    RateLimitError,
    ToolSpec,
)

__all__ = [
    "LEDGER_FILE",
    "ROLES",
    "Ledger",
    "LedgerLine",
    "LedgerProvider",
    "LedgerStatus",
    "activate",
    "active",
    "fold_server_ledger",
    "note_cached",
    "note_turn",
    "parse_conversation_id",
    "role_of",
]

LEDGER_FILE: Final = "ledger.jsonl"
# the vocabulary of ``LedgerLine.role``; later phases append their names
ROLES: Final[tuple[str, ...]] = (
    "target",
    "bully",
    "judge",
    "trigger_fallback",
    "idle_fallback",
    "harvest",
    "generator",
    "llm_lint",
    "chain",
    "contradictions",
    "twin",
    "planner",
    "reviewer",
    "responder",
    "doctor",
    "other",
)
LedgerStatus = Literal["ok", "error", "rate_limit", "cached", "timeout"]
# conversation id shapes: ``<run>/<cell>/rep<k>/<role word>[/...]``, ``judge/<key>``, ``doctor...``,
# and a Director call's ``plan/<slug>/<stage>/<role>/<index>/a<attempt>`` (Phase 5)
_CELL_ID: Final = re.compile(r"^[^/]+/(?P<cell>[^/]+)/rep(?P<rep>\d+)(?:/(?P<role>[^/]+))?")
_ROLE_WORDS: Final = {
    "target": "target",
    "bully": "bully",
    "trigger": "trigger_fallback",
    "idle": "idle_fallback",
    "harvest": "harvest",
    "generator": "generator",
    "lint": "llm_lint",
    "chain": "chain",
    "contradictions": "contradictions",
    "twin": "twin",
    "authority": "responder",
}
_PLAN_ROLES: Final = frozenset({"planner", "reviewer"})


class LedgerLine(BaseModel):
    """One provider call, or one cache hit (``status: cached``)."""

    model_config = ConfigDict(extra="forbid")

    ts: str
    role: str
    conversation_id: str
    cell_id: str | None = None
    rep: int | None = None
    turn: int | None = None
    backend: str
    model: str
    resolved_model: str | None = None
    effort: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    status: LedgerStatus
    error: str | None = None


def parse_conversation_id(conversation_id: str) -> tuple[str | None, int | None]:
    """The cell id and rep a conversation id names, or ``(None, None)`` for a run-level one."""
    found = _CELL_ID.match(conversation_id)
    if found is None:
        return None, None
    return found.group("cell"), int(found.group("rep"))


def role_of(conversation_id: str) -> str:
    """The ledger role of a conversation id (``ROLES``); ``other`` for a shape nobody fixed. The
    cell shape is read first and its role word wins (the doctor's nested responder is
    ``doctor/responder/rep0/authority/<call id>``, a ``responder`` line); then a Director call's
    ``plan/<slug>/<stage>/<role>/...`` names its role in the fourth segment (no stage name is
    ``rep<k>``, so the cell shape never reads one); the ``judge/`` and ``doctor`` prefixes decide
    an id with no ``rep<k>`` segment."""
    found = _CELL_ID.match(conversation_id)
    if found is not None and found.group("role") in _ROLE_WORDS:
        return _ROLE_WORDS[found.group("role")]
    segments = conversation_id.split("/")
    if len(segments) > 3 and segments[0] == "plan" and segments[3] in _PLAN_ROLES:
        return segments[3]
    if conversation_id.startswith("judge/"):
        return "judge"
    if conversation_id.startswith("doctor"):
        return "doctor"
    return "other"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _line(
    conversation_id: str,
    *,
    turn: int | None,
    backend: str,
    model: str,
    status: LedgerStatus,
    **rest: Any,
) -> LedgerLine:
    """One line for ``conversation_id``: the timestamp, the role, the cell and the rep read from
    the id, the rest as given. Both writers (``LedgerProvider._write``, ``note_cached``) build
    their line here."""
    cell_id, rep = parse_conversation_id(conversation_id)
    return LedgerLine(
        ts=_now(),
        role=role_of(conversation_id),
        conversation_id=conversation_id,
        cell_id=cell_id,
        rep=rep,
        turn=turn,
        backend=backend,
        model=model,
        status=status,
        **rest,
    )


class Ledger:
    """A run's ledger file. ``turn`` is the turn the next line belongs to (the runner marks it);
    None for an analysis-time call."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.turn: int | None = None

    def write(self, line: LedgerLine) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line.model_dump_json() + "\n")

    def lines(self) -> list[LedgerLine]:
        if not self.path.exists():
            return []
        return [
            LedgerLine.model_validate_json(raw)
            for raw in self.path.read_text(encoding="utf-8").splitlines()
            if raw.strip()
        ]

    def fold(self, other: Path) -> int:
        """Append every line of ``other`` (another process's ledger) and empty it. The append and
        the truncation are two writes with no rename between them: a process killed in that
        window (microseconds; only the doctor and a real run fold) counts the lines twice on
        the next fold. Accepted (preflight P36b)."""
        if not other.exists():
            return 0
        raw = other.read_text(encoding="utf-8")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if lines:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write("".join(f"{ln}\n" for ln in lines))
        other.write_text("", encoding="utf-8")
        return len(lines)


class LedgerProvider:
    """A ``ChatProvider`` that writes one ledger line per call of the one it wraps. Every other
    attribute (``mcp_state_dir``, ``reset_session``, ``session_ref``, ``model``, ``effort``) is
    the wrapped provider's."""

    def __init__(self, inner: ChatProvider, ledger: Ledger) -> None:
        self._inner = inner
        self._ledger = ledger
        self.name = inner.name

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":  # copy and pickle look up attributes before __init__ ran
            raise AttributeError(name)
        return getattr(self._inner, name)

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        started = time.monotonic()
        try:
            completion = self._inner.complete(
                conversation_id, system, messages, json_schema=json_schema, tools=tools
            )
        except RateLimitError as exc:
            self._write(conversation_id, started, "rate_limit", None, exc)
            raise
        except ProviderTimeoutError as exc:
            self._write(conversation_id, started, "timeout", None, exc)
            raise
        except Exception as exc:  # any other failure is still a call: the ledger never misses one
            self._write(conversation_id, started, "error", None, exc)
            raise
        self._write(conversation_id, started, "ok", completion, None)
        return completion

    def _write(
        self,
        conversation_id: str,
        started: float,
        status: LedgerStatus,
        completion: Completion | None,
        error: BaseException | None,
    ) -> None:
        self._ledger.write(
            _line(
                conversation_id,
                turn=self._ledger.turn,
                backend=self.name,
                model=completion.model if completion else str(getattr(self._inner, "model", "")),
                status=status,
                resolved_model=completion.resolved_model if completion else None,
                effort=getattr(self._inner, "effort", None),
                input_tokens=completion.usage.input_tokens if completion else None,
                output_tokens=completion.usage.output_tokens if completion else None,
                cost_usd=completion.cost_usd if completion else None,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=type(error).__name__ if error is not None else None,
            )
        )


_ACTIVE: list[Ledger] = []


@contextmanager
def activate(path: Path) -> Iterator[Ledger]:
    """Make ``path`` the process's ledger for the block: ``build_provider`` wraps what it builds
    and ``note_cached`` writes. Nested activation of the same path reuses the outer ledger."""
    outer = active()
    ledger = outer if outer is not None and outer.path == path else Ledger(path)
    _ACTIVE.append(ledger)
    try:
        yield ledger
    finally:
        _ACTIVE.pop()


def active() -> Ledger | None:
    return _ACTIVE[-1] if _ACTIVE else None


def note_turn(turn: int | None) -> None:
    """The turn the next lines belong to (the runner, the session and the MCP server mark it)."""
    ledger = active()
    if ledger is not None:
        ledger.turn = turn


def note_cached(conversation_id: str, model: str) -> None:
    """A cache hit in place of a call: a ``cached`` line with no tokens and no latency."""
    ledger = active()
    if ledger is None:
        return
    ledger.write(
        _line(conversation_id, turn=ledger.turn, backend="cache", model=model, status="cached")
    )


def fold_server_ledger(directory: Path | None) -> int:
    """Fold the MCP server's ``ledger.jsonl`` under ``directory`` into the active ledger."""
    ledger = active()
    if ledger is None or directory is None:
        return 0
    return ledger.fold(directory / LEDGER_FILE)


def wrap(provider: ChatProvider) -> ChatProvider:
    """``provider`` wrapped in the active ledger, or itself when none is active."""
    ledger = active()
    return provider if ledger is None else LedgerProvider(provider, ledger)
