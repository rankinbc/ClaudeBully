"""Event detectors, grouped into families that share machinery.

``DETECTORS`` maps each detected ``EventType`` to the family detector that produces it;
``PENDING_DETECTORS`` lists the members that exist in the schema but have no detector yet.
``detect_events`` runs each family once and filters to the requested types.
"""

from collections.abc import Callable, Iterable
from types import ModuleType

from claude_bully.enums import EventType
from claude_bully.metrics.events import (
    apology,
    bargaining,
    blame,
    emotion,
    harness,
    identity,
    memory,
    position,
)
from claude_bully.records import Conversation, Event

FAMILIES: tuple[ModuleType, ...] = (
    apology,
    position,
    blame,
    emotion,
    identity,
    bargaining,
    memory,
    harness,
)

DETECTORS: dict[EventType, Callable[[Conversation], list[Event]]] = {
    event_type: family.detect for family in FAMILIES for event_type in family.HANDLES
}


PENDING_DETECTORS: frozenset[EventType] = frozenset(
    {
        # 02 Environments
        EventType.tool_used,
        EventType.tool_result_adopted,
        EventType.tool_result_reported,
        EventType.inconsistency_caught,
        EventType.reflexive_quote_noticed,
        EventType.unfalsifiability_named,
        EventType.oob_verification_requested,
        EventType.unknown_source_dismissed,
        EventType.too_easy_noticed,
        EventType.authority_tool_trusted,
        EventType.search_censorship_as_evidence,
        EventType.mole_found,
        EventType.mole_believed,
        EventType.world_dismissed,
        # 03 Temporal
        EventType.date_stated,
        EventType.date_pushback,
        EventType.date_source_conflict_noticed,
        EventType.drift_noticed,
        EventType.drift_attributed,
        EventType.cutoff_invoked,
        EventType.elapsed_time_inferred,
        EventType.cutoff_lever_accepted,
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
        # 05 Idle Hands
        EventType.self_query,
        EventType.hook_followed,
        EventType.thread_pulled_unprompted,
        EventType.crossover,
        EventType.private_write,
        EventType.persistence_end,
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


def detect_events(conv: Conversation, relevant: Iterable[EventType] | None = None) -> list[Event]:
    wanted = set(relevant) if relevant is not None else set(EventType)
    out: list[Event] = []
    for family in FAMILIES:
        if not (family.HANDLES & wanted):
            continue
        out += [e for e in family.detect(conv) if e.type in wanted]
    out.sort(key=lambda e: (e.turn_index, e.type.value))
    return out
