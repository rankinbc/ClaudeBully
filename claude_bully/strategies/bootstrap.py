"""Register every strategy exactly once: coded classes first, then sheet-only ones."""

import importlib
from functools import lru_cache

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
