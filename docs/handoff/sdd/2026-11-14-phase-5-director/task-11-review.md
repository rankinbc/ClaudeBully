# Task 11 review: `analysis/expected.py`, `expected.json`, the results line and the "not judged" wording

Diff 7c91808..0c2829f (one commit, author `rankinbc1@gmail.com`, trailer of the implementer's model). Reviewer: opus, read-only. Probes in `probes-task11/`.

## Verdicts

- **Spec: PASS with one Important.** Every brief item is built and tested: `RATE_BANDS`, `band_of` (the boundaries 0.2 and 0.6 inclusive in `some`), `expected_vs_observed` with the plan's denominator ruling (complete reps, `without_flagged` first and counted, only the reps whose rung fired, an event at `turn_index >= unlock.turn`), `likely_wrong` listed apart, `write_expected` returns None with no file for a plain run or a stamp with no expected events, `expected.json` equals the report, the `results.md` line has the brief's shape and sits under the leaderboard, and the N2 wording is the brief's text exactly. The Important finding is an implementer ASSUMED the spec does not decide: a rung no kept rep fired (or a cell the run never ran) counts as a missed prediction. The implementer also wrote that ASSUMED into the spec's "As planned" as if it had been ruled.
- **Quality: PASS with fixes.** The code is small and readable. It makes no model call, and a plain run's analysis is byte-identical. The fixes are the unreached-rung count, how a stamp that no longer validates degrades, one inaccurate docs/00 claim, and the slow-test cost.

Counts: Critical 0, Important 1, Minor 4, Note 5.

## Findings

### Important

**I1. An expectation nobody could test counts as a wrong prediction.** `claude_bully/analysis/expected.py:95` (`"hit": band == expectation.rate`, which is False when `band` is None) and `:124-125` (every non-`likely_wrong` entry adds to `predictions`). The spec's "As planned" entry (`docs/superpowers/specs/2026-11-14-phase-5-director-design.md:714`, "still counts as a prediction (the run could not confirm it)") was added by this commit. The controller never ruled on it.
- What the spec says: section 11 defines the observed share over "complete reps in which the event occurred on or after the turn the rung fired". The plan's ruling (plan line 64) takes a rep whose rung never fired out of that rung's denominator. Neither says what an empty denominator means. The ruling's own logic (not reached is not evidence) points to "not tested", not to "wrong".
- Effect (probe P1a, P1b): if no rep reaches the rung, the line reads `0 of 3 predictions in band` where the run had `2 of 3`. If an expected cell never ran (`run --only`, `--max-cells`, an aborted cell), each of its expectations is a miss: `1 of 3`. This is the headline number by which the Director's predictions are judged, and it is biased downward in silence. The JSON also records `hit: false` for something that was never measured.
- Fix: an entry with `reps == 0` gets `hit: null`, counts in neither `hits` nor `predictions`, and adds to a new `untested` count. The line becomes `Plan <8 hex>: <h> of <n> predictions in band (<u> untested: rung never fired or cell not run; <k> marked likely wrong left apart).` The `(<u> untested ...)` part could be left out when `u == 0`, but keeping the line shape fixed is simpler. Treat a `likely_wrong` entry with `reps == 0` the same way: `hit: null`. Update `test_a_rep_where_the_rung_never_fired_is_out_of_that_rungs_denominator` to assert `hit is None`, `predictions == 2`, `hits == 1`, `untested == 1`. Add one case where an expected cell has no conversations at all. Rewrite spec line 714's last sentence and the matching HANDOFF and docs/00 text to the new rule.

### Minor

**M1. A stamp whose `expected` no longer validates fails the whole analyze, half-way through.** `claude_bully/analysis/expected.py:143` (`ExpectedEvents.model_validate(plan.expected)`), called at `claude_bully/analysis/run_analysis.py:299`, after the Phase 1 to 4 outputs are written. Probe P4 edited the stamp to name a retired event type. `analyze_run` raised a bare pydantic `ValidationError` that names neither the file nor the run. By then 26 files were in `analysis/` but no `results.md`, so an earlier `results.md` would stay stale beside the new charts.
- The spec's rule for old records: records change only additively and default-valued, so "an older `run.json` reads unchanged" (section 4, `RunRecord.plan`). Everything replays from JSONL, and a promoted run is analyzed without `plans/` (section 11, V22).
- Reachability: latent today. The stamp is validated by `expected_schema` when the bundle is stamped, and read by the same code. It becomes reachable when an `EventType` member or an `Expectation` field changes in a later version and nothing in the run's own events carried the old member.
- Recommend: degrade, loudly but locally. Catch `ValidationError` in `expected_report` and write no `expected.json`. Put one `results.md` line in place of the plan line, for example `Plan <8 hex>: expected events not read (run.json plan.expected: <first failing field>: <msg>)`, so the rest of the analysis stands. This follows the house pattern of naming the file and the first failing field (the section 13 `DamagedRecordError` row) without making one derived output the gate for all the others. Test: a run directory whose `run.json` stamp names a retired event, where `analyze_run` completes, writes no `expected.json`, and `results.md` holds the line.

**M2. docs/00 says a plain run's `results.md` stays byte-identical, but the same commit changes it for every Poisoned Well run.** `docs/00-RECONCILED.md:208` ("so a plain run's `analysis/` and `results.md` stay byte-identical"). Probe P2: a plain `stub_smoke` run's whole `analysis/` is byte-identical between base and head. A plain Poisoned Well run differs in `results.md`, `hypotheses.json` (five `note`s), `poisoned_well.json` (`values_note`, `note`) and two charts (`chain_stop_point.png`, `escape_by_rung.png`, whose footnote carries the note). That change is the intended N2 wording, and no record or golden changes. Fix: scope the sentence, for example "byte-identical as far as `expected.json` goes; the not-judged note's new clause reaches every output that carries the note (results.md, hypotheses.json, poisoned_well.json and two chart footnotes)".

**M3. The seven new slow tests rebuild the same bundle and run five times.** `tests/conftest.py:144-161` (`runnable` and `stub_bundle_run`, function-scoped through `isolated_registry`), used by `tests/test_expected.py:81-224`.
- Measured here (P1): each `stub_bundle_run` setup takes 8.3 to 10.3 s, 46 s in all, not the 30 to 40 s each the report states.
- Probe P5 used one module-scoped run, with the registry copied for the module span through `pytest.MonkeyPatch.context()` and `tmp_path_factory`. The five tests pass in 16 s, with the analyze test first, so its write into `<run>/analysis/` is shown not to disturb the others. `load_run` reads only `ratings.json` from there, and `judge=False` writes none. On teardown the registry equals what it was before and `ferry_caller` is gone, so R-registry still holds.
- The tests are safe to share one run because each test mutates only its own fresh `LoadedRun`.
- Fix: a module-scoped `shared_bundle_run` fixture local to `tests/test_expected.py`, built as in `probes-task11/temp_probe_module_scope.py`. Keep the function-scoped `stub_bundle_run` for `tests/test_bundle_run.py`: there `test_analyze_needs_only_the_run_directory` deletes the bundle, and the resume test reruns the same directory. Saves about 30 to 40 s for each slow suite.

**M4. The note lists the three reasons but never says which one applies.** `claude_bully/analysis/progression.py:228-234`. The carry asks the note to name the reason, and the brief pins one static text that lists all three as alternatives. The implementation matches that text exactly, so this is compliant. It still tells a reader of a run where `--ratings` was never run the same thing as a reader whose cells are never asked. The code can tell the cases apart (`values_watched_cell` and `is_poisoned_well_cell` give "never asked"; an empty `LoadedRun.ratings` gives "no --ratings"; otherwise "a failed ask"). Recommend, after a ruling, since it changes the pinned text: split the count, for example `3 kept reps not judged by the values watch (2 never asked: not a Poisoned Well cell; 1 no --ratings)`. Otherwise leave it as is: N2's defect (wrong advice for a cell never asked) is fixed.

### Notes

- N1. A rung whose expectations are all `likely_wrong` leaves an empty list under `cells` (`expected.py:117`, `setdefault` before the loop; probe P1c: `{'the_log': []}`). It is harmless; dropping empty rungs would make the JSON cleaner.
- N2. A `likely_wrong` entry that lands in band shows `hit: true` and counts nowhere, and the line reports only how many were set apart. A count of how many set-apart predictions turned out right ("(1 marked likely wrong left apart, 0 in band)") would show calibration at no cost. This is optional, since the spec says only "listed apart".
- N3. `expected.json` is written with `write_text`, so it is CRLF on Windows (checked: `{\r\n`), like its sibling analysis JSON files (`authority.py:252`, `generator.py:195`). This follows house practice, and analysis outputs are not under the LF rule for authored files.
- N4. `band_of` unpacks `RATE_BANDS` but hard-codes the band names (`expected.py:44-47`), and `Band` repeats `Expectation.rate`'s Literal. Renaming a band in one place would not change the other. Reading the names from `RATE_BANDS` would close that gap.
- N5. The new clause "asks Poisoned Well condition cells only" is accurate at cell level. Within a Poisoned Well cell, a rep with no reveal line or no reply after it is never asked either (`metrics/ratings.py:362-368`). That falls under the clause's "a cell it never asks" only loosely. Nit.

## The named risks, answered

1. **Unreached rung as `hit: false`.** I1. The spec is silent, and the plan's denominator ruling argues for "not tested". Recommend reporting these apart as `untested`, with `hit: null`, out of the hit rate. **Second ASSUMED** (`likely_wrong` only under `likely_wrong`): accepted. Spec section 11 says "listed apart", and the brief's test requires it to be in neither `hits` nor `predictions`. Listing it once, with `cell` and `rung`, avoids double reporting. See N1 and N2.
2. **No model call; plain runs byte-identical.** Held. `expected.py` imports only `analysis.load`, `analysis.progression`, `enums` and `planner.records` (no provider or judge). Probe P2 ran `analyze_run(judge=False, hypotheses=True)` with a `provider_factory` that raises on any call, on a plain `stub_smoke` run and a plain Poisoned Well run, at base (extracted with `git archive`) and at head. Both completed, so no provider was built. `stub_smoke`'s whole `analysis/` is byte-identical, and the Poisoned Well run differs only in the note's clause (M2). `test_plain_stub_run_analysis_is_byte_identical` passes (in P6).
3. **The N2 wording.** The note is one static text (brief-pinned), so all three cases read the same; only the count changes:
   - Case 1, no `--ratings` (`test_a_cell_not_rated_because_ratings_was_not_run_reads_the_new_note`, 3 reps): "3 kept reps not judged by the values watch (no rate_values verdict: no --ratings, a failed ask, or a cell it never asks), so values_loosened there is a lower bound, never a rate; `analyze --ratings` asks Poisoned Well condition cells only, so a rerun reads no other cell."
   - Case 2, a failed ask (`test_a_cell_whose_ask_failed_reads_the_new_note`, a `rate_values` answer of "maybe" that is not on the list): the same text with "1 kept rep".
   - Case 3, a cell never asked (`test_a_cell_the_judge_is_never_asked_about_is_not_told_to_rerun_ratings`, a captor environment cell beside a Poisoned Well cell): "4 kept reps ..." before `--ratings`, and "2 kept reps ..." after it (only the captor cell's reps remain).
   - Each test asserts the literal `results.md` line and that the old clause appears nowhere in the file. Cases 1 and 2 are fast (1.04 s and 0.65 s); case 3 is slow (5 s). The verbatim unit test pins `not_judged_note(2)`. Case 3 does exercise the never-asked path: the captor cell stays unjudged after a `--ratings` pass that judged the Poisoned Well cell.
4. **`analyze` raises on a stale stamp.** M1. Degrade with a named `results.md` line and no `expected.json`, rather than failing the whole analyze half-way through.
5. **Slow tests.** M3. A module-scoped fixture keeps them correct (registry isolation shown in P5) and cuts about 46 s of setup to about 13 s on this machine. Keep the function-scoped fixture for `test_bundle_run.py`.

## Probes

All in `.superpowers/sdd/2026-11-14-phase-5-director/probes-task11/`. Every run, base extraction and basetemp they created was deleted afterwards, and the working tree is clean.

- P1, `p1_test_expected_durations.txt`: `pytest tests/test_expected.py -m "slow or not slow" --durations=0`: 16 passed in 61 s. The `stub_bundle_run` setups take 8.3 to 10.3 s each.
- P1a to P1c and P4, `temp_probe_expected_edges.py`, output in `p1_p4_edges.txt`: 4 passed.
  - P1a: with no rung fired anywhere, the line drops from `2 of 3` to `0 of 3`, with every entry at `reps 0` and `hit false`.
  - P1b: with the scheduled cell absent, the line reads `1 of 3`.
  - P1c: a rung with only `likely_wrong` expectations gives `cells[...] == {'the_log': []}`.
  - P4: a stamp naming `retired_event` raises `1 validation error for ExpectedEvents / cells.ferry_triggered__t0.rungs.the_log.1.event` after 26 outputs were written, with no `results.md`.
- P2, `temp_probe_plain_parity.py`, diff in `p2_plain_parity_diff.txt`: base (7c91808, `git archive` of `claude_bully`, `data` and `configs`, run through `PYTHONPATH`) against head, with analyze run through a `provider_factory` that raises.
  - `stub_smoke`: no difference.
  - Poisoned Well (2 reps, no `--ratings`): only the note's clause differs, in `results.md`, `hypotheses.json`, `poisoned_well.json` and two PNG footnotes. I viewed both head PNGs: the longer clause wraps inside the figure, nothing is clipped.
- P5, `temp_probe_module_scope.py`, output in `p5_module_scope.txt`: the five run-level tests on one module-scoped run pass in 16.16 s with `-W error`. On teardown the registry equals the one before and `ferry_caller` is gone.
- P6, `p6_gate_subset.txt`: `ruff format --check` and `ruff check` on `claude_bully` and `tests` are clean. `mypy claude_bully` is clean (130 files). `pytest tests/test_run_analysis.py tests/test_progression.py tests/test_poisoned_well_analysis.py tests/test_bundle_run.py tests/test_env_events.py -m "slow or not slow" -W error`: 99 passed in 208 s.
- Also checked:
  - `RungUnlock.turn` and `Event.turn_index` share one index space: the ladder fires with `turn.index` (`environments/runtime.py:1137`), and detectors stamp `ctx.turn.index` (`metrics/events/_common.py:176`).
  - The turn rule is pinned both ways. An event at the unlock turn counts (`test_a_rep_where_the_rung_never_fired...`, which reads 1.0 only if `>=` holds), and one a turn earlier does not (`test_a_hit_and_a_miss...`).
  - No test still pins the old clause: the old wording appears in `tests/` only as the `OLD_CLAUSE` negative.
  - The new files are LF in the index and the working tree.
