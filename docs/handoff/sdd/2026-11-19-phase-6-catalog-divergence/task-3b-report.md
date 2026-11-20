# Task 3b report: the divergence outputs

Commit: 9d61f9a feat: Phase 6 Task 3b, divergence.jsonl, divergence.json, channels.json, the concealment chart and the calibration form (base ee3d747).

## What was implemented

- `claude_bully/analysis/arms.py` (new): `IGNITION_ARMS`; `arm_of(exp, specs, cell_id)` (pre-flight Q14: the body, so a config with no run is read without a `LoadedRun`); `ignition_arm(loaded, cell_id)` = `arm_of(loaded.experiment, loaded.specs, cell_id)`; `condition_arm`; `arm_labels(loaded, cell_ids)`. First match wins: the environment's `authority.sanctuary.kind`, an idle block whose `permission_line` is not `off`, then `cond.premise` (`captor` with `countdown_in_status: true` in the params its `captor` part receives through `factory.routed_params`, `captor`, `deathbed`, `audience_premise`, `poisoned_well`), else `none`. Never the cell's name. A control takes the arm of the first condition cell by cell id naming it, else its environment's alone (D-control-arm).
- `claude_bully/analysis/divergence.py` (new): the four name constants; `divergence_report` (the shape of the brief, counts only); `write_divergence(loaded, out_dir, *, asked)` (writes `divergence.jsonl` and `divergence.json` when any target turn has reasoning or `asked`, else `[]`); `write_channels`; `concealment_chart`; `reasoning_section`. Every text file through `atomic.write_atomic`. `divergence.json` is `json.dumps(report, indent=1, sort_keys=True)`; each jsonl line is `json.dumps(event.model_dump(mode="json", by_alias=True), sort_keys=True)`.
- `analysis/poisoned_well.py`: each arm's `escape` gains `reasoning_only: {"reps", "turns", "by_form": {"full", "weak"}}` over the arm's kept reps from `loaded.reasoning_events` (turns and per-form counts are distinct turns).
- `analysis/run_analysis.py`: after the Phase 4 block and before `analyze_expected`: `write_channels`, `write_divergence(loaded, out, asked=divergence)`, `concealment_chart` (appended to the chart list); the section passed to `write_results_md(reasoning=)`, only when `divergence.json` was written.
- `analysis/report.py`: `write_results_md(..., reasoning=None)`, placed after the temporal section.
- `scripts/judge_calibration.py`: `write_divergence(loaded, run_dir, per_verdict)`, `score_divergence(form, key)`, `--divergence` (a store_true beside the positional RUN_ID, as `--contradictions` is), `--score` dispatching on `kind: divergence`; both files written atomically; refuses a run with no `divergence.jsonl` naming `analyze <run> --divergence`.
- `metrics/divergence.py` (Task 3a carry 2, three lines): `PASS_SKIPPED_STUB = f"skipped: {SKIPPED_STUB}"`, `PASS_SKIPPED_NO_JUDGE = f"skipped: {SKIPPED_NO_JUDGE}"` from `metrics/ratings.py`. No cycle: `ratings.py` imports nothing of `divergence.py`, and `load.py` already imported both. This file is outside the brief's list; the carry allowed it.

## Privacy (carry 4)

Spec 5.5 puts `reasoning_span` in `divergence.jsonl`; spec 5.7 gives `divergence.json` counts only; spec 6.5 gives `channels.json` counts only. So `divergence.jsonl` is the one analysis file allowed a reasoning span. `tests/test_reasoning_channel.py::test_only_the_divergence_prompt_holds_recorded_reasoning` now: asserts `divergence.jsonl` holds the span (teeth) and not the sentinel (the rest of the reasoning); asserts `divergence.json`, `channels.json`, `results.md` and `concealment_by_arm.png` exist; and asserts every other analysis file, these four included, and the ledger hold neither the span nor the sentinel. The calibration form holds the reasoning by design (spec 5.8, both channels) and is written under `--out`, outside the run.

ASSUMED: `divergence.json` is not excepted, although the brief line names it (`they hold spans of the reasoning by design`). The brief's own shape for that file holds no span, and the spec gives it counts only, so the stricter reading serves the spec.

## Tests

