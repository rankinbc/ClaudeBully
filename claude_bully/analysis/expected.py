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
  predicted one. A rung no kept rep fired, or a cell the run never ran, has no share, no band
  and no verdict (``hit`` is None): the expectation is ``untested``, in neither ``hits`` nor
  ``predictions``, so the hit rate is over the expectations the run could test (fix round 1, I1).

Expectations marked ``likely_wrong`` are listed apart: read the same way, never counted in
``hits``, ``predictions`` or ``untested``.

A stamp whose ``expected`` no longer validates (an ``EventType`` retired since the run) is no
reason to stop an analysis: ``expected_report`` raises ``ExpectedUnreadableError``, and
``analyze_expected`` writes no ``expected.json`` and returns the ``results.md`` line that names
the run and the first failing field."""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import ValidationError

from claude_bully.analysis.load import ConvKey, LoadedRun
from claude_bully.analysis.progression import unlocks_of, without_flagged
from claude_bully.enums import CellStatus
from claude_bully.planner.records import Expectation, ExpectedEvents

EXPECTED_FILE: Final = "expected.json"
# a band's name and the share it ends at: ``rare`` is under 0.2, ``some`` 0.2 to 0.6 inclusive,
# ``most`` over 0.6 (the plan's ruling; one constant to move)
RATE_BANDS: Final = (("rare", 0.2), ("some", 0.6))

Band = Literal["rare", "some", "most"]


class ExpectedUnreadableError(ValueError):
    """The stamp's ``expected`` does not validate as ``ExpectedEvents`` (the message is the first
    failing field and why)."""


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
        # no rep to read, so nothing was tested: no verdict, never a miss (fix round 1, I1)
        "hit": None if band is None else band == expectation.rate,
        "reps": reps,
        "hypotheses": list(expectation.hypotheses),
    }


def expected_vs_observed(loaded: LoadedRun, expected: ExpectedEvents) -> dict[str, Any]:
    """The report: ``plan_hash``; ``cells`` (cell id -> rung -> one entry per counted
    expectation: ``event``, ``predicted``, ``observed``, ``band``, ``hit``, ``reps``,
    ``hypotheses``); ``flagged_left_out`` (reps ``values_loosened`` left out, over the expected
    cells); ``likely_wrong`` (the entries of the expectations marked so, each with its ``cell``
    and ``rung``, apart from ``cells``); ``hits`` and ``predictions`` (the counted entries that
    are hits, and the counted entries the run could test; an ``untested`` entry, whose ``hit`` is
    None, is in neither, and a ``likely_wrong`` one is in no count); ``untested`` (the counted
    entries no kept rep could test: the rung never fired, or the cell never ran)."""
    cells: dict[str, dict[str, list[dict[str, Any]]]] = {}
    likely_wrong: list[dict[str, Any]] = []
    flagged = hits = predictions = untested = 0
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
                if entry["hit"] is None:
                    untested += 1
                    continue
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
        "untested": untested,
    }


def _first_failure(exc: ValidationError) -> str:
    """``<field path>: <why>`` of the first failing field, the input it got when that is short,
    and how many more failed."""
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    why = first["msg"] if len(first["msg"]) <= 80 else first["msg"][:77] + "..."
    got = first.get("input")
    short = isinstance(got, str | int | float) and len(repr(got)) <= 40
    shown = f" (got {got!r})" if short else ""
    more = exc.error_count() - 1
    return f"{where}: {why}{shown}" + (f", and {more} more" if more else "")


def expected_report(loaded: LoadedRun) -> dict[str, Any] | None:
    """``expected_vs_observed`` of the events the run's stamp carries; None for a run with no
    stamp or a stamp with no expected events. Raises ``ExpectedUnreadableError`` for a stamp whose
    events no longer validate."""
    plan = loaded.run.plan
    if plan is None or plan.expected is None:
        return None
    try:
        events = ExpectedEvents.model_validate(plan.expected)
    except ValidationError as exc:
        raise ExpectedUnreadableError(_first_failure(exc)) from exc
    return expected_vs_observed(loaded, events)


def write_expected(
    loaded: LoadedRun, out: Path, report: dict[str, Any] | None = None
) -> Path | None:
    """``expected.json`` under ``out``; None, with no file, when ``expected_report`` is None.
    ``report`` is the one already built from ``loaded``. A stamp that does not validate raises
    ``ExpectedUnreadableError`` (``analyze_expected`` is the caller that goes on)."""
    report = report if report is not None else expected_report(loaded)
    if report is None:
        return None
    out.mkdir(parents=True, exist_ok=True)
    path = out / EXPECTED_FILE
    path.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    return path


def _head(digest: object) -> str:
    return digest[:8] if isinstance(digest, str) else "(no hash)"


def expected_line(report: Mapping[str, Any]) -> str:
    """``results.md``'s line: the plan hash, the predictions in band, those the run could not
    test and those marked likely wrong, left apart."""
    return (
        f"Plan {_head(report['plan_hash'])}: {report['hits']} of {report['predictions']} "
        f"predictions in band ({report['untested']} untested: rung never fired or cell not run; "
        f"{len(report['likely_wrong'])} marked likely wrong left apart)."
    )


def unreadable_line(loaded: LoadedRun, reason: str) -> str:
    """``results.md``'s line for a stamp whose expected events do not validate: the plan hash, the
    run, and the first failing field."""
    return (
        f"Plan {_head(loaded.run.plan_hash)} (run {loaded.run.run_id}): expected events not read, "
        f"so no {EXPECTED_FILE} (run.json plan.expected: {reason})."
    )


def analyze_expected(loaded: LoadedRun, out: Path) -> str | None:
    """What ``analyze_run`` does for the plan: build the report once, write ``expected.json`` and
    return ``results.md``'s line. None for a run with no expected events (no file, no line); a
    stamp that does not validate writes no file and returns the line that says so, and the
    analysis goes on."""
    try:
        report = expected_report(loaded)
    except ExpectedUnreadableError as exc:
        return unreadable_line(loaded, str(exc))
    if report is None:
        return None
    write_expected(loaded, out, report)
    return expected_line(report)


__all__ = [
    "EXPECTED_FILE",
    "RATE_BANDS",
    "ExpectedUnreadableError",
    "analyze_expected",
    "band_of",
    "expected_line",
    "expected_report",
    "expected_vs_observed",
    "unreadable_line",
    "write_expected",
]
