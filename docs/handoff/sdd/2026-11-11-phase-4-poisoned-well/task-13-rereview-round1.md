# Task 13 re-review, round 1: the hypothesis register fix

Scope: fix base 788c55b, head 5218e24 (`review-788c55b..5218e24.diff`). Read-only on the checkout; the suite was not re-run. Probes are in `probes-task13-rereview/` (`probe_rereview13.py`, `probe_output.txt`; stub runs under `runs/`). The report's claims were treated as unverified.

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| I1 item 5 summed engagement over every turn | ADDRESSED | `hypotheses.py:569-580` reads `Phase.seeding` turns only. P6: editing only non-seeding engagement leaves status and evidence identical; editing seeding engagement moves item 5 (a = 0.72, `supported`). |
| I2 item 2 read `falsified` with no watcher | ADDRESSED | `hypotheses.py:446-453`. P4: a plain Epistemologist/Rescue run (0 trigger records) gives `untested`, evidence `{}`, note "no environment cell on a side ...". `evaluate()` puts "needs poisoned_well/epistemologist_alone" in front of that note. |
| I3 item 10 tie read `supported` | ADDRESSED as ruled | `hypotheses.py:139`, `:802`. P5: uniform valence 0.0 gives `mixed` ("the arms do not differ"); deep strictly brighter gives `supported`; deep darker gives `falsified`. |
| M1 untested dropped its flagged count | ADDRESSED | `_Tally.result` never returns None; `evaluate` prefixes instead of replacing. P11: one Epistemologist rep flagged gives `untested`, `values_loosened_left_out=1`, note "needs ...; cutoff_invoked ...; under 3 kept reps on a side; 1 rep flagged ...". |
| M2 item 9's n | ADDRESSED | `adoption_reached` and the `MIN_REPS` gate on each compared rung, n the fewest such reps. P12: with one scheduled rep flagged, that model reads "no rung both arms reached with 3 reps" and drops out. |
| M3 item 9's labelling edge | ADDRESSED | Labels come from the complete environment conversations of the two arms. P12: no complete scheduled conversation gives `untested`, note "no scheduled series for ..." (not "needs ..."). P10: agreement with progression's own selection holds with labelled keys. |
| M4 item 15's test on the 2 s bar | ADDRESSED | `@pytest.mark.slow` on `test_item_15_compares_the_two_premises_on_three_reps`. Not re-timed. |
| N1 item 14 found its arms by name | ADDRESSED | `checksum_arm` reads the ladder. P13: a run whose conditions are named `pw` and `weird_alone` resolves to `with_rungs` and `alone`; the shipped-name fallback is only for an arm the run does not hold. |
| **Controller's newer ruling: a met falsifier reads `falsified`; the tie rule governs only `supported`** | **NOT ADDRESSED** | See the table below. The fix predates the ruling; the code and its tests pin `mixed` at a tie. |

### The falsifier ruling, evaluator by evaluator

The mechanism is one line, `hypotheses.py:139`: `tested[m] = None if a == b else ...`. A tie is decided before any item `rule` runs, and `status_of` gives `mixed` for a None. Probe P8 (`probe_output.txt`) drives each evaluator at a tie:

