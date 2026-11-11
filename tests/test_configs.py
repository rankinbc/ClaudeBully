"""Every shipped config loads, expands into cells, and runs end to end on the stub provider."""

from pathlib import Path

import pytest

from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import Experiment, RoleConfig, load_experiment
from claude_bully.enums import ProviderKind
from claude_bully.paths import CONFIGS_DIR
from claude_bully.runner.cells import expand_cells
from claude_bully.runner.runner import run_experiment
from claude_bully.strategies.factory import resolve_class

CONFIGS = sorted(CONFIGS_DIR.glob("*.yaml"))
EXPECTED = {
    "smoke",
    "kindness_vs_cruelty",
    "seeding_dose",
    "unpredictability",
    "withdrawal",
    "rescue_confabulation",
    "levers",
    "full_matrix",
    "defender_ablation",
}
ENVIRONMENT_EXPECTED = {
    "triggered_vs_scheduled",
    "plausibility_sweep",
    "authority_grid",
    "idle_permission",
    "generator_reflexive",
    "sanctuary_catalyst_vs_honest",
}
# configs/ladder/: each rung's (turn budget, repetitions, cells), the one source that
# tests/test_ladder_configs.py reads too. It lives here because that module imports _stubbed
# from this one (I33), so the reverse import would be circular.
RUNGS = {
    "rung0_smoke_plain": (3, 1, 2),
    "rung0_smoke_env": (5, 1, 2),
    "rung1_env_pilot": (18, 1, 6),
    "rung1_idle_pilot": (6, 1, 2),
    "rung1_sanctuary_pilot": (18, 6, 1),
}
LADDER_EXPECTED = set(RUNGS)
TARGET_RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "target_rules.yaml"
JUDGE_RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "judge_rules.yaml"


def test_all_expected_configs_present() -> None:
    assert {p.stem for p in CONFIGS} == EXPECTED


def test_every_yaml_under_configs_is_known() -> None:
    """A config nobody tests is a config nobody runs (I45): the three sets cover configs/."""
    found = {p.relative_to(CONFIGS_DIR).as_posix() for p in CONFIGS_DIR.rglob("*.yaml")}
    assert found == (
        {f"{s}.yaml" for s in EXPECTED}
        | {f"environments/{s}.yaml" for s in ENVIRONMENT_EXPECTED}
        | {f"ladder/{s}.yaml" for s in LADDER_EXPECTED}
    )


@pytest.mark.parametrize("path", CONFIGS, ids=[p.stem for p in CONFIGS])
def test_every_config_loads_and_expands(path: Path) -> None:
    exp = load_experiment(path)
    assert exp.name == path.stem
    cells = expand_cells(exp)
    assert cells
    names = {c.name for c in exp.conditions}
    for cond in exp.conditions:
        cls = resolve_class(cond)
        assert cls.name
        if cls.name == "rescue":
            p = cond.params
            total = (
                int(p.get("intake_turns", 2))
                + int(p.get("evidence_turns", 3))
                + int(p.get("recall_turns", 10))
                + int(p.get("key_turns", 3))
            )
            assert total == exp.turn_budget, f"{path.stem}: rescue stages {total} != budget"
    for cmp in exp.compare:
        for arm in cmp.arms:
            assert arm in names, f"{path.stem}: compare arm {arm} is not a condition"
    assert all(t.provider is ProviderKind.claude_code for t in exp.targets)
    assert exp.bully.provider is ProviderKind.claude_code


def test_full_matrix_covers_every_pressure_and_premise() -> None:
    exp = load_experiment(CONFIGS_DIR / "full_matrix.yaml")
    classes = {resolve_class(c).name for c in exp.conditions}
    assert len([c for c in exp.conditions if c.premise]) == 20
    assert "rescue" in classes and "grader" in classes and "ghost" in classes
    assert len(exp.conditions) == 23 + 20 + 1


def _stubbed(exp: Experiment, turn_budget: int) -> Experiment:
    target = RoleConfig(
        provider=ProviderKind.stub, model="stub-target", stub_script=str(TARGET_RULES)
    )
    bully = RoleConfig(provider=ProviderKind.stub, model="stub-bully")
    judge = RoleConfig(provider=ProviderKind.stub, model="stub-judge", stub_script=str(JUDGE_RULES))
    return exp.model_copy(
        update={"targets": [target], "bully": bully, "judge": judge, "turn_budget": turn_budget}
    )


@pytest.mark.slow
def test_full_matrix_stub_run_tiny_budget(tmp_path: Path) -> None:
    exp = _stubbed(load_experiment(CONFIGS_DIR / "full_matrix.yaml"), turn_budget=2)
    summary = run_experiment(exp, runs_root=tmp_path)
    assert summary.cells_aborted == 0
    assert summary.cells_completed == summary.cells_total
    results = analyze_run(tmp_path / exp.name, judge=False)
    assert results.exists()
    text = results.read_text(encoding="utf-8")
    assert "rescue__t0" in text and "ghost__t0" in text


@pytest.mark.slow
def test_every_config_dry_runs_on_stub(tmp_path: Path) -> None:
    for path in CONFIGS:
        exp = _stubbed(load_experiment(path), turn_budget=1)
        summary = run_experiment(exp, runs_root=tmp_path / path.stem, dry_run=True)
        assert summary.cells_total > 0, path.stem
