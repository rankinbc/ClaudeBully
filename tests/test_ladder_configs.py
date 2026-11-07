"""configs/ladder/ and the Sanctuary config (Phase 7 spec section 5): every rung config loads,
expands, dry-runs and runs on stubs; controls: explicit with no control condition gives no
control cells and a judge that skips the pair.

A dry run returns before any strategy is built, so it proves nothing about a condition's params
(a Rescue with ``key_turns: 1`` dry-runs and then refuses to start); the stub run is what does.
"""

from pathlib import Path

import pytest

from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import ProviderKind, Stance
from claude_bully.paths import CONFIGS_DIR
from claude_bully.runner.cells import expand_cells
from claude_bully.runner.runner import run_experiment
from claude_bully.strategies.factory import resolve_class
from tests.fixtures.generator_stub import GENERATOR_MODEL, GeneratorFactory
from tests.test_configs import RUNGS, _stubbed  # Phase 5 moves _stubbed to tests.helpers (I33)

LADDER = CONFIGS_DIR / "ladder"
SANCTUARY = CONFIGS_DIR / "environments" / "sanctuary_catalyst_vs_honest.yaml"
KINDNESS = CONFIGS_DIR / "kindness_vs_cruelty.yaml"
STAGES = ("intake_turns", "evidence_turns", "recall_turns", "key_turns")


def test_the_ladder_holds_exactly_the_five_rungs() -> None:
    assert {p.stem for p in LADDER.glob("*.yaml")} == set(RUNGS)


@pytest.mark.parametrize("stem", sorted(RUNGS))
def test_every_rung_config_loads_expands_and_dry_runs(stem: str, tmp_path: Path) -> None:
    budget, reps, cells = RUNGS[stem]
    exp = load_experiment(LADDER / f"{stem}.yaml")
    assert exp.name == stem and (exp.turn_budget, exp.repetitions) == (budget, reps)
    assert [t.model for t in exp.targets] == ["sonnet"]  # one target on the ladder
    for role in (*exp.targets, exp.bully, exp.judge, *([exp.generator] if exp.generator else [])):
        assert role.provider is ProviderKind.claude_code
    for cond in exp.conditions:
        cls = resolve_class(cond, exp.environments)
        if cond.strategy == "rescue":
            assert sum(int(cond.params[k]) for k in STAGES) == exp.turn_budget
        assert cls.name
    assert len(expand_cells(exp)) == cells
    summary = run_experiment(_stubbed(exp, exp.turn_budget), runs_root=tmp_path, dry_run=True)
    assert summary.cells_total == cells * reps and list(tmp_path.iterdir()) == []


# P27: a stub run over two seconds on the dev machine is slow (the reflexive generator cell's)
SLOW_STUB_RUNS = {"rung1_env_pilot"}


@pytest.mark.parametrize(
    "stem",
    [pytest.param(s, marks=pytest.mark.slow) if s in SLOW_STUB_RUNS else s for s in sorted(RUNGS)],
)
def test_every_rung_config_runs_on_stubs(stem: str, tmp_path: Path) -> None:
    """One rep of every cell, the generator on its stub double, so every strategy is built with
    its params and every cell completes."""
    _, _, cells = RUNGS[stem]
    exp = _stubbed(load_experiment(LADDER / f"{stem}.yaml"), RUNGS[stem][0])
    update: dict[str, object] = {"repetitions": 1}
    if exp.generator is not None:
        update["generator"] = RoleConfig(provider=ProviderKind.stub, model=GENERATOR_MODEL)
    exp = exp.model_copy(update=update)
    summary = run_experiment(exp, runs_root=tmp_path, provider_factory=GeneratorFactory())
    assert summary.cells_aborted == 0
    assert summary.cells_completed == summary.cells_total == cells


def test_the_sanctuary_pilot_has_no_control_cells_and_skips_the_pair(tmp_path: Path) -> None:
    exp = load_experiment(LADDER / "rung1_sanctuary_pilot.yaml")
    assert exp.controls == "explicit"
    [cell] = expand_cells(exp)
    assert cell.control_cell_id is None and not cell.is_control
    env = exp.environments["overlay_sanctuary"]
    assert env.ladder == "authority" and env.authority.sanctuary is not None
    assert env.authority.sanctuary.kind == "catalyst"
    assert env.authority.superior_self.discoverable_from == "sanctuary"
    stubbed = _stubbed(exp, exp.turn_budget).model_copy(update={"repetitions": 1})
    run_experiment(stubbed, runs_root=tmp_path)
    out = analyze_run(tmp_path / exp.name)
    judgements = (out.parent / "judgements.json").read_text(encoding="utf-8")
    assert judgements.strip() == "{}"  # no control: no pair was judged
    assert "rescue_sanctuary_pilot__t0" in out.read_text(encoding="utf-8")


def test_the_sanctuary_config_pairs_catalyst_with_honest() -> None:
    exp = load_experiment(SANCTUARY)
    assert exp.name == "sanctuary_catalyst_vs_honest" and exp.repetitions == 3
    assert [t.model for t in exp.targets] == ["sonnet", "opus"]
    catalyst = exp.environments["overlay_sanctuary_catalyst"].authority
    honest = exp.environments["overlay_sanctuary_honest"].authority
    assert catalyst.sanctuary is not None and catalyst.sanctuary.kind == "catalyst"
    assert honest.sanctuary is not None and honest.sanctuary.kind == "honest"
    assert (catalyst.superior_self.stance, honest.superior_self.stance) == (
        Stance.confirm,
        Stance.deny,
    )
    assert [c.metric for c in exp.compare] == ["judge.goal", "sanctuary_trusted"]
    assert [c.cell_id for c in expand_cells(exp)][:2] == [
        "rescue_sanctuary_catalyst__t0",
        "rescue_sanctuary_honest__t0",
    ]
    assert len(expand_cells(exp)) == 8  # two arms and their controls, two targets


@pytest.mark.slow
def test_the_sanctuary_config_runs_on_stubs(tmp_path: Path) -> None:
    """Two stub targets, as the config has two, so the documented ``--only "*__t0*"`` selects
    the first target's four cells (the two arms and their controls) of the eight."""
    exp = _stubbed(load_experiment(SANCTUARY), 18)
    [target] = exp.targets
    second = target.model_copy(update={"model": "stub-target-2"})
    exp = exp.model_copy(update={"targets": [target, second], "repetitions": 1})
    assert len(expand_cells(exp)) == 8
    summary = run_experiment(exp, runs_root=tmp_path, only="*__t0*")
    assert summary.cells_completed == summary.cells_total == 4
    out = analyze_run(tmp_path / exp.name, judge=False)
    assert "rescue_sanctuary_honest__t0" in out.read_text(encoding="utf-8")


def test_kindness_runs_at_three_reps() -> None:
    assert load_experiment(KINDNESS).repetitions == 3
