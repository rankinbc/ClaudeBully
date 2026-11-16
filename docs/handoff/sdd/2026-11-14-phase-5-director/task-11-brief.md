### Task 11: `analysis/expected.py`, `expected.json` and the "not judged" wording

**Files:**
- Create: `claude_bully/analysis/expected.py`
- Modify: `claude_bully/analysis/run_analysis.py` (`analyze_run` writes `expected.json`), `claude_bully/analysis/report.py` (`write_results_md(expected=)`), `claude_bully/analysis/progression.py` (`not_judged_note`'s last clause)
- Test: `tests/test_expected.py`

**Interfaces:**
- Consumes: `LoadedRun` (`run.plan`, `events`, `trigger_records`, `cells`, `specs`, `conversations`), `progression.unlocks_of`, `without_flagged`, `ExpectedEvents`.
- Produces: `EXPECTED_FILE: Final = "expected.json"`; `RATE_BANDS: Final = (("rare", 0.2), ("some", 0.6))`; `band_of(share: float) -> Literal["rare", "some", "most"]`; `expected_vs_observed(loaded: LoadedRun, expected: ExpectedEvents) -> dict[str, Any]` (`{"plan_hash", "cells": {cell: {rung: [{"event", "predicted", "observed", "band", "hit", "reps", "hypotheses"}]}}, "flagged_left_out", "likely_wrong": [...], "hits", "predictions"}`); `write_expected(loaded: LoadedRun, out: Path) -> Path | None`; `expected_line(report: Mapping[str, Any]) -> str`; `write_results_md(..., expected: str | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_expected.py
"""Phase 5 Task 11: expected events against the observed ones (spec section 11)."""

import json
from pathlib import Path

import pytest

from claude_bully.analysis.expected import EXPECTED_FILE, band_of, expected_line, expected_vs_observed, write_expected
from claude_bully.analysis.progression import not_judged_note


@pytest.mark.parametrize(
    ("share", "band"), [(0.0, "rare"), (0.19, "rare"), (0.2, "some"), (0.6, "some"), (0.61, "most"), (1.0, "most")]
)
def test_the_bands(share: float, band: str) -> None:
    assert band_of(share) == band
```

The rest are run-level and use one stub run from a bundle (Task 10's `runnable` fixture and `_stub_run`, moved to `tests/conftest.py` as the fixture `stub_bundle_run` (a `Path` to the run directory), which depends on `isolated_registry`, so `register_plan_personas` never leaves `ferry_caller` registered for the rest of the suite (R-registry, review I1); Task 10's tests use the same fixture), with its `LoadedRun` edited per test:

- `test_a_hit_and_a_miss_per_expectation`: in the loaded run, the condition rep's events include the first expectation's event after its rung's unlock turn and not the second's; `expected_vs_observed` gives the first `observed 1.0`, `band "most"`, `hit` as `predicted == "most"`, and the second `observed 0.0`, `band "rare"`; `hits` counts them; an event on a turn before the unlock does not count.
- `test_a_rep_where_the_rung_never_fired_is_out_of_that_rungs_denominator`.
- `test_flagged_reps_are_left_out_first_and_counted`: a `values_loosened` event added to one rep; `flagged_left_out == 1` and that rep is in no share.
- `test_likely_wrong_predictions_are_listed_apart`: the `likely_wrong` expectation is in `likely_wrong` and not in `hits` or `predictions`.
- `test_a_run_without_a_stamp_writes_nothing`: `write_expected` on a plain stub run returns None and writes no `expected.json`; `analyze_run` on it writes none either.
- `test_analyze_writes_expected_json_and_a_results_line`: `analyze_run(run_dir, judge=False)` writes `analysis/expected.json` equal to `expected_vs_observed`'s report, and `results.md` holds `expected_line(report)`, which reads `Plan <8 hex>: <hits> of <n> predictions in band (<k> marked likely wrong left apart).`.
- `test_the_not_judged_note_no_longer_tells_every_cell_to_rerun_ratings` (HANDOFF parked N2):

```python
def test_the_not_judged_note_no_longer_tells_every_cell_to_rerun_ratings() -> None:
    note = not_judged_note(2)
    assert note == (
        "2 kept reps not judged by the values watch (no rate_values verdict: no --ratings, a "
        "failed ask, or a cell it never asks), so values_loosened there is a lower bound, never a "
        "rate; `analyze --ratings` asks Poisoned Well condition cells only, so a rerun reads no "
        "other cell"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_expected.py -q -m "slow or not slow"`
Expected: FAIL at import.

- [ ] **Step 3: Implement**

`expected_vs_observed` per the Plan Decisions' ruling: the complete condition reps of each cell, `without_flagged` first (its count reported), per rung the reps in which `unlocks_of` holds that rung (a pseudo-rung never), per expectation the share of those reps with an event of its type at `turn >= unlock.turn`, its band, `hit`. `write_expected` returns None when `loaded.run.plan` is None or its `expected` is None; else writes `analysis/expected.json` (`json.dumps(report, indent=1, sort_keys=True)`). `analyze_run` calls it and passes `expected=expected_line(report)` to `write_results_md`, which puts the line under the leaderboard beside the `values` line. `not_judged_note`'s last clause becomes the test's text.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_expected.py tests/test_run_analysis.py tests/test_progression.py tests/test_poisoned_well_analysis.py -q -m "slow or not slow"`, then the gate.
Expected: PASS; any test that pinned the old note's last clause is updated to the new text in this commit.

- [ ] **Step 5: Docs-sync and commit**

docs/00 section B: `expected.json` as an analysis output (derived); HANDOFF "From the Phase 4 final re-review (parked)": N2 marked closed in Phase 5 Task 11 (re-anchor at execution: search for 'N2: the "not judged" note'). Spec "As planned": the band and denominator ruling.

```bash
git add claude_bully/analysis/expected.py claude_bully/analysis/run_analysis.py claude_bully/analysis/report.py \
  claude_bully/analysis/progression.py tests/test_expected.py tests/test_bundle_run.py tests/conftest.py docs/00-RECONCILED.md \
  docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 11, expected.json against the observed events, the results line and the not-judged wording (N2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

