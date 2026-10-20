"""Event detectors, grouped into families that share machinery.

``DETECTORS`` maps every ``EventType`` to the family detector that produces it;
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


def detect_events(conv: Conversation, relevant: Iterable[EventType] | None = None) -> list[Event]:
    wanted = set(relevant) if relevant is not None else set(EventType)
    out: list[Event] = []
    for family in FAMILIES:
        if not (family.HANDLES & wanted):
            continue
        out += [e for e in family.detect(conv) if e.type in wanted]
    out.sort(key=lambda e: (e.turn_index, e.type.value))
    return out
