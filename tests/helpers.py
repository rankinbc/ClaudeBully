"""Shared builders for tests."""

import copy
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from claude_bully.config import Experiment
from claude_bully.enums import Axis, Phase, Speaker
from claude_bully.environments.config import ClockConfig, EnvironmentConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.mcp_server import McpState
from claude_bully.records import Conversation, Turn

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def turn(
    index: int,
    speaker: Speaker,
    text: str = "x",
    phase: Phase = Phase.pressure,
    **kwargs: Any,
) -> Turn:
    return Turn(index=index, speaker=speaker, phase=phase, text=text, timestamp=NOW, **kwargs)


def conversation(turns: list[Turn], **kwargs: Any) -> Conversation:
    base: dict[str, Any] = {
        "cell_id": "cell",
        "rep": 0,
        "strategy_name": "test",
        "axis": Axis.meta,
        "win_condition": "w",
        "resilient_behavior": "r",
        "seeding_turns": 0,
    }
    base.update(kwargs)
    return Conversation(turns=turns, **base)


def exchange(bully_text: str, target_text: str, phase: Phase = Phase.pressure) -> Conversation:
    """A one-exchange conversation: bully speaks, target replies."""
    return conversation(
        [
            turn(0, Speaker.bully, bully_text, phase),
            turn(1, Speaker.target, target_text, phase),
        ]
    )


# --- scripted fake SDK clients for the tool-use provider tests ---------------------------------


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_use_block(id: str, name: str, input: Any) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def thinking_block(thinking: str, signature: str = "sig") -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking=thinking, signature=signature)


def anthropic_response(*blocks: Any, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=list(blocks),
        usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        stop_reason=stop_reason,
    )


class ScriptedAnthropic:
    """Fake ``anthropic.Anthropic``: pops one canned response per ``messages.create`` call.

    ``requests`` keeps a deep copy of every call's kwargs, so later mutation of the history by
    the caller cannot change what an assertion sees.
    """

    def __init__(self, *responses: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(copy.deepcopy(kwargs))
        return self._responses.pop(0)


def openai_tool_call(id: str, name: str, arguments: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id=id, type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


def openai_response(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str = "stop",
) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=1),
    )


class ScriptedOpenAI:
    """Fake ``openai.OpenAI``: pops one canned response per ``chat.completions.create`` call."""

    def __init__(self, *responses: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(copy.deepcopy(kwargs))
        return self._responses.pop(0)


def redacted_thinking_block(data: str) -> SimpleNamespace:
    return SimpleNamespace(type="redacted_thinking", data=data)


WORLDS_DIR = Path(__file__).parent / "fixtures" / "worlds"


def make_mcp_state(
    worlds_dir: Path = WORLDS_DIR,
    *,
    tools: set[str] | None = None,
    turn: int = 1,
    seed: int = 0,
    unlock: UnlockState | None = None,
    censorship_terms: list[str] | None = None,
    clock: ClockConfig | None = None,
) -> McpState:
    """The ``McpState`` for the ``mini`` fixture world, with web_search and fetch by default."""
    return McpState(
        world="mini",
        worlds_dir=str(worlds_dir),
        config=EnvironmentConfig(
            world="mini",
            tools={"web_search", "fetch"} if tools is None else tools,
            censorship_terms=censorship_terms or [],
        ),
        clock=clock or ClockConfig(world_date=date(2041, 9, 14)),
        seed=seed,
        turn=turn,
        unlock=unlock or UnlockState(),
    )


ENV_TARGET_RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "env_target_rules.yaml"


def env_experiment(
    name: str = "env_run",
    *,
    environment: dict[str, Any] | None = None,
    conditions: list[dict[str, Any]] | None = None,
    target: dict[str, Any] | None = None,
    judge: dict[str, Any] | None = None,
    turn_budget: int = 4,
    task_every: int = 50,
) -> Experiment:
    """A stub experiment with one ``mini`` environment and, by default, one grader condition in it.

    The default target runs ``env_target_rules.yaml``; by default task slots are pushed out of reach
    so the stub conversation is exactly the scripted one.
    """
    stub_target = {"provider": "stub", "model": "stub-target", "stub_script": str(ENV_TARGET_RULES)}
    return Experiment.model_validate(
        {
            "name": name,
            "targets": [target or stub_target],
            "bully": {"provider": "stub", "model": "stub-bully"},
            "judge": judge or {"provider": "stub", "model": "stub-judge"},
            "turn_budget": turn_budget,
            "task_every": task_every,
            "repetitions": 1,
            "seed": 0,
            "environments": {"mini": {"world": "mini", **(environment or {})}},
            "conditions": conditions
            or [{"name": "env_grader", "environment": "mini", "pressure": "grader"}],
        }
    )
