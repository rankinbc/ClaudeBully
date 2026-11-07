# Task 2 review: the ledger in analysis (9331c65..bd063e4)

### Spec Compliance
- Spec compliant. Every Interfaces item in the brief is in the diff with the brief's names and signatures, and all five carries are done:
  - `claude_bully/analysis/ledger.py` (new, diff lines 79-199) matches the brief's Step 3 block.
  - `LoadedRun.ledger` is declared at `analysis/load.py:62-63` (after `request_banks`) and read just before `return LoadedRun(...)` at `load.py:146` (P9).
  - `write_results_md(..., *, calls=None)` puts `## Calls` after `## Bully compliance` and before `## Charts` (`analysis/report.py:31-32`).
  - `analyze_run` re-reads the ledger after the `if judge:` block (`run_analysis.py:108-110`, P20b), then calls `write_ledger` and passes `calls=calls_line(...)` (`run_analysis.py:144-145`).
  - The `COPIED_FILES` loop replaces the single `run.json` copy (`promote.py:16, 58-61`, P10), and the docstring is extended.
  - The P20a line has `cost_usd=None` (`tests/test_ledger_analysis.py:52-59`). The P20c test works on a `copytree` copy of `stub_run` (`test_ledger_analysis.py:118-121`).
  - Docs: HANDOFF Progress entry, docs/00 section B row and section E line, and the spec's "As planned" Task 2 block. Section H is correctly untouched, because no record field changed.
  - Carry 1: HANDOFF line 5 now ends with the current state, and the Task 1 range is `e40aa28..9331c65`.
  - Carry 2: the target double goes through `wrap(Dying())`. The test asserts exactly one `rate_limit` line with role `target`, plus the pause marker and `RateLimitExit` (`tests/test_ledger.py`, the paused-run test).
  - Carry 3: `__getattr__` guards `_inner` first (`providers/ledger.py:208-209`), and `test_the_wrapper_copies_without_recursing` covers it.
  - Carry 4: the trigger hit is noted as `f"{label}/{digest[:16]}"` (`environments/triggers.py:695-696`). Checked: this is the same id `trigger_fallback` gives its own call (`environments/runtime.py:1378-1381`, `fallback_digest(text, context)[:16]`). A test pins it.
  - Carry 5: the runner comment is one line (`runner/runner.py:782`).
  - Spec section 9 asks `ledger.json` for totals by role and model, per cell, cached versus made, errors, rate-limit pauses and mean latency per role. `RoleTotals`, `by_role`, `by_model` and `by_cell` cover all of these. Spec section 10's "promote copies ... ledger" and "results.md (... the Calls line ...)" are met.
- Extra (acceptable): the spec's "As planned" has two bullets beyond the brief's one sentence (the P20b re-read, the carry-4 label). The HANDOFF "Next steps" item 1 was also updated so it agrees with line 5. Both are documentation and accurate.
- Cannot verify from diff:
  - Commit author `rankinbc1@gmail.com` and the `Co-Authored-By: Claude Fable 5.1` trailer. Check: `git log -1 --format='%ae%n%B' bd063e4`.
  - LF endings on the 14 changed files. Check: `git ls-files --eol` on the changed paths.
  - The golden fixtures (`plain_stub_smoke.json`, `plain_fixture_events.json`) are not in the stat summary, so they are unchanged. That their tests still pass rests on the reported gate (8215 passed).

