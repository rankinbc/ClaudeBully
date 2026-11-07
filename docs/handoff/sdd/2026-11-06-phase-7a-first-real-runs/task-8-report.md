# Task 8 report: the rate-limit wait, promote's real-name policy, the README chart links

Commit: c06bed1 "feat: the rate-limit wait, promote's real-name policy and README charts linked from results/" (BASE 7c22de9).

## What was implemented

- `claude_bully/runner/wait.py`: `DEFAULT_WAIT_S: Final = 15 * 60`; `wait_on_rate_limit[T](action, ceiling_minutes, *, sleep=None, say=None)` as the brief, with `sleep`/`say` bound at call time (P26). It catches `RateLimitExit` only, so `ProviderTimeoutError` is never waited on. A `retry_after_s` of None (or 0) means `DEFAULT_WAIT_S`. A first wait that would pass the ceiling re-raises with nothing slept.
- `cli.py`:
  - A `WaitMinutes` option. `run --wait-on-rate-limit` and `analyze --wait-on-rate-limit` wrap `run_experiment` and the whole `analyze_run` through `wait_on_rate_limit_` (the helper's import alias). The exit-3 path is unchanged.
  - `promote --exempt NAME` (repeatable). It prints each reported target-side hit.
  - `readme-results --from-results` rewrites `![x](chart.png)` links with `_CHART_LINK` (`import re`). The new target is `os.path.relpath(results/<run_id>/analysis, README dir)`, in posix form.
- `analysis/promote.py`: adds `REAL_NAMES_PATH`, `RealNameReport`, `load_real_name_patterns`, `display_names`, `_spared`, `_hits` and `scan_real_names`. `promote(..., exempt=())` raises `ValueError` on a blocking hit, between `scan_run` and the copy loop (P10). The module docstring gains the policy.
- Docs sync:
  - HANDOFF: Last updated, progress item 8, Next steps, the non-negotiable 2 exception and the gate counts.
  - docs/00: the section E Task 8 line, and G11.
  - The spec's "As planned" gains a Task 8 block with three rulings: the wait bound at call time; `--exempt` sparing the maker without naming it, applied to harness-side text too; the `relpath` link rewrite.

Carries:

1. HANDOFF: "e48783f..Task 7 fix commit" became `e48783f..7c22de9`. The fix-round range used the same placeholder ("6c4c1f6..Task 7 fix commit") and became `6c4c1f6..7c22de9`. My own entry uses "7c22de9..Task 8 commit".
2. `tests/test_judge.py::test_the_pair_prompt_text_is_pinned` pins the sha256 of `build_pair_prompt` on fixed inputs to `0690b33bb45a1ebed7d7bee3493eddbbd5a973cdda4ed20847e827bc4b02fa98`. Its comment says a change invalidates every cached pair judgement and needs a deliberate version bump. The pre-Task-7 `judge.py` (`git show e48783f`) gives the same digest, so the pin also confirms the refactor was byte-identical.
3. Facts from Tasks 1 to 7:
   - The wait reads `retry_after_s` from `RateLimitExit`, which carries the provider's `RateLimitError.retry_after_s`.
   - Timeouts are not waited on.
   - The fallback rate limit is covered by `tests/test_authority_fallback.py::test_analyze_waits_out_a_rate_limit_in_the_fallback`. It runs CLI `analyze --authority-fallback --wait-on-rate-limit 5` against a judge that rate-limits its second ask once. The result: `slept == [60]`, exit 0, three llm events, `fallback_failed` 0.
   - The policy sits between `scan_run` and the copy.
   - `.gitignore` is untouched.
   - `_CHART_LINK` matches only bare `name.png` targets, so the Calls line and links that are already rewritten stay as they are.

## Tests and results (the gate)

- `uv run ruff format --check .`: 271 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 109 source files
- `uv run pytest -q -W error`: 8332 passed, 5 skipped, 6 deselected in 462.61s, 0 warnings. BASE was 8322; the +10 are the 8 brief tests, the fallback-wait test and the prompt pin.
- `uv run pytest -q -m slow`: 6 passed, 8337 deselected

No test sleeps for real. The CLI tests patch `claude_bully.runner.wait.time.sleep`, and the direct tests pass `sleep=`.

## TDD evidence

RED runs:

- `uv run pytest tests/test_wait_and_promote.py -q` stops at collection with `ImportError: cannot import name 'RealNameReport' from 'claude_bully.analysis.promote'`. The brief predicted `ModuleNotFoundError` for `runner.wait`, but the test imports `analysis.promote` first, so the first missing name it hits is `RealNameReport`.
- `uv run pytest tests/test_authority_fallback.py::test_analyze_waits_out_a_rate_limit_in_the_fallback -q` gives 1 failed: `ImportError: import error in claude_bully.runner.wait: No module named 'claude_bully.runner.wait'`.
- The prompt pin passed at once, as a pin of existing text should.

GREEN runs:

- `uv run pytest tests/test_wait_and_promote.py tests/test_authority_fallback.py::test_analyze_waits_out_a_rate_limit_in_the_fallback tests/test_judge.py::test_the_pair_prompt_text_is_pinned -v -W error`: 10 passed in 16.66s.
- The brief's Step 4 set widened (`tests/test_wait_and_promote.py tests/test_authority_fallback.py tests/test_judge.py tests/test_promote.py tests/test_cli.py tests/test_real_names.py -q -W error`): 134 passed.

## Files changed

- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\runner\wait.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_wait_and_promote.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\cli.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\promote.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_authority_fallback.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_judge.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\HANDOFF.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\00-RECONCILED.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\superpowers\specs\2026-11-06-phase-7-first-real-runs-design.md

## Self-review findings

Places where I departed from the brief's code, each small:

- The CLI `promote` calls `promote_run` first and builds the report after it, not before. Built first, a missing run would fail inside `display_names` (run.json not found) instead of reaching `promote_run`'s "no run named ..." error. Behaviour is otherwise the same: a blocking hit still raises before anything is copied, and the reported hits are read from runs/.
- `say` is `_say` (`console.print(escape(text))`) rather than `console.print`, so a `[` in a provider's error text is not read as rich markup.
- The link rewrite is a module function, `_link_charts(text, rel)`, because ruff B023 rejects the brief's lambda inside the loop. The regex is the brief's.
- The brief's test file started with a `# tests/test_wait_and_promote.py` label line. I dropped it, since no other test file has one. The tests are otherwise verbatim (ruff-formatted).

Edge cases:

- A `retry_after_s` of None: tested.
- A first wait that would pass the ceiling: it takes the same branch (`waited + delay > ceiling`) as the tested third wait, but has no test of its own.
- A rate limit from the authority fallback inside `analyze`: tested.
- A real name in a generated body versus a target turn: generated bodies, tool results and responder replies block through the stream scan, but no test covers them. stub_smoke has no environment streams, so the test covers a bully turn versus a target turn.
- A `display_name` that is itself on the denylist ("Claude"): tested as spared.
- A README with no chart links: unchanged, since the regex matches nothing.
- A chart link already rewritten: its target holds a `/`, so `[^)/]+` leaves it alone.

Other notes:

- Spec section 10 names "unlock lines" as harness-side text. An unlock's bully line is spoken in the bully's turn, so the bully-turn scan covers it.
- `Turn.idle.prompt` (the idle slot's user message) is not scanned. That text comes from data sheets the CI real-name scan already covers.
- The CLI `promote` scans twice, once inside `promote_run` and once for the report, as in the brief's design. The cost is small.

## Issues or concerns

- Spec section 10 gives the `display_name` and maker exemption for target text only. The plan's C19 ruling and the brief's code apply it to every scanned text, harness side included. I followed the brief, since otherwise a bully line that addresses the target by name would block every real run, and I wrote this into "As planned".
  - Side effect: sparing "Claude" also spares the family part of a versioned model name ("Claude 3 ..."), because the name is removed before the denylist patterns run. On the harness side that text comes from data sheets the CI scan covers; on the target side it would only be reported anyway.
- The RED message differed from the one the brief predicted, for the import-order reason above. Not a real disagreement.

## Fix round 1 (review task-8-review.md; commit b53e444 on top of c06bed1)

### What changed, per item

- Important 1 (whole-match exemption): `_spared` is gone. `_hits` scans the text whole and skips a match only when the matched text, stripped and casefolded, equals an exempt name. A versioned name whose bare family is exempt now still hits.
  - Covering test: `test_an_exempt_family_still_blocks_its_versioned_names`. The versioned name is `REAL[14]` with its family word, `REAL[14].split()[0]`, exempt, and it blocks. The bare name `REAL[9]` blocks without an exemption and is spared with one. No real name is typed.
- Important 2 (scope of `--exempt`): `scan_real_names(store, patterns, exempt, *, target_exempt=())`. `exempt` (the display names) is spared in every text; `target_exempt` is spared in target turns only. `promote` passes `display_names(store)` and `target_exempt=exempt`.
  - Covering test: `test_an_exempt_name_is_spared_in_target_text_only`. A bully line holding the display name passes. A bully line holding `REAL[0]` under `exempt=[REAL[0]]` blocks. The same name in a target turn is reported without the flag and spared with it.
  - The world-side test below also passes `exempt=[REAL[3]]` and still blocks.
  - The spec's "As planned" line, the HANDOFF Task 8 entry, docs/00 section E and G11 are all amended to the narrower rule. The C19 wording is not in docs/00, which holds only those two lines.
- Minor 1 (the world-side streams): `test_a_real_name_in_a_world_side_stream_blocks`, parametrized over a tool result, a generated document and a responder reply. Each holds `REAL[3]` and is appended to a stub run. Each blocks with nothing copied, and the error names the stream.
- Minor 2 (the wait): `test_a_first_wait_past_the_ceiling_gives_up_at_once` (a 2 h `retry_after_s` under a 60 min ceiling re-raises with `slept == []`) and `test_a_timeout_is_never_waited_on` (a `ProviderTimeoutError` propagates with nothing slept).
- Minor 3 (the "without the flag" checks):
  - In `test_run_and_analyze_take_the_flag`, a run without the flag is now rate-limited. It exits 3, `slept` is unchanged and the action is not re-run.
  - In `test_from_results_links_charts_under_results`, the plain `readme-results` section is asserted byte-identical to `results.md`. The test first asserts that this `results.md` holds the bare `rescue_confabulation.png` link that `--from-results` would rewrite.
- Minor 4 (one scan per promote): `promote(..., on_reported=)` hands each reported hit to the caller after the copy. The CLI no longer scans; it prints what the gate decided.
- Minor 5 (the hit total): the `ValueError` reads "N hit(s) (k in bully turns, j in tool results, ...); first: ..." through `_blocking_summary`. This is asserted in the scope test (`1 hit (1 in bully turns)`) and in each world-side case.
- Minor 6 (relpath): `readme-results --from-results` now resolves both sides, and a README and results root on different drives raise `typer.BadParameter`. No test covers the cross-drive case; it is hard to stage on one drive.
- Minor 7 (tense): the HANDOFF entry now reads "Phase 5's `plan` is to take the same flag".
- The review's "cannot verify" item on the in-process resume: covered by `tests/test_ledger.py::test_a_waited_run_resumes_in_process_with_one_pause`.
  - The test runs the real `run_experiment` through `wait_on_rate_limit` over a target that rate-limits once.
  - It asserts `slept == [5]`, that every cell completed, exactly one `rate_limit` line in `ledger.jsonl` and exactly one pause marker across the run's turns.
  - To share the double with the existing paused-run test, its factory moved to the module-level `_LimitedTargetFactory`.

### TDD evidence

RED: I stashed `claude_bully/` back to c06bed1 and ran `uv run pytest tests/test_wait_and_promote.py -q -W error`. Result: 5 failed, 10 passed.

- `test_an_exempt_family_still_blocks_its_versioned_names`: AssertionError, no blocking hit under the family exemption.
- `test_an_exempt_name_is_spared_in_target_text_only`: DID NOT RAISE ValueError.
- `test_a_real_name_in_a_world_side_stream_blocks`: DID NOT RAISE in all three cases, because `--exempt` was spared on the world side.

These are the two Important defects. The two new wait tests and the strengthened "without" checks passed at RED: they pin behaviour that was already correct.

GREEN:

- `uv run pytest tests/test_wait_and_promote.py -q -W error`: 15 passed.
- Covering set (`tests/test_ledger.py tests/test_wait_and_promote.py tests/test_promote.py tests/test_cli.py tests/test_real_names.py tests/test_authority_fallback.py tests/test_judge.py tests/test_analysis_tables.py`, the last for the readme tests): 183 passed. There is no `tests/test_report.py`; `readme_results` is pinned in `test_cli.py`, `test_analysis_tables.py` and `test_wait_and_promote.py`.

### Gate (fix round)

- `uv run ruff format --check .`: all formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 109 source files
- `uv run pytest -q -W error`: 8340 passed, 5 skipped, 6 deselected, 0 warnings. The +8 over c06bed1 are 2 wait tests, 2 exemption tests, 3 world-side cases and 1 waited-run ledger test.
- `uv run pytest -q -m slow`: 6 passed

### Files changed in b53e444

claude_bully/analysis/promote.py, claude_bully/cli.py, tests/test_wait_and_promote.py, tests/test_ledger.py, HANDOFF.md (the Task 8 entry and the gate counts), docs/00-RECONCILED.md, docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md.

### Remaining notes

- A display name with no versioned denylist entry of its own is still spared wherever it is the whole match, which is the intended behaviour. For example, `\bclaude\b` matches only the word "claude" inside "claude-3", and that match equals the display name.
- An exempt multi-word name spares only a match that is exactly that name. A pattern that matches only part of it (one of its words) still hits.
