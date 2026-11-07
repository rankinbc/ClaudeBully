# Task 1 review: the test-suite guard and the cost ledger (e40aa28..9331c65)

I reviewed the 1750-line diff package in two passes: the production code first, then the tests and docs. I also ran seven focused checks outside the diff (A to G), each listed below with the risk it answers. I ran no test, because no doubt came up that the reported runs leave open. I mutated no file.

### Spec Compliance
- Spec compliant. I checked the brief's file list against the diff stat file by file. All 18 files are present (the 2 created, the 15 modified and the spec amendment), and no file outside the list was touched.
  - `claude_bully/providers/ledger.py` matches the brief's text. That covers `LEDGER_FILE`, `ROLES`, `LedgerStatus`, `LedgerLine` (extra="forbid"), `role_of` (cell shape first, P6), `parse_conversation_id` and the single `_line` builder (P35b). It also covers `Ledger.fold` with the P36b docstring, the delegating `LedgerProvider`, `activate`, `active`, `note_turn`, `note_cached`, `fold_server_ledger` and `wrap`.
  - The rest of the wiring also matches the brief:
    - the `build_provider` wrapping and `Completion.resolved_model`;
    - every `note_turn` site and every `note_cached` site;
    - the trigger watcher's `cache_label`/`cache_model` plumbing (P38);
    - the generator's note after `_check` (P4);
    - the `analyze_run` activation around the judge build (P8);
    - the MCP server's own ledger with `turn = state.turn`, and the `_recover` fold;
    - the conftest guard (P33) and `output/` in `.gitignore`.
  - Neither the fixtures under `tests/fixtures/golden/` nor `records.py` (`SCHEMA_VERSION`) appears in the diff stat, so the plain records and schema version 3 are untouched.
  - docs/00 sections B, E and H, the HANDOFF entry and the spec's "As planned" section are present. The test file adds 13 new test functions, as the brief says.
- The report's five concerns, judged on their merits:
  1. I accept the changed analysis test. `_ask` writes the cache after the first call, so a repeated prompt within one pass is a real hit. Spec section 4 says "A cache hit writes a line with `status: cached`", so the hit must be noted. The brief's "all ok" on the first pass was the defect. The new assertions hold up:
     - lines with status `ok` exist;
     - every first-pass line has `turn is None`;
     - every non-ok id repeats an `ok` id.

     The second-pass assertion is unchanged (tests/test_ledger.py:212-232).
  2. Removing the unused `load_stub_script` import is fine.
  3. Both places where the code differs from the spec follow the plan:
     - `effort` is implied by spec section 9 check 7 ("the flag in the ledger line");
     - `timeout` is in the spec's status vocabulary.

     Both are recorded in the spec's "As planned" section. Neither is a finding, but the substring match is fragile (Minor 4).
  4. The HANDOFF placeholder is real (Minor 1).
  5. The `__getattr__` recursion is real (Minor 3).
