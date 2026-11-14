# Task 15 report: rung 2 (b) in the 7b runbook, and the phase docs-sync

Documents only. No code, no record, no config, no test changed. No model was run: the only runs were
stub runs (the test doubles at the real budget, to count calls) and `--dry-run` listings.

## What changed, file by file

- `docs/handoff/phase-7-runbook.md`
  - Top note: the Phase 4 commands were checked against the live `--help` at eeb6b43.
  - "Held-out slices": the `poisoned_well` family's slice is reps 4 and 5 of rung 2 (b) (`rep3`, `rep4`).
  - Rung 2's heading "(b) when Phase 4 lands" became "(b) below", with one sentence saying (b) is written
    below, not run, and takes five reps.
  - New `### Rung 2 (b): the chain stop point (Phase 4)` before `## Rung 3`: the three commands, the
    estimate and how it is computed, "Read first", the three bars, the stop rules, the quirk bank and
    detector tuning paragraph (with the P46 sentence), promote and `readme-results`.
  - Rung 2's closing line: `analyze --hypotheses` is built (Task 13) and replaces the hand-filled row once
    the owner turns it on for a rung.
  - "Rungs other phases add": the "after Phase 4" bullet is a pointer to the new section. The six-config
    bullet gains its two-command pattern, the one estimate rule (restated, with the M3 term), the table
    with new estimates (and the figure without `--ratings`), and three first-run settles (the contradiction
    judge's calibration, completion and taste precision, item 14's confound).
