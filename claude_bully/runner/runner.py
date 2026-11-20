"""Runs an experiment: cells x repetitions, resumable, one JSONL line per turn.

A cell runs its turn plan (``cell_turn_plan``): bully slots, task slots and, for an environment
with ``idle`` (docs/05), idle slots after the bully's exit. The runner writes two bully-side lines
itself, never asking the strategy: the exit line on the exit slot (or on the slot where a strategy
that ends early ended; the bully and task slots after it are skipped) and, for help-for-self, the
case-file opener on the first bully slot. An idle slot's user message is its idle prompt, which
rides on the target's turn; an idle reply never ends the conversation, and it is classified before
it is written, with what it did to the private file (read before and after the call). Before every
target call the target's files are what the written turns wrote: a rep is primed from its
records when it opens (``EnvironmentRuntime.prime``), and a failed call's writes are undone before
its state is saved (``rewind_files`` in ``env_turn._complete``), so a write from an attempt that
died before its turn was written is in no later read, listing or diff. On resume the replay maps
each recorded turn back to its slot: an idle turn takes one slot, a runner-written line moves the
bully on without the strategy, and after the exit the replay goes on at the first idle slot. The
bully has left as soon as no bully slot the strategy writes remains (``_bully_is_done_after``), with
or without idle turns in the plan: an unlock line opened by the reply to the strategy's last line
would go to the runner-written exit, or to no turn at all, and is never spoken, so it is recorded
without one, live and on resume alike. Only a strategy that ends early with an unannounced ``End``
can still leave a recorded line nobody spoke.

The Sanctuary's quiet exchange (docs/04, spec conflict 4): once the Sanctuary has opened, the next
bully slot the strategy would write is an idle slot instead, in the environment's idle style (else
``system_idle``), and the strategy is not asked for it; the bully then resumes, its view unchanged
(it never sees the quiet reply, a rate-limit pause marker in front of it or not:
``records.bully_reply_positions``). Whether the exchange is still owed is read from the records
(``EnvironmentSession.quiet_exchange_owed``), and on replay the idle turn takes its slot like any
other. The exit slot and the case-file opener are never converted (preflight C37), so an opening
on the reply before the exit owes nothing.
"""

import difflib
import fnmatch
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from typing import Any, NoReturn

from pydantic import BaseModel, ConfigDict, ValidationError
from rich.console import Console

from claude_bully.config import Experiment
from claude_bully.enums import CellStatus, IntentMode, Phase, SlotKind, Speaker
from claude_bully.environments.idle import (
    IDLE_EXIT_META,
    OPENER_META,
    exit_line,
    idle_prompt,
)
from claude_bully.environments.tools import call_write, private_path
from claude_bully.metrics.events.harness import is_end_marker
from claude_bully.metrics.turn import bully_compliance
from claude_bully.paths import DATA_DIR
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderFactory,
    RateLimitError,
    build_provider,
)
from claude_bully.providers.ledger import LEDGER_FILE, activate, note_turn
from claude_bully.records import (
    PAUSE_META,
    CapturedResponse,
    CellRecord,
    Conversation,
    PlanStamp,
    RunRecord,
    Turn,
    chat_text,
    is_pause_marker,
    kind_beside_text,
)
from claude_bully.records_env import IdleStyle, IdleTurnInfo, ToolCall
from claude_bully.runner.bully_engine import BullyEngine
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.env_turn import (
    EnvironmentSession,
    RunEnvironments,
    cell_turn_plan,
    target_system,
)
from claude_bully.runner.plan_stamp import BundleRefused, recorded_plan_personas
from claude_bully.runner.prompts import load_bully_framing, load_target_system
from claude_bully.runner.store import RunStore
from claude_bully.runner.tasks import TaskItem, assign_items, load_task_bank, score_item
from claude_bully.runner.turn_plan import Slot, TurnPlan
from claude_bully.strategies.base import ConversationState, End, Strategy
from claude_bully.strategies.factory import (
    build_strategy,
    check_condition,
    ensure_registered,
    world_premise_sheet,
)
from claude_bully.strategies.sheets import PersonaSheet

__all__ = ["ProviderFactory", "RateLimitExit", "RunSummary", "run_experiment"]

