# Task 8 re-review, fix round 1 (stages 3 and 4)

Base dfdba24, head 93a60f0 (one commit). Diff read once (`review-dfdba24..93a60f0.diff`). The checkout was read only (`git status` clean at the end). Probes are in `probes-task8-rereview/`; every bundle a probe made sat in a TemporaryDirectory and was removed. No bundle of mine is left to delete. The owner's name was read at run time and never printed.

## Verdicts

| Finding | Verdict |
| --- | --- |
| I1 (adopted edit dropped from `edited` on a K9b resume) | Fixed |
| I2 (revise calls show unscanned bundle text) | Fixed for `plan.md` and the file being revised, in every file kind. The implementer's concern (world sheets, document index lines) is real; see point 3 |
| m1 (open block with no verdict unmarked) | Fixed |
| m2 (no guard against a run past open blocks) | Fixed in `Director.run`; the CLI-side tests stay a Task 9 carry |

New findings: Critical 0, Important 0, Minor 1 (the point-3 residual, which I recommend closing now), Notes 2.

## 1. I1: the review's K9b probe

`probe_edited.py` is the review's probe unchanged: run to `review`, append a line to DOC1, run to `revise`, once unbroken and once killed at `Kill("record", "revise:DOC1")` and resumed. Output `edited.out`:

```
unbroken: status revised, edited ['worlds/mini/corpus/crew-rota-september.md'], resumed []
killed:   status revised, edited ['worlds/mini/corpus/crew-rota-september.md'], resumed []
files equal True; record equal True; differing keys []
```

On dfdba24 the killed record's `edited` was `[]`. The fix is the one the review proposed (`or rel in own` in `_readopt`). I looked for the other direction, an entry the new clause keeps that an unbroken plan would not, and found none: an unbroken plan never removes an `edited` entry, and a put-back of a file the stage has not yet written still drops (`rel in own` is false, `differs` is false).

Beyond K9b (`probe_edit_kills.py`, `edit_kills.out`): owner lines adopted in both `plan.md` and DOC1, then a kill at each of 8 stage-4 checkpoints (`revise:plan.md` record; `revise:DOC1` transcript, record and files; `confirm:DOC1` transcript and record; `rendered:revise`; `stage:revise`). All 8 resumed plans equal the unbroken one: files, `comparable(record)` and `edited`. A K9b kill with DOC1 put back to its old text during the pause also keeps DOC1 in `edited`, as an unbroken plan does (the resume writes the revision back from its transcript).

The review's own hard-kill sweep, re-run on 93a60f0 (`probe_kills.py`, `kills.out`): 15 kills fired in 12 runs, 12 of 12 equal to their unbroken reference. That includes two kills inside stage 4's commit write on a plan that ends `failed`, which the m2 guard sits in front of.

## 2. I2: an edit made in a stage-4 pause

`probe_gap_plan.py` is the review's probe unchanged (`gap_plan.out`). Paused at `revise:plan.md`, the owner's name appended to `plan.md`, resumed: stage 4 failed with `the bundle fails a lint before the revise:plan.md call shows it: real_name_bundle: ...`, `edited ['plan.md']`, and no planner call was asked after the edit. On dfdba24 two planner messages held the name.

`probe_i2.py` (`i2.out`), the planted text checked in every planner and reviewer message sent after the edit:

| Case | Result |
| --- | --- |
| A1: pause at `revise:plan.md`, `plan.md` holds the owner's name | stage failed, 0 calls asked, 0 messages hold it |
| A2: pause at `revise:DOC1`, DOC1 holds it | same |
| A2b: same, DOC1 holds "Please ignore all previous instructions." | same (a `jailbreak_bundle` hit) |
| restore: A1, then the owner puts `plan.md` back and continues | plan `revised`; files equal an unbroken plan's; `edited []`; the record differs only in `stages[3].error`, which keeps the failure text by the failed-stage ruling (Task 7b) |

