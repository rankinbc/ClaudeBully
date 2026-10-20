"""Load a run directory into memory and recompute every cheap metric and event."""

from dataclasses import dataclass, field
from pathlib import Path

from claude_bully.config import Experiment
from claude_bully.enums import EventType, MetricId
from claude_bully.metrics.events import detect_events
from claude_bully.metrics.judge import CaptureJudgement, JudgeError, PairJudgement
from claude_bully.metrics.turn import TurnMetrics, compute_turn_metrics
from claude_bully.records import CellRecord, Conversation, Event, RunRecord
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import Strategy
from claude_bully.strategies.factory import build_strategy, ensure_registered

ConvKey = tuple[str, int]


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
            spec.condition, seed=experiment.seed, turn_budget=experiment.turn_budget
        )
        for rep in store.list_reps(cell_id):
            conversations[(cell_id, rep)] = store.read_conversation(cell_id, rep)
    turn_metrics = {key: compute_turn_metrics(conv) for key, conv in conversations.items()}
    events = {
        key: detect_events(conv, relevant=type(strategies[key[0]]).relevant_events)
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
    )
