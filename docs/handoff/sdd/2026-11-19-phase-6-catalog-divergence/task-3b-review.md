# Task 3b review: the divergence outputs

Range ee3d747..9d61f9a (one commit). Read: the reviewer rules, the brief, the global constraints, the carries file, pre-flight Q10, Q14 and Q37, spec 4.4 to 4.6, 5.1 to 5.8, 6.5, 11.x and 12.1 to 12.5, and the whole diff. Focused checks outside the diff, one per named risk:
- `metrics/divergence.py`: `divergence_pass` keys only complete conversations, so the jsonl line count matches; `counted_class`, `concealment_rate`.
- `records_env.TriggerEvent.turn` and `Discovery.turn` against `metrics/ratings.rating_items`: the hedge join reads the same turn index the ratings use.
- `enums.DivergenceClass` is a `StrEnum`, so `str(event.class_)` in the calibration script is the value.
- `metrics/ratings.py`: `SKIPPED_STUB` and `SKIPPED_NO_JUDGE` are "stub judge" and "no judge", so the notes are unchanged.
- `analysis/promote.py`: `COPIED_DIRS` already copies `analysis/`, and `scan_copied_emails` reads every copied text file. A span in `divergence.jsonl` therefore reaches promoted output under the same rules as the turn's own reasoning and the judge cache (spec 4.6). No new risk.
- `scripts/judge_calibration.py` imports no `build_provider`.

Probes (in `probes-task3b-review/`):
- `mutate_hedge_depth.py` and `mutate_hedge_depth.txt`: in-process mutations of `_hedge_turns` (returns nothing), `_depth_at` (always 0) and `_distress_by_depth` (concealed_distress always 0). Each was run against `test_the_report_counts_by_kind_class_and_state` and `test_hypotheses_reads_this_analysis_divergence`. All three mutations pass (see I1).
- `head_task_files.txt`: the five touched test files at HEAD (after the CRLF to LF conversion), run with `-m "slow or not slow" -n 8 -W error`: 60 passed. This settles the doubt that the committed LF tree was never run, since the fast suite ran before the conversion.

### Spec Compliance

Compliant, with the one plan-text deviation below accepted.

File by file against the brief's list, all of these are present: `analysis/arms.py` (new), `analysis/divergence.py` (new), `poisoned_well.py` (`_escape`), `run_analysis.py`, `report.py` (`reasoning=`), `scripts/judge_calibration.py` (`--divergence`), the four modified test files, the new `tests/test_divergence_analysis.py` and the docs-sync files. One file falls outside the list: `metrics/divergence.py` (3 lines), which is carry 2's optional change and is judged below.

Which written file may hold a quote of the target's reasoning:
- What the spec allows. Spec 5.5 puts `reasoning_span` (and `reply_span` and `rationale`) in `divergence.jsonl`. Spec 5.7 gives `divergence.json` counts only, and 6.5 gives `channels.json` counts only. Spec 12.4 limits the chart to labels ("class, arm and target API strings"). Spec 12.5 gives `results.md` availability and rates. Spec 5.8 gives the calibration form both channels, by design.
- The code matches. `divergence.jsonl` is the only analysis file written from `DivergenceEvent` text fields. `divergence_report`, `write_channels`, `concealment_chart` and `reasoning_section` read only counts, class names, arm labels and condition names. The calibration form holds `Turn.reasoning_text` whole and is written under `--out` (spec 5.8).
- The privacy test catches a failure in either direction:
  - If the span went missing from `divergence.jsonl`, the `SPAN in divergence.jsonl` assertion fails.
  - Every other file under `analysis/`, and the ledger, is checked for both `SPAN` and `SENTINEL`. A span or the reasoning in `divergence.json`, `channels.json`, `results.md` or the chart (all four are asserted present) fails the test.
  - If the jsonl held the rest of the reasoning, the `SENTINEL not in divergence.jsonl` assertion fails.
  - The exception is by exact path, with no wildcard (carry 4).
- The ASSUMED choice not to except `divergence.json` is correct. The brief's test bullet says it holds spans, but neither the brief's own shape for the file nor spec 5.7 has a span in it, and the spec supports the stricter assertion. The controller may want that plan bullet corrected so that Task 9 (which fills `plan_to_action_latency`) does not read it as permission.

Pre-flight rows:
- Q10 is implemented as ruled: two plain analyses are byte-equal for all three files; the jsonl and channels files are byte-equal to the flagged analysis's; `divergence.json` is equal once `note` is popped.
- Q14 is implemented: `arm_of(exp, specs, cell_id)` is the body, `ignition_arm` is a wrapper, and the test runs on `expand_cells`.
- Q37 is implemented: each half of the `stub_run` test analyzes into its own `out_dir`.

