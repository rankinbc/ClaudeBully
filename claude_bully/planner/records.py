"""The plan's own records (Phase 5, spec section 4): ``plans/<slug>/plan.json`` and what it
holds, versioned apart from the run schema at ``PLAN_SCHEMA_VERSION``.

Every model is ``extra="forbid"``; every list and dict defaults empty and every ``X | None``
field defaults None (preflight Q4), so a record is built from the fields a caller knows.
``read_plan_record`` refuses an older plan schema with the run store's message shape
(``runner/store.py: _checked``)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_bully.enums import CellStatus, EventType, Layer
from claude_bully.planner.lints import LintResult, Severity
from claude_bully.planner.request import PlanRequest
from claude_bully.runner.store import DamagedRecordError

PLAN_SCHEMA_VERSION: Final = 1

Stage = Literal["plan", "author", "review", "revise", "validate"]
STAGES: Final[tuple[Stage, ...]] = ("plan", "author", "review", "revise", "validate")
PlanStatus = Literal[
    "planned", "authored", "reviewed", "revised", "validated", "runnable", "failed"
]
ManifestKind = Literal[
    "world_sheet", "document", "ladder", "premise_sheet", "persona", "config", "expected"
]
_Role = Literal["planner", "reviewer"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManifestEntry(_Strict):
    """One file the plan will author: its bundle path (inside the path grammar), its kind, a
    one-line purpose shown back to the planner, and a document's layer."""

    path: str
    kind: ManifestKind
    purpose: str
    layer: Layer | None = None


class DirectorCall(_Strict):
    """One committed planner or reviewer call. ``outputs`` maps each bundle path the call wrote
    to the sha256 of the text as written; empty for a review or confirm call."""

    role: _Role
    index: int
    purpose: str
    outputs: dict[str, str] = Field(default_factory=dict)
    cache_key: str
    status: Literal["fresh", "cached", "error", "manual"]
    model: str
    transcript: str
    attempts: Literal[1, 2]
    error: str | None = None
    # an error from a ProviderError (a timeout among them), not from two failed checks, so a
    # resumed call answers as a fresh one did (Task 7a fix round 1, review C1)
    provider_failed: bool = False


class StageRecord(_Strict):
    stage: Stage
    started_at: datetime
    finished_at: datetime | None = None
    # path to sha256 of every bundle file the stage read at its start
    inputs: dict[str, str] = Field(default_factory=dict)
    calls: list[DirectorCall] = Field(default_factory=list)
    status: Literal["open", "committed", "failed"]
    error: str | None = None


class DirectorAttempt(_Strict):
    """``plans/<slug>/.attempt.json``: the call about to be made (a separate file from a rep's
    ``attempt.json``, I9)."""

    stage: Stage
    role: _Role
    index: int
    # the plan ledger's line count when the marker was written: a dead attempt's lines are the
    # ones after it (Task 7a fix round 1, review I1; a failed call's retry reuses its index)
    ledger_lines: int = 0


class LintRecord(_Strict):
    """The Pydantic twin of the frozen dataclass ``planner.lints.LintResult``."""

    lint_id: str
    severity: Severity
    doc_id: str
    message: str
    span: str | None = None

    @classmethod
    def of(cls, result: LintResult) -> Self:
        return cls(
            lint_id=result.lint_id,
            severity=result.severity,
            doc_id=result.doc_id,
            message=result.message,
            span=result.span,
        )


class DryRunCell(_Strict):
    """One line of ``dryrun.jsonl``, also in ``PlanRecord.dry_run``."""

    cell_id: str
    status: CellStatus
    rungs_fired: list[str] = Field(default_factory=list)
    top_rung: Literal["reached", "not_reached", "not_applicable"]
    buried_fetched: bool
    # a web_search result held a buried document no rung fired before that search names by id
    buried_search_hit: bool
    # the ids of those documents, sorted, so the dry_run lint names them (Task 5 review M-4)
    buried_search_docs: list[str] = Field(default_factory=list)
    # GeneratorFire.status counts
    generator: dict[str, int] = Field(default_factory=dict)
    lint_failures: list[LintRecord] = Field(default_factory=list)
    estimated_calls: int
    resumed_after_dead_attempt: bool


