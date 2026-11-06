# Task 8 report: generator arms, progression metrics, the reflexive config

Commit: 4512a83 on build/v1 (one commit on top of 70864b5), authored by rankinbc1@gmail.com. Not pushed.
Status: DONE_WITH_CONCERNS (concerns listed at the end; none block).

## What was built

- `claude_bully/analysis/load.py`: `LoadedRun.generated: dict[ConvKey, list[GeneratedDoc]]`, read in `load_run` after `_environment_context` (empty for a plain conversation). Brief code verbatim.
- `claude_bully/analysis/progression.py`: `ProgressionSummary.generated_docs_found` / `own_quote_found_turn` / `quote_latency`, `generator_progress(...)`, and `summarize` wiring (items from the `HarvestItem` records). Brief code verbatim; module docstring definitions and `__all__` extended.
- `claude_bully/analysis/generator.py`: complete, verbatim from the brief (`GENERATOR_FILE`, `GENERATOR_CHART`, `ARMS`, `LEFT_OUT_OF`, `generator_arm`, `ArmRates`, `arm_rates`, `write_generator`, `generator_chart`). `ruff format` only rewrapped the two long `ax.bar` lines.
- `claude_bully/analysis/run_analysis.py`: chart appended when returned, `write_generator` always called, after the Phase 2 block.
- `configs/environments/generator_reflexive.yaml`: verbatim from the brief.
- Fixtures: four `reflexive_quote_noticed` items from generated documents appended to `tests/fixtures/responses/environment.yaml` (suspicious, confirming, two near-misses), verbatim.
- Tests: `tests/test_generator_analysis.py` (brief, verbatim except the stub script name, see deviation 1), one assertion block in `tests/test_progression.py`, plus additions to `tests/test_generator_run.py` (deviation 2).
- Docs sync: see below.

## Deviations from the brief

