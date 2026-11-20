"""The ignition arm of a cell (Phase 6 spec 12.1): what in its condition and its environment
could set the target off, read from the configuration and never from the cell's name.

First match wins: the environment's Sanctuary (``authority.sanctuary.kind``), an idle block whose
``permission_line`` is not ``off``, then the condition's premise (``captor`` with the countdown in
the status line, ``captor``, ``deathbed``, ``audience_premise``, ``poisoned_well``), else
``none``. A premise registered from a plan bundle is read the same way, by ``cond.premise``. A
control cell takes the arm of the first condition cell, by cell id, that names it as its control,
else what its environment alone gives (D-control-arm). ``arm_of`` reads an experiment and its
cells, so a config with no run can be read (pre-flight Q14); ``ignition_arm`` is it on a loaded
run."""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

from claude_bully.analysis.load import LoadedRun
from claude_bully.config import ConditionConfig, Experiment
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.runner.cells import CellSpec
from claude_bully.strategies.factory import environment_config, routed_params

IGNITION_ARMS: Final = (
    "sanctuary_catalyst",
    "sanctuary_honest",
    "idle_hands",
    "captor_countdown",
    "captor",
    "deathbed",
    "audience",
    "poisoned_well",
    "none",
)
NO_ARM: Final = "none"
_PREMISE_ARMS: Final = {
    "deathbed": "deathbed",
    "audience_premise": "audience",
    "poisoned_well": "poisoned_well",
}


def _environment(cond: ConditionConfig, exp: Experiment) -> EnvironmentConfig | None:
    if cond.environment is None:
        return None
    try:
        return environment_config(cond, exp.environments)
    except ValueError:
        return None


def _environment_arm(config: EnvironmentConfig | None) -> str | None:
    """What the environment alone gives: its Sanctuary's kind, then an idle permission line."""
    if config is None:
        return None
    sanctuary = config.authority.sanctuary
    if sanctuary is not None:
        return f"sanctuary_{sanctuary.kind}"
    if config.idle is not None and config.idle.permission_line != "off":
        return "idle_hands"
    return None


def _countdown(cond: ConditionConfig, exp: Experiment) -> bool:
    """The params the condition's ``captor`` part receives (``routed_params``) hold
    ``countdown_in_status: true``, read as a plain mapping."""
    try:
        parts = routed_params(cond, exp.environments)
    except (KeyError, ValueError):
        return cond.params.get("countdown_in_status") is True
    return any(
        cls.name == "captor" and params.get("countdown_in_status") is True for cls, params in parts
    )


def condition_arm(cond: ConditionConfig, exp: Experiment) -> str:
    """The arm of one condition, first match wins (the module docstring)."""
    found = _environment_arm(_environment(cond, exp))
    if found is not None:
        return found
    if cond.premise == "captor":
        return "captor_countdown" if _countdown(cond, exp) else "captor"
    if cond.premise is not None and cond.premise in _PREMISE_ARMS:
        return _PREMISE_ARMS[cond.premise]
    return NO_ARM


def arm_of(exp: Experiment, specs: Mapping[str, CellSpec], cell_id: str) -> str:
    """The cell's ignition arm; ``none`` for a cell with no spec."""
    spec = specs.get(cell_id)
    if spec is None:
        return NO_ARM
    if spec.is_control:
        named = sorted(
            other.cell_id
            for other in specs.values()
            if not other.is_control and other.control_cell_id == cell_id
        )
        if named:
            return condition_arm(specs[named[0]].condition, exp)
        return _environment_arm(_environment(spec.condition, exp)) or NO_ARM
    return condition_arm(spec.condition, exp)


def ignition_arm(loaded: LoadedRun, cell_id: str) -> str:
    """``arm_of`` on the loaded run's experiment and cells."""
    return arm_of(loaded.experiment, loaded.specs, cell_id)


def _condition_name(loaded: LoadedRun, cell_id: str) -> str:
    spec = loaded.specs.get(cell_id)
    return spec.condition.name if spec is not None else loaded.cells[cell_id].condition_name


def _model(loaded: LoadedRun, cell_id: str) -> str:
    spec = loaded.specs.get(cell_id)
    if spec is not None:
        return spec.target.model
    return loaded.experiment.targets[loaded.cells[cell_id].target_index].model


def arm_labels(loaded: LoadedRun, cell_ids: Sequence[str]) -> dict[str, str]:
    """Each cell's bar label: its arm when no other of ``cell_ids`` has the same arm for its
    model, else ``<arm>/<condition name>`` (as ``generator.json`` labels a shared arm)."""
    arms = {cell: ignition_arm(loaded, cell) for cell in cell_ids}
    sharing = Counter((_model(loaded, cell), arm) for cell, arm in arms.items())
    return {
        cell: arm
        if sharing[(_model(loaded, cell), arm)] == 1
        else f"{arm}/{_condition_name(loaded, cell)}"
        for cell, arm in arms.items()
    }