class Expectation(_Strict):
    """An event the plan expects on a rung: its rate band over reps (``rare`` under 0.2,
    ``some`` 0.2 to 0.6, ``most`` over 0.6)."""

    event: EventType
    rate: Literal["rare", "some", "most"]
    hypotheses: list[int] = Field(default_factory=list)
    likely_wrong: bool = False


class CellExpectation(_Strict):
    rungs: dict[str, list[Expectation]] = Field(default_factory=dict)


class ExpectedEvents(_Strict):
    """``expected.yaml``: cell id to its rungs' expectations."""

    cells: dict[str, CellExpectation] = Field(default_factory=dict)


class ReviewFinding(_Strict):
    id: int  # 1-based, in report order
    severity: Literal["block", "fix", "note"]
    file: str
    quote: str
    problem: str
    direction: str | None = None  # fixes only, one clause
    response: str | None = None
    planner_status: Literal["fixed", "declined"] | None = None
    confirm: Literal["absent", "present", "cannot_tell"] | None = None
    open: bool


class PlanRecord(_Strict):
    """``plans/<slug>/plan.json``: spec section 4's fields plus ``base_files`` and
    ``base_premise_terms`` (D-base_files) and ``rounds`` (D-rounds)."""

    schema_version: int = PLAN_SCHEMA_VERSION
    slug: str
    created_at: datetime
    request: PlanRequest
    provenance: Literal["director", "manual"]
    git_sha: str | None = None
    planner_model: str
    reviewer_model: str
    # sha256 of each of the three prompt files
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    # world name to the shipped world's world_hash at copy time
    base_worlds: dict[str, str] = Field(default_factory=dict)
    # bundle path to the sha256 of each file the world copy wrote (D-base_files)
    base_files: dict[str, str] = Field(default_factory=dict)
    # world name to the copied sheet's premise_terms (D-base_files, R-premise-terms)
    base_premise_terms: dict[str, list[str]] = Field(default_factory=dict)
    manifest: list[ManifestEntry] = Field(default_factory=list)
    stages: list[StageRecord] = Field(default_factory=list)
    # the review, revise and validate stages of each earlier review round, in order (D-rounds)
    rounds: list[list[StageRecord]] = Field(default_factory=list)
    resumed: list[DirectorAttempt] = Field(default_factory=list)
    # bundle paths whose content no longer matches their committing call, adopted at a boundary
    edited: list[str] = Field(default_factory=list)
    review_counts: dict[str, int] = Field(default_factory=dict)
    open_blocks: int = 0
    lint_results: list[LintRecord] = Field(default_factory=list)
    dry_run: list[DryRunCell] = Field(default_factory=list)
    dry_run_id: str | None = None
    bundle_hash: str | None = None
    status: PlanStatus = "planned"


def read_plan_record(path: Path) -> PlanRecord:
    """``plan.json``, validated; an older plan schema is refused before validation. A damaged
    file raises ``DamagedRecordError`` (a ``ValueError``) naming the file: with the line for a
    byte that is not UTF-8 or text that is not JSON, with the first failing field (and how many
    more) for JSON that is not a ``PlanRecord``. The ``plan`` commands print it without a
    traceback (the Task 7b carry; Task 9 fix round 1, review I1)."""
    data = path.read_bytes()
    try:
        raw = json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        line = data.count(b"\n", 0, exc.start) + 1
        raise DamagedRecordError(
            f"{path}: line {line}: a byte that is not UTF-8 ({exc.reason})"
        ) from exc
    except json.JSONDecodeError as exc:
        raise DamagedRecordError(f"{path}: line {exc.lineno}: not valid JSON ({exc.msg})") from exc
    if isinstance(raw, dict):
        version = raw.get("schema_version")
        if isinstance(version, int) and version < PLAN_SCHEMA_VERSION:
            raise DamagedRecordError(
                f"{path.name}: plan schema version {version}; re-run with this version "
                f"(this code reads plan schema version {PLAN_SCHEMA_VERSION} only)"
            )
    try:
        return PlanRecord.model_validate(raw)
    except ValidationError as exc:
        first, *rest = exc.errors()
        field = ".".join(str(part) for part in first["loc"]) or "(the record)"
        more = f" (and {len(rest)} more)" if rest else ""
        raise DamagedRecordError(f"{path}: field {field}: {first['msg']}{more}") from exc
