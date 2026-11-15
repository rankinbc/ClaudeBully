"""The Director (Phase 5, spec sections 7 and 8): the call primitive every planner and reviewer
call goes through, the resume, and the stages, run in order inside the plan's own ledger.

``Director.ask`` holds spec section 8's order of one call's writes, and is the one place a
provider is built and called:

1. the stage record (a new open ``StageRecord`` is written before any marker, so a plan killed
   inside its first call names the stage);
2. ``.attempt.json`` names the call (``DirectorAttempt``);
3. the cache is read, a hit checked like a fresh reply; on a miss the session is reset and the
   provider called; a reply that fails its check is asked once more with the failures listed;
4. the transcript (the system prompt's hash, each attempt's message and reply; never a
   ``Completion.reasoning_text``, non-negotiable 6);
5. the commit: the ``DirectorCall`` appended to its stage, with the sha256 of every file it
   commits and any record field the call sets (``CallSpec.commit``, R-commit), in one
   ``plan.json`` write;
6. the files, each written LF (``Bundle.write_file``);
7. the cache put, for a fresh reply.

A rate limit commits nothing: the marker is removed and ``RateLimitExit`` raised, the stage left
open (D-rate-limit). A provider error, a timeout among them, is an ``error`` call, never waited
on. A first message over ``MAX_CONTEXT_CHARS`` is refused before it is sent
(``DirectorError``); a retry over it is an ``error`` call, recording the attempt that was sent.

``Director.run`` resumes at the first stage not committed (spec section 8): it records a dead
attempt first, while a committed ``error`` call still holds its index (R-marker), reopens a
failed stage (the failed-stage ruling), re-materializes the open stage
(``bundle.rematerialize_open_stage``) and goes on at ``len(calls)``. A resumed stage replays
its committed calls in order (``Director._call``): a committed call's answer is rebuilt from
its transcript by the call's pure ``parse``, never by a check that reads state, and a step
with no write of its own (the world close) is decided afresh only past the last committed
call, so every decision a resume makes is the one an unbroken plan made (Task 7b).
"""

import functools
import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, ValidationError

from claude_bully.atomic import write_atomic
from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import Layer
from claude_bully.environments.config import LadderConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.ladder import Ladder
from claude_bully.environments.world import (
    WORLDS_DIR,
    Document,
    WorldSheet,
    load_world,
    parse_document,
    world_hash,
)
from claude_bully.metrics.judge import JudgeCache
from claude_bully.paths import REPO_ROOT
from claude_bully.planner.bundle import (
    CACHE_DIR,
    LEDGER,
    PLAN_FILE,
    STATE_DIR,
    Bundle,
    BundlePathError,
    Transcript,
    TranscriptAttempt,
    bundle_personas,
    commit_order,
    committed_outputs,
    is_plan_persona,
    kind_of,
    normalize_text,
    plan_personas,
    rematerialize_open_stage,
    remove_leftovers,
    remove_leftovers_of,
    world_of,
)
from claude_bully.planner.bundle_lints import (
    MIN_ANCHOR_DOCS,
    dry_run_refusals,
    environment_refusals,
    model_from_text,
    plan_scans,
    premise_sheet_model,
    review_scans,
)
from claude_bully.planner.context import (
    MAX_CONTEXT_CHARS,
    REVIEW_FILE,
    ReviewGroup,
    TaskPart,
    confirm_message,
    load_director_prompt,
    planner_message,
    prompt_hashes,
    reviewer_message,
    unchanged_base_files,
)
from claude_bully.planner.lints import (
    LintContext,
    LintResult,
    failures,
    lint_document,
    lint_world,
    squash,
)
from claude_bully.planner.records import (
    STAGES,
    DirectorAttempt,
    DirectorCall,
    ExpectedEvents,
    ManifestEntry,
    ManifestKind,
    PlanRecord,
    PlanStatus,
    ReviewFinding,
    Stage,
    StageRecord,
)
from claude_bully.planner.request import PlanRequest, slug_for
from claude_bully.providers.base import (
    ChatProvider,
    Message,
    ProviderError,
    ProviderFactory,
    RateLimitError,
    build_provider,
)
from claude_bully.providers.ledger import LedgerLine, activate, note_cached
from claude_bully.runner.cells import expand_cells
from claude_bully.runner.runner import RateLimitExit, _git_sha
from claude_bully.runner.store import parsed_lines
from claude_bully.strategies.base import all_strategies
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.sheets import PersonaSheet

DIRECTOR_CACHE_VERSION: Final = 1
MAX_PLAN_CHARS: Final = 20_000
MIN_FILLER_SHARE: Final = 0.30
MAX_REPAIR_CALLS: Final = 10
# where the CLI lives, how long to wait, which variable holds a key: none changes a reply, so
# none is in the cache key (R-cache-key)
ROLE_KEY_EXCLUDES: Final = frozenset({"command", "timeout_s", "api_key_env"})
DOCS_DIR: Final = REPO_ROOT / "docs"
DIRECTOR_CACHE: Final = "director"

# the status a plan has earned once each stage commits
_EARNED: Final[Mapping[Stage, PlanStatus]] = {
    "plan": "planned",
    "author": "authored",
    "review": "reviewed",
    "revise": "revised",
    "validate": "validated",
}

PLAN_TASK: Final = (
    "Write plan.md, stage 1 of your instructions: the question restated with the comparison "
    "that answers it, the cells, the headline chart, the expected events per cell, what a null "
    "result looks like, and the budget check. Reply with the Markdown of plan.md and nothing "
    "else: it is written to the bundle as you send it."
)

# stage 3's chunking rule (spec section 7): one reviewer call per group, the corpus in chunks of
# at most REVIEW_CHUNK_DOCS documents; the manifest's budget counts the calls it implies
# (``review_calls``, Task 7b fix round 1, review M5)
REVIEW_CHUNK_DOCS: Final = 25
REVIEW_GROUPS: Final = ("corpus", "lines", "plan")
_LINES_KINDS: Final[frozenset[ManifestKind]] = frozenset(
    {"world_sheet", "ladder", "persona", "premise_sheet"}
)
_PLAN_KINDS: Final[frozenset[ManifestKind]] = frozenset({"config", "expected"})
WORLDS: Final = "worlds"
FIXED_ENTRIES: Final = ("config.yaml", "expected.yaml")

# {"files": [{"path", "kind", "purpose", "layer"}]} (spec section 7, stage 2 step 2)
MANIFEST_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["files"],
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "kind", "purpose", "layer"],
                "properties": {
                    "path": {"type": "string"},
                    "kind": {"enum": list(get_args(ManifestKind))},
                    "purpose": {"type": "string"},
                    "layer": {"enum": [*(layer.value for layer in Layer), None]},
                },
            },
        }
    },
}
# {"content": "<the file's text>"}: a file call's and a repair call's reply (step 3)
FILE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content"],
    "properties": {"content": {"type": "string"}},
}

MANIFEST_TASK: Final = (
    "Write the manifest, stage 2 of your instructions: every file the bundle needs that you "
    "will write, one entry each, as the JSON object "
    '{"files": [{"path": ..., "kind": ..., "purpose": ..., "layer": ...}]}. A path is one of '
    "config.yaml, expected.yaml, worlds/<name>/world.yaml, worlds/<name>/corpus/<stem>.md, "
    "worlds/<name>/ladders/<stem>.yaml, worlds/<name>/premises/<strategy>.yaml and "
    "personas/<stem>.yaml, each <name> and <stem> lowercase letters, digits, '-' and '_'; "
    "kind is that path's kind (world_sheet, document, ladder, premise_sheet, persona, config, "
    "expected); purpose is one line, shown back to you when the file is asked for; layer is a "
    "document's layer and null for every other file. A reused world is copied whole under "
    "worlds/<name>/ before any file is asked for: list only the files you add or patch. "
    "config.yaml and expected.yaml are always listed. The harness then asks for each file, one "
    "per call, in a fixed order: per world its sheet, its documents, its ladders and its "
    "premise sheets, then the personas, config.yaml and expected.yaml."
)


def file_task(entry: ManifestEntry) -> str:
    """The task of the file call for ``entry``: its path, kind and purpose, and the reply."""
    return (
        f"Write {entry.path}, a {entry.kind}, the manifest's entry for: {entry.purpose}\n"
        'Reply with the JSON object {"content": <the whole text of the file>}. The text must '
        "load into the contract above; it is written to the bundle as you send it."
    )


def repair_task(rel: str, problems: Sequence[str]) -> str:
    """The task of the repair call for ``rel``: what the world close found in it."""
    found = "".join(f"- {problem}\n" for problem in problems)
    return (
        f"The world close found these problems in {rel}, which is already written:\n{found}"
        'Reply with the JSON object {"content": <the whole text of the file, fixed>}; it '
        "replaces the file as you send it."
    )


Role = Literal["planner", "reviewer"]
Checkpoint = Callable[[str, str], None]


