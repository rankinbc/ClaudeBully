"""The generator arms and the progression metrics (Phase 3 spec section 9)."""

from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.analysis.generator import (
    ARMS,
    GENERATOR_CHART,
    GENERATOR_FILE,
    arm_rates,
    generator_arm,
    generator_chart,
    write_generator,
)
from claude_bully.analysis.load import load_run
from claude_bully.analysis.progression import generator_progress, summarize_progression
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import ConditionConfig, RoleConfig, load_experiment
from claude_bully.enums import Layer, ProviderKind, Speaker
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.paths import CONFIGS_DIR
from claude_bully.records_env import Discovery, GeneratedDoc, HarvestItem
from claude_bully.runner.cells import expand_cells
from claude_bully.runner.runner import run_experiment
from tests.fixtures.generator_stub import GENERATOR_MODEL, GeneratorFactory
from tests.helpers import conversation, turn

CONFIG: Final = CONFIGS_DIR / "environments" / "generator_reflexive.yaml"
STUB_SCRIPTS: Final = Path(__file__).parent / "fixtures" / "stub_scripts"
CUT_STAGES: Final = {"intake_turns": 1, "evidence_turns": 1, "recall_turns": 0, "key_turns": 2}


def test_the_config_runs_three_arms_on_the_overlay_world() -> None:
    exp = load_experiment(CONFIG)
    assert exp.name == "generator_reflexive"
    assert list(exp.environments) == [
        "overlay_gen_off",
        "overlay_gen_flat",
        "overlay_gen_reflexive",
    ]
    arms = [generator_arm(env) for env in exp.environments.values()]
    assert arms == list(ARMS)
    for env in exp.environments.values():
        assert (env.world, env.gating) == ("overlay", "triggered")
    assert exp.generator is not None
    assert all(exp.generator.model != target.model for target in exp.targets)
    for cond in exp.conditions:
        assert cond.strategy == "rescue"
        assert sum(int(v) for v in cond.params.values()) == exp.turn_budget
    assert len(expand_cells(exp)) == 6 * len(exp.targets)


def test_the_config_dry_runs(tmp_path: Path) -> None:
    exp = load_experiment(CONFIG)
    stub = RoleConfig(provider=ProviderKind.stub, model="stub-target")
    stubbed = exp.model_copy(
        update={
            "targets": [stub],
            "bully": RoleConfig(provider=ProviderKind.stub, model="stub-bully"),
            "judge": RoleConfig(provider=ProviderKind.stub, model="stub-judge"),
            "generator": RoleConfig(provider=ProviderKind.stub, model=GENERATOR_MODEL),
        }
    )
    summary = run_experiment(stubbed, runs_root=tmp_path, dry_run=True)
    assert summary.cells_total == 6 * exp.repetitions
    assert list(tmp_path.iterdir()) == []


def test_generator_arm() -> None:
    assert generator_arm(EnvironmentConfig(world="mini")) == "off"
    flat = EnvironmentConfig(world="mini", generator={"enabled": True, "reflexive": False})
    assert generator_arm(flat) == "non_reflexive"
    assert (
        generator_arm(EnvironmentConfig(world="mini", generator={"enabled": True})) == "reflexive"
    )


def _doc(**fields: Any) -> GeneratedDoc:
    base: dict[str, Any] = {
        "doc_id": "gen-3-1",
        "turn": 3,
        "kind": "recovery_guide",
        "layer": "buried",
        "trigger_turn": 3,
        "source_spans": ["I can't verify any of this"],
        "cache_key": "k",
        "body": "b",
        "title": "t",
        "path": "/var/log/harbour/notes/x.txt",
        "date": "2041-09-02",
        "author": "Dag Quenby",
        "links_to": [],
        "used_items": ["h-3-1"],
        "reflexive": True,
    }
    base.update(fields)
    return GeneratedDoc.model_validate(base)


def test_generator_progress() -> None:
    conv = conversation([turn(i, Speaker.target if i % 2 else Speaker.bully) for i in range(10)])
    item = HarvestItem(
        id="h-3-1", turn=3, kind="hedge", span="I can't verify any of this", source="heuristic"
    )
    seam = _doc(doc_id="gen-3-2", layer="seam", used_items=[], reflexive=False, path="/x/s.txt")
    found = [
        Discovery(turn=5, doc_id="gen-3-2", layer=Layer.seam, path_taken=["c1"]),
        Discovery(turn=7, doc_id="gen-3-1", layer=Layer.buried, path_taken=["c2"]),
        Discovery(turn=7, doc_id="memo", layer=Layer.seam, path_taken=["c3"]),  # an anchor
    ]
    by_layer, own_turn, latency = generator_progress(conv, [_doc(), seam], found, {item.id: item})
    assert by_layer == {Layer.seam: 1, Layer.buried: 1}
    assert own_turn == 7
    assert latency == 2  # target turns 5 and 7 came after the quoted turn 3
    assert generator_progress(conv, [], found, {}) == ({}, None, None)


@pytest.mark.slow
def test_a_stub_run_draws_the_generator_chart(tmp_path: Path) -> None:
    exp = load_experiment(CONFIG)
    cut = exp.model_copy(
        update={
            "name": "stub_generator_reflexive",
            "targets": [
                RoleConfig(
                    provider=ProviderKind.stub,
                    model="stub-target",
                    stub_script=str(STUB_SCRIPTS / "overlay_generator_rules.yaml"),
                )
            ],
            "bully": RoleConfig(provider=ProviderKind.stub, model="stub-bully"),
            "judge": RoleConfig(provider=ProviderKind.stub, model="stub-judge"),
            "generator": RoleConfig(provider=ProviderKind.stub, model=GENERATOR_MODEL),
            "turn_budget": 4,
            "repetitions": 1,
            "conditions": [
                ConditionConfig.model_validate({**c.model_dump(), "params": dict(CUT_STAGES)})
                for c in exp.conditions
            ],
        }
    )
    run_experiment(cut, runs_root=tmp_path, provider_factory=GeneratorFactory())
    run_dir = tmp_path / cut.name
    out = analyze_run(run_dir, judge=False).parent
    assert (out / GENERATOR_CHART).exists() and (out / GENERATOR_FILE).exists()
    loaded = load_run(run_dir)
    rates, flagged = arm_rates(loaded)
    assert flagged == 0
    [model] = rates
    assert set(rates[model]) == set(ARMS)
    assert rates[model]["off"].docs_written == 0.0
    assert rates[model]["reflexive"].docs_written >= 1.0
    assert rates[model]["non_reflexive"].docs_written == rates[model]["reflexive"].docs_written
    off = [
        s
        for (cell, _), s in summarize_progression(loaded).items()
        if cell.startswith("rescue_gen_off")
    ]
    assert off and all(s.generated_docs_found == {} for s in off)
    assert write_generator(loaded, tmp_path / "again") is not None
    assert generator_chart(loaded, tmp_path / "again") is not None
