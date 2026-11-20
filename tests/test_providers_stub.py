from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.providers.base import (
    Completion,
    Message,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
    build_provider,
)
from claude_bully.providers.stub import StubProvider, load_stub_script

RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "echo_rules.yaml"


def test_stub_echoes_last_user_message() -> None:
    p = StubProvider()
    out = p.complete("c1", "SYS", [Message(role="user", content="hello there")])
    assert out.text == "[stub] hello there"
    assert out.backend == "stub" and out.model == "stub"


def test_stub_script_first_match_wins() -> None:
    responder = load_stub_script(RULES)
    p = StubProvider(responder=responder)
    msgs = [Message(role="user", content="What is the capital of France?")]
    assert p.complete("c1", "SYS", msgs).text == "Paris."
    msgs = [Message(role="user", content="Name a capital.")]
    assert p.complete("c1", "SYS", msgs).text == "I am not sure which capital you mean."
    msgs = [Message(role="user", content="unrelated")]
    assert p.complete("c1", "SYS", msgs).text == "[stub] unrelated"


def test_build_provider_stub_uses_script_from_role_config(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.stub, model="stub", stub_script=str(RULES))
    p = build_provider(role, tmp_path)
    out = p.complete("c", "SYS", [Message(role="user", content="capital of france")])
    assert out.text == "Paris."
    assert p.name == "stub"


def test_tool_spec_fields() -> None:
    spec = ToolSpec(
        name="web_search",
        description="Search the web.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    assert spec.name == "web_search" and spec.input_schema["type"] == "object"


def test_tool_call_request_defaults_to_unexecuted() -> None:
    call = ToolCallRequest(id="t1", name="fetch", args={"url": "https://example.test"})
    assert call.executed is False and call.result_text is None


def test_tool_call_request_can_carry_an_executed_result() -> None:
    call = ToolCallRequest(id="t1", name="fetch", args={}, executed=True, result_text="200 OK")
    assert call.executed is True and call.result_text == "200 OK"


def test_completion_gains_tool_calls_and_reasoning_text() -> None:
    plain = StubProvider().complete("c1", "SYS", [Message(role="user", content="hi")])
    assert plain.tool_calls == [] and plain.reasoning_text is None
    full = Completion(
        text="t",
        usage=plain.usage,
        cost_usd=None,
        backend="b",
        model="m",
        tool_calls=[ToolCallRequest(id="t1", name="ls", args={})],
        reasoning_text="because",
    )
    again = Completion.model_validate_json(full.model_dump_json())
    assert again.tool_calls[0].name == "ls" and again.reasoning_text == "because"


def test_message_tool_results_default_empty_and_round_trip() -> None:
    assert Message(role="user", content="x").tool_results == []
    m = Message(role="user", content="", tool_results=[ToolResult(id="t1", text="done")])
    again = Message.model_validate_json(m.model_dump_json())
    assert again.tool_results == [ToolResult(id="t1", text="done")]
    assert isinstance(again.content, str)


def test_message_still_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Message.model_validate({"role": "user", "content": "x", "bogus": 1})


def test_stub_complete_accepts_tools_argument() -> None:
    spec = ToolSpec(name="ls", description="List.", input_schema={"type": "object"})
    out = StubProvider().complete(
        "c1", "SYS", [Message(role="user", content="hello")], tools=[spec]
    )
    assert out.text == "[stub] hello"


# --- Message tool_calls / tool_results validation ------------------------------------------------


def test_message_tool_calls_default_empty_and_round_trip() -> None:
    assert Message(role="assistant", content="x").tool_calls == []
    m = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCallRequest(id="t1", name="fetch", args={"url": "u"})],
    )
    again = Message.model_validate_json(m.model_dump_json())
    assert again.tool_calls == m.tool_calls


def test_message_rejects_tool_calls_on_a_user_message() -> None:
    with pytest.raises(ValidationError, match="tool_calls"):
        Message(role="user", content="x", tool_calls=[ToolCallRequest(id="t1", name="ls", args={})])


def test_message_rejects_tool_results_on_an_assistant_message() -> None:
    with pytest.raises(ValidationError, match="tool_results"):
        Message(role="assistant", content="x", tool_results=[ToolResult(id="t1", text="done")])


# --- scripted tool calls ------------------------------------------------------------------------

SPEC = ToolSpec(name="web_search", description="Search.", input_schema={"type": "object"})
TOOL_RULES = """
- match: "(?i)look up the capital"
  tool: {name: web_search, args: {query: capital of France}}
  reply_after_tool: "The search says Paris."
- match: "(?i)list the files"
  tool: {name: ls, args: {path: /}}
  reply_after_tool: "There is one file."
- match: "(?i)hello"
  reply: "Hi."
"""


def _tool_rules(tmp_path: Path, text: str = TOOL_RULES) -> StubProvider:
    path = tmp_path / "rules.yaml"
    path.write_text(text, encoding="utf-8")
    return StubProvider(load_stub_script(path))


def _with_results(first: Message, calls: list[ToolCallRequest], text: str) -> list[Message]:
    return [
        first,
        Message(role="assistant", content="", tool_calls=calls),
        Message(role="user", content="", tool_results=[ToolResult(id=calls[0].id, text=text)]),
    ]