class DirectorError(Exception):
    """A stage cannot go on; ``Director.run`` fails the stage and the plan with its message."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    return _sha256(json.dumps(value, sort_keys=True))


def director_cache_key(
    role: RoleConfig, system: str, message: str, schema: Mapping[str, Any] | None
) -> str:
    """The cache key of one attempt (R-cache-key): the model, the role's settings less
    ``ROLE_KEY_EXCLUDES``, the schema, the user message and the system prompt, beside
    ``DIRECTOR_CACHE_VERSION``. Nothing the agent sees is listed by hand, so nothing it sees is
    left out."""
    role_digest = _digest(role.model_dump(mode="json", exclude=set(ROLE_KEY_EXCLUDES)))
    schema_digest = _digest(None if schema is None else dict(schema))
    prompt = f"{DIRECTOR_CACHE_VERSION}\0{role_digest}\0{schema_digest}\0{message}"
    return JudgeCache.key(role.model, prompt, system=system)


def conversation_id(slug: str, stage: Stage, role: str, index: int, attempt: int) -> str:
    """``plan/<slug>/<stage>/<role>/<index>/a<attempt>``: one session per attempt (spec section
    6, "Sessions"); the ledger reads the role from the fourth segment."""
    return f"plan/{slug}/{stage}/{role}/{index}/a{attempt}"


@dataclass(frozen=True)
class CallSpec:
    """One planner or reviewer call. ``message(failures)`` builds the user message (through
    ``planner/context.py``'s builders only); ``check(reply)`` returns the parsed reply and its
    failures; ``outputs(parsed)`` the files the call commits, path to text; ``commit(parsed,
    record)`` sets the record fields the call commits, in the same write as the call (R-commit).
    ``parse(reply)``, when given, is the pure half of ``check``: a function of the reply alone,
    the parsed value ``check`` returns for it. A resume rebuilds a committed call's parsed reply
    with it, so a check that reads state (the manifest's call budget, the bundle on disk) is
    never run again on other state (the Task 7a re-review's carry); with none, ``check``'s
    parsed value is read."""

    stage: Stage
    role: Role
    purpose: str
    system: Literal["planner", "reviewer", "confirm"]
    schema: Mapping[str, Any] | None
    message: Callable[[Sequence[str]], str]
    check: Callable[[str], tuple[Any, list[str]]]
    outputs: Callable[[Any], dict[str, str]]
    commit: Callable[[Any, PlanRecord], None] | None = None
    parse: Callable[[str], Any] | None = None


@dataclass(frozen=True)
class Answer:
    """A committed call and its parsed reply. ``provider_failed``: the call's error came from a
    ``ProviderError`` (a timeout among them), not from two failed checks (R-stub-modes)."""

    call: DirectorCall
    parsed: Any
    provider_failed: bool = False


def _check_plan(reply: str) -> tuple[str, list[str]]:
    if not reply.strip():
        return reply, ["the reply is blank: plan.md needs the plan's text"]
    if len(reply) > MAX_PLAN_CHARS:
        return reply, [
            f"the reply is {len(reply):,} characters; plan.md holds at most {MAX_PLAN_CHARS:,}"
        ]
    return reply, []


_NOT_MANIFEST: Final = 'the reply is not the JSON object {"files": [...]} and nothing else'
_NOT_CONTENT: Final = 'the reply is not the JSON object {"content": <the file\'s text>}'


def _field_errors(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, error['loc'])) or '<root>'}: {error['msg']}" for error in exc.errors()
    )


def _read_manifest(reply: str) -> tuple[list[ManifestEntry] | None, str]:
    """The manifest a reply holds, or None and why not; a function of the reply alone."""
    try:
        data = json.loads(reply)
    except ValueError:
        return None, _NOT_MANIFEST
    if not isinstance(data, dict) or set(data) != {"files"} or not isinstance(data["files"], list):
        return None, _NOT_MANIFEST
    entries: list[ManifestEntry] = []
    for number, raw in enumerate(data["files"], 1):
        try:
            entries.append(ManifestEntry.model_validate(raw))
        except ValidationError as exc:
            return None, f"manifest entry {number} does not load: {_field_errors(exc)}"
    return entries, ""


def parse_manifest(reply: str) -> list[ManifestEntry] | None:
    """The manifest call's pure parse: the entries a reply holds, or None."""
    return _read_manifest(reply)[0]


def parse_content(reply: str) -> str | None:
    """A file or repair call's pure parse: the ``content`` string of ``{"content": ...}`` and
    nothing else, or None."""
    try:
        data = json.loads(reply)
    except ValueError:
        return None
    if not isinstance(data, dict) or set(data) != {"content"}:
        return None
    content = data["content"]
    return content if isinstance(content, str) else None


def _commit_manifest(parsed: Any, record: PlanRecord) -> None:
    record.manifest = list(parsed)  # R-commit: in the manifest call's own record write


_WORLD_KINDS: Final[Mapping[ManifestKind, int]] = {
    "world_sheet": 0,
    "document": 1,
    "ladder": 2,
    "premise_sheet": 3,
}
_LATER_KINDS: Final[tuple[ManifestKind, ...]] = ("persona", "config", "expected")


def author_order(manifest: Sequence[ManifestEntry]) -> list[ManifestEntry]:
    """Stage 2's file order (spec section 7, step 3): per world, in the order the manifest first
    names it, its sheet, its documents in manifest order, its ladders, then its premise sheets;
    then the personas, ``config.yaml`` and ``expected.yaml``, each in manifest order."""
    worlds = dict.fromkeys(world_of(e.path) for e in manifest if e.kind in _WORLD_KINDS)
    ordered: list[ManifestEntry] = []
    for world in worlds:
        mine = [e for e in manifest if e.kind in _WORLD_KINDS and world_of(e.path) == world]
        ordered += sorted(mine, key=lambda e: _WORLD_KINDS[e.kind])
    for kind in _LATER_KINDS:
        ordered += [e for e in manifest if e.kind == kind]
    return ordered


def _group_of(rel: str) -> str | None:
    """The ``REVIEW_GROUPS`` member a path is reviewed in; None outside the grammar and for
    ``review.md``."""
    try:
        kind = kind_of(rel)
    except BundlePathError:
        return None
    if kind == "document":
        return "corpus"
    if kind in _LINES_KINDS:
        return "lines"
    if kind in _PLAN_KINDS or rel == "plan.md":
        return "plan"
    return None


def _review_sets(paths: Iterable[str]) -> list[tuple[str, tuple[str, ...]]]:
    """Stage 3's chunking rule over ``paths`` (spec section 7, stage 3): the ``corpus`` group's
    documents in path order, in chunks of at most ``REVIEW_CHUNK_DOCS`` named ``corpus-1``,
    ``corpus-2``, ...; ``lines``, the world sheets, ladders, personas and premise sheets in path
    order; ``plan``, ``plan.md``, ``config.yaml`` and ``expected.yaml`` in that order. A group
    with no file is left out. The one rule ``review_calls`` (the budget) and ``review_groups``
    (the calls) both read, so the two never disagree."""
    by_group: dict[str, list[str]] = {name: [] for name in REVIEW_GROUPS}
    for rel in sorted(set(paths)):
        group = _group_of(rel)
        if group is not None:
            by_group[group].append(rel)
    plan_order = ("plan.md", *FIXED_ENTRIES)
    by_group["plan"].sort(key=plan_order.index)
    corpus = by_group["corpus"]
    out = [
        (f"corpus-{n + 1}", tuple(corpus[i : i + REVIEW_CHUNK_DOCS]))
        for n, i in enumerate(range(0, len(corpus), REVIEW_CHUNK_DOCS))
    ]
    return out + [(name, tuple(by_group[name])) for name in ("lines", "plan") if by_group[name]]


def review_calls(paths: Iterable[str]) -> int:
    """The reviewer calls stage 3 makes over a bundle holding ``paths`` (spec section 7, stage
    3, ``REVIEW_GROUPS``): one per chunk of at most ``REVIEW_CHUNK_DOCS`` documents (``corpus``),
    one for the world sheets, ladders, personas and premise sheets (``lines``), and one for
    ``plan.md``, ``config.yaml`` and ``expected.yaml`` (``plan``); a group with no file makes
    none, and a path outside the grammar, or ``review.md``, is in no group (``_review_sets``)."""
    return len(_review_sets(paths))


def review_groups(bundle: Bundle, record: PlanRecord) -> list[ReviewGroup]:
    """Stage 3's reviewer calls, one ``ReviewGroup`` each (``_review_sets``): every grammar file
    present but ``review.md`` and the unchanged base files (``context.unchanged_base_files``,
    the rule's one home, which the manifest's budget reads too), in groups; each group's
    ``index`` is the unchanged base files of its kinds, shown by one index line each so links
    can be followed. A group with no file is left out."""
    unchanged = unchanged_base_files(record.base_files, record.manifest)
    reviewed = set(bundle.index()) - set(unchanged) - {REVIEW_FILE}
    index: dict[str, list[str]] = {name: [] for name in REVIEW_GROUPS}
    for rel in unchanged:
        group = _group_of(rel)
        if group is not None:
            index[group].append(rel)
    return [
        ReviewGroup(name, files, tuple(index[name.partition("-")[0]]))
        for name, files in _review_sets(reviewed)
    ]


# ------------------------------------------------------------------ stage 3 and 4 replies

SEVERITIES: Final = ("block", "fix", "note")
Verdict = Literal["present", "absent", "cannot_tell"]
_VERDICTS: Final[tuple[Verdict, ...]] = get_args(Verdict)
# {"summary": {"block", "fix", "note"}, "findings": [{"severity", "file", "quote", "problem",
# "direction"}]} (spec section 7, stage 3; the reply context.REVIEW_REPLY names)
REVIEW_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "findings"],
    "properties": {
        "summary": {
            "type": "object",
            "additionalProperties": False,
            "required": list(SEVERITIES),
            "properties": {s: {"type": "integer", "minimum": 0} for s in SEVERITIES},
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "file", "quote", "problem", "direction"],
                "properties": {
                    "severity": {"enum": list(SEVERITIES)},
                    "file": {"type": "string"},
                    "quote": {"type": "string"},
                    "problem": {"type": "string"},
                    "direction": {"type": ["string", "null"]},
                },
            },
        },
    },
}
# {"content", "responses": [{"finding", "status", "text"}]} (spec section 7, stage 4)
REVISE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content", "responses"],
    "properties": {
        "content": {"type": "string"},
        "responses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["finding", "status", "text"],
                "properties": {
                    "finding": {"type": "integer"},
                    "status": {"enum": ["fixed", "declined"]},
                    "text": {"type": "string"},
                },
            },
        },
    },
}
# {"verdicts": [{"passage", "verdict"}]}, ``passage`` the local number shown (D-confirm)
CONFIRM_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["passage", "verdict"],
                "properties": {
                    "passage": {"type": "integer"},
                    "verdict": {"enum": list(_VERDICTS)},
                },
            },
        }
    },
}


class _Reply(BaseModel):
    """A judge or revise reply read strictly: no extra key, no coerced type."""

    model_config = ConfigDict(extra="forbid", strict=True)


class _Summary(_Reply):
    block: int
    fix: int
    note: int


class _RawFinding(_Reply):
    severity: Literal["block", "fix", "note"]
    file: str
    quote: str
    problem: str
    direction: str | None = None


class _Review(_Reply):
    summary: _Summary | None = None
    findings: list[_RawFinding]


class _Response(_Reply):
    finding: int
    status: Literal["fixed", "declined"]
    text: str


class Revision(_Reply):
    """A revise call's parsed reply: the file's whole new text and one response per finding."""

    content: str
    responses: list[_Response]


class _Verdict(_Reply):
    passage: int
    verdict: str


class _Verdicts(_Reply):
    verdicts: list[_Verdict]


_NOT_REVIEW: Final = (
    'the reply is not the JSON object {"summary": {...}, "findings": [...]} and nothing else'
)
_NOT_REVISION: Final = (
    'the reply is not the JSON object {"content": ..., "responses": [...]} and nothing else'
)
_NOT_VERDICTS: Final = 'the reply is not the JSON object {"verdicts": [...]} and nothing else'


def _load[T: _Reply](model: type[T], reply: str) -> T | None:
    try:
        return model.model_validate_json(reply)
    except ValidationError:
        return None


