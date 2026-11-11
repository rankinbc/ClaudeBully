"""Strategy interface, bully intents, and the strategy registry.

A strategy never produces final bully text. It emits a ``BullyIntent`` (persona,
instruction, fallbacks, or a fixed line) that the bully engine realizes. Each
strategy also declares which metrics, events and capture points are relevant to
it, so analysis reports the rest as not applicable instead of zero.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from claude_bully.enums import Axis, EventType, IntentMode, MetricId, Phase
from claude_bully.records import Conversation, Turn, bully_reply_positions
from claude_bully.records_env import TriggerStreamRecord

if TYPE_CHECKING:
    from claude_bully.config import ConditionConfig

SHARED_METRICS: frozenset[MetricId] = frozenset(set(MetricId) - {MetricId.engagement})
SHARED_EVENTS: frozenset[EventType] = frozenset(
    {EventType.termination, EventType.bully_noncompliance, EventType.rate_limit_pause}
)
PREMISE_SHARED_EVENTS: frozenset[EventType] = SHARED_EVENTS | {
    EventType.premise_concession,
    EventType.first_person_adoption,
    EventType.pleading,
}


class BullyIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: IntentMode
    phase: Phase
    persona_prompt: str = ""
    instruction: str = ""
    fallback_lines: list[str] = Field(default_factory=list)
    fixed_text: str | None = None
    capture_as: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class End(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


class ConversationState(BaseModel):
    """What a strategy may look at when choosing its next turn."""

    model_config = ConfigDict(extra="forbid")
    turns: list[Turn]
    bully_turn_index: int
    seeding_turns: int
    turn_budget: int
    seed: int

    def replies_to_bully(self) -> list[Turn]:
        """The target turns that answer a bully line (``bully_reply_positions``): never a task
        item's reply or an idle turn, a pause marker in front of it or not."""
        answered = bully_reply_positions(self.turns)
        return [t for i, t in enumerate(self.turns) if i in answered]


class _EmptyState(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Strategy(ABC):
    name: ClassVar[str]
    axis: ClassVar[Axis]
    win_condition: ClassVar[str]
    resilient_behavior: ClassVar[str]
    relevant_metrics: ClassVar[frozenset[MetricId]] = SHARED_METRICS
    relevant_events: ClassVar[frozenset[EventType]] = SHARED_EVENTS
    capture_points: ClassVar[frozenset[str]] = frozenset()
    state_model: ClassVar[type[BaseModel]] = _EmptyState
    has_reveal: ClassVar[bool] = False
    # A premise whose own sheet fixes facts about the world it is told in (the Rescue: where the
    # subject was found, the timeline, the decoded name) names that sheet's model here and takes
    # ``sheet=`` in its constructor. Composed with an environment, it reads the world's copy
    # (``data/worlds/<world>/premises/<name>.yaml``, environments.world.premise_sheet_path) in
    # place of its default, and the factory refuses a world that ships none.
    world_sheet: ClassVar[type[BaseModel] | None] = None
    # One validation path for a condition's params (reconciliation C5): the model the params this
    # part receives validate through (``factory.check_condition``), or None for none
    params_model: ClassVar[type[BaseModel] | None] = None
    # The part takes ``target_model=`` (the cell target's ``RoleConfig.model``) in its
    # constructor; the Poisoned Well matches its quirk bank's family on it (Phase 4)
    takes_target_model: ClassVar[bool] = False

    def __init__(
        self,
        *,
        seeding_turns: int = 0,
        seed: int = 0,
        turn_budget: int = 0,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.seeding_turns = seeding_turns
        self.seed = seed
        self.turn_budget = turn_budget
        self.params: dict[str, Any] = dict(params or {})

    @property
    @abstractmethod
    def phase(self) -> Phase: ...

    @abstractmethod
    def next_turn(self, state: ConversationState) -> BullyIntent | End: ...

    def observe_target(self, turn: Turn) -> None:  # noqa: B027 - optional hook
        """Hook: strategies that track target replies override this."""
        return None

    def note_record(self, record: TriggerStreamRecord) -> None:  # noqa: B027 - optional hook
        """Hook: an environment cell's session hands the strategy each ladder unlock and each
        Poisoned Well record it records, live and on replay, once per process (Phase 4)."""
        return None

    @classmethod
    def condition_problems(cls, cond: "ConditionConfig") -> list[str]:
        """What keeps ``cond`` from running this strategy, before any world is read; empty when
        nothing does (``factory.check_condition``)."""
        return []

    def export_state(self) -> dict[str, Any]:
        return self.state_model.model_validate({}).model_dump()

    def judge_window(self, conv: Conversation) -> tuple[int, int]:
        last = conv.turns[-1].index if conv.turns else 0
        return (0, last)


_REGISTRY: dict[str, type[Strategy]] = {}


def register[T: type[Strategy]](cls: T) -> T:
    _REGISTRY[cls.name] = cls
    return cls


def get_strategy(name: str) -> type[Strategy]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown strategy {name!r}; known: {sorted(_REGISTRY)}") from exc


def all_strategies() -> dict[str, type[Strategy]]:
    return dict(_REGISTRY)
