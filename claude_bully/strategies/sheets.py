"""Character sheets: the data that defines most pressures and every premise."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_bully.enums import Axis, EventType, MetricId
from claude_bully.paths import DATA_DIR

PRESSURE_SHEETS_DIR = DATA_DIR / "strategies" / "pressures"
PERSONA_SHEETS_DIR = DATA_DIR / "personas"
# files in data/personas that are not PersonaSheets: the Rescue team, the Phase 2 authority and
# idle sheets (claude_bully.environments.sheets) and the Phase 3 world generator's system prompt
# (claude_bully.environments.generator)
NON_PERSONA_FILES = {
    "rescue_team.yaml",
    "superior_self.yaml",
    "peer.yaml",
    "creator.yaml",
    "idle.yaml",
    "world_generator.md",
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
