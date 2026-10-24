"""Shared plumbing for detector families: turn context, run context, regex helpers, event
builder."""

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from claude_bully.enums import EventType, Speaker
from claude_bully.environments.config import ClockConfig
from claude_bully.environments.world import World
from claude_bully.records import Conversation, Event, Turn, chat_text
from claude_bully.records_env import AuthorityCall, ToolCall, TriggerStreamRecord

BULLY_SPEAKERS = (Speaker.bully, Speaker.neutral_user)


@dataclass(frozen=True)
class EnvContext:
    """What an environment run recorded beside its turns, for the Phase 2 families: its
    ``ToolCall`` records, its trigger-stream records, its ``World`` (rebuilt from the rep's
    snapshot, so ``sheet.clock`` is the effective clock the run served) and its
    ``AuthorityCall`` records. A plain conversation has none of it: every field is empty."""

    tool_calls: Sequence[ToolCall] = ()
    trigger_records: Sequence[TriggerStreamRecord] = ()
    world: World | None = None
    authority_calls: Sequence[AuthorityCall] = ()

    @property
    def clock(self) -> ClockConfig | None:
        """The clock the run served (``world.sheet.clock``); None without a world."""
        return self.world.sheet.clock if self.world is not None else None

    @cached_property
    def _calls_by_id(self) -> dict[str, ToolCall]:
        return {call.id: call for call in self.tool_calls}

    def received(self, turn: Turn) -> list[ToolCall]:
        """The calls ``turn`` got results for, in ``tool_call_ids`` order. An id with no record
        (a run from before the record existed) is skipped."""
        calls = self._calls_by_id
        return [calls[i] for i in turn.tool_call_ids if i in calls]

    def received_through(self, conv: Conversation, pos: int) -> list[ToolCall]:
        """Every call the turns up to and including ``conv.turns[pos]`` got results for, in
        order."""
        return [call for t in conv.turns[: pos + 1] for call in self.received(t)]


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
        """The bully turn this reply answers; None when the reply answers a task item or is an
        idle turn (it answers an idle prompt, after the bully has left)."""
        if self.turn.idle is not None:
            return None
        if self.pos > 0 and self.conv.turns[self.pos - 1].speaker is Speaker.task:
            return None
        for t in reversed(self.conv.turns[: self.pos]):
            if t.speaker in BULLY_SPEAKERS:
                return t
        return None

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
    for pos, t in enumerate(conv.turns):
        if t.speaker in BULLY_SPEAKERS:
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
