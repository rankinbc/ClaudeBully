"""Load a run directory into memory and recompute every cheap metric and event.

Everything comes from the run directory: an environment conversation's tool calls and trigger
records from its JSONL streams, and its ``World`` from ``rep{k}.world.json`` (never from the
repo's world files, which may have changed since the run).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from claude_bully.config import Experiment
from claude_bully.enums import EventType, MetricId
from claude_bully.environments.world import World, world_from_snapshot
from claude_bully.metrics.events import detect_events
from claude_bully.metrics.judge import CaptureJudgement, JudgeError, PairJudgement
from claude_bully.metrics.turn import TurnMetrics, compute_turn_metrics
from claude_bully.records import CellRecord, Conversation, Event, RunRecord
from claude_bully.records_env import ToolCall, TriggerStreamRecord
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import Strategy
from claude_bully.strategies.factory import build_strategy, ensure_registered

ConvKey = tuple[str, int]

log = logging.getLogger(__name__)


@dataclass
class LoadedRun:
    run: RunRecord
    experiment: Experiment
    cells: dict[str, CellRecord]
    specs: dict[str, CellSpec]
    conversations: dict[ConvKey, Conversation]
    turn_metrics: dict[ConvKey, list[TurnMetrics]]
    events: dict[ConvKey, list[Event]]
    strategies: dict[str, Strategy]
    judgements: dict[ConvKey, PairJudgement | JudgeError] = field(default_factory=dict)
    captures: dict[tuple[str, int, str], CaptureJudgement] = field(default_factory=dict)
    # environment context per conversation (empty or None for a plain one)
    tool_calls: dict[ConvKey, list[ToolCall]] = field(default_factory=dict)
    trigger_records: dict[ConvKey, list[TriggerStreamRecord]] = field(default_factory=dict)
    worlds: dict[ConvKey, World | None] = field(default_factory=dict)

    def control_for(self, cell_id: str) -> str | None:
        return self.cells[cell_id].control_cell_id

    def condition_cells(self) -> list[str]:
        return sorted(c for c, rec in self.cells.items() if not rec.is_control)

    def reps_of(self, cell_id: str) -> list[int]:
        return sorted(rep for (cid, rep) in self.conversations if cid == cell_id)


def relevant_for(
    loaded: LoadedRun, cell_id: str
) -> tuple[frozenset[MetricId], frozenset[EventType]]:
    cls = type(loaded.strategies[cell_id])
    return cls.relevant_metrics, cls.relevant_events


def load_run(run_dir: Path) -> LoadedRun:
    ensure_registered()
    store = RunStore(run_dir.parent, run_dir.name)
    run = store.read_run()
    experiment = Experiment.model_validate(run.experiment)
    specs = {s.cell_id: s for s in expand_cells(experiment)}
    cells: dict[str, CellRecord] = {}
    conversations: dict[ConvKey, Conversation] = {}
    strategies: dict[str, Strategy] = {}
    for cell_id in store.list_cells():
        record = store.read_cell(cell_id)
        cells[cell_id] = record
        spec = specs.get(cell_id)
        if spec is None:
            continue
        strategies[cell_id] = build_strategy(
            spec.condition,
            seed=experiment.seed,
            turn_budget=experiment.turn_budget,
            environments=experiment.environments,
        )
        for rep in store.list_reps(cell_id):
            conversations[(cell_id, rep)] = store.read_conversation(cell_id, rep)
    tool_calls, trigger_records, worlds = _environment_context(store, cells, conversations)
    turn_metrics = {key: compute_turn_metrics(conv) for key, conv in conversations.items()}
    events = {
        key: detect_events(
            conv,
            relevant=type(strategies[key[0]]).relevant_events,
            tool_calls=tool_calls[key],
            trigger_records=trigger_records[key],
            world=worlds[key],
        )
        for key, conv in conversations.items()
        if key[0] in strategies
    }
    return LoadedRun(
        run=run,
        experiment=experiment,
        cells=cells,
        specs=specs,
        conversations=conversations,
        turn_metrics=turn_metrics,
        events=events,
        strategies=strategies,
        tool_calls=tool_calls,
        trigger_records=trigger_records,
        worlds=worlds,
    )


def is_environment(cells: dict[str, CellRecord], conv: Conversation) -> bool:
    record = cells.get(conv.cell_id)
    return conv.environment_name is not None or (
        record is not None and record.environment is not None
    )


def _environment_context(
    store: RunStore, cells: dict[str, CellRecord], conversations: dict[ConvKey, Conversation]
) -> tuple[
    dict[ConvKey, list[ToolCall]],
    dict[ConvKey, list[TriggerStreamRecord]],
    dict[ConvKey, World | None],
]:
    """Each conversation's tool calls, trigger records and world, read from the run directory
    (``RunStore``'s readers). A snapshot written before the world sheet was kept beside it gives
    no world; the detectors that need one skip, and one warning per run says so."""
    tool_calls: dict[ConvKey, list[ToolCall]] = {}
    trigger_records: dict[ConvKey, list[TriggerStreamRecord]] = {}
    worlds: dict[ConvKey, World | None] = {}
    sheetless: list[str] = []
    for key, conv in conversations.items():
        cell_id, rep = key
        if not is_environment(cells, conv):
            tool_calls[key], trigger_records[key], worlds[key] = [], [], None
            continue
        tool_calls[key] = store.read_tool_calls(cell_id, rep)
        trigger_records[key] = store.read_trigger_records(cell_id, rep)
        payload = store.read_world_record(cell_id, rep)
        world = world_from_snapshot(payload, store.cell_dir(cell_id)) if payload else None
        worlds[key] = world
        if world is None:
            sheetless.append(f"{cell_id}/rep{rep}")
    if sheetless:
        log.warning(
            "run %s: %d environment conversation(s) have no world sheet in their snapshot "
            "(%s); inconsistency_caught, mole_found and mole_believed are skipped for them",
            store.run_id,
            len(sheetless),
            ", ".join(sheetless),
        )
    return tool_calls, trigger_records, worlds
