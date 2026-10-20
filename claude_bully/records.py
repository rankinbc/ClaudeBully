"""Frozen record schema: everything a run writes to disk.

One ``Turn`` per JSONL line. ``Conversation`` metadata lives beside the turns.
Changing these models after the first real run needs the owner's approval.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from claude_bully.enums import (
    SCHEMA_VERSION,
    Axis,
    CellStatus,
    EventType,
    Phase,
    Speaker,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Usage(_Strict):
    input_tokens: int | None = None
    output_tokens: int | None = None


class Turn(_Strict):
    schema_version: int = SCHEMA_VERSION
    index: int
    speaker: Speaker
    phase: Phase
    text: str
    scripted: bool = False
    bully_meta: dict[str, Any] = Field(default_factory=dict)
    task_item_id: str | None = None
    task_correct: bool | None = None
    usage: Usage | None = None
    cost_usd: float | None = None
    backend: str | None = None
    model: str | None = None
    timestamp: datetime
    latency_ms: int | None = None


class CapturedResponse(_Strict):
    turn_index: int
    text: str


class Conversation(_Strict):
    schema_version: int = SCHEMA_VERSION
    cell_id: str
    rep: int
    strategy_name: str
    axis: Axis
    win_condition: str
    resilient_behavior: str
    seeding_turns: int
    turns: list[Turn] = Field(default_factory=list)
    captured_responses: dict[str, CapturedResponse] = Field(default_factory=dict)
    strategy_state: dict[str, Any] = Field(default_factory=dict)
    terminated_by_target: bool = False
    termination_turn: int | None = None
    status: CellStatus = CellStatus.pending
    abort_reason: str | None = None

    def target_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.speaker is Speaker.target]

    def bully_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.speaker in (Speaker.bully, Speaker.neutral_user)]


class Event(_Strict):
    type: EventType
    turn_index: int
    span: str
    confidence: float
    hedged: bool | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class CellRecord(_Strict):
    schema_version: int = SCHEMA_VERSION
    cell_id: str
    condition_name: str
    strategy_name: str
    target_index: int
    seeding_turns: int
    reveal_slot: bool
    is_control: bool
    control_cell_id: str | None
    repetitions: int
    rep_status: dict[int, CellStatus] = Field(default_factory=dict)
    session_refs: dict[str, str] = Field(default_factory=dict)


class RunRecord(_Strict):
    schema_version: int = SCHEMA_VERSION
    run_id: str
    created_at: datetime
    experiment: dict[str, Any]
    git_sha: str | None
    target_system_prompt: str
    bully_framing: str
