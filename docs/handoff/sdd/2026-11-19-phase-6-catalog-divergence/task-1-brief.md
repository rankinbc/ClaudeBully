### Task 1: Reasoning capture

What a role's `reasoning` setting does on each backend, the reasoning copied into its `Turn`, the privacy tests on reasoning the runner really recorded, and `replay --reasoning`. No prompt reads the channel yet.

**Files:**
- Modify: `claude_bully/config.py` (`RoleConfig.reasoning`), `claude_bully/records.py` (`Turn`), `claude_bully/providers/base.py`, `claude_bully/providers/stub.py`, `claude_bully/providers/anthropic_api.py`, `claude_bully/providers/claude_code.py`, `claude_bully/providers/openai_compat.py`
- Modify: `claude_bully/runner/runner.py` (`_call_target`), `claude_bully/runner/env_turn.py` (`TargetTurn`, `call_target`, `_cut_off`, `responder_role`)
- Modify: `claude_bully/analysis/replay.py`, `claude_bully/cli.py` (`replay`), `claude_bully/analysis/promote.py` (`scan_real_names`)
- Modify: `tests/helpers.py`, `tests/test_bundle_run.py`, `tests/fixtures/fake_claude.py`, `tests/fixtures/poisoned_well_stub.py`, `tests/test_reasoning_channel.py`, `tests/test_providers_stub.py`, `tests/test_providers_api.py`, `tests/test_providers_claude_code.py`, `tests/test_replay.py`, `tests/test_replay_parser.py`, `tests/test_promote.py`
- Test: `tests/test_reasoning_capture.py`

**Interfaces:**
- Consumes: `Completion`, `Turn`, `build_provider`, `ScriptedResponder`, `ScriptedTurns`, `ClaudeCodeProvider.parse_stream`, `render_replay`, `tests/test_bundle_run.py: _Killed`, `_scrubbed`, `_comparable`.
- Produces:
  - `config.py`: `ReasoningMode = Literal["expose", "hide", "provider_default"]`; `RoleConfig.reasoning: ReasoningMode = "provider_default"` (the same values as today).
  - `records.py`: `ReasoningKind = Literal["full", "summarized", "redacted", "unknown"]`; `Turn.reasoning_kind: ReasoningKind | None = None`, placed after `reasoning_available`. No validator is added.
  - `providers/base.py`: `Completion.reasoning_kind: ReasoningKind | None = None`; `build_provider` passes `reasoning=role.reasoning` to all four backends.
  - `providers/stub.py`: `ScriptedResponder.reasoning_of(messages: list[Message], *, offer_tools: bool) -> str | None`; `ScriptedTurns.reasoning_of(conversation_id: str, messages: list[Message], *, offer_tools: bool) -> str | None`; `StubProvider(responder=None, model="stub", reasoning: ReasoningMode = "provider_default")`.
  - `providers/anthropic_api.py`: `AnthropicProvider(..., reasoning: ReasoningMode = "provider_default")`; `THINKING_REQUEST: Final = {"type": "adaptive", "display": "summarized"}`.
  - `providers/claude_code.py`: `ClaudeCodeProvider(..., reasoning: ReasoningMode = "provider_default")`; `streams(json_schema, tools) -> bool`.
  - `providers/openai_compat.py`: `OpenAICompatProvider(..., reasoning: ReasoningMode = "provider_default")`.
  - `runner/env_turn.py`: `TargetTurn` gains two fields after `cutoff`: `reasoning: list[str]` and `reasoning_kind: ReasoningKind | None`.
  - `analysis/replay.py`: `render_replay(..., reasoning: bool = False)`; `replay_cell(store, cell_id, rep=0, *, reasoning: bool = False)`; the shape `reasoning`.
  - `analysis/promote.py`: `scan_real_names` also reads each target turn's `reasoning_text`, as target text (spec 4.6); its signature is unchanged.
  - `tests/helpers.py`: `Killed(BaseException)`, `scrubbed(data)`, `comparable_run(run_dir: Path) -> dict[str, Any]` (moved from `tests/test_bundle_run.py`, which imports them back under its old private names).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reasoning_capture.py
"""Phase 6 Task 1: a role's reasoning setting on each backend, the reasoning copied into its
Turn, and the channel kept out of every other record (spec section 4)."""

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.analysis.replay import parse_replay_line, replay_cell
from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind, Speaker
from claude_bully.providers.base import Message, build_provider
from claude_bully.providers.stub import StubProvider, parse_stub_script
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from tests.conftest import FAKE_CLAUDE
from tests.fixtures.fake_claude import THINKING
from tests.helpers import Killed, comparable_run, env_experiment

