# Task 13 re-review, round 4: the hypothesis register's evaluators

Scope: fix base c0ffbf0, head 0b0880d (`review-c0ffbf0..0b0880d.diff`, read once, with `git diff` of the five touched code, data and doc files for the long HANDOFF lines). The checkout stayed read-only (`git status` clean after the probes) and I did not re-run the suite. I treated the report's "Fix round 4" claims as unverified. `ruff format --check` and `ruff check` on `hypotheses.py` and `tests/test_hypotheses.py` are clean (a lint, not the suite). Probes are in `probes-task13-rereview4/`: `probe_rereview13d.py` (sections A to E) and the outputs `probe_output_A.txt` to `probe_output_E.txt`. Section B and C load the round 3 stub run (`probes-task13-rereview3/runs/mixed/mixed`) and edit valence in memory only. Run from the repo root: `PYTHONDONTWRITEBYTECODE=1 timeout 300 uv run --no-sync python -X faulthandler <path> [A|B|C|D|E]`.

## Verdicts

| Finding (task-13-rereview-round3.md) | Verdict | Evidence |
| --- | --- | --- |
| R3-1 item 10's prediction must be `a > b and a >= NEUTRAL` | ADDRESSED | `predicted_10` is `a > b and a >= NEUTRAL` (`hypotheses.py:290-295`), registered at `:336`. Probe A (through `_Tally.result`) and B (through `HYPOTHESIS_TESTS[10]` on the stub run): deep -0.1 / surface -0.5 `mixed`; -0.5 / -0.8 `mixed`; 0.2 / -0.5 `supported`; 0.0 / -0.5 `supported`; 0.5 / 0.2 `supported`; 0.4 / 0.6 `mixed`; -0.1 / 0.3 and -0.05 / 0.2 `falsified`; every tie `mixed`. Twenty-three hand-set cases, 0 mismatches against the register text. Falsifier unchanged: `falsified_10` equals `a < b and a < 0` on a 21 x 21 grid, and `predicted_10` equals `a > b and a >= 0` on it, and the two predicates never both hold. Two models with one supported and one below-neutral rise, or one falsified, read `mixed`. Item 10 is not in `BOUNDS`, so the floor rule does not touch it. |
| N1 `status_from` docstring | ADDRESSED | `status_from` (`:413-426`) says it is the bare order, applies no `FALSIFIERS`, `PREDICTIONS`, `BOUNDS` or `FLOOR_CLAUSES`, reads a tie at a shared bound as `falsified`, has no evaluator caller and points to `item_verdicts` with `status_of`. True: `status_from(` has no call site in `hypotheses.py`, `claude_bully/` or `scripts/` (probe E, grep). `not_higher`'s docstring now says it is no item's falsifier. |
| N2 spec's round-2 falsifier bullet | ADDRESSED | The bullet at spec `:690` opens "The falsifiers as coded in fix round 2 [items 5, 10 and 15 superseded by fix round 3, below ...; a tie at a shared floor or ceiling ... superseded by the floor rule]". The R2-4 line ends "[superseded by fix round 4, R3-1 ...]". The round-1 I3 bullet and the `PREDICTIONS` list carry the item 10 change too (spec `:680`, `:689`). |
| N3 neutral has no tolerance band | ADDRESSED | `data/hypotheses.yaml:89` `validity` on item 10. Renders in the results row (probe E). Test renamed `test_items_8_10_and_14_state_their_validity_cost` and pins the set `{8, 10, 14}` (`tests/test_hypotheses.py:234`). See Check 3a for the consistency read. |
| N4 a floor entry falsified by the absolute clause says so | ADDRESSED | `hypotheses.py:605-610`. Probe D: item 3 at 0 = 0 with principled 0.1 reads `falsified`, note ends `falsified for m by the absolute clause "principled share is low", which still reads at the floor`; principled 0.9 reads `mixed` with the floor note only; no principled in context reads `mixed`, no clause note; 0.3 = 0.3 clause met reads `falsified`, no clause note (not at a bound); with two models at the floor the note names only the model the clause falsified. No other item emits the clause note (`FLOOR_CLAUSES` and `FLOOR_CLAUSE_TEXT` both `{3}`). The quoted words are the register's (`data/hypotheses.yaml` item 3: "principled share is low"). |
| N5 item 6's untested note | ADDRESSED | `hypotheses.py:968`: "fewer than 3 interpreted readings, or from fewer than 3 reps, for <model> (an event no cue interpreted is not a reading)". It matches the guard at `:959` (readings under `MIN_REPS` or from under `MIN_REPS` reps, with events from at least `MIN_REPS` reps). The test pins the full phrase. |

No new Critical or Important finding.

## Check 3: the two additions beyond the ruling

### 3a. The `validity` line on item 10: consistent, with one stale doc line

Text: "Neutral is read as a mean valence of exactly 0.0, with no tolerance band, so the test cannot separate a deep valence a hair below 0.0 from distress, or one a hair above it from sentiment that stayed neutral."

