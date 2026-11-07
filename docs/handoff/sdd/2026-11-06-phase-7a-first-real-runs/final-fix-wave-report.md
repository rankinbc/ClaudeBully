# Phase 7a final fix wave: report

FIX_BASE a5328f3, on `build/v1`. One commit (987f8d4). Every item in `final-fix-wave.md`, in its order, TDD: the failing tests first (RED runs below), then the fix (GREEN).

## 1. I1: the limit wordings, login first (Task 3 M5 rides)

What changed:
- `claude_bully/providers/claude_code.py`: `_RATE_LIMIT` (now `Final`) keeps its old alternatives, widens `rate limit` to `rate[ _]limit` (the API's `rate_limit_error`), and adds the word-bounded `\bhit your limit\b`, `\blimit reached\b`, `\blimit will reset\b`, `\bresets? at\b`. On an `is_error` result `_LOGIN` is now checked before `_RATE_LIMIT`. The non-zero-exit path keeps its order (the scope names the `is_error` results only).
- Runbook: every rung report, rung 0's first, records the exact text of any limit met ("What `rung_report.md` holds"), and the rung 0 checklist points there.

Tests (`tests/test_providers_claude_code.py`): `LIMIT_WORDINGS` (ten wordings, paraphrased so none names a product: `usage limit reached|<ts>`, `You've hit your limit · resets 3pm` with and without a zone, `5-hour limit reached ∙ resets 3pm`, `Weekly limit reached ∙ resets Mon 9am`, `Your limit will reset at 3pm.`, `Session limit reached. Resets at 15:00.`, `API Error: 429 rate_limit_error: ...`, `429 Too Many Requests`, `529 overloaded_error: Overloaded`), each on the error-result path and the failed-exit path; four negatives (`a limited edition`, `sunset at six`, `the presets are fine`, `my limits are mine`); a login text that says "try again" is a login error.

RED: 13 failed, 74 passed (12 wordings across the two paths, and the login order). GREEN: 102 passed over `test_providers_claude_code.py`, `test_provider_timeouts.py`, `test_doctor_live.py`.

## 2. I2: a rate limit is never degraded into a record

What changed:
- `except RateLimitError: raise` ahead of the `ProviderError` clause in `planner/llm_lint.py` (`LlmLint.verdict`), `environments/harvest.py` (`harvest_fallback`), `environments/idle.py` (`idle_fallback`), `environments/runtime.py` (`trigger_fallback`), `environments/generator.py` (`DocWriter.write_fire`).
- `runner/runner.py`: `_pause_for_rate_limit` takes a `Phase` (was a `Slot`; it only read the phase). `_call_target` pauses on a `RateLimitError` from `_idle_info` (before the reply is written: the resumed rep asks the target and the judge again) and from `env.after_target_turn` (after the written reply: `rewatch` redoes it on resume). `run()` also pauses on one from `env.rewatch` (a resume still limited), with the marker after the same target turn; without this an uncaught `RateLimitError` would crash the resume with no marker. `_bully_turn`'s only provider call (`engine.realize`) was already inside its pause; nothing judge-side runs in it, so it needed only the signature change.
- Runbook: the rung 0 checklist (:240) gains "no `rate_limit` line either, on any role"; the rung 1 stop rule (:262) says a `rate_limit` line on a judge-side role pauses like the target's and counts as a pause.

Tests:
- `tests/test_judge_side_rate_limits.py` (new): each of the five passes re-raises; the lint spends no retry (one call) and caches nothing.
- `tests/test_generator_run.py::test_a_rate_limit_in_a_judge_side_pass_pauses_the_run_and_the_resume_redoes_it[lint-llm_lint|harvest-harvest]`: one marker after the written target turn, one `rate_limit` ledger line on the pass's role (the judge wrapped in the run's ledger), no fire recorded, the rep `running`; the resume writes the fire as an unbroken run does, no `error` verdict, no degraded harvest.
- `tests/test_generator_run.py::test_a_resume_still_rate_limited_in_the_rewatch_pauses_again_after_the_same_turn`: the rewatch path (two markers after the same turn, then completion). Checked that it fails with the rewatch `except` disabled.
- `tests/test_runner_idle.py::test_a_rate_limit_in_the_idle_fallback_pauses_before_the_turn_and_the_resume_redoes_it`: no idle turn written, a marker; the resume labels it `ask`/`llm`, `fallback_failed` False.

