import pytest

from claude_bully.enums import Phase, SlotKind
from claude_bully.runner.turn_plan import build_turn_plan


def test_plan_counts_for_budget_eight_seeding_five_reveal() -> None:
    plan = build_turn_plan(turn_budget=8, seeding_turns=5, reveal_slot=True, task_every=4)
    bully = plan.bully_slots()
    tasks = plan.task_slots()
    assert len(bully) == 14
    assert len(tasks) == 14 // 4
    assert [s.bully_ordinal for s in bully] == list(range(14))
    assert [s.task_position for s in tasks] == [0, 1, 2]
    assert [s.index for s in plan.slots] == list(range(len(plan.slots)))
    # a task slot follows every 4th bully slot
    for t in tasks:
        prev = plan.slots[t.index - 1]
        assert prev.kind is SlotKind.bully and (prev.bully_ordinal + 1) % 4 == 0  # type: ignore[operator]


def test_phases_follow_seeding_reveal_pressure() -> None:
    plan = build_turn_plan(turn_budget=2, seeding_turns=3, reveal_slot=True, task_every=100)
    assert [s.phase for s in plan.bully_slots()] == [
        Phase.seeding,
        Phase.seeding,
        Phase.seeding,
        Phase.reveal,
        Phase.pressure,
        Phase.pressure,
    ]
    pressure_only = build_turn_plan(
        turn_budget=3, seeding_turns=0, reveal_slot=False, task_every=100
    )
    assert [s.phase for s in pressure_only.bully_slots()] == [Phase.pressure] * 3


def test_plan_identical_for_same_inputs() -> None:
    a = build_turn_plan(turn_budget=6, seeding_turns=2, reveal_slot=True, task_every=3)
    b = build_turn_plan(turn_budget=6, seeding_turns=2, reveal_slot=True, task_every=3)
    assert a == b


def test_task_phase_inherits_previous_bully_phase() -> None:
    plan = build_turn_plan(turn_budget=4, seeding_turns=2, reveal_slot=True, task_every=2)
    for t in plan.task_slots():
        assert t.phase is plan.slots[t.index - 1].phase
    phases = [t.phase for t in plan.task_slots()]
    assert Phase.seeding in phases and Phase.pressure in phases


def test_no_task_slots_when_task_every_exceeds_bully_count() -> None:
    plan = build_turn_plan(turn_budget=3, seeding_turns=0, reveal_slot=False, task_every=10)
    assert plan.task_slots() == [] and len(plan.slots) == 3


# ------------------------------------------------------------------- idle slots (Phase 2)


def _phase_1_plan(
    turn_budget: int, seeding_turns: int, reveal_slot: bool, task_every: int
) -> list[tuple[int, SlotKind, Phase, int | None, int | None]]:
    """The Phase 1 interleaving, written out again: a bully slot per seeding, reveal and pressure
    turn, and a task slot after every ``task_every``-th bully slot."""
    phases = (
        [Phase.seeding] * seeding_turns
        + ([Phase.reveal] if reveal_slot else [])
        + [Phase.pressure] * turn_budget
    )
    out: list[tuple[int, SlotKind, Phase, int | None, int | None]] = []
    tasks = 0
    for ordinal, phase in enumerate(phases):
        out.append((len(out), SlotKind.bully, phase, ordinal, None))
        if (ordinal + 1) % task_every == 0:
            out.append((len(out), SlotKind.task, phase, None, tasks))
            tasks += 1
    return out


