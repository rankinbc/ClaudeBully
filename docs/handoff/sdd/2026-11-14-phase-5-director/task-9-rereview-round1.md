# Task 9 re-review, fix round 1 (24b1903..9639ab8)

Scoped to I1 and the five Minors of task-9-review.md, the fix diff, and the binding ruling. The checkout was left read-only (git status clean at the end): every bundle was built on the doubles under the session scratchpad and deleted; mutations are applied at import by a pytest plugin. Probes and outputs are in `probes-task9-rereview1/`. The full gate was not re-run.

## Verdicts

| Finding | Verdict |
| --- | --- |
| I1 blanket ValueError catch | FIXED |
| m1 `plan new` stop message | FIXED for the named case; one new Minor (N1: a `validated` plan) |
| m2 stale `dryrun.jsonl` | FIXED for the named case; residual Note (N3: the review archive) |
| m3 missing paths | FIXED |
| m4 `--plans-root` help | FIXED for every `plan` command; the pre-existing `--runs-root` and `--results-root` still print the home folder name (7 commands, listed below) |
| m5 parity compares ledger and transcripts | FIXED, and it bites |

New findings: Critical 0, Important 0, Minor 3 (R1, N1, N2), Notes 4. No new breakage in the gate-relevant sense: the fix tests pass (see Checks), the planned-bug and damaged-record behaviors are as the ruling says.

## I1

Each case ran as a real process (`probes-task9-rereview1/case.py`: the stub doubles as the provider factory, then `cli.app()` with no CliRunner), so the exit code and the printed text are the real ones.

| Case | Command | Result |
| --- | --- | --- |
| Planted `int("not-a-number")` in `lint_bundle` | `plan validate` | Rich traceback with the `bug` frame and `ValueError: invalid literal ...`; no `error:` line; exit 1 |
| Planted pydantic `ValidationError` raised outside `read_plan_record` | `plan validate` | traceback with the `bug` frame; exit 1 (an unrelated pydantic error is not masked either) |
| Ledger line 2 not JSON, mid-file | `plan continue` | `error: <bundle>\ledger.jsonl: line 2 is not valid JSON (...); it is not a torn last line, so it is not dropped`; exit 1 |
| Ledger torn last line | `plan continue` | dropped by the torn-tail rule; plan goes on to `runnable`; exit 0 (unchanged) |
| `plan.json` with `open_blocks: "three"` | `validate`, `continue`, `review` | `error: <bundle>\plan.json: field open_blocks: Input should be a valid integer, ...`; exit 1 each |
| Same plus a second bad field | `validate` | `... field open_blocks: ... (and 1 more)`; exit 1 |
| `plan.json` not JSON | `validate` | `error: <file>: line 2: not valid JSON (Expecting value)`; exit 1 |
| `plan.json` with a byte that is not UTF-8 | `validate` | `error: <file>: line 1: a byte that is not UTF-8 (invalid start byte)`; exit 1 |
| Schema-invalid `plan.json` | `plan new --request ... --no-confirm` on that slug | `error: <file>: field open_blocks: ...`; exit 1, `SystemExit` (CliRunner probe) |

The new test `test_a_planted_bug_in_a_plan_command_keeps_its_traceback` bites: with `_plan_errors` mutated back to `(DirectorError, ValueError)` it fails (1 failed, 3 passed over the four I1 tests; the other three pass under the old catch because they test inputs the old catch also printed). Import order was checked in fresh interpreters (`records`, `runner.store`, `planner.cli`, `cli`, `bundle`): no cycle from `records` importing `runner.store`.

### Recommendation on a damaged transcript or attempt marker

Yes, raise `DamagedRecordError` for them. Evidence, real process, `plan continue` on a plan killed inside stage 2:

- Transcript truncated or of the wrong shape: traceback ending `ValidationError: 1 validation error for Transcript` (`bundle.py:302`, `read_transcript`).
- Attempt marker `.attempt.json` not JSON or of the wrong shape: traceback ending `ValidationError: ... for DirectorAttempt` (`bundle.py:331`, `read_attempt`).
- A ledger line that is valid JSON but not a `LedgerLine`, after the marker's offset: traceback ending `ValidationError: 7 validation errors for LedgerLine` (`director.py:1241`, `_drop_dead_lines`). The ruling's "a damaged ledger prints its file and line" holds for the unparseable line only.

Why raise it:

