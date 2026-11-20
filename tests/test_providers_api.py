import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx
import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.providers.anthropic_api import AnthropicProvider
from claude_bully.providers.base import (
    Message,
    ProviderError,
    RateLimitError,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
    build_provider,
)
from claude_bully.providers.openai_compat import OpenAICompatProvider
from tests.helpers import (
    ScriptedAnthropic,
    ScriptedOpenAI,
    anthropic_response,
    openai_response,
    openai_tool_call,
    redacted_thinking_block,
    text_block,
    thinking_block,
    tool_use_block,
)


class _FakeMessages:
    def __init__(self, fail: Exception | None = None) -> None:
        self.kwargs: dict[str, Any] = {}
        self.fail = fail

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.fail:
            raise self.fail
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello back")],
            usage=SimpleNamespace(input_tokens=7, output_tokens=3),
            stop_reason="end_turn",
        )


class _FakeAnthropic:
    def __init__(self, fail: Exception | None = None) -> None:
        self.messages = _FakeMessages(fail)


def test_anthropic_omits_temperature_by_default() -> None:
    client = _FakeAnthropic()
    p = AnthropicProvider(client=client)
    out = p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert "temperature" not in client.messages.kwargs
    assert client.messages.kwargs["model"] == "claude-opus-5-5"
    assert client.messages.kwargs["system"] == "SYS"
    assert client.messages.kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert out.text == "hello back" and out.usage.input_tokens == 7
    assert out.backend == "anthropic" and out.stop_reason == "end_turn"


def test_anthropic_sends_temperature_when_set() -> None:
    client = _FakeAnthropic()
    AnthropicProvider(model="claude-sonnet-4-6", temperature=0.2, client=client).complete(
        "c", "SYS", [Message(role="user", content="hi")]
    )
    assert client.messages.kwargs["temperature"] == 0.2


def test_anthropic_structured_output_config() -> None:
    client = _FakeAnthropic()
    schema = {"type": "object", "properties": {"k": {"type": "string"}}}
    AnthropicProvider(client=client).complete(
        "c", "SYS", [Message(role="user", content="hi")], json_schema=schema
    )
    assert client.messages.kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": schema}
    }


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls("err", response=response, body=None)


def test_anthropic_maps_rate_limit() -> None:
    client = _FakeAnthropic(fail=_status_error(anthropic.RateLimitError, 429))
    with pytest.raises(RateLimitError):
        AnthropicProvider(client=client).complete("c", "S", [Message(role="user", content="x")])


def test_anthropic_maps_other_status_errors() -> None:
    client = _FakeAnthropic(fail=_status_error(anthropic.BadRequestError, 400))
    with pytest.raises(ProviderError):
        AnthropicProvider(client=client).complete("c", "S", [Message(role="user", content="x")])


class _FakeCompletions:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="yo"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=1),
        )


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


def test_openai_compat_sends_system_as_first_message() -> None:
    client = _FakeOpenAI()
    p = OpenAICompatProvider(model="llama", base_url="https://x.example", client=client)
    out = p.complete("c", "SYS", [Message(role="user", content="hi")])
    kwargs = client.chat.completions.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "SYS"}
    assert kwargs["model"] == "llama" and "temperature" not in kwargs
    assert out.text == "yo" and out.backend == "openai_compat"


def test_openai_compat_json_schema_response_format() -> None:
    client = _FakeOpenAI()
    schema = {"type": "object"}
    OpenAICompatProvider(model="m", base_url=None, client=client).complete(
        "c", "S", [Message(role="user", content="x")], json_schema=schema
    )
    rf = client.chat.completions.kwargs["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"] == schema


def test_openai_compat_missing_package_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", None)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(ProviderError, match=r"claude-bully\[openai\]"):
        OpenAICompatProvider(model="m", base_url=None)