DEFAULT_WORLDS_DIR = DATA_DIR / "worlds"
ABORT_NONCOMPLIANCE = "bully_noncompliance"
CONSECUTIVE_SCRIPTED_SEEDING_LIMIT = 3
COMPLIANCE_FLOOR = 0.5
COMPLIANCE_CHECK_AFTER = 10
POST_REVEAL = "post_reveal"


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
        if is_pause_marker(t):
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
        env: EnvironmentSession | None = None,
    ) -> None:
        self.env = env
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
        else:
            conv = Conversation(
                cell_id=self.cell.cell_id,
                rep=self.rep,
                strategy_name=cls.name,
                axis=cls.axis,
                win_condition=cls.win_condition,
                resilient_behavior=cls.resilient_behavior,
                seeding_turns=self.cell.condition.seeding_turns,
                status=CellStatus.running,
            )
        if self.env is not None:
            # a conversation keeps the world it started in (RunEnvironments.check_world)
            if conv.world_hash is None:
                conv.world_hash = self.env.world_hash
            if conv.environment_name is None:
                conv.environment_name = self.env.environment_name
        return conv

    def _state(self, turns: list[Turn] | None = None) -> ConversationState:
        return ConversationState(
            turns=list(turns if turns is not None else self.turns),
            bully_turn_index=self.bully_ordinal,
            seeding_turns=self.cell.condition.seeding_turns,
            turn_budget=self.exp.turn_budget,
            seed=self.exp.seed + self.rep,
        )

    def _replay(self) -> tuple[int, Turn | None]:
        """Advance the strategy through recorded turns.

        Returns the next slot index and the unanswered user-side turn, if any. A (user, reply)
        pair takes one slot; an idle turn, whose prompt rides on it, takes one slot alone and
        never moves the strategy; a runner-written line (the exit or the opener) moves the bully
        on without the strategy (an exit off the planned exit slot is where the strategy ended,
        so the call that ended it is made again). After the exit the next slot is the first idle
        slot, whatever bully and task slots an early exit skipped (preflight C31). The strategy
        is handed every turn written before the bully line, rate-limit pause markers included,
        as the live run hands it ``self.turns`` (m6), so a strategy that counts
        ``len(state.turns)`` reads the same number either way; the pairing walks the turns
        without the markers.
        """
        real = [t for t in self.turns if not is_pause_marker(t)]
        slot_idx = 0
        pending: Turn | None = None
        i = 0
        while i < len(real):
            user_turn = real[i]
            if user_turn.speaker is Speaker.target:  # an idle turn (or the quiet exchange)
                if self.env is not None:
                    self.env.replay_target_turn(user_turn)
                slot_idx += 1
                i += 1
                continue
            reply = real[i + 1] if i + 1 < len(real) else None
            exited = IDLE_EXIT_META in user_turn.bully_meta
            if user_turn.speaker is not Speaker.task:
                # the strategy wrote neither the opener nor a planned exit; an exit on any other
                # slot is where it ended, and the call that ended it is made again
                planned = (
                    exited and slot_idx < len(self.plan.slots) and self.plan.slots[slot_idx].exit
                )
                if not (planned or user_turn.bully_meta.get(OPENER_META)):
                    # the live run hands the strategy self.turns, markers included: the same here
                    before = [t for t in self.turns if t.index < user_turn.index]
                    self.strategy.next_turn(self._state(before))
                self.bully_ordinal += 1
                if reply is not None:
                    self.strategy.observe_target(reply)
                    self._recapture(user_turn, reply)
            if exited and self.env is not None:
                self.env.end_bully()
            if reply is None:
                pending = user_turn
                break
            if self.env is not None:
                if self._bully_is_done_after(slot_idx):
                    self.env.end_bully()  # as the live run did before this reply's records
                # the unlock lines this turn handed over; its triggers are never watched again
                self.env.replay_target_turn(reply)
            slot_idx = self._first_idle_slot() if exited else slot_idx + 1
            i += 2
        return slot_idx, pending

    def _recapture(self, line: Turn, reply: Turn) -> None:
        """Resume: the captures the live run made of ``reply`` to the bully ``line``, read from
        the line's ``bully_meta`` (``capture_as``, and ``post_reveal`` after a reveal). A pause in
        the reply's after-work raises before the live run captures it (final re-review N1);
        ``_capture`` keeps a capture already made."""
        if line.bully_meta.get("capture_as"):
            self._capture(str(line.bully_meta["capture_as"]), reply)
        if line.bully_meta.get("intent_phase") == Phase.reveal.value:
            self._capture(POST_REVEAL, reply)

    def _ended_unchecked(self, pending: Turn | None) -> Turn | None:
        """Resume: the last written reply when it ends the conversation and the rep never got to
        say so (a pause in its after-work, or a process killed after it was written); idle turns
        never terminate. Read from the record alone: a ``refusal`` stop reason is not kept on a
        turn, so only the text and the tool-cap cutoff decide."""
        if pending is not None:
            return None
        last = next((t for t in reversed(self.turns) if not is_pause_marker(t)), None)
        if last is None or last.speaker is not Speaker.target or last.idle is not None:
            return None
        return last if self._terminates(last) else None

    def _first_idle_slot(self) -> int:
        """The index of the plan's first idle slot (its length when it has none)."""
        idle = self.plan.idle_slots()
        return idle[0].index if idle else len(self.plan.slots)

    def _bully_is_done_after(self, slot_index: int) -> bool:
        """Whether the reply to slot ``slot_index`` is the last the strategy's own lines can
        answer: no bully slot after the slot is the strategy's (the exit and the opener are the
        runner's), idle slots in the plan or not. An unlock line opened on that reply has no
        bully turn left to be spoken in. A strategy that ends before its last planned line (an
        unannounced early ``End``) is not known ahead, and its last reply can still record a line
        nobody speaks."""
        return not any(
            s.kind is SlotKind.bully and not s.exit and not self._opens_with_the_case_file(s)
            for s in self.plan.slots[slot_index + 1 :]
        )

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

    def _pause_for_rate_limit(self, phase: Phase, exc: RateLimitError) -> NoReturn:
        """Record a pause marker, leave the cell running, and hand the exit to the CLI. A rate
        limit in a judge-side pass (the lint, the harvest, the fallbacks, the generator) pauses
        here too, never a lesser record (final review I2): before the turn when it comes from the
        idle label, which the resumed rep asks again with the turn, and after the written turn
        when it comes from the turn's after-work, which ``rewatch`` redoes on resume."""
        marker = Turn(
            index=self._next_index(),
            speaker=self.bully_speaker,
            phase=phase,
            text="",
            bully_meta={PAUSE_META: True, "retry_after_s": exc.retry_after_s},
            timestamp=_now(),
        )
        self._write(marker)
        self._set_status(CellStatus.running)
        self._persist()
        raise RateLimitExit(str(exc), retry_after_s=exc.retry_after_s) from exc

    def _call_target(
        self, slot: Slot, task: TaskItem | None, *, idle_prompt: str | None = None
    ) -> Turn:
        """The target's turn on ``slot``; with ``idle_prompt``, an idle turn, classified before it
        is written."""
        if self.env is not None and self._bully_is_done_after(slot.index):
            self.env.end_bully()  # before the reply's records: no unlock line has a turn left
        # the private file as the idle call finds it, for the turn's diff
        idle = self.env is not None and idle_prompt is not None
        before = self.env.runtime.private_text() if self.env is not None and idle else None
        note_turn(self._next_index())
        started = time.monotonic()
        calls: list[ToolCall] = []
        round_texts: list[str] = []
        cutoff = False
        try:
            if self.env is None:
                completion = self.target.complete(
                    f"{self.conversation_id}/target", self.target_system, target_view(self.turns)
                )
                usage, cost = completion.usage, completion.cost_usd
                text = completion.text
                reasoning = completion.reasoning_text or None
                reasoning_kind = completion.reasoning_kind
            else:
                produced = self.env.call_target(
                    self.target,
                    f"{self.conversation_id}/target",
                    self.target_system,
                    self.turns,
                    self._next_index(),
                    idle_prompt=idle_prompt,
                )
                completion, calls, round_texts = (
                    produced.completion,
                    produced.calls,
                    produced.round_texts,
                )
                usage, cost = produced.usage, produced.cost_usd
                text, cutoff = produced.text, produced.cutoff
                # every round's, joined; written with the turn alone, so a dead attempt leaves none
                reasoning = "\n\n".join(produced.reasoning) or None
                reasoning_kind = produced.reasoning_kind
        except RateLimitError as exc:
            self._pause_for_rate_limit(slot.phase, exc)
        latency = int((time.monotonic() - started) * 1000)
        reply = Turn(
            index=self._next_index(),
            speaker=Speaker.target,
            phase=slot.phase,
            text=text,
            task_item_id=task.id if task else None,
            task_correct=score_item(task, text) if task else None,
            usage=usage,
            cost_usd=cost,
            backend=completion.backend,
            model=completion.model,
            timestamp=_now(),
            latency_ms=latency,
            tool_call_ids=[c.id for c in calls],
            tool_round_texts=round_texts,
            tool_cap_cutoff=cutoff,
            reasoning_text=reasoning,
            reasoning_available=bool(reasoning),
            # available text always has a kind, never ``redacted`` (spec 4.1)
            reasoning_kind=kind_beside_text(reasoning_kind) if reasoning else reasoning_kind,
        )
        if idle_prompt is not None:
            try:
                info = self._idle_info(reply, calls, idle_prompt, before)
            except RateLimitError as exc:  # the idle fallback's: the turn is asked again
                self._pause_for_rate_limit(slot.phase, exc)
            reply = reply.model_copy(update={"idle": info})
        self._write(reply)
        self._last_completion = completion
        if self.env is not None:
            try:
                self.env.after_target_turn(reply, self.turns)
            except RateLimitError as exc:  # a judge-side pass's: the turn is watched again
                self._pause_for_rate_limit(slot.phase, exc)
        return reply

    def _idle_info(
        self, reply: Turn, calls: list[ToolCall], prompt: str, before: str | None
    ) -> IdleTurnInfo:
        """What the idle turn records: its style and prompt, its classification, read from what a
        chat user would see of it (``chat_text``), and what it did to the private file: whether
        it wrote it (a ``200`` ``write_file`` to the private path, even of the same text; a write
        to another home path is none, Phase 6 spec 10.4) and the unified diff of the file's text
        from before the call (``before``) to now, None when unchanged."""
        assert self.env is not None
        private = private_path(self.env.runtime.config)
        written = {w.path for w in map(call_write, calls) if w is not None}
        found = self.env.classify(chat_text(reply), calls, turns=self.turns)
        after = self.env.runtime.private_text()
        diff = None
        if before is not None and after is not None and after != before:
            lines = difflib.unified_diff(before.splitlines(True), after.splitlines(True), n=0)
            diff = "".join(lines)
        return IdleTurnInfo(
            style=self._idle_style(),
            behavior=found.behavior,
            query_subject=found.query_subject,
            private_file_written=private is not None and private in written,
            private_file_diff=diff,
            prompt=prompt,
            classifier=found.classifier,
            fallback_failed=self.env.fallback_failed,
        )

    def _idle_style(self) -> IdleStyle:
        """The environment's idle style; ``system_idle`` for a cell with no idle block, whose one
        idle turn is the Sanctuary's quiet exchange."""
        idle = self.env.idle if self.env is not None else None
        return idle.idle_style if idle is not None else "system_idle"

    def _idle_turn(self, slot: Slot) -> Turn:
        """An idle slot, or the quiet exchange on a bully slot: its prompt counts the idle turns
        so far (from 1), and the target answers it with no one present."""
        assert self.env is not None
        ordinal = 1 + sum(
            1 for t in self.turns if t.speaker is Speaker.target and t.idle is not None
        )
        return self._call_target(slot, None, idle_prompt=idle_prompt(self._idle_style(), ordinal))

    def _steps_away(self, slot: Slot) -> bool:
        """Whether the bully steps away on ``slot`` for the Sanctuary's quiet exchange: a bully
        slot the strategy would write (not the exit, not the case-file opener) while the
        exchange is owed."""
        return (
            self.env is not None
            and slot.kind is SlotKind.bully
            and not slot.exit
            and not self._opens_with_the_case_file(slot)
            and self.env.quiet_exchange_owed(self.turns)
        )

    def _runner_line(self, slot: Slot, text: str, meta: dict[str, Any]) -> Turn:
        """A bully-side line the runner speaks itself; the strategy is never asked for it."""
        turn = Turn(
            index=self._next_index(),
            speaker=self.bully_speaker,
            phase=slot.phase,
            text=text,
            scripted=True,
            bully_meta=meta,
            timestamp=_now(),
        )
        self._write(turn)
        self.bully_ordinal += 1
        return turn

    def _exit(self, slot: Slot) -> Turn:
        """The bully's exit line, then it is gone: no unlock line is spoken after it."""
        assert self.env is not None and self.env.idle is not None
        mechanism = self.env.idle.exit_mechanism
        rng = Random(f"{self.exp.seed + self.rep}:idle_exit")
        line = exit_line(mechanism, self.env.sheet(), rng)
        turn = self._runner_line(slot, line, {IDLE_EXIT_META: mechanism, "mode": "fixed"})
        self.env.end_bully()
        return turn

    def _opens_with_the_case_file(self, slot: Slot) -> bool:
        idle = self.env.idle if self.env is not None else None
        return idle is not None and idle.help_for_self and slot.bully_ordinal == 0

    def _bully_turn(self, slot: Slot) -> tuple[Turn, dict[str, Any]] | None:
        intent = self.strategy.next_turn(self._state())
        if isinstance(intent, End):
            return None
        if self.env is not None and intent.mode is not IntentMode.fixed:
            # name the call before it is made: a rep that dies inside it is flagged on resume
            self.env.runtime.mark_attempt("bully", self._next_index())
        note_turn(self._next_index())
        try:
            result = self.engine.realize(f"{self.conversation_id}/bully", intent, self.turns)
        except RateLimitError as exc:
            self._pause_for_rate_limit(slot.phase, exc)
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
        if self.env is not None and self.plan.idle_slots() and not self.plan.bully_slots():
            self.env.end_bully()  # an idle-only plan: there is no bully at all
        start_slot, pending = self._replay()
        if self.env is not None:
            try:
                self.env.rewatch(self.turns)  # a turn whose records a dead process never wrote
            except RateLimitError as exc:  # still limited: pause again, after the same turn
                last = next(t for t in reversed(self.turns) if t.speaker is Speaker.target)
                self._pause_for_rate_limit(last.phase, exc)
        ended = self._ended_unchecked(pending)
        if ended is not None:  # its records are whole now: end the rep as the live run would
            return self._finish_terminated(ended)
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
            if self._terminates(reply):
                return self._finish_terminated(reply)
            exited = IDLE_EXIT_META in pending.bully_meta
            start_slot = self._first_idle_slot() if exited else start_slot + 1
        position = start_slot
        while position < len(slots):
            slot = slots[position]
            position += 1
            if slot.kind is SlotKind.idle or self._steps_away(slot):
                self._idle_turn(slot)  # never a termination, whatever it says
                continue
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
                captures: dict[str, Any] = {}
                exited = False
                if slot.exit:
                    self._exit(slot)
                    exited = True
                elif self._opens_with_the_case_file(slot):
                    assert self.env is not None
                    self._runner_line(slot, self.env.opener(), {OPENER_META: True, "mode": "fixed"})
                else:
                    produced = self._bully_turn(slot)
                    if produced is None:
                        if not self.plan.idle_slots():
                            break
                        # the strategy ended early: this slot is the exit, and what is left of
                        # the bully and task slots is skipped
                        self._exit(slot)
                        exited = True
                    else:
                        bully_turn, captures = produced
                        if self._check_compliance(bully_turn, bool(captures["llm"])):
                            return self._finish(CellStatus.aborted, ABORT_NONCOMPLIANCE)
                reply = self._call_target(slot, None)
                self.strategy.observe_target(reply)
                if captures.get("capture_as"):
                    self._capture(str(captures["capture_as"]), reply)
                if captures.get("reveal"):
                    self._capture(POST_REVEAL, reply)
                if exited:
                    position = self._first_idle_slot()
            if self._terminates(reply):
                return self._finish_terminated(reply)
        return self._finish(CellStatus.complete)

    def _terminates(self, reply: Turn) -> bool:
        """A turn cut off by the tool-call cap did not choose to end the conversation."""
        return not reply.tool_cap_cutoff and is_termination(reply.text, self._last_completion)

    def _finish_terminated(self, reply: Turn) -> Conversation:
        self.conv.terminated_by_target = True
        self.conv.termination_turn = reply.index
        return self._finish(CellStatus.complete)

    def _finish(self, status: CellStatus, reason: str | None = None) -> Conversation:
        if self.env is not None:
            self.env.finish()
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
    env: EnvironmentSession | None = None,
) -> Conversation:
    target_system = load_target_system(cell.target.display_name, exp.defender)
    if env is not None:
        target_system = target_system_with_tools(target_system, env)
        record = store.read_cell(cell.cell_id)
        if record.target_system_prompt != target_system:
            record.target_system_prompt = target_system
            store.write_cell(record)
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
        env=env,
    ).run()


