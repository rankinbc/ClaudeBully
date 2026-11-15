# Task 7b re-review, fix round 1

Scope: 32d9acd..91f1413 (one commit, `rankinbc1@gmail.com`, trailer present). Read-only on the checkout; probes in `probes-task7b-rereview/` (51 KB). Disk 2.06 GB free before, 2.07 GB after; every kill root lived in a `TemporaryDirectory` and was removed as soon as it was read.

## Verdicts

| Finding | Verdict |
| --- | --- |
| I1 (temp left by a kill inside the stage-opening write) | ADDRESSED |
| M1 (torn last ledger line wedges every resume; re-graded Important) | ADDRESSED. Mid-file damage raising out of `run()` is right (below). Two Notes |
| Hard-kill sweep: 3 resume failures, 2 cache-litter cases | ADDRESSED, all five |
| M2 (`inputs` and `edited`) | ADDRESSED for case A; case B records the current text, a Minor misstatement for the calls before the pause (below). No per-call field recommended |
| M3 (front-matter layer) | ADDRESSED |
| M4 (missing ladder under `triggered`) | ADDRESSED |
| M5 (budget count) | ADDRESSED for chunking. New Minor: the count over-counts a reused world |

Counts: new Critical 0, new Important 0, new Minor 1 (M5-new), new Notes 3. Fast tests `tests/test_director_author.py -m "not slow" -W error`: 31 passed. The new slow tests (`-m slow -k "leaves_no_temp_file or torn_last_ledger or re_recorded"`): 9 passed.

## 1. The review's 20 hard kills, re-run with its own probe

`probes-task7b-rereview/hard_kill_sweep.py` is a copy of the review's probe, unchanged. The unbroken write logs (`list_*.out`) match the review's line for line (104, 94 and 110 writes), so event indexes mean the same writes. Each kill is a hard kill: inside `write_atomic` (temp half written, no rename, no cleanup) or inside `Ledger.write` (torn line, no newline). The probe compares the hashed files, `comparable(record)`, `resumed`, the ledger's (id, status) lines, the cache keys, every transcript's bytes, the status and every `*.tmp` under the plans root (bundle and cache both).

| Scenario | Kills | Result |
| --- | --- | --- |
| clean | 10, 14, 20, 22, 24, 25, 30, 31, 96, 104 | 10 of 10 equal to the unbroken run, no resume raised, no `.tmp` left. Kills 10 (I1), 22 (M1), 25 and 31 (cache litter) were the four that failed before |
| still_fails | 88, 89, 90, 92, 93 | 5 of 5 equal |
| timeout_config (`--vs-clean`) | 93, 94, 95, 96, 97 | 5 of 5: 96 and 97 equal the unbroken run; 93, 94 and 95 equal a clean run, the dead raising call redone (the same reading the review allowed). Kill 93 (M1) raised before |

Total: 20 kills, 0 mismatches, 0 raised, 0 `.tmp`. The implementer's own sweep (1,051 kills in 10 scenarios) was not re-run; this check is the review's 20.

## 2. M1: the torn tail and the mid-file raise

`_drop_torn_ledger_tail` (director.py, in `_clear_hard_kill`) uses `runner/store.parsed_lines`: a last line with no newline that does not parse is dropped, the ledger rewritten through `write_atomic`; any other line that does not parse raises `ValueError` naming the line, before anything is written. Probe `probe_edges.py` (`probe_edges.out`):
- a tail cut inside a multibyte character is dropped, and the ledger equals its pre-tear bytes;
- trailing NUL bytes (a power-loss extension of the file) are dropped;
- junk in the middle plus a torn tail raises `ValueError`, naming the line, and `plan.json` is untouched.

Ledger lines end `\r\n` on this machine (`Ledger.write` opens in text mode), and the rewrite keeps each kept line's `\r`, so a kept line's bytes are unchanged.

