"""On-disk layout of a run: run.json, per-cell cell.json, per-rep JSONL turns and metadata.

Environment cells add up to four JSONL streams per rep (docs/00-RECONCILED.md section H) and one
corpus snapshot:

- ``rep{k}.tools.jsonl``      ``ToolCall``
- ``rep{k}.authority.jsonl``  ``AuthorityCall``, keyed by the id of the ``ToolCall`` it answered;
  written only by a cell whose environment enables an authority tier
- ``rep{k}.triggers.jsonl``   ``TriggerStreamRecord`` (``TriggerEvent``, ``RungUnlock``,
  ``Discovery``, ``GeneratorFire`` and the later kinds), discriminated by ``type``
- ``rep{k}.generated.jsonl``  ``GeneratedDoc``
- ``rep{k}.world.json``       ``{world_hash, docs: {id: body}}`` plus the world record
  (``environments.world.world_record``: ``sheet``, ``documents`` metadata, ``ladders``), written
  once per rep; analysis rebuilds the ``World`` from it (``world_from_snapshot``)

Every loader refuses a record from an older schema version (there is no migration: no real run
was recorded before schema version 3).

The tool-call and authority streams are written while a turn is produced, before the turn is. A
resumed rep drops the lines of every attempt that produced no turn (``drop_dead_attempts``) before
it goes on, so the streams hold what an unbroken run's do. The world generator (Phase 3) writes to
the trigger and generated streams after a target turn is written and before it is marked watched:
a resumed rep drops its lines of a turn never written, and every generated document and
``generator`` unlock that no committed ``GeneratorFire`` lists (``drop_uncommitted_generation``),
so a fire that died before its fire line is redone whole. The watch's records of a turn never
written (``quirk``, ``chain``, ``contradiction``; Phase 4) go the same way, in every environment
session. Of the lines that do not parse either drops only a torn final line; any other is an
error naming the file and the line.
"""

import json
import os
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, TypeAdapter

from claude_bully.enums import SCHEMA_VERSION
from claude_bully.environments.config import GENERATOR_RUNG
from claude_bully.environments.mcp_server import torn_line
from claude_bully.records import CellRecord, Conversation, RunRecord, Turn
from claude_bully.records_env import AuthorityCall, GeneratedDoc, ToolCall, TriggerStreamRecord

RUN_FILE = "run.json"
CELL_FILE = "cell.json"
TOOLS_STREAM = "tools"
AUTHORITY_STREAM = "authority"
TRIGGERS_STREAM = "triggers"
GENERATED_STREAM = "generated"

_TRIGGER_RECORD: TypeAdapter[TriggerStreamRecord] = TypeAdapter(TriggerStreamRecord)
# the trigger-stream record types the world generator writes per target turn (Phase 3)
GENERATION_TYPES: Final = frozenset({"harvest", "generator_fire"})
# the trigger-stream record types the watch writes after a target turn (Phase 4): the quirk
# answer, the chain verdict and the contradiction pair, each of its own turn
WATCH_TYPES: Final = frozenset({"quirk", "chain", "contradiction"})
COMMITTED_STATUSES: Final = frozenset({"written", "cached"})


class DamagedRecordError(ValueError):
    """A harness record on disk that does not read back: a line of a JSONL stream that is not
    a torn last line (``parsed_lines``), or a ``plan.json`` that is not UTF-8, not JSON, of an
    older plan schema or not a ``PlanRecord`` (``planner/records.read_plan_record``). The message
    names the file and the line, or the field. A ``ValueError``, so every caller that catches
    one still catches it; the ``plan`` commands catch this type alone and print it without a
    traceback, so a ``ValueError`` of a defect keeps its own (Phase 5 Task 9 fix round 1)."""


def _checked(raw: Any, source: Path) -> Any:
    """``raw`` unchanged, unless it is a record from an older schema version."""
    if isinstance(raw, dict):
        version = raw.get("schema_version")
        if isinstance(version, int) and version < SCHEMA_VERSION:
            raise ValueError(
                f"{source}: schema version {version}; re-run with this version "
                f"(this code reads schema version {SCHEMA_VERSION} only)"
            )
    return raw


def _load_json(path: Path) -> Any:
    return _checked(json.loads(path.read_text(encoding="utf-8")), path)


def _load_lines(path: Path) -> list[Any]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [_checked(json.loads(line), path) for line in fh if line.strip()]


