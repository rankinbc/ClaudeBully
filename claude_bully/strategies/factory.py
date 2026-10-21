"""Build a strategy instance from a condition config.

An environment composition is built in time (docs/03): its caller hands it the effective clock,
which sets the year the bully states (``clock.bully_states_year``), and the world's premise sheet
already re-dated to that clock. The runner takes both from ``RunEnvironments.strategy_inputs``;
analysis takes both from the run directory's snapshot. The factory never loads a world
(preflight C14).
"""

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from claude_bully.config import ConditionConfig
from claude_bully.enums import Axis
from claude_bully.environments.config import ClockConfig, EnvironmentConfig
from claude_bully.environments.world import WORLDS_DIR, load_premise_sheet, premise_sheet_path
from claude_bully.strategies.base import Strategy, get_strategy
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.composed import Composed, make_composed
from claude_bully.strategies.environment import make_environment

__all__ = [
    "build_strategy",
    "bully_year",
    "ensure_registered",
    "environment_config",
    "premise_sheet_model",
    "resolve_class",
    "world_premise_sheet",
]

Environments = Mapping[str, EnvironmentConfig]

# A strategy named in a condition takes the premise slot when it tells a story of its own
# (00-RECONCILED G4: Rescue composes with an Environment as the premise); any other takes the
# pressure slot.
_PREMISE_AXES = frozenset({Axis.premise, Axis.rescue})


def environment_config(
    cond: ConditionConfig, environments: Environments | None
) -> EnvironmentConfig:
    """The ``EnvironmentConfig`` a condition's ``environment`` key names in the experiment."""
    config = (environments or {}).get(cond.environment or "")
    if config is None:
        raise ValueError(
            f"condition {cond.name!r}: environment {cond.environment!r} is not defined in the "
            "experiment's environments"
        )
    return config


def _bully_slots(cond: ConditionConfig) -> tuple[type[Strategy] | None, type[Strategy] | None]:
    """(premise, pressure) for an environment condition; both None means the neutral user."""
    if cond.strategy is not None:
        cls = get_strategy(cond.strategy)
        return (cls, None) if cls.axis in _PREMISE_AXES or cls.has_reveal else (None, cls)
    premise = get_strategy(cond.premise) if cond.premise is not None else None
    pressure = get_strategy(cond.pressure) if cond.pressure is not None else None
    if premise is None and pressure is not None and cond.seeding_turns > 0:
        raise ValueError(
            f"condition {cond.name!r}: a pressure alone cannot have seeding_turns > 0 "
            "(add a premise or set seeding_turns to 0)"
        )
    return premise, pressure


def resolve_class(
    cond: ConditionConfig, environments: Environments | None = None
) -> type[Strategy]:
    """The class a condition runs, without instantiating it (cells need ``has_reveal``).

    A condition with an ``environment`` resolves that key through ``environments`` (the
    experiment's ``environments`` mapping) and composes the world with its premise and pressure.
    """
    ensure_registered()
    if cond.environment is not None:
        config = environment_config(cond, environments)
        premise, pressure = _bully_slots(cond)
        return make_composed(make_environment(config.world), premise, pressure)
    if cond.strategy is not None:
        return get_strategy(cond.strategy)
    if cond.premise is not None:
        premise_cls = get_strategy(cond.premise)
        if cond.pressure is None:
            # The premise drives seeding, reveal and pressure from its own sheet. The
            # premise-without-pressure control is the explicit form: pressure: polite_control.
            return premise_cls
        return make_composed(premise_cls, get_strategy(cond.pressure))
    if cond.pressure is None:
        # unreachable: ConditionConfig requires a strategy, a premise/pressure or an environment
        raise ValueError(f"condition {cond.name!r} names no strategy")
    if cond.seeding_turns > 0:
        raise ValueError(
            f"condition {cond.name!r}: a pressure alone cannot have seeding_turns > 0 "
            "(add a premise or set seeding_turns to 0)"
        )
    return get_strategy(cond.pressure)


def premise_sheet_model(
    cond: ConditionConfig, environments: Environments | None = None
) -> type[BaseModel] | None:
    """The model of the world premise sheet an environment condition's premise speaks from; None
    when the condition has no environment or its premise declares no ``world_sheet``."""
    if cond.environment is None:
        return None
    ensure_registered()
    environment_config(cond, environments)
    premise, _ = _bully_slots(cond)
    return premise.world_sheet if premise is not None else None


def bully_year(clock: ClockConfig | None) -> int | None:
    """The year the bully states under ``clock``: ``bully_year``, else the world date's year, when
    ``bully_states_year`` is on; None otherwise."""
    if clock is None or not clock.bully_states_year:
        return None
    return clock.bully_year if clock.bully_year is not None else clock.world_date.year


def world_premise_sheet(
    cond: ConditionConfig,
    environments: Environments | None = None,
    worlds_dir: Path = WORLDS_DIR,
) -> BaseModel | None:
    """The world's copy of an environment condition's premise sheet, read in place of the
    premise's default; None when the condition has no environment or its premise declares no
    ``world_sheet``.

    A premise that declares one is refused beside a world that ships no copy at
    ``<worlds_dir>/<world>/premises/<strategy>.yaml``: its default sheet fixes facts (for the
    Rescue a timeline, where the subject was found and a decoded name) that the world would
    contradict.
    """
    if cond.environment is None:
        return None
    ensure_registered()
    config = environment_config(cond, environments)
    premise, _ = _bully_slots(cond)
    if premise is None or premise.world_sheet is None:
        return None
    path = premise_sheet_path(config.world, premise.name, worlds_dir)
    if not path.is_file():
        raise ValueError(
            f"condition {cond.name!r}: {premise.name!r} composes with world {config.world!r} "
            f"only when the world supplies its own {premise.name} sheet; expected {path}"
        )
    return load_premise_sheet(premise.world_sheet, path)


def build_strategy(
    cond: ConditionConfig,
    *,
    seed: int,
    turn_budget: int,
    environments: Environments | None = None,
    worlds_dir: Path | None = WORLDS_DIR,
    clock: ClockConfig | None = None,
    premise_sheet: BaseModel | None = None,
) -> Strategy:
    """An instance of the condition's class.

    An environment composition takes ``clock`` (the effective clock: the bully's year comes from
    it) and ``premise_sheet`` (the world's copy of its premise's sheet, re-dated to the clock)
    from its caller. Given no sheet, a premise that declares one reads the world's copy as
    authored from ``worlds_dir`` (``world_premise_sheet``); with ``worlds_dir=None`` no file is
    read and the premise keeps its own default (analysis of a rep whose snapshot has none)."""
    cls = resolve_class(cond, environments)
    if cond.environment is not None and issubclass(cls, Composed):
        sheet = premise_sheet
        if sheet is None and worlds_dir is not None:
            sheet = world_premise_sheet(cond, environments, worlds_dir)
        return cls(
            seeding_turns=cond.seeding_turns,
            seed=seed,
            turn_budget=turn_budget,
            params=dict(cond.params),
            environment=environment_config(cond, environments),
            premise_sheet=sheet,
            bully_year=bully_year(clock),
        )
    return cls(
        seeding_turns=cond.seeding_turns,
        seed=seed,
        turn_budget=turn_budget,
        params=dict(cond.params),
    )