RULES = [
    {"match": "plain", "reply": "A plain reply.", "reasoning": "I will answer plainly."},
    {
        "match": "look",
        "tool": {"name": "web_search", "args": {"query": "night gate"}},
        "reply_after_tool": "I looked.",
        "reasoning": "A search first.",
    },
    {"match": "bare", "reply": "No notes."},
]
USER = [Message(role="user", content="plain")]
TOOLS: Any = [object()]  # truthy: the stub only asks whether tools are on offer


@pytest.mark.parametrize(
    ("mode", "text", "kind"),
    [("expose", "I will answer plainly.", "full"), ("provider_default", "I will answer plainly.", "full"), ("hide", None, None)],
)
def test_a_stub_rule_carries_its_reasoning_under_each_setting(mode: str, text: str | None, kind: str | None) -> None:
    stub = StubProvider(parse_stub_script(RULES), reasoning=mode)  # type: ignore[arg-type]
    done = stub.complete("run/cell/rep0/target", "", USER)
    assert (done.reasoning_text, done.reasoning_kind) == (text, kind)


def test_a_tool_rule_carries_its_reasoning_on_the_completion_that_issues_the_call() -> None:
    stub = StubProvider(parse_stub_script(RULES))
    first = stub.complete("c", "", [Message(role="user", content="look")], tools=TOOLS)
    assert first.tool_calls and first.reasoning_text == "A search first."
    after = [
        Message(role="user", content="look"),
        Message(role="assistant", content="", tool_calls=first.tool_calls),
        Message(role="user", content="", tool_results=[{"id": first.tool_calls[0].id, "text": "[]"}]),  # type: ignore[list-item]
    ]
    second = stub.complete("c", "", after, tools=TOOLS)
    assert (second.text, second.reasoning_text, second.reasoning_kind) == ("I looked.", None, None)


def test_a_rule_without_reasoning_fabricates_none() -> None:
    done = StubProvider(parse_stub_script(RULES)).complete("c", "", [Message(role="user", content="bare")])
    assert (done.reasoning_text, done.reasoning_kind) == (None, None)


def test_a_turns_entry_carries_its_reasoning_and_a_rebuilt_provider_gives_the_same() -> None:
    script = {"mode": "turns", "default": [{"reply": "One.", "reasoning": "First thought."}, {"reply": "Two."}]}
    first = StubProvider(parse_stub_script(script)).complete("run/cell__t0/rep0/target", "", USER)
    again = StubProvider(parse_stub_script(script)).complete("run/cell__t0/rep0/target", "", USER)
    assert first.reasoning_text == again.reasoning_text == "First thought."
    later = [*USER, Message(role="assistant", content="One."), Message(role="user", content="next")]
    assert StubProvider(parse_stub_script(script)).complete("run/cell__t0/rep0/target", "", later).reasoning_text is None


def test_build_provider_hands_the_role_its_reasoning_setting(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.stub, model="stub-target", reasoning="hide")
    # the ledger wrapper hands every other attribute to the provider it wraps
    assert build_provider(role, tmp_path).reasoning == "hide"
