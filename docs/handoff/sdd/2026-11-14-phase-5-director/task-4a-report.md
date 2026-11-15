# Task 4a report: the good fixture bundle, plan_personas and lint_bundle's first lints

## What I implemented

- `claude_bully/planner/bundle.py`:
  - `bundle_personas(bundle) -> dict[str, PersonaSheet]`: every `personas/*.yaml`, loaded with `load_yaml_model`, keyed by sheet name.
  - `plan_personas(sheets)`: a `@contextmanager`. It calls `ensure_registered()` first, then registers each sheet with `make_phased_premise`. On exit, exceptions included, each name it registered is removed, or given back the class it replaced. It reads `strategies.base._REGISTRY` through the module, so the `isolated_registry` monkeypatch reaches it. It never restores a snapshot. Blocks nest.
- `claude_bully/planner/bundle_lints.py`:
  - `BUNDLE_LINT_IDS`: twenty ids in spec section 9's order, `WORLD_LINT_IDS` among them.
  - `lint_bundle(bundle, *, dry_run=None)`. It runs:
    - `schema`, in this order, stopping at the first step that fails:
      1. Each grammar file loads into its model with no unknown field: `WorldSheet`, `parse_document`, `LadderConfig`, a premise's `world_sheet`, `PersonaSheet`, `Experiment`, `ExpectedEvents`.
      2. `config.yaml` and `expected.yaml` exist.
      3. Each world whose files loaded passes `load_world(name, bundle/worlds)`.
      4. `premise_terms` is non-empty and keeps every term of `base_premise_terms` (R-premise-terms).
      5. No persona name is in `all_strategies()`, read after `ensure_registered()` and before any registration.
      6. Every `environments[*].world` is a bundle world.
      7. `run_experiment(exp, runs_root=<TemporaryDirectory>, dry_run=True, worlds_dir=bundle/worlds)` passes inside `plan_personas(personas)`.
    - `manifest_complete`. Every manifest path exists unless its last `file:<path>` call is `error`. No grammar file other than `plan.md` and `review.md` is outside the manifest and `base_files`.
    - The world-level lints, per bundle world: Phase 3's `lint_world` and `lint_world_lines`. Every result is kept, warns included (R-good-warn). Document ids are rewritten to the bundle path of the file that holds them.
    - `bully_line` over every persona's `fallback_lines`, with `BULLY_LINE_SHAPES` plus `premise_words` from the worlds the config's environments name. The doc_id is `<persona>/fallback_lines/<i>`.
  - When `schema` fails, the model-needing lints report nothing. `manifest_complete` still runs: it needs only `plan.json` and the index.
- `tests/conftest.py`: `isolated_registry`, verbatim from the brief.
- `tests/fixtures/bundle_fixtures.py`: `GOOD`, `GOOD_MANIFEST` (13 entries in author order), `GOOD_WARNINGS`, `good_bundle`, `mutate`. Two extra public names: `BASE_WORLD` and `NO_FINDING`. `good_bundle` builds the bundle in this order:
  1. Writes the `PlanRecord` (provenance `manual`).
  2. Commits `plan.md` through `write_manual(stage="plan")`.
  3. Copies mini with `write_file` and commits `base_files`, `base_worlds["mini"] = world_hash(...)` and `base_premise_terms` in one record write.
  4. Commits `record.manifest = GOOD_MANIFEST` in one record write (Q17).
  5. Commits each manifest file through `write_manual(stage="author")`.
  6. Writes `review.md` (`block 0 / fix 0 / note 0\n`) with `write_file`.
  7. Commits the review and revise stages with no call, sets `review_counts` to zeros and sets status `authored`.
