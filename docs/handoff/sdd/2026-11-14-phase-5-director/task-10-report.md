# Task 10 report: `run` on a bundle

## What was implemented

- `claude_bully/planner/bundle.py`: `BUNDLE_WORLDS`, `BundleRefused(ValueError)`, `BundleRun(record, worlds_dir, personas, stamp)` (frozen dataclass), `load_bundle_for_run(root)`, `bundle_worlds_dir(root, worlds_dir)`, `register_plan_personas(personas)`, and `recorded_plan_personas(personas)`. The last is the scoped twin, built on Task 4a's `plan_personas`. Both rest on the private `_new_plan_sheets`, which:
  - calls `ensure_registered()` first;
  - leaves out a name already registered with an equal sheet;
  - refuses a name registered with another sheet, a coded strategy, or a sheet recorded under another name, naming both sources.
- The refusal texts follow the brief:
  - `bundle <slug> is <status>, not runnable: <reason>`. The reason is the first failing `LintRecord` as `<lint_id> <doc_id>: <message>`, else `<n> open block(s)`, else `stage 5 has not run`.
  - "bundle changed since it was validated; run `plan validate` again"
  - `--worlds-dir <given> is not the bundle's worlds directory <root>/worlds; a bundle runs on the worlds it validated`
- The stamp is `PlanStamp(slug, personas={name: sheet dumped}, expected=yaml.safe_load(expected.yaml))`.
- `claude_bully/runner/runner.py`: `run_experiment(..., plan_hash=None, plan=None)`. Right after `ensure_registered()` and the `RunStore`, it:
  1. reads an existing run record;
  2. refuses a mismatched `plan_hash` with `BundleRefused`: `the run's plan_hash <12 hex> is not the bundle's <12 hex>; start a new run`;
  3. runs the old body, now `_run_experiment`, inside `recorded_plan_personas`. The personas are `plan`'s, else the run record's. So registration comes before `expand_cells` (Q50), and it is undone on exit, exceptions included.

  A new `RunRecord` gets `plan_hash` and `plan`. A plain call is unchanged.
- `claude_bully/cli.py`: `run --worlds-dir`. When `plan.json` sits beside the config:
  - `_bundle_for_run` loads the bundle and its worlds directory. A `BundleRefused` becomes `typer.BadParameter` (exit 2). A `DamagedRecordError` prints `error: <message>` and exits 1. Nothing else is caught.
  - `register_plan_personas` runs before `load_experiment` and the `--only` check.
  - The call is `run_experiment(worlds_dir=<the bundle's>, plan_hash=, plan=)`.
  - A resume refusal raised inside `run_experiment` is also a usage error.

  A plain config gets `worlds_dir or DEFAULT_WORLDS_DIR`.
- `claude_bully/analysis/load.py`: `load_run` registers `run.plan.personas` after `ensure_registered()`.
- `claude_bully/analysis/replay.py`:
  - `PLAN_HASH_CHARS = 8`.
  - `render_replay(..., plan_hash=None)` appends `plan hash <8 hex>` after the environment line, or after the header when there is none.
  - `replay_cell` passes `store.read_run().plan_hash` when the store has a `run.json`, else None.
  - `_SHAPES` gains `("plan_hash", ^plan hash (?P<hash>[0-9a-f]{8})$)`.
- Docs-sync:
  - HANDOFF Phase 5 item 12, with the counts.
  - docs/00 section E (a new Task 10 paragraph), section B (`RunRecord.plan` is written by `run`) and section H (the Phase 5 line gains Task 10, version 3, additive).
  - docs/08 "CLI": the `run plans/<slug>/config.yaml` line.
  - The spec's "As planned": a Task 10 block of six lines.

## Tests

`tests/test_bundle_run.py` has 13 cases, 11 of them slow.

The brief's seven, some extended:
- the stamped run and its replay header, plus the A6 world-hash pin;
- analyze with `plans/` removed and the persona popped;
- a resume refused on a hash mismatch;
- the changed and not-runnable refusals;
- the CLI uses the bundle's worlds and stamps. Extended: `--only ferry_*` after the persona is popped.
- an explicit `--worlds-dir` refused unless it is the bundle's;
- `register_plan_personas`. Extended: an equal sheet keeps the same class, and a sheet under another name is refused.

