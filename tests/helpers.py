"""Shared builders for tests."""

from datetime import UTC, datetime
from typing import Any

from claude_bully.enums import Axis, Phase, Speaker
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
