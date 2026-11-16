# Task 9 report: stage 5, the `plan` sub-app and the whole parity suite

Status: DONE. One commit on 9ca91d4: 24b1903 "feat: Phase 5 Task 9, stage 5, the plan sub-app with --wait-on-rate-limit, and resume parity at all thirteen kill points" (author rankinbc1@gmail.com; not pushed). Gate: ruff format --check clean, ruff check clean, mypy (strict) and mypy --platform linux clean; `uv run pytest -q -W error` 10659 passed, 11 skipped, 188 deselected (16:47); `uv run pytest -q -m slow` 188 passed (18:59). Before: 10646 / 11 / 159 and slow 159; +13 fast, +29 slow, -1 slow (Task 7a's not-built-yet case, obsolete).

## What was implemented

- `claude_bully/planner/director.py`
  - `Director.validate()`, stage 5, in the brief's order:
    - the stage is opened with its `inputs` and the hand edits are adopted; a committed or failed validate record is replaced in that same write (R-validate-status); an open one is entered again;
    - `remove_leftovers`, then the static `lint_bundle`;
    - no dry run when a `schema` or `ladder_walk` result fails. The `dry_run` lint's result says `not run: the bundle does not load` or `not run: a ladder's firing examples do not walk it to its top rung`, and `dry_run` and `dry_run_id` are emptied;
    - otherwise `_scan_bundle("the dry run")` runs (the stage 2 to 4 path, reused; a hit fails the stage), then `dry_run`; `dry_run` and `dry_run_id` are written, the `dryrun` checkpoint fires, and `lint_bundle(dry_run=cells)` runs;
    - finally `lint_results`, `bundle_hash`, `clear_attempt` and the commit. The status is `runnable` when nothing fails and `open_blocks == 0`, else `validated`.
  - `Director.revalidate()` is `plan validate`. It is refused until stage 4 commits. It clears hard kills, resumes an open validate stage as `run` does, and fails the stage on a `DirectorError`.
  - `Director.review_round()` is `plan review` (D-rounds). It is refused until stage 2 commits. A round that has run out is archived in the three ordered writes, with the `archived` checkpoint between (1) and (2). (3) runs every time and is idempotent. Then `run(through="validate")`. A round has run out (`_round_finished`) when stage 5 is committed or failed, or stage 4 holds open blocks; a round in progress is resumed. A dead attempt that the last stage's marker names is recorded before the archive.
  - `held_by_open_blocks(record)` holds on stage 4 and `open_blocks`, never on status. `run` uses it.
  - `_commit_stage(status=)` replaces `failed=`.
  - `Director.new` names the request fields that differ.
  - The manifest's persona check reads `listed_strategies()`.
  - `run`'s `NotImplementedError` case is removed.
  - `_readopt` fix (see "Sweep findings").
- `claude_bully/planner/cli.py` (new) holds the following:
  - `plan_app` and its five commands;
  - `request_from_flags`, `cell_line`, `bundle_diff` and `world_diff`;
  - the seams `PlanProviders`, `WORLDS_DIR` and `PlanCheckpoint`, all read at call time;
  - the shared helpers: `_plan_errors` (a `DirectorError` or `ValueError` becomes `error: ...` and exit 1), `_drive` (`wait_on_rate_limit`, else exit 3), `_refuse_open_blocks`, `_report` and `_finish`.
- `claude_bully/cli.py` mounts the sub-app with `app.add_typer(plan_app, name="plan")`. It re-exports `RATE_LIMIT_EXIT_CODE` and `WaitMinutes`, which moved to `runner/wait.py` (Q46).
- `claude_bully/planner/records.py`
  - `read_plan_record` raises `ValueError` naming the file and the line for a byte that is not UTF-8 or text that is not JSON. This is the damaged-record carry.
  - `DryRunCell.buried_search_docs` is new, default `[]` (M-4).
- `claude_bully/planner/dryrun.py`
  - M-1: `_own_cache`, using `dryrun/_cache/OWNER`.
  - M-4: `_buried_hits` returns the ids.
  - M-5: the cell-level contract is stated in `dry_run`'s docstring.
  - Two resume fixes from the sweep, both in `_drop_dead_lines` (see "Sweep findings").
- `claude_bully/planner/bundle_lints.py`: the stray-hit message names the documents (M-4).
- `claude_bully/planner/bundle.py`: `hashed_paths(root)`.
- `claude_bully/paths.py`: `DEFAULT_PLANS_ROOT`.
- `tests/fixtures/director_stub.py`:
  - `run_plan(via_cli=, dryrun_kill=)` and `_run_via_cli`. A kill that never fires raises, so a dead seam cannot pass.
  - `dryrun_killing` and `DRYRUN_KILL_AT` (Task 5's `_killing`, now shared).
  - `first_sentence` splits a CRLF paragraph break. Python text mode writes the owner's plan.md edit as CRLF on Windows.

## Tests

New files:
- `tests/test_plan_cli.py`: 25 tests (13 fast, 12 slow);
- `tests/test_plan_parity.py`: 15 slow.

Changed files:
- `tests/test_dryrun.py`: 3 new slow tests; the stray-hit test asserts the named document; the rate-limit test compares the generated bodies;
- `tests/test_director_primitive.py`: the obsolete not-built-yet test is removed;
- `tests/test_director_review.py`: one stale comment.

RED:
- The brief's step 2, with the sub-app absent: `ModuleNotFoundError: No module named 'claude_bully.planner.cli'` at collection.
- Every added behaviour was mutated back in `probes-task9/mutations.py`. Final run, `probes-task9/mutations_final.out`:

| Mutation | Test that bites | Verdict |
| --- | --- | --- |
| M1: the cache owner check gone (M-1) | `test_a_resume_reads_only_its_own_ids_generated_cache` | RED |
| M2: the stage 5 scan gone | `test_stage_5_runs_the_denylist_scans_before_the_dry_run` | RED |
| M3: the no-dry-run guard gone | `test_no_dry_run_when_schema_or_ladder_walk_fails` (2) | RED |
| M4: plan.json's line naming gone | `test_a_damaged_plan_json_...` | RED |
| M5: the stray hit's document unnamed (M-4) | `test_a_stray_buried_search_hit_...` | RED |
| M6: the CLI's open-block exit gone | (survives: `run` holds too) | SURVIVED, by design |
| M6b: `run`'s hold gone | Task 8's `test_a_plan_with_an_open_block_goes_no_further_than_stage_4` | RED |
| M6c: both holds gone | `test_a_validated_bundle_that_is_not_runnable_exits_1` | RED |
| M7: the validate record not replaced | `test_plan_continue_and_validate_and_review` | RED |
| M8: no archive | the same test | RED |
| M9: no `archived` checkpoint | `test_a_review_round_killed_between_the_archive_copy_and_the_record_resumes` | RED |
| M10: write (3) gone | `test_a_review_round_drops_the_top_level_transcripts_no_call_names` | RED |
| M11: `PlanCheckpoint` not passed | parity K5-manifest and K13 ("the kill point was never reached") | RED |
| M12: runnable despite open blocks | `test_a_validated_bundle_that_is_not_runnable_exits_1` | RED |
| M13: the differing field not named | `test_plan_new_on_an_existing_slug_with_another_request_is_refused` | RED |
| M14: a torn ledger tail raises | `test_a_torn_last_ledger_line_is_dropped_and_the_resume_goes_on` | RED |
| M15: a committed fire's lines dropped | `test_a_kill_after_a_fire_commits_keeps_the_fires_ledger_lines` | RED |
| M16: every committed review archived | `test_a_review_round_paused_in_stage_4_is_resumed_not_archived_again` | RED |
| M17: the old readopt | `test_a_review_round_killed_in_stage_5_keeps_an_edit_an_earlier_stage_adopted` | RED |

GREEN:
- focused: `tests/test_plan_cli.py`, `tests/test_plan_parity.py` and `tests/test_dryrun.py`, all passing;
- `tests/test_director_{author,review,primitive}.py`: 166 passed after the readopt change;
- then the gate.

## Files changed

Modified:
- `claude_bully/cli.py`, `claude_bully/paths.py`, `claude_bully/runner/wait.py`;
- `claude_bully/planner/{bundle,bundle_lints,director,dryrun,records}.py`;
- `tests/fixtures/director_stub.py`, `tests/test_director_primitive.py`, `tests/test_director_review.py`, `tests/test_dryrun.py`;
- `HANDOFF.md`, `docs/00-RECONCILED.md` (sections B, E, H), `docs/08-DIRECTOR.md`;
- `docs/superpowers/specs/2026-11-14-phase-5-director-design.md` (section 13 row, "As planned" Task 9).

New:
- `claude_bully/planner/cli.py`, `tests/test_plan_cli.py`, `tests/test_plan_parity.py`.

The README drafts are untouched: the brief names no README lines.

## ASSUMED

- ASSUMED: `plan validate` is refused while a stage before stage 5 is not committed, and `plan review` while stage 2 is not. Both exit 1 with nothing written. Otherwise a committed stage 5 under an uncommitted stage would let `plan continue` skip it.
- ASSUMED, refined from the brief: `plan review` archives only a round that has run out, meaning stage 5 committed or failed, or stage 4 holding open blocks. It does not archive on any committed review. The sweep showed why: `plan review` run again after a kill in stages 4 or 5, or waited on after a rate limit there, archived the round in progress and started a new one. A round in progress is resumed. Pinned by M16.
- ASSUMED: a stage 5 scan hit fails the stage and the plan (status `failed`), as at stages 2 to 4, and it does so before `lint_results` is recorded.
- ASSUMED: `plan diff` prints only the diff, with no cell or status line, and exits 0.
- ASSUMED: when a plan is `validated` the CLI prints each failing lint (`fail <id> <doc>: <message>`), and it prints a failed stage's error.
- ASSUMED: the fake-claude session test lifts `MAX_PLAN_CHARS`. The fake replies with the whole ~200k message, so each call would otherwise retry once and the log would hold 4 calls, not the brief's 2.
- ASSUMED: the parity suite runs a fresh clean plan per point, as the brief writes it, rather than caching one. That costs about 240 s of slow time. Each point's two bundles are removed in a `finally`.

## Help text (COLUMNS=100; the `--plans-root` default is the repo's `plans/`, shown here as `<repo>/plans`)

```
Usage: plan [OPTIONS] COMMAND [ARGS]...
 The Director: a research question to a validated run bundle.
 new       Plan a new bundle: stages 1 to 5, stopping after stage 1 unless --no-confirm.
 continue  Resume a plan at its first stage not committed and run it through stage 5.
 review    Review an edited bundle again: stages 3, 4 and 5.
 validate  Run stage 5 again on the bundle as it stands. No model call.
 diff      Diff two bundles' hashed files, or one bundle's worlds against the shipped ones.

Usage: plan new [OPTIONS] [question]
 Plan a new bundle: stages 1 to 5, stopping after stage 1 unless --no-confirm.
 On an existing slug with the same request it continues; with another request it is
 refused. Exit 0 runnable or stopped after stage 1 as asked, 1 not runnable, 3 rate limited.
 Arguments: question <str> The research question (or question: in --request).
 --targets <str>   Comma list of provider:model, or a bare claude_code model.
 --budget <str>    max_turns,n_per_cell,max_cells[,max_calls].
 --scope <str>     Comma list of the spec areas shown.
 --hypotheses <str> Comma list of data/hypotheses.yaml ids.
 --constraint <str> A free-text constraint. Repeatable.
 --request <path>  A request YAML file; each flag given overrides it.
 --slug <str>      The plan's directory name.
 --world <str>     reuse or fresh.
 --base-world <str> The shipped world to reuse.
 --seed <int>      The config's seed.
 --no-confirm      Go on past stage 1 without stopping.
 --plans-root <path> Where plans are written. [default: <repo>/plans]
 --wait-on-rate-limit <float> Wait inside the process for a rate window, up to this many minutes.

Usage: plan continue [OPTIONS] {bundle}
 Resume a plan at its first stage not committed and run it through stage 5.
 A plan held by open blocks after stage 4 is refused without a call: edit the bundle and
 run plan review. Exit 0 runnable, 1 not runnable, 3 rate limited.
 bundle <path> The plan's directory, plans/<slug>. [required]
 --wait-on-rate-limit <float>

Usage: plan review [OPTIONS] {bundle}
 Review an edited bundle again: stages 3, 4 and 5.
 The last round's review, revise and validate records and transcripts are archived first,
 under transcripts/round-<n>/. Exit 0 runnable, 1 not runnable, 3 rate limited.
 bundle <path> [required]   --wait-on-rate-limit <float>

Usage: plan validate [OPTIONS] {bundle}
 Run stage 5 again on the bundle as it stands. No model call.
 The lints, the stub dry run and the bundle hash. Exit 0 runnable, 1 not runnable.

Usage: plan diff [OPTIONS] {bundle} [other]
 Diff two bundles' hashed files, or one bundle's worlds against the shipped ones.
 With one bundle, each copied world is diffed against <worlds-dir>/<name> after a line
 saying whether the shipped world has moved since the copy.
 other <path> A second bundle to diff against.
 --worlds-dir <path> The shipped worlds, for one bundle (data/worlds).
```

## The parity suite's kill table (`tests/test_plan_parity.py`, through `plan new --no-confirm` then `plan continue`)

Every point ends `runnable`, with hashed files byte-equal to the clean plan's, an equal `bundle_hash`, an equal `comparable(record)` (`ignore_dry_run_resume` at K12 only), and the killed run's cache keys a subset of the clean run's. All 15 passed, about 240 s.

| Point | Killed | `resumed` |
| --- | --- | --- |
| K1 | the planner double crashes inside `plan` | 1 |
| K2 | inside `manifest` | 1 |
| K3 | inside `file:<DOC3>` | 1 |
| K4 | `Kill("transcript", file:<DOC1>)` | 1 |
| K5 | `Kill("record", file:<DOC1>)` | 0 |
| K6 | `Kill("files", file:<DOC1>)` | 0 |
| K7 | inside `repair:<REPAIRED>` (`close_fail` on its file) | 1 |
| K8 | the reviewer double crashes inside `review:lines` | 1 |
| K9 | inside `revise:<DOC1>` | 1 |
| K10 | the reviewer crashes inside `confirm:<DOC1>` | 1 |
| K11 | `Kill("stage", "author")` | 0 |
| K12 | the dry run's target double killed at its 3rd call (`dryrun_killing`) | 0; a cell `resumed_after_dead_attempt` |
| K13 | `Kill("dryrun", "validate")` | 0 |
| K5-manifest | `Kill("record", "manifest")` | 0 |
| K11-review | `Kill("rendered", "review")` | 0 |

Hard kills inside every write: `probes-task9/hard_kill_stage5.py`, adapted from the 7b fix-round-1 sweep. It kills inside `write_atomic` (half a temp file is written) and inside `Ledger.write` (a torn line), runs the same command again, and compares files, record, resumed, plan ledger, cache, transcripts, `dryrun.jsonl`, the dry run's directories, the marker, status and leftovers.

| Scenario | Writes | Result (final code) |
| --- | --- | --- |
| `validate`: `plan continue` from a plan whose stage 4 committed, i.e. stage 5 with its whole dry run | 305 | 305 kills, 305 equal |
| `revalidate`: `plan validate` on a runnable plan (record replaced; the dry run read) | 5 | 5 kills, 5 equal |
| `review`: `plan review` on an edited runnable plan. Writes 1 to 50 are the archive, stages 3 and 4 and stage 5's opening; writes 338 to 350 are stage 5's end | 350 | 1-50: 50 equal; 338-350: 13 equal |
| `review`, sampled middle (the round's dry run) | | 100-110, 200-210, 300-310: 33 kills, 33 equal |

## Sweep findings (fixed in this task, each pinned by a RED test)

1. A torn last line of the dry run's own ledger, from a kill inside its append, made every resume raise. `dryrun._drop_dead_lines` parsed each line with `model_validate_json`. It now uses `runner/store.parsed_lines`, the runtime's torn-tail rule:
   - the torn line goes;
   - a last line without a newline gets one;
   - mid-file damage raises, naming the line.

   Old code: 39 of 305 stage-5 kills failed this way. Pinned by M14.
2. A kill after a fire's `GeneratorFire` commit but before the turn's state write had moved `watched_through` dropped the committed fire's two generator lines. The kill landed inside the fire's cache put or inside the state write. The resume never redoes a committed fire, so `estimated_calls` came out 30 instead of 32. A generator line is now owned by a committed fire whose plans hold the document id named in its conversation id (`<conv>/generator/<doc_id>/<attempt>`). Pinned by M15.
3. `_readopt`, from Task 7b, dropped an `edited` entry that an earlier stage had adopted. The case: plan.md was edited before the round and adopted at its stage 3; the round's stage 4 revision made plan.md match its committing call; stage 5 was then killed and re-entered, and plan.md left `edited`. The unbroken open only adds, so it keeps the entry. Now only an entry the readopting stage itself adopted can leave. Task 7b M2's "plan.md put back" case still leaves. Pinned by M17.
4. The `plan review` re-archive, as covered under ASSUMED. Pinned by M16.

## Carries against their tests

| Carry | Test |
| --- | --- |
| `continue` after open blocks refuses with a message and never goes to validate | `test_a_validated_bundle_that_is_not_runnable_exits_1` (message; no call; no validate stage; still after `plan validate`) |
| `plan validate` never `runnable` with open blocks | the same test (`status validated`), M12 |
| `stop_after_plan` on a committed stage 1 stops | `test_plan_new_again_without_no_confirm_on_a_planned_slug_stops_again` (CLI); Task 7a's `test_stop_after_plan_on_a_committed_plan_stops` |
| Damaged record: the `ValueError` names the line; the CLI prints it, no traceback; section 13 row | `test_a_damaged_plan_json_is_named_with_its_line_and_no_traceback`, `test_a_mid_file_ledger_damage_is_named_with_its_line_and_no_traceback`; spec section 13 row added |
| M-1: a resume reads only its own id's cache | `test_a_resume_reads_only_its_own_ids_generated_cache` (M1) |
| M-4: the stray-hit message names the document | `test_a_stray_buried_search_hit_fails_and_the_shipped_overlay_passes` (M5) |
| M-5: the cell-level contract stated | `dry_run`'s docstring and the spec; `test_a_rate_limit_pauses_the_dry_run_and_the_same_call_resumes_it` compares the generated bodies |
| `dry_run` only after `schema` and `ladder_walk` pass | `test_no_dry_run_when_schema_or_ladder_walk_fails` (2 cases; M3) |
| Director code reads list-strategies' filter | `_entry_failures` uses `listed_strategies()`. The grammar admits no `+` and no leading `_`, so no test can tell the difference (stated in the spec) |
| Stage 5 runs the denylist scans through `_scan_bundle`, reused not copied | `test_stage_5_runs_the_denylist_scans_before_the_dry_run` (M2) |
| Stage 5 records the whole `lint_bundle` in plan.json | `test_no_dry_run_when_schema_or_ladder_walk_fails` (lint_results); the parity suite (`comparable`) |
| Parity at every kill point stage 5 adds, hard kills inside each write | K12 and K13 in the CLI suite; the sweep table above |
| A rate limit pauses, never degrades | `test_a_rate_limit_exits_3_and_the_same_command_resumes`, `test_a_review_round_paused_in_stage_4_is_resumed_not_archived_again` |
| Stub providers only | every test; the dry run's factory; the one fake-claude test |
| Q46: the names moved to runner/wait.py | `cli.RATE_LIMIT_EXIT_CODE` in the rate-limit test; both CLIs import |
| Q48: `plan diff --worlds-dir` | `test_plan_diff_of_two_bundles_...`, `test_world_diff_says_when_the_shipped_world_moved_and_shows_the_edit` |
| Q50: a resumed run's personas registered before `expand_cells` | Task 10's `run_experiment` change, not this task. For the dry run, `dry_run` opens `plan_personas` before it builds the experiment, so a resume (K12 through the CLI) and the fresh-interpreter validate test cover it |
| Q59: the shapes test asserts more than identity | Already closed in Task 3 (`tests/test_world_lines.py: test_every_importer_reads_the_one_shape_object`, renamed for what it pins, plus the shape-name set). No change here |
| Q68: slow marks | the rate-limit test is marked slow; no fast test here runs over 2 s |
| Q73: the Files list follows the git add | `tests/fixtures/director_stub.py` is in the commit |

## Disk

- Start: 2.4 GB free.
- After the parity suite: 2.8 GB.
- During the sweeps: 2.4 to 2.9 GB.
- End: 2.06 GB (`Get-PSDrive C`, after the two gate runs; pytest keeps its last basetemps).

Every kill root and parity bundle was removed as soon as it was compared, and probe output stays under 200 MB (`probes-task9/`, about 100 KB).

## Concerns

1. The CLI catches every `ValueError`, as the damaged-record carry asks. A genuine bug that raises `ValueError` therefore prints as `error: ...` with no traceback. A test double's `ValueError` showed up that way during this task, and it cost a debugging step.
2. The open-block hold is doubled: `_refuse_open_blocks` in the CLI and `held_by_open_blocks` in `run`. Each alone survives a mutation of the other (M6). Both are pinned only together (M6c), plus `run`'s by Task 8's test.
3. When stage 5 runs no dry run, `dryrun.jsonl` and any earlier `dryrun/` directory are left on disk; only `record.dry_run` is emptied. Both are excluded from the hash, but they are stale.
4. The parity suite adds about 240 s, and `tests/test_plan_cli.py` about 3 minutes, to the slow run.
5. Not examined: a torn tail in a real run's `runs/<id>/ledger.jsonl` (`Ledger.write` appends in text mode; the runtime's own resume of that file). Only the dry run's copy was fixed here.
6. `world_diff` walks with `rglob`, which follows links. Bundle links are refused everywhere else.

## Fix round 1

Commit 9639ab8 on 24b1903, branch build/v1, author rankinbc1@gmail.com (verified with `git log -1 --format=%ae`). Not pushed. Probes and RED output are in `probes-task9-fixround1/`.

### Changes

- **I1.** `runner/store.py` gains `DamagedRecordError(ValueError)`.
  - `parsed_lines` raises it for a line that is not the torn last line. The message names the file and the line, as before.
  - `planner/records.read_plan_record` raises it for a byte that is not UTF-8 (file and line), text that is not JSON (file and line), and an older plan schema.
  - Its `PlanRecord.model_validate` is wrapped. A schema-invalid file raises `<file>: field <loc>: <message>`, plus "(and N more)" when there are more errors.
  - `planner/cli._plan_errors` catches `(DirectorError, DamagedRecordError)` and nothing else. `BundlePathError` is not caught, per the ruling. The Director already turns its expected cases into `DirectorError`.
- **m1.** `plan new` without `--no-confirm` calls `_stopped` (exit 0) for any status except `runnable` and `failed`. A plan held by open blocks is refused before the run. So an `authored` plan now prints the plan, `stopped after stage 1: review <bundle>/plan.md, then run plan continue <bundle>`, and `status authored`.
- **m2.** In `Director.validate`'s blocked branch (no dry run), `dryrun.jsonl` is unlinked (`missing_ok`). The `dryrun/` run directory stays. It is read again only for byte-identical content (K13). Being unlinked, `dryrun.jsonl` always equals `PlanRecord.dry_run`.
- **m3.**
  - `--request` takes `exists=True, dir_okay=False`.
  - `plan diff` checks that `BUNDLE`, and `OTHER` when given, hold a `plan.json` (`_a_plan`, split out of `_opened`).
  - All three cases are now usage errors (exit 2).
- **m4.** `--plans-root` uses `show_default=PLANS_ROOT_SHOWN` (`"<repo>/plans"`).
- **m5.** `tests/fixtures/director_stub.py` gains `ledger_ids` and `transcript_bytes`. `tests/test_plan_parity.py` asserts both, after the hashed files.
- **Docs.**
  - Spec section 13's damaged-record row names the type, the field case, and the fact that other exceptions keep their traceback.
  - The spec's "As planned" Task 9 block gains a fix round 1 bullet.
  - docs/08 and docs/00 section E have the exit-code wording: the field message, and exit 2 for a missing path.
  - The HANDOFF Task 9 line has the fix round and the new counts.

### Tests added

All are in `tests/test_plan_cli.py` unless marked.
- `test_a_planted_bug_in_a_plan_command_keeps_its_traceback`: `lint_bundle` is patched to `int("not-a-number")`. `result.exception` must be `ValueError`, and the traceback must hold the `planted_bug` frame.
- `test_a_schema_invalid_plan_json_is_named_with_its_file_and_field`: `open_blocks: "three"`, run through `validate`, `continue` and `review`. Each must exit 1 with `SystemExit` and print the bundle path and `plan.json: field open_blocks:`.
- `test_plan_new_again_without_no_confirm_on_an_authored_plan_prints_the_stop` (slow).
- `test_a_blocked_dry_run_leaves_no_dryrun_jsonl_of_the_last_one` (slow): runnable, then blocked (the file is gone), then reverted (the file is back and equals the record).
- `test_a_missing_path_is_a_usage_error_with_no_traceback` (3 cases).
- `test_plan_new_help_holds_no_home_folder_name`: `Path.home().name`, `str(REPO_ROOT)` and its posix form must be absent, and `<repo>/plans` present.
- `tests/test_plan_records.py::test_a_damaged_plan_json_raises_the_named_damaged_record_error`: 4 damage kinds.
- `tests/test_store.py`: the damaged-line test now also asserts `DamagedRecordError`.
- The existing mid-file ledger CLI test still asserts the file, the line and `SystemExit`.

### RED evidence (tests on 24b1903's code)

`probes-task9-fixround1/red.txt`: 10 failed.
- planted bug: `assert <class 'SystemExit'> is ValueError` (output `error: invalid literal for int() ...`).
- schema-invalid: the output was `error: 1 validation error for PlanRecord ...`, with no file and no field.
- authored plan: exit 1, output `status authored`.
- blocked dry run: `assert not True`, because `dryrun.jsonl` was still there.
- missing paths: 3 times `<Result FileNotFoundError(...)>`, exit 1.
- help: `assert '<home>' not in ...`. The home folder name was in the help. This was rerun with the home assertion first; the name is redacted here.
- records and store: `ImportError: cannot import name 'DamagedRecordError'`.

m5 strengthens a property that already held, so it is green on 24b1903 by design. Its bite was shown by mutation (`probes-task9-fixround1/mut_ledger.py`, `mutation_ledger.txt`). With `Director._drop_dead_lines` made a no-op:
- the 24b1903 parity test passes K4 (1 passed);
- the new test fails K4 at the `ledger_ids` line (`test_plan_parity.py:66`);
- K7, K8 and K10 pass under the mutation, since their dead call leaves no ledger line.

### Commands and output

- `uv run pytest -q -m "slow or not slow" tests/test_plan_cli.py tests/test_plan_records.py tests/test_store.py` (timeout 300): 82 passed in 184 s.
- `uv run pytest -q -m slow tests/test_plan_parity.py`: 15 passed in 237 s (ledger and transcript checks included).
- `uv run ruff format --check .`: 350 files already formatted.
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 128 source files.
- `uv run mypy --platform linux claude_bully`: Success: no issues found in 128 source files.
- `uv run pytest -q -W error`: 10666 passed, 11 skipped, 190 deselected in 1000 s (from 10659; 7 fast tests added).
- `uv run pytest -q -m slow`: 190 passed, 10677 deselected in 1130 s (from 188; 2 slow added).

### Disk

- Before: 2,207,068,160 bytes free (2.21 GB).
- During: the reading rose to 2.92 GB at one point, from outside activity.
- After: 2,200,805,376 bytes (2.20 GB).
- Every bundle lived under pytest's basetemp. The probe folder is under 20 KB.

### Concerns

1. `cli.py`'s `--runs-root` and `--results-root` help still prints the absolute path, which holds the home folder name. This is review m4's "same fix at the final review", left as scoped.
2. A damaged transcript (`Bundle.read_transcript`) or attempt marker (`Bundle.read_attempt`, `model_validate_json`) is not a `DamagedRecordError`. Before this round it printed as `error:` (pydantic text, no file). Now it shows a traceback. The ruling named only the two readers; wrap both if they should print cleanly.
3. A `BundlePathError` that escapes the Director (none known on a CLI path) now shows a traceback. Before, it printed as `error:`.
4. For a plan past stage 1, the m1 stop message still says "plan.md is yours to edit now and stage 2 adopts the edit". That is the spec's wording, but it is loose once stage 2 has committed.

## Fix round 2

Commit 6e90524 on 9639ab8, branch build/v1, author rankinbc1@gmail.com (verified with `git config user.email` and `git log -1 --format=%ae`), trailer `Co-Authored-By: Claude Sonnet 5.5`. Not pushed. No subagents. Probes, RED and green output are in `probes-task9-fixround2/`.

### Changes

- **N1 (re-graded Important).** `planner/cli.py: new`, without `--no-confirm`:
  - a plan standing at stage 1 (`planned`) prints the stop after stage 1 and exits 0, as before (D-exit's stop as asked);
  - any other plan goes through `_finish`, the report `plan validate` prints: the cell lines, a failed stage's error, open blocks, each failing lint result of a `validated` plan (`fail <lint_id> <doc_id>: <message>`), then `status <status>`. It exits 0 for `runnable` and 1 for every other status (`failed`, `validated`, `authored`, `reviewed`, `revised`);
  - `authored`, `reviewed` and `revised` also print `plan new without --no-confirm runs stage 1 only; this plan stands at <status>, so run plan continue <bundle>`;
  - a plan held by open blocks is still refused before the run.
  - ASSUMED: an `authored` plan exits 1. The ruling says 0 only for a runnable plan, and D-exit's stop-as-asked is a plan at stage 1. Round 1's authored test (exit 0 with the stop message) is replaced; the re-review's N1 text would have kept 0 for authored, reviewed and revised. The plan is unchanged either way.
- **N2.** `test_a_missing_path_is_a_usage_error_with_no_traceback` reads the output with whitespace and the panel's border characters removed and looks for the argument name and `nowhere` in that.
- **R1.**
  - `planner/records.py` gains `decode_record` (UTF-8 and JSON, with the line), `validated_record` (a model read from a file's bytes) and `damaged_field` (`<where>: field <name>: <message>`, `(and N more)`); `read_plan_record` is rebuilt on them, with the same messages.
  - `Bundle.read_transcript` and `Bundle.read_attempt` use `validated_record`.
  - `committed_outputs` raises `DamagedRecordError` for no attempt, a reply that is no JSON object with a `content` (new: before it was a bare `JSONDecodeError` or `KeyError`) and another purpose's paths; `_committed_texts` does for a text of another sha256. These last two were `ValueError`s that read as `error:` before round 1 and showed a traceback after it.
  - `Director._drop_dead_lines` (new `_ledger_numbered`) and `dryrun._drop_dead_lines` raise it, naming file, line and field, for a ledger line that parses but is no `LedgerLine`. The ledger is left as it was.
  - The CLI catch is unchanged (`DirectorError` and `DamagedRecordError` only), so a planted `ValueError` still keeps its traceback (round 1's test passes).
- **Docs.** Spec section 13's damaged-record row and "As planned" (a fix round 2 bullet, and round 1's "whatever stage it stands at" corrected), docs/08, docs/00 and the HANDOFF Task 9 line.

### Tests added or changed

- `tests/test_plan_cli.py`:
  - `test_plan_new_again_on_an_authored_plan_reports_its_status_and_exits_1` (slow; replaces round 1's authored-stop test);
  - `test_plan_new_again_on_a_validated_plan_prints_its_lint_failures_and_exits_1`;
  - `test_plan_new_again_on_a_runnable_plan_prints_its_cells_and_exits_0` (slow);
  - `test_plan_new_again_on_a_failed_plan_prints_the_failed_stage_and_exits_1` (slow);
  - `test_a_damaged_attempt_marker_is_named_with_its_file_and_no_traceback` (3 cases);
  - `test_a_damaged_transcript_is_named_with_its_file_and_no_traceback` (cut, wrong shape, not UTF-8);
  - `test_a_schema_invalid_ledger_line_is_named_with_its_file_and_line_and_no_traceback`;
  - the missing-path test, changed.
  Each plan is asserted unchanged and no planner or reviewer call is made.
- `tests/test_bundle.py`: `test_a_damaged_transcript_raises_the_named_damaged_record_error` (4 damage kinds), `test_a_damaged_attempt_marker_raises_the_named_damaged_record_error` (4), `test_a_committed_call_the_transcript_cannot_give_raises_the_named_damaged_record_error` (4 transcripts through `materialize`, plus a purpose that gives other paths).
- `tests/test_dryrun.py`: `test_a_schema_invalid_ledger_line_raises_the_named_damaged_record_error` (the dry run's own ledger, line 2).

### RED evidence (tests on 9639ab8's code)

- `probes-task9-fixround2/red_cli_dryrun.txt`: `uv run pytest -q -m "slow or not slow" tests/test_plan_cli.py tests/test_dryrun.py -k "again_on or damaged_attempt or damaged_transcript or schema_invalid_ledger"`: **10 failed, 2 passed** in 19.8 s.
  - authored: exit 0 with the stop message, not 1.
  - validated: exit 0, `stopped after stage 1`, no lint lines.
  - attempt marker, 3 cases: the pydantic `ValidationError` reaches the caller, not `SystemExit`.
  - transcript, 3 cases: same.
  - plan ledger line: `6 validation errors for LedgerLine` out of `director.py` (a bare `ValidationError`).
  - dry-run ledger line: `ValidationError` from `dryrun.py:642`.
  - The 2 that passed are the runnable and the failed plan: they already behaved, and pin it.
- `probes-task9-fixround2/red_bundle.txt`: `tests/test_bundle.py -k "damaged or cannot_give"`: **3 failed** (`ValidationError` for Transcript and for DirectorAttempt, and a bare `ValueError` for the sha256 mismatch).
- N2, `probes-task9-fixround2/red_n2_old_test_long_basetemp.txt`: round 1's test on 9639ab8 under `--basetemp` of 172 characters: `1 failed, 2 passed` (the `request` case, `nowhere` folded across the panel's line). It passed at 160 to 168 and 180 characters, which is why the length matters.

### Commands and output

- N2 proof, `green_n2_new_test_long_basetemp.txt`: the new test, `-k missing_path`, under `--basetemp` of 160 to 200 characters in steps of 2 (21 lengths, 172 and 176 among them, the lengths where the old test failed): `3 passed` every time.
- `timeout 300 uv run pytest -q -m "slow or not slow" tests/test_plan_cli.py tests/test_plan_records.py tests/test_store.py tests/test_bundle.py`: 153 passed, 2 skipped in 181 s.
- `timeout 280 uv run pytest -q -m "slow or not slow" tests/test_dryrun.py -k "ledger or torn or damaged"`: 3 passed.
- `uv run ruff format --check .`: 350 files already formatted.
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 128 source files.
- `uv run mypy --platform linux claude_bully`: Success: no issues found in 128 source files.
- `uv run pytest -q -W error`: **10678 passed, 11 skipped, 192 deselected** in 983 s (from 10666: 12 fast tests added).
- `uv run pytest -q -m slow`: **192 passed**, 10689 deselected in 1125 s (from 190: 3 slow added, round 1's authored-stop test replaced).

### Disk

2.8 GB free at the start; 2.1 GB after the two gate runs (pytest keeps its last basetemps). The long-basetemp folders were removed; no bundle was left behind.

### Concerns

1. ASSUMED, exit 1 for `authored`, `reviewed` and `revised` (above): if the controller wants 0 for a plan mid-flight, it is one condition in `cli.new` and one assertion in the authored test.
2. A transcript a call names that is missing from disk is still a `FileNotFoundError` traceback (not a damaged one); the ruling named damaged files only.
3. `Director._call` reads `attempts[-1]` of a transcript that parses but holds no attempts and gets an `IndexError`; only `committed_outputs` checks for it. Not reachable from a transcript the Director wrote.
4. Round 1's concerns 1 and 4 stand: the seven pre-existing commands' `--runs-root` and `--results-root` help still print the home path (final fix wave), and the stop message's wording past stage 2 no longer matters, since the stop is now only printed at stage 1.
