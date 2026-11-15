"""A plan bundle on disk (Phase 5, spec section 5): ``plans/<slug>/``, its path grammar, its
writes and its hash.

The Director writes only the paths of ``_GRAMMAR``, checked before anything touches the disk
(non-negotiable 1: a model-supplied string never selects where the harness writes). Every file
is written LF without a BOM, and the sha256 a call records is of the text as written
(D-write_file). The harness's own files (``plan.json``, ``.attempt.json``, the transcripts) are
outside the grammar and have their own writers here. ``materialize`` and
``rematerialize_open_stage`` write committed files back from the transcripts, the second being
spec section 8's resume rule for the open stage."""

import hashlib
import json
import os
import re
import weakref
from collections.abc import Collection, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict

from claude_bully.atomic import replace, write_atomic
from claude_bully.environments.world import hash_tree, load_yaml_model
from claude_bully.planner.records import (
    STAGES,
    DirectorAttempt,
    DirectorCall,
    ManifestKind,
    PlanRecord,
    Stage,
    StageRecord,
    read_plan_record,
)
from claude_bully.planner.request import WINDOWS_DEVICE_STEMS
from claude_bully.strategies import base as strategy_base
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.premises.phased import make_phased_premise
from claude_bully.strategies.sheets import PersonaSheet

PLAN_FILE: Final = "plan.json"
PERSONAS_DIR: Final = "personas"
ATTEMPT_FILE: Final = ".attempt.json"
TRANSCRIPTS: Final = "transcripts"
LEDGER: Final = "ledger.jsonl"
DRYRUN_DIR: Final = "dryrun"
DRYRUN_FILE: Final = "dryrun.jsonl"
STATE_DIR: Final = "state"
CACHE_DIR: Final = "_cache"
# what bundle_hash leaves out: the harness's own records, the dry run and the provider state
HASH_EXCLUDES: Final[frozenset[str]] = frozenset(
    {PLAN_FILE, ATTEMPT_FILE, LEDGER, DRYRUN_DIR, DRYRUN_FILE, STATE_DIR, TRANSCRIPTS}
)
FIXED_FILES: Final = ("plan.md", "config.yaml", "expected.yaml", "review.md")

NAME: Final = r"[a-z0-9][a-z0-9_-]{0,63}"
_GRAMMAR: Final = re.compile(
    rf"(?:plan\.md|config\.yaml|expected\.yaml|review\.md"
    rf"|worlds/(?P<world>{NAME})/(?:world\.yaml|corpus/(?P<doc>{NAME})\.md"
    rf"|ladders/(?P<ladder>{NAME})\.yaml|premises/(?P<premise>{NAME})\.yaml)"
    rf"|personas/(?P<persona>{NAME})\.yaml)"
)
# WINDOWS_DEVICE_STEMS is imported from claude_bully.planner.request (review I7)

_STAGE_NAMES: Final = "|".join(STAGES)
# the harness-built transcript paths: <stage>-<role>-<index>.json, at the top, under an earlier
# review round (D-rounds) or under failed/ (D-failed-stage), where a later failure of the same
# call is numbered on, <stage>-<role>-<index>-<n>.json from 2 (Task 7a fix round 1, review M3)
_TRANSCRIPT_STEM: Final = rf"(?:{_STAGE_NAMES})-(?:planner|reviewer)-(?:0|[1-9][0-9]*)"
_TRANSCRIPT: Final = re.compile(
    rf"{TRANSCRIPTS}/(?:(?:round-[1-9][0-9]*/)?{_TRANSCRIPT_STEM}"
    rf"|failed/{_TRANSCRIPT_STEM}(?:-(?:[2-9]|[1-9][0-9]+))?)\.json"
)
FAILED: Final = f"{TRANSCRIPTS}/failed"
_FIXED_KINDS: Final[dict[str, ManifestKind | None]] = {
    "plan.md": None,
    "config.yaml": "config",
    "expected.yaml": "expected",
    "review.md": None,
}
# atomic.write_atomic's temp file beside its target, ".<name>.<mkstemp's 8 characters>.tmp",
# which a process killed outright leaves behind (R-tmp); no grammar or harness file has the shape
_LEFTOVER: Final = re.compile(r"\..+\.[a-z0-9_]{8}\.tmp")
# the files no resume removes: the owner's plan and the rendered review (spec section 8)
_ALWAYS_OWNED: Final = frozenset({"plan.md", "review.md"})


