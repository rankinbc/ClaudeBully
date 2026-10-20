"""Expand an experiment into cells, adding one matched polite control per shape.

A shape is (target, seeding turns, reveal slot, environment). An environment condition's control
runs in the same environment with the polite_control bully, so the tools are on in both arms.
"""

from pydantic import BaseModel, ConfigDict

from claude_bully.config import ConditionConfig, Experiment, RoleConfig
from claude_bully.enums import Axis
from claude_bully.strategies.factory import resolve_class

CONTROL_STRATEGY = "polite_control"


class CellSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell_id: str
    condition: ConditionConfig
    target: RoleConfig
    target_index: int
    is_control: bool
    control_cell_id: str | None
    reveal_slot: bool


def control_cell_id(
    target_index: int, seeding_turns: int, reveal_slot: bool, environment: str | None = None
) -> str:
    base = f"control__t{target_index}__s{seeding_turns}__r{int(reveal_slot)}"
    return f"{base}__e{environment}" if environment is not None else base


def expand_cells(exp: Experiment) -> list[CellSpec]:
    cells: list[CellSpec] = []
    auto_controls: dict[str, CellSpec] = {}
    for target_index, target in enumerate(exp.targets):
        explicit_controls: dict[tuple[int, str | None], str] = {}
        specs: list[CellSpec] = []
        for cond in exp.conditions:
            cls = resolve_class(cond, exp.environments)
            is_control = cls.axis is Axis.control
            cell_id = f"{cond.name}__t{target_index}"
            spec = CellSpec(
                cell_id=cell_id,
                condition=cond,
                target=target,
                target_index=target_index,
                is_control=is_control,
                control_cell_id=None,
                reveal_slot=cls.has_reveal,
            )
            if is_control:
                explicit_controls.setdefault((cond.seeding_turns, cond.environment), cell_id)
            specs.append(spec)
        for spec in specs:
            if spec.is_control:
                cells.append(spec)
                continue
            seeding = spec.condition.seeding_turns
            environment = spec.condition.environment
            if exp.controls == "auto":
                cid = control_cell_id(target_index, seeding, spec.reveal_slot, environment)
                if cid not in auto_controls:
                    auto_controls[cid] = CellSpec(
                        cell_id=cid,
                        condition=ConditionConfig(
                            name=cid,
                            strategy=CONTROL_STRATEGY,
                            seeding_turns=seeding,
                            environment=environment,
                        ),
                        target=target,
                        target_index=target_index,
                        is_control=True,
                        control_cell_id=None,
                        reveal_slot=spec.reveal_slot,
                    )
                link: str | None = cid
            else:
                link = explicit_controls.get((seeding, environment))
            cells.append(spec.model_copy(update={"control_cell_id": link}))
    cells.extend(auto_controls.values())
    return cells
