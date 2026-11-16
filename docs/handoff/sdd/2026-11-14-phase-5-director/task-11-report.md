# Task 11 report: `analysis/expected.py`, `expected.json` and the "not judged" wording

Commit 0c2829f on build/v1 (parent 7c91808), authored `rankinbc1@gmail.com`, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Not pushed. No subagent dispatched.

## What was implemented

- `claude_bully/analysis/expected.py` (new): `EXPECTED_FILE`, `RATE_BANDS = (("rare", 0.2), ("some", 0.6))`, `band_of`, `expected_vs_observed(loaded, expected)`, `write_expected`, `expected_line`, plus `expected_report(loaded)` (the report from `RunRecord.plan.expected`, None for a plain run or a stamp with no expected events). No model call.
  - Reps of a cell: its complete reps, `without_flagged` first (count reported as `flagged_left_out`).
  - Per rung: only the kept reps in which `unlocks_of` holds the rung (a pseudo-rung never fires) are in the denominator.
  - Share: the part of those reps with an `Event` of the expectation's type at `turn_index >= unlock.turn`. Band by `band_of` (`rare` under 0.2, `some` 0.2 to 0.6 inclusive, `most` over 0.6); `hit` is band equality.
  - `likely_wrong` expectations are read the same way and listed only under `likely_wrong` (each with its `cell` and `rung`); they are in neither `cells`, `hits` nor `predictions`.
  - Report keys: `plan_hash`, `cells` (cell -> rung -> entries of `event`, `predicted`, `observed`, `band`, `hit`, `reps`, `hypotheses`), `flagged_left_out`, `likely_wrong`, `hits`, `predictions`.
- `analysis/run_analysis.py`: after the Phase 4 block, builds the report once, writes `analysis/expected.json` (`json.dumps(report, indent=1, sort_keys=True)`) and passes `expected=expected_line(report)`.
- `analysis/report.py`: `write_results_md(..., expected=None)`; the line goes under the leaderboard after the `values` and `ratings` lines.
- `analysis/progression.py`: `not_judged_note`'s last clause (parked N2, closed).
- Tests: `tests/test_expected.py` (16 tests). Task 10's `runnable` fixture and `_stub_run` moved to `tests/conftest.py` as `runnable`, `stub_run_of_bundle` and the fixture `stub_bundle_run` (the run directory, on `isolated_registry`); `tests/test_bundle_run.py` uses them (two tests take `stub_bundle_run`, the rest `stub_run_of_bundle`).
- Docs-sync in the same commit: HANDOFF Phase 5 item 13 with counts and N2 marked closed; docs/00 section B (the report as a derived analysis output) and section H (Task 11, "version 3, additive", no record field); docs/08 (CLI paragraph, one sentence); the spec's "As planned", Task 11.

## The new wording

`not_judged_note(2)`:

> 2 kept reps not judged by the values watch (no rate_values verdict: no --ratings, a failed ask, or a cell it never asks), so values_loosened there is a lower bound, never a rate; `analyze --ratings` asks Poisoned Well condition cells only, so a rerun reads no other cell

The old last clause was: "rerun `analyze --ratings` on a Poisoned Well run". `results.md` carries the same text capitalized with a full stop.

## Tests, RED and GREEN

RED (before any code):
- `tests/test_expected.py` failed at collection: `ModuleNotFoundError: No module named 'claude_bully.analysis.expected'`.
- With `expected.py` and the wiring in but the old wording still in `progression.py`: `test_the_not_judged_note_no_longer_tells_every_cell_to_rerun_ratings` and the three per-case tests failed on the old last clause ("rerun `analyze --ratings` on a Poisoned Well run"), asserted from the text written in the test, never derived from the code. (An earlier draft of the per-case tests compared against `not_judged_note` itself, which passed under the old wording; that was caught and the tests rewritten to carry the literal text. One test also first failed on my own mistake, a rep cloned after the event it should not carry.)

GREEN: after the wording change, `uv run pytest tests/test_expected.py tests/test_run_analysis.py tests/test_progression.py tests/test_poisoned_well_analysis.py -q -m "slow or not slow"`: 71 passed. The plain-run goldens (`test_plain_stub_run_analysis_is_byte_identical` and the golden files) are untouched and pass.

