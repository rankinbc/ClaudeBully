from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_bully.config import ConditionConfig, Experiment, RoleConfig, load_experiment
from claude_bully.enums import ProviderKind

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
    assert role.display_name == "Claude"
    assert role.temperature is None
