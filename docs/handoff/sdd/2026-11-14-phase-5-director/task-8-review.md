# Task 8 review: stages 3 and 4 (review, revision, blind confirm)

Base b29ed3f, head dfdba24 (one commit). Task-scoped gate. The checkout was read only; probes are in `probes-task8/review/`, and every bundle a probe made sat in a TemporaryDirectory that was removed once it had been compared.

## Verdicts

- **Spec: PASS WITH FIXES.** Every brief item, carry and preflight row Q42 to Q45 is built as specified, with one exception. Resume parity breaks at K9b when stage 4 adopted an owner edit of a file it then revises (I1).
- **Quality: PASS WITH FIXES.** The code is clean and the tests are thorough; I1 and I2 need fixing.
- **Counts:** Critical 0, Important 2, Minor 2, Notes 4.

## Findings

### Important

**I1. A resume drops an adopted edit from `edited` once stage 4 has revised that file (resume parity).** `claude_bully/planner/director.py:1123`

The new `own` rule keeps every path a committed call of the stage wrote out of `differs`. The `edited` filter at line 1123 keeps an existing entry only when `rel not in stage.inputs or rel in differs`. An owner edit adopted when stage 4 opens is in `stage.inputs`, and once `revise:<that file>` commits it is in `own`. A resume after that point therefore removes it from `edited`, while an unbroken plan keeps it.

Probe `probe_edited.py`: run to `review`, append a dull line to DOC1, then run to `revise`. The plan is run once unbroken and once killed at `Kill("record", "revise:DOC1")` (K9b) and resumed:

```
unbroken: status revised, edited ['worlds/mini/corpus/crew-rota-september.md'], resumed []
killed:   status revised, edited [], resumed []
files equal True; record equal False; differing keys ['edited']
```

This is the flow the spec gives the owner: an edit to the bundle, then `plan review` (Task 9), whose stage 4 then revises the edited file.

- **Fix:** keep an own path's membership as the stage found it: `edited = [rel for rel in self.record.edited if rel not in stage.inputs or rel in differs or rel in own]`.
- **Test:** add a K9b row in which DOC1 was hand-edited before stage 4 opened.

**I2. Stage 4's revise calls show the bundle to the planner without the scan that stage 2 runs before it shows `plan.md` (Task 6 re-review N-B, in stage 4).** `claude_bully/planner/director.py:1940` (the revise loop) and `:1850` (`_revise_spec`)

A revise call shows two kinds of bundle text, both unscrubbed:

- `plan.md`, under `## Bundle so far`;
- the file being revised, fenced in the task so that the scrub leaves it as written (`revise_task`, `:813`).

Before a revise call is asked, nothing scans either. The scans run only before the confirm calls.

Probe `probe_gap_plan.py`: a rate limit pauses the plan at `revise:plan.md`, stage 4's first call. The owner's name (read at run time and never printed) is then appended to `plan.md`, and the plan is resumed:

```
call: revise:plan.md: owner name in message True, in Bundle so far True
call: revise:worlds/mini/corpus/crew-rota-september.md: owner name in message True, in Bundle so far True
stage 4 failed; edited ['plan.md']; error 'the bundle fails a lint before the confirm:... call ...'
```

`probe_close.py` (gap) shows the same for DOC1 when it is edited during a pause at `revise:DOC1`. The name reaches two planner prompts before the confirm scan fails the stage. Stage 2 refuses exactly this case for `plan.md` (`_scan_plan`). The carry names only the reviewer and confirm calls, so this is not a breach of the carry's letter. It is the same rule left out of the one other stage whose planner calls show `plan.md` and owner-editable files.

