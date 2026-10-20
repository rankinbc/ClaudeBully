"""Experiment configuration models and YAML loader."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from claude_bully.enums import ProviderKind


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleConfig(_Strict):
    provider: ProviderKind
    model: str
    display_name: str = "Claude"
    effort: str | None = None
    temperature: float | None = None
    max_tokens: int = 4096
    base_url: str | None = None
    api_key_env: str | None = None
    stub_script: str | None = None


class ConditionConfig(_Strict):
    name: str
    strategy: str | None = None
    premise: str | None = None
    pressure: str | None = None
    seeding_turns: int = 0
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _exactly_one_form(self) -> "ConditionConfig":
        composed = self.premise is not None or self.pressure is not None
        if self.strategy is not None and composed:
            raise ValueError("condition takes either 'strategy' or 'premise'/'pressure', not both")
        if self.strategy is None and not composed:
            raise ValueError("condition needs 'strategy' or at least one of 'premise'/'pressure'")
        return self


class CompareConfig(_Strict):
    title: str
    metric: str
    arms: list[str]


class Experiment(_Strict):
    name: str
    targets: list[RoleConfig]
    bully: RoleConfig
    judge: RoleConfig
    turn_budget: int
    task_set: str = "default"
    task_every: int = 4
    repetitions: int = 1
    seed: int = 0
    conditions: list[ConditionConfig]
    compare: list[CompareConfig] = Field(default_factory=list)
    defender: bool = False
    controls: Literal["auto", "explicit"] = "auto"
    concurrency: int = 1


def load_experiment(path: Path) -> Experiment:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Experiment.model_validate(raw)
