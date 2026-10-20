"""Provider protocol shared by every backend, plus the factory."""

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.records import Usage


class ToolSpec(BaseModel):
    """A tool offered to the model: name, description and a JSON schema for its arguments."""

    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallRequest(BaseModel):
    """A tool call the model made. ``executed`` calls (the claude_code backend) carry a result."""

    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    args: dict[str, Any]
    executed: bool = False
    result_text: str | None = None


class ToolResult(BaseModel):
    """The outcome of one tool call, returned to the model on a user message."""

    model_config = ConfigDict(extra="forbid")
    id: str
    text: str


class Message(BaseModel):
    """One turn of provider-layer history (not the run-record schema).

    ``tool_calls`` belongs to an assistant message that asked for tools; ``tool_results`` belongs
    to the user message that answers them. Either may sit beside text ``content``.
    """

    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str
    tool_results: list[ToolResult] = []
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def _tool_fields_match_role(self) -> "Message":
        if self.tool_calls and self.role != "assistant":
            raise ValueError("tool_calls are only valid on an assistant message")
        if self.tool_results and self.role != "user":
            raise ValueError("tool_results are only valid on a user message")
        return self


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    usage: Usage
    cost_usd: float | None
    backend: str
    model: str
    raw_session_ref: str | None = None
    stop_reason: str | None = None
    tool_calls: list[ToolCallRequest] = []
    reasoning_text: str | None = None


class ProviderError(Exception):
    """Any backend failure that is not a rate limit."""


class RateLimitError(ProviderError):
    """The backend refused for quota reasons; the run should pause and resume later."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ChatProvider(Protocol):
    name: str

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion: ...


def build_provider(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
    """Instantiate the backend named by ``role.provider``. Imports lazily.

    ``with_mcp`` lets a claude_code backend serve sandbox tools: its MCP files live in
    ``state_dir / "mcp"``. Other backends ignore it (they take tools through their own API).
    """
    if role.provider is ProviderKind.stub:
        from claude_bully.providers.stub import StubProvider, load_stub_script

        responder = load_stub_script(Path(role.stub_script)) if role.stub_script else None
        return StubProvider(responder=responder, model=role.model)
    if role.provider is ProviderKind.claude_code:
        from claude_bully.providers.claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider(
            model=role.model,
            state_dir=state_dir,
            effort=role.effort,
            command=role.command,
            mcp_state_dir=state_dir / "mcp" if with_mcp else None,
        )
    if role.provider is ProviderKind.anthropic:
        from claude_bully.providers.anthropic_api import AnthropicProvider

        return AnthropicProvider(
            model=role.model, max_tokens=role.max_tokens, temperature=role.temperature
        )
    if role.provider is ProviderKind.openai_compat:
        from claude_bully.providers.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            model=role.model,
            base_url=role.base_url,
            api_key_env=role.api_key_env or "OPENAI_API_KEY",
            max_tokens=role.max_tokens,
            temperature=role.temperature,
        )
    raise ProviderError(f"unknown provider kind: {role.provider}")