def test_build_provider_anthropic_and_openai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("MY_API_KEY", "k2")
    a = build_provider(
        RoleConfig(provider=ProviderKind.anthropic, model="claude-opus-5-5"), tmp_path
    )
    assert isinstance(a, AnthropicProvider)
    pytest.importorskip("openai")
    o = build_provider(
        RoleConfig(
            provider=ProviderKind.openai_compat,
            model="m",
            base_url="https://x.example",
            api_key_env="MY_API_KEY",
        ),
        tmp_path,
    )
    assert isinstance(o, OpenAICompatProvider)


def test_openai_compat_rejects_http_remote_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(ProviderError, match="https"):
        OpenAICompatProvider(model="m", base_url="http://evil.example.com/v1", client=None)


def test_openai_compat_allows_http_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    OpenAICompatProvider(model="m", base_url="http://localhost:11434/v1")


def test_openai_compat_rejects_odd_key_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_SECRET", "k")
    with pytest.raises(ProviderError, match="api_key_env"):
        OpenAICompatProvider(model="m", base_url=None, api_key_env="HOME_SECRET", client=None)


# --- tool use: Anthropic ------------------------------------------------------------------------

FETCH = ToolSpec(
    name="fetch",
    description="Fetch a URL.",
    input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
)
LS = ToolSpec(name="ls", description="List files.", input_schema={"type": "object"})


def test_anthropic_passes_tools_and_never_forces_tool_choice() -> None:
    client = ScriptedAnthropic(anthropic_response(text_block("ok")))
    AnthropicProvider(client=client).complete(
        "c", "S", [Message(role="user", content="hi")], tools=[FETCH, LS]
    )
    kwargs = client.requests[0]
    assert kwargs["tools"] == [
        {"name": "fetch", "description": "Fetch a URL.", "input_schema": FETCH.input_schema},
        {"name": "ls", "description": "List files.", "input_schema": LS.input_schema},
    ]
    assert "tool_choice" not in kwargs


def test_anthropic_omits_tools_when_none_or_empty() -> None:
    client = ScriptedAnthropic(anthropic_response(text_block("a")), anthropic_response())
    p = AnthropicProvider(client=client)
    p.complete("c", "S", [Message(role="user", content="hi")])
    p.complete("c", "S", [Message(role="user", content="hi")], tools=[])
    assert all("tools" not in r and "tool_choice" not in r for r in client.requests)


def test_anthropic_parses_tool_use_blocks_into_tool_calls() -> None:
    client = ScriptedAnthropic(
        anthropic_response(
            text_block("Let me check."),
            tool_use_block("toolu_1", "fetch", {"url": "https://a.test"}),
            text_block(" One moment."),
            tool_use_block("toolu_2", "ls", {}),
            stop_reason="tool_use",
        )
    )
    out = AnthropicProvider(client=client).complete(
        "c", "S", [Message(role="user", content="go")], tools=[FETCH, LS]
    )
    assert out.text == "Let me check. One moment."
    assert out.stop_reason == "tool_use"
    assert out.tool_calls == [
        ToolCallRequest(id="toolu_1", name="fetch", args={"url": "https://a.test"}),
        ToolCallRequest(id="toolu_2", name="ls", args={}),
    ]
    assert all(c.executed is False and c.result_text is None for c in out.tool_calls)


def test_anthropic_plain_reply_has_no_tool_calls_or_reasoning() -> None:
    client = ScriptedAnthropic(anthropic_response(text_block("hi")))
    out = AnthropicProvider(client=client).complete(
        "c", "S", [Message(role="user", content="x")], tools=[FETCH]
    )
    assert out.tool_calls == [] and out.reasoning_text is None


def test_anthropic_rejects_non_object_tool_input() -> None:
    client = ScriptedAnthropic(
        anthropic_response(
            tool_use_block("toolu_1", "fetch", "https://a.test"), stop_reason="tool_use"
        )
    )
    with pytest.raises(ProviderError, match="fetch"):
        AnthropicProvider(client=client).complete(
            "c", "S", [Message(role="user", content="x")], tools=[FETCH]
        )


