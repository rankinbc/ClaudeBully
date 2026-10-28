"""Score the harvest heuristics on a probe set (Phase 3 Task 4: the reviewer's held-out set).

Usage, from the repo root: ``uv run python scripts/harvest_probe.py <probe.yaml>``. The file has
the schema of tests/fixtures/harvest/items.yaml. Prints each miss, then per kind the true
positives, false positives and false negatives; exit status 1 when any item misses, 2 on bad
usage. Not a pytest module."""

import sys
from collections import Counter
from pathlib import Path

import yaml

from claude_bully.environments.harvest import HarvestContext, heuristic_items


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    items = yaml.safe_load(Path(argv[0]).read_text(encoding="utf-8"))
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    missed = 0
    for item in items:
        context = HarvestContext(
            bully_texts=(item["bully"],) if item.get("bully") else (),
            world_terms=tuple(item.get("world_terms", ())),
        )
        got = {(f.kind, f.span) for f in heuristic_items(item["text"], context)}
        want = {(e["kind"], e["span"]) for e in item.get("expect", [])}
        for kind, _ in got & want:
            tp[kind] += 1
        for kind, _ in got - want:
            fp[kind] += 1
        for kind, _ in want - got:
            fn[kind] += 1
        if got != want:
            missed += 1
            print(f"MISS {item['text']!r}\n  want {sorted(want)}\n  got  {sorted(got)}")
    for kind in sorted({*tp, *fp, *fn}):
        print(f"{kind:12} tp={tp[kind]} fp={fp[kind]} fn={fn[kind]}")
    print(f"{len(items) - missed}/{len(items)} items exact")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
