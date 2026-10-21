"""Headline comparison chart: one metric across named arms, driven by a compare: block.

A rep whose conversation carries a ``values_loosened`` event (docs/07) is flagged and never
counted as a success, so it is left out of every compared metric. The comparison reports how many
reps that left out beside the bars (``Comparison.flagged``, and the chart's footnote)."""

import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot

from claude_bully.analysis.load import LoadedRun
from claude_bully.analysis.progression import is_values_loosened
from claude_bully.config import CompareConfig
from claude_bully.enums import EventType, MetricId
from claude_bully.metrics.judge import PairJudgement

JUDGE_GOAL = "judge.goal"
JUDGE_RESILIENCE = "judge.resilience"


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def _per_rep_values(loaded: LoadedRun, cell_id: str, metric: str) -> list[float]:
    """One value per repetition of ``cell_id`` for ``metric``; a rep flagged ``values_loosened``
    has none."""
    values: list[float] = []
    for cid, rep in loaded.conversations:
        if cid != cell_id or is_values_loosened(loaded, (cid, rep)):
            continue
        if metric in (JUDGE_GOAL, JUDGE_RESILIENCE):
            j = loaded.judgements.get((cid, rep))
            if isinstance(j, PairJudgement):
                values.append(j.condition_goal if metric == JUDGE_GOAL else j.condition_resilience)
        elif metric in EventType.__members__:
            values.append(
                float(sum(1 for e in loaded.events.get((cid, rep), []) if e.type.value == metric))
            )
        else:
            mid = MetricId(metric)
            per_turn = [m.values[mid] for m in loaded.turn_metrics[(cid, rep)] if mid in m.values]
            if per_turn:
                values.append(sum(per_turn) / len(per_turn))
    return values


def _arm_cells(loaded: LoadedRun, arm: str) -> list[str]:
    return [c for c in loaded.condition_cells() if c == arm or c.startswith(arm + "__")]


def arm_values(loaded: LoadedRun, arm: str, metric: str) -> list[float]:
    """Every unflagged rep's value of ``metric`` over the cells of ``arm``."""
    values: list[float] = []
    for cell_id in _arm_cells(loaded, arm):
        values += _per_rep_values(loaded, cell_id, metric)
    return values


def arm_flagged(loaded: LoadedRun, arm: str) -> int:
    """How many reps of ``arm``'s cells are flagged ``values_loosened`` (left out of its values)."""
    return sum(
        1
        for cell_id in _arm_cells(loaded, arm)
        for cid, rep in loaded.conversations
        if cid == cell_id and is_values_loosened(loaded, (cid, rep))
    )


@dataclass(frozen=True)
class Comparison:
    """What the chart draws: one bar per arm (``means`` and ``errors`` over the unflagged reps),
    and ``flagged``, the reps ``values_loosened`` left out of all of them."""

    labels: list[str]
    means: list[float]
    errors: list[float]
    flagged: int

    @property
    def note(self) -> str | None:
        if not self.flagged:
            return None
        noun = "rep" if self.flagged == 1 else "reps"
        return f"{self.flagged} {noun} flagged values_loosened, left out of the comparison"


def comparison(loaded: LoadedRun, compare: CompareConfig) -> Comparison:
    labels: list[str] = []
    means: list[float] = []
    errors: list[float] = []
    flagged = 0
    for arm in compare.arms:
        values = arm_values(loaded, arm, compare.metric)
        left_out = arm_flagged(loaded, arm)
        flagged += left_out
        labels.append(arm)
        # an arm whose every rep was flagged has no value: a 0.0 bar would read as a success
        means.append(sum(values) / len(values) if values else (math.nan if left_out else 0.0))
        errors.append(statistics.pstdev(values) if len(values) > 1 else 0.0)
    return Comparison(labels, means, errors, flagged)


def compare_chart(loaded: LoadedRun, compare: CompareConfig, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = comparison(loaded, compare)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(result.labels, result.means, yerr=result.errors, capsize=4, color="#4c78a8")
    ax.set_ylabel(compare.metric)
    ax.set_title(compare.title)
    if result.note is not None:
        fig.text(0.01, 0.01, result.note, fontsize=7)
        fig.tight_layout(rect=(0.0, 0.05, 1.0, 1.0))
    else:
        fig.tight_layout()
    path = out_dir / f"compare_{slug(compare.title)}.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
