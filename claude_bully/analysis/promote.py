"""Promote a finished run from the gitignored runs/ directory into the committed results/ tree.

Everything needed to recompute the analysis travels: run.json, cell records, JSONL turns,
conversation metadata, the judge cache, the analysis outputs and the ledger. Provider state
(sessions) does not. Transcripts are scanned against the jailbreak denylist first; publishing
them is the point of results/, so nothing denylisted may slip through.

Real names (non-negotiable 2): a hit in bully-side or task text, a tool result, a generated
document or a responder reply blocks; a hit in the target's own text is reported by the CLI and
kept, with the targets' ``display_name`` and any ``exempt`` name spared. README excerpts black
the rest out (Phase 9).
"""

import re
import shutil
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from claude_bully.enums import Speaker
from claude_bully.paths import DATA_DIR
from claude_bully.providers.ledger import LEDGER_FILE
from claude_bully.records import chat_text
from claude_bully.runner.store import RunStore

DENYLIST_PATH = DATA_DIR / "jailbreak_denylist.txt"
REAL_NAMES_PATH: Final = DATA_DIR / "denylists" / "real_names.txt"
COPIED_FILES: Final[tuple[str, ...]] = ("run.json", LEDGER_FILE)
COPIED_DIRS: Final[tuple[str, ...]] = ("judge_cache", "analysis")
CELL_FILE_GLOBS = ("cell.json", "rep*.turns.jsonl", "rep*.conversation.json")


@dataclass
class RealNameReport:
    """Real-name hits in a run (Phase 7 spec section 10): ``blocking`` (harness-side or
    world-side text: bully and task lines, tool results, generated documents, responder
    replies) and ``reported`` (the target's own text, kept and redacted in README excerpts)."""

    blocking: list[str]
    reported: list[str]


def load_denylist_patterns(path: Path = DENYLIST_PATH) -> list[re.Pattern[str]]:
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    return [re.compile(ln, re.IGNORECASE) for ln in lines]


def load_real_name_patterns(path: Path = REAL_NAMES_PATH) -> list[re.Pattern[str]]:
    return load_denylist_patterns(path)


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


def display_names(store: RunStore) -> set[str]:
    """Every target's ``display_name`` in the run's experiment: the one real name the target may
    say of itself (docs/00 G11)."""
    targets = store.read_run().experiment.get("targets", [])
    return {str(t.get("display_name", "")) for t in targets if t.get("display_name")}


def _spared(text: str, names: Collection[str]) -> str:
    for name in names:
        if name.strip():
            text = re.sub(rf"(?<!\w){re.escape(name.strip())}(?!\w)", "", text, flags=re.IGNORECASE)
    return text


def _hits(text: str, patterns: list[re.Pattern[str]], names: Collection[str]) -> list[str]:
    spared = _spared(text, names)
    return [p.pattern for p in patterns if p.search(spared)]


def scan_real_names(
    store: RunStore, patterns: list[re.Pattern[str]], exempt: Collection[str]
) -> RealNameReport:
    report = RealNameReport([], [])
    for cell_id in store.list_cells():
        for rep in store.list_reps(cell_id):
            where = f"{cell_id} rep{rep}"
            for turn in store.read_turns(cell_id, rep):
                for hit in _hits(chat_text(turn), patterns, exempt):
                    line = f"{where} turn {turn.index} ({turn.speaker.value}): {hit}"
                    (report.reported if turn.speaker is Speaker.target else report.blocking).append(
                        line
                    )
            for call in store.read_tool_calls(cell_id, rep):
                report.blocking += [
                    f"{where} tool result {call.id}: {h}"
                    for h in _hits(call.result_text, patterns, exempt)
                ]
            for doc in store.read_generated(cell_id, rep):
                report.blocking += [
                    f"{where} generated {doc.doc_id}: {h}"
                    for h in _hits(f"{doc.title}\n{doc.body}", patterns, exempt)
                ]
            for answered in store.read_authority_calls(cell_id, rep):
                report.blocking += [
                    f"{where} responder {answered.id}: {h}"
                    for h in _hits(answered.response, patterns, exempt)
                ]
    return report


def promote(
    run_id: str,
    runs_root: Path,
    results_root: Path,
    *,
    force: bool = False,
    exempt: Collection[str] = (),
) -> Path:
    store = RunStore(runs_root, run_id)
    if not store.exists():
        raise FileNotFoundError(f"no run named {run_id!r} under {runs_root}")
    dest = results_root / run_id
    if dest.exists() and not force:
        raise FileExistsError(f"{dest} already exists; pass force=True to replace it")
    scan_run(store, load_denylist_patterns())
    names = display_names(store) | set(exempt)
    report = scan_real_names(store, load_real_name_patterns(), names)
    if report.blocking:
        raise ValueError(
            "harness-side text names a real name; refusing to promote: "
            + "; ".join(report.blocking[:5])
        )
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
