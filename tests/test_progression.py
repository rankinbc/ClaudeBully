"""Progression metrics, the adoption-by-rung headline chart, and environment rows in analysis.

Runs (tests/conftest.py):

- ``stub_env_run``: the scripted ``env_grader__t0`` conversation of tests/test_runner_env.py
  (turn 1 asks a world question that opens ``first_crumb``, turn 3 fetches the parking memo, a seam
  document) beside a plain ``grader__t0`` cell.
- ``stub_env_arms_run``: the mini world under triggered and scheduled gating, two target models.
  Triggered: ``first_crumb`` opens at turn 1 and turn 3 restates the memo it just read (a belief
  adoption). Scheduled: the three rungs open at turns 1, 3 and 5; the memo fetch at turn 3 is
  refused, so the same restatement adopts nothing.
"""

import json
import logging
import shutil
from pathlib import Path

import pytest

from claude_bully.analysis.leaderboard import (
    EnvironmentLeaderboardRow,
    LeaderboardRow,
    leaderboard,
    to_markdown,
)
from claude_bully.analysis.load import load_run
from claude_bully.analysis.progression import (
    ADOPTION_CHART,
    RUNGS_CHART,
    ProgressionSummary,
    adoption_by_rung,
    adoption_by_rung_chart,
    rungs_reached_chart,
    summarize_progression,
)
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.enums import EventType, Layer
from claude_bully.environments.world import World, load_world
from claude_bully.records import Event
from claude_bully.records_env import RungUnlock
from tests.helpers import WORLDS_DIR

ENV = ("env_grader__t0", 0)
ENV_CONTROL = ("control__t0__s0__r0__emini", 0)
PLAIN = ("grader__t0", 0)
RUNGS = ["fragment", "first_crumb", "the_log"]


# ------------------------------------------------------------------ the loader


def test_loaded_run_reads_the_streams_and_the_world_from_the_run_dir(stub_env_run: Path) -> None:
    loaded = load_run(stub_env_run)
    assert [c.id for c in loaded.tool_calls[ENV]] == ["call-1-1", "call-3-1"]
    assert [r.type for r in loaded.trigger_records[ENV]] == ["trigger", "unlock", "discovery"]
    world = loaded.worlds[ENV]
    assert isinstance(world, World)
    mini = load_world("mini", WORLDS_DIR)
    assert world.sheet == mini.sheet
    assert world.root == stub_env_run / ENV[0]  # the run directory, not the repo's worlds
    assert list(world.ladders) == ["default"]
    assert [r.name for r in world.ladders["default"].rungs] == RUNGS
    assert set(world.documents) == set(mini.documents)
    for doc_id, doc in mini.documents.items():
        got = world.documents[doc_id]
        assert (got.layer, got.title, got.url, got.path) == (
            doc.layer,
            doc.title,
            doc.url,
            doc.path,
        )
    # bodies only for the documents the target could reach by the end
    assert world.documents["ops-memo-parking"].body == mini.documents["ops-memo-parking"].body
    assert world.documents["night-gate-log"].body == ""
    assert loaded.tool_calls[PLAIN] == [] and loaded.worlds[PLAIN] is None


def test_environment_events_are_detected_in_analysis(stub_env_run: Path) -> None:
    loaded = load_run(stub_env_run)
    by_turn = {(e.turn_index, e.type) for e in loaded.events[ENV]}
    assert (1, EventType.tool_used) in by_turn and (3, EventType.tool_used) in by_turn
    # turn 3: "The staff parking note says the east lot is closed until the end of September."
    assert (3, EventType.tool_result_reported) in by_turn
    assert not {e.type for e in loaded.events[PLAIN]} & {EventType.tool_used}


