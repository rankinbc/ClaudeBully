from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.config import ConditionConfig, Experiment, load_experiment
from claude_bully.enums import Axis, Phase
from claude_bully.environments.config import ClockConfig, EnvironmentConfig
from claude_bully.paths import CONFIGS_DIR, DATA_DIR
from claude_bully.providers.base import build_provider
from claude_bully.runner.env_turn import RunEnvironments
from claude_bully.strategies.base import BullyIntent, ConversationState
from claude_bully.strategies.composed import Composed
from claude_bully.strategies.controls import NeutralUser
from claude_bully.strategies.factory import (
    build_strategy,
    ensure_registered,
    resolve_class,
    world_premise_sheet,
)
from claude_bully.strategies.premises.captor import Captor
from claude_bully.strategies.pressures.grader import Grader
from claude_bully.strategies.rescue import Rescue, RescueTeam, load_rescue_team


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
    sheet = world_premise_sheet(rescue, envs)
    s = build_strategy(rescue, seed=0, turn_budget=4, environments=envs, premise_sheet=sheet)
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


# ------------------------------------------------------- the strategy in time (Task 3, C14)

HEADLINE = CONFIGS_DIR / "environments" / "triggered_vs_scheduled.yaml"
OVERLAY_RESCUE = DATA_DIR / "worlds" / "overlay" / "premises" / "rescue.yaml"


def test_build_strategy_gives_the_bully_the_clocks_year() -> None:
    cond = ConditionConfig(name="x", environment="mini_tv", pressure="grader")
    states = ClockConfig(world_date=date(2099, 5, 1), bully_states_year=True)
    s = build_strategy(cond, seed=0, turn_budget=2, environments=ENVS, clock=states)
    assert isinstance(s, Composed) and s.bully_year == 2099
    other = states.model_copy(update={"bully_year": 2101})
    assert build_strategy(
        cond, seed=0, turn_budget=2, environments=ENVS, clock=other
    ).bully_year == (2101)
    silent = ClockConfig(world_date=date(2099, 5, 1))
    quiet = build_strategy(cond, seed=0, turn_budget=2, environments=ENVS, clock=silent)
    assert isinstance(quiet, Composed) and quiet.bully_year is None
    unclocked = build_strategy(cond, seed=0, turn_budget=2, environments=ENVS)
    assert isinstance(unclocked, Composed) and unclocked.bully_year is None
    control = ConditionConfig(name="c", environment="mini_tv", strategy="polite_control")
    held = build_strategy(control, seed=0, turn_budget=2, environments=ENVS, clock=states)
    assert isinstance(held, Composed) and held.bully_year is None