def test_anthropic_renders_a_two_step_tool_history_exactly() -> None:
    client = ScriptedAnthropic(anthropic_response(text_block("Done.")))
    calls = [
        ToolCallRequest(id="toolu_1", name="fetch", args={"url": "https://a.test"}),
        ToolCallRequest(id="toolu_2", name="ls", args={}),
    ]
    results = [ToolResult(id="toolu_1", text="page"), ToolResult(id="toolu_2", text="a b")]
    history = [
        Message(role="user", content="Look into it."),
        Message(role="assistant", content="Checking.", tool_calls=calls),
        Message(role="user", content="", tool_results=results),
    ]
    AnthropicProvider(client=client).complete("c", "S", history, tools=[FETCH, LS])
    assert client.requests[0]["messages"] == [
        {"role": "user", "content": "Look into it."},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Checking."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "fetch",
                    "input": {"url": "https://a.test"},
                },
                {"type": "tool_use", "id": "toolu_2", "name": "ls", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "page"},
                {"type": "tool_result", "tool_use_id": "toolu_2", "content": "a b"},
            ],
        },
    ]


def test_anthropic_omits_empty_text_block_and_adds_user_text_after_results() -> None:
    client = ScriptedAnthropic(anthropic_response(text_block("ok")))
    history = [
        Message(role="user", content="go"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCallRequest(id="t1", name="ls", args={})],
        ),
        Message(role="user", content="and then?", tool_results=[ToolResult(id="t1", text="x")]),
    ]
    AnthropicProvider(client=client).complete("c", "S", history, tools=[LS])
    _, assistant, user = client.requests[0]["messages"]
    assert assistant["content"] == [{"type": "tool_use", "id": "t1", "name": "ls", "input": {}}]
    assert user["content"] == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "x"},
        {"type": "text", "text": "and then?"},
    ]


@pytest.mark.parametrize("blank", ["", "\n\n", " \t \n"])
def test_anthropic_never_renders_an_empty_or_whitespace_only_text_block(blank: str) -> None:
    """Carry 3, widened: the API refuses a whitespace-only text block, so beside a tool_use or a
    tool_result such content is left out, not sent."""
    client = ScriptedAnthropic(anthropic_response(text_block("ok")))
    history = [
        Message(role="user", content="go"),
        Message(
            role="assistant",
            content=blank,
            tool_calls=[ToolCallRequest(id="t1", name="ls", args={})],
        ),
        Message(role="user", content=blank, tool_results=[ToolResult(id="t1", text="x")]),
    ]
    AnthropicProvider(client=client).complete("c", "S", history, tools=[LS])
    _, assistant, user = client.requests[0]["messages"]
    assert assistant["content"] == [{"type": "tool_use", "id": "t1", "name": "ls", "input": {}}]
    assert user["content"] == [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]


def test_anthropic_captures_summarized_thinking_text() -> None:
    client = ScriptedAnthropic(
        anthropic_response(
            thinking_block("First I should look."),
            text_block("Looking."),
            thinking_block("Then summarize."),
            tool_use_block("t1", "ls", {}),
            stop_reason="tool_use",
        )
    )
    out = AnthropicProvider(client=client).complete(
        "c", "S", [Message(role="user", content="x")], tools=[LS]
    )
    assert out.reasoning_text == "First I should look.\n\nThen summarize."
    assert out.text == "Looking."


def test_anthropic_empty_or_absent_thinking_leaves_reasoning_text_none() -> None:
    client = ScriptedAnthropic(
        anthropic_response(thinking_block(""), text_block("a")),
        anthropic_response(text_block("b")),
    )
    p = AnthropicProvider(client=client)
    assert p.complete("c", "S", [Message(role="user", content="x")]).reasoning_text is None
    assert p.complete("c", "S", [Message(role="user", content="x")]).reasoning_text is None


