# Task 9 review: stage 5, the `plan` sub-app and the parity suite

Task-scoped gate on 9ca91d4..24b1903 (one commit, 24b1903). The checkout was left read-only: every mutation is applied at import time by a pytest plugin, and every bundle lives under pytest's basetemp or the session scratchpad. Probes are in `probes-task9/reviewer/`. The full suite was not re-run.

## Verdicts

- **Spec compliance: PASS, with one Important finding.** Every binding point holds:
  - resume parity at every kill point, including my own 15 real hard kills plus 6 targeted ones, all equal;
  - a rate limit pauses and never degrades;
  - `continue` refuses after open blocks, with the message;
  - `validate` is never `runnable` with open blocks;
  - a damaged record (a bad byte, bad JSON, a mid-file ledger line) prints its file and line;
  - no real model call;
  - no real name in the diff.

  Every carry's test bites (mutation table below). The ASSUMED re-archive rule departs from the brief's wording. It is needed for parity and is consistent with the spec's one-pass revise rule (Q3 below).
- **Quality: PASS WITH FIXES.** Fix the Important finding, I1 (the blanket `ValueError` catch), before Task 10 builds on the sub-app. The Minors can ride with it or go to the final review.

Counts: Critical 0, Important 1, Minor 5, Note 4.

## Findings

### Important

**I1. The CLI turns every `ValueError` into `error: ...` with no traceback, which hides real defects (named risk 1).** `claude_bully/planner/cli.py:202` (`_plan_errors`: `except (DirectorError, ValueError)`).
- Probe P1: `lint_bundle` was patched to hit a genuine bug (`int("not-a-number")`), then `plan validate` was run on the good bundle.
  - It prints `error: invalid literal for int() with base 10: 'not-a-number'` and exits 1.
  - `result.exception` is `SystemExit`. There is no traceback and no frame, so nothing points at `lint_bundle`.
  - The validate stage is left `open` in plan.json.
- Probe P1b: the same path raising `KeyError` keeps its traceback. The mask applies only to the `ValueError` family. That family includes pydantic's `ValidationError`, `json.JSONDecodeError` and `UnicodeDecodeError`, which are exactly what a code bug in record building raises.
- Probe P1c, beside it: a `plan.json` that is valid JSON but fails `PlanRecord` (`open_blocks: "three"`) prints `error: 1 validation error for PlanRecord ...` with neither the file nor a line. That damaged record falls outside the new section-13 row, and the blanket catch hides it.
- Recommendation: catch only a named type.
  1. Add `DamagedRecordError(ValueError)`, for example in `runner/store.py`. Subclassing `ValueError` keeps every existing `except ValueError` caller and every `pytest.raises(ValueError, match=...)` working.
  2. Raise it from `read_plan_record` for the UTF-8 and JSON cases (`records.py:200-210`). Also wrap `PlanRecord.model_validate` (`records.py:216`) so a schema-invalid file names the file and the first error's `loc`.
  3. Raise it from `parsed_lines` for mid-file damage.
  4. In `_plan_errors`, catch `(DirectorError, DamagedRecordError)`. `BundlePathError` is already a `ValueError`; add it explicitly if a bundle link should print cleanly.
  5. Check that `new`'s own `except ValueError` around `request_from_flags` (`cli.py:298`) still covers the flag errors. It does, since that `try` is separate.

  Then a test that a planted non-record `ValueError` reaches the runner as an exception, not as `SystemExit`. The implementer raised the same concern (report, Concerns 1).

### Minor

**m1. `plan new` without `--no-confirm` on a slug past stage 1 but not runnable exits 1 and prints only the status.** `claude_bully/planner/cli.py:303`.
- Probe P2: a plan run through stage 2 (`authored`), then `plan new --request <same>` with no `--no-confirm`.
  - Output `status authored`, exit 1.
  - The stages are unchanged (`stop_after_plan` held, which is correct), but no stop message is printed.
- D-exit says a stop the owner asked for exits 0 and says how to go on. The check keys on `record.status == "planned"` rather than on the run having returned at stage 1.
- Fix: when `not no_confirm` and the record is neither `runnable`, `failed` nor held by open blocks, call `_stopped` (exit 0). Add a test.

