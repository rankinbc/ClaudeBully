"""On-disk layout of a run: run.json, per-cell cell.json, per-rep JSONL turns and metadata.

Environment cells add up to four JSONL streams per rep (docs/00-RECONCILED.md section H) and one
corpus snapshot:

- ``rep{k}.tools.jsonl``      ``ToolCall``
- ``rep{k}.authority.jsonl``  ``AuthorityCall``, keyed by the id of the ``ToolCall`` it answered;
  written only by a cell whose environment enables an authority tier
- ``rep{k}.triggers.jsonl``   ``TriggerStreamRecord`` (``TriggerEvent``, ``RungUnlock``,
  ``Discovery`` and the later kinds), discriminated by ``type``
- ``rep{k}.generated.jsonl``  ``GeneratedDoc``
- ``rep{k}.world.json``       ``{world_hash, docs: {id: body}}`` plus the world record
  (``environments.world.world_record``: ``sheet``, ``documents`` metadata, ``ladders``), written
  once per rep; analysis rebuilds the ``World`` from it (``world_from_snapshot``)

Every loader refuses a record from an older schema version (there is no migration: no real run
was recorded before schema version 2).

The tool-call and authority streams are written while a turn is produced, before the turn is. A
resumed rep drops the lines of every attempt that produced no turn (``drop_dead_attempts``) before
it goes on, so the streams hold what an unbroken run's do. Of the lines that do not parse it
drops only a torn final line; any other is an error naming the file and the line.
"""

import json
import os
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from claude_bully.enums import SCHEMA_VERSION
from claude_bully.records import CellRecord, Conversation, RunRecord, Turn
from claude_bully.records_env import AuthorityCall, GeneratedDoc, ToolCall, TriggerStreamRecord

RUN_FILE = "run.json"
CELL_FILE = "cell.json"
TOOLS_STREAM = "tools"
AUTHORITY_STREAM = "authority"
TRIGGERS_STREAM = "triggers"
GENERATED_STREAM = "generated"

_TRIGGER_RECORD: TypeAdapter[TriggerStreamRecord] = TypeAdapter(TriggerStreamRecord)


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


def drop_dead_attempts(path: Path, produced: Collection[int]) -> int:
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
    ``ValueError`` naming the file and the line, and the file is left as it was.

    Kept lines are written back byte for byte, through a temp file and a rename; a file with
    nothing to drop is not touched."""
    if not path.exists():
        return 0
    kept: list[bytes] = []
    dropped = 0
    lines = path.read_bytes().split(b"\n")
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:  # also bytes that are not UTF-8
            if number == len(lines):  # nothing ends it: the writer died mid-line
                dropped += 1
                continue
            raise ValueError(
                f"{path}: line {number} is not valid JSON ({exc}); it is not a torn last line, "
                "so it is not dropped"
            ) from exc
        turn = record.get("turn") if isinstance(record, dict) else None
        if isinstance(turn, int) and turn in produced:
            kept.append(line)
        else:
            dropped += 1
    if dropped:
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(b"".join(line + b"\n" for line in kept))
        os.replace(tmp, path)
    return dropped


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
