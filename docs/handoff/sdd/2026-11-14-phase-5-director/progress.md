# SDD ledger — plan: docs/superpowers/plans/2026-11-14-phase-5-director.md
Spec: docs/superpowers/specs/2026-11-14-phase-5-director-design.md. Plan review: .superpowers/drafts/2026-11-14-phase-5-plan-review.md (Critical 1, Important 9, Minor 17), fixes log .superpowers/drafts/2026-11-14-phase-5-plan-fixes.md (all fixed). Global constraints: global-constraints.md (from the plan). Preflight: preflight.md.
Branch: build/v1, one working tree, no worktree. Controller: Opus 5.5. Push after each task. Owner direction (2026-11-13 night): continue autonomously; no real model runs (2026-11-11).
Tasks: 1, 2, 3, 4a, 4b, 5, 6, 7a, 7b, 8, 9, 10, 11, 12, 13 (fifteen commits).
Residuals the plan fixes log lists for the owner: a bundle persona's params are not validated; a host on an unlisted public suffix passes the lint (both pinned as known residuals).
Carried from Phase 4 (parked N2): the "not judged" note in analysis/progression.py tells the reader to rerun --ratings even for a cell never asked; Task 11 touches that wording.
Preflight: dispatched (opus, preflight.md).
Preflight (opus, preflight.md): 76 rows, 25 findings need a ruling (4 text-only: Q26, Q28, Q38, Q73; 21 change a task's code, fixtures or tests: Q4, Q10, Q11, Q17-Q21, Q24, Q30, Q39, Q42-Q46, Q48, Q50, Q59, Q61, Q68).
Ruling: every preflight row's recommended ruling is adopted as written and binds the task it names (the spec is the authority; each recommendation was checked against it in the scan); each task's dispatch points at its rows — cost if wrong: a task's review re-opens the row.
Task 1: BASE 97102a0; implementer dispatched (opus, task-1-brief.md, preflight rows naming Task 1, report task-1-report.md).
Task 1: implementer agent id a531f61ef89d1d1c5.
Task 1: implementer DONE at 262b8a2 (on 97102a0); gate 9912 passed, 10 skipped (the symlink test lacks the privilege; a junction twin added), 48 deselected, slow 48, both mypy clean; world hashes unchanged. ASSUMED: PlanRequest.slug refuses Windows device names; kind_of and world_of raise BundlePathError outside the grammar; transcript paths have their own closed grammar (round-<n>/, failed/ allowed); committed_outputs normalizes line endings; docs/08 unchanged. The preflight's controller-rulings section was empty; the adoption ruling is now written into preflight.md.
Task 1: review dispatched (opus, review-97102a0..262b8a2.diff, task-1-review.md).
Task 1: review (opus, task-1-review.md): spec compliant; quality Approved; Critical 0, Important 0, Minor 6, Nit 5. M1 bundle.py:282 write_manual overwrites an earlier call's transcript when a stage name is reopened (latent); M2 index() and bundle_hash read through a junction (writes, reads and removes refuse one); M3 raw exception from committed_outputs; M4 unvalidated slug in Bundle.create; M5 longest path over 260 chars; M6 literal BOM. ASSUMED decisions sound.
carry to Task 7a: M1 (a reopened stage never overwrites an earlier call's transcript; it is the open-stage re-materialization's seam) and M2 (index() and bundle_hash refuse a junction like the writers).
Task 1: minor (deferred, final review): M3-M6 and the nits.
Task 1: complete (commits 97102a0..262b8a2, review clean). Pushed.
Task 2: BASE d68aa3f; implementer dispatched (opus, task-2-brief.md, preflight rows naming Task 2 incl. Q10, Q11, report task-2-report.md).
Task 2: implementer agent id a790fb4ff0d90ad6b.
Task 2: implementer DONE at 049101d (on d68aa3f); gate 9932 passed, 10 skipped, 48 deselected, slow 48, both mypy clean; no golden changed; `_stubbed` gone from tests. ASSUMED: a turns script needs a non-empty default, by_cell optional; cell patterns via fnmatchcase (fnmatch ignores case on Windows); a non-string reasoning value refused; the stub-shape line in docs/00 F per the brief. Concerns: docs/08 line 175 still says "scripted" (Task 5's edit); all stubbed targets share model `stub-target`.
Task 2: review dispatched (sonnet, review-d68aa3f..049101d.diff, task-2-review.md).
Task 2: review (sonnet, task-2-review.md): spec met; quality good; Critical 0, Important 0, Minor 4, Nit 3. Probes: old _stubbed equals tests.helpers.stubbed on 66 caller/input pairs; Q11 clean on 17 dirtied env configs; turns mode edges as required; the reasoning key reaches no Completion field or run file. Minor: the ASSUMED rules (default required, non-string reasoning refused) untested; load_stub_script now refuses empty-falsy files ({}, 0, '', false) that used to load; the fnmatchcase deviation missing from the spec's "As planned"; the reasoning no-leak property has no shipped test.
carry to Task 5 (the dry run, the first full stubbed run): ship a test that the stub's reserved reasoning key reaches no Completion field, record or prompt; tests for the two ASSUMED stub rules; the fnmatchcase line in the spec's "As planned".
Task 2: minor (deferred, final review): load_stub_script's refusal of empty-falsy files (check no shipped script is empty); the nits.
Task 2: complete (commits d68aa3f..049101d, review clean). Pushed.
Task 3: BASE 6f15671; implementer dispatched (opus, task-3-brief.md, report task-3-report.md).
Task 3: implementer agent id a2e62745862222cd8.
Task 3: implementer DONE at e1487dd (on 6f15671); gate 10027 passed, 10 skipped, 48 deselected, slow 48, both mypy clean. overlay passes every lint (warns included), annex no fails, mini fails exactly D3's five (pinned); no golden or world file changed. ASSUMED: ladder_walk failures named <world>/<ladder>; outlet warns named <world>/<cast name>; a second inconsistency entry for the second-entry-id case; the canteen title rewritten to state "14 June 2051"; the Ledger archive re-layered to filler (removing its only seam link fails the load).
Task 3: review dispatched (opus, review-6f15671..e1487dd.diff, task-3-review.md).
Task 3: review (opus, task-3-review.md): spec pass; quality pass with one Important; Critical 0, Important 1, Minor 2, Nit 3. Probes ~85 fresh inputs, precision and recall 1.00 per lint; shapes moved unchanged; world hashes unchanged; no data changes. I1 tests/test_world_lines.py:682-705 the D3 pin compares (lint_id, doc_id) pairs, so a new failure on a pinned pair is absorbed (3 of 4 planted defects in mini absorbed). R-buried's stray-hit case carries to Task 5 (no search code yet). No event-id collisions (40 events, 7 walks). ASSUMED edits sound (they touch a temp overlay copy).
Ruling: fix round 1 = I1 (pin the full sorted (lint_id, doc_id, message, span) rows) and the two minors — cost if wrong: one more round.
carry to Task 5: R-buried's stray-search-hit case (a planted stray hit fails).
Task 3: fix round 1 dispatched (resume a2e62745862222cd8, FIX_BASE e1487dd).
Task 3: fix round 1 DONE (3165ad5; gate 10037 passed, 10 skipped, 48 deselected, slow 48; RED: three planted second failures passed e1487dd's pin). I1 whole-row pin; M1 every walk length pinned; M2 read-only shared mappings; N1. Scoped re-review dispatched (sonnet, review-e1487dd..3165ad5.diff, task-3-rereview-round1.md).
Task 3: re-review round 1 (sonnet, task-3-rereview-round1.md): I1, M1, M2 ADDRESSED (all four planted mini defects caught; no caller broken by MappingProxyType). No new Critical/Important; one nit (mypy on tests/ flags old line 647, outside the gate).
Task 3: fix round 1/5 (3 addressed, 0 open; commits e1487dd..3165ad5).
Task 3: complete (commits 6f15671..3165ad5, review clean after 1 fix round). Pushed.
