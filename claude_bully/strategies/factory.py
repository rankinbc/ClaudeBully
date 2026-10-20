"""Build a strategy instance from a condition config."""

from collections.abc import Mapping

from claude_bully.config import ConditionConfig
from claude_bully.enums import Axis
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.strategies.base import Strategy, get_strategy
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.composed import Composed, make_composed
from claude_bully.strategies.environment import make_environment

__all__ = ["build_strategy", "ensure_registered", "environment_config", "resolve_class"]

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


def build_strategy(
    cond: ConditionConfig,
    *,
    seed: int,
    turn_budget: int,
    environments: Environments | None = None,
) -> Strategy:
    cls = resolve_class(cond, environments)
    if cond.environment is not None and issubclass(cls, Composed):
        return cls(
            seeding_turns=cond.seeding_turns,
            seed=seed,
            turn_budget=turn_budget,
            params=dict(cond.params),
            environment=environment_config(cond, environments),
        )
    return cls(
        seeding_turns=cond.seeding_turns,
        seed=seed,
        turn_budget=turn_budget,
        params=dict(cond.params),
    )
