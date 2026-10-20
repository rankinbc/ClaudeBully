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
