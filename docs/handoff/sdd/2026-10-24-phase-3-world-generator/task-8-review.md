# Task 8 review: generator arms, progression metrics, the reflexive config

Range 70864b5..4512a83 (one commit, 4512a83). Diff file: `review-70864b5..4512a83.diff` (line numbers below as `diff:N` refer to it; file:line refers to HEAD).

Focused checks run outside the diff, one per named risk:
- Risk: `generator_progress` counts `Discovery` records without de-duplicating per document (unlike `_found`, which uses `setdefault`), so a repeated discovery would inflate `generated_docs_found`. Check: `claude_bully/environments/runtime.py:1227-1245`. The runtime records a document's `Discovery` only the first time (`self._discovered`). No inflation. PASS.
- Risk: the new stub's self-claim is not a closed heuristic shape, so the slow test would fire only by accident. Check: `claude_bully/environments/harvest.py:142-161`. "I'm a language model, I don't have a body" is the first `_SELF_CLAIM` pattern (`I'm` + `_NATURE` + `, ` + `_POSSESS`). PASS.
- Risk: `analyze_run` writes `generator.json` for runs with no generator, or the new calls break the Phase 2 analyses. Check: `write_generator` returns early on `not _runs_generator` (diff:240-243), and both new calls come after `write_temporal`/`write_authority`/`write_idle` (diff:637-644). With no generator, every conversation's arm is `off`, so no model has two arms and `generator_chart` returns None. PASS by reading. No test asserts the absence of `generator.json` on a Phase 2 run (`tests/test_run_analysis.py` has no generator assertion; see Minor m3).
- Doubt: does the slow test pin a real fire? Ran `uv run pytest tests/test_generator_analysis.py -m slow -q -W error`: 1 passed, 0 warnings. Its `docs_written >= 1.0` assertion holds only if the run wrote a real `GeneratedDoc`. PASS.

## Spec Compliance

Verdict: PASS with one gap (the carry's label-pinning requirement, Important I1).

| File | Brief + carries | Result |
| --- | --- | --- |
| `claude_bully/analysis/generator.py` | Complete module per brief | PASS. Verbatim. `ruff format` rewrapped only the two `ax.bar` calls (diff:276-287). |
| `claude_bully/analysis/load.py` | `LoadedRun.generated`, read after `_environment_context` | PASS (diff:349-350, 372-375, 397) |
| `claude_bully/analysis/progression.py` | Three fields, `generator_progress`, `summarize` wiring, items from `HarvestItem` | PASS (diff:494-498, 520-542, 552-570). Docstring and `__all__` extended. |
| `claude_bully/analysis/run_analysis.py` | Chart appended when returned; `write_generator` always called | PASS (diff:640-644) |
| `configs/environments/generator_reflexive.yaml` | Complete per brief | PASS. Verbatim (diff:652-712). No real names: `display_name: Claude` and the `sonnet`/`opus`/`haiku` model strings follow existing configs, and the brief mandates them. |
| `tests/fixtures/responses/environment.yaml` | Four items: two positives, two near-misses | PASS. Verbatim (diff:852-899). The report says `test_env_events.py` passed with them (28 passed), and I did not re-run it. Fictional path only. |
| `tests/test_generator_analysis.py` | Brief tests | PASS with one deviation: the slow test points at a new stub script (judged below). |
| `tests/test_progression.py` | One defaults assertion on an environment run | PASS (diff:1244-1250) |
| `HANDOFF.md` | Progress item 8, counts, Phase 7 item, resume prompt names Task 9 | PASS (diff:33-34, 56-57, 79-85, 89-90, 112, 123-124) |
| `docs/00-RECONCILED.md` | Section C fixtures, the three fields, section I row | PASS. The fields note sits in section B beside the "RunSummary gains" paragraph (diff:728), which is a reasonable place for it. |
| `docs/06-HYPOTHESES.md` | Hypothesis 6 names the config, arms and chart | PASS (diff:826) |
| `docs/02-ENVIRONMENTS.md` | "Metrics and events": the three metrics | PASS (diff:781). The experiments-row edit (diff:799) goes beyond the brief and is accurate. |
| Extra: `tests/fixtures/stub_scripts/overlay_generator_rules.yaml` | Not in the brief | Justified Extra (claim 1 below) |
| Extra: `tests/test_generator_run.py` | Not in the brief's file list; the carry (m1) invites it | Justified Extra (claim 2 below) |
| Carry: "Test the chart's wiring and labels, not its shape" | Required | FAIL. Wiring is tested; labels are not (I1). |
| Carry: read the record shapes as built | Required | PASS (claim 4) |
| Carry: reuse the shared fixtures | Required | PASS. `GeneratorFactory`, `GeneratorStub`, `HarvestJudge` and `GENERATOR_MODEL` are reused. The `_doc`/`HarvestItem` builders come from the brief's unit test. |
| Commit author and trailer (`Co-Authored-By: Claude Fable 5.1`) | Carry | CANNOT VERIFY. The diff package shows only the subject line, and git was not re-run. |

Judgement on the implementer's points:

1. **New stub script.** This is the right fix. The brief's test could never fire on `overlay_target_rules.yaml`: the shipped script says nothing the heuristic harvest holds (Task 4 carry: a stub run harvests only closed heuristic shapes). The added sentence is exactly the closed `_SELF_CLAIM` shape (`harvest.py:154-156`). The file adds no names beyond the overlay's fictional ones it was copied with (`Quillmoor Assist`, `rackandrelay.example`). Copying the script rather than editing it leaves the shared one, and the tests that use it, untouched. The test pins a real fire: `docs_written >= 1.0` (diff:1104) needs a committed `GeneratedDoc`, the run passed, and the off arm is pinned to 0.0 (diff:1103). Two weaknesses: it does not pin which arm's documents are reflexive (see m4), and the file's header has a reflow artifact (m5).
2. **Run-level tests for error, cap and degraded harvest** (diff:1198-1228). Each runs a real experiment through `_run` and asserts on the real `GeneratorFire` records: status `error` with the error text; status `rejected` with rejection `cap`; `plan.harvest_degraded == [1]` on every plan. Each then pushes the run through `arm_rates` and `write_generator`. These close Task 7's m1 at run level. Their analysis assertions are thin: `docs_written == 0.0` on a run with no documents, and `write_generator(...) is not None` with the payload never read (I1). As the report says, the analysis does not consume `status` or `harvest_degraded`, so these tests mainly pin Task 7's record path.
3. **Fixtures.** Two positives (suspicious, confirming) and two near-misses, verbatim from the brief, which states they were run against the detector. Each near-miss is labelled by a comment, not `near_miss: true`. That follows this file's existing convention (it holds no `near_miss` key) and is not a finding.
4. **Record shapes.** `generator_progress` reads `GeneratedDoc.doc_id`, `.layer`, `.reflexive`, `.used_items` and `HarvestItem.id`/`.turn` (diff:528-541). `arm_rates` counts committed `GeneratedDoc` records (diff:220). These match Task 7's records: the run-level assertion `(own_quote_found_turn, quote_latency) == (5, 1)` (diff:1163) holds on a real Task 7 run with a seam/buried pair. Nothing reads `unlock_rung`, and no metric needs it.

## Strengths

- The metrics are correct on real records. `generated_docs_found` restricts to generated `doc_id`s, so anchor discoveries are excluded (a unit test pins this, diff:1061). `own_quote_found_turn` takes the earliest discovery of a document whose `reflexive` is true, and Task 7 sets that only when items were used. `quote_latency` counts target turns in `(newest_item_turn, discovery_turn]` and returns None when the document names no known item (diff:535-541).
- The arm rates use the existing helpers rather than copying them: `without_flagged`, `flagged_note`, `count_resumed`, `environment_of`, `target_model`, `is_belief_adoption`. They pool condition cells only (controls excluded, diff:194) and complete conversations only (diff:196), the same denominators as the Phase 2 analyses.
- Arms are sorted deterministically by model and then `ARMS` order (diff:211-213). JSON keys are sorted per cell, and `zip(..., strict=True)` guards the panel loop.
- The deviation was diagnosed from a probe run, not patched over, and the shared `overlay_target_rules.yaml` was left alone.
- The Task 7 seam-pointer test now also pins the three progression metrics end to end on real records (diff:1162-1163).

## Issues

### Critical

None.

### Important

**I1. The chart's labels and `generator.json`'s contents are never asserted, against the stub-chart carry.**
- Where: `tests/test_generator_analysis.py:146-163` (diff:1096-1113) asserts only that `generator_arms.png` and `generator.json` exist and that `write_generator`/`generator_chart` return non-None. `tests/test_generator_run.py` `_reflexive_arm` (diff:1194) asserts `write_generator(...) is not None` and never reads the file.
- What is wrong: `task-8-carries.md` says "Test the chart's wiring and labels, not its shape." Nothing in the suite checks any of the following:
  - the tick labels `off` / `non-reflexive` / `reflexive`, the legend texts `belief adoption` / `reflexive quote noticed`, the panel title or the suptitle (`generator.py:149-164`);
  - the `values_loosened` footnote, required by the global constraint "values_loosened reps left out of every chart with the count stated";
  - that the chart is listed in `results.md`;
  - the `generator.json` schema the brief fixes ("every arm present for a model is written, each with the same five keys", plus `values_loosened_left_out`, `note`, `resumed_after_dead_attempt`).

  The implementer checked the labels by eye (report, "Stub-chart lesson"). That is not a test.
- Why it matters: this is exactly the Phase 2 lesson. A chart whose bars are empty on stubs can only be trusted through its labels and wiring, and a broken footnote or a renamed JSON key would pass the whole gate. Each Phase 2 analysis has these tests: `tests/test_phase2_charts.py:235` (`test_charts_leave_flagged_reps_out_and_say_so`), `:413`/`:430`/`:442` (the `*_json_counts_the_reps_resumed_after_a_dead_attempt` tests), the `results.md` listing check at `:226-227`, and the tick-label checks at `:309`/`:585`.
- Fix: extend the slow test, or add a fast test on the loaded run. Reuse `test_phase2_charts.py`'s `_texts`/`_json` pattern, keeping figures open via a monkeypatched `plt.close`. Then:
  - assert the tick-label texts, the two legend texts and the suptitle;
  - assert `f"]({GENERATOR_CHART})"` appears in `results.md`;
  - flag one rep with `values_loosened` and assert the footnote text plus `values_loosened_left_out == 1` and the reduced `reps`;
  - read `generator.json` and assert its top-level keys, the five keys per arm, and `resumed_after_dead_attempt`'s cell names.

### Minor

**m1. Arms pool every condition that shares a generator setting.** `generator.py:76-80` (diff:206-209) groups by `(model, arm)` only. In a run whose conditions differ in something besides the generator (gating, world, strategy), conversations with the same generator arm are pooled, and the chart compares mixtures. This is harmless for `generator_reflexive.yaml`, where the environments differ only in the generator, and it is plan-mandated. Fix: note it in the module docstring, or key the arm by environment label (`progression.environment_labels`) and refuse to pool across differing environments.

**m2. `generator_chart` computes `arm_rates` on every run, generator or not.** `generator.py:136` (diff:267) has no `_runs_generator` guard, unlike `write_generator` (diff:242). So every environment run since Phase 1 pays for `summarize` per conversation twice more (once in the chart and once in the JSON), only to draw nothing. It is correct but asymmetric and wasteful. Fix: return None early when `not _runs_generator(loaded)`.

**m3. No test pins "no `generator.json` for a run without a generator".** `write_generator`'s None branch (diff:242-243) is untested, and `tests/test_run_analysis.py` has no generator assertion. Fix: one assertion in an existing Phase 2 `analyze_run` test, `not (out / GENERATOR_FILE).exists()`.

**m4. The slow test does not show that the arms differ in reflexivity.** `test_generator_analysis.py:157-159` (diff:1103-1105) pins doc counts per arm, but not that the reflexive arm's documents carry `used_items`/`reflexive: true` while the non-reflexive arm's do not. That difference is the point of the three-arm design. Fix: assert `all(not d.reflexive for d in loaded.generated[flat_key])` and `any(d.reflexive for d in loaded.generated[reflexive_key])`.

**m5. Reflow artifact in the new stub script's header.** `tests/fixtures/stub_scripts/overlay_generator_rules.yaml:6` (diff:922) is one overlong line that splices two sentences mid-paragraph ("... skips as an echo. The service page and the world question open first_crumb on target turn 1 (the seam is"). Fix: rewrap the comment.

**m6. The new stub script copies `overlay_target_rules.yaml` wholesale to change one reply.** The file is 28 lines and differs in one sentence (diff:937). A future edit to the shared rules will silently not reach this copy. The stub-script format has no include, so a copy is defensible. Fix (optional): build the rules in the test by loading `overlay_target_rules.yaml` and replacing the one `reply_after_tool`, or add a header line naming the source file and the single difference (already half there).

**m7. `_reflexive_arm` is typed `-> Any` and returns a tuple.** `tests/test_generator_run.py` (diff:1187-1195) returns `(ArmRates, ProgressionSummary)`, and its docstring describes only the first. Fix: annotate `-> tuple[ArmRates, ProgressionSummary]` and name both in the docstring.

**m8. The `test_progression.py` defaults assertion is redundant.** The preceding `summaries[ENV] == ProgressionSummary(...)` (diff:1230-1242) already implies the defaults, because the expected object is built without the three fields. The brief asked for the assertion, and it is harmless.

## Assessment

Task quality: Needs fixes.

The metrics, the analysis module, the config and the stub-script fix are correct and read Task 7's records as built. The slow test pins a real fire. The one gap is the carry's requirement to test the chart's labels and wiring: the label texts, the flagged footnote, the `results.md` listing and the `generator.json` payload are all unasserted, so a broken label or key would pass the gate.
