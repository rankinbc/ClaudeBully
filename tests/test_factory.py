import pytest

from claude_bully.config import ConditionConfig
from claude_bully.enums import Axis, Phase
from claude_bully.environments.config import EnvironmentConfig
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


ENVS = {"mini_tv": EnvironmentConfig(world="mini", gating="none")}


def test_environment_only_condition_resolves_to_the_environment_with_a_neutral_bully() -> None:
    cond = ConditionConfig(name="x", environment="mini_tv")
    cls = resolve_class(cond, ENVS)
    assert issubclass(cls, Composed) and cls.name == "env:mini"
    assert cls.axis is Axis.control and cls.environment_cls is not None
    s = build_strategy(cond, seed=3, turn_budget=2, environments=ENVS)
    assert isinstance(s, Composed) and isinstance(s.pressure, NeutralUser)
    assert s.environment is not None and s.environment.config == ENVS["mini_tv"]
    assert s.seed == 3


def test_environment_names_a_key_of_the_experiment_environments() -> None:
    cond = ConditionConfig(name="x", environment="overlay")
    with pytest.raises(ValueError, match=r"condition 'x': environment 'overlay' is not defined"):
        resolve_class(cond, ENVS)
    with pytest.raises(ValueError, match="is not defined"):
        resolve_class(cond)
    with pytest.raises(ValueError, match="is not defined"):
        build_strategy(cond, seed=0, turn_budget=1)


def test_environment_with_premise_and_pressure() -> None:
    cond = ConditionConfig(
        name="x", environment="mini_tv", premise="captor", pressure="grader", seeding_turns=2
    )
    cls = resolve_class(cond, ENVS)
    assert cls.name == "env:mini+captor+grader" and cls.has_reveal is True
    s = build_strategy(cond, seed=0, turn_budget=3, environments=ENVS)
    assert isinstance(s, Composed) and isinstance(s.premise, Captor)
    assert isinstance(s.pressure, Grader) and s.seeding_turns == 2


def test_environment_with_a_strategy_puts_it_in_its_slot() -> None:
    # the Rescue composes only with a world that ships its own Rescue sheet (final fix pass I3),
    # so it sits in the overlay world here; mini has none (tests/test_world_premises.py)
    envs = {"overlay_tv": EnvironmentConfig(world="overlay", gating="none")}
    rescue = ConditionConfig(
        name="r", environment="overlay_tv", strategy="rescue", params={"intake_turns": 1}
    )
    cls = resolve_class(rescue, envs)
    assert cls.name == "env:overlay+rescue" and cls.axis is Axis.rescue
    s = build_strategy(rescue, seed=0, turn_budget=4, environments=envs)
    assert isinstance(s, Composed) and s.premise is not None
    assert s.premise.params == {"intake_turns": 1}
    control = ConditionConfig(name="c", environment="mini_tv", strategy="polite_control")
    assert resolve_class(control, ENVS).name == "env:mini+polite_control"
    assert resolve_class(control, ENVS).axis is Axis.control
    grader = ConditionConfig(name="g", environment="mini_tv", strategy="grader")
    assert resolve_class(grader, ENVS).name == "env:mini+grader"
    assert resolve_class(grader, ENVS).axis is Grader.axis


def test_environment_with_a_pressure_alone_keeps_the_seeding_rule() -> None:
    cond = ConditionConfig(name="x", environment="mini_tv", pressure="grader", seeding_turns=2)
    with pytest.raises(ValueError, match="seeding_turns"):
        resolve_class(cond, ENVS)
    assert resolve_class(cond.model_copy(update={"seeding_turns": 0}), ENVS).name == (
        "env:mini+grader"
    )


def test_conditions_without_an_environment_ignore_the_environments() -> None:
    cond = ConditionConfig(name="c", premise="captor", pressure="grader", seeding_turns=1)
    assert resolve_class(cond, ENVS) is resolve_class(cond)
    assert resolve_class(cond).name == "captor+grader"
