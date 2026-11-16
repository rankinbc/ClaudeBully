# Task 10 review: `run` on a bundle (82d7257..a895a3d)

Reviewer scope: task-scoped gate. Read the brief, carries, global constraints, preflight Q48/Q50 (and Q69), the diff once, and code outside the diff only for the named risks. The checkout was left read-only. The suite was not re-run. Every probe ran on stub doubles under a `--basetemp` inside `probes-task10/`, and that temp folder was deleted afterwards (probe folder: 92 KB).

## Verdicts

- **Spec: NOT YET.** Most binding points hold under probe: the refusal comes before any write, the plain goldens are byte-identical, A6 holds, resume parity holds, only the sanctioned exception types are caught, no real model call is made and no real names appear. One binding point fails: "personas are scoped and never leak". The process-long registration in `load_run` (which the brief asks for) leaks a bundle's persona into every later run analyzed in the same process. A real CLI path (`readme-results run_a run_b`) then crashes with a traceback (I1).
- **Quality: NOT YET.** The code is small, readable and well documented. The scoped twin `recorded_plan_personas` is a good design. One Important API hole remains: the stamp's two halves are independent arguments. A caller can record a false stamp, or resume one bundle's run on another bundle's personas without being refused (I2). Five Minors and two Nits follow.

Counts: Critical 0, Important 2, Minor 5, Nit 2.

## Findings

### Important

