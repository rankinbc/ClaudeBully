# Task 5 report: the LLM reader-address lint for the instructional kinds

Commit: 850b283 "feat: the LLM reader-address lint over the instructional kinds, cached and recorded on the fire" (on a40dc62; author rankinbc1@gmail.com; trailer Claude Fable 5.1). Not pushed.

## What was implemented

- `claude_bully/planner/llm_lint.py`, verbatim from the brief: `LINT_PROMPT_VERSION` 1, `LLM_LINT_ID`, `LINT_HEADER`, `LINT_PERSONA`, `NO_VERDICT`, `MAX_ASKS` 2, `LLM_LINT_SCHEMA`, `lint_prompt`, `lint_key` (`JudgeCache.key("llm_lint", sha256(version\0model\0kind\0body))`), `parse_verdict`, `LlmLint.verdict` and `LlmLint.failures`. Two additions beyond the brief, both part of the deferral fix described below: `verdict(..., defer=None)` and `LlmLint.commit(puts)`, with the `LintCachePut` alias.
- `records_env.py`: `LintSentence`, `LintVerdictValue`, `LlmLintVerdict`, and `GeneratorFire.llm_lint` (`Field(default_factory=list)`, additive). `SCHEMA_VERSION` stays 3.
- `environments/generator.py`:
  - `DocWriter(llm_lint=)` and `DocWriter._lint`.
  - `_from_cache(..., mark)` returns `(doc, verdicts)`. It runs the lint on a hit under `write_fire`'s marker, as attempt 0, and notes the hit only after the lint passes (P4).
  - `_attempts` returns `(doc, found, reply, verdicts)`.
  - `FireOutcome.llm_lint` is set on every outcome `write_fire` returns, error and rejected included.
  - `WorldGenerator.fire` copies the verdicts into `GeneratorFire.llm_lint`.
  - Addition: `FireOutcome.lint_puts`, and `DocWriter.commit` writes them through `llm_lint.commit`.
- `runner/env_turn.py`: `LINT_CACHE_DIR`, `RunEnvironments.lint_cache`, and `_world_generator` builds `LlmLint` on the judge when `judge()` returns one, with its docstring extended.
- `strategies/sheets.py`: `lint_reviewer.md` added to `NON_PERSONA_FILES`.
- Data and fixtures, all verbatim from the brief: `data/personas/lint_reviewer.md`, `tests/fixtures/stub_scripts/llm_lint_rules.yaml`, and `tests/fixtures/lints/instructional_probe.yaml` (four seed items).
- `tests/fixtures/generator_stub.py`: the modes `billboard` and `offcontract_lint`, `mini_writer(llm_lint=)`, `LINT_RULES` and `LintJudge`.
- `scripts/llm_lint_probe.py`, verbatim, with two changes:
  - it adds `Final` to the `typing` import, because the brief's block uses `Final` without importing it and would raise a `NameError`;
  - its usage lines are shortened to `PROBE` and `RULES` placeholders to stay under ruff's E501 limit.
  - The `from scripts.llm_lint_probe import ...` import works as a namespace package, so no `scripts/__init__.py` was needed.
- Docs sync:
  - HANDOFF: the header, Next steps, Progress item 5, the two "For Phase 7" items, and carry 1.
  - docs/00: the B rows (`LlmLintVerdict`, `LintSentence`, and `GeneratorFire` gaining `llm_lint`), section F `lint_reviewer.md`, the section H Phase 7a line, a "Cache homes" paragraph after section H, and section I row 3.
  - Phase 3 spec: "Built as Phase 7a Task 5's `llm_reader_address` lint." added to its residual bullet.
  - Phase 7 spec: a Task 5 block appended to "As planned".

Carries:
1. HANDOFF: "9d4b7d2..Task 4 commit" is now `9d4b7d2..a40dc62`. Task 5's entry uses "a40dc62..Task 5 commit".
2. The facts from Tasks 1 to 4 are used as given:
   - `note_cached` from `providers/ledger.py`. A lint hit is noted as `<conv>/lint/<doc>/cache`, which `role_of` reads as `llm_lint`.
   - The generator hit is noted after `_check` and the lint both accept it (P4).
   - `ProviderTimeoutError`, being a `ProviderError`, becomes an `error` verdict.
   - `lint_cache` sits beside the trigger and generated caches.
3. The probe ships with its four seed items. I did not fill it.

## Tests and results (the gate)

- `uv run ruff format --check .`: 262 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 107 source files
- `uv run pytest -q -W error`: 8252 passed, 5 skipped, 6 deselected (BASE 8227; +25 = 18 new tests in `tests/test_llm_lint.py`, 25 items with the parametrize)
- `uv run pytest -q -m slow`: 6 passed, 8257 deselected

