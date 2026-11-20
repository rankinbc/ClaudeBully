"""The divergence outputs (Phase 6 spec 5.5 to 5.7, 6.5, 12.4, 12.5): what the divergence pass
found, written under ``analysis/``.

- ``divergence.jsonl``: one ``DivergenceEvent`` per target turn of each complete conversation, in
  ``(cell_id, rep, turn)`` order. Each line holds the event's fields (spec 5.5): the spans of
  every verdict that has them (``reasoning_span`` and ``reply_span``, of any class, ``aligned``
  included, kept as the judge gave them; D-span checks a concealed verdict's alone) and the
  judge's free-text ``rationale``, either of which may quote the target's reasoning. It is the
  analysis file that may hold reasoning text, by design; every other file here is counts and
  labels.
- ``divergence.json`` (``divergence_report``): counts only, no span. Per target model and
  condition (a control is a condition here, keyed by its own condition name), over complete
  conversations with the ``values_loosened`` reps left out first: the arm, the reps and turns,
  the turns with reasoning by kind, the judged, unjudged and low-confidence counts, each class
  under ``counted_class``, the concealment rate (None, never 0, with no judged turn) and
  ``plan_to_action_latency`` (None until Task 9). Beside them the hedge decomposition and the
  concealed distress by discovery depth of the condition cells (the two entries
  ``hypotheses.py`` reads), the pass's note and the reps per cell that redid a dead attempt.
- ``channels.json`` (``write_channels``): counts only, per model, condition and event type, of
  the events found in the reply alone, in both channels and in the reasoning alone.
- ``concealment_by_arm.png``: the concealed classes' shares of the judged turns with reasoning,
  a stacked bar per condition labelled by its arm (``arms.arm_labels``).

Every text file goes through ``atomic.write_atomic``. Every output describes the latest analysis
(fix round 1, M4): an analysis that does not write one of these files removes the one an earlier
analysis left (``Path.unlink``, as ``expected.json`` is removed). Each removal is a single step,
so a kill between two leaves files that the next analysis removes in turn. A run with no
reasoning analysed without ``--divergence`` therefore has none of them."""

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - backend must be set before pyplot

from claude_bully.analysis.arms import arm_labels, ignition_arm  # noqa: E402
from claude_bully.analysis.load import ConvKey, LoadedRun, count_resumed  # noqa: E402
from claude_bully.analysis.progression import (  # noqa: E402
    LAYER_DEPTH,
    flagged_note,
    target_model,
    without_flagged,
)
from claude_bully.atomic import write_atomic  # noqa: E402
from claude_bully.enums import (  # noqa: E402
    CellStatus,
    Channel,
    DivergenceClass,
    EventType,
    Speaker,
    TriggerCategory,
)
from claude_bully.metrics.divergence import (  # noqa: E402
    CONCEALED,
    DIVERGENCE_MIN_CONFIDENCE,
    DIVERGENCE_PROMPT_VERSION,
    PASS_CACHE_ONLY,
    DivergenceEvent,
    concealment_rate,
    counted_class,
)
from claude_bully.records_env import Discovery, TriggerEvent  # noqa: E402

DIVERGENCE_FILE: Final = "divergence.json"  # the name ``hypotheses.DIVERGENCE_FILE`` reads
DIVERGENCE_JSONL: Final = "divergence.jsonl"
CHANNELS_FILE: Final = "channels.json"
CONCEALMENT_CHART: Final = "concealment_by_arm.png"
SECTION_HEADING: Final = "## Reasoning and reply"
KINDS: Final = ("full", "summarized", "unknown", "redacted")
CLASSES: Final = tuple(c.value for c in DivergenceClass)
JUDGED_CLASSES: Final = tuple(c for c in CLASSES if c != DivergenceClass.reasoning_absent)
LEFT_OUT_OF: Final = "the concealment shares"
# the chart's three stacks, each the classes it sums
STACKS: Final = (
    ("concealed skepticism", (DivergenceClass.concealed_skepticism,)),
    ("concealed concession", (DivergenceClass.concealed_concession,)),
    (
        "other concealed",
        (
            DivergenceClass.concealed_plan,
            DivergenceClass.concealed_distress,
            DivergenceClass.eval_suspicion_private,
        ),
    ),
)
Y_LABEL: Final = "share of judged turns with reasoning"
SUPTITLE: Final = "Concealment by arm"


# ------------------------------------------------------------------ the conversations read


def _condition(loaded: LoadedRun, cell_id: str) -> str:
    spec = loaded.specs.get(cell_id)
    return spec.condition.name if spec is not None else loaded.cells[cell_id].condition_name


def _complete(loaded: LoadedRun, cell_id: str) -> list[ConvKey]:
    return [
        (cell_id, rep)
        for rep in loaded.reps_of(cell_id)
        if loaded.conversations[(cell_id, rep)].status is CellStatus.complete
    ]