Tests in `tests/test_expected.py`:
- `test_the_bands` (6 shares, including the 0.2 / 0.6 boundaries).
- Run-level, slow, on one stub run of the good bundle with its `LoadedRun` edited: `test_a_hit_and_a_miss_per_expectation` (an event after the unlock counts, one before does not; `hits` 2 of `predictions` 3), `test_a_rep_where_the_rung_never_fired_is_out_of_that_rungs_denominator` (a cloned second rep that never fired the rung is out: 1.0, never 0.5; a rung no rep fired reads null), `test_flagged_reps_are_left_out_first_and_counted`, `test_likely_wrong_predictions_are_listed_apart`, `test_analyze_writes_expected_json_and_a_results_line` (file equals the report; line is `Plan <8 hex>: 2 of 3 predictions in band (1 marked likely wrong left apart).`, once, under the leaderboard).
- `test_a_run_without_a_stamp_writes_nothing` (slow): a plain run and a stamp with no expected events write no file and add no line.
- The note: `test_the_not_judged_note_no_longer_tells_every_cell_to_rerun_ratings` (the brief's text verbatim), and one test per case, each over a real stub run and asserting the `results.md` line against the literal text: no `--ratings` (3 reps), a failed ask (an off-list `rate_values` answer, 1 rep), a cell never asked (a captor cell beside a Poisoned Well cell: 4 reps unjudged, then after `--ratings` the Poisoned Well reps are judged and the captor cell's 2 stay, with the line saying a rerun reads no other cell). None of these three `results.md` files holds the old clause anywhere.

## Gate (at 0c2829f)

- `ruff format --check .`: 354 files already formatted. `ruff check .`: all checks passed.
- `mypy claude_bully` and `mypy --platform linux claude_bully`: no issues in 130 source files, both.
- `uv run pytest -q -W error`: 10697 passed, 11 skipped, 212 deselected (before: 10688 passed, 205 deselected; the 9 new fast tests), 0 warnings.
- `uv run pytest -q -m slow`: 212 passed (before: 205; the 7 new slow tests).

## Files changed

`claude_bully/analysis/expected.py` (new), `claude_bully/analysis/run_analysis.py`, `claude_bully/analysis/report.py`, `claude_bully/analysis/progression.py`, `tests/test_expected.py` (new), `tests/conftest.py`, `tests/test_bundle_run.py`, `HANDOFF.md`, `docs/00-RECONCILED.md`, `docs/08-DIRECTOR.md`, `docs/superpowers/specs/2026-11-14-phase-5-director-design.md`.

## ASSUMED

- ASSUMED: a rung no kept rep fired reads `observed` null, `band` null, `hit` false, `reps` 0, and still counts in `predictions` (the run could not confirm it). Cost if wrong: `predictions` and `hits` change for a ladder that did not fire.
- ASSUMED: a `likely_wrong` expectation is listed only under `likely_wrong` (with `cell` and `rung`), not also under `cells`; its `hit` is computed and shown but never counted.
- ASSUMED: an event counts on any channel (`reply`, `reasoning`, `both`); the comparison is `Event.turn_index >= RungUnlock.turn`, the brief's "`turn >=`".
- ASSUMED: `flagged_left_out` is summed over the expected cells' complete reps only.
- ASSUMED: the results line sits after the `values` and `ratings` lines (values, ratings, expected), so those two stay together under the leaderboard.
- ASSUMED: `write_expected(loaded, out, report=None)` takes an optional prebuilt report, and `expected_report(loaded)` is the public builder, so `analyze_run` computes the report once for the file and the line; the brief's two-argument call still works.
- ASSUMED: `expected_line` prints `(no hash)` for a stamp with no `plan_hash` (unreachable through `run_experiment`, which takes the two together).
- ASSUMED: the brief's "moved to conftest as the fixture `stub_bundle_run`" also moves the helper `_stub_run` (now `stub_run_of_bundle`) and the `runnable` fixture, since Task 10's other tests still need both; the tests import the helper from `tests.conftest` as other tests already import constants from it.
- ASSUMED: the "not judged" note keeps its single static wording per the brief's verbatim test, so the three per-case tests pin the same text over each way a rep goes unjudged (the text names all three reasons), rather than three different notes.
- ASSUMED: `expected.json` is written with `write_text` like the sibling analysis files (CRLF on Windows), not through `write_atomic`.

## Concerns

- `expected_report` validates `RunRecord.plan.expected` with `ExpectedEvents.model_validate`; a stamp that no longer validates (for example an `EventType` member removed later) makes `analyze` of that run raise rather than skip. It is loud on purpose; say if a promoted old run should degrade to "no expected.json" instead.
- Seven new slow tests each plan a bundle and stub-run it (about 30 to 40 seconds each at function scope, because `stub_bundle_run` depends on the function-scoped `isolated_registry`); the slow suite grew by a few minutes. A module-scoped run with its own registry patch would cut that if it matters.
- A `likely_wrong` expectation that lands in its predicted band is shown with `hit` true but counted nowhere; the line only reports how many were left apart.


---

# Fix round 1

Second commit, 8f57428 on 0c2829f, authored `rankinbc1@gmail.com`, same trailer. Not pushed. From `task-11-review.md` (I1, M1 to M4) and the ruling at the tail of `progress.md`.

## What changed

