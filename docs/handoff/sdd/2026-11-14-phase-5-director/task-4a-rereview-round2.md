# Task 4a re-review, fix round 2

Scoped re-review of `7d67f1e..ff6a2fc` (diff `review-7d67f1e..ff6a2fc.diff`, read once; one commit, four files: `bundle_lints.py`, the spec's D-lint_bundle line, `tests/test_bundle_lints.py`, `HANDOFF.md`). Read-only on the checkout (`git status` clean after every probe); every probe is under `probes-task4a-rereview2/` and builds its bundles in a temp directory; mutants are planted in-process by a pytest plugin, never by editing the source. No subagents. The report's "Fix round 2" claims were treated as unverified and each was re-measured.

## Verdicts

| Finding (from task-4a-rereview-round1.md) | Verdict | Evidence |
| --- | --- | --- |
| N-1 ladder check under every gating (`_LADDERED` dropped, spec corrected) | ADDRESSED | q1, q1b, q3c |
| N-2 `_refusals` dedupe | ADDRESSED | q2, q2b, q3c |
| N-3 a skip never stands without a fail | ADDRESSED | q3, q3b |

New findings: Critical 0, Important 0, Minor 0, Nit 3 (below). Round 1's open Nits N-4, N-5, N-6 are untouched, as ruled.

## N-1: ADDRESSED

- The diff removes `_LADDERED` and its comment; `_environments` now reads `elif env.ladder not in world.ladders` for every environment whose world loaded. `grep _LADDERED` over `claude_bully`, `tests` and `docs` finds nothing. The module docstring, the `_environments` docstring and the spec's D-lint_bundle line all say "whatever the gating" and cite `environments/runtime.py:503-508` (checked: that is the unconditional `served.ladders.get(config.ladder)` raise).
- Probe q1 runs the same edit over all three gatings, lint against the real `EnvironmentRuntime`:

| gating | ladder | `lint_bundle` schema fails | `EnvironmentRuntime` |
| --- | --- | --- | --- |
| none | nope | 1 ("environment 'mini_triggered': world 'mini' has no ladder 'nope'") | refuses |
| none | default | 0 | accepts |
| triggered | nope | 1 | refuses |
| triggered | default | 0 | accepts |
| scheduled | nope | 1 | refuses |
| scheduled | default | 0 | accepts |

  The lint and the runtime agree on all six. The one fail is accompanied by one `skipped:` warn for the condition that uses the environment (no second message).
- A `none` environment that names a world absent from the bundle gives the "no world under worlds/" fail only, not a second ladder message (the ladder clause does not run on a world that did not load). A `none` environment on a second bundle world (annex) reaches the dry run and reports that run's own refusal, not a ladder fail.
- The tests bite. In-process mutants over `tests/test_bundle_lints.py` (q3c):
  - revert to round 1 (ladder checked only under triggered and scheduled): `test_a_bundle_lint_case[schema-12-positive]` fails;
  - "every `none` environment fails" (an over-broad clause): `[schema-28-near]` fails, which is the new `none` near-miss;
  - unmutated: 75 passed on the same selection.
- The named test `test_a_no_gating_environment_naming_a_missing_ladder_fails_schema` pins the exact doc_id and message.

## N-2: ADDRESSED

- `list(dict.fromkeys(found)) or [whole]`: the key is the whole message string, so only byte-identical refusals merge, and first-seen order is kept. Probe q2 runs 12 shapes and compares each result count with the count of distinct alone-run texts; they are equal in every one:
  - three conditions on one environment with `honest: true`: 3 alone refusals, 1 result;
  - the same typo `stage_lenght` on two differently named conditions: 2 results (the message names the condition: "condition 'r1' (rescue) params: ..."), not merged;
  - near-alike typos (`stage_lenght` against `stage_lenth`): 2 results;
  - unknown strategies `nonesuch` against `nonesuch2`: 2; unknown environments `nope_env` against `nope_env2`: 2; two conditions on the same unknown environment: 2 (each message names its condition);
  - an environment-level refusal beside a condition-level one: 2; two environments each with their own `honest` refusal: 2 (each message names its environment);
  - the scheduled late-rung refusals that say "the shortest condition using it, 'X'" (q2b): two results, one per named condition, not merged.
- The only merges are the intended one (one environment's refusal shared by several conditions) and the same unknown-strategy name on two conditions (message text identical and naming no condition). The second loses nothing against round 1, which printed two identical lines.
- End to end through `lint_bundle` (q2b): a shared `honest` refusal on three conditions plus a distinct bad-param condition gives exactly two `schema` fails, the environment's once and the condition's.
- Bite (q3c): with the dedupe removed, `test_a_schema_positive_fails_for_its_reason[change-reasons11]` fails (the new shared-refusal row) and nothing else on the selection (the run stopped at the first failure; the report's RED also lists the named test).
- Residual (Nit N-7): no test pins "alike but different stays two". Two over-loose dedupe mutants, one keying on the message with quoted names blanked and one on its first 45 characters, pass all 75 selected tests. The code is correct (q2 B and C); only the pin is missing. A row of two Rescue conditions with the same typo and different names (`TWO_FAULTS` has the different-typo pair only) would close it.

## N-3: ADDRESSED

- `test_a_schema_skip_warn_never_stands_without_a_schema_fail` collects 21 cases (good bundle, 14 `SCHEMA_POSITIVES`, 6 `TWO_FAULTS`), as claimed. It asserts every `schema` warn starts with `skipped: `, any warn needs a `schema` fail, and the good bundle has no `schema` result at all.
- It bites (q3, in-process mutants, same selection; 21 pass unmutated):

| mutant | result |
| --- | --- |
| a skip planted after `_environments` when `out` is empty (the implementer's) | `[good]` fails |
| `_runnable` skips every condition wrongly | `[good]` fails |
| `_load_files` marks failures but loses the fail it appended (a real-shaped regression: skip without its fail) | `[positive-0]`, `[positive-1]`, `[two-faults-3]` fail |
| a non-skip `schema` warn added | all 21 fail |
| a skip added only on a bundle that already fails (legal) | 21 pass, so the test does not over-reject |

- The implementer's mutation claim holds. The test does not fail on 7d67f1e by construction (the property held), which the report states honestly.
- The near-miss share is real. Measured on the code at head (q3b): `schema` has 31 cases, 14 positives, 16 near-misses and 1 negative, as claimed. Every near-miss row changes the bundle on disk (sha256 snapshot before and after; zero hollow rows) and gives no `schema` result of either severity.
- The extra near-miss is the shared-refusal positive with its one fault removed: a second condition `ferry_triggered_two` on `mini_triggered`, no `honest: true`. It loads as a third condition (q3b prints the three), lint gives 0 schema results, and it is the only row in the suite with two conditions on one environment. It bites a mutant "fail when two conditions share an environment" (`[schema-29-near]` fails). The `none` near-miss (`gating: none`, the world's own `default` ladder) loads as `none`/`default` and bites "every `none` environment fails" (`[schema-28-near]`). Each of the three new schema rows therefore fences a distinct over-broad rule.
- The repo's near-miss rule needs more than half: 16 of 31 holds (15.5 needed); the report's note that three rows left it at 15 of 30 and a fourth was added is consistent.

## Report claims re-measured

- `uv run pytest tests/test_bundle_lints.py -q`: 120 passed, 1 deselected (report: 120 passed, from 91; +29 = 21 + 4 case rows + 2 reason rows + 2 named). Collect count of the skip test: 21.
- `ruff format --check` and `ruff check` on the two changed Python files: clean. The full gate and the slow run were not re-run (not asked); the diff touches only `bundle_lints.py` (a constant removed, one condition changed, one return line) and tests.
- HANDOFF.md (word diff): the fix round 1 clause now reads "whatever the gating, round 2", and a Fix round 2 sentence is added. Its counts (121 tests with one slow, 16 of 31, 14/16/1, 10159 passed) match the report and the 120 plus one slow run; the gate figure itself is the report's.
- Spec D-lint_bundle line: the "under triggered or scheduled gating ... run --dry-run builds no triggered ladder" clause is replaced by the corrected one; the rest of the line is unchanged.

## New breakage, by severity

### Critical, Important, Minor

None.

### Nit

- **N-7. Nothing pins that refusals differing only in a condition name stay two** (`bundle_lints.py:606`, `tests/test_bundle_lints.py` `TWO_FAULTS`). Two loose-dedupe mutants survive the whole selection (q3c). Code is correct today (q2 B, C, D, H). Fix: one `TWO_FAULTS` row with the same typo on two named conditions.
- **N-8. An unused environment that names a missing ladder fails `schema`, though the dry run accepts it** (q1b: `_refusals` returns nothing for an unused `none` or `triggered` environment with `ladder: nope`, and `EnvironmentRuntime` is built per used environment). This held since round 1 for triggered and scheduled (round 1's p8 included an unused environment); round 2 extends it to `none`, which is consistent with the world clause. The planner is told to fix a name no condition reads. Harmless; leave or document.
- **N-9. Identical refusals from different conditions merge into one that names no condition** (q2 D2: the same unknown strategy `nonesuch` on `u1` and `u2` gives one message). Round 1 printed two identical lines, which named no condition either, so nothing is lost; the strategy name is the repair handle.

## Probes (all under `probes-task4a-rereview2/`)

| Probe | Covers |
| --- | --- |
| `q1_none_ladder.py`, `q1_out.txt` | N-1 across none, triggered and scheduled against the runtime; unused and used `none` environments; world and ladder together |
| `q1b_unused.py`, `q1b_out.txt` | N-8: does the dry run refuse an unused environment's missing ladder |
| `q2_dedupe.py`, `q2_out.txt`; `q2b_sched.py`, `q2b_out.txt` | N-2: 12 shapes, alone results against deduped result; scheduled "shortest condition" messages; end to end |
| `q3_plugin.py`, `q3_out.txt` | N-3: five in-process mutants against the skip test |
| `q3b_nearmiss.py`, `q3b_out.txt` | the 31 schema cases: counts, every near-miss changes the bundle and passes with no result; the new rows load as intended |
| `q3c_plugin.py`, `q3c_out.txt` | N-1 and N-2 mutants (revert, over-broad `none`, over-broad shared environment, no dedupe, three loose dedupes) against the test selection |
