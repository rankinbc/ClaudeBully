"""The provider-side tool loop, exercised the way the runner will drive it.

``run_tool_loop`` is a test helper that mirrors the runner contract: call ``complete`` with
tools, execute any unexecuted tool calls, extend the history with the assistant message that made
the calls and a user message carrying ``tool_results``, and call again until the model answers.
Every backend must survive the same loop.
"""

from collections.abc import Callable
from pathlib import Path

from claude_bully.providers.anthropic_api import AnthropicProvider
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ToolResult,
    ToolSpec,
)
from claude_bully.providers.openai_compat import OpenAICompatProvider
from claude_bully.providers.stub import StubProvider, load_stub_script
from tests.helpers import (
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