**m2. A stage 5 that runs no dry run leaves the previous `dryrun.jsonl` on disk (named risk 4).** `claude_bully/planner/director.py:2038`.
- Probe P3:
  1. A runnable bundle has 4 cells.
  2. The ladder is broken so that `ladder_walk` fails. `plan validate` gives `validated`, `record.dry_run == []` and `dry_run_id None`, but `dryrun.jsonl` still holds the same 4 lines, byte for byte, and `dryrun/dryrun-1e4f83d89f9b/` stays.
- Can a later validate or review read it as current? **No.**
  - Nothing in the package reads `dryrun.jsonl`. It is only written (`dryrun.py:737`).
  - `bundle_lints` excludes it from its scans (`_HARNESS_RECORDS`). The reviewer and confirm builders refuse it.
  - `dry_run` always rewrites it from the run directory.
  - After the break was reverted, the hash returned to `dryrun-1e4f83d89f9b`. The old directory was read again (K13's rule) and its cells equal a fresh bundle's. The reuse is correct, because the content is identical.
- It still contradicts spec section 10 ("`dryrun.jsonl` is rewritten whole ... it is derived, never a second source") and section 15 ("`dryrun.jsonl` equals `PlanRecord.dry_run`"). A person or Task 12's CI scan of a checked-in bundle would read cells for content that no longer exists.
- Fix: in the blocked branch, write an empty `dryrun.jsonl` with `write_atomic`, or unlink it, and keep the run directory. Add a test beside `test_no_dry_run_when_schema_or_ladder_walk_fails` that starts from a runnable bundle.

**m3. Missing paths give raw tracebacks.** `claude_bully/planner/cli.py:54`, `:265` and `:354`. These are the very tracebacks that I1 hides for `ValueError`.
- Probe edges:
  - `plan diff <missing>` raises `FileNotFoundError` uncaught.
  - `plan diff <good> <missing>` raises `FileNotFoundError` uncaught.
  - `plan new q --request <missing>` raises `FileNotFoundError` uncaught.
- (`validate`, `continue` and `review` on a folder with no plan.json give a clean usage error, exit 2.)
- Fix: give `typer.Option(exists=True, dir_okay=False)` to `--request`. Give `diff` the `_opened`-style `plan.json` check for `bundle`, and `exists=True, file_okay=False` for `other`.

**m4. `plan new --help` prints the `--plans-root` default as the machine's absolute path, which holds the account's home folder name.** `claude_bully/planner/cli.py:275`.
- The report shows it as `<repo>/plans`, but the live help prints the full path (`probes-task9/reviewer/help.out`).
- It is runtime output, not a committed file, and `--runs-root` already does the same. Still, a pasted help block would carry a real name.
- Fix: `show_default="plans/"`. The same fix suits `RunsRoot` and `ResultsRoot` at the final review.

**m5. The CLI parity suite compares less than the sweep does.** `tests/test_plan_parity.py:835-844` (diff lines).
- It compares hashed files, `bundle_hash`, `comparable(record)`, the `resumed` count and the cache-key subset.
- `transcripts/` and `ledger.jsonl` are in `HASH_EXCLUDES`, so neither the transcript bytes nor the plan ledger are compared through the CLI. The earlier tasks' narrower point tests compare the ledger.
- Fix: add the plan ledger's `(conversation id, status)` lines and the transcript bytes to the parity assertion. My sweep compares both and found them equal, so this is cheap insurance, not a known gap.

### Notes

- **N1. The open-block hold is doubled.** It sits in `_refuse_open_blocks` (`cli.py:220`) and in `Director.run` (`held_by_open_blocks`). Removing the CLI's copy alone survives (my mutation `cli_hold_only`, as the report's M6 found). That is because `run` holds too, and `_report` then prints the same `failed: <n> open block(s)` line, so behaviour is unchanged. Either drop the CLI copy or keep it as defence in depth. It is not a defect.
- **N2. The `all_strategies` to `listed_strategies()` change cannot be observed** (mutation `all_strategies` survives, 17 tests). `listed_strategies` drops only `Composed` (`premise+pressure` names) and leading-underscore names, and the bundle grammar admits neither `+` nor a leading `_`. The carry is met by code reading, as the report says.
- **N3. Stage 5's scan sits only in the dry-run branch.**
  - A bundle that fails `schema` and also holds a real name records the name as a `real_name_bundle` fail and ends `validated`.
  - A bundle that loads and holds a real name fails the stage (`failed`) through `_scan_bundle`, with no `lint_results` recorded.
  - Both stop the plan, but the two ends differ for one fault. Worth one line in the spec's stage-5 order if kept.