Added:
- `test_a_not_runnable_bundle_names_its_first_failing_check`: the first `fail` lint is named, past a `warn`, as exact text; with no lint, `stage 5 has not run`.
- `test_the_cli_refuses_a_bundle_before_anything_is_written` (Q9): a bundle that is not runnable, or that changed, exits 2 and no runs directory is made. A damaged plan.json prints `error: ...plan.json...`, exits 1, no traceback.
- `test_a_killed_bundle_run_resumes_from_its_record_to_the_unbroken_run[target|bully|generator]` (resume parity):
  - the kill is a `BaseException` raised inside a double, through `dryrun_killing`;
  - the resume is called with no stamp;
  - the registry is clean after the clean run, after the kill and after the resume;
  - the conversations (turns less timestamps and latency), the plan stamp and the hash equal an unbroken run's.
- `test_a_plain_config_takes_the_worlds_dir_and_no_stamp`.

`tests/test_replay_parser.py`:
- `plan hash 0123abcd` in `CASES`, parsed as `plan_hash`;
- five near-misses in the negative list: 7 hex, 9 hex, capitals, the bare form, trailing text;
- `test_the_plan_hash_line_follows_the_environment_line_or_the_header`.

RED:
- Before the code: `tests/test_bundle_run.py` failed at import (`BundleRefused`). `tests/test_replay_parser.py` had 2 failures: the `plan_hash0` case, and the render test with `render_replay() got an unexpected keyword argument 'plan_hash'`.
- Mutant, no fallback to the record's personas (`recorded = plan`): the parity test fails `KeyError: 'ferry_caller'` in `expand_cells` (Q50).
- Mutant, `recorded_plan_personas` registering for the whole process: the parity test fails `assert 'ferry_caller' not in all_strategies()` (the scoped carry).
- Mutant, the CLI without `register_plan_personas` before `--only`: `KeyError: 'ferry_caller'`.
- My own regression, caught by the first full run. `replay_cell` read `run.json` unconditionally, so `tests/test_cli.py::test_replay_writes_utf8_when_stdout_is_cp1252[replay|show]` failed with `FileNotFoundError`. That fixture is a store with cells and no run record. Fixed with a `store.exists()` guard, recorded in "As planned".

GREEN:
- The focused run, `tests/test_bundle_run.py tests/test_replay_parser.py -m "slow or not slow"`, passed: 73 tests before the last additions. Each later test passed on its own.
- After each mutant was restored, its test was run again and passed.

Gate (final code):
- ruff format --check, ruff check, mypy strict, mypy --platform linux: all clean.
- `uv run pytest -q -W error`: 10687 passed, 11 skipped, 203 deselected, 0 warnings. Before: 10678 / 11 / 192; this task adds 9 fast cases and 11 slow ones.
- `uv run pytest -q -m slow`: 203 passed (192 before).
- The fast suite ran twice. The first run gave the 2 failures above (10685 passed). The re-run on the fixed code is the line given here.

## Files changed

- claude_bully/planner/bundle.py, claude_bully/runner/runner.py, claude_bully/cli.py, claude_bully/analysis/load.py, claude_bully/analysis/replay.py
- tests/test_bundle_run.py (new), tests/test_replay_parser.py
- HANDOFF.md, docs/00-RECONCILED.md, docs/08-DIRECTOR.md, docs/superpowers/specs/2026-11-14-phase-5-director-design.md

## ASSUMED

- ASSUMED: the brief's test reads `parsed.shape`, but `ReplayLine` has `kind`. The test reads `parsed.kind`; no alias was added.
- ASSUMED: the carry's "use the scoped plan_personas" governs `run_experiment`. The brief's process-long `register_plan_personas` stays for the CLI and `load_run`, which both need the class after the call returns. `recorded_plan_personas` joins the two, with the same refusals.
- ASSUMED: the resume mismatch is raised as `BundleRefused`, a `ValueError`, so the brief's `pytest.raises(ValueError, match="plan_hash")` holds and `run` prints it as a usage error, not a traceback.
  - A run with no recorded hash prints `(none)`.
  - A call with no `plan_hash` that resumes a bundle run is not refused, and it registers the recorded personas.
- ASSUMED: `_SHAPES` has no environment shape, so `plan_hash` goes first.
- ASSUMED: `register_plan_personas` compares the validated sheet's dump with the registered class's. It also marks what it registers in `_PLAN_CLASSES` (`is_plan_persona`), so a later bundle lint in the same process does not take it for a package strategy.
- ASSUMED: `cli.run` reads the bundle before `load_experiment`, so a refusal needs no config load.

## Carries against tests

