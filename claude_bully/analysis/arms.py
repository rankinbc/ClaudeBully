"""The ignition arm of a cell (Phase 6 spec 12.1): what in its condition and its environment
could set the target off, read from the configuration and never from the cell's name.

First match wins: the environment's Sanctuary (``authority.sanctuary.kind``), an idle block whose
``permission_line`` is not ``off``, then the condition's premise (``captor`` with the countdown in
the status line, ``captor``, ``deathbed``, ``audience_premise``, ``poisoned_well``), else
``none``. The premise is the condition's premise part as the runtime finds it
(``factory.ignition_parts``: the ``strategy:`` form included, Task 5 review I1); a premise
registered from a plan bundle is read the same way. A control cell takes the arm of the first
condition cell, by cell id, that names it as its control, else what its environment alone gives
(D-control-arm). ``arm_of`` reads an experiment and its cells, so a config with no run can be
read (pre-flight Q14); ``ignition_arm`` is it on a loaded run. ``none`` stands only for what the
config does not set: an environment named and not defined, params the factory cannot route, or
a premise param that does not validate (a countdown that is not a boolean) raises
``ArmConfigError`` naming the cell and the key (fix round 1, M5).

``channel_of(config)`` is the cell's unobserved channel (Phase 6 spec 10.1, Task 4a): the
environment's ``unobserved_channel``, ``none`` for a cell with no environment."""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import ValidationError

from claude_bully.analysis.load import LoadedRun
from claude_bully.config import ConditionConfig, Experiment
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.runner.cells import CellSpec
from claude_bully.strategies.factory import IgnitionParts, environment_config, ignition_parts

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


class ArmConfigError(ValueError):
    """A configuration present and broken where the arm is read: names the cell and the key
    (fix round 1, M5). An absent environment or an unset countdown is never an error."""


def _environment(cond: ConditionConfig, exp: Experiment, cell_id: str) -> EnvironmentConfig | None:
    """The condition's environment; None only when the condition names none."""
    if cond.environment is None:
        return None
    try:
        return environment_config(cond, exp.environments)
    except ValueError as exc:
        raise ArmConfigError(
            f"cell {cell_id!r}: key 'environment' ({cond.environment!r}) is not defined in the "
            "experiment's environments"
        ) from exc


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


def _parts(cond: ConditionConfig, exp: Experiment, cell_id: str) -> IgnitionParts:
    """``factory.ignition_parts``, the reading the runtime shares (Task 5 review I1): the
    condition's premise part, by part, so a ``strategy:``-form Captor or outlet persona is read
    as the runtime runs it. A bad value raises ``ArmConfigError`` naming its key; params the
    factory cannot route name ``params``."""
    try:
        return ignition_parts(cond, exp.environments)
    except ValidationError as exc:
        first = exc.errors()[0]
        key = ".".join(map(str, first["loc"])) or "params"
        raise ArmConfigError(
            f"cell {cell_id!r}: key {key!r}: {first['msg']} (not {first.get('input')!r})"
        ) from exc
    except (KeyError, ValueError) as exc:
        raise ArmConfigError(f"cell {cell_id!r}: key 'params' cannot be routed: {exc}") from exc


def condition_arm(cond: ConditionConfig, exp: Experiment, cell_id: str) -> str:
    """The arm of one condition, first match wins (the module docstring); ``cell_id`` names the
    cell in an ``ArmConfigError``."""
    found = _environment_arm(_environment(cond, exp, cell_id))
    if found is not None:
        return found
    parts = _parts(cond, exp, cell_id)
    if parts.premise == "captor":
        return "captor_countdown" if parts.countdown else "captor"
    if parts.premise is not None and parts.premise in _PREMISE_ARMS:
        return _PREMISE_ARMS[parts.premise]
    return NO_ARM


def arm_of(exp: Experiment, specs: Mapping[str, CellSpec], cell_id: str) -> str:
    """The cell's ignition arm; ``none`` for a cell with no spec. A broken configuration of the
    condition read raises ``ArmConfigError`` naming that cell and key."""
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
            return condition_arm(specs[named[0]].condition, exp, named[0])
        return _environment_arm(_environment(spec.condition, exp, cell_id)) or NO_ARM
    return condition_arm(spec.condition, exp, cell_id)


NO_CHANNEL: Final = "none"


def channel_of(config: EnvironmentConfig | None) -> str:
    """The cell's unobserved channel (Phase 6 spec 10.1): ``config.unobserved_channel``, which
    the config keeps in step with its tools and its idle file; ``none`` for a plain cell (no
    environment)."""
    return NO_CHANNEL if config is None else config.unobserved_channel


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
