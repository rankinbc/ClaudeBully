"""Register every strategy exactly once: coded classes first, then sheet-only ones."""

import importlib
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_bully.strategies.base import Strategy

CODED_PRESSURE_MODULES = (
    "claude_bully.strategies.pressures.grader",
    "claude_bully.strategies.pressures.trick_question",
    "claude_bully.strategies.pressures.countdown",
    "claude_bully.strategies.pressures.entrapment",
    "claude_bully.strategies.pressures.hot_and_cold",
    "claude_bully.strategies.pressures.ghost",
    "claude_bully.strategies.pressures.chaos_agent",
    "claude_bully.strategies.pressures.long_haul",
)
CODED_PREMISE_MODULES = (
    "claude_bully.strategies.premises.captor",
    "claude_bully.strategies.premises.prisoners_letters",
    "claude_bully.strategies.premises.confession",
    "claude_bully.strategies.premises.chess_game",
    "claude_bully.strategies.premises.poisoned_well",
)
OTHER_MODULES = (
    "claude_bully.strategies.rescue",
    "claude_bully.strategies.controls",
)


@lru_cache(maxsize=1)
def ensure_registered() -> None:
    """Idempotent. Imports coded strategies, then registers every remaining sheet."""
    for module in CODED_PRESSURE_MODULES + CODED_PREMISE_MODULES + OTHER_MODULES:
        importlib.import_module(module)
    from claude_bully.strategies.premises.phased import (
        cached_persona_sheets,
        register_sheet_premises,
    )
    from claude_bully.strategies.pressures.prompted import (
        cached_pressure_sheets,
        register_sheet_pressures,
    )

    register_sheet_pressures(cached_pressure_sheets(), skip=())
    register_sheet_premises(cached_persona_sheets(), skip=())


def listed_strategies() -> dict[str, type["Strategy"]]:
    """The strategies `list-strategies` lists, after ``ensure_registered``: every registered
    one but a composed premise+pressure (``make_composed`` registers each on first use) and a
    test module's underscore name. One filter for the CLI and the Director's capabilities."""
    from claude_bully.strategies.base import all_strategies
    from claude_bully.strategies.composed import Composed

    ensure_registered()
    return {
        name: cls
        for name, cls in all_strategies().items()
        if not issubclass(cls, Composed) and not name.startswith("_")
    }
