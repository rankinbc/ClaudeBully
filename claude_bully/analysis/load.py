"""Load a run directory into memory and recompute every cheap metric and event.

Everything comes from the run directory: an environment conversation's tool calls, authority
calls and trigger records from its JSONL streams, and its ``World`` from ``rep{k}.world.json``
(never from the repo's world files, which may have changed since the run). An environment cell's
strategy is built from the same snapshot: the clock its sheet records and the premise sheet the
bully spoke from (``premise_sheet``, carry m1), never from ``data/worlds``. A Poisoned Well
cell's strategy is pinned to its quirk entries and sheet as a rep recorded them (``session_refs``,
P46), never the live bank.
"""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from claude_bully.config import ConditionConfig, Experiment
from claude_bully.enums import EventType, MetricId
from claude_bully.environments.config import ClockConfig
from claude_bully.environments.world import World, world_from_snapshot
from claude_bully.metrics.events import detect_events
from claude_bully.metrics.events._common import AuthorityFallback
from claude_bully.metrics.judge import CaptureJudgement, JudgeError, PairJudgement
from claude_bully.metrics.ratings import RatingVerdict
from claude_bully.metrics.turn import TurnMetrics, compute_turn_metrics
from claude_bully.planner.bundle import register_plan_personas
from claude_bully.providers.ledger import LEDGER_FILE, Ledger, LedgerLine
from claude_bully.records import CellRecord, Conversation, Event, RunRecord
from claude_bully.records_env import (
    AuthorityCall,
    GeneratedDoc,
    ResumeRecord,
    ToolCall,
    TriggerStreamRecord,
)
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import Strategy
from claude_bully.strategies.factory import (
    build_strategy,
    ensure_registered,
    premise_sheet_model,
)
from claude_bully.strategies.premises.poisoned_well import pin_recorded, poisoned_well_part

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
    authority_calls: dict[ConvKey, list[AuthorityCall]] = field(default_factory=dict)
    trigger_records: dict[ConvKey, list[TriggerStreamRecord]] = field(default_factory=dict)
    worlds: dict[ConvKey, World | None] = field(default_factory=dict)
    # the documents the world generator wrote (Phase 3); empty for a plain conversation
    generated: dict[ConvKey, list[GeneratedDoc]] = field(default_factory=dict)
    # the Sanctuary's request bank as the rep's world record names it (m5); None without one
    request_banks: dict[ConvKey, str | None] = field(default_factory=dict)
    # the run's provider calls (Phase 7); empty for a run with no ledger
    ledger: list[LedgerLine] = field(default_factory=list)
    # per conversation, the candidate turns the authority fallback was asked on and could
    # not answer (Phase 7, P36a); empty without the fallback
    fallback_failed: dict[ConvKey, int] = field(default_factory=dict)
    # the judge's rating verdicts by ``<cell>/<rep>/<kind>/<turn>`` (Phase 4, ``analyze
    # --ratings`` or an existing ``ratings.json``); empty otherwise
    ratings: dict[str, RatingVerdict] = field(default_factory=dict)
    # the turns whose contradiction judge failed, per conversation, as the rep's world record
    # names them (Phase 4 Task 12, ``poisoned_well.contradictions_degraded``); empty without one
    contradictions_degraded: dict[ConvKey, list[int]] = field(default_factory=dict)

    def control_for(self, cell_id: str) -> str | None:
        return self.cells[cell_id].control_cell_id

    def condition_cells(self) -> list[str]:
        return sorted(c for c, rec in self.cells.items() if not rec.is_control)

    def reps_of(self, cell_id: str) -> list[int]:
        return sorted(rep for (cid, rep) in self.conversations if cid == cell_id)

    def resumes(self, key: ConvKey) -> list[ResumeRecord]:
        """The conversation's ``resume`` records: each time it redid a dead attempt, whose
        prompt its ``claude -p`` session may still hold. Empty for an unbroken rep."""
        return [r for r in self.trigger_records.get(key, []) if isinstance(r, ResumeRecord)]


def count_resumed(loaded: LoadedRun, keys: Iterable[ConvKey]) -> int:
    """How many of ``keys`` redid a dead attempt (``LoadedRun.resumes``), for the Phase 2
    analyses to report beside their flagged counts."""
    return sum(1 for key in keys if loaded.resumes(key))