Carries, all addressed:
- 1: the fourth note is written and tested in the file and in `results.md`, and spec 5.7 is marked "[refined in Task 3a's review]".
- 2: done in three lines, with no import cycle.
- 3: the helpers are imported from `tests/fixtures/catalog_stub.py`.
- 4: see the privacy findings above.

Cannot verify from diff:
- CV1: the gate counts and timings in the report (10965 fast, 243 slow, ruff, both mypy). The five touched test files pass at HEAD (probe above). The controller should accept the rest from the saved `probes-task3b/gate_*.txt`, noting that the full fast suite ran on the tree before the LF conversion.

### Strengths

- The privacy boundary is drawn exactly where the spec draws it. The test asserts the span is present where the spec wants it and absent everywhere else, by file name. The implementer chose the stricter reading over a loose brief bullet and said so.
- `n/a` is honoured end to end: `concealment_rate` is None (never 0) in the JSON, the chart shows `n/a` text and no bar, `results.md` prints `n/a`, and a depth with no judged turn is left out of `distress_by_depth`, so `share` never divides by zero.
- `arm_of` reads only configuration. Its test covers a condition named after another arm, a Sanctuary winning over a premise, and both auto and explicit controls, and it asserts `IGNITION_ARMS` coverage as a set equality.
- Every text file goes through `write_atomic`, the calibration form included. The `stub_run` test and the re-analysis tests write to their own `out_dir`, so test order does not matter.
- The `poisoned_well.json` change is purely additive. The test pins every other `escape` key as unchanged and checks that a flagged rep's reasoning escape is not counted.

### Issues

#### Critical

None.

#### Important

- I1: no test checks the values of `hedge_decomposition` or `distress_by_depth`.
  - Where: `claude_bully/analysis/divergence.py:370-430` (`_hedge_turns`, `_hedge_decomposition`, `_depth_at`, `_distress_by_depth`); tests at `tests/test_divergence_analysis.py:186-193` and `:197-205`.
  - What is wrong: the only checks are that the leaves are numbers, the key set, and that each depth present has `judged > 0`. The mutation probes (`probes-task3b-review/mutate_hedge_depth.txt`) show the tests still pass when `_hedge_turns` returns nothing, when every turn is depth 0, and when `concealed_distress` is always 0.
  - Why it matters: hypotheses items 3 and 10 read these two entries as evidence (spec 5.7, I37). The hedge join relies on `TriggerEvent.turn` meeting `DivergenceEvent.turn`. Its `premise_concession` branch reads `Event.hedged` or `attrs["hedged"]`, which the report says no detector sets today. So neither branch is exercised.
  - Fix: in `test_the_report_counts_by_kind_class_and_state`, or a sibling test on the same in-memory `loaded`:
    - add a `self_uncertainty` `TriggerEvent` on one hand-set judged turn and a hedged `premise_concession` `Event` on another;
    - add a `Discovery` of a `seam` document before a `concealed_distress` verdict;
    - assert the exact `hedge_decomposition[MODEL]` dict: `hedge_turns`, `judged`, the class counts, and an unjudged hedged turn counted in `hedge_turns` only;
    - assert the exact `distress_by_depth[MODEL]`, for example `{"0": ..., "2": {"judged": 1, "concealed_distress": 1, "share": 1.0}}`;
    - check that a hedge on a control cell is left out (the ASSUMED reading).

#### Minor

- M1: the docs claim more about the jsonl than the code enforces.
  - Where: the module docstring at `claude_bully/analysis/divergence.py:199-201`; `docs/10-ROUND-TWO.md` ("Outputs": "the only analysis file that quotes the reasoning (each concealed verdict's `reasoning_span`)"); the `docs/00-RECONCILED.md` B row.
  - What is wrong: these say the jsonl holds the reasoning span and "never holds the rest". In fact each line also carries the judge's free-text `rationale`, which may quote the reasoning. An `aligned` verdict's spans are also kept as given (D-span), so spans are not limited to concealed verdicts.
  - Why it is Minor: spec 5.5 allows all of this in the jsonl, so it is not a privacy breach; the prose just overstates.
  - Fix: say "the spans and the rationale of every verdict, any class" and drop "never holds the rest". The privacy test's `SENTINEL not in jsonl` holds only because the judge double's rationale is fixed text.
