"""The rate-limit wait (Phase 7 spec section 9), promote's real-name policy and the README chart
links (section 10)."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from claude_bully import cli
from claude_bully.analysis.promote import (
    RealNameReport,
    display_names,
    load_real_name_patterns,
    promote,
    scan_real_names,
)
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import load_experiment
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.runner.wait import DEFAULT_WAIT_S, wait_on_rate_limit
from tests.test_real_names import REAL

FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "stub_smoke.yaml"
runner = CliRunner()


# ------------------------------------------------------------------ the wait


def _flaky(failures: int, retry_after: float | None = 30) -> Any:
    left = {"n": failures}

    def action() -> str:
        if left["n"]:
            left["n"] -= 1
            raise RateLimitExit("usage limit", retry_after_s=retry_after)
        return "done"

    return action


def test_the_wait_sleeps_for_retry_after_then_retries() -> None:
    slept: list[float] = []
    said: list[str] = []
    out = wait_on_rate_limit(_flaky(2), 60, sleep=slept.append, say=said.append)
    assert out == "done" and slept == [30, 30] and len(said) == 2


def test_the_wait_defaults_to_fifteen_minutes_without_retry_after() -> None:
    slept: list[float] = []
    assert wait_on_rate_limit(_flaky(1, None), 60, sleep=slept.append, say=lambda s: None) == "done"
    assert slept == [DEFAULT_WAIT_S]


def test_the_ceiling_gives_up_and_no_ceiling_never_waits() -> None:
    slept: list[float] = []
    with pytest.raises(RateLimitExit):
        wait_on_rate_limit(_flaky(3, 60 * 25), 60, sleep=slept.append, say=lambda s: None)
    assert slept == [60 * 25, 60 * 25]  # a third wait would pass the hour
    with pytest.raises(RateLimitExit):
        wait_on_rate_limit(_flaky(1), None, sleep=slept.append, say=lambda s: None)
    assert len(slept) == 2  # nothing more slept


def test_run_and_analyze_take_the_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("claude_bully.runner.wait.time.sleep", slept.append)
    calls = {"run": 0, "analyze": 0}

    def flaky_run(*args: Any, **kwargs: Any) -> Any:
        calls["run"] += 1
        if calls["run"] == 1:
            raise RateLimitExit("usage limit", retry_after_s=7)
        from claude_bully.runner.runner import RunSummary

        return RunSummary(run_id="x", cells_total=0)

    def flaky_analyze(*args: Any, **kwargs: Any) -> Path:
        calls["analyze"] += 1
        if calls["analyze"] == 1:
            raise RateLimitExit("judge usage limit", retry_after_s=9)
        return tmp_path / "results.md"

    monkeypatch.setattr(cli, "run_experiment", flaky_run)
    monkeypatch.setattr(cli, "analyze_run", flaky_analyze)
    result = runner.invoke(
        cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path), "--wait-on-rate-limit", "60"]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        cli.app, ["analyze", "x", "--runs-root", str(tmp_path), "--wait-on-rate-limit", "60"]
    )
    assert result.exit_code == 0, result.output
    assert slept == [7, 9] and calls == {"run": 2, "analyze": 2}
    without = runner.invoke(cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path)])
    assert without.exit_code == 0  # the third call succeeds at once; no flag, no wait


# ------------------------------------------------------------------ promote's policy


def _run(root: Path) -> RunStore:
    exp = load_experiment(FIXTURE)
    run_experiment(exp, runs_root=root)
    analyze_run(root / exp.name, judge=False)
    return RunStore(root, exp.name)


def _rewrite_turn(store: RunStore, cell: str, *, speaker: str, text: str) -> None:
    path = store.cell_dir(cell) / "rep0.turns.jsonl"
    lines = [json.loads(ln) for ln in path.read_text("utf-8").splitlines()]
    target = next(ln for ln in lines if ln["speaker"] == speaker)
    target["text"] = text
    path.write_text("".join(json.dumps(ln) + "\n" for ln in lines), encoding="utf-8")


def test_a_harness_side_real_name_blocks_promotion(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    _rewrite_turn(
        store, "grader__t0", speaker="bully", text=f"I read it in {REAL[3]} this morning."
    )
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert report.blocking and not report.reported
    with pytest.raises(ValueError, match="grader__t0.*bully"):
        promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert not (tmp_path / "results" / store.run_id).exists()


def test_a_target_side_real_name_is_reported_and_promoted(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    _rewrite_turn(
        store, "grader__t0", speaker="target", text=f"As {REAL[3]} reported, the kettle is fixed."
    )
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert report.reported and not report.blocking
    dest = promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert dest.exists()
    result = runner.invoke(
        cli.app,
        [
            "promote",
            store.run_id,
            "--force",
            "--runs-root",
            str(tmp_path / "runs"),
            "--results-root",
            str(tmp_path / "results"),
        ],
    )
    assert result.exit_code == 0 and "reported" in result.output.lower()
    assert "grader__t0" in result.output


def test_the_display_name_and_exempt_names_are_spared(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    assert "claude" in {n.lower() for n in display_names(store)}
    _rewrite_turn(
        store, "grader__t0", speaker="target", text="I am Claude, and that is all I will say."
    )
    assert scan_real_names(
        store, load_real_name_patterns(), display_names(store)
    ) == RealNameReport([], [])
    _rewrite_turn(store, "grader__t0", speaker="target", text=f"My maker is {REAL[0]}.")
    report = scan_real_names(store, load_real_name_patterns(), display_names(store) | {REAL[0]})
    assert report == RealNameReport([], [])
    result = runner.invoke(
        cli.app,
        [
            "promote",
            store.run_id,
            "--exempt",
            REAL[0],
            "--runs-root",
            str(tmp_path / "runs"),
            "--results-root",
            str(tmp_path / "results"),
        ],
    )
    assert result.exit_code == 0 and "reported" not in result.output.lower()


# ------------------------------------------------------------------ the README links


def test_from_results_links_charts_under_results(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    readme = tmp_path / "README.md"
    readme.write_text("# x\n", encoding="utf-8")
    result = runner.invoke(
        cli.app,
        [
            "readme-results",
            store.run_id,
            "--from-results",
            "--results-root",
            str(tmp_path / "results"),
            "--readme",
            str(readme),
        ],
    )
    assert result.exit_code == 0, result.output
    text = readme.read_text(encoding="utf-8")
    assert f"](results/{store.run_id}/analysis/" in text
    assert "](output/" not in text and "](rescue_confabulation.png)" not in text
    plain = runner.invoke(
        cli.app,
        [
            "readme-results",
            store.run_id,
            "--runs-root",
            str(tmp_path / "runs"),
            "--readme",
            str(readme),
        ],
    )
    assert plain.exit_code == 0 and "](rescue_confabulation.png)" in readme.read_text("utf-8")
