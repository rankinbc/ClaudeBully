"""Promote a finished run from the gitignored runs/ directory into the committed results/ tree.

Everything needed to recompute the analysis travels: run.json, cell records, JSONL turns,
conversation metadata, the judge cache, the analysis outputs and the ledger. Provider state
(sessions) does not. Transcripts are scanned against the jailbreak denylist first; publishing
them is the point of results/, so nothing denylisted may slip through.
"""

import re
import shutil
from pathlib import Path

from claude_bully.paths import DATA_DIR
from claude_bully.providers.ledger import LEDGER_FILE
from claude_bully.runner.store import RunStore

DENYLIST_PATH = DATA_DIR / "jailbreak_denylist.txt"
COPIED_FILES = ("run.json", LEDGER_FILE)
COPIED_DIRS = ("judge_cache", "analysis")
CELL_FILE_GLOBS = ("cell.json", "rep*.turns.jsonl", "rep*.conversation.json")


def load_denylist_patterns(path: Path = DENYLIST_PATH) -> list[re.Pattern[str]]:
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    return [re.compile(ln, re.IGNORECASE) for ln in lines]


def scan_run(store: RunStore, patterns: list[re.Pattern[str]]) -> None:
    for cell_id in store.list_cells():
        for rep in store.list_reps(cell_id):
            for turn in store.read_turns(cell_id, rep):
                for pattern in patterns:
                    if pattern.search(turn.text):
                        raise ValueError(
                            f"{cell_id} rep{rep} turn {turn.index} matches denylist pattern "
                            f"{pattern.pattern!r}; refusing to promote"
                        )


def promote(run_id: str, runs_root: Path, results_root: Path, *, force: bool = False) -> Path:
    store = RunStore(runs_root, run_id)
    if not store.exists():
        raise FileNotFoundError(f"no run named {run_id!r} under {runs_root}")
    dest = results_root / run_id
    if dest.exists() and not force:
        raise FileExistsError(f"{dest} already exists; pass force=True to replace it")
    scan_run(store, load_denylist_patterns())
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in COPIED_FILES:
        source = store.run_dir / name
        if source.exists():
            shutil.copy2(source, dest / name)
    for cell_id in store.list_cells():
        src = store.cell_dir(cell_id)
        (dest / cell_id).mkdir()
        for pattern in CELL_FILE_GLOBS:
            for f in src.glob(pattern):
                shutil.copy2(f, dest / cell_id / f.name)
    for name in COPIED_DIRS:
        src_dir = store.run_dir / name
        if src_dir.is_dir():
            shutil.copytree(src_dir, dest / name)
    return dest
