# Task 4a re-review, fix round 1

Scoped re-review of `e4ca983..7d67f1e` (diff `review-e4ca983..7d67f1e.diff`, read once). Read-only on the checkout (`git status` clean after the probes); every probe is under `probes-task4a-rereview/` and builds its bundles in a temp directory. No subagents, and the suite was not run. The report's claims were treated as unverified and each was re-measured.

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| I1 manifest_complete near-misses | ADDRESSED | p9 |
| M1 schema reports every independent fault | ADDRESSED, two residuals (Nit) | p3, p8, p12 |
| M2 missing ladder fails schema | ADDRESSED for triggered and scheduled; PARTIAL overall (new Minor N-1) | p4, p8, p11 |
| M3 positives pin their reason | ADDRESSED | p13 |
| M4 duplicate persona name | ADDRESSED (the optional stem check was not added) | p3 |
| M5 no false clash inside plan_personas | ADDRESSED (a name-blind exemption, Nit) | p1, p11 |
| N1, N2, N3 | ADDRESSED | p3, p6 |
| N4, N5 | CARRIED as ruled (owner, 7b) | n/a |

Counts of new findings: Critical 0, Important 0, Minor 3, Nit 3.

### I1: ADDRESSED

- p9 takes each new row's mutation from `tests/test_bundle_lints.py` and tightens the rule across exactly the boundary the row fences, in-process only. Each row bites, and the good bundle still passes every tightened rule:
  - `_base_file_hand_edited` (`tests/test_bundle_lints.py:156`; the other rows at `:129`, `:141`, `:165`, `:176`): fails a "base file's sha must equal `base_files`" rule.
  - `_manifest_patches_a_second_base_file`: fails a "manifest may not name a base file" rule.
  - `_review_with_findings_and_harness_files`: fails a rule that counts `.attempt.json` or a review transcript as outside the manifest. `Bundle.index()` never lists those, so the rule has to walk the disk, and only this row would notice.
  - `_errored_but_present`: fails a "present with an error call" rule.
  - `_ok_then_error_and_absent`: fails a "first call decides" rule (1 result); its sibling `_errored_and_absent` still passes that rule (0).
- The three hollow rows of the first review are gone. The real near-miss share is 6 of 9 (2 positives, 1 negative, 6 near-misses that change the bundle), as claimed.
- p3 reproduces the review's own seven `manifest_complete` near-miss cases (ok then error absent, error present, hand edit, second base patch, transcript, `.attempt.json`, review findings): all pass the code, and the five positives still fail.

### M1: ADDRESSED

- The review's six two-fault bundles (p3 DOUBLES), before and after:

| Bundle | Before | After |
| --- | --- | --- |
| persona `captor` plus `world: overlay` | 1 result | both faults, plus 2 skip warns |
| document `mood:` plus bad Rescue param | 1 | both faults, plus 5 skip warns |
| two bad Rescue conditions | 1 | both conditions' refusals |
| config `colour` plus expected extra | 2 | both, plus 1 skip |
| empty `premise_terms` plus persona `captor` | 3 | both, plus 2 skips |
| `world: overlay` plus bad Rescue param | 1 | both, plus 1 skip |

- Every fresh p3 positive still fails and every near-miss still passes. The three remaining MISMATCH lines are the review's own known probe-input errors: `control` is registered as `polite_control`, the far-date body text, and the optional stem-versus-name check (M4).
- The skip logic is sound: a skip is never placed on a bundle with no failure (p8, below).

### M2: ADDRESSED for two of three gatings (see N-1)

- `env ladder missing` fails on triggered ("environment 'mini_triggered': world 'mini' has no ladder 'nope'") and on scheduled (p4). The `alt.yaml` near-miss passes.

### M3: ADDRESSED

- p13 switches each schema clause off in-process and runs the test's own `_matches` over `SCHEMA_POSITIVES`. All rows match with every clause on. With one clause off:
  - empty-terms: 3 rows stop matching;
  - drops-recorded-terms: 1 row;
  - environment-world: 1 row;
  - ladder: 1 row;
  - duplicate-persona: 1 row;
  - strategy-name clash: 1 row.
- Each clause has a row that pins it. This closes both survivors the review found (`if not terms`, and the environment-world loop).

### M4: ADDRESSED

- `personas/ferry_twin.yaml` beside `ferry_caller.yaml` gives "persona 'ferry_caller' is also personas/ferry_caller.yaml", plus skips for the conditions that name it. The stem-differs-from-name case still passes; the review made it optional.

### M5: ADDRESSED

- p1 case F: `lint_bundle(beta)` and `lint_bundle(alpha)` linted inside beta's open block give no fail; the registry equals its snapshot after the block.
- p1b: an exception before or after `register`, or duplicate keys, leaves the registry equal to its snapshot.
- The exemption is name-blind (Nit N-5).

