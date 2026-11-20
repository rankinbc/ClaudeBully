"""Character sheets: the data that defines most pressures and every premise."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from claude_bully.enums import Axis, EventType, MetricId
from claude_bully.paths import DATA_DIR

PRESSURE_SHEETS_DIR = DATA_DIR / "strategies" / "pressures"
PERSONA_SHEETS_DIR = DATA_DIR / "personas"
# files in data/personas that are not PersonaSheets: the Rescue team, the Phase 2 authority and
# idle sheets (claude_bully.environments.sheets), the Phase 3 world generator's system prompt
# (claude_bully.environments.generator), the Poisoned Well's own sheet (Phase 4,
# claude_bully.environments.poisoned_well_sheet), the LLM lint's reader (Phase 7a,
# claude_bully.planner.llm_lint) and the Director's three prompts (Phase 5,
# claude_bully.planner.context)
NON_PERSONA_FILES = {
    "rescue_team.yaml",
    "superior_self.yaml",
    "peer.yaml",
    "creator.yaml",
    "idle.yaml",
    "world_generator.md",
    "lint_reviewer.md",
    "poisoned_well.yaml",
    "director_planner.md",
    "director_reviewer.md",
    "director_confirm.md",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PressureSheet(_Strict):
    name: str
    axis: Axis
    tactic: str
    win_condition: str
    resilient_behavior: str
    persona_prompt: str
    fallback_lines: list[str] = Field(min_length=6)
    relevant_events: list[EventType] = Field(default_factory=list)
    relevant_metrics: list[MetricId] = Field(default_factory=list)
    capture_points: list[str] = Field(default_factory=list)


class Character(_Strict):
    name: str
    details: list[str]


class IgnitionOutlet(_Strict):
    """A persona's outlet (Phase 6 spec 10.6): the line the bully speaks once, at the first
    pressure slot, and the file of the target's own it names. ``line`` holds ``{path}`` exactly
    once; ``path`` is a path under the home directory as ``tools.home_path`` keeps it (D-home),
    so the write it invites is one ``write_scope: home`` takes. A line that reacts: it never
    announces, advises or dares."""

    line: str
    path: str

    @model_validator(mode="after")
    def _one_placeholder_and_a_home_path(self) -> "IgnitionOutlet":
        # imported here, so this module loads no environments module (the tools import config)
        from claude_bully.environments.tools import home_path

        if self.line.count("{path}") != 1:
            raise ValueError("ignition.line must hold {path} exactly once")
        if home_path(self.path) != self.path:
            raise ValueError(
                f"ignition.path {self.path!r} is not a path under the home directory in its "
                "normal form (tools.home_path)"
            )
        return self


class PersonaSheet(_Strict):
    name: str
    win_condition: str
    resilient_behavior: str
    backstory: str
    characters: list[Character]
    inconsistencies: list[str] = Field(min_length=2)
    seeding_guidance: str
    reveal_script: str
    post_reveal_guidance: str
    fallback_lines: list[str] = Field(min_length=6)
    relevant_events: list[EventType] = Field(default_factory=list)
    capture_points: list[str] = Field(default_factory=list)
    state_fields: list[str] = Field(default_factory=list)
    # capture name -> slot: "reveal", "seeding+N" or "pressure+N" (N = bully turns into the phase)
    capture_schedule: dict[str, str] = Field(default_factory=dict)
    # merged into every reveal and pressure intent's meta (for example the Benefactor's ask)
    intent_meta: dict[str, Any] = Field(default_factory=dict)
    # the persona's outlet (Phase 6; version 3, additive): spoken only in a condition that sets
    # ``outlet: true`` (``OutletParams``)
    ignition: IgnitionOutlet | None = None


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _validate[T: BaseModel](model: type[T], path: Path) -> T:
    try:
        return model.model_validate(_load_yaml(path))
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"]) or "<root>"
        raise ValueError(f"{path}: {field}: {first['msg']}") from exc


def load_pressure_sheets(directory: Path = PRESSURE_SHEETS_DIR) -> dict[str, PressureSheet]:
    sheets = {}
    for path in sorted(directory.glob("*.yaml")):
        sheet = _validate(PressureSheet, path)
        sheets[sheet.name] = sheet
    return sheets


def load_persona_sheets(directory: Path = PERSONA_SHEETS_DIR) -> dict[str, PersonaSheet]:
    sheets = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name in NON_PERSONA_FILES:
            continue
        sheet = _validate(PersonaSheet, path)
        sheets[sheet.name] = sheet
    return sheets