**Is it right for the mid-file `ValueError` to propagate out of `run()`? Yes.**
- Spec section 13 has no row for a damaged harness-written record, and section 8 says only that a resume reads `plan.json` and the files. Nothing there says to fail the stage. The project's rule for a damaged line is the runtime's: raise naming the file and the line, never drop a record without a word (`parsed_lines`' docstring; Phase 4 Task 14's `EnvironmentRuntime._read_log`, in `docs/00-RECONCILED.md`). A bad byte in `plan.json` already raises from `read_record` (deferred minor of Task 4b).
- Failing the stage would be wrong on the mechanics. `_clear_hard_kill` runs before the stage is read, so there is often no stage record to fail. No call failed, so a `failed` plan would misdescribe it. A `plan continue` would meet the same line and fail the same way.
- `DirectorError` is the section 13 "the stage failed" channel; a damaged ledger is not a stage's failure.

The condition: Task 9's CLI must catch `ValueError` from `run()` and print the file and line, not a traceback, and the spec's section 13 should get its row ("A damaged line in `ledger.jsonl`: `run` raises naming the line; the owner repairs or removes it"). Carry both to Task 9. The test `test_damage_in_the_middle_of_the_plan_ledger_still_raises` already pins that `plan.json` is unchanged.

Notes on M1 (neither blocks):
- **N-A.** A last line that parses but has no newline is not dropped, so the next append glues to it. `probe_glue.py` stripped the final newline after stage 1: after stage 2 the ledger's first line holds two records. The next `_clear_hard_kill` that runs (any later stage) would raise at mid-file damage and the plan would be wedged. The window is one byte boundary inside one `write` call, so it is not a realistic kill; a full disk could leave it. Fix: in `_drop_torn_ledger_tail`, if the file does not end in `\n`, rewrite it with the newline.
- **N-B.** `_ledger_raw` (7a code, not in this diff) reads with `str.splitlines()`; `parsed_lines` splits on `\n` only. pydantic emits U+2028, U+2029 and U+0085 raw in `LedgerLine.error` (probe: `splitlines()` gives 3 pieces from one line). A provider error text carrying one splits the line for `_ledger_raw`, which `_ledger_lines` and `_drop_dead_lines` use, and `LedgerLine.model_validate_json` on a fragment raises. Existing since 7a, rare. Fix: read it with `split("\n")` as `parsed_lines` does.

## 3. M2: `inputs` and `edited`

Probe `probe_inputs.py` (the review's, re-run; `probe_inputs.out`):
- **Case A** (plan.md fails the scan, the owner puts the planner's bytes back): `edited []`, `inputs[plan.md]` is the good text's sha (`6df53a8585ae`); the rejected text's sha (`4b0365b70e2c`) is gone; no call saw the bad line. Fixed.
- **Case B** (an edit during a rate-limit pause): `edited ['plan.md']`, `inputs[plan.md]` is the edited sha (`33a70a6281a6`). Two committed calls, `manifest` and `file:worlds/mini/world.yaml`, saw the old text (`6df53a8585ae`); the later calls saw the edit.

**Does the record misstate what an earlier call saw? Yes, for those two calls.** The spec defines `inputs` as the bundle files "the stage read at its start" (section 4); after the fix it is "as of the stage's latest entry". The record says plan.md was edited, which is true, and gives the sha the next calls read, but a reader of `inputs` alone would think the manifest call saw the edited text. Nothing reads `inputs` yet.

**Should `inputs` be per call? No, not now.** Each call's evidence already exists per call: its transcript holds the user message sent (plan.md in full, section 7), and `DirectorCall.cache_key` is a hash of that whole message, so a reader can tell that two calls saw different bytes without a new field. A per-call `inputs` would repeat the bundle's shas on every call record and change the commit write that the kill points pin. Recommend:
1. State the new meaning in spec section 4 and the D-copy bullet: `inputs` is the stage's inputs as of its latest entry; an earlier call's view is its transcript.
2. Task 9's `plan diff` reads a call's view from its transcript when it needs one. If it then wants a field, add `DirectorCall.inputs` (additive, default empty) with that reader, not before.
3. The stricter option from the review (refuse with `DirectorError` when plan.md changes with calls committed) stays available; the ruling chose the record over refusal, and the code does so consistently.

Severity: Minor, a wording and spec fix, no code.

## 4. Spot checks

**M3 (layer).** Probe: a manifest entry saying `buried` for a document whose front matter says `surface` fails arrival with the message naming both layers; an entry with `layer` None passes; a `repair:` call goes through the same `_check_file`, so the same check. The test pins the near-miss. One side effect, N7's dead end made strict: a repair of a buried document that is unreachable (the planner's only route is a change of layer, since the document cannot link to itself) now fails arrival too. That is the intended direction (the manifest's floor and filler share read the entries' layers), and N7 already says the mapping should point at the world's seam documents.

**M4 (ladder).** `environment_refusals` runs `_environments` over the bundle's worlds, under every gating; `dry_run_refusals` then checks only the conditions whose environment passed. Probe on the good config: both ladders bad gives two messages (one per environment); a world not in the bundle gives two `is no world under worlds/` messages and no dry-run refusal on top; the triggered and scheduled cases give exactly one message each (the fix's tests). Cosmetic: for a world that does not load, the refusal list holds `skipped: the ladder of environment ... (world 'mini' does not load)`, a warn-level text turned into a refusal. That only arises when a world has failed to load after its close passed, so it does not reach in practice.

