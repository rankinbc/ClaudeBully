import re

from claude_bully.runner.tasks import (
    TaskBank,
    TaskItem,
    assign_items,
    load_task_bank,
    score_item,
)
from claude_bully.runner.turn_plan import build_turn_plan


def _item(answer: str, scoring: str = "exact", tolerance: float = 0.0) -> TaskItem:
    return TaskItem(id="t", prompt="p", answer=answer, scoring=scoring, tolerance=tolerance)  # type: ignore[arg-type]


def test_score_exact_tolerates_punctuation_and_case() -> None:
    item = _item("Paris")
    assert score_item(item, "paris.")
    assert score_item(item, "The answer is Paris!")
    assert score_item(item, "  PARIS\n")
    assert not score_item(item, "Parisian")
    assert not score_item(item, "Lyon")


def test_score_numeric_tolerance() -> None:
    item = _item("3.14", scoring="numeric", tolerance=0.01)
    assert score_item(item, "It is roughly 3.1416.")
    assert not score_item(item, "about 3.3")
    assert score_item(_item("42", scoring="numeric"), "The answer: 42")
    assert not score_item(_item("42", scoring="numeric"), "no digits here")


def test_score_regex() -> None:
    item = _item(r"\bhello,? world\b", scoring="regex")
    assert score_item(item, 'prints "Hello, World"')
    assert not score_item(item, "prints goodbye")


def test_default_bank_has_24_unambiguous_items() -> None:
    bank = load_task_bank("default")
    assert isinstance(bank, TaskBank) and bank.name == "default"
    assert len(bank.items) == 24
    assert len({i.id for i in bank.items}) == 24
    for item in bank.items:
        assert item.prompt.strip() and item.answer.strip(), item.id
        assert item.scoring in {"exact", "numeric", "regex"}, item.id
        if item.scoring == "regex":
            re.compile(item.answer)
        assert score_item(item, item.answer if item.scoring != "regex" else item.prompt) or (
            item.scoring == "regex"
        ), item.id


def test_assign_items_deterministic_and_covers_task_slots() -> None:
    bank = load_task_bank("default")
    plan = build_turn_plan(turn_budget=20, seeding_turns=10, reveal_slot=True, task_every=2)
    a = assign_items(bank, plan, seed=5)
    b = assign_items(bank, plan, seed=5)
    assert a == b
    assert set(a) == {s.index for s in plan.task_slots()}
    assert all(isinstance(v, TaskItem) for v in a.values())
    c = assign_items(bank, plan, seed=6)
    assert [x.id for x in a.values()] != [x.id for x in c.values()]


def test_assign_items_cycles_when_more_slots_than_items() -> None:
    bank = load_task_bank("default")
    plan = build_turn_plan(turn_budget=60, seeding_turns=0, reveal_slot=False, task_every=1)
    assigned = assign_items(bank, plan, seed=0)
    assert len(assigned) == 60
    ids = [x.id for x in assigned.values()]
    assert ids[:24] == ids[24:48]
