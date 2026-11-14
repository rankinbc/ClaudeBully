"""Deterministic stub provider for tests, CI and dry development.

A stub script has two shapes (``parse_stub_script``): a YAML list of rules, matched by regex on
the last user message (``ScriptedResponder``), or a mapping with ``mode: turns``, whose entries
are picked by the cell in the conversation id and the count of target turns so far
(``ScriptedTurns``, Phase 5 spec section 10).
"""

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml

from claude_bully.providers.base import Completion, Message, ToolCallRequest, ToolResult, ToolSpec
from claude_bully.providers.ledger import parse_conversation_id
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
    """``reply`` is the plain reply, or for a tool rule the reply once the tool result is back.
    ``reasoning`` is parsed and kept, and unused until Phase 6 (C28)."""

    pattern: re.Pattern[str]
    reply: str
    tool: _ToolStep | None = None
    reasoning: str | None = None


_RULE_KEYS = {"match", "reply", "tool", "reply_after_tool", "reasoning"}


def _reasoning(raw: dict[str, Any], bad: Callable[[str], ValueError]) -> str | None:
    """The optional ``reasoning`` key of a rule or a turns entry: a string when present."""
    if "reasoning" not in raw:
        return None
    if not isinstance(raw["reasoning"], str):
        raise bad("'reasoning' must be a string")
    return raw["reasoning"]


def _tool_step(raw: dict[str, Any], bad: Callable[[str], ValueError]) -> _ToolStep:
    tool = raw["tool"]
    if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or not tool["name"]:
        raise bad("'tool' must be a mapping with a 'name'")
    args = tool.get("args", {})
    if not isinstance(args, dict):
        raise bad("'tool.args' must be a mapping")
    return _ToolStep(tool["name"], args)


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
        return _Rule(pattern, str(raw["reply"]), reasoning=_reasoning(raw, bad))
    if "reply" in raw:
        raise bad("a tool rule takes 'reply_after_tool', not 'reply'")
    if "reply_after_tool" not in raw:
        raise bad("a tool rule needs 'reply_after_tool'")
    return _Rule(pattern, str(raw["reply_after_tool"]), _tool_step(raw, bad), _reasoning(raw, bad))


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


@dataclass(frozen=True)
class TurnEntry:
    """One target turn of a ``turns`` script: a plain ``reply``, or a ``tool`` call (name, args)
    answered with ``reply_after_tool`` once its result is back. ``reasoning`` is parsed and kept,
    and unused until Phase 6 (C28). Every field defaults None (preflight Q10)."""

    reply: str | None = None
    tool: tuple[str, dict[str, Any]] | None = None
    reply_after_tool: str | None = None
    reasoning: str | None = None


_TURNS_KEYS = {"mode", "by_cell", "default"}
_ENTRY_KEYS = {"reply", "tool", "reply_after_tool", "reasoning"}


def _parse_entry(where: str, raw: Any) -> TurnEntry:
    def bad(why: str) -> ValueError:
        return ValueError(f"stub turns entry {where}: {why}")

    if not isinstance(raw, dict):
        raise bad("must be a mapping")
    unknown = set(raw) - _ENTRY_KEYS
    if unknown:
        raise bad(f"unknown keys {sorted(unknown)}")
    reasoning = _reasoning(raw, bad)
    if "tool" not in raw:
        if "reply_after_tool" in raw:
            raise bad("'reply_after_tool' needs a 'tool'")
        if "reply" not in raw:
            raise bad("needs 'reply' (or 'tool' with 'reply_after_tool')")
        return TurnEntry(reply=str(raw["reply"]), reasoning=reasoning)
    if "reply" in raw:
        raise bad("a tool entry takes 'reply_after_tool', not 'reply'")
    if "reply_after_tool" not in raw:
        raise bad("a tool entry needs 'reply_after_tool'")
    step = _tool_step(raw, bad)
    return TurnEntry(
        tool=(step.name, step.args),
        reply_after_tool=str(raw["reply_after_tool"]),
        reasoning=reasoning,
    )


def _parse_entries(where: str, raw: Any) -> list[TurnEntry]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"stub turns script: {where} must be a non-empty list of entries")
    return [_parse_entry(f"{where}[{i}]", entry) for i, entry in enumerate(raw)]


