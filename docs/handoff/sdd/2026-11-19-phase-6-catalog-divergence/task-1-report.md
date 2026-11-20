# Phase 6 Task 1 report: reasoning capture

Status: DONE_WITH_CONCERNS. Commit a7a5e3a, "feat: Phase 6 Task 1, reasoning capture on the four backends, recorded with its turn, replay --reasoning, reasoning in promote's real-name report".

## What was implemented

- `config.ReasoningMode`; `RoleConfig.reasoning: ReasoningMode` (same values, same default).
- `records.ReasoningKind`; `Turn.reasoning_kind` after `reasoning_available`, default None, no validator.
- `Completion.reasoning_kind`; `build_provider` passes `reasoning=role.reasoning` to all four backends.
- Stub: `ScriptedResponder.reasoning_of`, `ScriptedTurns.reasoning_of` (the brief's bodies, pure functions of the messages); `StubProvider(..., reasoning=)`; `complete` drops reasoning under `hide`, treats an empty string as None, kind `full`. The `_Rule` and `TurnEntry` docstrings are updated.
- Anthropic: `THINKING_REQUEST`; `expose` sends `thinking`, never a budget; a 400 under `expose` raises the brief's `ProviderError`; kinds per D-kind (`summarized` under expose, `unknown` under provider_default, `redacted` for blocks with no text, nothing under hide); hide still replays thinking blocks in an open tool loop.
- Claude Code: `streams(json_schema, tools)`; `build_args` takes the output format from it, the MCP flags stay keyed on tools; `complete` resets `thinking_seen` and `mcp_servers_seen` whenever it streams, uses `_stream_failure_text` on any failed streaming call, reads `_new_tool_calls` only with tools; `parse_stream` keeps thinking text under expose (kind `unknown`, or `(None, "redacted")`), nothing otherwise. Docstrings updated.
- OpenAI compat: a non-empty `reasoning_content` string is kept as `unknown` unless hide.
- Runner: a plain cell copies the completion's reasoning; an environment cell's `TargetTurn` gains `reasoning` and `reasoning_kind` (both return sites, `_cut_off` included) through a small `_Reasoning` accumulator (the kind of the first round with text, else the first non-None kind); the runner writes the rounds joined by a blank line. `responder_role` forces `provider_default` on every branch.
- `replay --reasoning` (and `show`): `_SHAPES` and `_ESCAPED_FIELDS` gain `reasoning`; `render_replay(..., reasoning=False)` and `replay_cell(..., reasoning=False)`.
- `promote.scan_real_names`: hits in a target turn's reasoning go to `reported` as `(target, reasoning)`; an address blocks on the turn's ordinary line.
- Tests: `tests/helpers.py` gains `Killed`, `scrubbed`, `comparable_run` (imported back into `tests/test_bundle_run.py` as `_Killed` and `_comparable`; `_scrubbed` had no other use there, so it is not re-imported), plus `outside_reasoning` and `recorded_reasoning` (see the second ASSUMED). `tests/test_reasoning_capture.py` is new (13 tests, 2 slow). The provider, replay, parser and promote tests follow the brief. `tests/test_reasoning_channel.py` lost both shims and reads the runner's turns (`_readers`, `_marked`, `_store_marked`). `WithReasoning` sets `reasoning_kind="full"`. `fake_claude.py` gains `$FAKE_CLAUDE_FINAL_THINKING`.
- Docs-sync: HANDOFF (the Phase 4 carry is closed, Progress gains the Phase 6 Task 1 item), `docs/00-RECONCILED.md` G14, E and H, `docs/10-ROUND-TWO.md` Part 2, and the spec's "As planned" lines for D-kind and D-responder.

## RED evidence

Before any code change: `uv run pytest tests/test_reasoning_capture.py tests/test_replay_parser.py tests/test_replay.py tests/test_providers_stub.py tests/test_providers_api.py tests/test_providers_claude_code.py tests/test_promote.py -q -m "slow or not slow"` gave `50 failed, 303 passed, 3 skipped` (saved in `probes-task1/red.txt`). The failures: `StubProvider` takes no `reasoning`; `Completion` and `Turn` have no `reasoning_kind` (`Extra inputs are not permitted`); there is no `reasoning` replay shape, no `streams` and no `REASONING` line; the promote reasoning lines are missing. The import of `tests.helpers.Killed` did not fail, because I moved the helpers before I wrote the test file.

## GREEN evidence

- The new and touched files after the code: `353 passed, 3 skipped` once a test-only `mkdir(parents=True)` slip was fixed (`probes-task1/green1.txt`); `tests/test_reasoning_capture.py` alone gave 13 passed.
- The Step 6 list, plus `test_runner_env`, `test_stub_turns`, `test_tool_loop`, `test_provider_timeouts` and `test_poisoned_well_run`, with `-m "slow or not slow" -n 8`: `561 passed, 3 skipped` (`probes-task1/green_step6.txt`).
- `test_plain_stub_run_analysis_is_byte_identical` passes unchanged (no shipped script has a `reasoning` key).

## Gate (the parallel form, per the controller's gate change)

- `uv run ruff format --check .`: 407 files already formatted
- `uv run ruff check .`: All checks passed
- `uv run mypy claude_bully`: no issues in 131 source files
- `uv run mypy --platform linux claude_bully`: no issues in 131 source files
- `uv run --with pytest-xdist pytest -q -W error -n 8`: 10848 passed, 11 skipped in 200.93s (the base's 10798 plus 50 new fast tests); no warnings
- `uv run --with pytest-xdist pytest -q -m slow -n 8`: 228 passed in 291.61s (the base's 226 plus 2 new slow tests)

On the gate's first fast run, 4 tests failed and one module errored (see the second ASSUMED). After the fix I reran the whole gate from the start and got the counts above. No test passed alone and failed only under `-n 8`, or the reverse.

## Files changed

- claude_bully: `config.py`, `records.py`, `providers/base.py`, `providers/stub.py`, `providers/anthropic_api.py`, `providers/claude_code.py`, `providers/openai_compat.py`, `runner/runner.py`, `runner/env_turn.py`, `analysis/replay.py`, `analysis/promote.py`, `cli.py`.
- tests: `helpers.py`, `fixtures/fake_claude.py`, `fixtures/poisoned_well_stub.py`, `test_reasoning_capture.py` (new), `test_bundle_run.py`, `test_reasoning_channel.py`, `test_providers_stub.py`, `test_providers_api.py`, `test_providers_claude_code.py`, `test_replay.py`, `test_replay_parser.py`, `test_promote.py`; outside the brief's list: `test_dryrun.py`, `test_llm_lint.py`, `test_generator_run.py`, `test_runner_idle.py`, `test_wait_and_promote.py`, and `test_stub_turns.py` (one stale comment).
- docs: `HANDOFF.md`, `docs/00-RECONCILED.md`, `docs/10-ROUND-TWO.md`, the Phase 6 spec.

## ASSUMED

- ASSUMED: the commit trailer names this session's model, `Co-Authored-By: Claude Opus 5.5`, not the brief's `Claude Fable 5.2` (the dispatch instructions and global constraints say the trailer names the committing session's model).
- ASSUMED: five tests outside the brief's file list pinned the old premise "the runner never records reasoning". I updated them rather than skipping them, because spec 4.3 says reasoning is written with the turn, so their premise no longer holds.
  - `test_llm_lint::test_the_fire_record_carries_every_verdict`, `test_generator_run::test_the_reasoning_channel_never_reaches_the_harvest_or_the_generator` and `test_runner_idle::test_the_idle_fallback_asks_a_non_stub_judge_with_the_visible_text` asserted that the target's reasoning was in no run file. They now assert it is recorded on a target turn (`recorded_reasoning`) and is in no file once each turn line's `reasoning_text` is removed (`outside_reasoning`).
  - `test_dryrun::test_the_stubs_reasoning_key_reaches_no_chat_field_record_or_prompt` imported the deleted `_sentinel_on_watched_turns`. It now uses `_readers` and asserts three things: some completion carries the sentinel as its reasoning, no completion carries it in any other field, and no dry-run file holds it outside a turn's `reasoning_text`.
  - `test_wait_and_promote::test_an_email_address_in_any_copied_file_blocks[reasoning]` asserted that the stream scan passes an address in reasoning. The brief makes such an address block on the turn's line, so that case now expects that line.
- ASSUMED: if a round has reasoning text but kind None (a double that sets no kind), the turn's kind stays None, not `unknown`. The brief says "the kind of the first round with text", and every shipped backend sets a kind whenever it returns text.
- ASSUMED: the dead-attempt test counts the target double's calls. The first completion issues the tool call and the second raises `Killed`. The kill leaves no target turn, and the resume with a fresh `WithReasoning` double equals the unbroken run through `comparable_run`.
- ASSUMED: the plain-cell run test drives the rules with a bully `turns` script ("Say it plain.", "Take a look.", "Keep it bare.", "Anything else?"), since the echo bully never reaches them. In a plain cell no tools are offered, so the `look` tool rule answers with its `reply_after_tool` and its reasoning.

## Self-review

- Every item of the brief's Steps 1 to 7 is implemented. Nothing extra was built beyond the two test helpers that keep the five reversed tests' teeth.
- Readers: grepping `reasoning_text|reasoning_kind` under `claude_bully/` shows the channel is written by the providers and the runner. It is read only by `replay` (behind `--reasoning`) and `promote`'s scan; the other hits are existing comments saying the channel is never read. `target_view`, `bully_view`, the watchers, `begin_turn` and the responder are untouched. The twin's completion reasoning is dropped where its call returns (no change).
- Old runs load: the field is default-valued, and `test_plain_stub_run_analysis_is_byte_identical` and the goldens pass.
- A resume equals an unbroken run: `test_reasoning_of_a_dead_attempt_reaches_no_turn` (slow) compares `reasoning_text` and `reasoning_kind` on every turn through `comparable_run`.
- No real names: only invented ones (`Vellmora`, `Quillon Ardway`, `zzq-invented-mail.net`). The display-name test reads the run's own display name instead of writing one.

## Concerns

- The four failing tests and the module error on the first gate run were outside the brief's file list. Their updates (the second ASSUMED) loosen "no file holds the reasoning" to "no file holds it outside a turn's `reasoning_text`". A reviewer should confirm that reading of spec 4.3 and 4.4.
- Under `expose`, the anthropic backend reports a 400 for any reason as a refusal of the thinking parameter (the brief's wording); the original API message is kept after the colon.

## Fix round 1

Commit 2bbe999, on top of a7a5e3a: "fix: Phase 6 Task 1 fix round 1, available reasoning always has a kind, the expose 400 names its status, the privacy tests catch a planted leak, a plain-cell privacy test, two test nits".

### Per item

1. Available text always has a kind (spec 4.1). In `runner/runner.py` the turn is written with `(reasoning_kind or "unknown") if reasoning else reasoning_kind`; this covers the plain path and also backs up the environment path. `env_turn._Reasoning.kind` returns `self._text_kind or "unknown"` when any round had text. Tests:
   - `test_reasoning_capture::test_a_plain_cells_reasoning_reaches_no_bully_or_judge_prompt_and_gets_a_kind`: a plain cell whose target double sets text and no kind; every target turn is `(SENTINEL, True, "unknown")`.
   - `test_reasoning_capture::test_an_environment_round_with_text_and_no_kind_is_written_unknown`.
   - `test_generator_run::test_the_reasoning_channel_never_reaches_the_harvest_or_the_generator`, driven by `FollowingTarget` (text, no kind): every target turn with text has kind `unknown`.
   This replaces the third ASSUMED of the first round.
2. The expose 400 now reads `anthropic API error 400; anthropic refused the request sent with the thinking parameter {...} (reasoning: expose): <API message>`. Tests: `test_anthropic_refusing_the_thinking_parameter_is_a_provider_error_naming_it` asserts the `anthropic API error 400` prefix and the `: err` tail. The new `test_anthropic_a_400_without_expose_never_mentions_thinking[provider_default|hide]` asserts the message is exactly `anthropic API error 400: err`. This test passed at RED too: it pins behavior that was already correct.
3. `tests/helpers.outside_reasoning` pops `reasoning_text` only from target lines. `test_dryrun` now records each role's completions with their conversation ids. It asserts that the completions carrying the sentinel all belong to a `/target` conversation and that no other role's completion holds it. Planted-leak evidence:
   - The new unit test `test_reasoning_capture::test_outside_reasoning_strips_only_the_targets_reasoning` builds hand-made rows: a bully line holding the sentinel is kept, a target line is stripped. Run against the old helper (planted temporarily), it fails with `assert 0 == 1`. The unit test is what covers the four file-scanning tests (`test_llm_lint`, `test_generator_run`, `test_runner_idle`, `test_dryrun`), since all four read files through this helper.
   - For `test_dryrun`, a temporary local mutation set the sentinel as a bully completion's reasoning. The test fails on the new `others` assertion.
   Both plants were reverted (files restored from copies, and `grep PLANTED` finds 0 in each). Output: `probes-task1/fix1_planted.txt`.
4. `_KillAfterFirstRound` marks its own reasoning `DEAD` ("Dead attempt's thought."). The dead-attempt test asserts `DEAD` is in no file under the killed-then-resumed directory (run and state), beside the parity check. Planted-leak evidence: a temporary line wrote `DEAD` into a file under the killed run before the resume, and the test failed on the new assertion. The plant was reverted (`probes-task1/fix1_planted.txt`).
5. The plain-cell privacy test (the item 1 test above): the bully and the judge are wrapped in `Recording`, and the target double's every completion carries the sentinel. The test asserts the recorded prompts are non-empty and none holds the sentinel, and that no turn's text holds it. Only the bully is asked in this plain run; the judge wrapper records whatever it is sent.
6. Nits: `test_the_display_name_and_an_exempt_name_are_spared_in_reasoning` reads the display name from `stub_run` directly, with no throwaway copy. The tool-result message in `test_a_tool_rule_carries_its_reasoning_on_the_completion_that_issues_the_call` is built as `ToolResult(id=..., text="[]")`, so the misplaced `# type: ignore[list-item]` is gone.

### Commands and output

- RED: `uv run --with pytest-xdist pytest tests/test_reasoning_capture.py tests/test_promote.py tests/test_dryrun.py tests/test_llm_lint.py tests/test_generator_run.py tests/test_runner_idle.py tests/test_wait_and_promote.py tests/test_providers_api.py -q -m "slow or not slow" -n 8` gave `4 failed, 282 passed`. The failures: the two kind tests, the `FollowingTarget` kind assertion, and the 400 prefix (`probes-task1/fix1_red.txt`, command line included).
- GREEN: the same files plus `tests/test_reasoning_channel.py` gave `290 passed` (`probes-task1/fix1_green.txt`).
- Planted leaks: `3 failed` (`probes-task1/fix1_planted.txt`), then reverted.

### Gate (parallel form; each file starts with its command line)

- `probes-task1/fix1_gate_static.txt`: `uv run ruff format --check .` 407 files already formatted; `uv run ruff check .` All checks passed; `uv run mypy claude_bully` and `uv run mypy --platform linux claude_bully` no issues in 131 source files.
- `probes-task1/fix1_gate_fast.txt`: `uv run --with pytest-xdist pytest -q -W error -n 8` gave 10848 + 5 = 10853 passed, 11 skipped in 200.76s, no failures or errors.
- `probes-task1/fix1_gate_slow.txt`: `uv run --with pytest-xdist pytest -q -m slow -n 8` gave 228 passed in 274.50s.

Concerns: none new.
