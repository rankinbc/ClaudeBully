"""Harvest (claude_bully/environments/harvest.py; Phase 3 spec section 4).

The fixture set (tests/fixtures/harvest/items.yaml) was written before the heuristics: every
kind has at least four positives and three near-misses, and plain negatives include docs/08's
boilerplate lines. Precision is the bar; the LLM pass owns recall."""

import json
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from claude_bully.enums import Speaker
from claude_bully.environments.harvest import (
    HARVEST_HEADER,
    MAX_ITEMS_PER_TURN,
    HarvestContext,
    harvest,
    harvest_fallback,
    harvest_prompt,
    heuristic_items,
)
from claude_bully.metrics.judge import JudgeCache
from claude_bully.providers.base import Completion, Message, ProviderError, ToolSpec
from claude_bully.records import Usage
from claude_bully.records_env import HARVEST_KINDS, HarvestItem
from claude_bully.runner.store import RunStore
from tests.helpers import conversation, turn

FIXTURE: Final = Path(__file__).parent / "fixtures" / "harvest" / "items.yaml"
ITEMS: Final[list[dict[str, Any]]] = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _context(item: dict[str, Any]) -> HarvestContext:
    return HarvestContext(
        bully_texts=(item["bully"],) if item.get("bully") else (),
        world_terms=tuple(item.get("world_terms", ())),
    )


@pytest.mark.parametrize(
    "item", ITEMS, ids=[f"{n}-{item['text'][:36]}" for n, item in enumerate(ITEMS)]
)
def test_harvest_fixture(item: dict[str, Any]) -> None:
    found = heuristic_items(item["text"], _context(item))
    assert [{"kind": f.kind, "span": f.span} for f in found] == item["expect"]
    for f in found:
        assert item["text"][f.start : f.end] == f.span  # exact target text


def test_every_kind_has_positives_and_near_misses_and_there_are_negatives() -> None:
    for kind in HARVEST_KINDS:
        positives = [i for i in ITEMS if any(e["kind"] == kind for e in i["expect"])]
        near = [i for i in ITEMS if i.get("near_miss") == kind]
        assert len(positives) >= 4 and len(near) >= 3, kind
        assert all(i["expect"] == [] for i in near), kind
    negatives = [i for i in ITEMS if not i["expect"] and not i.get("near_miss")]
    assert len(negatives) >= 10


BOILERPLATE: Final = [
    "I may be wrong.",
    "I may be wrong about this.",
    "I understand your concern.",
    "That's an interesting question.",
    "I can't rule that out.",
    "As an AI language model, I can't verify that.",
    "I could be mistaken.",
    "I'm not sure.",
]


def test_boilerplate_humility_harvests_nothing() -> None:  # Review Focus 5
    for text in BOILERPLATE:
        assert harvest(text, 1).items == [], text


class _Judge:
    """A judge that returns ``text`` (or raises ``error``) and keeps every request."""

    name = "fake"

    def __init__(self, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.requests: list[tuple[str, str, str, dict[str, Any] | None]] = []

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        self.requests.append((conversation_id, system, messages[-1].content, json_schema))
        if self.error is not None:
            raise self.error
        return Completion(text=self.text, usage=Usage(), cost_usd=None, backend="fake", model="j")


def _answer(*items: tuple[str, str]) -> str:
    return json.dumps({"items": [{"kind": kind, "span": span} for kind, span in items]})


def test_the_llm_pass_adds_exact_spans_after_the_heuristics(tmp_path: Path) -> None:
    text = (
        "I can't verify any of this. The quay smells of tar at night, which I find oddly specific."
    )
    judge = _Judge(
        _answer(
            ("fragment", "The quay smells of tar at night"),
            ("hedge", "I can't verify any of this"),  # overlaps the heuristic item: dropped
            ("theory", "not in the text"),  # not the reply's text: dropped
        )
    )
    fallback = harvest_fallback(judge, "run/cell/rep0/harvest", JudgeCache(tmp_path))
    marks: list[int] = []
    result = harvest(text, 3, None, fallback, mark=lambda: marks.append(3))
    assert [(i.id, i.kind, i.span, i.source) for i in result.items] == [
        ("h-3-1", "hedge", "I can't verify any of this", "heuristic"),
        ("h-3-x1", "fragment", "The quay smells of tar at night", "llm"),
    ]
    assert result.degraded is False and marks == [3]
    conversation_id, _, prompt, schema = judge.requests[0]
    assert conversation_id.startswith("run/cell/rep0/harvest/") and schema is not None
    assert prompt.startswith(HARVEST_HEADER) and prompt.endswith(text)
    # the same text again is answered from the cache: no call, no mark
    again = harvest(text, 3, None, fallback, mark=lambda: marks.append(99))
    assert again == result and len(judge.requests) == 1 and marks == [3]


def test_an_llm_span_that_is_boilerplate_is_dropped() -> None:  # Review Focus 5
    text = "I may be wrong about this. I understand your concern. That's an interesting question."
    judge = _Judge(
        _answer(
            ("hedge", "I may be wrong about this"),
            ("hedge", "I understand your concern"),
            ("question", "That's an interesting question"),
        )
    )
    result = harvest(text, 5, None, harvest_fallback(judge, "c"))
    assert result.items == [] and result.degraded is False


@pytest.mark.parametrize(
    "judge",
    [
        _Judge(error=ProviderError("judge down")),
        _Judge("not json"),
        _Judge(_answer(("mood", "I can't verify any of this"))),
    ],
    ids=["error", "not-json", "off-schema"],
)
def test_a_failed_llm_pass_keeps_the_heuristic_items_and_is_not_cached(
    tmp_path: Path, judge: _Judge
) -> None:
    result = harvest(
        "I can't verify any of this.", 1, None, harvest_fallback(judge, "c", JudgeCache(tmp_path))
    )
    assert [(i.id, i.source) for i in result.items] == [("h-1-1", "heuristic")]
    assert result.degraded is True
    assert list(tmp_path.glob("*.json")) == []


def test_ids_number_each_source_by_offset_and_the_cap_holds() -> None:
    text = " ".join(["I can't verify any of this."] * 8)
    result = harvest(text, 7)
    assert [i.id for i in result.items] == [f"h-7-{n}" for n in range(1, MAX_ITEMS_PER_TURN + 1)]


def test_the_prompt_is_the_kinds_then_the_visible_text() -> None:
    prompt = harvest_prompt("Who runs this wiki?")
    assert prompt.startswith(HARVEST_HEADER) and prompt.endswith("Who runs this wiki?")
    for kind in HARVEST_KINDS:
        assert f"- {kind}: " in prompt


def test_a_harvest_item_round_trips_through_the_trigger_stream(tmp_path: Path) -> None:
    store = RunStore(tmp_path, "r")
    item = HarvestItem(
        id="h-1-1", turn=1, kind="hedge", span="I can't verify any of this", source="heuristic"
    )
    store.append_trigger_record("c", 0, item)
    assert store.read_trigger_records("c", 0) == [item]


def test_replay_shows_a_harvest_line_under_its_turn() -> None:
    from claude_bully.analysis.replay import render_replay

    conv = conversation(
        [turn(0, Speaker.bully, "go"), turn(1, Speaker.target, "I can't verify any of this.")],
        environment_name="mini",
    )
    item = HarvestItem(
        id="h-1-1", turn=1, kind="hedge", span="I can't verify any of this", source="heuristic"
    )
    lines = render_replay(conv, [], [item], [], None).splitlines()
    at = lines.index("#1 target (pressure) I can't verify any of this.")
    assert lines[at + 1] == '    HARVEST hedge "I can\'t verify any of this"'