**I1. A bundle persona registered by `load_run` leaks across runs in one process. A second bundle run that reuses the name with another sheet is refused with a traceback.**
`claude_bully/analysis/load.py:123` (`register_plan_personas(run.plan.personas)`), `claude_bully/planner/bundle.py:662-669` (`_new_plan_sheets` refuses a registered name whose sheet differs).
- `load_run(A)` registers A's `ferry_caller` for the whole process. A later `analyze_run(B)`, `load_run(B)` or `run_experiment(B, plan=B.stamp)` in the same process raises `ValueError: plan persona 'ferry_caller': the plan's recorded sheet is not the sheet of the registered strategy` (probe R1c), where B is a bundle whose `ferry_caller` sheet differs from A's.
- The real CLI reaches this. `claude-bully readme-results ra rb` calls `analyze_run` once per run in one process (`cli.py:293`) and exits 1 with that traceback (probe R1c).
- This is a likely workflow: a slug is edited, re-validated and run again, then both runs are compared.
- The same refusal hits two `cli.run` invocations in one process (probe R1b, exit 1). That case only arises in tests or embedding, so on its own it would be a Nit.
- The carry (Q48 in the carries file: "leaks nothing across cells, tests or processes") is broken here, not in `run_experiment`. `run_experiment` is scoped, and probe R1a shows two bundle runs in one process each seeing their own sheet, with nothing left behind.
- Nothing after `load_run` reads the registry. `analysis/run_analysis.py` uses it only through `load_run`, and no other analysis module calls `get_strategy`, `all_strategies` or `expand_cells`.

Fix, either of:
- (a) Minimal, and keeps the brief's `test_analyze_needs_only_the_run_directory`: in `_new_plan_sheets`, when the registered class `is_plan_persona(registered)`, replace it rather than refuse. Refuse only a coded strategy, or a sheet recorded under another name. Add a test for `analyze_run(A)` then `analyze_run(B)` with the same persona name and different sheets.
- (b) Cleaner: wrap `load_run`'s body in `recorded_plan_personas(...)` so `load_run` registers nothing past its return. Amend the brief test's last assertion; the controller rules on the brief deviation.

**I2. `plan_hash` and `plan` are independent. A caller can record a false stamp, and a resume with `plan` but no `plan_hash` is not refused and runs on the given stamp's personas.**
`claude_bully/runner/runner.py:787-793`.
- `run_experiment(plan_hash=A.hash, plan=B.stamp)` writes a `run.json` with A's hash and B's personas (probe R4).
- `plan=` alone writes a stamp with `plan_hash: null`.
- `plan_hash=` alone with an unregistered persona fails as a bare `KeyError` in `expand_cells` (no run directory is made).
- Worst case: a killed run of A resumed with `plan_hash=None, plan=B.stamp` is not refused, because the hash check needs `plan_hash`. `recorded = plan if plan is not None else existing.plan` then registers B's sheet for the resumed cells, while `run.json` still says A (probe R4: "resumed cells saw B's sheet=True; record still A=True").
- The CLI always passes both halves (`cli.py:300-302`), so the CLI cannot reach this. The API is the contract Task 11's `stub_bundle_run` fixture builds on, and the binding point "RunRecord.plan pins the bundle's identity" should hold at the API.

Fix:
- At the top of `run_experiment`, `if (plan is None) != (plan_hash is None): raise ValueError("plan and plan_hash go together")`.
- On a resume whose `existing.plan` is set, register from `existing.plan`, not from `plan`. Refuse a given `plan` that is not equal to `existing.plan` (`BundleRefused`, the same message shape as the hash refusal).
- Add a test for each.

### Minor

**M1. The early `run.json` read changes what `run --dry-run` does on an existing run directory, and the order of errors on a resume.** `runner/runner.py:787`.
- At base, a dry run returned before `run.json` was read (base `runner.py:803-811`).
- Now a dry run on a directory holding a damaged or older-schema `run.json` raises `JSONDecodeError`, or `ValueError ... schema version 2`, instead of listing the cells (probe R6).
- On a real resume, the same damage now surfaces before a `check_condition` or world-validation error that used to come first.
- No existing test pins either behaviour (grepped `tests/test_store.py`, which reads the store directly, and the `dry_run=True` callers). The report's "fails slightly earlier, with the same error" understates the dry-run change.

Fix: either state it in docs/00 section E, or read `existing` lazily, only when `plan_hash` is given or `plan` is None and the run is not a dry run.

**M2. `_not_runnable` says "stage 5 has not run" for a `failed` plan whose stage failed with an error.** `planner/bundle.py:599-607`.
- A plan whose stage 5 failed on a scan hit or a `BundlePathError` (`director.py:2060`), or whose stage 2 failed, has no failing lint and no open block. The refusal then says "stage 5 has not run", which is false, or at least hides the cause.
- Probe R3 shows this reason for every status written with empty lints. For a real `validated` plan the reason is always a lint or a block (`director.py:2062`), so only `failed` is affected.

Fix: before the fallback, name the last failed `StageRecord` as `<stage> failed: <error>`. The brief's three clauses stay, with one clause added.

**M3. The runner now imports the planner (`runner/runner.py:55`), but the planner already imports `runner.store`.** It works, because the gate passes, but it inverts the layering, and later edits can turn it into an import cycle.

Fix: move `BundleRefused` and the two registration helpers into a neutral module (for example `claude_bully/runner/plan_stamp.py` or `strategies/plan_personas.py`) that both packages import.

**M4. The parity test compares less than it claims.** `tests/test_bundle_run.py:240-256` (`_comparable`) compares only each conversation's status, its turns (less timestamp and latency) and the stamp.
- Probe R5 compared every JSON/JSONL record of the run directory at five more kill points (target@1, target@5, bully@1, bully@4, generator@2).
- The only differences were the established resume record (`{"type": "resume", ...}` in the resumed rep's trigger stream) and, for the generator kill, the dead fire's completed call line kept in the cost ledger (a real run's ledger is untouched by rule).

Fix: extend `_comparable` to the tool, trigger (less `resume` records), generated and world streams, so the test pins what the probe found.

**M5. The docs/00 section B line overstates "so a resume needs no `plans/`".** `docs/00-RECONCILED.md:74`.
- A resume needs no `plans/` for its personas, but an incomplete run still needs `<bundle>/worlds`: the run directory holds per-rep snapshots, not the world.
- Without the bundle, `worlds_dir` has nothing to load and `check_worlds` fails.

Fix: "a resume needs no `plans/` for its personas; it runs on the bundle's `worlds/`".

### Nit

- **N1.** `task-10-carries.md` labels the persona-registration carry "Q48". Preflight Q48 is `plan diff --worlds-dir`, and the registration row is Q50. The implementation covers Q50. The label is the ledger's, not the code's.
- **N2.** The resume-refusal text ends "start a new run". Naming how (`--run-id <new>`) would make it actionable.

## Named risks, answered

1. **Persona scope.**
   - Two bundle runs through `run_experiment` in one process each see their own sheet, and neither leaves a registration behind (R1a).
   - A plain run after a bundle run plus `load_run` in the same process passes the `plain_stub_smoke.json` golden check (`test_plain_stub_run_analysis_is_byte_identical` called on it). Its whole record tree equals a plain run made before the bundle, once wall-clock keys are dropped. `run.json` keeps `"plan": null`, `"plan_hash": null` and the same key order (R1d).
   - `load_run` and `analyze_run(judge=False)` of a bundle run in a fresh process, with `plans/` deleted, register the persona and succeed. `replay` in a fresh process prints `plan hash 70d6c345` after the environment line (R1e).
   - The leak is in `load_run` and the CLI's process-long registration: I1.
2. **A6.**
   - The bundle's `worlds/mini` is a full copy: no shipped file is missing from it.
   - An audit hook on `open` recorded 0 opens of the shipped world (a temp copy standing in for it), of `data/worlds` and of `tests/fixtures/worlds` during the unbroken run, the analysis, the resume and the re-analysis.
   - A run killed at target@3, then resumed after every shipped corpus file and `world.yaml` was edited, equals the unbroken run, apart from the resume record. Its `results.md` is identical, and so is a re-analysis of the unbroken run after the edit (R2).
   - The world is copied into the bundle, covered by `bundle_hash`, and pinned per run by `RunRecord.world_hashes` (`hash_tree` of the copy). A resume after the copy itself is edited is refused at the CLI (`bundle_hash`), and per rep by `check_world`'s `WorldChangedError`.
3. **The refusals.**
   - Each of `planned`, `authored`, `reviewed`, `revised`, `validated` and `failed` exits 2 with or without `--dry-run`, and no runs directory is made (R3). The changed-bundle and damaged-`plan.json` cases are covered by the implementer's test.
   - A resume against another bundle's run exits 2 with "the run's plan_hash 70d6c3458852 is not the bundle's 4a05aa0816be; start a new run". Every byte of the run directory is unchanged.
   - A bundle config aimed at a plain run's id exits 2 with "(none)".
   - **Recommendation: keep `BundleRefused(ValueError)`. Do not make it a `DirectorError`.**
     - `DirectorError` is a Director stage's failure, and the `plan` commands print it with exit 1.
     - `run`'s refusal is an input-level usage error, exit 2, as the brief specifies ("a `BundleRefused` is typer.BadParameter-style output and exit 2").
     - It fits Task 9's contract as the brief's sanctioned third type. The CLI catches it at exactly two sites (`cli.py:307`, `cli.py:335`), and every other exception keeps its traceback.
     - Its home should move out of `planner/` (M3).
4. **The stamp.** Yes: I2.
5. **Resume parity.** Probe R5 killed the run at five points other than the implementer's three and resumed with no stamp. Each matches the unbroken run apart from the resume record and the ledger's kept dead call (M4). Nothing leaked after a kill.
6. **The early `run.json` read.** No existing test changes. Behaviour does change, for a dry run on a damaged or old `run.json` and for error order: M1.

## Probes

Script: `probes-task10/test_t10_probes.py`, run from the repo root:

```
python -m pytest <script> -p tests.conftest -m "slow or not slow" -o faulthandler_timeout=60 --basetemp=<probes-task10/tmp>
```

`no_real_providers` is active. The CLI probes wrap `cli.run_experiment` so the bundle's real config runs on `stubbed_experiment` and `dryrun_provider_factory`. Raw output: `probes-task10/probe_notes.txt`.

| Probe | What | Result |
| --- | --- | --- |
| R1a | two bundle runs (different `ferry_caller` sheets) through `run_experiment`, one process | each saw its own sheet; registry clean after each |
| R1b | the same two through `cli.run`, one process | B exits 1, `ValueError` (I1) |
| R1c | `analyze_run(A)` then `analyze_run(B)`; `run_experiment(B)` after `load_run(A)`; `readme-results ra rb` | all three raise the persona `ValueError` (I1) |
| R1d | plain stub_smoke run after a bundle run plus `load_run` | golden passes; record tree equal to the earlier plain run (wall-clock `ts` aside) |
| R1e | `load_run`, `analyze_run`, `replay` in a fresh process, `plans/` deleted | ok; `plan hash 70d6c345` line placed correctly |
| R2 | A6: audit of shipped-world opens; shipped world edited between kill and resume; re-analysis | 0 shipped opens; equal to unbroken run (resume record aside); `results.md` identical |
| R3 | six non-runnable statuses, with and without `--dry-run`; resume against another bundle; bundle onto a plain run id | all exit 2, nothing written, run dir bytes unchanged |
| R4 | mismatched `plan_hash`/`plan`; `plan` only; `plan_hash` only; resume A with `plan=B` and no hash | false stamp recorded; resume not refused and runs on B's sheet (I2) |
| R5 | parity at target@1, target@5, bully@1, bully@4, generator@2 | equal apart from the resume record and the ledger's dead-call line |
| R6 | `dry_run=True` on a damaged and on a v2 `run.json` | now raises (base: listed the cells) (M1) |

Disk: about 2.3 GB free at the end. Every temp run and bundle was deleted.
