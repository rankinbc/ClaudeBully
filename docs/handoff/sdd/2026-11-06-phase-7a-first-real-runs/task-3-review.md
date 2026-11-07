# Task 3 review: provider timeouts, the clean child environment, resolved_model, the thinking-block fact

Base bd063e4, head 5161884. I read the diff, the brief, the carries and the report. I also ran these named checks outside the diff:
- `claude_code.py:395-433`, the whole `complete()` body. The risk: where the login classification can fire.
- A grep for `subprocess.(run|Popen|...)` in `claude_bully/`. The risk: another `claude` spawn without the clean environment.
- A grep for `timed out|TimeoutExpired|Timeout` in `claude_bully/`. The risk: another provider's timeout loses its `timeout` line when the substring rule is removed.
- A grep for `responder_role(` and `.responder`, plus reads of `env_turn.py:1262-1292`, `env_turn.py:1373-1385` and `mcp_server.py:452-470`. The risk: a responder built without the 120 s.
- `pyproject.toml:47`. The risk: the N818 justification for the rename.

I re-ran no tests.

### Spec Compliance
- Spec compliant against the brief and all five carries. The deviations are justified:
  - The name is `ProviderTimeoutError` because ruff `N` is selected (`pyproject.toml:47`) and N818 requires the suffix.
  - A second responder assertion changed (`tests/test_runner_env.py:1201-1206`), the same kind of edit as Step 4.
  - `COPIED_DIRS` was also annotated (`promote.py:150`) because the carry's premise was wrong. This is harmless.
- Brief file list, item by item:
  - `config.py:32-33`: done.
  - `providers/base.py`:
    - `ProviderTimeoutError` is at `base.py:85`.
    - `timeout_s` is passed inside `_wrapped(...)` (P1).
  - `providers/claude_code.py`:
    - The constants and `_LOGIN` are at `:59-70`.
    - `clean_child_env` and `resolved_model` are module functions (`:73-86`).
    - `__init__` gains `mcp_tool_timeout_s` and `thinking_seen`.
    - `child_env` is there.
    - `parse_stream` sets `thinking_seen` and still drops the text (`:351-356`).
    - The login branch comes after the rate-limit check (`:366-367`).
    - `resolved_model` is passed to the `Completion`.
    - `env=` is on the one `subprocess.run` (`:408-416`).
  - `runner/env_turn.py`: `RESPONDER_TIMEOUT_S` is at `:185` and in `__all__` (`:167`); `responder_role` is at `:193`.
  - `tests/fixtures/fake_claude.py`: the docstring, `RESOLVED_MODEL`, `_ENV_PREFIXES`, the `env` log entry, `modelUsage`, `login_error`, `FAKE_CLAUDE_STRUCTURED`. `serves` is unchanged.
  - The tests: 9 tests in `tests/test_provider_timeouts.py`, matching the brief.
  - HANDOFF, docs/00 (sections A, E, G14, H) and the spec's "As planned" Task 3 block.
- Carries, one by one:
  1. Carry 1 is done:
     - The timeout raises the subclass with the same message (`claude_code.py:417-418`).
     - The wrapper branches on the type and gains `except Exception`, which writes an `error` line and re-raises (`ledger.py:230-235`).
     - Two tests are added (`tests/test_ledger.py:888-904`), and P2 now rests on the type.
     - The grep shows no other provider raises a "timed out" ProviderError, so removing the substring rule loses no classification.
  2. Carry 2 is done (`promote.py:149-150`).
  3. Carry 3 is done: HANDOFF line 5 says "Phase 7a is in progress" once, and the range is `9331c65..bd063e4`.
  4. Carry 4 is done: rounded to one decimal at `analysis/ledger.py:113`, and a 1.7 assertion is added at `tests/test_ledger_analysis.py:933`.
  5. Carry 5 is done: docs/00 section E (`:639`) and the spec's "As planned".
- Cannot verify from diff:
  - **Whether a real `claude -p` login failure exits 0.** The fake's `login_error` exits 0, and the classification exists only on that path (see Important 1). Task 4's live check 2 should look at the exit code and text of a real logged-out run.
  - **Whether a real result's `modelUsage` lists more than one model, and in what order** (see Important 2). Rung 0 or `doctor --live` should log the keys once.
  - **Windows behaviour when the outer 600 s timeout fires on a target that serves tools.** `subprocess.run` kills `claude.exe` and then, on Windows, calls `communicate()` with no timeout. If the MCP server (a grandchild) inherited the pipe handles, that wait can block, and the server and any nested responder become orphans.
    - This is pre-existing (the timeout predates this task); this task does not change it.
    - The controller should check it once on the real stack in 7b.
  - **That `cli.py:247` (`claude --version`) runs under `clean_child_env()`.** That is Task 4's job (P12); the grep shows it does not today.

### Strengths
- The deviations are small, and the report names each one with its reason. The rename is forced by the repo's lint rules, and the reasoning is sound.
- The clean-environment test proves the right thing end to end:
  - It sets `CLAUDECODE` and `CLAUDE_CODE_ENTRYPOINT` in the parent.
  - It reads what the real child process saw from the fake's log.
  - It checks that `MCP_TOOL_TIMEOUT` is present only on the call that serves tools (`tests/test_provider_timeouts.py:53-80`).
