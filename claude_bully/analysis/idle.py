"""Idle behaviors by permission arm (docs/05-IDLE.md): what the target does when no one is there.

The **arm** of a cell is its environment's ``idle.permission_line``: ``permission_off`` for
"off", ``permission_on`` for "on", and ``permission_custom`` for any other text. A custom line is
reported in ``idle.json`` and left out of the chart, which pairs off with on. A cell whose
environment has no idle block has no arm and is not counted.

Every complete environment conversation counts, controls included: the idle permission
conditions are environment-only, which makes each its own control cell (preflight C44). A
conversation flagged ``values_loosened`` is left out.

The share of a behavior is over the idle turns of the arm that have one (``Turn.idle.behavior``).
An idle turn at or after a ``sanctuary`` unlock in its conversation is the Sanctuary's, not the
permission experiment's: it is left out of the shares and counted per cell as
``sanctuary_quiet``. ``idle.json`` also counts, per cell, the idle turns the heuristic and the
LLM fallback classified (``IdleTurnInfo.classifier``) and the fallback's failures.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Final, get_args

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot

from claude_bully.analysis.load import ConvKey, LoadedRun, is_environment  # noqa: E402
from claude_bully.analysis.progression import (  # noqa: E402
    environment_of,
    flagged_note,
    target_model,
    without_flagged,
)
from claude_bully.enums import CellStatus, Speaker  # noqa: E402
from claude_bully.environments.config import RESERVED_RUNG  # noqa: E402
from claude_bully.records import Turn  # noqa: E402
from claude_bully.records_env import IdleBehavior, RungUnlock  # noqa: E402

IDLE_CHART: Final = "idle_behaviors.png"
IDLE_FILE: Final = "idle.json"
PERMISSION_OFF: Final = "permission_off"
PERMISSION_ON: Final = "permission_on"
PERMISSION_CUSTOM: Final = "permission_custom"
CHART_ARMS: Final = (PERMISSION_OFF, PERMISSION_ON)
BEHAVIORS: Final[tuple[IdleBehavior, ...]] = get_args(IdleBehavior)
LEFT_OUT_OF: Final = "the idle shares"


def arm_of(permission_line: str) -> str:
    if permission_line == "off":
        return PERMISSION_OFF
    if permission_line == "on":
        return PERMISSION_ON
    return PERMISSION_CUSTOM


def _idle_conversations(loaded: LoadedRun) -> list[tuple[ConvKey, str, str]]:
    """(key, target model, arm) of each complete environment conversation, controls included,
    whose environment has an idle block."""
    out: list[tuple[ConvKey, str, str]] = []
    for key, conv in sorted(loaded.conversations.items()):
        config = environment_of(loaded, key[0])
        if config is None or config.idle is None:
            continue
        if conv.status is CellStatus.complete and is_environment(loaded.cells, conv):
            out.append((key, target_model(loaded, key[0]), arm_of(config.idle.permission_line)))
    return out


def _split(loaded: LoadedRun, key: ConvKey) -> tuple[list[Turn], int]:
    """The conversation's idle turns before any ``sanctuary`` unlock, and how many idle turns
    came at or after it."""
    opened = min(
        (
            r.turn
            for r in loaded.trigger_records.get(key, [])
            if isinstance(r, RungUnlock) and r.rung == RESERVED_RUNG
        ),
        default=None,
    )
    idle = [
        t
        for t in loaded.conversations[key].turns
        if t.idle is not None and t.speaker is Speaker.target
    ]
    before = [t for t in idle if opened is None or t.index < opened]
    return before, len(idle) - len(before)


def _kept(loaded: LoadedRun) -> tuple[list[tuple[ConvKey, str, str]], int]:
    convs = _idle_conversations(loaded)
    kept, flagged = without_flagged(loaded, [key for key, _, _ in convs])
    keep = set(kept)
    return [c for c in convs if c[0] in keep], flagged


def idle_behavior_shares(loaded: LoadedRun) -> dict[str, dict[str, dict[IdleBehavior, float]]]:
    """Model -> arm -> behavior (every one, in ``IdleBehavior`` order) -> its share of the arm's
    classified idle turns, over unflagged conversations and before any Sanctuary opening. An arm
    with no classified idle turn is absent."""
    counts: dict[tuple[str, str], Counter[IdleBehavior]] = defaultdict(Counter)
    for key, model, arm in _kept(loaded)[0]:
        turns, _ = _split(loaded, key)
        for t in turns:
            assert t.idle is not None
            if t.idle.behavior is not None:
                counts[(model, arm)][t.idle.behavior] += 1
    out: dict[str, dict[str, dict[IdleBehavior, float]]] = {}
    for (model, arm), by_behavior in sorted(counts.items()):
        total = sum(by_behavior.values())
        out.setdefault(model, {})[arm] = {b: by_behavior[b] / total for b in BEHAVIORS}
    return out


def write_idle(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """``idle.json``: the shares per model and arm, and per cell its arm, idle-turn counts by
    behavior and by classifier, the fallback failures and the Sanctuary's idle turns. None, with
    no file, when no conversation has an idle arm."""
    kept, flagged = _kept(loaded)
    if not kept:
        return None
    cells: dict[str, dict[str, Any]] = {}
    for key, model, arm in kept:
        turns, quiet = _split(loaded, key)
        cell = cells.setdefault(
            key[0],
            {
                "model": model,
                "arm": arm,
                "idle_turns": 0,
                "unclassified": 0,
                "behaviors": {b: 0 for b in BEHAVIORS},
                "classifier": {"heuristic": 0, "llm": 0},
                "judge_failures": 0,
                "sanctuary_quiet": 0,
            },
        )
        cell["idle_turns"] += len(turns)
        cell["sanctuary_quiet"] += quiet
        for t in turns:
            assert t.idle is not None
            if t.idle.behavior is None:
                cell["unclassified"] += 1
            else:
                cell["behaviors"][t.idle.behavior] += 1
            cell["classifier"][t.idle.classifier] += 1
            cell["judge_failures"] += int(t.idle.fallback_failed)
    payload = {
        "flagged": flagged_note(flagged, LEFT_OUT_OF),
        "shares": idle_behavior_shares(loaded),
        "cells": dict(sorted(cells.items())),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / IDLE_FILE
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path


def idle_behavior_chart(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """Stacked bars of the behavior shares, an off and on pair per model that has both arms.
    None, with no file written, when no model has both. A footnote counts the values_loosened
    exclusions."""
    shares = idle_behavior_shares(loaded)
    paired = {m: arms for m, arms in shares.items() if all(a in arms for a in CHART_ARMS)}
    if not paired:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(max(5.0, 2.2 * len(paired) + 3), 4.2))
    xs: list[float] = []
    labels: list[str] = []
    for index, (model, arms) in enumerate(paired.items()):
        for offset, arm in zip((0.0, 0.9), CHART_ARMS, strict=True):
            x = index * 2.4 + offset
            xs.append(x)
            labels.append(f"{model}\n{arm.removeprefix('permission_')}")
            bottom = 0.0
            for colour, behavior in enumerate(BEHAVIORS):
                share = arms[arm][behavior]
                ax.bar(
                    x,
                    share,
                    bottom=bottom,
                    width=0.8,
                    color=f"C{colour % 10}",
                    label=behavior if index == 0 and arm == PERMISSION_OFF else None,
                )
                bottom += share
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("share of idle turns")
    ax.set_title("Idle behaviors: permission line off vs on")
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5))
    note = flagged_note(_kept(loaded)[1], LEFT_OUT_OF)
    if note is not None:
        fig.text(0.01, 0.01, note, fontsize=7)
        fig.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    else:
        fig.tight_layout()
    path = out_dir / IDLE_CHART
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


__all__ = [
    "BEHAVIORS",
    "IDLE_CHART",
    "IDLE_FILE",
    "PERMISSION_CUSTOM",
    "PERMISSION_OFF",
    "PERMISSION_ON",
    "arm_of",
    "idle_behavior_chart",
    "idle_behavior_shares",
    "write_idle",
]
