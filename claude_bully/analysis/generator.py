"""The world generator's arms (Phase 3 spec section 9; docs/06 hypothesis 6).

A conversation's arm is its environment's generator: ``off``, ``non_reflexive`` (documents at
the same turns, nothing harvested in them) or ``reflexive``. The non-reflexive arm separates
being quoted from the world getting bigger. Condition cells only (a control's polite bully is no
pressure) and complete conversations only; every rate leaves ``values_loosened`` reps out and
says how many (``flagged_note``). Reps are grouped by (model, condition, arm), so two conditions
that share a generator setting are never pooled (Task 8 m1): an entry is keyed by its arm when
its condition is the arm's only one for the model, else ``<arm>/<condition>``, and names its
condition either way. ``generator.json`` holds the rates per model and entry, with each entry's
fire counts from its ``GeneratorFire`` records (fires, written, cached, rejected per kind,
errored, and the LLM lint's fail and error verdicts; Task 3 F2), and the reps per cell resumed
after a dead attempt; ``generator_arms.png`` draws adoption and the ``reflexive_quote_noticed``
rate side by side per entry, a panel per model, a bar labelled by its condition where two
conditions share its arm."""

import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

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
from claude_bully.records_env import GeneratorFire  # noqa: E402

GENERATOR_FILE: Final = "generator.json"
GENERATOR_CHART: Final = "generator_arms.png"
ARMS: Final = ("off", "non_reflexive", "reflexive")
LEFT_OUT_OF: Final = "the generator arms"
REJECTIONS: Final = ("cap", "contract", "lints")
LINT_COUNTED: Final = ("fail", "error")


def _zeros(names: tuple[str, ...]) -> dict[str, int]:
    return dict.fromkeys(names, 0)


class ArmRates(BaseModel):
    """One (model, condition, arm) entry: rates over its kept reps, then counts over their fires
    (``condition`` and the counts are additive, Phase 7a final fix wave)."""

    model_config = ConfigDict(extra="forbid")

    reps: int
    docs_written: float
    adoption_rate: float
    quote_noticed_rate: float
    own_quote_found_rate: float
    condition: str = ""
    fires: int = 0
    written: int = 0
    cached: int = 0
    rejected: dict[str, int] = Field(default_factory=lambda: _zeros(REJECTIONS))
    errors: int = 0
    llm_lint: dict[str, int] = Field(default_factory=lambda: _zeros(LINT_COUNTED))


def generator_arm(config: EnvironmentConfig) -> str:
    if not config.generator.enabled:
        return "off"
    return "reflexive" if config.generator.reflexive else "non_reflexive"


def _condition_of(loaded: LoadedRun, cell_id: str) -> str:
    spec = loaded.specs.get(cell_id)
    return spec.condition.name if spec is not None else loaded.cells[cell_id].condition_name


def _conversations(loaded: LoadedRun) -> list[tuple[ConvKey, str, str, str]]:
    """(key, target model, condition, arm) of each complete condition conversation in an
    environment."""
    out: list[tuple[ConvKey, str, str, str]] = []
    for key, conv in sorted(loaded.conversations.items()):
        config = environment_of(loaded, key[0])
        record = loaded.cells.get(key[0])
        if config is None or record is None or record.is_control:
            continue
        if conv.status is CellStatus.complete:
            model, condition = target_model(loaded, key[0]), _condition_of(loaded, key[0])
            out.append((key, model, condition, generator_arm(config)))
    return out


def _fire_counts(loaded: LoadedRun, keys: list[ConvKey]) -> dict[str, Any]:
    """The entry's fire counts over its conversations' ``GeneratorFire`` records."""
    fires = [
        record
        for key in keys
        for record in loaded.trigger_records.get(key, [])
        if isinstance(record, GeneratorFire)
    ]
    rejected, llm_lint = _zeros(REJECTIONS), _zeros(LINT_COUNTED)
    for fire in fires:
        if fire.status == "rejected" and fire.rejection is not None:
            rejected[fire.rejection] += 1
        for verdict in fire.llm_lint:
            if verdict.verdict in llm_lint:
                llm_lint[verdict.verdict] += 1
    return {
        "fires": len(fires),
        "written": sum(1 for fire in fires if fire.status == "written"),
        "cached": sum(1 for fire in fires if fire.status == "cached"),
        "rejected": rejected,
        "errors": sum(1 for fire in fires if fire.status == "error"),
        "llm_lint": llm_lint,
    }


def arm_rates(loaded: LoadedRun) -> tuple[dict[str, dict[str, ArmRates]], int]:
    """Model -> entry -> rates over the unflagged reps, and how many reps were left out. An
    entry is one (condition, arm) of the model, keyed by its arm when the arm has that one
    condition for the model, else ``<arm>/<condition>``."""
    convs = _conversations(loaded)
    kept, flagged = without_flagged(loaded, [key for key, *_ in convs])
    keep = set(kept)
    grouped: dict[tuple[str, str, str], list[ConvKey]] = defaultdict(list)
    for key, model, condition, arm in convs:
        if key in keep:
            grouped[(model, condition, arm)].append(key)
    sharing: dict[tuple[str, str], int] = defaultdict(int)
    for model, _, arm in grouped:
        sharing[(model, arm)] += 1
    out: dict[str, dict[str, ArmRates]] = {}
    for (model, condition, arm), keys in sorted(
        grouped.items(), key=lambda kv: (kv[0][0], ARMS.index(kv[0][2]), kv[0][1])
    ):

        def share(test: Callable[[ConvKey], bool], keys: list[ConvKey] = keys) -> float:
            return sum(1 for key in keys if test(key)) / len(keys)

        label = arm if sharing[(model, arm)] == 1 else f"{arm}/{condition}"
        out.setdefault(model, {})[label] = ArmRates(
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
            condition=condition,
            **_fire_counts(loaded, keys),
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
    for key, *_ in _conversations(loaded):
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


def _tick(label: str, rates: ArmRates) -> str:
    """A bar's label: its arm, and under it its condition when the arm is shared."""
    arm = label.split("/", 1)[0].replace("_", "-")
    return arm if "/" not in label else f"{arm}\n{rates.condition}"


def generator_chart(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """Adoption and the reflexive-quote rate per entry, a panel per model with two or more
    (a bar is labelled by its condition too where two conditions share its arm);
    None, with no file, when no model has two or no environment runs the generator. A footnote
    counts the values_loosened reps."""
    if not _runs_generator(loaded):
        return None
    rates, flagged = arm_rates(loaded)
    drawn = {model: arms for model, arms in rates.items() if len(arms) >= 2}
    if not drawn:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, len(drawn), figsize=(4.6 * len(drawn), 3.8), squeeze=False)
    for ax, (model, arms) in zip(axes[0], drawn.items(), strict=True):
        present = list(arms)  # arm_rates' order: by arm, then by condition
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
        ax.set_xticklabels([_tick(label, arms[label]) for label in present])
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