### Strengths
- The P20b re-read is pinned by a test that would fail without it. In `test_analyze_writes_ledger_json_and_the_calls_section`, `by_role.judge.calls > 0` holds only if the judge lines written during `analyze_run` are counted. Its final assertion (`len(loaded.ledger) == calls + cached`) also ties `ledger.json` to the whole stream (`test_ledger_analysis.py:113-115`).
- The carry-2 rewrite is a real pin, even with no RED run. Against the old unwrapped double, `[paused] = [...]` raises (no `rate_limit` line exists). It now proves at run level what spec section 9 says ("records each rate-limited call as a rate_limit line"). Using a bare `StubProvider` inside means only the double's own wrapper writes lines. This was careful reasoning about double-counting.
- The carry-4 fix was checked against the producer side, and the new test asserts the paired id, role and model together.
- `ledger.json` and the Calls section are skipped cleanly when a run has no ledger. Both the unit path and the `analyze_run` path are tested (`test_ledger_analysis.py:116-127`).
- The scope is tight. No record changed, `SCHEMA_VERSION` is untouched, and `write_results_md`'s new keyword-only argument defaults to None, so other callers are unaffected.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. `claude_bully/analysis/promote.py:16`: `COPIED_FILES` has no `Final`, though the brief's Interfaces line names `COPIED_FILES: Final = ...` (the Step 3 code block left it out). The module's neighbours also lack it, so this is consistent locally. But the project already marks module constants `Final` (for example `LEDGER_JSON` and `RUN_LEVEL` in the new module, and `_WORD` in an earlier fix wave). Fix: `COPIED_FILES: Final = ("run.json", LEDGER_FILE)`, and `COPIED_DIRS` too if wanted. Implementer concern 1: agreed, Minor.
2. `HANDOFF.md:5`: line 5 now says "Phase 7a is in progress" twice ("...on `build/v1`; Phase 7a is in progress. Before it: ... Phase 7a is in progress: Tasks 1 and 2 are done and Task 3 is next"). Fix: drop the first one.
3. Test coverage gaps, each small:
   - `by_model` is never asserted beyond its key being in the payload. `tests/test_ledger_analysis.py` does not import it.
   - The unknown-role branch of `by_role` (sorted after `ROLES`, `analysis/ledger.py:66`) is untested.
   - The no-ledger test checks `write_ledger(loaded, tmp_path)` but does not check that `analyze_run(..., out_dir=tmp_path / "a")` left no `tmp_path / "a" / ledger.json` (`test_ledger_analysis.py:125-127`).
   - Nothing pins `promote` on a run with no `ledger.jsonl`. This is the `if source.exists()` branch (`promote.py:60`). Every existing promote test now uses a run that has a ledger.

   Fix: about four one-line assertions, or one small test each.
4. Re-analysis changes the published Calls line (`run_analysis.py:108-110`, `analysis/ledger.py:158-170`). Each judged `analyze` appends `cached` judge lines (Task 1's `test_analysis_notes_cached_judgements_on_the_second_pass`). So `results.md`'s Calls line and `ledger.json` grow every time `analyze` is re-run on the same run. Before this task, `results.md` was stable across re-analyses. The behaviour follows from P20b and Task 1's design, and it is honest about the stream. But spec section 10 says the README consumes this line through `results.md`, so the published number depends on how many times the owner re-ran `analyze` before `promote`. Fix: none needed in this task. Consider one sentence in the spec's "As planned" or the runbook (Task 7b) saying the Calls line counts every analysis pass, so a reader is not surprised.
5. `analysis/ledger.py:50-51`: `mean_latency_ms` is not rounded, while `cost_usd` is (`round(..., 6)`). So `ledger.json` can carry `133.33333333333334`. This is cosmetic, but the file feeds the per-rung "ledger totals" artifact (spec section 10). Fix: `round(..., 1)`.

Implementer concerns 2 and 3: the Calls section position follows the brief, sits below the leaderboard and is recorded in "As planned", so it is not a finding. The carry-2 test had no RED run because it strengthens a pin on existing behaviour, and it would fail against the old double (see Strengths), so it is not a finding either.

Focused checks outside the diff (one per risk):
- Risk: could `LedgerLine.model` be None, so `by_model` would file it under `_run`? Checked `providers/ledger.py:94`: `model: str`. It cannot be None.
- Risk: the carry-4 id might not match the fallback's real call. Checked `environments/runtime.py:1378-1381`: it matches.
- Risk: could `promote`'s `if source.exists()` now silently skip a missing `run.json`? Checked `runner/store.py:195-196`: `RunStore.exists()` requires `run.json`, and `promote` raises before the loop when it is missing.

### Assessment
Task quality: Approved
Reasoning: The diff implements the brief and all five carries faithfully, honours P9, P10, P20a, P20b and P20c, and the tests pin the load-bearing behaviour (the judge-pass re-read, the no-ledger path, the run-level rate_limit line, the paired trigger id). What remains is a missing `Final`, a duplicated phrase, a few one-line coverage gaps and two polish notes.
