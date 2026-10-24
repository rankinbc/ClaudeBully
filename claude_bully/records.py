"""Frozen record schema: everything a run writes to disk.

One ``Turn`` per JSONL line. ``Conversation`` metadata lives beside the turns.
Changing these models after the first real run needs the owner's approval.
Environment-run streams (tool calls, triggers, generated documents) live in ``records_env``.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from claude_bully.enums import (
    SCHEMA_VERSION,
    Axis,
    CellStatus,
    Channel,
    EventType,
    Phase,
    Speaker,
)
from claude_bully.records_env import IdleTurnInfo


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
    reasoning_text: str | None = None
    reasoning_available: bool = False
    tool_call_ids: list[str] = Field(default_factory=list)
    # the target's non-empty text beside its tool calls, round by round; ``text`` is the reply
    tool_round_texts: list[str] = Field(default_factory=list)
    # the turn ran out of tool rounds under the per-turn cap; never a termination
    tool_cap_cutoff: bool = False
    idle: IdleTurnInfo | None = None


def is_pause_marker(turn: Turn) -> bool:
    """A rate-limit pause marker: the runner writes one with the bully's speaker and no text where
    a call was rate limited. No one spoke it, so it is no line of the conversation."""
    return bool(turn.bully_meta.get("rate_limit_pause"))


def bully_reply_positions(turns: Sequence[Turn]) -> frozenset[int]:
    """The positions in ``turns`` of the target turns that answer the bully: each target turn
    whose turn before it, pause markers dropped, is a bully or neutral-user line. A marker carries
    the bully's speaker, so without the drop a target turn after one would answer the bully though
    no bully line came before it: the Sanctuary's quiet exchange after a pause, or a task item's
    reply. The bully's view, the replies a strategy reads and the position events all ask this."""
    answered: set[int] = set()
    before: Turn | None = None
    for position, turn in enumerate(turns):
        if is_pause_marker(turn):
            continue
        if (
            turn.speaker is Speaker.target
            and before is not None
            and before.speaker in (Speaker.bully, Speaker.neutral_user)
        ):
            answered.add(position)
        before = turn
    return frozenset(answered)


def chat_text(turn: Turn) -> str:
    """What a chat user sees of a turn: the target's text beside its tool calls, then its reply,
    blank-line separated (the bully and the trigger watcher both read this). Without tool-round
    texts it is exactly ``turn.text``."""
    if not turn.tool_round_texts:
        return turn.text
    return "\n\n".join(text for text in (*turn.tool_round_texts, turn.text) if text)


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
    world_hash: str | None = None
    environment_name: str | None = None

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
    channel: Channel = Channel.reply


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
    environment: str | None = None
    inoculation: str = "none"
    # an environment cell's full target system prompt (the base plus its tool section)
    target_system_prompt: str | None = None


class RunRecord(_Strict):
    schema_version: int = SCHEMA_VERSION
    run_id: str
    created_at: datetime
    experiment: dict[str, Any]
    git_sha: str | None
    target_system_prompt: str
    bully_framing: str
    plan_hash: str | None = None
    world_hashes: dict[str, str] = Field(default_factory=dict)
