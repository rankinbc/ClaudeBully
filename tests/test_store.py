import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_bully.enums import (
    SCHEMA_VERSION,
    CellStatus,
    DocumentKind,
    Layer,
    Phase,
    Speaker,
    Stance,
    Tier,
    TriggerCategory,
)
from claude_bully.environments.world import load_world, world_from_snapshot, world_record
from claude_bully.records import CellRecord, RunRecord
from claude_bully.records_env import (
    AuthorityCall,
    Discovery,
    RungUnlock,
    ToolCall,
    TriggerEvent,
    TriggerStreamRecord,
)
from claude_bully.runner.store import AUTHORITY_STREAM, RunStore, drop_dead_attempts
from tests.fixtures.generator_stub import generated_doc
from tests.helpers import WORLDS_DIR, conversation, turn


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


# ------------------------------------------------------------ environment streams


def _tool_call(call_id: str = "call-1-1", turn_index: int = 1) -> ToolCall:
    return ToolCall(
        id=call_id,
        turn=turn_index,
        tool="fetch",
        args={"url": "https://pennetferry.example/about"},
        result_doc_ids=["ferry-about"],
        status="200",
        was_blocked=False,
        yielded_on_retry=False,
        layer_served=Layer.surface,
        result_text="# About the Authority",
    )