### N1 to N3: ADDRESSED

- Blank terms: `[" "]` and `[" ", ""]` on a fresh world give "premise_terms has no term" once.
- `Gate log` for `gate log` passes (the premise pattern is case-insensitive).
- p6, the eleven malformed files, each name the file with no crash. A root that is no mapping reads `<root>: Input should be a valid dictionary`, and the message reads "does not load as Experiment".
- A document's message no longer repeats its path.
- `premise_terms: []` on a world with recorded terms gives one result (p3, double five).

## The ASSUMED calls

### 1. A skip is a warn: SOUND, with a hardening note

Asked: can a bundle with only a skip warn pass `lint_bundle` as runnable when its earlier step failed? No.

- **By construction.** Every `_skipped` has a fail it points at, emitted earlier in the same `_schema`:
  - `_load_worlds` skips only a world in `failed_worlds`, which `_load_files` fills in the same `except` that appends the fail.
  - `_environments` and `_runnable` skip only on a world that failed (a fail came from `_load_files` or `load_world`), a persona fail, an environment fail, or `config.yaml` not loading (a fail or "missing").
  - `_schema` returns `(out, None)` for any non-empty `out` (`bundle_lints.py:667`), so a skip can never yield a loaded bundle.
- **Measured (p8).** 61 bundles: all 47 p3 cases, the six doubles, and eight extra edge cases (an empty `worlds/annex/`, a stray file only under a world, an unused environment, a broken persona used by a condition, a broken persona beside a valid used one, a bad ladder file, a deleted `config.yaml`). In every one:
  - any skip warn comes with at least one schema fail;
  - `_schema` returns `None` exactly when it returns results;
  - no model-needing lint runs while schema fails;
  - there is no non-skip schema warn.
  - 0 problems.
- **Hardening (Nit N-3).** The coupling is implicit. If a later edit emitted a skip with no fail, `lint_bundle` would return no fail, run no world lint (`loaded is None`), and the bundle would look clean with every lint silent. Nothing pins this. Fix: a one-line test `any skip => any schema fail` over the six two-fault bundles, or `_schema` asserting it.

### 2. The ladder check only under triggered or scheduled gating: UNSOUND (Minor N-1)

- The stated premise, "under `none`, no ladder is read", is false. `EnvironmentRuntime.__init__` reads the ladder for every gating, before it builds the `Ladder`: `claude_bully/environments/runtime.py:503-508` raises "world 'mini' has no ladder 'nope'" unconditionally. `runtime.py:706` and `:873` index `world.ladders[config.ladder]` with no gating test.
- p11: `gating: none` plus `ladder: nope` gives NO fail from `lint_bundle` (p8 extra: 0 fails), while `EnvironmentRuntime(...)` for the same config raises `ValueError: world 'mini' has no ladder 'nope' (ladders: ['default'])`.
- The controller ruled "a missing ladder fails schema", with no gating qualifier. The implementer narrowed it on a wrong reading of the dry run.
- The clause line is `bundle_lints.py:581` (`env.gating in _LADDERED`); `_LADDERED` is `:411`.
- Fix: drop the `_LADDERED` test and the constant. This also corrects the spec's D-lint_bundle line, which repeats the narrowing. The `none` case needs its own row (positive and near-miss).
- Cost if left: a `none` arm that names a renamed ladder passes every lint of this task and refuses at its first rep, after `run.json` is written. Task 5's cell dry run may catch it, but the review's "carry to Task 5" note does not name `none`.

### 3. Isolation on refusal (`_refusals`, `bundle_lints.py:588-608`): KEEP, with two edits

Asked: after a whole dry run refuses, each condition is run alone. Can it report a refusal the whole run would not, and so mislead the repair?

- **No false refusal, by argument.** Every check in `run_experiment(dry_run=True)` is per-condition or per-environment (`check_condition`, `_poisoned_well_checks`, the environment switches, `world_premise_sheet`, `_premise_checks`, `_check_opener`). The one cross-condition rule is `_shortest_condition`: "no exchange after the last exchange of the shortest condition using the environment". A run on one condition has a subset of the cells, so its shortest cell is never shorter than the whole run's. A late schedule that refuses alone refuses in the whole too. The experiment-level validators are bypassed by `model_copy`, so the alone run adds none.
- **No false refusal, measured (p10).**
  - A pool of 10 conditions (good, bad param, unknown strategy, unknown environment, three scheduled lengths, triggered, captor, seeded) under four schedules, 280 random subsets, about 1,400 dry runs, 24 s.
  - 0 conditions refused alone but passed in context. Context means the condition run whole with the subset's non-refusing conditions.
  - 0 subsets where the whole run refused and no condition did alone (so the `or [whole]` fallback was never needed).
  - The tool's result count matched the number of alone-refusers in every subset.
  - Cost is about 15 ms a dry run, and the extra runs happen only after a refusal.