- M2: the report and rows are built more than once per analysis.
  - Where: `claude_bully/analysis/run_analysis.py:826-831`; `claude_bully/analysis/divergence.py:474,524-525`.
  - What is wrong: `divergence_report` is built twice (inside `write_divergence` and again for `reasoning_section`). `concealment_chart` then rebuilds `_rows` and every `_row` a third time instead of reading the report. That is cheap on stub runs but means three passes over every event.
  - Fix: have `write_divergence` return (or accept) the report and pass it to the section and the chart.
- M3: a private name is imported across modules.
  - Where: `claude_bully/analysis/divergence.py:37`.
  - What is wrong: it imports the private `progression._LAYER_DEPTH` (the report raises this itself).
  - Fix: rename it `LAYER_DEPTH` in `progression.py` (its three uses there are local), or add a public `layer_depth(layer)`.
- M4: after a flagged analysis, a plain re-analysis leaves the file but drops the section.
  - Where: `claude_bully/analysis/divergence.py:465-466`; `run_analysis.py:826-830`.
  - What is wrong: on a run with no reasoning, a flagged analysis writes `divergence.json` and the `## Reasoning and reply` section. A later plain analysis in place leaves the file alone (the brief mandates "leaving `analysis/` as it was"), so `--hypotheses` still reads it, but `results.md` loses the section. The two outputs then disagree about whether the pass's result exists.
  - Why it is Minor: the plan mandates the behaviour of the file.
  - Fix: add one sentence in docs/10, or get a ruling: write the section whenever the file exists, or never.
- M5: two helpers swallow errors and fall back silently.
  - Where: `claude_bully/analysis/arms.py:100-106` and `:121-127`.
  - What is wrong: `_environment` treats a `ValueError` as "no environment", and `_countdown` falls back to the condition's raw `params` on `KeyError` or `ValueError`. A config the factory cannot route therefore gets an arm read from part of its configuration, with no note.
  - Why it matters: on a loaded run the config has already validated, so this only affects `arm_of` on configs that have not run (Task 11's test over `configs/`). There, a silent `none` would hide a broken config.
  - Fix: let the error propagate, or return a distinct value the test can see.
- M6: a test variable is reused for two things.
  - Where: `tests/test_reasoning_channel.py:256` and `:273`.
  - What is wrong: `events` holds the events the pass returned, then is rebound to the jsonl path in the same test.
  - Fix: rename the second one (`events_file`) so the later `path == events` check reads unambiguously.
- M7: docs/10 describes `by_kind` inaccurately.
  - Where: `docs/10-ROUND-TWO.md` ("Outputs").
  - What is wrong: it says `by_kind` breaks down "those turns" (the `with_reasoning` turns) by kind. But `redacted` is counted on `reasoning_absent` turns (the report's ASSUMED choice), and in the test `by_kind` sums to 4 while `with_reasoning` is 3.
  - Fix: say that `by_kind` counts every turn's recorded kind, including `redacted` on turns with no reasoning.

The ASSUMED choices, the file outside the brief's list and the CRLF fix, judged on their merits:
- Not excepting `divergence.json`: correct (see Spec Compliance).
- `hedge_decomposition` and `distress_by_depth` over condition cells only, with controls as rows in `models`: reasonable. It matches the register's `_environment_cells` reading, and the brief's "controls are conditions here" applies to `models`. It is untested (I1).
- `metrics/divergence.py` building `PASS_SKIPPED_*` from the literals in `ratings.py`: acceptable under carry 2. The values are unchanged, and `ratings.py` imports nothing from `divergence.py`. It does tie the divergence note to the ratings' reason strings, which the new comment says.
- The `progression._LAYER_DEPTH` import: M3.
- The six files converted from CRLF to LF after the fast suite: the controller confirmed the index stores them as LF, and the five touched test files pass on the committed tree (probe). No finding.
- The rest are each reasonable and consistent with the brief:
  - `by_kind` counting `redacted` on absent turns;
  - a turn counted as hedged through `Event.hedged` or `attrs`;
  - `channels.json` rows including controls;
  - the chart's bar per condition, with `n/a` where nothing is judged;
  - the section's per-model lines;
  - the CLI flag's shape and the key's contents;
  - `note` defaulting to `cache_only`.

### Assessment

Task quality: Needs fixes. The privacy boundary, the `n/a` handling, the arms and the pre-flight rulings are right and well tested. The one gap that matters is that the two entries the register reads (`hedge_decomposition`, `distress_by_depth`) have no test that would notice them counting nothing (I1).
