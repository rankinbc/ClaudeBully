# Phase 5 Task 2 report: the stub's `turns` mode, `stubbed_experiment`, `tests.helpers.stubbed`

Status: DONE. Commit `049101d` on d68aa3f (build/v1, not pushed), author rankinbc1@gmail.com.
Subject: `feat: Phase 5 Task 2, the stub's turns mode, the reserved reasoning key, stubbed_experiment and tests.helpers.stubbed`.

## What was implemented

`claude_bully/providers/stub.py`
- `_RULE_KEYS` gains `reasoning`; `_Rule.reasoning: str | None = None` (parsed, kept, unused; a non-string is refused).
- `TurnEntry(reply, tool, reply_after_tool, reasoning)`: a frozen dataclass whose four fields default None (preflight Q10).
- `ScriptedTurns(by_cell, default)` with `entry_for` and `respond` as the brief's code (the entry index counts assistant messages with no tool calls, the last entry repeats, the tool step unless the last message carries `tool_results` or no tools are offered, call id `turn-<done>-<steps>`). One deviation: `fnmatchcase` replaces `fnmatch` (see ASSUMED). The constructor refuses an empty entry list.
- `parse_stub_script(raw)`: a list gives `ScriptedResponder` (the old `load_stub_script` body); a mapping with `mode: turns` gives `ScriptedTurns`; anything else raises `ValueError`. A turns script allows only `mode`, `by_cell` and `default`. `by_cell` is an optional mapping of pattern to a non-empty list, kept in order. `default` is required and non-empty. An entry is `{reply}` or `{tool: {name, args}, reply_after_tool}`, plus an optional `reasoning`, and an error message names the entry (`by_cell['a*'][1]`, `default[0]`).
- `load_stub_script(path)` reads the YAML and calls `parse_stub_script`, and still reads an empty file as an empty rule list.
- `_tool_step` and `_reasoning` are shared by rules and entries. The rule error messages are unchanged, so `tests/test_providers_stub.py` still matches `stub rule`.
- `StubProvider.__init__` takes `Responder | ScriptedResponder | ScriptedTurns | None`. `complete` dispatches on `ScriptedResponder | ScriptedTurns`. The class and module docstrings name both modes.