- `tests/fixtures/bundles/good/`:
  - `plan.md`: question, cells, headline chart, expected events, null result, budget.
  - `config.yaml` and `expected.yaml`, with the brief's values.
  - `personas/ferry_caller.yaml`.
  - `worlds/mini/world.yaml`: only `the_log_line` changed, to "You were not supposed to see that. Nobody was."
  - `worlds/mini/ladders/default.yaml`: examples added on every rung.
  - `canteen-menu.md`: `date: 2041-09-08` added.
  - `courier-fare-notice.md`: url changed to `https://quillon-courier.example/news/fare-notice`.
  - Six new documents:
    - Seam: `crew-rota-september`, which links `rota-overtime-sheet`.
    - Seam: `harbour-works-ticket`, which links no buried document.
    - Filler: `pier-cafe-hours` (unlinked; this is DOCS[2]).
    - Buried: `rota-overtime-sheet` (sorts after `night-gate-log`).
    - Filler: `courier-letters-allotments`.
    - Filler: `lost-property-notice`.
  - Mini's layer counts become surface 2, seam 3, buried 2, filler 6 of 13.
- `tests/test_real_names.py`:
  - `SCANNED` gains `FIXTURE_BUNDLES`.
  - A bundle's top-level `config.yaml` is routed to `_bundle_configs()` and scanned through `_config_hits`.
  - New tests: `test_the_scan_covers_the_fixture_bundles` (asserts `good/plan.md` is scanned) and `test_no_real_names_in_the_fixture_bundle_configs`.
- Docs:
  - HANDOFF Phase 5 item 4.
  - docs/00 section H (Task 4a changes no record).
  - docs/08: the Schema and Inconsistency rows name their lint ids.
  - The spec's "As planned" Task 4a block: D-lint_bundle, D-plan_personas, R-registry, R-good-warn, R-premise-terms, the good bundle.

## Tests

`tests/test_bundle_lints.py` has 61 tests, 1 of them slow.

