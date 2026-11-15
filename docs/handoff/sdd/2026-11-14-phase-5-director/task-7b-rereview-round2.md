# Task 7b re-review, fix round 2

Scope: 91f1413..cceb3bb (one commit, `review-91f1413..cceb3bb.diff`, read once). Read-only on the checkout; probes in `probes-task7b-rereview2/` (41 KB), each writing only under a `TemporaryDirectory`. Disk 2.16 GB free before, 2.48 GB after. `git status` clean.

## Verdicts

| Finding | Verdict |
| --- | --- |
| M5-new (the budget over-counts a reused world) | FIXED |
| The `inputs` spec line (spec section 4 and the M2 bullet) | ADDRESSED. One wording Note |
| N-A (a complete last ledger line with no newline) | FIXED |
| N-B (`_ledger_raw` split on `splitlines`) | FIXED |

Counts: new Critical 0, new Important 0, new Minor 0, new Notes 3 (below). Fast tests `tests/test_director_author.py -m "not slow" -W error`: 34 passed (31 before plus the 3 new). `mypy` on `context.py` and `director.py`: clean.

## 1. M5-new: the budget (check 1)

The code: `_review_calls` builds `{plan.md, *base_files, *entry paths}`, subtracts `context.unchanged_base_files(base, entries)` (the base files no entry names) and hands the rest to `review_calls`. That leaves `plan.md` plus the entries, which is the spec's review set ("the files the planner wrote"; `ReviewGroup.index` shows the rest by one line each).

`probe_budget.py` (`probe_budget.out`), the shipped `overlay` world (46 documents, 54 base files) reused:

| Case | Count | Independent oracle `review_calls({plan.md, *entry paths})` | Old formula |
| --- | --- | --- | --- |
| overlay plus 2 new documents, config, expected | 2 | 2 | 4 |
| 22 patched base docs plus 2 new (24 documents) | 2 | 2 | 4 |
| 23 patched plus 2 new (25 documents) | 2 | 2 | 4 |
| 24 patched plus 2 new (26 documents) | 3 | 3 | 4 |
| 25 patched base docs, no new | 2 | 2 | 4 |
| 26 patched base docs, no new | 3 | 3 | 4 |
| 2 new documents plus the base `world.yaml` patched | 3 | 3 | 4 |
| `base_world` None, a shipped world named, not yet copied (2 new docs) | 2 | 2 | n/a |

- Plan fits at `max_director_calls` 8 and is refused at 7: limit 8 gives no refusal; limit 7 gives "1 calls made, the manifest call, its 4 file calls and 2 review calls make 8".
- A plan that adds or changes a base file counts it. The count steps from 2 to 3 exactly when the changed documents cross 25 (23 patched plus 2 new is 25 documents and 2 calls; 24 plus 2 is 26 and 3). A patched `world.yaml` adds the `lines` group. A 26-document plan fits at its exact total of 33 and is refused at 32.
- The new test goes red on the old formula (`probe_red.py`: the test raises `AssertionError` with `_review_calls` monkeypatched back to the 91f1413 body).
- The shipped-world-still-to-be-copied case needs no files listed: its unchanged files add no call and its changed files are entries (row 8).

One residual, not a finding: an entry that names a base file and writes it byte-identical is counted and reviewed in full by this rule, where spec section 7's sentence "the files that differ from the base copy" would not. The error is one call too many, the safe side. Task 8's `review_groups` must use the helper's rule (by entry) and the spec sentence should say so (Note 2).

## 2. The ledger tail and the split (check 2)

`_drop_torn_ledger_tail` now reads: no lines, return; the last line does not parse, drop it; the last line parses and the file does not end in `\n`, keep it and rewrite; else return. The rewrite is `raw.decode() + "\n"` per kept line through `write_atomic`, which writes bytes as given.

`probe_ledger.py` (`probe_ledger.out`, 19 checks, 19 PASS) on this machine's real ledger, where `Ledger.write` produces CRLF lines (stage 1: 1 line; through stage 2: 15 lines, every line ending `\r`):
- A cut between `\r` and `\n` is restored to the original bytes. A record with `\r\n` stripped gets `\n` (record bytes kept). A second pass changes nothing.
- A torn last line is dropped and every kept line is byte-identical, `\r` included. Every kept line still parses (`LedgerLine.model_validate_json` over each line with its `\r`; `Ledger.lines()` reads the file).
- `_drop_dead_lines` over the CRLF ledger drops exactly the named line and leaves every other line's bytes unchanged (the old `read_text` round trip had turned `\r\n` into `\n`; the bytes route keeps it, an improvement). A marker naming no line leaves the file untouched.
- N-A end to end: stage 1's ledger cut to no newline, `Director.open` and `run(through="author")`: 15 lines, none holding two records, a further pass raises nothing. This is the review's own `probe_glue` scenario, which glued before.
- N-B: three lines carrying raw U+2028, U+2029 and U+0085 (confirmed emitted unescaped): `_ledger_lines` is 3 (the old `splitlines` gives 6 pieces); `_clear_hard_kill` leaves the file alone; `_drop_dead_lines` drops exactly the named line and validates the others whole; a complete last line carrying a raw separator with no newline is closed off with its bytes kept; a torn tail after separator-bearing lines is dropped.
- `_ledger_lines` stays equal to the line count after the tail repair, so a marker's `ledger_lines` offset still means the same.
- Both ledger tests go red on the old code (`probe_red.py`: `_drop_torn_ledger_tail` and `_ledger_raw` monkeypatched back, `AssertionError` or an exception from the test).

