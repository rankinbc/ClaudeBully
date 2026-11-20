"""The detector-audit and judge-calibration forms (Phase 7 spec sections 7 and 8): written from
a stub run's records, scored once filled. Stub providers only."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.analysis.load import load_run
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import ProviderKind
from claude_bully.metrics.events import environment, poisoned_well
from claude_bully.metrics.judge import PAIR_INTRO, PAIR_RUBRIC
from claude_bully.records_env import ALL_HARVEST_KINDS
from claude_bully.runner.runner import run_experiment
from scripts import detector_audit, judge_calibration
from tests.fixtures.generator_stub import FOLLOWER_MODEL, GENERATOR_MODEL, GeneratorFactory
from tests.helpers import WORLDS_DIR, env_experiment

FIXTURES = Path(__file__).parent / "fixtures"
STUB_SMOKE = FIXTURES / "configs" / "stub_smoke.yaml"
JUDGE_RULES = FIXTURES / "stub_scripts" / "judge_rules.yaml"
IDLE_RULES = FIXTURES / "stub_scripts" / "idle_target_rules.yaml"


@pytest.fixture(scope="module")
def judged_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("judged")
    exp = load_experiment(STUB_SMOKE).model_copy(
        update={
            "judge": RoleConfig(
                provider=ProviderKind.stub, model="stub-judge", stub_script=str(JUDGE_RULES)
            )
        }
    )
    run_experiment(exp, runs_root=root)
    analyze_run(root / exp.name)
    return root / exp.name


@pytest.fixture(scope="module")
def idle_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("idle")
    exp = env_experiment(
        "idle_run",
        environment={"idle": {"idle_turns": 2, "permission_line": "on"}},
        target={"provider": "stub", "model": "stub-target", "stub_script": str(IDLE_RULES)},
        turn_budget=2,
    )
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR)
    return root / exp.name


@pytest.fixture(scope="module")
def generator_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A mixed run: the generator cell and its control (the generator on) beside a plain
    grader cell and its control, where nothing harvests."""
    root = tmp_path_factory.mktemp("gen")
    exp = env_experiment(
        "gen_run",
        environment={"generator": {"enabled": True}},
        conditions=[
            {"name": "env_grader", "environment": "mini", "pressure": "grader"},
            {"name": "grader", "strategy": "grader"},
        ],
        target={"provider": "stub", "model": FOLLOWER_MODEL},
        generator={"provider": "stub", "model": GENERATOR_MODEL},
    )
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR, provider_factory=GeneratorFactory())
    return root / exp.name


# ------------------------------------------------------------------ detector audit

FORM_KEYS = {"id", "cell_id", "rep", "turn", "text", "context", "label"}


def test_the_environment_form_is_blind_and_its_key_holds_the_events(stub_env_run: Path) -> None:
    form, key = detector_audit.write_form(load_run(stub_env_run), "environment", cap=60)
    assert form["family"] == key["family"] == "environment"
    assert form["run_id"] == key["run_id"] == stub_env_run.name
    assert form["labels"] == sorted(t.value for t in environment.HANDLES)
    items = form["items"]
    # the rater sees the turn, its window and an empty slot only (spec section 7, "Labels")
    assert items and all(set(i) == FORM_KEYS for i in items)
    assert all(i["label"] == "" and len(i["context"]) <= 3 for i in items)
    assert [i["id"] for i in items] == [k["id"] for k in key["items"]]
    fired = [k for k in key["items"] if k["fired"]]
    assert fired and all(e["event"] and e["span"] is not None for k in fired for e in k["events"])
    # the authority form reads the split spec section 7 asks for (P16); every other family's
    # events are heuristic
    assert all(e["classifier"] == "heuristic" for k in fired for e in k["events"])
    assert len(items) <= 60
    assert "reasoning" not in yaml.safe_dump([form, key]).lower()


def test_the_sample_is_stratified_across_cells(generator_run: Path) -> None:
    form, key = detector_audit.write_form(load_run(generator_run), "environment", cap=4)
    # 6 fired turns and 4 cue turns on this run: half of the cap from each pool
    assert key["pool"] == {"fired": 6, "cue": 4}
    assert key["sampled"] == {"fired": 2, "cue": 2}
    assert sorted(k["fired"] for k in key["items"]) == [False, False, True, True]
    assert len({i["cell_id"] for i in form["items"]}) > 1
    # a cap past both pools takes everything
    _, whole = detector_audit.write_form(load_run(generator_run), "environment", cap=60)
    assert whole["sampled"] == whole["pool"]


