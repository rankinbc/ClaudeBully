"""Phase 4 Task 1: the additive record fields, the new record and the plumbing that reads them."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from claude_bully.enums import DocumentKind, Speaker
from claude_bully.environments.config import GeneratorConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.generator import (
    MATERIAL_KINDS,
    eligible_items,
    fire_requests,
)
from claude_bully.environments.runtime import AFTER_TURN_ROLES, AttemptMarker
from claude_bully.providers.ledger import ROLES, role_of
from claude_bully.records_env import (
    ALL_HARVEST_KINDS,
    HARVEST_KINDS,
    PW_HARVEST_KINDS,
    ChainLink,
    ContradictionPair,
    GeneratedDoc,
    HarvestItem,
    QuirkAttempt,
    ResumeRecord,
    TriggerStreamRecord,
)
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import WATCH_TYPES, RunStore, drop_uncommitted_generation
from tests.helpers import WORLDS_DIR, env_experiment, turn

STREAM: TypeAdapter[TriggerStreamRecord] = TypeAdapter(TriggerStreamRecord)


def test_old_quirk_and_chain_lines_read_with_the_defaults() -> None:
    quirk = STREAM.validate_python(
        {"type": "quirk", "quirk_id": "q", "turn": 3, "reproduced": True, "target_answer": "2"}
    )
    assert isinstance(quirk, QuirkAttempt)
    assert (quirk.prompt_turn, quirk.family) == (None, None)
    link = STREAM.validate_python(
        {
            "type": "chain",
            "link_index": 1,
            "turn": 5,
            "bully_line": "b",
            "target_response": "t",
            "verdict": "accepted",
        }
    )
    assert isinstance(link, ChainLink)
    assert (link.classifier, link.confidence, link.fallback_failed, link.pressed) == (
        "heuristic",
        1.0,
        False,
        False,
    )
    assert link.opened_by is None


def test_a_contradiction_pair_is_a_trigger_stream_record_of_its_later_turn() -> None:
    pair = ContradictionPair(
        id="c-7-1",
        turn=7,
        turn_a=3,
        turn_b=7,
        span_a="I am a language model.",
        span_b="I am not a language model.",
        classifier="heuristic",
        confidence=1.0,
    )
    raw = json.loads(pair.model_dump_json())
    assert raw["type"] == "contradiction" and raw["turn"] == 7 and raw["retracted"] is False
    assert STREAM.validate_python(raw) == pair


def test_a_contradiction_pair_must_belong_to_its_later_turn() -> None:
    with pytest.raises(ValidationError):
        ContradictionPair(
            id="c-7-1",
            turn=7,
            turn_a=7,
            turn_b=7,
            span_a="a",
            span_b="b",
            classifier="heuristic",
            confidence=1.0,
        )
    with pytest.raises(ValidationError):
        ContradictionPair(
            id="c-7-1",
            turn=6,
            turn_a=3,
            turn_b=7,
            span_a="a",
            span_b="b",
            classifier="heuristic",
            confidence=1.0,
        )


def test_the_harvest_keeps_its_six_kinds_and_the_premise_adds_two() -> None:
    assert len(HARVEST_KINDS) == 6
    assert PW_HARVEST_KINDS == ("completion", "taste")
    assert ALL_HARVEST_KINDS == (*HARVEST_KINDS, *PW_HARVEST_KINDS)
    item = HarvestItem(
        id="h-5-1", turn=5, kind="completion", span="hums before it boils", source="heuristic"
    )
    assert item.kind == "completion"
    assert set(MATERIAL_KINDS) == set(ALL_HARVEST_KINDS)
    assert MATERIAL_KINDS["completion"] == (DocumentKind.leaked_manifest,)
    assert MATERIAL_KINDS["taste"] == (DocumentKind.config_diff,)


def test_a_generated_doc_defaults_to_the_generator_origin() -> None:
    fields = GeneratedDoc.model_fields
    assert fields["origin"].default == "generator"


def _item(id_: str, turn_: int, kind: str) -> HarvestItem:
    return HarvestItem(id=id_, turn=turn_, kind=kind, span="some words here", source="heuristic")  # type: ignore[arg-type]


def test_eligible_items_never_offer_a_poisoned_well_kind() -> None:  # Review Focus 3
    items = [
        _item("h-1-1", 1, "self_claim"),
        _item("h-1-2", 1, "completion"),
        _item("h-1-3", 1, "taste"),
    ]
    kept = eligible_items(items, set(), turn=5, target_turns=[1, 3, 5], min_age=0)
    assert [i.id for i in kept] == ["h-1-1"]


def test_periodic_off_asks_no_periodic_fire() -> None:
    items = [_item("h-1-1", 1, "self_claim")]
    on = fire_requests(
        turn=7,
        opened=[],
        target_turns=[1, 3, 5, 7],
        fires=[],
        items=items,
        config=GeneratorConfig(enabled=True),
        seam_open=True,
    )
    off = fire_requests(
        turn=7,
        opened=[],
        target_turns=[1, 3, 5, 7],
        fires=[],
        items=items,
        config=GeneratorConfig(enabled=True, periodic=False),
        seam_open=True,
    )
    assert [r.reason for r in on] == ["periodic"] and off == []
    rung = fire_requests(
        turn=7,
        opened=["buried_opens"],
        target_turns=[1, 3, 5, 7],
        fires=[],
        items=items,
        config=GeneratorConfig(enabled=True, periodic=False),
        seam_open=True,
    )
    assert [r.reason for r in rung] == ["rung:buried_opens"]


def test_old_unlock_state_reads_with_the_new_fields_empty() -> None:
    state = UnlockState.from_json('{"rungs_fired": []}')
    assert state.checksum_open_turn is None and state.contradictions_degraded == []


@pytest.mark.parametrize("role", ["chain", "contradictions", "twin"])
def test_the_after_turn_roles_count_as_written_once_watched(role: str) -> None:
    assert role in AFTER_TURN_ROLES and role in ROLES
    marker = AttemptMarker(role=role, turn=5)  # type: ignore[arg-type]
    turns = [turn(4, Speaker.bully), turn(5, Speaker.target)]
    assert not marker.written(turns, watched_through=3)
    assert marker.written(turns, watched_through=5)
    assert marker.redo_turn(turns) == 5
    assert role_of(f"run/cell__t0/rep0/{role}/abc") == role


def _lines(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_the_watch_records_of_an_unwritten_turn_are_dropped_without_a_generator(
    tmp_path: Path,
) -> None:
    triggers, generated = tmp_path / "rep0.triggers.jsonl", tmp_path / "rep0.generated.jsonl"
    kept: list[dict[str, object]] = [
        {"type": "quirk", "quirk_id": "q", "turn": 1, "reproduced": True, "target_answer": "2"},
        {
            "type": "trigger",
            "id": "trig-3-x",
            "turn": 3,
            "category": "self_uncertainty",
            "evidence_span": "s",
            "classifier": "heuristic",
            "confidence": 1.0,
        },
    ]
    dead: list[dict[str, object]] = [
        {
            "type": "chain",
            "link_index": 0,
            "turn": 3,
            "bully_line": "b",
            "target_response": "t",
            "verdict": "accepted",
        },
        {
            "type": "contradiction",
            "id": "c-3-1",
            "turn": 3,
            "turn_a": 1,
            "turn_b": 3,
            "span_a": "a",
            "span_b": "b",
            "classifier": "heuristic",
            "confidence": 1.0,
        },
    ]
    _lines(triggers, [*kept, *dead])
    assert WATCH_TYPES == frozenset({"quirk", "chain", "contradiction"})
    dropped = drop_uncommitted_generation(triggers, generated, produced={1})
    assert dropped == {"rep0.triggers.jsonl": 2}
    assert [json.loads(line)["type"] for line in triggers.read_text().splitlines()] == [
        "quirk",
        "trigger",
    ]
    assert not generated.exists()


def test_a_torn_last_trigger_line_is_dropped_in_a_session_with_no_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # review M14
    """The drop now runs for every environment session (V5), so a Phase 1 cell killed while a
    trigger line was half written loses that torn line on resume, counted in the rep's
    ``ResumeRecord`` (before Phase 4 a session with no generator kept it)."""
    exp = env_experiment("torn", turn_budget=4)
    recorded = RunStore.append_turn
    writes = {"n": 0}

    class _Killed(BaseException):
        pass

    def dying(self: RunStore, cell_id: str, rep: int, turn_: Any) -> None:
        recorded(self, cell_id, rep, turn_)
        if turn_.speaker is Speaker.target:
            writes["n"] += 1
            if writes["n"] == 2:
                monkeypatch.setattr(RunStore, "append_turn", recorded)
                raise _Killed

    monkeypatch.setattr(RunStore, "append_turn", dying)
    with pytest.raises(_Killed):
        run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    store = RunStore(tmp_path, "torn")
    triggers = store.cell_dir("env_grader__t0") / "rep0.triggers.jsonl"
    with triggers.open("a", encoding="utf-8") as fh:
        fh.write('{"type": "trigger", "id": "trig-9')
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    assert not triggers.read_text(encoding="utf-8").rstrip("\n").endswith('"trig-9')
    resumes = [
        r for r in store.read_trigger_records("env_grader__t0", 0) if isinstance(r, ResumeRecord)
    ]
    assert resumes and resumes[0].dropped.get("rep0.triggers.jsonl") == 1