- **What can mislead (p10b).** The alone message for a longer condition says "the shortest condition using it, 'C_sched5'" when the whole run names 'B_sched0' (at `the_log: 22`, the lines name B with 13 bully turns and C with 18). Both are true statements about those conditions. They give the same repair (move the exchange), and B's line is always present, so the planner is not misdirected. The wording "shortest" is only true inside the alone run. Nit N-6.
- **One regression against the old behaviour (p10c, Minor N-2).** An environment-level refusal that every condition on that environment hits is reported once per condition: two conditions on `mini_triggered` with `honest: true` give two identical fail lines (same doc_id, same message). This reverses the first round's ASSUMED "one fault is reported once". Fix: dedupe in `_refusals`, `list(dict.fromkeys(...))`.
- Recommendation: keep it. It is what lets a bundle with two bad conditions report both, which M1 asked for, and the measured cost is negligible. Add the dedupe, and optionally prefix an alone message with "condition 'X' alone:".

## New breakage, by severity

### Critical, Important

None.

### Minor

- **N-1. A `none` environment naming a missing ladder passes `schema`** (`claude_bully/planner/bundle_lints.py:411`, `:581`). The ladder clause was narrowed to triggered and scheduled on a wrong reading of the runtime, which reads the ladder under every gating (`claude_bully/environments/runtime.py:503-508`). Probe p11 and p8. Fix: drop `_LADDERED`; correct the spec line and the ASSUMED. Add a `none` positive and a near-miss.
- **N-2. A shared environment-level refusal is reported once per condition** (`bundle_lints.py:597-608`). Probe p10c: two identical `schema` fails. Fix: dedupe the messages. This is also what keeps "one fault is reported once" true.
- **N-3. Nothing pins "a skip never stands without a fail"** (`bundle_lints.py:429-433`, `:667`; `tests/test_bundle_lints.py:548-565`). Safe today (p8, 61 bundles), but a regression would make a bundle look clean with every lint silent. Fix: a test that `any skip => any schema fail`, over the six two-fault bundles and the clean bundle.

### Nit

- **N-4. The skip hides a second fault that the dry run does not depend on, and the dry run reports one refusal per condition.**
  - p12: with `ladder: nope` on a triggered environment and a typo in its condition, only the ladder fault shows and the condition is skipped. The dry run builds no triggered ladder, so the dependency does not hold. Only a Poisoned Well on that environment would give a derivative message.
  - Separately, a scheduled environment's bad schedule rung and a typo in its own condition report only the typo, since `expand_cells` raises before `validate`. Within one condition the dry run still stops at its first refusal. The skip notes keep this honest, and it costs one more `plan validate` round.
- **N-5. `is_plan_persona` is name-blind** (`bundle.py:337-342`, `bundle_lints.py:551`). p11: a persona named `captor`, linted inside an open block that registered that same sheet, reports no clash, while outside any block it does. Unreachable in the flow (the lint runs before registration), and the review's alternative was narrower (a registered phased premise holding an equal sheet). Fix: compare the sheet, or leave it with a docstring line.
- **N-6. An alone message's "shortest condition" wording** (see ASSUMED 3). Optional prefix.

## Probes (all under `probes-task4a-rereview/`)

| Probe | Covers |
| --- | --- |
| `p3_lint_cases.py`, `p3_lib.py`, `p3_out.txt` | the review's 47 cases and six doubles at head; 44 OK against 40 before, 3 known MISMATCH |
| `p1_registry.py`, `p1b_registry_raise.py` (`*_out.txt`) | M5 and registry isolation |
| `p4_missing_ladder.py`, `p6_malformed.py` (`*_out.txt`) | M2, the eleven malformed files |
| `p8_skip_invariants.py`, `p8_out.txt` | skip never without a fail; loaded is None exactly when results exist (61 bundles); the `none` gap |
| `p9_manifest_bite.py`, `p9_out.txt` | I1 rows bite on tightened rules |
| `p10_isolation.py`, `p10b_messages.py`, `p10c_duplicates.py` (`*_out.txt`) | isolation: false refusals, messages, duplicates, cost |
| `p11_none_gating.py`, `p11_out.txt` | N-1 against the runtime; N-5 |
| `p12_residual_doubles.py`, `p12_out.txt` | N-4 |
| `p13_pin_bite.py`, `p13_out.txt` | M3 clause switch-off |