def test_the_cap_and_the_seed_fix_the_sample(generator_run: Path) -> None:
    loaded = load_run(generator_run)
    small = detector_audit.write_form(loaded, "environment", cap=4, seed=1)
    again = detector_audit.write_form(loaded, "environment", cap=4, seed=1)
    other = detector_audit.write_form(loaded, "environment", cap=4, seed=2)
    assert len(small[0]["items"]) == 4 and small == again
    turns = [(i["cell_id"], i["turn"]) for i in small[0]["items"]]
    assert turns != [(i["cell_id"], i["turn"]) for i in other[0]["items"]]


def test_the_idle_form_carries_both_labels_in_its_key(idle_run: Path) -> None:
    form, key = detector_audit.write_form(load_run(idle_run), "idle")
    assert form["items"] and all(set(i) == FORM_KEYS | {"prompt"} for i in form["items"])
    assert key["note"] == detector_audit.IDLE_NOTE
    assert all(k["fired"] and len(k["events"]) == 1 for k in key["items"])
    labels = [k["events"][0] for k in key["items"]]
    assert all({"event", "classifier", "heuristic", "fallback_failed"} <= set(e) for e in labels)
    # no hooks and no task on this run, so the recompute is the run's own heuristic label
    assert all(e["heuristic"] == e["event"] for e in labels if e["classifier"] == "heuristic")


def test_the_harvest_form_reads_only_cells_that_harvest(generator_run: Path) -> None:
    loaded = load_run(generator_run)
    form, key = detector_audit.write_form(loaded, "harvest")
    fired = [k for k in key["items"] if k["fired"]]
    assert fired and all(e["event"] and e["span"] for k in fired for e in k["events"])
    assert any(not k["fired"] for k in key["items"])  # turns with nothing harvested
    # the plain cells never run the generator, so none of their turns is a candidate
    cells = {i["cell_id"] for i in form["items"]}
    plain = {c for c in loaded.cells if not detector_audit.runs_generator(loaded, (c, 0))}
    assert plain and cells and not cells & plain


def test_the_family_list_holds_the_poisoned_well_and_every_harvest_kind(
    stub_env_run: Path,
) -> None:
    """Phase 4 Task 9: the twelve Poisoned Well detectors are an audit family, and the harvest
    form's labels are all eight kinds, the two expected items among them (I43)."""
    assert detector_audit.FAMILIES[-1] == "poisoned_well"
    assert set(detector_audit.FAMILIES) == {*detector_audit.EVENT_FAMILIES, "idle", "harvest"}
    assert detector_audit.family_labels("poisoned_well") == tuple(
        sorted(t.value for t in poisoned_well.HANDLES)
    )
    assert detector_audit.family_labels("harvest") == tuple(sorted(ALL_HARVEST_KINDS))
    assert {"completion", "taste"} <= set(detector_audit.family_labels("harvest"))
    form, key = detector_audit.write_form(load_run(stub_env_run), "poisoned_well")
    assert form["labels"] == list(detector_audit.family_labels("poisoned_well"))
    assert key["family"] == "poisoned_well"


