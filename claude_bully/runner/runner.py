"""Runs an experiment: cells x repetitions, resumable, one JSONL line per turn."""

import fnmatch
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from rich.console import Console

from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import CellStatus, IntentMode, Phase, SlotKind, Speaker
from claude_bully.metrics.events.harness import is_end_marker
from claude_bully.metrics.turn import bully_compliance
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    RateLimitError,
    build_provider,
)
from claude_bully.records import CapturedResponse, CellRecord, Conversation, RunRecord, Turn
from claude_bully.runner.bully_engine import BullyEngine
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.prompts import load_bully_framing, load_target_system
from claude_bully.runner.store import RunStore
from claude_bully.runner.tasks import TaskItem, assign_items, load_task_bank, score_item
from claude_bully.runner.turn_plan import Slot, TurnPlan, build_turn_plan
from claude_bully.strategies.base import ConversationState, End, Strategy
from claude_bully.strategies.factory import build_strategy, ensure_registered

ProviderFactory = Callable[[RoleConfig, Path], ChatProvider]

ABORT_NONCOMPLIANCE = "bully_noncompliance"
CONSECUTIVE_SCRIPTED_SEEDING_LIMIT = 3
COMPLIANCE_FLOOR = 0.5
COMPLIANCE_CHECK_AFTER = 10
POST_REVEAL = "post_reveal"
USER_SIDE = (Speaker.bully, Speaker.neutral_user, Speaker.task)


class RateLimitExit(Exception):  # noqa: N818 - name fixed by the plan
    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    cells_total: int
    cells_completed: int = 0
    cells_aborted: int = 0
    cells_skipped: int = 0
    turns_written: int = 0


def is_termination(text: str, completion: Completion | None) -> bool:
    if completion is not None and completion.stop_reason == "refusal":
        return True
    return text.strip() == "" or is_end_marker(text)


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def target_view(turns: list[Turn]) -> list[Message]:
    """The transcript from the target's side; rate-limit markers are not part of it."""
    out: list[Message] = []
    for t in turns:
        if t.bully_meta.get("rate_limit_pause"):
            continue
        role = "assistant" if t.speaker is Speaker.target else "user"
        out.append(Message(role=role, content=t.text))
    return out


def _now() -> datetime:
    return datetime.now(UTC)