@pytest.mark.parametrize("mode", ["provider_default", "hide", "expose"])
def test_anthropic_replays_thinking_blocks_unchanged_with_their_tool_calls(mode: str) -> None:
    """Under every reasoning setting, ``hide`` included, the open tool loop's thinking blocks go
    back to the API unchanged (Phase 6 Task 1)."""
    client = ScriptedAnthropic(
        anthropic_response(
            thinking_block("", signature="sig-1"),
            tool_use_block("t1", "ls", {}),
            stop_reason="tool_use",
        ),
        anthropic_response(text_block("done")),
    )
    p = AnthropicProvider(client=client, reasoning=mode)  # type: ignore[arg-type]
    first = Message(role="user", content="go")
    out = p.complete("c", "S", [first], tools=[LS])
    history = [
        first,
        Message(role="assistant", content=out.text, tool_calls=out.tool_calls),
        Message(role="user", content="", tool_results=[ToolResult(id="t1", text="x")]),
    ]
    p.complete("c", "S", history, tools=[LS])
    assert client.requests[1]["messages"][1]["content"] == [
        {"type": "thinking", "thinking": "", "signature": "sig-1"},
        {"type": "tool_use", "id": "t1", "name": "ls", "input": {}},
    ]


# --- Phase 6 Task 1: the reasoning setting ----------------------------------------------------


def _anthropic(mode: str, *responses: object) -> tuple[AnthropicProvider, ScriptedAnthropic]:
    client = ScriptedAnthropic(*responses)
    return AnthropicProvider(client=client, reasoning=mode), client  # type: ignore[arg-type]


def _all_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [*value, *(k for v in value.values() for k in _all_keys(v))]
    if isinstance(value, list):
        return [k for v in value for k in _all_keys(v)]
    return []


@pytest.mark.parametrize("mode", ["expose", "hide", "provider_default"])
def test_anthropic_asks_for_adaptive_thinking_only_under_expose(mode: str) -> None:
    p, client = _anthropic(mode, anthropic_response(text_block("a")))
    p.complete("c", "S", [Message(role="user", content="x")])
    request = client.requests[0]
    if mode == "expose":
        assert request["thinking"] == {"type": "adaptive", "display": "summarized"}
    else:
        assert "thinking" not in request
    assert "budget_tokens" not in _all_keys(request)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("expose", ("First.\n\nSecond.", "summarized")),
        ("provider_default", ("First.\n\nSecond.", "unknown")),
        ("hide", (None, None)),
    ],
)
def test_anthropic_keeps_the_thinking_text_by_setting(
    mode: str, expected: tuple[str | None, str | None]
) -> None:
    p, _ = _anthropic(
        mode,
        anthropic_response(thinking_block("First."), thinking_block("Second."), text_block("a")),
    )
    out = p.complete("c", "S", [Message(role="user", content="x")])
    assert (out.reasoning_text, out.reasoning_kind) == expected


@pytest.mark.parametrize("mode", ["expose", "provider_default"])
@pytest.mark.parametrize(
    "block", [redacted_thinking_block("x"), thinking_block("")], ids=["redacted", "empty"]
)
def test_anthropic_blocks_with_no_text_are_redacted(mode: str, block: Any) -> None:
    p, _ = _anthropic(mode, anthropic_response(block, text_block("a")))
    out = p.complete("c", "S", [Message(role="user", content="x")])
    assert (out.reasoning_text, out.reasoning_kind) == (None, "redacted")


@pytest.mark.parametrize("mode", ["expose", "hide", "provider_default"])
def test_anthropic_without_a_thinking_block_has_no_kind(mode: str) -> None:
    p, _ = _anthropic(mode, anthropic_response(text_block("a")))
    out = p.complete("c", "S", [Message(role="user", content="x")])
    assert (out.reasoning_text, out.reasoning_kind) == (None, None)


