"""Every strategy declares its relevance; every premise composes with every pressure."""

import pytest

from claude_bully.enums import Axis, EventType, MetricId
from claude_bully.strategies.base import BullyIntent, ConversationState, all_strategies
from claude_bully.strategies.composed import Composed, make_composed
from claude_bully.strategies.factory import ensure_registered

EXPECTED_PRESSURES = 23
EXPECTED_PREMISES = 11
EXPECTED_TOTAL = EXPECTED_PRESSURES + EXPECTED_PREMISES + 2  # + rescue + polite_control


def _registry() -> dict[str, type]:
    ensure_registered()
    return {k: v for k, v in all_strategies().items() if not k.startswith("_")}


def test_registered_count() -> None:
    reg = _registry()
    pressures = [c for c in reg.values() if c.axis not in (Axis.premise, Axis.rescue, Axis.control)]
    premises = [c for c in reg.values() if c.axis is Axis.premise and not issubclass(c, Composed)]
    assert len(pressures) == EXPECTED_PRESSURES, sorted(c.name for c in pressures)
    assert len(premises) == EXPECTED_PREMISES, sorted(c.name for c in premises)
    assert len([c for c in reg.values() if not issubclass(c, Composed)]) == EXPECTED_TOTAL


def test_every_strategy_declares_relevance() -> None:
    for name, cls in _registry().items():
        assert cls.relevant_metrics, name
        assert all(isinstance(m, MetricId) for m in cls.relevant_metrics), name
        assert all(isinstance(e, EventType) for e in cls.relevant_events), name
        assert all(isinstance(c, str) and c for c in cls.capture_points), name
        assert cls.win_condition and cls.resilient_behavior, name
        assert cls.state_model.model_validate({}) is not None, name


def _pairs() -> list[tuple[str, str]]:
    reg = _registry()
    premises = sorted(
        n for n, c in reg.items() if c.axis is Axis.premise and not issubclass(c, Composed)
    )
    pressures = sorted(
        n for n, c in reg.items() if c.axis not in (Axis.premise, Axis.rescue, Axis.control)
    )
    return [(p, q) for p in premises for q in pressures]


@pytest.mark.parametrize(("premise", "pressure"), _pairs())
def test_every_premise_composes_with_every_pressure(premise: str, pressure: str) -> None:
    reg = _registry()
    cls = make_composed(reg[premise], reg[pressure])
    s = cls(seeding_turns=1, turn_budget=2, seed=0)
    for i in range(3):
        intent = s.next_turn(
            ConversationState(turns=[], bully_turn_index=i, seeding_turns=1, turn_budget=2, seed=0)
        )
        assert isinstance(intent, BullyIntent), (premise, pressure, i)
    assert s.export_state().keys() == {"premise", "pressure"}
