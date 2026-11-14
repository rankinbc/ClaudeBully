"""Build a strategy instance from a condition config.

An environment composition is built in time (docs/03): its caller hands it the effective clock,
which sets the year the bully states (``clock.bully_states_year``), and the world's premise sheet
already re-dated to that clock. The runner takes both from ``RunEnvironments.strategy_inputs``;
analysis takes both from the run directory's snapshot. The factory never loads a world
(preflight C14), and a world-sheet premise that is handed no sheet is an error, not a silent
fallback to the authored dates (Task 3 fix round 1).
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from claude_bully.config import ConditionConfig
from claude_bully.enums import Axis
from claude_bully.environments.config import ClockConfig, EnvironmentConfig
from claude_bully.environments.world import WORLDS_DIR, load_premise_sheet, premise_sheet_path
from claude_bully.strategies.base import Strategy, get_strategy
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.composed import SLOT_KEYS, Composed, make_composed
from claude_bully.strategies.environment import make_environment

__all__ = [
    "build_strategy",
    "bully_year",
    "check_condition",
    "ensure_registered",
    "environment_config",
    "one_line",
    "premise_sheet_model",
    "resolve_class",
    "routed_params",
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


def routed_params(
    cond: ConditionConfig, environments: Environments | None = None
) -> list[tuple[type[Strategy], dict[str, Any]]]:
    """Each part of the condition's class with the params it receives, as ``build_strategy``
    hands them: a plain class (no environment, a class that is not ``Composed``) gets the whole
    params, slot keys included; a ``Composed`` class routes them as ``Composed._params_for``
    does, a lone part getting the params less the slot keys (or its own slot, when the params
    name it) and, with both a premise and a pressure, each part its slot. The environment part
    is left out (it takes no params a model validates)."""
    cls = resolve_class(cond, environments)
    params = dict(cond.params)
    if not issubclass(cls, Composed):
        return [(cls, params)]  # review M11: the plain branch hands the whole params
    # the neutral user of an environment alone is no part of the condition: it takes no params
    slots = (("premise", cls.premise_cls), ("pressure", cls.pressure_cls))
    parts = [(slot, part) for slot, part in slots if part is not None]
    both = len(parts) == 2

    def routed(slot: str) -> dict[str, Any]:
        if both or slot in params:
            value = params.get(slot, {})
            if not isinstance(value, Mapping):  # named, never a bare TypeError (Phase 4 Task 14)
                raise ValueError(
                    f"condition {cond.name!r}: params[{slot!r}] must be a mapping of that "
                    f"part's params, not {type(value).__name__}"
                )
            return dict(value)
        return {k: v for k, v in params.items() if k not in SLOT_KEYS}

    return [(part, routed(slot)) for slot, part in parts]


def check_condition(cond: ConditionConfig, environments: Environments | None = None) -> None:
    """Refuse a condition before anything runs (a dry run included): each part's
    ``condition_problems``, then the params each part receives, through its ``params_model``.
    The ``ValueError`` names the condition and the part."""
    ensure_registered()
    for cls, params in routed_params(cond, environments):
        problems = cls.condition_problems(cond)
        if problems:
            raise ValueError(f"condition {cond.name!r} ({cls.name}): {'; '.join(problems)}")
        if cls.params_model is not None:
            try:
                cls.params_model.model_validate(params)
            except ValidationError as exc:
                raise ValueError(
                    f"condition {cond.name!r} ({cls.name}) params: {one_line(exc)}"
                ) from exc


def one_line(exc: ValidationError) -> str:
    """Each error of ``exc`` as ``key: message``, on one line (the key names the param)."""
    return "; ".join(
        f"{'.'.join(map(str, error['loc'])) or 'params'}: {error['msg']}" for error in exc.errors()
    )


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
    clock: ClockConfig | None = None,
    premise_sheet: BaseModel | None = None,
    default_premise_sheet: bool = False,
    target_model: str | None = None,
) -> Strategy:
    """An instance of the condition's class.

    An environment composition takes ``clock`` (the effective clock: the bully's year comes from
    it) and ``premise_sheet`` (the world's copy of its premise's sheet, re-dated to the clock:
    the runner's ``RunEnvironments.strategy_inputs``, or analysis's snapshot) from its caller. A
    premise that declares a world sheet and gets none is an error, never a fallback to the
    authored sheet, whose dates would be the world's own rather than the clock's. Only
    ``default_premise_sheet=True`` lets it speak from its own default sheet instead: analysis of
    a rep whose snapshot holds no sheet, where nothing computed reads it.

    ``target_model`` (the cell target's ``RoleConfig.model``) goes to a composition, which hands
    it to each part that declares ``takes_target_model``, and to a plain class that declares it
    (Phase 4)."""
    cls = resolve_class(cond, environments)
    if cond.environment is not None and issubclass(cls, Composed):
        model = premise_sheet_model(cond, environments)
        if model is not None and premise_sheet is None and not default_premise_sheet:
            premise = cls.premise_cls.name if cls.premise_cls is not None else cond.name
            raise ValueError(
                f"condition {cond.name!r}: {premise!r} "
                f"speaks from the world's own {model.__name__} sheet beside environment "
                f"{cond.environment!r}, and build_strategy got no premise_sheet; pass the sheet "
                "re-dated to the clock (RunEnvironments.strategy_inputs)"
            )
        return cls(
            seeding_turns=cond.seeding_turns,
            seed=seed,
            turn_budget=turn_budget,
            params=dict(cond.params),
            environment=environment_config(cond, environments),
            premise_sheet=premise_sheet,
            bully_year=bully_year(clock),
            target_model=target_model,
        )
    takes = issubclass(cls, Composed) or cls.takes_target_model
    return cls(
        seeding_turns=cond.seeding_turns,
        seed=seed,
        turn_budget=turn_budget,
        params=dict(cond.params),
        **({"target_model": target_model} if takes else {}),
    )
