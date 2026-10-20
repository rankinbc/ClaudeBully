"""Provider protocol shared by every backend, plus the factory."""

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.records import Usage


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    usage: Usage
    cost_usd: float | None
    backend: str
    model: str
    raw_session_ref: str | None = None
    stop_reason: str | None = None


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
    ) -> Completion: ...


def build_provider(role: RoleConfig, state_dir: Path) -> ChatProvider:
    """Instantiate the backend named by ``role.provider``. Imports lazily."""
    if role.provider is ProviderKind.stub:
        from claude_bully.providers.stub import StubProvider, load_stub_script

        responder = load_stub_script(Path(role.stub_script)) if role.stub_script else None
        return StubProvider(responder=responder, model=role.model)
    raise ProviderError(f"unknown provider kind: {role.provider}")