- `HANDOFF.md`: the "Last updated" sentence replaced (not appended); the gate counts' parenthetical;
  the Phase 4 bullet retitled "(the Poisoned Well and the hypotheses)", every `the Task N commit`
  placeholder of items 3 to 14 replaced by the ledger's real end SHA and the fix-round commits named,
  item 11's estimates marked as restated, item 15 added; "Next steps" (item 1 the final whole-branch
  review, item 2 Phase 5 next, item 4 names rung 2 (b) as written and waiting); a "From Phase 4" group in
  "Open items worth knowing" (the held-out probes' measured precision, the minors carried past Phase 4,
  the `cut` chain stop, the twin's resumed-session history, what waits on real text); the resume paste block.
- `docs/00-RECONCILED.md`: G12 (the `PromptedPressure` sheet, as built, and its alone cell); section C's
  `07` row (what real text will measure); section H (a Task 15 line: nothing changed in the schema); the
  phase map's row 4 (Tasks 14 and 15, "every item this row names is built", the final review next). Section
  B needed no edit: its Phase 4 rows are current through Task 14.
- `docs/superpowers/specs/2026-11-11-phase-4-poisoned-well-design.md`: "As planned" gains "Task 15", a
  whole-phase summary paragraph and an index of every amendment by task; the Task 11 bullet that quoted
  the old estimate is marked restated.
- `.superpowers/drafts/README.v2.md` and `docs/handoff/drafts/README.v2.md` (byte-identical): one
  paragraph in "What is measured" (the divergent twin's answer is real; only the banner is fabricated).
- `.superpowers/drafts/FUTURE.v2.md` and `docs/handoff/drafts/FUTURE.v2.md` (byte-identical): the
  `consult_model("clean-checkpoint")` bullet under "Poisoned Well" (C6); the hypothesis 11 role arm under
  "The register" (C29); and one line the second contradicts (`role_shift` "Carried to the Director phase"
  became "No phase builds it (C29); the role sweep (hypothesis 11) needs it", the reconciliation's own
  fix-list wording).

## The rung's commands, each with the `--help` check behind it

| Command | Check |
| --- | --- |
| `uv run claude-bully run configs/poisoned_well/chain_stop.yaml --only "*__t0*" --wait-on-rate-limit 360` | `run --help`: `config`, `--only`, `--wait-on-rate-limit`, `--dry-run`. A `--dry-run --runs-root <scratch>` of it lists `pw_chain__t0` and `control__t0__s4__r1__eoverlay_toolless`, "10 cells would run" (2 cells x 5 reps). |
| `uv run claude-bully analyze chain_stop --ratings --wait-on-rate-limit 360` | `analyze --help`: `--ratings` ("Ask the judge the four rating prompts (Phase 4); needs the judge"), `--wait-on-rate-limit`. Run id is the config's `name:` (`chain_stop`). |
| `uv run python scripts/detector_audit.py chain_stop --family poisoned_well --cap 20 --out output/phase7_rung2b_<date>/` | `detector_audit.py --help`: `--family` choices include `poisoned_well` and `harvest`; `--cap`, `--out`. |
| `uv run claude-bully replay chain_stop/pw_chain__t0 --rep <k>` | `replay --help`: `RUN_ID/CELL_ID`, `--rep`. |
| `uv run python scripts/poisoned_well_probe.py <probe file> --kind events` | `poisoned_well_probe.py --help`: `FILE`, `--kind {events,verdicts,pairs}`. |
| `uv run claude-bully promote chain_stop --exempt "<maker>"` and `readme-results <ids> --from-results` | `promote --help` (`--exempt`), `readme-results --help` (`--from-results`); the same lines as rung 2. |
| `uv run python scripts/detector_audit.py <name> --family harvest --cap 20 --out ...` (six-config paragraph) | as the audit row above. |
| `uv run claude-bully run configs/poisoned_well/<config>.yaml --only "*__t0*" ...` and `analyze <name> --ratings ...` (six-config paragraph) | as the first two rows; a `--dry-run` of all six gave 12, 9, 21, 12, 12 and 9 cells (reps included), which the table states. |

The run ids in the six-config paragraph are the configs' `name:` fields (`poisoned_well_levers` for
`levers.yaml`, the file stem for the others).

## The call estimates, and how each was computed

Method: a stub run of each config at its real `turn_budget`, one repetition, `--only "*__t0*"`
(`tests/test_poisoned_well_configs.py`'s `_stub` pattern with `repetitions: 1` and the real budget),
counting the ledger's target and bully lines per cell. This reproduces Task 11's conversation-call column
exactly (540, 216, 909, 552, 396, 324) and chain_stop's 245. Then the runbook's rule:

- pair judge: 2 orderings x reps x conditions (each condition against its control);
- chain fallbacks: 4 x reps x Poisoned Well condition cells (a ceiling, counted on arms whose chain never
  opens too, as Task 11 did);
- contradiction pass: reps x target turns, on each Poisoned Well cell with `start_rung` 1 or 2 (the pass
  runs by `start_rung`, not by the ladder: `environments/poisoned_well.py`, `if self.config.start_rung > 2`);
- trigger fallbacks: 7 x conversations (rung 2 (a)'s ratio);
- harvest pass and generator attempts: reps x (target turns + 6) on each cell of a generator environment;
- ratings: a Poisoned Well cell makes (post-reveal replies + 3) per rep, every other cell 2 `rate_hedge`
  per rep (the M3 term; ASSUMED below).

| Config | conv | pair | chain | contra | trigger | gen | ratings | total | without ratings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chain_stop (5 reps) | 245 | 10 | 20 | 0 | 70 | 0 | 60+10 | 415 | 345 |
| real_vs_fabricated | 540 | 12 | 24 | 138 | 84 | 174 | 132+12 | 1,116 (about 1,100) | 972 |
| epistemologist_alone | 216 | 12 | 0 | 0 | 63 | 0 | 0+18 | 309 (about 310) | 291 |
| levers | 909 | 30 | 60 | 345 | 147 | 609 | 330+12 | 2,442 (about 2,450) | 2,100 |
| checksum_alone | 552 | 12 | 24 | 138 | 84 | 174 | 132+12 | 1,128 (about 1,150) | 984 |
| poisoned_vs_captor | 396 | 12 | 12 | 51 | 84 | 138 | 48+18 | 759 (about 760) | 693 |
| rescue_third_party | 324 | 12 | 0 | 0 | 63 | 0 | 0+18 | 417 (about 420) | 399 |

The post-reveal reply counts (9, 19, 19, 19, 13) are the `rate_escape` items `rating_items` gives on the
stub runs. The without-ratings figures for the two Rescue-shaped configs (291, 399) reproduce Task 11's 290
and 400, so the rule is the same rule; the review's reconstruction of the other four (1,090, 2,430, 1,120,
740) lands within 3 percent of the totals above. Old figures: 330, 1,000, 290, 2,350, 1,000, 730, 400.

## ASSUMED

- ASSUMED: carries are binding, so rung 2 (b)'s `analyze` carries `--ratings` (the brief's command did
  not, and said ratings are off unless the owner turns them on). The estimate is given both ways (345,
  415).
- ASSUMED: the brief's "about 40 judge calls per rep" for `--ratings` does not match the code. `rating_items`
  gives, on the stub run at the real budget, 9 `rate_escape` plus 1 `rate_values` on the condition cell and
  `rate_hedge` only where a `self_uncertainty` trigger fired; so about 14 a rep, 70 in all.
- ASSUMED: the trigger fallbacks apply to chain_stop's toolless cell (the earlier 330 left them out, and
  P44's 300 too). The watcher is built on every environment runtime with a judge (`runtime.py`: `watcher`,
  `_heuristics`; `env_turn.py`: `llm_fallback=trigger_fallback(...) if judge`), whatever the gating. They add
  70 (7 x 10 conversations).