- All three are harness records written atomically, so a damaged one is a disk fault or a hand edit, which is what spec section 13's row names ("a damaged harness record").
- The traceback does not name the file either (the pydantic text names only the model), and before this round it printed as `error:` with the same file-less text, so today's output is no more useful and is noisier.
- It is one wrapper in the shape `read_plan_record` already has (file, first field, how many more), at about four sites: `read_transcript`, `read_attempt`, the `LedgerLine` parse in `_drop_dead_lines`, and the sha-mismatch and shape `ValueError`s in `_committed_texts` and `committed_outputs`, which already name the transcript and read as `error:` text before this round.

Grade: Minor (R1). It does not block Task 10; fold it into the next touch of those readers or the final review. A test per site, "names the file", plus one that a planted bug still keeps its traceback.

## The Minors

### m1 `plan new` stop message: FIXED, with N1

- `plan new --request <same>` without `--no-confirm` on an `authored` plan: prints the plan, `stopped after stage 1: review <bundle>/plan.md, then run plan continue <bundle>`, `status authored`; exit 0; no stage record changed and no planner or reviewer call was made (calls added: 0 and 0). On a fresh slug it stops as before (exit 0, `status planned`). On a `runnable` plan it goes through `_finish` (cell lines, `status runnable`, exit 0).
- `test_plan_new_again_without_no_confirm_on_an_authored_plan_prints_the_stop` passes with the fix.
- **N1 (Minor, new): the rule `record.status not in ("runnable", "failed")` also catches `validated`.** A plan whose stage 5 committed with failing lints (status `validated`) now prints `stopped after stage 1: review plan.md, then run plan continue ...`, then `status validated`, and exits 0. The lint failures are not printed. The same command with `--no-confirm` prints `fail trigger_examples ...`, `fail ladder_walk ...`, `fail dry_run ...` and exits 1. Before this round, a `validated` plan gave exit 1 with the failures. Probe: `rr_probes_m1.out`.
  - Effect: a not-runnable plan reports exit 0 and tells the owner to review plan.md and run `plan continue`, which has nothing to continue.
  - Fix: stop only while stage 5 has not committed (`planned`, `authored`, `reviewed`, `revised`); send `validated` through `_finish`. Add a test beside the authored one, and reword the spec's "whatever stage it stands at".
  - Grade Minor: `plan new` without `--no-confirm` is the interactive path, and the plan stays on disk and unchanged.

### m2 stale `dryrun.jsonl`: FIXED for the named case

- `test_a_blocked_dry_run_leaves_no_dryrun_jsonl_of_the_last_one` passes, and fails (1 failed) with `Path.unlink` made a no-op for `dryrun.jsonl`. The unlink is idempotent (`missing_ok`), the `dryrun/` run directory stays, and a kill between the unlink and the commit resumes into the same branch.
- **N3 (Note): the invariant "`dryrun.jsonl` equals `PlanRecord.dry_run`" still breaks on one other path.** `_archive_round` (`director.py:2148`) clears `record.dry_run` at the start of `plan review` but leaves `dryrun.jsonl`. When the round then pauses or fails before stage 5 (a rate limit in stage 3, the common case), the file holds the old cells while the record holds none. Probe: a runnable plan, `plan.md` edited, every `review:*` call set to `rate_limit`, `plan review` exits 3 with `record.dry_run == 0` and `dryrun.jsonl` still 4 lines (`rr_probes.out` in the m2 run). Nothing reads the file, as the review found, so this stays a Note; the one-line fix is the same unlink in `_archive_round`.

### m3 missing paths: FIXED

All usage errors, exit 2, `SystemExit`, naming the argument and the path (`rr_probes_fast.out`):

- `plan diff <missing>` (BUNDLE), `plan diff <good> <missing>` (OTHER), `plan diff <dir with no plan.json>`, `plan diff <a file>`, the same two with the second argument.
- `plan new q? --request <missing>` and `--request <a directory>`.
- `plan validate <missing>`, `plan continue <empty dir>`, `plan review <a file>`.
- `plan new --request <bad YAML>` and `<schema-invalid YAML>` exit 2 through the existing `except ValueError` (unchanged).
- `plan diff <good> <good>` exits 0 with an empty diff; `plan diff <good>` still prints the world diff.

### m4 `--plans-root` help: FIXED for `plan`; the pre-existing flags still leak

Every command's `--help` was run with `COLUMNS=400` (`test_m4...`, in `rr_probes_fast.out`) and checked for the home folder name, the repo root and any absolute drive path.

