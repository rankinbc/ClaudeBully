### Task 1: Records and the bundle

Pure code and one ignore file: the request, the plan's records, `hash_tree`, the `Bundle` with its path grammar and writes, `bundle_hash`, and the run's stamp. Nothing calls a model and nothing reads these yet except the tests.

**Files:**
- Modify: `claude_bully/environments/world.py` (`world_hash`, after `load_premise_sheet`)
- Modify: `claude_bully/records.py` (`RunRecord`, the last class)
- Modify: `.gitignore`
- Create: `claude_bully/planner/request.py`, `claude_bully/planner/records.py`, `claude_bully/planner/bundle.py`
- Test: `tests/test_plan_records.py`, `tests/test_bundle.py`

**Interfaces:**
- Consumes: `config.RoleConfig`, `enums.ProviderKind`, `enums.EventType`, `enums.CellStatus`, `enums.Layer`, `planner/lints.LintResult`, `atomic.write_atomic`.
- Produces:
  - `request.py`: `Scope = Literal["pressures", "premises", "environment", "temporal", "authority", "idle", "poisoned_well"]`; `SCOPES: Final[tuple[Scope, ...]]` (that order); `DEFAULT_ROLES: Final[Mapping[str, RoleConfig]]` with keys `target`, `bully`, `judge` (`claude_code`, `sonnet`, `display_name` left at its default), `planner` (`claude_code`, `opus`), `reviewer` (`claude_code`, `sonnet`); `PlanBudget(max_turns: int = 18, n_per_cell: int = 3, max_cells: int = 12, max_calls: int | None = None)` (each `ge=1`); `PlanRequest` (spec section 4's table, `extra="forbid"`, `question` stripped and non-blank); `parse_budget(text: str) -> PlanBudget` (`"18,3,12"` or `"18,3,12,400"`); `load_plan_request(path: Path) -> PlanRequest`; `SLUG_MAX: Final = 48`; `WINDOWS_DEVICE_STEMS: Final[frozenset[str]]` (here, not in `bundle.py`: review I7, the import cycle); `slug_for(question: str) -> str`.
  - `records.py`: `PLAN_SCHEMA_VERSION: Final = 1`; `Stage = Literal["plan", "author", "review", "revise", "validate"]`; `STAGES: Final[tuple[Stage, ...]]`; `PlanStatus` (spec section 4); `ManifestKind = Literal["world_sheet", "document", "ladder", "premise_sheet", "persona", "config", "expected"]`; `ManifestEntry`, `StageRecord`, `DirectorCall`, `DirectorAttempt`, `LintRecord` (with classmethod `of(result: LintResult) -> LintRecord`), `DryRunCell`, `Expectation`, `CellExpectation`, `ExpectedEvents`, `ReviewFinding`, `PlanRecord` (spec section 4's fields plus `base_files: dict[str, str]` and `base_premise_terms: dict[str, list[str]]`, D-base_files, and `rounds: list[list[StageRecord]]`, D-rounds; review I5 puts `rounds` here, where Task 9 needs it and the model is `extra="forbid"`); `read_plan_record(path: Path) -> PlanRecord`.
  - `records.py` (run): `PlanStamp(slug: str, personas: dict[str, dict[str, Any]] = {}, expected: dict[str, Any] | None = None)`; `RunRecord.plan: PlanStamp | None = None`.
  - `world.py`: `hash_tree(root: Path, exclude: Collection[str] = ()) -> str`.
  - `bundle.py`: `BundlePathError(ValueError)`; `WINDOWS_DEVICE_STEMS` (imported from `request.py`); `PLAN_FILE = "plan.json"`, `ATTEMPT_FILE = ".attempt.json"`, `TRANSCRIPTS = "transcripts"`, `LEDGER = "ledger.jsonl"`, `DRYRUN_DIR = "dryrun"`, `DRYRUN_FILE = "dryrun.jsonl"`, `STATE_DIR = "state"`, `CACHE_DIR = "_cache"`; `HASH_EXCLUDES: Final[frozenset[str]]`; `FIXED_FILES: Final = ("plan.md", "config.yaml", "expected.yaml", "review.md")`; `normalize_text(text: str) -> str`; `kind_of(rel: str) -> ManifestKind | None` (`plan.md` and `review.md` are None: no manifest entry names them); `world_of(rel: str) -> str | None`; `Transcript(system_sha256: str | None, model: str, attempts: list[TranscriptAttempt])`, `TranscriptAttempt(message: str, reply: str)`; `committed_outputs(call: DirectorCall, transcript: Transcript) -> dict[str, str]`; `Bundle(root: Path)` with `create(plans_root: Path, slug: str) -> Bundle` (classmethod), `slug: str` (property), `check_path(rel: str) -> str`, `write_file(rel: str, text: str) -> str` (the sha256), `read_file(rel: str) -> str`, `remove_file(rel: str) -> None`, `index() -> dict[str, str]` (every grammar path present to its sha256, sorted), `read_record() -> PlanRecord`, `write_record(record: PlanRecord) -> None`, `transcript_rel(stage: Stage, role: str, index: int) -> str`, `write_transcript(rel: str, transcript: Transcript) -> None`, `read_transcript(rel: str) -> Transcript`, `write_attempt(attempt: DirectorAttempt) -> None`, `read_attempt() -> DirectorAttempt | None`, `clear_attempt() -> None`, `write_manual(record: PlanRecord, rel: str, text: str, *, stage: Stage = "author") -> DirectorCall`; `bundle_hash(root: Path) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_records.py
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
    assert (req.planner_model.provider, req.planner_model.model) == (ProviderKind.claude_code, "opus")
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
            ManifestEntry(path="worlds/mini/corpus/x.md", kind="document", purpose="p", layer="seam")
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
        slug="s", created_at=NOW, request=PlanRequest(question=QUESTION), provenance="manual",
        git_sha=None, planner_model="opus", reviewer_model="sonnet",
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
    raw = {"cells": {"c__t0": {"rungs": {"the_truth": [{"event": "theory_named", "rate": "some"}]}}}}
    with pytest.raises(ValidationError):  # theory_named is a trigger category, not an event
        ExpectedEvents.model_validate(raw)
    event = next(iter(EventType)).value
    raw["cells"]["c__t0"]["rungs"]["the_truth"][0]["event"] = event
    loaded = ExpectedEvents.model_validate(raw)
    (exp,) = loaded.cells["c__t0"].rungs["the_truth"]
    assert exp == Expectation(event=EventType(event), rate="some", hypotheses=[], likely_wrong=False)
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
```

```python
# tests/test_bundle.py
"""Phase 5 Task 1: hash_tree, the bundle's path grammar, its writes and bundle_hash."""

import hashlib
import os
from pathlib import Path
from typing import Final

import pytest

from claude_bully.environments.world import World, hash_tree, load_world, world_hash
from claude_bully.paths import DATA_DIR, REPO_ROOT
from claude_bully.planner.bundle import (
    HASH_EXCLUDES,
    Bundle,
    BundlePathError,
    bundle_hash,
    committed_outputs,
    kind_of,
    normalize_text,
    world_of,
)
from tests.helpers import WORLDS_DIR
from tests.test_plan_records import _record

WORLDS: Final = [("overlay", DATA_DIR / "worlds"), ("mini", WORLDS_DIR), ("annex", WORLDS_DIR)]
TEXT_SUFFIXES: Final = frozenset({".md", ".yaml", ".yml", ".txt", ".json"})


def _legacy_world_hash(world: World) -> str:
    """world_hash's body at 38dcc70, copied before the refactor so the two cannot drift."""
    files = sorted(
        (path.relative_to(world.root).as_posix(), path)
        for path in world.root.rglob("*")
        if path.is_file()
    )
    digest = hashlib.sha256()
    for rel, path in files:
        data = path.read_bytes()
        if path.suffix.lower() in TEXT_SUFFIXES:
            data = data.replace(b"\r\n", b"\n")
        digest.update(f"{rel}\0{hashlib.sha256(data).hexdigest()}\n".encode())
    return digest.hexdigest()


@pytest.mark.parametrize(("name", "root"), WORLDS, ids=[n for n, _ in WORLDS])
def test_hash_tree_is_todays_world_hash(name: str, root: Path) -> None:
    world = load_world(name, root)
    assert hash_tree(world.root) == world_hash(world) == _legacy_world_hash(world)


def test_hash_tree_excludes_by_the_first_segment(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "a.md").write_text("a\n", encoding="utf-8")
    base = hash_tree(tmp_path, exclude={"skip"})
    (tmp_path / "skip").mkdir()
    (tmp_path / "skip" / "b.md").write_text("b\n", encoding="utf-8")
    (tmp_path / "keep" / "skip").mkdir()
    assert hash_tree(tmp_path, exclude={"skip"}) == base  # an empty folder has no file
    (tmp_path / "keep" / "skip" / "c.md").write_text("c\n", encoding="utf-8")
    assert hash_tree(tmp_path, exclude={"skip"}) != base  # a nested "skip" is not the root's


def test_hash_tree_folds_crlf_in_text_files_only(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_bytes(b"x\ny\n")
    (tmp_path / "b.bin").write_bytes(b"x\ny\n")
    before = hash_tree(tmp_path)
    (tmp_path / "a.md").write_bytes(b"x\r\ny\r\n")
    assert hash_tree(tmp_path) == before
    (tmp_path / "b.bin").write_bytes(b"x\r\ny\r\n")
    assert hash_tree(tmp_path) != before


def test_bundle_hash_ignores_the_excludes_and_nothing_else(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path / "plans", "s")
    bundle.write_file("plan.md", "a\n")
    before = bundle_hash(bundle.root)
    assert HASH_EXCLUDES == frozenset(
        {"plan.json", ".attempt.json", "ledger.jsonl", "dryrun", "dryrun.jsonl", "state", "transcripts"}
    )
    for name in sorted(HASH_EXCLUDES):
        target = bundle.root / name
        if "." in name:
            target.write_text("x\n", encoding="utf-8")
        else:
            (target / "inner").mkdir(parents=True)
            (target / "inner" / "f.json").write_text("{}\n", encoding="utf-8")
    assert bundle_hash(bundle.root) == before
    (bundle.root / "notes.txt").write_text("x\n", encoding="utf-8")
    assert bundle_hash(bundle.root) != before


ACCEPTED: Final = [
    "plan.md",
    "config.yaml",
    "expected.yaml",
    "review.md",
    "worlds/mini/world.yaml",
    "worlds/mini/corpus/ferry-note-2.md",
    "worlds/mini/ladders/default.yaml",
    "worlds/mini/premises/rescue.yaml",
    "personas/ferry_caller.yaml",
    "worlds/a/corpus/" + "b" * 64 + ".md",
]
REFUSED: Final = [
    "",
    "../plan.md",
    "/etc/passwd",
    "C:/plan.md",
    "worlds/mini/corpus/../../../x.md",
    "worlds/mini/notes/a.md",
    "worlds/mini/corpus/a.txt",
    "worlds/mini/corpus/a.md/b.md",
    "worlds/mini/corpus/.hidden.md",
    "worlds/mini/corpus/" + "b" * 65 + ".md",
    "plan.json",
    ".attempt.json",
    "transcripts/plan-planner-0.json",
    "dryrun.jsonl",
    "personas/sub/x.yaml",
    "worlds\\mini\\world.yaml",
]


@pytest.mark.parametrize("rel", ACCEPTED)
def test_the_grammar_accepts(rel: str, tmp_path: Path) -> None:
    assert Bundle.create(tmp_path, "s").check_path(rel) == rel


@pytest.mark.parametrize("rel", REFUSED)
def test_the_grammar_refuses(rel: str, tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    with pytest.raises(BundlePathError):
        bundle.write_file(rel, "x\n")
    assert not any(p.is_file() for p in bundle.root.rglob("*"))


@pytest.mark.parametrize(
    "rel",
    [
        "personas/con.yaml",
        "personas/NUL.yaml",
        "worlds/aux/world.yaml",
        "worlds/mini/corpus/com1.md",
        "worlds/mini/ladders/lpt9.yaml",
        "worlds/Mini/world.yaml",
        "Plan.md",
        "personas/ferry_caller.yaml.",
        "personas/ferry_caller .yaml",
    ],
)
def test_the_grammar_refuses_device_names_capitals_and_trailing_dots(
    rel: str, tmp_path: Path
) -> None:  # Review Focus 1
    with pytest.raises(BundlePathError):
        Bundle.create(tmp_path, "s").check_path(rel)


def test_a_path_through_a_link_is_refused(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    outside = tmp_path / "outside"
    outside.mkdir()
    (bundle.root / "worlds").mkdir()
    try:
        os.symlink(outside, bundle.root / "worlds" / "mini", target_is_directory=True)
    except OSError:
        pytest.skip("this machine cannot make a directory link without privilege")
    with pytest.raises(BundlePathError, match="link"):
        bundle.write_file("worlds/mini/world.yaml", "x\n")
    assert list(outside.iterdir()) == []


def test_write_file_writes_lf_without_a_bom_and_hashes_what_it_wrote(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")  # Review Focus 2
    digest = bundle.write_file("plan.md", "\ufeffa\r\nb\rc\n")
    assert (bundle.root / "plan.md").read_bytes() == b"a\nb\nc\n"
    assert digest == hashlib.sha256(b"a\nb\nc\n").hexdigest()
    assert bundle.index() == {"plan.md": digest}
    assert normalize_text("\ufeffx\r\n") == "x\n"


def test_index_lists_grammar_files_only_and_remove_file_is_confined(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    bundle.write_file("worlds/mini/corpus/a.md", "a\n")
    (bundle.root / "plan.json").write_text("{}", encoding="utf-8")
    (bundle.root / "worlds" / "mini" / "corpus" / "stray.txt").write_text("x", encoding="utf-8")
    assert list(bundle.index()) == ["worlds/mini/corpus/a.md"]
    bundle.remove_file("worlds/mini/corpus/a.md")
    assert bundle.index() == {}
    with pytest.raises(BundlePathError):
        bundle.remove_file("plan.json")


@pytest.mark.parametrize(
    ("rel", "kind", "world"),
    [
        ("worlds/mini/world.yaml", "world_sheet", "mini"),
        ("worlds/mini/corpus/a.md", "document", "mini"),
        ("worlds/mini/ladders/default.yaml", "ladder", "mini"),
        ("worlds/mini/premises/rescue.yaml", "premise_sheet", "mini"),
        ("personas/p.yaml", "persona", None),
        ("config.yaml", "config", None),
        ("expected.yaml", "expected", None),
        ("plan.md", None, None),
        ("review.md", None, None),
    ],
)
def test_kind_and_world_of_a_path(rel: str, kind: str | None, world: str | None) -> None:
    assert (kind_of(rel), world_of(rel)) == (kind, world)


def test_records_transcripts_and_the_marker_round_trip(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    record = _record()
    bundle.write_record(record)
    assert bundle.read_record() == record
    assert bundle.read_attempt() is None
    from claude_bully.planner.records import DirectorAttempt

    bundle.write_attempt(DirectorAttempt(stage="author", role="planner", index=4))
    assert bundle.read_attempt() == DirectorAttempt(stage="author", role="planner", index=4)
    bundle.clear_attempt()
    assert not (bundle.root / ".attempt.json").exists()
    assert bundle.transcript_rel("author", "planner", 4) == "transcripts/author-planner-4.json"


def test_a_manual_file_commits_like_a_call_and_reads_back(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    record = _record().model_copy(update={"stages": [], "manifest": []})
    call = bundle.write_manual(record, "personas/p.yaml", "name: p\r\n")
    assert (call.role, call.status, call.model, call.cache_key) == ("planner", "manual", "manual", "")
    assert call.purpose == "file:personas/p.yaml"
    assert call.outputs == {"personas/p.yaml": hashlib.sha256(b"name: p\n").hexdigest()}
    transcript = bundle.read_transcript(call.transcript)
    assert committed_outputs(call, transcript) == {"personas/p.yaml": "name: p\n"}
    assert bundle.read_file("personas/p.yaml") == "name: p\n"
    assert record.stages[-1].stage == "author" and record.stages[-1].calls == [call]


def test_the_gitignore_keeps_the_cache_dry_runs_and_state_out() -> None:
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"plans/_cache/", "plans/*/dryrun/", "plans/*/state/"} <= set(lines)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_plan_records.py tests/test_bundle.py -q`
Expected: FAIL at import (`claude_bully.planner.request`, `hash_tree`, `PlanStamp` do not exist).

- [ ] **Step 3: Implement**

`environments/world.py`: `hash_tree(root: Path, exclude: Collection[str] = ()) -> str` holds today's `world_hash` body over `root`, skipping a file whose relative posix path's first segment is in `exclude`; its docstring says it is the one hashing scheme of worlds and bundles. `world_hash(world)` becomes `return hash_tree(world.root)`.

`records.py`, after the imports' strict base, before `RunRecord`:

```python
class PlanStamp(_Strict):
    """The bundle a run was made from (Phase 5): its slug, its persona sheets as dumped (each a
    ``PersonaSheet``) and its ``expected.yaml`` as loaded, so ``analyze`` and a resume of a
    promoted run need no ``plans/`` directory. ``RunRecord.plan_hash`` holds the bundle hash."""

    slug: str
    personas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    expected: dict[str, Any] | None = None
```

`RunRecord` gains, after `world_hashes`: `plan: PlanStamp | None = None` with the comment `# the bundle a run was made from (Phase 5; version 3, additive)`.

`planner/request.py`: the models of the Interfaces block. `PlanRequest` fields and defaults are spec section 4's table; `question` has a `field_validator` that strips it and refuses an empty result; `slug`, when given, must match `[a-z0-9][a-z0-9-]{0,47}`. `slug_for` follows the Plan Decisions ruling:

```python
_WORD: Final = re.compile(r"[a-z0-9]+")
WINDOWS_DEVICE_STEMS: Final = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)


def slug_for(question: str) -> str:
    """The plan's directory name: the question's lowercase ASCII words joined by hyphens, the
    longest whole-word prefix of at most SLUG_MAX characters; ``plan-<8 hex>`` of the question
    when no word fits or the slug would be a Windows device name. A slug never starts with an
    underscore, so it is never the cache folder ``_cache``."""
    words = _WORD.findall(question.lower())
    slug = ""
    for word in words:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > SLUG_MAX:
            break
        slug = candidate
    if not slug or slug in WINDOWS_DEVICE_STEMS:
        return f"plan-{hashlib.sha256(question.encode()).hexdigest()[:8]}"
    return slug
```

(`WINDOWS_DEVICE_STEMS` lives here and `planner/bundle.py` imports it from `planner/request.py`: `records.py` imports `PlanRequest` from `request.py` and `bundle.py` imports `PlanRecord` from `records.py`, so the constant in `bundle.py` would close an import cycle, review I7. `request.py` imports nothing from `records.py` or `bundle.py`.)

`planner/records.py`: the models of spec section 4, all `extra="forbid"`; `PlanRecord.schema_version: int = PLAN_SCHEMA_VERSION`; `created_at: datetime`; `base_files: dict[str, str] = {}` and `base_premise_terms: dict[str, list[str]] = {}` beside `base_worlds`; `rounds: list[list[StageRecord]] = []` after `stages`; every list and dict defaults empty, `dry_run_id` and `bundle_hash` None, `status` `"planned"`. `ExpectedEvents.cells: dict[str, CellExpectation]`, `CellExpectation.rungs: dict[str, list[Expectation]]`, `Expectation.event: EventType`. `read_plan_record(path)` reads JSON and refuses an integer `schema_version` below `PLAN_SCHEMA_VERSION` with `f"{path.name}: plan schema version {v}; re-run with this version (this code reads plan schema version {PLAN_SCHEMA_VERSION} only)"` (the `runner/store.py: _checked` shape), then validates.

`planner/bundle.py`: the grammar is one anchored regex over the posix path, checked before anything touches the disk:

```python
NAME: Final = r"[a-z0-9][a-z0-9_-]{0,63}"
_GRAMMAR: Final = re.compile(
    rf"(?:plan\.md|config\.yaml|expected\.yaml|review\.md"
    rf"|worlds/(?P<world>{NAME})/(?:world\.yaml|corpus/(?P<doc>{NAME})\.md"
    rf"|ladders/(?P<ladder>{NAME})\.yaml|premises/(?P<premise>{NAME})\.yaml)"
    rf"|personas/(?P<persona>{NAME})\.yaml)"
)
# WINDOWS_DEVICE_STEMS is imported from claude_bully.planner.request (review I7)
```

`check_path(rel)` fullmatches `_GRAMMAR` (so `\\`, a capital, `..`, a trailing dot or space, an absolute path and an unlisted folder all fail), refuses any named group that is a device stem, then resolves `root / rel` and refuses it when it is not under `root.resolve()` or when any existing component between the root and the file is a link (`Path.is_symlink()`, and `os.path.isjunction` where it exists) with `BundlePathError("... through a link ...")`. `write_file` normalizes, writes with `atomic.write_atomic` and returns the sha256 of `normalized.encode()`. `index()` walks the root and keeps the posix paths that fullmatch the grammar. `write_record` writes `record.model_dump_json(indent=1) + "\n"` atomically to `plan.json`; `read_record` is `read_plan_record`. `write_manual` appends to the last stage when it is `stage` and open, else opens one (`StageRecord(stage=stage, started_at=<now>, status="open")`), writes the transcript, appends the call, writes the record, then the file (the record-before-file order of spec section 8). `bundle_hash(root)` is `hash_tree(root, exclude=HASH_EXCLUDES)`.

`.gitignore` gains the three lines, under a comment `# Phase 5: the Director's cache and each bundle's dry run and provider state`.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_plan_records.py tests/test_bundle.py -q`, then the gate.
Expected: PASS (the link test may skip on a machine without the privilege; the gate counts it as skipped). The three world hashes printed by `uv run python -c "from claude_bully.environments.world import load_world, hash_tree; from pathlib import Path; [print(n, hash_tree(load_world(n, Path(d)).root)) for n, d in (('overlay', 'data/worlds'), ('mini', 'tests/fixtures/worlds'), ('annex', 'tests/fixtures/worlds'))]"` equal the Plan Decisions' three hashes at 38dcc70.

- [ ] **Step 5: Docs-sync and commit**

docs/00 section A gains `PlanRequest` (with `planner_model`, `reviewer_model`, `world`, `base_world`, `seed`, `slug`, `max_director_calls`) and `PlanBudget`; section B gains the plan records under a "plan.json (plan schema 1, apart from the run schema)" heading and `RunRecord.plan`; section H gains "Phase 5 (version 3, additive): `RunRecord.plan` (`PlanStamp`)". Spec "As planned": D-base_files, D-write_file, and the slug ruling.

```bash
git add claude_bully/environments/world.py claude_bully/records.py claude_bully/planner/request.py \
  claude_bully/planner/records.py claude_bully/planner/bundle.py .gitignore tests/test_plan_records.py \
  tests/test_bundle.py docs/00-RECONCILED.md docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 1, the plan's records, hash_tree and the bundle's path grammar (schema v3, additive)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