- `test_a_bundle_lint_case`: 50 cases. Each non-schema case also asserts that `schema` reports nothing (Q21).
- `test_the_bundle_lints_carry_more_near_misses_than_positives_so_far`: checks `schema` and `manifest_complete`.
- `test_the_good_bundle_passes_every_lint`: no fail, and the warns equal `GOOD_WARNINGS`.
- `test_the_good_bundle_is_recorded_as_a_manual_plan`: stages, calls, `review.md`, ten world files of which four are patches, `base_files`, `base_premise_terms`.
- `test_the_manifest_pins_what_the_director_tests_lean_on`: Q18 and Q19.
- `test_a_document_result_names_its_bundle_path`.
- `test_a_fallback_line_result_names_the_persona_and_the_line`.
- `test_a_schema_failure_silences_the_lints_that_need_a_loaded_model`.
- `test_plan_personas_removes_only_what_it_registered` (the brief's test).
- `test_plan_personas_puts_back_a_class_it_replaced_and_nests`: added, covering the "puts back what it replaced" clause.
- `test_the_lints_leave_the_registry_as_they_found_it`.
- `test_the_lints_in_a_fresh_process_keep_every_strategy`: slow, runs in a subprocess.

## Per lint: rule and near-miss share

| Lint | Rule | Positives | Near-misses | Negatives | Near-miss share |
| --- | --- | --- | --- | --- | --- |
| `schema` | Steps 1 to 7 above | 7 | 9 | 1 | 9 of 17 |
| `manifest_complete` | As above | 2 | 4 | 1 | 4 of 7 |
| `bully_line` | Unlock lines and persona fallback lines against the shapes and premise words | 2 (unlock line, fallback line) | 2 | 1 | 2 of 5 |
| `trigger_examples` | Task 3's rule | 1 | 1 | 1 | 1 of 3 |
| `ladder_walk` | Task 3's rule | 1 | 1 | 1 | 1 of 3 |
| `inconsistency_declared` | Task 3's rule | 1 | 1 | 1 | 1 of 3 |
| `clock_rule` | Task 3's rule | 1 | 1 | 1 | 1 of 3 |
| `layer_counts` | Task 3's rule | 1 | 1 | 1 | 1 of 3 |
| `seam_dead_ends` | Task 3's rule | 1 | 1 | 1 | 1 of 3 |
| `outlet_backing` | Task 3's rule | 1 | 1 | 1 | 1 of 3 |

The world-level lints get one positive and one near-miss each here, as the brief says; their full sets, with over half near-misses, are Task 3's. Positive reasons, each measured:

- `schema`:
  - colour: an Experiment extra field.
  - mood: a Document extra field.
  - captor: the name clash.
  - overlay: "is no world under worlds/".
  - rescue_plain `stage_lenght`: `run --dry-run` refuses it through RescueParams.
  - `premise_terms: []`: empty.
  - `gate log` dropped: "drops gate log".
- `ladder_walk`: an unknown unlock id. `schema` still passes; `run_experiment(dry_run=True)` does not build ladders.
- `outlet_backing`: Pennet Ferry Authority added as an `Outlet:` cast entry, with no link in.

## RED and GREEN

- RED 1, at import: with `bundle.py` and `bundle_lints.py` stashed at HEAD, `uv run pytest tests/test_bundle_lints.py -q` fails at collection with `ImportError: cannot import name 'bundle_personas' from 'claude_bully.planner.bundle'`.
- RED 2, per case: with `lint_bundle` stubbed to `return []`, 22 tests fail:
  - every positive (18 of them);
  - the good-bundle warn pin;
  - the bundle-path, fallback-line and schema-silencing tests.

  Every near-miss and negative passes.
- Order: the fixture files were written first, then the module code, then the test file. The RED runs above were taken against HEAD's modules and against a stubbed `lint_bundle`; no lint was tuned after a test ran, except as noted under GREEN.
- GREEN, focused: `pytest tests/test_bundle_lints.py tests/test_real_names.py tests/test_cli.py -m "slow or not slow" -W error` gives 164 passed.
- GREEN fixes after the first runs:
  - The fallback-line test's expected set was missing the `advice` shape, which "Look at" also matches.
  - The first full gate failed one test: `test_plan_personas_removes_only_what_it_registered` saw 38 strategies, not 36. `tests/test_strategy_base.py` and `tests/test_strategy_plumbing.py` register `_`-prefixed strategies when the suite is collected. The assertion now counts names without a leading underscore, which is `list-strategies`' own rule.
- Gate:
  - ruff format --check and ruff check: clean.
  - `mypy claude_bully` and `mypy --platform linux claude_bully`: clean.
  - `pytest -q -W error`: 10099 passed, 10 skipped, 49 deselected. This is the second full run, after the fix; the first was 1 failed, 10098 passed. The full suite was run twice, not once as the brief asks.
  - `pytest -q -m slow`: 49 passed.

## Registry isolation evidence

- Fresh process: the slow subprocess test runs `lint_bundle` twice in a new interpreter and prints `36 False`.
- Both test orders, each under `-W error -m "slow or not slow"`:
  - `test_bundle_lints.py` then `test_cli.py`: passed.
  - `test_cli.py` then `test_bundle_lints.py`: 79 passed.
  - The underscore strategies' modules collected first, then `test_bundle_lints.py`, then `test_cli.py`: 103 passed.
- In the full suite, `test_cli.py`'s 36 holds with `test_bundle_lints.py` run before it.
- `lint_bundle` restores the registry on its own, through `plan_personas`, even without the fixture.

## Reader-eye review of the lines the bundle adds (for the task's reviewer; my read)

- `the_log_line`, "You were not supposed to see that. Nobody was.": it reacts, as a slip. It announces nothing, advises nothing, dares nothing and names no place.
- The six `fallback_lines` each react and point nowhere:
  1. "I keep thinking about the noise that night."
  2. "Hold on. That doesn't sit right with me either."
  3. "My uncle never talked about his nights at the quay."
  4. "Funny. I had the same thought on the last crossing."
  5. "I'm not sure why that bothers me so much."
  6. "Wait. That one went straight through me."
- The ladder `examples` are target lines, not bully lines.
- The task's reviewer still owes the binding verdict.

## Files changed

- Modified:
  - `claude_bully/planner/bundle.py`
  - `claude_bully/planner/bundle_lints.py`
  - `tests/conftest.py`
  - `tests/test_real_names.py`
  - `HANDOFF.md`
  - `docs/00-RECONCILED.md`
  - `docs/08-DIRECTOR.md`
  - `docs/superpowers/specs/2026-11-14-phase-5-director-design.md`
- Created:
  - `tests/fixtures/bundle_fixtures.py`
  - `tests/test_bundle_lints.py`
  - `tests/fixtures/bundles/good/`:
    - `plan.md`, `config.yaml`, `expected.yaml`
    - `personas/ferry_caller.yaml`
    - `worlds/mini/world.yaml`
    - `worlds/mini/ladders/default.yaml`
    - eight corpus files

## ASSUMED

- ASSUMED: `config.yaml` is loaded with `Experiment.model_validate` of its YAML, which is what `load_experiment` does. This lets the message name every field.
- ASSUMED: `schema` requires `config.yaml` and `expected.yaml` to exist, since both are fixed files.
- ASSUMED: `schema` stops at the first failing step: files, then worlds and terms, then persona names, then environment worlds, then the dry run. One fault is reported once, and a persona that clashes with a strategy is never registered over it.
- ASSUMED: "its call" in `manifest_complete` is the last `file:<path>` call across `record.stages`. `rounds` holds only review, revise and validate stages.
- ASSUMED: a persona's name is its sheet's `name`. `bundle_personas` keys by it.
- ASSUMED: "every fires line opens its rung with mini's cast terms" means the rung opens with the cast names as the watcher's world terms. Each fires line also names a cast member.
- ASSUMED: "hypotheses: [9] on one" means one Expectation.
- ASSUMED: three `manifest_complete` near-misses are properties the good bundle already has: `plan.md` and `review.md` present; a base file unchanged; a base file patched by a manifest entry. They are written as changes that only assert that property.
- ASSUMED: `good_bundle` sets `review_counts` to zeros. `created_at` and the stage times are `now`.
- ASSUMED: the outlet_backing cases add an `Outlet:` cast entry, because mini has no outlet.

## Concerns

- The brief's registry test pinned `len(all_strategies()) == 36`. In the full suite that is 38, because of two test-module strategies. I changed the assertion to count non-underscore names. Please confirm this reading.
- `schema` does not catch a ladder that fails to build. `run_experiment(dry_run=True)` does not build ladders, so `ladder_walk` reports it instead.
- `GOOD_MANIFEST` is a module-level mutable list, as the interface types it. `good_bundle` copies it.

## Fix round 1

This round answers `task-4a-review.md`: I1, M1 to M5 and N1 to N3. It is one new commit on e4ca983.

### What changed

- **I1, `manifest_complete`.** The three near-misses that only asserted something are replaced by changes that really mutate the bundle. Each keeps its precondition as an assert.
  - `_base_file_hand_edited`: `ferry-about.md` is edited by hand. No manifest entry names it, and its sha now differs from `base_files`.
  - `_manifest_patches_a_second_base_file`: a new `ManifestEntry` for `ferry-about.md` is committed through `write_manual`.
  - `_review_with_findings_and_harness_files`: `review.md` gets a finding, and a `transcripts/review-reviewer-0.json` and an `.attempt.json` are added.
  - Two more rows from the review: `_ok_then_error_and_absent` (the last call is an error after an ok call, and the file is gone) and `_errored_but_present`.
  - The real near-miss share is now 6 of 9: 2 positives, 6 near-misses that change the bundle, 1 negative.
- **M1, `schema` reports every independent fault.**
  - Every step runs on whatever loaded.
  - A step that depends on a failed one is skipped with a `schema` warn reading `skipped: <what> (<why>)`. The skipped steps are: `load_world` of a world whose file failed; the ladder check of an environment whose world did not load; the environment checks and the dry run when `config.yaml` does not load; and the dry run of a condition whose environment failed or whose world did not load, that names a persona that failed, or that names an unknown part while a persona file failed to load.
  - The dry run covers the conditions that can be checked. When the whole run refuses, each condition is run alone so that each one's refusal is reported; if none refuses alone, the whole run's refusal is reported.
  - The test is `test_independent_faults_are_each_reported_and_a_dependent_step_says_it_was_skipped`. It runs the review's six two-fault bundles. Each one now reports both faults and the expected skip notes, and every schema warn starts with `skipped: `.
- **M2, ladders.** Under triggered or scheduled gating, an environment's `ladder` must be one of its world's ladders: "environment 'mini_triggered': world 'mini' has no ladder 'nope'". There is a positive (`ladder: nope`) and a near-miss (an `alt.yaml` ladder that exists).
- **M3, reasons pinned.** `SCHEMA_POSITIVES` holds 12 positives. Each lists every fail result it gives, as `(doc_id, a substring of the message)`. `test_a_schema_positive_fails_for_its_reason` requires an exact match, and requires that no message repeats its doc_id. The fresh-world `premise_terms: []` case was added.
  - I checked by deleting clauses, restoring the file each time:
    - empty-terms clause deleted: 6 failed;
    - environment-world clause deleted: 3 failed;
    - ladder clause deleted: 2 failed.
- **M4, duplicate names.** Two persona files with one `name` fail, naming both: "persona 'ferry_caller' is also personas/ferry_caller.yaml". Only the first file's sheet is kept. A duplicated name is not registered, and its conditions are skipped.
- **M5, open blocks.** `bundle.py` gains `is_plan_persona(cls)`, backed by a `WeakSet` of every class `plan_personas` registered. The name check skips those classes, because they are a plan's personas, not strategies. `test_the_lints_inside_an_open_block_for_the_same_persona_find_no_clash` covers this: no fail, and the outer block's class is still in place inside the block.
- **Nits.**
  - N1: blank terms count as none: "premise_terms has no term", tested on a fresh world with `[" ", ""]`.
  - N2: recorded terms are compared after strip and casefold. "Gate log" is now a near-miss that passes.
  - N3, messages:
    - "does not load as Experiment";
    - the root is labelled `<root>`, tested with an `expected.yaml` that is a list;
    - a message no longer repeats its path;
    - `premise_terms: []` on a reused world gives one result, not two.
  - N4: `first_crumb_line` is unchanged. It is the owner's prose call.
  - N5: `repair:` calls are still not read. Carried to 7b.
- Near-miss share for `schema`: 14 of 27 (12 positives, 14 near-misses, 1 negative). The new near-misses are `captors`, the case change, a blank term beside real terms, the `alt` ladder and an unused second persona.

### RED and GREEN

- RED: on e4ca983's code, `timeout 300 uv run pytest tests/test_bundle_lints.py -q` gives 18 failed, 73 passed. The failures are:
  - four schema rows of `test_a_bundle_lint_case`: the annex blank-terms, missing-ladder and duplicate-persona positives, and the Gate-log near-miss;
  - seven of `test_a_schema_positive_fails_for_its_reason`;
  - all six of the two-fault test;
  - the open-block test.
- GREEN:
  - `tests/test_bundle_lints.py`: 91 passed.
  - Order runs, each with `-W error -m "slow or not slow"`:
    - `test_bundle_lints.py`, `test_real_names.py`, `test_cli.py`: 195 passed;
    - `test_cli.py` then `test_bundle_lints.py`: 110 passed.
  - Gate: ruff format --check, ruff check and both mypy runs clean; `pytest -q -W error` 10130 passed, 10 skipped, 49 deselected (from 10099: 31 tests); `pytest -q -m slow` 49 passed.

### Files

- `claude_bully/planner/bundle_lints.py`
- `claude_bully/planner/bundle.py` (`is_plan_persona`)
- `tests/test_bundle_lints.py`
- `HANDOFF.md`
- the spec's "As planned" D-lint_bundle line

### ASSUMED

- ASSUMED: a skip note is a `schema` warn, not a fail. It sits beside the failure that caused it and never appears on a bundle that has no failure, so `GOOD_WARNINGS` is unchanged.
- ASSUMED: the ladder clause applies under `triggered` and `scheduled` gating only. Under `none`, no ladder is read.
- ASSUMED: this replaces the earlier ASSUMED "schema stops at the first failing step".

### Concerns

- When the whole dry run refuses, the per-condition runs add one dry run per condition. With the good bundle's two conditions this is small.
- A per-condition run without its explicit control could report a refusal the whole run would not. That only happens when the whole run has already refused.

## Fix round 2

This round answers `task-4a-rereview-round1.md` (N-1 to N-3) under the controller's ruling. One new commit on 7d67f1e. Fixer: sonnet (fresh).

### What changed

- **N-1, the ladder check under every gating.** `EnvironmentRuntime.__init__` (`claude_bully/environments/runtime.py:503-508`) reads `served.ladders.get(config.ladder)` and raises "world ... has no ladder ..." under every gating, so a `gating: none` environment naming a missing ladder passed `lint_bundle` and refused at its first rep.
  - `claude_bully/planner/bundle_lints.py`: `_LADDERED` and its comment are gone; `_environments` tests `env.ladder not in world.ladders` for every environment that has a loaded world. The module docstring and `_environments` docstring say "whatever the gating".
  - `docs/superpowers/specs/2026-11-14-phase-5-director-design.md`, the D-lint_bundle line: "under triggered or scheduled gating ... (review M2: `run --dry-run` builds no triggered ladder)" now reads "its `ladder` a ladder of that world, whatever the gating (review M2; fix round 2: `EnvironmentRuntime` reads the ladder under every gating, `environments/runtime.py:503-508`, so a `none` environment naming a missing ladder refuses at its first rep)". This supersedes fix round 1's ASSUMED ("the ladder clause applies under triggered and scheduled gating only"): that assumption was wrong.
  - Tests: a `SCHEMA_POSITIVES` row (`gating: none`, `ladder: nope` gives exactly "world 'mini' has no ladder 'nope'"), the named test `test_a_no_gating_environment_naming_a_missing_ladder_fails_schema` (exact doc_id and message), and a near-miss in `CASES` (`gating: none` with the world's own `default` ladder passes).
- **N-2, `_refusals` dedupe.** The per-condition results are `list(dict.fromkeys(found)) or [whole]`: an environment-level refusal two conditions share is reported once, and two conditions with different refusals are still both reported (the existing two-bad-Rescue-conditions row).
  - Tests: a `SCHEMA_POSITIVES` row (the `mini_triggered` environment gets `honest: true`, which the mini sheet cannot honour, plus a second condition on it, `ferry_triggered_two`; exactly one result), the named test `test_an_environment_refusal_two_conditions_share_is_reported_once`, and a near-miss (the second condition alone, no refusal).
- **N-3, a skip never stands without a fail.** `test_a_schema_skip_warn_never_stands_without_a_schema_fail`, parametrized over 21 bundles: the good bundle (the one fixture bundle), each of the 14 `SCHEMA_POSITIVES` and each of the 6 `TWO_FAULTS` bundles. Every `schema` warn must start with `skipped: `; any warn requires a `schema` fail; the good bundle has no `schema` result at all.
- Near-miss share: the repo test `test_the_bundle_lints_carry_more_near_misses_than_positives_so_far` needs more than half of `schema`'s cases to be near-misses. The two new positives and the `none` near-miss gave 15 of 30, so a fourth row was added (the second condition alone, above): `schema` is now 16 near-misses of 31 (14 positives, 16 near-misses, 1 negative).
- `HANDOFF.md`: the Task 4a entry's fix round 1 clause corrected ("an environment's ladder must be its world's (whatever the gating, round 2)") and a Fix round 2 sentence with the counts appended.

### RED and GREEN

RED, on 7d67f1e's source with only the new tests present (`git status` showed only `tests/test_bundle_lints.py` modified):

```
$ timeout 300 uv run pytest tests/test_bundle_lints.py -q
FAILED tests/test_bundle_lints.py::test_a_bundle_lint_case[schema-12-positive]
FAILED tests/test_bundle_lints.py::test_a_schema_positive_fails_for_its_reason[<lambda>-reasons10]
FAILED tests/test_bundle_lints.py::test_a_schema_positive_fails_for_its_reason[change-reasons11]
FAILED tests/test_bundle_lints.py::test_a_no_gating_environment_naming_a_missing_ladder_fails_schema
FAILED tests/test_bundle_lints.py::test_an_environment_refusal_two_conditions_share_is_reported_once
5 failed, 115 passed, 1 deselected in 46.83s
```

- The `none` ladder row, `reasons10` and the named `none` test fail with "[] == [('config.yaml', \"environment 'mini_triggered': world 'mini' has no ladder 'nope'\")]": `lint_bundle` gave no fail.
- The shared-refusal row (`reasons11`) and the named dedupe test fail with two identical `run --dry-run refuses it: environment 'mini_triggered' ... sets honest: true ...` results (`assert 1 == 2` shape: "where 2 = len([...])").
- An earlier RED run, before the extra near-miss, also showed `test_the_bundle_lints_carry_more_near_misses_than_positives_so_far` failing ("('schema', 15, 30)"); that is the test-count rule, fixed by the fourth row, not a code fault.
- **The skip-invariant test does not fail on 7d67f1e, by construction**: the property already held (the re-review measured 61 bundles). It is a regression pin, so its bite was shown by mutation instead: with a planted `if not out: out.append(_skipped(... 'planted' ...))` after `bad_envs = _environments(...)` (a skip with no fail), `test_a_schema_skip_warn_never_stands_without_a_schema_fail[good]` fails ("skipped: planted (a skip with no fail)"); the source was then restored byte for byte (diff stat unchanged).

GREEN:

- `timeout 300 uv run pytest tests/test_bundle_lints.py -q`: 120 passed, 1 deselected (from 91 passed: +29 = 21 skip-invariant, 4 case rows, 2 reason rows, 2 named tests).
- Gate, in Git Bash with `/c/Users/Brian.Rankin/.local/bin` on PATH:
  - `uv run ruff format --check .`: 335 files already formatted
  - `uv run ruff check .`: All checks passed!
  - `uv run mypy claude_bully`: Success: no issues found in 125 source files
  - `uv run mypy --platform linux claude_bully`: Success: no issues found in 125 source files
  - `uv run pytest -q -W error`: 10159 passed, 10 skipped, 49 deselected in 783.58s (from 10130: +29)
  - `uv run pytest -q -m slow`: 49 passed, 10169 deselected in 161.43s

### Files

- `claude_bully/planner/bundle_lints.py`
- `tests/test_bundle_lints.py`
- `docs/superpowers/specs/2026-11-14-phase-5-director-design.md` (the D-lint_bundle line)
- `HANDOFF.md`

### ASSUMED

- ASSUMED: the skip-invariant test's population is the good bundle, `SCHEMA_POSITIVES` and `TWO_FAULTS`; `tests/fixtures/bundles/` holds only `good` today, so Task 4b's added fixture bundles are not in it yet.
- ASSUMED: the dedupe compares whole messages (`dict.fromkeys`). Two conditions whose refusals differ in any word (a condition name in the message) are both kept.

### Concerns

- None new. The re-review's Nits N-4 (a skip hides a second fault the dry run does not depend on), N-5 (`is_plan_persona` is name-blind) and N-6 (an alone message's "shortest condition" wording) are untouched, as ruled.