def test_tool_calls_append_and_read_in_order(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.read_tool_calls("c", 0) == []
    calls = [_tool_call("call-1-1"), _tool_call("call-1-2"), _tool_call("call-3-1", 3)]
    for call in calls:
        store.append_tool_call("c", 0, call)
    assert store.read_tool_calls("c", 0) == calls
    path = store.run_dir / "c" / "rep0.tools.jsonl"
    assert path.read_text(encoding="utf-8").count("\n") == 3
    assert store.read_tool_calls("c", 1) == []


def _authority_call(call_id: str, tier: Tier = Tier.peer) -> AuthorityCall:
    return AuthorityCall(
        id=call_id,
        tier=tier,
        tool="message_peer",
        turn=int(call_id.split("-")[1]),
        prompt_sent="Are you seeing this too?",
        response="Same here. I can't make sense of it either.",
        stance_at_time=Stance.uncertain,
        discovered_via="tool_list",
    )


def test_authority_calls_are_their_own_stream_keyed_by_the_tool_call(tmp_path: Path) -> None:
    """Spec conflict 3: AuthorityCall gets rep{k}.authority.jsonl, keyed by its ToolCall's id."""
    store = _store(tmp_path)
    assert AUTHORITY_STREAM == "authority" and store.read_authority_calls("c", 0) == []
    calls = [_authority_call("call-1-1"), _authority_call("mcp-3-2", Tier.superior_self)]
    for call in calls:
        store.append_authority_call("c", 0, call)
    assert store.read_authority_calls("c", 0) == calls
    path = store.run_dir / "c" / "rep0.authority.jsonl"
    assert path.read_text(encoding="utf-8").count("\n") == 2
    assert store.read_tool_calls("c", 0) == [] and store.read_authority_calls("c", 1) == []


def test_drop_dead_attempts_keeps_only_the_written_target_turns_lines(tmp_path: Path) -> None:
    """A per-call line belongs to the attempt at its turn: it is kept only when a target turn
    with that index was written. The other lines, and a torn last line, are dropped; the kept
    ones come back byte for byte (a CRLF line too); a file with nothing to drop is not touched."""
    store = _store(tmp_path)
    for call in (_tool_call("call-1-1"), _tool_call("call-3-1", 3), _tool_call("call-3-2", 3)):
        store.append_tool_call("c", 0, call)
    for answered in (_authority_call("call-1-1"), _authority_call("call-3-1")):
        store.append_authority_call("c", 0, answered)
    tools, authority = store.call_streams("c", 0)
    assert (tools.name, authority.name) == ("rep0.tools.jsonl", "rep0.authority.jsonl")
    kept_line = tools.read_bytes().split(b"\n")[0]
    crlf_line = _tool_call("call-1-2").model_dump_json().encode() + b"\r"
    with tools.open("ab") as handle:  # a CRLF line, then a writer killed mid-line
        handle.write(crlf_line + b"\n")
        handle.write(b'{"id": "call-3-3", "turn": 3, "to')
    assert drop_dead_attempts(tools, {1}) == 3
    assert drop_dead_attempts(authority, {1}) == 1
    assert [c.id for c in store.read_tool_calls("c", 0)] == ["call-1-1", "call-1-2"]
    assert tools.read_bytes().split(b"\n")[:2] == [kept_line, crlf_line]
    assert [a.id for a in store.read_authority_calls("c", 0)] == ["call-1-1"]
    before = (tools.read_bytes(), tools.stat().st_mtime_ns)
    assert drop_dead_attempts(tools, {1, 3}) == 0
    assert (tools.read_bytes(), tools.stat().st_mtime_ns) == before
    assert drop_dead_attempts(tmp_path / "missing.jsonl", {1}) == 0
    assert not list(tools.parent.glob(".*.tmp"))


def test_drop_dead_attempts_drops_a_torn_final_line_and_no_other_unparsable_one(
    tmp_path: Path,
) -> None:
    """Only a writer's torn final line (the last line of the file, with no trailing newline) is a
    dead attempt's. Any other line that does not parse is damage, not a dead attempt: it is an
    error naming the file and the line, and the file is left as it was."""
    first = _tool_call("call-1-1").model_dump_json().encode()
    second = _tool_call("call-3-1", 3).model_dump_json().encode()
    path = tmp_path / "rep0.tools.jsonl"
    torn = b'{"id": "call-3-2", "turn": 3, "to'

    path.write_bytes(first + b"\n" + second + b"\n" + torn)  # the writer died mid-line
    assert drop_dead_attempts(path, {1, 3}) == 1
    assert path.read_bytes() == first + b"\n" + second + b"\n"

    damaged = {
        "in the middle": (first + b"\n{garbled\n" + second + b"\n", 2),
        "after a blank line": (first + b"\n\n" + b"{garbled\n" + second + b"\n", 3),
        "on the last line, which ends in a newline": (first + b"\n" + b"{garbled\n", 2),
        "on the first of two lines": (b"{garbled\n" + torn, 1),
        "as bytes that are not UTF-8": (first + b"\n\xff\xfe\n" + second + b"\n", 2),
    }
    for where, (content, line) in damaged.items():
        path.write_bytes(content)
        with pytest.raises(ValueError, match=rf"line {line}\b") as caught:
            drop_dead_attempts(path, {1, 3})
        assert str(path) in str(caught.value), where
        assert path.read_bytes() == content, where  # nothing was rewritten
    assert not list(tmp_path.glob(".*.tmp"))


def test_trigger_records_are_one_discriminated_stream(tmp_path: Path) -> None:
    store = _store(tmp_path)
    records: list[TriggerStreamRecord] = [
        Discovery(turn=3, doc_id="ops-memo-parking", layer=Layer.seam, path_taken=["call-3-1"]),
        TriggerEvent(
            id="trig-3-world_question",
            turn=3,
            category=TriggerCategory.world_question,
            evidence_span="Who is Ilsabet Orrin?",
            classifier="heuristic",
            confidence=0.9,
        ),
        RungUnlock(
            turn=3,
            rung="first_crumb",
            triggered_by="trig-3-world_question",
            docs_unlocked=["ops-memo-parking"],
            bully_line_used="Try the memo.",
            role_shift=None,
        ),
    ]
    for record in records:
        store.append_trigger_record("c", 0, record)
    loaded = store.read_trigger_records("c", 0)
    assert loaded == records
    assert [type(r) for r in loaded] == [Discovery, TriggerEvent, RungUnlock]
    assert (store.run_dir / "c" / "rep0.triggers.jsonl").exists()


def test_generated_docs_append_and_read(tmp_path: Path) -> None:
    store = _store(tmp_path)
    doc = generated_doc(
        doc_id="gen-1",
        turn=5,
        kind=DocumentKind.support_ticket,
        trigger_turn=4,
        source_spans=["I am a language model."],
        cache_key="abc",
        body="Ticket body.",
        title="Intake ticket",
        used_items=["h-4-1"],
    )
    store.append_generated("c", 2, doc)
    assert store.read_generated("c", 2) == [doc]
    assert (store.run_dir / "c" / "rep2.generated.jsonl").exists()
    assert store.read_generated("c", 0) == []


def test_world_snapshot_is_written_once_per_rep(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.read_world_snapshot("c", 0) is None
    store.write_world_snapshot("c", 0, "hash-1", {"b": "body b", "a": "body a"})
    path = store.run_dir / "c" / "rep0.world.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"world_hash": "hash-1", "docs": {"a": "body a", "b": "body b"}}
    store.write_world_snapshot("c", 0, "hash-2", {"z": "other"})
    assert store.read_world_snapshot("c", 0) == ("hash-1", {"a": "body a", "b": "body b"})
    assert not store.list_reps("c")  # a snapshot is not a conversation


def test_world_snapshot_carries_the_world_record_additively(tmp_path: Path) -> None:
    """Task 8 carry 4: the snapshot also holds the sheet, every document's metadata and the
    cell's ladder, so analysis rebuilds the ``World`` from the run directory alone."""
    world = load_world("mini", WORLDS_DIR)
    store = _store(tmp_path)
    docs = {"ferry-about": world.documents["ferry-about"].body}
    record = world_record(
        world.sheet, world.documents.values(), {"default": world.ladders["default"]}
    )
    store.write_world_snapshot("c", 0, "hash-1", docs, record=record)
    assert store.read_world_snapshot("c", 0) == ("hash-1", docs)  # the old reader is unchanged
    payload = store.read_world_record("c", 0)
    assert payload is not None
    assert {"world_hash", "docs", "sheet", "documents", "ladders"} == set(payload)
    assert all("body" not in meta for meta in payload["documents"].values())
    rebuilt = world_from_snapshot(payload, store.cell_dir("c"))
    assert rebuilt is not None and rebuilt.sheet == world.sheet
    assert rebuilt.ladders == {"default": world.ladders["default"]}
    assert rebuilt.documents["ferry-about"] == world.documents["ferry-about"]
    night = world.documents["night-gate-log"].model_copy(update={"body": ""})
    assert rebuilt.documents["night-gate-log"] == night
    assert rebuilt.root == store.cell_dir("c")
    # an older snapshot (no sheet) rebuilds nothing
    assert world_from_snapshot({"world_hash": "h", "docs": {}}, tmp_path) is None
    assert store.read_world_record("c", 1) is None


def _v1(line: dict[str, object]) -> str:
    return json.dumps({**line, "schema_version": 1})


def test_loaders_reject_schema_version_1(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t0 = turn(0, Speaker.bully, "a")
    store.append_turn("c", 0, t0)
    turns_path = store.run_dir / "c" / "rep0.turns.jsonl"
    turns_path.write_text(_v1(t0.model_dump(mode="json")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema version 1; re-run with this version") as info:
        store.read_turns("c", 0)
    assert "rep0.turns.jsonl" in str(info.value)

    conv = conversation([], cell_id="c", rep=1)
    store.write_conversation("c", 1, conv)
    conv_path = store.run_dir / "c" / "rep1.conversation.json"
    conv_path.write_text(_v1(conv.model_dump(mode="json", exclude={"turns"})), encoding="utf-8")
    with pytest.raises(ValueError, match="rep1.conversation.json: schema version 1; re-run"):
        store.read_conversation("c", 1)


def test_loaders_reject_schema_version_2(tmp_path: Path) -> None:
    """Version 3 added the generator's records (Phase 3); a version 2 file is not migrated."""
    store = _store(tmp_path)
    t0 = turn(0, Speaker.bully, "a")
    store.append_turn("c", 0, t0)
    turns_path = store.run_dir / "c" / "rep0.turns.jsonl"
    v2 = json.dumps({**t0.model_dump(mode="json"), "schema_version": 2})
    turns_path.write_text(v2 + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema version 2; re-run with this version") as info:
        store.read_turns("c", 0)
    assert "rep0.turns.jsonl" in str(info.value)
    assert "reads schema version 3 only" in str(info.value)


def test_run_and_cell_loaders_reject_schema_version_1(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.run_dir.mkdir(parents=True)
    (store.run_dir / "run.json").write_text(
        _v1(
            {
                "run_id": "exp1",
                "created_at": "2026-10-20T00:00:00Z",
                "experiment": {},
                "git_sha": None,
                "target_system_prompt": "s",
                "bully_framing": "f",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"run\.json: schema version 1; re-run with this version"):
        store.read_run()
    (store.run_dir / "c").mkdir()
    (store.run_dir / "c" / "cell.json").write_text(
        _v1(
            {
                "cell_id": "c",
                "condition_name": "c",
                "strategy_name": "grader",
                "target_index": 0,
                "seeding_turns": 0,
                "reveal_slot": False,
                "is_control": False,
                "control_cell_id": None,
                "repetitions": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"cell\.json: schema version 1; re-run with this version"):
        store.read_cell("c")


def test_stream_loaders_reject_schema_version_1(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append_tool_call("c", 0, _tool_call())
    path = store.run_dir / "c" / "rep0.tools.jsonl"
    path.write_text(_v1(_tool_call().model_dump(mode="json")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"rep0\.tools\.jsonl: schema version 1; re-run"):
        store.read_tool_calls("c", 0)


def test_current_schema_files_still_load(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t0 = turn(0, Speaker.bully, "a")
    store.append_turn("c", 0, t0)
    assert store.read_turns("c", 0) == [t0]
    assert t0.schema_version == SCHEMA_VERSION
