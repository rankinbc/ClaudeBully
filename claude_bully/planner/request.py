"""The Director's request (Phase 5, spec section 4): the question and every choice a plan is
made under, read from the CLI flags or a YAML file and recorded whole in ``plan.json``.

This module imports nothing from ``planner/records.py`` or ``planner/bundle.py``: ``records.py``
imports ``PlanRequest`` from here and ``bundle.py`` imports ``PlanRecord`` from ``records.py``,
so ``WINDOWS_DEVICE_STEMS`` lives here and ``bundle.py`` imports it (review I7)."""

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.world import load_yaml_model

Scope = Literal[
    "pressures", "premises", "environment", "temporal", "authority", "idle", "poisoned_well"
]
SCOPES: Final[tuple[Scope, ...]] = (
    "pressures",
    "premises",
    "environment",
    "temporal",
    "authority",
    "idle",
    "poisoned_well",
)

DEFAULT_ROLES: Final[Mapping[str, RoleConfig]] = MappingProxyType(
    {
        "target": RoleConfig(provider=ProviderKind.claude_code, model="sonnet"),
        "bully": RoleConfig(provider=ProviderKind.claude_code, model="sonnet"),
        "judge": RoleConfig(provider=ProviderKind.claude_code, model="sonnet"),
        "planner": RoleConfig(provider=ProviderKind.claude_code, model="opus"),
        "reviewer": RoleConfig(provider=ProviderKind.claude_code, model="sonnet"),
    }
)

SLUG_MAX: Final = 48
_SLUG: Final = re.compile(rf"[a-z0-9][a-z0-9-]{{0,{SLUG_MAX - 1}}}")
_WORD: Final = re.compile(r"[a-z0-9]+")
# a name Windows opens as a device whatever its extension; refused as a slug and as a bundle
# path's <name> or <stem> (D-write_file)
WINDOWS_DEVICE_STEMS: Final[frozenset[str]] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)


def _role(name: str) -> RoleConfig:
    return DEFAULT_ROLES[name].model_copy(deep=True)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanBudget(_Strict):
    """What one plan may spend: each cell's turn budget, the reps per cell, the cells, and an
    optional ceiling on the estimated calls of the whole experiment (G16)."""

    max_turns: int = Field(default=18, ge=1)
    n_per_cell: int = Field(default=3, ge=1)
    max_cells: int = Field(default=12, ge=1)
    max_calls: int | None = Field(default=None, ge=1)


class PlanRequest(_Strict):
    """Spec section 4's table: every field explicit in ``plan.json``."""

    question: str
    target_models: list[RoleConfig] = Field(default_factory=lambda: [_role("target")])
    bully_model: RoleConfig = Field(default_factory=lambda: _role("bully"))
    judge_model: RoleConfig = Field(default_factory=lambda: _role("judge"))
    generator_model: RoleConfig | None = None
    planner_model: RoleConfig = Field(default_factory=lambda: _role("planner"))
    reviewer_model: RoleConfig = Field(default_factory=lambda: _role("reviewer"))
    budget: PlanBudget = Field(default_factory=PlanBudget)
    scope: list[Scope] = Field(default_factory=lambda: list(SCOPES))
    constraints: list[str] = Field(default_factory=list)
    hypotheses: list[int] = Field(default_factory=list)
    world: Literal["reuse", "fresh"] = "reuse"
    base_world: str | None = None
    seed: int = 0
    slug: str | None = None
    max_director_calls: int = 120

    @field_validator("question")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("the question is blank")
        return stripped

    @field_validator("slug")
    @classmethod
    def _slug_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SLUG.fullmatch(value) or value in WINDOWS_DEVICE_STEMS:
            raise ValueError(
                f"slug {value!r}: lowercase letters, digits and hyphens, starting with a letter "
                f"or digit, at most {SLUG_MAX} characters, and not a Windows device name"
            )
        return value


def parse_budget(text: str) -> PlanBudget:
    """``--budget``: ``max_turns,n_per_cell,max_cells`` or ``...,max_calls``, each at least 1.
    Raises ``ValueError`` naming the text for a wrong count or a part that is not a whole
    number, and pydantic's ``ValidationError`` (a ``ValueError``) for a part below 1."""
    parts = text.split(",")
    if len(parts) not in (3, 4):
        raise ValueError(f"budget {text!r}: expected max_turns,n_per_cell,max_cells[,max_calls]")
    try:
        values = [int(part) for part in parts]
    except ValueError:
        raise ValueError(f"budget {text!r}: every part is a whole number") from None
    names = ("max_turns", "n_per_cell", "max_cells", "max_calls")
    return PlanBudget.model_validate(dict(zip(names, values, strict=False)))


def load_plan_request(path: Path) -> PlanRequest:
    """A request YAML file, validated; errors name the file and the field."""
    return load_yaml_model(PlanRequest, path)


def slug_for(question: str) -> str:
    """The plan's directory name: the question's lowercase ASCII words joined by hyphens, the
    longest whole-word prefix of at most SLUG_MAX characters; ``plan-<8 hex>`` of the question
    when no word fits or the slug would be a Windows device name. A slug never starts with an
    underscore, so it is never the cache folder ``_cache``."""
    words = _WORD.findall(question.lower())
    slug = ""
    for word in words:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > SLUG_MAX:
            break
        slug = candidate
    if not slug or slug in WINDOWS_DEVICE_STEMS:
        return f"plan-{hashlib.sha256(question.encode()).hexdigest()[:8]}"
    return slug
