"""OpenAI-compatible chat completions backend for non-Claude targets."""

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

from claude_bully.providers.base import (
    Completion,
    Message,
    ProviderError,
    RateLimitError,
    ToolCallRequest,
    ToolSpec,
)
from claude_bully.records import Usage

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}
_KEY_ENV = re.compile(r"^[A-Z][A-Z0-9_]*_(API_KEY|TOKEN)$")


def _check_endpoint(base_url: str | None) -> None:
    """Experiment configs are trusted, but a key must never travel in clear text."""
    if base_url is None:
        return
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" and host not in _LOCAL_HOSTS:
        raise ProviderError(f"base_url must use https unless it is localhost: {base_url}")


def _check_key_env_name(api_key_env: str) -> None:
    if not _KEY_ENV.match(api_key_env):
        raise ProviderError(
            f"api_key_env must look like NAME_API_KEY or NAME_TOKEN, got {api_key_env!r}"
        )


def _render_messages(system: str, messages: list[Message]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            rendered.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.args)},
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        elif m.role == "user" and m.tool_results:
            rendered.extend(
                {"role": "tool", "tool_call_id": r.id, "content": r.text} for r in m.tool_results
            )
            if m.content:
                rendered.append({"role": "user", "content": m.content})
        else:
            rendered.append({"role": m.role, "content": m.content})
    return rendered


def _tool_call(raw: Any) -> ToolCallRequest:
    name = raw.function.name
    arguments = raw.function.arguments
    if isinstance(arguments, str):
        # Some servers send "" for a call with no arguments.
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as exc:
            raise ProviderError(f"tool call {name!r} has malformed JSON arguments: {exc}") from exc
    if not isinstance(arguments, dict):
        raise ProviderError(f"tool call {name!r} arguments are not a JSON object")
    return ToolCallRequest(id=raw.id, name=name, args=arguments)


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        model: str,
        base_url: str | None,
        api_key_env: str = "OPENAI_API_KEY",
        max_tokens: int = 4096,
        temperature: float | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        _check_endpoint(base_url)
        _check_key_env_name(api_key_env)
        if client is not None:
            self._client = client
            return
        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "the openai package is not installed; install claude-bully[openai]"
            ) from exc
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ProviderError(f"environment variable {api_key_env} is not set")
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": _render_messages(system, messages),
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "verdict", "schema": json_schema},
            }
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - mapped below by class name
            name = type(exc).__name__
            if name == "RateLimitError":
                raise RateLimitError(str(exc)) from exc
            raise ProviderError(f"openai-compatible API error: {exc}") from exc
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return Completion(
            text=choice.message.content or "",
            usage=Usage(
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
            ),
            cost_usd=None,
            backend=self.name,
            model=self.model,
            stop_reason=getattr(choice, "finish_reason", None),
            tool_calls=[_tool_call(c) for c in getattr(choice.message, "tool_calls", None) or []],
        )