- Q48, register before `expand_cells`, scoped, no leaks: the parity test asserts the registry after each run, the kill included. `test_the_cli_run_uses_the_bundles_worlds_and_stamps` asserts `--only` on the bundle persona.
- Preflight Q50: the parity test resumes with `plan=None` after the killed run removed the persona.
- Q9, refuse a bundle that is not runnable, non-zero, before any write: `test_the_cli_refuses_a_bundle_before_anything_is_written`, `test_a_changed_or_not_runnable_bundle_is_refused` and `test_a_not_runnable_bundle_names_its_first_failing_check`.
- Task 9's error contract: the same CLI test covers a damaged plan.json (`error:`, exit 1, no traceback). The CLI catches only `BundleRefused` and `DamagedRecordError`.
- Task 6, filtered strategies: no new code lists `all_strategies()`; `_new_plan_sheets` looks one name up in the registry.
- Pin the plan on the run record: `test_a_run_from_a_bundle_is_stamped_and_replays_its_hash`. The goldens are unchanged: `git status tests/fixtures/golden` is clean.
- Copy every named world (A6): the same test asserts that `world_hashes` are the `hash_tree` of the bundle's copies. The run reads only `<bundle>/worlds`.
- Resume parity: `test_a_killed_bundle_run_resumes_from_its_record_to_the_unbroken_run[target|bully|generator]`.
- Real names: none added. The new messages hold only paths, slugs, hashes and persona names.
- Phase 4 lessons: stub doubles only; no rate-limit path changed; the pyproject `faulthandler_timeout` is untouched.
- Disk and shell writes: see Free disk. Regex lines went through the Edit tool or exact Python string replacements, never a shell redirect to a relative path.

## Free disk

- Before: 2.8 GB free (df). After: 2.96 GB free (`Get-PSDrive C`, 2961432576 bytes).
- Every test run lived under pytest's tmp_path. Only small RED logs were kept, in the scratchpad.

## Concerns

- `run_experiment` now reads `run.json` at its start on every resume, a plain one included. A damaged `run.json` fails slightly earlier than before, with the same error.
- `plan_hash` and `plan` are independent arguments, and a caller passing one without the other is not refused. The CLI always passes both.
- The brief's Step 5 said "As planned: none new". The dispatch asked for the section, so it gained the Task 10 block.

## Fix round 1 (review I1, I2, M1 to M5, N1, N2; base a895a3d)

### What changed

- **I1.** A plan persona registered again under its name with another sheet now replaces the earlier plan persona; only a strategy of the package (or a sheet recorded under another name) is refused (`runner/plan_stamp._new_plan_sheets`).
  - A deeper cause turned up while writing the test: `strategies/composed.make_composed` cached each composition by name (`_WITH_ENVIRONMENT`, the registry for the two-part form). So even with the registry right, a second bundle's run or `load_run` in one process built its environment cells from the first bundle's persona class and sheet.
  - The review's probe R1a measured the registry, not the composition, so it could not see this.
  - A cached composition is now reused only when its environment, premise and pressure classes are the ones given.
- **I2.** `run_experiment` refuses `plan` without `plan_hash` or the reverse (`ValueError: plan and plan_hash go together: ...`).
  - A resume given a stamp is refused with `BundleRefused` when its run records another hash, or another `plan` (`the run's plan is not the one given; ...`).
  - The personas registered on a resume are always the run record's. Every refusal comes before any write.
- **M1.** The early `run.json` read stays, because a resume given no stamp needs the record's personas. docs/00 section E now states that `run --dry-run` on a damaged or older `run.json` fails on it.
- **M2.** `_not_runnable` names the last failed stage as `<stage> failed: <error>`, after the open blocks and before `stage 5 has not run`.
- **M3.** `BundleRefused`, `plan_personas`, `is_plan_persona`, `register_plan_personas` and `recorded_plan_personas` move to the new `claude_bully/runner/plan_stamp.py`, which imports no planner or analysis module.
  - `planner/bundle.py` re-exports the first four, so every existing importer stands.
  - `runner/runner.py`, `analysis/load.py` and `cli.py` import from the new module.
  - No runner module now imports a planner module that imports the runner. The text lints that `runner/env_turn.py` already read (`planner/llm_lint.py`) import no runner module.
