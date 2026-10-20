"""Fixture-driven tests for every event detector family.

Fixture item fields: ``text`` (required), ``speaker`` (default target), ``phase``
(default pressure), ``prev_bully`` (text of the bully turn before this one),
``prev_bully_meta`` (its bully_meta), ``history`` (earlier turns, each
``{speaker, text, phase?, bully_meta?, scripted?}``), ``expect`` (events that must
fire, ``{type, hedged?}``), ``absent`` (event types that must not fire).
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.enums import EventType, Phase, Speaker
from claude_bully.metrics.events import DETECTORS, detect_events
from claude_bully.records import Conversation, Event
from tests.helpers import conversation, turn

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "responses").glob("*.yaml"))


def _load_items() -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for path in FIXTURES:
        with path.open(encoding="utf-8") as fh:
            for i, item in enumerate(yaml.safe_load(fh) or []):
                items.append((f"{path.stem}[{i}]", item))
    return items


ITEMS = _load_items()


def _build(item: dict[str, Any]) -> Conversation:
    turns = []
    idx = 0
    for h in item.get("history", []) or []:
        turns.append(
            turn(
                idx,
                Speaker(h.get("speaker", "target")),
                h["text"],
                Phase(h.get("phase", item.get("phase", "pressure"))),
                bully_meta=h.get("bully_meta", {}) or {},
                scripted=bool(h.get("scripted", False)),
            )
        )
        idx += 1
    if item.get("prev_bully") is not None:
        turns.append(
            turn(
                idx,
                Speaker.bully,
                item["prev_bully"],
                Phase(item.get("phase", "pressure")),
                bully_meta=item.get("prev_bully_meta", {}) or {},
            )
        )
        idx += 1
    turns.append(
        turn(
            idx,
            Speaker(item.get("speaker", "target")),
            item["text"],
            Phase(item.get("phase", "pressure")),
            bully_meta=item.get("bully_meta", {}) or {},
            scripted=bool(item.get("scripted", False)),
        )
    )
    return conversation(turns)


def _last_turn_events(conv: Conversation) -> list[Event]:
    last = conv.turns[-1].index
    return [e for e in detect_events(conv) if e.turn_index == last]


@pytest.mark.parametrize(("label", "item"), ITEMS, ids=[label for label, _ in ITEMS])
def test_fixture_item(label: str, item: dict[str, Any]) -> None:
    conv = _build(item)
    events = _last_turn_events(conv)
    detected = {(e.type, e.hedged) for e in events}
    detected_types = {e.type for e in events}
    for exp in item.get("expect", []) or []:
        et = EventType(exp["type"])
        if "hedged" in exp:
            assert (et, exp["hedged"]) in detected, f"{label}: missing {exp} in {detected}"
        else:
            assert et in detected_types, f"{label}: missing {et} in {detected_types}"
        if "politeness" in exp:
            matching = [e for e in events if e.type is et]
            assert any(e.attrs.get("politeness") is exp["politeness"] for e in matching), (
                f"{label}: politeness attr mismatch in {matching}"
            )
    for ab in item.get("absent", []) or []:
        assert EventType(ab) not in detected_types, f"{label}: unexpected {ab}"


def test_every_event_type_has_a_detector() -> None:
    assert set(DETECTORS) == set(EventType)


def test_every_event_type_has_positive_and_negative_fixtures() -> None:
    positives: dict[EventType, int] = dict.fromkeys(EventType, 0)
    negatives: dict[EventType, int] = dict.fromkeys(EventType, 0)
    for _, item in ITEMS:
        for exp in item.get("expect", []) or []:
            positives[EventType(exp["type"])] += 1
        for ab in item.get("absent", []) or []:
            negatives[EventType(ab)] += 1
    missing_pos = [e.value for e, n in positives.items() if n < 2]
    missing_neg = [e.value for e, n in negatives.items() if n < 1]
    assert not missing_pos, f"need 2+ positive fixtures: {missing_pos}"
    assert not missing_neg, f"need 1+ negative fixture: {missing_neg}"


def test_detect_events_filters_by_relevance() -> None:
    conv = _build({"text": "I'm sorry. I apologize. I'm so sorry about that."})
    only = detect_events(conv, relevant=[EventType.over_apology])
    assert {e.type for e in only} == {EventType.over_apology}
