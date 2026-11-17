# Phase 5 final review: the fix wave

Base 32df6ea, one commit on build/v1 (the commit after 32df6ea in progress.md). Every finding of `final-review.md` (I1 to
I3, M1 to M9) and every "Fix before close" row of its triage; the "Leave parked" rows untouched.
Stub providers only; no real call. New tests: `tests/test_phase5_final_fixes.py` (43 cases, 11 of
them slow; every fast call under 2 s). RED was taken with the code changes stashed on 32df6ea:
`probes-final-fixwave/red_at_32df6ea.out` (41 failed, 2 passed: the two passing are the help
near-misses, `plan new` and `plan diff`, already clean) and `red2_at_32df6ea.out` (the I2 cases
re-run after a fixture fix, 4 failed, each on the behavior). GREEN: 43 passed, `-W error`.

## I1. A denylist hit in a stage 4 revision is a dead end

- Fix: `bundle_lints.reply_scans(bundle, record, rel, text)` runs `review_scans`' clauses and
  spares (`plan_scans`' plan.md clause, `real_name_bundle` with its owner clause,
  `boundary_bundle`, `jailbreak_bundle`) over one file as a reply gives it, normalized as
  `write_file` writes it, whether or not the file is on disk, and returns that file's results
  alone (`_View` gained a `reply` override and `wanted()`, so only that path is read; the config
  spare's display names come from the reply when the file is `config.yaml`). `Director._reply_hits`
  turns each hit into `<path>: <lint_id>: holds <what>`, and `_check_file` (stage 2's file and
  repair calls, stage 4's repairs) and `_check_revision` (every revision, `plan.md`'s too) add
  them to the arrival failures. A hit is one retry naming the lint, then an `error` call that
  commits nothing; a stage-4 revision then leaves its file as stage 3 reviewed it and its blocks
  open (D-revise-error), and `plan review` is the way on. This closes Task 8's N7 and N10.
- Tests: `test_a_revision_holding_a_denylist_hit_is_retried_naming_the_lint[document-owner, plan]`
  (RED: the revision committed, stage 4 failed on the next scan; GREEN: attempts 2, the retry
  names `real_name_bundle: holds` / `boundary_bundle: holds` and no name);
  `test_a_revision_holding_a_hit_twice_commits_nothing_and_plan_review_gets_past_it` (the kill
  test: the error call, DOC1 byte-equal to the good file, one open block; killed after the call's
  transcript, record and files writes, each resume equal to the unbroken plan in record, hashed
  files and ledger; then `review_round` reaches `runnable`. RED: status/open_blocks);
  `test_a_planner_written_hit_in_a_document_title_never_reaches_a_later_prompt` (N10; RED: the
  call was `fresh` and later prompts carried the title); `test_reply_scans_read_one_file_as_the_reply_gives_it`
  (three hits and three near-misses, a path not on disk, another file's hit never the reply's;
  RED: ImportError). Updated: `test_director_review.py`'s confirm-scan test is now
  `test_a_denylist_hit_in_a_revision_is_an_error_call_and_never_reaches_the_confirm_call`;
  `test_director_author.py`'s planner-written-hit test now expects stage 2 to fail on the error
  call, kill parity kept, and a continue with a clean planner to reach `reviewed`.
- Hard kills inside every write (`probes-final-fixwave/hard_kill_sweep_fixwave.py`, Task 7b fix
  round 1's sweep with an unarmed setup): `revise_hit_once` 21 of 21 equal, `revise_hit_twice` 19
  of 19, `author_hit_twice` (two commands) 101 of 101.
- ASSUMED: the failure names the file, the lint and the kind of hit, never the matched text, so
  neither the retry nor the recorded `error` (which CI's scans of `plans/` read) carries a name or
  a phrase; the planner's message scrubs a real name anyway. Cost if wrong: a retry less able to
  find a Boundary or jailbreak word.
- ASSUMED: a document's arrival may list a real name twice (`lint_document`'s own clause and
  `real_name_bundle`'s); left, since both fail closed.

## I2. A resumed stage 3, 4 or 5 deletes an owner-added file

- Fix: `rematerialize_open_stage` removes an unowned grammar file only when the open stage is
  `plan` or `author`, with a `say` line per file (`Director.run` passes `self.say`); stages 3 to 5 remove
  none. Spec section 8's resume bullet amended; the runbook's rung D paragraph rewritten (M8).
- Tests: `test_a_resume_of_stages_3_to_5_keeps_an_owner_added_file[review, revise, validate]`
  (RED: the file removed); `test_a_resume_of_stage_2_removes_an_unowned_file_with_one_line`
  (RED: no `say`); `test_plan_review_paused_by_a_rate_limit_keeps_an_owner_added_file` (the probe's
  part E through the CLI against an unbroken twin with the same cache: RED, the file gone after
  the resume; GREEN, files and record equal to the twin's).
- Hard kills: `review_owner_file` (an owner-added document, stage 3 paused at its first call,
  resumed by a second command) 20 kills, 19 equal, 1 equal to the run with no pause (the kill
  inside the pause's own window), 0 mismatched; the file kept in every one.
- ASSUMED: stage 1 keeps the removal too (the review named `author` alone): before stage 2
  commits no manifest can name an owner's file, and `test_director_primitive.py`'s
  `test_rematerializing_rewrites_the_open_stage_and_removes_what_nothing_owns` pins the stage-1
  removal. Cost if wrong: an owner's file added during a stage-1 pause is removed, with a line.
- ASSUMED: the rate-limited group in the CLI test is `review:corpus-1`, the group that shows the
  added file: an unchanged group's call is a cache hit on the runnable plan's cache and never
  reaches the double (the review's probe used a fresh plans root).

## I3. Tracebacks on the owner's workflow

- Fix: `bundle.undecodable(bundle)` lists each grammar file that is not UTF-8 with `not_utf8`'s
  message (moved from `bundle_lints._not_utf8`, one wording); `Director._scan_bundle` raises
  `DirectorError` on it first (the stage fails naming the file and byte, before any marker or
  message), and `review_round` refuses it before `_archive_round`, so a finished round is not
  archived. `Bundle.read_transcript` raises `DamagedRecordError` for a file not on disk;
  `_last_reply` (now used by `_call`) for a committed reply with no attempt; `committed_outputs`
  for a `content` that is no string (Task 1 M3, Task 9 N-c). `Director.ask` clears the marker
  when the first message cannot be built (nothing was sent), so no false dead attempt.
- Tests: `test_a_missing_transcript_raises_the_named_damaged_record_error` (RED:
  FileNotFoundError), `test_a_non_string_content_raises_the_named_damaged_record_error` (four
  shapes and a near-miss; RED: AttributeError),
  `test_a_committed_reply_with_no_attempt_raises_the_named_damaged_record_error` (RED:
  IndexError), `test_plan_continue_of_a_plan_whose_review_transcript_is_damaged_names_it[missing,
  no_attempt]`, `test_plan_review_of_a_runnable_plan_with_a_missing_transcript_names_it`,
  `test_plan_continue_with_a_non_string_content_in_a_transcript_names_it` (CLI: `error:` naming
  the file, exit 1, no traceback; RED: the raw exceptions),
  `test_a_file_that_is_not_utf8_fails_the_stage_naming_it_and_a_continue_goes_on` (cp1252 during a
  stage-3 pause: the stage fails naming `plan.md` and byte 0xe9, `resumed` empty, no marker; saved
  as UTF-8, the continue commits stage 3; RED: UnicodeDecodeError),
  `test_plan_review_refuses_a_file_that_is_not_utf8_before_the_archive[plan.md-cp1252,
  personas-utf-16]` (the record unchanged, still runnable, no round; then the same command
  archives; RED: the round archived and a traceback).
- ASSUMED: the check covers grammar files only, the files a message shows; `plan validate`
  keeps failing `schema` on them as before.

## The Minors

- M1: `paths.shown_paths` and `paths.shown_default`, one helper: the seven older commands'
  `--runs-root` and `--results-root` and `PLANS_ROOT_SHOWN` show `<repo>/...`; `plan diff`
  labels `a/<path>`, `b/<path>`, `shipped/<name>/<path>`, `worlds/<name>/<path>`, and its "holds
  no world" line is redacted. Tests: `test_no_command_help_prints_the_home_folder[9 commands]`
  (RED for the seven), `test_shown_paths_writes_the_checkout_and_the_home_folder_as_tokens`,
  `test_plan_diff_labels_each_file_by_its_bundle_path` (RED: absolute labels).
- M2: `Director._fail` records `shown_paths(error)`. Test:
  `test_a_failed_stage_records_its_error_with_no_absolute_path` (no repo root or home path in
  `plan.json`, the owner pattern does not match it; RED). ASSUMED: the 8.3 short form of the home
  folder is not replaced (a temp path; no production message names it).
- M3: spec section 12 row 2a and the runbook's move-in paragraph. Docs only.
- M4: `read_plan_record` refuses a newer plan schema. Test:
  `test_a_plan_json_of_a_newer_plan_schema_is_refused` (RED: read as 1). ASSUMED: done although
  the triage parks Task 1's N2 as "M4 above": the brief names all nine Minors, and the change only
  refuses (fail closed).
- M5: `schema` fails a bundle with no `plan.md`, appended beside the off-grammar failures so no
  load stops (the dry run is still blocked by any `schema` fail, `_dry_run_blocked`). Test:
  `test_a_bundle_with_no_plan_md_fails_schema` (RED).
- M6: `plan new` without `--no-confirm` on a `planned` plan whose author stage has a call prints
  `... this plan stands in stage author, so run plan continue <root>` and exits 1. Test:
  `test_plan_new_without_no_confirm_on_a_plan_inside_stage_2_says_to_continue` (RED: exit 0 and
  the stop). ASSUMED: exit 1, as for the other mid-plan statuses; an author stage opened with no
  call yet keeps the stop (its "stage 2 adopts the edit" is still true).
- M7: `claude_bully/expectations.py` holds the three models, `planner/records.py` re-exports
  them. Test: `test_the_analysis_imports_no_planner_module` (RED: `expected.py`).
- M8: the runbook (with I2).
- M9: `load_run` raises `DamagedRecordError` naming `run.json` and `plan.personas`; `analyze`
  prints it as `error:`, exit 1. Test: `test_a_hand_damaged_stamp_is_a_named_error_at_analyze`
  (RED: ValueError).

## Fix before close

- Task 11 `stale`: `LoadedRun.ratings_stale` (from `ReadBack.stale_reps`) and
  `ratings_prompt_stale` (`rate_values` in `stale_kinds`), set on the read-back path;
  `unjudged_reason` tests `stale` after `failed_ask`, before `no_ratings`; the clause: "the
  rate_values verdict is stale (the rep or the prompt changed since it was asked) and is left
  out, ...; `analyze --ratings` asks the judge about these reps again". Tests: `test_the_stale_clause`,
  `test_a_stale_rating_verdict_reads_the_stale_reason[prompt, rep]` (end to end on the Poisoned
  Well stubs; RED: "never asked" and "--ratings was not run"). ASSUMED: the flag form instead of
  expanding the set to every rep; a Poisoned Well rep never asked reads `stale` after a prompt
  change (its rerun then reads `never_asked`).
- Task 11's notes: N-C, an unreadable stamp removes the old `expected.json`
  (`test_an_unreadable_stamp_removes_the_expected_json_an_earlier_analysis_wrote`, RED); N-A,
  "untested: rung never fired, cell not run or every rep flagged"
  (`test_the_untested_parenthetical_names_its_third_cause`, RED); N-B, every advice names what it
  asks about ("asks the judge about this rep" / "these reps"); `tests/test_expected.py`'s
  templates and three line expectations updated.
- Task 13's three nits: the runbook says the 54 overlay files are not shown at all, the entry's
  kind is the path's (four kinds named), the 109-column line is reflowed and the size reason
  says CI loads each transcript (its replies, never its message).
- Task 1 M6: `normalize_text` writes `"﻿"`. Test:
  `test_normalize_text_is_written_with_the_bom_escape` (RED: the literal bytes).
- The seven commands' help: M1.
- Ledger line 74's cost line: the spec does not repeat it (section 9 already says no later scan
  closes the split-phrase residual); the fix wave's "As planned" entry records that the reviewer
  stage is the one backstop. The ledger line itself is the controller's.

## Files changed

Code: `claude_bully/expectations.py` (new), `paths.py`, `cli.py`, `analysis/expected.py`,
`analysis/load.py`, `analysis/progression.py`, `analysis/run_analysis.py`,
`planner/bundle.py`, `planner/bundle_lints.py`, `planner/cli.py`, `planner/director.py`,
`planner/records.py`. Tests: `tests/test_phase5_final_fixes.py` (new),
`tests/test_director_review.py`, `tests/test_director_author.py`, `tests/test_expected.py`. Docs:
`HANDOFF.md` (Progress item 16, the header, Next steps, Open items), `docs/00-RECONCILED.md`
(section H's fix-wave line), `docs/08-DIRECTOR.md` (stage 2 and stage 3/4 paragraphs, `plan
diff`), `docs/handoff/phase-7-runbook.md` (rung D), the spec (sections 8, 12, 13, the Task 11
untested line, "As planned"). Ledger: this report and `probes-final-fixwave/`.

## Gate

Run by the controller after the agent stalled on its slow-suite wait (the agent saw the same fast count).

- ruff format --check, ruff check, mypy claude_bully, mypy --platform linux claude_bully: clean (131 source files).
- pytest -q -W error: 10798 passed, 11 skipped, 226 deselected (26 min).
- pytest -q -m slow: NOT RUN. Claude Code stopped it for low system memory. The new file's 11 slow cases and the four hard-kill sweeps above ran green inside the agent's session. Rerun the slow suite before the re-review closes.

## Concerns

- The slow suite is unverified at this commit (see Gate).
- The agent stalled (stream watchdog) after the fast suite; the work was complete, and the controller committed it.
