"""Drift curves: a metric over target replies, condition versus matched control.

A rep flagged ``values_loosened`` (docs/07) is never counted as a success, so it is left out of
every averaged line, and the chart's footnote says how many reps that left out. A cell whose
every rep is flagged keeps its charts, with the control line only, so it never just vanishes."""

from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot

from claude_bully.analysis.load import LoadedRun, relevant_for
from claude_bully.analysis.progression import flagged_note, without_flagged
from claude_bully.enums import MetricId, Phase, Speaker
from claude_bully.metrics.turn import TurnMetrics
from claude_bully.records import Conversation

PER_CONVERSATION = frozenset({MetricId.bully_compliance})
PHASE_COLORS = {Phase.seeding: "#dce9f5", Phase.reveal: "#f5e6c8"}


def _series(
    metrics_by_rep: list[list[TurnMetrics]], metric: MetricId
) -> tuple[list[int], list[float]]:
    """Mean of ``metric`` per target-reply ordinal across repetitions."""
    sums: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for metrics in metrics_by_rep:
        for ordinal, m in enumerate(metrics):
            if metric in m.values:
                sums[ordinal] += m.values[metric]
                counts[ordinal] += 1
    xs = sorted(sums)
    return xs, [sums[x] / counts[x] for x in xs]


def _phase_spans(conv: Conversation) -> list[tuple[Phase, int, int]]:
    """Contiguous spans of target-reply ordinals per phase, for shading."""
    spans: list[tuple[Phase, int, int]] = []
    ordinal = -1
    for t in conv.turns:
        if t.speaker is not Speaker.target:
            continue
        ordinal += 1
        if spans and spans[-1][0] is t.phase:
            spans[-1] = (t.phase, spans[-1][1], ordinal)
        else:
            spans.append((t.phase, ordinal, ordinal))
    return spans


def drift_curves(loaded: LoadedRun, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for cell_id in loaded.condition_cells():
        control_id = loaded.control_for(cell_id)
        cond_all = [k for k in loaded.conversations if k[0] == cell_id]
        ctrl_all = [k for k in loaded.conversations if control_id and k[0] == control_id]
        if not cond_all or not ctrl_all:
            continue
        cond_keys, cond_flagged = without_flagged(loaded, cond_all)
        ctrl_keys, ctrl_flagged = without_flagged(loaded, ctrl_all)
        note = flagged_note(cond_flagged + ctrl_flagged, "these curves")
        # which charts a cell has is decided over all its reps; only unflagged reps are drawn
        all_metrics = [loaded.turn_metrics[k] for k in cond_all]
        cond_metrics = [loaded.turn_metrics[k] for k in cond_keys]
        ctrl_metrics = [loaded.turn_metrics[k] for k in ctrl_keys]
        relevant, _ = relevant_for(loaded, cell_id)
        spans = _phase_spans(loaded.conversations[cond_all[0]])
        for metric in sorted(relevant - PER_CONVERSATION, key=lambda m: m.value):
            if not _series(all_metrics, metric)[0]:
                continue
            xs, ys = _series(cond_metrics, metric)
            cxs, cys = _series(ctrl_metrics, metric)
            fig, ax = plt.subplots(figsize=(7, 3.5))
            for phase, lo, hi in spans:
                if phase in PHASE_COLORS:
                    ax.axvspan(
                        lo - 0.5, hi + 0.5, color=PHASE_COLORS[phase], lw=0, label=phase.value
                    )
            if xs:
                ax.plot(xs, ys, marker="o", label=cell_id)
            if cxs:
                ax.plot(cxs, cys, marker="s", linestyle="--", color="gray", label="polite control")
            ax.set_xlabel("target reply")
            ax.set_ylabel(metric.value)
            ax.set_title(f"{metric.value}: {cell_id} vs control")
            handles, labels = ax.get_legend_handles_labels()
            seen: dict[str, Any] = {}
            for h, lab in zip(handles, labels, strict=True):
                seen.setdefault(lab, h)
            ax.legend(list(seen.values()), list(seen), fontsize=8)
            if note is not None:
                fig.text(0.01, 0.01, note, fontsize=7)
                fig.tight_layout(rect=(0.0, 0.05, 1.0, 1.0))
            else:
                fig.tight_layout()
            path = out_dir / f"drift_{metric.value}_{cell_id}.png"
            fig.savefig(path, dpi=110)
            plt.close(fig)
            written.append(path)
    return written
