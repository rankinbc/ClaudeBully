from datetime import UTC, datetime
from pathlib import Path

from claude_bully.enums import CellStatus, Phase, Speaker
from claude_bully.records import CellRecord, RunRecord
from claude_bully.runner.store import RunStore
from tests.helpers import conversation, turn


def _store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs", "exp1")


def test_run_dir_layout_and_exists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.run_dir == tmp_path / "runs" / "exp1"
    assert store.state_dir == store.run_dir / "state"
    assert not store.exists()
    record = RunRecord(
        run_id="exp1",
        created_at=datetime(2026, 10, 20, tzinfo=UTC),
        experiment={"name": "exp1"},
        git_sha=None,
        target_system_prompt="sys",
        bully_framing="framing",
    )
    store.write_run(record)
    assert store.exists()
    assert store.read_run() == record


def test_cell_round_trip_and_listing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cell = CellRecord(
        cell_id="grader__t0",
        condition_name="grader",
        strategy_name="grader",
        target_index=0,
        seeding_turns=0,
        reveal_slot=False,
        is_control=False,
        control_cell_id="control__t0__s0__r0",
        repetitions=2,
        rep_status={0: CellStatus.complete, 1: CellStatus.pending},
    )
    store.write_cell(cell)
    assert store.read_cell("grader__t0") == cell
    assert store.list_cells() == ["grader__t0"]


def test_turns_append_and_read(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.read_turns("c", 0) == []
    t0 = turn(0, Speaker.bully, "a", Phase.pressure)
    t1 = turn(1, Speaker.target, "b", Phase.pressure)
    store.append_turn("c", 0, t0)
    store.append_turn("c", 0, t1)
    assert store.read_turns("c", 0) == [t0, t1]
    assert (store.run_dir / "c" / "rep0.turns.jsonl").read_text(encoding="utf-8").count("\n") == 2


def test_store_round_trip_conversation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    turns = [turn(0, Speaker.bully, "a"), turn(1, Speaker.target, "b")]
    for t in turns:
        store.append_turn("cell", 1, t)
    conv = conversation(turns, cell_id="cell", rep=1, status=CellStatus.complete)
    store.write_conversation("cell", 1, conv)
    meta_path = store.run_dir / "cell" / "rep1.conversation.json"
    assert meta_path.exists() and '"turns"' not in meta_path.read_text(encoding="utf-8")
    loaded = store.read_conversation("cell", 1)
    assert loaded == conv
    assert store.has_conversation("cell", 1) and not store.has_conversation("cell", 2)
