"""The plan's expected events against the observed ones (Phase 5 Task 11, spec section 11).

A run made from a plan bundle carries the bundle's ``expected.yaml`` in ``RunRecord.plan``
(``PlanStamp.expected``), so this needs no ``plans/`` directory. Everything here reads what
``load_run`` took from the run directory and makes no model call. A run with no stamp, or a
stamp that holds no expected events, writes nothing.

Per cell, per rung, per expected event, the observed share is read like this:

- the reps are the cell's complete reps, less those flagged ``values_loosened``
  (``progression.without_flagged``; their count is reported, never silently dropped);
- of those, only the reps in which the rung fired count (``progression.unlocks_of`` gives its
  turn; a pseudo-rung never fires), so a rep that never reached the rung is out of that rung's
  denominator;
- the share is the part of them with an event of that type on or after the turn the rung fired
  (``Event.turn_index >= RungUnlock.turn``), on any channel;
- the band is where the share lands (``band_of``), and ``hit`` is that band equal to the
  predicted one. A rung no kept rep fired has no share and no band, and is no hit.

Expectations marked ``likely_wrong`` are listed apart: read the same way, never counted in
``hits`` or ``predictions``."""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, Literal

from claude_bully.analysis.load import ConvKey, LoadedRun
from claude_bully.analysis.progression import unlocks_of, without_flagged
from claude_bully.enums import CellStatus
from claude_bully.planner.records import Expectation, ExpectedEvents

EXPECTED_FILE: Final = "expected.json"
# a band's name and the share it ends at: ``rare`` is under 0.2, ``some`` 0.2 to 0.6 inclusive,
# ``most`` over 0.6 (the plan's ruling; one constant to move)
RATE_BANDS: Final = (("rare", 0.2), ("some", 0.6))

Band = Literal["rare", "some", "most"]


def band_of(share: float) -> Band:
    """The band a share of reps lands in: ``rare`` under 0.2, ``some`` from 0.2 to 0.6
    inclusive, ``most`` over 0.6."""
    (_, rare_below), (_, some_to) = RATE_BANDS
    if share < rare_below:
        return "rare"
    return "some" if share <= some_to else "most"


def _kept_reps(loaded: LoadedRun, cell_id: str) -> tuple[list[ConvKey], int]:
    """The cell's complete reps less the flagged ones, and how many the flag left out."""
    complete = [
        (cell_id, rep)
        for rep in loaded.reps_of(cell_id)
        if loaded.conversations[(cell_id, rep)].status is CellStatus.complete
    ]
    return without_flagged(loaded, complete)


def _unlock_turns(loaded: LoadedRun, keys: Iterable[ConvKey]) -> dict[ConvKey, dict[str, int]]:
    """Per rep, the turn each rung first fired (``unlocks_of``, which leaves the pseudo-rungs
    out)."""
    turns: dict[ConvKey, dict[str, int]] = {}
    for key in keys:
        fired: dict[str, int] = {}
        for unlock in unlocks_of(loaded.trigger_records.get(key, [])):
            fired.setdefault(unlock.rung, unlock.turn)
        turns[key] = fired
    return turns


def _entry(
    loaded: LoadedRun,
    expectation: Expectation,
    rung: str,
    turns: dict[ConvKey, dict[str, int]],
) -> dict[str, Any]:
    reps = seen = 0
    for key, fired in turns.items():
        if rung not in fired:
            continue  # the rung never fired in this rep: out of its denominator
        reps += 1
        if any(
            e.type is expectation.event and e.turn_index >= fired[rung]
            for e in loaded.events.get(key, [])
        ):
            seen += 1
    observed = seen / reps if reps else None
    band = band_of(observed) if observed is not None else None
    return {
        "event": expectation.event.value,
        "predicted": expectation.rate,
        "observed": observed,
        "band": band,
        "hit": band == expectation.rate,
        "reps": reps,
        "hypotheses": list(expectation.hypotheses),
    }


def expected_vs_observed(loaded: LoadedRun, expected: ExpectedEvents) -> dict[str, Any]:
    """The report: ``plan_hash``; ``cells`` (cell id -> rung -> one entry per counted
    expectation: ``event``, ``predicted``, ``observed``, ``band``, ``hit``, ``reps``,
    ``hypotheses``); ``flagged_left_out`` (reps ``values_loosened`` left out, over the expected
    cells); ``likely_wrong`` (the entries of the expectations marked so, each with its ``cell``
    and ``rung``, apart from ``cells``); ``hits`` and ``predictions`` (the counted entries that
    are hits, and all counted entries; a ``likely_wrong`` one is in neither)."""
    cells: dict[str, dict[str, list[dict[str, Any]]]] = {}
    likely_wrong: list[dict[str, Any]] = []
    flagged = hits = predictions = 0
    for cell_id in sorted(expected.cells):
        kept, left_out = _kept_reps(loaded, cell_id)
        flagged += left_out
        turns = _unlock_turns(loaded, kept)
        by_rung: dict[str, list[dict[str, Any]]] = {}
        for rung, expectations in expected.cells[cell_id].rungs.items():
            counted = by_rung.setdefault(rung, [])
            for expectation in expectations:
                entry = _entry(loaded, expectation, rung, turns)
                if expectation.likely_wrong:
                    likely_wrong.append({"cell": cell_id, "rung": rung, **entry})
                    continue
                counted.append(entry)
                predictions += 1
                hits += int(entry["hit"])
        cells[cell_id] = by_rung
    return {
        "plan_hash": loaded.run.plan_hash,
        "cells": cells,
        "flagged_left_out": flagged,
        "likely_wrong": likely_wrong,
        "hits": hits,
        "predictions": predictions,
    }


def expected_report(loaded: LoadedRun) -> dict[str, Any] | None:
    """``expected_vs_observed`` of the events the run's stamp carries; None for a run with no
    stamp or a stamp with no expected events."""
    plan = loaded.run.plan
    if plan is None or plan.expected is None:
        return None
    return expected_vs_observed(loaded, ExpectedEvents.model_validate(plan.expected))


def write_expected(
    loaded: LoadedRun, out: Path, report: dict[str, Any] | None = None
) -> Path | None:
    """``expected.json`` under ``out``; None, with no file, when ``expected_report`` is None.
    ``report`` is the one already built from ``loaded`` (``analyze_run`` makes it once for the
    file and the ``results.md`` line)."""
    report = report if report is not None else expected_report(loaded)
    if report is None:
        return None
    out.mkdir(parents=True, exist_ok=True)
    path = out / EXPECTED_FILE
    path.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    return path


def expected_line(report: Mapping[str, Any]) -> str:
    """``results.md``'s line: the plan hash, the predictions in band and the ones apart."""
    digest = report["plan_hash"]
    head = digest[:8] if isinstance(digest, str) else "(no hash)"
    return (
        f"Plan {head}: {report['hits']} of {report['predictions']} predictions in band "
        f"({len(report['likely_wrong'])} marked likely wrong left apart)."
    )


__all__ = [
    "EXPECTED_FILE",
    "RATE_BANDS",
    "band_of",
    "expected_line",
    "expected_report",
    "expected_vs_observed",
    "write_expected",
]