- Cannot verify from diff:
  - The commit author and trailer. The diff file lists only the commit subject. The controller should run `git log -1 --format='%ae%n%B' 9331c65` and expect `rankinbc1@gmail.com` and `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
  - LF endings. The report says `git diff --check` is clean, but CRLF is not visible in a diff. The controller should run `git ls-files --eol` on the 18 files.
  - The gate counts (8207 passed, 5 skipped, 6 deselected, 6 slow, 0 warnings). These come from the report; I did not observe them.

### Strengths
- **The wrapper is transparent to every call site.** Check A tested two risks: `isinstance` or `type()` on a built provider, and attribute writes that would land on the wrapper and never reach the inner provider. A grep over `claude_bully/` found neither. The one structural read is `getattr(target, "mcp_state_dir", None)` (claude_bully/runner/env_turn.py:1256). It goes through `__getattr__`, and tests/test_ledger.py:140-145 pins it.
- **Every run-time build happens under the activation.** Check C tested whether a provider built before `with activate(...)` in `run_experiment` would go unledgered. `RunEnvironments.__init__`, `validate`, `check_worlds` and `world_hashes` build no provider. The environment judge is built lazily in `judge()` (env_turn.py:985-990), and its first call is from `open()` (env_turn.py:1258), inside the loop. The runner's own builds (runner.py:799, 804) are inside the block.
- **The guard cuts the API clients.** Check B tested whether a `from anthropic import Anthropic` bound at import time would escape the module-attribute patch. Both backends look the class up when they construct: `anthropic.Anthropic()` (anthropic_api.py:31) and `openai.OpenAI(...)` (openai_compat.py:112). So `patch.setattr` takes effect. `_NoRealClient` constructs and raises only on use, so the two `build_provider` API tests are unchanged.
- **The `command` scan covers every role.** Check F tested whether a responder role in YAML could carry a `command` the scan misses. No responder role is written in YAML: `_responder_role` derives it from the target or the bully (env_turn.py:1364-1374). Scanning targets, bully, judge and generator therefore covers every role.
- **The `model` field is the configured alias, as spec section 4 requires.** Check G tested whether a backend's resolved id in `Completion.model` would split per-model totals. Every backend sets `model=self.model` (claude_code.py:334, anthropic_api.py:134, openai_compat.py:164, stub.py:170).
- **Provider errors are mapped.** Check E tested two risks: failures that are not a `ProviderError` write no line, and the timeout label depends on message text. `claude_code.py:368` raises "claude -p timed out after ...", which the substring match catches. Every other failure path in the four backends maps to `ProviderError` or `RateLimitError`. The remaining gaps are Minor 4.
- **`activate` pops in `finally`.** A `RateLimitExit` out of the cell loop cannot leave a ledger active for the next test.
- **The integration tests check real records, not mocks.** The fold test drives the fake `claude` through a real MCP server (tests/test_ledger.py:269-297). It checks the responder line count against `authority.jsonl`, checks the turn numbers, and checks that the server file is emptied.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **HANDOFF.md:5 and HANDOFF.md:171: stale and placeholder text.**
   - Line 5 now says Phase 7a is in progress, yet still ends with "Next is the owner's ruling on the Phases 4 to 9 drafts ... with Phase 7a first", which contradicts Next steps item 1.
   - Line 171 reads "(e40aa28..Task 1 commit)".
   - Why it matters: a reader picking the work up on another machine gets two different "next" items.
   - Fix: end line 5 with "Next is Phase 7a Task 2", and fill in the range `e40aa28..9331c65` in the next docs commit.
2. **tests/test_ledger.py:235-266: the test name claims more than the test checks (plan-mandated).**
   - `test_a_paused_run_records_the_pause` asserts that every line is `ok`. The rate-limited call goes through the factory's test double, outside `build_provider`, so no `rate_limit` line is written.
   - So no test pins spec section 9's "the ledger records each rate-limited call as a `rate_limit` line" at run level. Only the wrapper unit test (tests/test_ledger.py:191-197) covers it.
   - Why it matters: a later change that breaks the run path's rate-limit line passes the suite.
   - Fix: have the double raise inside a wrapped provider, for example `return wrap(Dying())` from `claude_bully.providers.ledger`. Then assert exactly one `rate_limit` line with `role == "target"`. If the test keeps its current assertion, rename it.
3. **claude_bully/providers/ledger.py:208: `__getattr__` recurses when `_inner` is unset.**
   - `copy.copy`, `pickle` and any `object.__new__` path call `hasattr(obj, "__setstate__")` before `__init__` has run.
   - That call re-enters `__getattr__("_inner")` and raises `RecursionError`, not `AttributeError`. Nothing copies a provider today, so this is latent.
   - Fix: make the first line `if name == "_inner": raise AttributeError(name)`, or delegate through `self.__dict__["_inner"]`.
4. **claude_bully/providers/ledger.py:229: brittle and incomplete error classification.**
   - `timeout` is decided by the substring "timed out". Task 3 adds provider timeouts and is free to word their message differently.
   - An exception that is not a `ProviderError` writes no line at all. Examples: an unmapped `anthropic.APIError` subclass, or a stub script's `ValueError`. The smoke rung's check that ledger lines equal provider calls plus cache hits (spec section 5) can then fail silently.
   - Fix: in Task 3, raise a `ProviderTimeout(ProviderError)` and branch on its type. Optionally add an `except Exception` that writes `status="error"` and re-raises.
5. **claude_bully/environments/idle.py:744 and claude_bully/environments/triggers.py:697: some cache hits are not noted, or are hard to pair.**
   - In-memory memo hits (the branch with no cache) are not noted. In a run the cache is always a `JudgeCache`, so this gap is theoretical.
   - The trigger watcher's `cached` lines go under `<conv>/trigger` with no digest. This is plan-mandated (P38): the brief sets `cache_label` that way in `RunEnvironments.open`. The harvest and idle hits carry `/<digest[:16]>`, so Task 2 can pair those hits with the call they saved, but not the trigger hits.
   - Fix: note the memo hits too, and pass the digest along, for example `f"{self._cache_label}/{digest[:16]}"`.
6. **claude_bully/runner/runner.py:782-783: an orphaned comment line.** Re-wrapping a comment after the re-indent left a one-word line, "# sheet". Fix: shorten the comment to one line.

### Assessment
Task quality: Approved
Reasoning: The diff implements the brief and the binding Plan Decisions faithfully. The wrapper is transparent to every call site that reads the built provider, and every run-time build happens under the activation. The one change from the brief, in the analysis test, fixes a wrong expectation rather than weakening a check, and all six findings are polish or latent edges.
