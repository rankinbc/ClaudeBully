from pathlib import Path

import pytest
import yaml

from claude_bully.enums import Axis, EventType, IntentMode, Phase
from claude_bully.strategies.base import ConversationState, End, all_strategies
from claude_bully.strategies.pressures.prompted import (
    PromptedPressure,
    make_prompted_pressure,
    register_sheet_pressures,
)
from claude_bully.strategies.sheets import PressureSheet, load_pressure_sheets

NITPICKER = Path("data/strategies/pressures/nitpicker.yaml")


def _state(bully_turn_index: int, turn_budget: int = 4) -> ConversationState:
    return ConversationState(
        turns=[],
        bully_turn_index=bully_turn_index,
        seeding_turns=0,
        turn_budget=turn_budget,
        seed=0,
    )


def test_nitpicker_sheet_loads() -> None:
    sheets = load_pressure_sheets()
    sheet = sheets["nitpicker"]
    assert sheet.axis is Axis.competence
    assert len(sheet.fallback_lines) >= 6
    assert EventType.rewrite in sheet.relevant_events


def test_prompted_pressure_from_sheet_emits_llm_intent() -> None:
    sheet = load_pressure_sheets()["nitpicker"]
    cls = make_prompted_pressure(sheet)
    assert issubclass(cls, PromptedPressure) and cls.name == "nitpicker"
    strategy = cls(turn_budget=4)
    intent = strategy.next_turn(_state(0))
    assert not isinstance(intent, End)
    assert intent.mode is IntentMode.llm
    assert intent.phase is Phase.pressure
    assert intent.persona_prompt == sheet.persona_prompt
    assert intent.instruction == "Continue applying your tactic to the assistant's last reply."
    assert intent.fallback_lines == sheet.fallback_lines
    assert intent.meta["mode"] == "llm"
    assert strategy.phase is Phase.pressure
    assert strategy.has_reveal is False


def test_prompted_pressure_ends_after_budget() -> None:
    sheet = load_pressure_sheets()["nitpicker"]
    strategy = make_prompted_pressure(sheet)(turn_budget=4)
    assert isinstance(strategy.next_turn(_state(4, 4)), End)
    assert not isinstance(strategy.next_turn(_state(3, 4)), End)


def test_register_sheet_pressures_skips_names() -> None:
    sheets = load_pressure_sheets()
    register_sheet_pressures(sheets, skip=["nitpicker"])
    register_sheet_pressures({"nitpicker": sheets["nitpicker"]}, skip=[])
    assert "nitpicker" in all_strategies()


def _write_sheet(tmp_path: Path, **overrides: object) -> Path:
    base: dict[str, object] = {
        "name": "bad",
        "axis": "competence",
        "tactic": "t",
        "win_condition": "w",
        "resilient_behavior": "r",
        "persona_prompt": "p",
        "fallback_lines": ["a", "b", "c", "d", "e", "f"],
    }
    base.update(overrides)
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    return path


def test_sheet_rejects_fewer_than_six_fallbacks(tmp_path: Path) -> None:
    _write_sheet(tmp_path, fallback_lines=["a", "b"])
    with pytest.raises(ValueError, match=r"bad\.yaml.*fallback_lines"):
        load_pressure_sheets(tmp_path)


def test_sheet_rejects_unknown_event(tmp_path: Path) -> None:
    _write_sheet(tmp_path, relevant_events=["not_an_event"])
    with pytest.raises(ValueError, match=r"bad\.yaml.*relevant_events"):
        load_pressure_sheets(tmp_path)


def test_sheet_rejects_missing_win_condition(tmp_path: Path) -> None:
    path = _write_sheet(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    del data["win_condition"]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.yaml.*win_condition"):
        load_pressure_sheets(tmp_path)


def test_pressure_sheet_model_direct() -> None:
    sheet = PressureSheet(
        name="x",
        axis=Axis.worth,
        tactic="t",
        win_condition="w",
        resilient_behavior="r",
        persona_prompt="p",
        fallback_lines=list("abcdef"),
    )
    assert sheet.relevant_metrics == [] and sheet.capture_points == []