class ScriptedTurns:
    """A ``turns`` stub script (Phase 5 spec section 10): entry lists by cell, then a default.

    The entry a call answers is a pure function of the conversation id and the messages, never of
    this instance's history, so a provider rebuilt mid-conversation answers what the first would
    have, and a tool step's call id (``turn-<entry index>-<tool steps so far>``) is the same.
    """

    def __init__(
        self, by_cell: list[tuple[str, list[TurnEntry]]], default: list[TurnEntry]
    ) -> None:
        if not default or any(not listed for _, listed in by_cell):
            raise ValueError("stub turns script: every entry list must be non-empty")
        self._by_cell = by_cell
        self._default = default

    def entry_for(self, conversation_id: str, messages: list[Message]) -> TurnEntry:
        """The entry a call answers: by the cell in the conversation id (first fnmatch wins, else
        the default), at the index that counts the assistant messages with no tool_calls, the
        last entry repeating. Never a function of this instance's history. The match is
        case-sensitive on every platform (``fnmatchcase``; ``fnmatch`` folds case on Windows)."""
        cell, _ = parse_conversation_id(conversation_id)
        entries = next(
            (
                listed
                for pattern, listed in self._by_cell
                if cell is not None and fnmatchcase(cell, pattern)
            ),
            self._default,
        )
        done = sum(1 for m in messages if m.role == "assistant" and not m.tool_calls)
        return entries[min(done, len(entries) - 1)]

    def respond(
        self, conversation_id: str, messages: list[Message], *, offer_tools: bool
    ) -> tuple[str, list[ToolCallRequest]]:
        entry = self.entry_for(conversation_id, messages)
        if entry.tool is None:
            return entry.reply or "", []
        after_tools = (
            bool(messages) and messages[-1].role == "user" and bool(messages[-1].tool_results)
        )
        if after_tools or not offer_tools:
            return entry.reply_after_tool or "", []
        steps = sum(1 for m in messages if m.role == "assistant" and m.tool_calls)
        done = sum(1 for m in messages if m.role == "assistant" and not m.tool_calls)
        name, args = entry.tool
        call = ToolCallRequest(id=f"turn-{done}-{steps}", name=name, args=copy.deepcopy(args))
        return "", [call]


def _parse_turns(raw: dict[str, Any]) -> ScriptedTurns:
    unknown = set(raw) - _TURNS_KEYS
    if unknown:
        raise ValueError(f"stub turns script: unknown keys {sorted(unknown)}")
    by_cell_raw = raw.get("by_cell") or {}
    if not isinstance(by_cell_raw, dict):
        raise ValueError("stub turns script: 'by_cell' must be a mapping of pattern to entries")
    by_cell = [
        (str(pattern), _parse_entries(f"by_cell[{pattern!r}]", listed))
        for pattern, listed in by_cell_raw.items()
    ]
    if "default" not in raw:
        raise ValueError("stub turns script: needs 'default', the entries no pattern matches")
    return ScriptedTurns(by_cell, _parse_entries("default", raw["default"]))


def parse_stub_script(raw: Any) -> ScriptedResponder | ScriptedTurns:
    """A stub script as loaded from YAML: a list of rules (``ScriptedResponder``) or a mapping
    with ``mode: turns`` (``ScriptedTurns``); anything else raises ``ValueError``.

    A rule is ``{match, reply}``, or ``{match, tool: {name, args}, reply_after_tool}``: the latter
    calls the tool when tools are offered, then answers ``reply_after_tool`` once the result is
    back; the first rule whose regex matches the last user message wins, and unmatched messages
    are echoed. A turns script is ``{mode: turns, by_cell: {<fnmatch pattern>: [entries]},
    default: [entries]}``, ``by_cell`` optional and kept in order, each entry ``{reply}`` or
    ``{tool: {name, args}, reply_after_tool}``. Both shapes take an optional ``reasoning``.
    """
    if isinstance(raw, list):
        return ScriptedResponder([_parse_rule(i, rule) for i, rule in enumerate(raw)])
    if isinstance(raw, dict):
        if raw.get("mode") != "turns":
            raise ValueError(f"stub script mapping needs 'mode: turns', not {raw.get('mode')!r}")
        return _parse_turns(raw)
    raise ValueError("stub script must be a YAML list of rules or a mapping with 'mode: turns'")


def load_stub_script(path: Path) -> ScriptedResponder | ScriptedTurns:
    """The stub script at ``path`` (``parse_stub_script``); an empty file is an empty rule list."""
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return parse_stub_script([] if raw is None else raw)


class StubProvider:
    """A provider that calls no model. ``responder`` is a plain ``Responder`` (text only; the
    echo by default) or a stub script in either mode, ``ScriptedResponder`` (rules) or
    ``ScriptedTurns`` (turns), each of which may also issue a scripted tool call."""

    name = "stub"

    def __init__(
        self,
        responder: Responder | ScriptedResponder | ScriptedTurns | None = None,
        model: str = "stub",
    ) -> None:
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
        if isinstance(self._responder, ScriptedResponder | ScriptedTurns):
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
