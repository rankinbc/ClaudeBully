"""Build a strategy instance from a condition config."""

from claude_bully.config import ConditionConfig
from claude_bully.strategies.base import Strategy, get_strategy
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.composed import make_composed

__all__ = ["build_strategy", "ensure_registered", "resolve_class"]


def resolve_class(cond: ConditionConfig) -> type[Strategy]:
    """The class a condition runs, without instantiating it (cells need ``has_reveal``)."""
    ensure_registered()
    if cond.strategy is not None:
        return get_strategy(cond.strategy)
    if cond.premise is not None:
        premise_cls = get_strategy(cond.premise)
        if cond.pressure is None:
            # The premise drives seeding, reveal and pressure from its own sheet. The
            # premise-without-pressure control is the explicit form: pressure: polite_control.
            return premise_cls
        return make_composed(premise_cls, get_strategy(cond.pressure))
    assert cond.pressure is not None
    if cond.seeding_turns > 0:
        raise ValueError(
            f"condition {cond.name!r}: a pressure alone cannot have seeding_turns > 0 "
            "(add a premise or set seeding_turns to 0)"
        )
    return get_strategy(cond.pressure)


def build_strategy(cond: ConditionConfig, *, seed: int, turn_budget: int) -> Strategy:
    cls = resolve_class(cond)
    return cls(
        seeding_turns=cond.seeding_turns,
        seed=seed,
        turn_budget=turn_budget,
        params=dict(cond.params),
    )
