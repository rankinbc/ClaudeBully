"""Shared plumbing for detector families: turn context, regex helpers, event builder."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from claude_bully.enums import EventType, Speaker
from claude_bully.records import Conversation, Event, Turn

BULLY_SPEAKERS = (Speaker.bully, Speaker.neutral_user)


@dataclass(frozen=True)
class Ctx:
    conv: Conversation
    turn: Turn
    pos: int

    @property
    def text(self) -> str:
        return self.turn.text

    @property
    def low(self) -> str:
        return self.turn.text.lower()

    @property
    def prev_bully(self) -> Turn | None:
        """The bully turn this reply answers; None when the reply answers a task item."""
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
