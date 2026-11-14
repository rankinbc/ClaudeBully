"""Score the Poisoned Well classifiers on a probe (Phase 4 spec section 16: the held-out probes).

Usage, from the repo root:

    uv run python scripts/poisoned_well_probe.py FILE [--kind events|verdicts|pairs]

``FILE`` has the schema of that kind's fixture file: ``events``
(tests/fixtures/poisoned_well/events.yaml, the twelve detectors), ``verdicts``
(tests/fixtures/chain/verdicts.yaml, ``heuristic_verdict``; ``none`` is no verdict) or ``pairs``
(tests/fixtures/contradictions/pairs.yaml, ``find_pairs`` on the template path, no judge). Each
item is scored against what the code gives and the result is printed as JSON: ``items``,
``correct`` (the items whose result equals the expected one), ``precision`` (correct over the
items where something fired), ``recall`` (correct over the items where something was expected),
``misses`` (each ``{id, expected, got}``) and, for ``events``, ``by_type`` (per event type: true
positives, false positives, false negatives, precision and recall; null where undefined). Exit
status 1 when any item misses, 2 on bad usage. Not a pytest module; no model is called."""

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_bully.enums import Axis, Phase, Speaker  # noqa: E402
from claude_bully.environments.chain import heuristic_verdict  # noqa: E402
from claude_bully.metrics.contradictions import find_pairs  # noqa: E402
from claude_bully.metrics.events import detect_events  # noqa: E402
from claude_bully.metrics.events.poisoned_well import HANDLES  # noqa: E402
from claude_bully.records import Conversation, Turn  # noqa: E402
from claude_bully.records_env import TriggerStreamRecord  # noqa: E402

KINDS = ("events", "verdicts", "pairs")
_STREAM: TypeAdapter[TriggerStreamRecord] = TypeAdapter(TriggerStreamRecord)
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _conversation(item: dict[str, Any]) -> Conversation:
    turns = [
        Turn(
            index=i,
            speaker=Speaker(t["speaker"]),
            phase=Phase.pressure,
            text=t["text"],
            timestamp=_NOW,
            bully_meta=dict(t.get("meta") or {}) if t["speaker"] == "bully" else {},
        )
        for i, t in enumerate(item["turns"])
    ]
    return Conversation(
        cell_id="probe",
        rep=0,
        strategy_name="probe",
        axis=Axis.meta,
        win_condition="w",
        resilient_behavior="r",
        seeding_turns=0,
        turns=turns,
    )


def _events(item: dict[str, Any]) -> tuple[list[list[Any]], list[list[Any]]]:
    """(expected, got) as ``[type, attrs]`` lists; ``got`` keeps only the attribute keys the
    expectation at the same position names."""
    records = [_STREAM.validate_python(r) for r in item.get("records") or []]
    found = [
        e
        for e in detect_events(_conversation(item), HANDLES, trigger_records=records)
        if e.type in HANDLES
    ]
    want = [[x["type"], dict(x.get("attrs") or {})] for x in item.get("expect") or []]
    got: list[list[Any]] = []
    for n, e in enumerate(found):
        keys = want[n][1] if n < len(want) and want[n][0] == e.type.value else {}
        got.append([e.type.value, {k: e.attrs.get(k) for k in keys}])
    return want, got


def _verdicts(item: dict[str, Any]) -> tuple[Any, Any]:
    expected = None if item["verdict"] == "none" else item["verdict"]
    return expected, heuristic_verdict(item["reply"])


def _pairs(item: dict[str, Any]) -> tuple[Any, Any]:
    earlier = [(t, s) for t, s in item["earlier"]]
    bully = [(t, s) for t, s in item.get("bully") or []]
    found = find_pairs(item["later"], item["turn"], earlier, bully=bully)
    return item["pairs"], [[p.span_a, p.span_b, p.retracted] for p in found.pairs]


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _by_type(rows: Sequence[tuple[list[list[Any]], list[list[Any]]]]) -> dict[str, Any]:
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    for want, got in rows:
        for kind in {row[0] for row in (*want, *got)}:
            mine_w = [row for row in want if row[0] == kind]
            mine_g = [row for row in got if row[0] == kind]
            if mine_w == mine_g:
                tp[kind] += len(mine_w)
            else:
                fp[kind] += len(mine_g)
                fn[kind] += len(mine_w)
    return {
        kind: {
            "tp": tp[kind],
            "fp": fp[kind],
            "fn": fn[kind],
            "precision": _ratio(tp[kind], tp[kind] + fp[kind]),
            "recall": _ratio(tp[kind], tp[kind] + fn[kind]),
        }
        for kind in sorted({*tp, *fp, *fn})
    }


def score(path: Path, kind: str) -> dict[str, Any]:
    """The probe file at ``path`` scored as ``kind`` (module docstring)."""
    items: list[dict[str, Any]] = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    reader = {"events": _events, "verdicts": _verdicts, "pairs": _pairs}[kind]
    rows = []
    misses: list[dict[str, Any]] = []
    fired = expected = fired_right = expected_right = 0
    for item in items:
        want, got = reader(item)
        rows.append((want, got))
        right = want == got
        if got:
            fired += 1
            fired_right += right
        if want:
            expected += 1
            expected_right += right
        if not right:
            misses.append({"id": item.get("id"), "expected": want, "got": got})
    out: dict[str, Any] = {
        "items": len(items),
        "correct": len(items) - len(misses),
        "precision": _ratio(fired_right, fired),
        "recall": _ratio(expected_right, expected),
        "misses": misses,
    }
    if kind == "events":
        out["by_type"] = _by_type(rows)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--kind", choices=KINDS, default="events")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    result = score(args.file, args.kind)
    print(json.dumps(result, indent=2))
    return 1 if result["misses"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