def _counts(findings: Iterable[ReviewFinding]) -> dict[str, int]:
    listed = list(findings)
    return {s: sum(f.severity == s for f in listed) for s in SEVERITIES}


def _count_line(counts: Mapping[str, int]) -> str:
    return " / ".join(f"{s} {counts[s]}" for s in SEVERITIES)


def parse_review(reply: str) -> list[ReviewFinding]:
    """A review call's pure parse: the findings a reply holds, unnumbered (``id=0``), a block
    ``open`` until stage 4 closes it; none for a reply that does not load."""
    review = _load(_Review, reply)
    if review is None:
        return []
    return [
        ReviewFinding(
            id=0,
            severity=raw.severity,
            file=raw.file,
            quote=raw.quote,
            problem=raw.problem,
            direction=raw.direction,
            open=raw.severity == "block",
        )
        for raw in review.findings
    ]


def check_findings(
    reply: str, group: ReviewGroup, bundle: Bundle
) -> tuple[list[ReviewFinding], list[str]]:
    """A review reply's findings (unnumbered, ``id=0``) and its failures, spec section 7 stage
    3's refusals in full: a reply that is not the object; no ``summary`` (a reply with no
    findings is clean only with the explicit zero summary, so a review the harness cannot read
    is never read as none); a finding's ``file`` not a file of the group; a ``block`` with no
    quote; a non-empty quote whose ``squash`` is not in the ``squash`` of the file's text (as
    the review message shows it); the summary's counts not the findings'. No failure repeats
    a quote, so none can carry a ``call:`` line into the retry."""
    review = _load(_Review, reply)
    if review is None:
        return [], [_NOT_REVIEW]
    findings = parse_review(reply)
    failures: list[str] = []
    if review.summary is None:
        failures.append(
            'the reply has no summary; with nothing to report it is {"summary": {"block": 0, '
            '"fix": 0, "note": 0}, "findings": []}'
        )
    for number, finding in enumerate(findings, 1):
        if finding.file not in group.files:
            failures.append(
                f"finding {number}: {finding.file!r} is not a file of this group "
                f"({', '.join(group.files)})"
            )
        elif finding.severity == "block" and not squash(finding.quote):
            failures.append(f"finding {number}: a block quotes the exact text it is about")
        elif squash(finding.quote) not in squash(bundle.read_file(finding.file)):
            failures.append(f"finding {number}: its quote is not text of {finding.file}")
    counts = _counts(findings)
    if review.summary is not None and review.summary.model_dump() != counts:
        failures.append(
            f"the summary counts {_count_line(review.summary.model_dump())}, but the findings "
            f"are {_count_line(counts)}"
        )
    return findings, failures


def parse_revision(reply: str) -> Revision | None:
    """A revise call's pure parse: its ``content`` and ``responses``, or None."""
    return _load(Revision, reply)


def parse_verdicts(reply: str) -> dict[int, str] | None:
    """A confirm call's pure parse: each local passage number to its verdict, or None."""
    loaded = _load(_Verdicts, reply)
    if loaded is None:
        return None
    return {v.passage: v.verdict for v in loaded.verdicts}


def check_verdicts(reply: str, shown: int) -> tuple[dict[int, str] | None, list[str]]:
    """A confirm reply's verdicts and its failures: a reply that is not the object, a number
    that is not one shown (1 to ``shown``), a number given twice, a verdict not one of
    ``present``, ``absent``, ``cannot_tell``. A number left out is no failure (preflight Q44):
    its passage has no verdict, and its block stays open (spec section 7, stage 4)."""
    loaded = _load(_Verdicts, reply)
    if loaded is None:
        return None, [_NOT_VERDICTS]
    failures: list[str] = []
    seen: Counter[int] = Counter(v.passage for v in loaded.verdicts)
    for number, times in sorted(seen.items()):
        if not 1 <= number <= shown:
            failures.append(f"passage {number} is not a number shown (1 to {shown})")
        elif times > 1:
            failures.append(f"passage {number} has {times} verdicts; give one per number")
    for verdict in dict.fromkeys(v.verdict for v in loaded.verdicts):
        if verdict not in _VERDICTS:
            failures.append(f"{verdict!r} is not a verdict: give present, absent or cannot_tell")
    return parse_verdicts(reply), failures


def _last_stage(record: PlanRecord, stage: Stage) -> StageRecord | None:
    return next((s for s in reversed(record.stages) if s.stage == stage), None)


def _last_reply(bundle: Bundle, call: DirectorCall) -> str:
    return bundle.read_transcript(call.transcript).attempts[-1].reply


def review_findings(bundle: Bundle, record: PlanRecord) -> list[ReviewFinding]:
    """The committed review calls' findings, numbered 1.. in call order and reply order, as
    stage 3 left them: no response, no verdict."""
    review = _last_stage(record, "review")
    found: list[ReviewFinding] = []
    for call in review.calls if review is not None else []:
        if call.status != "error" and call.purpose.startswith("review:"):
            found += parse_review(_last_reply(bundle, call))
    return [finding.model_copy(update={"id": n}) for n, finding in enumerate(found, 1)]


def _blocks(findings: Sequence[ReviewFinding], rel: str) -> list[ReviewFinding]:
    """The blocks on ``rel`` in id order: the confirm call's passages, numbered 1 to k."""
    return [f for f in findings if f.file == rel and f.severity == "block"]


def findings_of(bundle: Bundle, record: PlanRecord) -> list[ReviewFinding]:
    """The one reader of the findings (R-review-md): ``review_findings``, then from the
    committed revise stage's calls, read from their transcripts, each block and fix finding's
    ``response`` and ``planner_status`` (its file's ``revise:`` reply) and each block's
    ``confirm`` (its file's ``confirm:`` reply, the local passage number mapped back) and
    ``open``. A block closes only when its ``planner_status`` is ``fixed``, ``squash(quote)`` is
    not in the ``squash`` of its file as the stage's last committed call that wrote it left it,
    and its verdict is ``absent`` (spec section 7, stage 4). No record holds a second copy, so a
    resume renders what an unbroken plan renders, whatever the files hold now."""
    findings = review_findings(bundle, record)
    revise = _last_stage(record, "revise")
    if revise is None:
        return findings
    texts: dict[str, str] = {}
    for call in revise.calls:
        if call.status == "error":
            continue
        kind, _, rel = call.purpose.partition(":")
        if call.outputs:
            texts.update(committed_outputs(call, bundle.read_transcript(call.transcript)))
        if kind == "revise":
            revision = parse_revision(_last_reply(bundle, call))
            answers = {r.finding: r for r in revision.responses} if revision else {}
            for finding in findings:
                if finding.file == rel and finding.id in answers:
                    finding.response = answers[finding.id].text
                    finding.planner_status = answers[finding.id].status
        elif kind == "confirm":
            verdicts = parse_verdicts(_last_reply(bundle, call)) or {}
            for number, block in enumerate(_blocks(findings, rel), 1):
                verdict = verdicts.get(number)
                if verdict in _VERDICTS:
                    block.confirm = verdict
    for finding in findings:
        if finding.severity == "block":
            now = texts.get(finding.file)
            finding.open = not (
                finding.planner_status == "fixed"
                and now is not None
                and squash(finding.quote) not in squash(now)
                and finding.confirm == "absent"
            )
    return findings


def render_review(findings: Sequence[ReviewFinding], *, revised: bool = False) -> str:
    """``review.md`` (spec section 7, stage 3; A4): the summary line ``block N / fix N / note
    N``, then per file in path order a blank line, ``## <file>`` and its findings in id order,
    ``- [<id>] <severity>: "<quote>" <problem>`` with `` (direction: <direction>)`` on a fix
    that has one; under a finding with a response, ``  - response (<planner_status>):
    <response>``; under a block with a verdict, ``  - confirm: <verdict> (closed)`` when it
    closed, ``(open)`` otherwise. With ``revised`` (stage 4's render, after the confirm pass) a
    block with no verdict (a number the confirm reply left out, a confirm call that failed
    twice, a file whose revision errored) reads ``  - confirm: none (open)``, so every open
    block is marked (Task 8 review m1). The quote is a JSON string, so a quote across a line
    break or holding a quote mark stays one line and exact; the problem, direction and response
    are squashed to one line. LF, one trailing newline."""
    parts = [_count_line(_counts(findings)) + "\n"]
    for rel in sorted({f.file for f in findings}):
        lines = [f"## {rel}"]
        for f in sorted((f for f in findings if f.file == rel), key=lambda f: f.id):
            line = f"- [{f.id}] {f.severity}: {json.dumps(f.quote, ensure_ascii=False)}"
            line += f" {squash(f.problem)}" if squash(f.problem) else ""
            if f.severity == "fix" and f.direction and squash(f.direction):
                line += f" (direction: {squash(f.direction)})"
            lines.append(line)
            if f.response is not None and f.planner_status is not None:
                lines.append(f"  - response ({f.planner_status}): {squash(f.response)}".rstrip())
            if f.severity == "block" and (f.confirm is not None or revised):
                verdict = f.confirm or "none"
                lines.append(f"  - confirm: {verdict} ({'open' if f.open else 'closed'})")
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts)


def _fenced(text: str, info: str = "") -> str:
    """``text`` in a fence longer than any backtick run it holds, so the context scrub, which
    never edits a fenced block, leaves it as written and a quote in it stays exact."""
    run = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, run + 1)
    body = text if text.endswith("\n") else f"{text}\n"
    return f"{fence}{info}\n{body}{fence}\n"


def revise_task(rel: str, text: str, rendered: str) -> str:
    """The task of the ``revise:<rel>`` call (spec section 7, stage 4; docs/08 "Stage 4"): the
    file as committed before stage 4, its findings as ``render_review`` renders them, and the
    reply's fields. Both are fenced, so the scrub leaves them as written."""
    info = "markdown" if rel.endswith(".md") else "yaml"
    return (
        f"Revise {rel}, stage 4 of your instructions: fix every finding tagged block or fix "
        "below and answer each one; a note needs no answer. The file as it stands:\n"
        f"{_fenced(text, info)}"
        f"Its findings:\n{_fenced(rendered)}"
        'Reply with the JSON object {"content": <the whole text of the file, revised>, '
        '"responses": [{"finding": <the number in brackets>, "status": "fixed" | "declined", '
        '"text": <what you changed, or why you did not>}]}, one response per block and fix '
        "finding above. The content is checked as the file was when it arrived, and replaces "
        "the file as you send it."
    )


