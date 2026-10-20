"""Anthropic Messages API backend (API key or ``ant auth login`` profile)."""

from typing import Any

import anthropic

from claude_bully.providers.base import Completion, Message, ProviderError, RateLimitError
from claude_bully.records import Usage


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-opus-5-5",
        max_tokens: int = 4096,
        temperature: float | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = client if client is not None else anthropic.Anthropic()

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
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if json_schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            retry_after = None
            try:
                retry_after = float(exc.response.headers.get("retry-after", ""))
            except (ValueError, AttributeError):
                pass
            raise RateLimitError(str(exc), retry_after_s=retry_after) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"anthropic connection error: {exc}") from exc
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = getattr(response, "usage", None)
        return Completion(
            text=text,
            usage=Usage(
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
            ),
            cost_usd=None,
            backend=self.name,
            model=self.model,
            stop_reason=getattr(response, "stop_reason", None),
        )