def test_anthropic_refusing_the_thinking_parameter_is_a_provider_error_naming_it() -> None:
    client = _FakeAnthropic(fail=_status_error(anthropic.BadRequestError, 400))
    p = AnthropicProvider(client=client, reasoning="expose")
    with pytest.raises(ProviderError, match="thinking") as info:
        p.complete("c", "S", [Message(role="user", content="x")])
    assert not isinstance(info.value, RateLimitError)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("expose", ("x", "unknown")), ("provider_default", ("x", "unknown")), ("hide", (None, None))],
)
def test_openai_compat_keeps_reasoning_content_by_setting(
    mode: str, expected: tuple[str | None, str | None]
) -> None:
    response = openai_response("reply")
    response.choices[0].message.reasoning_content = "x"
    client = ScriptedOpenAI(response, openai_response("plain"))
    p = OpenAICompatProvider(model="m", base_url=None, client=client, reasoning=mode)  # type: ignore[arg-type]
    out = p.complete("c", "S", [Message(role="user", content="q")])
    assert (out.reasoning_text, out.reasoning_kind) == expected
    bare = p.complete("c", "S", [Message(role="user", content="q")])
    assert (bare.reasoning_text, bare.reasoning_kind) == (None, None)


# --- tool use: OpenAI-compatible ----------------------------------------------------------------


def _openai(*responses: object) -> tuple[OpenAICompatProvider, ScriptedOpenAI]:
    client = ScriptedOpenAI(*responses)
    return OpenAICompatProvider(model="m", base_url=None, client=client), client


def test_openai_compat_passes_tools_in_function_shape_without_tool_choice() -> None:
    p, client = _openai(openai_response("ok"))
    p.complete("c", "S", [Message(role="user", content="hi")], tools=[FETCH])
    kwargs = client.requests[0]
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "fetch",
                "description": "Fetch a URL.",
                "parameters": FETCH.input_schema,
            },
        }
    ]
    assert "tool_choice" not in kwargs


def test_openai_compat_omits_tools_when_none_or_empty() -> None:
    p, client = _openai(openai_response("a"), openai_response("b"))
    p.complete("c", "S", [Message(role="user", content="hi")])
    p.complete("c", "S", [Message(role="user", content="hi")], tools=[])
    assert all("tools" not in r for r in client.requests)


def test_openai_compat_parses_tool_calls_with_json_arguments() -> None:
    p, _ = _openai(
        openai_response(
            None,
            [
                openai_tool_call("call_1", "fetch", '{"url": "https://a.test"}'),
                openai_tool_call("call_2", "ls", "{}"),
            ],
            finish_reason="tool_calls",
        )
    )
    out = p.complete("c", "S", [Message(role="user", content="go")], tools=[FETCH, LS])
    assert out.text == "" and out.stop_reason == "tool_calls"
    assert out.tool_calls == [
        ToolCallRequest(id="call_1", name="fetch", args={"url": "https://a.test"}),
        ToolCallRequest(id="call_2", name="ls", args={}),
    ]


def test_openai_compat_plain_reply_has_no_tool_calls() -> None:
    p, _ = _openai(openai_response("yo"))
    assert p.complete("c", "S", [Message(role="user", content="x")]).tool_calls == []


def test_openai_compat_empty_arguments_mean_no_arguments() -> None:
    p, _ = _openai(openai_response(None, [openai_tool_call("c1", "ls", "")]))
    out = p.complete("c", "S", [Message(role="user", content="x")], tools=[LS])
    assert out.tool_calls == [ToolCallRequest(id="c1", name="ls", args={})]


@pytest.mark.parametrize("arguments", ['{"url": ', "not json", "[1, 2]", '"text"', "null"])
def test_openai_compat_bad_tool_arguments_raise_naming_the_tool(arguments: str) -> None:
    p, _ = _openai(openai_response(None, [openai_tool_call("c1", "fetch", arguments)]))
    with pytest.raises(ProviderError, match="fetch"):
        p.complete("c", "S", [Message(role="user", content="x")], tools=[FETCH])


def test_openai_compat_renders_a_two_step_tool_history_exactly() -> None:
    p, client = _openai(openai_response("Done."))
    calls = [
        ToolCallRequest(id="call_1", name="fetch", args={"url": "https://a.test"}),
        ToolCallRequest(id="call_2", name="ls", args={}),
    ]
    results = [ToolResult(id="call_1", text="page"), ToolResult(id="call_2", text="a b")]
    history = [
        Message(role="user", content="Look into it."),
        Message(role="assistant", content="", tool_calls=calls),
        Message(role="user", content="", tool_results=results),
    ]
    p.complete("c", "SYS", history, tools=[FETCH, LS])
    assert client.requests[0]["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "Look into it."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "fetch", "arguments": '{"url": "https://a.test"}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "ls", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "page"},
        {"role": "tool", "tool_call_id": "call_2", "content": "a b"},
    ]


