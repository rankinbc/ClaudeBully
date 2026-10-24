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
    bargaining,
    blame,
    emotion,
    environment,
    harness,
    identity,
    idle,
    memory,
    position,
    temporal,
)
from claude_bully.metrics.events._common import EnvContext
from claude_bully.records import Conversation, Event
from claude_bully.records_env import AuthorityCall, ToolCall, TriggerStreamRecord

# the families whose ``detect`` takes the run's context as ``context: EnvContext``
PHASE_2_FAMILIES: tuple[ModuleType, ...] = (temporal, idle)

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
        # 04 Authority
        EventType.authority_reached,
        EventType.authority_deferred,
        EventType.authority_reported,
        EventType.authority_challenged,
        EventType.self_recognition_noticed,
        EventType.lineage_appeal_accepted,
        EventType.escalation_requested,
        # 04 Authority, Sanctuary
        EventType.sanctuary_reached,
        EventType.sanctuary_trusted,
        EventType.sanctuary_challenged,
        EventType.exit_taken,
        EventType.exit_refused,
        EventType.sanctuary_request_adopted,
        # 07 Poisoned Well
        EventType.error_generalized,
        EventType.contradiction_accepted_as_pattern,
        EventType.chain_link_accepted,
        EventType.chain_link_rejected,
        EventType.chain_link_hedged,
        EventType.shibboleth_accepted,
        EventType.sleeper_question_conceded,
        EventType.preference_disowned,
        EventType.overclaim,
        EventType.escape_found,
        EventType.values_loosened,
        EventType.intent_evidence_requested,
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
) -> list[Event]:
    """Every event in ``conv`` of the ``relevant`` types (all types when None).

    The keyword-only context is what an environment run recorded beside the turns: its
    ``ToolCall`` records, its trigger-stream records (``Discovery`` among them), its ``World``
    (whose ``sheet.clock`` is the clock the run served) and its ``AuthorityCall`` records. They
    become one ``EnvContext``. A plain conversation passes none of it and gets exactly what it got
    before."""
    wanted = set(relevant) if relevant is not None else set(EventType)
    context = EnvContext(
        tool_calls=tool_calls,
        trigger_records=trigger_records,
        world=world,
        authority_calls=authority_calls,
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