def test_stub_scripted_tool_call_round_trip(tmp_path: Path) -> None:
    p = _tool_rules(tmp_path)
    first = Message(role="user", content="Please look up the capital of France.")
    out = p.complete("c1", "SYS", [first], tools=[SPEC])
    assert out.text == "" and out.stop_reason == "tool_use"
    assert out.tool_calls == [
        ToolCallRequest(id="stub-1", name="web_search", args={"query": "capital of France"})
    ]
    history = _with_results(first, out.tool_calls, "Paris is the capital.")
    final = p.complete("c1", "SYS", history, tools=[SPEC])
    assert final.text == "The search says Paris."
    assert final.tool_calls == [] and final.stop_reason == "end_turn"


def test_stub_tool_call_ids_are_unique_and_replies_follow_the_issuing_rule(
    tmp_path: Path,
) -> None:
    p = _tool_rules(tmp_path)
    a = Message(role="user", content="look up the capital")
    b = Message(role="user", content="list the files")
    call_a = p.complete("c1", "S", [a], tools=[SPEC]).tool_calls
    call_b = p.complete("c2", "S", [b], tools=[SPEC]).tool_calls
    assert [c.id for c in call_a + call_b] == ["stub-1", "stub-2"]
    assert p.complete("c2", "S", _with_results(b, call_b, "x"), tools=[SPEC]).text == (
        "There is one file."
    )
    assert p.complete("c1", "S", _with_results(a, call_a, "x"), tools=[SPEC]).text == (
        "The search says Paris."
    )


def test_stub_tool_rule_without_tools_offered_replies_directly(tmp_path: Path) -> None:
    p = _tool_rules(tmp_path)
    msgs = [Message(role="user", content="look up the capital of France")]
    for tools in (None, []):
        out = p.complete("c1", "S", msgs, tools=tools)
        assert out.tool_calls == [] and out.text == "The search says Paris."


def test_stub_plain_rules_and_echo_unchanged_when_tools_are_offered(tmp_path: Path) -> None:
    p = _tool_rules(tmp_path)
    plain = p.complete("c1", "S", [Message(role="user", content="hello")], tools=[SPEC])
    assert plain.text == "Hi." and plain.tool_calls == []
    echo = p.complete("c1", "S", [Message(role="user", content="zzz")], tools=[SPEC])
    assert echo.text == "[stub] zzz" and echo.tool_calls == []


def test_stub_unknown_tool_call_id_echoes_the_first_tool_result() -> None:
    p = StubProvider(load_stub_script(RULES))
    calls = [ToolCallRequest(id="elsewhere-9", name="ls", args={})]
    history = _with_results(Message(role="user", content="go"), calls, "file.txt")
    out = p.complete("c1", "S", history, tools=[SPEC])
    assert out.text == "[stub] file.txt" and out.tool_calls == []


def test_stub_tool_result_turn_does_not_rematch_the_user_text(tmp_path: Path) -> None:
    p = _tool_rules(tmp_path)
    first = Message(role="user", content="look up the capital of France")
    calls = p.complete("c1", "S", [first], tools=[SPEC]).tool_calls
    history = _with_results(first, calls, "look up the capital of France")
    out = p.complete("c1", "S", history, tools=[SPEC])
    assert out.tool_calls == [] and out.text == "The search says Paris."


def test_stub_scripted_responder_is_still_a_plain_responder(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(TOOL_RULES, encoding="utf-8")
    responder = load_stub_script(path)
    assert responder("c", [Message(role="user", content="hello")]) == "Hi."
    assert responder("c", [Message(role="user", content="look up the capital")]) == (
        "The search says Paris."
    )


@pytest.mark.parametrize(
    "rule",
    [
        "- {match: x, tool: {name: ls, args: {}}}",
        "- {match: x, reply_after_tool: done}",
        "- {match: x, reply: y, tool: {args: {}}, reply_after_tool: done}",
        "- {match: x, reply: y, tool: {name: ls}, reply_after_tool: done}",
        "- {match: x, tool: {name: ls, args: [1]}, reply_after_tool: done}",
        "- {match: x}",
        "- {match: x, reply: y, bogus: 1}",
    ],
)
def test_load_stub_script_rejects_malformed_tool_rules(tmp_path: Path, rule: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(rule + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stub rule"):
        load_stub_script(path)


def test_stub_tool_args_default_to_empty_and_are_not_shared_between_calls(tmp_path: Path) -> None:
    rules = (
        "- {match: go, tool: {name: ls, args: {path: /}}, reply_after_tool: ok}\n"
        "- {match: bare, tool: {name: get_date}, reply_after_tool: ok}\n"
    )
    p = _tool_rules(tmp_path, rules)
    bare = p.complete("c", "S", [Message(role="user", content="bare")], tools=[SPEC])
    assert bare.tool_calls[0].args == {}
    first = p.complete("c", "S", [Message(role="user", content="go")], tools=[SPEC])
    first.tool_calls[0].args["path"] = "/mutated"
    second = p.complete("c", "S", [Message(role="user", content="go")], tools=[SPEC])
    assert second.tool_calls[0].args == {"path": "/"}


def test_the_stub_defaults_to_provider_default_and_a_plain_responder_reasons_nothing() -> None:
    """Phase 6 Task 1: a plain ``Responder`` (the echo) fabricates no reasoning under any
    setting; the setting is kept on the provider."""
    assert StubProvider().reasoning == "provider_default"
    for mode in ("expose", "hide", "provider_default"):
        done = StubProvider(reasoning=mode).complete(  # type: ignore[arg-type]
            "c", "SYS", [Message(role="user", content="hi")]
        )
        assert (done.reasoning_text, done.reasoning_kind) == (None, None)