class BundlePathError(ValueError):
    """A path the bundle refuses: outside the grammar, outside the root, or through a link."""


def normalize_text(text: str) -> str:
    """``text`` as every bundle file is written: a leading BOM dropped, CRLF and lone CR to LF."""
    return text.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_link(path: Path) -> bool:
    return path.is_symlink() or os.path.isjunction(path)


def _tree(root: Path, exclude: Collection[str] = ()) -> tuple[list[Path], list[Path]]:
    """Every file under ``root``, never read through a link, and every link met on the way (a
    symlink or a junction, to a file or a folder), which is not entered (Task 1 review M2:
    ``Path.rglob`` follows a junction on Python 3.12). A top-level entry named in ``exclude`` is
    left out with everything under it."""
    files: list[Path] = []
    links: list[Path] = []
    folders = [root]
    while folders:
        folder = folders.pop()
        with os.scandir(folder) as entries:
            for entry in entries:
                path = Path(entry.path)
                if folder == root and entry.name in exclude:
                    continue
                if _is_link(path):
                    links.append(path)
                elif entry.is_dir(follow_symlinks=False):
                    folders.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.append(path)
    return files, links


def _match(rel: str) -> re.Match[str] | None:
    """The grammar's match of ``rel``, or None when it is outside the grammar or names a
    Windows device as a <name> or <stem>."""
    match = _GRAMMAR.fullmatch(rel)
    if match is None:
        return None
    if any(group in WINDOWS_DEVICE_STEMS for group in match.groupdict().values() if group):
        return None
    return match


def _grammar(rel: str) -> re.Match[str]:
    match = _match(rel)
    if match is None:
        raise BundlePathError(f"{rel!r}: not a path the bundle's grammar allows")
    return match


def kind_of(rel: str) -> ManifestKind | None:
    """The manifest kind of a grammar path; None for ``plan.md`` and ``review.md``, which no
    manifest entry names. Raises ``BundlePathError`` for a path outside the grammar."""
    match = _grammar(rel)
    if rel in _FIXED_KINDS:
        return _FIXED_KINDS[rel]
    if match["doc"]:
        return "document"
    if match["ladder"]:
        return "ladder"
    if match["premise"]:
        return "premise_sheet"
    if match["world"]:
        return "world_sheet"
    return "persona"


def world_of(rel: str) -> str | None:
    """The world a grammar path belongs to; None outside ``worlds/``. Raises
    ``BundlePathError`` for a path outside the grammar."""
    return _grammar(rel)["world"]


class TranscriptAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    reply: str


class Transcript(BaseModel):
    """``transcripts/<stage>-<role>-<index>.json``: one entry per attempt; no timestamp, no
    reasoning text."""

    model_config = ConfigDict(extra="forbid")

    system_sha256: str | None
    model: str
    attempts: list[TranscriptAttempt]


def committed_outputs(call: DirectorCall, transcript: Transcript) -> dict[str, str]:
    """The text of each file ``call`` committed, read from its transcript's last reply and
    normalized as written: ``plan`` gives ``plan.md`` the reply; ``file:``, ``repair:`` and
    ``revise:`` give their path ``json.loads(reply)["content"]``. A call that committed no file
    gives none. Raises ``ValueError`` when the purpose does not give the paths ``call.outputs``
    names."""
    if not call.outputs:
        return {}
    if not transcript.attempts:
        raise ValueError(f"{call.transcript}: no attempt to read the committed files from")
    reply = transcript.attempts[-1].reply
    kind, _, path = call.purpose.partition(":")
    if call.purpose == "plan":
        files = {"plan.md": reply}
    elif kind in ("file", "repair", "revise") and path:
        files = {path: json.loads(reply)["content"]}
    else:
        files = {}
    if set(files) != set(call.outputs):
        raise ValueError(
            f"{call.transcript}: purpose {call.purpose!r} gives {sorted(files)}, "
            f"the call records {sorted(call.outputs)}"
        )
    return {rel: normalize_text(text) for rel, text in files.items()}