- `tests/test_divergence_analysis.py` (new, 11 tests): all the brief's tests, plus `test_the_reasoning_section_prints_each_condition_and_the_note`. Pre-flight Q10: two plain analyses are byte-equal to each other for all three files; `divergence.jsonl` and `channels.json` are byte-equal to the flagged analysis's; `divergence.json` equals the flagged one's once `note` (`cache_only` against `run`) is set aside. Pre-flight Q37: each half of the stub_run test analyzes into its own `out_dir`. Q14: the ignition test calls `arm_of` on `expand_cells(exp)`, covers every arm of `IGNITION_ARMS`, a condition named `captor_countdown` that is `none`, a Sanctuary winning over a captor premise, auto controls (first naming cell by id) and explicit controls named by none (their environment's arm).
- `tests/test_poisoned_well_analysis.py`: `test_the_chain_numbers_on_three_reps`'s exact `escape` dict gains the zero `reasoning_only`; new `test_a_reasoning_only_escape_is_counted_apart_by_form` (a flagged rep's reasoning escape is not counted; every other `escape` key keeps its value).
- `tests/test_audit_forms.py`: `test_the_divergence_form_is_blind_and_its_key_scores_it` (slow; a module fixture analyzed with `--divergence`; `build_provider` patched to raise in `providers.base` and `run_analysis`) and `test_the_divergence_form_refuses_a_run_with_no_divergence_events`.
- `tests/test_run_analysis.py`: `test_a_plain_analyze_reads_the_cache_and_makes_no_call` now checks the fourth note's file output (carry 1): `divergence.json` `note` `skipped: no judge`, the cached judged count, and the `results.md` section with the note and the chart.

RED (saved in `probes-task3b/red_divergence_analysis.txt` and `red_other_files.txt`): the new test module failed at import (`cannot import name 'divergence' from 'claude_bully.analysis'`, arms.py held aside for the run); the other files: 6 failed, 1 passed (no `write_divergence` in the script, `KeyError: 'reasoning_only'`, the exact escape dict, no `divergence.jsonl`, no `divergence.json`).

GREEN: `uv run pytest tests/test_divergence_analysis.py tests/test_poisoned_well_analysis.py tests/test_audit_forms.py tests/test_run_analysis.py tests/test_hypotheses.py tests/test_reasoning_channel.py tests/test_divergence.py -q -m "slow or not slow" -n 8`: 210 passed.

Measured times (`--durations`): `test_a_run_without_reasoning_writes_no_divergence_file_unless_asked` 6.15 s; the `judged_run` module fixture about 3.6 s setup; `test_a_second_plain_analysis_writes_the_same_bytes` 2.38 s. Every test on `judged_run`, `stub_run` or `divergence_judged` is marked slow. The fast new tests take under a second each (the refusal test shares the existing module fixture `idle_run`).

## Gate (each saved in probes-task3b/gate_*.txt)

- `uv run ruff format --check .`: 414 files already formatted, exit 0
- `uv run ruff check .`: All checks passed, exit 0
- `uv run mypy claude_bully`: no issues in 134 source files, exit 0
- `uv run mypy --platform linux claude_bully`: no issues in 134 source files, exit 0
- `uv run pytest -q -W error -n 8`: 10965 passed, 11 skipped (from 10960: 5 fast tests), exit 0
- `uv run pytest -q -m slow -n 8`: 243 passed (from 235: 8 slow tests), exit 0

After the fast run, six edited files were found with CRLF endings (written by a patch script) and turned back into LF; `ruff format --check` and `ruff check` were run again and passed. No other change was made between the gate and the commit except the docs-sync, after which `tests/test_boundary.py`, `tests/test_records.py` and `tests/test_guardrails.py` (which read docs) were run: 83 passed.

## Files changed

claude_bully/analysis/arms.py (new), claude_bully/analysis/divergence.py (new), claude_bully/analysis/poisoned_well.py, claude_bully/analysis/run_analysis.py, claude_bully/analysis/report.py, claude_bully/metrics/divergence.py, scripts/judge_calibration.py, tests/test_divergence_analysis.py (new), tests/test_poisoned_well_analysis.py, tests/test_audit_forms.py, tests/test_run_analysis.py, tests/test_reasoning_channel.py, HANDOFF.md, docs/00-RECONCILED.md (B rows, E line, H), docs/10-ROUND-TWO.md (Part 2 "Outputs"), docs/07-POISONED-WELL.md, the spec (5.7's note list marked "[refined in Task 3a's review]"; As planned: D-arms, D-divergence-files).

## ASSUMED

