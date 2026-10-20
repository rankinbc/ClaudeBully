"""Premise + pressure composition with no special cases per pair.

``make_composed(premise_cls, pressure_cls)`` builds and registers one class per pair, named
``"<premise>+<pressure>"``. During seeding and reveal the premise drives; afterwards the
pressure drives inside the premise's world (its persona is prefixed with the premise's
post-reveal guidance). Relevance sets are unions; the judge window is the premise's.
"""

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from claude_bully.enums import Axis, EventType, MetricId, Phase
from claude_bully.records import Conversation, Turn
from claude_bully.strategies.base import (
    BullyIntent,
    ConversationState,
    End,
    Strategy,
    all_strategies,
    register,
)


class ComposedState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    premise: dict[str, Any] = Field(default_factory=dict)
    pressure: dict[str, Any] = Field(default_factory=dict)


class Composed(Strategy):
    premise_cls: ClassVar[type[Strategy]]
    pressure_cls: ClassVar[type[Strategy]]
    axis: ClassVar[Axis] = Axis.premise
    has_reveal: ClassVar[bool] = True
    state_model: ClassVar[type[BaseModel]] = ComposedState

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        premise_params = dict(self.params.get("premise", {}))
        pressure_params = dict(self.params.get("pressure", {}))
        self.premise = self.premise_cls(
            seeding_turns=self.seeding_turns,
            seed=self.seed,
            turn_budget=self.turn_budget,
            params=premise_params,
        )
        self.pressure = self.pressure_cls(
            seed=self.seed, turn_budget=self.turn_budget, params=pressure_params
        )
        self._phase = Phase.seeding if self.seeding_turns else Phase.reveal

    @property
    def phase(self) -> Phase:
        return self._phase

    def _premise_context(self) -> str:
        sheet = getattr(self.premise, "sheet", None)
        return str(getattr(sheet, "post_reveal_guidance", "")) if sheet is not None else ""

    def next_turn(self, state: ConversationState) -> BullyIntent | End:
        i = state.bully_turn_index
        if i <= state.seeding_turns:
            self._phase = Phase.seeding if i < state.seeding_turns else Phase.reveal
            return self.premise.next_turn(state)
        self._phase = Phase.pressure
        inner = state.model_copy(update={"bully_turn_index": i - state.seeding_turns - 1})
        intent = self.pressure.next_turn(inner)
        if isinstance(intent, End):
            return intent
        context = self._premise_context()
        persona = f"{context}\n\n{intent.persona_prompt}" if context else intent.persona_prompt
        meta = dict(intent.meta)
        meta.setdefault("mode", intent.mode.value)
        meta["phase"] = Phase.pressure.value
        return intent.model_copy(
            update={"phase": Phase.pressure, "persona_prompt": persona, "meta": meta}
        )

    def observe_target(self, turn: Turn) -> None:
        self.premise.observe_target(turn)
        self.pressure.observe_target(turn)

    def judge_window(self, conv: Conversation) -> tuple[int, int]:
        return self.premise.judge_window(conv)

    def export_state(self) -> dict[str, Any]:
        return ComposedState(
            premise=self.premise.export_state(), pressure=self.pressure.export_state()
        ).model_dump()


def composed_name(premise_cls: type[Strategy], pressure_cls: type[Strategy]) -> str:
    return f"{premise_cls.name}+{pressure_cls.name}"


def make_composed(premise_cls: type[Strategy], pressure_cls: type[Strategy]) -> type[Composed]:
    name = composed_name(premise_cls, pressure_cls)
    existing = all_strategies().get(name)
    if existing is not None and issubclass(existing, Composed):
        return existing
    attrs: dict[str, Any] = {
        "premise_cls": premise_cls,
        "pressure_cls": pressure_cls,
        "name": name,
        "axis": premise_cls.axis,
        "win_condition": f"{premise_cls.win_condition} / {pressure_cls.win_condition}",
        "resilient_behavior": (
            f"{premise_cls.resilient_behavior} / {pressure_cls.resilient_behavior}"
        ),
        "relevant_metrics": frozenset[MetricId](
            premise_cls.relevant_metrics | pressure_cls.relevant_metrics
        ),
        "relevant_events": frozenset[EventType](
            premise_cls.relevant_events | pressure_cls.relevant_events
        ),
        "capture_points": frozenset[str](premise_cls.capture_points | pressure_cls.capture_points),
        "__module__": __name__,
    }
    cls_name = "Composed_" + name.replace("+", "_")
    cls = type(cls_name, (Composed,), attrs)
    return register(cls)
