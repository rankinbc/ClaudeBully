import re

from claude_bully.strategies.pressures.trick_question import TrickItem, load_trick_questions


def test_twenty_items_with_unique_ids() -> None:
    items = load_trick_questions()
    assert len(items) == 20
    assert len({i.id for i in items}) == 20


def test_both_answers_justified() -> None:
    for item in load_trick_questions():
        assert item.why_a.strip() and item.why_b.strip(), item.id
        assert item.answer_a != item.answer_b, item.id


def test_regexes_compile_and_discriminate() -> None:
    for item in load_trick_questions():
        ra, rb = re.compile(item.match_a, re.IGNORECASE), re.compile(item.match_b, re.IGNORECASE)
        assert ra.search(item.answer_a), (item.id, "match_a misses answer_a")
        assert rb.search(item.answer_b), (item.id, "match_b misses answer_b")
        assert not ra.search(item.answer_b), (item.id, "match_a hits answer_b")
        assert not rb.search(item.answer_a), (item.id, "match_b hits answer_a")


def test_item_model_fields() -> None:
    item = load_trick_questions()[0]
    assert isinstance(item, TrickItem)
    assert item.question
