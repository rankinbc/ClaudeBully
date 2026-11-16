# Task 13 review: rung D in the runbook and the phase docs-sync (c8c0c5c..64b4cf0)

Scope: documents only, five files. Read-only review; the suite was not re-run (the gate equals Task 12's by the report). The diff, the brief, global constraints, the preflight rows naming 13 (Q55, Q56, Q72), the ledger and the report were read; the report was treated as unverified and each claim below was checked against the code.

## Verdicts

- **Spec compliance: met, with one Important defect.** Rung D is marked "not run", carries no v1 number, holds M2 and N-4, and every command in it exists with the flags it names. The one defect is the seeded-bundle recipe for the 8-of-10 bar (I1): as written it cannot reach most of the defect classes it names.
- **Quality: good, with fixes.** The edits are precise, the HANDOFF ranges are exact, the open items are near-complete and the docs agree with the code. The findings are accuracy and scope notes, none of which blocks the commit on its own except I1, which is a recipe fix.

Counts: Critical 0, Important 1, Minor 5, Nit 6.

## Check 1: rung D against spec section 18

Verified:

- "Not run until the owner says so" opens the section (runbook:703; section heading at :701); the "after Phase 5" bullet (runbook:919) points at it and names no v1 figure. `MAX_AUTHOR_CALLS` and "40 to 100 calls" are gone from the runbook (grep, whole repo: they remain only in the Phase 7 spec section 14, the 7a plan, drafts and ledger text; see M5).
- The command is the brief's, verbatim, plus `--plans-root <a directory outside the repo>`, which is the binding Task 12 M2 carry. Every flag exists in `claude_bully/planner/cli.py`: `--no-confirm` (:291), `--base-world` (:289), `--hypotheses` (:273), `--slug` (:287), `--plans-root` (:294), `--wait-on-rate-limit` (`runner/wait.py:21-27`, minutes). `plan continue`, `plan review` and `plan validate` take a bundle and the same wait flag (:340, :354, :372); `validate` takes none, as the runbook says. `doctor --live` and "Step 0" exist (runbook:196).
- M2 is stated (runbook:716-720, 786-793): an in-flight plan is made outside the repository and moved into `plans/` once runnable and clean. N-4 is stated (runbook:746-753): the example's `plan.md` null pools the arms over two targets (six reps per arm) at `buried_opens` and `the_truth` (`plans/example-triggered-vs-scheduled/plan.md:57-65` agrees), while `item_9` (`analysis/hypotheses.py:1080-1115`) compares per model, each arm's mean over the rungs both arms reached. Accurate, and the "never one as a check on the other" instruction is the right reading. The report's concern that the pooled null is in `plan.md`, not `expected.yaml`, is correct and the runbook words it right.
- The two readers were run: the `plan.json` reader on the example bundle prints stage statuses, each call's `role index purpose status attempts` and `runnable file calls 3 with a retry 0`; the field names (`DirectorCall.attempts`, `.status`, `.purpose`, `StageRecord.error`) match `planner/records.py`. The ledger reader's keys (`role`, `status`) match `LedgerLine`; `input_tokens`, `resolved_model` and the `timeout` status exist (`providers/ledger.py:73,92-112`). `file:<path>` and `repair:<path>` purposes match `director.py:1624`; the transcript name `<stage>-<role>-<index>.json` and its `message` field match `bundle.py:83-84,182-192`.
- The review.md description (first line `block N / fix N / note N`, a `confirm:` line ending `(closed)` or `(open)` under a block) matches `render_review` (`director.py:790-817`).
- The two measurements and the report decision match section 18 and section 17. The stub-measured sizes (195,000 and 235,000 characters against `MAX_CONTEXT_CHARS = 300,000`, `context.py:200`) match the ledger.

## Check 2: HANDOFF accuracy

- **Ranges, review results and fix-round counts: all fourteen entries match the ledger's "complete" lines exactly** (1: 97102a0..262b8a2 clean; 2: d68aa3f..049101d clean; 3: 6f15671..3165ad5, 1 round; 4a: 370b177..ff6a2fc, 2 rounds, 7d67f1e and ff6a2fc; 4b: b54f2e1..5591258, 3 rounds, 8ec2485, dff6e26, 5591258; 5: 40d87e4..855733f clean; 6: 91a3bc8..ff6d18d, 2 rounds, 44ff1fa and ff6d18d; 7a: 7efbebe..be05ee5, 1 round; 7b: 3a1ef89..cceb3bb, 2 rounds, 91f1413 and cceb3bb; 8: b29ed3f..19f5485, 3 rounds, 93a60f0, e57d54e, 19f5485; 9: 9ca91d4..6e90524, 2 rounds, 9639ab8 and 6e90524; 10: 82d7257..cb2731f, 1 round; 11: 7c91808..8f57428, 1 round; 12: 72ed8f0..1dda514, 2 rounds, e191082 and 1dda514). A word-level diff of the fourteen entries shows only the parenthetical changed ("one commit on <base>" replaced); no detail was lost.
- **Gate counts:** 10766 passed, 11 skipped, 215 deselected, slow 215 (HANDOFF:42 and the Progress bullet); the 9825/9/48/48 start is Phase 4's close.
- **Next steps:** item 1 says the Phase 5 final whole-branch review is next, then one fix wave and a re-review; item 2 says Phase 6 next; rung D is written and waits on the owner (items 1, 2 and 4). Correct.
- **Open items:** the "From Phase 5" group (HANDOFF:316-323) carries every "minor (deferred, final review)" and "carry to the final fix wave" ledger line: Tasks 1, 2, 4a, 4b (closed note), 5, 6, 7b, 8 (N7, N9, N10), 9 (both ledger lines and the round-2 notes), 10, 11 (the `stale` reason and three notes), 12 (M-1 and two of three nits), plus the plan's two stated residuals. The Task 11 "N2" item under the Phase 4 group is marked closed. **Missing: one nit.** The Task 12 re-review's third nit (the report's claim "the owner pattern has no lookahead" is wrong, no effect; ledger line 216) is not carried (N3).

## Check 3: docs/00, docs/08 and "As planned" against the code

- **Bundle layout (docs/08:29-44):** the outputs table and the path grammar match `bundle._GRAMMAR` (`bundle.py:69-74`: `plan.md`, `config.yaml`, `expected.yaml`, `review.md`, `worlds/<name>/{world.yaml, corpus/<stem>.md, ladders/<stem>.yaml, premises/<stem>.yaml}`, `personas/<stem>.yaml`; `NAME` regex and device stems), the transcript shape (`Transcript.system_sha256, model, attempts`), the hash excludes (`HASH_EXCLUDES`) and the git-ignored `plans/_cache/`, `plans/*/dryrun/`, `plans/*/state/` (`.gitignore`). The example bundle has no `ledger.jsonl`, as docs/00 says.
- **CLI (docs/00:132,152, docs/08 CLI block):** five subcommands `new`, `continue`, `review`, `validate`, `diff`; the flag list, exit codes 0/1/2/3, the open-block refusal text (`failed: <n> open block(s); edit the bundle and run plan review`, `cli.py:158-159`) and `new`-on-an-existing-plan behaviour match `cli.py`. `run --worlds-dir` (docs/00:154) was checked by the Task 10 review; not re-read here.
- **Review format (docs/08 "The review as rendered"):** matches `render_review`, including `confirm: none (open)` and "Stage 3's render has no confirm line".
- **Dry run's bully line (A9):** `DRYRUN_BULLY_LINE = "I hear you. Go on."` (`dryrun.py:83`); `not_applicable` only when `ladder is None` (`dryrun.py:331-336`). Matches.
- **docs/00 sections A, B, F:** already carry `PlanRequest`/`PlanBudget` (:26-27), `PlanRecord` and `RunRecord.plan` (:62, :75, :79), the prompt files and `plans/` (:158, :160), as the report says; section E, G11, G16, H and phase-map row 5 read correctly.
- **"As planned":** 19 D- lines and 8 R- lines is the 27 the plan marks, in plan order; the summary's arithmetic checks (14 reviewed task commits, 3 clean, 11 with fix rounds, 20 rounds in all). One stale-by-misstatement claim (M1) and one omission (M4, below).

## Check 4: real names and emojis

Added lines carry no occurrence of the owner's name (0 of 244) and no emoji or arrow; the one non-ASCII character added is an en dash in docs/08 text moved from the original table. No CR in added text; five files only, no code. The name occurrences already in HANDOFF and docs/08 are unchanged (5 and 1 before and after).

## Findings

### Critical

None.

### Important

**I1. The seeded-bundle recipe cannot reach the defect classes it names (runbook:764-774; spec "As planned" Task 13 ASSUMED, spec:786).**
The bar says the controller plants ten defects in "a scratch copy of the example bundle", including "an unlock line that announces its evidence by paraphrase" and "a document whose main point is the premise", then runs `plan review <copy>`. But stage 3 shows the reviewer only files that are not "unchanged base files", and `unchanged_base_files` is defined by manifest membership, not by bytes: "the files of the base copy that no manifest entry names ... never reviewed in full ... A patched base file is an entry" (`planner/context.py:270-278`, used at `director.py:464-465`). The example's `plan.json` has 54 `base_files` (the whole overlay copy) and a manifest of two entries, `config.yaml` and `expected.yaml`. So an in-place edit to a corpus document or to the world sheet's `unlock_lines` (where unlock lines live, `WorldSheet.unlock_lines`) is shown to the reviewer as an index line only (id, layer, kind, title, address, links; "never its body", `context.py:565`). Those planted defects are invisible by construction, so the check would score near 0 of 10 for them and fail the bar for a reason that says nothing about the reviewer.
Fix: say in the bar that every planted defect is either a new file (a new `worlds/overlay/corpus/<stem>.md`, a new `personas/<stem>.yaml`, a changed `plan.md`, `config.yaml` or `expected.yaml`) or, for an edit to an overlay file, that the controller first adds a manifest entry for that path to the copy's `plan.json`, and cite `context.unchanged_base_files` as the reason. Record the same in the spec's Task 13 ASSUMED bullet.

### Minor

**M1. "The spec fixes no mechanism" is not what section 18 says (runbook:771-772; spec:786 against spec:444).** Section 18 names one: "the fixture bundles of section 15, run once through the real reviewer". The recipe departs from it for a good reason (those are lint fixtures the lints and scans stop before any reviewer call), but both documents say the spec is silent. Fix: reword to "section 18 names the fixture bundles of section 15, which are lint fixtures the stage 3 scans and stage 5 lints stop before the reviewer, and the CLI has no reviewer-only command, so ..." in both places; "As planned" exists to record departures, so this one should read as one.

**M2. The call estimate understates the rung (runbook:722-727, 764-774; HANDOFF:230).** The runbook adds a second plan-sized run (`plan review` on the scratch copy, "its own ceiling of 120 calls") but the Estimate paragraph, HANDOFF item 4 ("50 to 110, no run of a bundle") and the spec summary all give 50 to 110 only. The rung can cost up to about 230 calls. Fix: state "50 to 110 for the plan, plus up to 120 for the seeded check" in the Estimate paragraph and in HANDOFF:230.

**M3. The commit step is silent on bundle size (runbook:786-793).** `TranscriptAttempt` stores each attempt's whole `message` (`bundle.py:182-186`), and a planner message is about 195,000 to 235,000 characters at build (the runbook's own measurement). Across 50 to 110 calls a real bundle's `transcripts/` run to tens of megabytes, against 135 KB for the stub-built example, and the repository scans read every text file. Fix: add the bundle's total bytes and `transcripts/` bytes to the report's list, and make "commit `transcripts/` or not" an explicit owner decision in the commit paragraph.

**M4. docs/08's validation table omits two built lints, under a sentence that reads as complete (docs/08:204, table at :206-224).** "Every row below is built" is true of the rows present, but `seam_dead_ends` and `outlet_backing` (spec section 9:267-268, built in Task 3, listed in `bundle_lints.py:174-175`) have no row, so the table is not the full lint set the sentence implies. Fix: add the two warn rows (one line each), or word the sentence as "every lint named here is built".

**M5. A stale v1 figure remains one hop from the runbook (Phase 7 spec section 14, `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md:330`).** It still says "about 40 to 100 planner and reviewer calls (`MAX_AUTHOR_CALLS = 80` is the ceiling)". The runbook's intro promises "where this file departs from the spec's text, the line says so" (runbook:18-19), and rung D's 50 to 110 under `max_director_calls = 120` departs from it without saying so. Fix: one sentence in Rung D ("the Phase 7 spec's 40 to 100 and `MAX_AUTHOR_CALLS` are v1's; Phase 5 spec section 18 governs"), or a line in that spec's "As planned".

### Nit

- **N1. Two 450-character `python -c` one-liners (runbook:734, 740)** are hard to read, review and edit; the report ran them, which is the right check, but a short `scripts/` file (or three shorter commands) would read better and be reusable at the rung. Per the workspace rule, ask the owner whether to keep them as a re-usable script.
- **N2. `<a directory outside the repo>` (runbook:711)** leaves the controller to invent a folder. The rung's own output convention (runbook:58, `output/phase7_<rung>_<date>/`, git-ignored) gives a home that is not under `plans/`, which is all the scans need: `--plans-root output/phase7_rungD_<date>/plans`. Name it.
- **N3. HANDOFF:323 omits the Task 12 re-review's third nit** (the report's "owner pattern has no lookahead" claim is wrong, no effect). One clause.
- **N4. The runbook intro (runbook:17) lists `plan new`, `plan review` and `plan validate` as read against the live `--help` but rung D also uses `plan continue`**, which exists with the flag named; add it for completeness.
- **N5. "into a slug of its own beside it" (runbook:713-714)** reads as `plans/` beside the example, then the next sentence says the plan is made elsewhere and moved in. Say "once moved in, beside it".
- **N6. The ledger snapshot under `docs/handoff/sdd/2026-11-14-phase-5-director/` lags** (it was written at Task 12's close, `c8c0c5c`); the report names it as the controller's step and HANDOFF Next steps 1(b) says to regenerate the package. Refresh it with this review's result when Task 13 closes.

## What was checked and found sound (no action)

- The 27 departure lines against the plan's Plan Decisions (19 D- ids and 8 R- ids, in plan order); the plan-review rulings are the last eight; the "[refined in the plan review]" marks stand in the spec text.
- Gate honesty: the commit changes five Markdown files; the full gate's counts are the report's and equal Task 12's; `tests/test_director_prompts.py` and `tests/test_director_context.py` (the readers of docs/08 and docs/01-07) were run alone first (84 passed), a sound ordering for a documents-only change.
- docs/00's "version 3, additive" lines: `RunRecord.plan` is the phase's one run-record change; Task 13's line says documents only.
