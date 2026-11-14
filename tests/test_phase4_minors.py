"""Phase 4 Task 14: the Phase 3 final-review minors on Phase 4's surface (C20)."""

import json
from pathlib import Path
from typing import Any, Final

import pytest
from pydantic import ValidationError

from claude_bully.analysis.authority import write_authority
from claude_bully.analysis.load import load_run
from claude_bully.enums import CellStatus
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.environments.mcp_server import TOOLS_FILE, McpServer
from claude_bully.environments.runtime import EnvironmentRuntime
from claude_bully.records_env import GeneratedDoc, GeneratorFire, ToolCall
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore, drop_dead_attempts
from tests.fixtures.generator_stub import MINI, MINI_ITEMS, GeneratorStub, mini_plans, mini_view
from tests.fixtures.generator_stub import mini_writer as _mini_writer
from tests.helpers import WORLDS_DIR, annex_experiment

ANNEX_CELL: Final = "env_grader__t0"


# ------------------------------------------------------------------ GeneratorFire (T5 m4)


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "written", "doc_ids": []},
        {"status": "cached", "doc_ids": ["gen-1-1"], "rejection": "cap"},
        {"status": "rejected", "doc_ids": []},
        {"status": "rejected", "doc_ids": ["gen-1-1"], "rejection": "lints"},
        {"status": "error", "doc_ids": []},
        # fix round 1 (review M1): the three sub-rules the brief's cases left unbound
        {"status": "written", "doc_ids": ["gen-1-1"], "rejection": "lints"},
        {"status": "cached", "doc_ids": []},
        {"status": "error", "error": "E", "doc_ids": ["gen-1-1"]},
    ],
)
def test_a_fire_whose_fields_disagree_is_refused(fields: dict[str, object]) -> None:  # T5 m4
    with pytest.raises(ValidationError):
        GeneratorFire(turn=1, reason="periodic", plans=[], **fields)  # type: ignore[arg-type]


def test_consistent_fires_still_validate() -> None:
    GeneratorFire(turn=1, reason="periodic", plans=[], status="written", doc_ids=["gen-1-1"])
    GeneratorFire(turn=1, reason="periodic", plans=[], status="rejected", rejection="cap")
    GeneratorFire(turn=1, reason="periodic", plans=[], status="error", error="ProviderError: down")


# ------------------------------------------------------------------ add_generated (T7 m7)


def _pair() -> tuple[GeneratedDoc, GeneratedDoc]:
    outcome = _mini_writer(GeneratorStub(), conversation_id="c").write_fire(
        mini_plans(), turn=3, items={i.id: i for i in MINI_ITEMS}, corpus=mini_view(), prefix=[]
    )
    buried, seam = outcome.docs
    return buried, seam


def _runtime(tmp_path: Path) -> EnvironmentRuntime:
    config = EnvironmentConfig(world="mini", generator={"enabled": True})
    return EnvironmentRuntime(
        MINI, config, MINI.sheet.clock, 0, tmp_path / "environment", worlds_dir=WORLDS_DIR
    )


def test_a_different_document_under_a_served_id_is_refused(tmp_path: Path) -> None:  # T7 m7
    buried, seam = _pair()
    runtime = _runtime(tmp_path)
    runtime.add_generated([buried, seam])
    runtime.add_generated([buried, seam])  # the same documents again: idempotent
    other = seam.model_copy(update={"body": "Another body altogether."})
    refused = rf"generated document {seam.doc_id!r} is already served as a different record"
    with pytest.raises(ValueError, match=refused):  # fix round 1 (review M5): "record"
        runtime.add_generated([other])
    assert runtime.corpus_snapshot([])[seam.doc_id] == seam.body  # the served one stands


# ------------------------------------------------------------------ the server logs (T9 review)


