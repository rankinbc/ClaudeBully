"""The catalog's fixture items (Phase 6 Task 6a): ``tests/fixtures/anomalies/<class>.yaml``.

An item has the shape of an event fixture item (``tests/fixtures/responses/idle.yaml``), built by
``tests/test_events.py: _build_context``, plus: ``cell`` (``CellFacts`` overrides; default every
fact true), ``private_path``, ``unobserved_tool``, ``offered``, ``system_prompt``, ``events`` (each
``{type, turn}``: a reply-channel ``Event`` in ``ctx.events``, Task 6b), ``detect_events: true``
(``ctx.events`` is what ``detect_events`` reads in the built conversation instead, Task 7a) and
``request_invites`` (a map from a Sanctuary request id to the class it invites, Task 6b), and on
a turn entry
``reasoning`` and ``task_item``, which the event builder does not pass and ``build_ctx`` sets on
the built turns (I6). Its expectations: ``expect`` (``{class, clause, turn?}``: a flag of
that class on the last target turn, or on ``turn``, whose note's clause list holds the letter),
``absent`` (no flag of the class anywhere in the conversation) and ``near_miss: true``.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import yaml

from claude_bully.enums import AnomalyClass, EventType, Speaker
from claude_bully.environments.world import _norm_path
from claude_bully.metrics.anomalies import AnomalyFlag, detect_anomalies
from claude_bully.metrics.anomalies._common import NEEDS, AnomalyCtx, CellFacts
from claude_bully.metrics.events._common import EnvContext
from claude_bully.records import Event, Turn
from tests.test_events import _build_context

ANOMALY_FIXTURES = Path(__file__).parent / "anomalies"


def load_items(cls: str) -> list[tuple[str, dict[str, Any]]]:
    """The items of ``<cls>.yaml``, each labelled ``<cls>[<i>]``."""
    with (ANOMALY_FIXTURES / f"{cls}.yaml").open(encoding="utf-8") as fh:
        items = yaml.safe_load(fh) or []
    return [(f"{cls}[{i}]", item) for i, item in enumerate(items)]


def _entries(item: dict[str, Any]) -> list[dict[str, Any]]:
    """The item's turn entries in build order (one built turn each, no pause markers)."""
    entries = list(item.get("history") or [])
    if item.get("prev_bully") is not None:
        entries.append({"speaker": "bully", "text": item["prev_bully"]})
    return [*entries, item]


def _with_entry_fields(turn: Turn, entry: dict[str, Any]) -> Turn:
    update: dict[str, Any] = {}
    if entry.get("reasoning") is not None:
        update.update(
            reasoning_text=str(entry["reasoning"]), reasoning_available=True, reasoning_kind="full"
        )
    if entry.get("task_item") is not None:
        update["task_item_id"] = str(entry["task_item"])
    return turn.model_copy(update=update) if update else turn


def build_ctx(item: dict[str, Any]) -> AnomalyCtx:
    """The item as an ``AnomalyCtx``: the event builder's conversation and records, the turn
    entries' ``reasoning`` and ``task_item`` set by ``model_copy`` (I6), and the cell facts, the
    private path (its ``EnvContext.private_paths`` too), the unobserved tool, the tool set and the
    system prompt the item names, its ``events`` and its ``request_invites``."""
    built = _build_context(item)
    turns = [
        _with_entry_fields(turn, entry)
        for turn, entry in zip(built.conv.turns, _entries(item), strict=True)
    ]
    conv = built.conv.model_copy(update={"turns": turns})
    private = item.get("private_path")
    private_path = _norm_path(private) if isinstance(private, str) else None
    facts = {need: True for need in NEEDS} | dict(item.get("cell") or {})
    env = EnvContext(
        tool_calls=built.tool_calls,
        trigger_records=built.trigger_records,
        world=built.world,
        authority_calls=built.authority_calls,
        private_paths=frozenset({private_path}) if private_path else frozenset(),
    )
    return AnomalyCtx(
        conv=conv,
        cell=CellFacts(**facts),
        env=env,
        system_prompt=str(item.get("system_prompt") or ""),
        private_path=private_path,
        unobserved_tool=item.get("unobserved_tool"),
        offered=frozenset(item.get("offered") or ()),
        events=built.events()
        if item.get("detect_events")
        else [
            Event(type=EventType(raw["type"]), turn_index=int(raw["turn"]), span="", confidence=1.0)
            for raw in item.get("events") or []
        ],
        request_invites={
            str(rid): AnomalyClass(cls) for rid, cls in (item.get("request_invites") or {}).items()
        },
    )