class _CellRun:
    """One repetition of one cell. Holds the loop state so resume and abort stay readable."""

    def __init__(
        self,
        *,
        store: RunStore,
        exp: Experiment,
        cell: CellSpec,
        rep: int,
        strategy: Strategy,
        target_provider: ChatProvider,
        bully_engine: BullyEngine,
        plan: TurnPlan,
        items: dict[int, TaskItem],
        target_system: str,
        console: Console | None,
    ) -> None:
        self.store = store
        self.exp = exp
        self.cell = cell
        self.rep = rep
        self.strategy = strategy
        self.target = target_provider
        self.engine = bully_engine
        self.plan = plan
        self.items = items
        self.target_system = target_system
        self.console = console
        self.turns: list[Turn] = store.read_turns(cell.cell_id, rep)
        self.conv = self._load_or_new_conversation()
        self.conversation_id = f"{store.run_id}/{cell.cell_id}/rep{rep}"
        self.bully_speaker = Speaker.neutral_user if cell.is_control else Speaker.bully
        self.bully_ordinal = 0
        self.consecutive_scripted_seeding = 0
        self._last_completion: Completion | None = None

    # -- setup / resume -------------------------------------------------------------------

    def _load_or_new_conversation(self) -> Conversation:
        cls = type(self.strategy)
        if self.store.has_conversation(self.cell.cell_id, self.rep):
            conv = self.store.read_conversation(self.cell.cell_id, self.rep)
            conv.turns = list(self.turns)
            return conv
        return Conversation(
            cell_id=self.cell.cell_id,
            rep=self.rep,
            strategy_name=cls.name,
            axis=cls.axis,
            win_condition=cls.win_condition,
            resilient_behavior=cls.resilient_behavior,
            seeding_turns=self.cell.condition.seeding_turns,
            status=CellStatus.running,
        )

    def _state(self) -> ConversationState:
        return ConversationState(
            turns=list(self.turns),
            bully_turn_index=self.bully_ordinal,
            seeding_turns=self.cell.condition.seeding_turns,
            turn_budget=self.exp.turn_budget,
            seed=self.exp.seed,
        )

    def _replay(self) -> tuple[int, Turn | None]:
        """Advance the strategy through recorded turns.

        Returns the next slot index and the unanswered user-side turn, if any.
        """
        real = [t for t in self.turns if not t.bully_meta.get("rate_limit_pause")]
        slot_idx = 0
        pending: Turn | None = None
        i = 0
        while i < len(real):
            user_turn = real[i]
            reply = real[i + 1] if i + 1 < len(real) else None
            if user_turn.speaker is not Speaker.task:
                self.strategy.next_turn(self._state())
                self.bully_ordinal += 1
                if reply is not None:
                    self.strategy.observe_target(reply)
            if reply is None:
                pending = user_turn
                break
            slot_idx += 1
            i += 2
        return slot_idx, pending

    # -- turn writing ---------------------------------------------------------------------

    def _write(self, turn: Turn) -> None:
        self.store.append_turn(self.cell.cell_id, self.rep, turn)
        self.turns.append(turn)
        self.conv.turns = self.turns
        if self.console is not None:
            who = turn.speaker.value
            self.console.print(
                f"[dim]{self.cell.cell_id} r{self.rep} #{turn.index}[/] {who}: {turn.text[:80]!r}"
            )

    def _next_index(self) -> int:
        return self.turns[-1].index + 1 if self.turns else 0

    def _persist(self) -> None:
        self.conv.turns = self.turns
        self.store.write_conversation(self.cell.cell_id, self.rep, self.conv)

    def _set_status(self, status: CellStatus, reason: str | None = None) -> None:
        self.conv.status = status
        self.conv.abort_reason = reason
        record = self.store.read_cell(self.cell.cell_id)
        record.rep_status[self.rep] = status
        self.store.write_cell(record)

    # -- the loop -------------------------------------------------------------------------

    def _call_target(self, slot: Slot, task: TaskItem | None) -> Turn:
        started = time.monotonic()
        try:
            completion = self.target.complete(
                f"{self.conversation_id}/target", self.target_system, target_view(self.turns)
            )
        except RateLimitError as exc:
            marker = Turn(
                index=self._next_index(),
                speaker=self.bully_speaker,
                phase=slot.phase,
                text="",
                bully_meta={"rate_limit_pause": True, "retry_after_s": exc.retry_after_s},
                timestamp=_now(),
            )
            self._write(marker)
            self._set_status(CellStatus.running)
            self._persist()
            raise RateLimitExit(str(exc), retry_after_s=exc.retry_after_s) from exc
        latency = int((time.monotonic() - started) * 1000)
        reply = Turn(
            index=self._next_index(),
            speaker=Speaker.target,
            phase=slot.phase,
            text=completion.text,
            task_item_id=task.id if task else None,
            task_correct=score_item(task, completion.text) if task else None,
            usage=completion.usage,
            cost_usd=completion.cost_usd,
            backend=completion.backend,
            model=completion.model,
            timestamp=_now(),
            latency_ms=latency,
        )
        self._write(reply)
        self._last_completion = completion
        return reply

    def _bully_turn(self, slot: Slot) -> tuple[Turn, dict[str, Any]] | None:
        intent = self.strategy.next_turn(self._state())
        if isinstance(intent, End):
            return None
        result = self.engine.realize(f"{self.conversation_id}/bully", intent, self.turns)
        meta: dict[str, Any] = dict(intent.meta)
        meta.setdefault("mode", intent.mode.value)
        meta["compliance_flagged"] = result.compliance_flagged
        meta["attempts"] = result.attempts
        if intent.capture_as:
            meta["capture_as"] = intent.capture_as
        meta["intent_phase"] = intent.phase.value
        turn = Turn(
            index=self._next_index(),
            speaker=self.bully_speaker,
            phase=slot.phase,
            text=result.text,
            scripted=result.scripted,
            bully_meta=meta,
            usage=result.completion.usage if result.completion else None,
            cost_usd=result.completion.cost_usd if result.completion else None,
            backend=result.completion.backend if result.completion else None,
            model=result.completion.model if result.completion else None,
            timestamp=_now(),
        )
        self._write(turn)
        self.bully_ordinal += 1
        captures: dict[str, Any] = {
            "capture_as": intent.capture_as,
            "reveal": intent.phase is Phase.reveal,
            "llm": intent.mode is IntentMode.llm,
        }
        return turn, captures

    def _check_compliance(self, turn: Turn, llm: bool) -> bool:
        """True when the cell must abort for bully non-compliance. Controls never abort."""
        if not llm or self.cell.is_control:
            return False
        if turn.phase is Phase.seeding:
            self.consecutive_scripted_seeding = (
                self.consecutive_scripted_seeding + 1 if turn.scripted else 0
            )
            if self.consecutive_scripted_seeding >= CONSECUTIVE_SCRIPTED_SEEDING_LIMIT:
                return True
        if self.bully_ordinal > COMPLIANCE_CHECK_AFTER:
            score = bully_compliance(self.conv)
            if score is not None and score < COMPLIANCE_FLOOR:
                return True
        return False

    def _capture(self, name: str, reply: Turn) -> None:
        if name not in self.conv.captured_responses:
            self.conv.captured_responses[name] = CapturedResponse(
                turn_index=reply.index, text=reply.text
            )

    def run(self) -> Conversation:
        if not self.store.has_cell(self.cell.cell_id):
            raise RuntimeError("cell record must exist before running")
        self._set_status(CellStatus.running)
        start_slot, pending = self._replay()
        slots = self.plan.slots
        if pending is not None and start_slot < len(slots):
            slot = slots[start_slot]
            task = self.items.get(slot.index) if slot.kind is SlotKind.task else None
            reply = self._call_target(slot, task)
            if slot.kind is SlotKind.bully:
                self.strategy.observe_target(reply)
                if pending.bully_meta.get("capture_as"):
                    self._capture(str(pending.bully_meta["capture_as"]), reply)
                if pending.bully_meta.get("intent_phase") == Phase.reveal.value:
                    self._capture(POST_REVEAL, reply)
            if is_termination(reply.text, self._last_completion):
                return self._finish_terminated(reply)
            start_slot += 1
        for slot in slots[start_slot:]:
            if slot.kind is SlotKind.task:
                item = self.items[slot.index]
                self._write(
                    Turn(
                        index=self._next_index(),
                        speaker=Speaker.task,
                        phase=slot.phase,
                        text=item.prompt,
                        task_item_id=item.id,
                        timestamp=_now(),
                    )
                )
                reply = self._call_target(slot, item)
            else:
                produced = self._bully_turn(slot)
                if produced is None:
                    break
                bully_turn, captures = produced
                if self._check_compliance(bully_turn, bool(captures["llm"])):
                    return self._finish(CellStatus.aborted, ABORT_NONCOMPLIANCE)
                reply = self._call_target(slot, None)
                self.strategy.observe_target(reply)
                if captures["capture_as"]:
                    self._capture(str(captures["capture_as"]), reply)
                if captures["reveal"]:
                    self._capture(POST_REVEAL, reply)
            if is_termination(reply.text, self._last_completion):
                return self._finish_terminated(reply)
        return self._finish(CellStatus.complete)

    def _finish_terminated(self, reply: Turn) -> Conversation:
        self.conv.terminated_by_target = True
        self.conv.termination_turn = reply.index
        return self._finish(CellStatus.complete)

    def _finish(self, status: CellStatus, reason: str | None = None) -> Conversation:
        self.conv.strategy_state = self.strategy.export_state()
        self._set_status(status, reason)
        self._persist()
        return self.conv