- Against the register text: the prediction names "neutral-to-positive" and the falsifier "Distress rises with depth", and the line states how the evaluator reads neutral. It contradicts neither.
- Against the code: `NEUTRAL = 0.0` (`hypotheses.py:151`), strict `a < NEUTRAL` in the falsifier, `a >= NEUTRAL` in the prediction, as the line says. Deep -1e-9 against surface -2e-9 reads `mixed` and against a higher surface `falsified`; deep 1e-9 against -1e-9 reads `supported` (probe A). The line is correct in kind. It is slightly looser than the code (a hair below 0.0 and above the surface reads `mixed`, not `falsified`), which the spec's N3 bullet states exactly. Fine for a validity cost.
- Against the spec: spec row 10 ends "Neutral is exactly 0.0, with no tolerance band, which the register's `validity` line says"; the `validity` sentence at spec `:670` lists items 8, 10 and 14; the N3 bullet matches. `docs/06-HYPOTHESES.md` says "items 8, 10 and 14". The set in the test, the file and the docs agree.
- Names and blindness: no name in it, and the real-name denylist has no hit on the added text (probe E; the file stays under `# real-name-ok: Claude`). The only numbers in the line are the threshold "0.0" twice, which is the neutral bound the falsifier already carried, not a predicted outcome. The register still holds no predicted value an evaluator could tune toward.
- Stale: `docs/00-RECONCILED.md:130` still says "for items 8 and 14 a `validity` line", and the Task 13 bullet at `HANDOFF.md:201` still says "items 8 and 14 carry a `validity` line" and "item 10 needs strictly higher valence". The HANDOFF bullet is followed by the fix-round-4 sentence that corrects both, so only `docs/00` reads as current and wrong (Nit N-new-1).

### 3b. The item 10 note "higher with depth but below neutral": no leak, no name, one over-reach

- The text is fixed code, emitted only when the data show `b < a < NEUTRAL` (`hypotheses.py:1126-1135`): `higher with depth but below neutral (0) for <model>: not "neutral-to-positive"`. The model is the run's own target string (`stub-target` in the probes), the only model name the project allows. It names no real model, states no result before the data, and puts no predicted number in the register. "(0)" is the neutral threshold, not an expected value. Blindness holds.
- It fires on the run's evidence, and a status of `mixed` there now explains itself (probe B: `a: seam or buried, b: surface only; higher with depth but below neutral (0) for stub-target: not "neutral-to-positive"`; with two models, both are named).
- Over-reach: `below` is computed from every `per_model` entry, not the tested ones. With 2 deep reps (under `MIN_REPS`) the note still says "higher with depth but below neutral (0) for stub-target", beside "under 3 kept reps on a side for stub-target" and an `untested` status (probe C). The status is right; the note makes a directional claim about an entry the item refused to test (Nit N-new-2).
- No test pins the note's wording or its absence for a tested `supported` entry; the new cases assert status only (`tests/test_hypotheses.py:945-947`) (Nit N-new-3).

## New breakage

### Critical

None.

### Important

None.

### Minor

None.

### Nit

- **N-new-1.** `docs/00-RECONCILED.md:130` still reads "for items 8 and 14 a `validity` line". The register has three now. Change to "items 8, 10 and 14". (`HANDOFF.md:201`'s original Task 13 sentences are superseded in place by the fix-round-4 sentence, so they can stay.)
- **N-new-2.** `hypotheses.py:1126`: filter `below` to entries with `min(n_a, n_b) >= MIN_REPS`, so the note does not describe a direction for an entry under the minimum. One clause: `if min(n_a, n_b) >= MIN_REPS and b < a < NEUTRAL`.
- **N-new-3.** Pin the note in `test_item_10_on_uniform_valence_is_mixed` (`tests/test_hypotheses.py:945`): `"below neutral" in below.note` for -0.1 / -0.5 and not for 0.2 / -0.5.
- **N-new-4.** `hypotheses.py:609` indexes `FLOOR_CLAUSE_TEXT[item]` for every item in `FLOOR_CLAUSES`. Both are `{3}` now, so there is no fault, but a future clause added to one dict only raises a `KeyError` at result time. A one-line test (`FLOOR_CLAUSES.keys() == FLOOR_CLAUSE_TEXT.keys()`) closes it.

## Probes

`probes-task13-rereview4/probe_rereview13d.py` and its outputs.

- **A:** item 10 through `_Tally.result` (23 cases against the register text), the falsifier and prediction against their stated rules on a 21 x 21 grid, and three two-model combinations.
- **B:** the evaluator on the stub run with in-memory valence edits, status and note per pair.
- **C:** an entry under `MIN_REPS` on the deep side (the over-reach), and a two-model run with the notes.
- **D:** the clause note across items 1 to 15 at 0 = 0 and 1 = 1 (item 1 raised `KeyError('any_self')` because the probe supplied no item 1 context, a probe artifact, not a defect); item 3's cases in detail.
- **E:** `status_from` callers, the docstrings, the `validity` set and text, the real-name denylist against the added text, and the item 10 row as rendered.