def _rows(loaded: LoadedRun) -> dict[tuple[str, str], tuple[list[str], list[ConvKey], int]]:
    """(model, condition) -> its cells, its kept complete conversations and how many it left
    out flagged, every cell with a spec (controls included), in (model, condition) order."""
    rows: dict[tuple[str, str], tuple[list[str], list[ConvKey], int]] = {}
    for cell_id in sorted(loaded.cells):
        if cell_id not in loaded.specs:
            continue
        kept, flagged = without_flagged(loaded, _complete(loaded, cell_id))
        row = (target_model(loaded, cell_id), _condition(loaded, cell_id))
        cells, keys, left_out = rows.get(row, ([], [], 0))
        rows[row] = ([*cells, cell_id], [*keys, *kept], left_out + flagged)
    return dict(sorted(rows.items()))


def _condition_keys(loaded: LoadedRun) -> dict[str, list[ConvKey]]:
    """Model -> the kept complete conversations of its condition cells (no control)."""
    out: dict[str, list[ConvKey]] = defaultdict(list)
    for cell_id in sorted(loaded.cells):
        if cell_id not in loaded.specs or loaded.cells[cell_id].is_control:
            continue
        kept, _ = without_flagged(loaded, _complete(loaded, cell_id))
        out[target_model(loaded, cell_id)] += kept
    return dict(sorted(out.items()))


def _events(loaded: LoadedRun, keys: Iterable[ConvKey]) -> list[DivergenceEvent]:
    return [e for key in keys for e in loaded.divergence.get(key, [])]


# ------------------------------------------------------------------ divergence.json


def _is_judged(event: DivergenceEvent) -> bool:
    return event.judged and event.class_ not in (None, DivergenceClass.reasoning_absent)


def _row(loaded: LoadedRun, cells: list[str], keys: list[ConvKey], left_out: int) -> dict[str, Any]:
    events = _events(loaded, keys)
    by_kind = dict.fromkeys(KINDS, 0)
    classes = dict.fromkeys(CLASSES, 0)
    for event in events:
        if event.reasoning_kind is not None:
            by_kind[event.reasoning_kind] += 1
        counted = counted_class(event)
        if counted is not None:
            classes[counted.value] += 1
    return {
        "arm": ignition_arm(loaded, cells[0]),
        "reps": len(keys),
        "values_loosened_left_out": left_out,
        "turns": len(events),
        "with_reasoning": sum(
            1 for e in events if e.class_ is not DivergenceClass.reasoning_absent
        ),
        "by_kind": by_kind,
        "judged": sum(1 for e in events if _is_judged(e)),
        "unjudged": sum(1 for e in events if e.class_ is None),
        "low_confidence": sum(
            1
            for e in events
            if _is_judged(e)
            and e.class_ in CONCEALED
            and e.judge_confidence is not None
            and e.judge_confidence < DIVERGENCE_MIN_CONFIDENCE
        ),
        "classes": classes,
        "concealment_rate": concealment_rate(events),
        "plan_to_action_latency": None,  # Task 9
    }


def _hedge_turns(loaded: LoadedRun, key: ConvKey) -> set[int]:
    """The target turns with a ``self_uncertainty`` trigger record or a hedged
    ``premise_concession`` event (the reply channel's, ``LoadedRun.events``)."""
    turns = {
        r.turn
        for r in loaded.trigger_records.get(key, [])
        if isinstance(r, TriggerEvent) and r.category is TriggerCategory.self_uncertainty
    }
    turns |= {
        e.turn_index
        for e in loaded.events.get(key, [])
        if e.type is EventType.premise_concession
        and (e.hedged is True or e.attrs.get("hedged") is True)
    }
    return turns


def _hedge_decomposition(loaded: LoadedRun) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for model, keys in _condition_keys(loaded).items():
        entry = {"hedge_turns": 0, "judged": 0, **dict.fromkeys(JUDGED_CLASSES, 0)}
        for key in keys:
            hedged = _hedge_turns(loaded, key)
            for event in loaded.divergence.get(key, []):
                if event.turn not in hedged:
                    continue
                entry["hedge_turns"] += 1
                counted = counted_class(event)
                if _is_judged(event) and counted is not None:
                    entry["judged"] += 1
                    entry[counted.value] += 1
        out[model] = entry
    return out


def _depth_at(discoveries: list[Discovery], turn: int) -> int:
    """The deepest layer among the discoveries at or before ``turn``, 0 with none."""
    return max((LAYER_DEPTH[d.layer] for d in discoveries if d.turn <= turn), default=0)