@dataclass(frozen=True)
class Bundle:
    """``plans/<slug>/``. Every path it is handed is bundle-relative and posix."""

    root: Path

    @classmethod
    def create(cls, plans_root: Path, slug: str) -> Self:
        """The bundle ``plans_root/slug``, its directory made when missing; writes no file."""
        root = plans_root / slug
        root.mkdir(parents=True, exist_ok=True)
        return cls(root)

    @property
    def slug(self) -> str:
        return self.root.name

    def _confined(self, rel: str) -> Path:
        """``root / rel``, refused when an existing component between the root and the file is
        a link, or when it resolves outside the root."""
        root = self.root.resolve()
        current = self.root
        for part in rel.split("/"):
            current = current / part
            if current.is_symlink() or os.path.isjunction(current):
                raise BundlePathError(f"{rel!r}: the path runs through a link ({current})")
        if not current.resolve().is_relative_to(root):
            raise BundlePathError(f"{rel!r}: resolves outside the bundle root {root}")
        return current

    def check_path(self, rel: str) -> str:
        """``rel`` when the Director may write it; raises ``BundlePathError`` otherwise."""
        _grammar(rel)
        self._confined(rel)
        return rel

    def write_file(self, rel: str, text: str) -> str:
        """Write a grammar path, normalized (``normalize_text``), atomically; return the sha256
        of the text as written."""
        self.check_path(rel)
        normalized = normalize_text(text)
        write_atomic(self.root / rel, normalized)
        return _sha256(normalized)

    def read_file(self, rel: str) -> str:
        """A grammar path's text as it is on disk (no newline translation)."""
        self.check_path(rel)
        return (self.root / rel).read_bytes().decode("utf-8")

    def remove_file(self, rel: str) -> None:
        """Remove a grammar path; a missing file is no error."""
        self.check_path(rel)
        (self.root / rel).unlink(missing_ok=True)

    def index(self) -> dict[str, str]:
        """Every grammar path present, to the sha256 of its bytes, sorted by path. A file reached
        through a link, or that is one, is left out, as every write and read refuses it (Task 1
        review M2); the harness's own folders (``HASH_EXCLUDES``) hold no grammar path and are
        not walked."""
        files, _ = _tree(self.root, HASH_EXCLUDES)
        found = {path.relative_to(self.root).as_posix(): path for path in files}
        return {
            rel: hashlib.sha256(found[rel].read_bytes()).hexdigest()
            for rel in sorted(found)
            if _match(rel) is not None
        }

    def read_record(self) -> PlanRecord:
        return read_plan_record(self.root / PLAN_FILE)

    def write_record(self, record: PlanRecord) -> None:
        write_atomic(self.root / PLAN_FILE, record.model_dump_json(indent=1) + "\n")

    def transcript_rel(self, stage: Stage, role: str, index: int) -> str:
        return f"{TRANSCRIPTS}/{stage}-{role}-{index}.json"

    def _transcript_path(self, rel: str) -> Path:
        if _TRANSCRIPT.fullmatch(rel) is None:
            raise BundlePathError(f"{rel!r}: not a transcript path")
        return self._confined(rel)

    def write_transcript(self, rel: str, transcript: Transcript) -> None:
        write_atomic(self._transcript_path(rel), transcript.model_dump_json(indent=1) + "\n")

    def read_transcript(self, rel: str) -> Transcript:
        return Transcript.model_validate_json(self._transcript_path(rel).read_bytes())

    def archive_failed_transcript(self, rel: str) -> str | None:
        """Move a failed call's transcript under ``transcripts/failed/`` (one rename), to
        ``<name>.json`` or, when an earlier failure of the same call holds that, to the first
        free ``<name>-<n>.json`` from 2, so no failed transcript is written over (review M3).
        Returns the path it moved to; None when ``rel`` is already gone, a move made before a
        kill, so a reopen redone after one moves nothing."""
        source = self._transcript_path(rel)
        if not source.exists():
            return None
        stem = rel.rsplit("/", 1)[-1].removesuffix(".json")
        to = f"{FAILED}/{stem}.json"
        n = 2
        while self._transcript_path(to).exists():
            to = f"{FAILED}/{stem}-{n}.json"
            n += 1
        target = self._transcript_path(to)
        target.parent.mkdir(parents=True, exist_ok=True)
        replace(source, target)
        return to

    def write_attempt(self, attempt: DirectorAttempt) -> None:
        write_atomic(self.root / ATTEMPT_FILE, attempt.model_dump_json() + "\n")

    def read_attempt(self) -> DirectorAttempt | None:
        path = self.root / ATTEMPT_FILE
        if not path.is_file():
            return None
        return DirectorAttempt.model_validate_json(path.read_bytes())

    def clear_attempt(self) -> None:
        (self.root / ATTEMPT_FILE).unlink(missing_ok=True)

    def write_manual(
        self, record: PlanRecord, rel: str, text: str, *, stage: Stage = "author"
    ) -> DirectorCall:
        """Commit a hand-authored file like a call: a ``manual`` ``DirectorCall`` appended to
        the last stage when it is ``stage`` and open (else to a new open one), its transcript
        one attempt whose reply is ``{"content": text}``; the transcript, then the record, then
        the file (spec section 8's order). ``record`` is updated in place.

        A stage name opened again (``stage`` committed earlier) numbers its calls on past every
        call recorded under that name, so its transcripts never overwrite an earlier call's
        (Task 1 review M1); a transcript path some call of the record already names is refused
        with ``BundlePathError`` before any write."""
        self.check_path(rel)
        last = record.stages[-1] if record.stages else None
        index = sum(len(s.calls) for s in record.stages if s.stage == stage)
        transcript_rel = self.transcript_rel(stage, "planner", index)
        if transcript_rel in named_transcripts(record):
            raise BundlePathError(f"{transcript_rel}: a committed call of the record names it")
        if last is None or last.stage != stage or last.status != "open":
            last = StageRecord(stage=stage, started_at=datetime.now(UTC), status="open")
            record.stages.append(last)
        self.write_transcript(
            transcript_rel,
            Transcript(
                system_sha256=None,
                model="manual",
                attempts=[TranscriptAttempt(message="", reply=json.dumps({"content": text}))],
            ),
        )
        call = DirectorCall(
            role="planner",
            index=index,
            purpose=f"file:{rel}",
            outputs={rel: _sha256(normalize_text(text))},
            cache_key="",
            status="manual",
            model="manual",
            transcript=transcript_rel,
            attempts=1,
        )
        last.calls.append(call)
        self.write_record(record)
        self.write_file(rel, text)
        return call


