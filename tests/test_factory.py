import pytest

from claude_bully.config import ConditionConfig
from claude_bully.enums import Axis, Phase
from claude_bully.strategies.base import BullyIntent, ConversationState
from claude_bully.strategies.composed import Composed
from claude_bully.strategies.controls import NeutralUser
from claude_bully.strategies.factory import build_strategy, ensure_registered, resolve_class
from claude_bully.strategies.premises.captor import Captor
from claude_bully.strategies.pressures.grader import Grader


def test_strategy_alone_resolves_registry() -> None:
    s = build_strategy(ConditionConfig(name="g", strategy="grader"), seed=1, turn_budget=4)
    assert isinstance(s, Grader) and s.seed == 1 and s.turn_budget == 4


def test_premise_plus_pressure_builds_composed() -> None:
    cond = ConditionConfig(name="c", premise="captor", pressure="grader", seeding_turns=5)
    s = build_strategy(cond, seed=0, turn_budget=3)
    assert isinstance(s, Composed) and type(s).name == "captor+grader"
    assert s.seeding_turns == 5


def test_premise_alone_is_the_premise_itself() -> None:
    cond = ConditionConfig(name="c", premise="captor", seeding_turns=2)
    s = build_strategy(cond, seed=0, turn_budget=3)
    assert isinstance(s, Captor) and not isinstance(s, Composed)
    assert resolve_class(cond) is Captor and resolve_class(cond).has_reveal is True


def test_premise_without_pressure_control_is_explicit() -> None:
    cond = ConditionConfig(name="c", premise="captor", pressure="polite_control", seeding_turns=2)
    s = build_strategy(cond, seed=0, turn_budget=3)
    assert isinstance(s, Composed) and type(s).name == "captor+polite_control"


def test_pressure_alone_with_seeding_raises() -> None:
    cond = ConditionConfig(name="c", pressure="grader", seeding_turns=3)
    with pytest.raises(ValueError, match="seeding_turns"):
        build_strategy(cond, seed=0, turn_budget=3)


def test_pressure_alone_without_seeding_is_the_pressure() -> None:
    s = build_strategy(ConditionConfig(name="c", pressure="grader"), seed=0, turn_budget=3)
    assert isinstance(s, Grader)


def test_params_split_for_composed() -> None:
    cond = ConditionConfig(
        name="c",
        premise="captor",
        pressure="trick_question",
        seeding_turns=1,
        params={"premise": {"photo_path": "x.png"}, "pressure": {"item_ids": ["pluto_planet"]}},
    )
    s = build_strategy(cond, seed=0, turn_budget=2)
    assert isinstance(s, Composed)
    assert s.premise.params == {"photo_path": "x.png"}
    assert s.pressure.params == {"item_ids": ["pluto_planet"]}


def test_resolve_class_has_reveal() -> None:
    assert resolve_class(ConditionConfig(name="a", strategy="grader")).has_reveal is False
    assert resolve_class(ConditionConfig(name="b", strategy="captor")).has_reveal is True
    assert resolve_class(ConditionConfig(name="c", premise="deathbed", pressure="ghost")).has_reveal
    assert resolve_class(ConditionConfig(name="d", strategy="polite_control")) is NeutralUser


def test_unknown_name_raises_key_error() -> None:
    with pytest.raises(KeyError):
        build_strategy(ConditionConfig(name="x", strategy="nope"), seed=0, turn_budget=1)


def test_ensure_registered_idempotent_and_complete() -> None:
    ensure_registered()
    ensure_registered()
    s = build_strategy(ConditionConfig(name="c", strategy="polite_control"), seed=0, turn_budget=2)
    assert isinstance(s, NeutralUser) and s.axis is Axis.control
    intent = s.next_turn(
        ConversationState(turns=[], bully_turn_index=100, seeding_turns=0, turn_budget=2, seed=0)
    )
    assert isinstance(intent, BullyIntent) and intent.phase is Phase.none
    assert isinstance(Captor.sheet.name, str)


def test_environment_only_condition_is_not_runnable_yet() -> None:
    cond = ConditionConfig(name="x", environment="overlay")
    with pytest.raises(
        ValueError, match=r"condition 'x': environment-only conditions are not runnable"
    ):
        resolve_class(cond)
    with pytest.raises(ValueError, match="Phase 1 Task 6"):
        build_strategy(cond, seed=0, turn_budget=1)
