# Task 4 report: doctor --live, the nine preflights, check 4b and the JSON report

Commit: fb19c95 "feat: doctor --live runs the nine preflights and the thinking-block check, with a JSON report" (on 9d4b7d2, build/v1, not pushed).

## What was implemented

- `claude_bully/doctor.py` (new), from the brief's code block: `DOCTOR_REPORT`, `DOCTOR_SUCCESSOR`, `CHECK_NAMES`, `INFORMATIONAL`, `CheckResult`, `mini_worlds_dir`, `default_out_dir`, `run_live_checks`, `write_report`, `failed`, plus the ten check functions. Every subprocess the doctor spawns runs under `clean_child_env()` (P12).
- `claude_bully/metrics/judge.py`: `strip_fences = _strip_fences` (P7).
- `claude_bully/cli.py`: the `doctor` command as in the brief (`--live`, `--out`, `--runs-root`; the offline `--version` run is under `clean_child_env()`; `activate(out_dir / LEDGER_FILE)`, `run_live_checks(..., runs_root=runs_root, repo_root=REPO_ROOT)`, `write_report`, one line per check, the report path, exit 1 when `failed(results)`). Removed `_mini_worlds_dir`, `_doctor_mcp_round_trip` and the imports nothing else used (`tempfile` stays).
- `tests/test_doctor_live.py` (new): the brief's 4 tests.
- `tests/test_cli.py`: deleted the 5 live tests and the 2 helpers (`_FakeLiveClaude`, `_live_doctor`). Patched `test_doctor_offline_has_no_mcp_check_and_never_builds_a_provider` as the brief says. Removed `import json`, which was now unused.
- Docs sync:
  - HANDOFF.md: the Progress item 4, the "For Phase 7" responder line ("Built: ..."), the Task 3 range filled with `bd063e4..9d4b7d2`, and the "Last updated" and Next-steps lines (Tasks 1 to 4 done).
  - docs/00-RECONCILED.md: the section E line.
  - The spec's "As planned" gains a Task 4 block: P30a, P30b, the module split, the report and exit rule, and the clean children.

Carries:
1. Carry 1 (MCP_TOOL_TIMEOUT is inherited): no change was needed. The brief's assertion already checks only the `CLAUDECODE` and `CLAUDE_CODE_` prefixes and never asserts `MCP_TOOL_TIMEOUT` absent on the nested entry. The spec amendment records that the nested responder inherits it.
2. Carry 2 (`thinking_seen` reset): moved above `self._write_mcp_config()` in `ClaudeCodeProvider.complete`. `tests/test_provider_timeouts.py::test_the_stream_reports_whether_a_thinking_block_was_seen` covers the reset and passes.
3. Carry 3 (`ProviderTimeoutError`, `login_error_exit`): the doctor never names the timeout class or the substring, so nothing needed changing there. `test_doctor_live_exits_1_when_not_logged_in` runs the exit-0 mode as written, then runs again on `login_error_exit` into a second out dir and asserts exit 1, `login.ok is False` and "not logged in". For this, `_live` gained a `name=` keyword.
4. Carry 4 (`resolved_model`): check 2's detail prints `reply.resolved_model or reply.model`. The test asserts `stub-sonnet-20260101` is in it.

## Tests and results (the gate, run once before the commit)

- `uv run ruff format --check .`: 258 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 106 source files
- `uv run pytest -q -W error`: 8225 passed, 5 skipped, 6 deselected. This is 8226 at BASE, minus the 5 deleted tests, plus the 4 new ones.
- `uv run pytest -q -m slow`: 6 passed, 8230 deselected

## TDD evidence

- RED: `uv run pytest tests/test_doctor_live.py -q` gave `ImportError: cannot import name 'doctor' from 'claude_bully'` during collection (1 error). This was expected because the module did not exist yet. The brief predicted `ModuleNotFoundError`; with `from claude_bully import cli, doctor` it surfaces as an ImportError with the same cause.
- First GREEN attempt: `uv run pytest tests/test_doctor_live.py tests/test_cli.py -q` gave 1 failed and 2 errors, with two causes:
  - `ruff check --fix` had removed the "unused" `resolve_claude_command` import from doctor.py, which the fixture patches. It was restored as an explicit re-export.
  - `test_replay_reads_the_world_from_the_run_not_from_the_world_files` patched `cli.load_world`, which the brief's import cleanup removed (see concerns).
- GREEN: the same command gave 20 passed in 34.77s.
- Inspected doctor.json from a run on the fake:
  - All ten checks were ok. `thinking` was "yes: ...". `responder` was "the nested responder answered in 264 ms". `login` was "replied 'reply to: ping'; model stub-sonnet-20260101".
  - The ledger held 6 `doctor` lines (one with effort low) and 1 `responder` line, `doctor/responder/rep0/authority/mcp-1-1`.

## Files changed

- claude_bully/doctor.py (new)
- claude_bully/cli.py
- claude_bully/metrics/judge.py
- claude_bully/providers/claude_code.py
- tests/test_doctor_live.py (new)
- tests/test_cli.py
- HANDOFF.md
- docs/00-RECONCILED.md
- docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md

## Self-review

- Every brief requirement is met: the Interfaces names and signatures, the `__all__` contents, P6, P12, P22, P30a/b, P34a, C21 and the `--out` ruling.
- No test writes under the real `runs/` or the repo's `output/`: after the suite, `runs/` holds only `.gitkeep` and `output/` does not exist.
- The doctor's scratch `tempfile.TemporaryDirectory` lives in the system temp directory, not under tmp_path, as the old CLI code's did. It is removed on exit.
- No real names. `Pennet Assist 4 Final` is invented, per the brief. No emojis, LF.
- The reasoning channel stays private: check 4b reports yes, no or unknown, never text.

