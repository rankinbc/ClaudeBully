# Task 2 re-review, round 1 (fix base b89f793, head ce99c41)

Scope: findings M1 to M5 of `task-2-review.md` and the fix diff `review-b89f793..ce99c41.diff`. Read-only on the checkout (git status clean before and after). Probes are in `probes-task2-rereview/`.

## Finding Verdicts

1. M1: ADDRESSED. `tests/test_analysis_load.py` (diff 141-167): `test_a_values_loosened_said_in_reasoning_alone_is_kept_apart_and_never_lost` runs a real stub environment run whose target puts the `values_positive` firing line in its first turn's reasoning and never in a reply, then reads it back through `load_run`. It asserts no `values_loosened` in `events[key]`, exactly one in `reasoning_events[key]` at the turn whose reasoning said it with channel `reasoning` (the count is one, `len(...) == len(said) == 1`), and `is_values_loosened` False. The event comes from the channel pass, not a hand plant. The test fails on a dropping or misplacing loader: the implementer's RED (`probes-task2/fr1_red_m1.txt`, `reasoning_events[key] = []` gives 1 failed) is confirmed independently by `probes-task2-rereview/probe_m1_mutants.py`, where the unmutated test passes and four mutants of `load.detect_events` each make it fail (reasoning-only events relabelled `reply`, relabelled `both`, the reasoning pass switched off, the events dropped before the split). The hand-planted test stays, as it should.
2. M2: ADDRESSED. `claude_bully/analysis/expected.py:16-17` now reads "in the reply or both channels (never reasoning alone, spec 6.4: `LoadedRun.events` holds no reasoning-only event)". It matches the code (`expected.py:100` reads `loaded.events` only). No code change.
3. M3: ADDRESSED. `tests/test_channel_pass.py:407` marks `test_neutral_reasoning_on_every_turn_gives_no_reasoning_event` `@pytest.mark.slow  # 3.6 to 4.2 s alone, 4.91 s under -n 8 (ruling Q49, fix round 1 M3)`. `slow` is registered and deselected by default (`pyproject.toml:68-69`). The gate counts agree (`fr1_gate_pytest_fast.txt` 10892 passed, 11 skipped; `fr1_gate_pytest_slow.txt` 230 passed: one test added to fast, one moved to slow, one added to slow).
4. M4: ADDRESSED. `tests/test_channel_pass.py:274-280, 290-294, 296-308`: the `_cases` docstring states the assumption (one `World` per name is shared, sound only while no builder and no detector mutates a `World`); `load_once` records each world's `model_dump_json()` at load in `_SHARED_WORLDS`; `_assert_worlds_unchanged()` runs at the end of both fixture-wide loops (`:380`, `:421`), and `load_once` calls the original `load_world`, so there is no recursion. Verified by `probe_m4_guard.py`: with the cases built the guard is quiet; setting `world.sheet.mole_doc` on the shared `annex` world makes it raise "a detector or builder mutated a shared World", and it is quiet again once restored. The only call site, `tests/test_events.py:127`, passes `(name, WORLDS_DIR)` positionally, so the narrower cache key (name only) changes nothing. The guard runs only in the two slow loops; the six fast tests that share `_cases()` are not guarded, which the task did not require.
5. M5: ADDRESSED. `docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md:157` now ends "(ruling A7)". The rulings table has A7 (line 489) as "A reasoning-only `values_loosened`" and A9 (line 491) as the outlet persona. No other spec line cites A9 for `is_values_loosened`.

Counts: 5 addressed, 0 not addressed.

## New Breakage in the Fix Diff

None. Checked: no em dash in any added line; the HANDOFF item 2 edit matches the gate counts and the file's markings (both loops `slow`); no test, import or helper the diff touches is used elsewhere in a way the change affects (`env_experiment`, `Speaker` and `yaml` were already importable in `test_analysis_load.py`); the covering run (`fr1_covering.txt`, 67 passed) and the gate outputs (ruff, both mypy runs, fast and slow pytest, each its own exit 0) are present and agree with the report.

## Out-of-Scope Observations

- `load_once` keys `_SHARED_WORLDS` by world name alone, where the old `functools.cache` keyed on `(name, worlds_dir)`. Sound today (one call site, one constant `WORLDS_DIR`); would matter only if a later fixture loaded the same name from another directory. Not worth a change.
- The "reasoning-only count" the new test asserts is the number of reasoning-only `values_loosened` events in `reasoning_events`; the `channels.json` figure (`values_loosened_reasoning_only`) is a later task's, as the report says. When that task lands it should add its own assertion on the file.

## Verdict

Approved. All five findings addressed; no new Critical, Important or Minor issues.
