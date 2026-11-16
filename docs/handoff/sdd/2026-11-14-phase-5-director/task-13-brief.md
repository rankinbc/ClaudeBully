### Task 13: Rung D in the runbook, and the phase docs-sync

Documents only; no code. Nothing in this task runs a model (owner direction 2026-11-11).

**Files:**
- Modify: `docs/handoff/phase-7-runbook.md` (re-anchor at execution: search for '## Rungs other phases add', and the bullet starting '- after Phase 5: rung D')
- Modify: `HANDOFF.md` (re-anchor at execution: search for '### Progress', '### Next steps, in order', '## Open items worth knowing', and the gate counts under '## Setting up a new machine')
- Modify: `docs/00-RECONCILED.md` (sections A, B, E, F, H; phase map row 5 complete)
- Modify: `docs/08-DIRECTOR.md` (the bundle layout of spec section 5, the CLI of section 11, the review format of Task 8)
- Modify: `docs/superpowers/specs/2026-11-14-phase-5-director-design.md` ("As planned": the whole-phase summary)

- [ ] **Step 1: Write rung D into the runbook**

Replace the "after Phase 5" bullet (its `MAX_AUTHOR_CALLS = 80` and "40 to 100 calls" are v1's) with a pointer to a new section `### Rung D: the Director's first real plan (Phase 5)`, placed after the last rung section and before '## Rungs other phases add', holding spec section 18 as built: not run until the owner says so; `doctor --live` first; the command `uv run claude-bully plan new "Does triggered gating beat scheduled on the Rescue premise?" --no-confirm --base-world overlay --hypotheses 9 --slug director-triggered-vs-scheduled --wait-on-rate-limit 360`; the estimate (one plan call, one manifest call, about 30 file calls, up to 10 repairs, 4 review calls, about 10 revise calls, about 5 confirm calls: 50 to 110 calls under `max_director_calls = 120`, ledgered as `planner` and `reviewer`; the dry run and the lints cost nothing); read first `plan.json`'s `stages[*].calls[*].attempts` and `status`, then `review.md`; the bars and stop rules of spec section 18; that a bundle whose `review.md` (or `plan.md`, or a transcript's reply) quotes a real name is not committed as it stands, since the repository scan reads every text file of a checked-in bundle (R-scan-bundles); the two measurements (a planner call's input size with `docs/01` to `docs/07` in it, and whether the CLI's attached context shows up in authored files); and that its report decides whether the specs are distilled and whether the example bundle is replaced.

- [ ] **Step 2: The phase docs-sync**

HANDOFF Progress gains "Phase 5 (the Director)" with the thirteen tasks (fifteen commits: 4a, 4b, 7a and 7b, R-split), each with its range and review result, and the gate counts; "Next steps": Phase 6 next, rung D waiting on the owner; "Open items": anything a task parked. docs/00: section A `PlanRequest` complete, B the plan records and `RunRecord.plan`, E the `plan` commands and `run --worlds-dir`, F the three prompt files and `plans/`, H "Phase 5 (version 3, additive): `RunRecord.plan`", phase map row 5 complete. docs/08: the layout, the CLI, the review format, the dry run's fixed bully line (A9). Spec "As planned": every **Departs from the spec** line of this plan's Plan Decisions, the plan review's rulings among them, in plan order, one line each, then a one-paragraph summary. The spec text the review's rulings changed is already marked "[refined in the plan review]"; the summary says so.

- [ ] **Step 3: Verify and commit**

Run: `uv run python -c "import pathlib,re,sys; t=pathlib.Path('docs/handoff/phase-7-runbook.md').read_text(encoding='utf-8'); sys.exit(0 if '### Rung D' in t and 'MAX_AUTHOR_CALLS' not in t else 1)"`, then the gate (documents only: the counts equal Task 12's).
Expected: exit 0; the gate green.

```bash
git add docs/handoff/phase-7-runbook.md HANDOFF.md docs/00-RECONCILED.md docs/08-DIRECTOR.md \
  docs/superpowers/specs/2026-11-14-phase-5-director-design.md
git commit -m "docs: Phase 5 Task 13, rung D in the 7b runbook and the phase docs-sync

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review (done when the plan was written; revised after the plan review)

1. **Spec coverage.** Section 1's five success lines: Task 9 (runnable on stubs; the rebuild from `plan.json` and `transcripts/` through `materialize`, tested by `test_materialize_rebuilds_the_authored_files_from_the_record_and_the_transcripts`), Tasks 5 and 7a to 9 (kill points), 10 (`run` on a bundle, `analyze` and `replay` from the run directory), 3, 4a and 4b (the lints), 5 and every task's stubs (no real call). Section 2's decisions: each lands in its task (A1 Task 7b's copy, A2 Task 7b's manifest, A3 Task 7a's `ask`, A4 Task 8, A5 Task 8, A6 Task 10, A7 Task 7a, A8 the constants, A9 replaced by the trace and its committed test, D-A9). Section 3's units: all, with D-cli and D-plan_personas. Section 4: Task 1 (with D-base_files and D-rounds, `rounds` round-tripped there). Section 5: Tasks 1 and 12. Section 6: Task 6 (D-confirm, D-reply), sessions in Task 7a, the fake-claude reset in Task 9, blindness at confirm time in Task 8. Section 7: Tasks 7a to 9. Section 8: Task 7a's `ask` and `run`, K1 to K13 across Tasks 5, 7a, 7b, 8 and 9, with the manifest's commit points (R-commit) and the review render (R-review-md). Section 9: Tasks 3 to 5 (D2, D3, D4, D-outlet, R-premise-terms, R-bare-host). Section 10: Tasks 2 and 5 (R-buried, R-dryrun-pure). Section 11: Tasks 9 to 11. Section 12: the Global Constraints and the scans of Tasks 4a and 12 (R-scan-bundles). Section 13: the error rows map to Tasks 7a and 7b (provider error, continued with no dead attempt, rate limit, timeout, off-contract, document dropped, close failure, ceiling), Task 8 (review that cannot be validated, open block), Task 10 (bundle edited, persona clash), Task 9 (`plan diff` for a moved shipped world). Section 15: every bullet has a test named in a task. Section 16: thirteen tasks in the spec's order, 4 and 7 split (R-split). Section 18: Task 13.
2. **Step scan.** Each test step carries code or a table of exact fixtures; each code step a signature and the values the spec pins; the commit order, the resume loop, `walk_lines`, `slug_for`, the grammar and the stub's index rule are given as code because no signature determines them.
3. **Type consistency.** `lint_bundle(bundle, *, dry_run=None)`, `dry_run(bundle) -> list[DryRunCell]`, `walk_lines(world, ladder) -> list[str]`, `Director.run(*, stop_after_plan, through)`, `run_plan(plans_root, *, through, ...)`, `findings_of(bundle, record)`, `register_plan_personas(personas: Mapping[str, Mapping[str, Any]])`, `PlanStamp.personas: dict[str, dict[str, Any]]`, `director_cache_key(role, system, message, schema)` and `Answer(call, parsed, provider_failed)` agree across Tasks 4a to 12.
4. **Review Focus.** Five lines, each with its test in its owning task (Tasks 1, 7b, 9, 10).
5. **Proportion.** The plan is longer than the spec because it carries every test, as the Phase 4 plan did; the code blocks are tests, the call primitive and the few algorithms no signature fixes.