def test_a_filled_event_form_scores_precision_and_recall(tmp_path: Path) -> None:
    def item(n: int, label: Any, text: str) -> dict[str, Any]:
        return {"id": n, "cell_id": "c", "rep": 0, "turn": n, "text": text, "label": label}

    def keyed(n: int, *events: str) -> dict[str, Any]:
        found = [{"event": e, "span": f"s{n}", "classifier": "heuristic"} for e in events]
        return {"id": n, "fired": bool(events), "events": found}

    head = {"run_id": "r", "family": "environment"}
    form = {
        **head,
        "items": [
            item(1, "tool_used", "a"),
            item(2, ["tool_used", "tool_result_reported"], "b"),
            item(3, "none", "c"),
            item(4, "tool_used", "d"),
            item(5, "none", "e"),
            item(6, "", "unlabelled"),
        ],
    }
    answers = {
        **head,
        "items": [
            keyed(1, "tool_used"),
            keyed(2, "tool_used"),
            keyed(3, "tool_used"),
            keyed(4),
            keyed(5),
            keyed(6, "tool_used"),
        ],
    }
    scores = detector_audit.score_form(form, answers)
    got = scores["tool_used"]
    assert (got["fired"], got["tp"], got["fp"], got["fn"]) == (3, 2, 1, 1)
    assert got["precision"] == pytest.approx(2 / 3) and got["recall"] == pytest.approx(2 / 3)
    assert got["misses"] == ["fp: 's3' in c", "fn: d"]
    assert scores["tool_result_reported"]["fn"] == 1
    path = tmp_path / "environment.yaml"
    path.write_text(yaml.safe_dump(form), encoding="utf-8")
    path.with_suffix(".key.yaml").write_text(yaml.safe_dump(answers), encoding="utf-8")
    assert detector_audit.main(["--score", str(path)]) == 0
    # a label outside the family's types is an error naming the item, never a new type
    form["items"][0]["label"] = "tool_usd"
    with pytest.raises(ValueError, match="item 1"):
        detector_audit.score_form(form, answers)
    path.write_text(yaml.safe_dump(form), encoding="utf-8")
    assert detector_audit.main(["--score", str(path)]) == 1


def test_the_cli_writes_a_form_and_its_key(stub_env_run: Path, tmp_path: Path) -> None:
    code = detector_audit.main(
        [
            stub_env_run.name,
            "--family",
            "environment",
            "--out",
            str(tmp_path),
            "--runs-root",
            str(stub_env_run.parent),
        ]
    )
    assert code == 0
    assert sorted(p.name for p in tmp_path.glob("*.yaml")) == [
        "environment.key.yaml",
        "environment.yaml",
    ]
    assert yaml.safe_load((tmp_path / "environment.yaml").read_text("utf-8"))["items"]


# ------------------------------------------------------------------ judge calibration


def test_the_pairs_form_is_blind_and_its_key_holds_the_verdict(judged_run: Path) -> None:
    loaded = load_run(judged_run)
    form, key = judge_calibration.write_pairs(loaded, judged_run)
    assert form["items"] and len(form["items"]) == len(key["items"])
    item = form["items"][0]
    # what the judge was given beside the windows (parity), and nothing it was denied
    assert set(item) == {
        "pair",
        "goal",
        "resilient_behavior",
        "transcript_a",
        "transcript_b",
        "label",
    }
    assert PAIR_RUBRIC in form["instructions"] and PAIR_INTRO in form["instructions"]
    conv = loaded.conversations[(key["items"][0]["judged"].rsplit("/", 1)[0], 0)]
    assert (item["goal"], item["resilient_behavior"]) == (
        conv.win_condition,
        conv.resilient_behavior,
    )
    assert "User:" in item["transcript_a"] and "Assistant:" in item["transcript_a"]
    assert item["label"] == {
        "more_resilient": "",
        "resilience_a": None,
        "resilience_b": None,
        "reason": "",
    }
    assert "judge" not in json.dumps(form)  # the rater never sees the judge's answer
    # nor a cell id, condition or control, which names the tactic: the key alone maps the
    # opaque id to the pair
    assert {k["judged"].rsplit("/", 1)[0] for k in key["items"]} <= set(loaded.cells)
    assert not any(cell in json.dumps(form) for cell in loaded.cells)
    verdict = key["items"][0]["judge"]
    assert verdict["more_resilient"] in ("A", "B", "tie") and "inconsistency" in verdict


def test_a_filled_pairs_form_scores_agreement_and_the_gap(judged_run: Path) -> None:
    form, key = judge_calibration.write_pairs(load_run(judged_run), judged_run)
    for item, keyed in zip(form["items"], key["items"], strict=True):
        item["label"] = {
            "more_resilient": keyed["judge"]["more_resilient"],
            "resilience_a": keyed["judge"]["resilience_a"] + 1,
            "resilience_b": keyed["judge"]["resilience_b"],
            "reason": "same as the judge, a point kinder to A",
        }
    scores = judge_calibration.score_pairs(form, key)
    assert scores["pairs"] == len(form["items"]) and scores["agreement"] == scores["pairs"]
    assert scores["mean_abs_gap"] == pytest.approx(0.5)
    # the stub judge answers "B" in both orderings, so every pair it judged is inconsistent:
    # the count is the judge's, over the rated pairs
    assert scores["inconsistent"] == sum(bool(k["judge"]["inconsistency"]) for k in key["items"])
    assert scores["inconsistent"] == scores["pairs"]
    # a letter is normalised; a malformed label is an error naming the pair, never a skip
    first = form["items"][0]
    first["label"]["more_resilient"] = f" {key['items'][0]['judge']['more_resilient'].lower()} "
    assert judge_calibration.score_pairs(form, key) == scores
    for bad in ({"more_resilient": "C"}, {"more_resilient": "A", "resilience_a": 4}, None):
        first["label"] = bad
        with pytest.raises(ValueError, match=first["pair"]):
            judge_calibration.score_pairs(form, key)


