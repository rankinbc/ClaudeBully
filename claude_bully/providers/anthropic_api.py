"""Anthropic Messages API backend (API key or ``ant auth login`` profile)."""

from typing import Any

import anthropic

from claude_bully.providers.base import (
    Completion,
    Message,
    ProviderError,
    RateLimitError,
    ToolCallRequest,
    ToolSpec,
)
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
        # Thinking blocks the model produced alongside a tool call, keyed by that call's id. They
        # must go back to the API unchanged with the tool_use they preceded, and ``Message`` has
        # nowhere to carry them, so the provider keeps them for the turn that follows.
        self._thinking_by_call_id: dict[str, list[dict[str, Any]]] = {}

    def _render(self, message: Message) -> dict[str, Any]:
        if message.role == "assistant" and message.tool_calls:
            blocks: list[dict[str, Any]] = list(
                self._thinking_by_call_id.get(message.tool_calls[0].id, [])
            )
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            blocks.extend(
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.args}
                for c in message.tool_calls
            )
            return {"role": "assistant", "content": blocks}
        if message.role == "user" and message.tool_results:
            blocks = [
                {"type": "tool_result", "tool_use_id": r.id, "content": r.text}
                for r in message.tool_results
            ]
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            return {"role": "user", "content": blocks}
        return {"role": message.role, "content": message.content}

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
            "system": system,
            "messages": [self._render(m) for m in messages],
        }
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
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
        tool_calls = [_tool_call(block) for block in response.content if block.type == "tool_use"]
        thinking = [
            block.thinking
            for block in response.content
            if block.type == "thinking" and getattr(block, "thinking", "")
        ]
        if tool_calls:
            replay = [_replayable(block) for block in response.content]
            self._thinking_by_call_id[tool_calls[0].id] = [b for b in replay if b is not None]
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
            tool_calls=tool_calls,
            reasoning_text="\n\n".join(thinking) or None,
        )


def _tool_call(block: Any) -> ToolCallRequest:
    if not isinstance(block.input, dict):
        raise ProviderError(f"anthropic tool_use for {block.name!r} has a non-object input")
    return ToolCallRequest(id=block.id, name=block.name, args=block.input)


def _replayable(block: Any) -> dict[str, Any] | None:
    """A thinking block as the API wants it back, or None for any other block."""
    if block.type == "thinking":
        return {
            "type": "thinking",
            "thinking": getattr(block, "thinking", ""),
            "signature": getattr(block, "signature", ""),
        }
    if block.type == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.data}
    return None