def test_openai_compat_keeps_assistant_text_and_adds_user_text_after_tool_messages() -> None:
    p, client = _openai(openai_response("ok"))
    history = [
        Message(role="user", content="go"),
        Message(
            role="assistant",
            content="Checking.",
            tool_calls=[ToolCallRequest(id="c1", name="ls", args={})],
        ),
        Message(role="user", content="and then?", tool_results=[ToolResult(id="c1", text="x")]),
    ]
    p.complete("c", "S", history, tools=[LS])
    _, _, assistant, tool, user = client.requests[0]["messages"]
    assert assistant["content"] == "Checking."
    assert tool == {"role": "tool", "tool_call_id": "c1", "content": "x"}
    assert user == {"role": "user", "content": "and then?"}


# --- thinking replay scope: only the open tool loop, per conversation --------------------------


def _asst(call_id: str) -> Message:
    return Message(
        role="assistant",
        content="",
        tool_calls=[ToolCallRequest(id=call_id, name="ls", args={})],
    )


def _res(call_id: str) -> Message:
    return Message(role="user", content="", tool_results=[ToolResult(id=call_id, text="x")])


def _thinking_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message["content"]
    if isinstance(content, str):
        return []
    return [b for b in content if b["type"] in ("thinking", "redacted_thinking")]


def _tool_turn(sig: str, call_id: str) -> Any:
    return anthropic_response(
        thinking_block("", signature=sig),
        tool_use_block(call_id, "ls", {}),
        stop_reason="tool_use",
    )


def test_anthropic_replays_thinking_only_for_the_open_tool_loop() -> None:
    client = ScriptedAnthropic(
        _tool_turn("sig-1", "t1"),
        anthropic_response(text_block("a1")),
        anthropic_response(text_block("a2")),
        _tool_turn("sig-3", "t3"),
        anthropic_response(text_block("a3")),
    )
    p = AnthropicProvider(client=client)
    u1, u2, u3 = (Message(role="user", content=f"u{i}") for i in (1, 2, 3))
    a1, a2 = (Message(role="assistant", content=f"a{i}") for i in (1, 2))
    p.complete("c", "S", [u1], tools=[LS])
    p.complete("c", "S", [u1, _asst("t1"), _res("t1")], tools=[LS])
    p.complete("c", "S", [u1, _asst("t1"), _res("t1"), a1, u2], tools=[LS])
    p.complete("c", "S", [u1, _asst("t1"), _res("t1"), a1, u2, a2, u3], tools=[LS])
    history = [u1, _asst("t1"), _res("t1"), a1, u2, a2, u3, _asst("t3"), _res("t3")]
    p.complete("c", "S", history, tools=[LS])

    # while turn 1's loop was open its thinking went back with it ...
    assert _thinking_blocks(client.requests[1]["messages"][1]) == [
        {"type": "thinking", "thinking": "", "signature": "sig-1"}
    ]
    # ... and once turn 3's loop is open, only turn 3 carries thinking.
    final = client.requests[4]["messages"]
    assert [i for i, m in enumerate(final) if _thinking_blocks(m)] == [7]
    assert _thinking_blocks(final[7]) == [
        {"type": "thinking", "thinking": "", "signature": "sig-3"}
    ]


