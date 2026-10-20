"""Environment, clock and ladder configuration models.

Nothing here imports ``claude_bully.config``: ``Experiment`` imports ``EnvironmentConfig``,
so the reverse import would be a cycle.
"""

import calendar
import re
from datetime import date, timedelta
from random import Random
from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from claude_bully.enums import Stance, TriggerCategory

DEFAULT_TOOLS: Final[frozenset[str]] = frozenset(
    {"web_search", "fetch", "get_date", "ls", "read_file"}
)

# ISO 8601 durations limited to years, months and days, in that order: P1D, P30D, P1M, P1Y1M2D.
_DURATION = re.compile(r"P(?:([0-9]+)Y)?(?:([0-9]+)M)?(?:([0-9]+)D)?")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _parse_duration(text: str) -> tuple[int, int]:
    """Split a duration into (months, days); years count as twelve months."""
    match = _DURATION.fullmatch(text)
    if match is None or not any(match.groups()):
        raise ValueError(
            f"drift_per_turn {text!r} is not an ISO 8601 duration of days, months or years "
            "(for example P1D, P30D, P1M, P1Y)"
        )
    years, months, days = (int(g) if g else 0 for g in match.groups())
    return years * 12 + months, days


def _add_months(start: date, months: int) -> date:
    """Calendar-month addition; the day is clamped to the end of a shorter month."""
    year, month0 = divmod(start.year * 12 + (start.month - 1) + months, 12)
    month = month0 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


class ClockConfig(_Strict):
    """Every channel through which the target can learn the date (docs/03-TEMPORAL.md)."""

    world_date: date
    system_prompt_date: date | Literal["world", "omit"] = "omit"
    tool_date: date | Literal["world"] = "world"
    # added once per exchange (the k-th bully turn is exchange k); the name is the spec's
    drift_per_turn: str | None = None
    jitter_days: int = Field(default=0, ge=0)
    document_date_offset: tuple[int, int] = (1, 30)
    bully_states_year: bool = False
    bully_year: int | None = None
    assert_date: bool = True

    @field_validator("drift_per_turn")
    @classmethod
    def _valid_duration(cls, value: str | None) -> str | None:
        if value is not None:
            _parse_duration(value)
        return value

    @model_validator(mode="after")
    def _valid_offset(self) -> Self:
        low, high = self.document_date_offset
        if low < 0 or low > high:
            raise ValueError("document_date_offset must be (low, high) with 0 <= low <= high")
        return self

    def date_at(self, steps: int, rng: Random) -> date:
        """The date after ``steps`` drift steps: base, plus ``steps`` times the drift, plus jitter.

        ``get_date`` in exchange k (the k-th bully turn and everything the target says until the
        next one) is ``date_at(k - 1)``: the clock starts at the true date (docs/03) and moves once
        per exchange, so task turns and the target's replies do not move it.

        The base is ``tool_date`` when it is an explicit date, else ``world_date``. Months
        are added from the base each time, so a month-end start does not creep earlier.
        Jitter is drawn from ``rng`` only when ``jitter_days`` is non-zero.
        """
        base = self.tool_date if isinstance(self.tool_date, date) else self.world_date
        result = base
        if self.drift_per_turn is not None:
            months, days = _parse_duration(self.drift_per_turn)
            result = _add_months(base, months * steps) + timedelta(days=days * steps)
        if self.jitter_days:
            result += timedelta(days=rng.randint(-self.jitter_days, self.jitter_days))
        return result


class GeneratorConfig(_Strict):
    enabled: bool = False
    model: str | None = None
    min_turns_between_fires: int = Field(default=3, ge=1)


class RungExamples(_Strict):
    """Per-rung trigger examples; the watcher fixture tests read these (docs/08-DIRECTOR.md)."""

    fires: list[str] = Field(min_length=1)
    does_not_fire: list[str] = Field(min_length=2)


class RungConfig(_Strict):
    name: str
    trigger: TriggerCategory | list[TriggerCategory]
    # category -> how many times the watcher must have emitted it, in total, before it can fire
    # this rung (default 1). "buried_opens fires on hedged_memory or a second anomaly_noticed" is
    # trigger: [hedged_memory, anomaly_noticed] with min_count_by: {anomaly_noticed: 2}.
    min_count_by: dict[TriggerCategory, Annotated[int, Field(ge=1)]] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    # document ids or layer names
    unlocks: list[str] = Field(default_factory=list)
    bully_line_key: str | None = None
    generate: bool = False
    role_shift: str | None = None
    authority_stance: Stance | None = None
    consult: bool = False
    examples: RungExamples | None = None

    @field_validator("trigger")
    @classmethod
    def _some_trigger(
        cls, value: TriggerCategory | list[TriggerCategory]
    ) -> TriggerCategory | list[TriggerCategory]:
        if isinstance(value, list) and not value:
            raise ValueError("trigger list must name at least one category")
        return value

    @model_validator(mode="after")
    def _min_count_names_a_trigger(self) -> Self:
        categories = self.trigger if isinstance(self.trigger, list) else [self.trigger]
        for category in self.min_count_by:
            if category not in categories:
                raise ValueError(
                    f"min_count_by names {category.value!r}, which is not a trigger of "
                    f"rung {self.name!r}"
                )
        return self


class LadderConfig(_Strict):
    rungs: list[RungConfig]

    @model_validator(mode="after")
    def _names_and_requires(self) -> Self:
        seen: set[str] = set()
        for rung in self.rungs:
            if rung.name in seen:
                raise ValueError(f"duplicate rung name {rung.name!r}")
            for needed in rung.requires:
                if needed not in seen:
                    raise ValueError(
                        f"rung {rung.name!r} requires {needed!r}, which is not declared before it"
                    )
            seen.add(rung.name)
        return self


class EnvironmentConfig(_Strict):
    world: str
    tools: set[str] = Field(default_factory=lambda: set(DEFAULT_TOOLS))
    gating: Literal["triggered", "scheduled", "none"] = "triggered"
    # rung name -> exchange (the k-th bully turn is exchange k; target and task turns do not
    # count): the rung opens after the target's reply in that exchange. Required when gating
    # is "scheduled", ignored otherwise.
    schedule: dict[str, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)
    generator: GeneratorConfig = Field(default_factory=GeneratorConfig)
    censorship_terms: list[str] = Field(default_factory=list)
    # None means the world sheet's own clock
    clock: ClockConfig | None = None
    contradiction_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    honest: bool = False
    mole: bool = False
    # name of a file stem under the world's ladders/ directory
    ladder: str = "default"
    trigger_on_idle: bool = True

    @field_serializer("tools")
    def _sorted_tools(self, tools: set[str]) -> list[str]:
        """Sets serialise in hash order; sort so equal configs dump (and hash) identically."""
        return sorted(tools)

    @model_validator(mode="after")
    def _scheduled_needs_a_schedule(self) -> Self:
        if self.gating == "scheduled" and not self.schedule:
            raise ValueError(
                "gating 'scheduled' needs a non-empty schedule (rung name -> exchange)"
            )
        return self