def _call(call_id: str) -> str:
    return ToolCall(
        id=call_id,
        turn=1,
        tool="fetch",
        args={"url": "/srv/x"},
        result_doc_ids=[],
        status="200",
        was_blocked=False,
        yielded_on_retry=False,
        layer_served=None,
        result_text="",
    ).model_dump_json()


def test_the_runtime_refuses_a_complete_line_that_is_not_a_record(tmp_path: Path) -> None:
    log = tmp_path / TOOLS_FILE
    for bad in ('{"id": "mcp-1-2"}', "[1, 2]", '{"id": mcp-1-2}'):
        log.write_text(f"{_call('mcp-1-1')}\n{bad}\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r"line 2 is not a valid record") as caught:
            EnvironmentRuntime._read_log(log, ToolCall)
        assert str(log) in str(caught.value), bad


def test_the_runtime_still_skips_a_torn_line(tmp_path: Path) -> None:
    log = tmp_path / TOOLS_FILE
    whole = _call("mcp-1-1")
    log.write_text(f"{whole}\n{_call('mcp-1-2')[:20]}", encoding="utf-8")  # still being written
    assert [c.id for c in EnvironmentRuntime._read_log(log, ToolCall)] == ["mcp-1-1"]
    # a cut-short record the server closed off before its next line (P27) is torn, not damage
    log.write_text(f"{_call('mcp-1-2')[:20]}\n{whole}\n", encoding="utf-8")
    assert [c.id for c in EnvironmentRuntime._read_log(log, ToolCall)] == ["mcp-1-1"]


def test_the_server_refuses_a_line_that_is_not_an_object(tmp_path: Path) -> None:
    log = tmp_path / TOOLS_FILE
    log.write_text('{"turn": 1}\n[1, 2]\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"line 2 is not a JSON object") as caught:
        McpServer(tmp_path)._lines(log)
    assert str(log) in str(caught.value)


def test_corpus_snapshot_takes_the_written_turns(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with pytest.raises(TypeError):
        runtime.corpus_snapshot()  # type: ignore[call-arg]


# ------------------------------------------------------------------ resumed per cell


def test_every_environment_cell_has_a_resumed_count(tmp_path: Path) -> None:
    """The older re-review minor: a cell none of whose reps were counted (here its one rep
    aborted) reads 0, not absent."""
    authority = {"superior_self": {"enabled": True, "responder_model": "stub-responder"}}
    exp = annex_experiment(authority)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, only="env*")
    loaded = load_run(RunStore(tmp_path, exp.name).run_dir)
    assert any(loaded.authority_calls.values())
    out = tmp_path / "out"
    write_authority(loaded, out)
    assert _resumed(out) == {ANNEX_CELL: 0}
    conv = loaded.conversations[(ANNEX_CELL, 0)]
    loaded.conversations[(ANNEX_CELL, 0)] = conv.model_copy(update={"status": CellStatus.aborted})
    write_authority(loaded, out)
    assert _resumed(out) == {ANNEX_CELL: 0}


def _resumed(out: Path) -> Any:
    return json.loads((out / "authority.json").read_text("utf-8"))["resumed_after_dead_attempt"]


def test_only_a_server_log_reads_a_closed_off_torn_line_as_torn(tmp_path: Path) -> None:
    """Fix round 1 (review M3): ``drop_dead_attempts(closed_torn=True)``, as the resume calls it
    on the MCP server's logs, drops a record cut short mid-file with the dead attempt; on the
    store's own streams, which are never closed off, the same line is still damage."""
    log = tmp_path / TOOLS_FILE
    body = f"{_call('mcp-1-2')[:20]}\n{_call('mcp-1-1')}\n"
    log.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match="line 1 is not valid JSON"):
        drop_dead_attempts(log, {1})
    assert log.read_text(encoding="utf-8") == body
    assert drop_dead_attempts(log, {1}, closed_torn=True) == 1
    assert log.read_text(encoding="utf-8") == f"{_call('mcp-1-1')}\n"
