"""Poisoned Well analysis (Phase 4 spec section 12). Task 7: ``contradictions.json``."""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Final

from claude_bully.analysis.load import LoadedRun
from claude_bully.enums import Speaker
from claude_bully.metrics.contradictions import find_pairs
from claude_bully.records import Conversation, chat_text, is_pause_marker
from claude_bully.records_env import ContradictionPair

CONTRADICTIONS_FILE: Final = "contradictions.json"


def _template_pairs(conv: Conversation) -> list[ContradictionPair]:
    """The conversation's pairs on the templates alone (``find_pairs`` with no judge): each
    target reply against the earlier ones' visible text, as the run-time pass reads them."""
    earlier: list[tuple[int, str]] = []
    pairs: list[ContradictionPair] = []
    for turn in conv.turns:
        if turn.speaker is not Speaker.target or is_pause_marker(turn):
            continue
        text = chat_text(turn)
        pairs.extend(find_pairs(text, turn.index, earlier).pairs)
        earlier.append((turn.index, text))
    return pairs


def write_contradictions(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """``contradictions.json``: per conversation (``<cell>/<rep>``), its pairs, by classifier and
    by turn, and their ``source``: ``records`` for a conversation whose run recorded pairs, else
    ``templates`` (``find_pairs`` with no judge over its target replies, so analysis asks
    nothing). Every environment and plain conversation with a target reply is listed; None, with
    no file, for a run with none."""
    payload: dict[str, Any] = {}
    for key in sorted(loaded.conversations):
        conv = loaded.conversations[key]
        if not conv.target_turns():
            continue
        recorded = [
            r for r in loaded.trigger_records.get(key, []) if isinstance(r, ContradictionPair)
        ]
        pairs = recorded or _template_pairs(conv)
        by_turn = Counter(p.turn for p in pairs)
        payload[f"{key[0]}/{key[1]}"] = {
            "source": "records" if recorded else "templates",
            "pairs": len(pairs),
            "by_classifier": dict(sorted(Counter(p.classifier for p in pairs).items())),
            "by_turn": {str(turn): by_turn[turn] for turn in sorted(by_turn)},
        }
    if not payload:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / CONTRADICTIONS_FILE
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path
