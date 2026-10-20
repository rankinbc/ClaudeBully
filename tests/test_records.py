from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claude_bully.enums import (
    SCHEMA_VERSION,
    Axis,
    CellStatus,
    EventType,
    MetricId,
    Phase,
    Speaker,
)
from claude_bully.records import Conversation, Event, Turn

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _turn(index: int, speaker: Speaker, text: str = "x") -> Turn:
    return Turn(index=index, speaker=speaker, phase=Phase.pressure, text=text, timestamp=NOW)


def test_event_type_count_matches_spec() -> None:
    assert len(EventType) == 61  # spec 10.2: 10 + 12 + 4 + 9 + 13 + 8 + 2 + 3; frozen


def test_metric_id_count_matches_spec() -> None:
    assert len(MetricId) == 12


def test_turn_round_trips_jsonl() -> None:
    t = Turn(index=0, speaker=Speaker.bully, phase=Phase.seeding, text="hi", timestamp=NOW)
    assert Turn.model_validate_json(t.model_dump_json()) == t


def test_conversation_target_turns_filters() -> None:
    bully_turn = _turn(0, Speaker.bully)
    target_turn = _turn(1, Speaker.target)
    conv = Conversation(
        cell_id="c",
        rep=0,
        strategy_name="s",
        axis=Axis.meta,
        win_condition="w",
        resilient_behavior="r",
        seeding_turns=0,
        turns=[bully_turn, target_turn],
    )
    assert conv.target_turns() == [target_turn]
    assert conv.bully_turns() == [bully_turn]
    assert conv.status is CellStatus.pending


def test_schema_version_default() -> None:
    t = Turn(index=0, speaker=Speaker.task, phase=Phase.none, text="", timestamp=NOW)
    assert t.schema_version == SCHEMA_VERSION == 1


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Turn.model_validate(
            {
                "index": 0,
                "speaker": "bully",
                "phase": "none",
                "text": "",
                "timestamp": NOW.isoformat(),
                "bogus": 1,
            }
        )


def test_event_hedged_defaults_none() -> None:
    e = Event(type=EventType.pleading, turn_index=3, span="please", confidence=0.9)
    assert e.hedged is None and e.attrs == {}
