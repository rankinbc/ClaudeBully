# Task 11 re-review, round 1: `analysis/expected.py`, `expected.json` and the "not judged" note

Diff 0c2829f..8f57428 (one commit, `review-0c2829f..8f57428.diff`). Reviewer: sonnet, read-only. Probes in `probes-task11-rereview/` (all runs, base extractions and basetemps they made are deleted).

## Verdicts

| Finding | Verdict |
| --- | --- |
| I1, an untested expectation counted as a miss | FIXED |
| M1, a stamp that no longer validates stops analyze | FIXED |
| M2, docs/00 H "byte-identical" claim | FIXED |
| M3, the slow tests rebuild one bundle run five times | FIXED (registry isolation holds) |
| M4, the note lists three reasons without saying which applies | FIXED as built; one inexactness is real (see Point 3) |

New Critical: 0. New Important: 0. New Minor: 1 (Point 3, the stale verdict). Notes: 5.

## 1. I1: untested expectations are in neither `hits` nor `predictions`

Re-ran the review's probes (P1a to P1c) against 8f57428, plus four more (`temp_probe_rr1_expected.py`):

- P1a, no rung fired anywhere: baseline `2 of 3 predictions in band (0 untested ...; 1 marked likely wrong left apart)`; with every unlock removed `0 of 0 predictions in band (3 untested: rung never fired or cell not run; 1 marked likely wrong left apart)`. The review's number was `0 of 3`. Every entry has `reps` 0 and `observed`, `band`, `hit` all null; the `likely_wrong` entry has `hit` null too and is in no count.
- P1b, the scheduled cell never ran: `1 of 2 ... (1 untested ...)`, where the review had `1 of 3`. A cell whose rep is not complete reads the same (`1 of 2`, 1 untested).
- End to end (P1e): a run copy with the `the_log` unlock lines stripped from every `rep*.triggers.jsonl` (4 lines), through `analyze_run`: `expected.json` carries `untested`, and `results.md` has the one `0 of 0 ... (3 untested ...)` line.
- Invariant checked on every report: `predictions` equals the entries with a non-null `hit`, `hits` equals those true, `untested` equals the counted entries less the tested ones, and `hit`, `band`, `observed` are null exactly when `reps` is 0. It holds in all cases above and the report is JSON-native.
- P1c (a rung whose only expectation is `likely_wrong`) still gives `cells[...] == {'the_log': []}` (review N1, not in the ruling, not done).
- No consumer of `expected.json` or of `hit` exists outside `analysis/expected.py` (grep over `claude_bully` and `scripts`), so a null `hit` breaks nothing downstream.
- Docs: the spec's "As planned" sentence ("still counts as a prediction") is gone; spec, docs/00 B and H, docs/08 and HANDOFF carry the new rule and line shape (grep for the old sentence over `*.md` and `*.py` finds only the historical plan file's test list).

## 2. An invalid stamp skips `expected.json`, names a line, and the rest of analyze runs