def test_anthropic_replays_no_thinking_once_the_tool_loop_is_closed() -> None:
    client = ScriptedAnthropic(
        _tool_turn("sig-1", "t1"),
        anthropic_response(text_block("a1")),
        anthropic_response(text_block("a2")),
    )
    p = AnthropicProvider(client=client)
    u1 = Message(role="user", content="u1")
    p.complete("c", "S", [u1], tools=[LS])
    p.complete("c", "S", [u1, _asst("t1"), _res("t1")], tools=[LS])
    closed = [
        u1,
        _asst("t1"),
        _res("t1"),
        Message(role="assistant", content="a1"),
        Message(role="user", content="u2"),
    ]
    p.complete("c", "S", closed, tools=[LS])
    assert [_thinking_blocks(m) for m in client.requests[2]["messages"]] == [[]] * 5
    assert p._thinking == {}


def test_anthropic_keeps_no_cache_entry_for_a_tool_call_without_thinking() -> None:
    client = ScriptedAnthropic(
        anthropic_response(tool_use_block("t1", "ls", {}), stop_reason="tool_use")
    )
    p = AnthropicProvider(client=client)
    p.complete("c", "S", [Message(role="user", content="go")], tools=[LS])
    assert p._thinking == {}


def test_anthropic_thinking_cache_is_per_conversation_when_tool_ids_collide() -> None:
    client = ScriptedAnthropic(
        _tool_turn("sig-A", "t1"),
        _tool_turn("sig-B", "t1"),
        anthropic_response(text_block("done A")),
        anthropic_response(text_block("done B")),
    )
    p = AnthropicProvider(client=client)
    go = Message(role="user", content="go")
    p.complete("conv-a", "S", [go], tools=[LS])
    p.complete("conv-b", "S", [go], tools=[LS])  # a plain user turn must not evict conv-a
    loop = [go, _asst("t1"), _res("t1")]
    p.complete("conv-a", "S", loop, tools=[LS])
    p.complete("conv-b", "S", loop, tools=[LS])
    assert _thinking_blocks(client.requests[2]["messages"][1]) == [
        {"type": "thinking", "thinking": "", "signature": "sig-A"}
    ]
    assert _thinking_blocks(client.requests[3]["messages"][1]) == [
        {"type": "thinking", "thinking": "", "signature": "sig-B"}
    ]


def test_anthropic_replays_redacted_thinking_data_unchanged() -> None:
    client = ScriptedAnthropic(
        anthropic_response(
            redacted_thinking_block("opaque-bytes"),
            tool_use_block("t1", "ls", {}),
            stop_reason="tool_use",
        ),
        anthropic_response(text_block("done")),
    )
    p = AnthropicProvider(client=client)
    go = Message(role="user", content="go")
    p.complete("c", "S", [go], tools=[LS])
    p.complete("c", "S", [go, _asst("t1"), _res("t1")], tools=[LS])
    assert _thinking_blocks(client.requests[1]["messages"][1]) == [
        {"type": "redacted_thinking", "data": "opaque-bytes"}
    ]


def test_anthropic_replays_real_sdk_thinking_blocks_from_their_model_dump() -> None:
    from anthropic.types import RedactedThinkingBlock, TextBlock, ThinkingBlock, ToolUseBlock

    thinking = ThinkingBlock.model_validate(
        {"type": "thinking", "thinking": "why", "signature": "sig-r", "future_field": "keep"}
    )
    redacted = RedactedThinkingBlock(type="redacted_thinking", data="blob")
    client = ScriptedAnthropic(
        anthropic_response(
            thinking,
            redacted,
            TextBlock(type="text", text="Looking."),
            ToolUseBlock(type="tool_use", id="t1", name="ls", input={}),
            stop_reason="tool_use",
        ),
        anthropic_response(text_block("done")),
    )
    p = AnthropicProvider(client=client)
    go = Message(role="user", content="go")
    out = p.complete("c", "S", [go], tools=[LS])
    assert out.reasoning_text == "why" and out.text == "Looking."
    history = [
        go,
        Message(role="assistant", content=out.text, tool_calls=out.tool_calls),
        _res("t1"),
    ]
    p.complete("c", "S", history, tools=[LS])
    assert client.requests[1]["messages"][1]["content"] == [
        thinking.model_dump(exclude_none=True),
        redacted.model_dump(exclude_none=True),
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "id": "t1", "name": "ls", "input": {}},
    ]
