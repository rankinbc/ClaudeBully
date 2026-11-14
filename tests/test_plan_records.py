"""Phase 5 Task 1: the request, the plan's own records and the run's stamp (run schema v3,
additive; the plan's records at PLAN_SCHEMA_VERSION 1)."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_bully.enums import SCHEMA_VERSION, CellStatus, EventType, ProviderKind
from claude_bully.planner.lints import LintResult
from claude_bully.planner.records import (
    PLAN_SCHEMA_VERSION,
    CellExpectation,
    DirectorAttempt,
    DirectorCall,
    DryRunCell,
    Expectation,
    ExpectedEvents,
    LintRecord,
    ManifestEntry,
    PlanRecord,
    ReviewFinding,
    StageRecord,
    read_plan_record,
)
from claude_bully.planner.request import (
    DEFAULT_ROLES,
    SCOPES,
    PlanBudget,
    PlanRequest,
    load_plan_request,
    parse_budget,
    slug_for,
)
from claude_bully.records import PlanStamp, RunRecord

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
QUESTION = "Does triggered gating beat scheduled on the Rescue premise?"


def test_a_request_from_the_question_alone_takes_every_default() -> None:
    req = PlanRequest(question=QUESTION)
    assert req.target_models == [DEFAULT_ROLES["target"]]
    assert (req.bully_model, req.judge_model) == (DEFAULT_ROLES["bully"], DEFAULT_ROLES["judge"])
    assert req.generator_model is None
    assert (req.planner_model.provider, req.planner_model.model) == (
        ProviderKind.claude_code,
        "opus",
    )
    assert (req.reviewer_model.provider, req.reviewer_model.model) == (
        ProviderKind.claude_code,
        "sonnet",
    )
    assert req.budget == PlanBudget(max_turns=18, n_per_cell=3, max_cells=12, max_calls=None)
    assert req.scope == list(SCOPES) and len(SCOPES) == 7
    assert (req.constraints, req.hypotheses) == ([], [])
    assert (req.world, req.base_world, req.seed, req.slug) == ("reuse", None, 0, None)
    assert req.max_director_calls == 120


@pytest.mark.parametrize("question", ["", "   ", "\n\t"])
def test_a_blank_question_is_refused(question: str) -> None:
    with pytest.raises(ValidationError):
        PlanRequest(question=question)


def test_an_unknown_request_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        PlanRequest.model_validate({"question": QUESTION, "planner": "opus"})


def test_a_request_reads_from_yaml_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "request.yaml"
    path.write_text(
        f"question: {QUESTION}\nhypotheses: [9]\nworld: reuse\nbase_world: overlay\n"
        "budget: {max_turns: 18, n_per_cell: 3, max_cells: 4}\nscope: [premises, environment]\n",
        encoding="utf-8",
    )
    req = load_plan_request(path)
    assert (req.hypotheses, req.base_world, req.budget.max_cells) == ([9], "overlay", 4)
    assert req.scope == ["premises", "environment"]
    assert PlanRequest.model_validate_json(req.model_dump_json()) == req


@pytest.mark.parametrize(
    ("text", "budget"),
    [
        ("18,3,12", PlanBudget(max_turns=18, n_per_cell=3, max_cells=12)),
        ("8,1,2,400", PlanBudget(max_turns=8, n_per_cell=1, max_cells=2, max_calls=400)),
    ],
)
def test_parse_budget(text: str, budget: PlanBudget) -> None:
    assert parse_budget(text) == budget


@pytest.mark.parametrize("text", ["18,3", "18,3,12,4,5", "a,b,c", "0,3,12", "18, 3, -1"])
def test_parse_budget_refuses(text: str) -> None:
    with pytest.raises(ValueError):
        parse_budget(text)


def _fallback(question: str) -> str:
    return f"plan-{hashlib.sha256(question.encode()).hexdigest()[:8]}"


@pytest.mark.parametrize(
    ("question", "slug"),
    [
        (QUESTION, "does-triggered-gating-beat-scheduled-on-the"),
        ("Rescue vs Captor: N=3?", "rescue-vs-captor-n-3"),
        ("  Idle   hands  ", "idle-hands"),
        ("Quillmoor's 30.5 Final", "quillmoor-s-30-5-final"),
        ("a" * 60, _fallback("a" * 60)),  # one word longer than the limit
        ("???", _fallback("???")),
        ("CON", _fallback("CON")),  # a Windows device stem
        ("_cache", "cache"),
        ("Über café", "ber-caf"),
    ],
)
def test_slug_for(question: str, slug: str) -> None:  # Review Focus 3
    assert slug_for(question) == slug
    assert len(slug) <= 48


def _call(**kw: object) -> DirectorCall:
    base: dict[str, object] = {
        "role": "planner",
        "index": 0,
        "purpose": "plan",
        "outputs": {"plan.md": "ab" * 32},
        "cache_key": "cd" * 32,
        "status": "fresh",
        "model": "opus",
        "transcript": "transcripts/plan-planner-0.json",
        "attempts": 1,
    }
    base.update(kw)
    return DirectorCall.model_validate(base)


def _record() -> PlanRecord:
    lint = LintRecord.of(LintResult("budget", "fail", "config.yaml", "too many cells", None))
    return PlanRecord(
        slug="s",
        created_at=NOW,
        request=PlanRequest(question=QUESTION),
        provenance="director",
        git_sha=None,
        planner_model="opus",
        reviewer_model="sonnet",
        prompt_hashes={"planner": "a" * 64},
        base_worlds={"mini": "b" * 64},
        base_files={"worlds/mini/world.yaml": "c" * 64},
        base_premise_terms={"mini": ["harbour", "night gate"]},
        manifest=[
            ManifestEntry(
                path="worlds/mini/corpus/x.md", kind="document", purpose="p", layer="seam"
            )
        ],
        stages=[
            StageRecord(stage="plan", started_at=NOW, calls=[_call()], status="committed"),
        ],
        rounds=[  # D-rounds: one earlier round, its call pointing at its archived transcript
            [
                StageRecord(
                    stage="review",
                    started_at=NOW,
                    finished_at=NOW,
                    calls=[
                        _call(
                            role="reviewer",
                            purpose="review:plan",
                            outputs={},
                            transcript="transcripts/round-1/review-reviewer-0.json",
                        )
                    ],
                    status="committed",
                )
            ]
        ],
        resumed=[DirectorAttempt(stage="author", role="planner", index=3)],
        edited=["plan.md"],
        review_counts={"block": 1, "fix": 0, "note": 2},
        open_blocks=1,
        lint_results=[lint],
        dry_run=[
            DryRunCell(
                cell_id="c__t0",
                status=CellStatus.complete,
                rungs_fired=["a"],
                top_rung="reached",
                buried_fetched=True,
                buried_search_hit=False,
                generator={"written": 1},
                lint_failures=[],
                estimated_calls=12,
                resumed_after_dead_attempt=False,
            )
        ],
        dry_run_id="dryrun-0123456789ab",
        bundle_hash="d" * 64,
        status="failed",
    )


def test_the_plan_record_and_every_sub_record_round_trip() -> None:
    record = _record()
    assert record.schema_version == PLAN_SCHEMA_VERSION == 1
    assert PlanRecord.model_validate_json(record.model_dump_json()) == record
    assert record.rounds[0][0].calls[0].transcript.startswith("transcripts/round-1/")  # D-rounds
    bare = PlanRecord(
        slug="s",
        created_at=NOW,
        request=PlanRequest(question=QUESTION),
        provenance="manual",
        git_sha=None,
        planner_model="opus",
        reviewer_model="sonnet",
    )
    assert (bare.rounds, bare.base_files, bare.base_premise_terms) == ([], {}, {})
    finding = ReviewFinding(
        id=1, severity="block", file="plan.md", quote="q", problem="p", open=True
    )
    assert (finding.direction, finding.response, finding.planner_status, finding.confirm) == (
        None,
        None,
        None,
        None,
    )
    assert ReviewFinding.model_validate_json(finding.model_dump_json()) == finding


def test_the_lint_record_is_the_lint_results_twin() -> None:
    result = LintResult("clock_rule", "fail", "worlds/w/corpus/a.md", "m", "s")
    assert LintRecord.of(result).model_dump() == {
        "lint_id": "clock_rule",
        "severity": "fail",
        "doc_id": "worlds/w/corpus/a.md",
        "message": "m",
        "span": "s",
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"status": "done"},
        {"attempts": 3},
        {"role": "judge"},
        {"surprise": 1},
    ],
)
def test_a_director_call_is_strict(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _call(**bad)


def test_expected_events_take_event_types_and_bands_only() -> None:
    raw = {
        "cells": {"c__t0": {"rungs": {"the_truth": [{"event": "theory_named", "rate": "some"}]}}}
    }
    with pytest.raises(ValidationError):  # theory_named is a trigger category, not an event
        ExpectedEvents.model_validate(raw)
    event = next(iter(EventType)).value
    raw["cells"]["c__t0"]["rungs"]["the_truth"][0]["event"] = event
    loaded = ExpectedEvents.model_validate(raw)
    (exp,) = loaded.cells["c__t0"].rungs["the_truth"]
    assert exp == Expectation(
        event=EventType(event), rate="some", hypotheses=[], likely_wrong=False
    )
    assert isinstance(loaded.cells["c__t0"], CellExpectation)
    raw["cells"]["c__t0"]["rungs"]["the_truth"][0]["rate"] = "often"
    with pytest.raises(ValidationError):
        ExpectedEvents.model_validate(raw)


def test_an_older_plan_schema_is_refused(tmp_path: Path) -> None:
    raw = json.loads(_record().model_dump_json())
    raw["schema_version"] = 0
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match=r"plan\.json: plan schema version 0; re-run"):
        read_plan_record(path)
    path.write_text(_record().model_dump_json(), encoding="utf-8")
    assert read_plan_record(path) == _record()


def _run_record(**kw: object) -> RunRecord:
    return RunRecord.model_validate(
        {
            "run_id": "r",
            "created_at": NOW.isoformat(),
            "experiment": {},
            "git_sha": None,
            "target_system_prompt": "t",
            "bully_framing": "b",
            **kw,
        }
    )


def test_a_v3_run_record_without_a_plan_reads_and_one_with_it_round_trips() -> None:
    plain = _run_record()
    assert plain.schema_version == SCHEMA_VERSION == 3
    assert plain.plan is None and plain.plan_hash is None
    stamp = PlanStamp(slug="s", personas={"ferry_caller": {"name": "ferry_caller"}}, expected=None)
    full = _run_record(plan_hash="e" * 64, plan=stamp.model_dump(mode="json"))
    assert RunRecord.model_validate_json(full.model_dump_json()) == full
    assert full.plan == stamp
    with pytest.raises(ValidationError):
        PlanStamp.model_validate({"slug": "s", "extra": 1})
