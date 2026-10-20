"""OpenAI-compatible chat completions backend for non-Claude targets."""

import os
from typing import Any

from claude_bully.providers.base import Completion, Message, ProviderError, RateLimitError
from claude_bully.records import Usage


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
    ) -> Completion:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
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
        )