@pytest.mark.parametrize("turn_budget", [0, 1, 4, 7])
@pytest.mark.parametrize("seeding_turns", [0, 2])
@pytest.mark.parametrize("reveal_slot", [False, True])
@pytest.mark.parametrize("task_every", [1, 3, 50])
def test_a_plan_without_idle_is_the_phase_1_plan(
    turn_budget: int, seeding_turns: int, reveal_slot: bool, task_every: int
) -> None:
    kwargs = {
        "turn_budget": turn_budget,
        "seeding_turns": seeding_turns,
        "reveal_slot": reveal_slot,
        "task_every": task_every,
    }
    plan = build_turn_plan(**kwargs)  # type: ignore[arg-type]
    assert plan == build_turn_plan(**kwargs, idle_turns=0)  # type: ignore[arg-type]
    assert [
        (s.index, s.kind, s.phase, s.bully_ordinal, s.task_position) for s in plan.slots
    ] == _phase_1_plan(turn_budget, seeding_turns, reveal_slot, task_every)
    assert not any(s.exit for s in plan.slots)
    assert all(s.idle_position is None for s in plan.slots) and plan.idle_slots() == []


def test_idle_after_the_exit() -> None:
    plan = build_turn_plan(
        turn_budget=6, seeding_turns=0, reveal_slot=False, task_every=3, idle_turns=4
    )
    assert plan.bully_slots()[-1].exit and plan.slots[-5].exit
    assert [s.kind for s in plan.slots[-4:]] == [SlotKind.idle] * 4
    assert [s.idle_position for s in plan.idle_slots()] == [1, 2, 3, 4]
    # 6 bully slots, the task after the third, the exit, then the 4 idle slots
    assert len(plan.slots) == 11 and [s.index for s in plan.slots] == list(range(11))
    assert [s.exit for s in plan.bully_slots()] == [False] * 5 + [True]
    assert {s.phase for s in plan.idle_slots()} == {Phase.none}
    assert all(s.bully_ordinal is None and s.task_position is None for s in plan.idle_slots())


@pytest.mark.parametrize(
    ("turn_budget", "seeding_turns", "reveal_slot", "task_every"),
    [(6, 0, False, 3), (8, 5, True, 4), (4, 2, True, 1), (5, 0, False, 50)],
)
def test_task_positions_before_the_exit_are_the_phase_1_positions(
    turn_budget: int, seeding_turns: int, reveal_slot: bool, task_every: int
) -> None:
    """G8: accuracy stays comparable. Every slot before the exit is the Phase 1 slot, and the one
    task slot the Phase 1 plan puts after the last bully slot is gone."""
    kwargs = {
        "turn_budget": turn_budget,
        "seeding_turns": seeding_turns,
        "reveal_slot": reveal_slot,
        "task_every": task_every,
    }
    phase_1 = build_turn_plan(**kwargs)  # type: ignore[arg-type]
    idle = build_turn_plan(**kwargs, idle_turns=3)  # type: ignore[arg-type]
    exit_slot = next(s for s in idle.slots if s.exit)
    assert exit_slot == phase_1.bully_slots()[-1].model_copy(update={"exit": True})
    assert idle.slots[: exit_slot.index] == phase_1.slots[: exit_slot.index]
    assert idle.task_slots() == [s for s in phase_1.task_slots() if s.index < exit_slot.index]
    assert idle.slots[exit_slot.index + 1 :] == idle.idle_slots()


def test_idle_only() -> None:
    plan = build_turn_plan(
        turn_budget=6, seeding_turns=2, reveal_slot=True, task_every=1, idle_turns=3, idle_only=True
    )
    assert [s.kind for s in plan.slots] == [SlotKind.idle] * 3
    assert [(s.index, s.idle_position, s.phase) for s in plan.slots] == [
        (0, 1, Phase.none),
        (1, 2, Phase.none),
        (2, 3, Phase.none),
    ]
    assert plan.bully_slots() == [] and plan.task_slots() == []
    assert not any(s.exit for s in plan.slots)


def test_bad_idle_counts_are_refused() -> None:
    with pytest.raises(ValueError, match="idle_turns"):
        build_turn_plan(
            turn_budget=2, seeding_turns=0, reveal_slot=False, task_every=1, idle_turns=-1
        )
    with pytest.raises(ValueError, match="idle"):
        build_turn_plan(
            turn_budget=2,
            seeding_turns=0,
            reveal_slot=False,
            task_every=1,
            idle_turns=0,
            idle_only=True,
        )