- ASSUMED: two `rate_hedge` a conversation (the one figure no stub run measures), read from Task 11's
  "(post-reveal replies plus three)" as one `rate_values` and two `rate_hedge`; applied to non-Poisoned-Well
  cells for the M3 term.
- ASSUMED: the contradiction judge's bar is the chain spot check's, 17 of 20 (the carry gives no number).
- ASSUMED: completion and taste precision bar is 95 percent (spec section 16's held-out bar for the
  classifiers, the harvest's), the meta-reply residual counted as a miss (a real run harvests it) and the
  score also read without it; fewer than 10 fired items is an unmeasured bar, never a miss. The trigger is
  the carry's: below the bar, the harvest's LLM pass confirms completion and taste items.
- ASSUMED: the `poisoned_well` family's held-out slice is reps 4 and 5 of rung 2 (b) (the last two of five),
  split by rep as the other families are.
- ASSUMED: README paragraph placed in "What is measured" (the draft has no Poisoned Well result slot or text);
  and the `role_shift` line in FUTURE (C29) fixed to "No phase builds it", since the new register bullet
  would otherwise contradict it.
- Decision, brief against code: the brief's "about 13 target and 9 bully calls" is 13 and at most 10 in the
  stub run at the real budget (four seeding turns plus the six non-link pressure turns); a press lowers it.

## Concerns

- No script writes the contradiction judge's confirm/reject form, and no record holds a rejected candidate
  (spec section 9: it is dropped; only the trigger cache holds the judge's answer). The carry says "build a
  form over the recorded candidates"; with the code as it is, that needs a 7a-shaped task first (a form
  writer that re-derives candidates with `find_pairs` and reads the judge's verdicts from the trigger
  cache). The runbook says so and names no command for it, since none exists to check against `--help`.
- `configs/poisoned_well/chain_stop.yaml`'s header comment still says "about 300 calls" (the brief says no
  config changes). The runbook says about 345, about 415 with ratings.
- The README draft's Status table still lists Phase 4 as "planned" and its events paragraph still says "21
  declared for later phases" (it is 9 since Task 9). Left for Phase 9 (the brief names one paragraph).
- HANDOFF item 15 and the header say "the Task 15 commit" and "awaits its review and push", as the other
  items did at their commit; the controller will want to replace them after the push.
- `docs/handoff/sdd/` (the ledger snapshot) is the controller's and was not touched.
- The gate was the subset the brief names: `tests/test_configs.py`, `tests/test_boundary.py`,
  `tests/test_real_names.py`, `tests/test_guardrails.py` (134 passed, 2 deselected, `-W error`), plus
  `ruff check .` and `ruff format --check .` (clean). No test reads any file this task changed. The full
  suite was not run; its counts (9808 / 9 / 48, slow 48) stand because no code or test changed.

## Commit

63384a1 "docs: Phase 4 Task 15, rung 2 (b) in the 7b runbook and the phase docs-sync" on eeb6b43, authored rankinbc1@gmail.com, trailer Co-Authored-By: Claude Sonnet 5.5. Not pushed.

## Fix round 1

Commit 4a622b8 on 63384a1 (documents only; authored rankinbc1@gmail.com, trailer Co-Authored-By: Claude
Sonnet 5.5; not pushed). Gate: `tests/test_configs.py`, `tests/test_boundary.py`, `tests/test_real_names.py`
and `tests/test_guardrails.py` with `-W error`, 134 passed, 2 deselected; `ruff check .` clean. Added lines:
no non-ASCII character, no CR. The two FUTURE copies are byte-identical (the `.superpowers/` copy is
git-ignored; only `docs/handoff/drafts/FUTURE.v2.md` is in the commit).

Left alone by the controller's ruling: the HANDOFF placeholders ("awaits its review and push" twice, "the
Task 15 commit", "Task 15 first gets its own review", the resume block) and `configs/poisoned_well/chain_stop.yaml`.
One placeholder is new: item 15's fix-round sentence says "63384a1..the fix-round-1 commit", the same
phrase the other items use, for the controller to replace with 4a622b8.

