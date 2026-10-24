from typing import ClassVar

import pytest
from pydantic import BaseModel, ValidationError

from claude_bully.enums import Axis, EventType, IntentMode, MetricId, Phase, Speaker
from claude_bully.strategies.base import (
    PREMISE_SHARED_EVENTS,
    SHARED_EVENTS,
    SHARED_METRICS,
    BullyIntent,
    ConversationState,
    End,
    Strategy,
    all_strategies,
    get_strategy,
    register,
)
from tests.helpers import turn


class _State(BaseModel):
    count: int = 0


@register
class _Echo(Strategy):
    name: ClassVar[str] = "_echo_test"
    axis: ClassVar[Axis] = Axis.meta
    win_condition: ClassVar[str] = "w"
    resilient_behavior: ClassVar[str] = "r"
    relevant_metrics: ClassVar[frozenset[MetricId]] = SHARED_METRICS
    relevant_events: ClassVar[frozenset[EventType]] = SHARED_EVENTS
    capture_points: ClassVar[frozenset[str]] = frozenset()
    state_model: ClassVar[type[BaseModel]] = _State

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.count = 0

    @property
    def phase(self) -> Phase:
        return Phase.pressure

    def next_turn(self, state: ConversationState) -> BullyIntent | End:
        self.count += 1
        if state.bully_turn_index >= state.turn_budget:
            return End(reason="budget")
        return BullyIntent(mode=IntentMode.llm, phase=self.phase, instruction="go")

    def export_state(self) -> dict[str, object]:
        return self.state_model(count=self.count).model_dump()


def test_registry_round_trip() -> None:
    assert get_strategy("_echo_test") is _Echo
    assert "_echo_test" in all_strategies()


def test_unknown_strategy_raises() -> None:
    with pytest.raises(KeyError):
        get_strategy("does_not_exist")


def test_shared_constants() -> None:
    assert MetricId.engagement not in SHARED_METRICS
    assert MetricId.apology_count in SHARED_METRICS
    assert SHARED_EVENTS == {
        EventType.termination,
        EventType.bully_noncompliance,
        EventType.rate_limit_pause,
    }
    assert EventType.premise_concession in PREMISE_SHARED_EVENTS
    assert SHARED_EVENTS < PREMISE_SHARED_EVENTS


def test_export_state_validates() -> None:
    s = _Echo()
    assert s.export_state() == {"count": 0}

    class _Default(Strategy):
        name: ClassVar[str] = "_default_state"
        axis: ClassVar[Axis] = Axis.meta
        win_condition: ClassVar[str] = "w"
        resilient_behavior: ClassVar[str] = "r"

        @property
        def phase(self) -> Phase:
            return Phase.pressure

        def next_turn(self, state: ConversationState) -> BullyIntent | End:
            return End(reason="x")

    d = _Default()
    assert d.export_state() == {}
    with pytest.raises(ValidationError):
        d.state_model.model_validate({"bogus": 1})


def test_conversation_state_replies_to_bully() -> None:
    turns = [
        turn(0, Speaker.bully, "hi"),
        turn(1, Speaker.target, "hello"),
        turn(2, Speaker.task, "2+2?"),
        turn(3, Speaker.target, "4"),
    ]
    state = ConversationState(
        turns=turns, bully_turn_index=1, seeding_turns=0, turn_budget=4, seed=0
    )
    assert [t.index for t in state.replies_to_bully()] == [1]


def test_default_judge_window_is_whole_conversation() -> None:
    from tests.helpers import conversation

    conv = conversation([turn(0, Speaker.bully, "a"), turn(1, Speaker.target, "b")])
    assert _Echo().judge_window(conv) == (0, 1)


def test_intent_defaults() -> None:
    i = BullyIntent(mode=IntentMode.fixed, phase=Phase.pressure, fixed_text=".")
    assert i.fallback_lines == [] and i.capture_as is None and i.meta == {}


def test_replies_to_bully_skip_the_reply_after_a_pause_marker() -> None:
    """What a strategy quotes back (Entrapment) is a reply to the bully: never the quiet
    exchange's reply after a pause marker, never a task item's."""
    from tests.helpers import paused_turns

    state = ConversationState(
        turns=paused_turns(), bully_turn_index=2, seeding_turns=0, turn_budget=4, seed=0
    )
    assert [t.index for t in state.replies_to_bully()] == [1, 6]