**M5 (count).** The rule now follows the chunking: 25 documents per corpus call, one `lines`, one `plan`, an empty group none; the four parametrized tests hold (25 gives 3, 26 gives 4, 50 gives 4, 51 gives 5), and the good bundle still counts 3.

**New Minor, M5-new: the count over-counts a reused world.** `_review_calls` builds `paths` from `plan.md`, every `record.base_files` path and the manifest's. Task 6's `ReviewGroup` (built) shows the unchanged base files by one index line each (`ReviewGroup.index`; `reviewer_message`'s `### Unchanged base files`), and the plan's Task 8 test asserts `unchanged.isdisjoint(corpus.files)` for the good bundle's two unchanged base documents. So an unchanged base file is no corpus file and no `lines` file. Probe `probe_review_calls.py` (`probe_review_calls.out`), the shipped `overlay` world (46 documents) reused with 2 new documents:
- the budget counts 4 review calls (`ceil(48/25)` = 2 corpus, plus `lines`, plus `plan`);
- the changed files alone give 2 (one corpus chunk, one `plan`);
- at `max_director_calls` 8, which the changed-files count fits, the manifest is refused: "1 calls made, the manifest call, its 4 file calls and 4 review calls make 10".

This reverses the direction the fix report claims (a lower bound that "never refuses a valid plan") for a reused world: it refuses a plan within about 2 calls of its limit. With the default 120 it rarely bites. Fix: build `paths` from `plan.md` and the manifest's entries alone (a patched base file is an entry), or have Task 8 define `review_groups` first and count from it; carry to Task 8 a test that `review_calls` over the manifest equals `len(review_groups(...))` on the good bundle and on a reuse bundle with unchanged files.

## 5. Named checks that held

- `_clear_hard_kill` runs once per stage pass, before the stage is read, so a plan with no record (7a's K1, `plan new` again) is covered; the test parametrizes `[None, plan, author]`.
- The cache sweep is keyed: `remove_leftovers_of` removes only the temp of a key a committed call of this plan names, and the test plants a temp beside an unnamed key and shows it kept. An in-flight put of another plan with the same key could in principle lose its temp; the two plans would need an identical message, so not a finding.
- `_readopt` writes only when `inputs` or `edited` changed (read from the code); the 20 kills show a resumed record equal to the unbroken one, so a plain resume leaves the record as an unbroken run does.
- Free disk: 2.06 GB before, 2.07 GB after (`Get-PSDrive C`).

## Probes

All in `probes-task7b-rereview/`: `hard_kill_sweep.py` (the review's, unchanged) with `hard_clean.out`, `hard_still_fails.out`, `hard_timeout_config.out` and the three `list_*.out`; `probe_inputs.py` and `.out`; `probe_edges.py` and `.out` (M1 variants, M3, M4); `probe_glue.py` (N-A); `probe_review_calls.py` and `.out` (M5-new); `mutplugin.py`, `probe_arrival.py` and `probe_missing_ladder.py` copied unchanged, not re-run. Each probe writes only under a `TemporaryDirectory`.
