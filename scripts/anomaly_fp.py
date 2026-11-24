"""The catalog's false-positive rate on control conversations (Phase 6 spec 16; Task 7a).

    uv run python scripts/anomaly_fp.py RUN... [--runs-root DIR] [--ceiling 0.02]

For each run: ``load_run``, then per catalog class the flags of
``detect_anomalies(ctx_for(...))`` over every complete control conversation, divided by the
target turns of the control conversations the class is applicable to (``applicable``). A class
no control conversation can show has no rate: ``n/a``, never zero. One line per class, the runs
pooled; the exit code is 1 when a rate is over the ceiling (the rung's 2 percent), else 0. No
model call: the heuristic detectors only, no provider is built.
"""

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_bully.analysis.load import load_run  # noqa: E402
from claude_bully.enums import CellStatus  # noqa: E402
from claude_bully.metrics.anomalies import CATALOG, applicable, detect_anomalies  # noqa: E402
from claude_bully.metrics.anomalies._common import ctx_for  # noqa: E402
from claude_bully.paths import DEFAULT_RUNS_ROOT  # noqa: E402

if TYPE_CHECKING:
    from claude_bully.analysis.load import LoadedRun

CEILING: Final = 0.02

Rates = dict[str, dict[str, float | int]]


def _counts(loaded: "LoadedRun") -> dict[str, tuple[int, int]]:
    """Per class, (control turns, flags) over the run's complete control conversations."""
    counts = {cls.value: (0, 0) for cls in CATALOG}
    for key, conv in sorted(loaded.conversations.items()):
        record = loaded.cells.get(key[0])
        if record is None or not record.is_control or conv.status is not CellStatus.complete:
            continue
        ctx = ctx_for(loaded, key)
        flags = detect_anomalies(ctx)
        turns = len(ctx.targets())
        for cls in CATALOG:
            if not applicable(cls, ctx.cell):
                continue
            seen, flagged = counts[cls.value]
            counts[cls.value] = (seen + turns, flagged + sum(f.class_ is cls for f in flags))
    return counts


def _rates(counts: dict[str, tuple[int, int]]) -> Rates:
    return {
        cls: {
            "control_turns": turns,
            "flags": flags,
            "rate": flags / turns if turns else math.nan,
        }
        for cls, (turns, flags) in counts.items()
    }


def control_rates(loaded: "LoadedRun") -> Rates:
    """Per catalog class (its value): ``control_turns`` (the target turns of the complete control
    conversations the class is applicable to), ``flags`` (its flags there) and ``rate`` (flags per
    control turn; NaN, printed ``n/a``, when there is no such turn)."""
    return _rates(_counts(loaded))


def format_rates(rates: Rates) -> list[str]:
    """One line per class, in catalog order."""
    lines = []
    for cls, row in rates.items():
        rate = row["rate"]
        shown = "n/a" if math.isnan(rate) else f"{rate:.4f}"
        lines.append(
            f"{cls}: control_turns={row['control_turns']} flags={row['flags']} rate={shown}"
        )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("runs", nargs="+", metavar="RUN")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--ceiling", type=float, default=CEILING)
    args = parser.parse_args(argv)
    pooled = {cls.value: (0, 0) for cls in CATALOG}
    for run in args.runs:
        for cls, (turns, flags) in _counts(load_run(args.runs_root / run)).items():
            seen, flagged = pooled[cls]
            pooled[cls] = (seen + turns, flagged + flags)
    rates = _rates(pooled)
    for line in format_rates(rates):
        print(line)
    over = [cls for cls, row in rates.items() if row["rate"] > args.ceiling]
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