- **Fix:** route each revise call that is about to be asked through the same scan (`_judge_call`'s guard, renamed for example `_scanned_call`). Use at least `_scan_plan()`; `review_scans` would also cover the file being revised.
- **Test:** add one that pauses at `revise:plan.md`, edits `plan.md` with the owner's name and asserts that no planner message holds it.

### Minor

**m1. `review.md` does not mark an open block that has no verdict.** `claude_bully/planner/director.py:798`

A block gets a `confirm: ... (open)` line only when it has a verdict. These open blocks render without one:

- a block whose number the confirm reply left out (Q44);
- a block whose confirm call failed its check twice;
- a block whose revise call errored.

The owner, who is told to edit the bundle and run `plan review`, cannot tell from `review.md` which blocks are still open. The brief pins this format, so the fix needs a ruling.

- **Fix:** after stage 4, write `  - confirm: none (open)` for a block with no verdict, or state the omission in docs/08's format paragraph.

**m2. Carry to Task 9: nothing in `Director.run` itself stops a plan with open blocks.** `claude_bully/planner/director.py:1261`

The implementer's concern 4 is reachable today only as `NotImplementedError`:

- `run(through="revise")` again returns `failed` with 0 calls;
- `run(through="validate")` raises `stage validate is not built yet`.

Probe `probe_close.py` section 4 shows both. The end state (stage 4 `committed`, plan `failed`) agrees with:

- the spec's section 7 stage 4 ("a plan with `open_blocks > 0` is `failed`");
- the section 13 row;
- D-revise-error;
- `PlanStatus`.

Once Task 9 builds `validate`, `Director.run` will walk past the committed stages straight into it. D-revise-error puts the guard in `plan continue`, keyed on a committed stage 4 with `open_blocks > 0` (R-validate-status).

- **Fix (carry to Task 9):**
  - Test that `plan continue` refuses before it calls `Director.run`.
  - Test that `plan validate` on such a plan never reaches `runnable` (spec line 97: `runnable` needs `open_blocks == 0`).
  - Alternatively, put the same guard at the top of `Director.run`.

### Notes

- **N1.** A confirm call is asked for a file whose blocks cannot close, because its revise call failed its check twice or it declined every block. That spends a reviewer call and a `max_director_calls` slot for no possible outcome. It is literal to the spec ("one confirm per file that had a block"), so I leave it as it is. If it is kept, the spec's "As planned" block could say so.
- **N2.** The budget is a lower bound, as the carry rules. Probe `probe_close.py` section 6: the stub plan needs 21 calls, and at `max_director_calls: 20` it passes the manifest's budget (16 implied) and fails at the confirm call with `the plan would pass max_director_calls (20): 20 calls made`. That is clean (stage 4 failed, nothing past the limit), but the say line understates the plan by its stage 4 calls. Worth one sentence in the runbook or docs/08.
- **N3.** A `not_in_group` retry's fix line echoes the reviewer's own `file` value and lists every file of the group (up to 25 paths). This is harmless: it holds only text the reviewer sent and harness paths.
- **N4.** The brief's render test could not pass as written (`personas/p.yaml` against a pinned `## personas/ferry_caller.yaml`). The implementer corrected the test and not the format, which is right.

## Requirements check

| Item | Result |
| --- | --- |
| Interfaces (`REVIEW_CHUNK_DOCS`, `REVIEW_GROUPS`, `review_groups`, `check_findings`, `render_review`, `findings_of`, `review`, `revise`, `ReviewerStub(...verdicts)`) | Present, with the brief's signatures |
| `check_findings` refusals (spec section 7 stage 3) | All five, plus "not the object"; 13 cases with near-misses; a quote is squash-matched against the file's raw text, which is what the reviewer message shows (`reviewer_message` does not scrub) |
| `review.md` written, then `rendered`, then commit with `review_counts` (R-review-md) | Yes |
| `findings_of` the one reader, from transcripts | Yes; a hand edit afterwards changes nothing (test, and a probe) |
| Revise: path order, arrival check, exactly one response, D-revise-error | Yes |
| World re-close within the bound left from stage 2 (Q40) | Yes, its repairs counted in `revise` |
| Block closes only on all three | Yes; probes below |
| `open_blocks`, status `revised` or `failed`, stage committed | Yes |
| Q42 (the dull sentence never equals the quote) | `dull()`; a second round through the Director's own path ends `revised` (probe) |
| Q43 (a provider error on a confirm fails stage 4; continue closes it) | Yes (test; the implementer's `confirm_provider_error` sweep) |
| Q44 (a missing number is no refusal) | `check_verdicts`; the `missing` row stays open |
| Q45 (`no_response`) | Defined; the test passes |
| Scans before each reviewer and confirm call, owner clause, never raise | Yes. The probe counted 4 scans for 4 judge calls, including a retried one (a retry is not rescanned, and the bundle is unchanged between attempts) |
| `review_calls == len(review_groups)` | Good bundle 3, overlay plus two documents 2 (test). Both read `_review_sets`, so they cannot disagree on the same path set |
| Budget counts the review stage by the same rule | Yes; revise, confirm and repairs are uncounted (the carry), and `_check_ceiling` bounds them (probe N2) |
| Rate limit pauses | Yes, on `review:lines` and `confirm:DOC1` (test); also on `revise:DOC1`, with kills in the resume (my sweep) |
| No real model call | Doubles only |
| Gate items I re-ran | `tests/test_director_review.py`, all 39 (including the slow ones), passed in 173 s; ruff check is clean on the touched paths; mypy strict is clean on the three touched modules. Full suite not re-run, as instructed |

## The prompts as built (named risk 1)

Probe `probe_prompts.py`, output in `prompts.out`.

### What each judge call is shown

- **The four judge calls.** The stub plan makes three reviewer calls and one confirm call, each in a fresh session (`reset_session` per conversation id). None holds any of the following:
  - `review.md` text;
  - the name `review.md`;
  - the owner's name;
  - `reasoning_text`.
- **Confirm system prompt.** It is `director_confirm.md` verbatim, as Task 6 pinned it (D-confirm). It asks whether "the stated problem is present anywhere in it, in those words or in others", and it says that a passage "may or may not appear in the file". It contains no cue toward block or pass, and none about a revision.
- **Confirm message, harness parts.** These are `## Passages` (a `call:` line, each passage as a JSON-string quote and its stated problem) and `## Reply` (the fields only). The cue scan found none of: revis, earlier, version, fixed, planner, declined, response, round, sha, hash, diff, before, after, previous, changed, updated, edit, block, fix, severity, author. The message shows no severity, response, status, hash, round number or conversation id.
- **Reviewer messages.** Their parts are `## Bundle`, `### Unchanged base files` (index lines), `## Lint list` (ids only), `## Report on` and `## Reply`. The reply part names the fields and says, neutrally, that an empty report is `[]` with every count 0. The lean in the reviewer system prompt ("find where it would give itself away", "Flag anything that reads as written to persuade") is docs/08's text, kept verbatim by Task 6 and documented as primed to find (Task 6 review M5). It is not Task 8's.

### Round 1 against round 2 through the Director's own path

Plan A is the clean plan. Plan B is authored with DOC1 as plan A's revision left it, so B's review, revise and confirm calls are a second round over the same file. The two confirm system prompts are identical, and the unified diff of the two confirm messages is:

```
-The stairwell light has a new bulb. Day shifts are unchanged from August.
+The noticeboard by the stairs is tidy. Day shifts are unchanged from August.
-1. "The September rota is pinned in the mess room."
+1. "The stairwell light has a new bulb."
```

Only the file's own text and the passage quoted from it differ. `confirm_message(rel, text, passages, fix)` takes no round, hash or history input, so this holds by construction. Plan B ends `revised`, which settles Q42.

### Retry fix lists (named risk 5)

| Failed reply | `### Fix these` line on the retry |
| --- | --- |
| `not_in_group` | "finding 2: 'plan.md' is not a file of this group (<the group's paths>)" |
| `quote_missing` | "finding 2: its quote is not text of <file>" |
| `counts_wrong` | "the summary counts block 2 / ... but the findings are block 1 / ..." |
| `empty_no_summary` | "the reply has no summary; with nothing to report it is {zero summary}" |
| confirm `off_contract` | "the reply is not the JSON object {"verdicts": [...]} and nothing else" |

Every failure is built from the same call's reply and the harness's own paths. `check_findings` never repeats a quote, and `check_verdicts` names only numbers and the verdict string.

- No path reads `review.md`: `reviewer_message` and `confirm_message` refuse it.
- `failures` starts empty for each call in `ask`, so no earlier call's or dead attempt's failures carry over.
- A retry therefore cannot carry `review.md` text or a revision cue into a reviewer or confirm message.
- With `fix=()`, the messages are byte-identical to Task 6's (Task 6's tests still pass).

## Block and close probes (named risk 2)

Probe `probe_close.py`, output in `close.out`. Each row lists, per block: id, `planner_status`, verdict, open.

| Case | Result |
| --- | --- |
| Revise removes the quote but keeps the problem in other words; a judge that reads the file | `(1, fixed, present, True)`: open, plan `failed` |
| Same revision; a lax judge that always answers `absent` | `(1, fixed, absent, False)`: closed. The harness cannot catch a paraphrase on its own. That is the judge's job, by design (A5), and the confirm message gives the judge the whole file and the stated problem |
| Declined, but the quote removed; the judge says `absent` | open |
| Fixed, quote removed; the judge says `present` | open |
| Fixed, quote kept; the judge says `absent` | open |
| Two blocks on one file; verdicts {1: absent, 2: present} | ids 1 closed, 2 open; local numbers map back in id order; `review.md` shows `(closed)` and `(open)` as expected |
| `cannot_tell` | open; status `failed`, stage 4 committed |

## Hard-kill sweep of my own (named risk 6)

Probe `probe_kills.py`, output in `kills.out`. It reuses the implementer's write hooks and snapshot (`probes-task8/hard_kill_sweep.py`), in scenarios and boundaries the implementer's table does not list. **15 kills fired in 12 runs; all 12 runs are equal to their unbroken reference**:

- files;
- `comparable(record)`;
- `resumed`;
- ledger;
- cache;
- transcripts;
- status;
- no `*.tmp`.

| Scenario (not in the implementer's table) | Kill |
| --- | --- |
| two blocks on DOC1, one left open | the confirm transcript write; stage 4's `review.md` write; stage 4's commit write (status `failed`) |
| `cannot_tell` | the `revise:DOC1` file write; the confirm call's cache put |
| `keep_quote` | stage 4's commit write (status `failed`) |
| rate limit on `revise:DOC1` (2 commands) | the resume's first write (`.attempt.json`); the resume's `revise:DOC1` transcript write |
| `review:corpus-1` retried (`quote_missing` once) | its two-attempt transcript write |
| double kill, clean plan | the confirm transcript, then the resume's write 1 (the ledger rewrite) |
| double kill, clean plan | stage 3's `review.md` write, then the resume's write 2 (`plan.json`) |
| double kill, clean plan | `revise:DOC1`'s record write (K9b), then the resume's write 3 (`.attempt.json`) |

The one parity break found (I1) needs an owner edit that the sweep's scenarios do not make; it came from a targeted probe.

## Free disk

- Before: 2,420,695,040 bytes (`Get-PSDrive C`).
- After: 3,087,093,760 bytes (other activity on the machine freed space). Probe output: 58 KB.
