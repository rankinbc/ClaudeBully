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
