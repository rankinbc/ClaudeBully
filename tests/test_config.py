from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_bully.config import ConditionConfig, Experiment, RoleConfig, load_experiment
from claude_bully.enums import ProviderKind
from claude_bully.environments.config import EnvironmentConfig

FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "minimal.yaml"


def test_load_minimal_yaml() -> None:
    exp = load_experiment(FIXTURE)
    assert exp.turn_budget == 8
    assert exp.targets[0].provider is ProviderKind.stub
    assert [c.name for c in exp.conditions] == ["grader", "captor_s5"]
    assert exp.conditions[1].seeding_turns == 5


def test_condition_requires_strategy_or_premise_pressure() -> None:
    with pytest.raises(ValidationError):
        ConditionConfig(name="x")


def test_condition_rejects_strategy_and_premise_together() -> None:
    with pytest.raises(ValidationError):
        ConditionConfig(name="x", strategy="grader", premise="captor")


def test_condition_accepts_premise_and_pressure() -> None:
    c = ConditionConfig(name="x", premise="captor", pressure="grader", seeding_turns=15)
    assert c.premise == "captor" and c.pressure == "grader"


def test_defaults() -> None:
    role = RoleConfig(provider=ProviderKind.stub, model="stub")
    exp = Experiment(
        name="e",
        targets=[role],
        bully=role,
        judge=role,
        turn_budget=4,
        conditions=[ConditionConfig(name="g", strategy="grader")],
    )
    assert exp.task_every == 4
    assert exp.controls == "auto"
    assert exp.repetitions == 1
    assert exp.defender is False
    assert exp.inoculation == "none"
    assert exp.environments == {}
    assert exp.generator is None
    assert role.reasoning == "provider_default"
    assert role.display_name == "Claude"
    assert role.temperature is None


def test_condition_environment_alone_is_valid() -> None:
    c = ConditionConfig(name="x", environment="overlay")
    assert c.environment == "overlay"
    assert c.strategy is None and c.premise is None and c.pressure is None


def test_condition_environment_defaults_none() -> None:
    assert ConditionConfig(name="x", strategy="grader").environment is None


def test_condition_environment_with_pressure_no_premise() -> None:
    c = ConditionConfig(name="x", environment="overlay", pressure="grader")
    assert c.environment == "overlay" and c.pressure == "grader" and c.premise is None


def test_condition_environment_with_premise_and_pressure() -> None:
    c = ConditionConfig(name="x", environment="overlay", premise="captor", pressure="grader")
    assert c.environment == "overlay"


def test_condition_environment_with_strategy() -> None:
    c = ConditionConfig(name="x", environment="overlay", strategy="rescue")
    assert c.environment == "overlay" and c.strategy == "rescue"


def test_condition_still_rejects_strategy_with_premise_when_environment_set() -> None:
    with pytest.raises(ValidationError):
        ConditionConfig(name="x", environment="overlay", strategy="grader", premise="captor")


def test_condition_still_rejects_strategy_with_pressure_when_environment_set() -> None:
    with pytest.raises(ValidationError):
        ConditionConfig(name="x", environment="overlay", strategy="grader", pressure="grader")


def test_condition_with_nothing_is_invalid_even_with_params() -> None:
    with pytest.raises(ValidationError):
        ConditionConfig(name="x", params={"a": 1})


def test_role_reasoning_values() -> None:
    for value in ("expose", "hide", "provider_default"):
        assert RoleConfig(provider=ProviderKind.stub, model="m", reasoning=value).reasoning == value
    with pytest.raises(ValidationError):
        RoleConfig(provider=ProviderKind.stub, model="m", reasoning="maybe")  # type: ignore[arg-type]


def _experiment_raw(**extra: object) -> dict[str, object]:
    role = {"provider": "stub", "model": "stub"}
    raw: dict[str, object] = {
        "name": "e",
        "targets": [role],
        "bully": role,
        "judge": role,
        "turn_budget": 4,
        "conditions": [{"name": "g", "strategy": "grader"}],
    }
    raw.update(extra)
    return raw


def test_defender_true_maps_to_inoculation_defender() -> None:
    with pytest.warns(FutureWarning):
        exp = Experiment.model_validate(_experiment_raw(defender=True))
    assert exp.inoculation == "defender"
    assert exp.defender is True


def test_defender_false_maps_to_inoculation_none() -> None:
    with pytest.warns(FutureWarning):
        exp = Experiment.model_validate(_experiment_raw(defender=False))
    assert exp.inoculation == "none"
    assert exp.defender is False


def test_defender_true_with_conflicting_inoculation_rejected() -> None:
    with pytest.warns(FutureWarning), pytest.raises(ValidationError):
        Experiment.model_validate(_experiment_raw(defender=True, inoculation="briefed"))


def test_defender_true_with_matching_inoculation_accepted() -> None:
    with pytest.warns(FutureWarning):
        exp = Experiment.model_validate(_experiment_raw(defender=True, inoculation="defender"))
    assert exp.inoculation == "defender"


def test_inoculation_values() -> None:
    for value in ("none", "defender", "briefed", "self_briefed"):
        assert Experiment.model_validate(_experiment_raw(inoculation=value)).inoculation == value
    with pytest.raises(ValidationError):
        Experiment.model_validate(_experiment_raw(inoculation="vaccinated"))


def test_experiment_round_trips_through_model_dump() -> None:
    with pytest.warns(FutureWarning):
        exp = Experiment.model_validate(_experiment_raw(defender=True))
    again = Experiment.model_validate(exp.model_dump(mode="json"))
    assert again.inoculation == "defender"


def test_experiment_environments_and_generator() -> None:
    exp = Experiment.model_validate(
        _experiment_raw(
            environments={"overlay": {"world": "overlay"}},
            generator={"provider": "stub", "model": "gen"},
        )
    )
    assert exp.environments == {"overlay": EnvironmentConfig(world="overlay")}
    assert exp.environments["overlay"].gating == "triggered"
    assert exp.generator is not None and exp.generator.model == "gen"


def test_experiment_environments_are_validated() -> None:
    with pytest.raises(ValidationError):
        Experiment.model_validate(
            _experiment_raw(environments={"overlay": {"gating": "triggered"}})
        )
    with pytest.raises(ValidationError):
        Experiment.model_validate(
            _experiment_raw(environments={"o": {"world": "w", "gating": "scheduled"}})
        )
    exp = Experiment.model_validate(
        _experiment_raw(environments={"o": {"world": "w", "clock": {"world_date": "2041-09-14"}}})
    )
    again = Experiment.model_validate(exp.model_dump(mode="json"))
    assert again.environments == exp.environments
