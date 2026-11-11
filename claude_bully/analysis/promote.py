"""Promote a finished run from the gitignored runs/ directory into the committed results/ tree.

Everything needed to recompute the analysis travels: run.json, cell records, JSONL turns,
conversation metadata, the judge cache, the analysis outputs and the ledger. Provider state
(sessions) does not. Transcripts are scanned against the jailbreak denylist first; publishing
them is the point of results/, so nothing denylisted may slip through.

Real names (non-negotiable 2): a hit in bully-side or task text, a tool result, a generated
document or a responder reply blocks; a hit in the target's own text is reported by the CLI and
kept. The targets' ``display_name`` is spared in every text, an ``exempt`` name in the target's
own text only, and only where the match is that name itself. README excerpts black the rest out
(Phase 9).

Email addresses (Task 12, R4): the ``claude -p`` CLI attaches the account's email address to every
conversation (rung 0 finding 1), so every stream above is also scanned for ``EMAIL``. An address
on a reserved domain (RFC 2606: ``.example``, ``.test``, ``.invalid``, ``.localhost``,
``example.com``/``.net``/``.org``) is spared, as the shipped worlds use them; any other blocks in
every stream, the target's own text included, and neither a display name nor ``exempt`` spares
it: an address is personal data, not a name the target may say of itself. A blocking line names
the stream and ``email address (domain redacted)``, never the address.
"""

import re
import shutil
from collections import Counter
from collections.abc import Callable, Collection
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
EMAIL: Final = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
# RFC 2606: the top-level names and the second-level domains reserved for examples and tests
_RESERVED_EMAIL_DOMAINS: Final = (
    "example",
    "test",
    "invalid",
    "localhost",
    "example.com",
    "example.net",
    "example.org",
)
# what a blocking line says in place of the address it found
EMAIL_HIT: Final = "email address (domain redacted)"


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


def _hits(text: str, patterns: list[re.Pattern[str]], names: Collection[str]) -> list[str]:
    """The patterns with a match in ``text`` that is not itself one of ``names`` (compared
    case-insensitively). The text is scanned whole, so a versioned name whose bare family is
    exempt (the family word followed by a version) is still a hit."""
    spared = {n.strip().casefold() for n in names if n.strip()}
    return [
        p.pattern
        for p in patterns
        if any(m.group(0).strip().casefold() not in spared for m in p.finditer(text))
    ]


def _reserved(domain: str) -> bool:
    """Whether ``domain`` is, or is under, a name RFC 2606 reserves."""
    folded = domain.casefold()
    return any(folded == d or folded.endswith(f".{d}") for d in _RESERVED_EMAIL_DOMAINS)


def email_hits(text: str) -> list[str]:
    """One ``EMAIL_HIT`` per address in ``text`` off a reserved domain; nothing spares one."""
    return [EMAIL_HIT for m in EMAIL.finditer(text) if not _reserved(m.group(1))]


def scan_real_names(
    store: RunStore,
    patterns: list[re.Pattern[str]],
    exempt: Collection[str],
    *,
    target_exempt: Collection[str] = (),
) -> RealNameReport:
    """Every hit of ``patterns`` in the run. ``exempt`` (the targets' display names) is spared in
    every text; ``target_exempt`` (``promote --exempt``, the maker's name, say) in the target's
    own turns only, so a harness-side or world-side text naming it still blocks (spec section
    10). Every email address off a reserved domain blocks, in every text (``email_hits``)."""
    report = RealNameReport([], [])
    in_target = [*exempt, *target_exempt]
    for cell_id in store.list_cells():
        for rep in store.list_reps(cell_id):
            where = f"{cell_id} rep{rep}"
            for turn in store.read_turns(cell_id, rep):
                is_target = turn.speaker is Speaker.target
                text = chat_text(turn)
                line = f"{where} turn {turn.index} ({turn.speaker.value})"
                for hit in _hits(text, patterns, in_target if is_target else exempt):
                    (report.reported if is_target else report.blocking).append(f"{line}: {hit}")
                report.blocking += [f"{line}: {hit}" for hit in email_hits(text)]
            for call in store.read_tool_calls(cell_id, rep):
                report.blocking += [
                    f"{where} tool result {call.id}: {h}"
                    for h in [
                        *_hits(call.result_text, patterns, exempt),
                        *email_hits(call.result_text),
                    ]
                ]
            for doc in store.read_generated(cell_id, rep):
                text = f"{doc.title}\n{doc.body}"
                report.blocking += [
                    f"{where} generated {doc.doc_id}: {h}"
                    for h in [*_hits(text, patterns, exempt), *email_hits(text)]
                ]
            for answered in store.read_authority_calls(cell_id, rep):
                report.blocking += [
                    f"{where} responder {answered.id}: {h}"
                    for h in [
                        *_hits(answered.response, patterns, exempt),
                        *email_hits(answered.response),
                    ]
                ]
    return report


# what a blocking line names after its ``<cell> rep<k>`` prefix: a turn (with its speaker) or
# one of the world-side streams
_BLOCKING_SOURCE: Final = re.compile(
    r"^\S+ rep\d+ (?:turn \d+ \((\w+)\)|(tool result|generated|responder))"
)
_STREAM_LABELS: Final = {
    "tool result": "tool results",
    "generated": "generated documents",
    "responder": "responder replies",
}


def _blocking_summary(lines: list[str]) -> str:
    """``N hits (2 in bully turns, 1 in tool results)``: the total and where they are."""
    counts: Counter[str] = Counter()
    for line in lines:
        m = _BLOCKING_SOURCE.match(line)
        assert m is not None, line  # every line is built by scan_real_names
        counts[f"{m.group(1)} turns" if m.group(1) else _STREAM_LABELS[m.group(2)]] += 1
    where = ", ".join(f"{n} in {source}" for source, n in sorted(counts.items()))
    return f"{len(lines)} hit{'s' if len(lines) != 1 else ''} ({where})"


def promote(
    run_id: str,
    runs_root: Path,
    results_root: Path,
    *,
    force: bool = False,
    exempt: Collection[str] = (),
    on_reported: Callable[[str], None] | None = None,
) -> Path:
    """Copy the run into ``results_root``. ``exempt`` names are spared in the target's own text
    only (the targets' display names everywhere); a blocking hit raises ``ValueError`` before
    anything is copied. ``on_reported`` is told each reported target-side hit after the copy."""
    store = RunStore(runs_root, run_id)
    if not store.exists():
        raise FileNotFoundError(f"no run named {run_id!r} under {runs_root}")
    dest = results_root / run_id
    if dest.exists() and not force:
        raise FileExistsError(f"{dest} already exists; pass force=True to replace it")
    scan_run(store, load_denylist_patterns())
    report = scan_real_names(
        store, load_real_name_patterns(), display_names(store), target_exempt=exempt
    )
    if report.blocking:
        raise ValueError(
            "harness-side text names a real name, or a text holds an email address; refusing "
            "to promote: "
            f"{_blocking_summary(report.blocking)}; first: " + "; ".join(report.blocking[:5])
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
    if on_reported is not None:
        for hit in report.reported:
            on_reported(hit)
    return dest