- Clean: the root, `list-strategies`, `plan`, `plan new`, `plan continue`, `plan review`, `plan validate`, `plan diff`. `plan new --help` shows the default as `<repo>/plans`.
- Still printing the home path (the pre-existing `--runs-root` and `--results-root` defaults, as the fixer says): `analyze`, `doctor`, `promote` (both flags), `readme-results` (both), `replay`, `run`, `show`. Seven commands, not just two flags. The same `show_default=` fix applies; it stays a final-review carry as the ruling scoped.
- `test_plan_new_help_holds_no_home_folder_name` checks `plan new` only.

### m5 parity compares ledger and transcripts: FIXED, and it bites

- `ledger_ids` compares each plan-ledger line's conversation id (less the `plan/<slug>/` prefix) and status, in file order. It cannot compare ledger bytes, since a line carries a timestamp (`LedgerLine.ts`), and the review asked for exactly these two fields. `transcript_bytes` compares every file under `transcripts/` byte for byte, rounds included.
- Mutation `transcript` (a transcript rewritten over an existing file keeps its attempts twice): the 24b1903 parity test passes at K4 (1 passed); the new one fails at K4 on `transcripts/author-planner-2.json`.
- Mutation `ledger` (`Director._drop_dead_lines` a no-op): the 24b1903 test passes at K4; the new one fails at `test_plan_parity.py:66` (the ledger ids differ at index 4: `author/planner/2/a1` against `author/planner/3/a1`, one extra line).
- Without a mutation, K4 passes on the new test (20 s). The fixer reports all 15 points passing; I ran K4 only.

## Other notes

- **N2 (Minor, new): `test_a_missing_path_is_a_usage_error_with_no_traceback` depends on the temp path's length.** The Rich error panel wraps at 80 columns and folds a long path mid-word, so `"nowhere" in result.output` fails when the fold lands inside it. With a long `--basetemp` (about 130 characters) the BUNDLE and OTHER cases fail (2 failed); with the default temp folder all 3 pass. Fix: run the invoke with `env={"COLUMNS": "400"}`, as the help test does, or assert on the argument name and a short fixed name.
- **N4 (Note):** the stop message still says "plan.md is yours to edit now and stage 2 adopts the edit" for a plan past stage 2 (the fixer's concern 4). It reads wrongly for `authored` and later; reword with N1.
- **N5 (Note, concern 3 of the report):** a `BundlePathError` no longer prints as `error:`. By reading, no CLI path lets one escape: `hashed_paths` skips links and `validate` turns `bundle_hash`'s into `DirectorError`. Not exercised with a real link.
- **N6 (Note, pre-existing, found by the probe):** editing a committed manifest call's transcript reply so that it no longer parses makes `plan continue` die with `TypeError: 'NoneType' object is not iterable` (`director.py:1439`, `_copy_worlds` on a `None` manifest). It was a traceback before this round too (a `TypeError` was never caught); recorded for the final review.

## Checks run

- `uv run pytest -p rr_mut -q tests/test_plan_cli.py tests/test_plan_records.py tests/test_store.py -k "planted_bug or schema_invalid or missing_path or help_holds or damaged_plan_json or damaged_line or drop_dead_attempts or mid_file"`: 11 selected, 9 passed and 2 failed under a long `--basetemp` (the 2 are N2 only); the 3 `missing_path` tests then passed on their own with the default temp folder. `blocked_dry_run_leaves` and `authored_plan_prints_the_stop` (slow): 2 passed.
- Mutations (all by plugin, the checkout untouched): `blanket` (RED 1, the planted-bug test), `hold_unlink` (RED 1, the m2 test), `transcript` and `ledger` against the new and the old parity suite (new RED, old green).
- Real-process cases: 20 (`i1_cases*.out`). CliRunner probes: `test_rr_probes.py`, outputs in `rr_probes*.out`. The m1 probe ran a full plan through `validated` on the doubles; no real model was reachable (`PlanProviders` was the stub factory throughout).

## Files

All under `.superpowers/sdd/2026-11-14-phase-5-director/probes-task9-rereview1/`: `prep.py`, `case.py` (real-process cases), `test_rr_probes.py`, `rr_mut.py` (mutation plugin), `test_old_parity.py` (24b1903's suite with the fixture import added), and the outputs `i1_cases.out`, `i1_cases2.out`, `i1_cases3.out`, `rr_probes_fast.out`, `rr_probes_m1.out`, `rr_probes.out`, `parity_mut.out`, `fix_tests.out`. The `.out` files hold local paths from the machine (they are probe logs, not committed material).

## Disk

2.1 GB free at the start; 2.9 GB at the end (outside activity as well). Every base bundle, work copy and basetemp was removed.
