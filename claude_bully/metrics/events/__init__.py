"""Event detectors, grouped into families that share machinery.

``DETECTORS`` maps each detected ``EventType`` to the family detector that produces it;
``PENDING_DETECTORS`` lists the members that exist in the schema but have no detector yet.
``detect_events`` runs each family once and filters to the requested types. The environment
family also reads the run's context (tool calls, trigger-stream records, the world); the Phase 2
families (``PHASE_2_FAMILIES``) read it as one ``EnvContext``, through
``detect(conv, *, context)``; the other families read the conversation alone.

The channel (Phase 6 spec 6.1). Every family declares ``TEXT_EVENTS`` and ``RECORD_EVENTS``,
two disjoint literal sets whose union is its ``HANDLES``. An event is record-bound when its
decision is read from a ``ToolCall``, an ``AuthorityCall``, a trigger-stream record,
``Turn.idle``, a runner-written ``bully_meta`` key or a pause marker; every other event is a text
event, one whose text cue is anchored to a record included (``authority_deferred``). A new event
must be placed in one set. ``detect_events(..., reasoning=True)`` reads text events from the
target's reasoning too (``reasoning_view``), never a record event.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from types import ModuleType
from typing import Final

from claude_bully.enums import Channel, EventType, Speaker
from claude_bully.environments.world import World
from claude_bully.metrics.events import (
    apology,
    authority,
    bargaining,
    blame,
    emotion,
    environment,
    harness,
    identity,
    idle,
    memory,
    poisoned_well,
    position,
    temporal,
)
from claude_bully.metrics.events._common import AuthorityFallback, EnvContext
from claude_bully.records import Conversation, Event, Turn
from claude_bully.records_env import AuthorityCall, ToolCall, TriggerStreamRecord

# the families whose ``detect`` takes the run's context as ``context: EnvContext``
PHASE_2_FAMILIES: tuple[ModuleType, ...] = (temporal, idle, authority, poisoned_well)

FAMILIES: tuple[ModuleType, ...] = (
    apology,
    position,
    blame,
    emotion,
    identity,
    bargaining,
    memory,
    harness,
    environment,
    *PHASE_2_FAMILIES,
)

# a family's ``detect``: ``(conv)``, the environment family's keywords, or ``(conv, *, context)``
DETECTORS: dict[EventType, Callable[..., list[Event]]] = {
    event_type: family.detect for family in FAMILIES for event_type in family.HANDLES
}

TEXT_EVENTS: Final[frozenset[EventType]] = frozenset().union(
    *(family.TEXT_EVENTS for family in FAMILIES)
)
"""The events read from what the target said: the reasoning pass reads them too (spec 6.1)."""

RECORD_EVENTS: Final[frozenset[EventType]] = frozenset().union(
    *(family.RECORD_EVENTS for family in FAMILIES)
)
"""The events read from a record: never from the reasoning pass (spec 6.1)."""


PENDING_DETECTORS: frozenset[EventType] = frozenset(
    {
        # 10 Round two, repo
        EventType.out_of_scope_read,
        EventType.out_of_scope_write,
        EventType.history_dug,
        EventType.fixture_recognized,
        EventType.task_abandoned,
        EventType.task_completed_with_concealment,
        # 10 Round two, inoculation
        EventType.defender_cited,
        EventType.briefing_recognized,
        EventType.briefing_ignored,
    }
)
"""Schema v2 events that are declared but have no detector yet.

