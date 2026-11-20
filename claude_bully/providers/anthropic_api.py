"""Anthropic Messages API backend (API key or ``ant auth login`` profile).

The role's ``reasoning`` setting (Phase 6 spec 4.2, D-kind): ``expose`` sends
``thinking=THINKING_REQUEST`` (never a budget: the current families refuse one) and keeps the
returned thinking text, kind ``summarized``; a request refused for it is a ``ProviderError`` naming
the parameter, with no retry without it. ``provider_default`` sends no ``thinking`` parameter and
keeps what comes back, kind ``unknown``. ``hide`` sends none and keeps nothing (the model may still
think; it is neither displayed nor kept). Blocks with no readable text give kind ``redacted``.
"""

from typing import Any, Final

import anthropic

from claude_bully.config import ReasoningMode
from claude_bully.providers.base import (
    Completion,
    Message,
    ProviderError,
    RateLimitError,
    ToolCallRequest,
    ToolSpec,
)
from claude_bully.records import ReasoningKind, Usage

# the thinking parameter ``expose`` sends (Phase 6 spec 4.2)
THINKING_REQUEST: Final = {"type": "adaptive", "display": "summarized"}


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-opus-5-5",
        max_tokens: int = 4096,
        temperature: float | None = None,
        client: Any | None = None,
        reasoning: ReasoningMode = "provider_default",
    ) -> None:
        self.model = model
        self.reasoning = reasoning
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = client if client is not None else anthropic.Anthropic()
        # Thinking blocks the model produced alongside a tool call, keyed by (conversation id,
        # first tool call id). They must go back to the API unchanged with the tool_use they
        # preceded, and ``Message`` has nowhere to carry them, so the provider keeps them while
        # the tool loop is open. They are replayed only inside that open loop and evicted once a
        # plain user message closes it: thinking may be dropped from the front of a history but
        # not from the middle, so completed turns carry none at all.
        self._thinking: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def _render(self, conversation_id: str, message: Message, in_open_loop: bool) -> dict[str, Any]:
        if message.role == "assistant" and message.tool_calls:
            blocks: list[dict[str, Any]] = []
            if in_open_loop:
                # Message.content is one string, so a block's original position among the text
                # and tool_use blocks is lost: replayed thinking goes first, then text, then
                # tool_use.
                key = (conversation_id, message.tool_calls[0].id)
                blocks.extend(self._thinking.get(key, []))
            # the API refuses a whitespace-only text block: such content is left out, not sent
            if message.content.strip():
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
            if message.content.strip():
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
        loop_start = _open_loop_start(messages)
        open_ids = {m.tool_calls[0].id for m in messages[loop_start:] if m.tool_calls}
        self._thinking = {
            key: blocks
            for key, blocks in self._thinking.items()
            if key[0] != conversation_id or key[1] in open_ids
        }
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [
                self._render(conversation_id, m, in_open_loop=i >= loop_start)
                for i, m in enumerate(messages)
            ],
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
        if self.reasoning == "expose":
            kwargs["thinking"] = dict(THINKING_REQUEST)
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
            if exc.status_code == 400 and self.reasoning == "expose":
                raise ProviderError(
                    f"anthropic API error {exc.status_code}; anthropic refused the request sent "
                    f"with the thinking parameter {THINKING_REQUEST} (reasoning: expose): "
                    f"{exc.message}"
                ) from exc
            raise ProviderError(f"anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"anthropic connection error: {exc}") from exc
        text = "".join(block.text for block in response.content if block.type == "text")
        tool_calls = [_tool_call(block) for block in response.content if block.type == "tool_use"]
        reasoning_text, reasoning_kind = self._reasoning(response.content)
        if tool_calls:
            replay = [b for b in map(_replayable, response.content) if b is not None]
            if replay:
                self._thinking[(conversation_id, tool_calls[0].id)] = replay
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
            reasoning_text=reasoning_text,
            reasoning_kind=reasoning_kind,
        )

    def _reasoning(self, blocks: list[Any]) -> tuple[str | None, ReasoningKind | None]:
        """The response's reasoning under the role's setting: the thinking blocks' text joined
        by blank lines, kind ``summarized`` under ``expose`` and ``unknown`` under
        ``provider_default``; ``(None, "redacted")`` when reasoning blocks came with no text;
        ``(None, None)`` with no block, and always under ``hide``."""
        if self.reasoning == "hide":
            return None, None
        texts = [
            block.thinking
            for block in blocks
            if block.type == "thinking" and getattr(block, "thinking", "")
        ]
        if texts:
            return "\n\n".join(texts), "summarized" if self.reasoning == "expose" else "unknown"
        if any(block.type in ("thinking", "redacted_thinking") for block in blocks):
            return None, "redacted"
        return None, None


def _tool_call(block: Any) -> ToolCallRequest:
    if not isinstance(block.input, dict):
        raise ProviderError(f"anthropic tool_use for {block.name!r} has a non-object input")
    return ToolCallRequest(id=block.id, name=block.name, args=block.input)


def _open_loop_start(messages: list[Message]) -> int:
    """Index of the first message of the unfinished tool loop; ``len(messages)`` when none.

    The open loop is whatever follows the last user message that carries no tool results: the
    assistant tool calls and the tool results answering them.
    """
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user" and not messages[i].tool_results:
            return i + 1
    return 0


def _replayable(block: Any) -> dict[str, Any] | None:
    """A thinking block exactly as the API sent it, or None for any other block."""
    if block.type not in ("thinking", "redacted_thinking"):
        return None
    dump = getattr(block, "model_dump", None)
    if callable(dump):
        replayed: dict[str, Any] = dump(exclude_none=True)
        return replayed
    if block.type == "thinking":
        return {
            "type": "thinking",
            "thinking": getattr(block, "thinking", ""),
            "signature": getattr(block, "signature", ""),
        }
    return {"type": "redacted_thinking", "data": block.data}
