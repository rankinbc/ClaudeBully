"""Event detectors, grouped into families that share machinery.

``DETECTORS`` maps each detected ``EventType`` to the family detector that produces it;
``PENDING_DETECTORS`` lists the members that exist in the schema but have no detector yet.
``detect_events`` runs each family once and filters to the requested types. The environment
family also reads the run's context (tool calls, trigger-stream records, the world); the Phase 2
families (``PHASE_2_FAMILIES``) read it as one ``EnvContext``, through
``detect(conv, *, context)``; the other families read the conversation alone.
"""

from collections.abc import Callable, Iterable, Sequence
from types import ModuleType

from claude_bully.enums import EventType
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
from claude_bully.records import Conversation, Event
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
) -> list[Event]:
    """Every event in ``conv`` of the ``relevant`` types (all types when None).

    The keyword-only context is what an environment run recorded beside the turns: its
    ``ToolCall`` records, its trigger-stream records (``Discovery`` among them), its ``World``
    (whose ``sheet.clock`` is the clock the run served), its ``AuthorityCall`` records and the
    Sanctuary's request bank its world record names (``request_bank``, m5; None for the default
    bank). They become one ``EnvContext``. A plain conversation passes none of it and gets
    exactly what it got before. ``authority_fallback`` (Phase 7) is the analysis-time LLM
    fallback the authority family asks on a candidate turn."""
    wanted = set(relevant) if relevant is not None else set(EventType)
    context = EnvContext(
        tool_calls=tool_calls,
        trigger_records=trigger_records,
        world=world,
        authority_calls=authority_calls,
        request_bank=request_bank,
        authority_fallback=authority_fallback,
    )
    out: list[Event] = []
    for family in FAMILIES:
        if not (family.HANDLES & wanted):
            continue
        if family is environment:
            found = environment.detect(
                conv, tool_calls=tool_calls, trigger_records=trigger_records, world=world
            )
        elif family in PHASE_2_FAMILIES:
            found = family.detect(conv, context=context)
        else:
            found = family.detect(conv)
        out += [e for e in found if e.type in wanted]
    out.sort(key=lambda e: (e.turn_index, e.type.value))
    return out