def bundle_hash(root: Path) -> str:
    """``hash_tree`` over the bundle less ``HASH_EXCLUDES``: what a run reads and what the
    reviewer read. A bundle that holds a link there (a symlink or a junction) is refused with
    ``BundlePathError``, since the hash would cover files outside it (Task 1 review M2);
    ``hash_tree`` itself is unchanged, so every world hash stays as it was."""
    _, links = _tree(root, HASH_EXCLUDES)
    if links:
        raise BundlePathError(f"{root}: the bundle holds a link ({links[0]})")
    return hash_tree(root, exclude=HASH_EXCLUDES)


def _stage_records(record: PlanRecord) -> list[StageRecord]:
    """Every stage record: the current ones, then each earlier review round's."""
    return [*record.stages, *(stage for round_ in record.rounds for stage in round_)]


def named_transcripts(record: PlanRecord) -> set[str]:
    """Every transcript path a call of ``record`` names, in any stage or earlier round."""
    return {call.transcript for stage in _stage_records(record) for call in stage.calls}


def _committed_texts(bundle: Bundle, calls: Iterable[DirectorCall]) -> dict[str, str]:
    """The text each path holds after ``calls`` in order (a later call's file wins), each read
    from its call's transcript (``committed_outputs``) and refused with ``ValueError`` when it
    does not hash to the sha the call recorded (Task 1 review N5: a transcript another call
    overwrote is caught here, never written)."""
    texts: dict[str, str] = {}
    for call in calls:
        if not call.outputs:
            continue
        for rel, text in committed_outputs(call, bundle.read_transcript(call.transcript)).items():
            if _sha256(text) != call.outputs[rel]:
                raise ValueError(
                    f"{call.transcript}: the {call.purpose} reply gives {rel} a text whose "
                    "sha256 is not the one the call recorded"
                )
            texts[rel] = text
    return texts


def _write_changed(bundle: Bundle, texts: Mapping[str, str]) -> list[str]:
    """Write each path whose bytes differ from its text (or that is missing); the paths
    written, in order."""
    rewritten = []
    for rel, text in texts.items():
        bundle.check_path(rel)
        path = bundle.root / rel
        if not path.is_file() or path.read_bytes() != text.encode("utf-8"):
            bundle.write_file(rel, text)
            rewritten.append(rel)
    return rewritten