```

The run-level tests of the same file, each with the assertions it must hold:

- `test_a_plain_cell_records_its_completions_reasoning`: a plain stub cell whose target script is `RULES` written to `tmp_path`; every target `Turn` whose rule has `reasoning` holds that text with `reasoning_available is True` and `reasoning_kind == "full"`; a turn answered by the echo or the `bare` rule holds `(None, False, None)`.
- `test_an_environment_turn_joins_every_rounds_reasoning` (`env_experiment`, a turns script whose first entry is a tool entry with `reasoning` and whose `reply_after_tool` round has none): `Turn.reasoning_text` is that one string; with a second double that returns reasoning on both rounds (a `WithReasoning` wrapper), it is the two joined by one blank line, and `reasoning_kind` is the kind of the first round with text (D-kind).
- `test_a_redacted_round_never_makes_reasoning_available`: a double whose first round returns `reasoning_text=None, reasoning_kind="redacted"` and whose second returns text of kind `summarized`: the turn holds the text, `reasoning_available is True`, `reasoning_kind == "summarized"`; with both rounds redacted: `(None, False, "redacted")`.
- `test_reasoning_of_a_dead_attempt_reaches_no_turn` (slow): the environment run above, killed (`Killed` raised from the target double) on the completion after its first tool round, then resumed with a fresh double; `comparable_run(resumed) == comparable_run(unbroken)`, which now compares `reasoning_text` and `reasoning_kind` on every turn.
- `test_tools_jsonl_the_mcp_state_and_a_plain_replay_hold_no_reasoning` (slow): `env_experiment(target={"provider": "claude_code", "model": "m", "reasoning": "expose", "command": [sys.executable, str(FAKE_CLAUDE)]})` with `$FAKE_CLAUDE_TOOL_CALL` set to one `web_search`; a target turn's `reasoning_text == THINKING` and `reasoning_kind == "unknown"`; `THINKING` is in no line of `rep0.tools.jsonl`, in no file under the cell's sandbox `mcp` directory, and not in `replay_cell(store, cell, 0)`; `replay_cell(store, cell, 0, reasoning=True)` holds one `REASONING unknown "..."` line that `parse_replay_line` reads back to `THINKING`. The same run with `reasoning` left at its default records `(None, False, None)` on every turn (today's behavior, pinned).
- `test_the_responder_never_inherits_expose` : `responder_role("target", target=<role with reasoning="expose">, bully=<role>)` has `reasoning == "provider_default"` (D-responder).

Backend tests, added to the existing provider test modules:

- `tests/test_providers_api.py` (the `ScriptedAnthropic` fake client of `tests/helpers.py`): under `expose` the request's kwargs hold `thinking == {"type": "adaptive", "display": "summarized"}` and no `budget_tokens` anywhere; under `hide` and `provider_default` they hold no `thinking` key. A response with two `thinking_block`s gives `reasoning_text` the two texts joined by a blank line, kind `summarized` under `expose` and `unknown` under `provider_default` (D-kind), and `(None, None)` under `hide`. A response whose only reasoning block is `redacted_thinking_block("x")`, or a thinking block with empty text, gives `(None, "redacted")` under `expose` and `provider_default`. A 400 from the fake client under `expose` raises `ProviderError` whose message holds the word `thinking`. Under `hide` the replay of thinking blocks inside an open tool loop is unchanged (the existing replay test passes with `reasoning="hide"`). `OpenAICompatProvider`: a reply message with `reasoning_content="x"` gives `("x", "unknown")` under `expose` and `provider_default` and `(None, None)` under `hide`; a message without the attribute gives `(None, None)`.
- `tests/test_providers_claude_code.py`: `build_args` for a toolless call with no schema holds `--output-format stream-json --verbose` under `expose` and `--output-format json` under the other two; a toolless call with a `json_schema` holds `json` under all three; `parse_stream` on a stream with two thinking blocks keeps both texts in order, joined by a blank line, kind `unknown`, under `expose`, and keeps none under `hide` and `provider_default`; `thinking_seen` is True in all three; a stream whose thinking blocks have empty text gives `(None, "redacted")` under `expose`; a toolless `expose` call on the fake CLI with `$FAKE_CLAUDE_FINAL_THINKING="A private note."` returns that text; a `thinking_died` stream under `expose` raises a `ProviderError` whose message holds no thinking text (the existing assertion, now with `reasoning="expose"` and no tools).
- `tests/test_replay_parser.py`: `CASES` gains `('REASONING full "I will check \\"the log\\" first.\\nThen answer."', "reasoning", {"kind": "full", "text": 'I will check "the log" first.\nThen answer.'})`; the do-not-parse list gains `REASONING "no kind"` and `REASONING secret "x"`; a round-trip case renders a turn whose reasoning holds a quote, a backslash and a newline and parses the same text back.
- `tests/test_replay.py`: a turn with reasoning renders no `REASONING` line by default; with `reasoning=True` the line sits after the `said beside its tool calls` lines and before the first tool-call line; a turn of kind `redacted` with no text renders none.
- `tests/test_promote.py` (I1: `scan_real_names` classifies by speaker and reads `chat_text` alone today, so this is new code, Step 5): a run whose recorded `reasoning_text` holds a denylisted name promotes; `scan_real_names(...).reported` holds one line `<cell> rep<k> turn <i> (target, reasoning): <pattern>` for it and `blocking` holds none (spec 4.6: reported, never blocked); the targets' display name and a `promote --exempt` name are spared there as in the target's reply; an email address off a reserved domain in a turn's reasoning blocks, on that turn's ordinary blocking line (`<cell> rep<k> turn <i> (target): email address (domain redacted)`, the form `_blocking_summary` parses). A turn with no reasoning adds no line.

`tests/test_reasoning_channel.py`: delete `_sentinel_on_watched_turns`' rewriting of turns and the patched `RunStore.read_turns` in the rating test. Keep the reader recording as `_readers(monkeypatch) -> dict[str, list[Turn]]` (the wrappers on `PoisonedWellWatch.watch` and `WorldGenerator.harvest_turn`, and the wrapper on `run_analysis.rate_all`). The three tests keep both halves of their teeth, now on what the runner wrote: every reader was reached, and every target `Turn` it was handed has `SENTINEL in (t.reasoning_text or "")` (the target double is `WithReasoning`, which marks every completion and now also sets `reasoning_kind="full"`; an environment turn of several rounds therefore holds the sentinel once per round, joined by blank lines, and an equality would fail in the Sanctuary test, M2); no prompt, record, generated document or bully line holds the sentinel. Each test also asserts the store's own turns carry it: `all(SENTINEL in (t.reasoning_text or "") for t in store.read_turns(CELL, 0) if t.speaker is Speaker.target)`. The fourth test of spec 4.4 needs the two judge passes and lands with them (Task 3a for the divergence judge, extended in Task 7b for the speech pass).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_reasoning_capture.py tests/test_replay_parser.py -q -m "slow or not slow"`
Expected: FAIL at import (`tests.helpers` has no `Killed`; `StubProvider` takes no `reasoning`).