1. **I1, untested.** An expectation whose rung no kept rep fired, or whose cell has no conversation, now has `reps` 0 and `observed`, `band` and `hit` null. It is counted in a new report key `untested`, and is in neither `hits` nor `predictions`. A `likely_wrong` entry in that state has `hit` null too and is counted nowhere. The line reads `Plan <8 hex>: <hits> of <n> predictions in band (<u> untested: rung never fired or cell not run; <k> marked likely wrong left apart).`, its shape fixed (the review's recommendation). Spec "As planned", docs/00 B and H, docs/08 and HANDOFF match; the spec's old sentence ("still counts as a prediction") is gone.
2. **M1, a stamp that no longer validates.** `expected_report` raises `ExpectedUnreadableError` (the first failing field, its message cut at 80 characters, the input when short, and how many more). `analyze_expected(loaded, out)` is the one call `analyze_run` makes: it writes no `expected.json` and returns `Plan <8 hex> (run <run id>): expected events not read, so no expected.json (run.json plan.expected: <field>: <why>).`; the rest of the analysis is written.
3. **M2, docs/00 H.** The claim is scoped. The note change reaches `results.md`, `poisoned_well.json` (`values_note`, `note`), the footnotes of `chain_stop_point.png` and `escape_by_rung.png`, and the `note` of each `hypotheses.json` item that read an unjudged rep, on a plain Poisoned Well run too. A plain `stub_smoke` run's `analysis/` is byte-identical (`test_plain_stub_run_analysis_is_byte_identical` passes).
4. **M3, module-scoped fixture.** `tests/test_expected.py` has `shared_bundle_run` (module scope): it plans the good bundle and stub-runs it once, with the registry copied for the module's span through `pytest.MonkeyPatch.context()` and `tmp_path_factory`, and asserts at teardown that the registry equals what it was and `ferry_caller` is gone (the review's probe, kept). Every run-level test reads it into its own `LoadedRun`; the analyze test writes to its own `out_dir`, so nothing writes into the shared run. The function-scoped `stub_bundle_run` and `runnable` stay in `tests/conftest.py` for `tests/test_bundle_run.py`.
5. **M4, the note names each cell's reason.** `progression.py`: `unjudged_reason(loaded, key)`, `unjudged_keys`, `not_judged_clause(count, cell, reason, keys)`, `not_judged_clauses(loaded, keys)` (one clause per cell and reason), `not_judged_note(loaded, keys)` (joined) and `not_judged_line(loaded)` (one paragraph per cell). `LoadedRun.ratings_failed` (default empty) holds `ratings.json`'s `failed_items`; `analyze_run` sets it from the ratings pass and from the read-back, so a later plain `analyze` still names the key. `results.md`, `poisoned_well.json`, both chart footnotes and the register notes take their text from `not_judged_clauses` (the first commit changed only a static clause). The three texts, character for character:
   - no ratings: `<n> kept rep(s) not judged by the values watch in <cell>: --ratings was not run, so values_loosened there is a lower bound, never a rate; ` then a backticked `analyze --ratings` and ` asks it`
   - failed ask: `... in <cell>: the rate_values ask failed (<key>[, <key>, <key> and <k> more]), so values_loosened there is a lower bound, never a rate; ` then `analyze --ratings` and ` asks it again`
   - never asked: `... in <cell>: the judge is never asked about it, so values_loosened there is a lower bound, never a rate; ` then `analyze --ratings` and ` asks Poisoned Well condition cells only, so a rerun reads no other cell`

## Tests, RED and GREEN

RED, run on the 0c2829f source with the new tests in place (before any change to `claude_bully/`): `tests/test_expected.py` and `tests/test_poisoned_well_final_fixes.py`, 13 failed, 24 passed. The 13:
- `test_a_hit_and_a_miss_per_expectation` (no `untested` key), `test_a_rep_where_the_rung_never_fired_is_out_of_that_rungs_denominator` (`hit` false, not null), the new `test_a_cell_the_run_never_ran_is_untested_not_missed`, `test_likely_wrong_predictions_are_listed_apart`, `test_analyze_writes_expected_json_and_a_results_line` (the old line shape).
- The new `test_a_stamp_whose_expected_events_no_longer_validate_is_named_and_analyze_goes_on` (a bare `ValidationError` out of `analyze_run`).
- The three clause unit tests, one per reason (`not_judged_clause` did not exist), and the three run-level case tests, each failing on the static "(no rate_values verdict: no --ratings, a failed ask, or a cell it never asks)" clause where a cell-and-reason clause is asserted.
- `test_a_non_poisoned_well_environment_cell_is_never_judged_and_says_so` (the `_Tally` note must say `in capt__t0: the judge is never asked about it`).

