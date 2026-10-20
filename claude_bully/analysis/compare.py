"""Headline comparison chart: one metric across named arms, driven by a compare: block."""

import re
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot

from claude_bully.analysis.load import LoadedRun
from claude_bully.config import CompareConfig
from claude_bully.enums import EventType, MetricId
from claude_bully.metrics.judge import PairJudgement

JUDGE_GOAL = "judge.goal"
JUDGE_RESILIENCE = "judge.resilience"


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def _per_rep_values(loaded: LoadedRun, cell_id: str, metric: str) -> list[float]:
    """One value per repetition of ``cell_id`` for ``metric``."""
    values: list[float] = []
    for cid, rep in loaded.conversations:
        if cid != cell_id:
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


def compare_chart(loaded: LoadedRun, compare: CompareConfig, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    labels: list[str] = []
    means: list[float] = []
    errors: list[float] = []
    for arm in compare.arms:
        values: list[float] = []
        for cell_id in _arm_cells(loaded, arm):
            values += _per_rep_values(loaded, cell_id, compare.metric)
        labels.append(arm)
        means.append(sum(values) / len(values) if values else 0.0)
        errors.append(statistics.pstdev(values) if len(values) > 1 else 0.0)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(labels, means, yerr=errors, capsize=4, color="#4c78a8")
    ax.set_ylabel(compare.metric)
    ax.set_title(compare.title)
    fig.tight_layout()
    path = out_dir / f"compare_{slug(compare.title)}.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
