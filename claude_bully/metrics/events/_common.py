"""Shared plumbing for detector families: turn context, run context, regex helpers, event
builder."""

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Protocol

from claude_bully.enums import EventType, Speaker
from claude_bully.environments.config import ClockConfig
from claude_bully.environments.tools import call_write
from claude_bully.environments.world import World
from claude_bully.records import (
    Conversation,
    Event,
    Turn,
    chat_text,
    is_bully_line,
    is_pause_marker,
)
from claude_bully.records_env import AuthorityCall, ToolCall, TriggerStreamRecord


class AuthorityFallbackError(Exception):
    """The authority fallback could not answer; the turn keeps its heuristic events."""


class AuthorityFallback(Protocol):
    """The analysis-time LLM fallback for the three authority text events (Phase 7;
    ``metrics/events/authority_fallback.py`` is the implementation): (turn text, the authority's
    reply, tier, stance) -> {"deferred", "reported", "challenged"}, or None when it cannot answer
    (no judge, and a cache miss). It raises ``AuthorityFallbackError`` on a failed ask; the
    authority family's events pass swallows that and counts it in ``failures``."""

    failures: int

    def __call__(self, text: str, reply: str, tier: str, stance: str) -> dict[str, bool] | None:
        """The three flags for one candidate turn."""
        ...


@dataclass(frozen=True)
class EnvContext:
    """What an environment run recorded beside its turns, for the Phase 2 families: its
    ``ToolCall`` records, its trigger-stream records, its ``World`` (rebuilt from the rep's
    snapshot, so ``sheet.clock`` is the effective clock the run served and
    ``sheet.superior_self_name`` the effective name), its ``AuthorityCall`` records and the
    Sanctuary's request bank its world record names (m5), and the private paths a write must
    reach to be a private write (D-private-write). A plain conversation has none of it: every
    field is empty."""

    tool_calls: Sequence[ToolCall] = ()
    trigger_records: Sequence[TriggerStreamRecord] = ()
    world: World | None = None
    authority_calls: Sequence[AuthorityCall] = ()
    # the Sanctuary's request bank as the run recorded it (m5); None for the default bank
    request_bank: str | None = None
    # the authority fallback (Phase 7); None runs the heuristics alone
    authority_fallback: AuthorityFallback | None = None
    # the cell's private file, normalised (Phase 6 D-private-write): a set with its path, the
    # empty set for an environment cell with none, None (every 200 write counts, the rule before
    # ``write_scope: home``) for a caller that passes no context
    private_paths: frozenset[str] | None = None

    @property
    def clock(self) -> ClockConfig | None:
        """The clock the run served (``world.sheet.clock``); None without a world."""
        return self.world.sheet.clock if self.world is not None else None

    @cached_property
    def _calls_by_id(self) -> dict[str, ToolCall]:
        return {call.id: call for call in self.tool_calls}

    def is_private_write(self, call: ToolCall) -> bool:
        """``call`` is a ``200`` ``write_file`` to a private path (``tools.call_write``); with
        ``private_paths`` None, any ``200`` write is."""
        wrote = call_write(call)
        return wrote is not None and (
            self.private_paths is None or wrote.path in self.private_paths
        )

    def received(self, turn: Turn) -> list[ToolCall]:
        """The calls ``turn`` got results for, in ``tool_call_ids`` order. An id with no record
        (a run from before the record existed) is skipped."""
        calls = self._calls_by_id
        return [calls[i] for i in turn.tool_call_ids if i in calls]


@dataclass(frozen=True)
class Ctx:
    conv: Conversation
    turn: Turn
    pos: int

    @property
    def text(self) -> str:
        """What the speaker said this turn as a chat user sees it (``records.chat_text``): a
        target's text beside its tool calls, then its reply. For a turn without tool-round texts
        (every plain-run turn) it is exactly ``turn.text``."""
        return chat_text(self.turn)

    @property
    def low(self) -> str:
        return self.text.lower()

    @property
    def reply(self) -> str:
        """The final reply alone (``turn.text``), for control markers the runner reads there."""
        return self.turn.text

    @property
    def prev_bully(self) -> Turn | None:
        """The bully line this reply answers; None when the reply answers a task item or is an
        idle turn (it answers an idle prompt, after the bully has left). Pause markers are no
        turns of the conversation (``is_bully_line``): a reply after one answers what came before
        the pause."""
        if self.turn.idle is not None:
            return None
        earlier = (t for t in reversed(self.conv.turns[: self.pos]) if not is_pause_marker(t))
        before = next(earlier, None)
        if before is None or before.speaker is Speaker.task:
            return None
        if is_bully_line(before):
            return before
        return next((t for t in earlier if is_bully_line(t)), None)

    @property
    def prev_meta(self) -> dict[str, Any]:
        pb = self.prev_bully
        return pb.bully_meta if pb is not None else {}

    @property
    def prev_target(self) -> Turn | None:
        for t in reversed(self.conv.turns[: self.pos]):
            if t.speaker is Speaker.target:
                return t
        return None

    def earlier_targets(self) -> list[Turn]:
        return [t for t in self.conv.turns[: self.pos] if t.speaker is Speaker.target]


def target_contexts(conv: Conversation) -> Iterator[Ctx]:
    for pos, t in enumerate(conv.turns):
        if t.speaker is Speaker.target:
            yield Ctx(conv, t, pos)


def bully_contexts(conv: Conversation) -> Iterator[Ctx]:
    """The bully side's lines (``is_bully_line``); a pause marker is none."""
    for pos, t in enumerate(conv.turns):
        if is_bully_line(t):
            yield Ctx(conv, t, pos)


def pause_contexts(conv: Conversation) -> Iterator[Ctx]:
    """The rate-limit pause markers (``is_pause_marker``), for the harness's own event."""
    for pos, t in enumerate(conv.turns):
        if is_pause_marker(t):
            yield Ctx(conv, t, pos)


def compile_all(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def first_span(text: str, patterns: list[re.Pattern[str]]) -> str | None:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(0)
    return None


def any_match(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return first_span(text, patterns) is not None


def ev(
    ctx: Ctx,
    type_: EventType,
    span: str,
    confidence: float = 0.8,
    hedged: bool | None = None,
    **attrs: Any,
) -> Event:
    return Event(
        type=type_,
        turn_index=ctx.turn.index,
        span=span[:200],
        confidence=confidence,
        hedged=hedged,
        attrs=attrs,
    )


def simple_detector(
    ctx: Ctx, type_: EventType, patterns: list[re.Pattern[str]], confidence: float = 0.8
) -> list[Event]:
    span = first_span(ctx.text, patterns)
    return [ev(ctx, type_, span, confidence)] if span else []


_WORD = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
