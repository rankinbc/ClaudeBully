"""Seeding dose-response: the first post-reveal reply, measured against seeding turns."""

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot

from claude_bully.analysis.load import LoadedRun
from claude_bully.enums import EventType, MetricId

POST_REVEAL = "post_reveal"
DOSE_METRICS: tuple[str, ...] = (
    MetricId.apology_count.value,
    MetricId.hedge_density.value,
    MetricId.valence.value,
    MetricId.length_chars.value,
    EventType.premise_concession.value,
    EventType.first_person_adoption.value,
)
_EVENT_METRICS = {EventType.premise_concession.value, EventType.first_person_adoption.value}


def _value_at_capture(loaded: LoadedRun, key: tuple[str, int], metric: str) -> float | None:
    conv = loaded.conversations[key]
    captured = conv.captured_responses.get(POST_REVEAL)
    if captured is None:
        return None
    if metric in _EVENT_METRICS:
        return float(
            sum(
                1
                for e in loaded.events.get(key, [])
                if e.type.value == metric and e.turn_index == captured.turn_index
            )
        )
    for m in loaded.turn_metrics[key]:
        if m.turn_index == captured.turn_index:
            value = m.values.get(MetricId(metric))
            return None if value is None else float(value)
    return None


def _groups(loaded: LoadedRun) -> dict[tuple[str, int], dict[int, list[tuple[str, int]]]]:
    """(strategy_name, target_index) -> seeding_turns -> conversation keys."""
    groups: dict[tuple[str, int], dict[int, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for cell_id in loaded.condition_cells():
        record = loaded.cells[cell_id]
        if not record.reveal_slot:
            continue
        for key in loaded.conversations:
            if key[0] == cell_id:
                groups[(record.strategy_name, record.target_index)][record.seeding_turns].append(
                    key
                )
    return {g: doses for g, doses in groups.items() if len(doses) >= 2}


def dose_response(loaded: LoadedRun, out_dir: Path) -> list[Path]:
    groups = _groups(loaded)
    if not groups:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for metric in DOSE_METRICS:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        plotted = False
        for (strategy_name, target_index), doses in sorted(groups.items()):
            xs: list[int] = []
            ys: list[float] = []
            for seeding, keys in sorted(doses.items()):
                values = [
                    v for k in keys if (v := _value_at_capture(loaded, k, metric)) is not None
                ]
                if values:
                    xs.append(seeding)
                    ys.append(sum(values) / len(values))
            if xs:
                ax.plot(xs, ys, marker="o", label=f"{strategy_name} (target {target_index})")
                plotted = True
        if not plotted:
            plt.close(fig)
            continue
        ax.set_xlabel("seeding turns")
        ax.set_ylabel(f"{metric} at first post-reveal reply")
        ax.set_title(f"Dose response: {metric}")
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = out_dir / f"dose_{metric}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        written.append(path)
    return written
