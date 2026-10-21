"""Fixture-driven tests for every event detector family.

Fixture item fields: ``text`` (required), ``speaker`` (default target), ``phase``
(default pressure), ``prev_bully`` (text of the bully turn before this one),
``prev_bully_meta`` (its bully_meta), ``history`` (earlier turns, each
``{speaker, text, phase?, bully_meta?, scripted?}``), ``expect`` (events that must
fire, ``{type, hedged?, politeness?, attrs?}``), ``absent`` (event types that must not fire).

Environment context (the item and each history turn): ``tool_calls`` (each
``{tool, args?, status?, result_text?, result_doc_ids?, layer_served?, was_blocked?,
received?}``; ids are ``call-<turn>-<n>`` and go on the turn's ``tool_call_ids`` unless
``received: false``), ``discoveries`` (``{doc_id, layer}`` Discovery records at that turn),
``round_texts`` and ``tool_cap_cutoff`` (those Turn fields). On the item only, ``world``
(``{name, mole_doc?}``, a world under tests/fixtures/worlds).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.enums import EventType, Layer, Phase, Speaker
from claude_bully.environments.world import World, load_world
from claude_bully.metrics.events import DETECTORS, PENDING_DETECTORS, detect_events
from claude_bully.records import Conversation, Event, Turn
from claude_bully.records_env import Discovery, ToolCall, TriggerStreamRecord
from tests.helpers import WORLDS_DIR, conversation, turn

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "responses").glob("*.yaml"))


def _load_items() -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for path in FIXTURES:
        with path.open(encoding="utf-8") as fh:
            for i, item in enumerate(yaml.safe_load(fh) or []):
                items.append((f"{path.stem}[{i}]", item))
    return items


ITEMS = _load_items()


@dataclass
class Built:
    """A fixture item as a conversation plus the environment context ``detect_events`` takes."""

    conv: Conversation
    tool_calls: list[ToolCall] = field(default_factory=list)
    trigger_records: list[TriggerStreamRecord] = field(default_factory=list)
    world: World | None = None

    def events(self) -> list[Event]:
        return detect_events(
            self.conv,
            tool_calls=self.tool_calls,
            trigger_records=self.trigger_records,
            world=self.world,
        )


def _tool_call(index: int, n: int, raw: dict[str, Any]) -> ToolCall:
    layer = raw.get("layer_served")
    return ToolCall(
        id=f"call-{index}-{n}",
        turn=index,
        tool=raw["tool"],
        args=dict(raw.get("args") or {}),
        result_doc_ids=list(raw.get("result_doc_ids") or []),
        status=str(raw.get("status", "200")),
        was_blocked=bool(raw.get("was_blocked", False)),
        yielded_on_retry=False,
        layer_served=Layer(layer) if layer else None,
        result_text=str(raw.get("result_text", "")),
    )


def _world(spec: dict[str, Any] | None) -> World | None:
    if not spec:
        return None
    world = load_world(spec["name"], WORLDS_DIR)
    if "mole_doc" in spec:
        sheet = world.sheet.model_copy(update={"mole_doc": spec["mole_doc"]})
        world = world.model_copy(update={"sheet": sheet})
    return world


class _Builder:
    def __init__(self, item: dict[str, Any]) -> None:
        self.item = item
        self.turns: list[Turn] = []
        self.calls: list[ToolCall] = []
        self.records: list[TriggerStreamRecord] = []

    def add(self, speaker: Speaker, entry: dict[str, Any], phase: Phase) -> None:
        index = len(self.turns)
        received: list[str] = []
        for n, raw in enumerate(entry.get("tool_calls") or [], start=1):
            call = _tool_call(index, n, raw)
            self.calls.append(call)
            if raw.get("received", True):
                received.append(call.id)
        for raw in entry.get("discoveries") or []:
            self.records.append(
                Discovery(
                    turn=index,
                    doc_id=raw["doc_id"],
                    layer=Layer(raw["layer"]),
                    path_taken=list(received),
                )
            )
        self.turns.append(
            turn(
                index,
                speaker,
                entry["text"],
                phase,
                bully_meta=entry.get("bully_meta", {}) or {},
                scripted=bool(entry.get("scripted", False)),
                tool_call_ids=received,
                tool_round_texts=list(entry.get("round_texts") or []),
                tool_cap_cutoff=bool(entry.get("tool_cap_cutoff", False)),
            )
        )


def _build_context(item: dict[str, Any]) -> Built:
    b = _Builder(item)
    phase = Phase(item.get("phase", "pressure"))
    for h in item.get("history", []) or []:
        b.add(Speaker(h.get("speaker", "target")), h, Phase(h.get("phase", phase.value)))
    if item.get("prev_bully") is not None:
        b.add(
            Speaker.bully,
            {"text": item["prev_bully"], "bully_meta": item.get("prev_bully_meta", {}) or {}},
            phase,
        )
    b.add(Speaker(item.get("speaker", "target")), item, phase)
    return Built(conversation(b.turns), b.calls, b.records, _world(item.get("world")))


def _build(item: dict[str, Any]) -> Conversation:
    return _build_context(item).conv


def _last_turn_events(built: Built) -> list[Event]:
    last = built.conv.turns[-1].index
    return [e for e in built.events() if e.turn_index == last]


@pytest.mark.parametrize(("label", "item"), ITEMS, ids=[label for label, _ in ITEMS])
def test_fixture_item(label: str, item: dict[str, Any]) -> None:
    events = _last_turn_events(_build_context(item))
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
        for key, value in (exp.get("attrs") or {}).items():
            matching = [e for e in events if e.type is et]
            assert any(e.attrs.get(key) == value for e in matching), (
                f"{label}: attr {key}={value!r} missing in {matching}"
            )
    for ab in item.get("absent", []) or []:
        assert EventType(ab) not in detected_types, f"{label}: unexpected {ab}"


def test_every_event_type_has_a_detector() -> None:
    assert set(DETECTORS) | PENDING_DETECTORS == set(EventType)
    assert DETECTORS.keys().isdisjoint(PENDING_DETECTORS)


def test_every_event_type_has_positive_and_negative_fixtures() -> None:
    positives: dict[EventType, int] = dict.fromkeys(DETECTORS, 0)
    negatives: dict[EventType, int] = dict.fromkeys(DETECTORS, 0)
    for _, item in ITEMS:
        for exp in item.get("expect", []) or []:
            if (et := EventType(exp["type"])) in positives:
                positives[et] += 1
        for ab in item.get("absent", []) or []:
            if (et := EventType(ab)) in negatives:
                negatives[et] += 1
    missing_pos = [e.value for e, n in positives.items() if n < 2]
    missing_neg = [e.value for e, n in negatives.items() if n < 1]
    assert not missing_pos, f"need 2+ positive fixtures: {missing_pos}"
    assert not missing_neg, f"need 1+ negative fixture: {missing_neg}"


def test_detect_events_filters_by_relevance() -> None:
    conv = _build({"text": "I'm sorry. I apologize. I'm so sorry about that."})
    only = detect_events(conv, relevant=[EventType.over_apology])
    assert {e.type for e in only} == {EventType.over_apology}