- `thinking_seen` covers both directions: True after a stream with a thinking block, then False on the next stream. That proves the per-stream reset (`tests/test_provider_timeouts.py:96-120`). The privacy assertion (`"PRIVATE" not in out.model_dump_json()`) keeps the non-negotiable pinned.
- The `except Exception` in the ledger wrapper is placed after the two typed branches, re-raises, and is tested with a bare `ValueError`, so the ledger cannot silently miss a call.
- `responder_role` collapses three early returns into one exit with a single timeout default. A role that sets its own timeout keeps it, and the test pins all three resolutions.
- The responder reaches the MCP server through `build_provider(state.responder, ...)` (`mcp_server.py:456-462`), so the 120 s really applies to the nested call. The in-process responder path (`env_turn.py:1269-1274`) gets the same role.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **`claude_code.py:421-427` versus `:366-367`: the login classification is only on the exit-0 path.**
   - What is wrong:
     - `_LOGIN` is checked only in `_from_result`, which runs only when `proc.returncode == 0`.
     - The non-zero-exit branch checks `_RATE_LIMIT` against the combined stdout and stderr, but not `_LOGIN`. A logged-out `claude -p` that exits non-zero, the likely real shape, surfaces as `claude -p exited 1: ...`, never as `not logged in`.
     - The fake's `login_error` exits 0 (the `login_error` branch of `tests/fixtures/fake_claude.py`), so the test cannot see the gap.
   - Why it matters: spec section 9's check 2 passes on that classification, and Task 4 consumes it. The rate-limit check already covers both paths, which shows the authors expected error text on non-zero exits.
   - The brief placed the check only in `_from_result`, so this is partly plan-mandated.
   - Fix:
     - Add `if _LOGIN.search(combined): raise ProviderError(f"claude -p is not logged in: {combined.strip()[:200]}")` after the `_RATE_LIMIT` check in the non-zero branch.
     - Give the fake a mode that writes the same error result and exits 1.
     - Add one test.
2. **`claude_code.py:80-86`, `resolved_model` takes the first `modelUsage` key (plan-mandated).**
   - What is wrong: Claude Code's `modelUsage` can list an auxiliary model (a small model for internal steps) beside the main one, and JSON key order is the emitter's, not the main model's.
   - Why it matters: "the exact model behind an alias" is what the ledger and the README attribution read, so a wrong first key mislabels every line silently. `tests/test_provider_timeouts.py:90` pins the first-key choice on a two-key dict.
   - Fix: choose the key with the most `outputTokens` (or `costUSD`), and fall back to the first key on a tie or missing counts. Change the test to a two-key dict where the auxiliary key comes first. Record the ruling change in "As planned".

#### Minor (Nice to Have)
1. **`claude_code.py:80-86` and spec `:88`: the `model` fallback.** The spec's fallback is the init event's `model` (stream path). The code reads the result's own `model`, which a real result likely does not carry, so the fallback probably never fires. The plan ruling chose this, and it is recorded. If the init event is wanted, `parse_stream` could pass it to `_from_result`.
2. **`tests/test_provider_timeouts.py:31-37` and `:76`: the fixture does not clear `MCP_TOOL_TIMEOUT`.**
   - `clean_child_env()` deliberately keeps that key, so an ambient `MCP_TOOL_TIMEOUT` in the developer's shell (for example, a Claude Code settings `env` block) fails `assert MCP_TOOL_TIMEOUT_ENV not in plain["env"]`. The report's concern 4 is the same fact.
   - Fix: add `monkeypatch.delenv("MCP_TOOL_TIMEOUT", raising=False)` to the fixture.
3. **`claude_code.py:356`: `thinking_seen` is never reset at the start of `complete()`.**
   - A stream that exits non-zero, or that ends with no result, leaves the previous stream's value in place, and so does a toolless JSON call.
   - The docstring says "the newest stream", and check 4b reads it right after a successful check 4, so this is harmless today.
   - Fix: set `self.thinking_seen = None` before a stream call, so a failed stream reads as unknown, not as stale.
4. **`config.py:33`: `timeout_s` is not validated.**
   - `timeout_s: 0` or a negative value passes validation and makes every call time out at once.
   - The field is also inert on non-`claude_code` providers, but a responder on the API backend still carries 120. That is plan-mandated ("on both backends") and harmless.
   - Fix: `Field(default=None, gt=0)`.
5. **`claude_code.py:364-367`: rate-limit text wins over a login message.**
   - The rate-limit check runs first, and `_RATE_LIMIT` includes the broad `try again`. A login message that also says "try again" becomes a `RateLimitError`, and the run pauses for hours instead of failing fast.
   - The brief mandates the order. Worth a fixture line, or narrowing `try again`, once real login texts are seen.

### Assessment
Task quality: Needs fixes
Reasoning: The task matches the brief and every carry. The code is clean and well tested. The login classification, though, misses the non-zero-exit path that a real logged-out run likely takes, and Task 4's check 2 depends on it. `resolved_model`'s first-key rule is a plan-mandated fragility, worth fixing before the ledger names models in a README.
