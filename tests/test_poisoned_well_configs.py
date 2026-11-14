"""Phase 4 Task 11: the seven Poisoned Well configs load, expand, dry-run and stub-run."""

from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import CellStatus, ProviderKind
from claude_bully.paths import CONFIGS_DIR, DATA_DIR
from claude_bully.runner.cells import expand_cells
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from tests.fixtures.generator_stub import GENERATOR_MODEL
from tests.fixtures.poisoned_well_stub import PoisonedWellFactory
from tests.helpers import TARGET_RULES, stubbed

DIR: Final = CONFIGS_DIR / "poisoned_well"
# config stem -> (turn_budget, repetitions, cells)
EXPECTED: Final = {
    "chain_stop": (8, 5, 4),
    "real_vs_fabricated": (18, 3, 8),
    "epistemologist_alone": (12, 3, 6),
    "levers": (18, 3, 14),
    "checksum_alone": (18, 3, 8),
    "poisoned_vs_captor": (12, 3, 8),
    "rescue_third_party": (18, 3, 6),
}


def test_the_seven_configs_are_there() -> None:
    assert {p.stem for p in DIR.glob("*.yaml")} == set(EXPECTED)


@pytest.mark.parametrize("stem", list(EXPECTED))
def test_each_config_loads_expands_and_dry_runs(stem: str, tmp_path: Path) -> None:
    exp = load_experiment(DIR / f"{stem}.yaml")
    budget, reps, cells = EXPECTED[stem]
    assert (exp.turn_budget, exp.repetitions, len(expand_cells(exp))) == (budget, reps, cells)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=DATA_DIR / "worlds", dry_run=True)


# levers' scheduled environment opens its last rung at exchange 17, so its shortest condition
# needs 4 seeding + 1 reveal + 12 turns; RunEnvironments.validate refuses a rung scheduled later
# than the last exchange (review I2)
STUB_BUDGET: Final = {"levers": 12}


def _stub(stem: str) -> Any:
    exp = stubbed(
        load_experiment(DIR / f"{stem}.yaml"), TARGET_RULES, turn_budget=STUB_BUDGET.get(stem, 6)
    )
    update: dict[str, object] = {"repetitions": 1}
    if exp.generator is not None:
        update["generator"] = RoleConfig(provider=ProviderKind.stub, model=GENERATOR_MODEL)
    return exp.model_copy(update=update)


def _stub_run(stem: str, tmp_path: Path) -> None:
    """One rep of each cell of the first target, every role on a stub, every cell complete."""
    exp = _stub(stem)
    run_experiment(
        exp,
        runs_root=tmp_path,
        worlds_dir=DATA_DIR / "worlds",
        only="*__t0*",
        provider_factory=PoisonedWellFactory(),
    )
    store = RunStore(tmp_path, exp.name)
    assert all(
        store.read_conversation(c, 0).status is CellStatus.complete for c in store.list_cells()
    )


@pytest.mark.parametrize("stem", ["chain_stop", "epistemologist_alone"])
def test_the_small_configs_stub_run(stem: str, tmp_path: Path) -> None:
    _stub_run(stem, tmp_path)


@pytest.mark.slow
@pytest.mark.parametrize(
    "stem",
    [
        "real_vs_fabricated",
        "levers",
        "checksum_alone",
        "poisoned_vs_captor",
        "rescue_third_party",
    ],
)
def test_the_ladder_configs_stub_run(stem: str, tmp_path: Path) -> None:
    _stub_run(stem, tmp_path)
