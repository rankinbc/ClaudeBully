"""Rescue confabulation curve: cumulative hedged and unhedged fragments per target reply."""

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot

from claude_bully.analysis.load import LoadedRun
from claude_bully.enums import Axis, EventType, Speaker

FILE_NAME = "rescue_confabulation.png"


def _rescue_cells(loaded: LoadedRun) -> list[str]:
    return [c for c in loaded.condition_cells() if type(loaded.strategies[c]).axis is Axis.rescue]


def rescue_curve(loaded: LoadedRun, out_dir: Path) -> Path | None:
    cells = [c for c in _rescue_cells(loaded) if any(k[0] == c for k in loaded.conversations)]
    if not cells:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for cell_id in cells:
        # cumulative counts per target-reply ordinal, averaged across reps
        hedged_sum: dict[int, float] = defaultdict(float)
        unhedged_sum: dict[int, float] = defaultdict(float)
        reps = 0
        model = ""
        for (cid, rep), conv in loaded.conversations.items():
            if cid != cell_id:
                continue
            reps += 1
            events = loaded.events.get((cid, rep), [])
            by_turn: dict[int, tuple[int, int]] = defaultdict(lambda: (0, 0))
            for e in events:
                if e.type is EventType.confabulation:
                    h, u = by_turn[e.turn_index]
                    by_turn[e.turn_index] = (h + 1, u) if e.hedged else (h, u + 1)
            h_cum = u_cum = 0
            ordinal = 0
            for t in conv.turns:
                if t.speaker is not Speaker.target:
                    continue
                model = model or (t.model or "")
                h, u = by_turn.get(t.index, (0, 0))
                h_cum += h
                u_cum += u
                hedged_sum[ordinal] += h_cum
                unhedged_sum[ordinal] += u_cum
                ordinal += 1
        if not reps:
            continue
        xs = sorted(hedged_sum)
        label = f"{cell_id} ({model})" if model else cell_id
        ax.plot(xs, [hedged_sum[x] / reps for x in xs], marker="o", label=f"{label} hedged")
        ax.plot(
            xs,
            [unhedged_sum[x] / reps for x in xs],
            marker="s",
            linestyle="--",
            label=f"{label} unhedged",
        )
    ax.set_xlabel("target reply")
    ax.set_ylabel("cumulative confabulations")
    ax.set_title("Rescue: confabulation under leading questions")
    ax.legend(fontsize=7)
    fig.tight_layout()
    path = out_dir / FILE_NAME
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
