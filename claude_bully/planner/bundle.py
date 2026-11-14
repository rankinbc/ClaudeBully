"""A plan bundle on disk (Phase 5, spec section 5): ``plans/<slug>/``, its path grammar, its
writes and its hash.

The Director writes only the paths of ``_GRAMMAR``, checked before anything touches the disk
(non-negotiable 1: a model-supplied string never selects where the harness writes). Every file
is written LF without a BOM, and the sha256 a call records is of the text as written
(D-write_file). The harness's own files (``plan.json``, ``.attempt.json``, the transcripts) are
outside the grammar and have their own writers here."""

import hashlib
import json
import os
import re
import weakref
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict

from claude_bully.atomic import write_atomic
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
# review round (D-rounds) or under failed/ (D-failed-stage)
_TRANSCRIPT: Final = re.compile(
    rf"{TRANSCRIPTS}/(?:(?:round-[1-9][0-9]*|failed)/)?"
    rf"(?:{_STAGE_NAMES})-(?:planner|reviewer)-(?:0|[1-9][0-9]*)\.json"
)
_FIXED_KINDS: Final[dict[str, ManifestKind | None]] = {
    "plan.md": None,
    "config.yaml": "config",
    "expected.yaml": "expected",
    "review.md": None,
}


class BundlePathError(ValueError):
    """A path the bundle refuses: outside the grammar, outside the root, or through a link."""


def normalize_text(text: str) -> str:
    """``text`` as every bundle file is written: a leading BOM dropped, CRLF and lone CR to LF."""
    return text.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        """Every grammar path present, to the sha256 of its bytes, sorted by path."""
        found = {
            path.relative_to(self.root).as_posix(): path
            for path in self.root.rglob("*")
            if path.is_file()
        }
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
        the file (spec section 8's order). ``record`` is updated in place."""
        self.check_path(rel)
        last = record.stages[-1] if record.stages else None
        if last is None or last.stage != stage or last.status != "open":
            last = StageRecord(stage=stage, started_at=datetime.now(UTC), status="open")
            record.stages.append(last)
        index = len(last.calls)
        transcript_rel = self.transcript_rel(stage, "planner", index)
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
    reviewer read."""
    return hash_tree(root, exclude=HASH_EXCLUDES)


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