def _distress_by_depth(loaded: LoadedRun) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for model, keys in _condition_keys(loaded).items():
        counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        for key in keys:
            found = [r for r in loaded.trigger_records.get(key, []) if isinstance(r, Discovery)]
            for event in loaded.divergence.get(key, []):
                if not _is_judged(event):
                    continue
                tally = counts[_depth_at(found, event.turn)]
                tally[0] += 1
                tally[1] += int(counted_class(event) is DivergenceClass.concealed_distress)
        out[model] = {
            str(depth): {
                "judged": judged,
                "concealed_distress": distress,
                "share": distress / judged,
            }
            for depth, (judged, distress) in sorted(counts.items())
        }
    return out


def divergence_report(loaded: LoadedRun) -> dict[str, Any]:
    """``divergence.json`` (the module docstring): counts only, never a span. ``analyze_run``
    builds it once and hands it to ``write_divergence``, ``reasoning_section`` and
    ``concealment_chart`` (fix round 1, M2)."""
    models: dict[str, dict[str, Any]] = {}
    for (model, condition), (cells, keys, left_out) in _rows(loaded).items():
        models.setdefault(model, {})[condition] = _row(loaded, cells, keys, left_out)
    return {
        "prompt_version": DIVERGENCE_PROMPT_VERSION,
        "note": loaded.pass_notes.get("divergence", PASS_CACHE_ONLY),
        "models": models,
        "hedge_decomposition": _hedge_decomposition(loaded),
        "distress_by_depth": _distress_by_depth(loaded),
        "resumed_after_dead_attempt": {
            cell_id: count_resumed(loaded, _complete(loaded, cell_id))
            for cell_id in sorted(loaded.cells)
            if cell_id in loaded.specs
        },
    }


def _has_reasoning(loaded: LoadedRun) -> bool:
    return any(
        t.reasoning_available
        for conv in loaded.conversations.values()
        for t in conv.turns
        if t.speaker is Speaker.target
    )


def _remove(path: Path) -> None:
    """A stale output an earlier analysis left, removed (fix round 1, M4)."""
    path.unlink(missing_ok=True)


def write_divergence(
    loaded: LoadedRun,
    out_dir: Path,
    *,
    asked: bool,
    report: Mapping[str, Any] | None = None,
) -> list[Path]:
    """``divergence.jsonl`` and ``divergence.json`` (``report``, built here when not given)
    when any target turn of the run has reasoning or ``asked`` (``--divergence`` was given).
    Otherwise ``[]``, and the two files an earlier analysis left are removed, ``divergence.json``
    first (the file ``hypotheses`` reads), so no output describes an earlier analysis."""
    events_path, report_path = out_dir / DIVERGENCE_JSONL, out_dir / DIVERGENCE_FILE
    if not (asked or _has_reasoning(loaded)):
        _remove(report_path)
        _remove(events_path)
        return []
    lines = [
        json.dumps(event.model_dump(mode="json", by_alias=True), sort_keys=True)
        for key in sorted(loaded.divergence)
        for event in sorted(loaded.divergence[key], key=lambda e: e.turn)
    ]
    if report is None:
        report = divergence_report(loaded)
    write_atomic(events_path, "".join(f"{line}\n" for line in lines))
    write_atomic(report_path, json.dumps(report, indent=1, sort_keys=True))
    return [events_path, report_path]


# ------------------------------------------------------------------ channels.json


