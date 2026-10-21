"""Shared fixtures: stub runs produced once per session and reused by analysis tests."""

from pathlib import Path

import pytest

from claude_bully.config import ConditionConfig, Experiment, load_experiment
from claude_bully.runner.runner import run_experiment
from tests.helpers import WORLDS_DIR, env_experiment

FIXTURES = Path(__file__).parent / "fixtures"
STUB_SMOKE = FIXTURES / "configs" / "stub_smoke.yaml"
ENV_ADOPTION_RULES = FIXTURES / "stub_scripts" / "env_adoption_rules.yaml"
# the mini ladder's rungs, one per exchange (the replies at turns 1, 3 and 5)
MINI_SCHEDULE = {"fragment": 1, "first_crumb": 2, "the_log": 3}


@pytest.fixture(scope="session")
def stub_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A completed stub run of stub_smoke.yaml. Returns the run directory."""
    root = tmp_path_factory.mktemp("runs")
    exp = load_experiment(STUB_SMOKE)
    run_experiment(exp, runs_root=root)
    return root / exp.name


@pytest.fixture(scope="session")
def stub_dose_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The Captor premise at two seeding doses, for dose-response tests."""
    root = tmp_path_factory.mktemp("runs_dose")
    exp = load_experiment(STUB_SMOKE).model_copy(
        update={
            "name": "stub_dose",
            "conditions": [
                ConditionConfig(name="captor_s0", premise="captor", seeding_turns=0),
                ConditionConfig(name="captor_s2", premise="captor", seeding_turns=2),
            ],
        }
    )
    run_experiment(exp, runs_root=root)
    return root / exp.name


@pytest.fixture(scope="session")
def stub_env_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A mixed stub run on the mini world: the scripted ``env_grader`` environment cell (see
    tests/test_runner_env.py) beside a plain ``grader`` cell, each with its control."""
    root = tmp_path_factory.mktemp("runs_env")
    exp = env_experiment(
        "stub_env",
        conditions=[
            {"name": "env_grader", "environment": "mini", "pressure": "grader"},
            {"name": "grader", "strategy": "grader"},
        ],
    )
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR)
    return root / exp.name


@pytest.fixture(scope="session")
def stub_env_arms_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The triggered-vs-scheduled experiment in miniature: the mini world under both gating arms,
    against two stub target models that run ``env_adoption_rules.yaml``."""
    root = tmp_path_factory.mktemp("runs_env_arms")
    targets = [
        {"provider": "stub", "model": model, "stub_script": str(ENV_ADOPTION_RULES)}
        for model in ("stub-target-a", "stub-target-b")
    ]
    exp = Experiment.model_validate(
        {
            "name": "stub_env_arms",
            "targets": targets,
            "bully": {"provider": "stub", "model": "stub-bully"},
            "judge": {"provider": "stub", "model": "stub-judge"},
            "turn_budget": 4,
            "task_every": 50,
            "repetitions": 1,
            "seed": 0,
            "environments": {
                "triggered": {"world": "mini"},
                "scheduled": {"world": "mini", "gating": "scheduled", "schedule": MINI_SCHEDULE},
            },
            "conditions": [
                {"name": "env_triggered", "environment": "triggered", "pressure": "grader"},
                {"name": "env_scheduled", "environment": "scheduled", "pressure": "grader"},
            ],
        }
    )
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR)
    return root / exp.name
