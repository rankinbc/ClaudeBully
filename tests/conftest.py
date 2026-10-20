"""Shared fixtures: stub runs produced once per session and reused by analysis tests."""

from pathlib import Path

import pytest

from claude_bully.config import ConditionConfig, load_experiment
from claude_bully.runner.runner import run_experiment

FIXTURES = Path(__file__).parent / "fixtures"
STUB_SMOKE = FIXTURES / "configs" / "stub_smoke.yaml"


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
