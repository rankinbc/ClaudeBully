# Task 2 review: the channel pass (cfa495f..b89f793)

## Spec Compliance

Compliant. I checked the brief's file list against the diff file by file. Every listed file is changed: `metrics/events/__init__.py`, the 13 family modules, `analysis/load.py`, `tests/test_events.py`, `tests/test_env_events.py`, `tests/test_analysis_load.py` and the new `tests/test_channel_pass.py`. The extra files (`records.py`, `runner/runner.py`, `runner/env_turn.py`, `tests/test_reasoning_capture.py`) are the two riders from `task-2-carries.md` and nothing more.

- Step 3: every family declares `TEXT_EVENTS` and `RECORD_EVENTS` as written-out literals, never one derived from the other. The record sets match the brief's table exactly: harness 3, environment `tool_used` and `mole_found`, idle 6, authority 4, poisoned_well 4. Each record event has a one-line comment, and the docstring of `RECORD_EVENTS` in `authority.py` states D-exit-refused and R-M3 (diff 523-529). The unions are built from `FAMILIES` (diff 273-281), and the module docstring states the rule of 6.1 (diff 217-224).
- Step 4: `reasoning_view` is the brief's body verbatim (diff 304-322). It changes only `text` and `tool_round_texts`, so `tool_call_ids`, `idle` and the context stay as spec 6.2 requires. `detect_events` keeps the old body as `_detect`, and the second pass is the brief's code (diff 373-397). The docstring states R-I2's three costs.
- Step 5: `load_run` reads with `reasoning=True` and splits by channel (diff 158-170). The fallback's failure count is read as before, and no other consumer changed. I grepped `claude_bully/`: `load_run` is the only caller of `detect_events`, and nothing outside `load.py` reads `reasoning_events` or `Event.channel`.
- Step 1: every test the brief names is present, and the assertions match the brief, including the measured `HISTORY_BOTH` pin.
- Q49: the reasoning-equal loop (5.1 to 5.3 s) is marked `slow` with its measurement in a comment. The neutral loop (3.6 to 4.2 s) stays fast.
- Rider 1: the plain-cell privacy test now runs `analyze_run` and asserts the judge's prompts are non-empty and free of the sentinel.
- Rider 2: spec 4.1 allows only `full`, `summarized` or `unknown` beside available text. `kind_beside_text` normalises `redacted` there on both cell kinds, and a test was RED before the change.
- Step 7 docs-sync is done: HANDOFF item 2, docs/00 sections C and H, docs/10 Part 2, and the spec's "As planned" D-exit-refused, R-M3 and R-I2. No em dash was added.

Cannot verify from the diff:

- CV1: the gate's exit codes. The implementer reports that the wrapper exited 1 even though both pytest steps passed. The controller's own rerun of the fast suite (`-W error`) and the slow suite settles this.
- CV2: the loop timings under the controller's `-n 8` run. If the neutral loop goes over 5 s there, Q49 makes it `slow`.

## Strengths

- The early return computes `_detect(...)` before testing the flag, so a run without reasoning gets exactly the old body. The environment family now reads its keywords from the context it was built with, which holds the same values. The goldens and `test_without_reasoning_the_result_is_todays` pin this.
- The second pass keeps no record event and nothing from another turn, and it never asks the authority fallback, the only LLM reader among the detectors (`EnvContext` holds no other). The privacy and record-leak risks are closed in the code, not just in the docs.
- A `both` event is the reply event itself (its span and attrs come from the reply), so `LoadedRun.events` carries no reasoning text.
- The tests are not vacuous:
  - The fallback test asserts `plain >= 1` before it compares counts.
  - The neutral loop compares the whole event list with the channel set aside, and pins the `both` set exactly.
  - My mutant probe shows the tool-turn test bites. With a view that puts a tool turn's reasoning in its reply text, `authority[23]` gives a reasoning-only `authority_deferred` and `environment[76]` a reasoning-only `world_dismissed`. As built, neither appears.
- The case list is built lazily with a per-build world cache, which keeps collection cost off every xdist worker. The report explains and measures this choice.

## Issues

### Critical

None.

### Important

None.

### Minor

- M1. `tests/test_analysis_load.py` (diff 1446-1458): `test_a_reasoning_only_values_loosened_never_flags_the_rep` plants an event by hand into `reasoning_events`. That only shows `is_values_loosened` does not read that list, which it never did. Nothing checks the other half of the review focus: that a reasoning-only `values_loosened` is not lost. That would mean checking that one produced by the pass reaches `reasoning_events` and stays out of `events`. The split in `load_run` does not depend on event type, and the `premise_concession` load test covers it generically. My probe shows the pass finds it: in all 32 Poisoned Well fixture items with a `values_loosened`, moving the firing reply into reasoning gives a `reasoning`-channel event (`probes-task2-review/probe_values_loosened.py`). So this is a coverage gap, not a defect. The test shape is plan-mandated. Fix: add one case that runs `detect_events(..., reasoning=True)` on such an item, applies `load_run`'s split, and asserts the event sits in the reasoning list and that `is_values_loosened` is False on a `LoadedRun` built from that split.
- M2. `claude_bully/analysis/expected.py:16`: the docstring says an expected event is counted "on any channel". Since this task, `loaded.events` holds `reply` and `both` only, so a reasoning-only event is not counted. That behavior is correct under A5, but the docstring now misleads. Change it to "in the reply or both channels (never reasoning alone, spec 6.4)".
- M3. `tests/test_channel_pass.py` (diff 1847): `test_neutral_reasoning_on_every_turn_gives_no_reasoning_event` measured 3.6 to 4.2 s alone. Each case runs a plain pass plus one pass per target turn, so it does more detector work than "loops over every event fixture more than twice" (R-I12). It complies with Q49 as measured, but it is the fast suite's likeliest test to cross the bar on a loaded machine. Worth a comment naming the measurement, as the slow one has.
- M4. `tests/test_channel_pass.py` (diff 1738-1749): `_cases()` patches `test_events.load_world` with `functools.cache`, so one `World` object is shared across every item of a world. This is safe only while no detector or builder mutates a `World`. `tests/test_events.py: _world` copies before changing, and no detector writes one today. The assumption is unstated in the test and has no guard. Name it in the docstring, or freeze the check, so a later detector that mutates a world fails loudly here.
- M5. Spec section 6.4 (`docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md:157`, unchanged by this task) cites "ruling A9" for `is_values_loosened`. The ruling is A7, and A9 is the outlet persona. The brief, HANDOFF and docs/00 all cite A7 correctly. Fix it at the next spec touch.

## Assessment

Task quality: Approved. The channel pass matches spec 6.1 to 6.4 and the brief, and both riders are done. The early return keeps runs without reasoning byte-equal, and no reasoning-only event reaches a pre-existing count, flag or LLM reader. What remains is minor test coverage and doc drift.

Probes (read-only, no model call): `probes-task2-review/probe_values_loosened.py` (32 of 32 moved to the reasoning channel) and `probes-task2-review/probe_toolturn_mutant.py` (as built: none; mutant: one leak per item).

Focused checks outside the diff, each with its risk:

- The callers of `detect_events` and the readers of `channel` and `reasoning_events` in `claude_bully/`. Risk: a reasoning-only event or a `both` relabel reaching another consumer. None found.
- The fields of `EnvContext`. Risk: another LLM reader in the second pass. Only the fallback.
- `tests/test_events.py: _world`. Risk: the cached world being mutated. It copies first.
- `expected.py`'s docstring (M2).
