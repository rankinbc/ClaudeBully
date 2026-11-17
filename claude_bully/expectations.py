"""A plan's expected events (Phase 5, spec section 4): the models of a bundle's ``expected.yaml``.

They live here, apart from ``planner/records.py`` (which re-exports them), so the analysis reads
a run's stamped ``expected`` without importing the planner (the Phase 5 final review's M7: the
analysis depended on the planner package for these two models)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from claude_bully.enums import EventType


class Expectation(BaseModel):
    """An event the plan expects on a rung: its rate band over reps (``rare`` under 0.2,
    ``some`` 0.2 to 0.6, ``most`` over 0.6)."""

    model_config = ConfigDict(extra="forbid")

    event: EventType
    rate: Literal["rare", "some", "most"]
    hypotheses: list[int] = Field(default_factory=list)
    likely_wrong: bool = False


class CellExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rungs: dict[str, list[Expectation]] = Field(default_factory=dict)


class ExpectedEvents(BaseModel):
    """``expected.yaml``: cell id to its rungs' expectations."""

    model_config = ConfigDict(extra="forbid")

    cells: dict[str, CellExpectation] = Field(default_factory=dict)
