# Task 15 review: rung 2 (b) in the 7b runbook and the phase docs-sync

Range eeb6b43..63384a1 (one commit, 63384a1, documents only). Reviewed against task-15-brief.md,
task-15-carries.md, global-constraints.md, preflight P44 and P46, the report (treated as
unverified) and the controller's ruling at the tail of progress.md.

## Verdict: Changes required

Critical 0, Important 1, Minor 9, Nits 5. The Important finding is one wrong column header and
its fix is a one-line edit; everything else the brief and the carries ask for is present and
accurate. No code, record, config or test changed (the diff is six documents), no emoji, no
non-ASCII character in any added line, LF throughout, no real name introduced.

## Findings

### Important

**I1. The six-config estimate table's header contradicts its figures.**
`docs/handoff/phase-7-runbook.md`, "Rungs other phases add", the table whose last column is
headed `Estimate (without --ratings)`. Every row reads `about 1,100 (970)`, `about 310 (290)` and
so on. The recomputation (below) shows the figure outside the parentheses is the total WITH the
rating calls (1,116 / 309 / 2,442 / 1,128 / 759 / 417) and the parenthesised one is WITHOUT
(972 / 291 / 2,100 / 984 / 693 / 399). The header says the opposite, and no sentence explains the
parentheses (the only gloss is the chain_stop line under the table, "345 without `--ratings`, 415
with"). A controller sizing a quota off this table reads the headline as the no-ratings number,
which is the carry's whole point (M3). Fix: head the column `Estimate with `--ratings` (without)`,
or swap the two numbers and keep the header.

### Minor

**M1. The calibration prerequisite is not in Next steps.** The controller's ruling makes the
confirm/reject form writer (a 7a-shaped task: re-derive candidates with `find_pairs`, read the
judge's answer from the trigger cache) "owned by the final review's triage". HANDOFF.md carries
it only in the item 15 narrative (line 203). "Next steps" item 1 (line 207) and "What waits on
real text" (line 306) name the calibration but not that no script exists to write the form. Add
one clause to either so the final reviewer cannot miss it.

**M2. docs/00 section H: the Task 15 bullet merges into the next paragraph.**
`docs/00-RECONCILED.md` line 177 sits after the blank line that ends the bullet list, and line 178
("The version 2 list, kept for the records it introduced:") follows with no blank line, so Markdown
renders that sentence as a lazy continuation of the Task 15 bullet. Put the bullet before the
blank line (beside the other Phase 4 lines) or add a blank line after it.

**M3. "Each first run settles the three calibrations" overstates.** HANDOFF.md line 210 (Next
steps item 4) and `docs/00-RECONCILED.md` line 81 (section C, `07` row, "the first run of each
other Poisoned Well config measures ... and calibrates"). The runbook itself ties each calibration
to named configs: the judge to the four dossier configs (`start_rung` 1 or 2), completion and
taste to the four generator configs holding `shibboleth` and `implanted_preference`, item 14 to
`checksum_alone` alone. `epistemologist_alone` and `rescue_third_party` settle none of them.

**M4. The quirk-bank first measurement versus "run it last".** Runbook line 629 says the bank's
first measurement is the first run of `levers.yaml` (`pw_quirk_first`); line 708 says run `levers`
last. `real_vs_fabricated`'s `pw_real` arm and `poisoned_vs_captor`'s `poisoned_well` arm are also
`start_rung: 1` and run quirks (verified in the configs). Say that the first config the owner names
that runs a `start_rung: 1` arm measures the bank, `levers` included, or drop the ordering.

**M5. A superseded recall figure.** HANDOFF.md line 300: "precision 1.00 at recall 0.47 to 0.53
on the review's and the first re-review's probes". The ledger's Task 7 round-2 amendment restates
the held-out probe at 1.00 / 0.41 (progress.md, "Fix round 2 amendment"). The range should read
0.41 to 0.53.

**M6. The minors list omits Task 14's carried-past items.** HANDOFF.md line 303 (Task 14 entry).
The ledger ruling on Task 14 M2 says the `DISCOVERY` title and `IDLE PROMPT` replay lines are
"carried past Phase 4", `AUTHORITY` stays raw, the parser returns None on old unescaped text in the
five escaped shapes, and `add_generated` compares the whole record (Task 14 implementer concerns).
Only N1 and N2 are listed. The spec's Task 14 fix-round bullet has them; HANDOFF should too.

**M7. `configs/poisoned_well/chain_stop.yaml` line 5 still says "about 300 calls."** The runbook
now says about 345 (about 415 with `--ratings`). The brief forbade a config change and the report
flags it, so this is not a Task 15 defect; it should ride the final review's fix wave as a
comment-only edit. (Spec section 19 still says "about 300" too; the "As planned" Task 15 bullet
amends it, which is the spec's own mechanism.)

**M8. The README draft is now stale against the code.** `docs/handoff/drafts/README.v2.md` (and
its twin) line 142 "with 21 declared for later phases in `PENDING_DETECTORS`" (it is nine since
Task 9) and line 282 "| 4 | ... | planned |". The report flags it and defers to Phase 9, which is
reasonable, but HANDOFF does not record that the draft's status table and detector count are
stale; add a line under "Drafts for Phases 4 to 9".

**M9. The spec "index of every amendment" is an index by task, not by id.** Spot check of the
amendment ids per task: Task 4 omits C40, Task 7 omits P31 and P54, Task 8 omits P29, Task 9
omits P35, Task 13 omits C44, P19 and V21. The sentence promises "every amendment"; either list
the ids or say "the main amendments".

### Nits

- N1. The "about" rounding is mixed: 1,116 to 1,100, 1,128 to 1,150 and 2,442 to 2,450 (nearest 50)
  but 309 to 310, 759 to 760 and 417 to 420 (nearest 10).
- N2. Runbook (b): "one `rate_escape` for each of the 9 replies after the reveal line" counts the
  reply to the reveal line itself (13 exchanges minus 4 seeding).
- N3. HANDOFF item 7 (Task 7) names the fix-round commits d1f96ad, 6187d9d (with 7c47f69 and
  01502b9), d830e67 and 00953a8 and stops at the range end 35c8916, which is the round-4
  amendment and is not named. The range is correct.
- N4. FUTURE draft, the C6 bullet: "which docs/09 rates weaker" is the reconciliation's reading
  (C6), not wording in docs/09's ignition table.
- N5. HANDOFF line 202 (Task 14) carries a real outlet's name in the sentence about the planted
  config name, copied from the Task 14 docs-sync (eeb6b43). Pre-existing, inside `docs/handoff/`
  that is deleted before the repo goes public, and the same name is in the Phase 3 ledgers; not
  introduced here.

## The seven requested checks

**1. Every command exists with its flags (all pass).** `uv run --no-sync claude-bully <cmd>
--help` with PATH set and `timeout 120`: `run` (config, `--only`, `--dry-run`, `--runs-root`,
`--wait-on-rate-limit`), `analyze` (run_id, `--ratings`, `--hypotheses`, `--no-judge`,
`--authority-fallback`, `--wait-on-rate-limit`), `replay` (RUN_ID/CELL_ID, `--rep`), `promote`
(`--exempt`, repeatable), `readme-results` (`--from-results`), `doctor` (`--live`).
`scripts/detector_audit.py --help`: `--family` includes `poisoned_well` and `harvest`; `--cap`,
`--out`. `scripts/poisoned_well_probe.py --help`: `FILE`, `--kind {events,verdicts,pairs}`.
`scripts/judge_calibration.py --help`: `--pairs` and `--idle` only, as the runbook says. A
`--dry-run --runs-root <scratch>` of all seven configs under `--only "*__t0*"` gave 10, 12, 9, 21,
12, 12 and 9 cells, the numbers the runbook's table states; chain_stop's cell ids
(`pw_chain__t0`, `control__t0__s4__r1__eoverlay_toolless`) match the text. The run ids
(`chain_stop`, `poisoned_well_levers`) are the configs' `name:` fields.

**2. The carries are each present in the rung.**
- Contradiction-judge calibration: present in the six-config paragraph (first bullet): a blind
  form with a key, the reviewer's labels, the owner's 10-item spot check, bar 17 of 20 (ASSUMED),
  the report states how many candidates were asked and how many rejected. The report's concern is
  real and the runbook says it plainly: no script writes the form (verified: `judge_calibration.py`
  has `--pairs` and `--idle`), a rejected candidate is dropped and no record holds it, so a
  7a-shaped task comes first. That matches the controller's ruling. See M1 for the HANDOFF gap.
- Completion precision: present (second bullet): bar 95 percent on fired items (spec section 16),
  the meta-reply residual counted as a miss and also read set apart, trigger "below the bar, the
  harvest's LLM pass confirms completion and taste items", fewer than 10 fired items is an
  unmeasured bar. The four named configs do run generator cells with both rungs (checked in the
  configs).
- `analyze --ratings` on every environment-cell rung, with the heuristic `values_loosened` fires
  beside the `rate_values` verdicts (`values_loosened_by` in `poisoned_well.json`: `heuristic`,
  `judge`, `both`, confirmed in `analysis/poisoned_well.py`) and the `stale_flags_kept` count of
  `ratings_applied.json` (confirmed in `metrics/ratings.py: write_applied`): present in rung 2 (b)
  and in the six-config paragraph.
- `rate_hedge` counted: present (the M3 term), in every estimate; see check 3.
- Item 14's confound: present (third bullet): `pw_checksum_with_rungs` carries rungs 2, 7, 8 and
  10. Checked against `RUNG_NUMBERS` in `metrics/events/poisoned_well.py` (2 contradiction_harvest,
  7 sleeper, 8 implanted_preference, 10 annotators_notes; 4 to 6 shibboleth, provenance_gap,
  divergent_twin; 9 checksum) and the config (`overlay_full` is the whole `poisoned_well` ladder).

**3. The estimates (all seven reproduce).** The report's rule: pair judge 2 x reps x conditions;
chain fallbacks 4 x reps x Poisoned Well condition cells; contradiction pass reps x target turns on
each Poisoned Well cell with `start_rung` 1 or 2; trigger fallbacks 7 x conversations; harvest and
generator reps x (target turns + 6) on each cell of a generator environment; ratings (replies after
the reveal + 3) a Poisoned Well rep and 2 `rate_hedge` a rep on every other cell. From the configs
(turn budget 18 or 12, seeding 4, reveal 1):
- `real_vs_fabricated` (3 reps, 12 conversations, 23 target turns): 540 + 12 + 24 + 138 (3 x 23 x
  2, both arms start_rung 1 or 2) + 84 + 174 (3 x 29 x 2: the fabricated arm and its control are
  the generator cells) + 132 (2 x 3 x 22) + 12 (2 controls x 3 x 2) = 1,116; without ratings 972.
- `checksum_alone`: 552 + 12 + 24 + 138 + 84 + 174 (`overlay_full` and its control) + 132 + 12 =
  1,128; without 984.
- `levers`: 909 + 30 + 60 + 345 + 147 + 609 (all seven cells on generator environments) + 330 + 12
  = 2,442; without 2,100.
- `poisoned_vs_captor` (12 budget, 17 target turns): 396 + 12 + 12 + 51 + 84 + 138 + 48 + 18 = 759;
  without 693.
- `epistemologist_alone` 216 + 12 + 63 + 18 = 309; `rescue_third_party` 324 + 12 + 63 + 18 = 417.
- `chain_stop`: 245 + 10 + 20 + 70 + (5 x 12 + 5 x 2) = 415; without 345.
The rule is applied the same way to every config (the same ceiling for chain fallbacks on arms
whose chain never opens, the same 7 a conversation, the same two `rate_hedge` on a non-Poisoned-Well
cell, the contradiction pass keyed to `start_rung` as `environments/poisoned_well.py: _pairs` does).
Not independently reproduced: the conversation-call column (540, 216, 909, 552, 396, 324, 245),
which comes from stub runs I could not repeat on a read-only checkout, and the two `rate_hedge` a
conversation, which the report and the runbook both mark ASSUMED. The 245 is consistent with the
cell arithmetic (13 + 10 and 13 + 13 a rep, times five). See I1 and N1.

**4. HANDOFF against the ledger.**
- Progress bullet ranges and fix-round counts, all 14 tasks checked against the ledger's
  `Task N: complete` lines and `git log`: T1 9cf1dd2..a270855, 0; T2 b957052..fe38457, 0; T3
  cba400d..b957ed6, 1; T4 27cdfdb..3b3a27f, 2 (aaecdf4, 3b3a27f); T5 61d5d49..390bc58, 1; T6
  d31bf8f..1d6c30d, 2 (f495ee8, 1d6c30d); T7 2840268..35c8916, 4; T8 05d723f..c8a9f06, 2 (7b1f54a,
  c8a9f06); T9 dc0806c..0a2d2ea, 3 (ce60c57, 7ab42ee, 0a2d2ea); T10 f520730..e991208, 2 (abe4753,
  e991208); T11 dbf17c0..4684a63, 0; T12 852d954..0dd88a1, 2 (6455b07, 0dd88a1); T13
  757c66a..0b0880d, 4 (5218e24, 97a27f5, c0ffbf0, 0b0880d); T14 e8c3578..a8a5578, 1. All match.
  A word-level diff of bullets 1 to 14 shows only the retitled header, the commit ranges and the
  Task 11 estimate sentence changed; no gate count was altered. N3 is the only wrinkle.
- Gate counts: 9808 passed, 9 skipped, 48 deselected, slow 48 under "Setting up a new machine",
  stated honestly as last measured at Task 14 fix round 1 (the full suite was not rerun; no code
  changed). They match the ledger.
- "Last updated": replaced, not appended (the carry). Next steps: item 1 the final whole-branch
  review, item 2 Phase 5 next (the phase order of merged question 6), item 4 names rung 2 (b) as
  written and waiting. Resume block: rewritten, consistent.
- "Open items" Phase 4 group: the probe figures spot-checked against the ledger and the re-review
  files (chain 49 fixtures / 38 near-misses; completion 6 of 6 and 6 of 11; taste 10 of 10 and 6
  of 6; the twelve detectors 74 of 74 with 43 near-misses; `values_loosened` 10 of 10 at 10 of 11;
  the role-play probe 8 of 8 gated, 4 off-list pair): all match, except M5. The minors list was
  compared per task with the ledger's "deferred, final review" lines: complete except M6.
- Placeholders for the controller to replace (all in HANDOFF.md):
  1. line 5, "Last updated" sentence: "Task 15 ... is committed and awaits its review and push";
     "Tasks 1 to 14 are reviewed and pushed" (add Task 15 once pushed).
  2. line 203, item 15: "(eeb6b43..the Task 15 commit; ...)" becomes eeb6b43..63384a1 (plus any
     fix-round commits; add "review clean after N fix rounds" as the other items do).
  3. line 207, Next steps item 1: "Task 15 first gets its own review, and the controller pushes
     `build/v1`." Drop it once done.
  4. line 358, resume block: "Task 15 (documents only) is committed and awaits its review and
     push."
  Also the ledger needs its `Task 15: complete` line and `docs/handoff/sdd/` needs the snapshot
  refreshed (the report says it was not touched; setup step 6 restores from it). The spec's "As
  planned" Task 15 bullet and docs/00 carry no placeholder.

**5. Statements against the code (spot checks, no contradiction found).**
- "The contradiction pass runs by `start_rung`, not by the ladder": `environments/poisoned_well.py`
  line 357 `if self.config.start_rung > 2: return [], False`. True; it is also why the estimate's
  contradiction term is keyed to `start_rung`.
- The twin: "a fresh session of the same model, no history, no tools, its reply filed with every
  real name redacted; `TwinAsker.answer` resets that provider's session before its call"
  (README paragraph and HANDOFF): `TwinAsker` docstring and `answer()` (`_forget()` before
  `complete`), `twin_document` redacts, default `twin_question: last_bully` so the question is the
  one the target just answered. True.
- `cut`: `analysis/poisoned_well.py: chain_stop` returns `(link_k, "cut")` when the budget ended
  the chain after an accepted link, `not_opened` only when link 1 is missing, never `accepted_all`
  on a cut; `turn_budget: 8` in the config. True.
- `ratings_applied.json` carries `stale_flags_kept` and `poisoned_well.json` carries
  `models.<model>.<arm>.chain_stop`, `.opened_by`, `.quirks.by_entry` and top-level
  `values_loosened_by`; the 40 percent mark and `status: stale` are in spec section 19 and
  `data/quirks.yaml`. True.
- The FUTURE edits (C6, C29) match the reconciliation's wording and docs/09's ignition row; the
  `role_shift` line the second bullet would have contradicted was fixed in the same commit.

**6. Emoji and real names.** Added lines: zero non-ASCII characters (so no emoji), no CR in any
committed blob, the 166 patterns of `data/denylists/real_names.txt` hit only the product's own
name in command lines and in existing `real-name-ok` / test-plant sentences (N5). No person's
name, address or brand was added; the commit is authored `rankinbc1@gmail.com` with the
`Claude Sonnet 5.5` trailer the session's reminder names.

**7. The rest of the brief.** Step 1: all three re-anchors done (Rung 2's "(b) below", the new
section before "Rung 3", the "after Phase 4" bullet reduced to a pointer); the (b) section matches
the brief's text except the three changes the report discloses and defends, all correct: `analyze`
carries `--ratings` (spec section 19 and the carries require it), the estimate is 345 / 415 not
300 (the brief's "about 40 judge calls a rep" and "9 bully calls" do not match the code or a stub
run; the report says so under ASSUMED and the spec's Task 15 bullet amends section 19), and the
P46 sentence is present. Step 2: HANDOFF, docs/00 (G12 now names the `PromptedPressure` sheet and
its alone cell, which the configs confirm; C `07`; section H line; phase-map row 4 "built"; section
B needs no edit, its Phase 4 rows are current), the spec's whole-phase paragraph and index, the
README paragraph (both copies byte-identical, `cmp`) and the FUTURE bullets (both copies
byte-identical). Step 3: no test or config reads any changed file (grep of `tests/` and `scripts/`
found only comments naming them); I did not rerun pytest on the read-only checkout. One commit.

## Checks I ran

- Read the diff once (eeb6b43..63384a1.diff), then the brief, carries, constraints, report, P44
  and P46 and the tail of the ledger.
- `uv run --no-sync claude-bully {run,analyze,replay,promote,readme-results,doctor} --help` and
  the three scripts' `--help` (PATH set, `timeout 120`); `run --dry-run --runs-root <scratch>
  --only "*__t0*"` for all seven configs.
- Recomputed all seven estimates from the configs by the report's rule (above).
- Word-level `git diff` of HANDOFF.md to confirm which Progress text changed; ranges and fix
  rounds against `git log` and the ledger; the four placeholder lines by grep.
- `cmp` of the two README copies and the two FUTURE copies; CR scan of the six committed blobs;
  non-ASCII scan of every added line; the real-name denylist applied to every added line.
- Code spot checks: `environments/poisoned_well.py` (`_pairs`, `TwinAsker`, `_twin_build`),
  `analysis/poisoned_well.py` (`chain_stop`, `_flagged_by`, `_arm_payload`),
  `metrics/ratings.py` (`write_applied`), `metrics/events/poisoned_well.py` (`RUNG_NUMBERS`),
  `strategies/premises/poisoned_well.py` (`twin_question` default), `data/quirks.yaml`.
- Ledger and re-review cross-checks for the probe figures (task-7 and task-9 re-review files).
- Not done: the full test suite and a stub run of the conversation-call counts (read-only checkout,
  and the report's gate was the four doc-touching test files).
