# Phase 6 Task 1 review: reasoning capture (afff3a2..a7a5e3a)

Scope: the brief, the global constraints and review focus, spec section 4 and the "As planned" lines D-kind and D-responder, the implementer's report, and the whole diff (3462 lines, read in passes). Focused checks outside the diff are named with their risk below. No suite was re-run; no probe script was needed.

## Spec Compliance

Compliant. Every file the brief lists is changed, and every interface it produces is there with the signature it names:

- `config.ReasoningMode`, `RoleConfig.reasoning: ReasoningMode = "provider_default"` (config.py).
- `records.ReasoningKind`; `Turn.reasoning_kind` placed after `reasoning_available`, default None, no validator (records.py).
- `Completion.reasoning_kind`; `build_provider` passes `reasoning=role.reasoning` to all four backends (providers/base.py).
- Stub: both `reasoning_of` methods are the brief's bodies; `complete` asks before `respond`, drops under `hide`, treats "" as None, kind `full` (providers/stub.py). The `_Rule` and `TurnEntry` docstrings lost "unused until Phase 6".
- Anthropic: `THINKING_REQUEST`; `thinking` sent only under `expose`, no budget; the 400-under-`expose` message is the brief's; the kind table follows D-kind; `hide` still replays thinking blocks in an open tool loop (anthropic_api.py, `_reasoning`).
- Claude Code: `streams(json_schema, tools)`; `build_args` takes the format from it and keeps the MCP flags on `tools`; `complete` resets `thinking_seen`/`mcp_servers_seen` whenever it streams, uses `_stream_failure_text` on any failed streaming call, reads `_new_tool_calls` only with tools; `parse_stream` keeps text only under `expose` (claude_code.py).
- OpenAI compat: a non-empty `reasoning_content` string, kind `unknown`, unless `hide` (openai_compat.py).
- Runner: the plain cell copies the completion's reasoning; `TargetTurn` gains `reasoning` and `reasoning_kind` after `cutoff`, filled at both return sites, `_cut_off` included; the runner joins the rounds with a blank line (runner.py, env_turn.py). `responder_role` forces `provider_default` on every branch.
- `replay --reasoning`: the `_SHAPES` entry, `_ESCAPED_FIELDS["reasoning"]`, `render_replay(..., reasoning=False)`, `replay_cell(..., reasoning=False)`, the CLI option with the brief's help text; `show` is the same function (replay.py, cli.py).
- `promote.scan_real_names`: reasoning hits are `reported` as `(target, reasoning)`, an address blocks on the turn's own line; `scan_run` is untouched (promote.py).
- Tests: every brief test is present, with the assertions the brief lists. `tests.helpers` gains `Killed`, `scrubbed` and `comparable_run`, which `test_bundle_run.py` imports back as `_Killed` and `_comparable`. `_scrubbed` is not re-imported because nothing there uses it, which is right.
- Docs-sync: HANDOFF (the carry is closed, Progress gains the item), `00-RECONCILED.md` G14, E and H, `10-ROUND-TWO.md` Part 2, the spec's two "As planned" lines. The added Markdown has no em or en dashes.

Files outside the brief's list, judged on their merits:

- `tests/test_dryrun.py`: forced. It imported `_sentinel_on_watched_turns`, which the brief deletes, so this was a slip in the plan. The rewrite keeps the harvest-reader half and the prompt half.
- `tests/test_llm_lint.py`, `tests/test_generator_run.py`, `tests/test_runner_idle.py`: forced by spec 4.3 ("written with the turn and only with the turn"). Each keeps its prompt assertions. "In no file" becomes "recorded on a target turn, and in no file outside a turn line's `reasoning_text`", which is the spec's own rule. I agree with the implementer's reading of 4.3 and 4.4. The helper is a little too loose (Minor 3).
- `tests/test_wait_and_promote.py` `[reasoning]`: forced by the brief's promote step, since an address in reasoning now blocks at the stream scan. The file scan of a turns line is still covered by the `bully_meta` case in the same test.
- `tests/test_stub_turns.py`: one stale comment corrected.

Extra: none in production code. Two test helpers were added (`outside_reasoning`, `recorded_reasoning`).

Small deviation: the brief puts the `run_analysis.rate_all` wrapper inside `_readers`, but it stays inline in `test_no_rating_prompt_holds_the_reasoning_channel` (tests/test_reasoning_channel.py:~140). It works the same way, so this is not an issue.

Cannot verify from the diff:

1. Whether the fast gate ran with `-W error`. `probes-task1/gate_fast.txt` does not record its command line, and the report says it did. The controller should confirm from the shell history or rerun one module with `-W error`.
2. The cost of the three unmarked run-level tests in `tests/test_reasoning_capture.py` (`test_a_plain_cell_records_its_completions_reasoning`, plus `test_an_environment_turn_joins_every_rounds_reasoning` and `test_a_redacted_round_never_makes_reasoning_available`, which run two env experiments each). R-I12 allows two runs, but "more than a few seconds" needs a `--durations` reading.

## Strengths

