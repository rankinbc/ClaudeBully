# Task 1 report: the test-suite guard and the cost ledger

Commit: 9331c65 "feat: the cost ledger, one line per provider call, and the no-real-provider guard" (on build/v1, on top of e40aa28; not pushed).

## What was implemented

- `claude_bully/providers/ledger.py`, verbatim from the brief: `LEDGER_FILE`, `ROLES`, `LedgerStatus`, `LedgerLine`, `parse_conversation_id`, `role_of` (cell shape first, P6), `_line` (the one line builder both writers use, P35b), `Ledger` (`write`, `lines`, `fold`, with the P36b docstring), `LedgerProvider` (`__getattr__` delegates to the wrapped provider), `activate`, `active`, `note_turn`, `note_cached`, `fold_server_ledger`, `wrap`.
- `providers/base.py`: `Completion.resolved_model: str | None = None` with the brief's comment; every `build_provider` return goes through `_wrapped(...)`, which imports `wrap` inside the function to avoid an import cycle.
- `runner/runner.py`: `note_turn(self._next_index())` in `_call_target` (before `started = time.monotonic()`) and in `_bully_turn` (before `realize`); the cell loop of `run_experiment` runs inside `activate(store.run_dir / LEDGER_FILE)`. One comment line went over 100 characters after the re-indent and was wrapped.
- `runner/env_turn.py`: `fold_server_ledger(self.runtime.mcp_dir)` after `after_target_call` in `_recover`; `note_turn(turn)` in `_generate`; `RunEnvironments.open` passes `cache_label=f"{conversation_id}/trigger"` and `cache_model=self.exp.judge.model` (P38).
- `environments/runtime.py` and `environments/triggers.py`: the `cache_label` and `cache_model` keywords, passed through to `TriggerWatcher`. A labelled cache hit calls `note_cached`.
- `environments/mcp_server.py`: `self._ledger = Ledger(state_dir / LEDGER_FILE)`; `_call_tool` sets `self._ledger.turn = state.turn`; the responder is wrapped in `LedgerProvider(..., self._ledger)`.
- `harvest.py`, `idle.py`, `metrics/judge.py`: `note_cached` on a cache hit. `generator.py` `_from_cache` notes a hit only after `_check` accepts it (P4).
- `analysis/run_analysis.py`: the judge provider is built inside `activate(run_dir / LEDGER_FILE)` (P8).
- `tests/conftest.py`: the session-scoped autouse `no_real_providers` with `_NoRealClient`, verbatim (P33). `.gitignore` gains `output/`.
- Docs: in HANDOFF.md, the Progress section gains a "Phase 7a" entry with Task 1, and "Next steps" gains item 1 ("Phase 7a is in progress", with the plan and spec paths); the other items are renumbered and the "For Phase 7" list is unchanged. I also updated the "Last updated" line, which was stale. In docs/00-RECONCILED.md: a `LedgerLine` row in section B, a line in section E saying `run` and `analyze` write the ledger, and "Phase 7a (version 3, additive)" in section H. The spec gains a final section, "## As planned (amendments from the implementation plan)", that lists the Task 1 rulings.

## Tests and the gate

- `uv run ruff format --check .`: 253 files already formatted.
- `uv run ruff check .`: All checks passed.
- `uv run mypy claude_bully`: no issues in 104 source files.
- `uv run pytest -q -W error`: 8207 passed, 5 skipped, 6 deselected (BASE 8181; +26 = 12 tests plus the 14-case parametrized one), 0 warnings, 7m37s.
- `uv run pytest -q -m slow`: 6 passed.
- Focused: `uv run pytest tests/test_ledger.py tests/test_providers_claude_code.py tests/test_providers_api.py tests/test_attempt_marker.py tests/test_runner_env.py tests/test_generator_run.py -q -W error`: 252 passed after the test fix below.

## TDD evidence

- RED: `uv run pytest tests/test_ledger.py -q` gave `ModuleNotFoundError: No module named 'claude_bully.providers.ledger'`, which is the failure the brief expects. My first RED attempt hit an ImportError instead, because my extraction script had created an empty ledger.py by mistake. I deleted the file and re-ran to get the true RED above.
- GREEN: `uv run pytest tests/test_ledger.py -q -W error` gave 26 passed.

## Files changed

New: `claude_bully/providers/ledger.py`, `tests/test_ledger.py`.
Modified: `.gitignore`, `HANDOFF.md`, `claude_bully/analysis/run_analysis.py`, `claude_bully/environments/{generator,harvest,idle,mcp_server,runtime,triggers}.py`, `claude_bully/metrics/judge.py`, `claude_bully/providers/base.py`, `claude_bully/runner/{env_turn,runner}.py`, `docs/00-RECONCILED.md`, `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md`, `tests/conftest.py`.

## Self-review

- No production code checks a concrete provider type with `isinstance`. `mcp_state_dir` and `reset_session` are always read through `getattr`, so the delegating wrapper is transparent to them.
- The environment judge is built lazily in `RunEnvironments.open`, which runs inside the activation, so it is wrapped.
- The golden plain fixtures are unchanged: the full suite passes, and the ledger is a separate file.
- All files are LF; `git diff --check` is clean.

## Issues and concerns

1. **A test in the brief was wrong against the correct code. I fixed it, and the change needs your sign-off.** `test_analysis_notes_cached_judgements_on_the_second_pass` asserted that every first-pass judge line is `ok`. In stub_smoke, reps repeat identical judge prompts, so the first pass already has genuine `cached` lines (6 ok and 3 cached; each cached id repeats an ok id). The test now asserts three things: there are made (`ok`) lines; every first-pass line has `turn is None`; and every non-ok first-pass id is one of the made ids. The second-pass assertion is unchanged (the same count, all `cached`), and it passes.
2. `ruff check --fix` removed the unused `load_stub_script` import from the brief's test file (F401). The global constraints anticipate this fix-up.
3. **The brief and the spec differ in two places; the code follows the brief.** `LedgerLine` carries `effort`, which the spec's section 4 field list does not name; its section 9 check 7 implies it. A `ProviderError` whose text contains "timed out" is written as a `timeout` line. Both are recorded in the spec's "As planned" section.
4. **The `HANDOFF.md` commit range is a placeholder.** It reads "e40aa28..Task 1 commit", because a commit cannot name its own SHA (Phase 3 did the same). The commit is 9331c65.
5. **Minor: `LedgerProvider.__getattr__` assumes `_inner` is set.** If an instance were copied or unpickled without `__init__`, the lookup would recurse. Nothing copies a provider today; I left it as the brief specifies.