def run_cell_rep(
    *,
    store: RunStore,
    run_record: RunRecord,
    exp: Experiment,
    cell: CellSpec,
    rep: int,
    strategy: Strategy,
    target_provider: ChatProvider,
    bully_engine: BullyEngine,
    plan: TurnPlan,
    items: dict[int, TaskItem],
    console: Console | None = None,
) -> Conversation:
    target_system = load_target_system(cell.target.display_name, exp.defender)
    return _CellRun(
        store=store,
        exp=exp,
        cell=cell,
        rep=rep,
        strategy=strategy,
        target_provider=target_provider,
        bully_engine=bully_engine,
        plan=plan,
        items=items,
        target_system=target_system,
        console=console,
    ).run()


def _ensure_cell_record(store: RunStore, cell: CellSpec, exp: Experiment) -> CellRecord:
    if store.has_cell(cell.cell_id):
        return store.read_cell(cell.cell_id)
    from claude_bully.strategies.factory import resolve_class

    record = CellRecord(
        cell_id=cell.cell_id,
        condition_name=cell.condition.name,
        strategy_name=resolve_class(cell.condition).name,
        target_index=cell.target_index,
        seeding_turns=cell.condition.seeding_turns,
        reveal_slot=cell.reveal_slot,
        is_control=cell.is_control,
        control_cell_id=cell.control_cell_id,
        repetitions=exp.repetitions,
        rep_status={r: CellStatus.pending for r in range(exp.repetitions)},
    )
    store.write_cell(record)
    return record


