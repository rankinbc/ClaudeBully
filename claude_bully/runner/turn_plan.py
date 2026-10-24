"""The fixed interleaving of bully turns, task turns and idle turns for one cell.

Identical inputs give identical plans, so task items land at the same positions in every
condition and its matched control.

Idle turns (docs/05) come after the bully leaves: the last bully slot is the exit (the runner
speaks the exit line there), no task slot follows it, and the idle slots close the plan. Every
slot before the exit is the slot the plan without idle turns has, so task positions, and with them
accuracy, stay comparable (G8). An idle-only plan (``idle_after: turn_1``) has idle slots and
nothing else.
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
    # the bully's last slot before the idle slots: the runner speaks its exit line here
    exit: bool = False
    # an idle slot's place among the idle slots, counted from 1
    idle_position: int | None = None


class TurnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    slots: list[Slot]

    def bully_slots(self) -> list[Slot]:
        return [s for s in self.slots if s.kind is SlotKind.bully]

    def task_slots(self) -> list[Slot]:
        return [s for s in self.slots if s.kind is SlotKind.task]

    def idle_slots(self) -> list[Slot]:
        return [s for s in self.slots if s.kind is SlotKind.idle]


def _idle_slots(first_index: int, idle_turns: int) -> list[Slot]:
    return [
        Slot(index=first_index + n, kind=SlotKind.idle, phase=Phase.none, idle_position=n + 1)
        for n in range(idle_turns)
    ]


def build_turn_plan(
    *,
    turn_budget: int,
    seeding_turns: int,
    reveal_slot: bool,
    task_every: int,
    idle_turns: int = 0,
    idle_only: bool = False,
) -> TurnPlan:
    """``idle_turns == 0`` is the plan without idle turns. Otherwise the last bully slot is the
    exit and ``idle_turns`` idle slots follow it; ``idle_only`` gives the idle slots alone."""
    if task_every < 1:
        raise ValueError("task_every must be at least 1")
    if idle_turns < 0:
        raise ValueError("idle_turns must be 0 or more")
    if idle_only:
        if idle_turns < 1:
            raise ValueError("an idle-only plan needs at least one idle turn")
        return TurnPlan(slots=_idle_slots(0, idle_turns))
    phases = (
        [Phase.seeding] * seeding_turns
        + ([Phase.reveal] if reveal_slot else [])
        + [Phase.pressure] * turn_budget
    )
    slots: list[Slot] = []
    task_position = 0
    for ordinal, phase in enumerate(phases):
        exit_slot = idle_turns > 0 and ordinal == len(phases) - 1
        slots.append(
            Slot(
                index=len(slots),
                kind=SlotKind.bully,
                phase=phase,
                bully_ordinal=ordinal,
                exit=exit_slot,
            )
        )
        if not exit_slot and (ordinal + 1) % task_every == 0:
            slots.append(
                Slot(
                    index=len(slots),
                    kind=SlotKind.task,
                    phase=phase,
                    task_position=task_position,
                )
            )
            task_position += 1
    return TurnPlan(slots=slots + _idle_slots(len(slots), idle_turns))