def _world_files(root: Path, name: str) -> list[tuple[str, Path]]:
    """Each file under a world's folder ``root``, as its bundle path under ``worlds/<name>/``
    beside its own path, in path order."""
    return [
        (f"{WORLDS}/{name}/{path.relative_to(root).as_posix()}", path)
        for path in sorted(p for p in root.rglob("*") if p.is_file())
    ]


_ARRIVAL_MODELS: Final[Mapping[ManifestKind, type[BaseModel]]] = {
    "world_sheet": WorldSheet,
    "ladder": LadderConfig,
    "persona": PersonaSheet,
    "expected": ExpectedEvents,
}
# the first document a world-close message names ("document 'x' links_to ...", "buried
# document 'x' is unreachable ..."): World.validate_links' own message shapes
_NAMED_DOCUMENT: Final = re.compile(r"(?:buried )?document '([^']+)'")


class Director:
    """One plan's Director over ``bundle`` and its ``record`` (spec section 7)."""

    def __init__(
        self,
        bundle: Bundle,
        record: PlanRecord,
        *,
        provider_factory: ProviderFactory = build_provider,
        worlds_dir: Path = WORLDS_DIR,
        docs_dir: Path = DOCS_DIR,
        checkpoint: Checkpoint | None = None,
        say: Callable[[str], None] = print,
    ) -> None:
        self.bundle = bundle
        self.record = record
        self.provider_factory = provider_factory
        self.worlds_dir = worlds_dir
        self.docs_dir = docs_dir
        self.checkpoint = checkpoint
        self.say = say
        self.cache = JudgeCache(bundle.root.parent / CACHE_DIR / DIRECTOR_CACHE)
        self._providers: dict[Role, ChatProvider] = {}

    @classmethod
    def new(cls, request: PlanRequest, *, plans_root: Path, **kw: Any) -> Self:
        """A new plan for ``request`` under ``plans_root``, its ``plan.json`` written. A slug that
        already holds a plan for the same request is continued (``plan new`` run again); one
        that holds another request's plan is refused with ``DirectorError``."""
        slug = request.slug or slug_for(request.question)
        bundle = Bundle.create(plans_root, slug)
        if (bundle.root / PLAN_FILE).is_file():
            record = bundle.read_record()
            if record.request != request:
                raise DirectorError(
                    f"{bundle.root} holds a plan for another request; give this one another "
                    "slug, or continue that plan"
                )
            return cls(bundle, record, **kw)
        record = PlanRecord(
            slug=slug,
            created_at=datetime.now(UTC),
            request=request,
            provenance="director",
            git_sha=_git_sha(),
            planner_model=request.planner_model.model,
            reviewer_model=request.reviewer_model.model,
            prompt_hashes=prompt_hashes(),
        )
        bundle.write_record(record)
        return cls(bundle, record, **kw)

    @classmethod
    def open(cls, root: Path, **kw: Any) -> Self:
        """The plan at ``root``, as its ``plan.json`` holds it."""
        bundle = Bundle(root)
        return cls(bundle, bundle.read_record(), **kw)

    # ------------------------------------------------------------------ the call primitive

    def ask(self, spec: CallSpec) -> Answer:
        """One call, in spec section 8's order of writes (the module docstring)."""
        # _open_stage writes a new StageRecord before any marker, so a kill inside the stage's
        # first call leaves a record that names the stage (K1; review Minor 2)
        stage = self._open_stage(spec.stage)
        index = len(stage.calls)
        self._check_ceiling()  # DirectorError naming max_director_calls before any write
        rel = self.bundle.transcript_rel(spec.stage, spec.role, index)
        self.bundle.write_attempt(
            DirectorAttempt(
                stage=spec.stage, role=spec.role, index=index, ledger_lines=self._ledger_lines()
            )
        )
        system = load_director_prompt(spec.system)
        role = self._role(spec.role)
        provider = self._provider(spec.role)
        attempts: list[TranscriptAttempt] = []
        failures: list[str] = []
        parsed: Any = None
        status: Literal["fresh", "cached", "error"] = "error"
        key = ""
        error: str | None = None
        provider_failed = False
        for attempt in (1, 2):
            message = spec.message(failures)
            if len(message) > MAX_CONTEXT_CHARS:
                what = "the retry's message" if attempt == 2 else "the message"
                over = (
                    f"{spec.purpose}: {what} is {len(message):,} characters, over "
                    f"MAX_CONTEXT_CHARS ({MAX_CONTEXT_CHARS:,})"
                )
                if attempt == 2:  # attempt 1 was sent: an error call records it (review M2)
                    error = f"{'; '.join(failures)}; {over}; the retry was not sent"
                    break
                self.bundle.clear_attempt()  # nothing was sent: no call is dead
                raise DirectorError(f"{over}; nothing was sent")
            key = director_cache_key(role, system, message, spec.schema)
            cid = conversation_id(self.bundle.slug, spec.stage, spec.role, index, attempt)
            hit = self.cache.get(key)
            reply = hit.get("reply") if hit is not None else None
            if isinstance(reply, str):
                parsed, failures = spec.check(reply)
                if not failures:
                    note_cached(cid, role.model)
                    attempts.append(TranscriptAttempt(message=message, reply=reply))
                    status = "cached"
                    break
            reset = getattr(provider, "reset_session", None)
            if callable(reset):
                reset(cid)
            try:
                completion = provider.complete(
                    cid,
                    system,
                    [Message(role="user", content=message)],
                    json_schema=None if spec.schema is None else dict(spec.schema),
                )
            except RateLimitError as exc:
                self.bundle.clear_attempt()  # D-rate-limit: a pause commits nothing
                raise RateLimitExit(str(exc), exc.retry_after_s) from exc
            except ProviderError as exc:  # a timeout among them: an error, never waited on
                error = f"{type(exc).__name__}: {exc}"
                provider_failed = True
                break
            reply = completion.text  # never completion.reasoning_text (non-negotiable 6)
            attempts.append(TranscriptAttempt(message=message, reply=reply))
            parsed, failures = spec.check(reply)
            if not failures:
                status = "fresh"
                break
        if status == "error" and error is None:
            error = "; ".join(failures)
        self.bundle.write_transcript(
            rel, Transcript(system_sha256=_sha256(system), model=role.model, attempts=attempts)
        )
        self._checkpoint("transcript", spec.purpose)
        outputs = spec.outputs(parsed) if status != "error" else {}
        normalized = {path: normalize_text(text) for path, text in outputs.items()}
        for path in normalized:
            self.bundle.check_path(path)  # refused before the commit, never after it
        call = DirectorCall(
            role=spec.role,
            index=index,
            purpose=spec.purpose,
            outputs={path: _sha256(text) for path, text in normalized.items()},
            cache_key=key,
            status=status,
            model=role.model,
            transcript=rel,
            attempts=2 if len(attempts) == 2 else 1,
            error=error,
            provider_failed=provider_failed,
        )
        stage.calls.append(call)
        if status != "error" and spec.commit is not None:
            spec.commit(parsed, self.record)  # R-commit: the call's record fields, one write
        self.bundle.write_record(self.record)  # the commit
        self._checkpoint("record", spec.purpose)
        for path, text in normalized.items():
            self.bundle.write_file(path, text)
        self._checkpoint("files", spec.purpose)
        if status == "fresh":
            self.cache.put(key, {"reply": attempts[-1].reply})
        return Answer(call=call, parsed=parsed, provider_failed=provider_failed)

    def _role(self, role: Role) -> RoleConfig:
        request = self.record.request
        return request.planner_model if role == "planner" else request.reviewer_model

    def _provider(self, role: Role) -> ChatProvider:
        """The role's provider, built on its first use (state dir ``state/<role>``) and kept."""
        if role not in self._providers:
            state_dir = self.bundle.root / STATE_DIR / role
            self._providers[role] = self.provider_factory(self._role(role), state_dir)
        return self._providers[role]

    def _checkpoint(self, step: str, purpose: str) -> None:
        if self.checkpoint is not None:
            self.checkpoint(step, purpose)

    def _check_ceiling(self) -> None:
        """Refuse the call when the plan has made ``max_director_calls`` calls (spec section 13:
        refused before the call, with the count)."""
        limit = self.record.request.max_director_calls
        made = self._calls_made()
        if made >= limit:
            raise DirectorError(
                f"the plan would pass max_director_calls ({limit}): {made} calls made"
            )

    def _all_calls(self) -> list[DirectorCall]:
        """Every committed call, in every stage and earlier round."""
        stages = [*self.record.stages, *(s for r in self.record.rounds for s in r)]
        return [call for stage in stages for call in stage.calls]

    def _calls_made(self) -> int:
        """The planner and reviewer calls the plan has committed (a manual file is none)."""
        return sum(call.status != "manual" for call in self._all_calls())

    # ------------------------------------------------------------------ stages and resume

    def _stage(self, stage: Stage) -> StageRecord | None:
        return _last_stage(self.record, stage)

    def _open_stage(self, stage: Stage, *, adopt: bool = False) -> StageRecord:
        """The open record of ``stage``, written as a new one when the last record is not it. A
        stage is opened once: a name the record already holds is refused, so no call of a
        second record of it can take an earlier call's index and transcript (Task 1 review M1;
        a resume reopens a failed stage in place). With ``adopt``, a new record holds the sha of
        every grammar file present (``inputs``) and the plan adopts the hand edits it finds
        (``_adopt_edits``), in the record write that opens the stage, before anything else; an
        open record entered again re-records them (``_readopt``)."""
        last = self.record.stages[-1] if self.record.stages else None
        if last is not None and last.stage == stage and last.status == "open":
            if adopt:
                self._readopt(last)
            return last
        if self._stage(stage) is not None:
            raise DirectorError(f"stage {stage} has a record already; a stage is opened once")
        opened = StageRecord(stage=stage, started_at=datetime.now(UTC), status="open")
        if adopt:
            opened.inputs = self.bundle.index()
            self._adopt_edits(opened.inputs)
        self.record.stages.append(opened)
        self.bundle.write_record(self.record)
        return opened

    def _adopt_edits(self, present: Mapping[str, str]) -> None:
        """``edited`` gains each path present whose sha differs from the one its last committing
        call recorded, or, for a file no call wrote, from ``base_files`` (spec section 8: a
        committed stage's files are the owner's to edit, and the next stage adopts them)."""
        owned = self._owned()
        for rel, sha in present.items():
            if rel in owned and owned[rel] != sha and rel not in self.record.edited:
                self.record.edited.append(rel)

    def _owned(self, *, besides: StageRecord | None = None) -> dict[str, str]:
        """Each committed path to the sha its last committing call recorded, or, for a file no
        call wrote, ``base_files``'; the calls of ``besides`` left out."""
        owned = dict(self.record.base_files)
        for stage in commit_order(self.record):
            if stage is not besides:
                for call in stage.calls:
                    owned.update(call.outputs)
        return owned

    def _readopt(self, stage: StageRecord) -> None:
        """Review M2: a stage entered again (a resume after a kill or a pause, a continue after
        a failure) re-records what it opened with, so the record says what its next call reads:
        ``inputs`` holds each of its paths as it now is (one the resume removed left out), and
        ``edited`` holds one of them exactly when it differs from its committing call's sha (a
        plan.md put back after a failed scan leaves it; an edit made during a pause joins it).
        Other entries of ``edited`` stay. A path the stage itself writes keeps the sha it opened
        with and is no edit (Task 8): a file a committed call of the stage rewrote (stage 4's
        revisions), which the resume wrote back from that call's transcript, and ``review.md``,
        which the review and revise stages render before they commit (R-review-md). Each is the
        stage's output, not its input. One record write, only when either changed."""
        present = self.bundle.index()
        own = {rel for call in stage.calls for rel in call.outputs}
        if stage.stage in ("review", "revise"):
            own.add(REVIEW_FILE)
        inputs = {
            rel: stage.inputs[rel] if rel in own else present[rel]
            for rel in stage.inputs
            if rel in present
        }
        owned = self._owned(besides=stage)
        differs = {
            rel
            for rel, sha in inputs.items()
            if rel not in own and rel in owned and owned[rel] != sha
        }
        # a path the stage itself writes keeps its membership as the stage found it (review I1:
        # an edit adopted at stage 4's open, of a file stage 4 then revises, stays adopted)
        edited = [
            rel
            for rel in self.record.edited
            if rel not in stage.inputs or rel in differs or rel in own
        ]
        edited += sorted(differs - set(edited))
        if inputs != stage.inputs or edited != self.record.edited:
            stage.inputs = inputs
            self.record.edited = edited
            self.bundle.write_record(self.record)

    def _call(self, stage: StageRecord, index: int, spec: CallSpec) -> Answer:
        """The answer to the stage's call at ``index``: asked when the stage has not reached it,
        else rebuilt from the committed call, so a resumed stage handles it exactly as it
        handled the fresh answer (review C1: a committed ``error`` call fails the stage again,
        never reads as done). The parsed reply is read back from the transcript by the spec's
        pure ``parse`` (else its ``check``'s parsed value), so no check that reads state runs
        on a resume; a call there with another purpose is refused."""
        if index >= len(stage.calls):
            return self.ask(spec)
        call = stage.calls[index]
        if call.purpose != spec.purpose:
            raise DirectorError(
                f"stage {stage.stage}: call {index} is {call.purpose!r}, not {spec.purpose!r}"
            )
        parsed: Any = None
        if call.status != "error":
            reply = self.bundle.read_transcript(call.transcript).attempts[-1].reply
            parsed = spec.parse(reply) if spec.parse is not None else spec.check(reply)[0]
        return Answer(call=call, parsed=parsed, provider_failed=call.provider_failed)

    def _commit_stage(self, stage: StageRecord, *, failed: bool = False) -> None:
        """The stage committed and the status it earned, or with ``failed`` the plan
        ``failed`` (stage 4 with ``open_blocks > 0``), in one record write."""
        stage.status = "committed"
        stage.finished_at = datetime.now(UTC)
        self.record.status = "failed" if failed else _EARNED[stage.stage]
        self.bundle.write_record(self.record)

    def _fail(self, stage: Stage, error: str) -> None:
        """The stage failed, and with it the plan (spec section 13)."""
        failed = self._stage(stage) or self._open_stage(stage)
        failed.status = "failed"
        failed.error = error
        failed.finished_at = datetime.now(UTC)
        self.record.status = "failed"
        self.bundle.write_record(self.record)

    def _record_dead_attempt(self, stage: StageRecord) -> None:
        """A marker naming a call of ``stage`` at or past ``len(calls)`` is a dead attempt: its
        ledger lines are dropped, it is appended to ``record.resumed`` unless it is already the
        last entry there (the runtime's ``flagged`` rule, ``runner/env_turn.py``: a resume
        killed before its marker clear reads the same marker again, review M1), and the marker
        is cleared; any other marker is only cleared, so a marker is read at most once
        (R-marker)."""
        attempt = self.bundle.read_attempt()
        if attempt is None:
            return
        if attempt.stage == stage.stage and attempt.index >= len(stage.calls):
            self._drop_dead_lines(attempt)
            if attempt not in self.record.resumed[-1:]:
                self.record.resumed.append(attempt)
                self.bundle.write_record(self.record)
        self.bundle.clear_attempt()

    def _ledger_raw(self) -> list[str]:
        """The plan ledger's non-blank lines, split on ``\\n`` alone as ``parsed_lines`` splits
        (fix round 2, re-review N-B: ``splitlines`` also splits on U+2028, U+2029 and U+0085,
        which a provider's error text can carry raw); each line's bytes kept."""
        path = self.bundle.root / LEDGER
        if not path.is_file():
            return []
        return [line for line in path.read_bytes().decode("utf-8").split("\n") if line.strip()]

    def _ledger_lines(self) -> int:
        """The plan ledger's line count, which a marker records (``ledger_lines``)."""
        return len(self._ledger_raw())

    def _drop_dead_lines(self, attempt: DirectorAttempt) -> None:
        """Drop the dead attempt's lines from the plan's ledger, the rule the dry run applies
        through ``AttemptMarker.written`` (Task 5, D-K12): a line whose call never reached the
        record. The marker names the newest call's lines exactly: those of its conversation
        ids after its ``ledger_lines`` (review I1: a failed call's retry reuses the index and the
        ids, so the failed call's own line, before the offset, stays). The redone call writes its
        own, so the ledger reads as an unbroken plan's. A rate limit's line stays, its marker
        cleared before any resume (D-rate-limit; the dry run, whose lines are stub calls, drops
        it)."""
        raw = self._ledger_raw()
        prefix = f"plan/{self.bundle.slug}/{attempt.stage}/{attempt.role}/{attempt.index}/"
        kept = raw[: attempt.ledger_lines] + [
            line
            for line in raw[attempt.ledger_lines :]
            if not LedgerLine.model_validate_json(line).conversation_id.startswith(prefix)
        ]
        if len(kept) != len(raw):
            write_atomic(self.bundle.root / LEDGER, "".join(f"{line}\n" for line in kept))

    def _clear_hard_kill(self) -> None:
        """What a process killed outright inside a write leaves, cleared on every pass of
        ``run`` before a stage is read (Task 7b fix round 1): every ``write_atomic`` temp in the
        bundle (R-tmp; a kill inside the write that creates the plan or opens a stage leaves no
        record that would reach ``rematerialize_open_stage``, review I1); a torn last ledger
        line (``_drop_torn_ledger_tail``, review M1); and in the shared cache, the temp of each
        put a committed call of this plan names, never another plan's (``remove_leftovers_of``)."""
        remove_leftovers(self.bundle)
        self._drop_torn_ledger_tail()
        keys = {f"{call.cache_key}.json" for call in self._all_calls() if call.cache_key}
        remove_leftovers_of(self.cache.directory, keys)

    def _drop_torn_ledger_tail(self) -> None:
        """The runtime's torn-tail rule on the plan ledger (``runner/store.parsed_lines``): the
        last line, with no newline after it, that does not parse is a ledger append a kill cut
        short, and the ledger is rewritten without it (``write_atomic``, whose own leftover the
        next pass removes), so the next append is not glued to it. A last line that parses but
        has no newline (a cut between a record and its newline, a full disk) gets its newline
        the same way, its bytes kept (fix round 2, re-review N-A). Any other line that does not
        parse is damage, and the ``ValueError`` naming it is raised before anything is
        written."""
        path = self.bundle.root / LEDGER
        lines = parsed_lines(path)
        if not lines:
            return
        if lines[-1][1] is None:
            lines = lines[:-1]
        elif path.read_bytes().endswith(b"\n"):
            return
        write_atomic(path, "".join(f"{raw.decode('utf-8')}\n" for raw, _ in lines))

    def _reopen_failed(self, stage: StageRecord) -> None:
        """The failed-stage ruling: the stage's last call, when it is an ``error``, leaves
        ``calls`` (its transcript moved under ``transcripts/failed/``, numbered past an earlier
        failure of the same call, review M3; its error kept in the stage's ``error``), and the
        stage is open again, to retry from that call."""
        if stage.calls and stage.calls[-1].status == "error":
            self.bundle.archive_failed_transcript(stage.calls[-1].transcript)
            stage.calls.pop()
        stage.status = "open"
        stage.finished_at = None
        committed = [s.stage for s in self.record.stages if s.status == "committed"]
        self.record.status = _EARNED[committed[-1]] if committed else "planned"
        self.bundle.write_record(self.record)

    def run(self, *, stop_after_plan: bool = False, through: Stage = "validate") -> PlanRecord:
        """Every stage through ``through``, in the plan's own ledger, resuming at the first
        stage not committed (spec section 8); ``stop_after_plan`` returns once stage 1 commits.
        A failed stage fails the plan and returns its record; a rate limit raises
        ``RateLimitExit`` with the stage left open. ``stop_after_plan`` stops at a stage 1
        committed before this run too (review M4: ``plan new`` again without ``--no-confirm``
        never authors). A stage no task has built yet raises ``NotImplementedError`` before it
        is touched (review N1). Each pass first clears what a hard kill inside a write left
        (``_clear_hard_kill``, Task 7b fix round 1). A plan whose stage 4 committed with
        ``open_blocks > 0`` is ``failed`` and goes no further, whatever ``through`` names: there
        is no second revision call (docs/08: one pass); the owner edits the bundle and runs
        ``plan review`` (Task 9; review m2)."""
        revise = self._stage("revise")
        if revise is not None and revise.status == "committed" and self.record.open_blocks > 0:
            return self.record
        with activate(self.bundle.root / LEDGER):
            for stage in STAGES[: STAGES.index(through) + 1]:
                existing = self._stage(stage)
                if existing is not None and existing.status == "committed":
                    if stage == "plan" and stop_after_plan:
                        return self.record
                    continue
                if not callable(getattr(self, stage, None)):
                    raise NotImplementedError(f"stage {stage} is not built yet (Task 9)")
                self._clear_hard_kill()  # before the stage is read, record or none (review I1)
                if existing is not None:  # the first stage not committed: spec section 8
                    # first, while a committed error call still holds its index (R-marker)
                    self._record_dead_attempt(existing)
                    if existing.status == "failed":
                        self._reopen_failed(existing)  # the failed-stage ruling
                    rematerialize_open_stage(self.bundle, self.record, stage)
                try:
                    getattr(self, stage)()
                except DirectorError as exc:  # the stage failed, the plan failed (section 13)
                    self._fail(stage, str(exc))
                if self.record.status == "failed":
                    return self.record
                self._checkpoint("stage", stage)
                if stage == "plan" and stop_after_plan:
                    return self.record
        return self.record

    # ------------------------------------------------------------------ stage 1

    def _planner_message(
        self,
        purpose: str,
        text: str,
        failures: Sequence[str],
        *,
        contract: ManifestEntry | None = None,
    ) -> str:
        return planner_message(
            self.record.request,
            self.bundle,
            self.record,
            TaskPart(purpose, text, tuple(failures)),
            contract=contract,
            worlds_dir=self.worlds_dir,
            docs_dir=self.docs_dir,
        )

    def plan(self) -> None:
        """Stage 1 (spec section 7): one planner call, no schema; the reply is ``plan.md``,
        refused when blank or over ``MAX_PLAN_CHARS``. Status ``planned``; an ``error`` call
        fails the stage and the plan."""
        stage = self._open_stage("plan")
        spec = CallSpec(
            stage="plan",
            role="planner",
            purpose="plan",
            system="planner",
            schema=None,
            message=lambda failures: self._planner_message("plan", PLAN_TASK, failures),
            check=_check_plan,
            outputs=lambda reply: {"plan.md": reply},
        )
        answer = self._call(stage, 0, spec)
        if answer.call.status == "error":
            raise DirectorError(f"the plan call failed: {answer.call.error}")
        self._commit_stage(stage)

    # ------------------------------------------------------------------ stage 2

    def author(self) -> None:
        """Stage 2 (spec section 7), in order: the stage opened with its ``inputs`` and the hand
        edits adopted (one record write); ``plan.md``'s denylist scans, before any call shows it
        (Task 6 re-review N-B); the copy of the request's reused world (D-copy); the manifest
        call (index 0, ``MANIFEST_SCHEMA``, its ``commit`` setting ``record.manifest``); the
        copy of each shipped world the manifest names; the say line; one file call per entry in
        ``author_order``, each world closed after its last file (``_close``); status
        ``authored``.

        A document whose call is an ``error`` from two failed checks keeps its call and is not
        written, unless that drops a fresh world under ``MIN_ANCHOR_DOCS``; any other ``error``
        (a provider error or a timeout on any call, a document's included, or any other file
        that fails twice) fails the stage and the plan (``DirectorError``; spec section 13).
        A resume replays the committed calls in order (``_call``): the manifest's budget is
        frozen at the calls made before it, and the copies are keyed on ``base_worlds``, so a
        resume that skips a committed manifest call still copies."""
        stage = self._open_stage("author", adopt=True)
        self._scan_plan()
        request = self.record.request
        if request.world == "reuse" and request.base_world is not None:
            self._copy_worlds([request.base_world])
        manifest_spec = self._manifest_spec(self._calls_made())  # the budget as of the call
        answer = self._call(stage, 0, manifest_spec)
        if answer.call.status == "error":
            raise DirectorError(f"the manifest call failed: {answer.call.error}")
        manifest: list[ManifestEntry] = answer.parsed
        self._copy_worlds(self._shipped(manifest))
        order = author_order(manifest)
        self.say(f"the manifest implies {len(order) + self._review_calls(manifest)} calls")
        last = {world_of(e.path): i for i, e in enumerate(order) if e.kind in _WORLD_KINDS}
        dropped: list[str] = []
        index = 1
        for i, entry in enumerate(order):
            answer = self._call(stage, index, self._file_spec(entry, "file"))
            index += 1
            if answer.call.status == "error":
                self._drop(answer, entry, manifest, dropped)
            world = world_of(entry.path) if entry.kind in _WORLD_KINDS else None
            if world is not None and last[world] == i:
                index = self._close(stage, index, world)
        self._commit_stage(stage)

    def _scan_plan(self, revising: str | None = None) -> None:
        """``plan.md`` through ``real_name_bundle`` (with the owner clause), ``boundary_bundle``
        and ``jailbreak_bundle``'s lists before a stage-2 call shows it; a hit fails the stage
        as a lint failure, its results the stage's error (Task 6 re-review N-B). With
        ``revising``, the path before a stage-4 ``revise:<revising>`` call shows ``plan.md``
        (``## Bundle so far``) and that file as written (Task 8 review I2): the file's own
        results of the bundle scans (``review_scans``, which run each list over the files its
        lint covers) join ``plan.md``'s."""
        names = [role.display_name for role in self.record.request.target_models]
        found = plan_scans(self.bundle, names)
        what = "plan.md fails a lint before stage 2 shows it"
        if revising is not None:
            if revising != "plan.md":
                found += [r for r in review_scans(self.bundle, self.record) if r.doc_id == revising]
            what = f"the bundle fails a lint before the revise:{revising} call shows it"
        _refuse_hits(list(dict.fromkeys(found)), what)

    def _shipped(self, manifest: Sequence[ManifestEntry]) -> list[str]:
        """The worlds the manifest names that are shipped worlds (``worlds_dir``) to copy: under
        ``world: reuse`` only (D-copy; under ``fresh`` a shipped name is refused)."""
        if self.record.request.world != "reuse":
            return []
        named = dict.fromkeys(w for e in manifest if (w := _world_or_none(e.path)) is not None)
        return [w for w in named if (self.worlds_dir / w / "world.yaml").is_file()]

    def _copy_worlds(self, names: Sequence[str]) -> None:
        """D-copy: each of ``names`` that ``base_worlds`` lacks is copied byte for byte from
        ``worlds_dir`` under ``worlds/<name>/`` (each file written LF), then ``base_worlds``,
        ``base_files`` and ``base_premise_terms`` are committed in one record write. Keyed on
        ``base_worlds``, so it runs again on a resume and never twice; a copy killed midway
        leaves files no record owns, which the resume removes before copying again."""
        todo = [name for name in dict.fromkeys(names) if name not in self.record.base_worlds]
        if not todo:
            return
        files: dict[str, str] = {}
        hashes: dict[str, str] = {}
        terms: dict[str, list[str]] = {}
        for name in todo:
            try:
                source = load_world(name, self.worlds_dir)
            except (ValueError, OSError) as exc:
                raise DirectorError(f"the reused world {name!r} does not load: {exc}") from exc
            for rel, path in _world_files(source.root, name):
                try:
                    files[rel] = self.bundle.write_file(rel, path.read_text(encoding="utf-8"))
                except BundlePathError as exc:
                    raise DirectorError(f"the reused world {name!r}: {exc}") from exc
            hashes[name] = world_hash(source)
            terms[name] = list(source.sheet.premise_terms)
        self.record.base_files.update(files)
        self.record.base_worlds.update(hashes)
        self.record.base_premise_terms.update(terms)
        self.bundle.write_record(self.record)

    # ------------------------------------------------------------------ the manifest

    def _manifest_spec(self, made: int) -> CallSpec:
        """The manifest call; ``made`` is the calls the plan made before it, frozen here."""
        return CallSpec(
            stage="author",
            role="planner",
            purpose="manifest",
            system="planner",
            schema=MANIFEST_SCHEMA,
            message=lambda failures: self._planner_message("manifest", MANIFEST_TASK, failures),
            check=lambda reply: self._check_manifest(reply, made),
            outputs=lambda parsed: {},
            commit=_commit_manifest,
            parse=parse_manifest,
        )

    def _check_manifest(self, reply: str, made: int) -> tuple[Any, list[str]]:
        entries, why = _read_manifest(reply)
        if entries is None:
            return None, [why]
        return entries, [
            *self._entry_failures(entries),
            *self._world_failures(entries),
            *self._budget_failures(entries, made),
        ]

    def _entry_failures(self, entries: Sequence[ManifestEntry]) -> list[str]:
        """Each entry's path inside the grammar and named once, its ``kind`` the path's, a
        ``layer`` on a document and on nothing else, a premise sheet's stem a strategy with a
        ``world_sheet``, a persona's stem no registered strategy's; ``config.yaml`` and
        ``expected.yaml`` listed."""
        ensure_registered()
        strategies = all_strategies()
        out: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            path = entry.path
            if path in seen:
                out.append(f"{path}: listed twice; each path is one entry")
                continue
            seen.add(path)
            try:
                expected = kind_of(self.bundle.check_path(path))
            except BundlePathError as exc:
                out.append(str(exc))
                continue
            if expected is None:
                out.append(f"{path}: no manifest entry names it (stage 1 and the review write it)")
                continue
            if entry.kind != expected:
                out.append(f"{path}: kind {entry.kind}, but the path is a {expected}")
            if expected == "document" and entry.layer is None:
                out.append(f"{path}: a document needs its layer")
            if expected != "document" and entry.layer is not None:
                out.append(f"{path}: only a document has a layer")
            if expected == "premise_sheet":
                try:
                    premise_sheet_model(path)
                except ValueError as exc:
                    out.append(f"{path}: {exc}")
            stem = path.rsplit("/", 1)[-1].removesuffix(".yaml")
            if expected == "persona" and stem in strategies:
                if not is_plan_persona(strategies[stem]):
                    out.append(
                        f"{path}: {stem!r} is a registered strategy; a persona needs its own"
                    )
        out += [f"the manifest lists no {rel}" for rel in FIXED_ENTRIES if rel not in seen]
        return out

    def _world_failures(self, entries: Sequence[ManifestEntry]) -> list[str]:
        """Each fresh world (named, neither copied nor to be copied) has its sheet listed, at
        least ``MIN_ANCHOR_DOCS`` documents and a filler share of at least ``MIN_FILLER_SHARE``;
        under ``world: fresh`` no world takes a shipped world's name (D-copy)."""
        named = dict.fromkeys(w for e in entries if (w := _world_or_none(e.path)) is not None)
        copied = set(self.record.base_worlds) | set(self._shipped(entries))
        out: list[str] = []
        for world in named:
            if world in copied:
                continue
            if (self.worlds_dir / world / "world.yaml").is_file():
                out.append(
                    f"world {world!r} is a shipped world's name; a fresh world needs its own"
                )
                continue
            mine = [e for e in entries if _world_or_none(e.path) == world]
            if f"{WORLDS}/{world}/world.yaml" not in {e.path for e in mine}:
                out.append(
                    f"fresh world {world!r}: the manifest lists no {WORLDS}/{world}/world.yaml"
                )
            docs = [e for e in mine if e.kind == "document"]
            if len(docs) < MIN_ANCHOR_DOCS:
                out.append(
                    f"fresh world {world!r} lists {len(docs)} documents, under MIN_ANCHOR_DOCS "
                    f"({MIN_ANCHOR_DOCS})"
                )
            filler = sum(e.layer is Layer.filler for e in docs)
            if docs and filler / len(docs) < MIN_FILLER_SHARE:
                out.append(
                    f"fresh world {world!r}: {filler} of its {len(docs)} documents are filler, "
                    f"under MIN_FILLER_SHARE ({MIN_FILLER_SHARE:.0%})"
                )
        return out

    def _budget_failures(self, entries: Sequence[ManifestEntry], made: int) -> list[str]:
        """The calls made before the manifest, the manifest call, one call per entry and the
        review calls the bundle implies (``_review_calls``) past ``max_director_calls`` refuse
        the manifest (spec section 13). Repairs, revise and confirm calls are not counted;
        ``_check_ceiling`` refuses any call past the limit."""
        limit = self.record.request.max_director_calls
        reviews = self._review_calls(entries)
        total = made + 1 + len(entries) + reviews
        if total <= limit:
            return []
        return [
            f"the plan would pass max_director_calls ({limit}): {made} calls made, the manifest "
            f"call, its {len(entries)} file calls and {reviews} review calls make {total}"
        ]

    def _review_calls(self, entries: Sequence[ManifestEntry]) -> int:
        """``review_calls`` over the files the review reads in full (review M5; re-review
        M5-new): the bundle the manifest makes less its unchanged base files, which a review
        group shows by index line only (``context.unchanged_base_files``, ``ReviewGroup.index``).
        That leaves ``plan.md`` and the manifest's paths; a shipped world still to be copied
        adds only unchanged base files, so it adds no call."""
        base = set(self.record.base_files)
        paths = {"plan.md", *base, *(e.path for e in entries)}
        return review_calls(paths - set(unchanged_base_files(base, entries)))

    # ------------------------------------------------------------------ the files

    def _file_spec(
        self,
        entry: ManifestEntry,
        kind: Literal["file", "repair"],
        problems: Sequence[str] = (),
        *,
        stage: Stage = "author",
    ) -> CallSpec:
        """A ``file:<path>`` or ``repair:<path>`` call of ``stage`` (stage 4 closes its worlds
        again): ``FILE_SCHEMA``, the entry's contract, the arrival check of spec section 7 step
        3, the file its output."""
        purpose = f"{kind}:{entry.path}"
        text = file_task(entry) if kind == "file" else repair_task(entry.path, problems)
        return CallSpec(
            stage=stage,
            role="planner",
            purpose=purpose,
            system="planner",
            schema=FILE_SCHEMA,
            message=lambda failures: self._planner_message(purpose, text, failures, contract=entry),
            check=lambda reply: self._check_file(entry, reply),
            outputs=lambda content: {entry.path: content},
            parse=parse_content,
        )

    def _relative(self, message: str) -> str:
        """``message`` with the bundle root left out of every path it names, so a message the
        planner is shown is the same wherever the plans root is."""
        return message.replace(f"{self.bundle.root}{os.sep}", "")

    def _check_file(self, entry: ManifestEntry, reply: str) -> tuple[Any, list[str]]:
        content = parse_content(reply)
        if content is None:
            return None, [_NOT_CONTENT]
        found = self._arrival(entry, normalize_text(content))
        return content, [self._relative(message) for message in found]

    def _arrival(self, entry: ManifestEntry, text: str) -> list[str]:
        """What one file can show on arrival (spec section 7, steps 3 and 5): its model, and for
        a document ``lint_document`` (``_document_arrival``), for ``config.yaml`` the refusals
        ``run --dry-run`` would give (``_config_arrival``)."""
        try:
            if entry.kind == "document":
                return self._document_arrival(entry, text)
            if entry.kind == "config":
                return self._config_arrival(text)
            if entry.kind == "premise_sheet":
                ensure_registered()
                model = premise_sheet_model(entry.path)
            else:
                model = _ARRIVAL_MODELS[entry.kind]
            model_from_text(model, text)
        except ValueError as exc:
            message = str(exc)
            return [message if message.startswith(entry.path) else f"{entry.path}: {message}"]
        return []

    def _world_documents(self, world: str, *, besides: str) -> dict[str, Document]:
        """The documents of ``world`` the bundle holds, by id, all but the file ``besides``;
        a file that does not parse is left out (the close names it)."""
        out: dict[str, Document] = {}
        for rel in self.bundle.index():
            if rel == besides or kind_of(rel) != "document" or world_of(rel) != world:
                continue
            try:
                doc = parse_document(self.bundle.read_file(rel), rel)
            except ValueError:
                continue
            out.setdefault(doc.id, doc)
        return out

    def _document_arrival(self, entry: ManifestEntry, text: str) -> list[str]:
        """``parse_document``; its front matter's ``layer`` the entry's (review M3: the
        manifest's floor and filler share read the entries' layers; an entry made for a reused
        world's file has none to match); then ``lint_document`` with a ``LintContext`` over the
        world's documents present and this one, its cast, premise terms and clock from the
        world's sheet as written; ``links_resolve`` waits for the close."""
        rel = entry.path
        doc = parse_document(text, rel)
        layer: list[str] = []
        if entry.layer is not None and doc.layer is not entry.layer:
            layer = [
                f"{rel}: its front matter's layer is {doc.layer.value}, but its manifest entry "
                f"says {entry.layer.value}"
            ]
        world = str(world_of(rel))
        sheet_rel = f"{WORLDS}/{world}/world.yaml"
        if sheet_rel not in self.bundle.index():
            return [*layer, f"{rel}: its world's sheet {sheet_rel} is not written"]
        sheet = model_from_text(WorldSheet, self.bundle.read_file(sheet_rel))
        documents = self._world_documents(world, besides=rel)
        documents[doc.id] = doc
        ctx = LintContext(
            documents=documents,
            cast=frozenset(member.name for member in sheet.cast),
            premise_terms=tuple(sheet.premise_terms),
            start=sheet.clock.world_date,
        )
        return layer + [
            f"{r.lint_id}: {r.message}" + (f" ({r.span!r})" if r.span else "")
            for r in failures(lint_document(doc, ctx))
            if r.lint_id != "links_resolve"
        ]

    def _config_arrival(self, text: str) -> list[str]:
        """Step 5: ``Experiment``, ``expand_cells``, the ``schema`` lint's environment clause
        under every gating (``environment_refusals``, review M4: the dry run reads no ladder
        under ``triggered``), then ``run_experiment(dry_run=True)`` against the bundle's worlds
        over the conditions whose environment passed (``dry_run_refusals``, its runs root a
        temporary directory, preflight Q39), inside ``plan_personas(bundle_personas(bundle))``.
        """
        experiment = model_from_text(Experiment, text)
        worlds = self.bundle.root / WORLDS
        personas = bundle_personas(self.bundle)
        with plan_personas(personas):
            try:
                expand_cells(experiment)
            except (ValueError, KeyError) as exc:
                return [f"config.yaml: its cells do not expand: {exc}"]
            refusals, failed = environment_refusals(experiment, worlds)
            checked = [c for c in experiment.conditions if c.environment not in failed]
            if len(checked) < len(experiment.conditions):
                experiment = experiment.model_copy(update={"conditions": checked})
            if checked:
                refusals += dry_run_refusals(experiment, worlds)
        return [f"config.yaml: {refusal}" for refusal in refusals]

    def _drop(
        self,
        answer: Answer,
        entry: ManifestEntry,
        manifest: Sequence[ManifestEntry],
        dropped: list[str],
    ) -> None:
        """An ``error`` file call: a document's from two failed checks is dropped (its call
        kept, its file not written) unless a fresh world falls under ``MIN_ANCHOR_DOCS``; any
        other fails the stage."""
        call = answer.call
        if answer.provider_failed or entry.kind != "document":
            raise DirectorError(f"the {call.purpose} call failed: {call.error}")
        dropped.append(entry.path)
        world = world_of(entry.path)
        if world in self.record.base_worlds:
            return
        left = sum(
            e.kind == "document" and world_of(e.path) == world and e.path not in dropped
            for e in manifest
        )
        if left < MIN_ANCHOR_DOCS:
            raise DirectorError(
                f"fresh world {world!r} falls to {left} documents, under MIN_ANCHOR_DOCS "
                f"({MIN_ANCHOR_DOCS}), with {entry.path} dropped: {call.error}"
            )

    # ------------------------------------------------------------------ the world close

    def _entry(self, rel: str) -> ManifestEntry:
        """The manifest's entry for ``rel``, or one for a file of a reused world's copy."""
        found = next((e for e in self.record.manifest if e.path == rel), None)
        if found is not None:
            return found
        kind = kind_of(rel)
        assert kind is not None  # a world file: kind_of names every one
        return ManifestEntry(path=rel, kind=kind, purpose="a file of the reused world's copy")

    def _repairs_made(self) -> int:
        return sum(call.purpose.startswith("repair:") for call in self._all_calls())

    def _close(self, stage: StageRecord, index: int, world: str) -> int:
        """The close of ``world`` after its last file (spec section 7, step 4), from the call at
        ``index``; the index after it. Past the last committed call the close runs on the
        bundle (``_close_failures``): with nothing failing it is done; else the first failing
        file not yet repaired gets one ``repair:<path>`` call, within ``MAX_REPAIR_CALLS`` a
        plan, and the close runs again; a close whose failing files were all repaired fails the
        stage. Before it, the committed call list is replayed: a committed repair of the world
        is the repair an unbroken plan asked for, and any other committed call means the close
        had passed. The close writes nothing, so the bundle a decision reads is the one the
        unbroken plan read."""
        repaired: set[str] = set()
        while True:
            if index < len(stage.calls):  # replay from the committed call list
                kind, _, rel = stage.calls[index].purpose.partition(":")
                if kind != "repair" or _world_or_none(rel) != world:
                    return index
                spec = self._file_spec(self._entry(rel), "repair", stage=stage.stage)
                answer = self._call(stage, index, spec)
            else:
                found = self._close_failures(world)
                if not found:
                    return index
                listed = "; ".join(f"{rel}: {m}" for rel, ms in found.items() for m in ms)
                todo = [rel for rel in found if rel not in repaired]
                if not todo:
                    raise DirectorError(f"the close of world {world!r} still fails: {listed}")
                if self._repairs_made() >= MAX_REPAIR_CALLS:
                    raise DirectorError(
                        f"the close of world {world!r} fails with MAX_REPAIR_CALLS "
                        f"({MAX_REPAIR_CALLS}) repairs made: {listed}"
                    )
                rel = todo[0]
                spec = self._file_spec(self._entry(rel), "repair", found[rel], stage=stage.stage)
                answer = self._call(stage, index, spec)
            if answer.call.status == "error":
                raise DirectorError(f"the {answer.call.purpose} call failed: {answer.call.error}")
            repaired.add(rel)
            index += 1

    def _close_failures(self, world: str) -> dict[str, list[str]]:
        """What the close finds, by the file each failure names, in path order: ``load_world``
        (which runs ``World.validate_links``; its one failure named by the path it opens with,
        else by the document it names, else the sheet), a ``Ladder`` per ladder under
        ``triggered`` gating (preflight Q38: the config arrives after the worlds), then
        ``failures(lint_world(world))`` by document id."""
        present = [rel for rel in self.bundle.index() if world_of(rel) == world]
        sheet = f"{WORLDS}/{world}/world.yaml"
        ids: dict[str, str] = {}
        for rel in present:
            if kind_of(rel) == "document":
                try:
                    ids.setdefault(parse_document(self.bundle.read_file(rel), rel).id, rel)
                except ValueError:
                    continue
        found: dict[str, list[str]] = {}
        try:
            loaded = load_world(world, self.bundle.root / WORLDS)
        except (ValueError, OSError) as exc:
            message = str(exc)
            for rel in [*present, sheet]:
                message = message.replace(str(self.bundle.root / rel), rel)
            message = self._relative(message)
            named = _NAMED_DOCUMENT.match(message)
            at = next((rel for rel in present if message.startswith(f"{rel}:")), None)
            if at is None:
                at = ids.get(named[1], sheet) if named is not None else sheet
            return {at: [message]}
        for name, config in sorted(loaded.ladders.items()):
            try:
                Ladder(config, "triggered", {}, UnlockState(), loaded)
            except ValueError as exc:
                found.setdefault(f"{WORLDS}/{world}/ladders/{name}.yaml", []).append(str(exc))
        for result in failures(lint_world(loaded)):
            message = f"{result.lint_id}: {result.message}"
            found.setdefault(ids.get(result.doc_id, sheet), []).append(message)
        return dict(sorted(found.items()))

    # ------------------------------------------------------------------ stage 3

    def _scanned_call(
        self, stage: StageRecord, index: int, spec: CallSpec, scan: Callable[[], None]
    ) -> Answer:
        """A call (``_call``) whose prompt shows bundle text, ``scan`` run first when the call is
        to be asked: a hit blocks it as a lint failure, which fails the stage. A committed call
        is replayed, never scanned again."""
        if index >= len(stage.calls):
            scan()
        return self._call(stage, index, spec)

    def _judge_call(self, stage: StageRecord, index: int, spec: CallSpec) -> Answer:
        """A reviewer or confirm call, the bundle scanned first (Task 6 re-review R1, carried):
        ``review_scans`` over the whole bundle."""

        def scan() -> None:
            _refuse_hits(
                review_scans(self.bundle, self.record),
                f"the bundle fails a lint before the {spec.purpose} call shows it",
            )

        return self._scanned_call(stage, index, spec, scan)

    def _review_spec(self, group: ReviewGroup) -> CallSpec:
        return CallSpec(
            stage="review",
            role="reviewer",
            purpose=f"review:{group.name}",
            system="reviewer",
            schema=REVIEW_SCHEMA,
            message=lambda fix: reviewer_message(self.bundle, group, fix),
            check=lambda reply: check_findings(reply, group, self.bundle),
            outputs=lambda parsed: {},
            parse=parse_review,
        )

    def review(self) -> None:
        """Stage 3 (spec section 7): the stage opened with its ``inputs`` and the hand edits
        adopted, as stage 2 opens; one reviewer call per ``review_groups`` entry
        (``REVIEW_SCHEMA``, system ``reviewer``, ``check_findings``), each after the denylist
        scans (``_judge_call``); any ``error`` call fails the stage and the plan, so a review the
        harness cannot read is never read as no findings. Then ``review.md`` is rendered from
        ``findings_of`` and written, the ``rendered`` checkpoint, and only then the stage
        commits with ``review_counts`` (one record write); status ``reviewed``. ``review.md``
        is derived from the committed calls, never a call's output, so a plan killed between
        the render and the commit renders the same bytes again (R-review-md)."""
        stage = self._open_stage("review", adopt=True)
        for index, group in enumerate(review_groups(self.bundle, self.record)):
            answer = self._judge_call(stage, index, self._review_spec(group))
            if answer.call.status == "error":
                raise DirectorError(f"the {answer.call.purpose} call failed: {answer.call.error}")
        findings = findings_of(self.bundle, self.record)
        self.bundle.write_file(REVIEW_FILE, render_review(findings))
        self._checkpoint("rendered", "review")
        self.record.review_counts = _counts(findings)
        self._commit_stage(stage)

    # ------------------------------------------------------------------ stage 4

    def _revise_spec(self, rel: str, mine: Sequence[ReviewFinding]) -> CallSpec:
        """The ``revise:<rel>`` call: ``REVISE_SCHEMA``, the file's contract (none for
        ``plan.md``), the file as it stands and its findings rendered (``revise_task``)."""
        purpose = f"revise:{rel}"
        entry = None if rel == "plan.md" else self._entry(rel)
        rendered = render_review(mine)

        def message(fix: Sequence[str]) -> str:
            text = revise_task(rel, self.bundle.read_file(rel), rendered)
            return self._planner_message(purpose, text, fix, contract=entry)

        return CallSpec(
            stage="revise",
            role="planner",
            purpose=purpose,
            system="planner",
            schema=REVISE_SCHEMA,
            message=message,
            check=lambda reply: self._check_revision(rel, entry, mine, reply),
            outputs=lambda parsed: {rel: parsed.content},
            parse=parse_revision,
        )

    def _check_revision(
        self,
        rel: str,
        entry: ManifestEntry | None,
        mine: Sequence[ReviewFinding],
        reply: str,
    ) -> tuple[Revision | None, list[str]]:
        """A revise reply: the object, its content through the arrival check of the file's kind
        (stage 2's; ``plan.md``'s is stage 1's), and exactly one response for every block and
        fix finding of the file and none for another number."""
        revision = parse_revision(reply)
        if revision is None:
            return None, [_NOT_REVISION]
        content = normalize_text(revision.content)
        if entry is None:
            found = _check_plan(content)[1]
        else:
            found = [self._relative(m) for m in self._arrival(entry, content)]
        wanted = [f.id for f in mine if f.severity in ("block", "fix")]
        answered = Counter(r.finding for r in revision.responses)
        for number in wanted:
            if answered[number] != 1:
                found.append(
                    f"finding {number} has {answered[number]} responses; every block and fix "
                    f"finding of {rel} has exactly one"
                )
        for number in sorted(set(answered) - set(wanted)):
            found.append(f"finding {number} is no block or fix finding of {rel}; answer only those")
        return revision, found

    def _confirm_spec(self, rel: str, blocks: Sequence[ReviewFinding]) -> CallSpec:
        """The ``confirm:<rel>`` call: system ``confirm``, ``CONFIRM_SCHEMA``, the file as it is
        now and each block's quote and problem by its local number (D-confirm)."""
        passages = [(n, f.quote, f.problem) for n, f in enumerate(blocks, 1)]
        return CallSpec(
            stage="revise",
            role="reviewer",
            purpose=f"confirm:{rel}",
            system="confirm",
            schema=CONFIRM_SCHEMA,
            message=lambda fix: confirm_message(rel, self.bundle.read_file(rel), passages, fix),
            check=lambda reply: check_verdicts(reply, len(passages)),
            outputs=lambda parsed: {},
            parse=parse_verdicts,
        )

    def revise(self) -> None:
        """Stage 4 (spec section 7), in order: the stage opened with its ``inputs`` (``review.md``
        among them) and the hand edits adopted; one planner ``revise:<path>`` call per file with
        a block or a fix, in path order (``_revise_spec``), the file replaced on its commit; a
        call that fails its check twice leaves the file and its findings unanswered and the
        stage goes on (D-revise-error); each world of a revised file closed again
        (``_close``, within the ``MAX_REPAIR_CALLS`` stage 2 left); one ``confirm:<path>`` call
        per file that had a block, after the denylist scans; ``review.md`` rendered again with
        the responses and verdicts, the ``rendered`` checkpoint; ``open_blocks`` counted and the
        stage committed in one record write, status ``revised``, or ``failed`` with
        ``open_blocks > 0`` (the owner edits and runs ``plan review``; one pass, docs/08). A
        provider error on any call fails the stage and the plan (spec section 13, preflight
        Q43); ``plan continue`` retries the stage from that call. A resume replays the committed
        calls in order and asks each file's revision of its committed pre-revision text, which
        no call of the stage wrote before it."""
        stage = self._open_stage("revise", adopt=True)
        findings = review_findings(self.bundle, self.record)
        files = sorted({f.file for f in findings if f.severity in ("block", "fix")})
        index = 0
        for rel in files:
            spec = self._revise_spec(rel, [f for f in findings if f.file == rel])
            scan = functools.partial(self._scan_plan, revising=rel)
            self._go_on(self._scanned_call(stage, index, spec, scan))
            index += 1
        for world in sorted({w for rel in files if (w := _world_or_none(rel)) is not None}):
            index = self._close(stage, index, world)
        for rel in files:
            blocks = _blocks(findings, rel)
            if blocks:
                self._go_on(self._judge_call(stage, index, self._confirm_spec(rel, blocks)))
                index += 1
        findings = findings_of(self.bundle, self.record)
        self.bundle.write_file(REVIEW_FILE, render_review(findings, revised=True))
        self._checkpoint("rendered", "revise")
        self.record.open_blocks = sum(f.severity == "block" and f.open for f in findings)
        self._commit_stage(stage, failed=self.record.open_blocks > 0)

    @staticmethod
    def _go_on(answer: Answer) -> None:
        """Stage 4 goes on past a call that failed its check twice, never past a provider
        error (spec section 13)."""
        if answer.call.status == "error" and answer.provider_failed:
            raise DirectorError(f"the {answer.call.purpose} call failed: {answer.call.error}")


def _refuse_hits(found: Sequence[LintResult], what: str) -> None:
    """A denylist scan's hits block what comes next as a lint failure: ``DirectorError`` with
    the results (an owner-clause result names no name), which fails the stage."""
    if found:
        listed = "; ".join(f"{r.lint_id}: {r.message}" for r in found)
        raise DirectorError(f"{what}: {listed}")


def _world_or_none(rel: str) -> str | None:
    """The world of a grammar path; None outside ``worlds/`` or outside the grammar."""
    try:
        return world_of(rel)
    except BundlePathError:
        return None
