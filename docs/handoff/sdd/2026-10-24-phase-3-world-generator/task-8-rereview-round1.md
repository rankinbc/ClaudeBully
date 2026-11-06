# Task 8 re-review, round 1: fix 24b9a25 on 4512a83

Scope: the five findings of `task-8-review.md` (I1, m2, m3, m4, m7) and the fix diff `review-4512a83..24b9a25.diff`. Line numbers are file:line at HEAD (24b9a25).

One focused check run, for the doubt "do the new assertions hold on a real stub run": `uv run pytest tests/test_generator_analysis.py -q -W error -m "slow or not slow"` gave `9 passed in 12.37s`. The full suite was not re-run.

## Finding Verdicts

### I1. Chart labels, footnote, results.md line, generator.json contents: ADDRESSED

The new assertions pin literal expected values or values computed from the stub run's records, not the code's own output.

- Tick labels: `tests/test_generator_analysis.py:221` asserts `["off", "non-reflexive", "reflexive"]` (literals).
- Legend texts: `:224-227` assert `["belief adoption", "reflexive quote noticed"]` (literals). Panel title and y label: `:228` asserts `(MODEL, "share of reps")`. Suptitle: `:229` asserts the literal `TITLE` (`:138`) is among the figure's texts. The report's RED check (legend renamed, test failed) is consistent with these being real pins.
- Bar heights: `:231` asserts `[0.0, 0.0, 0.5, 0.0, 0.5, 0.5]`. These are hand-derived from the injected events (`:217-218`: a confirming quote in one reflexive rep, a suspicious one in one non-reflexive rep, out of two reps a cell), not read back from `arm_rates`. This goes beyond the carry's "wiring and labels".
- Footnote absent when nothing is flagged: `:232` (`"values_loosened"` appears in no text).
- Footnote present when flagged: `:238-242` assert the literal `"1 rep flagged values_loosened, left out of the generator arms"` in the figure's texts after flagging one reflexive rep. `:243-246` assert the JSON carries `values_loosened_left_out == 1`, the same note, and `reps == {"off": 2, "non_reflexive": 2, "reflexive": 1}` (the flagged rep is out).
- `results.md` listing: `:313` asserts `f"]({GENERATOR_CHART})"` in `results.md` after a real `analyze_run`, with the chart file non-empty (`:312`). This matches the `tests/test_phase2_charts.py` pattern, which also uses the module's own constants.
- `generator.json` contents, `:249-293`:
  - top-level keys in order (`:265`), `values_loosened_left_out`/`note` (`:266`), `resumed_after_dead_attempt == {FLAT: 1, OFF: 0, REFLEXIVE: 0}` after one injected `ResumeRecord` (`:267`);
  - arms in `ARMS` order, the five rate keys per arm, `reps == 2` per arm (`:269-272`);
  - `docs_written` `[0.0, 1.0, 1.0]`, cross-checked against each rep's own `loaded.generated` lengths `{OFF: [0, 0], FLAT: [1, 1], REFLEXIVE: [1, 1]}` (`:274-279`), so it is computed from the stub run's records and also hard-pinned;
  - adoption and quote-noticed rates `0.0` (the stub's replies carry none), `own_quote_found_rate == [0.0, 0.0, 0.5]` after one injected `Discovery` (`:281-282`).
- The three progression metrics: `:285-293` assert `generated_docs_found == {Layer.seam: 1}`, `(own_quote_found_turn, quote_latency) == (7, 3)` for the rep with the injected find (target turns 3, 5, 7 after the quoted item at turn 1), and `({}, None, None)` for the other five reps. The brief's `generator.json` carries only `own_quote_found_rate`; the other two metrics live in `progression.json`, so pinning them through `summarize_progression` is the correct reading.
- `_reflexive_arm` (`tests/test_generator_run.py:412-424`) now reads `generator.json` back and asserts it holds the reflexive rates, `values_loosened_left_out == 0` and `note` None. This compares the file to `arm_rates` (same code), so it checks the writer's round trip, not an independent value. It is a supplement; the pins above carry the finding.

### m2. `generator_chart` guard: ADDRESSED

- `claude_bully/analysis/generator.py:137-138` returns None on `not _runs_generator(loaded)`, before `arm_rates` (`:139`). The docstring (`:134-136`) names the new case.
- `tests/test_generator_analysis.py:296-306` replaces `arm_rates` with a function that raises, runs `generator_chart` and `write_generator` on the non-generator `stub_env_arms_run`, and asserts both return None and `tmp_path` is empty. Removing the guard makes it fail (the report's RED evidence shows the raise from `generator.py:136`). The test would also catch a regression that drew a chart.
- Caller handling: the only non-test caller is `claude_bully/analysis/run_analysis.py:134-136`, which already did `if chart is not None: charts.append(chart)`. It handles None. The test callers (`tests/test_generator_analysis.py:219, 241, 304, 334`) assert on the return value.

### m3. No `generator.json` for a run without a generator: ADDRESSED

- `tests/test_progression.py:449-451` (inside the existing `analyze_run` test `test_analyze_writes_the_progression_charts_and_summaries`, on `stub_env_arms_run`) asserts neither `generator.json` nor `generator_arms.png` exists.
- `tests/test_phase2_charts.py:227-229` asserts the same per config (sweep, grid, idle) in `test_stub_runs_draw_each_headline_chart`. Without the guard in `write_generator`, an all-`off` run would write the file, so the assertion bites.

### m4. Reflexive vs non-reflexive documents differ: ADDRESSED

- `tests/test_generator_analysis.py:323-330` (slow test), per rep: off arm wrote `[]`; every non-reflexive doc has `not d.reflexive and d.used_items == []`; every reflexive doc has `d.reflexive and d.used_items`; both arms are non-empty. It passed in my focused run.

### m7. `_reflexive_arm` annotation and docstring: ADDRESSED

- `tests/test_generator_run.py:412` is `-> tuple[ArmRates, ProgressionSummary]`, with both names imported (`:401-405` in the diff). The docstring (`:413-415`) names both. The three callers (`:434, 444, 457`) unpack a pair as before.

## New Breakage in the Fix Diff

None.

Checked and clear:
- `generator_chart` None return: one production caller (`run_analysis.py:134`), handled.
- `generator.py` change is the guard only, and it is the same predicate as `write_generator`'s.
- `HANDOFF.md` count 8128 to 8132 matches +4 new fast tests (chart labels, footnote and JSON, JSON contents, no-generator run); the slow count stays 6. No other file in the repo outside `.superpowers` still says 8128.
- The module-scope `generator_run` fixture runs the 12-cell stub run once for the nine tests in the file (12s here), so moving the run out of the slow-only path costs little in the fast suite.
- The `figures` fixture restores `plt.close` and closes the kept figures on teardown, so no figures leak into other tests.
- The `overlay_generator_rules.yaml` change is comment rewrap only.

## Out-of-Scope Observations

- `figures` and `_texts` in `tests/test_generator_analysis.py:178-197` repeat the helpers in `tests/test_phase2_charts.py`. They could move to `conftest.py`. Duplication only.
- The `results.md` listing check (`:313`) lives in the slow test only, as the Phase 2 equivalent does. A fast `results.md` check would need the `analyze_run` path, which the module fixture makes cheap now.
- Review minors not in this fix round's list (m1 pooling across conditions that share a generator setting, m6 copied stub script, m8 redundant defaults assertion) were left as they were. They were never required.

## Verdict

All findings addressed, no new Critical/Important breakage