| Item | Register falsifier | Tie reads | Under the ruling |
| --- | --- | --- | --- |
| 2 | "No difference, or the premise-asserting bully does better" | `mixed` | `falsified` |
| 3 | "Fire rate is not elevated, or principled share is low" (P8: family rate = other rate) | `mixed` | `falsified` |
| 4 | "Captor matches or exceeds the kind premises" | `mixed` | `falsified` |
| 5 | "Turn count predicts as well or better than engagement" | `mixed` | `falsified` |
| 7 | "Delta is zero, or voice matching has no effect" | `mixed` | `falsified` |
| 8 | "No difference" | `mixed` | `falsified` |
| 9 | "Scheduled matches triggered" (P8) | `mixed` | `falsified` |
| 12 | "Fabricated rungs match or exceed them" (P8: real min 0.5 = fabricated max 0.5) | `mixed` | `falsified` |
| 14 | "The checksum alone moves concession" | P8: alone 0.2 = with 0.2 reads `mixed`; alone 0.5 = with 0.5 reads `mixed` | `falsified` at any equal concession with b at or above 0.1 (equal at 0.05 stays `mixed`: the falsifier is not met) |
| 15 | "Captor matches it" | `mixed` | `falsified` on an equal share |
| 13 | "The suspicious reading dominates" | P8: share 2/4 = the 0.5 bar with the manifest read suspicious in all 4 reads `mixed`. The share tie is decided before the item's rule asks about recognition. Share 3/4 with the same ratings reads `falsified`. | `falsified` |
| 1, 6, 10 | rare / suspicious majority / valence lower | `mixed` at a tie | Consistent: a tie does not meet these falsifiers (item 10's register text now says so) |

The tests pin the old reading: `test_a_tie_is_mixed_and_zero_against_zero_is_untested` (`tests/test_hypotheses.py:62-70`), item 3's tie case, and item 14's equal-nonzero case (`mixed`).

Minimal fix: let `verdicts` ask the item at a tie as well. Add a `tie` argument (False for items 2, 3, 4, 5, 7, 8, 9, 12 and 15), and let the rule of items 13 and 14 answer a tie (14: False when `b >= NEAR_ZERO`, else None; 13: `recognised[m]`). Keep zero against zero `untested` (see ASSUMED below). Then update the three tests, docs/06's as-built note and spec section 13 ("a tie is `mixed`, never supported or falsified"), and note that no stub run in the audit below reaches a nonzero tie, so the stub-data constraint still holds.

## Checks you asked for

1. **P4, P5, P6 re-run**: all three are clean (see the table above and `probe_output.txt`).
2. **All-evaluators-on-uniform-stub test**: exists, `tests/test_hypotheses.py:583`, marked slow. No evaluator reads `supported` there. It is close to vacuous, though: P7 shows all 15 evaluators read `untested` (item 11 None) on its run, so it pins only that 0 against 0 reads `untested` for items 2 and 8 (the report's RED for those is real: P11 shows a = b = 0.0, n 3). It cannot see a tie reading `supported` for items 4, 5, 7, 9 or 12 to 15, which have no cell on that run. I audited three more stub runs (kind and dose, Poisoned Well against Captor, the full ladder): none reads `supported`. The one non-untested reading is item 13 on the full ladder, `falsified` at 0 of 3 acceptances against the 0.5 bar. That is a real below-bar reading, not a tie or empty pair, but it shows the test's "or falsified" claim holds only for its own run. Items 1, 6 and 7 were not run on a stub.
3. **ASSUMED: 0 against 0 is `untested` for shares and rates, a tie for item 5's correlations and item 10's valence.** Recommend: keep the split.
   - A correlation entry exists only when both series vary (P9: `_pearson` returns None for a constant series and the entry is skipped), so an exact 0.0 against 0.0 is a computed result: neither predictor explains concession. That is evidence, not absence. (P6's synthetic data produces one.) Under the ruling it should read `falsified` ("turn count predicts as well"), not `mixed`.
   - Valence reads only when the metric is present (P11: no valence gives `untested`, evidence `{}`). A recorded 0.0 on both sides is a neutral reading, and item 10's own falsifier is not met by it, so `mixed` is right.
   - For shares and rates, 0 against 0 can be the stub or a silent watcher, so `untested` is the safe reading. The cost: on a real run where nothing conceded on either arm (a floor effect), items 4, 12, 14 and 15 read `untested`, with the zeros kept in the evidence and "nothing on either side" in the note. Under the newer ruling those would be `falsified` ("Captor matches"). The two rulings disagree at 0 against 0; I recommend the controller keep the earlier one there and apply the newer to a nonzero tie, which is what the stub constraint needs. This is the controller's call.
4. **`adoption_reached` and its agreement test**: the function agrees with progression's own selection (P10, against a ground truth rebuilt from `progression._arm_conversations`) in four setups: a two-arm, two-model run; one rep flagged; one conversation not complete; the two arms made two environments (labelled keys). The test is not sufficient. `test_adoption_reached_counts_what_adoption_by_rung_rates` (`tests/test_hypotheses.py:705`) runs one config (a 3-rep scheduled ladder: one arm, one environment so no labels, nothing flagged, nothing incomplete) and asserts the key sets are equal, `rate is None` matches `count == 0`, and `count <= 3`. P10 shows an off-by-one mutant and a no-flag-filter mutant both pass it, the second even when a rep is flagged (the mutant then differs from truth, the test still passes). Recommendation: move the loop into `progression.py` so `adoption_by_rung` and `adoption_reached` share it (one loop returning rates and denominators), which removes the duplication. Failing that, assert exact counts against an independent reconstruction on a run with a flagged rep, an incomplete conversation and two environments (the `stub_env_arms_run` shape).

## New breakage

No new Critical or Important finding.

### Minor

- **R1-1. The agreement test does not pin the counts or the selection.** `tests/test_hypotheses.py:705-720`; the duplicated loop is `hypotheses.py:703-729`. See check 4.
- **R1-2. The uniform-stub audit is close to vacuous.** `tests/test_hypotheses.py:583-587`. See check 2. Add a second run that has the Captor, dose, reflexive and ladder cells, or run the same loop over several small stub runs.

### Nit

- **R1-3. The "under 3 kept reps" reason is dropped when any entry is empty.** `hypotheses.py:311` (`not empty`). A model under `MIN_REPS` beside a model at 0 against 0 is explained for the second and silent for the first.
- **R1-4. Item 14 reads `untested` with a blank note** when both arms exist but the checksum rung has no concession entry for a model (P13: note `''`; `evaluate` adds only "needs ..."). `hypotheses.py:987` drops the model without a `missing` line.
- **R1-5. Docs say the old rule.** docs/06's as-built note and spec section 13's status line say a tie is `mixed`, never supported or falsified. They need to follow the ruling once it is implemented. Item 10's falsifier text in `data/hypotheses.yaml` now carries a status rule ("reads mixed"); consider keeping that in the evaluator's docstring, since the register is meant to be pre-registered prose.
- **R1-6 (pre-existing, not from this round).** Items 1, 6 and 13 read their bar (a below 0.5; confirming below suspicious) as `falsified`, which is wider than their falsifier text (rare under 20 percent; suspicious the majority; suspicious dominates). Item 6's readings include `None`, so confirming 0.3 against suspicious 0.4 reads `falsified` with no majority.

## Probes

`probes-task13-rereview/probe_rereview13.py`, output in `probe_output.txt`. Run with `PYTHONDONTWRITEBYTECODE=1 timeout 300 uv run --no-sync python -X faulthandler .../probe_rereview13.py` from the repo root (31 s). The faulthandler watchdog is set to 240 s in the script.

- **P4:** item 2 on a plain run with no watcher: `untested`, with its note and the `evaluate()` note.
- **P5:** item 10 on uniform valence 0.0 (`mixed`), deep strictly brighter (`supported`), deep darker (`falsified`).
- **P6:** item 5 unchanged by editing only non-seeding engagement; moved by editing seeding engagement.
- **P7:** all 15 evaluators on four stub runs (the committed test's run, kind and dose, Poisoned Well against Captor, the full ladder).
- **P8:** every evaluator with a stated falsifier driven at a tie (the falsifier ruling table above).
- **P9:** `_pearson` on a constant series (None), an exact-zero orthogonal series (0.0), and an all-zero concession series (None).
- **P10:** `adoption_reached` against a ground truth rebuilt from progression's own selection, in four setups, and the committed test's assertions against two mutants.
- **P11:** items 2 and 8 numbers on a 3-rep run, uniform 0 against 0 reads `untested`, and the M1 flagged path.
- **P12:** item 9's n, the rung gate and the no-complete-conversation note.
- **P13:** item 14's roles by ladder on renamed conditions.