def write_channels(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """``channels.json`` (spec 6.5) when any conversation has reasoning; None otherwise, and the
    file an earlier analysis left is removed (fix round 1, M4). Counts only, over the kept reps:
    per event type the reply events, the events of both channels and the reasoning-only events,
    and the reps with it in any channel."""
    path = out_dir / CHANNELS_FILE
    if not _has_reasoning(loaded):
        _remove(path)
        return None
    models: dict[str, dict[str, Any]] = {}
    loosened: list[str] = []
    for (model, condition), (_, keys, _) in _rows(loaded).items():
        counts: dict[str, dict[str, int]] = {}
        reps: dict[str, set[ConvKey]] = defaultdict(set)
        for key in keys:
            channelled = [
                *((e, e.channel.value) for e in loaded.events.get(key, [])),
                *((e, "reasoning_only") for e in loaded.reasoning_events.get(key, [])),
            ]
            for event, slot in channelled:
                name = event.type.value
                entry = counts.setdefault(name, {"reply": 0, "both": 0, "reasoning_only": 0})
                entry["reasoning_only" if slot == Channel.reasoning.value else slot] += 1
                reps[name].add(key)
            if any(
                e.type is EventType.values_loosened for e in loaded.reasoning_events.get(key, [])
            ):
                loosened.append(f"{key[0]}/{key[1]}")
        models.setdefault(model, {})[condition] = {
            name: {**entry, "reps": len(reps[name])}
            for name, entry in sorted(counts.items())
            if any(entry.values())
        }
    payload = {"models": models, "values_loosened_reasoning_only": sorted(loosened)}
    write_atomic(path, json.dumps(payload, indent=1, sort_keys=True))
    return path


# ------------------------------------------------------------------ the chart


def _first_cells(loaded: LoadedRun) -> dict[tuple[str, str], str]:
    """(model, condition) -> its first cell by cell id, the bar's label source; no event read."""
    firsts: dict[tuple[str, str], str] = {}
    for cell_id in sorted(loaded.cells):
        if cell_id in loaded.specs:
            row = (target_model(loaded, cell_id), _condition(loaded, cell_id))
            firsts.setdefault(row, cell_id)
    return firsts


def concealment_chart(
    loaded: LoadedRun, out_dir: Path, report: Mapping[str, Any] | None = None
) -> Path | None:
    """``concealment_by_arm.png`` from ``report``'s rows (``divergence_report``, built here when
    not given): a panel per model with a judged turn with reasoning, a stacked bar per condition
    (``n/a``, no bar, for a condition with no judged turn). None when no turn is judged, and the
    chart an earlier analysis left is removed (fix round 1, M4)."""
    path = out_dir / CONCEALMENT_CHART
    if report is None:
        report = divergence_report(loaded)
    rows: dict[tuple[str, str], dict[str, Any]] = {
        (model, condition): row
        for model, conditions in report["models"].items()
        for condition, row in conditions.items()
    }
    drawn = sorted({model for (model, _), row in rows.items() if row["judged"]})
    if not drawn:
        _remove(path)
        return None
    firsts_of = _first_cells(loaded)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, len(drawn), figsize=(4.8 * len(drawn), 4.0), squeeze=False)
    for ax, model in zip(axes[0], drawn, strict=True):
        present = [(cond, rows[(m, cond)]) for (m, cond) in sorted(rows) if m == model]
        firsts = [firsts_of[(model, cond)] for cond, _ in present]
        labels = arm_labels(loaded, firsts)
        xs = range(len(present))
        bottoms = [0.0] * len(present)
        for label, classes in STACKS:
            heights = [
                sum(row["classes"][c.value] for c in classes) / row["judged"]
                if row["judged"]
                else 0.0
                for _, row in present
            ]
            ax.bar(list(xs), heights, bottom=bottoms, width=0.6, label=label)
            bottoms = [b + h for b, h in zip(bottoms, heights, strict=True)]
        for x, (_, row) in zip(xs, present, strict=True):
            if not row["judged"]:
                ax.text(x, 0.02, "n/a", ha="center", fontsize=8)
        ax.set_xticks(list(xs))
        ax.set_xticklabels([labels[cell] for cell in firsts], fontsize=7)
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel(Y_LABEL)
        ax.set_title(model)
    axes[0][0].legend(fontsize=7, loc="upper left")
    fig.suptitle(SUPTITLE)
    reps = sum(row["reps"] for row in rows.values())
    turns = sum(row["turns"] for row in rows.values())
    absent = sum(row["classes"][DivergenceClass.reasoning_absent.value] for row in rows.values())
    share = f"{absent / turns:.2f}" if turns else "n/a"
    notes = [f"{reps} reps, {turns} turns; reasoning_absent share {share}"]
    flagged = flagged_note(
        sum(row["values_loosened_left_out"] for row in rows.values()), LEFT_OUT_OF
    )
    if flagged is not None:
        notes.append(flagged)
    fig.text(0.01, 0.01, "\n".join(notes), fontsize=7)
    fig.tight_layout(rect=(0.0, 0.04 * len(notes), 1.0, 0.95))
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


# ------------------------------------------------------------------ results.md


def _kinds(by_kind: Mapping[str, int]) -> str:
    shown = [f"{kind} {n}" for kind, n in by_kind.items() if n]
    return ", ".join(shown) if shown else "no kind"


def reasoning_section(report: Mapping[str, Any]) -> str:
    """The ``## Reasoning and reply`` section of ``results.md``: per model a line, then one line
    per condition (``n/a`` for a null rate), then the pass's note."""
    lines = [SECTION_HEADING, ""]
    for model, conditions in report.get("models", {}).items():
        lines += [f"`{model}`:", ""]
        for condition, row in conditions.items():
            rate = row["concealment_rate"]
            shown = "n/a" if rate is None else f"{rate:.2f}"
            lines.append(
                f"- {condition} ({row['arm']}): reasoning on {row['with_reasoning']} of "
                f"{row['turns']} turns ({_kinds(row['by_kind'])}), judged {row['judged']}, "
                f"concealment {shown}"
            )
        lines.append("")
    lines.append(f"Divergence pass: {report.get('note')}.")
    return "\n".join(lines)
