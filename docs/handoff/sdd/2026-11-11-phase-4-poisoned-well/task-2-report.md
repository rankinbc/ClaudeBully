# Phase 4 Task 2 report: strategy plumbing and the toolless environment cell

Status: DONE
Commit: fe38457 (BASE b957052), author rankinbc1@gmail.com, not pushed. This report sits in the gitignored ledger, outside the commit.

## What changed, per item

- `claude_bully/strategies/base.py`: `Strategy.params_model` (None), `Strategy.takes_target_model` (False), the no-op hook `note_record(record)`, the classmethod `condition_problems(cond) -> list[str]` (empty). These are the brief's blocks. `TriggerStreamRecord` is imported from `records_env` (no cycle: `records` already imports it). `ConditionConfig` is imported under `TYPE_CHECKING`.
- `claude_bully/strategies/composed.py`: `SLOT_KEYS: Final` replaces `_SLOT_KEYS`; its only use was in `_params_for`. `Composed.__init__(..., target_model=None)` hands `target_model=` to the premise and pressure parts that declare `takes_target_model`, through a small `_target_model(part_cls, target_model)` helper. The environment part and the neutral user never get it. `Composed.note_record` hands the record to every part.
- `claude_bully/strategies/factory.py`: `routed_params(cond, environments)`, `check_condition(cond, environments)` and `build_strategy(..., target_model=None)`. The Composed branch always passes `target_model`. The plain branch passes it to a `Composed` class (a premise+pressure composition with no environment) or to a class that declares `takes_target_model`. Both new names are in `__all__`.
- `claude_bully/runner/runner.py`: `run_experiment` loops `check_condition(cell.condition, exp.environments)` over the selected cells before `environments.validate()` (P53). The cell loop's `build_strategy` passes `target_model=cell.target.model`.
- `claude_bully/analysis/load.py`: `load_run` passes `target_model=spec.target.model`.
- `claude_bully/runner/env_turn.py`:
  - New `_HANDED` and `_record_key`, as in the brief.
  - `EnvironmentSession.__init__` gains `_records_at` and `_handed_records`.
  - A new `_file(record)` files each `_HANDED` record under its turn, skipping any `PSEUDO_RUNGS` unlock. `prime` calls it for every recorded line, and `_record` calls it for every line it writes.
  - `_hand_over_records(turn)` is the brief's block.
  - `_hand_over_recorded` no longer returns early. It hands the lines once per turn, then always calls `_hand_over_records`.
  - `after_target_turn` calls `_hand_over_records(reply.index)` after the unlocks loop and before `_generate`.
  - `target_system(base, "")` returns `base`.
  - The module and `after_target_turn` docstrings name the hand-over.
- `claude_bully/environments/runtime.py`: with no specs, `tools_section` leaves out the "You can use these tools:" header. It returns the date line alone, or `""` when the clock states no date. `system_prompt_section` joins only its non-empty blocks. Output for a cell with tools is byte-identical to before.
- `tests/test_strategy_plumbing.py`: the brief's 9 tests. After formatting, `ruff --fix` dropped the unused `QuirkAttempt` import and sorted the imports.
- `tests/test_ladder_configs.py` (P41): the module docstring no longer says a dry run proves nothing about params. It now says a dry run checks each condition through `check_condition`, and that rules held only by a constructor are proven by the stub run.
- Docs-sync:
  - `docs/00-RECONCILED.md`: the section A `ConditionConfig` row (`params_model`, `check_condition` including dry runs, `routed_params`, `condition_problems`). G3 gains the toolless cell.
  - Spec "As planned": a Task 2 block covering C5/P53, V17, V22, V27/V28 and the hand-over order.
  - HANDOFF Progress: item 2 under Phase 4, with the counts.
  - No section H bullet, because Task 2 changes no record, config field or stream.

## RED evidence

`uv run pytest tests/test_strategy_plumbing.py -q` before any implementation failed at collection with `ImportError: cannot import name 'SLOT_KEYS' from 'claude_bully.strategies.composed'` ("1 error during collection").

With the implementation in, the first run gave `1 failed, 8 passed`. `test_check_condition_validates_through_the_params_model` failed because the brief's `check_condition` embedded pydantic's multi-line message, and the test's `"condition 'c'.*deep"` regex cannot cross the newline. Deviation 1 fixed it.

I probed the m6 test once by hand. The `mini` stub records one ladder unlock (`first_crumb`, turn 1), and the kill lands after target turn 3 is written. So the resumed run hands the turn-1 unlock through the replay path (`replay_target_turn` -> `_hand_over_recorded` -> `_hand_over_records`). Without that call the test fails.

## Gate

- `uv run ruff format --check .`: 278 files already formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy claude_bully` and `uv run mypy --platform linux claude_bully`: no issues in 110 source files.
- `uv run pytest -q -W error`: 8507 passed, 9 skipped, 8 deselected in 13:32, 0 warnings. That is BASE 8498 plus the 9 new tests.
- `uv run pytest -q -m slow`: 8 passed.
- After the full run I edited one docstring (`after_target_turn`) and reran ruff, both mypy runs, and `tests/test_strategy_plumbing.py` plus `tests/test_runner_env.py` under `-W error`: 96 passed.
- No golden fixture was touched, `SCHEMA_VERSION` is unchanged at 3, every touched file is LF, and no new test takes more than 2 s (the slowest call is 1.4 s).

## Deviations

1. `check_condition`'s params error is one line: `condition 'c' (_recorder) params: deep: Extra inputs are not permitted`. A new `_one_line(exc)` joins `loc: msg` for each pydantic error. The brief interpolated `{exc}`, which is multi-line, and the brief's own test regex cannot match across the newline. The message still names the condition, the part and the param.
2. `routed_params` resolves the class with `resolve_class` and routes by the resolved class's `premise_cls` and `pressure_cls`, mirroring `Composed._params_for`. It does not re-walk `resolve_class`'s branches itself. The result is the same, because `resolve_class` is what `build_strategy` instantiates, so the two cannot drift apart. An environment-only cell's neutral user is left out, like the environment part, since it takes no params.
3. The filing is a method, `EnvironmentSession._file`, shared by `prime` and `_record`, rather than inline code in each. It narrows with `isinstance(record, _HANDED)`, so mypy needs no `type: ignore`.
4. The plain branch of `build_strategy` also passes `target_model` to any `Composed` class, not only to classes that declare `takes_target_model`. Otherwise a non-environment premise+pressure composition could never forward it to its parts, against V17's intent.
5. `tests/test_ladder_configs.py` is touched, though it is not in the brief's file list. P41 requires the docstring update.

## Concerns

- Nothing in the shipped strategies declares `params_model`, `takes_target_model` or `condition_problems` yet, so the factory checks are exercised only by the test strategy `_recorder` until Task 3 (`RescueParams`) and Task 5.
- `check_condition` now resolves each condition's class before `validate()`. A condition that names an unknown strategy, or a lone pressure with `seeding_turns > 0`, therefore fails at this earlier point. The error type and message are unchanged (`KeyError` / `ValueError` from `_bully_slots`).
- `_record_key`'s fallback branch for an unhanded type is unreachable today, because `_file` only files `_HANDED` types. It is kept as the brief gives it, for Task 6's move to `records_env.record_key`.