A kill inside the new rewrite is the same `write_atomic` the round 1 sweep covered: the original ledger stays and the next pass removes the temp (`remove_leftovers` runs first in `_clear_hard_kill`). No new kill point.

The new splitting test covers LF lines only and the newline test strips a CRLF to a bare record, so no test pins a kept `\r`; the probe does. Not a defect.

## 3. The spec line (check 3)

Section 4's `StageRecord.inputs`: "path to sha256 of every bundle file the stage reads, as of the stage's latest entry: a stage entered again after a kill, a pause or a failure re-records it; what an earlier call of the stage saw is pinned by that call's transcript, which holds the message sent, and its `cache_key`, a hash of it".

- "As of the stage's latest entry" matches the code: `author` opens with `_open_stage("author", adopt=True)`; on an open stage `_readopt` re-records each path of `inputs` as it now is and `edited`, writing only on a change. All three entries are one path: after a kill and after a pause the stage is open, after a failure `_reopen_failed` opens it, and each reaches `_readopt` (the first re-review's probe_inputs case B showed it).
- "The transcript holds the message sent": `ask` writes `TranscriptAttempt(message, reply)` for every fresh and cached attempt, and a retry's message too.
- The M2 bullet ("calls committed before a pause are read from their transcripts, never from `inputs`") and the D-copy bullet ("opened with its `inputs`") agree with it. Spec line 221's "the next stage adopts what it finds (`StageRecord.inputs`, `PlanRecord.edited`)" still holds.

Wording Note (Note 1): "`cache_key`, a hash of it" is a hash of the message together with the model, the role's settings, the schema, the system prompt and `DIRECTOR_CACHE_VERSION` (`director_cache_key`), not of the message alone. Two calls with different messages still get different keys, which is the property the line relies on. Also a `provider_failed` error call's transcript holds no attempt (the attempt is appended after the provider returns), but that call fails the stage, so no later call is described by it.

## 4. New breakage

None. Nothing changed in a record or a schema. The spec's budget bullet, the fix-round-2 bullet and the HANDOFF line match the code and the numbers above (overlay plus 2 new documents counts 2 and fits at 8).

## Notes (none blocks)

1. The `cache_key` wording above. Fix: "a hash of it with the model, the role's settings, the schema and the system prompt".
2. Carry to Task 8. The plan's Task 8 text (`docs/superpowers/plans/2026-11-14-phase-5-director.md`, the `review_groups` test at about line 3157) and `task-7b-carries.md` do not mention `unchanged_base_files`; only the fix report's ASSUMED line and the spec's fix-round-2 bullet do. Task 8's `review_groups` should build `index` from it, and the parity test the first re-review asked for is still unwritten: `review_calls` over the manifest equals `len(review_groups(...))` on the good bundle and on a reuse bundle with unchanged files. State in spec section 7's review-set sentence that "differ from the base copy" means "named by a manifest entry".
3. Pre-existing and outside this diff: `providers/ledger.py` `Ledger.lines()` (line 193) and `Ledger.fold()` (line 205) still read with `splitlines`. `probe_ledger_lines.py`: a line holding raw U+2028 written by `Ledger.write` makes `Ledger.lines()` raise `ValidationError`. The run ledgers' readers (`analysis/load.py:181`, `analysis/run_analysis.py:253`, `doctor.py`) share it, and Task 9's reading of the plan ledger will if it uses `Ledger.lines()`. Fix when touched: split on `"\n"` there too, or have Task 9 read the plan ledger through `parsed_lines`.

## Probes

All in `probes-task7b-rereview2/`: `probe_budget.py` and `.out`; `probe_ledger.py` and `.out` (19 checks); `probe_red.py` and `.out` (3 passed: each new test goes red under its old code); `probe_ledger_lines.py` and `.out` (Note 3). Commands ran in Git Bash with `/c/Users/Brian.Rankin/.local/bin` on PATH, each under `timeout 300`.
