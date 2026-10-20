"""Deterministic stub provider for tests, CI and dry development."""

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from claude_bully.providers.base import Completion, Message, ToolCallRequest, ToolResult, ToolSpec
from claude_bully.records import Usage

Responder = Callable[[str, list[Message]], str]


def _last_user(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""


def echo_responder(conversation_id: str, messages: list[Message]) -> str:
    return "[stub] " + _last_user(messages)


@dataclass(frozen=True)
class _ToolStep:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class _Rule:
    """``reply`` is the plain reply, or for a tool rule the reply once the tool result is back."""

    pattern: re.Pattern[str]
    reply: str
    tool: _ToolStep | None = None


_RULE_KEYS = {"match", "reply", "tool", "reply_after_tool"}


def _parse_rule(index: int, raw: Any) -> _Rule:
    def bad(why: str) -> ValueError:
        return ValueError(f"stub rule {index}: {why}")

    if not isinstance(raw, dict):
        raise bad("must be a mapping")
    unknown = set(raw) - _RULE_KEYS
    if unknown:
        raise bad(f"unknown keys {sorted(unknown)}")
    if "match" not in raw:
        raise bad("missing 'match'")
    pattern = re.compile(str(raw["match"]))
    if "tool" not in raw:
        if "reply_after_tool" in raw:
            raise bad("'reply_after_tool' needs a 'tool'")
        if "reply" not in raw:
            raise bad("needs 'reply' (or 'tool' with 'reply_after_tool')")
        return _Rule(pattern, str(raw["reply"]))
    if "reply" in raw:
        raise bad("a tool rule takes 'reply_after_tool', not 'reply'")
    if "reply_after_tool" not in raw:
        raise bad("a tool rule needs 'reply_after_tool'")
    tool = raw["tool"]
    if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or not tool["name"]:
        raise bad("'tool' must be a mapping with a 'name'")
    args = tool.get("args", {})
    if not isinstance(args, dict):
        raise bad("'tool.args' must be a mapping")
    return _Rule(pattern, str(raw["reply_after_tool"]), _ToolStep(tool["name"], args))


class ScriptedResponder:
    """Rules from a stub script. Callable as a plain ``Responder``; also able to call tools.

    Called directly it only ever returns text, so a tool rule answers with its
    ``reply_after_tool``. :class:`StubProvider` uses :meth:`respond`, which issues the scripted
    tool call (id ``stub-<n>``) when tools are on offer and remembers which rule issued each id so
    the follow-up turn, the one carrying ``tool_results``, can return that rule's reply.
    """

    def __init__(self, rules: list[_Rule]) -> None:
        self._rules = rules
        self._issued: dict[str, int] = {}
        self._issued_count = 0

    def __call__(self, conversation_id: str, messages: list[Message]) -> str:
        return self.respond(conversation_id, messages, offer_tools=False)[0]

    def respond(
        self, conversation_id: str, messages: list[Message], *, offer_tools: bool
    ) -> tuple[str, list[ToolCallRequest]]:
        if messages and messages[-1].role == "user" and messages[-1].tool_results:
            return self._after_tools(messages[-1].tool_results), []
        last = _last_user(messages)
        for index, rule in enumerate(self._rules):
            if not rule.pattern.search(last):
                continue
            if rule.tool is None or not offer_tools:
                return rule.reply, []
            self._issued_count += 1
            call_id = f"stub-{self._issued_count}"
            self._issued[call_id] = index
            call = ToolCallRequest(
                id=call_id, name=rule.tool.name, args=copy.deepcopy(rule.tool.args)
            )
            return "", [call]
        return echo_responder(conversation_id, messages), []

    def _after_tools(self, results: list[ToolResult]) -> str:
        for result in results:
            index = self._issued.get(result.id)
            if index is not None:
                return self._rules[index].reply
        return "[stub] " + results[0].text


def load_stub_script(path: Path) -> ScriptedResponder:
    """YAML list of rules; the first whose regex matches the last user message wins.

    A rule is ``{match, reply}``, or ``{match, tool: {name, args}, reply_after_tool}``: the latter
    calls the tool when tools are offered, then answers ``reply_after_tool`` once the result is
    back. Unmatched messages are echoed.
    """
    with path.open(encoding="utf-8") as fh:
        rules_raw = yaml.safe_load(fh) or []
    if not isinstance(rules_raw, list):
        raise ValueError("stub script must be a YAML list of rules")
    return ScriptedResponder([_parse_rule(i, raw) for i, raw in enumerate(rules_raw)])


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
        tool_calls: list[ToolCallRequest] = []
        if isinstance(self._responder, ScriptedResponder):
            text, tool_calls = self._responder.respond(
                conversation_id, messages, offer_tools=bool(tools)
            )
        else:
            text = self._responder(conversation_id, messages)
        sent = len(system) + sum(
            len(m.content) + sum(len(r.text) for r in m.tool_results) for m in messages
        )
        return Completion(
            text=text,
            usage=Usage(input_tokens=sent),
            cost_usd=0.0,
            backend=self.name,
            model=self.model,
            stop_reason="tool_use" if tool_calls else "end_turn",
            tool_calls=tool_calls,
        )