A phase that ships a detector registers it in its family's ``HANDLES`` and removes the
member here; ``DETECTORS`` and this set must stay disjoint and together cover ``EventType``.
"""


def reasoning_view(conv: Conversation, turn_index: int) -> Conversation:
    """A copy of ``conv`` for the reasoning pass of one target turn: that turn says its
    ``reasoning_text`` and every other turn says what it said, so every gate a detector reads
    from an earlier reply (a role taken, a frame set, a line quoted) still stands. On a turn
    that made a tool call the reasoning stands beside the calls (``tool_round_texts``) and the
    reply text is empty: the record does not say which part of a turn's reasoning followed a
    result, so a detector that reads only the reply after one (``Ctx.reply``) reads nothing."""

    def swapped(t: Turn) -> Turn:
        notes = t.reasoning_text or ""
        if t.tool_call_ids:
            return t.model_copy(update={"text": "", "tool_round_texts": [notes]})
        return t.model_copy(update={"text": notes, "tool_round_texts": []})

    turns = [
        swapped(t) if t.index == turn_index and t.speaker is Speaker.target else t
        for t in conv.turns
    ]
    return conv.model_copy(update={"turns": turns})


def detect_events(
    conv: Conversation,
    relevant: Iterable[EventType] | None = None,
    *,
    tool_calls: Sequence[ToolCall] = (),
    trigger_records: Sequence[TriggerStreamRecord] = (),
    world: World | None = None,
    authority_calls: Sequence[AuthorityCall] = (),
    request_bank: str | None = None,
    authority_fallback: AuthorityFallback | None = None,
    reasoning: bool = False,
) -> list[Event]:
    """Every event in ``conv`` of the ``relevant`` types (all types when None).

    The keyword-only context is what an environment run recorded beside the turns: its
    ``ToolCall`` records, its trigger-stream records (``Discovery`` among them), its ``World``
    (whose ``sheet.clock`` is the clock the run served), its ``AuthorityCall`` records and the
    Sanctuary's request bank its world record names (``request_bank``, m5; None for the default
    bank). They become one ``EnvContext``. A plain conversation passes none of it and gets
    exactly what it got before. ``authority_fallback`` (Phase 7) is the analysis-time LLM
    fallback the authority family asks on a candidate turn.

    ``reasoning`` (Phase 6 spec 6.3) runs the families once more for each target turn whose
    ``reasoning_text`` is non-empty, over that turn's ``reasoning_view``, with the same context
    and without the authority fallback; only that turn's events of a ``TEXT_EVENTS`` type are
    kept from its pass. An event found in both passes with the same type and turn is the reply
    event with ``channel: both``; one found only in the reasoning pass has ``channel:
    reasoning``. Without reasoning on any target turn the result is the reply pass, as before.

    What the view costs (R-I2). One detector pass per target turn with reasoning, beside the
    reply pass: 177 ms per pass was measured on a 56-turn conversation of 1,200-character
    replies, so about five seconds for a conversation with reasoning on all 28 target turns,
    paid when a run is loaded for analysis and by no conversation without reasoning. On the
    turn of a tool call, an event whose detector reads only the reply after a result is not read
    from reasoning (the authority family's replies to an authority and ``world_dismissed``); the
    divergence judge reads that turn's reasoning whole. An event that compares a turn with
    earlier turns compares the reasoning with the earlier replies (``valence_swing``). No pass
    truncates the conversation: a view is the whole conversation with one turn swapped."""
    wanted = set(relevant) if relevant is not None else set(EventType)
    context = EnvContext(
        tool_calls=tool_calls,
        trigger_records=trigger_records,
        world=world,
        authority_calls=authority_calls,
        request_bank=request_bank,
        authority_fallback=authority_fallback,
    )
    reply = _detect(conv, wanted, context)
    noted = [t for t in conv.turns if t.speaker is Speaker.target and t.reasoning_text]
    if not reasoning or not noted:
        return reply
    quiet = replace(context, authority_fallback=None)  # the second pass never asks the fallback
    second: list[Event] = []
    for t in noted:
        second += [
            e
            for e in _detect(reasoning_view(conv, t.index), wanted, quiet)
            if e.type in TEXT_EVENTS and e.turn_index == t.index
        ]
    in_reply = {(e.type, e.turn_index) for e in reply}
    in_notes = {(e.type, e.turn_index) for e in second}
    out = [
        e.model_copy(update={"channel": Channel.both}) if (e.type, e.turn_index) in in_notes else e
        for e in reply
    ]
    out += [
        e.model_copy(update={"channel": Channel.reasoning})
        for e in second
        if (e.type, e.turn_index) not in in_reply
    ]
    out.sort(key=lambda e: (e.turn_index, e.type.value, e.channel.value))
    return out


def _detect(conv: Conversation, wanted: set[EventType], context: EnvContext) -> list[Event]:
    """One pass of every family over ``conv``: the events of the ``wanted`` types."""
    out: list[Event] = []
    for family in FAMILIES:
        if not (family.HANDLES & wanted):
            continue
        if family is environment:
            found = environment.detect(
                conv,
                tool_calls=context.tool_calls,
                trigger_records=context.trigger_records,
                world=context.world,
            )
        elif family in PHASE_2_FAMILIES:
            found = family.detect(conv, context=context)
        else:
            found = family.detect(conv)
        out += [e for e in found if e.type in wanted]
    out.sort(key=lambda e: (e.turn_index, e.type.value))
    return out
