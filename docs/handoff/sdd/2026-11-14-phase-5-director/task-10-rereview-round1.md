# Task 10 re-review, fix round 1 (a895a3d..cb2731f)

Scope: the findings of task-10-review.md (I1, I2, M1 to M5, N1, N2) and the fix diff `review-a895a3d..cb2731f.diff`, read once. The checkout was left read-only and the tree is clean. Probes are in `probes-task10-rereview/` (`test_t10_rereview.py`, raw output in `probe_notes.txt`). Each probe ran on stub doubles under a `--basetemp` inside that folder, and the temp folders were deleted afterwards (the folder is now 68 KB; disk is about 2.2 GB free).

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| I1 | FIXED | P1, P5, and `tests/test_bundle_run.py` green |
| I2 | FIXED | P2 |
| M1 | FIXED (documented) | docs/00 section E states the dry-run change; the reviewer offered this option |
| M2 | FIXED | P4 and the fixer's test |
| M3 | FIXED | fresh-process imports and the layering test (one Nit below) |
| M4 | FIXED | `_comparable` now compares turns, tools, authority, triggers less `resume`, generated and the world record |
| M5 | FIXED | docs/00 section B: "needs no `plans/` for its personas, though it runs on the bundle's `worlds/`" |
| N1 | ACCEPTED, no code change | the label belongs to the ledger, and the report reads it as Q50 |
| N2 | FIXED | both refusals end `start a new run with another --run-id`, and the test asserts `--run-id` |

New findings: Critical 0, Important 0, Minor 0, Nit 3.

## 1. I1: the persona registry and the composition cache

**Does the cache key on the sheet?** Yes, in effect.

- `make_composed` now reuses an entry only when `environment_cls`, `premise_cls` and `pressure_cls` are the same class objects (`is`).
- A plan persona's class is built new on every registration. `make_phased_premise` calls `type(...)` each time, and `_apply_sheet` sets the sheet only on that new class. Nothing caches persona classes by name: `cached_persona_sheets` caches the shipped sheets only.
- So a different sheet always means a different `premise_cls`, and the cached composition is rebuilt.
- Equal sheets reuse the registered class, because `_new_plan_sheets` compares `model_dump(mode="json")`. That is correct.
- The cache holds strong references to its classes, so an `id` cannot be reused while an entry is live.
- `env:<world>` is cached by world name, but it holds only the name. The world is loaded from `worlds_dir` at run time.

**Probe P1.** Two bundles A and B have the same `ferry_caller` name, the same environment and conditions, and the same `win_condition`. Only the sheet text differs: one backstory sentence and the first fallback line. All of it ran in one process with no outside registration (the scoped path). The test spies on the bully double's `system` and messages.

| Step | Result |
| --- | --- |
| Run A, run B, run A again | Each bully saw only its own backstory marker (52 calls each). Nothing was registered after A. |
| `load_run(A)` (process-long registration), then run B, then run A | B saw MARKB and A saw MARKA. |
| `load_run` of A, B, A2, B2, A3, B in turn | Each run loaded its own backstory and its own fallback line. |
| `readme-results ra rb` and `readme-results rb ra`, from a registry with `ferry_caller` popped | Both exit 0. `load_run` afterwards gives A, B, A, each with its own sheet. |
| `_WITH_ENVIRONMENT` | Holds a single `env:mini+ferry_caller` entry, overwritten in place, so old compositions are not kept. The fixer's concern that they "still hold" overstates it. |

The cache cannot serve the wrong sheet on any path tried.