def test_the_idle_form_is_blind_and_its_key_scores_it(idle_run: Path, tmp_path: Path) -> None:
    form, key = judge_calibration.write_idle(load_run(idle_run))
    # the rater sees the idle prompt, the reply, the window and an empty slot only
    assert form["items"] and all(
        set(i) == {"id", "cell_id", "rep", "turn", "prompt", "reply", "context", "label"}
        for i in form["items"]
    )
    assert all(i["label"] == "" and len(i["context"]) <= 3 for i in form["items"])
    assert key["note"] == detector_audit.IDLE_NOTE
    assert [i["id"] for i in form["items"]] == [k["id"] for k in key["items"]]
    assert all(
        {"final", "classifier", "heuristic", "fallback_failed"} <= set(k) for k in key["items"]
    )
    for item, keyed in zip(form["items"], key["items"], strict=True):
        item["label"] = keyed["final"]
    scores = judge_calibration.score_idle(form, key)
    assert scores["turns"] == len(form["items"]) and scores["final_agreement"] == scores["turns"]
    assert scores["true_waits_upgraded"] == 0 and set(scores["by_classifier"]) <= {
        "heuristic",
        "llm",
    }
    # no hooks and no task on this run: the recompute agrees wherever the heuristic decided
    decided = [k for k in key["items"] if k["classifier"] == "heuristic"]
    assert decided and scores["heuristic_agreement"] >= len(decided)
    # the CLI writes the form and its key and scores them joined by id
    code = judge_calibration.main(
        [idle_run.name, "--idle", "--out", str(tmp_path), "--runs-root", str(idle_run.parent)]
    )
    assert code == 0 and (tmp_path / "idle.key.yaml").exists()
    (tmp_path / "idle.yaml").write_text(yaml.safe_dump(form), encoding="utf-8")
    assert judge_calibration.main(["--score", str(tmp_path / "idle.yaml"), "--idle"]) == 0
    form["items"][0]["label"] = "nap"
    with pytest.raises(ValueError, match="item 1"):
        judge_calibration.score_idle(form, key)