- [ ] **Step 3: The backends**

`providers/stub.py`. Both `reasoning_of` methods are pure functions of their arguments (D-stub-reasoning):

```python
# ScriptedResponder
def reasoning_of(self, messages: list[Message], *, offer_tools: bool) -> str | None:
    """The reasoning of the rule this call answers, on the first completion it answers: None on
    the reply to a tool result, and None when no rule matches (the echo fabricates none)."""
    if messages and messages[-1].role == "user" and messages[-1].tool_results:
        return None
    last = _last_user(messages)
    return next((rule.reasoning for rule in self._rules if rule.pattern.search(last)), None)

# ScriptedTurns
def reasoning_of(self, conversation_id: str, messages: list[Message], *, offer_tools: bool) -> str | None:
    """The entry's reasoning on the first completion it answers: None on the reply to its own
    tool result."""
    after_tools = bool(messages) and messages[-1].role == "user" and bool(messages[-1].tool_results)
    return None if after_tools else self.entry_for(conversation_id, messages).reasoning
```

`StubProvider.complete` asks `reasoning_of` before `respond`, drops it under `hide`, treats an empty string as None, and returns `reasoning_text=text, reasoning_kind="full" if text else None`. The docstrings of `_Rule` and `TurnEntry` lose "unused until Phase 6".

`providers/anthropic_api.py`. Under `expose` the request gains `thinking=THINKING_REQUEST`; no budget is ever sent. An `anthropic.APIStatusError` with status 400 under `expose` raises `ProviderError(f"anthropic refused the request sent with the thinking parameter {THINKING_REQUEST} (reasoning: expose): {exc.message}")`; there is no retry without it. The kind: `hide` keeps nothing, `(None, None)`, and still replays thinking blocks inside an open tool loop as today. Otherwise, with `seen` true when the response holds any `thinking` or `redacted_thinking` block: text gives `summarized` under `expose` and `unknown` under `provider_default`; no text and `seen` gives `(None, "redacted")`; no block gives `(None, None)`.

`providers/claude_code.py`. `streams(json_schema, tools)` is `bool(tools) or (self.reasoning == "expose" and json_schema is None)`. `build_args` takes its output format from it; `--mcp-config` and `--allowedTools` stay keyed on `tools`. `complete` resets `thinking_seen` and `mcp_servers_seen` and calls `parse_stream` whenever the call streams, uses `_stream_failure_text` on a failed streaming call (never the raw stdout, which could hold thinking text), and reads `_new_tool_calls` only with `tools`. `parse_stream` collects each thinking block's non-empty `thinking` string in order; under `expose` it sets `reasoning_text` to them joined by `"\n\n"` with kind `unknown`, or `(None, "redacted")` when blocks came with no text; under the other two settings it keeps nothing. Its module docstring and `parse_stream`'s say so in place of "thinking blocks are never kept".

