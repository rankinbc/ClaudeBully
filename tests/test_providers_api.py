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
from claude_bully.providers.base import Message, ProviderError, RateLimitError, build_provider
from claude_bully.providers.openai_compat import OpenAICompatProvider


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
    p = OpenAICompatProvider(model="llama", base_url="http://x", client=client)
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
    monkeypatch.setenv("MY_KEY", "k2")
    a = build_provider(
        RoleConfig(provider=ProviderKind.anthropic, model="claude-opus-5-5"), tmp_path
    )
    assert isinstance(a, AnthropicProvider)
    pytest.importorskip("openai")
    o = build_provider(
        RoleConfig(
            provider=ProviderKind.openai_compat,
            model="m",
            base_url="http://x",
            api_key_env="MY_KEY",
        ),
        tmp_path,
    )
    assert isinstance(o, OpenAICompatProvider)