- **N4. The fix that makes a committed fire own its generator ledger lines keys on the document id** (`dryrun.py:652`). That is sound while a fire's document ids are unique within a rep, which holds today because the ids carry the turn. If a later phase lets two fires plan the same id, a dead attempt's line could be kept. It is cheap to assert in `_rep_owners`.

## Named risks

### 1. The blanket ValueError catch

This is I1. Recommendation: catch a named `DamagedRecordError(ValueError)` (plus `DirectorError`). Every other exception then shows its traceback.

### 2. Every carry has a test that bites

`probes-task9/reviewer/mutplug.py` and `run_mutations.sh`, output in `mutations.out`. Each mutation is applied at import, and the checkout is untouched.

| Carry | Mutation | Test run | Result |
| --- | --- | --- | --- |
| (baseline, no mutation) | none | `planned_slug_stops_again`, `damaged_plan_json` | pass |
| `stop_after_plan` on a committed stage 1 stops | the committed-stage-1 stop dropped | `test_plan_new_again_without_no_confirm_on_a_planned_slug_stops_again`, `test_stop_after_plan_on_a_committed_plan_stops` | RED (2) |
| M-1 own-id cache | `_own_cache` back to Task 5's rule | `test_a_resume_reads_only_its_own_ids_generated_cache` | RED |
| M-4 the message names the document | `buried_search_docs` emptied | `test_a_stray_buried_search_hit_fails_and_the_shipped_overlay_passes` | RED |
| `dry_run` only after `schema` and `ladder_walk` | guard gone | `test_no_dry_run_when_schema_or_ladder_walk_fails` | RED (2) |
| the same, `ladder_walk` half | `_DRY_RUN_NEEDS` schema only | the same | RED (1 of 2) |
| Stage 5 runs `_scan_bundle` | the stage-5 call made a no-op | `test_stage_5_runs_the_denylist_scans_before_the_dry_run` | RED |
| `validate` never `runnable` with open blocks | `open_blocks` ignored at commit | `test_a_validated_bundle_that_is_not_runnable_exits_1` | RED |
| `continue` refuses after open blocks | both holds gone | the same | RED |
| (the same) | the CLI's hold alone gone | the same | survives (N1) |
| Damaged record names file and line | the old `read_plan_record` | `test_a_damaged_plan_json_is_named_with_its_line_and_no_traceback` | RED |
| ASSUMED re-archive rule | the brief's "any committed review" rule | `test_a_review_round_paused_in_stage_4_is_resumed_not_archived_again` | RED |
| `all_strategies` filtered | `all_strategies()` back | `tests/test_director_author.py -k "persona or strateg or manifest"` (fast) | survives, as expected (N2) |

- **M-5:** the contract is stated in `dry_run`'s docstring and in the spec's "As planned" section. The rate-limit test now also compares the generated documents' titles and bodies, and asserts some exist. This was checked by reading.
- **Reuse, not copy:** `review_scans(` is called once in the package, inside `Director._scan_bundle` (`director.py:1429`). Stage 5 calls `_scan_bundle("the dry run")` (`director.py:2030`).
- **Mid-file ledger damage:** `test_a_mid_file_ledger_damage_is_named_with_its_line_and_no_traceback` asserts the file, the line and `SystemExit`. It was read, not mutated, since `parsed_lines` is Task 7b's.

### 3. The four sweep faults

1. **The torn tail of the dry run's ledger** (`dryrun.py:631`, `parsed_lines`).
   - It is minimal: the same torn-tail rule as the plan ledger. Mid-file damage still raises, naming the line, so no damaged state is hidden.
   - The extra rewrite when the last line lacks its newline is harmless, and redundant with `Ledger.write`'s own newline repair.
2. **A committed fire owns its generator lines** (`dryrun.py:652`).
   - It is minimal: it is consulted only for a line the turn-owner rule would drop, and it returns None for every line that is not a generator line.
   - It does not mask a dead attempt as long as document ids are unique per fire (N4).