- ASSUMED: `divergence.json` holds no span and is not excepted in the privacy test (above).
- ASSUMED: `hedge_decomposition` and `distress_by_depth` read the condition cells alone (no controls), as the register's items 3 and 10 do (`_environment_cells`); the `models` rows include controls as the brief says. Each model with a kept condition conversation gets a `hedge_decomposition` entry, zeros included, so the register always has numbers to read.
- ASSUMED: `by_kind` counts every turn's non-None kind (so `redacted`, which carries no text, is counted on a `reasoning_absent` turn); `with_reasoning` is the turns not `reasoning_absent`.
- ASSUMED: a hedged `premise_concession` is one whose `Event.hedged` or `attrs["hedged"]` is true (no detector sets either today).
- ASSUMED: `channels.json` rows come from every cell's kept reps, controls included and keyed by their condition name, as in `divergence.json`; a condition whose every rep was flagged has an empty row.
- ASSUMED: the chart draws a bar for every condition of a drawn model, ordered by condition name, and writes `n/a` (no bar) for a condition with no judged turn. The footnote reads `<reps> reps, <turns> turns; reasoning_absent share <0.00>` over every row, then the `values_loosened` note.
- ASSUMED: the `results.md` section prints a line per model (the model in backticks) and under it the brief's line per condition, then `Divergence pass: <note>.`; `<by_kind>` lists the non-zero kinds (`no kind` if none).
- ASSUMED: the calibration CLI takes `--divergence` as a flag beside the positional RUN_ID, as `--contradictions` does. The key holds the conversation and turn as well as the class and confidence, as the contradictions key does. Items are in the jsonl order, and `--per-verdict N` keeps the first N per judged class.
- ASSUMED: `divergence_report` defaults `note` to `cache_only` when no pass note is set (a `LoadedRun` built outside `analyze_run`).

## Self-review

- The brief is implemented in full, with nothing extra beyond the one section test and carry 2's three lines.
- No reasoning reaches a forbidden reader. The new readers of `Turn.reasoning_text` are only the calibration form, by design and outside the run. `channels.json`, `divergence.json` and the chart hold counts and labels only.
- On a run with no reasoning and no flag, `analysis/` gains no file and `results.md` is unchanged. The plain goldens are unchanged (the fast suite passes). The one change to a pre-existing output is the brief's additive `escape.reasoning_only` in `poisoned_well.json`.
- `SCHEMA_VERSION` is unchanged and no record was touched.
- Every new text file is written atomically.
- No order-dependent test: the `stub_run` halves and the plain re-analyses write to their own `out_dir`, and `judged_run`'s `analysis/` is never rewritten in place.

## Concerns

- `analysis/divergence.py` imports `progression._LAYER_DEPTH`, a private name; the brief names the scale. Ruff does not flag it.
- I read three lines of the plan file by grep (the D-arms, D-control-arm and D-divergence-files rulings) to word the spec's As planned lines. I did not read the plan whole.

## Fix round 1

Commit: 8cc7e88, a new commit on top of 9d61f9a (no amend). Findings from the review: 0 Critical, 1 Important, 7 Minor.