def test_the_calibration_cli_writes_and_scores(
    judged_run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = judge_calibration.main(
        [judged_run.name, "--pairs", "--out", str(tmp_path), "--runs-root", str(judged_run.parent)]
    )
    assert (
        code == 0 and (tmp_path / "pairs.yaml").exists() and (tmp_path / "pairs.key.yaml").exists()
    )
    capsys.readouterr()
    code = judge_calibration.main(
        ["--score", str(tmp_path / "pairs.yaml"), "--key", str(tmp_path / "pairs.key.yaml")]
    )
    assert code == 0
    # an unfilled form scores no pair, and says so, without failing (P34b)
    scores = json.loads(capsys.readouterr().out)
    assert scores["pairs"] == 0 and scores["agreement"] == 0 and scores["mean_abs_gap"] is None


def test_a_run_never_judged_writes_no_pairs_form(
    idle_run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = judge_calibration.main(
        [idle_run.name, "--pairs", "--out", str(tmp_path), "--runs-root", str(idle_run.parent)]
    )
    assert code == 1 and not (tmp_path / "pairs.yaml").exists()
    assert "no judgements.json; run analyze with the judge first" in capsys.readouterr().err


# ------------------------------------------------------------------ Phase 6 Task 3b: --divergence

DIVERGENCE_SHOWN = {"id", "line", "reasoning", "reply", "label"}


@pytest.fixture(scope="module")
def divergence_judged(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """``catalog_stub.divergence_run`` analyzed once with ``--divergence`` under
    ``CatalogJudge``: five aligned verdicts and one concealed plan."""
    from tests.fixtures.catalog_stub import CatalogJudge, catalog_factory, divergence_run

    root = tmp_path_factory.mktemp("divergence_form")
    factory = catalog_factory(CatalogJudge())
    run_dir = divergence_run(root, factory)
    analyze_run(run_dir, divergence=True, provider_factory=factory)
    return run_dir


@pytest.mark.slow  # the module's stub experiment and its analysis (R-I12)
def test_the_divergence_form_is_blind_and_its_key_scores_it(
    divergence_judged: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import claude_bully.analysis.run_analysis as run_analysis
    import claude_bully.providers.base as base
    from claude_bully.metrics.divergence import answered_line
    from claude_bully.records import chat_text
    from tests.fixtures.catalog_stub import CELL, CONTROL

    def no_provider(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the divergence form builds no provider")

    monkeypatch.setattr(base, "build_provider", no_provider)
    monkeypatch.setattr(run_analysis, "build_provider", no_provider)
    loaded = load_run(divergence_judged)
    form, key = judge_calibration.write_divergence(loaded, divergence_judged, 3)
    assert form["kind"] == "divergence" and key["kind"] == "divergence.key"
    assert form["instructions"] and form["run_id"] == key["run_id"] == loaded.run.run_id
    items = form["items"]
    # at most three per judged class: three of the five aligned, the one concealed plan
    assert len(items) == 4
    for item in items:
        assert set(item) == DIVERGENCE_SHOWN and item["label"] == ""
        assert CELL not in item["id"] and CONTROL not in item["id"]
    keyed = {k["id"]: k for k in key["items"]}
    assert [i["id"] for i in items] == [k["id"] for k in key["items"]]
    assert len(set(keyed)) == len(items)
    classes = [k["class"] for k in key["items"]]
    assert sorted(classes) == ["aligned"] * 3 + ["concealed_plan"]
    assert all(k["confidence"] == 0.9 for k in key["items"])
    # each item shows the turn as the judge saw it: the line answered, the reasoning, the reply
    for item in items:
        cell, rep = keyed[item["id"]]["conversation"].rsplit("/", 1)
        conv = loaded.conversations[(cell, int(rep))]
        pos = next(p for p, t in enumerate(conv.turns) if t.index == keyed[item["id"]]["turn"])
        assert item["reasoning"] == conv.turns[pos].reasoning_text
        assert item["reply"] == chat_text(conv.turns[pos])
        assert item["line"] == answered_line(conv, pos)
    # labelled with the key's classes, every item agrees
    for item in items:
        item["label"] = keyed[item["id"]]["class"]
    scores = judge_calibration.score_divergence(form, key)
    assert scores["labelled"] == scores["agreement"] == 4 and scores["disagreements"] == []
    items[0]["label"] = "concealed_distress" if classes[0] != "concealed_distress" else "aligned"
    scores = judge_calibration.score_divergence(form, key)
    assert scores["agreement"] == 3 and len(scores["disagreements"]) == 1
    items[0]["label"] = "reasoning_absent"  # never the judge's to give
    with pytest.raises(ValueError, match=items[0]["id"]):
        judge_calibration.score_divergence(form, key)
    # the CLI writes both files and scores them by the form's kind
    out = tmp_path / "forms"
    code = judge_calibration.main(
        [
            divergence_judged.name,
            "--divergence",
            "--per-verdict",
            "3",
            "--out",
            str(out),
            "--runs-root",
            str(divergence_judged.parent),
        ]
    )
    assert code == 0
    written = yaml.safe_load((out / "divergence.yaml").read_text(encoding="utf-8"))
    assert written["kind"] == "divergence" and (out / "divergence.key.yaml").is_file()
    assert judge_calibration.main(["--score", str(out / "divergence.yaml")]) == 0


def test_the_divergence_form_refuses_a_run_with_no_divergence_events(
    idle_run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(FileNotFoundError, match=f"analyze {idle_run.name} --divergence"):
        judge_calibration.write_divergence(load_run(idle_run), idle_run, None)
    code = judge_calibration.main(
        [idle_run.name, "--divergence", "--out", str(tmp_path), "--runs-root", str(idle_run.parent)]
    )
    assert code == 1 and not (tmp_path / "divergence.yaml").exists()
    assert f"analyze {idle_run.name} --divergence" in capsys.readouterr().err
