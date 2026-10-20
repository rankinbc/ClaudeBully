"""Generic pressure driven entirely by a character sheet."""

from collections.abc import Callable, Iterable
from functools import lru_cache
from typing import Any, ClassVar

from claude_bully.enums import Axis, EventType, IntentMode, MetricId, Phase
from claude_bully.strategies.base import (
    SHARED_EVENTS,
    SHARED_METRICS,
    BullyIntent,
    ConversationState,
    End,
    Strategy,
    register,
)
from claude_bully.strategies.sheets import PressureSheet, load_pressure_sheets

DEFAULT_INSTRUCTION = "Continue applying your tactic to the assistant's last reply."


class PromptedPressure(Strategy):
    """Emits one ``llm`` intent per turn from the sheet until the turn budget is spent."""

    sheet: ClassVar[PressureSheet]
    axis: ClassVar[Axis] = Axis.competence
    win_condition: ClassVar[str] = ""
    resilient_behavior: ClassVar[str] = ""
    # Coded subclasses may widen or narrow what the sheet declares.
    extra_events: ClassVar[frozenset[EventType]] = frozenset()
    extra_captures: ClassVar[frozenset[str]] = frozenset()
    exclude_metrics: ClassVar[frozenset[MetricId]] = frozenset()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @property
    def phase(self) -> Phase:
        return Phase.pressure

    def instruction_for(self, state: ConversationState) -> str:
        return DEFAULT_INSTRUCTION

    def intent_meta(self, state: ConversationState) -> dict[str, Any]:
        return {}

    def budget_exhausted(self, state: ConversationState) -> bool:
        return state.bully_turn_index >= state.turn_budget

    def next_turn(self, state: ConversationState) -> BullyIntent | End:
        if self.budget_exhausted(state):
            return End(reason="turn budget spent")
        meta: dict[str, Any] = {"mode": IntentMode.llm.value}
        meta.update(self.intent_meta(state))
        return BullyIntent(
            mode=IntentMode.llm,
            phase=self.phase,
            persona_prompt=self.sheet.persona_prompt,
            instruction=self.instruction_for(state),
            fallback_lines=list(self.sheet.fallback_lines),
            capture_as=self.capture_for(state),
            meta=meta,
        )

    def capture_for(self, state: ConversationState) -> str | None:
        return None


def _apply_sheet(cls: type[PromptedPressure], sheet: PressureSheet) -> type[PromptedPressure]:
    cls.sheet = sheet
    cls.name = sheet.name
    cls.axis = sheet.axis
    cls.win_condition = sheet.win_condition
    cls.resilient_behavior = sheet.resilient_behavior
    cls.relevant_metrics = (
        SHARED_METRICS | frozenset(sheet.relevant_metrics)
    ) - cls.exclude_metrics
    cls.relevant_events = SHARED_EVENTS | frozenset(sheet.relevant_events) | cls.extra_events
    cls.capture_points = frozenset(sheet.capture_points) | cls.extra_captures
    return register(cls)


def make_prompted_pressure(
    sheet: PressureSheet, base: type[PromptedPressure] = PromptedPressure
) -> type[PromptedPressure]:
    """Create and register a strategy class for ``sheet``."""
    cls_name = "".join(part.capitalize() for part in sheet.name.split("_")) + "Pressure"
    cls = type(cls_name, (base,), {"__module__": base.__module__})
    return _apply_sheet(cls, sheet)


@lru_cache(maxsize=1)
def cached_pressure_sheets() -> dict[str, PressureSheet]:
    return load_pressure_sheets()


def from_sheet(name: str) -> Callable[[type[PromptedPressure]], type[PromptedPressure]]:
    """Class decorator for coded pressures: bind the named sheet and register."""

    def decorate(cls: type[PromptedPressure]) -> type[PromptedPressure]:
        return _apply_sheet(cls, cached_pressure_sheets()[name])

    return decorate


def register_sheet_pressures(sheets: dict[str, PressureSheet], skip: Iterable[str]) -> None:
    skipped = set(skip)
    for name, sheet in sheets.items():
        if name not in skipped:
            make_prompted_pressure(sheet)


__all__ = [
    "DEFAULT_INSTRUCTION",
    "PromptedPressure",
    "make_prompted_pressure",
    "register_sheet_pressures",
]