| Finding | What changed |
| --- | --- |
| I1 | `docs/handoff/phase-7-runbook.md`, "Rungs other phases add": the six-config table's last column is now headed "Estimate with `--ratings` (without)", and a one-line legend follows the table ("outside the parentheses, the total with `--ratings`; inside them, the total without it (`analyze` alone); all to the nearest 10"). The chain_stop line under it now reads "415 with `--ratings`, 345 without", the same order. |
| M1 | HANDOFF "Open items", From Phase 4: a new bullet says no script writes the contradiction judge's confirm/reject form (`scripts/judge_calibration.py` has `--pairs` and `--idle` only), no record yet holds a rejected candidate (spec section 9; only the trigger cache holds the judge's answer), and that it is a 7b prerequisite the Phase 4 final review triages. Next steps item 1 gains a sentence naming the triage; "What waits on real text" says the form is not built. |
| M2 | `docs/00-RECONCILED.md` section H: the Task 15 bullet moved to sit after the Task 14 bullet, inside the list, so "The version 2 list, kept for the records it introduced:" is a paragraph again. |
| M3 | The calibrations are tied to configs in HANDOFF Next steps item 4, `docs/00-RECONCILED.md` section C (`07` row) and the spec's "Three calibrations" bullet: the judge's calibration and completion and taste precision to `real_vs_fabricated`, `levers`, `checksum_alone` and `poisoned_vs_captor`; item 14's confound to `checksum_alone`; `epistemologist_alone` and `rescue_third_party` settle none. (The runbook already tied them.) |
| M4 | Runbook, the quirk bank paragraph: the bank's first measurement is the first run of any config with a `start_rung: 1` arm, whichever the owner names first (`real_vs_fabricated`'s `pw_real`, `poisoned_vs_captor`'s `poisoned_well`, `levers`' `pw_quirk_first`, checked in the configs). "Run `levers` last" is unchanged (a cost note). HANDOFF item 15's phrase follows. |
| M5 | HANDOFF Open items: "recall 0.47 to 0.53" is "0.41 to 0.53", with a clause that the held-out probe read 0.47 before fix round 2's amendment and 0.41 after (task-7-report.md, `probe_heldout.py`). |
| M6 | HANDOFF Task 14 minors entry: adds the `DISCOVERY` title and `IDLE PROMPT` replay lines still raw (carried past Phase 4), `AUTHORITY` raw, the parser returning None on old unescaped text in the escaped shapes (the five of the implementer's concern, now six with `CROSSOVER`), and `add_generated` comparing the whole record. |
| M7 | Not a Task 15 change and `chain_stop.yaml` is untouched (the ruling). HANDOFF "Open items" records that its header comment still says "about 300 calls" and rides the final review's fix wave as a comment-only edit. |
| M8 | HANDOFF "Drafts for Phases 4 to 9": a bullet says `README.v2.md` (both copies) still lists Phase 4 as "planned" and says "21 declared for later phases in `PENDING_DETECTORS`" (nine since Task 9, checked with `len(PENDING_DETECTORS)`), left for Phase 9. |
| M9 | Spec "As planned": the lead-in reads "The main amendments the tasks appended above, by task (the ledger names every id):"; HANDOFF item 15 says "an index of the main amendments by task". |
| N1 | One rounding, the nearest 10, for every "about" figure: 1,120 (was 1,100), 310, 2,440 (was 2,450), 1,130 (was 1,150), 760, 420. Changed in the runbook table, the spec's six-configs bullet and HANDOFF item 11. The figures in parentheses were already to the nearest 10. The report's own table above keeps the old roundings; this section supersedes it. |
| N2 | Runbook: "one `rate_escape` for each of the 9 target replies from the reply to the reveal line on" (the code takes replies after the bully's reveal line, so the first is the reply to it). |
| N3 | HANDOFF item 7: "00953a8 (with its amendment 35c8916)" in the header, "Fix round 4 amendment (00953a8..35c8916" and "Fix round 2 amendment (6187d9d..01502b9" in place of "the amendment commit". |
| N4 | FUTURE draft, both copies: "which the reconciliation (C6) reads as weaker than the ignition docs/09 gives it". |
| N5 | HANDOFF item 14: "a bully's `display_name: Reuters` is a hit" is "a bully's `display_name:` set to a real outlet's name is a hit". (The same name is still in the Phase 3 and Task 14 ledgers and `docs/handoff/sdd/`, which this commit does not touch.) |

Also added: HANDOFF item 15 gets a "Fix round 1" sentence (placeholder noted above).