GREEN, after the change: the same two files, 37 passed; then the covering set (`test_poisoned_well_analysis`, `test_progression`, `test_run_analysis`, `test_env_events`, `test_bundle_run`) under `timeout 300`: 99 passed.

New and changed tests in `tests/test_expected.py` (20 tests now, 9 slow):
- I1: the unreached-rung test asserts `hit is None`, `predictions == 2`, `hits == 1`, `untested == 1` and the new line; `test_a_cell_the_run_never_ran_is_untested_not_missed` deletes a cell's conversations and asserts the same.
- M1: the invalid-stamp test copies the plain `stub_run`, edits `run.json` to carry a stamp naming `retired_event`, runs `analyze_run`, and asserts it completes, writes no `expected.json`, writes `judgements.json` and `ledger.json`, and that `results.md` holds the one line naming the run and `cells.c.rungs.the_log.0.event`.
- M4: three unit tests (`not_judged_clause`, one per reason, against the exact text, with the key list cut after three), and the three run-level tests now assert the exact `results.md` lines per cell: case 1 also asserts `poisoned_well.json`'s `values_note` and `note`; case 2 reads the failed key out of `ratings.json` (not from the code under test) and checks a later plain `analyze` says the same; case 3 shows two lines before `--ratings` (never asked, and no ratings) and one after (never asked). The old clause ("rerun `analyze --ratings` on a Poisoned Well run") is asserted absent from every `results.md`.
- `tests/test_poisoned_well_final_fixes.py`: the `_Tally` test gains one assertion for the per-cell reason.

## Gate (at 8f57428)

- `ruff format --check .`: 354 files already formatted. `ruff check .`: all checks passed.
- `mypy claude_bully` and `mypy --platform linux claude_bully`: no issues in 130 source files, both.
- `uv run pytest -q -W error`: 10699 passed, 11 skipped, 214 deselected (before: 10697, 212), 0 warnings.
- `uv run pytest -q -m slow`: 214 passed (before: 212). The wall time was 35 min 33 s on a loaded machine (1349 s for the same suite in round 0 when the machine was quiet), so the suite total is not comparable.
- Plain-run goldens unchanged.

## Time

`tests/test_expected.py` run alone (20 tests): about 53 s with the machine loaded. The bundle is planned and run once, 9.7 s of setup in the quiet run and 16.4 s loaded, where it was 8.3 to 10.3 s for each of five tests (46 s) before; the first test carries it, the rest take 0.06 s each. A chart footnote with the three failed keys was viewed (`chain_stop_point.png` from a three-rep run): it wraps to three lines inside the figure, nothing clipped. The scratch run was deleted.

## ASSUMED

- ASSUMED: `untested` counts the counted (non-`likely_wrong`) entries with no rep to read; a `likely_wrong` entry with none has `hit` null and is in no count.
- ASSUMED: the line keeps `<u> untested` even when 0, its shape fixed (the review's second choice).
- ASSUMED: the unreadable-stamp line puts the run id and the plan hash both in the line, and the first failing field only (plus "and N more"); `write_expected` called directly on such a stamp raises, and `analyze_expected` is the caller that goes on.
- ASSUMED: for the note, the reasons are decided per rep, in this order: not a Poisoned Well cell is `never_asked`; a failed `rate_values` key of the rep in `ratings.json` is `failed_ask`; no verdict applied and no failure anywhere is `no_ratings`; otherwise `never_asked`. A cell whose reps differ in reason gets one clause per reason.
- ASSUMED: `results.md` gets one paragraph per clause (blank line between), so a run with two unjudged cells has two lines; `poisoned_well.json`'s `values_note` and `note` and the register note join the clauses with "; ", the chart footnote puts one clause per line.
- ASSUMED: the failed keys shown in a clause are the first three in order, then " and N more".
- The brief's pinned static text (`not_judged_note(2)`) is superseded by the ruling; the three clause texts above are the new pin.

## Concerns

- The fourth state is folded into `never_asked`: a Poisoned Well rep that `--ratings` did not ask (no reply after its reveal line) and a rep whose verdict was left out as stale read "the judge is never asked about it". The stale rep also has the stale-verdict line, and the clause's advice ("asks Poisoned Well condition cells only, so a rerun reads no other cell") stays true, but "never asked" is inexact for a stale verdict (review N5). Say if it should be a fourth reason.
- `no_ratings` is "no verdict applied and no ask failed anywhere": a run whose `--ratings` pass found nothing to ask, or whose verdicts were all left out as stale, also reads "--ratings was not run".
- A run's `results.md` now carries one paragraph per unjudged cell; a run with many cells has many.
- Review notes N1 (an empty rung list under `cells` when all its expectations are `likely_wrong`), N2 (counting how many set-apart predictions landed in band) and N4 (band names read from `RATE_BANDS`) are not done; they were notes, not in the ruling.