def relevant_for(
    loaded: LoadedRun, cell_id: str
) -> tuple[frozenset[MetricId], frozenset[EventType]]:
    cls = type(loaded.strategies[cell_id])
    return cls.relevant_metrics, cls.relevant_events


def load_run(run_dir: Path, *, authority_fallback: AuthorityFallback | None = None) -> LoadedRun:
    """The run directory in memory, every cheap metric and event recomputed.
    ``authority_fallback`` (Phase 7) is the authority family's analysis-time LLM fallback,
    asked on candidate turns."""
    ensure_registered()
    store = RunStore(run_dir.parent, run_dir.name)
    run = store.read_run()
    if run.plan is not None:  # a run made from a plan bundle: its personas, from run.json alone
        register_plan_personas(run.plan.personas)
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
        clock, sheet = _strategy_inputs(store, cell_id, spec.condition, experiment)
        strategies[cell_id] = build_strategy(
            spec.condition,
            seed=experiment.seed,
            turn_budget=experiment.turn_budget,
            environments=experiment.environments,
            clock=clock,
            premise_sheet=sheet,
            # a rep with no snapshot sheet yet (or from before Task 3): the premise's default,
            # explicitly; nothing analysis computes reads the sheet
            default_premise_sheet=sheet is None,
            target_model=spec.target.model,
        )
        _pin_poisoned_well(strategies[cell_id], record, store.list_reps(cell_id))
        for rep in store.list_reps(cell_id):
            conversations[(cell_id, rep)] = store.read_conversation(cell_id, rep)
    tool_calls, authority_calls, trigger_records, worlds = _environment_context(
        store, cells, conversations
    )
    generated = {
        key: store.read_generated(*key) if is_environment(cells, conv) else []
        for key, conv in conversations.items()
    }
    world_records = {key: store.read_world_record(*key) for key in conversations}
    request_banks = {key: recorded_request_bank(world_records[key]) for key in conversations}
    contradictions_degraded = {
        key: turns
        for key in conversations
        if (turns := recorded_degraded_turns(world_records[key])) is not None
    }
    turn_metrics = {key: compute_turn_metrics(conv) for key, conv in conversations.items()}
    events: dict[ConvKey, list[Event]] = {}
    fallback_failed: dict[ConvKey, int] = {}
    for key, conv in conversations.items():
        if key[0] not in strategies:
            continue
        failed_before = authority_fallback.failures if authority_fallback is not None else 0
        events[key] = detect_events(
            conv,
            relevant=type(strategies[key[0]]).relevant_events,
            tool_calls=tool_calls[key],
            trigger_records=trigger_records[key],
            world=worlds[key],
            authority_calls=authority_calls[key],
            request_bank=request_banks[key],
            authority_fallback=authority_fallback,
        )
        if authority_fallback is not None:
            fallback_failed[key] = authority_fallback.failures - failed_before
    ledger = Ledger(run_dir / LEDGER_FILE).lines()
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
        authority_calls=authority_calls,
        trigger_records=trigger_records,
        worlds=worlds,
        generated=generated,
        request_banks=request_banks,
        ledger=ledger,
        fallback_failed=fallback_failed,
        contradictions_degraded=contradictions_degraded,
    )


def _pin_poisoned_well(strategy: Strategy, record: CellRecord, reps: Iterable[int]) -> None:
    """A Poisoned Well cell's strategy speaks from its lowest rep's recorded refs (P46), never
    the live bank and sheet, which may have changed since (an entry marked stale, reworded or
    removed). A cell none of whose reps recorded refs keeps its lazy, unread refs: nothing
    ``load_run`` computes reads them (``judge_window``, ``relevant_events``), and analysis reads
    entry ids and families from the ``QuirkAttempt`` records."""
    part = poisoned_well_part(strategy)
    if part is None:
        return
    for rep in sorted(reps):
        if pin_recorded(part, record.session_refs, rep):
            return


