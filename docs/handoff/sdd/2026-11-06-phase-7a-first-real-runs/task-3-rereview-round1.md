# Task 3 re-review, round 1 (5161884..9d4b7d2)

### Finding Verdicts

- **I1: a login error was recognised only on exit 0.** ADDRESSED. `claude_code.py:436-437` (new) checks `_LOGIN` on `combined` inside the non-zero branch, after the rate-limit check at :433-434, and raises `claude -p is not logged in: ...`. For a stream call `combined` is built from `_stream_failure_text` (:472-488), which carries the result event's text, so the stream path names a login too; model text still never reaches it. `fake_claude.py` gains `login_error_exit` (the same error result, `return 0 if mode == "login_error" else 1`) and documents it. `tests/test_provider_timeouts.py:138-146` loops over both modes and asserts `match="not logged in"`; the implementer's RED run showed the exit-1 path producing `claude -p exited 1: ...` before the fix, so the test does catch the defect. Only the toolless path is exercised with exit 1; the stream path shares the branch and is read-verified, not tested (Minor, below).
- **I2: `resolved_model` took the first `modelUsage` key.** ADDRESSED. `claude_code.py:84-100` returns `max(usage, key=output_tokens)`, so the key with the largest `outputTokens`; `max` keeps the first of equal keys, which gives the tie and no-tokens rule; non-dict entries and non-int tokens count 0; falls back to `model`, then None. The test (`test_provider_timeouts.py:88-101`) pins helper-first (`helper-1` 3 vs `main-2` 40 gives `main-2`), tie (`a-1`), no tokens (`x-1`), `model` fallback and `{}` gives None. The spec's "As planned" Task 3 bullet now states the amended rule and says it amends the Plan Decision. Fits the brief (the fact is the model that did the work).
- **M2: the fixture did not clear `MCP_TOOL_TIMEOUT`.** ADDRESSED. `test_provider_timeouts.py` fixture adds `monkeypatch.delenv("MCP_TOOL_TIMEOUT", raising=False)` beside the other two delenvs.
- **M3: `thinking_seen` stale after a failed stream.** ADDRESSED. `claude_code.py:409` resets it to None inside `if tools:` right after `_write_mcp_config()`, before the subprocess runs, so a crash or timeout leaves None. The thinking test now appends a `crash` stream call and asserts `thinking_seen is None` (RED was `assert False is None`). Toolless calls do not touch it, which matches "the newest stream".
- **M4: `timeout_s` accepted 0 and negatives.** ADDRESSED. `config.py:34` is `Field(default=None, gt=0)` (`Field` is already imported and used in the module). `test_the_role_timeout_reaches_the_provider` loops over 0 and -1 and asserts `ValidationError` matching "greater than 0" (RED was DID NOT RAISE). None still means the default (that test's first lines). The spec line says "greater than 0 when set".

### New Breakage in the Fix Diff

None Critical or Important. Minor:
- Minor, `claude_code.py:408-409`: the reset sits after `_write_mcp_config()`, so if that write raises `OSError`, `thinking_seen` keeps the previous stream's value. Moving the reset above the write would close it. Not blocking.
- Minor, `claude_code.py:436`: on the toolless non-zero path `_LOGIN` searches raw stdout plus stderr, so a non-zero exit whose output happens to carry model text containing "log in" or "authenticat..." would be named a login error. The message is still a `ProviderError`, and the rate-limit check beside it has the same exposure by design; the implementer noted the stream/toolless asymmetry. Not blocking.
- Minor, tests: the exit-1 login case is pinned toolless only; no `login_error_exit` call with `tools=` covers the `_stream_failure_text` route.
- Minor, `claude_code.py:93-96`: `isinstance(tokens, int)` also accepts a bool and rejects a float count; the CLI emits integers, so this is theoretical.

### Test-count reconciliation

Reconciled, no gap. The diff adds no `def test_` and no parametrize: `tests/test_provider_timeouts.py` still has 9 test functions (the implementer's own RED run says "4 failed, 5 passed" = 9, and the GREEN run "9 passed"). The new cases are assertions or loops folded into existing tests: the exit-0/exit-1 login loop replaced the single call in `test_a_login_error_...`; the three `resolved_model` cases are extra asserts in `test_the_resolved_model_...`; the 0/-1 refusal is a loop in `test_the_role_timeout_reaches_the_provider`; the crash/None check is appended to the thinking test. pytest counts functions, so 8226 stays 8226. The report's "unchanged count; the fix round extended existing tests" is accurate. The report names the covering tests, shows RED and GREEN output, and a gate (ruff format and check, mypy, `pytest -W error` 8226 passed, slow 6 passed); I did not re-run the suite.

### Out-of-Scope Observations

None.

### Verdict

Fix round: All findings addressed, no new Critical/Important breakage.