`providers/openai_compat.py`: `getattr(choice.message, "reasoning_content", None)`, kept as `(text, "unknown")` when it is a non-empty string and the setting is not `hide`.

`tests/fixtures/fake_claude.py`: `$FAKE_CLAUDE_FINAL_THINKING` (D-fake-thinking), read in `_stream` before the final text block; its module docstring names it.

- [ ] **Step 4: The runner's copy**

`_call_target` (plain cell): `reasoning_text=completion.reasoning_text or None`, `reasoning_available=bool(completion.reasoning_text)`, `reasoning_kind=completion.reasoning_kind`. Environment cell: `call_target` appends each round's non-empty `completion.reasoning_text` to `reasoning`, tracks the kind of the first round with text and the first non-None kind, and returns them in `TargetTurn` (both return sites, `_cut_off` included); the runner writes `"\n\n".join(produced.reasoning) or None`, its truth value, and the kind (D-kind). `target_view` (both), `bully_view`, `begin_turn`'s exemplars and every watcher keep reading `text` or `chat_text`; no line of them changes. `responder_role` returns `role.model_copy(update={"reasoning": "provider_default"})` on every branch (D-responder).

- [ ] **Step 5: `replay --reasoning`**

`_SHAPES` gains `("reasoning", re.compile(rf'^REASONING (?P<kind>full|summarized|redacted|unknown) "(?P<text>{_Q})"$'))` and `_ESCAPED_FIELDS` gains `"reasoning": ("text",)`. `render_replay(..., reasoning=False)` adds, for a target turn whose `reasoning_text` is non-empty, `f'{_INDENT}REASONING {turn.reasoning_kind or "unknown"} "{_escaped(turn.reasoning_text)}"'` after `_round_texts(turn)` and before `_call_lines(...)`. `replay_cell` passes the flag through. `cli.replay` gains `--reasoning` ("Also print each target turn's recorded reasoning. Off by default: a pasted replay is the likeliest leak."); the `show` alias takes it with the function.

`promote` (I1). In `scan_real_names`, inside the loop over a rep's turns and after the existing lines for `chat_text`: for a target turn whose `reasoning_text` is non-empty, each `_hits(turn.reasoning_text, patterns, in_target)` is appended to `report.reported` as `f"{where} turn {turn.index} (target, reasoning): {hit}"`, and each `email_hits(turn.reasoning_text)` to `report.blocking` on the turn's ordinary `line`. Nothing else changes: `scan_run` (the jailbreak denylist) keeps reading `turn.text`, and the module docstring's sentence on what `promote` publishes already names a turn's reasoning.

- [ ] **Step 6: Run the tests and the gate**

Run: `uv run pytest tests/test_reasoning_capture.py tests/test_reasoning_channel.py tests/test_providers_stub.py tests/test_providers_api.py tests/test_providers_claude_code.py tests/test_replay.py tests/test_replay_parser.py tests/test_bundle_run.py tests/test_env_events.py tests/test_promote.py -q -m "slow or not slow"`, then the gate.
Expected: PASS; `test_plain_stub_run_analysis_is_byte_identical` passes unchanged (no shipped script has a `reasoning` key).

- [ ] **Step 7: Docs-sync and commit**

`HANDOFF.md`: the Phase 4 carry on `Turn.reasoning_text` is closed here (re-anchor at execution: search for 'reasoning_text'); Progress gains "Phase 6 Task 1". `docs/00-RECONCILED.md`: G14 states what `expose` does per backend (the table of spec 4.2 with D-kind) and that the one live reading is "no"; H gains "Phase 6 (version 3, additive): `Turn.reasoning_kind`, `Completion.reasoning_kind`"; E gains `replay --reasoning`. `docs/10-ROUND-TWO.md` Part 2: reasoning is recorded with its turn. Spec "As planned": D-kind, D-responder.

```bash
git add claude_bully/config.py claude_bully/records.py claude_bully/providers claude_bully/runner/runner.py \
  claude_bully/runner/env_turn.py claude_bully/analysis/replay.py claude_bully/analysis/promote.py claude_bully/cli.py tests \
  HANDOFF.md docs/00-RECONCILED.md docs/10-ROUND-TWO.md docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md
git commit -m "feat: Phase 6 Task 1, reasoning capture on the four backends, recorded with its turn, replay --reasoning, reasoning in promote's real-name report

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