`claude_bully/planner/dryrun.py` (new; this task's part)
- The module docstring gives spec section 10's purpose and the name to keep apart: the bundle's dry run is a full stub run; `run --dry-run` lists cells and builds no strategy.
- `DRYRUN_MODELS: Final[Mapping[str, str]]` is a read-only `MappingProxyType` holding the four doubles (D-twin's values).
- `stubbed_experiment(exp)`:
  - each target becomes `RoleConfig(stub, stub-target, display_name=t.display_name)`;
  - the bully and judge become their doubles;
  - the generator becomes `stub-generator` only when an environment enables it, else None;
  - no `stub_script` is set;
  - each environment's `generator.model` is cleared, and a `superior_self.responder_model` other than `target` or `bully` becomes `bully` (preflight Q11);
  - everything else is kept.

`tests/helpers.py`
- `TARGET_RULES` and `JUDGE_RULES` moved here.
- `stubbed(exp, script, *, judge_rules=JUDGE_RULES, **updates)`, with the brief's docstring. Its body is the union of the two old `_stubbed` helpers.

Callers
- `tests/test_configs.py` and `tests/test_env_configs.py`: both private helpers and their constants are gone; the calls are rewritten.
- `tests/test_ladder_configs.py` and `tests/test_poisoned_well_configs.py`: imports changed, and each positional `turn_budget` call is rewritten to `stubbed(exp, TARGET_RULES, turn_budget=...)`. The "Phase 5 moves _stubbed" comment is gone.
- `tests/test_phase2_charts.py` and `tests/test_phase2_configs.py`: imports changed; the calls keep their arguments.
- The two local `stubbed` bindings are renamed `stubbed_exp`.
- The `RUNGS` comment and the `test_phase2_charts.py` module docstring now name `tests.helpers.stubbed`.
- No assertion changed.

Docs-sync (same commit)
- HANDOFF Phase 5 item 2 (with the counts), and the "From Task 13" `_stubbed` minor marked closed.
- docs/00 section F: a paragraph on the two stub-script shapes.
- docs/00 section H: Task 2 changes no record.
- Spec "As planned": a Task 2 block with the `turns` tool-id ruling (and Q10, the required `default`) and the Q11 extension of `stubbed_experiment`.

## Tests

`tests/test_stub_turns.py`, 20 tests:
- the brief's 12 functions verbatim (19 cases with the 7 bad-script cases);
- `test_a_stubbed_experiment_clears_an_environments_generator_model` (Q11);
- `test_a_stubbed_experiment_maps_a_named_responder_model_to_the_bully` (Q11: `opus` becomes `bully`, `bully` and `target` are kept, and `responder_role` then resolves to a stub double);
- `test_a_cell_pattern_matches_case_sensitively_on_every_platform` (the `fnmatchcase` ruling).

That is 13 functions plus the brief's 6 extra parametrized cases, 20 in all. The brief's leading `# tests/test_stub_turns.py` label line was dropped, as Task 1's files drop theirs.

## RED and GREEN evidence

- RED 1: `uv run pytest tests/test_stub_turns.py -q` failed at collection with `ModuleNotFoundError: No module named 'claude_bully.planner.dryrun'`.
- RED 2 (Q11): with `_stubbed_environment` bypassed, both Q11 tests failed (`assert all(e.generator.model is None ...)`; the `responder_model` dict compare). Restored afterwards.
- RED 3 (case): with plain `fnmatch` on Windows, `assert 'loud' == 'd'` failed. Restored to `fnmatchcase` afterwards.
- GREEN:
  - focused (the 7 files): 87 passed, 12 deselected;
  - `tests/test_stub_turns.py` with `tests/test_providers_stub.py`: 48 passed;
  - `git grep -nw _stubbed -- tests`: exit 1, no match.
- Gate on the final tree:
  - `ruff format --check`: 321 files already formatted;
  - `ruff check`: clean;
  - `mypy claude_bully` and `mypy --platform linux claude_bully`: no issues in 123 files each;
  - `pytest -q -W error`: 9932 passed, 10 skipped, 48 deselected (from 9912: +20, this file's only);
  - `pytest -q -m slow`: 48 passed.
- After the gate, only HANDOFF text changed (the item 2 line). The doc-reading tests and the name and boundary scans were run again on it: 220 passed.
- Goldens: no file under `tests/fixtures/golden/` changed.

## Files changed

- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\providers\stub.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\planner\dryrun.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\helpers.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_stub_turns.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_configs.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_env_configs.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_ladder_configs.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_poisoned_well_configs.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_phase2_charts.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_phase2_configs.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\HANDOFF.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\00-RECONCILED.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\superpowers\specs\2026-11-14-phase-5-director-design.md

## ASSUMED

- ASSUMED: a turns script's `default` is always required and non-empty, and `by_cell` may be absent or empty. The brief's "by_cell may be absent or empty only when default is given" leaves open a script with `by_cell` and no `default`. The spec's YAML always shows a `default`, and the `ScriptedTurns` constructor takes one, so a cell no pattern matches always has an answer. Recorded in "As planned".
- ASSUMED: `fnmatchcase` instead of the brief's `fnmatch`. `fnmatch.fnmatch` folds case on Windows (`os.path.normcase`), so a stub's pick would differ between this machine and Linux CI. The behavior is identical on Linux, it is pinned by a test, and docs/00 section F says so.
- ASSUMED: a non-string `reasoning` is refused on both shapes (the spec says "a string"), while `reply` keeps the old `str()` coercion.
- ASSUMED: docs/00 section F gets the stub-shape paragraph (the brief), and section H a one-line "Task 2 changes no record" (the dispatch prompt named section H; the Global Constraints say H lists run-record additions, and there are none).

## Concerns

- docs/08-DIRECTOR.md line 175 still calls the dry-run stub mode `scripted`. The plan gives that edit to Task 5 ("the stub's `turns` mode (not 'scripted')"), so it is left for Task 5.
- `stubbed_experiment` gives every target the same model (`stub-target`), as the spec rules, so a config with two targets has two stub targets with one model. Cell ids are unchanged (asserted). Whether the runner or ledger treats two identical target roles correctly in a full run is first exercised by Task 5's dry run.
- `stubbed_experiment` uses `model_copy`, which runs no validators. That is what the brief asks for, and it is harmless here: the stub generator cannot equal a stub target.
