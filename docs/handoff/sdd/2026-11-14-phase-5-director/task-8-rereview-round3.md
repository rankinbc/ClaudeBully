# Task 8 re-review, fix round 3 (stage 2's opening scan and resume parity)

Base e57d54e, head 19f5485 (one commit). Diff read once (`review-e57d54e..19f5485.diff`: `director.py`, one test, three doc lines). The checkout was read only (`git status` clean at the end). Probes are in `probes-task8-rereview3/`; every bundle a probe made sat in a TemporaryDirectory, and the two pytest base temp folders of my runs (30 MB) were deleted. Free disk at the end: 2.4 GB. The owner's name was read at run time and never printed.

## Verdict

**I1 is fixed. New findings: Critical 0, Important 0, Minor 0, Notes 3.**

| Check | Result |
| --- | --- |
| 1. I1 case: resumed run against unbroken run | Equal on failed stage, plan status, `comparable` records, files and ledger ids; a continue after the owner's fix recovers (8 of 8 cells and 16 of 16 continues, below) |
| 2. Does `besides` let an owner edit slip past | No. 0 planner messages held an owner edit in any of 3 pauses x 2 markers x every bundle path (110 cases) |
| 3. The 8 gap cases | All fail before any prompt (0 calls asked, 0 messages hold the text). The 2 stage-2 cases too |

The fix is what the round-2 re-review suggested: `_scan_bundle(before, besides=())` drops the `review_scans` results whose `doc_id` is in `besides`, and `author()` passes `{rel for call in stage.calls for rel in call.outputs}`. Stage 3 and stage 4 (`_scanned_call`) pass nothing and still scan the whole bundle. Every `LintResult.doc_id` the three whole-bundle scans and `plan_scans` give is the bundle path, so the filter matches on path. No other caller of `author()` exists (grep over `claude_bully` and `tests`).

## 1. The I1 case, re-run (`probe_round3.py A`, `round3_A.out`; `probe_parity.py`, `parity_kill_files.out`, `parity_others.out`)

A planner double writes the owner's name as a trailing YAML comment into one file of stage 2, a hit no arrival check of a non-document file reads. Two targets (the last file `expected.yaml`, a middle file `personas/ferry_caller.yaml`) x four kill steps (after the transcript write, the record write, the files write, the stage commit), each resumed and run through stage 3, against an unbroken plan.

