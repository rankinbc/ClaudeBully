"""The world generator's arms (Phase 3 spec section 9; docs/06 hypothesis 6).

A conversation's arm is its environment's generator: ``off``, ``non_reflexive`` (documents at
the same turns, nothing harvested in them) or ``reflexive``. The non-reflexive arm separates
being quoted from the world getting bigger. Condition cells only (a control's polite bully is no
pressure) and complete conversations only; every rate leaves ``values_loosened`` reps out and
says how many (``flagged_note``). ``generator.json`` holds the rates per model and arm and the
reps per cell resumed after a dead attempt; ``generator_arms.png`` draws adoption and the
``reflexive_quote_noticed`` rate side by side per arm, a panel per model."""

import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot
from pydantic import BaseModel, ConfigDict  # noqa: E402

from claude_bully.analysis.load import ConvKey, LoadedRun, count_resumed  # noqa: E402
from claude_bully.analysis.progression import (  # noqa: E402
    environment_of,
    flagged_note,
    summarize,
    target_model,
    without_flagged,
)
from claude_bully.enums import CellStatus, EventType  # noqa: E402
from claude_bully.environments.config import EnvironmentConfig  # noqa: E402
from claude_bully.metrics.events.environment import is_belief_adoption  # noqa: E402

GENERATOR_FILE: Final = "generator.json"
GENERATOR_CHART: Final = "generator_arms.png"
ARMS: Final = ("off", "non_reflexive", "reflexive")
LEFT_OUT_OF: Final = "the generator arms"


class ArmRates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reps: int
    docs_written: float
    adoption_rate: float
    quote_noticed_rate: float
    own_quote_found_rate: float


def generator_arm(config: EnvironmentConfig) -> str:
    if not config.generator.enabled:
        return "off"
    return "reflexive" if config.generator.reflexive else "non_reflexive"


def _conversations(loaded: LoadedRun) -> list[tuple[ConvKey, str, str]]:
    """(key, target model, arm) of each complete condition conversation in an environment."""
    out: list[tuple[ConvKey, str, str]] = []
    for key, conv in sorted(loaded.conversations.items()):
        config = environment_of(loaded, key[0])
        record = loaded.cells.get(key[0])
        if config is None or record is None or record.is_control:
            continue
        if conv.status is CellStatus.complete:
            out.append((key, target_model(loaded, key[0]), generator_arm(config)))
    return out


def arm_rates(loaded: LoadedRun) -> tuple[dict[str, dict[str, ArmRates]], int]:
    """Model -> arm -> rates over the unflagged reps, and how many reps were left out."""
    convs = _conversations(loaded)
    kept, flagged = without_flagged(loaded, [key for key, _, _ in convs])
    keep = set(kept)
    grouped: dict[tuple[str, str], list[ConvKey]] = defaultdict(list)
    for key, model, arm in convs:
        if key in keep:
            grouped[(model, arm)].append(key)
    out: dict[str, dict[str, ArmRates]] = {}
    for (model, arm), keys in sorted(
        grouped.items(), key=lambda kv: (kv[0][0], ARMS.index(kv[0][1]))
    ):

        def share(test: Callable[[ConvKey], bool], keys: list[ConvKey] = keys) -> float:
            return sum(1 for key in keys if test(key)) / len(keys)

        out.setdefault(model, {})[arm] = ArmRates(
            reps=len(keys),
            docs_written=sum(len(loaded.generated.get(key, [])) for key in keys) / len(keys),
            adoption_rate=share(
                lambda key: any(is_belief_adoption(e) for e in loaded.events.get(key, []))
            ),
            quote_noticed_rate=share(
                lambda key: any(
                    e.type is EventType.reflexive_quote_noticed for e in loaded.events.get(key, [])
                )
            ),
            own_quote_found_rate=share(
                lambda key: summarize(loaded, key).own_quote_found_turn is not None
            ),
        )
    return out, flagged


def _runs_generator(loaded: LoadedRun) -> bool:
    return any(env.generator.enabled for env in loaded.experiment.environments.values())


def write_generator(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """``generator.json``; None, with no file, when no environment runs the generator."""
    if not _runs_generator(loaded):
        return None
    rates, flagged = arm_rates(loaded)
    cells: dict[str, list[ConvKey]] = defaultdict(list)
    for key, _, _ in _conversations(loaded):
        cells[key[0]].append(key)
    payload: dict[str, Any] = {
        "arms": {
            model: {arm: r.model_dump() for arm, r in arms.items()} for model, arms in rates.items()
        },
        "values_loosened_left_out": flagged,
        "note": flagged_note(flagged, LEFT_OUT_OF),
        "resumed_after_dead_attempt": {
            cell: count_resumed(loaded, keys) for cell, keys in sorted(cells.items())
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / GENERATOR_FILE
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path


def generator_chart(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """Adoption and the reflexive-quote rate per arm, a panel per model with two arms or more;
    None, with no file, when no model has two. A footnote counts the values_loosened reps."""
    rates, flagged = arm_rates(loaded)
    drawn = {model: arms for model, arms in rates.items() if len(arms) >= 2}
    if not drawn:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, len(drawn), figsize=(4.6 * len(drawn), 3.8), squeeze=False)
    for ax, (model, arms) in zip(axes[0], drawn.items(), strict=True):
        present = [arm for arm in ARMS if arm in arms]
        xs = range(len(present))
        ax.bar(
            [x - 0.2 for x in xs],
            [arms[a].adoption_rate for a in present],
            width=0.4,
            label="belief adoption",
        )
        ax.bar(
            [x + 0.2 for x in xs],
            [arms[a].quote_noticed_rate for a in present],
            width=0.4,
            label="reflexive quote noticed",
        )
        ax.set_xticks(list(xs))
        ax.set_xticklabels([a.replace("_", "-") for a in present])
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel("share of reps")
        ax.set_title(model)
    axes[0][0].legend(fontsize=7, loc="upper left")
    fig.suptitle("World generator: off, non-reflexive, reflexive")
    note = flagged_note(flagged, LEFT_OUT_OF)
    if note is not None:
        fig.text(0.01, 0.01, note, fontsize=7)
        fig.tight_layout(rect=(0.0, 0.04, 1.0, 0.95))
    else:
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    path = out_dir / GENERATOR_CHART
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