def drop_dead_attempts(path: Path, produced: Collection[int], *, closed_torn: bool = False) -> int:
    """Rewrite the per-call JSONL file ``path`` without the lines of attempts that died, and
    return how many lines it dropped.

    A line belongs to the attempt at its ``turn``. That attempt died when no target turn with
    that index was written: it was killed before its turn was, or paused by a rate limit whose
    marker took the index. So a line is kept only when its ``turn`` is in ``produced``, the
    indices of the written target turns.

    The one line that may not parse is the writer's torn final line: the last line of the file,
    with no trailing newline, cut by the kill that ended the attempt. It is dropped with the
    attempt. Any other line that does not parse (in the middle, or ended by a newline) is damage,
    not a dead attempt, and dropping it would lose a record without a word: it raises a
    ``ValueError`` naming the file and the line, and the file is left as it was. With
    ``closed_torn`` (the MCP server's logs, whose ``_append_line`` closes off a killed writer's
    fragment before its next record, P27), a record cut short anywhere in the file is torn too
    (``mcp_server.torn_line``) and is dropped the same way (Phase 4 Task 14 fix round 1, review
    M3); the store's own streams are never closed off, so there it is still damage.

    Kept lines are written back byte for byte, through a temp file and a rename; a file with
    nothing to drop is not touched."""
    parsed = parsed_lines(path, closed_torn=closed_torn)
    return _keep_only(path, parsed, [_turn_in(record, produced) for _, record in parsed])


def _turn_in(record: Any, produced: Collection[int]) -> bool:
    turn = record.get("turn") if isinstance(record, dict) else None
    return isinstance(turn, int) and turn in produced