def recorded_request_bank(payload: Mapping[str, Any] | None) -> str | None:
    """The Sanctuary's request bank a rep's world record names (``authority.request_bank``,
    m5); None for a rep with no snapshot, no Sanctuary, or a record from before Task 9."""
    authority = (payload or {}).get("authority")
    bank = authority.get("request_bank") if isinstance(authority, dict) else None
    return bank if isinstance(bank, str) else None


def recorded_degraded_turns(payload: Mapping[str, Any] | None) -> list[int] | None:
    """The turns whose contradiction judge failed, as a rep's world record names them
    (``poisoned_well.contradictions_degraded``, Phase 4 Task 12); None for a rep with no
    snapshot, no Poisoned Well watch, or a record from before Task 12."""
    block = (payload or {}).get("poisoned_well")
    turns = block.get("contradictions_degraded") if isinstance(block, dict) else None
    if not isinstance(turns, list):
        return None
    return sorted(t for t in turns if isinstance(t, int))


def _strategy_inputs(
    store: RunStore, cell_id: str, cond: ConditionConfig, experiment: Experiment
) -> tuple[ClockConfig | None, BaseModel | None]:
    """An environment cell's clock and premise sheet, read from the first of its reps' snapshots
    that has a world sheet: the effective clock the run served and the premise sheet the bully
    was given. (None, None) for a plain cell, or for one with no such snapshot yet: the strategy
    is then built without them, and no world file is read."""
    if cond.environment is None:
        return None, None
    model = premise_sheet_model(cond, experiment.environments)
    for rep in store.list_reps(cell_id):
        payload = store.read_world_record(cell_id, rep)
        if not payload or "sheet" not in payload:
            continue
        clock = ClockConfig.model_validate(payload["sheet"]["clock"])
        raw = payload.get("premise_sheet")
        sheet = model.model_validate(raw) if model is not None and raw is not None else None
        return clock, sheet
    return None, None


def is_environment(cells: dict[str, CellRecord], conv: Conversation) -> bool:
    record = cells.get(conv.cell_id)
    return conv.environment_name is not None or (
        record is not None and record.environment is not None
    )


def _environment_context(
    store: RunStore, cells: dict[str, CellRecord], conversations: dict[ConvKey, Conversation]
) -> tuple[
    dict[ConvKey, list[ToolCall]],
    dict[ConvKey, list[AuthorityCall]],
    dict[ConvKey, list[TriggerStreamRecord]],
    dict[ConvKey, World | None],
]:
    """Each conversation's tool calls, authority calls, trigger records and world, read from the
    run directory (``RunStore``'s readers). A snapshot written before the world sheet was kept
    beside it gives no world; the detectors that need one skip, and one warning per run says so.
    A rep with no authority stream (no tier enabled, or a run before Phase 2) has no calls."""
    tool_calls: dict[ConvKey, list[ToolCall]] = {}
    authority_calls: dict[ConvKey, list[AuthorityCall]] = {}
    trigger_records: dict[ConvKey, list[TriggerStreamRecord]] = {}
    worlds: dict[ConvKey, World | None] = {}
    sheetless: list[str] = []
    for key, conv in conversations.items():
        cell_id, rep = key
        if not is_environment(cells, conv):
            tool_calls[key], authority_calls[key], trigger_records[key] = [], [], []
            worlds[key] = None
            continue
        tool_calls[key] = store.read_tool_calls(cell_id, rep)
        authority_calls[key] = store.read_authority_calls(cell_id, rep)
        trigger_records[key] = store.read_trigger_records(cell_id, rep)
        payload = store.read_world_record(cell_id, rep)
        world = world_from_snapshot(payload, store.cell_dir(cell_id)) if payload else None
        worlds[key] = world
        if world is None:
            sheetless.append(f"{cell_id}/rep{rep}")
    if sheetless:
        log.warning(
            "run %s: %d environment conversation(s) have no world sheet in their snapshot "
            "(%s). Lost for them: the declared inconsistencies (inconsistency_caught skips), the "
            "mole (mole_found and mole_believed skip), the document titles and outlets (the "
            "detectors name documents by ids, urls and paths only) and the ladder "
            "(max_rung_reached is None and rungs are ordered as they fired)",
            store.run_id,
            len(sheetless),
            ", ".join(sheetless),
        )
    return tool_calls, authority_calls, trigger_records, worlds