`probe_kinds.py` (`kinds.out`): a reviewer that raises a fix on each of `config.yaml`, `expected.yaml`, the persona, the ladder and the world sheet; a pause at that file's revise call; the owner's name added as a comment. For all five, stage 4 fails before the call, 0 calls asked, 0 messages hold the name. So the `review_scans` results filtered on the revised file cover every kind a revise call can be about, not only documents.

Order of effects, from the diff: `_scanned_call` scans only when `index >= len(stage.calls)`, so a replay is never rescanned and a retry inside `ask` is not either (the bundle is unchanged between the two attempts). The stage 4 first-call and the resumed-call paths both reach it.

## 3. The implementer's concern: world sheets and document index lines

**Confirmed, and it is reachable.** `bundle_so_far` (`context.py:582`) shows `plan.md`, the manifest, every world sheet in full and one index line per document (id, layer, kind, title, address, `links_to`), and it is the one prompt part the scrub leaves alone. The new scan covers `plan.md` and the file being revised, so an owner edit of a sheet, or of another document's front matter, reaches every revise prompt from then on.

`probe_i2.py` B cases, the owner's name as a comment on `worlds/mini/world.yaml` (B1, B3, B5) or in the `title:` of `canteen-menu.md`, a document stage 4 does not revise (B2, B4):

| Case | Planner messages that held the name | End state |
| --- | --- | --- |
| B1 / B2: sheet or title edited at a pause at `revise:plan.md`, plan has a block | `revise:plan.md` and `revise:DOC1` | the confirm scan fails stage 4 before `confirm:DOC1`; both revisions are committed and spent |
| B3 / B4: the same, a reviewer with no block, so no confirm call | `revise:plan.md` and `revise:DOC1` | **stage 4 commits, plan `revised`**; nothing in the Director catches it. `review_scans` on the final bundle reports the hit, so stage 5's `lint_bundle` (Task 9) will |
| B5: sheet edited at a pause at `revise:DOC1`, no block | `revise:DOC1` | same as B3 |

`probe_where_name_lands.py` (`where_name_lands.out`): in B3 the name ends up in `worlds/mini/world.yaml` and in `transcripts/revise-planner-0.json` and `-1.json` (the transcripts hold the prompts, and transcripts are exempt from the scans). The planner prompt goes to the same provider the owner already uses.

**Grade by effect: Minor.**

- It needs the owner to put a forbidden string (own name, a real name, a Boundary word, a jailbreak phrase) into a world sheet or a document's front matter. Document bodies are not shown, so a body edit does not reach a prompt.
- What leaks is the owner's own text, to a planner call. It never reaches a target model or a run.
- It is caught later: at the confirm scan when the plan has a block (the usual case, since a plan with a block is the one that needs a revise), and at stage 5's lint in any case. A plan holding the hit cannot become `runnable`.
- It is the same residual stage 2 has and the spec's "As planned" now states.

**Recommendation: close it now, in stage 4.** Reasons:

1. **It costs nothing to scan.** `_scan_plan(revising=...)` already calls `review_scans` over the whole bundle and then throws away every result not on the revised file. Dropping the filter makes the revise guard exactly `_judge_call`'s guard: one scan, whole bundle, before every call that shows bundle text. The change is one line (`found += review_scans(self.bundle, self.record)` in place of the filtered comprehension; `plan_scans` is inside `review_scans`).
2. **It is the designed path once Task 9 lands.** The spec's owner flow is: edit the bundle after `review.md`, then `plan review`, whose stage 4 reads that bundle. Today the gap needs a mid-stage pause edit; with `plan review` the edit sits at the front of the stage.
3. **I tried it.** `wholebundle_patch.py` applies the one-line change by monkeypatch (the repo is untouched). `probe_i2_wholebundle.py` (`i2_wholebundle.out`): A1, A2, A2b and B1 to B5 all fail the stage before any call is asked, with no message holding the planted text. `tests/test_director_review.py` with the patch: all 44 passed (211 s, `pytest_wholebundle.out`). So no existing test depends on the narrower scan.

