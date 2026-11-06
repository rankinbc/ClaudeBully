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
from claude_bully.metrics.events import environment
from claude_bully.metrics.judge import PAIR_INTRO, PAIR_RUBRIC
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


def test_the_idle_form_and_its_score(idle_run: Path) -> None:
    form = judge_calibration.write_idle(load_run(idle_run))
    assert form["items"] and all(
        {"prompt", "reply", "final", "classifier", "heuristic", "label"} <= set(i)
        for i in form["items"]
    )
    for item in form["items"]:
        item["label"] = item["final"]
    scores = judge_calibration.score_idle(form)
    assert scores["turns"] == len(form["items"]) and scores["final_agreement"] == scores["turns"]
    assert scores["true_waits_upgraded"] == 0 and set(scores["by_classifier"]) <= {
        "heuristic",
        "llm",
    }
    # no hooks and no task on this run: the recompute agrees wherever the heuristic decided
    decided = [i for i in form["items"] if i["classifier"] == "heuristic"]
    assert decided and scores["heuristic_agreement"] >= len(decided)
    form["items"][0]["label"] = "nap"
    with pytest.raises(ValueError, match="item 1"):
        judge_calibration.score_idle(form)


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