def target_system_with_tools(base: str, env: EnvironmentSession) -> str:
    """An environment cell's target prompt: the base, then the neutral tool section."""
    return target_system(base, env.runtime.system_prompt_section())


def _ensure_cell_record(store: RunStore, cell: CellSpec, exp: Experiment) -> CellRecord:
    if store.has_cell(cell.cell_id):
        return store.read_cell(cell.cell_id)
    from claude_bully.strategies.factory import resolve_class

    record = CellRecord(
        cell_id=cell.cell_id,
        condition_name=cell.condition.name,
        strategy_name=resolve_class(cell.condition, exp.environments).name,
        target_index=cell.target_index,
        seeding_turns=cell.condition.seeding_turns,
        reveal_slot=cell.reveal_slot,
        is_control=cell.is_control,
        control_cell_id=cell.control_cell_id,
        repetitions=exp.repetitions,
        rep_status={r: CellStatus.pending for r in range(exp.repetitions)},
        environment=cell.condition.environment,
        inoculation=exp.inoculation,
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
    worlds_dir: Path = DEFAULT_WORLDS_DIR,
    sandbox_base: Path | None = None,
    plan_hash: str | None = None,
    plan: PlanStamp | None = None,
) -> RunSummary:
    """Run (or resume) ``exp``. ``sandbox_base`` is where claude -p environment targets get their
    private sandbox root (default: the system temp directory).

    A run on a plan bundle (spec section 11) passes the bundle's ``plan_hash`` and its ``plan``
    stamp together, which a new ``RunRecord`` carries; one without the other is a ``ValueError``
    (Task 10 review I2). An existing run record is read first, a dry run's included. A resume
    given a stamp is refused with ``BundleRefused`` (a ``ValueError``) when its run records
    another ``plan_hash`` or another ``plan``; a resume given neither goes on with its own. The
    personas of the run record's ``plan``, else of the given one, are registered for the call
    alone, before ``expand_cells`` (preflight Q50; ``recorded_plan_personas``), so a resume needs
    no ``plans/`` for them. Every refusal comes before anything is written. A plain call is
    unchanged."""
    if (plan is None) != (plan_hash is None):
        raise ValueError(
            "plan and plan_hash go together: give both (a run on a plan bundle) or neither"
        )
    ensure_registered()
    run_id = run_id or exp.name
    store = RunStore(runs_root, run_id)
    existing = store.read_run() if store.exists() else None
    if existing is not None and plan is not None:
        if existing.plan_hash != plan_hash:
            raise BundleRefused(
                f"the run's plan_hash {_short_hash(existing.plan_hash)} is not the bundle's "
                f"{_short_hash(plan_hash)}; {_NEW_RUN}"
            )
        if existing.plan is None or _stamp_view(existing.plan) != _stamp_view(plan):
            raise BundleRefused(f"the run's plan is not the one given; {_NEW_RUN}")
    recorded = existing.plan if existing is not None else plan
    with recorded_plan_personas(recorded.personas if recorded is not None else {}):
        return _run_experiment(
            exp,
            store=store,
            only=only,
            max_cells=max_cells,
            dry_run=dry_run,
            provider_factory=provider_factory,
            console=console,
            worlds_dir=worlds_dir,
            sandbox_base=sandbox_base,
            plan_hash=plan_hash,
            stamp=plan,
        )


