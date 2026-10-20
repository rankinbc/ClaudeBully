"""Deterministic stub provider for tests, CI and dry development."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from claude_bully.providers.base import Completion, Message, ToolSpec
from claude_bully.records import Usage

Responder = Callable[[str, list[Message]], str]


def _last_user(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""


def echo_responder(conversation_id: str, messages: list[Message]) -> str:
    return "[stub] " + _last_user(messages)


def load_stub_script(path: Path) -> Responder:
    """YAML list of ``{match: <regex>, reply: <str>}``; first match on the last user message."""
    with path.open(encoding="utf-8") as fh:
        rules_raw = yaml.safe_load(fh) or []
    rules = [(re.compile(r["match"]), str(r["reply"])) for r in rules_raw]

    def responder(conversation_id: str, messages: list[Message]) -> str:
        last = _last_user(messages)
        for pattern, reply in rules:
            if pattern.search(last):
                return reply
        return echo_responder(conversation_id, messages)

    return responder


class StubProvider:
    name = "stub"

    def __init__(self, responder: Responder | None = None, model: str = "stub") -> None:
        self._responder = responder or echo_responder
        self.model = model
        self.calls = 0

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        self.calls += 1
        text = self._responder(conversation_id, messages)
        return Completion(
            text=text,
            usage=Usage(input_tokens=len(system) + sum(len(m.content) for m in messages)),
            cost_usd=0.0,
            backend=self.name,
            model=self.model,
            stop_reason="end_turn",
        )
