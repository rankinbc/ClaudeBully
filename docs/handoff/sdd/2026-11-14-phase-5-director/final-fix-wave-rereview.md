# Phase 5 final review: re-review of the fix wave

Fix base 32df6ea, head 78db56f (one commit). Read-only on the checkout. I read the diff
(`review-32df6ea..78db56f.diff`) in passes: every code hunk in full, the docs and test hunks
where a finding depends on them. I checked the report's claims against the code. Probes and
outputs are in `probes-final-rereview/`, all on stubs, with no network and no model call:

- `fast_new_file.out`: `tests/test_phase5_final_fixes.py -m "not slow" -W error`. 32 passed.
- `slow_i1_i2.out`: the I1 kill and dead-end test, and the I2 CLI rate-limit twin test. 2 passed.
- `modified_tests.out`: the rewritten `test_director_author` and `test_director_review` cases
  and the I3 cp1252 stage-3 test. 6 passed.
- `probe_help.py`, `.out`: `--help` of all 13 commands, scanned for the home folder and the
  checkout path. 0 hits.

Line numbers below are at 78db56f.

## Finding Verdicts

- **I1, a denylist hit in a stage 4 revision is a dead end**: ADDRESSED.
  - `bundle_lints.py:1288` `reply_scans` runs `review_scans`' clauses over the reply's file
    alone. `_View.wanted`, at `:622`, limits each scan to that path, and the config spare reads
    the reply when the file is `config.yaml`.
  - `director.py:1685` `_reply_hits` is added to the arrival failures in `_check_file`
    (`:1683`) and in `_check_revision` (`:1994`). The failure text is `split(':')[0]` of the
    lint message ("holds a real name", "holds the owner's name"), so it carries no matched text.
  - A hit is one retry, then an `error` call with no outputs. The file stays as it was and the
    block stays open.
  - The kill test and the `review_round` test pass in `slow_i1_i2.out`. The fixer's hard-kill
    sweeps give 21/21, 19/19 and 101/101 equal.
- **I2, a resumed stage 3, 4 or 5 deletes an owner-added file**: ADDRESSED.
  - `bundle.py:99` `_REMOVING_STAGES = {"plan","author"}`, and `:555` returns before the removal
    loop for every other stage.
  - Each removal prints one `say` line. `director.py:1349` passes `say=self.say`.
  - Spec section 8 and the runbook's rung D paragraph are amended.
  - The CLI twin test (part E of the probe) passes. The fixer's sweep gives 20 kills and 0
    mismatches, with the file kept in every one.
- **I3, traceback paths on the owner's workflow**: ADDRESSED.
  - `bundle.py:573` `undecodable`. `director.py:1464` `_scan_bundle` calls
    `_refuse_undecodable` first, and `:2173` `review_round` refuses before `_archive_round`.
  - `bundle.py:333` `read_transcript` raises `DamagedRecordError` for a file that is not on disk.
  - `director.py:727` `_last_reply` raises `DamagedRecordError` for empty attempts, and `_call`
    reads through it (`:1193`).
  - `bundle.py:226` refuses a `content` that is not a string.
  - `director.py:967` clears the marker when the first message cannot be built.
  - The cp1252 stage-3 test (no traceback, `resumed == []`, no marker, continue goes on) and
    the plan-review refusal tests pass.
- **M1, absolute home paths in help and `plan diff`**: ADDRESSED.
  - `paths.py:20,30` add `shown_paths` and `shown_default`. `cli.py:58,63` use them, and
    `planner/cli.py:60` sets `PLANS_ROOT_SHOWN` through them.
  - `planner/cli.py:441,477` label each side `a/`, `b/`, `shipped/` or `worlds/`.
  - `probe_help.out` shows all 13 commands clean.
- **M2, a failed stage's error puts the checkout path in `plan.json`**: ADDRESSED.
  `director.py:1212` records `failed.error = shown_paths(error)`, and the M2 test passes (no
  repo or home path, the owner pattern does not match).
- **M3, "a validated bundle never fails CI" covers lint-read files only**: ADDRESSED. Spec
  section 12 has a new row 2a, and the runbook's move-in paragraph names `ledger.jsonl` errors and
  `plan.json` errors.
- **M4, a newer plan schema is read as schema 1**: ADDRESSED. `records.py:234` refuses a version
  above `PLAN_SCHEMA_VERSION`, and the test passes.
- **M5, a runnable bundle can lack `plan.md`**: ADDRESSED. `bundle_lints.py:832` adds a `schema`
  fail for a missing `plan.md`, beside the off-grammar failures. The only other fixture bundle,
  `tests/fixtures/bundles/good`, has a `plan.md`.
- **M6, `plan new` without `--no-confirm` inside stage 2 prints the stage 1 stop**: ADDRESSED.
  `planner/cli.py:334` stops only when the author stage has no call. Otherwise it prints
  "stands in stage author ... plan continue" and exits 1 through `_finish`. The test passes.
- **M7, `analysis/expected.py` imports `planner/records.py`**: ADDRESSED.
  `claude_bully/expectations.py` is new, `analysis/expected.py:40` imports from it, and
  `records.py` re-exports it. The config is the same as `_Strict` (`extra="forbid"`).