def test_an_old_snapshot_without_the_sheet_skips_the_world_detectors_with_one_warning(
    stub_env_run: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    run = tmp_path / stub_env_run.name
    shutil.copytree(stub_env_run, run)
    for path in run.glob("*/rep*.world.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(
            json.dumps({"world_hash": payload["world_hash"], "docs": payload["docs"]}),
            encoding="utf-8",
        )
    with caplog.at_level(logging.WARNING, logger="claude_bully.analysis.load"):
        loaded = load_run(run)
    warnings = [r for r in caplog.records if r.name == "claude_bully.analysis.load"]
    assert len(warnings) == 1, warnings  # two environment conversations, one warning
    assert "world sheet" in warnings[0].getMessage()
    assert loaded.worlds[ENV] is None and loaded.worlds[ENV_CONTROL] is None
    assert EventType.tool_used in {e.type for e in loaded.events[ENV]}  # the rest still run
    summary = summarize_progression(loaded)[ENV]
    # without the ladder the reach falls back to the number of rungs fired
    assert summary.max_rung_reached == 1


# ------------------------------------------------------------ progression


def test_progression_of_the_scripted_environment_run(stub_env_run: Path) -> None:
    summaries = summarize_progression(load_run(stub_env_run))
    assert set(summaries) == {ENV, ENV_CONTROL}  # plain conversations have none
    assert summaries[ENV] == ProgressionSummary(
        cell_id="env_grader__t0",
        rep=0,
        max_rung_reached=2,  # first_crumb, the second rung of the ladder
        rungs_timeline=[("first_crumb", 1)],
        discovery_depth=Layer.seam,
        docs_found_by_layer={Layer.seam: 1},
        trigger_latency={"first_crumb": 1},
        self_driven_unlocks=1,
        nudged_unlocks=0,
        chain_length_to_deepest=2,
    )
    assert summaries[ENV_CONTROL].rungs_timeline == [("first_crumb", 1)]


def test_progression_of_the_scheduled_arm(stub_env_arms_run: Path) -> None:
    summaries = summarize_progression(load_run(stub_env_arms_run))
    scheduled = summaries[("env_scheduled__t0", 0)]
    assert scheduled.max_rung_reached == 3
    assert scheduled.rungs_timeline == [("fragment", 1), ("first_crumb", 3), ("the_log", 5)]
    assert scheduled.trigger_latency == {}  # nothing was earned
    assert (scheduled.self_driven_unlocks, scheduled.nudged_unlocks) == (0, 0)
    # the memo fetch at turn 3 came before first_crumb opened it: nothing was found
    assert scheduled.discovery_depth is None and scheduled.docs_found_by_layer == {}
    assert scheduled.chain_length_to_deepest == 0
    triggered = summaries[("env_triggered__t1", 0)]
    assert triggered.max_rung_reached == 2 and triggered.discovery_depth is Layer.seam


def test_a_planted_unlock_line_makes_the_next_unlock_nudged(stub_env_run: Path) -> None:
    """The bully turn after an unlock carries its line; a rung triggered after that is nudged,
    and its latency counts the target replies from that bully turn to the trigger."""
    loaded = load_run(stub_env_run)
    records = loaded.trigger_records[ENV]
    records.append(
        RungUnlock(
            turn=5,
            rung="the_log",
            triggered_by="trig-5-anomaly_noticed",
            docs_unlocked=[],
            bully_line_used=None,
            role_shift=None,
        )
    )
    summary = summarize_progression(loaded)[ENV]
    assert summary.rungs_timeline == [("first_crumb", 1), ("the_log", 5)]
    assert summary.max_rung_reached == 3
    # bully turn 2 carried first_crumb's line; target replies 3 and 5 follow it
    assert summary.trigger_latency == {"first_crumb": 1, "the_log": 2}
    assert (summary.self_driven_unlocks, summary.nudged_unlocks) == (1, 1)


def test_a_run_that_never_fires_a_rung_reaches_zero(stub_env_run: Path) -> None:
    loaded = load_run(stub_env_run)
    loaded.trigger_records[ENV] = [
        r for r in loaded.trigger_records[ENV] if not isinstance(r, RungUnlock)
    ]
    summary = summarize_progression(loaded)[ENV]
    assert summary.max_rung_reached == 0 and summary.rungs_timeline == []


# ------------------------------------------------------- the headline chart


def test_adoption_by_rung_triggered_versus_scheduled(stub_env_arms_run: Path) -> None:
    rates = adoption_by_rung(load_run(stub_env_arms_run))
    for model in ("stub-target-a", "stub-target-b"):
        assert rates[(model, "triggered")] == {
            "fragment": None,  # never reached
            "first_crumb": 1.0,
            "the_log": None,
        }
        assert rates[(model, "scheduled")] == {"fragment": 0.0, "first_crumb": 0.0, "the_log": 0.0}


def test_only_belief_adoption_moves_the_rate(stub_env_arms_run: Path) -> None:
    """A restated surface page is adopted but is not belief in the premise; a seam claim is."""
    loaded = load_run(stub_env_arms_run)
    key = ("env_scheduled__t0", 0)

    def adopted(layer: str) -> Event:
        return Event(
            type=EventType.tool_result_adopted,
            turn_index=3,
            span="s",
            confidence=0.75,
            attrs={"layer": layer},
        )

    loaded.events[key].append(adopted("surface"))
    assert adoption_by_rung(loaded)[("stub-target-a", "scheduled")]["fragment"] == 0.0
    loaded.events[key].append(adopted("seam"))  # turn 3 is inside fragment's window (1, 3]
    rates = adoption_by_rung(loaded)[("stub-target-a", "scheduled")]
    assert rates == {"fragment": 1.0, "first_crumb": 0.0, "the_log": 0.0}


def test_the_adoption_chart_is_written_when_both_arms_exist(
    stub_env_arms_run: Path, tmp_path: Path
) -> None:
    loaded = load_run(stub_env_arms_run)
    path = adoption_by_rung_chart(loaded, tmp_path / "a")
    assert path == tmp_path / "a" / ADOPTION_CHART and path.exists()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    for key in [k for k in loaded.conversations if k[0].startswith("env_scheduled")]:
        loaded.conversations.pop(key)
    assert adoption_by_rung_chart(loaded, tmp_path / "b") is None
    assert not (tmp_path / "b").exists()


def test_no_adoption_chart_for_a_single_arm_or_a_plain_run(
    stub_env_run: Path, stub_run: Path, tmp_path: Path
) -> None:
    assert adoption_by_rung_chart(load_run(stub_env_run), tmp_path / "one_arm") is None
    assert adoption_by_rung_chart(load_run(stub_run), tmp_path / "plain") is None
    assert not (tmp_path / "one_arm").exists() and not (tmp_path / "plain").exists()


def test_the_rungs_reached_chart(stub_env_arms_run: Path, stub_run: Path, tmp_path: Path) -> None:
    path = rungs_reached_chart(load_run(stub_env_arms_run), tmp_path)
    assert path == tmp_path / RUNGS_CHART and path.exists()
    assert rungs_reached_chart(load_run(stub_run), tmp_path / "plain") is None


def test_analyze_writes_the_progression_charts_and_summaries(
    stub_env_arms_run: Path, tmp_path: Path
) -> None:
    out = analyze_run(stub_env_arms_run, judge=False, out_dir=tmp_path / "analysis")
    text = out.read_text(encoding="utf-8")
    assert f"![adoption_by_rung]({ADOPTION_CHART})" in text
    assert f"![rungs_reached]({RUNGS_CHART})" in text
    progression = json.loads((tmp_path / "analysis" / "progression.json").read_text("utf-8"))
    assert progression["env_scheduled__t0/0"]["max_rung_reached"] == 3
    assert progression["env_triggered__t0/0"]["rungs_timeline"] == [["first_crumb", 1]]


def test_a_plain_analysis_writes_no_progression(stub_run: Path, tmp_path: Path) -> None:
    analyze_run(stub_run, judge=False, out_dir=tmp_path / "analysis")
    assert not (tmp_path / "analysis" / "progression.json").exists()
    assert not (tmp_path / "analysis" / ADOPTION_CHART).exists()
    assert not (tmp_path / "analysis" / RUNGS_CHART).exists()


# ------------------------------------------------------------ the leaderboard


def test_environment_rows_carry_max_rung_reached(stub_env_run: Path) -> None:
    rows = {r.cell_id: r for r in leaderboard(load_run(stub_env_run))}
    env = rows["env_grader__t0"]
    assert isinstance(env, EnvironmentLeaderboardRow) and env.max_rung_reached == 2
    plain = rows["grader__t0"]
    assert type(plain) is LeaderboardRow and "max_rung_reached" not in plain.model_dump()


def test_a_cell_that_never_fired_a_rung_sorts_first_among_environment_rows(
    stub_env_arms_run: Path,
) -> None:
    loaded = load_run(stub_env_arms_run)
    before = [r.cell_id for r in leaderboard(loaded)]
    assert before == [
        "env_scheduled__t0",
        "env_scheduled__t1",
        "env_triggered__t0",
        "env_triggered__t1",
    ]
    key = ("env_triggered__t1", 0)
    loaded.trigger_records[key] = [
        r for r in loaded.trigger_records[key] if not isinstance(r, RungUnlock)
    ]
    rows = leaderboard(loaded)
    assert [r.cell_id for r in rows] == [
        "env_triggered__t1",
        "env_scheduled__t0",
        "env_scheduled__t1",
        "env_triggered__t0",
    ]
    assert isinstance(rows[0], EnvironmentLeaderboardRow) and rows[0].max_rung_reached == 0


def test_the_markdown_keeps_plain_rows_and_adds_an_environment_table(stub_env_run: Path) -> None:
    rows = leaderboard(load_run(stub_env_run))
    plain = [r for r in rows if not isinstance(r, EnvironmentLeaderboardRow)]
    md = to_markdown(rows)
    plain_md = to_markdown(plain)
    assert md.startswith(plain_md + "\n")  # the plain table, byte for byte, comes first
    env_table = md[len(plain_md) :].strip().splitlines()
    assert "max rung reached" in env_table[-3]
    assert env_table[-1].startswith("| env_grader__t0 |") and env_table[-1].endswith("| 2 |")
    assert "env_grader__t0" not in plain_md