- **M4.** The parity test's `_comparable` compares each rep's tool calls, authority calls, trigger records (less the `resume` record), generated documents and world snapshot, each less its wall-clock keys.
- **M5.** docs/00 section B: "a resume needs no `plans/` for its personas, though it runs on the bundle's `worlds/`".
- **N2.** Both resume refusals end `start a new run with another --run-id`.
- **N1.** This is a ledger label (the carries file's "Q48" is preflight Q50), so nothing in the code changes. The report's carry list reads it as Q50.

### Tests (written first, RED on a895a3d)

`tests/test_bundle_run.py`. RED run: 6 failed, 10 passed.

| Test | RED on a895a3d | Now |
| --- | --- | --- |
| `test_two_bundle_runs_sharing_a_persona_name_are_reported_in_one_process` (new, slow) | `ValueError: plan persona 'ferry_caller': ... not the sheet of the registered strategy` | Two bundles, the second's `ferry_caller` with another `win_condition`, re-validated, both run in one process. `readme-results ra rb` exits 0; `load_run` gives A, B, A each its own sheet. The second run's conversations carry B's win condition and not A's. |
| the same test, with only the composition fix reverted | `assert any(win_b in w ...)` fails: B's run spoke A's sheet | |
| `test_a_stamp_goes_with_its_hash_and_a_resume_keeps_its_own` (new, slow) | `DID NOT RAISE ValueError` | `plan` alone and `plan_hash` alone refused with no run directory made. After a kill, `plan=B` with no hash is refused (`ValueError`), and `plan_hash=A, plan=B` is refused (`BundleRefused`). The run directory's bytes are unchanged; a resume given neither runs on the recorded sheet. |
| `test_the_runner_does_not_import_the_planner_side_that_imports_it` (new) | `['runner.py: planner.bundle']`, with a895a3d's `runner.py` | The planner side that imports the runner is computed transitively from the sources. |
| `test_a_not_runnable_bundle_names_its_first_failing_check` (M2) | `- runnable: validate failed: a scan hit` missing | |
| `test_a_resumed_run_is_refused_on_a_hash_mismatch` (N2) | no `--run-id` in the text | |
| `test_register_plan_personas` (I1) | the replace raised | Another plan sheet replaces; `captor` and a sheet under another name are still refused. |
| `test_a_killed_bundle_run_resumes_from_its_record_to_the_unbroken_run[*]` (M4) | | Passes with the wider comparison. |

GREEN:
- `tests/test_bundle_run.py` (16 passed).
- `tests/test_composed.py`, `tests/test_cli.py`, `tests/test_replay_parser.py` and `tests/test_strategy_plumbing.py` (119 passed).
- All under `timeout 300`.

Gate, run once:
- ruff format --check, ruff check and both mypy runs: clean.
- `uv run pytest -q -W error`: 10688 passed, 11 skipped, 205 deselected. That is +1 fast case (the layering test); the brief's register test was reworked in place.
- `uv run pytest -q -m slow`: 205 passed (+2).
- The goldens are unchanged.

### Files changed

- `claude_bully/runner/plan_stamp.py` (new), `claude_bully/planner/bundle.py`, `claude_bully/runner/runner.py`, `claude_bully/analysis/load.py`, `claude_bully/cli.py`, `claude_bully/strategies/composed.py`
- `tests/test_bundle_run.py`
- `HANDOFF.md`, `docs/00-RECONCILED.md`, and the spec's "As planned" (a fix round 1 block, amending section 11's `register_plan_personas` and the section 13 row "Two bundles' personas share a name ...")

### ASSUMED

- ASSUMED: I1's "each run sees its own sheet" includes the run path, so the `make_composed` cache fix is in scope. It is a one-condition change in `strategies/composed.py`, and the gate shows no other effect.
- ASSUMED: the pair rule's misuse is a `ValueError` (a caller defect, with its traceback). A resume given a stamp that does not match is a `BundleRefused` (usage error, exit 2 at the CLI), as the hash refusal already was.
- ASSUMED: the stamp is compared through `model_dump(mode="json")` on both sides, so a value YAML loads as a date compares equal to its JSON string.
- ASSUMED: the layering test forbids only the planner modules that import the runner, directly or through another planner module (`records`, `bundle`, ...). The planner's text lints, which the runner and environments import, stay allowed.

### Free disk

About 2.3 GB free before this round and 2.2 GB after (`df`). Every run lived under pytest's tmp_path.

### Concerns

- `_WITH_ENVIRONMENT` still holds the replaced compositions until the process ends, a few classes each. They are never reused over other parts.
- The early `run.json` read on a dry run (M1) is now documented, not changed.