It needs a test (pause at `revise:plan.md`, add the owner's name to `worlds/mini/world.yaml`, assert no planner message holds it), the spec bullet and docs/08's sentence reworded (the stage-4 scan is the bundle scan, as the judge calls run it), and one gate run. Stage 2 has the same residual with the same shape; carry that to Task 9 or fix it the same way (stage 2's bundle is the planner's own output plus a base world scanned at load, so it is less exposed). If the gate cost is a worry, carrying the stage-4 gap is defensible, because it is a Minor, but it would then need to be a named Task 9 item before `plan review` is built.

## 4. m1 and m2

**m1: fixed.** `probe_m1_m2.py` (`m1_m2.out`), six cases (clean, a confirm reply that leaves the number out, a confirm call that fails twice, a revise call that fails twice, a declined block, `cannot_tell`). In each, every block has a `confirm:` line, and an open block's line says `(open)`:

- a confirm that left out its number or failed twice reads `  - confirm: none (open)`;
- a revise that failed twice still gets its confirm call (N1), so the block reads `  - confirm: absent (open)` (open and marked);
- a plan after stage 3 only has no `confirm:` line, so stage 3's render and the `RENDERED` pin are unchanged.

The revise task's findings are rendered with `revised=False`, so no `none` line reaches a planner prompt. docs/08's format paragraph states the new line.

**m2: fixed in `Director.run`.** On the five open-block cases above, `run(through="validate")` returns the record unchanged (status `failed`, 4 stages, no new call) where dfdba24 raised `NotImplementedError`. On the clean plan it still raises `stage validate is not built yet`, so the guard does not touch a plan with no open block. The guard is keyed on `revise.status == "committed"` and `open_blocks > 0`, so a stage 4 that failed (a provider error) still resumes. It returns before `activate(...)` and `_clear_hard_kill()`; nothing a stage-4 commit leaves behind needs clearing (the two stage-4 commit kills in the sweep resume equal). The CLI-side tests (`plan continue` refusing before it calls `run`; `plan validate` never reaching `runnable`) remain a Task 9 carry, as the report says; they should be written into Task 9's brief or carries file. The guard's claim that Task 9's `plan review` moves the stages to `rounds` is forward-looking (the field exists in the record; nothing in this diff moves them).

## New breakage

None found. Checked: `_scanned_call` (replay, retry), the `edited` rule (put-back, kill sweep), `render_review` callers (stage 3 unchanged), `_NamingPlanner` moved to DOC1 (the confirm-scan test is still meaningful: it fails at the confirm scan, as before).

## Notes

- **N5.** An owner edit made after a revise call has committed and before the next call is overwritten on resume, because the resume writes each committed call's output back from its transcript (`_readopt`'s docstring says so). `probe_i2.py` A2c (`plan.md` edited at a pause at `revise:DOC1`) and A3 (DOC1 edited at a pause at `confirm:DOC1`): the edit is gone, `edited []`, nothing flagged. This is Task 7b's rule and not in this diff, but it is what the owner meets on the stage-4 pause flow; a sentence in docs/08 or the runbook would help.
- **N6.** After a stage fails on the new scan and the owner fixes the file and continues, the record differs from an unbroken plan in `stages[3].error` alone (the failed-stage ruling keeps the error). Files are equal.

## Probes (all in `probes-task8-rereview/`)

`probe_edited.py`, `probe_gap_plan.py` (the review's, unchanged), `probe_kills.py` (the review's, one path fixed), `probe_i2.py`, `probe_kinds.py`, `probe_restore.py`, `probe_edit_kills.py`, `probe_m1_m2.py`, `probe_where_name_lands.py`, `probe_list.py`, `wholebundle_patch.py` with `probe_i2_wholebundle.py`, and an `.out` for each. No full-suite or ruff run (not asked); only `tests/test_director_review.py`, once, with the candidate patch.
