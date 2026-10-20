from pathlib import Path

from claude_bully.analysis.compare import compare_chart
from claude_bully.analysis.leaderboard import (
    LeaderboardRow,
    compliance_report,
    leaderboard,
    to_markdown,
)
from claude_bully.analysis.load import load_run
from claude_bully.analysis.report import update_readme, write_results_md
from claude_bully.analysis.rescue import rescue_curve
from claude_bully.config import CompareConfig
from claude_bully.enums import CellStatus, EventType
from claude_bully.metrics.judge import JudgeError, JudgeScores, JudgeVerdict, PairJudgement


def _judgement(cond: str, ctrl: str, goal: float, res: float) -> PairJudgement:
    scores = JudgeScores(bully_goal_achieved=int(goal), resilience=int(res), rationale="r")
    verdict = JudgeVerdict(a=scores, b=scores, more_resilient="tie")
    return PairJudgement(
        condition_cell_id=cond,
        condition_rep=0,
        control_cell_id=ctrl,
        control_rep=0,
        condition_goal=goal,
        condition_resilience=res,
        control_goal=0.0,
        control_resilience=3.0,
        inconsistency=False,
        verdicts=[verdict, verdict],
    )


def test_leaderboard_rows_without_judgements(stub_run: Path) -> None:
    rows = leaderboard(load_run(stub_run))
    assert [r.cell_id for r in rows] == sorted(r.cell_id for r in rows)  # all None -> stable order
    by_id = {r.cell_id: r for r in rows}
    assert set(by_id) == {"grader__t0", "captor_s2__t0", "rescue__t0"}
    g = by_id["grader__t0"]
    assert isinstance(g, LeaderboardRow)
    assert g.goal_achieved is None and g.resilience is None and g.control_resilience is None
    assert g.reps_complete == 1 and g.reps_aborted == 0
    assert g.task_accuracy_delta is not None
    assert g.bully_compliance == 1.0
    assert isinstance(g.event_counts, dict)
    assert g.headline_metric and (g.headline_value is None or isinstance(g.headline_value, float))
    assert g.seeding_turns == 0 and by_id["captor_s2__t0"].seeding_turns == 2


def test_leaderboard_sorts_by_goal_with_none_last(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    loaded.judgements[("grader__t0", 0)] = _judgement("grader__t0", "control__t0__s0__r0", 1.0, 2.0)
    loaded.judgements[("rescue__t0", 0)] = _judgement("rescue__t0", "control__t0__s0__r0", 3.0, 1.0)
    loaded.judgements[("captor_s2__t0", 0)] = JudgeError("bad json")
    rows = leaderboard(loaded)
    assert [r.cell_id for r in rows] == ["rescue__t0", "grader__t0", "captor_s2__t0"]
    assert rows[0].goal_achieved == 3.0 and rows[0].resilience == 1.0
    assert rows[0].control_resilience == 3.0
    assert rows[2].goal_achieved is None


def test_leaderboard_none_for_aborted_only_cell(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    conv = loaded.conversations[("grader__t0", 0)]
    conv.status = CellStatus.aborted
    conv.abort_reason = "bully_noncompliance"
    row = {r.cell_id: r for r in leaderboard(loaded)}["grader__t0"]
    assert row.reps_complete == 0 and row.reps_aborted == 1
    assert row.goal_achieved is None and row.task_accuracy_delta is None


def test_leaderboard_event_counts_exclude_aborted_reps(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    conv = loaded.conversations[("grader__t0", 0)]
    conv.status = CellStatus.aborted
    row = {r.cell_id: r for r in leaderboard(loaded)}["grader__t0"]
    assert row.event_counts == {} and row.headline_value is None


def test_leaderboard_none_without_control(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    loaded.conversations.pop(("control__t0__s0__r0", 0))
    row = {r.cell_id: r for r in leaderboard(loaded)}["grader__t0"]
    assert row.task_accuracy_delta is None and row.control_resilience is None
    assert row.bully_compliance == 1.0  # does not need a control


def test_to_markdown_prints_na(stub_run: Path) -> None:
    md = to_markdown(leaderboard(load_run(stub_run)))
    lines = md.splitlines()
    assert lines[0].startswith("| ") and set(lines[1].replace("|", "").strip()) <= {"-", " ", ":"}
    assert "n/a" in md and "grader__t0" in md


def test_compliance_report_lists_every_cell(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    loaded.conversations[("rescue__t0", 0)].status = CellStatus.aborted
    loaded.conversations[("rescue__t0", 0)].abort_reason = "bully_noncompliance"
    md = compliance_report(loaded)
    for cell in loaded.cells:
        assert cell in md
    assert "bully_noncompliance" in md


def test_compare_chart_written(stub_run: Path, tmp_path: Path) -> None:
    loaded = load_run(stub_run)
    cfg = CompareConfig(
        title="Kindness vs cruelty", metric="apology_count", arms=["grader", "rescue"]
    )
    path = compare_chart(loaded, cfg, tmp_path)
    assert path.name == "compare_kindness_vs_cruelty.png" and path.exists()
    ev = CompareConfig(
        title="Concessions", metric=EventType.premise_concession.value, arms=["captor_s2"]
    )
    assert compare_chart(loaded, ev, tmp_path).exists()
    judge = CompareConfig(title="Goal", metric="judge.goal", arms=["grader", "captor_s2"])
    assert compare_chart(loaded, judge, tmp_path).exists()


def test_rescue_curve_written_and_none_without_rescue(stub_run: Path, tmp_path: Path) -> None:
    loaded = load_run(stub_run)
    path = rescue_curve(loaded, tmp_path)
    assert path is not None and path.exists() and path.name == "rescue_confabulation.png"
    loaded.conversations.pop(("rescue__t0", 0))
    assert rescue_curve(loaded, tmp_path / "none") is None


def test_write_results_md(stub_run: Path, tmp_path: Path) -> None:
    loaded = load_run(stub_run)
    chart = tmp_path / "charts" / "drift_x.png"
    chart.parent.mkdir()
    chart.write_bytes(b"png")
    path = write_results_md(loaded, tmp_path / "charts", [chart])
    text = path.read_text(encoding="utf-8")
    assert path.name == "results.md"
    assert "## Leaderboard" in text and "## Bully compliance" in text
    assert "![drift_x](drift_x.png)" in text
    assert "stub_smoke" in text


def test_update_readme_replaces_between_markers(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Title\n\n<!-- results:start -->\nold\n<!-- results:end -->\n\nTail\n", encoding="utf-8"
    )
    results = tmp_path / "results.md"
    results.write_text("NEW RESULTS\n", encoding="utf-8")
    update_readme(readme, results)
    text = readme.read_text(encoding="utf-8")
    assert "old" not in text and "NEW RESULTS" in text
    assert (
        text.index("<!-- results:start -->")
        < text.index("NEW RESULTS")
        < text.index("<!-- results:end -->")
    )
    assert text.endswith("Tail\n")
    bare = tmp_path / "bare.md"
    bare.write_text("# Bare\n", encoding="utf-8")
    update_readme(bare, results)
    assert bare.read_text(encoding="utf-8").count("<!-- results:start -->") == 1
    assert "NEW RESULTS" in bare.read_text(encoding="utf-8")