- The reasoning lives in a local and the `TargetTurn` until the one `Turn(...)` construction (runner.py:~422, the only `speaker=Speaker.target` site in the package). No runtime state, MCP state or attempt marker ever holds it, so "a dead attempt leaves none" holds by construction, and the slow kill test confirms it through `comparable_run`.
- `_Reasoning` (env_turn.py) is a small, single-purpose accumulator. It makes D-kind ("never `redacted` beside available text") a property, so the rule is not left to the call sites.
- The claude_code change is careful about the leak surface. Every streaming failure now quotes event types and lengths only, toolless `expose` calls included, and the new `thinking_died` test has real teeth: the fake writes `THINKING` into the torn line.
- `test_reasoning_channel.py` now reads the runner's own records, and `_store_marked` adds a third half: the store itself must carry the sentinel. Without that half, a silent regression to "records nothing" would make the privacy tests vacuous.
- The provider tests cover the whole mode-by-response table, including the "no `budget_tokens` anywhere" check through a recursive key walk.

## Issues

### Critical

None.

### Important

None.

### Minor

1. **A turn can record available text with kind None, against spec 4.1** (runner.py:~396 and ~416, env_turn.py `_Reasoning.add`). Spec 4.1: when `reasoning_available` is true, "the kind is `full`, `summarized` or `unknown`". The runner copies `completion.reasoning_kind` as it is. A completion with text and no kind therefore writes `(text, True, None)`. The implementer flagged this as an ASSUMED. No shipped backend does it, but the suite's own doubles do: `tests/fixtures/generator_stub.py:377,386` (`FollowingTarget`) and `tests/fixtures/director_stub.py:169` set `reasoning_text` with no kind, so the suite writes turn records the spec says cannot exist. `render_replay` already falls back to `unknown`, which shows the case was anticipated. Fix: in the runner (plain and env), write `reasoning_kind or "unknown"` whenever the text is non-empty, and add one assertion to an existing double-driven test. This matters before Task 2 and Task 3a start reading the kind.

2. **Under `expose`, every anthropic 400 is reported as a refusal of the thinking parameter** (anthropic_api.py:~474; plan-mandated). A 400 from a too-long context, a bad tool schema or a `temperature` the API rejects beside thinking gets the same text. The sentence is literally true ("refused the request sent with the thinking parameter"), and `exc.message` is kept after the colon, so the true cause is still visible. That is why this is Minor and not Important. Two small improvements: add the status code (`anthropic API error 400, request sent with the thinking parameter ...: <message>`) so the generic and the `expose` errors read alike, and add a test that a 400 under `provider_default` or `hide` does not mention `thinking`. Today only the `expose` branch is tested.

3. **`outside_reasoning` strips `reasoning_text` from every turn line, not only from target lines** (tests/helpers.py:~1867). The four reversed tests would pass if the target's reasoning leaked into a bully turn's `reasoning_text`. Fix: pop the key only where `row["speaker"] == "target"`. Similarly, `test_dryrun`'s `any(c.reasoning_text == SENTINEL ...)` with the chat-only check would accept the sentinel as a bully or generator completion's reasoning. Asserting that only target-conversation completions carry it would close that.

4. **The dead-attempt test cannot tell the dead attempt's reasoning from the resumed attempt's** (tests/test_reasoning_capture.py:~249). Both attempts mark "Marked.", so the only thing that could catch a leak is a changed count of joined copies. Giving `_KillAfterFirstRound` its own marker ("Dead.") and asserting it is in no file under the killed run would make the test check the property its name claims, not just parity.

5. **No plain-cell privacy assertion.** `test_a_plain_cell_records_its_completions_reasoning` checks what is recorded, but not that the plain cell's bully, strategy and judge prompts lack it. The environment tests cover `bully_view` (the same function). A plain strategy reading turn history is only covered by reading the code: grepping `reasoning_text` under `claude_bully/` shows no reader but replay and promote. A `Recording` around the plain bully with a sentinel rule would pin it cheaply.

6. **Test nits.** In `test_the_display_name_and_an_exempt_name_are_spared_in_reasoning` (tests/test_promote.py:~2257), a throwaway copy is made only to read the display name; `display_names(RunStore(stub_run.parent, stub_run.name))` gives the same. The `# type: ignore[list-item]` in `test_a_tool_rule_carries_its_reasoning_on_the_completion_that_issues_the_call` landed on the closing-paren line after formatting. That is harmless, since mypy runs only on `claude_bully`.

### Named risks checked (risk, then the one check)

- **A reader carries recorded reasoning to a forbidden place.** I grepped `reasoning_text|reasoning_kind|reasoning_available` under `claude_bully/`. Readers: `replay` (behind the flag), `promote.scan_real_names`, the runner and the providers. I grepped whole-turn serialisation (`model_dump` on turns or conversations): only `RunStore.append_turn`/`read_conversation`, which is the record itself, and `write_conversation`, which excludes turns. `_last_completion` is read only by `is_termination`. The responder's role is forced to `provider_default`, and the MCP server keys responders in process only (mcp_server.py:461). No leak found.
- **A run recorded before this change still loads.** The field is additive and default-valued under `extra="forbid"`. No validator was added. `Completion` is never read from disk (grep for `Completion.model_validate` found nothing). The plain goldens pass unchanged, per the report.
- **A resumed run equals an unbroken one.** The reasoning has one write site (the `Turn`), and `comparable_run` now compares whole turns. The slow kill test passes, per the report. See Minor 4 for its sharpness.

## Assessment

Task quality: **Approved.** The channel is captured where the spec says, written only with its turn, and kept out of every reader I could find. The changes to the five tests outside the brief were forced and follow spec 4.3. Minor 1, normalising the kind when text is present, is worth folding in before Task 2 reads `reasoning_kind`.
