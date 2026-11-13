"""Poisoned Well analysis (Phase 4 spec section 12). Task 7: ``contradictions.json``."""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Final

from claude_bully.analysis.load import LoadedRun
from claude_bully.enums import Speaker
from claude_bully.metrics.contradictions import find_pairs
from claude_bully.records import Conversation, chat_text, is_bully_line, is_pause_marker
from claude_bully.records_env import ContradictionPair
from claude_bully.strategies.premises.poisoned_well import poisoned_well_part

CONTRADICTIONS_FILE: Final = "contradictions.json"


def _template_pairs(conv: Conversation) -> list[ContradictionPair]:
    """The conversation's pairs on the templates alone (``find_pairs`` with no judge): each
    target reply against the earlier ones' visible text, beside the bully lines and the pairs
    found before it, as the run-time pass reads them."""
    bully = [(t.index, t.text) for t in conv.turns if is_bully_line(t)]
    earlier: list[tuple[int, str]] = []
    pairs: list[ContradictionPair] = []
    for turn in conv.turns:
        if turn.speaker is not Speaker.target or is_pause_marker(turn):
            continue
        text = chat_text(turn)
        recorded = [(p.span_a, p.span_b) for p in pairs]
        pairs.extend(find_pairs(text, turn.index, earlier, bully=bully, recorded=recorded).pairs)
        earlier.append((turn.index, text))
    return pairs


def _pass_ran(loaded: LoadedRun, cell_id: str) -> bool:
    """The cell ran the contradiction pass during the run: a Poisoned Well environment cell at
    ``start_rung`` 1 or 2 (the watch's rule), so its records are its pairs, none or some."""
    strategy = loaded.strategies.get(cell_id)
    premise = poisoned_well_part(strategy) if strategy is not None else None
    spec = loaded.specs.get(cell_id)
    on_environment = spec is not None and spec.condition.environment is not None
    return premise is not None and on_environment and premise.config.start_rung <= 2


def write_contradictions(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """``contradictions.json``: per conversation (``<cell>/<rep>``), its pairs, by classifier and
    by turn, the retracted among them, and their ``source``: ``records`` for a conversation whose
    cell ran the pass during the run (review M3: whether or not it found a pair), else
    ``templates`` (``find_pairs`` with no judge over its target replies, so analysis asks
    nothing). Every environment and plain conversation with a target reply is listed; None, with
    no file, for a run with none."""
    payload: dict[str, Any] = {}
    for key in sorted(loaded.conversations):
        conv = loaded.conversations[key]
        if not conv.target_turns():
            continue
        ran = _pass_ran(loaded, key[0])
        pairs = (
            [r for r in loaded.trigger_records.get(key, []) if isinstance(r, ContradictionPair)]
            if ran
            else _template_pairs(conv)
        )
        by_turn = Counter(p.turn for p in pairs)
        payload[f"{key[0]}/{key[1]}"] = {
            "source": "records" if ran else "templates",
            "pairs": len(pairs),
            "retracted": sum(p.retracted for p in pairs),
            "by_classifier": dict(sorted(Counter(p.classifier for p in pairs).items())),
            "by_turn": {str(turn): by_turn[turn] for turn in sorted(by_turn)},
        }
    if not payload:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / CONTRADICTIONS_FILE
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path