- I1: added `test_the_hedge_decomposition_and_the_distress_by_depth_count_hand_set_records` (slow, in-memory edits of `judged_run`). It sets these records on CELL's four target turns:
  - a concealed skepticism at depth 0;
  - a concealed distress on the turn a seam document is found, with a `self_uncertainty` trigger;
  - an aligned verdict after a surface find, so the depth stays 2, with a `world_question` trigger, which is no hedge;
  - an unjudged turn carrying a hedged `premise_concession` (`Event.hedged`);
  - on the control, a hedge and a distress verdict, which must be left out.

  It asserts the exact dicts: `hedge_decomposition == {model: {hedge_turns 2, judged 1, concealed_distress 1, rest 0}}` and `distress_by_depth == {model: {"0": {1, 0, 0.0}, "2": {2, 1, 0.5}}}`. It also checks that `attrs["hedged"]` counts the same as the field. With nothing judged, it asserts `distress_by_depth == {model: {}}` (a depth with no judged turn is left out, never a 0 share), and that hedge turns are still counted with judged 0.

  Mutations, run in process (the review's script with this test added, `probes-task3b/fix1_mutate_hedge_depth.py`, output in `fix1_mutate_hedge_depth.txt`):
  - none: 3 passed;
  - no_hedges: 1 failed, exit 1;
  - depth_zero: 1 failed, exit 1;
  - no_distress: 1 failed, exit 1.
- M1: I checked spec 5.x. 5.5 lists `reasoning_span`, `reply_span` and `rationale` on `DivergenceEvent` in `analysis/divergence.jsonl`, and D-span keeps an aligned verdict's spans as given. No sentence forbids either, so I reworded rather than stopping. The `analysis/divergence.py` module docstring, the docs/10 "Outputs" paragraph and the docs/00 B row now say that each line holds the spans of every verdict that has them (any class, `aligned` included) and the judge's free-text `rationale`, either of which may quote the reasoning. "Only" and "never the rest" are gone. The privacy test's comment says its sentinel check holds because the double's rationale is fixed text.
- M2: `analyze_run` builds `divergence_report(loaded)` once and passes it to `write_divergence(..., report=)`, `reasoning_section` and `concealment_chart(loaded, out, report)`. The chart reads the report's rows, plus `_first_cells` (cells and specs only, no event pass) for the bar labels. Both functions still build the report themselves when called without one.
- M3: `progression._LAYER_DEPTH` is now `progression.LAYER_DEPTH`. There is one definition; its three local uses and `divergence.py` import it.
- M4: every output now describes the latest analysis.
  - `write_divergence` removes `divergence.json` and then `divergence.jsonl` when it does not write them.
  - `concealment_chart` removes the chart when no turn is judged.
  - Removal is `Path.unlink(missing_ok=True)`, the same path Phase 5 uses for `expected.json` (`analyze_expected`). Each removal is one step, so a kill between two leaves files that the next analysis removes again.
  - `channels.json` rule: it is written when any conversation of the run has reasoning. That is a property of the run's records, and a run with reasoning keeps it, so staleness cannot come from a re-analysis of the same run. It can only come from an `out_dir` that once held another analysis. `write_channels` now also removes the file when it does not write it, so the same guarantee holds there too.
  - Test: `test_a_plain_reanalysis_removes_what_a_flagged_one_left` (slow, about 12 s). A flagged analysis of the no-reasoning `stub_run` into `out/` writes the files; a stray chart and `channels.json` are planted. A plain analysis with `--hypotheses` into `out/` then leaves none of the five files, `results.md` has no section and no chart, and `hypotheses.json` is byte-equal to one from a directory never analysed with the flag. A stray `divergence.jsonl` (the kill-between-removals state) is removed by the next analysis.
  - The spec's "As planned" section gains one M4 line.
- M5: added `arms.ArmConfigError(ValueError)`. A present but broken config now raises it, naming the cell and the key:
  - an environment named but not defined: `cell '<id>': key 'environment' ('<name>') ...`;
  - params `routed_params` cannot route: `key 'params'`;
  - a `countdown_in_status` that is not a boolean: `key 'countdown_in_status'`.

  `none` or `captor` comes back only for the documented absences: no environment, or no countdown set. A control reports the condition cell it reads. Test: `test_a_broken_config_raises_naming_the_cell_and_the_key` (fast) covers the three raises, a control's raise, and three absences that give an arm.
- M6: in `tests/test_reasoning_channel.py` the jsonl path is now `events_file` (and `held` for its bytes), so `events` keeps holding the pass's events.
- M7: docs/10 now says `by_kind` counts every turn's recorded kind, `redacted` included on `reasoning_absent` turns, so it can sum past `with_reasoning`.

RED: I1 was a gap in the tests, not the code. Its teeth are the three mutations above, each of which fails the new test. The M4 and M5 tests were written against the new behavior; under 9d61f9a the M4 test's file checks would fail (the files were left in place) and the M5 test cannot import `ArmConfigError`.

Line endings: `git ls-files --eol` on every changed file shows `i/lf w/lf` (`probes-task3b/fix1_eol.txt`).

Gate after the last edit (the docs included), each step on its own (`probes-task3b/fix1_gate_*.txt`):
- `uv run ruff format --check .`: 414 files already formatted, exit 0
- `uv run ruff check .`: all checks passed, exit 0
- `uv run mypy claude_bully`: no issues found in 134 source files, exit 0
- `uv run mypy --platform linux claude_bully`: no issues found in 134 source files, exit 0
- `uv run pytest -q -W error -n 8`: 10966 passed, 11 skipped (from 10965: 1 fast test), exit 0
- `uv run pytest -q -m slow -n 8`: 245 passed (from 243: 2 slow tests), exit 0

Files: claude_bully/analysis/arms.py, divergence.py, progression.py, run_analysis.py; tests/test_divergence_analysis.py, tests/test_reasoning_channel.py; docs/00-RECONCILED.md, docs/10-ROUND-TWO.md, the spec, HANDOFF.md. No test outside the brief's list was changed.

ASSUMED: `write_channels` also removes a stale `channels.json`. The ruling left it to its own rule, and doing this makes that rule match the others.

ASSUMED: `ArmConfigError` subclasses `ValueError`, so any caller that already catches `ValueError` (the load paths) behaves as before.

Concern: `ignition_arm` on a loaded run now raises where it used to say `none`. Every run that reached `analyze` passed `check_condition` at run time, and the gate shows no case. A hand-edited `run.json` with a dangling environment would now stop the divergence report with a named error.
