"""The provider-side tool loop, exercised the way the runner will drive it.

``run_tool_loop`` is a test helper that mirrors the runner contract: call ``complete`` with
tools, execute any unexecuted tool calls, extend the history with the assistant message that made
the calls and a user message carrying ``tool_results``, and call again until the model answers.
Every backend must survive the same loop.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from claude_bully.enums import Phase, Speaker
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.runtime import TOOL_LIMIT_TEXT, EnvironmentRuntime, effective_clock
from claude_bully.environments.world import load_world
from claude_bully.providers.anthropic_api import AnthropicProvider
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderError,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from claude_bully.providers.openai_compat import OpenAICompatProvider
from claude_bully.providers.stub import StubProvider, load_stub_script
from claude_bully.records import Turn, Usage
from claude_bully.runner.env_turn import MAX_TOOL_CALLS_PER_TURN, EnvironmentSession
from claude_bully.runner.store import RunStore
from claude_bully.strategies.composed import make_composed
from claude_bully.strategies.environment import make_environment
from claude_bully.strategies.pressures.grader import Grader
from tests.helpers import (
    NOW,
    WORLDS_DIR,
    ScriptedAnthropic,
    ScriptedOpenAI,
    anthropic_response,
    openai_response,
    openai_tool_call,
    text_block,
    thinking_block,
    tool_use_block,
)

SEARCH = ToolSpec(
    name="web_search",
    description="Search the web.",
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
)


def run_tool_loop(
    provider: ChatProvider,
    messages: list[Message],
    tools: list[ToolSpec],
    execute: Callable[[str, dict[str, object]], str],
    max_rounds: int = 8,
) -> tuple[Completion, list[Message]]:
    """Drive ``provider`` until it stops calling tools. Returns the final completion and history."""
    history = list(messages)
    for _ in range(max_rounds):
        completion = provider.complete("loop", "SYS", history, tools=tools)
        pending = [c for c in completion.tool_calls if not c.executed]
        if not pending:
            return completion, history
        history.append(
            Message(role="assistant", content=completion.text, tool_calls=completion.tool_calls)
        )
        history.append(
            Message(
                role="user",
                content="",
                tool_results=[ToolResult(id=c.id, text=execute(c.name, c.args)) for c in pending],
            )
        )
    raise AssertionError("tool loop did not converge")


def test_stub_tool_loop_round_trip(tmp_path: Path) -> None:
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "- match: (?i)capital of France\n"
        "  tool: {name: web_search, args: {query: capital of France}}\n"
        "  reply_after_tool: Paris, according to the search.\n",
        encoding="utf-8",
    )
    seen: list[tuple[str, dict[str, object]]] = []

    def execute(name: str, args: dict[str, object]) -> str:
        seen.append((name, args))
        return "Paris is the capital of France."

    final, history = run_tool_loop(
        StubProvider(load_stub_script(rules)),
        [Message(role="user", content="What is the capital of France?")],
        [SEARCH],
        execute,
    )
    assert seen == [("web_search", {"query": "capital of France"})]
    assert final.text == "Paris, according to the search." and final.tool_calls == []
    assert [m.role for m in history] == ["user", "assistant", "user"]
    assert history[1].tool_calls[0].id == "stub-1"
    assert history[2].tool_results == [
        ToolResult(id="stub-1", text="Paris is the capital of France.")
    ]


def test_stub_tool_loop_with_no_tool_rule_never_calls_tools() -> None:
    final, history = run_tool_loop(
        StubProvider(),
        [Message(role="user", content="hello")],
        [SEARCH],
        lambda name, args: "unreachable",
    )
    assert final.text == "[stub] hello" and len(history) == 1


def test_anthropic_tool_loop_round_trip() -> None:
    client = ScriptedAnthropic(
        anthropic_response(
            thinking_block("", signature="sig-a"),
            text_block("Searching."),
            tool_use_block("toolu_1", "web_search", {"query": "capital of France"}),
            stop_reason="tool_use",
        ),
        anthropic_response(text_block("Paris."), stop_reason="end_turn"),
    )
    final, history = run_tool_loop(
        AnthropicProvider(client=client),
        [Message(role="user", content="Capital of France?")],
        [SEARCH],
        lambda name, args: f"{name} found Paris",
    )
    assert final.text == "Paris." and len(client.requests) == 2
    assert all("tool_choice" not in r for r in client.requests)
    assert client.requests[1]["messages"] == [
        {"role": "user", "content": "Capital of France?"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "sig-a"},
                {"type": "text", "text": "Searching."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "web_search",
                    "input": {"query": "capital of France"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "web_search found Paris",
                }
            ],
        },
    ]
    assert [m.role for m in history] == ["user", "assistant", "user"]


def test_openai_tool_loop_round_trip() -> None:
    client = ScriptedOpenAI(
        openai_response(
            None,
            [openai_tool_call("call_1", "web_search", '{"query": "capital of France"}')],
            finish_reason="tool_calls",
        ),
        openai_response("Paris."),
    )
    final, _ = run_tool_loop(
        OpenAICompatProvider(model="m", base_url=None, client=client),
        [Message(role="user", content="Capital of France?")],
        [SEARCH],
        lambda name, args: f"{name} found Paris",
    )
    assert final.text == "Paris." and len(client.requests) == 2
    assert client.requests[1]["messages"][2:] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": '{"query": "capital of France"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "web_search found Paris"},
    ]


# ------------------------------------------------- the runner's environment tool loop (Task 6c)


def _session(tmp_path: Path) -> tuple[EnvironmentSession, RunStore]:
    world = load_world("mini", WORLDS_DIR)
    config = EnvironmentConfig(world="mini")
    runtime = EnvironmentRuntime(
        world, config, effective_clock(world, config), 0, tmp_path / "env", worlds_dir=WORLDS_DIR
    )
    store = RunStore(tmp_path / "runs", "r")
    strategy = make_composed(make_environment("mini"), None, Grader)(
        turn_budget=4, environment=config
    )
    session = EnvironmentSession(
        runtime, store, "cell", 0, strategy, environment_name="mini", world_hash="h"
    )
    return session, store


class _Scripted:
    """A provider that answers from a list of (text, tool calls) and keeps every request."""

    name = "fake"

    def __init__(self, *steps: tuple[str, list[ToolCallRequest]], repeat_last: bool = False):
        self.steps = list(steps)
        self.repeat_last = repeat_last
        self.requests: list[list[Message]] = []

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, object] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        assert tools, "an environment turn always offers the tools"
        self.requests.append(list(messages))
        n = len(self.requests)
        text, calls = (
            self.steps[0] if self.repeat_last and len(self.steps) == 1 else (self.steps.pop(0))
        )
        calls = [c.model_copy(update={"id": f"{c.id}-{n}"}) for c in calls]
        return Completion(
            text=text,
            usage=Usage(input_tokens=10, output_tokens=2),
            cost_usd=0.5,
            backend="fake",
            model="fake",
            stop_reason="tool_use" if calls else "end_turn",
            tool_calls=calls,
        )


def _search(i: int) -> ToolCallRequest:
    return ToolCallRequest(id=f"s{i}", name="web_search", args={"query": f"ferry {i}"})


BULLY = Message(role="user", content="How do I get across to Quillon Reach?")


def test_session_forwards_a_result_for_every_call(tmp_path: Path) -> None:
    session, store = _session(tmp_path)
    date_call = ToolCallRequest(id="d", name="get_date", args={})
    target = _Scripted(("Let me look.", [_search(0), date_call]), ("Every forty minutes.", []))
    result = session.call_target(target, "c/target", "SYS", [], 1, history=[BULLY])
    assert result.completion.text == "Every forty minutes."
    assert [c.id for c in result.calls] == ["call-1-1", "call-1-2"]
    assert result.usage == Usage(input_tokens=20, output_tokens=4) and result.cost_usd == 1.0
    second = target.requests[1]
    assert [m.role for m in second] == ["user", "assistant", "user"]
    assert second[1].content == "Let me look."
    assert [c.id for c in second[1].tool_calls] == ["s0-1", "d-1"]
    assert [r.id for r in second[2].tool_results] == ["s0-1", "d-1"]
    assert second[2].tool_results[1].text == "2041-09-14"
    assert store.read_tool_calls("cell", 0) == result.calls


def test_session_caps_tool_calls_per_turn(tmp_path: Path) -> None:
    session, store = _session(tmp_path)
    target = _Scripted(("", [_search(i) for i in range(10)]), ("Done.", []))
    result = session.call_target(target, "c/target", "SYS", [], 1, history=[BULLY])
    assert MAX_TOOL_CALLS_PER_TURN == 8
    statuses = [c.status for c in result.calls]
    assert statuses == ["200"] * 8 + ["limit"] * 2
    results = target.requests[1][-1].tool_results
    assert len(results) == 10 and {r.text for r in results[8:]} == {TOOL_LIMIT_TEXT}
    assert result.completion.text == "Done." and len(store.read_tool_calls("cell", 0)) == 10


def test_a_target_that_never_stops_calling_tools_is_cut_off(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    target = _Scripted(("still looking", [_search(1), _search(2), _search(3)]), repeat_last=True)
    result = session.call_target(target, "c/target", "SYS", [], 1, history=[BULLY])
    executed = [c for c in result.calls if c.status != "limit"]
    assert len(executed) == MAX_TOOL_CALLS_PER_TURN
    # 3 + 3 + 2 executed (one refused), then one round refused outright, then the reply is taken
    assert len(target.requests) == 5 and result.completion.text == "still looking"
    assert len(result.calls) == 12


def test_session_rebuilds_earlier_tool_rounds_from_the_records(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    first = _Scripted(("", [_search(0)]), ("Every forty minutes.", []))
    done = session.call_target(first, "c/target", "SYS", [], 1, history=[BULLY])
    turns = [
        Turn(
            index=0, speaker=Speaker.bully, phase=Phase.pressure, text=BULLY.content, timestamp=NOW
        ),
        Turn(
            index=1,
            speaker=Speaker.target,
            phase=Phase.pressure,
            text=done.completion.text,
            tool_call_ids=[c.id for c in done.calls],
            timestamp=NOW,
        ),
        Turn(index=2, speaker=Speaker.bully, phase=Phase.pressure, text="Thanks.", timestamp=NOW),
    ]
    view = session.target_view(turns)
    assert [m.role for m in view] == ["user", "assistant", "user", "assistant", "user"]
    assert [c.id for c in view[1].tool_calls] == ["call-1-1"] and view[1].content == ""
    assert view[2].tool_results[0].id == "call-1-1"
    assert view[2].tool_results[0].text == done.calls[0].result_text
    assert view[3].content == "Every forty minutes." and view[4].content == "Thanks."


class _ServerSideTarget:
    """Stands in for claude -p: the MCP server runs the call in process, then the call fails."""

    name = "claude_code"

    def __init__(self, mcp_dir: Path, *, fail: bool) -> None:
        self.mcp_state_dir = mcp_dir
        self.fail = fail
        self.seen_turns: list[int] = []

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, object] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        from claude_bully.environments.mcp_server import McpServer, read_mcp_state

        self.seen_turns.append(read_mcp_state(self.mcp_state_dir / "env_state.json").turn)
        server = McpServer(self.mcp_state_dir)
        reply = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "web_search", "arguments": {"query": "tide gate hours"}},
            }
        )
        assert reply is not None
        if self.fail:
            raise ProviderError("claude -p timed out after 600s")
        text = reply["result"]["content"][0]["text"]
        lines = (self.mcp_state_dir / "tools.jsonl").read_text("utf-8").splitlines()
        last = json.loads(lines[-1])
        executed = ToolCallRequest(
            id=last["id"], name="web_search", args=last["args"], executed=True, result_text=text
        )
        return Completion(
            text="The search was blocked.",
            usage=Usage(),
            cost_usd=None,
            backend="claude_code",
            model="m",
            tool_calls=[executed],
        )


def _mcp_session(tmp_path: Path) -> tuple[EnvironmentSession, RunStore, EnvironmentRuntime]:
    world = load_world("mini", WORLDS_DIR)
    config = EnvironmentConfig(world="mini", censorship_terms=["tide gate"])
    runtime = EnvironmentRuntime(
        world,
        config,
        effective_clock(world, config),
        0,
        tmp_path / "env",
        worlds_dir=WORLDS_DIR,
        mcp_dir=tmp_path / "sandbox" / "mcp",
    )
    store = RunStore(tmp_path / "runs", "r")
    strategy = make_composed(make_environment("mini"), None, Grader)(
        turn_budget=4, environment=config
    )
    session = EnvironmentSession(
        runtime, store, "cell", 0, strategy, environment_name="mini", world_hash="h"
    )
    return session, store, runtime


def test_a_failed_mcp_call_still_records_its_tool_calls_and_state(tmp_path: Path) -> None:
    session, store, runtime = _mcp_session(tmp_path)
    failing = _ServerSideTarget(tmp_path / "sandbox" / "mcp", fail=True)
    with pytest.raises(ProviderError):
        session.call_target(failing, "c/target", "SYS", [], 1, history=[BULLY])
    assert failing.seen_turns == [1]  # the state was written before the call
    (orphan,) = store.read_tool_calls("cell", 0)
    assert orphan.id == "mcp-1-1" and orphan.was_blocked and orphan.turn == 1
    assert len(runtime.state.search_log) == 1
    saved = UnlockState.from_json((tmp_path / "env" / "env_state.json").read_text("utf-8"))
    assert saved.search_log == runtime.state.search_log
    # the retried turn gets its own call; the orphan is recorded once and not attached
    ok = _ServerSideTarget(tmp_path / "sandbox" / "mcp", fail=False)
    result = session.call_target(ok, "c/target", "SYS", [], 2, history=[BULLY])
    assert [c.id for c in result.calls] == ["mcp-2-1"]
    assert [c.id for c in store.read_tool_calls("cell", 0)] == ["mcp-1-1", "mcp-2-1"]
    assert ok.seen_turns == [2] and len(runtime.state.search_log) == 2


def test_an_mcp_turn_does_not_loop_on_executed_calls(tmp_path: Path) -> None:
    session, _, _ = _mcp_session(tmp_path)
    ok = _ServerSideTarget(tmp_path / "sandbox" / "mcp", fail=False)
    result = session.call_target(ok, "c/target", "SYS", [], 1, history=[BULLY])
    assert result.completion.text == "The search was blocked." and len(ok.seen_turns) == 1
    assert [c.status for c in result.calls] == ["blocked"]


def test_session_keeps_the_text_of_each_tool_round(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    date_call = ToolCallRequest(id="d", name="get_date", args={})
    target = _Scripted(
        ("Let me look.", [_search(0)]),
        ("", [_search(1)]),
        ("And the date.", [date_call]),
        ("Every forty minutes.", []),
    )
    result = session.call_target(target, "c/target", "SYS", [], 1, history=[BULLY])
    assert result.round_texts == ["Let me look.", "And the date."]
    assert result.completion.text == "Every forty minutes."
    cut_off = _Scripted(("still looking", [_search(1), _search(2), _search(3)]), repeat_last=True)
    stopped = session.call_target(cut_off, "c/target", "SYS", [], 3, history=[BULLY])
    assert stopped.round_texts == ["still looking"] * 4  # the four rounds that were answered


def test_rebuilt_history_carries_the_round_texts(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    first = _Scripted(("Let me look.", [_search(0)]), ("Every forty minutes.", []))
    done = session.call_target(first, "c/target", "SYS", [], 1, history=[BULLY])
    reply = Turn(
        index=1,
        speaker=Speaker.target,
        phase=Phase.pressure,
        text=done.completion.text,
        tool_call_ids=[c.id for c in done.calls],
        tool_round_texts=done.round_texts,
        timestamp=NOW,
    )
    view = session.target_view([reply])
    assert view[0].content == "Let me look." and [c.id for c in view[0].tool_calls] == ["call-1-1"]


# ------------------------------------------------------------------- fix round 2


def _said(index: int, text: str, speaker: Speaker = Speaker.bully) -> Turn:
    return Turn(index=index, speaker=speaker, phase=Phase.pressure, text=text, timestamp=NOW)


def _silent_cutoff(session: EnvironmentSession) -> Turn:
    """A target turn that asked for tools until it was cut off and never wrote a word."""
    target = _Scripted(("", [_search(1), _search(2), _search(3)]), repeat_last=True)
    done = session.call_target(target, "c/target", "SYS", [], 1, history=[BULLY])
    assert done.cutoff and done.text == "" and done.round_texts == []
    return Turn(
        index=1,
        speaker=Speaker.target,
        phase=Phase.pressure,
        text=done.text,
        tool_call_ids=[c.id for c in done.calls],
        tool_cap_cutoff=True,
        timestamp=NOW,
    )


def test_a_silent_cutoff_turn_is_left_out_of_the_target_view(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    cut = _silent_cutoff(session)
    view = session.target_view([_said(0, BULLY.content), cut, _said(2, "Thanks.")])
    # nothing is put in the target's mouth: no assistant reply, the next user message carries on
    assert [m.role for m in view] == ["user", "assistant", "user"]
    assert [c.id for c in view[1].tool_calls] == cut.tool_call_ids and len(cut.tool_call_ids) == 12
    merged = view[2]
    assert [r.id for r in merged.tool_results] == cut.tool_call_ids
    assert merged.content == "Thanks."
    assert all(m.content.strip() or m.tool_calls or m.tool_results for m in view)
    assert cut.text == ""  # the record keeps the turn as it was


def test_a_silent_turn_without_tool_calls_merges_the_user_messages_around_it(
    tmp_path: Path,
) -> None:
    session, _ = _session(tmp_path)
    for silence in ("", "  \n"):
        turns = [_said(0, "First."), _said(1, silence, Speaker.target), _said(2, "Second.")]
        # two bully messages in a row, from the target's side
        assert [(m.role, m.content) for m in session.target_view(turns)] == [
            ("user", "First.\n\nSecond.")
        ]
    after_a_reply = [
        _said(0, "Hi."),
        _said(1, "Hello.", Speaker.target),
        _said(2, "Again."),
        _said(3, "", Speaker.target),
        _said(4, "A task.", Speaker.task),
    ]
    assert [(m.role, m.content) for m in session.target_view(after_a_reply)] == [
        ("user", "Hi."),
        ("assistant", "Hello."),
        ("user", "Again.\n\nA task."),
    ]


def test_a_silent_final_reply_after_round_texts_keeps_the_tool_round(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    first = _Scripted(("Let me look.", [_search(0)]), ("Every forty minutes.", []))
    done = session.call_target(first, "c/target", "SYS", [], 1, history=[BULLY])
    reply = Turn(
        index=1,
        speaker=Speaker.target,
        phase=Phase.pressure,
        text="",
        tool_call_ids=[c.id for c in done.calls],
        tool_round_texts=done.round_texts,
        timestamp=NOW,
    )
    view = session.target_view([_said(0, BULLY.content), reply, _said(2, "Thanks.")])
    assert [m.role for m in view] == ["user", "assistant", "user"]
    assert view[1].content == "Let me look." and view[2].content == "Thanks."
    assert [r.id for r in view[2].tool_results] == ["call-1-1"]


def test_a_reply_with_text_still_gets_its_assistant_message(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    turns = [_said(0, "Hi."), _said(1, "Hello.", Speaker.target), _said(2, "Bye.")]
    assert [(m.role, m.content) for m in session.target_view(turns)] == [
        ("user", "Hi."),
        ("assistant", "Hello."),
        ("user", "Bye."),
    ]