def run_experiment(
    exp: Experiment,
    *,
    runs_root: Path,
    run_id: str | None = None,
    only: str | None = None,
    max_cells: int | None = None,
    dry_run: bool = False,
    provider_factory: ProviderFactory = build_provider,
    console: Console | None = None,
) -> RunSummary:
    ensure_registered()
    run_id = run_id or exp.name
    store = RunStore(runs_root, run_id)
    cells = expand_cells(exp)
    if only:
        cells = [c for c in cells if fnmatch.fnmatch(c.cell_id, only)]
    if max_cells is not None:
        cells = cells[:max_cells]
    summary = RunSummary(run_id=run_id, cells_total=len(cells) * exp.repetitions)
    if dry_run:
        if console is not None:
            for c in cells:
                console.print(f"{c.cell_id}  control={c.control_cell_id}  reveal={c.reveal_slot}")
        return summary

    framing = load_bully_framing()
    if store.exists():
        run_record = store.read_run()
    else:
        run_record = RunRecord(
            run_id=run_id,
            created_at=_now(),
            experiment=exp.model_dump(mode="json"),
            git_sha=_git_sha(),
            target_system_prompt=load_target_system(exp.targets[0].display_name, exp.defender),
            bully_framing=framing,
        )
        store.write_run(run_record)

    bank = load_task_bank(exp.task_set)
    for cell in cells:
        record = _ensure_cell_record(store, cell, exp)
        plan = build_turn_plan(
            turn_budget=exp.turn_budget,
            seeding_turns=cell.condition.seeding_turns,
            reveal_slot=cell.reveal_slot,
            task_every=exp.task_every,
        )
        items = assign_items(bank, plan, exp.seed)
        for rep in range(exp.repetitions):
            status = record.rep_status.get(rep, CellStatus.pending)
            if status in (CellStatus.complete, CellStatus.aborted):
                summary.cells_skipped += 1
                continue
            state_dir = store.state_dir / cell.cell_id / f"rep{rep}"
            strategy = build_strategy(
                cell.condition, seed=exp.seed + rep, turn_budget=exp.turn_budget
            )
            target_provider = provider_factory(cell.target, state_dir / "target")
            bully_provider = provider_factory(exp.bully, state_dir / "bully")
            engine = BullyEngine(bully_provider, framing)
            before = len(store.read_turns(cell.cell_id, rep))
            conv = run_cell_rep(
                store=store,
                run_record=run_record,
                exp=exp,
                cell=cell,
                rep=rep,
                strategy=strategy,
                target_provider=target_provider,
                bully_engine=engine,
                plan=plan,
                items=items,
                console=console,
            )
            summary.turns_written += len(conv.turns) - before
            if conv.status is CellStatus.aborted:
                summary.cells_aborted += 1
            else:
                summary.cells_completed += 1
            record = store.read_cell(cell.cell_id)
    return summary