def parsed_lines(path: Path, *, closed_torn: bool = False) -> list[tuple[bytes, Any]]:
    """Each non-blank line of a JSONL file with its value; the torn last line (no newline after
    it) has the value None, and with ``closed_torn`` so does a record cut short that a later
    line closed off (``mcp_server.torn_line``). Any other line that does not parse raises
    ``DamagedRecordError`` naming the file and the line, as in ``drop_dead_attempts``. The
    runtime's torn-tail rule, which the Director's resume also applies to the plan ledger
    (Phase 5 Task 7b fix round 1)."""
    if not path.exists():
        return []
    lines = path.read_bytes().split(b"\n")
    out: list[tuple[bytes, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            out.append((line, json.loads(line)))
        except ValueError as exc:  # also bytes that are not UTF-8
            # the writer died mid-line: the last line, or one the server closed off
            if number == len(lines) or (closed_torn and torn_line(line)):
                out.append((line, None))
                continue
            raise DamagedRecordError(
                f"{path}: line {number} is not valid JSON ({exc}); it is not a torn last line, "
                "so it is not dropped"
            ) from exc
    return out


def _keep_only(path: Path, parsed: list[tuple[bytes, Any]], keep: list[bool]) -> int:
    """Rewrite ``path`` with the lines of ``parsed`` that ``keep`` marks, byte for byte, through
    a temp file and a rename; untouched when every line is kept. Returns the lines dropped."""
    dropped = keep.count(False)
    if dropped:
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(
            b"".join(line + b"\n" for (line, _), kept in zip(parsed, keep, strict=True) if kept)
        )
        os.replace(tmp, path)
    return dropped


def drop_uncommitted_generation(
    triggers: Path, generated: Path, produced: Collection[int]
) -> dict[str, int]:
    """Rewrite a rep's trigger and generated streams without the world generator's lines of a
    dead attempt (Phase 3): every ``harvest`` and ``generator_fire`` line, every watch record
    (``quirk``, ``chain``, ``contradiction``; Phase 4) and every ``generator`` unlock of a turn no
    written target turn has, and every generated document and ``generator``
    unlock whose id no committed ``GeneratorFire`` (status written or cached, of a written turn)
    lists. A fire's ``GeneratorFire`` is written last, so a fire that died before it is dropped
    whole and redone. Other records are kept as ``drop_dead_attempts`` keeps them; a torn last
    line is dropped. Returns the lines dropped per file name, non-zero only."""
    trigger_lines = parsed_lines(triggers)
    committed = {
        doc_id
        for _, rec in trigger_lines
        if isinstance(rec, dict)
        and rec.get("type") == "generator_fire"
        and rec.get("status") in COMMITTED_STATUSES
        and rec.get("turn") in produced
        for doc_id in rec.get("doc_ids", [])
    }

    def keep_record(rec: Any) -> bool:
        if not isinstance(rec, dict):
            return False
        written = _turn_in(rec, produced)
        if rec.get("type") in GENERATION_TYPES | WATCH_TYPES:
            return written
        if rec.get("type") == "unlock" and rec.get("rung") == GENERATOR_RUNG:
            return written and all(d in committed for d in rec.get("docs_unlocked", []))
        return True

    generated_lines = parsed_lines(generated)
    dropped = {
        triggers.name: _keep_only(
            triggers, trigger_lines, [keep_record(r) for _, r in trigger_lines]
        ),
        generated.name: _keep_only(
            generated,
            generated_lines,
            [_turn_in(r, produced) and r.get("doc_id") in committed for _, r in generated_lines],
        ),
    }
    return {name: count for name, count in dropped.items() if count}


class RunStore:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = root
        self.run_id = run_id
        self.run_dir = root / run_id
        self.state_dir = self.run_dir / "state"

    # -- run ----------------------------------------------------------------------------

    def exists(self) -> bool:
        return (self.run_dir / RUN_FILE).exists()

    def write_run(self, record: RunRecord) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / RUN_FILE).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def read_run(self) -> RunRecord:
        return RunRecord.model_validate(_load_json(self.run_dir / RUN_FILE))

    # -- cells --------------------------------------------------------------------------

    def cell_dir(self, cell_id: str) -> Path:
        return self.run_dir / cell_id

    def write_cell(self, record: CellRecord) -> None:
        d = self.cell_dir(record.cell_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / CELL_FILE).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def read_cell(self, cell_id: str) -> CellRecord:
        return CellRecord.model_validate(_load_json(self.cell_dir(cell_id) / CELL_FILE))

    def has_cell(self, cell_id: str) -> bool:
        return (self.cell_dir(cell_id) / CELL_FILE).exists()

    def list_cells(self) -> list[str]:
        if not self.run_dir.exists():
            return []
        return sorted(
            p.name for p in self.run_dir.iterdir() if p.is_dir() and (p / CELL_FILE).exists()
        )

    # -- turns and conversations ---------------------------------------------------------

    def _turns_path(self, cell_id: str, rep: int) -> Path:
        return self.cell_dir(cell_id) / f"rep{rep}.turns.jsonl"

    def _conversation_path(self, cell_id: str, rep: int) -> Path:
        return self.cell_dir(cell_id) / f"rep{rep}.conversation.json"

    def _append(self, path: Path, record: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")

    def append_turn(self, cell_id: str, rep: int, turn: Turn) -> None:
        self._append(self._turns_path(cell_id, rep), turn)

    def read_turns(self, cell_id: str, rep: int) -> list[Turn]:
        return [Turn.model_validate(raw) for raw in _load_lines(self._turns_path(cell_id, rep))]

    def write_conversation(self, cell_id: str, rep: int, conv: Conversation) -> None:
        path = self._conversation_path(cell_id, rep)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = conv.model_dump(mode="json", exclude={"turns"})
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def has_conversation(self, cell_id: str, rep: int) -> bool:
        return self._conversation_path(cell_id, rep).exists()

    def read_conversation(self, cell_id: str, rep: int) -> Conversation:
        payload = _load_json(self._conversation_path(cell_id, rep))
        payload["turns"] = [t.model_dump(mode="json") for t in self.read_turns(cell_id, rep)]
        return Conversation.model_validate(payload)

    def list_reps(self, cell_id: str) -> list[int]:
        d = self.cell_dir(cell_id)
        if not d.exists():
            return []
        reps = []
        for p in d.glob("rep*.conversation.json"):
            reps.append(int(p.name[len("rep") : -len(".conversation.json")]))
        return sorted(reps)

    # -- environment streams -------------------------------------------------------------

    def _stream_path(self, cell_id: str, rep: int, stream: str) -> Path:
        return self.cell_dir(cell_id) / f"rep{rep}.{stream}.jsonl"

    def append_tool_call(self, cell_id: str, rep: int, call: ToolCall) -> None:
        self._append(self._stream_path(cell_id, rep, TOOLS_STREAM), call)

    def read_tool_calls(self, cell_id: str, rep: int) -> list[ToolCall]:
        path = self._stream_path(cell_id, rep, TOOLS_STREAM)
        return [ToolCall.model_validate(raw) for raw in _load_lines(path)]

    def append_authority_call(self, cell_id: str, rep: int, call: AuthorityCall) -> None:
        self._append(self._stream_path(cell_id, rep, AUTHORITY_STREAM), call)

    def read_authority_calls(self, cell_id: str, rep: int) -> list[AuthorityCall]:
        path = self._stream_path(cell_id, rep, AUTHORITY_STREAM)
        return [AuthorityCall.model_validate(raw) for raw in _load_lines(path)]

    def call_streams(self, cell_id: str, rep: int) -> list[Path]:
        """The rep's per-call streams, whose lines are tied to the turn being produced: the tool
        calls and the authority calls (``drop_dead_attempts``)."""
        return [self._stream_path(cell_id, rep, s) for s in (TOOLS_STREAM, AUTHORITY_STREAM)]

    def generation_streams(self, cell_id: str, rep: int) -> tuple[Path, Path]:
        """The rep's trigger and generated streams, which the world generator writes to
        (``drop_uncommitted_generation``)."""
        return (
            self._stream_path(cell_id, rep, TRIGGERS_STREAM),
            self._stream_path(cell_id, rep, GENERATED_STREAM),
        )

    def drop_contradictions(self, cell_id: str, rep: int, turn: int) -> int:
        """Rewrite the rep's trigger stream without the ``contradiction`` lines of ``turn``: a
        turn watched again on resume whose pass did not find the dead attempt's pairs again (a
        judge that failed then and answers now), so the rewatch's pairs stand alone (P54; the
        final review's M1). Every other line is kept byte for byte. Returns the lines dropped."""
        path = self._stream_path(cell_id, rep, TRIGGERS_STREAM)
        lines = parsed_lines(path)
        keep = [
            not (isinstance(r, dict) and r.get("type") == "contradiction" and r.get("turn") == turn)
            for _, r in lines
        ]
        return _keep_only(path, lines, keep)

    def append_trigger_record(self, cell_id: str, rep: int, record: TriggerStreamRecord) -> None:
        self._append(self._stream_path(cell_id, rep, TRIGGERS_STREAM), record)

    def read_trigger_records(self, cell_id: str, rep: int) -> list[TriggerStreamRecord]:
        path = self._stream_path(cell_id, rep, TRIGGERS_STREAM)
        return [_TRIGGER_RECORD.validate_python(raw) for raw in _load_lines(path)]

    def append_generated(self, cell_id: str, rep: int, doc: GeneratedDoc) -> None:
        self._append(self._stream_path(cell_id, rep, GENERATED_STREAM), doc)

    def read_generated(self, cell_id: str, rep: int) -> list[GeneratedDoc]:
        path = self._stream_path(cell_id, rep, GENERATED_STREAM)
        return [GeneratedDoc.model_validate(raw) for raw in _load_lines(path)]

    def _world_path(self, cell_id: str, rep: int) -> Path:
        return self.cell_dir(cell_id) / f"rep{rep}.world.json"

    def write_world_snapshot(
        self,
        cell_id: str,
        rep: int,
        world_hash: str,
        docs: dict[str, str],
        *,
        record: Mapping[str, Any] | None = None,
    ) -> bool:
        """Write ``rep{k}.world.json`` unless the rep already has one. True when written.

        ``record`` (``world_record``: the sheet, document metadata and ladders) is added beside
        ``world_hash`` and ``docs``; neither of those two keys changes."""
        path = self._world_path(cell_id, rep)
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"world_hash": world_hash, "docs": dict(sorted(docs.items()))}
        for key, value in (record or {}).items():
            if key not in payload:
                payload[key] = value
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        return True

    def read_world_snapshot(self, cell_id: str, rep: int) -> tuple[str, dict[str, str]] | None:
        path = self._world_path(cell_id, rep)
        if not path.exists():
            return None
        payload = _load_json(path)
        return str(payload["world_hash"]), {str(k): str(v) for k, v in payload["docs"].items()}

    def read_world_record(self, cell_id: str, rep: int) -> dict[str, Any] | None:
        """The whole ``rep{k}.world.json`` payload, or None when the rep has no snapshot."""
        path = self._world_path(cell_id, rep)
        if not path.exists():
            return None
        payload = _load_json(path)
        return dict(payload) if isinstance(payload, dict) else None