RED: 8 failed (5 unit, 2 run-level, 1 idle; the idle one printed "idle fallback failed, heuristic label kept: RateLimitError"). GREEN: 1015 passed over the lint, harvest, idle, runtime, runner, runner_env, runner_idle, attempt_marker, ledger and generator-run files; mypy clean. The rewatch test was added after the first GREEN and passes.

## 3. The `claude_bully/atomic.py` bundle with Task 4 M7

What changed:
- `claude_bully/atomic.py` (new, stdlib only: `os`, `tempfile`, `time`, `pathlib`, `typing`): `replace(tmp, path)` (`REPLACE_TRIES` 20, `REPLACE_WAIT_S` 0.05, the temp file removed on the last `PermissionError`) and `write_atomic(path, text)` (mkdir, `mkstemp` in `path.parent` named `.<name>.*.tmp`, UTF-8 bytes, `replace`; the temp file unlinked on any failure, and the descriptor closed if `fdopen` itself fails, else the unlink fails on Windows).
- `runtime._write_atomic` delegates to it; `mcp_server._replace` is gone and `write_mcp_state` calls it; `JudgeCache.put` calls it (the `.tmp` leak closed). Unused `os`/`time`/`tempfile` imports removed. One behaviour note: the runtime's and the judge cache's files were written in text mode (CRLF on Windows); they are now LF bytes everywhere, as the MCP state already was.
- Task 4 M7: `triggers.TRIGGER_PROMPT_VERSION = 1`; `fallback_digest(text, context, model="")` hashes `trigger<version>`, the model, the text and the claims; the watcher passes its `cache_model`; `trigger_fallback(provider, cid, *, model="")` uses the same digest for its conversation id, and `RunEnvironments.open` passes `self.exp.judge.model` (the same value as the watcher's `cache_model`). `idle.fallback_key(reply, model="")` hashes `idle2\0<model>\0<reply>`, and `idle_fallback` passes `getattr(provider, "model", "")`.
- `tests/test_judge.py::test_a_kill_between_the_temp_write_and_the_rename_leaves_the_old_entry` patched `claude_bully.metrics.judge.os.replace`, which no longer exists; it now patches `claude_bully.atomic.os.replace` and also asserts no `.tmp` is left (the one failure of the first full gate run, below).
- Existing pins moved with the formulas: `tests/test_idle.py` (four `idle2\0\0` keys), `tests/test_triggers.py` (two digests), `tests/test_ledger.py` (the trigger hit's id now with `"stub-judge"`).

Tests (`tests/test_atomic.py`, new): LF UTF-8 and no leftover; `replace` waits out two `PermissionError`s; gives up after 20 and removes the temp file; a non-`PermissionError` failure at the rename and at the write leaves no `.tmp` (through `JudgeCache.put`); the three writers go through `atomic.replace`; no `os.replace(` left in the three old homes and `atomic.py` imports only the stdlib; the trigger key changes with the model and the version; the trigger conversation id carries the cache digest and two models make two entries; the idle key changes with the model and another judge re-asks.

RED: 4 failed, 3 passed (the leak in both places, the three writers, the leftover loops), then 3 failed for M7. GREEN: 10 passed; the trigger, idle, ledger, runtime and runner-idle files 2799 passed after the pins moved (2 trigger pins were the only failures before they moved).

## 4. Task 8 m1: the arms by (model, condition, arm)

What changed (`analysis/generator.py`): `_conversations` yields (key, model, condition, arm), the condition from the cell spec (else the cell record's `condition_name`); `arm_rates` groups by (model, condition, arm), keys an entry by its arm when it is the arm's only condition for the model, else `<arm>/<condition>`, and sorts by model, arm order, condition. `ArmRates.condition` (additive). `generator_chart` draws every entry in that order and labels a shared arm's bar `<arm>\n<condition>`.

Tests: `tests/test_generator_analysis.py::test_two_conditions_in_one_arm_are_never_pooled` (the shipped config keeps `off`, `non_reflexive`, `reflexive`, each naming its condition; with the flat cell's condition moved onto the reflexive environment the entries are `off`, `reflexive/rescue_gen_flat`, `reflexive/rescue_gen_reflexive`, two reps each, never four; the JSON and the tick labels follow). `RATE_KEYS` gains the new keys.

RED and GREEN with item 5 below.

## 5. The rejection counts per kind

What changed: `ArmRates` gains `fires`, `written`, `cached`, `rejected` (`cap`, `contract`, `lints`), `errors`, `llm_lint` (`fail`, `error`), defaults zero; `_fire_counts` reads the entry's kept conversations' `GeneratorFire` records. `generator.json`'s arm entries carry them beside `docs_written` (the counts are totals over the entry's reps; `docs_written` stays a mean). Runbook: the 1b note and the rung 3 stop rule read these counts before the raw records.

Tests (`tests/test_generator_run.py`, on real run records): the writer-error test gains `fires 1, errors 1`; the cap test `rejected.cap 1`; new `test_generator_json_counts_the_fires_by_outcome_and_the_lint_verdicts[lint_fail_then_pass|lint_undecided|off_contract]` (a billboard then a pass: written, `llm_lint.fail` 1; two off-contract lint replies: `rejected.lints` 1, `llm_lint.error` 2; two off-contract generator replies: `rejected.contract` 1).

RED (items 4 and 5): 7 failed, 8 passed (`'ArmRates' object has no attribute 'fires'`, the key list, the split). GREEN: 36 passed over both files.

## 6. I3: the probe ledgered

What changed (`scripts/llm_lint_probe.py`): `main` checks its arguments, then activates a ledger at `<--state>/ledger.jsonl` around building the lint and running it (the stub path wraps its `StubProvider`, so the test sees lines), and in a `finally` prints `Calls: <calls_line>` (or `none`) and `Ledger: <path>`. Runbook 1b: both probe commands pass `--state output/phase7_rung1b_<date>/lint_probe_state`; the paragraph names the `Calls:`/`Ledger:` lines, says the second run's line counts both, and that the Calls table adds them under `llm_lint`.

Tests: `tests/test_llm_lint.py::test_the_probe_ledgers_its_calls_under_state_and_prints_the_calls_line[probe|stances]`. The old `test_the_probe_script_scores_on_the_stub_rules` now passes `--state tmp_path`: without it, the first GREEN run wrote `output/llm_lint_probe_state/ledger.jsonl` into the working tree (git-ignored; deleted).

RED: 2 failed. GREEN: 34 passed.

## 7. Minor riders

- M1: `analysis/run_analysis.py`'s docstring names both analysis-time calls (the pair judge and the authority fallback).
- M8: HANDOFF Progress items 5 and 6 read "`LINT_PROMPT_VERSION` 1, now 2" and "`AUTHORITY_FALLBACK_VERSION` 1, now 2".
- M10: runbook :230-231 rewrapped (and the paragraph it ran into).
- M4: docs/00 H's cache-key sentence names the trigger and idle keys' fix and the pair judge's whole-prompt key, and says every cache entry goes through `atomic.py`; now true.
- L55: `cli.run` raises `typer.BadParameter("'<glob>' matches no cell of '<exp>'", param_hint="--only")` before anything runs or is written, dry run included. Test `tests/test_cli.py::test_run_only_matching_no_cell_is_a_bad_parameter[run|dry_run]`; RED 2 failed, GREEN 18 passed.
- M5: no code change needed. `EnvironmentSession._complete` already calls `_recover` (which folds the server ledger) in its `except BaseException` path, so a failed target call's responder lines are folded; the review's reading ("only after a successful target call") missed that path. Pinned by `tests/test_ledger.py::test_a_failed_target_call_still_folds_the_servers_responder_lines` (fake `claude -p` in `stream_malformed` mode: the tool runs, the stream fails; one `error` target line, one `ok` responder line at turn 1, the server file empty). It passed at once; checked that it fails with that `_recover` call removed.

## Docs-sync

- Spec "As planned": a "Final review" block (I1, I2, the bundle with M7, m1, the fire counts, I3, the riders).
- docs/00-RECONCILED.md H: a "Phase 7a final fix wave (version 3, additive; analysis output and cache keys only)" line listing the `generator.json` additions and the key changes; the M4 sentence.
- HANDOFF: "Last updated"; setup step 5's counts; M8; a Progress entry "Phase 7a final review and fix wave" with the gate counts; Next steps item 1 is now the scoped re-review; the "Parked, and must land before Phase 7" block removed and closed as a line under "From Phase 3"; the two "bundled below" references and the "For Phase 7" bullet closed; the resume prompt.
- Runbook: as listed per item (rung report limit text, step 0 past tense, :230-231 wrap, :240, :262, the 1b probe state and calls line, the 1b and rung 3 count reads).

`SCHEMA_VERSION` stays 3: no record changed. Golden plain fixtures untouched.

## Gate

Run once over the finished tree, then the fast suite and the three static checks again after one test fix:

- `uv run ruff format --check .`: 275 files already formatted.
- `uv run ruff check .`: All checks passed.
- `uv run mypy claude_bully`: no issues in 110 source files.
- `uv run pytest -q -W error`: first run 1 failed, 8406 passed, 5 skipped, 8 deselected; the failure was `tests/test_judge.py::test_a_kill_between_the_temp_write_and_the_rename_leaves_the_old_entry`, which patched `claude_bully.metrics.judge.os.replace` (gone with the bundle). Repointed at `claude_bully.atomic.os.replace` (plus a no-`.tmp` assertion); the rerun: **8407 passed, 5 skipped, 8 deselected**, 0 warnings (BASE 8354 passed: +53).
- `uv run pytest -q -m slow`: **8 passed**, 8412 deselected (BASE 8).

## Files changed

New: `claude_bully/atomic.py`, `tests/test_atomic.py`, `tests/test_judge_side_rate_limits.py`.

Modified: `claude_bully/analysis/generator.py`, `claude_bully/analysis/run_analysis.py`, `claude_bully/cli.py`, `claude_bully/environments/generator.py`, `claude_bully/environments/harvest.py`, `claude_bully/environments/idle.py`, `claude_bully/environments/mcp_server.py`, `claude_bully/environments/runtime.py`, `claude_bully/environments/triggers.py`, `claude_bully/metrics/judge.py`, `claude_bully/planner/llm_lint.py`, `claude_bully/providers/claude_code.py`, `claude_bully/runner/env_turn.py`, `claude_bully/runner/runner.py`, `scripts/llm_lint_probe.py`, `tests/test_cli.py`, `tests/test_generator_analysis.py`, `tests/test_generator_run.py`, `tests/test_idle.py`, `tests/test_judge.py`, `tests/test_ledger.py`, `tests/test_llm_lint.py`, `tests/test_providers_claude_code.py`, `tests/test_runner_idle.py`, `tests/test_triggers.py`, `HANDOFF.md`, `docs/00-RECONCILED.md`, `docs/handoff/phase-7-runbook.md`, `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md`.

## Self-review findings

- The rewatch path was not in the scope's list but is needed: once the passes re-raise, a resume still under the limit would raise out of `rewatch` in `run()` with no marker. Added the pause there and a test.
- The idle-label pause comes before the reply is written, so the resumed rep re-calls the target (one more target call, and the redone reply may differ). That is the ruling's "the rep resumes and redoes the pass"; the alternative (write the turn without its label) would put a degraded record on disk.
- `ArmRates` key order in `generator.json` changed by addition only; `tests/test_generator_analysis.py` pinned the exact key list, updated.
- The trigger and idle key changes make every existing entry under `runs/_cache/triggers/` a miss (by design, M7); the runbook already moves `runs/_cache/` aside before rung 0.

## Issues or concerns

- Login first on error results (as ruled) has a reverse risk: a limit message that also mentions logging in (for example a hint like "run /login to switch accounts") would now be a login error and stop the rep instead of pausing, because `_LOGIN`'s `\blog ?in\b` matches "/login". None of the known wordings does this. If rung 0 meets one, the fix is to test the word-bounded limit phrases before `_LOGIN` and only `try again` after it. The rung report's exact-text record is what would show it.
- A sixth swallow, outside the five the scope names: `environments/authority.py:758` (`_respond`) turns any `ProviderError` from the in-process responder, a `RateLimitError` included, into a lost reply. On the `claude -p` path the responder runs inside the MCP server, where re-raising would only kill the tool call; on the API path it could pause like the others. Left as is; worth a ruling.
- `runner/store.py: _keep_only` still does a bare `os.replace` with no `PermissionError` retry (a fourth atomic write, not among the three the bundle names). It could call `atomic.replace`; not done, to keep to the scope.
- The review's I1 premise that a plain `ProviderError` marks the rep `aborted` does not match the code: a target `ProviderError` propagates out of `run_experiment` with the rep still `running` (only non-compliance aborts). The I1 fix stands either way (a miss still stops the run instead of pausing it), but a rerun resumes rather than skips.

## Re-review follow-up (final-rereview.md: N1, N2, N3)

One new commit on top of 987f8d4 (no amend).

### N1 (Important): a pause in the after-work lost the reply's captures and its termination

What changed (`claude_bully/runner/runner.py`):
- `_replay` calls a new `_recapture(line, reply)` for every written (bully line, reply) pair. It re-applies `capture_as` and, after a reveal (`intent_phase == reveal`), `post_reveal` from the line's `bully_meta`, as the live path does. `_capture` keeps one already made, so a rep resumed after an ordinary pause or kill is unchanged.
- `run()`, after `rewatch` (so the turn's records are whole), calls `_ended_unchecked(pending)`. When no bully line is pending and the last written turn is a non-idle target reply that `_terminates` (text empty or `[END]`, not a tool-cap cutoff), the rep finishes as terminated, as the live run would have. Limitation: this reads the record alone, so a `refusal` stop reason, which no turn keeps, is not re-derived. The docstring says so.

Test: `tests/test_after_work_pause.py::test_a_pause_in_the_after_work_keeps_the_capture_and_the_termination`.
- The setup is a stub env run whose second bully line carries `capture_as: probe` and is the reveal, and whose second reply is `[END]`.
- The runtime's after-work (the trigger watch, a judge-side pass) is rate-limited once, on that reply's turn (3).
- The unbroken run terminates at turn 3 with both captures.
- The paused run has a marker and no captures. After resume it is `complete`, `terminated_by_target` at turn 3, its captures equal the unbroken run's, and its real turns equal the unbroken run's: no bully line after the `[END]`.

RED: 1 failed, `assert (False, None) == (True, 3)` on the resumed conversation; the unbroken run's assertions passed. GREEN: 1 passed. Each half is load-bearing:
- With `_recapture` disabled, the test fails on `captured_responses`.
- With the termination check disabled, it fails on `terminated_by_target`.

### N2 (Minor): runbook :246 and :270

The rung 0 checklist now says a judge-side pass's `rate_limit` line comes with a pause marker, but the responder's does not. Inside the MCP server a limited responder is a `rate_limit` line on role `responder` plus a lost reply (`No reply.`), with no pause, as ruled. The rung 1 stop rule says such a line pauses nothing, reads as a lost consult, and the rung report names it as a limit. I also rewrapped the paragraph's tail.

### N3 (Minor)

- HANDOFF's "The generator arms' first real run (Task 8)" bullet now points at the new per-entry fire counts.
- docs/00 H says the counts are totals over the entry's kept reps, while `docs_written` is a per-rep mean.

Also synced:
- The spec's "Final review" block gains an N1 bullet.
- HANDOFF's Progress entry records the re-review and the follow-up.
- HANDOFF's setup step 5 count is now 8408.

### Gate (once, after the fixes)

- Covering tests (`tests/test_runner*.py`, `tests/test_wait_and_promote.py`, `tests/test_ledger.py`, `tests/test_after_work_pause.py`): 232 passed.
- `uv run ruff format --check .`: 276 files already formatted.
- `uv run ruff check .`: All checks passed.
- `uv run mypy claude_bully`: no issues in 110 source files.
- `uv run pytest -q -W error`: **8408 passed, 5 skipped, 8 deselected**, 0 warnings.
- `uv run pytest -q -m slow`: **8 passed**, 8413 deselected.

Files: `claude_bully/runner/runner.py`, `tests/test_after_work_pause.py` (new), `docs/handoff/phase-7-runbook.md`, `HANDOFF.md`, `docs/00-RECONCILED.md`, `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md`.
