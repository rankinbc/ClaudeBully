# Task 15 re-review, round 1: fix commit 4a622b8 on 63384a1

Scope: the Task 15 review's I1, M1 to M9 and N1 to N5 (task-15-review.md), against the fix diff
(review-63384a1..4a622b8.diff, five documents, 39 insertions and 32 deletions). The report's "Fix
round 1" section was treated as unverified. Out of scope by the controller's ruling and not
judged: the HANDOFF placeholders ("awaits its review and push", "the Task 15 commit", "the
fix-round-1 commit", the resume block) and `configs/poisoned_well/chain_stop.yaml`.

## Verdict: Approved. I1, M1 to M9 and N1 to N5 are all addressed. No new Critical or Important.

One new Minor (an unsupported sentence the M9 fix added) and three trivial nits, below.

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| I1 | Addressed | Runbook table header is now "Estimate with `--ratings` (without)"; a legend line follows ("outside the parentheses, the total with `--ratings`; inside them, the total without it (`analyze` alone); all to the nearest 10"); the chain_stop line under it reads "415 with `--ratings`, 345 without", the same order. The figures read right against the review's recomputation (below). |
| M1 | Addressed | HANDOFF "Open items", From Phase 4: new bullet (no script writes the confirm/reject form; `judge_calibration.py` has `--pairs` and `--idle` as its form writers; a rejected candidate is dropped, spec section 9, and only the trigger cache `runs/_cache/triggers/` holds the answer; a 7a-shaped form writer first). Next steps item 1 gains the triage sentence; "What waits on real text" says "(its confirm/reject form is not built yet)". Cache path and spec section 9 checked. |
| M2 | Addressed | `docs/00-RECONCILED.md` section H: the Task 15 bullet now sits between the Task 14 and the "Phase 7b rung 0 fix, Task 12" bullets, inside the list; a blank line then "The version 2 list, kept for the records it introduced:" stands as its own paragraph. The 7b bullet was not lost. |
| M3 | Addressed | Calibrations tied to configs in HANDOFF Next steps item 4, docs/00 section C `07` row, and the spec's "Three calibrations" bullet: judge calibration and completion and taste to `real_vs_fabricated`, `levers`, `checksum_alone`, `poisoned_vs_captor`; item 14's confound to `checksum_alone`; `epistemologist_alone` and `rescue_third_party` settle none. Matches the runbook's bullets and the configs (the two named configs have no Poisoned Well cell; `start_rung` 1 or 2 and the generator ladder sit in the other four). |
| M4 | Addressed | Runbook quirk-bank paragraph: first measurement is the first run of a config with a `start_rung: 1` arm, whichever the owner names first. Checked in the configs: `real_vs_fabricated` `pw_real` (1), `poisoned_vs_captor` `poisoned_well` (1), `levers` `pw_quirk_first` and `pw_scheduled` (1). HANDOFF item 15 follows. "Run `levers` last" kept as a cost note. |
| M5 | Addressed | HANDOFF now "recall 0.41 to 0.53 ... (the held-out one 0.47 before fix round 2's amendment, 0.41 after)". task-7-report.md: 0.47 in fix round 2 (line 517), 0.41 in the "Fix round 2 amendment" section (line 722) and unchanged through rounds 3 and 4. Correct. |
| M6 | Addressed | Task 14 minors entry now lists `DISCOVERY` title and `IDLE PROMPT` replay lines raw, `AUTHORITY` raw, the parser returning None on old unescaped text in the five escaped shapes plus `CROSSOVER` since fix round 1, and `add_generated` comparing the whole record. Matches the ledger's Task 14 rows (the implementer's concerns, M2 ruling, a8a5578 escaping CROSSOVER). |
| M7 | Addressed (as ruled) | `chain_stop.yaml` untouched (`git diff --stat` shows five documents only). HANDOFF "Open items" records the comment-only edit for the final review's fix wave and that spec section 19's "about 300" is amended by the "As planned" Task 15 bullet. |
| M8 | Addressed | HANDOFF "Drafts for Phases 4 to 9" bullet: `README.v2.md` (both copies, `cmp` identical) still lists Phase 4 as "planned" (line 282) and says "21 declared ... `PENDING_DETECTORS`" (line 142); the set holds 9 members in `metrics/events/__init__.py`. Correct. |
| M9 | Addressed, with a new Minor | The spec lead-in reads "The main amendments the tasks appended above, by task (the ledger names every id):" and HANDOFF item 15 says "the main amendments by task". "Main" fixes the overclaim; the parenthesis is new and unsupported (see New-1). |
| N1 | Addressed | One rounding for the table: 1,120 / 310 / 2,440 / 1,130 / 760 / 420 with `--ratings`, 970 / 290 / 2,100 / 980 / 690 / 400 without. |
| N2 | Addressed (runbook, HANDOFF) | Runbook: "each of the 9 target replies from the reply to the reveal line on". `metrics/ratings.py` line 364 takes replies at positions after the reveal line, so the first is the reply to it: 13 target replies minus 4 seeding = 9. The spec's Task 15 bullet still says "after the reveal line" (see Nit c). |
| N3 | Addressed | HANDOFF item 7: "00953a8 (with its amendment 35c8916)", "Fix round 2 amendment (6187d9d..01502b9", "Fix round 4 amendment (00953a8..35c8916". `git log` confirms 7c47f69 and 01502b9 are round 2's two amendments and 35c8916 is round 4's. |
| N4 | Addressed | FUTURE draft (both copies, `cmp` identical): "which the reconciliation (C6) reads as weaker than the ignition docs/09 gives it". C6 in the reconciliation carries the reading. |
| N5 | Addressed | HANDOFF item 14 now says "a bully's `display_name:` set to a real outlet's name is a hit"; no outlet name remains in HANDOFF or docs/*.md. |

## Check 2: the re-rounded estimates agree

The review's recomputation, from the configs by the report's rule: with `--ratings` 1,116 /
309 / 2,442 / 1,128 / 759 / 417; without 972 / 291 / 2,100 / 984 / 693 / 399. To the nearest 10:
1,120 / 310 / 2,440 / 1,130 / 760 / 420 and 970 / 290 / 2,100 / 980 / 690 / 400.

- Runbook table (in config order `real_vs_fabricated`, `epistemologist_alone`, `levers`,
  `checksum_alone`, `poisoned_vs_captor`, `rescue_third_party`): about 1,120 (970), 310 (290),
  2,440 (2,100), 1,130 (980), 760 (690), 420 (400). All twelve match.
- Spec, "The six configs' estimates" bullet: 1,120, 310, 2,440, 1,130, 760, 420, and "970, 290,
  2,100, 980, 690 and 400 without `--ratings`". Match.
- HANDOFF item 11: "about 415 for rung 2 (b), and 1,120, 310, 2,440, 1,130, 760 and 420" (same
  order). Match. HANDOFF item 15's fix-round sentence repeats the six with `--ratings`. Match.
- chain_stop: 345 without and 415 with, in the runbook estimate paragraph, the line under the
  table, the spec and HANDOFF, all the same.
- The table header now says the outside figure is with `--ratings`; the legend says the same and
  the parentheses are without. The header and the legend read correctly and agree with each other
  and with the line under the table. grep for the old figures (1,100, 2,450, 1,150, "Estimate
  (without") finds only history (plan drafts, the Task 11 review, the config comment) and nothing
  live.

## Check 3: new inaccuracy, emoji, non-ASCII

- Added lines (39): 0 non-ASCII bytes (so no emoji), 0 CR; the five committed blobs have no CR;
  the 166 patterns of `data/denylists/real_names.txt` hit none of the added lines.
- No code, record, config or test changed (five documents).
- New-1 (Minor, new). The spec's "As planned" index lead-in says "(the ledger names every id)".
  It does not: `progress.md` carries no `C40`, `P31`, `P29`, `P35`, `C44`, `P19` or `V21`; those
  ids sit in the preflight, the task briefs, carries and reports and the spec's own sections
  (e.g. `C44` only in task-13-report.md). In HANDOFF, "the ledger" is `progress.md`. Say "the
  preflight and the task reports name the rest", or drop the parenthesis. Not a Task 15 gate.
- Nit a: "all to the nearest 10" (legend) and the report's "one rounding for every about figure"
  hold for the table; "about 345" and "about 415" are the exact stub-run sums (245 + 10 + 20 + 70,
  then + 70), not tens. Harmless.
- Nit b: HANDOFF Next steps item 4, "`checksum_alone`'s states register item 14's confound",
  reads awkwardly ("states" is the noun); "and `checksum_alone`'s with-rungs arm registers item 14's
  confound" would be clearer.
- Nit c: the spec's Task 15 section 19 bullet keeps "9 `rate_escape` after the reveal line"; N2
  was fixed in the runbook and HANDOFF only. True as written (the reply is after the reveal line).

## What I did

- Read the fix diff once (word-level, since the lines are long), the review, and the report's Fix
  round 1 section.
- Re-read the changed passages in the current files: runbook table, legend, chain_stop line, quirk
  bank paragraph, calibration bullets; HANDOFF items 7, 11, 14, 15, Next steps 1 and 4, Open items
  and Drafts; docs/00 sections C and H; the spec bullets.
- Checked against code and ledger: `claude_bully/metrics/ratings.py` (rate_escape replies after
  the reveal position), `claude_bully/metrics/events/__init__.py` (`PENDING_DETECTORS` is 9),
  the configs' `start_rung` and artifact lists, `scripts/judge_calibration.py` usage, the trigger
  cache path (`runs/_cache/triggers`), `git log` for the Task 7 commit names, task-7-report.md
  for 0.47 and 0.41, progress.md for Task 14's rows and the ids in New-1, the reconciliation's C6,
  `cmp` of the README and FUTURE twins, and the non-ASCII, CR and real-name scans.
- Not done: the test suite (read-only checkout; the report's gate is four doc-touching test
  files, 134 passed) and any dispatch.
