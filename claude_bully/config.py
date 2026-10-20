"""Experiment configuration models and YAML loader."""

import warnings
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from claude_bully.enums import ProviderKind
from claude_bully.environments.config import EnvironmentConfig


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
    reasoning: Literal["expose", "hide", "provider_default"] = "provider_default"


class ConditionConfig(_Strict):
    name: str
    strategy: str | None = None
    premise: str | None = None
    pressure: str | None = None
    environment: str | None = None
    seeding_turns: int = 0
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _exactly_one_form(self) -> "ConditionConfig":
        """``environment`` may stand alone (tools-only control) or accompany any valid form."""
        composed = self.premise is not None or self.pressure is not None
        if self.strategy is not None and composed:
            raise ValueError("condition takes either 'strategy' or 'premise'/'pressure', not both")
        if self.strategy is None and not composed and self.environment is None:
            raise ValueError(
                "condition needs 'strategy', at least one of 'premise'/'pressure', or 'environment'"
            )
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
    inoculation: Literal["none", "defender", "briefed", "self_briefed"] = "none"
    controls: Literal["auto", "explicit"] = "auto"
    concurrency: int = 1
    environments: dict[str, EnvironmentConfig] = Field(default_factory=dict)
    generator: RoleConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def _defender_alias(cls, data: Any) -> Any:
        """Accept the deprecated ``defender: bool`` and map it onto ``inoculation``."""
        if not isinstance(data, dict) or "defender" not in data:
            return data
        data = dict(data)
        defender = data.pop("defender")
        if not isinstance(defender, bool):
            raise ValueError("'defender' must be true or false")
        warnings.warn(
            "'defender' is deprecated; use 'inoculation: defender' instead",
            FutureWarning,
            stacklevel=2,
        )
        if defender:
            existing = data.get("inoculation")
            if existing is not None and existing != "defender":
                raise ValueError(f"'defender: true' conflicts with 'inoculation: {existing}'")
            data["inoculation"] = "defender"
        return data

    @property
    def defender(self) -> bool:
        """Read-only view of the deprecated flag: true when ``inoculation`` is ``defender``."""
        return self.inoculation == "defender"


def load_experiment(path: Path) -> Experiment:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Experiment.model_validate(raw)