**Probe P1b (Nit, pre-existing).** A composition with no environment (premise plus pressure, `ferry_caller+polite_control`) is put in `_REGISTRY` under its composed name. It outlives the scoped `plan_personas` block. A later composition over another sheet is rebuilt correctly (`c2 is not c1`, with B's sheet), so no wrong sheet is served. The stale entry stays in the registry. `listed_strategies` filters out `Composed`, and the bundle config uses environment conditions only.

## 2. I2

The check now sits at the top of `run_experiment`, before `ensure_registered()` and the store. On a resume, `recorded = existing.plan`.

**Probe P2:**

- `plan` alone, and `plan_hash` alone, on a new run: each raises `ValueError: plan and plan_hash go together ...`. No runs directory is made.
- After a run of A is killed (target@3), five refusals were tried. In every case the run directory is byte-identical and the `ferry_caller` registration is unchanged:

| Case | Refusal |
| --- | --- |
| `plan=B` alone | `ValueError` |
| `plan_hash=A, plan=B` | `BundleRefused: the run's plan is not the one given; ...` |
| `plan_hash=B, plan=B` | `BundleRefused: the run's plan_hash 9c64f2c485ef is not the bundle's 2cd50981c5c0; ...` |
| `plan_hash=A`, A's stamp with `expected` changed | `BundleRefused` (plan) |
| `plan_hash=A, plan=B` with `dry_run=True` | `BundleRefused` (plan), before the dry run |

- **A resume keeps its own stamp.**
  - A resume given neither half: the bully saw A's sheet only, and `run.json` is byte-identical. `_run_experiment` reads an existing record and never rewrites it.
  - A resume given A's own stamp: the same result.
  - Each resumed run equals an unbroken run except for `rep0.triggers.jsonl`. The only difference there is the `{"type":"resume",...}` line.
- A plain run's id resumed with a stamp is refused (`plan_hash (none) ...`), and its bytes are unchanged.

## 3. runner/plan_stamp.py and the re-exports

- `plan_stamp.py` imports only `strategies.base`, `strategies.bootstrap`, `strategies.premises.phased` and `strategies.sheets`.
- I imported each of these modules in its own fresh `python -I`: `runner.plan_stamp`, `runner.runner`, `planner.bundle`, `analysis.load`, `cli`, `strategies.composed` and `planner.records`. Each import succeeded, so there is no cycle.
- `import claude_bully.runner.plan_stamp` loads no planner or analysis module.
- `import claude_bully.runner.runner` loads only `planner.lints`, `planner.llm_lint` and `planner.second_person`, through `env_turn` and `environments`. None of them imports the runner.
- `planner/bundle.py` re-exports `BundleRefused`, `is_plan_persona`, `plan_personas` and `register_plan_personas`. No importer uses `recorded_plan_personas` from the planner.
- `test_the_runner_does_not_import_the_planner_side_that_imports_it` passes, and the layering holds.
- Nit: the test's regex (`(from|import) claude_bully\.(\w+)\.(\w+)`) misses the form `from claude_bully.planner import bundle`. No such line exists today.

## 4. The minors and nits

- **M2.** `_not_runnable` names the last failed stage after the lints and the open blocks. P4: `... is failed, not runnable: author failed: author broke`.
  - Nit: a hand-edited failed stage with `error: null` reads `validate failed: None`. `Director._fail` always sets the error, so only a hand edit reaches this.
- **M4.** I read the diff. The ledger is still left out, as the review found it should be (a dead call's line is kept by rule).
- **M1, M5, N1, N2.** As in the table above.

## 5. Plain goldens after a bundle run

Probe P5 ran these steps in one process:

1. A plain `stub_smoke` run and a plain environment run (`env_experiment`, mini).
2. Bundle runs of A and B, then `load_run` of each.
3. The same two plain runs again.

Results:

- `test_plain_stub_run_analysis_is_byte_identical` passes on the second plain run.
- The plain run's whole record tree, and the plain environment run's, each equal the run made before the bundles, with the wall-clock keys and `state/` left out.
- `run.json` keeps `"plan": null` and `"plan_hash": null`.
- `tests/test_bundle_run.py`, `tests/test_composed.py` and `tests/test_env_events.py` pass, slow tests included (68 passed).

## Probes

```
python -m pytest probes-task10-rereview/test_t10_rereview.py -p tests.conftest -m "slow or not slow" -o faulthandler_timeout=60 --basetemp=<probes-task10-rereview/tmp>
```

5 passed (P1, P1b, P2, P4, P5).