## Issues or concerns

1. One test edit beyond the brief's list. `test_cli.py::test_replay_reads_the_world_from_the_run_not_from_the_world_files` had `monkeypatch.setattr(cli, "load_world", no_worlds)`. The brief's cleanup drops `load_world` from `cli`, so that line raised AttributeError. I deleted the line: cli can no longer call `load_world`, and the module-level patch of `claude_bully.environments.world.load_world` stays. In total 2 tests are patched, not 1.
2. The brief's patched offline test, `monkeypatch.setattr("claude_bully.doctor.run_live_checks", explode)`, is weak. `cli` binds `run_live_checks` by name at import, so the patch would not catch a live call from the offline path. The offline path's early `return` is what really guards it. I used the brief's line verbatim. A stronger pin would be `monkeypatch.setattr(cli, "run_live_checks", explode)`; this is the controller's call.
3. `resolve_claude_command` in doctor.py is unused by the code. ruff F401 removes it, so it is kept as an explicit re-export (`resolve_claude_command as resolve_claude_command`) with a comment, for the brief's dual patch.
4. Spec check 5 asks for "an AuthorityCall with a reply that is not `NO_REPLY_TEXT`". The brief's code checks only that an AuthorityCall exists and does not import `NO_REPLY_TEXT`, though the Interfaces list it. The two are equivalent: the desk writes no AuthorityCall when the responder is lost (`authority.py` returns `NO_REPLY_TEXT` with status error before an `AuthorityCall` is built). I kept the brief's code.
5. P30a and P30b are written into the spec's "As planned" as amendments that need the owner's sign-off at this task's review.

## Fix round 1 (review task-4-review.md)

Commit: a40dc62 "fix: doctor --live starts each run on a fresh ledger, check 7 reads the flag off its line, and the review's test pins" (a new commit on fb19c95, not pushed).

What changed, per item:
- I1 (a rerun mixed two ledgers):
  - `cli.py` unlinks `out_dir / ledger.jsonl` before `activate`.
  - Check 5 now reads only the lines it folded itself (`ledger.lines()[-folded:]`), so it can never print a previous run's latency.
  - New test `test_a_rerun_into_the_same_dir_reports_only_its_own_calls` runs the doctor twice into one `--out` and asserts that the second report's ledger, and `ledger.jsonl`, hold one run's lines.
  - RED, with the unlink replaced by `pass`: `assert 14 == 7`. GREEN with the fix.
- I2 (the inert offline patch): `test_cli.py` now patches `cli.run_live_checks` and `claude_bully.doctor.ClaudeCodeProvider`.
- I3 (the vacuous P22 assertion): the e2e test asserts `tmp/repo/output` is a directory after the run. It also asserts that the real repo's `output/` exists exactly as it did before the run. That check only reads the tree, never writes it.
- Spec gap (check 7): `_check_effort` passes only on a reply plus `effort == "low"` on the newest `doctor-effort` ledger line. With no ledger active it fails with "no doctor-effort ledger line".
  - New test `test_the_effort_check_reads_the_flag_off_its_ledger_line` pins both sides: without an activation it fails, and with one it passes.
  - The e2e test asserts "effort low" in the detail.
- M1: `_mcp_provider(command, tmp, worlds_dir)` builds check 4's provider before the call, and `mcp_provider` is assigned before `_check_mcp(provider)` runs, so checks 4b and 9 read it even when the call raised.
- M2:
  - Check 5 catches the outer call's exception and folds the server ledger whatever happened.
  - Every failure detail names the nested line ("the nested line is <status> after N ms") or "no nested ledger line".
  - "(see stderr)" is gone.
- M4: one `except Exception` in `_timed`.
- M5: `run_live_checks(command, *, runs_root, repo_root)` has no `out_dir`, and `CheckResult` has no `cost_usd`. The CLI call is updated. The JSON test did not reference either field.
- M6: the `resolve_claude_command` re-export in `doctor.py` and the fixture's patch of it are removed.
- M7: `failed` and `INFORMATIONAL` are added to `doctor.__all__`.
- M8: the bare `assert` in `run_live_checks` is dropped. The e2e test's `tuple(checks) == CHECK_NAMES` pins the order. The `mcp_state_dir is None` case in `_check_mcp` returns a failed result instead of asserting.
- M11: `default_out_dir` uses the local date. `doctor.json`'s `date` stays a UTC timestamp.
- The spec's "As planned" Task 4 block gains a "Task 4 review" bullet covering the interface amendment (`out_dir`, `cost_usd`, `__all__`), the fresh ledger, check 7, M1, M2 and the local date.
- Not in this round (not in the controller's list): M9 (exact `.gitignore` match), M10 (the fake's MCP-server environment and `--version` branch), and M12 (the HANDOFF "9d4b7d2..Task 4 commit" placeholder, left for the controller's docs sync).

Covering tests:
- `uv run pytest tests/test_doctor_live.py tests/test_cli.py tests/test_ledger.py -q`: 52 passed.

Gate:
- `uv run ruff format --check .`: 258 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 106 source files
- `uv run pytest -q -W error`: 8227 passed, 5 skipped, 6 deselected (8225 + 2 new tests)
- `uv run pytest -q -m slow`: 6 passed
- After the suite, `runs/` holds only `.gitkeep`, and `output/` does not exist.
