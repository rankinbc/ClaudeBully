"""On-disk layout of a run: run.json, per-cell cell.json, per-rep JSONL turns and metadata."""

import json
from pathlib import Path

from claude_bully.records import CellRecord, Conversation, RunRecord, Turn

RUN_FILE = "run.json"
CELL_FILE = "cell.json"


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
        return RunRecord.model_validate_json((self.run_dir / RUN_FILE).read_text(encoding="utf-8"))

    # -- cells --------------------------------------------------------------------------

    def cell_dir(self, cell_id: str) -> Path:
        return self.run_dir / cell_id

    def write_cell(self, record: CellRecord) -> None:
        d = self.cell_dir(record.cell_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / CELL_FILE).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def read_cell(self, cell_id: str) -> CellRecord:
        return CellRecord.model_validate_json(
            (self.cell_dir(cell_id) / CELL_FILE).read_text(encoding="utf-8")
        )

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

    def append_turn(self, cell_id: str, rep: int, turn: Turn) -> None:
        path = self._turns_path(cell_id, rep)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(turn.model_dump_json() + "\n")

    def read_turns(self, cell_id: str, rep: int) -> list[Turn]:
        path = self._turns_path(cell_id, rep)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            return [Turn.model_validate_json(line) for line in fh if line.strip()]

    def write_conversation(self, cell_id: str, rep: int, conv: Conversation) -> None:
        path = self._conversation_path(cell_id, rep)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = conv.model_dump(mode="json", exclude={"turns"})
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def has_conversation(self, cell_id: str, rep: int) -> bool:
        return self._conversation_path(cell_id, rep).exists()

    def read_conversation(self, cell_id: str, rep: int) -> Conversation:
        payload = json.loads(self._conversation_path(cell_id, rep).read_text(encoding="utf-8"))
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
