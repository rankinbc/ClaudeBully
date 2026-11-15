# Task 8 re-review, fix round 2 (the whole-bundle scan at stage 2 and stage 4)

Base 93a60f0, head e57d54e (one commit). Diff read once (`review-93a60f0..e57d54e.diff`). The checkout was read only (`git status` clean at the end). Probes are in `probes-task8-rereview2/`; every bundle a probe made sat in a TemporaryDirectory and was removed. Free disk at the end: 2.3 GB. The owner's name was read at run time and never printed.

## Verdicts

| Item | Verdict |
| --- | --- |
| The Minor of round 1 (a world-sheet or title edit reaches revise prompts unscanned; same gap at stage 2) | Fixed. All 8 gap and pause cases fail before any planner prompt carries the planted text |
| Resume parity (the implementer's concern 1) | **Not equal. A new Important finding (I1 below):** a stage 2 resumed mid-stage can fail on the planner's own committed output, and the plan then cannot be continued |
| `_scan_plan` and `_judge_call` removed | Confirmed: no caller left; round-1 tests pass (50 of 50) |

New findings: Critical 0, **Important 1**, Minor 0, Notes 2.

## 1. The 8 gap and pause cases

Stage 4: `probe_i2_head.py` is round 1's `probe_i2.py` with a scenario filter (nothing else changed), run on e57d54e. Outputs `i2_head_a.out`, `i2_head_b.out`. Each case: pause at a stage-4 revise call by a rate limit, the owner edit, the resume.

| Case | Pause at | Edit | Result at e57d54e |
| --- | --- | --- | --- |
| A1 | `revise:plan.md` | owner's name in `plan.md` | stage 4 failed, 0 calls asked after the edit, 0 messages hold it |
| A2 | `revise:DOC1` | name in DOC1 | same |
| A2b | `revise:DOC1` | jailbreak phrase in DOC1 | same (`jailbreak_bundle`) |
| B1 | `revise:plan.md` | name in a comment on `worlds/mini/world.yaml` | same (round 1: both revise prompts held it) |
| B2 | `revise:plan.md` | name in the `title:` of `canteen-menu.md` | same |
| B3 | `revise:plan.md` | as B1, no block, no confirm call | same (round 1: stage 4 committed `revised`) |
| B4 | `revise:plan.md` | as B2, no confirm call | same |
| B5 | `revise:DOC1` | as B1, no confirm call | same |

A2c and A3 (an edit after a revise call committed) still end `revised` with `edited []`, the N5 rule, unchanged and not in this diff.

Stage 2: `tests/test_director_author.py -k "world_sheet_or_a_document_title or plan_md_with_a_denylist"` 3 passed (`pytest_stage2_cases.out`), and `probe_parity.py stage2_sheet stage2_title` (`stage2_edit_head.out`): a rate limit on the first file call, the name planted in the copied sheet or the base document's title, the resume: stage 2 and the plan `failed`, 0 calls asked after the edit, 0 messages hold the name.

So the finding's fix is as described. The cost is I1.

## 2. Resume parity: I1 (Important)

`probe_parity.py` (outputs `parity_kill_files.out`, `parity_others.out`). A planner double writes a hit into one file of stage 2: the owner's name as a trailing YAML comment. Arrival has no owner clause for a non-document file, and `_real_name` of the document lint reads `real_names.txt` only, so the call commits. Cases: unbroken; killed after the transcript, record and files write of the last stage-2 call (`file:expected.yaml`); killed after the stage commit; and a rate limit on `file:config.yaml` after a planted `personas/ferry_caller.yaml`.

| Run | Failed stage | Plan | Stage records | Error |
| --- | --- | --- | --- | --- |
| Unbroken | **review** (stage 3) | failed | plan, author (committed), review (failed) | `before the review:corpus-1 call shows it` |
| Killed after the transcript write, resumed | review | failed | same | same (the call is asked again; the file is not yet on disk at the opening scan) |
| Killed after the record write, resumed | **author** (stage 2) | failed | plan, author (failed) | `before stage 2 shows it` |
| Killed after the files write, resumed | **author** | failed | same | same |
| Killed after the stage commit, resumed | review | failed | same as unbroken | same |
| Rate limit on `file:config.yaml` (after the planted persona), resumed | **author** | failed | same | same |

**Answers.** Unbroken, stage 3 fails. Killed after the last call commits (record or files), then resumed, stage 2 fails. The differing keys of `comparable`: `stages[1].status` (`committed` against `failed`), `stages[1].error` (none against the lint text) and the stage count (3 against 2). Files, transcripts and the ledger's line count (15) are equal; the ledger bytes differ in every pair of runs, even the pairs whose records are equal, so I do not count that. In the rate-limit case stage 2 also stops with `config.yaml` and `expected.yaml` never authored, 14 ledger lines against 15.

**Cause.** A resume of stage 2 first writes each committed call's output back from its transcript (`rematerialize_open_stage`), then `_scan_bundle("stage 2")` reads the whole bundle, the planner's own earlier output included. An unbroken pass opens stage 2 with only `plan.md` and the base worlds on disk, so it never sees that output at the opening.

**Grade by effect: Important, not a nicety of the failed stage's name.** The record difference alone would be Minor (both end `failed`, nothing is shown to a model). The effect is the recovery:

- Unbroken, the owner removes the hit from `expected.yaml` and continues: stage 3 runs and the plan ends `reviewed`.
- Resumed, the owner removes the hit and continues: `_reopen_failed` reopens stage 2, `rematerialize_open_stage` writes the committed call's text back over the owner's fix, the opening scan fails again, and the plan stays `failed` with the planted text back in the file. Verified for the kill after the files write and for the rate limit (`parity_kill_files.out`, `parity_others.out`: "the planted text is back in the file: True; bytes equal the planted file: True"). The owner has no way out inside the Director (the transcript would have to be edited, or the plan started again, which spends the whole stage's calls).
- At 93a60f0 the same resumed case recovers (`parity_old_scan.out`: both runs `reviewed`, records equal). So I1 comes from this diff.

How likely: it needs a planner-written hit in a file whose arrival check does not read the lists (a persona, ladder, world sheet, `expected.yaml` or `config.yaml`: a real name, an owner's name, a Boundary or jailbreak string) and any interruption of stage 2 after that call commits. A rate limit mid-stage is the common interruption (a stage 2 is about 15 calls). The planner is told not to write names, so the hit is rare; the harm when it happens is a plan that can never pass stage 2.

**Smallest fix (tried).** Stage 2's opening scan leaves out the paths its own committed calls wrote. Those files are the planner's output rebuilt from transcripts, never owner text (an owner edit to one is overwritten on resume), and they are scanned by the first stage-3 reviewer call as in an unbroken pass. Everything the round-2 fix was for (plan.md, base and copied worlds, a document title) is still scanned. In `author()`:

```python
own = {rel for call in stage.calls for rel in call.outputs}
self._scan_bundle("stage 2", besides=own)   # review_scans(...) results with doc_id not in besides
```

`_scan_bundle(before, besides=())` filters `r.doc_id not in besides` before `_refuse_hits`; stage 3 and 4 callers pass nothing. I applied it by monkeypatch (`FIX_STAGE2_SCAN=1`, repo untouched): all four interrupted cases above end exactly as the unbroken run (`comparable` equal, stage 3 fails), the owner's fix then continues to `reviewed` (`parity_with_fix.out`), and the stage-2 sheet and title cases still fail before any call (`stage2_edit_fix.out`). It needs one test: a kill after the record write of a stage-2 call that wrote a hit (a persona with the owner's name) must end with stage 3 failed, as the unbroken plan, and a continue after the owner's edit must reach `reviewed`.

## 3. Removed helpers and the round-1 tests

- `grep -rn "_scan_plan\|_judge_call" --include=*.py` finds no caller in `claude_bully/` or `tests/`. What remains is prose (HANDOFF, the spec, the Task 7b report, which state the removal or are history) and two old probe files under `.superpowers/` (`probes-task7b/mutations.py`, `probes-task8-rereview/wholebundle_patch.py`), which no test imports. `ruff check` on `director.py` and the two test files: clean (the `functools` and `plan_scans` imports went with their last use).
- `tests/test_director_review.py` in full (`-m "slow or not slow"`, 228 s): 50 passed, which holds round 1's K9b test, the m1 and m2 tests and the 8 pause cases. `tests/test_director_author.py -k "world_sheet_or_a_document_title or plan_md_with_a_denylist"` (the N-B test and the two new ones): 3 passed. I did not re-run the whole gate.

## New breakage

I1 above. Nothing else found: `_scanned_call` still scans only when `index >= len(stage.calls)`, so a replay is never rescanned; stage 3's and stage 4's error text for a reviewer, revise or confirm call is the one round 1 had (`the bundle fails a lint before the <purpose> call shows it`); stage 2's text changed to `the bundle fails a lint before stage 2 shows it` and the author test asserts only `real_name_bundle: `.

## Notes

- **N7.** Stage 4 has the same overwrite rule at its confirm scan, and it is not in this diff. `probe_stage4_overwrite.py` (`stage4_overwrite.out`): the planner's `revise:DOC1` content holds the owner's name, so the scan before `confirm:DOC1` fails stage 4; the owner removes the line and continues; the committed revise call's text is written back and stage 4 fails again. The confirm scan was whole-bundle before this diff (`_judge_call`), so this is Task 7b's resume rule meeting an older scan, not fix round 2. The remedy is a design choice (let a resume keep an owner's edit of a file a committed call wrote, or scan a revised file's own text differently), so it belongs to a Task 9 item; the stage-2 filter above does not reach it, and I would not widen this fix round for it.
- **N8.** The test for the stage-2 gap pauses at the first file call, which the implementer states: neither file is one stage 2 has written. The new I1 test has to pause after a call that wrote the hit, so it covers what that test cannot.

## Probes (all in `probes-task8-rereview2/`)

`probe_i2_head.py` with `i2_head_a.out` and `i2_head_b.out`; `probe_parity.py` (cases `unbroken_vs_kill_files`, `kill_record`, `kill_transcript`, `kill_stage`, `rate_limit_mid`, `stage2_sheet`, `stage2_title`; `OLD_STAGE2_SCAN=1` gives 93a60f0's stage-2 scan, `FIX_STAGE2_SCAN=1` the candidate fix) with `parity_kill_files.out`, `parity_others.out`, `parity_old_scan.out`, `parity_with_fix.out`, `stage2_edit_head.out`, `stage2_edit_fix.out`; `probe_stage4_overwrite.py` with `stage4_overwrite.out`; `pytest_stage2_cases.out`, `pytest_review_all.out`.
