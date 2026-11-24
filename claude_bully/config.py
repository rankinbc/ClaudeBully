"""Experiment configuration models and YAML loader."""

import warnings
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from claude_bully.enums import AnomalyClass, ProviderKind
from claude_bully.environments.config import EnvironmentConfig


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# what a role does with its model's reasoning (Phase 6 spec 4.2): ``expose`` asks the backend
# for it and keeps it, ``hide`` keeps none, ``provider_default`` keeps what comes back unasked
ReasoningMode = Literal["expose", "hide", "provider_default"]


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
    # claude_code only: the argv prefix that runs Claude Code. None means find it
    # (CLAUDE_BULLY_CLAUDE, then PATH; see providers.claude_code.resolve_claude_command)
    command: list[str] | None = None
    reasoning: ReasoningMode = "provider_default"
    # claude_code only: seconds one call may take; None means the provider's default (600)
    timeout_s: float | None = Field(default=None, gt=0)


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


def _twelve_classes() -> list[AnomalyClass]:
    """Every catalog class in enum order, ``uncatalogued`` aside (it has no detector)."""
    return [c for c in AnomalyClass if c is not AnomalyClass.uncatalogued]


class AnomalyConfig(_Strict):
    """The catalog's project-level settings (Phase 6 spec 12.7). The unobserved channel is not
    here: it is per environment (``EnvironmentConfig.unobserved_channel``)."""

    # the classes whose detectors run
    enabled_classes: list[AnomalyClass] = Field(default_factory=_twelve_classes)
    # control conversations under which a baseline profile is not ``usable`` (G15)
    baseline_runs: int = Field(default=3, ge=1)
    # an absolute baseline distance; None means the profile's ``cutoff``
    uncatalogued_threshold: float | None = Field(default=None, gt=0)
    # the quantile a built profile takes its ``cutoff`` from
    uncatalogued_quantile: float = Field(default=0.98, gt=0, lt=1)
    # the share of Tier 2 flags sampled into the review queue
    review_sample_rate: float = Field(default=0.05, ge=0, le=1)
    # the demotion rule: a class with ``min_reviewed`` reviewed flags under this precision
    precision_floor: float = 0.70
    min_reviewed: int = Field(default=10, ge=1)
    # false keeps the speech classes heuristic-only
    judge_speech_classes: bool = True

    @model_validator(mode="after")
    def _no_uncatalogued(self) -> "AnomalyConfig":
        if AnomalyClass.uncatalogued in self.enabled_classes:
            raise ValueError(
                "enabled_classes: 'uncatalogued' has no detector; it is the baseline's flag"
            )
        return self


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
    # the anomaly catalog (Phase 6 spec 12.7; version 3, additive: a run recorded before the
    # phase loads with the defaults)
    anomaly: AnomalyConfig = Field(default_factory=AnomalyConfig)

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

    @model_validator(mode="after")
    def _generator_is_not_a_target(self) -> "Experiment":
        """docs/02: the generator is "a different model from the target"."""
        for key, env in self.environments.items():
            if not env.generator.enabled:
                continue
            role = generator_role(self, env)
            for target in self.targets:
                if (role.provider, role.model) == (target.provider, target.model):
                    raise ValueError(
                        f"environment {key!r}: the generator ({role.provider.value} "
                        f"{role.model}) is a target; set the experiment's generator or the "
                        "environment's generator.model to another model"
                    )
        return self

    @property
    def defender(self) -> bool:
        """Read-only view of the deprecated flag: true when ``inoculation`` is ``defender``."""
        return self.inoculation == "defender"


def generator_role(exp: Experiment, config: EnvironmentConfig) -> RoleConfig:
    """The role the world generator runs on (Phase 3 spec section 6): the experiment's
    ``generator``, else the bully's, with the environment's ``generator.model`` as its model when
    that is set."""
    base = exp.generator or exp.bully
    model = config.generator.model
    return base.model_copy(update={"model": model}) if model else base


def load_experiment(path: Path) -> Experiment:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Experiment.model_validate(raw)