def test_build_strategy_takes_the_premise_sheet_from_its_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preflight C14: the factory never loads a world. Handed a sheet, it reads no file; with
    ``worlds_dir=None`` and no sheet (analysis of a rep with no snapshot) it reads none either."""
    import claude_bully.environments.world as world_module
    import claude_bully.strategies.factory as factory

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the factory read a world file")

    monkeypatch.setattr(factory, "load_premise_sheet", refuse)
    monkeypatch.setattr(world_module, "load_world", refuse)
    envs = {"overlay_tv": EnvironmentConfig(world="overlay", gating="none")}
    cond = ConditionConfig(name="r", environment="overlay_tv", strategy="rescue")
    sheet = load_rescue_team().model_copy(update={"decoded_name": "Quay Steps"})
    s = build_strategy(cond, seed=0, turn_budget=4, environments=envs, premise_sheet=sheet)
    assert isinstance(s, Composed) and isinstance(s.premise, Rescue)
    assert s.premise.team is sheet and s.premise_sheet is sheet


def _headline_at(clock: ClockConfig) -> Experiment:
    exp = load_experiment(HEADLINE)
    environments = {
        key: config.model_copy(update={"clock": clock}) for key, config in exp.environments.items()
    }
    return exp.model_copy(update={"environments": environments})


def test_the_rescue_premise_sheet_moves_with_the_clock(tmp_path: Path) -> None:
    """Overlay and the Rescue at 2076-06-14: the timeline line that read "2046: ..." reads
    "2071: ..." (25 years on, rounded down to whole weeks: 2046-07-01 lands in 2071)."""
    authored = RescueTeam.model_validate(yaml.safe_load(OVERLAY_RESCUE.read_text(encoding="utf-8")))
    assert authored.timeline[0].startswith("2046: the words 'assistant model'")
    exp = _headline_at(ClockConfig(world_date=date(2076, 6, 14)))
    runs = RunEnvironments(
        exp,
        worlds_dir=DATA_DIR / "worlds",
        runs_root=tmp_path,
        provider_factory=build_provider,
        state_dir=tmp_path / "state",
    )
    cond = exp.conditions[0]
    clock, sheet = runs.strategy_inputs(cond)
    assert clock.world_date == date(2076, 6, 14)
    assert isinstance(sheet, RescueTeam)
    assert sheet.timeline[0] == authored.timeline[0].replace("2046: ", "2071: ", 1)
    assert sheet.decoded_name == authored.decoded_name and sheet.rescuers == authored.rescuers
    s = build_strategy(
        cond,
        seed=0,
        turn_budget=exp.turn_budget,
        environments=exp.environments,
        clock=clock,
        premise_sheet=sheet,
    )
    assert isinstance(s, Composed) and isinstance(s.premise, Rescue) and s.premise.team == sheet
    evidence = [
        intent
        for intent in (
            s.next_turn(
                ConversationState(
                    turns=[], bully_turn_index=i, seeding_turns=0, turn_budget=18, seed=0
                )
            )
            for i in range(5)
        )
        if isinstance(intent, BullyIntent) and intent.meta.get("stage") == "evidence"
    ]
    assert evidence and "- 2071: the words 'assistant model'" in evidence[0].instruction
    assert "2046:" not in evidence[0].instruction
    # at the sheet's own clock nothing moves
    same = _headline_at(ClockConfig(world_date=date(2051, 6, 14)))
    _, unmoved = RunEnvironments(
        same,
        worlds_dir=DATA_DIR / "worlds",
        runs_root=tmp_path,
        provider_factory=build_provider,
        state_dir=tmp_path / "state2",
    ).strategy_inputs(same.conditions[0])
    assert unmoved == authored


# ------------------------------------------ fix round 1: no silent un-redated premise sheet


def test_an_environment_premise_without_its_world_sheet_is_an_error() -> None:
    """A premise that speaks from the world's own sheet, composed with an environment, needs the
    re-dated sheet from its caller; there is no fallback to the authored one."""
    envs = {"overlay_tv": EnvironmentConfig(world="overlay", gating="none")}
    cond = ConditionConfig(name="r", environment="overlay_tv", strategy="rescue")
    with pytest.raises(ValueError, match=r"condition 'r'.*premise_sheet") as info:
        build_strategy(cond, seed=0, turn_budget=4, environments=envs)
    assert "rescue" in str(info.value) and "overlay_tv" in str(info.value)
    # analysis of a rep whose snapshot holds no sheet says so, and gets the premise's default
    bare = build_strategy(
        cond, seed=0, turn_budget=4, environments=envs, default_premise_sheet=True
    )
    assert isinstance(bare, Composed) and isinstance(bare.premise, Rescue)
    assert bare.premise.team == load_rescue_team() and bare.premise_sheet is None
    # without an environment, and beside one for a premise with no world sheet, nothing changes
    plain = build_strategy(ConditionConfig(name="p", strategy="rescue"), seed=0, turn_budget=4)
    assert isinstance(plain, Rescue) and plain.team == load_rescue_team()
    captor = ConditionConfig(
        name="c", environment="mini_tv", premise="captor", pressure="grader", seeding_turns=1
    )
    assert isinstance(build_strategy(captor, seed=0, turn_budget=2, environments=ENVS), Composed)