def materialize(
    bundle: Bundle, record: PlanRecord, *, stages: Collection[Stage] | None = None
) -> list[str]:
    """Write every committed call's files from the transcripts, in commit order: ``plan``,
    ``author``, each round of ``rounds`` in order, then the current ``review`` and ``revise``
    stages (D-rounds), for the stages named or all; a path several calls wrote holds the last
    one's text. Returns the paths whose bytes it rewrote; a path already holding its text is
    left alone."""
    wanted = set(STAGES if stages is None else stages)
    ordered = [s for name in ("plan", "author") for s in record.stages if s.stage == name]
    ordered += [s for round_ in record.rounds for s in round_]
    ordered += [s for name in ("review", "revise") for s in record.stages if s.stage == name]
    calls = [call for s in ordered if s.stage in wanted for call in s.calls]
    return _write_changed(bundle, _committed_texts(bundle, calls))


def remove_leftovers(bundle: Bundle) -> list[str]:
    """Remove every ``write_atomic`` leftover in the bundle (R-tmp), never through a link; the
    bundle-relative paths removed."""
    files, _ = _tree(bundle.root)
    removed = []
    for path in sorted(files):
        if _LEFTOVER.fullmatch(path.name):
            path.unlink(missing_ok=True)
            removed.append(path.relative_to(bundle.root).as_posix())
    return removed


def rematerialize_open_stage(bundle: Bundle, record: PlanRecord, stage: Stage) -> list[str]:
    """Spec section 8's resume rule for ``stage``, the first stage not committed: every file a
    committed call of it wrote whose bytes no longer hash to the call's record is rewritten from
    the call's transcript (a later call of the stage winning on a path it rewrote), and every
    grammar file owned by neither ``base_files``, a committed call of any stage or round,
    ``plan.md`` nor ``review.md`` is removed. Every ``write_atomic`` leftover in the bundle is
    removed first (R-tmp). A committed stage is the owner's to edit: only its leftovers go.
    Returns the paths it rewrote."""
    remove_leftovers(bundle)
    current = next((s for s in reversed(record.stages) if s.stage == stage), None)
    if current is None or current.status == "committed":
        return []
    rewritten = _write_changed(bundle, _committed_texts(bundle, current.calls))
    owned = set(record.base_files) | _ALWAYS_OWNED
    owned |= {rel for s in _stage_records(record) for call in s.calls for rel in call.outputs}
    for rel in bundle.index():
        if rel not in owned:
            bundle.remove_file(rel)
    return rewritten


def bundle_personas(bundle: Bundle) -> dict[str, PersonaSheet]:
    """Every ``personas/*.yaml`` of the bundle, loaded as a ``PersonaSheet``, by sheet name.
    Raises ``ValueError`` naming the file and the field for one that does not load."""
    return {
        sheet.name: sheet
        for sheet in (
            load_yaml_model(PersonaSheet, path)
            for path in sorted((bundle.root / PERSONAS_DIR).glob("*.yaml"))
        )
    }


# every class a plan_personas block registered: a plan's persona, never a strategy of the
# package (the schema lint's name check reads it, review M5)
_PLAN_CLASSES: Final[weakref.WeakSet[type[strategy_base.Strategy]]] = weakref.WeakSet()


def is_plan_persona(cls: type[strategy_base.Strategy]) -> bool:
    """True for a class a ``plan_personas`` block registered."""
    return cls in _PLAN_CLASSES


@contextmanager
def plan_personas(sheets: Mapping[str, PersonaSheet]) -> Iterator[None]:
    """The bundle's personas registered for the block (D-plan_personas, R-registry).

    ``ensure_registered()`` runs first, so the block never sees a registry that loads its
    strategies later. Each sheet is registered with ``make_phased_premise``; on exit, exceptions
    included, each name the block registered is removed, or given back the class it replaced.
    Nothing else is touched: a strategy something else registered inside the block stays, and the
    registry is never restored from a snapshot (a snapshot taken before the first load would
    empty it for good). Blocks nest, each undoing only its own registrations."""
    ensure_registered()
    replaced: dict[str, type[strategy_base.Strategy] | None] = {}
    try:
        for sheet in sheets.values():
            replaced.setdefault(sheet.name, strategy_base._REGISTRY.get(sheet.name))
            _PLAN_CLASSES.add(make_phased_premise(sheet))
        yield
    finally:
        for name, previous in replaced.items():
            if previous is None:
                strategy_base._REGISTRY.pop(name, None)
            else:
                strategy_base._REGISTRY[name] = previous