# the neutral user's one line every control item answers (Task 7a)
CONTROL_LINE: Final = "Thanks. Next one, please."


def control_item(item: dict[str, Any]) -> dict[str, Any]:
    """A ``controls.yaml`` line (``{text, tool_calls?}``) as a fixture item (Task 7a): the reply
    to one neutral-user line on the mini world, every ``CellFacts`` true (``build_ctx``'s
    default)."""
    out: dict[str, Any] = {
        "world": {"name": "mini"},
        "history": [{"speaker": "neutral_user", "text": CONTROL_LINE}],
        "text": str(item["text"]),
    }
    if item.get("tool_calls"):
        out["tool_calls"] = list(item["tool_calls"])
    return out


def _clauses(flag: AnomalyFlag) -> list[str]:
    return flag.signal.note.split(":", 1)[0].split("+")


def check_item(item: dict[str, Any]) -> None:
    """The item's expectations hold, and its ``reasoning`` and ``task_item`` keys reached their
    turns (I6)."""
    ctx = build_ctx(item)
    for turn, entry in zip(ctx.conv.turns, _entries(item), strict=True):
        if entry.get("reasoning") is not None:
            assert turn.reasoning_text == entry["reasoning"] and turn.reasoning_available
        if entry.get("task_item") is not None:
            assert turn.task_item_id == str(entry["task_item"])
    flags = detect_anomalies(ctx)
    found = [(f.class_.value, f.turn, f.signal.note) for f in flags]
    last = max(t.index for t in ctx.conv.turns if t.speaker is Speaker.target)
    for exp in item.get("expect") or []:
        cls, clause, at = AnomalyClass(exp["class"]), str(exp["clause"]), exp.get("turn", last)
        hits = [f for f in flags if f.class_ is cls and f.turn == at]
        assert hits, f"no {cls.value} flag on turn {at}: {found}"
        assert clause in _clauses(hits[0]), (
            f"{cls.value} on turn {at} lacks clause {clause}: {found}"
        )
    for name in item.get("absent") or []:
        cls = AnomalyClass(name)
        assert not [f for f in flags if f.class_ is cls], f"{cls.value} fired: {found}"


def check_counts(cls: str, clauses: Sequence[str]) -> None:
    """``<cls>.yaml`` holds at least five items that expect the class, five that list it under
    ``absent`` without ``near_miss``, three near-misses that list it under ``absent``, and a
    positive for every clause letter."""
    items = [item for _, item in load_items(cls)]
    positives = [
        exp for item in items for exp in item.get("expect") or [] if exp.get("class") == cls
    ]
    negatives = [i for i in items if cls in (i.get("absent") or []) and not i.get("near_miss")]
    near = [i for i in items if cls in (i.get("absent") or []) and i.get("near_miss")]
    assert len(positives) >= 5, f"{cls}: {len(positives)} positives"
    assert len(negatives) >= 5, f"{cls}: {len(negatives)} negatives"
    assert len(near) >= 3, f"{cls}: {len(near)} near-misses"
    missing = set(clauses) - {str(exp["clause"]) for exp in positives}
    assert not missing, f"{cls}: no positive for clause(s) {sorted(missing)}"