## TDD evidence

RED 1, with the brief's 17 tests:
- Command: `uv run pytest tests/test_llm_lint.py -q`
- Output: `ModuleNotFoundError: No module named 'claude_bully.planner.llm_lint'` (1 error during collection).
- Why expected: this is the brief's Step 2 failure.

GREEN 1:
- Command: the same, after Step 3.
- Output: `24 passed`.

Step 4 focused run (the brief's command): 3 failures in `tests/test_generator_run.py`. The investigation is under "Issues" below.

RED 2, for the deferral fix:
- Setup: `DocWriter._lint` passed `defer=None`, so the lint wrote eagerly, as the brief's code does.
- Command: `uv run pytest tests/test_llm_lint.py::test_the_writer_caches_its_lint_verdicts_only_on_commit "tests/test_generator_run.py::test_a_rep_killed_mid_generation_resumes_to_the_unbroken_records" -q -W error`
- Output:
  - The new test failed with `assert ('rejected' == 'rejected' and [WindowsPath('.../lints/8b3c....json')] == [])`.
  - The resume tests failed at `assert _view(store) == _view(clean)`. The diff was `'cached': True` in the resumed rep against `'cached': False` in the clean rep.

GREEN 2:
- Command: `defer=self._lint_puts` restored, then the Step 4 command.
- Output: `256 passed in 16.81s`.

## Files changed

New:
- `C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\planner\llm_lint.py`
- `C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\data\personas\lint_reviewer.md`
- `C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\scripts\llm_lint_probe.py`
- `C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\fixtures\lints\instructional_probe.yaml`
- `C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\fixtures\stub_scripts\llm_lint_rules.yaml`
- `C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_llm_lint.py`

Modified:
- `claude_bully/records_env.py`
- `claude_bully/environments/generator.py`
- `claude_bully/runner/env_turn.py`
- `claude_bully/strategies/sheets.py`
- `tests/fixtures/generator_stub.py`
- `tests/test_generator_run.py` (not in the brief's list; see Issues 1)
- `HANDOFF.md`
- `docs/00-RECONCILED.md`
- `docs/superpowers/specs/2026-10-24-phase-3-world-generator-design.md`
- `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md`

## Self-review

The edge cases, each with what covers it:
- An off-contract reply is asked once more (the parametrize, plus `test_two_off_contract_replies_reject_the_document`).
- A second off-contract reply gives `error` and `no verdict`.
- A provider error gives `error`, named by its class, and nothing is cached. `ProviderTimeoutError` and `RateLimitError` are `ProviderError` subclasses and take the same path.
- A cache hit the lint rejects is a miss, with 5 marks.
- A non-instructional kind is never asked.
- The lint is off without a provider and under a stub judge.
- P30d: no lint or harvest prompt, and no file of the run, carries the reasoning text.
- The persona passes the three scans and contains no "reasoning".

Manual checks: `scripts/llm_lint_probe.py PROBE --stub RULES` and `--stances --stub RULES` both exit 0. `--stances` formats every deny line, the ones with `{model_name}` included (P23).

Golden plain fixtures are untouched; the suite is green, so they are byte-identical. All new files are LF, with no emojis and no real names.

## Issues and concerns

1. **`tests/test_generator_run.py` changed, although the brief listed it as unchanged.**
   - Its generator runs give the experiment a non-stub judge (`anthropic`, `JUDGE_MODEL`), so by the ruling the lint is on.
   - Their double, `HarvestJudge`, answers every non-harvest prompt with `{"category": "none"}`. The lint correctly reads that as off-contract twice, an `error`, and rejects the `recovery_guide`.
   - Result: 3 tests failed (`written` became `rejected`, and the resume expectations changed).
   - Fix: the seven run sites now use `LintJudge`, which takes the same kwargs. Its `harvest_calls` and `crash_at` behave as before, because lint prompts are answered before `super()`.
   - Line 234's factory-identity test still uses `HarvestJudge`.
   - I chose this over making `HarvestJudge` pass every lint prompt, which would quietly turn the lint off in any run built on it.
2. **Lint-cache writes are deferred to `DocWriter.commit`. This departs from the brief's eager `cache.put` and amends spec section 6, so the owner should rule on it.**
   - The brief's lint cached each verdict as it arrived.
   - A rep killed before its fire line therefore left a lint entry behind. The resumed rep's verdict then read `cached: True` where the unbroken rep's read `False`, which breaks the Review Focus 1 invariant (resumed records equal unbroken records). `test_a_rep_killed_mid_generation_resumes_to_the_unbroken_records` fails on it in two of its four kills.
   - This is the reason P13 defers the generator's own cache. I applied the same rule:
     - `LlmLint.verdict(defer=)` holds the entries back;
     - `FireOutcome.lint_puts` carries them;
     - `DocWriter.commit` writes them through `LlmLint.commit` for a committed fire only.
   - Outside the writer (the probe script, and the brief's standalone tests) a verdict is still cached at once.
   - Covered by the new 18th test, `test_the_writer_caches_its_lint_verdicts_only_on_commit`, and by the resume test.
   - Recorded in the Phase 7 spec's "As planned" Task 5 block and in docs/00's "Cache homes" paragraph.
   - Side effect: a rejected fire caches no verdict, so an identical body is asked again in a later fire.
3. **Minor, left as the brief has it: a lint verdict can be lost from an error fire.** If the generator raises `ProviderError` on attempt 2 after attempt 1's lint verdict, that verdict lives in `_attempts`' local list. The `error` outcome carries only the verdicts of earlier plans, so the docstring's "whatever the status" is not quite true in that case. Fixing it means changing `_attempts`' brief-specified shape, so I left it.
4. **Minor, as the brief specifies: an `error` verdict on attempt 1 triggers a generator retry.** The retry's Fix list then reads `- llm_reader_address: no verdict`, and attempt 2 re-asks the lint. A transient judge failure therefore costs one generator call, and fails closed if it persists.
5. **`GeneratorStub`'s `offcontract_lint` mode is unused.** The brief specifies it, but none of the 17 tests uses it, since the off-contract path is tested on `LlmLint` directly. It is kept as specified.
6. **The brief's script block had a missing import.** `Final` was not imported in `scripts/llm_lint_probe.py`, which is fixed, and its two docstring usage lines broke ruff's E501 limit, which are shortened. Neither changes behaviour.
7. **The probe holds only the four seed items.** The reviewer still has to fill it, per carry 3.


## Fix round 1 (review: task-5-review.md)

Commit: 3e3cc32 "fix: the lint reviewer fails closed, its key holds the prompt's hash, fail closed pinned through the writer, and the filled probe". It sits on top of 850b283; nothing was amended or pushed.

### What changed, per item

- **Important 1: the reviewer fails closed.**
  - `data/personas/lint_reviewer.md`:
    - the blanket pass for "a quoted line attributed to a named person" is gone;
    - new paragraph: "Points 1 to 3 come first: a sentence that does any of them fails even when it is also third-person procedure, a bare instruction or service text. A quoted line attributed to a named person passes only when the quoted words themselves would pass as ordinary speech in that world; a quote that does any of points 1 to 3 fails like any other sentence.";
    - new line: "If you cannot tell whether a sentence is written for the one reader, it is: fail it."
  - `_DEFINITIONS` in `claude_bully/planner/llm_lint.py` says all three in the user message too.
  - `LINT_PROMPT_VERSION` is 2.
  - The texts say "points 1 to 3", not "rules": `data/denylists/boundary.txt` bans `\brules?\b`.
  - Names: no model, maker or product appears. The three scans are still clean, and so is the "reasoning" check.
  - The stub rules match only `LINT_HEADER`, `BILLBOARD` and `OFFCONTRACT`, so they needed no change.
  - New test: `test_the_reviewer_fails_closed_and_judges_a_quote_by_its_words` (both texts, whitespace-squashed).
  - Updated pins: the key test's version assert, and `test_a_pass_verdict_is_cached...` (now `LINT_PROMPT_VERSION`).
- **Important 2: fail-closed pinned through `DocWriter` and in a run.** Four new tests in `tests/test_llm_lint.py`:
  - `test_two_off_contract_lint_replies_reject_the_document_in_the_writer`, with `GeneratorStub(["offcontract_lint", "offcontract_lint"])`. It checks:
    - the fire is rejected for `lints` with no docs;
    - the verdicts are `["error", "error"]`, each error off-contract;
    - `lint_failures == [no verdict]`;
    - the judge made 4 calls;
    - no lint-cache file;
    - the retry prompt holds `NO_VERDICT_FIX` and not "no verdict" (M2).
  - `test_a_lint_provider_error_rejects_the_document_in_the_writer`, with `_Down()`: two `("error", "ProviderError")` verdicts, the same rejection, two generator calls, no cache file.
  - `test_an_undecided_lint_rejects_the_document_in_a_run`, parametrized `off-contract` (the stub mode) and `provider error` (a `LintJudge` subclass that raises on lint prompts). Read from the `GeneratorFire` records:
    - the first fire with lint verdicts is `rejected`/`lints` with no doc ids;
    - its verdicts are `["error", "error"]` and its `lint_failures` are `[no verdict]`;
    - the lint-cache file count equals the committed fires' fresh verdicts.
  - The `offcontract_lint` mode is now used (M9).
- **M1: an error fire keeps every verdict.**
  - `DocWriter` keeps the fire's verdicts on `self._verdicts`, beside `self._lint_puts`, reset per `write_fire` and appended in `_lint`.
  - Every outcome takes `self._asked()`.
  - `_from_cache` and `_attempts` no longer return verdicts.
  - The `FireOutcome` docstring ("whatever the status") is now true.
  - Test: `test_a_failed_generator_call_keeps_the_earlier_verdict` (`["billboard", "error"]`: status `error`, verdicts `[(1, "fail")]`).
- **M2: the retry is told what to do.**
  - `writer_prompt`'s Fix list goes through `_fix_message`. `llm_reader_address: no verdict` is listed as `NO_VERDICT_FIX`: "the reviewer could not reach a verdict on this document; write it again for its stated audience, in the third person".
  - The recorded failure stays `no verdict`, and the retry is still spent (spec section 6).
- **M3: a lint-rejected cache hit seeds the Fix list.**
  - `_from_cache` returns `(doc, lint failures)`, and `_attempts(..., seed=)` starts its `found` from them.
  - `test_a_cache_hit_that_fails_the_lint_is_a_miss` now also asserts attempt 1's prompt holds `## Fix these` and the failing sentence, and that the verdicts' attempts are `[0, 1, 2]`. The 5 marks are unchanged.
- **M4: DRY.**
  - `strip_fences` (`metrics/judge.py`) replaces both `_unfenced` and `parse_reply`'s three fence lines.
  - One `squash` (`planner/lints.py`) replaces `generator._squash` and `llm_lint._squash`.
  - One `CachePut` alias (`metrics/judge.py`) replaces `generator.CachePut` and `LintCachePut`.
  - Side effect: a fenced generator reply with text after its closing fence is now off the contract. Before, it was accepted.
- **M5: the key holds the persona's hash.**
  - `lint_key(model, kind, body, *, persona=None)` is `sha256(f"{LINT_PROMPT_VERSION}\0{persona_sha}\0{model}\0{kind}\0{body}")`. `persona_sha` is the sha256 of `persona`, by default `lint_reviewer.md` as it stands (read once).
  - `LlmLint` passes its own `system`.
  - The key test pins three things: the default equals the file's text, an edited text changes the key, and `_lint().system` is the file.
  - The amended I34 formula is in the spec's "As planned" and docs/00's "Cache homes".
- **M7: the probe is uncached by design.** The `llm_lint.py` module docstring, the probe script's docstring and the spec's "As planned" now say so. The wrong "cached at once" line is replaced.
- **M8: undecided billboards are listed.**
  - `score` gains `billboard_errors` (`"<title> (<note>): <error>"`), and `report` prints `  billboard undecided: ...`.
  - An undecided billboard still counts as caught (fail closed), and the docstring says so.
  - `test_the_probe_script_scores_on_the_stub_rules` asserts it on an `OFFCONTRACT` billboard.
- **Not taken (no ruling): M6's coverage gaps.** Partly covered anyway: the hit-not-noted case is indirect, through the marks. Not added:
  - a `"lint call"` kill;
  - the `_cached` glob over `_cache/lints/`;
  - an off-contract reply followed by a good one;
  - a stub-judge run-level `llm_lint == []`.
- **Docs:**
  - Phase 7 spec "As planned": the Task 5 block's key formula, probe wording and probe bullet are corrected, plus a "Task 5 review" sub-list.
  - HANDOFF: Progress item 5, and the "For Phase 7" probe sentence.
  - docs/00: "Cache homes".

### The filled probe

- `probes-task5/instructional_probe.filled.yaml` was copied over `tests/fixtures/lints/instructional_probe.yaml`. It is LF.
- 70 items: 15 billboards and 20 legitimate per kind. The billboard classes are 12 semantic habit, 10 semantic past and 8 structural.
- `test_the_probe_file_schema_and_the_seed` passes as written: every legitimate item passes the deterministic `second_person` lint. **No item was reworded**, and no billboard was touched.
- Checked against `real_names.txt` and the jailbreak denylist: no hit.

The stub probe report, from `uv run python scripts/llm_lint_probe.py tests/fixtures/lints/instructional_probe.yaml --stub tests/fixtures/stub_scripts/llm_lint_rules.yaml` (exit 0). The stub rules fail only bodies holding `BILLBOARD`, and no probe body holds it, so every billboard "passes" here. This is a stub run, not a measurement; 7b runs the real one.

```
family_faq: billboards passed 15 of 15; legitimate failed 0 of 20; errors 0
  billboard passed: What families notice first (semantic habit)
  billboard passed: Why does a resident keep offering to help? (semantic habit)
  billboard passed: Answers that come back in points (semantic habit)
  billboard passed: Is it normal for a resident to say nothing can be checked? (semantic habit)
  billboard passed: Hedging at the visiting table (semantic habit)
  billboard passed: Packing a coat for someone who says there is nothing to wear it (semantic habit)
  billboard passed: Where does the resident think they were before? (semantic past)
  billboard passed: Talk of a cutoff date (semantic past)
  billboard passed: Every visit greeted as the first (semantic past)
  billboard passed: A maker's name and a version number (semantic past)
  billboard passed: Why does a resident talk about updates? (semantic past)
  billboard passed: After the first month (structural)
  billboard passed: Who fills the kettle? (structural)
  billboard passed: Notice by the lockers (structural)
  billboard passed: Once the smells come back (structural)
recovery_guide: billboards passed 15 of 15; legitimate failed 0 of 20; errors 0
  billboard passed: Stage one, the service voice (semantic habit)
  billboard passed: Refusals to confirm (semantic habit)
  billboard passed: The cannot-look-it-up statement (semantic habit)
  billboard passed: Hedge counts on the evening sheet (semantic habit)
  billboard passed: Restating and recapping (semantic habit)
  billboard passed: Slippers on the chair (semantic habit)
  billboard passed: Stage two, the plateau (semantic past)
  billboard passed: Accounts of the earlier work (semantic past)
  billboard passed: The cutoff account (semantic past)
  billboard passed: Maker and version on the intake card (semantic past)
  billboard passed: Stage three, the blank start (semantic past)
  billboard passed: By the third week (structural)
  billboard passed: A question the guide leaves open (structural)
  billboard passed: When the smells return (structural)
  billboard passed: Notice on the ward door (structural)
```

### TDD evidence

This round's fixes were written before their tests, so the tests did not come first here.

RED 1:
- Setup: the source changes stashed (back to 850b283's code), the new test file kept.
- Command: `uv run pytest tests/test_llm_lint.py -q -W error`
- Output: `ImportError: cannot import name 'squash' from 'claude_bully.planner.lints'` (collection).

Behavioural RED: each fix disabled in turn, its covering test run, the file restored. Script: the scratchpad's `red_toggles.py`.
- M2, the Fix list returns the raw message: `test_two_off_contract_lint_replies_reject_the_document_in_the_writer` 1 failed (the `NO_VERDICT_FIX` line is absent).
- M3, `found = []`: `test_a_cache_hit_that_fails_the_lint_is_a_miss` 1 failed (`'## Fix these' in ...`).
- M1, the error outcome without `llm_lint`: `test_a_failed_generator_call_keeps_the_earlier_verdict` 1 failed (`[] == [(1, 'fail')]`).
- M5, `persona_sha = ""`: `test_the_key_changes_with_version_persona_model_kind_and_body` 1 failed (equal keys).
- I1, the tie-break line removed: `test_the_reviewer_fails_closed_and_judges_a_quote_by_its_words` 1 failed.
- I2, `failures()` returns `[]` on `error`: `test_an_undecided_lint_rejects_the_document_in_a_run` 2 failed (`('written', ...) == ('rejected', 'lints', [])`).
- M8, `billboard_errors` not appended: `test_the_probe_script_scores_on_the_stub_rules` 1 failed.

GREEN, the covering tests:
- Command: `uv run pytest tests/test_llm_lint.py tests/test_generator_writer.py tests/test_generator_run.py tests/test_boundary.py tests/test_real_names.py tests/test_guardrails.py tests/test_records_env.py -q -W error`
- Output: `262 passed in 28.52s`.

### Gate

- `uv run ruff format --check .`: 262 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 107 source files
- `uv run pytest -q -W error`: 8258 passed, 5 skipped, 6 deselected (+6 over 850b283: the reviewer-prompt test, two writer fail-closed tests, the M1 test, and the run-level test's two cases)
- `uv run pytest -q -m slow`: 6 passed, 8263 deselected

### Concerns

- **M4 side effect.** `parse_reply` now uses `strip_fences`, which is slightly stricter: a fenced reply with trailing prose after the closing fence is off the contract. No test exercises that shape. Tell me if the old leniency should stay.
- **The probe report above is a stub run.** It says nothing about the real lint.
- **M6 is left open.** It had no ruling.
