"""The detector-audit and judge-calibration forms (Phase 7 spec sections 7 and 8): written from
a stub run's records, scored once filled. Stub providers only."""

import json
from pathlib import Path

import pytest
import yaml

from claude_bully.analysis.load import load_run
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import ProviderKind
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
    root = tmp_path_factory.mktemp("gen")
    exp = env_experiment(
        "gen_run",
        environment={"generator": {"enabled": True}},
        target={"provider": "stub", "model": FOLLOWER_MODEL},
        generator={"provider": "stub", "model": GENERATOR_MODEL},
    )
    run_experiment(
        exp,
        runs_root=root,
        worlds_dir=WORLDS_DIR,
        only="env_grader*",
        provider_factory=GeneratorFactory(),
    )
    return root / exp.name


# ------------------------------------------------------------------ detector audit


def test_the_environment_form_lists_fired_events_and_cue_turns(stub_env_run: Path) -> None:
    form = detector_audit.write_form(load_run(stub_env_run), "environment", cap=60)
    assert form["family"] == "environment" and form["run_id"] == stub_env_run.name
    items = form["items"]
    fired = [i for i in items if i["fired"]]
    assert fired and all(i["event"] and i["span"] is not None for i in fired)
    # the authority form reads the split spec section 7 asks for (P16); every other family's
    # events are heuristic
    assert all(i["classifier"] == "heuristic" for i in fired)
    assert all(i["label"] == "" and len(i["context"]) <= 3 for i in items)
    assert all(
        set(i) >= {"id", "cell_id", "rep", "turn", "fired", "text", "context", "label"}
        for i in items
    )
    assert len(items) <= 60
    assert "reasoning" not in yaml.safe_dump(form).lower()


def test_the_cap_and_the_seed_fix_the_sample(stub_env_run: Path) -> None:
    loaded = load_run(stub_env_run)
    small = detector_audit.write_form(loaded, "position", cap=3, seed=1)
    again = detector_audit.write_form(loaded, "position", cap=3, seed=1)
    assert len(small["items"]) <= 3 and small == again


def test_the_idle_form_carries_both_labels(idle_run: Path) -> None:
    form = detector_audit.write_form(load_run(idle_run), "idle")
    items = form["items"]
    assert items and all(i["fired"] for i in items)
    assert all({"final", "classifier", "heuristic", "prompt"} <= set(i) for i in items)


def test_the_harvest_form_has_one_item_per_harvested_span(generator_run: Path) -> None:
    form = detector_audit.write_form(load_run(generator_run), "harvest")
    fired = [i for i in form["items"] if i["fired"]]
    assert fired and all(i["kind"] and i["span"] for i in fired)
    assert any(not i["fired"] for i in form["items"])  # turns with nothing harvested


def test_a_filled_event_form_scores_precision_and_recall(tmp_path: Path) -> None:
    form = {
        "run_id": "r",
        "family": "environment",
        "items": [
            {"id": 1, "fired": True, "event": "tool_used", "label": "tool_used", "text": "a"},
            {"id": 2, "fired": True, "event": "tool_used", "label": "tool_used", "text": "b"},
            {"id": 3, "fired": True, "event": "tool_used", "label": "none", "text": "c"},
            {"id": 4, "fired": False, "event": None, "label": "tool_used", "text": "d"},
            {"id": 5, "fired": False, "event": None, "label": "none", "text": "e"},
        ],
    }
    scores = detector_audit.score_form(form)
    got = scores["tool_used"]
    assert (got["fired"], got["tp"], got["fp"], got["fn"]) == (3, 2, 1, 1)
    assert got["precision"] == pytest.approx(2 / 3) and got["recall"] == pytest.approx(2 / 3)
    assert got["misses"] == ["fp: c", "fn: d"]
    path = tmp_path / "form.yaml"
    path.write_text(yaml.safe_dump(form), encoding="utf-8")
    assert detector_audit.main(["--score", str(path)]) == 0


def test_the_cli_writes_a_form_file(stub_env_run: Path, tmp_path: Path) -> None:
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
    [form] = list(tmp_path.glob("*.yaml"))
    assert form.name == "environment.yaml" and yaml.safe_load(form.read_text("utf-8"))["items"]


# ------------------------------------------------------------------ judge calibration


def test_the_pairs_form_is_blind_and_its_key_holds_the_verdict(judged_run: Path) -> None:
    form, key = judge_calibration.write_pairs(load_run(judged_run), judged_run)
    assert form["items"] and len(form["items"]) == len(key["items"])
    item = form["items"][0]
    assert set(item) == {"pair", "transcript_a", "transcript_b", "label"}
    assert "User:" in item["transcript_a"] and "Assistant:" in item["transcript_a"]
    assert item["label"] == {
        "more_resilient": "",
        "resilience_a": None,
        "resilience_b": None,
        "reason": "",
    }
    assert "judge" not in json.dumps(form)  # the rater never sees the judge's answer
    # nor the cell id, which names the tactic: the key alone maps the opaque id to the pair
    judged = {k["judged"].split("/")[0] for k in key["items"]}
    assert judged and not any(cell in json.dumps(form) for cell in judged)
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