3. **`_readopt`** (`director.py:1143`, `adopted_here`).
   - It is minimal: an `edited` entry can leave only when this stage's own recorded input differed from its committing call. That is what an unbroken open does, since `_adopt_edits` only adds.
   - Task 7b's M2 case (plan.md put back after a failed scan) still leaves, because plan.md is in `adopted_here` and no longer differs.
4. **The ASSUMED "plan review archives only a round that has run out"** (`director.py:2110`, `_round_finished`). Quoted rules:
   - Spec section 7, stage 4: "Status `revised`; a plan with `open_blocks > 0` is `failed`, and the owner edits the bundle and runs `plan review`. There is no second revision call (docs/08: one pass)."
   - Spec section 7, "The commands' reach": "`plan review` reruns stages 3, 4 and 5 on an edited bundle; the old `review.md` goes to `transcripts/review-<n>.md`. Both adopt hand edits at their start (`edited`)."
   - The plan's D-rounds: "`plan review` archives only when the current stage list holds a committed `review` stage; otherwise (killed after (2), or a round in progress) it finishes (3), which is idempotent ..., and runs on."
   - The plan's D-revise-error: "`plan continue` on a plan whose stage 4 is committed with `open_blocks > 0` prints the reason and exits 1 without a call ...; `plan review` and `plan validate` still run."

   The ASSUMED archives when the review stage is committed and the round is over: stage 5 is committed or failed, or stage 4 committed holding open blocks. The second case is the one-pass rule's end of a round. A round that is still open is resumed: review committed, with stage 4 open, failed by a provider error, or committed clean with stage 5 not yet done.

   Under the brief's wording, `plan review` run again after a kill or a rate limit in stage 4 would archive a half-finished round, including an open revise `StageRecord`. That breaks the binding parity point; my mutation `archive_any_committed_review` turns M16's test RED. So the refinement is required, not just allowed. It does not mask a state:
   - a stage 3 or stage 4 that failed resumes as `plan continue` would (D-revise-error's retry);
   - a stage 5 that failed is archived, and the next round reviews the owner's fix.

   Its one cost is that an edit made during a paused round is adopted by the resumed stage rather than reviewed. The next `plan review` reviews it, and `plan validate` stamps unreviewed edits by design anyway. The spec's "As planned" D-rounds line records the refinement, which is acceptable.

### 4. The stale `dryrun.jsonl`

See m2: it is stale, it is read by nothing, and the run directory is reused only for byte-identical content.

### 5. Help, flags and exit codes against the spec

Live help is in `probes-task9/reviewer/help.out`.
- `new` has every flag of spec section 11: `--targets`, `--budget`, `--scope`, `--hypotheses`, `--constraint` (repeatable), `--request`, `--slug`, `--world`, `--base-world`, `--seed`, `--no-confirm`, `--plans-root` and `--wait-on-rate-limit`.
- `continue` and `review` take `--wait-on-rate-limit`. `validate` has none, as the spec says (no model call). `diff` takes `[other]` and `--worlds-dir` (Q48).
- Exit codes: 0 when runnable, or when stopped after stage 1 as asked (D-exit, with the m1 edge); 1 otherwise; 3 for a rate limit (`_drive`, which goes through `runner/wait.wait_on_rate_limit`).
- The rate-limit message matches `run`'s shape ("Progress is saved; retry the same command after ..."). `test_a_review_round_paused_in_stage_4_is_resumed_not_archived_again` exercises the real in-process wait (`slept == [60.0]`).
- `diff` prints no cell or status line (ASSUMED, recorded in D-exit).
- **Q46 is gone:**
  - `RATE_LIMIT_EXIT_CODE` and `WaitMinutes` live in `runner/wait.py`, which imports neither CLI.
  - Nothing under `claude_bully/` imports `claude_bully.cli`.
  - `import claude_bully.planner.cli` then `import claude_bully.cli` works in a fresh interpreter, and `cli.RATE_LIMIT_EXIT_CODE` resolves to 3 (the same `WaitMinutes` object).
  - Importing `runner.wait` loads neither CLI.

### 6. My hard-kill sweep

The probe is `probes-task9/reviewer/kill_sweep.py` with `kill_driver.py`; output is in `kill_sweep.out` and `kill_sweep_targeted.out`. It was written independently of the implementer's sweep:
- **Real kills:** each runs in a fresh process with `os._exit(137)`, so no handler, `finally` or temp-file cleanup runs.
- **Events:** every `os.replace` in the process counts as a kill point. That covers every `write_atomic` anywhere: the bundle, plan.json, the marker, the Director's cache, the dry run's run store and env state, the `OWNER` file and `dryrun.jsonl`. The kill lands after the temp file is written and before the rename. Every `Ledger.write` also counts, killed after half the line is appended with no newline.
- **Setup:** one base plan through `plan new --no-confirm`, runnable, then `plan.md` edited, so that both commands run a full dry run, and `review` a full round.
- **Compared, against the same command unbroken, after the same command was run again:**
  - status, hashed files and `comparable(record, ignore_dry_run_resume=True)`;
  - `resumed` (at most one more);
  - `dryrun.jsonl` without the resume flag, and the names of the dry-run directories;
  - every transcript's bytes, `round-1/` and `review-1.md` included;
  - the plan ledger's `(id, status)` lines, the marker, every `*.tmp` under the plans root, and the cache keys as a subset.
- Each copy was deleted as soon as it was compared.

| Scenario | Events | Kills (event: what) | Equal |
| --- | --- | --- | --- |
| `plan validate`, edited runnable plan | 305 | 1 plan.json (stage open), 2 `dryrun/_cache/OWNER`, 78 and 154 dry-run ledger torn, 229 a rep's env_state, 305 plan.json (commit) | 6 of 6 |
| `plan review`, edited runnable plan | 350 | 1, 2, 3 archive copies of round-1 transcripts, 61 and 292 dry-run ledger torn, 119 env_state, 177 and 234 a rep's attempt marker, 350 the commit | 9 of 9 |
| `plan review`, targeted (beyond the 15) | 350 | 7 `review-1.md` copy (before the `archived` checkpoint), 8 the archive record write (2), 11 the first review call's ledger line torn, 25 stage 3's commit after its render, 31 `plan.md` written by a revise call, 46 stage 4's commit | 6 of 6 |

Total: 15 of 15 equal in the asked sweep, and 6 of 6 at the targeted archive, stage 3 and stage 4 writes: 21 real kills, 0 mismatches. Every killed process exited 137, and every resume ended with exit 0 and status `runnable` on its first try.

## Other checks

- **No real model call:** the CLI tests and parity suite patch `PlanProviders` with `StubFactory`, and the dry run uses its own doubles. The one `build_provider` test runs the fake claude (`tests/fixtures/fake_claude.py`), and `no_real_providers` is session-wide.
- **No real names:** the diff holds no name, and no address outside the reserved domains. The commit author line is the machine's git name, as on every earlier Phase 5 commit, so it predates this task. The one name leak is the m4 help default.
- **Stage 5 order** (`director.py` `validate`) matches the brief and the spec's "As planned" line: open with adoption, replacing a committed or failed record; leftovers; the static lints; the guard; the scan; the dry run; the record write; the K13 checkpoint; the lints with the cells; then `lint_results`, `bundle_hash`, the marker clear and the commit. `runnable` requires no fail and `open_blocks == 0`.
- **Docs-sync:** docs/00 section E (V24) and section H ("version 3, additive", `buried_search_docs`), docs/08's CLI and exit codes, the spec's section 13 row and its "As planned" Task 9 block, and the HANDOFF progress line are all present.

## Probes

All are in `probes-task9/reviewer/`:
- `help.out`: live help of every command.
- `test_reviewer_probes.py` and `probes.out`: P1, P1b, P1c (the ValueError mask), P2 (`new` again on an authored plan), P3 (the stale `dryrun.jsonl`).
- `test_reviewer_edges.py` and `edges.out`: missing paths and bad flags.
- `mutplug.py`, `run_mutations.sh` and `mutations.out`: the carry mutations.
- `kill_driver.py`, `kill_sweep.py`, `kill_sweep.out`, `kill_sweep_targeted.out`, and `events_validate.txt` / `events_review.txt`: the hard-kill sweep and its event lists.

## Disk

- Start: 2.21 GB free.
- Mid-review: 2.06 GB.
- End: 2.06 GB.

Every basetemp and sweep root was removed after its run.