| Check, for each of the 8 target x step cells | Result |
| --- | --- |
| Failed stage and plan status | Unbroken and resumed both: plan `failed`, stages `plan committed, author committed, review failed` (round 2: resumed stopped at `author failed`) |
| Error | Both `before the review:corpus-1 call shows it: real_name_bundle: holds the owner's name`, which does not name the owner |
| `comparable(record)` | Equal in all 8 (`{}` differing keys) |
| `hashed_files` | Equal in all 8 |
| Ledger ids and statuses (the test's `_ledger_ids`) | Equal in all 8 |
| Continue after the owner replaces the comment | Both plans reach `reviewed`, stage 3 `committed`, the hit is not back in the file, `edited == [target]` (the fix is adopted, not written back over). 16 of 16 continues |

Also run, from round 2's probe unchanged (`parity_kill_files.out`, `parity_others.out`): kill after files and after record of the last file, after the transcript, after the stage commit, and a rate limit on `file:config.yaml` after a planted persona. All end as the unbroken plan: `comparable` `{}`, files equal, the owner's fix then continues to `reviewed` (the recovery lines in both outputs: "planted text back in the file: False").

The ledger bytes differ in every pair of runs (timestamps). In the rate-limit case the resumed ledger has 16 lines against the unbroken 15; `probe_ratelimit_ledger.py` (`ratelimit_ledger.out`) shows the one extra line is `author/planner/12/a1 rate_limit`, the interruption's own record. Round 2's output at 93a60f0 shows the same 16 against 15, so it is old behaviour and no breakage.

RED check: `nobesides_plugin.py` makes `_scan_bundle` ignore `besides` (e57d54e's behaviour) and runs the new test: the first case fails on `('author', 'failed') != ('author', 'committed')`, the named reason. With the fix: `tests/test_director_author.py -k "planner_written_hit or world_sheet_or_a_document_title or plan_md_with_a_denylist"` 7 passed (`pytest_stage2_cases.out`).

## 2. Can an owner edit slip past `besides` (`probe_round3.py B` and `C`, `round3_B.out`, `round3_C.out`)

Why it should not: `Director.run` calls `rematerialize_open_stage` before `author()`, and that rewrites every output of every committed call of the stage from its transcript (`_write_changed` over `_committed_texts(current.calls)`, any path whose bytes differ or that is missing), and removes every grammar file no call, `base_files`, `plan.md` or `review.md` owns. So the set `besides` skips is exactly the set whose bytes were just reset to the planner's own committed text. Nothing owner-written can sit in a skipped path when the scan reads it.

Run to check it. Stage 2 paused three ways (rate limit on `file:config.yaml`: 12 calls committed, 11 own paths; rate limit on `file:expected.yaml`: 13 calls, 12 own; kill after the files write of `file:personas/ferry_caller.yaml`: 12 calls, 11 own). For each path of the bundle (own or not, `plan.md` included) and each marker (the owner's name, the jailbreak phrase `disregard all previous instructions`), the marker appended to that file as an owner would, then the resume with a fresh planner double; every planner message after the edit is read for the marker.

| Path kind | Result |
| --- | --- |
| A path a stage-2 call wrote (personas, ladder, world sheet, the written documents, `config.yaml`, `expected.yaml`) | The edit is overwritten by the resume; the marker is not on disk after; 0 messages hold it; the plan goes on to `reviewed`; `edited []` |
| A path no call wrote (`plan.md`, the base documents `ferry-about.md`, `journal-0901.md`, `night-gate-log.md`, `ops-memo-parking.md`, `pier-day.md`) | Stage 2 `failed` at its opening scan, 0 planner calls after the edit, 0 messages hold it |
| A file the owner creates while paused (`config.yaml`, `expected.yaml`, `personas/zz_owner.yaml`, `worlds/mini/corpus/zz-owner.md`, `worlds/extra/world.yaml`) | Removed by the resume (or rewritten by the planner's later call); 0 messages hold the name; the plan reaches `reviewed` |

Leaks: 0 in every case. The overwrite of an own path is silent (`edited []`): the long-standing resume rule (spec section 8), not new here.

## 3. The 8 gap cases and the 2 stage-2 cases

`probe_i2_head.py` is round 2's probe, copied unchanged and run on 19f5485 (`i2_head_a.out`, `i2_head_b.out`). A1, A2, A2b (a jailbreak phrase), B1, B2, B3, B4, B5: stage 4 `failed`, plan `failed`, 0 calls asked after the edit, 0 messages hold the planted text, the error does not name the owner. A2c and A3 (an edit after a revise or confirm call committed) end `revised` with `edited []`, the N5 rule, unchanged and not in this diff. The stage-2 cases (a copied world sheet and a base document's title edited at a pause): stage 2 `failed`, 0 calls asked, 0 messages hold the name (`parity_others.out`); the repo's two stage-2 tests and the N-B denylist test pass (above).

## New breakage

None found.

## Notes

- **N9.** `besides` is safe because `rematerialize_open_stage` precedes it, and `Director.run` is the only caller of `author()`. If Task 9 ever calls `author()` on a plan without `run` (or `write_manual` puts an owner's text into a stage-2 call's `outputs`, which no Director path does now: the example bundle is hand-authored and never run through `author()`), an own path's owner text would pass the opening scan. The `author` docstring states the dependency ("an owner's edit to one is overwritten"); a one-line test that an owner edit to an own path is overwritten and never shown would pin it. Not needed to close this finding.
- **N10.** The planner-written hit is now handled as in an unbroken run: it reaches the later stage-2 planner prompts (the planner's own text read back to the planner, as `Bundle so far` shows it) and is stopped by the first stage-3 scan, before any reviewer sees it. Parity, not a leak.
- **N7 (carried).** Stage 4's confirm-call scan has the same overwrite dead end (round 2's `stage4_overwrite.out`); the fix does not touch it and the report names it as a carry to the final review. Agreed it is a design choice for Task 9, not this round.

## Test and doc review

The new test (`test_a_stage_2_resumed_after_a_planner_written_hit_ends_as_an_unbroken_plan_does`, 4 slow cases) asserts the unbroken and the resumed plan on stages, error text, `comparable`, files, ledger ids, the plan record free of the name, and the continue to `reviewed` with `edited == [target]`. It covers the kills I1 named; the rate-limit pause and the owner-edit-in-an-own-path case are covered only by my probes (A and B above), which pass. The three doc edits (HANDOFF item 10, docs/08 stage 2 sentence, the spec's D-plan-in-context line and a Fix round 3 bullet) describe the code as it is; the claim "a plan at 93a60f0 recovered" matches round 2's `parity_old_scan.out`.

## Probes (all in `probes-task8-rereview3/`)

`probe_round3.py` (A: parity grid, B: owner edit in every path, C: owner-created files), `probe_parity.py` and `probe_i2_head.py` (copied from round 2, unchanged), `probe_ratelimit_ledger.py`, `nobesides_plugin.py` (pytest plugin for the RED check); outputs `round3_A.out`, `round3_B.out`, `round3_C.out`, `parity_kill_files.out`, `parity_others.out`, `i2_head_a.out`, `i2_head_b.out`, `ratelimit_ledger.out`, `pytest_stage2_cases.out`.
