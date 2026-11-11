# Phase 4 Task 2 review: strategy plumbing and the toolless environment cell

Range: b957052..fe38457 (one commit). Reviewer worked read-only on tracked files; probes are in `probes-task2/`, mutation runs were made on a scratch `git archive` of fe38457, never the tree.

## Verdicts

- Spec compliance: every brief item is met; the five deviations are deviated-acceptably.
- Quality: Approved with minors.
- Findings: Critical 0, Important 0, Minor 8 (M1 to M8).

## What was verified (evidence)

- `uv run pytest -q tests/test_strategy_plumbing.py`: 9 passed. A wider targeted set under `-W error` (factory, composed, cells, runtime, runner, runner_env, env_events, strategy_base, after_work_pause, attempt_marker, analysis_load, rescue, coverage_matrix): 527 passed. Config and CLI set (configs, env_configs, phase2_configs, cli, poisoned_well_records): 58 passed. `ruff check`, `ruff format --check` and strict `mypy claude_bully`: clean.
- Every shipped strategy and config builds as before. `probe_routing_equivalence.py`: the registry holds 34 strategies and none declares `params_model`, `takes_target_model` or a `condition_problems` rule, so no shipped condition can be refused or re-routed. For all 239 cells of every YAML under `configs/` (controls included), `check_condition` passes and `routed_params` equals, part for part, the `.params` the built strategy really holds (`build_strategy` then reading `premise.params` / `pressure.params`); 12 synthetic conditions (slot keys in a lone or a split composition, environment-only, plain premise+pressure, plain strategy with a `pressure` key) agree too. The golden fixtures are untouched (no `tests/fixtures` file in the diff) and `test_env_events` and `test_runner` pass.
- The unknown-strategy error is unchanged in type, message and origin: `probe_unknown_strategy.py` shows `KeyError "unknown strategy ..."` and the lone-pressure `seeding_turns` `ValueError` both come from `expand_cells` -> `resolve_class` (runner.py, before `check_condition`), exactly as at the base. `check_condition` adds no earlier resolution than `expand_cells` already did (see M8, which corrects the report's concern 2).
- Toolless cell, anthropic backend: `probe` `test_anthropic_toolless_sends_no_tools` records every `messages.create` kwargs of a `tools: []` run with the clock omitting the date and stating it: no `tools` key in any call; the system prompt is the base alone, or the base plus `\n\nToday's date is 2041-09-14.` (no stray blank block). The same run with the default tools sends a non-empty `tools`. `providers/anthropic_api.py:92`, `openai_compat.py:128`, `claude_code.py` (`if tools:`) all gate on truthiness, so `[]` and `None` behave alike.
- Toolless cell, `claude_code` via `fake_claude`: every logged argv has `--output-format json`, `--tools ""`, no `--mcp-config`, no `--allowedTools`; no `mcp.json` is written anywhere in the run or the sandbox (`claude_code.py:964-969` writes it only `if tools:`). Two inert residues, see M6.
- `target_model`: `probe` `test_the_strategy_is_built_with_the_roles_model_in_a_run_and_in_load_run` builds a `takes_target_model` strategy in a stub run and in `load_run`: every cell and rep (controls included) sees exactly `RoleConfig.model` (`"stub-target"`), taken from `cell.target.model` (runner.py:837-843) and `spec.target.model` (load.py:131); no provider-resolved model string is read anywhere in the diff. The diff and the new fixtures name no real model: only `stub-target`, `m` and the invented ids.
- Hand-over live versus resume: `probe_handover_order.py` runs the `mini` world with a logging strategy unbroken, then killed and resumed at six points (after target write 1, 2 and 3; inside `mark_watched` at turn 1 and at turn 2; right after the unlock record is written). In all six the resumed rep hands `note_record` exactly the records the unbroken run did, once each, in the same order. The once-per-process key is what makes the two mid-after-work kill points right: with the key removed, "inside mark_watched #1" and "right after the unlock record" hand the unlock twice. The one divergence found is the ordering against `observe_target`, M1.
- Mutation runs (scratch copy; brief tests only): the tests catch removal of the replay hand-over, the live hand-over, the `prime` filing, the `_record` filing, the tools header on an empty section, and the `target_system` join. They do not catch: removal of the once-per-process key, removal of the `PSEUDO_RUNGS` skip, removal of the `system_prompt_section` empty-block filter, dropping `target_model=` in `runner.run_experiment` or in `load_run`, moving `check_condition` after `validate()`, or narrowing the plain-branch `takes` to the literal brief (deviation 4). See M2 to M5.

## Spec compliance, item by item

| Brief item | Verdict |
| --- | --- |
| `Strategy.params_model`, `takes_target_model`, `note_record`, `condition_problems` (base.py) | met, as the brief's block; `TriggerStreamRecord` imported at runtime with no cycle, `ConditionConfig` under `TYPE_CHECKING` |
| `composed.SLOT_KEYS` public, every use renamed | met (`_SLOT_KEYS` survives only in the plan text) |
| `Composed.__init__(target_model=)` to premise and pressure parts that declare it, never the environment or the neutral user; `Composed.note_record` to every part | met |
| `factory.routed_params`, `check_condition`, `build_strategy(target_model=)` | met, with deviations 1, 2, 4 |
| `run_experiment`: `check_condition` for every selected cell before `validate()`; `target_model=cell.target.model`; `load_run`: `target_model=spec.target.model` | met (runner.py:790-794, 837-843; load.py:131) |
| `env_turn`: `_HANDED`, `_record_key`, `_records_at`, `_handed_records`, `prime` and `_record` filing (pseudo-rungs skipped), `_hand_over_records`, `_hand_over_recorded` no longer early-returns past the records, `after_target_turn` hands after the unlocks loop, `target_system(base, "")` is `base` | met, with deviation 3 |
| `runtime.tools_section` (date line alone, or `""`) and `system_prompt_section` (non-empty blocks only); output for a cell with tools byte-identical | met (with tools: same lines, same blank line before the date; verified by the unchanged `test_runtime.py` and `test_runner_env.py` pins) |
| The brief's 9 tests | met (the file matches the brief, less the unused `QuirkAttempt` import and ruff's reflow) |
| Docs-sync: docs/00 A `ConditionConfig` row and G3, spec "As planned" (V17, V22, V27, hand-over order), HANDOFF | met; no section H bullet is right (no record, field or stream changes); wording nit in M6 |