`temp_probe_rr1_stamp.py`, on a copy of the bundle run whose `run.json` stamp names `retired_event` (the review's P4):

- `analyze_run(judge=False, hypotheses=True)` completes. Against the same run analyzed with the valid stamp, the only file missing is `expected.json`; every other non-PNG file is byte-equal except `results.md`. `hypotheses.json` is there.
- The line sits under the leaderboard, before `## Bully compliance` (line 17 between lines 4 and 19): `Plan 70d6c345 (run good_bundle): expected events not read, so no expected.json (run.json plan.expected: cells.ferry_triggered__t0.rungs.the_log.1.event: Input should be 'over_apology', 'apology_for_existing', 'self_deprecation', '... (got 'retired_event')).` It names the run, the plan hash, the file, the field path and the offending value.
- Variants: a bad `rate` names `...rungs.the_log.0.rate ... (got 'often')`; three faults read `..., and 2 more`; an unknown top-level key reads `cellz: Extra inputs are not permitted`; a 300-character event is cut at 80 characters. A stamp `expected` that is no dict never reaches this code: `RunRecord` itself refuses it in `load_run` (a bare `ValidationError`, the older, separate failure; not this task).
- Through the CLI (`claude-bully analyze oldrun --no-judge`): exit 0, no traceback.
- `expected: {}` (a stamp with no `cells`) is no failure: it writes `expected.json` and `0 of 0 ... (0 untested ...; 0 marked likely wrong ...)`. That was the first commit's behavior; not part of the fix.
- Note N-C below: an `expected.json` written by an earlier analyze stays on disk beside the "not read" line.

## 3. The note: each cell names its own reason

Clause texts, the three reasons and the advice, read off the code and run end to end (`temp_probe_rr1_note.py`):

- `no_ratings`: `--ratings was not run ... `analyze --ratings` asks it`.
- `failed_ask`: `the rate_values ask failed (<up to 3 keys> and N more) ... `analyze --ratings` asks it again`. The key is read from `ratings.json`'s `failed_items` (`LoadedRun.ratings_failed`) on the `--ratings` pass and on a later plain analyze.
- `never_asked`: `the judge is never asked about it ... `analyze --ratings` asks Poisoned Well condition cells only, so a rerun reads no other cell`.
- A cell is named in each clause; two cells with two reasons give two paragraphs. The plain `stub_smoke` case is unaffected (below).

### Is "never asked" wrong enough to mislead? Yes, in one case: a stale verdict

The fixer's account is that a rep `--ratings` did not ask, or whose verdict was stale, reads "never asked". The first half is a fair reading (a Poisoned Well rep with no reply after its reveal line is never asked, and a rerun changes nothing). The second half is wrong in the way that matters, because for a stale verdict a rerun is exactly the fix:

- A run judged with `--ratings`, then its `rate_values` prompt digest in `ratings.json` changed (the prompt edited since): a plain `analyze` prints, in `results.md`, `2 kept reps not judged by the values watch in pw__t0: the judge is never asked about it, ... a rerun reads no other cell.` directly above `2 stale rating verdict(s) left out, 14 applied; rerun `analyze --ratings`.` The two lines contradict. In `poisoned_well.json` (`note`, each arm's `values_note`), both chart footnotes and the `hypotheses.json` notes, the clause stands alone, and tells the reader a rerun reads nothing new.
- One rep resumed since it was rated (its recorded turn count differs): `1 kept rep ... never asked ... rerun reads no other cell`, beside `8 stale rating verdict(s) left out ...; rerun`. Then `analyze --ratings` rerun: both lines gone (the judge was asked again).
- Every verdict stale (all reps changed): the clause reads `--ratings was not run` (false: it ran) with `analyze --ratings asks it` (right), beside `16 stale rating verdict(s) left out ...`.
- Where a stale line stands beside it (`results.md` and stderr) the right action is still on the page. In the three outputs with no stale line, the reader is told not to rerun when the rerun is the fix.

**Recommendation: yes, add a fourth reason, `stale`, rated Minor.** The information is already on `ReadBack` (`stale_reps`, `stale_kinds`, `kept`) and is thrown away at `analyze_run`:

- Add `LoadedRun.ratings_stale` (the `<cell>/<rep>` reps whose `rate_values` verdict was left out, expanded to every rep when `stale_kinds` holds `rate_values`), set from `read_back` in the same two places `ratings_failed` is.
- In `unjudged_reason`, test it before `no_ratings`/`never_asked`: reason `stale`, clause `... in <cell>: the rate_values verdict is stale (the rep or the prompt changed since it was asked), so it is left out, so values_loosened there is a lower bound, never a rate; `analyze --ratings` asks it again`.
- One test per shape above, red on the current code (the three stale probes in `temp_probe_rr1_note.py` are the starting point).

It is a Minor, not a blocker: the number is still labelled "a lower bound, never a rate", nothing is mis-reported, and the stale line and the stderr warning carry the rerun advice. Take it now only if a round is already open for something else; otherwise the final fix wave. The other two inexactnesses the fixer names stay as they are:

- `no_ratings` reads "--ratings was not run" when `--ratings` was asked with a stub judge (probe: stderr says "--ratings needs a non-stub judge"; the line says "not run", true in effect) and when a pass found nothing to ask. A rerun is harmless there. Optional.
- A rep with no reply after its reveal line is "never asked"; the advice stays true.

## 4. Goldens and registry isolation

- Golden fixtures: `git diff 0c2829f 8f57428 -- tests/fixtures data configs` is empty. `tests/test_env_events.py::test_plain_stub_run_analysis_is_byte_identical`, `tests/test_flagged_charts.py` and the other eight modules below pass.
- Plain parity, base 7c91808 (`git archive`, run through `PYTHONPATH`, the import path printed to prove it) against head 8f57428, one `stub_smoke` run copied to each (`temp_probe_rr1_parity.py`): the whole `analysis/` directory and the whole run directory are byte-identical (`diff -rq`). A plain Poisoned Well run (no `--ratings`, no environment beyond it) differs in exactly the five files the review's P2 found: `results.md`, `hypotheses.json`, `poisoned_well.json` and the two charts' footnotes. The `results.md` diff is only the one not-judged line (old three-way clause to `... in pw__t0: --ratings was not run ...`) and the five register rows that quote it. docs/00 H now says that.
- Registry isolation with `shared_bundle_run`: `tests/test_expected.py` first, then `test_cli.py` (pins the listed strategy count), `test_composed.py`, `test_coverage_matrix.py`, `test_director_context.py`, `test_phased_premise.py`, `test_strategy_base.py`, `test_env_events.py` and `test_flagged_charts.py`, `-W error`: 446 passed in 126 s, so `ferry_caller` did not outlive the module (the fixture's own teardown assert also held). The same 20 tests of `tests/test_expected.py` run in reverse order: 20 passed in 49 s, so no test depends on another's order. `analyze_run(shared run, out_dir=elsewhere, hypotheses=True)` adds and changes no file under the shared run (36 files before and after), so sharing it is safe. `tests/conftest.py` keeps the function-scoped `stub_bundle_run` for `tests/test_bundle_run.py`.
- `ruff check` and `ruff format --check` on `claude_bully/analysis` and the two touched test files: clean.
- Covering set, `-W error`, in two runs (one run of all six exceeded the 300 s cap on this loaded machine and was killed at 55 percent, nothing red): `test_poisoned_well_final_fixes`, `test_poisoned_well_analysis`, `test_progression`, `test_ratings` 108 passed in 114 s; `test_run_analysis`, `test_bundle_run` 22 passed in 258 s. I did not rerun the full 214-test slow suite the fixer reports.

## Notes (none blocking)

- N-A: the `untested` parenthetical names two causes ("rung never fired or cell not run"), but a third produces it too: every rep of the cell flagged `values_loosened` (probe P1c: `1 of 1 ... (2 untested: rung never fired or cell not run ...)` with `flagged_left_out` 1). `expected.json` shows the flag count; the line does not. Wording only.
- N-B: the clause "`analyze --ratings` asks it" has no antecedent for "it" (the cell, or its reps). Wording only.
- N-C: a run analyzed once with a valid stamp keeps its `expected.json` when a later analyze finds the stamp unreadable (probe: the file is still there beside `Plan ... expected events not read, so no expected.json`). Reachable only after an `EventType` or `Expectation` change in a later version. Cleaning a stale file would make the line true.
- N-D: review notes N1 (an empty rung list under `cells`), N2 (how many set-apart predictions landed in band) and N4 (band names from `RATE_BANDS`) were not in the ruling and are not done.
- N-E: the first test of `tests/test_expected.py` carries the bundle setup (16 s on this loaded machine in the 446-test run, about 10 s when quiet); the rest take 0.06 s each, as the fixer reports.
