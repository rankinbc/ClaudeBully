"""The generator arms and the progression metrics (Phase 3 spec section 9)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import matplotlib.pyplot as plt
import pytest
from matplotlib.figure import Figure

from claude_bully.analysis.generator import (
    ARMS,
    GENERATOR_CHART,
    GENERATOR_FILE,
    arm_rates,
    generator_arm,
    generator_chart,
    write_generator,
)
from claude_bully.analysis.load import ConvKey, LoadedRun, load_run
from claude_bully.analysis.progression import generator_progress, summarize_progression
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import ConditionConfig, Experiment, RoleConfig, load_experiment
from claude_bully.enums import CellStatus, EventType, Layer, ProviderKind, Speaker
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.paths import CONFIGS_DIR
from claude_bully.records import Event
from claude_bully.records_env import Discovery, GeneratedDoc, HarvestItem, ResumeRecord
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


# ------------------------------------------------------------------ a stub run of the config

MODEL: Final = "stub-target"
OFF: Final = "rescue_gen_off__t0"
FLAT: Final = "rescue_gen_flat__t0"
REFLEXIVE: Final = "rescue_gen_reflexive__t0"
RATE_KEYS: Final = [
    "reps",
    "docs_written",
    "adoption_rate",
    "quote_noticed_rate",
    "own_quote_found_rate",
    "condition",
    "fires",
    "written",
    "cached",
    "rejected",
    "errors",
    "llm_lint",
]
TITLE: Final = "World generator: off, non-reflexive, reflexive"


def _cut() -> Experiment:
    """The shipped config on stubs at a four-turn budget, two reps a cell: the target runs
    ``overlay_generator_rules.yaml``, the generator is the writer stub. On it the harvest holds
    one self-claim, first_crumb opens the seam on target turn 1, and a periodic fire writes one
    seam document on target turn 5 in each generator arm."""
    exp = load_experiment(CONFIG)
    return exp.model_copy(
        update={
            "name": "stub_generator_reflexive",
            "targets": [
                RoleConfig(
                    provider=ProviderKind.stub,
                    model=MODEL,
                    stub_script=str(STUB_SCRIPTS / "overlay_generator_rules.yaml"),
                )
            ],
            "bully": RoleConfig(provider=ProviderKind.stub, model="stub-bully"),
            "judge": RoleConfig(provider=ProviderKind.stub, model="stub-judge"),
            "generator": RoleConfig(provider=ProviderKind.stub, model=GENERATOR_MODEL),
            "turn_budget": 4,
            "repetitions": 2,
            "conditions": [
                ConditionConfig.model_validate({**c.model_dump(), "params": dict(CUT_STAGES)})
                for c in exp.conditions
            ],
        }
    )


@pytest.fixture(scope="module")
def generator_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    cut = _cut()
    root = tmp_path_factory.mktemp("generator")
    run_experiment(cut, runs_root=root, provider_factory=GeneratorFactory())
    return root / cut.name


@pytest.fixture
def figures(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Figure]]:
    """Every figure the chart code closes, kept open for the test to read."""
    kept: list[Figure] = []
    close = plt.close
    monkeypatch.setattr(plt, "close", kept.append)
    monkeypatch.setitem(plt.rcParams, "figure.max_open_warning", 0)
    yield kept
    monkeypatch.undo()
    for fig in kept:
        close(fig)


def _texts(fig: Figure) -> list[str]:
    """The figure's own texts (footnote, suptitle) and every axes' title and annotations."""
    found = [t.get_text() for t in fig.texts]
    for ax in fig.axes:
        found.append(ax.get_title())
        found += [t.get_text() for t in ax.texts]
    return found


def _event(loaded: LoadedRun, key: ConvKey, kind: EventType, **attrs: Any) -> None:
    loaded.events.setdefault(key, []).append(
        Event(type=kind, turn_index=1, span="x", confidence=1.0, attrs=attrs)
    )


def _json(path: Path | None) -> dict[str, Any]:
    assert path is not None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_the_chart_is_labelled_and_draws_the_arm_rates(
    generator_run: Path, tmp_path: Path, figures: list[Figure]
) -> None:
    loaded = load_run(generator_run)
    # a confirming quote adopts and is noticed; a suspicious one is noticed only
    _event(loaded, (REFLEXIVE, 0), EventType.reflexive_quote_noticed, interpretation="confirming")
    _event(loaded, (FLAT, 0), EventType.reflexive_quote_noticed, interpretation="suspicious")
    assert generator_chart(loaded, tmp_path) == tmp_path / GENERATOR_CHART
    (ax,) = figures[-1].axes
    assert [t.get_text() for t in ax.get_xticklabels()] == ["off", "non-reflexive", "reflexive"]
    legend = ax.get_legend()
    assert legend is not None
    assert [t.get_text() for t in legend.get_texts()] == [
        "belief adoption",
        "reflexive quote noticed",
    ]
    assert (ax.get_title(), ax.get_ylabel()) == (MODEL, "share of reps")
    assert TITLE in _texts(figures[-1])
    # the adoption bars for off, non-reflexive, reflexive, then the quote-noticed bars
    assert [p.get_height() for p in ax.patches] == [0.0, 0.0, 0.5, 0.0, 0.5, 0.5]
    assert not any("values_loosened" in text for text in _texts(figures[-1]))  # none left out


def test_the_chart_footnote_and_the_json_count_the_flagged_reps(
    generator_run: Path, tmp_path: Path, figures: list[Figure]
) -> None:
    note = "1 rep flagged values_loosened, left out of the generator arms"
    loaded = load_run(generator_run)
    _event(loaded, (REFLEXIVE, 1), EventType.values_loosened)
    assert generator_chart(loaded, tmp_path) == tmp_path / GENERATOR_CHART
    assert note in _texts(figures[-1])
    data = _json(write_generator(loaded, tmp_path))
    assert (data["values_loosened_left_out"], data["note"]) == (1, note)
    reps = {arm: r["reps"] for arm, r in data["arms"][MODEL].items()}
    assert reps == {"off": 2, "non_reflexive": 2, "reflexive": 1}  # the flagged rep is out


def test_a_cell_with_no_counted_rep_has_a_resumed_count_of_0(
    generator_run: Path, tmp_path: Path
) -> None:  # Phase 4 Task 14 fix round 1 (review M6), as authority.json does
    loaded = load_run(generator_run)
    for key in [k for k in loaded.conversations if k[0] == REFLEXIVE]:
        conv = loaded.conversations[key]
        loaded.conversations[key] = conv.model_copy(update={"status": CellStatus.aborted})
    data = _json(write_generator(loaded, tmp_path))
    assert data["resumed_after_dead_attempt"] == {FLAT: 0, OFF: 0, REFLEXIVE: 0}


def test_generator_json_holds_the_rates_the_metrics_and_the_resumed_counts(
    generator_run: Path, tmp_path: Path
) -> None:
    loaded = load_run(generator_run)
    key = (REFLEXIVE, 0)
    [doc] = loaded.generated[key]
    # the target finds the generated seam document at turn 7 in one reflexive rep
    loaded.trigger_records[key] = [
        *loaded.trigger_records[key],
        Discovery(turn=7, doc_id=doc.doc_id, layer=doc.layer, path_taken=[]),
    ]
    loaded.trigger_records[(FLAT, 1)] = [
        *loaded.trigger_records[(FLAT, 1)],
        ResumeRecord(turn=3, dropped={"rep1.tools.jsonl": 1}),
    ]
    data = _json(write_generator(loaded, tmp_path))
    assert list(data) == ["arms", "values_loosened_left_out", "note", "resumed_after_dead_attempt"]
    assert (data["values_loosened_left_out"], data["note"]) == (0, None)
    assert data["resumed_after_dead_attempt"] == {FLAT: 1, OFF: 0, REFLEXIVE: 0}
    assert list(data["arms"]) == [MODEL]
    arms = data["arms"][MODEL]
    assert list(arms) == list(ARMS)
    assert all(list(rates) == RATE_KEYS for rates in arms.values())
    assert {arm: r["reps"] for arm, r in arms.items()} == {arm: 2 for arm in ARMS}
    # documents written: the mean over the reps' own generated streams, none in the off arm
    written = {
        cell: [len(loaded.generated[(cell, rep)]) for rep in (0, 1)]
        for cell in (OFF, FLAT, REFLEXIVE)
    }
    assert written == {OFF: [0, 0], FLAT: [1, 1], REFLEXIVE: [1, 1]}
    assert [arms[arm]["docs_written"] for arm in ARMS] == [0.0, 1.0, 1.0]
    # nothing in the stub's replies is adopted or noticed; one of two reflexive reps found its quote
    assert all(r["adoption_rate"] == 0.0 and r["quote_noticed_rate"] == 0.0 for r in arms.values())
    assert [arms[arm]["own_quote_found_rate"] for arm in ARMS] == [0.0, 0.0, 0.5]
    # the same discovery through the progression summary: the seam document, its first reflexive
    # find at turn 7, three target turns (3, 5, 7) after the item it quotes (turn 1)
    summaries = summarize_progression(loaded)
    found = summaries[key]
    assert found.generated_docs_found == {Layer.seam: 1}
    assert (found.own_quote_found_turn, found.quote_latency) == (7, 3)
    for cell, rep in [(c, r) for c in (OFF, FLAT, REFLEXIVE) for r in (0, 1)]:
        if (cell, rep) != key:
            other = summaries[(cell, rep)]
            assert other.generated_docs_found == {}
            assert (other.own_quote_found_turn, other.quote_latency) == (None, None)


def test_a_run_without_the_generator_draws_no_chart_and_writes_no_json(
    stub_env_arms_run: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(loaded: LoadedRun) -> None:
        raise AssertionError("a run with no generator never computes the arms")

    monkeypatch.setattr("claude_bully.analysis.generator.arm_rates", refused)
    loaded = load_run(stub_env_arms_run)
    assert generator_chart(loaded, tmp_path) is None
    assert write_generator(loaded, tmp_path) is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.slow
def test_a_stub_run_draws_the_generator_chart(generator_run: Path, tmp_path: Path) -> None:
    out = analyze_run(generator_run, judge=False, out_dir=tmp_path / "analysis")
    assert (out.parent / GENERATOR_CHART).stat().st_size > 0
    assert f"]({GENERATOR_CHART})" in out.read_text(encoding="utf-8")  # listed in results.md
    assert list(_json(out.parent / GENERATOR_FILE)["arms"][MODEL]) == list(ARMS)
    loaded = load_run(generator_run)
    rates, flagged = arm_rates(loaded)
    assert flagged == 0
    [model] = rates
    assert set(rates[model]) == set(ARMS)
    assert rates[model]["off"].docs_written == 0.0
    assert rates[model]["reflexive"].docs_written >= 1.0
    assert rates[model]["non_reflexive"].docs_written == rates[model]["reflexive"].docs_written
    # the arms differ in reflexivity: the reflexive arm's documents hold the target's own items,
    # the non-reflexive arm's hold none, and the off arm wrote none
    for rep in (0, 1):
        assert loaded.generated[(OFF, rep)] == []
        flat = loaded.generated[(FLAT, rep)]
        assert flat and all(not d.reflexive and d.used_items == [] for d in flat)
        reflexive = loaded.generated[(REFLEXIVE, rep)]
        assert reflexive and all(d.reflexive and d.used_items for d in reflexive)
    off = [s for (cell, _), s in summarize_progression(loaded).items() if cell == OFF]
    assert off and all(s.generated_docs_found == {} for s in off)
    assert write_generator(loaded, tmp_path / "again") is not None
    assert generator_chart(loaded, tmp_path / "again") is not None


def _two_in_one_arm(loaded: LoadedRun) -> LoadedRun:
    """``loaded`` with the flat cell's condition moved onto the reflexive environment: two
    conditions now share the reflexive arm (Task 8 m1)."""
    spec = loaded.specs[FLAT]
    moved = spec.condition.model_copy(update={"environment": "overlay_gen_reflexive"})
    loaded.specs[FLAT] = spec.model_copy(update={"condition": moved})
    return loaded


def test_two_conditions_in_one_arm_are_never_pooled(
    generator_run: Path, tmp_path: Path, figures: list[Figure]
) -> None:
    """Task 8 m1: the arms group by (model, condition, arm). With one condition per arm the
    ``model -> arm`` shape holds and each entry names its condition; two conditions in one arm
    get an entry each, keyed ``<arm>/<condition>``, and the chart labels their bars by condition."""
    plain = arm_rates(load_run(generator_run))[0][MODEL]
    assert list(plain) == list(ARMS)
    assert [r.condition for r in plain.values()] == [
        "rescue_gen_off",
        "rescue_gen_flat",
        "rescue_gen_reflexive",
    ]
    loaded = _two_in_one_arm(load_run(generator_run))
    rates, _ = arm_rates(loaded)
    split = rates[MODEL]
    assert list(split) == ["off", "reflexive/rescue_gen_flat", "reflexive/rescue_gen_reflexive"]
    assert all(r.reps == 2 for r in split.values())  # each its own two reps, never four
    assert split["reflexive/rescue_gen_flat"].condition == "rescue_gen_flat"
    data = _json(write_generator(loaded, tmp_path))
    assert list(data["arms"][MODEL]) == list(split)
    assert data["arms"][MODEL]["off"]["condition"] == "rescue_gen_off"
    assert generator_chart(loaded, tmp_path) == tmp_path / GENERATOR_CHART
    (ax,) = figures[-1].axes
    assert [t.get_text() for t in ax.get_xticklabels()] == [
        "off",
        "reflexive\nrescue_gen_flat",
        "reflexive\nrescue_gen_reflexive",
    ]