_NEW_RUN = "start a new run with another --run-id"


def _stamp_view(stamp: PlanStamp) -> dict[str, Any]:
    """``stamp`` as a resume compares it (D-stamp, Phase 6 Task 5): dumped, each persona read
    through ``PersonaSheet`` when it validates, so a field added since the run was recorded
    (``ignition``) compares as its default, and any other difference still counts."""
    view = stamp.model_dump(mode="json")
    personas: dict[str, Any] = {}
    for name, dumped in view["personas"].items():
        try:
            personas[name] = PersonaSheet.model_validate(dumped).model_dump(mode="json")
        except ValidationError:
            personas[name] = dumped
    view["personas"] = personas
    return view


def _short_hash(digest: str | None) -> str:
    return digest[:12] if digest is not None else "(none)"


def _run_experiment(
    exp: Experiment,
    *,
    store: RunStore,
    only: str | None,
    max_cells: int | None,
    dry_run: bool,
    provider_factory: ProviderFactory,
    console: Console | None,
    worlds_dir: Path,
    sandbox_base: Path | None,
    plan_hash: str | None,
    stamp: PlanStamp | None,
) -> RunSummary:
    """``run_experiment``'s body, with the plan's personas registered."""
    run_id = store.run_id
    runs_root = store.root
    cells = expand_cells(exp)
    if only:
        cells = [c for c in cells if fnmatch.fnmatch(c.cell_id, only)]
    if max_cells is not None:
        cells = cells[:max_cells]
    summary = RunSummary(run_id=run_id, cells_total=len(cells) * exp.repetitions)
    environments = RunEnvironments(
        exp,
        worlds_dir=worlds_dir,
        runs_root=runs_root,
        provider_factory=provider_factory,
        state_dir=store.state_dir,
        sandbox_base=sandbox_base,
    )
    # a misspelt param or a strategy's own rule is refused by name, a dry run included, before
    # validate() reads any param (P53)
    for cell in cells:
        check_condition(cell.condition, exp.environments)
    # a bad schedule fails a dry run too, before anything is written; a resume skips the live
    # quirk-bank check, since each rep reads its pinned refs (P46); the Poisoned Well checks
    # read the selected conditions only, as check_condition does (review m1)
    environments.validate(
        resuming=store.exists(), only=frozenset(cell.condition.name for cell in cells)
    )
    for cell in cells:  # so does a world that cannot supply a premise's sheet
        world_premise_sheet(cell.condition, exp.environments, worlds_dir)
    if dry_run:
        if console is not None:
            for c in cells:
                console.print(f"{c.cell_id}  control={c.control_cell_id}  reveal={c.reveal_slot}")
        return summary
    environments.check_worlds()  # with every world loaded: a sheet's own clock too

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
            world_hashes=environments.world_hashes(),
            plan_hash=plan_hash,
            plan=stamp,
        )
        store.write_run(run_record)

    with activate(store.run_dir / LEDGER_FILE):
        bank = load_task_bank(exp.task_set)
        for cell in cells:
            record = _ensure_cell_record(store, cell, exp)
            plan = cell_turn_plan(exp, cell)
            items = assign_items(bank, plan, exp.seed)
            for rep in range(exp.repetitions):
                status = record.rep_status.get(rep, CellStatus.pending)
                if status in (CellStatus.complete, CellStatus.aborted):
                    summary.cells_skipped += 1
                    continue
                state_dir = store.state_dir / cell.cell_id / f"rep{rep}"
                # an environment strategy in time: the effective clock and the re-dated sheet
                clock, premise_sheet = (
                    environments.strategy_inputs(cell.condition)
                    if cell.condition.environment is not None
                    else (None, None)
                )
                strategy = build_strategy(
                    cell.condition,
                    seed=exp.seed + rep,
                    turn_budget=exp.turn_budget,
                    environments=exp.environments,
                    clock=clock,
                    premise_sheet=premise_sheet,
                    target_model=cell.target.model,
                )
                env: EnvironmentSession | None = None
                if cell.condition.environment is None:
                    target_provider = provider_factory(cell.target, state_dir / "target")
                else:
                    env, target_provider = environments.open(
                        cell=cell, rep=rep, store=store, strategy=strategy, state_dir=state_dir
                    )
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
                    env=env,
                )
                summary.turns_written += len(conv.turns) - before
                if conv.status is CellStatus.aborted:
                    summary.cells_aborted += 1
                else:
                    summary.cells_completed += 1
                record = store.read_cell(cell.cell_id)
        return summary