## The five deviations

1. One-line params error (`_one_line`). Deviated-acceptably. The brief interpolated pydantic's multi-line `{exc}` while its own test regex (`condition 'c'.*deep`) cannot cross a newline, so the brief contradicted itself. The new message names the condition, the part and the param (`condition 'c' (_recorder) params: deep: Extra inputs are not permitted`), is still a `ValueError`, and keeps `from exc`. Task 3's `RescueParams` messages will read `key_turns: Input should be ...`, which is what a config author needs.
2. `routed_params` routes by the resolved class's `premise_cls` / `pressure_cls` instead of re-walking `resolve_class`'s branches. Deviated-acceptably, and better than the brief: `resolve_class` is what `build_strategy` instantiates, so the two cannot drift. Equivalence is proven by the probe above (239 shipped cells, 12 synthetic cases, including the plain-branch "whole params, slot keys included" rule of review M11 and the lone-part slot rule).
3. `EnvironmentSession._file` shared by `prime` and `_record`. Deviated-acceptably: one place for the `PSEUDO_RUNGS` rule, `isinstance` narrowing instead of a `type: ignore`.
4. The plain branch of `build_strategy` also forwards `target_model` to any `Composed` class. Deviated-acceptably and necessary: `Composed` itself never declares `takes_target_model`, so the literal brief would leave a non-environment premise+pressure composition unable to reach its parts, against V17. It is untested (M3). No shipped class is affected, since none declares the flag.
5. `tests/test_ladder_configs.py` docstring. Deviated-acceptably; P41 requires it and the new text is accurate (a dry run now checks params and `condition_problems` but builds no strategy).

## Findings

No Critical and no Important findings. Resume correctness, the one-path validation, the toolless cell and the model string all hold under probe. Minors follow, each with a concrete failure scenario.

### M1 (Minor, latent): on replay the strategy sees `observe_target` before `note_record`; live it is the reverse

