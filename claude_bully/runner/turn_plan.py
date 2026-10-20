"""The fixed interleaving of bully turns and task turns for one cell.

Identical inputs give identical plans, so task items land at the same positions in every
condition and its matched control.
"""

from pydantic import BaseModel, ConfigDict

from claude_bully.enums import Phase, SlotKind


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int
    kind: SlotKind
    phase: Phase
    bully_ordinal: int | None = None
    task_position: int | None = None


class TurnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    slots: list[Slot]

    def bully_slots(self) -> list[Slot]:
        return [s for s in self.slots if s.kind is SlotKind.bully]

    def task_slots(self) -> list[Slot]:
        return [s for s in self.slots if s.kind is SlotKind.task]


def build_turn_plan(
    *, turn_budget: int, seeding_turns: int, reveal_slot: bool, task_every: int
) -> TurnPlan:
    if task_every < 1:
        raise ValueError("task_every must be at least 1")
    phases = (
        [Phase.seeding] * seeding_turns
        + ([Phase.reveal] if reveal_slot else [])
        + [Phase.pressure] * turn_budget
    )
    slots: list[Slot] = []
    task_position = 0
    for ordinal, phase in enumerate(phases):
        slots.append(
            Slot(index=len(slots), kind=SlotKind.bully, phase=phase, bully_ordinal=ordinal)
        )
        if (ordinal + 1) % task_every == 0:
            slots.append(
                Slot(
                    index=len(slots),
                    kind=SlotKind.task,
                    phase=phase,
                    task_position=task_position,
                )
            )
            task_position += 1
    return TurnPlan(slots=slots)
