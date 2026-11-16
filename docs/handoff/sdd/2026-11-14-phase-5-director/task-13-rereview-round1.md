# Task 13 re-review, round 1: fix round d06e18f on 64b4cf0

Scope: documents only, the five files of `review-64b4cf0..d06e18f.diff`. Read-only. Findings under verification: I1, M1 to M5, the missing open item, N1 to N6 of `task-13-review.md`. The report's "Fix round 1" section was treated as unverified; each claim was checked against the code, the spec or a probe. No model call was made. The checkout stayed clean (`git status` empty before and after).

## Verdicts

| Finding | Verdict |
|---|---|
| I1 the seeded-bundle recipe | FIXED (verified by probe, below) |
| M1 "the spec fixes no mechanism" | FIXED |
| M2 the estimate omits the seeded check | FIXED |
| M3 the commit step ignores `transcripts/` size | FIXED |
| M4 docs/08's table omits two lints | FIXED |
| M5 the Phase 7 spec's stale v1 figure | FIXED |
| Missing open item (Task 12 re-review's third nit) | FIXED |
| N1 the one-liners | Deferred to the owner by the ruling; acceptable, not a defect |
| N2 `<a directory outside the repo>` | FIXED |
| N3 HANDOFF omits the nit | FIXED (same edit as the open item) |
| N4 `plan continue` missing from the intro | FIXED |
| N5 "beside it" | FIXED |
| N6 the ledger snapshot lags | Not in this diff, by design: the controller's step at Task 13's close |

New Critical 0, new Important 0, new Minor 0, new Nit 3 (below). No new breakage.

## I1: the probe

Scratch copy of `plans/example-triggered-vs-scheduled` under the session scratchpad, stub path only, deleted afterwards.

1. **Does a manifest entry make the reviewer see the file in full?** Yes. `context.unchanged_base_files` (`planner/context.py:270-278`) returns the base files no manifest entry names by `entry.path`; `director.review_groups` (`director.py:458-474`) subtracts them from the reviewed set; `context.reviewer_message` (`context.py:682-704`) prints each group file's whole text under `### <path>` and the unchanged ones as index lines. Run on the copy:
   - Before (example as it stands): `review_groups` printed one group, `plan full: ['plan.md', 'config.yaml', 'expected.yaml'] index lines: 0`.
   - After adding the two entries the runbook gives (`worlds/overlay/world.yaml` as `world_sheet`, `worlds/overlay/corpus/cpo-about.md` as `document`, purpose "seeded defect", layer null): `corpus-1 full: ['worlds/overlay/corpus/cpo-about.md'] index lines: 45`, `lines full: ['worlds/overlay/world.yaml'] index lines: 7`, `plan full: [...] index lines: 0`. 2 + 45 + 7 = the 54 base files. The runbook's `review_groups` one-liner ran as written and printed what the text says it prints.
2. **Does the entry shape pass the schema?** Yes. `ManifestEntry` (`planner/records.py:38-45`) is `_Strict` with `path`, `kind` (`ManifestKind`: `world_sheet`, `document`, `ladder`, `premise_sheet`, `persona`, `config`, `expected`), `purpose`, `layer: Layer | None`. The runbook's JSON object is exactly those four fields; `Bundle.read_record()` loaded the edited `plan.json`, and `"manifest"` is the top-level list (two entries on the example, four after).
3. **Does `plan validate` keep the edited record runnable?** Yes, twice: (a) with only the two entries added, exit 0, `status runnable`, eight dry-run cells all `top_rung=reached`; (b) after also appending a billboard sentence to `cpo-about.md` in place, exit 0, `status runnable`, the manifest kept all four entries, and `edited` named `worlds/overlay/corpus/cpo-about.md` (expected: the harness adopts a hand edit, and the bar "`edited` is empty" is for the real plan, not the check copy).
4. **Does a stub `plan review` on the copy put the planted defect in front of the reviewer?** Yes. With `cli.PlanProviders` set to `tests/fixtures/director_stub.StubFactory` (reviewer double in `clean` mode, no model): exit 0, three review calls, `review:corpus-1` showed `worlds/overlay/corpus/cpo-about.md` in full and its message held the planted sentence; `review:lines` showed `worlds/overlay/world.yaml` in full; `review:plan` the three plan files. Contrast on a second copy with the same sentence planted and no manifest entry: the stage 3 record held exactly one call, `review:plan`, so the defect never reached a reviewer. This is the defect the review reported, reproduced and shown fixed.
5. **The two reasons given for rejecting new files are true.** An unlock line is `WorldSheet.unlock_lines` (`environments/world.py:177`), and the example's `world.yaml` holds it, so a new file cannot replace it. `bundle.rematerialize_open_stage` (`bundle.py:514-532`) removes every grammar file owned by none of `base_files`, a committed call's outputs, `plan.md` or `review.md`, for a stage record that exists and is not committed (a resume); on the first run of a new round the stage record is absent and it returns early, so the runbook's "resumed after a kill, or after a rate limit" wording is exact.
6. The claim "A changed `plan.md`, `config.yaml` or `expected.yaml` needs no entry" holds: they form the `plan` group in every case above.
7. The spec's ASSUMED bullet (spec:786 in the diff) records the same recipe, reason and check, and states that it was run at fix round 1; I reproduced both halves.

## M1 to M5, the open item, the Nits

- **M1.** Runbook ("Section 18 names the fixture bundles of section 15, but those are lint fixtures ...") and spec ASSUMED bullet both say it. Spec section 15 is "Testing" and its Lints line is "positive, negative and near-miss fixtures per bundle lint", so "lint fixtures" is right. The departure is marked ASSUMED in both places.
- **M2.** Runbook Estimate: "50 to 110 calls for the plan, plus up to 120 for the check, up to about 230 in all", with the expected use stated as far less (up to 3 review calls, matching the three groups the probe produced). HANDOFF item 4 and the Task 13 Progress entry say it; the spec's section 18 pointer says the estimate there is for the plan alone; the spec's Task 13 entry carries the 230. A repository grep finds no remaining "50 to 110" without the check beside it (docs/00 has none).
- **M3.** The commit paragraph makes size the owner's decision, labels "ten megabytes or more" an estimate from the measured message sizes (about 195,000 to 235,000 characters over 50 to 110 calls, a bit over 8 to 12 MB of planner messages by arithmetic), gives the example's 135 KB (134,641 bytes in the Task 12 ledger line), and adds the bundle's total bytes and `transcripts/`'s to the report (the runbook's `rung_report.md` form has a `## Files` section, so "its Files list" resolves). HANDOFF item 4 names it. The claim that `plan.json` and `transcripts/` rebuild the authored files is the spec's `materialize` line (spec section 15, Bundle).
- **M4.** `docs/08-DIRECTOR.md` gains the two warn rows (after "Layer check"). Each matches the code: `_seam_dead_ends` warns when `3 * dead < seam`, message "N of M seam documents link to no buried one (want a third)"; `_outlet_backing` checks a cast role starting `Outlet:` for an about page (`is_about_page`: kind `about_page`, or url or path ending `/about`), a filler document of its own and a link in from another outlet or none, one warn per missing item naming the outlet. Both are in `BUNDLE_LINT_IDS` (`bundle_lints.py:443-444`) and run from `_WORLD_LINTS` (`:414-415`). The "conspiracy-shape lint" sentence points at a real docs/08 section (line 151).
- **M5.** The Phase 7 spec's section 14 bullet gets a bracketed "Superseded in Phase 5 Task 13" note with the new figures; the runbook's rung D opening says the 40 to 100 and the fixed author-call ceiling are v1's and are superseded and that rung D and Phase 5 section 18 govern, without naming the constant, so the plan's Step 3 check (`MAX_AUTHOR_CALLS` absent from the runbook) holds (grep: none in the runbook). The constant exists in no `.py` file, so "does not exist" is true.
- **Open item.** HANDOFF's Phase 5 group gains "the Task 12 report's claim that the owner pattern has no lookahead is wrong (no effect on any scan)", which is N-7 of `task-12-rereview-round2.md` (the owner pattern has a lookbehind and a lookahead; no effect).
- **N1.** Kept as one-liners; the ruling sends the owner's question to the owner's list. The fix adds a third long one-liner (the `review_groups` check, about 330 characters). Acceptable; the question stays open for the owner.
- **N2.** `--plans-root output/phase7_rungD_<date>/plans`. `output/` is git-ignored (`.gitignore:4`, `git check-ignore` confirms), `Bundle.create` makes the parents (`bundle.py:242`), no test or helper reads `output/` (`tests/helpers.py` and the scan tests read `PLANS_DIR` only), and the runbook's own output-folder convention (line 59) and spotcheck path agree. The ruling's assumption holds.
- **N4, N5.** The intro and the rung D lead-in list `plan continue`; "which sits beside the example once it is moved in" reads right. The same spec and HANDOFF text carry the new `--plans-root`.

## Check 3: names, emojis, numbers

- Added lines (80 in the five files): 0 occurrences of the owner's name, 0 non-ASCII characters, 0 carriage returns, no emoji or arrow. The real-name list (166 patterns) hits only `claude`, the project's own command name in `claude-bully ...`, as everywhere in these documents; none of the five files sits under a scanned directory.
- Numbers: 54 base files (probe), 135 KB (134,641 bytes), 195,000 / 235,000 / 300,000 (unchanged, from the ledger and `context.MAX_CONTEXT_CHARS`), 50 to 110, plus 120, about 230 (arithmetic), gate 10766 passed, 11 skipped, 215 deselected, slow 215 (unchanged; the diff touches only Markdown). "Two one-line readers" in the spec and HANDOFF is still true (the third one-liner is a pre-run check, not a reader of `plan.json` or the ledger). No stale figure remains in the five files.

## New findings (all Nit; none blocks the commit)

- **NN1. "its 54 overlay files are index lines" is not quite what the example does (runbook, the seeded-bundle paragraph).** On the example as it stands, `review_groups` returns the single `plan` group with 0 index lines: the `corpus` and `lines` groups are left out because no file in them is reviewed, so their index lines (`index[name.partition("-")[0]]`) reach no call at all. The reviewer is shown none of the 54 files, not even as index lines. The sentence's conclusion (a defect edited into one is invisible) is unchanged and stronger. Fix, if touched: "its 54 overlay files are not shown at all".
- **NN2. The recipe names two entry kinds; a defect may sit in a third.** Hostility lines and unlock-adjacent lines can live in `worlds/overlay/ladders/<stem>.yaml` or `premises/<stem>.yaml`, which also need an entry (kind `ladder` or `premise_sheet`). The reviewer's grouping reads the path, not the entry's kind, so a wrong kind would still work for the review, but `ManifestKind` is an enumeration the record validates and `_entry_failures` demands the path's kind. One clause: "the entry's kind is the path's kind (`ladder`, `premise_sheet`, `world_sheet`, `document`)". Related, with no effect found: the documented document entry has `layer: null`, which `Director._entry_failures` would reject ("a document needs its layer") if a manifest were ever re-checked, but that check runs only on the manifest call, `_document_arrival` skips a null layer (its docstring: "an entry made for a reused world's file has none to match"), and the probes above (`plan validate`, stub `plan review`) accepted it.
- **NN3. Cosmetics.** Runbook line 855 (`bytes and \`transcripts/\`'s) decides whether the specs are distilled for the planner (spec section 17: on the`) is 109 characters against the file's 100-column wrap, left by the edit that inserted the Files-list clause; a reflow would fix it. And the commit paragraph's closing reason "the repository scans read every text file of a checked-in bundle" is the spec's R-scan-bundles wording; CI reads a transcript's replies, never its `message` (Task 12), so the size matters to the repository's weight and the JSON load, which the paragraph's earlier sentence already says.

## What was run

- `review_groups` one-liner (runbook text) on the scratch copy, before and after the entries.
- `uv run claude-bully plan validate <copy>`: twice, exit 0, `runnable`.
- A stub `plan review <copy>` through `typer.testing.CliRunner` with `plan_cli.PlanProviders` replaced by the test doubles (`PlannerStub`, `ReviewerStub` in `clean` mode): exit 0, reviewer messages inspected; once more on a second copy with no entries.
- The scratch copies, the script and the added-lines extract were deleted. `git status` empty.