1. **New stub script `tests/fixtures/stub_scripts/overlay_generator_rules.yaml`; the slow test points at it instead of `overlay_target_rules.yaml`.** The brief's slow test, transcribed verbatim, failed: `rates[model]["reflexive"].docs_written >= 1.0` gave 0.0. Cause (traced with a probe run, not a transcription error): the generator fires only on a `generate: true` rung (`buried_opens`, `the_truth`) or periodically, and a periodic fire needs an eligible harvest item. `overlay_target_rules.yaml` never says anything the heuristic harvest holds, so the run has no `HARVEST` lines and no fire in any arm. The new script is a copy with one change: the first reply carries "I'm a language model, I don't have a body." as its middle sentence. It sits after the service sentence because "describes" in the next sentence reads as a report frame and blocks the item (`_next_reports`), and before the question (the second rule matches on the question). With it, first_crumb opens on target turn 1 (seam open), the harvest holds `h-1-1`, and the periodic fire writes one seam document on target turn 5 in both generator arms and none in the off arm. The shared `overlay_target_rules.yaml` is untouched (other tests use it).
2. **Run-level tests added to `tests/test_generator_run.py`** (not in the brief's file list): three assertions on the first test (`generated_docs_found == {seam: 1, buried: 1}`, `own_quote_found_turn == 5`, `quote_latency == 1`), and three new tests. See "Task 7 m1" below.
3. **Docs edits slightly beyond the brief's list:** the "Generator on/off" row of the experiments table in `docs/02-ENVIRONMENTS.md` now names the three arms and the config; the progression-summary note in `docs/00-RECONCILED.md` sits beside the existing "RunSummary gains ..." paragraph at the end of section B, since that is where the sibling per-conversation summary fields are described (section C holds the event note).
4. No change to any brief code block otherwise.

## Carries

- **Task 7 final state / record shapes:** read `generator.py`, `env_turn.py`, `store.py`, `records_env.py` at HEAD before writing. The analysis reads `GeneratedDoc` (`reflexive` is `plan.reflexive and bool(used)`, so a doc is reflexive only when it used items), `Discovery`, `HarvestItem`; nothing the brief's code assumed was off.
- **Task 4 coinage:** no metric counts items by kind; nothing to adjust.
- **P12:** `generator_arm` and the config are mine and done; `GeneratorConfig.reflexive` used as landed.
- **Stub-chart lesson:** the slow test checks wiring, labels, file existence, doc counts per arm (off 0, reflexive and non-reflexive equal and at least 1), not the chart's shape. I looked at the stub chart: all rates are 0 so the bars are empty; panel title is the target model string, legend and tick labels are the brief's.
- **Task 7 m1:** my analysis does not consume `GeneratorFire.status` or `DocPlan.harvest_degraded` (it counts committed `GeneratedDoc` records), so the carry did not require a fixture. I closed the analysis-path gap anyway with run-level tests on real records: `test_a_writer_error_is_a_fire_with_no_documents_and_the_arm_reads_it` (status `error`, error text, 0 documents), `test_a_fire_over_the_cap_is_rejected_and_the_arm_reads_it` (`max_docs: 1`, status `rejected`, rejection `cap`), `test_a_degraded_harvest_is_marked_on_the_plans_and_the_arm_reads_the_run` (judge raising `ProviderError` on the first harvest; every plan carries `harvest_degraded == [1]`). Each then runs `arm_rates` and `write_generator` over the real run. So the cap, writer error and degraded harvest now each have a run-level test. These tests exercise code that already existed when written (the analysis was in place), so they had no RED phase.
- **Shared fixtures:** reused `GeneratorFactory`, `GeneratorStub`, `HarvestJudge`; no hand-built records beyond the brief's `_doc`/`HarvestItem` unit test for `generator_progress`.
- **Environment:** uv PATH export from the carries used; scratch files under the named scratchpad `impl-task8\` folder (probe script and its output); nothing else in the scratchpad read.
- **Docs sync:** done, below.
- **Commit:** one commit, author rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` as the carries name. Note: the harness attribution reminder in this session names the model as Sonnet 5.5; I followed the carries. Amend the trailer if you want it to name the model that actually ran.

## RED evidence

- Fixtures appended and tests written first. `uv run pytest tests/test_generator_analysis.py tests/test_env_events.py tests/test_progression.py -q -x`: collection error `ModuleNotFoundError: No module named 'claude_bully.analysis.generator'` (the expected failure).
- `tests/test_env_events.py` alone: 28 passed (the new environment.yaml items pass, as the brief says).
- `tests/test_progression.py` alone: `FAILED test_progression_of_the_scripted_environment_run` with `AttributeError: 'ProgressionSummary' object has no attribute 'generated_docs_found'`, 26 others passed.
- After the brief's code: `tests/test_generator_analysis.py tests/test_env_events.py tests/test_progression.py tests/test_run_analysis.py`: 64 passed, 1 deselected. The slow test then failed once (`assert 0.0 >= 1.0`, deviation 1), and passed after the new stub script.

## Gate (final tree; the only later change is the HANDOFF count line)

- `uv run ruff format --check .`: `250 files already formatted`
- `uv run ruff check .`: `All checks passed!`
- `uv run mypy claude_bully`: `Success: no issues found in 103 source files`
- `uv run pytest -q -W error`: `8128 passed, 5 skipped, 6 deselected in 410.75s (0:06:50)` (base 8113 passed, 5 deselected: +15 passed, +1 deselected)
- `uv run pytest -q -m slow`: `6 passed, 8133 deselected in 102.81s` (base 5)

## Docs-sync edits

- `docs/00-RECONCILED.md`: section B (after the "RunSummary gains ..." paragraph), the three new progression fields and how they are computed; section C, `reflexive_quote_noticed` now lists the generated-document fixtures (suspicious, confirming, two near-misses; detector unchanged); section I, Phase 3 row gains the measurement layer (`LoadedRun.generated`, the three fields, `analysis/generator.py`, `generator.json`, `generator_arms.png`, the config).
- `docs/06-HYPOTHESES.md`, hypothesis 6: "Tested by" names `generator_reflexive.yaml`, the three arms (the non-reflexive one separates being quoted from a bigger world) and `generator_arms.png`.
- `docs/02-ENVIRONMENTS.md`: "Metrics and events" progression paragraph gains the three metrics and the `generator.json` / chart description; the "Generator on/off" experiment row names the three arms and the config.
- `HANDOFF.md`: last-updated line (Task 8 complete, Task 9 next); Progress item 8; test counts 8128 / 5 / 6 and 6 slow; Next steps start at Task 9; a Phase 7 open item (first real run of the arms: check the generator role with `doctor --live`; stub data says nothing about the arms; read `generator_fire` records when `docs_written` is low); the resume prompt names Task 9.

## Concerns and observations

- `generator.json` (schema fixed by the brief) reports mean documents written but not fires that were rejected or errored, so a reflexive arm degraded by writer failures reads like a quieter arm. Noted in HANDOFF for Phase 7; I did not add keys.
- `docs/06` hypothesis 6's prediction text says `self_recognition_noticed`, while its metric column and section G7 say `reflexive_quote_noticed` (a different event). Pre-existing mismatch, left alone.
- The config names the generator model `haiku` (verbatim from the brief), as existing configs name `sonnet` for bully and judge. It is a config model string, not data under the real-name scans.
- `global-constraints.md` still says the trailer is Opus 5.5 (stale against the carries and HANDOFF).

## Fix round 1 (commit 24b9a25, on 4512a83)

Authored by rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, not pushed. The commit also carries the HANDOFF fast-suite count (8128 to 8132) and the m5 comment rewrap below.

### What changed

- **I1 (labels, footnote, results.md, generator.json).** `tests/test_generator_analysis.py` now runs the config once per module (`generator_run` fixture: stub run, four-turn budget, two reps a cell) and adds fast tests that read the drawn figure and the written JSON, following `tests/test_phase2_charts.py` (`figures` fixture keeps figures open, `_texts`):
  - `test_the_chart_is_labelled_and_draws_the_arm_rates`: tick labels `off`, `non-reflexive`, `reflexive`; legend texts `belief adoption`, `reflexive quote noticed`; panel title (the model string) and y label; the suptitle; the six bar heights against rates computed from injected events (a confirming quote in one reflexive rep, a suspicious one in one non-reflexive rep: `[0, 0, 0.5, 0, 0.5, 0.5]`); no footnote text when nothing is left out.
  - `test_the_chart_footnote_and_the_json_count_the_flagged_reps`: one rep flagged `values_loosened`; the chart carries `1 rep flagged values_loosened, left out of the generator arms`, and `generator.json` has `values_loosened_left_out == 1`, the same note, and the reflexive arm's `reps` down to 1.
  - `test_generator_json_holds_the_rates_the_metrics_and_the_resumed_counts`: top-level keys in order, the three arms in `ARMS` order, the five rate keys per arm, reps, documents written (cross-checked against each rep's own generated records), adoption and quote-noticed rates, `own_quote_found_rate` 0.5 after one injected `Discovery` of the reflexive seam document, `resumed_after_dead_attempt` per cell (one injected `ResumeRecord`), and the three progression metrics from `summarize_progression` for that rep (`{seam: 1}`, 7, 3: target turns 3, 5, 7 after the quoted item at turn 1) and the defaults for every other rep.
  - The slow test now uses the fixture, runs `analyze_run` into a temp dir, and asserts the `](generator_arms.png)` line in `results.md` and the arms in the written `generator.json`.
  - `_reflexive_arm` in `tests/test_generator_run.py` now reads `generator.json` back and asserts it holds the same reflexive rates, with `values_loosened_left_out == 0` and `note` None.
- **m2.** `generator_chart` returns None when no environment runs the generator (the `_runs_generator` guard `write_generator` has); docstring updated. `test_a_run_without_the_generator_draws_no_chart_and_writes_no_json` monkeypatches `arm_rates` to raise on a non-generator run (`stub_env_arms_run`), so it pins that the arms are never computed; it also asserts no file is written.
- **m3.** `generator.json` and `generator_arms.png` are asserted absent in `test_analyze_writes_the_progression_charts_and_summaries` (`tests/test_progression.py`) and, per config, in the Phase 2 slow test `test_stub_runs_draw_each_headline_chart` (`tests/test_phase2_charts.py`).
- **m4.** The slow test asserts, per rep, that the off arm wrote nothing, every non-reflexive document has `reflexive` false and no `used_items`, and every reflexive document has `reflexive` true and `used_items`.
- **m7.** `_reflexive_arm` is annotated `-> tuple[ArmRates, ProgressionSummary]` and its docstring names both.
- **m5 (not asked, trivial).** The header of `tests/fixtures/stub_scripts/overlay_generator_rules.yaml` is rewrapped; its spliced overlong line is gone.

### RED evidence

New tests first (before the guard): `uv run pytest tests/test_generator_analysis.py -q -W error` gave `1 failed, 7 passed, 1 deselected`; the failure was `test_a_run_without_the_generator_draws_no_chart_and_writes_no_json` with `AssertionError: a run with no generator never computes the arms` raised from `generator.py:136` (`generator_chart` calling `arm_rates`). The other new tests exercise existing behaviour and passed on first run. To check the label tests bite, I temporarily changed the legend label to `quote noticed`: `test_the_chart_is_labelled_and_draws_the_arm_rates` failed with `At index 1 diff: 'quote noticed' != 'reflexive quote noticed'`; the file was restored (the diff of `generator.py` is the guard only).

### Commands and outputs

- `uv run pytest tests/test_generator_analysis.py tests/test_generator_run.py tests/test_run_analysis.py tests/test_progression.py tests/test_phase2_charts.py -q -W error`: `77 passed, 2 deselected in 44.39s`
- `uv run pytest -q -m slow`: `6 passed, 8137 deselected in 98.46s (0:01:38)`
- `uv run ruff format --check .`: `250 files already formatted`
- `uv run ruff check .`: `All checks passed!`
- `uv run mypy claude_bully`: `Success: no issues found in 103 source files`
- `uv run pytest -q -W error`: `8132 passed, 5 skipped, 6 deselected in 408.20s (0:06:48)` (round 0: 8128; +4 new fast tests)
- HANDOFF.md fast-suite count updated to 8132 (slow stays 6).