- **M8, the runbook's "a new file vanishes" clause**: ADDRESSED. The rung D paragraph now says
  a resumed stage 3, 4 or 5 removes no file, after a kill or a rate limit, within the wait or
  past it. "would vanish" appears nowhere in the runbook or in `docs/08`.
- **M9, a hand-damaged `run.json` stamp tracebacks at `analyze`**: ADDRESSED.
  `analysis/load.py:135` turns the `ValueError` into `DamagedRecordError` naming `run.json`
  and `plan.personas`, `cli.py:205` prints `error:` and exits 1, and the test passes.

Triage rows marked "fix before close":

- **Task 8 N7, stage 4's confirm-scan overwrite dead end**: ADDRESSED (as I1).
- **Task 8 N10, a planner-written hit reaching later stage 2 prompts**: ADDRESSED.
  `_check_file` runs the reply scans, so a hit is never committed. The test
  `test_a_planner_written_hit_in_a_document_title_never_reaches_a_later_prompt` passes (slow,
  green in the fixer's run; the rewritten `test_director_author` case passes here).
- **Task 7b, an owner-added file removed by a resume**: ADDRESSED (as I2).
- **Task 9, the missing-transcript and empty-attempts traceback paths**: ADDRESSED (as I3).
  The CLI tests for `continue` and `review` pass.
- **Task 1 M3 and Task 9 N-c, a non-string `content`**: ADDRESSED. See `bundle.py:226`; the
  four shapes and the near-miss pass.
- **Task 9 m4, the seven commands' root help**: ADDRESSED (as M1).
- **Task 11, the fourth reason `stale`**: ADDRESSED.
  - `analysis/progression.py:247` gives `stale` after `failed_ask` and before `no_ratings`.
  - `run_analysis.py:241` sets `ratings_stale` and `ratings_prompt_stale` on the read-back path.
  - The clause says the verdict is stale and that a rerun asks the judge again. The tests pass.
- **Task 11's three notes**: ADDRESSED.
  - `analysis/expected.py:233` unlinks a stale `expected.json` when the stamp is unreadable.
  - `:211` adds "every rep flagged".
  - The advice now names "the judge about this rep / these reps".
- **Task 13's three nits**: ADDRESSED. The runbook now says "not shown at all", names the four
  entry kinds, and reflows the long line. The remaining lines over 100 columns (771, 854) are
  outside the diff and older.
- **Task 1 M6, the literal BOM in `normalize_text`**: ADDRESSED. `bundle.py:108` writes
  `"﻿"`, and the source holds no EF BB BF bytes (checked with grep and by the test).

## New Breakage in the Fix Diff

- **Minor**: `docs/superpowers/specs/2026-11-14-phase-5-director-design.md:801` reads
  "`normalize_text` writes the BOM as `<U+FEFF>`". The intended text is the escape `﻿`, but
  the line holds the invisible literal character, so the span renders empty and the doc says the
  opposite of the fix. This is the same hazard M6 removed from the code. The fix report
  (lines 148-149, with its copy under `docs/handoff/sdd/`) has the same slip.
  `tests/test_phase5_final_fixes.py:784-785` also uses literal U+FEFF characters in its test
  strings. That works, but `"﻿"` would be the clearer form there too.
- **Minor**: the I2 docs-sync is incomplete. The spec's Task 13 ASSUMED bullet
  (`2026-11-14-phase-5-director-design.md:790`, a line the diff did not change) still says
  `rematerialize_open_stage` removes a grammar file that no record owns "when a stage 3 is
  resumed". The amended section 8 now contradicts it. One clause would fix it.

No Critical or Important breakage found. I checked the non-negotiables:

- No real name or emoji appears in the added lines. The only non-ASCII characters are "é" in a
  cp1252 test string, existing em-dashes and the BOMs above.
- Reply-scan failures carry no matched text.
- No reasoning text and no network is on any new path.
- Replay from JSONL is unchanged: `committed_outputs` only adds a refusal.

## Out-of-Scope Observations

- The slow suite has not been run at 78db56f. The report's Gate section and HANDOFF item 16
  both say so. I ran 9 of the slow cases that bear on I1 to I3, and all were green. The slow
  suite is still owed before close.
- In `red2_at_32df6ea.out`, the RED for the three stage 3 to 5 cases fails on a `TypeError`
  (the `say` keyword) rather than on the behavior. That says nothing about HEAD's code, and the
  old behavior (the file removed) is clear from the removed code.
- Older, and the fixer's own ASSUMED: a document's arrival also runs `lint_document`'s own
  real-name clause. If that clause's message quotes the match, a document's retry or its
  recorded `error` could carry the name. I did not verify this; it is outside the diff.
- `read_transcript`'s and `_last_reply`'s new messages name the absolute transcript path. They
  are printed at the CLI, never recorded or sent to a model, as with the other
  `DamagedRecordError` messages.

## Verdict

All findings addressed, no new Critical/Important breakage. Counts: 22 addressed (I1 to I3, M1
to M9, 10 triage rows), 0 not addressed, 0 new Critical, 0 new Important, 2 new Minor.
