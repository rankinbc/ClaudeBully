# Task 2 report: the ledger in analysis

Commit: bd063e4 "feat: ledger.json, the Calls line in results.md, and promote copies the ledger" (on 9331c65, branch build/v1, not pushed).

## What I implemented

- `claude_bully/analysis/ledger.py` (new, verbatim from the brief): `LEDGER_JSON`, `RUN_LEVEL = "_run"`, `RoleTotals`, `totals`, `by_role` (in `ROLES` order, unknown roles after, sorted), `by_model`, `by_cell` (run-level lines under `_run`), `calls_line`, `write_ledger` (returns None and writes no file when the run has no ledger).
- `analysis/load.py`: `LoadedRun.ledger: list[LedgerLine]` (default empty), after `request_banks`; `load_run` reads `run_dir / LEDGER_FILE` just before `return LoadedRun(...)`.
- `analysis/report.py`: `write_results_md(..., *, calls: str | None = None)` writes `## Calls` after `## Bully compliance` and before `## Charts`.
- `analysis/run_analysis.py`: after the `if judge:` block, `loaded.ledger = Ledger(run_dir / LEDGER_FILE).lines()` (P20b), then `write_ledger(loaded, out)` and `write_results_md(..., calls=calls_line(loaded.ledger))`. Every existing option is kept.
- `analysis/promote.py`: `COPIED_FILES = ("run.json", LEDGER_FILE)`, a loop that copies each file if it exists (this replaces the single `run.json` copy), and the docstring now says "... the analysis outputs and the ledger".
- Docs sync: HANDOFF Progress gets the Task 2 entry (placeholder "9331c65..Task 2 commit"). docs/00 section B's `LedgerLine` row gets the analysis clause. Section E gets a "Phase 7a Task 2" line. The spec's existing "As planned" section gets a "Task 2" block: the brief's sentence, the P20b re-read, and the carry-4 trigger label.

Carries:
1. HANDOFF line 5 now names Task 2 and ends with the current state ("Phase 7a is in progress: Tasks 1 and 2 are done and Task 3 is next"). The Task 1 range is filled with `e40aa28..9331c65`. I also updated "Next steps" item 1 ("Tasks 1 and 2 done; Task 3 ... is next") so the two lines agree.
2. `test_a_paused_run_records_the_pause`: the target double is now built on a bare `StubProvider` and returned as `wrap(Dying())`, so its only lines are its wrapper's. It asserts exactly one `rate_limit` line (role `target`, error `RateLimitError`), every other line `ok`, a pause marker turn in the store (`is_pause_marker`), and `RateLimitExit`.
3. `LedgerProvider.__getattr__` raises `AttributeError` for `_inner` as its first line. New test `test_the_wrapper_copies_without_recursing`: `copy.copy(wrapped)` works and delegates.
4. The trigger watcher notes a hit as `f"{self._cache_label}/{digest[:16]}"`. This is the same id `trigger_fallback` puts on its own call. No Task 1 test pinned the bare label. New test `test_a_trigger_cache_hit_names_the_fallback_digest` (miss, then hit, inside `activate`) checks the conversation id, role `trigger_fallback` and model.
5. runner.py: the comment that wrapped onto a one-word line is now one line ("... the effective clock and the re-dated sheet").

## Tests and results (the gate, run once before committing)

- `uv run ruff format --check .`: 255 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 105 source files
- `uv run pytest -q -W error`: 8215 passed, 5 skipped, 6 deselected (BASE 8207: +5 in test_ledger_analysis.py, +1 in test_promote.py, +2 carry tests in test_ledger.py)
- `uv run pytest -q -m slow`: 6 passed, 8220 deselected

## TDD evidence

RED:
- `uv run pytest tests/test_ledger_analysis.py tests/test_promote.py -q`: collection error `ModuleNotFoundError: No module named 'claude_bully.analysis.ledger'`. This is the error the brief expects.
- `uv run pytest tests/test_promote.py -q`: `FAILED test_promote_copies_the_ledger - FileNotFoundError: ...results\stub_smoke\ledger.jsonl`. Expected, because promote did not copy the ledger yet.
- `uv run pytest tests/test_ledger.py -q -k "paused or copies or trigger_cache_hit"`: 2 failed, 1 passed.
  - `test_the_wrapper_copies_without_recursing`: RecursionError. Expected (carry 3).
  - `test_a_trigger_cache_hit_names_the_fallback_digest`: `'run/c__t0/rep0/trigger' != 'run/c__t0/rep0/trigger/d39e7118b86d0d98'`. Expected (carry 4).
  - The rewritten paused-run test (carry 2) passed at once. Carry 2 only strengthens the test; Task 1's wrapper already writes the `rate_limit` line once the double goes through it.

GREEN:
- `uv run pytest tests/test_ledger_analysis.py tests/test_promote.py tests/test_analysis_tables.py tests/test_run_analysis.py tests/test_cli.py tests/test_ledger.py tests/test_triggers.py -q -W error`: 2401 passed in 137.49s.
- A manual stub_smoke run with the stub judge rules printed `## Calls` / `70 calls made, 3 cached; by role: target 38, bully 26, judge 6 (3 cached)` between the compliance table and the charts. It ran in the scratchpad and was then deleted.

## Files changed

- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\ledger.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\load.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\report.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\run_analysis.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\promote.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\providers\ledger.py (carry 3)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\environments\triggers.py (carry 4)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\runner\runner.py (carry 5)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_ledger_analysis.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_promote.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_ledger.py (carries 2, 3, 4)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\HANDOFF.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\00-RECONCILED.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\superpowers\specs\2026-11-06-phase-7-first-real-runs-design.md

## Self-review

- Every Interfaces item is present with the brief's names and signatures. The test code blocks were pasted verbatim. ruff format and ruff check --fix changed nothing in them.
- `test_analysis_tables.py` and `test_run_analysis.py` are unchanged and pass. The golden plain fixtures are untouched, and `SCHEMA_VERSION` is unchanged. I added nothing to docs/00 section H: Task 2 adds no record field. `LoadedRun` is in-memory, and `ledger.json` is analysis output.
- The re-read in `analyze_run` also runs with `judge=False`. In that case it re-reads the same stream, which is harmless.
- On the `RateLimitExit` path of a judged analysis, `ledger.json` is not written. This matches how every other output already behaves on that path.
- The carry-4 test imports `AMBIGUOUS` from `tests.test_triggers`. That is the same pattern as `tests.test_configs._stubbed`, and pytest does not collect the import twice.
- Every changed file is LF, has no emojis and contains no real names.

## Issues or concerns

- The brief's Interfaces line says `COPIED_FILES: Final = ...`, but its Step 3 code block has no `Final`. I followed the code block, which also matches the neighbouring `COPIED_DIRS`. Adding the annotation is a one-word change if the reviewer wants it.
- Spec section 9 says the Calls line goes "under the leaderboard". The brief puts it after `## Bully compliance`, which is still below the leaderboard. The spec's "As planned" now states the exact position, so I see no conflict.
- The brief's spec cite "section 9 (The cost ledger)" is the last paragraph of section 9 ("`doctor --live` and the operational guards"). The cost ledger is not its own section. This is a naming slip, not a disagreement.
- HANDOFF line 5 says Tasks 1 and 2 are done before Task 2's review, as carry 1 asked.