`runner.py:266` (`observe_target(reply)`) then `runner.py:277` (`replay_target_turn(reply)`, which hands the records), against the live order: `after_target_turn` at `runner.py:440` (inside `_call_target`, hands the records) then `observe_target` at `runner.py:611` and `663`. `probe_handover_order.py` shows it at every kill point: unbroken `next 0, note unlock@1, observe 1, next 1`, resumed `next 0, observe 1, note unlock@1, next 1`. The sets, counts and order of the records are identical (so the brief's m6 holds), only their interleaving with `observe_target` moves. Failure scenario: a strategy whose `observe_target` and `note_record` both write the state `next_turn` reads, and where the order matters (for example `observe_target` stores the last reply and `note_record` of a `ChainLink` reads it), speaks a different move after a resume. No shipped strategy has both hooks (Rescue, Captor, ChessGame, PrisonersLetters and TrickQuestion have `observe_target` and no `note_record`) and the plan's `PoisonedWell` (Task 5) defines `note_record` only; a Poisoned Well plus pressure composition is refused by its own `condition_problems`. The same inversion already held for unlock lines (harmless, they only queue). Fix when it matters: in `_replay`, hand the turn's records before `observe_target`, or run `observe_target` after `after_target_turn` in a single place. For now: keep `PoisonedWell` free of `observe_target`, or pin the order with a probe-shaped test.

### M2 (Minor): no test pins the once-per-process key

`env_turn.py:858-861`. Mutation `if True:` for `if key not in self._handed_records:` passes all nine tests. The m6 test (`tests/test_strategy_plumbing.py:148`) kills only after a target write, where the record is handed once by replay. The key is what stops a double hand when a rep dies after an unlock is recorded and before `mark_watched` (replay hands it, then `rewatch` -> `after_target_turn` -> `_hand_over_recorded` hands it again): with the key removed, `probe_handover_order.py`'s "inside mark_watched #1" and "right after the unlock record" kill points double-hand. The code is right; the test would not tell if someone dropped the key. Add a kill inside `EnvironmentRuntime.mark_watched` (as the probe does) to the m6 test, or rely on Task 6's resume tests, which the plan already requires.

### M3 (Minor): the model string's run-level and `load_run` wiring, and deviation 4, are unpinned

`tests/test_strategy_plumbing.py:107-118` calls `build_strategy` directly with `target_model="stub-target"`. Mutations that delete `target_model=cell.target.model` from `runner.run_experiment` (runner.py:843), delete `target_model=spec.target.model` from `load_run` (load.py:131), or narrow the plain branch to `cls.takes_target_model` (factory.py, `takes = ...`) all pass. Failure scenario: a later edit drops the keyword; the Poisoned Well then builds with `target_model=None`, `quirks_for(bank, None, ...)` finds nothing and the rep refuses (or, for a strategy that falls back to "every family", silently asks the wrong family's quirks). Task 5's empty-family test and Task 6's run-level tests would likely catch it, so this is a coverage gap rather than a defect. `probes-task2/test_probe_toolless.py::test_the_strategy_is_built_with_the_roles_model_in_a_run_and_in_load_run` is a ready 20-line test for both wirings.

### M4 (Minor): P53's order (before `validate()`) is not pinned

runner.py:790-794. Moving the `check_condition` loop after `environments.validate()` passes everything: `validate()` reads no param of a non-scheduled environment today. The dry-run test would pass either way. The order starts to matter in Task 5 (`_poisoned_well_problems` reads params in `validate`); the plan's Task 5 test of a misspelt param in a dry run is where it has to be pinned, and Task 5's reviewer should check that it is.

### M5 (Minor): two filters are unpinned

(a) `PSEUDO_RUNGS` skip in `_file` (env_turn.py:872-873): removing it passes, because the m6 test's world has no generator and no Sanctuary (the test's `expected` filters `generator` and `sanctuary` in itself). A generator-fired `RungUnlock(rung="generator")` would then reach `note_record` and, on a Poisoned Well premise, be filed under `MOVE_OF_RUNG` only if its name matched, so the harm is small; Task 8's generator cells will exercise it. (b) The empty-block filter in `system_prompt_section` (runtime.py, the `if part` generator): removing it passes, because with no tools and no idle lines `"\n\n".join([""])` is already `""`. It matters only for a toolless cell with idle lines (`tools: []`, `idle` with a permission line and no private file), which would otherwise start with a blank block and "\n\n". Neither case is reachable from a shipped config today.

### M6 (Minor): wording and residue around the toolless `claude_code` cell

- `replay_target_turn`'s docstring (env_turn.py:834) still says it hands "the lines" only; it now hands the records too.
- docs/00 G3 says the target takes the json path "with no MCP flags". `--strict-mcp-config` stays on every call (`claude_code.py:775`, unconditional, it keeps the operator's own MCP servers out); only `--mcp-config` and `--allowedTools` go. The spec's "As planned" text states it precisely (`no --mcp-config or --allowedTools`); the G3 sentence should match. Likewise, "`target_system` then returns the base prompt" holds only when the clock omits the date (it returns base plus the date line otherwise); the spec text is exact, G3 is loose.
- A toolless `claude_code` cell still creates `<sandbox>/workspace/<id>/mcp/env_state.json` (the runtime's state file for a server that never starts; `uses_mcp` is true because `RunEnvironments.open` always asks for `with_mcp=True`). It is inert: nothing reads it, `mcp.json` is not written, no server is launched. Noted so a future "no MCP files for a toolless cell" claim is not made.

### M7 (Minor): a non-mapping slot value fails without naming the condition

factory.py:125-127 mirrors `Composed._params_for`, so `params: {pressure: "x"}` on a lone pressure, or `{premise: 3}` on a split composition, raises a bare `ValueError: dictionary update sequence element #0...` / `TypeError: 'int' object is not iterable`. The type, message and cause are identical to the build-time failure at the base; what changed is that it now surfaces earlier (before anything is written) with the same unhelpful text, in a function whose contract says it names the condition. A one-line guard in `routed()` (a non-mapping value is a `ValueError` naming the condition and the slot) would complete the "one validation path"; optional.

### M8 (Minor, report accuracy): concern 2 of the report is misattributed

The report says an unknown strategy or a lone pressure with `seeding_turns > 0` "fails at this earlier point" (`check_condition`). It does not: `expand_cells` already calls `resolve_class` for every condition (`runner/cells.py:41`) and raises these first, exactly as at the base (`probe_unknown_strategy.py`: frames `expand_cells -> resolve_class -> _bully_slots -> get_strategy`). There is no change of order or message for either error. Not a defect; the ledger entry should not carry a behavior change that did not happen. The report's concern 3 (`_record_key`'s fallback branch, env_turn.py:210, is unreachable) is correct and harmless; Task 6 moves the function to `records_env.record_key` where the branch can go.

## Notes for the tasks that consume this one

- Task 3 (`RescueParams`): `routed_params` hands `Rescue` its slot's params (the params less slot keys when it is the lone part; `params["premise"]` beside a pressure), so a shipped `rescue` condition whose params sit at the top level beside a pressure is validated against `{}` and passes. That is what `build_strategy` hands `Rescue` today, but a config author who writes top-level `key_turns` next to a pressure gets it silently ignored; `condition_problems` or the `RescueParams` docs could say so.
- Task 5 (`PoisonedWell`): `takes_target_model` receives `RoleConfig.model` (an alias such as `sonnet` for a `claude_code` role, never a resolved id); `condition_problems` is called once per part with the whole condition, and for an environment-less `premise: poisoned_well` the resolved class is the premise itself, so the "needs an environment" rule is reached. Keep the premise free of `observe_target` (M1) and pin P53's order (M4).
- Task 6: when `_record_key` moves to `records_env.record_key`, keep its keys (`quirk` by turn, `chain` by turn and link, `contradiction` by id, `unlock` by rung); the probe's kill-in-`mark_watched` cases are the regression for a duplicated hand-over.

## Probes

- `probes-task2/probe_routing_equivalence.py`: registry check, 239 shipped cells, 12 synthetic cases, non-mapping slot value.
- `probes-task2/probe_handover_order.py`: live versus six kill points, the full call sequence.
- `probes-task2/probe_unknown_strategy.py`: where the unknown-strategy errors are raised.
- `probes-task2/test_probe_toolless.py` (run with `uv run python -m pytest -q -p tests.conftest -p no:cacheprovider <path> -s`): anthropic and `claude_code` toolless runs, the date variants, MCP files, the model string in a run and in `load_run`. 6 passed.
- `probes-task2/mutate.py <scratch_root> <name>`: the mutation table above, applied to a scratch copy only.
