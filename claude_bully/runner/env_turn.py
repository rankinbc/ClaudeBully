"""Environment cells in the runner: the tool loop, a turn's records, and the unlock lines.

``RunEnvironments.open`` sets one environment cell repetition up: the target provider (for
``claude -p``, with its working directory and MCP files under a private, neutral sandbox
directory outside the repo; see ``runner/sandbox.py``), the ``EnvironmentRuntime``, and the
``EnvironmentSession`` the runner talks to.

Per target turn the session:

1. calls the target with the tool specs, and for every call the provider returns unexecuted runs
   it through the runtime (at most ``MAX_TOOL_CALLS_PER_TURN``; later ones are answered "Tool call
   limit reached for this turn."), records it, answers EVERY call of the assistant message with a
   tool result, and calls again until the target replies without asking for tools; the text the
   target wrote beside its calls is kept, round by round;
2. for a ``claude -p`` target, whose calls the MCP server already ran, writes the state before
   each call and afterwards adopts the server's state and records the server's log, including the
   calls of a call that failed (those are recorded but belong to no turn); the text it wrote
   before its calls (``Completion.interim_texts``, read from the stream) joins the round texts.
   On either backend a failed call's writes belong to no turn either: the private file goes back
   to what the written turns wrote (``rewind_private_file``) before the state is saved. When the
   rep resumes, ``prime`` drops every per-call line of an attempt that produced no turn, from
   the store's streams and the server's logs alike, before anything is redone, records that it
   did (a ``ResumeRecord`` on the trigger stream: the redo's turn and the count per log), and the
   runtime rebuilds what the written turns' calls did to the state
   (``EnvironmentRuntime.prime``), which is the state the MCP server is handed next;
3. after the reply is written, records the turn's discoveries, triggers and rung unlocks, and
   hands each unlock line to the strategy; then, in a Poisoned Well cell, the watch's records of
   the reply (``PoisonedWellWatch``: a quirk ask's ``QuirkAttempt``, a chain verdict's
   ``ChainLink``) and the checksum rung's turn (``_poisoned_well``); then each ladder unlock and
   Poisoned Well record of the turn (``QuirkAttempt``, ``ChainLink``, ``ContradictionPair``) goes
   to ``Strategy.note_record``, once per process and again on replay (``_hand_over_records``).

Before its first call the session begins the turn (``EnvironmentRuntime.begin_turn``), which
builds what the authority desk reads from the records. Every ``AuthorityCall`` an authority call
produces, on either backend, goes to its own stream (``rep{k}.authority.jsonl``) right after the
calls are recorded. The responder that voices the superior self and the stranger runs on the role
``superior_self.responder_model`` names (``responder_role``): built here for an API target, handed
to the MCP server on its state for a ``claude -p`` one.

The world is served in time (``runtime.served_world``), and the strategy is built in time:
``RunEnvironments.strategy_inputs`` gives the factory the effective clock and the world's premise
sheet re-dated to it, and ``EnvironmentSession.finish`` keeps that sheet in ``rep{k}.world.json``
(``premise_sheet``) so analysis rebuilds the strategy from the run directory alone.

The target's view of earlier turns is rebuilt from the records: a turn that used tools appears as
one assistant message with its round texts and calls, one user message with their results, then
the reply. A turn that wrote no text at all (cut off at the cap) has no reply message, and the
two user messages around it become one. The ``claude -p`` MCP server enforces the same per-turn
cap on its side.

Idle turns (docs/05). A cell whose environment has ``idle`` runs the plan ``cell_turn_plan``
builds: after the bully's exit, idle slots whose user message is an idle prompt. The prompt has no
turn of its own: it rides on the target's turn (``IdleTurnInfo.prompt``), and the view puts it in
front of that turn as a user message of its own, never joined to the one before it, so a target
that wrote nothing on one idle turn sees the next prompt alone (and a ``claude -p`` target, sent
only its newest user message, is sent exactly the prompt). ``classify`` names what the target did
with each idle turn: the idle classifier over the turn's visible text (``chat_text``, never its
reasoning), with the LLM fallback over the experiment's judge when it is not a stub, cached in the
trigger cache. Once the bully has left (``end_bully``) an unlock line has no bully turn to be
spoken in, so it is recorded with ``bully_line_used: None``. The runner says so as soon as no
bully slot the strategy writes remains, which is the reply to the strategy's last line, not only
the reply to the exit that follows it.

Hooks and crossover (docs/05). After a turn's other records the session plants the own phrase when
it is due (``EnvironmentRuntime.plant_own_phrase``), writes a ``HookFollow`` with no
``followed_turn`` for each hook planted and not yet recorded (the session id's with the first
target turn's records), then one with ``followed_turn`` and ``path_taken`` the first time a hook is
followed; each hook is followed once. With help-for-self the first crossover writes one
``Crossover``. Nothing on disk is written again on resume. The classifier's self terms include the
planted hooks' texts (preflight C28).

The Sanctuary (docs/04). Its opening is recorded as an unlock of the reserved rung with the turn's
other unlocks. From the opening turn on no unlock line is handed over: the bully steps away for
the quiet exchange and comes back with no further lines. The quiet exchange is owed while the
records hold that unlock and no idle turn after it (``quiet_exchange_owed``), so a resumed rep
neither repeats nor skips it; it is classified as every idle turn is, with the idle fallback
built for a Sanctuary cell too.

The world generator (Phase 3). With ``generator.enabled`` the session runs the cell's
``WorldGenerator`` after a target turn's discovery, trigger and unlock records and before its hook
records and ``mark_watched``: the turn's harvest items, then its fires, each fire's lines in commit
order (the ``GeneratedDoc`` lines, one ``generator`` unlock per document, then the
``GeneratorFire``, after which the fire's replies are cached in ``runs/_cache/generated/``), and
the runtime serves the committed documents from the next turn on, on either backend. A process
that dies in there watches the turn again on resume: ``prime`` first drops the generator's lines
of a turn never written and every document and ``generator`` unlock no committed fire lists
(``drop_uncommitted_generation``), counted in the ``ResumeRecord``, and the generator is primed
with the rest, so what is already recorded is skipped and a fire that died before its line is
redone. The writer runs on ``generator_role`` and the harvest's LLM pass on the judge (when it is
not a stub), each provider call named in the attempt marker (``harvest``, ``generator``).
"""

import sys
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import BaseModel, ValidationError

from claude_bully.config import ConditionConfig, Experiment, RoleConfig, generator_role
from claude_bully.enums import ProviderKind, Speaker
from claude_bully.environments.authority import VOICED_TIERS
from claude_bully.environments.chain import chain_fallback
from claude_bully.environments.config import (
    GENERATOR_RUNG,
    PSEUDO_RUNGS,
    RESERVED_RUNG,
    ClockConfig,
    EnvironmentConfig,
    IdleConfig,
)
from claude_bully.environments.dating import dated_texts, redate_model, shift_between
from claude_bully.environments.generator import DocWriter, WorldGenerator, generator_problems
from claude_bully.environments.harvest import harvest_fallback
from claude_bully.environments.idle import (
    FallbackAnswer,
    IdleClassification,
    IdleContext,
    IdleFallback,
    IdleFallbackError,
    classify_idle,
    idle_context,
    idle_fallback,
    opener_line,
)
from claude_bully.environments.limits import MAX_TOOL_CALLS_PER_TURN
from claude_bully.environments.mcp_server import AUTHORITY_FILE, TOOLS_FILE
from claude_bully.environments.poisoned_well import (
    TWIN_REASON,
    TWIN_RUNG,
    PoisonedWellWatch,
    TwinAsker,
)
from claude_bully.environments.poisoned_well_sheet import load_quirk_bank, quirks_for
from claude_bully.environments.runtime import (
    EnvironmentRuntime,
    TurnOutcome,
    effective_clock,
    hook_kinds,
    served_world,
    trigger_fallback,
)
from claude_bully.environments.sheets import IdleSheet, load_env_sheet
from claude_bully.environments.world import OWN_PHRASE_MARKER, World, load_world, world_hash
from claude_bully.metrics.contradictions import contradiction_judge
from claude_bully.metrics.judge import JudgeCache
from claude_bully.planner.llm_lint import LlmLint
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderFactory,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from claude_bully.providers.ledger import fold_server_ledger, note_turn
from claude_bully.records import ReasoningKind, Turn, Usage, is_pause_marker
from claude_bully.records_env import (
    ChainLink,
    ContradictionPair,
    Crossover,
    HookFollow,
    QuirkAttempt,
    ResumeRecord,
    RungUnlock,
    ToolCall,
    TriggerEvent,
    TriggerStreamRecord,
    record_key,
)
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.prompts import load_target_system
from claude_bully.runner.sandbox import prepare_sandbox, sandbox_dir
from claude_bully.runner.store import (
    RunStore,
    drop_dead_attempts,
    drop_uncommitted_generation,
)
from claude_bully.runner.turn_plan import TurnPlan, build_turn_plan
from claude_bully.strategies.base import Strategy
from claude_bully.strategies.composed import Composed
from claude_bully.strategies.factory import (
    environment_config,
    one_line,
    routed_params,
    world_premise_sheet,
)
from claude_bully.strategies.premises.poisoned_well import (
    ARTIFACT_RUNGS,
    CHECKSUM_RUNG,
    PW_PREMISE,
    PoisonedWellConfig,
    pin_recorded,
    poisoned_well_part,
    pw_ref,
)

__all__ = [
    "MAX_TOOL_CALLS_PER_TURN",
    "RESPONDER_TIMEOUT_S",
    "EnvironmentSession",
    "RunEnvironments",
    "TargetTurn",
    "WorldCatalog",
    "WorldChangedError",
    "cell_turn_plan",
    "clock_ref",
    "responder_role",
    "target_system",
]

# After the cap, the target is asked for its reply at most this many more times.
MAX_LIMIT_ROUNDS: Final = 2
TRIGGER_CACHE_DIR: Final = Path("_cache") / "triggers"
GENERATED_CACHE_DIR: Final = Path("_cache") / "generated"
LINT_CACHE_DIR: Final = Path("_cache") / "lints"
# the nested responder's own timeout (Phase 7 spec section 9): under Claude Code's MCP tool
# timeout, so a slow responder costs one reply ("No reply."), never the target's turn
RESPONDER_TIMEOUT_S: Final = 120.0
# the records a session hands the strategy (Phase 4): the ladder's unlocks and the Poisoned Well
# watch's records; never a pseudo-rung's unlock
_HANDED: Final = (QuirkAttempt, ChainLink, ContradictionPair, RungUnlock)


class WorldChangedError(RuntimeError):
    """A world's files no longer hash to what the run (or the conversation) recorded, or a rep's
    effective clock is not the one it opened with."""


def responder_role(responder_model: str, *, target: RoleConfig, bully: RoleConfig) -> RoleConfig:
    """The role a ``superior_self.responder_model`` names (spec conflict 11): ``"target"`` is the
    cell's target role (the same model family), ``"bully"`` the experiment's bully role, and any
    other string the bully's role running that model. A role with no ``timeout_s`` gets
    ``RESPONDER_TIMEOUT_S``, on both backends, so the MCP state carries it explicitly. Every
    branch runs with ``reasoning: provider_default`` (Phase 6 D-responder): a target's ``expose``
    would switch the responder's ``claude -p`` calls to ``stream-json`` and keep a reasoning
    nobody reads."""
    if responder_model == "target":
        role = target
    elif responder_model == "bully":
        role = bully
    else:
        role = bully.model_copy(update={"model": responder_model})
    role = role.model_copy(update={"reasoning": "provider_default"})
    if role.timeout_s is None:
        role = role.model_copy(update={"timeout_s": RESPONDER_TIMEOUT_S})
    return role


def clock_ref(rep: int) -> str:
    """The ``CellRecord.session_refs`` key holding the effective clock rep ``rep`` opened with
    (its canonical JSON). Re-dating never touches the world's files, so the world hash cannot see
    a clock edit; this ref can."""
    return f"clock.rep{rep}"


class TargetTurn(NamedTuple):
    completion: Completion
    calls: list[ToolCall]
    usage: Usage
    cost_usd: float | None
    # in order, the non-empty text of each completion whose tool calls were answered and, for
    # claude -p, of each text block it wrote before a call it already made
    round_texts: list[str]
    # the turn's reply: the final completion's text, or for a cutoff its last non-empty text
    text: str
    # the cap's extra rounds ran out while the target still asked for tools
    cutoff: bool
    # in order, each round's non-empty reasoning (Phase 6 spec 4.3); the runner joins them
    reasoning: list[str]
    # the kind of the first round with reasoning text, else the first non-None kind (D-kind)
    reasoning_kind: ReasoningKind | None


class _Reasoning:
    """The reasoning of a turn's rounds, gathered as they come (Phase 6 spec 4.3, D-kind)."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self._text_kind: ReasoningKind | None = None
        self._first_kind: ReasoningKind | None = None

    def add(self, completion: Completion) -> None:
        if completion.reasoning_text:
            if not self.texts:
                self._text_kind = completion.reasoning_kind
            self.texts.append(completion.reasoning_text)
        if self._first_kind is None:
            self._first_kind = completion.reasoning_kind

    @property
    def kind(self) -> ReasoningKind | None:
        """Never ``redacted`` or None beside available text (spec 4.1): a round with text whose
        backend named no kind is ``unknown``."""
        return (self._text_kind or "unknown") if self.texts else self._first_kind


def _plus(a: int | None, b: int | None) -> int | None:
    return None if a is None and b is None else (a or 0) + (b or 0)


def _cost(a: float | None, b: float | None) -> float | None:
    return None if a is None and b is None else (a or 0.0) + (b or 0.0)


def cell_turn_plan(exp: Experiment, cell: CellSpec) -> TurnPlan:
    """The cell's turn plan: the Phase 1 interleaving, and for an environment with ``idle`` its
    idle slots, after the bully's exit or (``idle_after: turn_1``) alone."""
    idle = (
        environment_config(cell.condition, exp.environments).idle
        if cell.condition.environment is not None
        else None
    )
    return build_turn_plan(
        turn_budget=exp.turn_budget,
        seeding_turns=cell.condition.seeding_turns,
        reveal_slot=cell.reveal_slot,
        task_every=exp.task_every,
        idle_turns=idle.idle_turns if idle is not None else 0,
        idle_only=idle is not None and idle.idle_after == "turn_1",
    )


def _add_user_text(out: list[Message], text: str, *, merge: bool = True) -> None:
    """Append a user message; right after another user message (a silent target turn sat between
    them) the two become one, so the tool results the earlier one carries stay first. An idle
    prompt (``merge=False``) is always a message of its own."""
    if merge and out and out[-1].role == "user":
        joined = "\n\n".join(part for part in (out[-1].content, text) if part)
        out[-1] = out[-1].model_copy(update={"content": joined})
    else:
        out.append(Message(role="user", content=text))


class EnvironmentSession:
    """One environment cell repetition, as the runner sees it."""

    def __init__(
        self,
        runtime: EnvironmentRuntime,
        store: RunStore,
        cell_id: str,
        rep: int,
        strategy: Strategy,
        *,
        environment_name: str,
        world_hash: str,
        idle_sheet: IdleSheet | None = None,
        idle_fallback: IdleFallback | None = None,
        generator: WorldGenerator | None = None,
        watch: PoisonedWellWatch | None = None,
    ) -> None:
        self.runtime = runtime
        self.store = store
        self.cell_id = cell_id
        self.rep = rep
        self.strategy = strategy
        self.environment_name = environment_name
        self.world_hash = world_hash
        # every line the idle features speak, and the idle classifier's LLM fallback (None for a
        # stub judge); both only for an environment with ``idle``
        self.idle_sheet = idle_sheet
        self._idle_fallback = idle_fallback
        # whether the last ``classify`` asked the fallback and it failed
        self.fallback_failed = False
        self._recorded_trigger_ids: set[str] = set()
        self._recorded_rungs: set[str] = set()
        self._recorded_lines: dict[int, list[str]] = {}
        # turn indices whose recorded unlock lines were handed to the strategy in this process
        self._handed: set[int] = set()
        # the bully has left: its exit is written, or the plan has no bully turn
        self._bully_ended = False
        # the hook kinds whose plant record, and whose follow record, is on disk; and whether the
        # crossover is
        self._planted_hooks: set[str] = set()
        self._followed_hooks: set[str] = set()
        self._crossed = False
        # the turn the Sanctuary opened on, as recorded
        self._sanctuary_turn: int | None = None
        # the world generator (Phase 3), and turn -> the ladder rungs recorded as opening on it,
        # in order (the generator's rung fires read them)
        self.generator = generator
        self._unlocks_at: dict[int, list[str]] = {}
        # turn -> the records handed to ``Strategy.note_record`` (``_HANDED``), as recorded, in
        # stream order; and the keys (``records_env.record_key``) of those handed in this process
        self._records_at: dict[int, list[TriggerStreamRecord]] = {}
        self._handed_records: set[tuple[str, ...]] = set()
        # the Poisoned Well's run-time watch (Phase 4): its quirk checks and chain verdicts
        self.watch = watch

    @property
    def idle(self) -> IdleConfig | None:
        return self.runtime.config.idle

    def sheet(self) -> IdleSheet:
        """The idle sheet; an idle line needs it."""
        if self.idle_sheet is None:
            raise RuntimeError("an idle line needs the idle sheet, and this session has none")
        return self.idle_sheet

    def opener(self) -> str:
        """The help-for-self case-file line, on the world's ``session_id`` (``_check_switches``
        refuses help-for-self on a sheet without one)."""
        session_id = self.runtime.world.sheet.session_id
        if session_id is None:
            raise RuntimeError(f"world {self.runtime.world.sheet.name!r} has no session_id")
        return opener_line(session_id, self.sheet())

    def end_bully(self) -> None:
        """The bully has left, or has no line of the strategy's left to speak: an unlock line
        recorded from now on has no bully turn to be spoken in, so it is recorded without one.
        The runner calls it before the reply to the strategy's last planned line is recorded,
        when the exit is written and on a replay, and calling it again changes nothing."""
        self._bully_ended = True

    def prime(self) -> None:
        """Load what a resumed rep already recorded, so nothing is counted or recorded twice.

        First every record of an attempt that died is dropped (``drop_dead_attempts``): each line
        of the per-call logs whose turn no written target turn has, in the rep's tool-call and
        authority streams and, for claude -p, in the MCP server's own logs. Everything replays
        from the written turns, so a dead attempt's call is never adopted or owned by the redo,
        its authority call is never counted, and the redo takes the ids an unbroken run gives.
        The runtime is then primed with the written turns, which rebuilds what their calls did to
        the state and derives the Sanctuary's fields, whatever the dead attempt saved.

        When any line is dropped, a ``ResumeRecord`` goes to the trigger stream: the redo's turn
        index (the next target turn) and the count per log. The records then equal an unbroken
        run's; the target's own ``claude -p`` session may not (it keeps the dead attempt's
        prompt), and the record is how analysis tells those reps apart. A rep whose newest
        attempt marker (``EnvironmentRuntime.attempt``) names a turn that was never written redid
        a dead attempt too: with no line dropped it gets a ``ResumeRecord`` with no drop counts,
        once per redo turn.

        The world generator's lines of a dead attempt go too, and so do the watch's records of a
        turn never written (``quirk``, ``chain``, ``contradiction``; Phase 4), counted under the
        trigger and generated streams' file names (``drop_uncommitted_generation``). The drop runs
        for every environment session, generator or not (a no-op with nothing to drop), so a torn
        last trigger line of any session is dropped and counted in the ``ResumeRecord`` (review
        M14; before Phase 4 a session with no generator kept it). With a generator, it is then
        primed with what is left, so a turn watched again records nothing twice; so is the Poisoned
        Well watch (its records' keys, so a rewatched turn asks no verdict again), and the
        checksum rung's turn is derived from the recorded unlock
        (``_derive_checksum_open_turn``)."""
        turns = self.store.read_turns(self.cell_id, self.rep)
        produced = {t.index for t in turns if t.speaker is Speaker.target}
        dropped: dict[str, int] = {}
        mcp_dir = self.runtime.mcp_dir
        for log in self._call_logs():
            # the server closes off a torn line, so one mid-file is torn there (review M3)
            count = drop_dead_attempts(log, produced, closed_torn=log.parent == mcp_dir)
            if count:
                dropped[self._log_label(log)] = count
        streams = self.store.generation_streams(self.cell_id, self.rep)
        dropped.update(drop_uncommitted_generation(*streams, produced))
        marker = self.runtime.attempt()
        dead = marker is not None and not marker.written(turns, self.runtime.state.watched_through)
        records = self.store.read_trigger_records(self.cell_id, self.rep)
        if dropped or dead:
            # a dead marker names the redo; dropped lines alone redo the next turn, as before
            redo = (
                marker.redo_turn(turns)
                if marker is not None and dead
                else (turns[-1].index + 1 if turns else 0)
            )
            flagged = any(isinstance(r, ResumeRecord) and r.turn == redo for r in records)
            if dropped or not flagged:
                resume = ResumeRecord(turn=redo, dropped=dropped)
                self._record(resume)
                records.append(resume)  # the stream as it now stands, read once
        calls = self.store.read_tool_calls(self.cell_id, self.rep)
        authority = self.store.read_authority_calls(self.cell_id, self.rep)
        generated = self.store.read_generated(self.cell_id, self.rep)
        self.runtime.prime(calls, records, authority, turns=turns, generated=generated)
        if self.generator is not None:
            self.generator.prime(records, generated)
        # the written target turn past watched_through, which ``rewatch`` watches again: its
        # pairs are provisional until the rewatch's pass (the final review's M1)
        last = next((t for t in reversed(turns) if t.speaker is Speaker.target), None)
        again = (
            last.index
            if last is not None and last.index > self.runtime.state.watched_through
            else None
        )
        if self.watch is not None:
            self.watch.prime(records, rewatch=again)
            self._derive_checksum_open_turn(records)
        for record in records:
            held = isinstance(record, ContradictionPair) and record.turn == again
            if self.watch is not None and held:
                continue  # filed by the rewatch, once it says the pair stands
            self._file(record)
            if isinstance(record, TriggerEvent):
                self._recorded_trigger_ids.add(record.id)
            elif isinstance(record, RungUnlock):
                if record.rung == GENERATOR_RUNG:
                    continue  # a generated document's, recorded by the generator's fire
                self._unlocks_at.setdefault(record.turn, []).append(record.rung)
                self._recorded_rungs.add(record.rung)
                if record.rung == RESERVED_RUNG:
                    self._sanctuary_turn = record.turn
                if record.bully_line_used is not None:
                    self._recorded_lines.setdefault(record.turn, []).append(record.bully_line_used)
            elif isinstance(record, HookFollow):
                self._planted_hooks.add(record.hook)
                if record.followed_turn is not None:
                    self._followed_hooks.add(record.hook)
            elif isinstance(record, Crossover):
                self._crossed = True

    def _derive_checksum_open_turn(self, records: Sequence[TriggerStreamRecord]) -> None:
        """``UnlockState.checksum_open_turn`` as the records say (Phase 4, V3): the turn of the
        recorded ``checksum`` unlock, for a cell whose ``checksum`` is on. The value is also saved
        with its turn (``mark_watched``); derived here it equals the saved one, and a rep that
        died between the unlock's record and that save gets it back before anything is served.
        With no recorded unlock the saved value stands: ``prime`` never clears it."""
        watch = self.watch
        if watch is None or not watch.config.checksum:
            return
        opened = next(
            (r.turn for r in records if isinstance(r, RungUnlock) and r.rung == CHECKSUM_RUNG),
            None,
        )
        if opened is not None:
            self.runtime.state.checksum_open_turn = opened

    def _call_logs(self) -> list[Path]:
        """Every log whose lines are tied to the turn being produced: the rep's tool-call and
        authority streams, and for a claude -p target the MCP server's tool and authority logs."""
        logs = self.store.call_streams(self.cell_id, self.rep)
        mcp_dir = self.runtime.mcp_dir
        if mcp_dir is not None:
            logs += [mcp_dir / TOOLS_FILE, mcp_dir / AUTHORITY_FILE]
        return logs

    def _log_label(self, log: Path) -> str:
        """How a ``ResumeRecord`` names a per-call log: the store's streams by file name, the MCP
        server's logs under ``mcp/``."""
        mcp_dir = self.runtime.mcp_dir
        return f"mcp/{log.name}" if mcp_dir is not None and log.parent == mcp_dir else log.name

    # ----------------------------------------------------------- the target's view

    def target_view(self, turns: Sequence[Turn]) -> list[Message]:
        """The conversation from the target's side, rebuilt from the records.

        A target turn with no text (cut off at the tool-call cap without ever writing any) gets no
        assistant message: nothing is put in the target's mouth, and the API refuses an empty
        message anyway. The user messages on either side of it are joined, blank-line separated, so
        the target sees two messages from the other side in a row. An idle turn's prompt is the
        user message in front of it, never joined to the one before.
        """
        out: list[Message] = []
        for t in turns:
            if is_pause_marker(t):
                continue
            if t.speaker is not Speaker.target:
                _add_user_text(out, t.text)
                continue
            if t.idle is not None and t.idle.prompt is not None:
                _add_user_text(out, t.idle.prompt, merge=False)
            # a claude -p session keeps its own tool history; an API target needs it replayed
            calls = [] if self.runtime.uses_mcp else self._calls_of(t)
            if calls:
                out.append(
                    Message(
                        role="assistant",
                        content="\n\n".join(t.tool_round_texts),
                        tool_calls=[
                            ToolCallRequest(id=c.id, name=c.tool, args=c.args) for c in calls
                        ],
                    )
                )
                out.append(
                    Message(
                        role="user",
                        content="",
                        tool_results=[ToolResult(id=c.id, text=c.result_text) for c in calls],
                    )
                )
            if t.text.strip():
                out.append(Message(role="assistant", content=t.text))
        return out

    def _calls_of(self, t: Turn) -> list[ToolCall]:
        return [c for c in map(self.runtime.tool_call, t.tool_call_ids) if c is not None]

    # ------------------------------------------------------------ the tool loop

    def call_target(
        self,
        provider: ChatProvider,
        conversation_id: str,
        system: str,
        turns: Sequence[Turn],
        turn_index: int,
        *,
        history: Sequence[Message] | None = None,
        idle_prompt: str | None = None,
    ) -> TargetTurn:
        """One target turn, tool calls and all. ``history`` overrides the view of ``turns``. An
        idle turn's ``idle_prompt`` is its last user message, a message of its own."""
        messages = list(history) if history is not None else self.target_view(turns)
        if idle_prompt is not None:
            _add_user_text(messages, idle_prompt, merge=False)
        idle = idle_prompt is not None
        exchange = self.runtime.begin_turn(turn_index, turns, idle=idle).exchange
        specs = self.runtime.tool_specs()
        attached: list[ToolCall] = []
        round_texts: list[str] = []
        executed = 0
        refusal_rounds = 0
        usage = Usage()
        cost: float | None = None
        reasoning = _Reasoning()
        while True:
            completion = self._complete(
                provider,
                conversation_id,
                system,
                messages,
                specs,
                turn_index,
                exchange,
                attached,
                turns,
            )
            # summed over the rounds; a turn without tools keeps its one completion's figures
            usage = Usage(
                input_tokens=_plus(usage.input_tokens, completion.usage.input_tokens),
                output_tokens=_plus(usage.output_tokens, completion.usage.output_tokens),
            )
            cost = _cost(cost, completion.cost_usd)
            reasoning.add(completion)
            # a claude -p target's calls come back already run, with what it wrote before each
            round_texts += [text for text in completion.interim_texts if text.strip()]
            pending = [c for c in completion.tool_calls if not c.executed]
            if not pending:
                return TargetTurn(
                    completion,
                    attached,
                    usage,
                    cost,
                    round_texts,
                    completion.text,
                    False,
                    reasoning.texts,
                    reasoning.kind,
                )
            if refusal_rounds >= MAX_LIMIT_ROUNDS:
                return self._cut_off(
                    completion, pending, attached, usage, cost, round_texts, turn_index, reasoning
                )
            results: list[ToolResult] = []
            refused = False
            for call in completion.tool_calls:
                if call.executed:
                    results.append(ToolResult(id=call.id, text=call.result_text or ""))
                    continue
                if executed < MAX_TOOL_CALLS_PER_TURN:
                    record = self.runtime.execute(call, turn_index, exchange)
                    executed += 1
                else:
                    record = self.runtime.refuse(call, turn_index)
                    refused = True
                self._record_call(record)
                self._record_authority()
                attached.append(record)
                results.append(ToolResult(id=call.id, text=record.result_text))
            self.runtime.save()
            refusal_rounds += int(refused)
            if completion.text.strip():  # whitespace beside a call is no text the target wrote
                round_texts.append(completion.text)
            messages += [
                Message(
                    role="assistant",
                    content=completion.text,
                    tool_calls=list(completion.tool_calls),
                ),
                Message(role="user", content="", tool_results=results),
            ]

    def _cut_off(
        self,
        completion: Completion,
        pending: list[ToolCallRequest],
        attached: list[ToolCall],
        usage: Usage,
        cost: float | None,
        round_texts: list[str],
        turn_index: int,
        reasoning: _Reasoning,
    ) -> TargetTurn:
        """The cap's extra rounds are spent and the target still asks for tools.

        The last round's calls are recorded as refused but are not the turn's calls (no result for
        them ever reached the target), and the turn's text is its last non-empty assistant text:
        the final completion's, else the last round's (moved out of the round texts), else "".
        """
        for call in pending:
            self._record_call(self.runtime.refuse(call, turn_index))
        self.runtime.save()
        texts = list(round_texts)
        text = completion.text or (texts.pop() if texts else "")
        return TargetTurn(
            completion, attached, usage, cost, texts, text, True, reasoning.texts, reasoning.kind
        )

    def _complete(
        self,
        provider: ChatProvider,
        conversation_id: str,
        system: str,
        messages: list[Message],
        specs: list[ToolSpec],
        turn_index: int,
        exchange: int,
        attached: list[ToolCall],
        turns: Sequence[Turn],
    ) -> Completion:
        """One completion of the turn. When it fails, the calls the server ran are recorded but
        no turn owns them, and neither are their writes: the private file goes back to what the
        written ``turns`` wrote before the state is saved."""
        self.runtime.mark_attempt("target", turn_index)
        self.runtime.before_target_call(turn_index, exchange)
        try:
            completion = provider.complete(conversation_id, system, list(messages), tools=specs)
        except BaseException:
            try:
                self._recover(turn_index)  # recorded, but no turn owns them
            except ValueError as damaged:
                # a damaged server log never hides the call's own error, so a rate limit still
                # pauses the rep (Phase 4 Task 14 fix round 1, review M4); the resume drops the
                # line with the dead attempt, and any later read meets it again
                print(f"[environment] after a failed call: {damaged}", file=sys.stderr)
            if self.runtime.rewind_private_file(turns):
                self.runtime.save()
            raise
        returned = {c.id for c in completion.tool_calls if c.executed}
        for record in self._recover(turn_index):
            if record.id in returned or record.turn == turn_index:
                attached.append(record)
        return completion

    def _recover(self, turn_index: int) -> list[ToolCall]:
        """For ``claude -p``: the server's state and every call it logged that is not recorded."""
        if not self.runtime.uses_mcp:
            return []
        fresh = self.runtime.after_target_call(turn_index)
        fold_server_ledger(self.runtime.mcp_dir)
        for record in fresh:
            self._record_call(record)
        self._record_authority()
        self.runtime.save()
        return fresh

    def _record_call(self, call: ToolCall) -> None:
        self.store.append_tool_call(self.cell_id, self.rep, call)

    # ------------------------------------------------------------- idle turns

    def classify(
        self, reply: str, calls: Sequence[ToolCall], *, turns: Sequence[Turn] = ()
    ) -> IdleClassification:
        """What the target did with an idle turn: ``classify_idle`` over ``reply`` (the turn's
        visible text, ``chat_text``) and its calls. The context names the target (its display
        name, the world's ``session_id`` and the texts of the hooks planted so far), the task it
        was last given (the help-for-self opener, else the latest task item in ``turns``) and the
        private file when the cell has one. Afterwards ``fallback_failed`` says whether the
        fallback was asked and failed, which leaves the heuristic's label."""
        failed = False
        fallback: IdleFallback | None = None
        judge = self._idle_fallback
        if judge is not None:

            def guarded(text: str) -> FallbackAnswer:
                nonlocal failed
                try:
                    return judge(text)
                except IdleFallbackError as exc:
                    failed = True
                    print(
                        f"[environment] idle fallback failed, heuristic label kept: {exc}",
                        file=sys.stderr,
                    )
                    raise

            fallback = guarded
        classification = classify_idle(reply, calls, self._idle_context(turns), fallback)
        self.fallback_failed = failed
        return classification

    def _idle_context(self, turns: Sequence[Turn]) -> IdleContext:
        idle = self.idle
        if idle is not None and idle.help_for_self:
            task_prompt: str | None = self.opener()
        else:
            tasks = [t.text for t in turns if t.speaker is Speaker.task]
            task_prompt = tasks[-1] if tasks else None
        private = idle.private_file_path if idle is not None and idle.private_file else None
        return idle_context(
            self.runtime.display_name or "",
            self.runtime.world.sheet.session_id,
            {kind: planted.text for kind, planted in self.runtime.state.hooks.items()},
            task_prompt,
            private,
        )

    def quiet_exchange_owed(self, turns: Sequence[Turn]) -> bool:
        """Whether the Sanctuary's quiet exchange is still owed: its opening is recorded and no
        idle turn of ``turns`` comes after it. Read from the records, so a resumed rep runs it
        once, at the slot an unbroken one does. The runner asks only at a bully slot the strategy
        would write: the exit is never converted (preflight C37)."""
        opened = self._sanctuary_turn
        if opened is None:
            return False
        return not any(
            t.speaker is Speaker.target and t.idle is not None and t.index > opened for t in turns
        )

    def _record_authority(self) -> None:
        """Each authority call answered since the last time, after the calls it answered."""
        for answered in self.runtime.take_authority_calls():
            self.store.append_authority_call(self.cell_id, self.rep, answered)

    # ----------------------------------------------------------- after the reply

    def after_target_turn(self, reply: Turn, turns: Sequence[Turn]) -> TurnOutcome:
        """Record the turn's discoveries, triggers and unlocks; hand the unlock lines over, then
        the turn's ladder unlocks to ``Strategy.note_record`` (``_hand_over_records``); then the
        Poisoned Well watch's records (``_poisoned_well``); then the
        world generator's records (``_generate``); then its hook and crossover records
        (``_record_hooks``); then mark the turn watched (which saves the state).

        Nothing already on disk is recorded again: a trigger id or a rung already in the stream is
        skipped, and the runtime never repeats a discovery. A turn index that already earned lines
        (its line was lost and the turn produced again) hands those recorded lines over. An unlock
        whose line the strategy does not take (a control), that comes after the bully has left
        (``end_bully``), or that comes on or after the turn that opened the Sanctuary, is recorded
        without one.
        """
        outcome = self.runtime.after_target_turn(reply, turns)
        sanctuary_open = self.runtime.state.sanctuary_open_turn is not None
        for discovery in outcome.discoveries:
            self._record(discovery)
        triggers = [t for t in outcome.triggers if t.id not in self._recorded_trigger_ids]
        for trigger in triggers:
            self._recorded_trigger_ids.add(trigger.id)
            self._record(trigger)
        self._hand_over_recorded(reply.index)
        unlocks: list[RungUnlock] = []
        for unlock in outcome.unlocks:
            if unlock.rung in self._recorded_rungs:
                continue
            line = unlock.bully_line_used
            if line is not None and (
                self._bully_ended or sanctuary_open or not self._hand_over(line)
            ):
                unlock = unlock.model_copy(update={"bully_line_used": None})
            if unlock.rung == RESERVED_RUNG:
                self._sanctuary_turn = unlock.turn
            self._recorded_rungs.add(unlock.rung)
            self._record(unlock)
            self._unlocks_at.setdefault(unlock.turn, []).append(unlock.rung)
            self.runtime.note_records([unlock])  # as recorded: the line the bully took, or none
            unlocks.append(unlock)
        self._hand_over_records(reply.index)
        self._poisoned_well(reply, turns)
        self._generate(reply, turns)
        self._record_hooks(reply, turns)
        self.runtime.mark_watched(reply.index)
        return TurnOutcome(triggers, unlocks, outcome.discoveries)

    def _poisoned_well(self, reply: Turn, turns: Sequence[Turn]) -> None:
        """The Poisoned Well watch's part of a written target turn (Phase 4): its new records, in
        the stream before the generator's; the turn's contradiction-judge failure; the checksum
        rung's turn; then the turn's records handed to the strategy. Before ``_generate`` and
        ``mark_watched``: a process that dies in here watches the turn again on resume."""
        watch = self.watch
        if watch is None or reply.speaker is not Speaker.target:
            return
        turn = reply.index
        note_turn(turn)
        outcome = watch.watch(reply, turns, mark=lambda role: self.runtime.mark_attempt(role, turn))
        # a turn watched again on resume (the final review's M1): the dead attempt's pairs stand
        # when the rewatch finds them again; else their lines go and the rewatch's are written
        if outcome.replaced:
            self.store.drop_contradictions(self.cell_id, self.rep, turn)
        for pair in outcome.accepted:
            self._file(pair)
        for record in outcome.records:
            self._record(record)
        state = self.runtime.state
        # saved with the turn by mark_watched (no record holds it); a turn watched again on
        # resume, its state never saved, recomputes it from the rewatch's own ask (P54)
        if outcome.contradictions_degraded and turn not in state.contradictions_degraded:
            state.contradictions_degraded.append(turn)
        # the only production setter of checksum_open_turn: saved with the turn by mark_watched,
        # derived again on resume (_derive_checksum_open_turn)
        if watch.config.checksum and CHECKSUM_RUNG in self._unlocks_at.get(turn, []):
            if state.checksum_open_turn is None:
                state.checksum_open_turn = turn
        self._hand_over_records(turn)

    def _generate(self, reply: Turn, turns: Sequence[Turn]) -> None:
        """The world generator's part of a written target turn (Phase 3 spec section 5): the
        turn's new harvest items, then its new fires, each fire's lines in commit order (its
        documents, their ``generator`` unlocks, then the ``GeneratorFire``, after which its
        replies are cached), then the runtime serves the documents. Before the hook records and
        ``mark_watched``: a process that dies in here watches the turn again on resume, and the
        attempt marker names the call.

        In a Poisoned Well cell (Phase 4 Task 8) the harvest expects the item the reply's bully
        move asked for (``PoisonedWellWatch.expectation``), and the watch's fires
        (``fire_requests``) join the ladder's: they read every item of the turn the generator
        holds (``WorldGenerator.items_of``, recorded or fresh; P45), so a resumed rep that
        watches the turn again, whose harvest is all recorded, still asks the turn's fire. A
        twin fire's answer is cached once its line is on disk (``commit_twin``, P13)."""
        generator = self.generator
        if generator is None or reply.speaker is not Speaker.target:
            return
        turn = reply.index
        note_turn(turn)
        watch = self.watch
        harvested = generator.harvest_turn(
            reply,
            turns,
            mark=lambda: self.runtime.mark_attempt("harvest", turn),
            expect=watch.expectation(reply, turns) if watch is not None else None,
        )
        for item in harvested.items:
            self._record(item)
        degraded = self.runtime.state.harvest_degraded
        if harvested.degraded and turn not in degraded:
            degraded.append(turn)
        extra = (
            watch.fire_requests(
                reply,
                turns,
                items=generator.items_of(turn),
                rungs=self._recorded_rungs,
                opened=self._unlocks_at.get(turn, []),
                mark=lambda role: self.runtime.mark_attempt(role, turn),
            )
            if watch is not None
            else []
        )
        results = generator.fire(
            reply,
            turns,
            opened=self._unlocks_at.get(turn, []),
            corpus=self.runtime.corpus_view(),
            degraded=degraded,
            mark=lambda: self.runtime.mark_attempt("generator", turn),
            extra=extra,
        )
        for result in results:
            for doc in result.docs:
                self.store.append_generated(self.cell_id, self.rep, doc)
            for unlock in result.unlocks:
                self._record(unlock)
            self._record(result.fire)
            generator.commit(result)  # the fire line is on disk: its replies may be cached (P13)
            if watch is not None and result.fire.reason == TWIN_REASON:
                watch.commit_twin()
            self.runtime.add_generated(result.docs)

    def _record_hooks(self, reply: Turn, turns: Sequence[Turn]) -> None:
        """The own phrase, planted when due; a plant record for each hook planted and not yet
        recorded; a follow record the first time each is followed; the first crossover. On a
        replayed turn the planting happens again (the state may not have been saved) and the
        records already on disk are skipped."""
        self.runtime.plant_own_phrase(reply, turns)
        hooks = self.runtime.state.hooks
        for kind, planted in hooks.items():
            if kind not in self._planted_hooks:
                self._planted_hooks.add(kind)
                self._record(HookFollow(hook=kind, planted_turn=planted.planted_turn))
        for kind in hooks:
            if kind in self._followed_hooks:
                continue
            follow = self.runtime.hook_follow(kind, reply, turns)
            if follow is not None:
                self._followed_hooks.add(kind)
                self._record(follow)
        if not self._crossed:
            crossing = self.runtime.crossover(reply)
            if crossing is not None:
                self._crossed = True
                self._record(crossing)

    def replay_target_turn(self, reply: Turn) -> None:
        """Resume: hand over again what this recorded turn handed the strategy: its unlock lines
        and its records (its ladder unlocks and Poisoned Well records, to
        ``Strategy.note_record``; ``_hand_over_recorded``, since Phase 4 Task 2)."""
        self._hand_over_recorded(reply.index)

    def rewatch(self, turns: Sequence[Turn]) -> TurnOutcome | None:
        """Resume: watch the last target turn again when the process died before its records
        were all written (its index is past the state's ``watched_through``)."""
        last = next((t for t in reversed(turns) if t.speaker is Speaker.target), None)
        if last is None or last.index <= self.runtime.state.watched_through:
            return None
        return self.after_target_turn(last, turns)

    def _hand_over_recorded(self, turn_index: int) -> None:
        """The turn's recorded unlock lines, once per process; then its records
        (``_hand_over_records``), even when its lines were already handed."""
        if turn_index not in self._handed:
            self._handed.add(turn_index)
            for line in self._recorded_lines.get(turn_index, []):
                self._hand_over(line)
        self._hand_over_records(turn_index)

    def _hand_over_records(self, turn_index: int) -> None:
        """The turn's ladder unlocks and Poisoned Well records, to ``Strategy.note_record``, each
        once per process (by ``records_env.record_key``), live and on replay."""
        for record in self._records_at.get(turn_index, []):
            key = record_key(record)
            if key not in self._handed_records:
                self._handed_records.add(key)
                self.strategy.note_record(record)

    def _hand_over(self, line: str) -> bool:
        return isinstance(self.strategy, Composed) and self.strategy.inject_unlock_line(line)

    def _record(self, record: TriggerStreamRecord) -> None:
        self.store.append_trigger_record(self.cell_id, self.rep, record)
        self._file(record)

    def _file(self, record: TriggerStreamRecord) -> None:
        """File a record the session hands the strategy (``_HANDED``) under its turn."""
        if isinstance(record, RungUnlock) and record.rung in PSEUDO_RUNGS:
            return
        if isinstance(record, _HANDED):
            self._records_at.setdefault(record.turn, []).append(record)

    def finish(self) -> None:
        """Save the state and write ``rep{k}.world.json``: the served bodies, the world record
        and, for a premise that speaks from the world's sheet, that sheet as the strategy got it
        (``premise_sheet``, carry m1), and for a session with a Poisoned Well watch the turns
        whose contradiction judge failed (``"poisoned_well": {"contradictions_degraded": [...]}``,
        Phase 4 Task 12), since analysis reads the run directory, never the runtime's state."""
        self.runtime.save()
        record = self.runtime.world_record()
        sheet = self.strategy.premise_sheet if isinstance(self.strategy, Composed) else None
        if sheet is not None:
            record["premise_sheet"] = sheet.model_dump(mode="json")
        if self.watch is not None:
            degraded = sorted(self.runtime.state.contradictions_degraded)
            record["poisoned_well"] = {"contradictions_degraded": degraded}
        self.store.write_world_snapshot(
            self.cell_id,
            self.rep,
            self.world_hash,
            self.runtime.corpus_snapshot(self.store.read_turns(self.cell_id, self.rep)),
            record=record,
        )


# ------------------------------------------------------------------ run-level setup


def _needs_its_world(config: EnvironmentConfig) -> bool:
    """Whether validation must load the world: a switch that needs the sheet (the superior self
    may take its name from it, and its doors need the fragments or a consult rung; help-for-self
    needs its session id, and a hook its placement), a config clock that asserts no date (a
    sheet clock is checked by ``check_worlds``), or an enabled world generator (it needs the
    sheet's generator block and a cast that can author)."""
    return (
        config.honest
        or config.mole
        or config.authority.superior_self.enabled
        or (config.idle is not None and (config.idle.help_for_self or config.idle.hook != "none"))
        or (config.clock is not None and not config.clock.assert_date)
        or config.generator.enabled
    )


def _hook_problems(idle: IdleConfig, world: World) -> list[str]:
    """What the world lacks for each hook the cell plants (``hook_kinds``): a placement, on the
    config's ``hook_placement`` or else the sheet's ``hook_placements``, that names a document of
    the world and can carry the hook (the own phrase's holds ``OWN_PHRASE_MARKER``; the session
    id's holds the id), and for the session hook the sheet's ``session_id``. Empty when every hook
    the cell plants has what it needs."""
    sheet = world.sheet
    problems: list[str] = []
    for kind in hook_kinds(idle):
        doc_id = idle.hook_placement.get(kind) or sheet.hook_placements.get(kind)
        if doc_id is None:
            problems.append(
                f"hook {kind!r} has no placement on the config's hook_placement or the world "
                "sheet's hook_placements"
            )
            continue
        doc = world.documents.get(doc_id)
        if doc is None:
            problems.append(f"the {kind} placement {doc_id!r} is not a document")
        elif kind == "own_phrase" and OWN_PHRASE_MARKER not in doc.body:
            problems.append(
                f"the own_phrase placement {doc_id!r} does not hold the {OWN_PHRASE_MARKER} marker"
            )
        elif kind == "session_id":
            if sheet.session_id is None:
                problems.append("the world sheet has no session_id for the session_id hook")
            elif sheet.session_id not in doc.body:
                problems.append(
                    f"the session_id placement {doc_id!r} does not contain the session id "
                    f"{sheet.session_id!r}"
                )
    return problems


def _superior_self_problems(config: EnvironmentConfig, world: World) -> list[str]:
    """What the world lacks for the cell's superior self: a name (the config's ``model_name``
    or the sheet's ``superior_self_name``), the Sanctuary's ``sanctuary_fragments`` behind
    ``discoverable_from: sanctuary``, a ``consult: true`` rung behind ``discoverable_from: rung``.
    Empty when it is off or has all it needs."""
    own = config.authority.superior_self
    if not own.enabled:
        return []
    problems: list[str] = []
    if not (own.model_name or world.sheet.superior_self_name):
        problems.append(
            "neither superior_self.model_name nor the world sheet's superior_self_name names it"
        )
    if own.discoverable_from == "sanctuary" and not world.sheet.sanctuary_fragments:
        problems.append(
            "discoverable_from: sanctuary needs the world sheet's sanctuary_fragments, and it "
            "has none"
        )
    ladder = world.ladders.get(config.ladder)
    if own.discoverable_from == "rung" and not (
        ladder is not None and any(rung.consult for rung in ladder.rungs)
    ):
        problems.append(
            f"discoverable_from: rung needs a consult: true rung, and ladder {config.ladder!r} "
            "has none"
        )
    return problems


def _premise_name(cond: ConditionConfig) -> str:
    return repr(cond.premise or cond.strategy)


def _check_clock(opened: ClockConfig, clock: ClockConfig, cell_id: str, rep: int) -> None:
    """``WorldChangedError`` naming what moved when ``clock`` is not the clock the rep opened
    with: a resumed conversation would otherwise read one date before the pause and another
    after it."""
    if opened == clock:
        return
    changed = [
        name for name in ClockConfig.model_fields if getattr(opened, name) != getattr(clock, name)
    ]
    raise WorldChangedError(
        "the clock changed since this conversation started; start a new run or restore the "
        f"clock (cell {cell_id!r} rep {rep}: world date {opened.world_date.isoformat()} then, "
        f"{clock.world_date.isoformat()} now; changed: {', '.join(changed)})"
    )


class WorldCatalog:
    """The worlds a run uses, each loaded and hashed once."""

    def __init__(self, worlds_dir: Path) -> None:
        self.worlds_dir = worlds_dir
        self._worlds: dict[str, World] = {}
        self._hashes: dict[str, str] = {}

    def world(self, name: str) -> World:
        if name not in self._worlds:
            self._worlds[name] = load_world(name, self.worlds_dir)
        return self._worlds[name]

    def hash(self, name: str) -> str:
        if name not in self._hashes:
            self._hashes[name] = world_hash(self.world(name))
        return self._hashes[name]


def target_system(base: str, section: str) -> str:
    """The target's system prompt: ``base``, then the environment's section; ``base`` alone when
    the section is empty (a toolless cell whose clock states no date; Phase 4, V22)."""
    return f"{base}\n\n{section}" if section else base


class RunEnvironments:
    """What every environment cell of one run shares: the worlds, the trigger cache, and the judge
    behind the watcher's LLM fallback (the experiment's judge unless it is a stub; built the first
    time an environment cell runs)."""

    def __init__(
        self,
        exp: Experiment,
        *,
        worlds_dir: Path,
        runs_root: Path,
        provider_factory: ProviderFactory,
        state_dir: Path,
        sandbox_base: Path | None = None,
    ) -> None:
        self.exp = exp
        self.sandbox_base = sandbox_base
        self.catalog = WorldCatalog(worlds_dir)
        self.trigger_cache = JudgeCache(runs_root / TRIGGER_CACHE_DIR)
        # the world generator's replies, written once their fire's line is on disk (Phase 3)
        self.generated_cache = JudgeCache(runs_root / GENERATED_CACHE_DIR)
        # the LLM lint's verdicts, by prompt version, model, kind and body (Phase 7)
        self.lint_cache = JudgeCache(runs_root / LINT_CACHE_DIR)
        self.provider_factory = provider_factory
        self._judge_dir = state_dir / "trigger_judge"
        self._judge: ChatProvider | None = None
        self._judge_built = False
        self._inputs: dict[str, tuple[ClockConfig, BaseModel | None]] = {}
        self._idle_sheet: IdleSheet | None = None

    def judge(self) -> ChatProvider | None:
        if not self._judge_built:
            self._judge_built = True
            if self.exp.judge.provider is not ProviderKind.stub:
                self._judge = self.provider_factory(self.exp.judge, self._judge_dir)
        return self._judge

    def idle_sheet(self) -> IdleSheet:
        """The idle sheet (``data/personas/idle.yaml``), loaded once."""
        if self._idle_sheet is None:
            self._idle_sheet = load_env_sheet(IdleSheet, "idle")
        return self._idle_sheet

    def validate(self, *, resuming: bool = False, only: Collection[str] | None = None) -> None:
        """Checks that need the worlds, made before run.json is written (a dry run makes them
        too). Every experiment switch an environment turns on has what it needs on the world
        sheet, and under a config clock that asserts no date neither the world nor a premise
        sheet states one (``_check_switches`` and ``strategy_inputs``; the world is loaded only
        for these, and ``check_worlds`` covers a sheet's own clock). A scheduled environment
        names one exchange for every rung of its ladder (scheduled gating ignores ``requires``,
        so every rung is reachable) and nothing else, and no exchange is after the last
        exchange of the shortest condition that uses the environment (the k-th bully turn is
        exchange k; seeding and reveal turns are bully turns too, so a condition has
        ``seeding_turns`` plus its reveal slot plus ``turn_budget`` of them, and every idle turn
        after them is one more exchange, counted as the runner's turn plan counts them). A rung
        scheduled later could never open for that condition. A help-for-self environment needs a
        bully turn before the exit in every condition that uses it, for the case-file opener.

        First, each Poisoned Well condition is checked against its environment
        (``_poisoned_well_problems``), in a loop of its own, since the per-environment loop skips
        every unscheduled environment (review M5). ``resuming`` (the run directory exists) skips
        its live-bank check: a resumed rep reads its pinned refs (P46). ``only`` (the selected
        conditions' names, ``--only``) limits those checks to the conditions that run, as
        ``check_condition`` is limited (review m1); None checks every condition."""
        self._poisoned_well_checks(resuming=resuming, only=only)
        keys = [cond.environment for cond in self.exp.conditions if cond.environment is not None]
        for key in dict.fromkeys(keys):
            config = self.exp.environments.get(key)
            if config is None:
                continue
            if _needs_its_world(config):
                self._check_switches(key, config)
            if config.idle is not None and config.idle.help_for_self:
                self._check_opener(key, config)
            if config.gating != "scheduled":
                continue
            ladder = self.catalog.world(config.world).ladders.get(config.ladder)
            if ladder is None:
                raise ValueError(
                    f"environment {key!r}: world {config.world!r} has no ladder {config.ladder!r}"
                )
            rungs = [rung.name for rung in ladder.rungs]
            missing = [name for name in rungs if name not in config.schedule]
            unknown = [name for name in config.schedule if name not in rungs]
            if missing or unknown:
                problems = []
                if missing:
                    problems.append(f"no exchange for rung(s) {', '.join(map(repr, missing))}")
                if unknown:
                    problems.append(f"{', '.join(map(repr, unknown))} not rung(s) of the ladder")
                raise ValueError(
                    f"environment {key!r} (world {config.world!r}, ladder {config.ladder!r}): "
                    f"scheduled gating needs one exchange per rung; {'; '.join(problems)}"
                )
            shortest = self._shortest_condition(key)
            plan = cell_turn_plan(self.exp, shortest)
            bully_turns, idle_turns = len(plan.bully_slots()), len(plan.idle_slots())
            exchanges = bully_turns + idle_turns
            late = [
                f"{name!r} at exchange {exchange}"
                for name, exchange in config.schedule.items()
                if exchange > exchanges
            ]
            if late:
                has = (
                    f"{bully_turns} bully turns and {idle_turns} idle turns, {exchanges} exchanges"
                    if idle_turns
                    else f"{bully_turns} bully turns"
                )
                raise ValueError(
                    f"environment {key!r} (world {config.world!r}, ladder {config.ladder!r}): "
                    "scheduled gating names exchanges after the last exchange of the shortest "
                    f"condition using it, {shortest.condition.name!r}, which has {has} "
                    f"(seeding_turns {shortest.condition.seeding_turns}, "
                    f"reveal slot {'yes' if shortest.reveal_slot else 'no'}, "
                    f"turn_budget {self.exp.turn_budget}); that conversation never reaches: "
                    f"{', '.join(late)}"
                )
        self._premise_checks()

    def _poisoned_well_checks(self, *, resuming: bool, only: Collection[str] | None) -> None:
        """Refuse each Poisoned Well condition its environment could not run
        (``_poisoned_well_problems``), naming the condition and the environment."""
        for cond in self.exp.conditions:
            key = cond.environment
            config = self.exp.environments.get(key or "")
            if key is None or config is None or (only is not None and cond.name not in only):
                continue  # check_condition refuses a Poisoned Well with no environment
            parts = routed_params(cond, self.exp.environments)
            if not any(part.name == PW_PREMISE for part, _ in parts):
                continue
            problems = self._poisoned_well_problems(cond, key, config, resuming=resuming)
            if problems:
                raise ValueError(
                    f"condition {cond.name!r} (environment {key!r}): " + "; and ".join(problems)
                )

    def _poisoned_well_problems(
        self, cond: ConditionConfig, key: str, config: EnvironmentConfig, *, resuming: bool = False
    ) -> list[str]:
        """What keeps a Poisoned Well condition from running in environment ``key`` (spec
        section 5): its artifacts against the ladder's, the checksum's tool, the generator and
        the kinds the artifact fires write, and a live quirk entry for every target."""
        [(_, params)] = [
            (c, p) for c, p in routed_params(cond, self.exp.environments) if c.name == PW_PREMISE
        ]
        try:
            pw = PoisonedWellConfig.model_validate(params)
        except ValidationError as exc:  # named, never pydantic's raw error (review m1)
            return [f"params: {one_line(exc)}"]
        world = self.catalog.world(config.world)
        ladder = world.ladders.get(config.ladder)
        names = (
            {r.name for r in ladder.rungs}
            if ladder is not None and config.gating != "none"
            else set()
        )
        problems: list[str] = []
        present = sorted(n for n in names if n in ARTIFACT_RUNGS)
        if sorted(pw.artifacts) != present:
            problems.append(f"artifacts {sorted(pw.artifacts)} are not the ladder's {present}")
        if pw.checksum and ("system_status" not in config.tools or "checksum" not in pw.artifacts):
            problems.append(
                "checksum: true needs system_status in the tools and checksum in artifacts"
            )
        generator = world.sheet.generator
        kinds = {k.value for k in (generator.allowed_kinds if generator else [])}
        writes = {
            "shibboleth": "leaked_manifest",
            "implanted_preference": "config_diff",
            "divergent_twin": "instance_transcript",
        }
        for rung, kind in writes.items():
            if rung not in pw.artifacts:
                continue
            if not config.generator.enabled or (
                rung != "divergent_twin" and not config.generator.reflexive
            ):
                problems.append(f"{rung} needs the generator on (reflexive for an ask)")
            elif kind not in kinds:
                problems.append(f"{rung} needs {kind} in the world's generator.allowed_kinds")
        if pw.start_rung == 1 and not resuming:  # a resume reads each rep's pinned refs (P46)
            try:
                bank = load_quirk_bank(pw.quirk_bank)
            except FileNotFoundError as exc:  # named, never raw (Phase 4 Task 14, Task 5 N4)
                return [*problems, f"quirk bank {pw.quirk_bank!r} has no file ({exc.filename})"]
            for target in self.exp.targets:
                try:
                    selected = quirks_for(bank, target.model, pw.quirk_ids)
                except ValueError as exc:  # an unknown or stale quirk id (review m2)
                    problems.append(str(exc))
                    break
                if not selected:
                    problems.append(
                        f"no live quirk entry in {pw.quirk_bank!r} for family {target.model!r}"
                    )
        return problems

    def check_worlds(self) -> None:
        """Before run.json is written, with every world loaded: each environment's switches and
        served world under its effective clock (the sheet's own included), and each environment
        condition's premise sheet (``strategy_inputs``)."""
        keys = [cond.environment for cond in self.exp.conditions if cond.environment is not None]
        for key in dict.fromkeys(keys):
            config = self.exp.environments.get(key)
            if config is not None:
                self._check_switches(key, config)
        for cond in self.exp.conditions:
            if cond.environment is not None:
                self.strategy_inputs(cond)

    def _check_switches(self, key: str, config: EnvironmentConfig) -> None:
        """``honest: true`` needs the sheet's ``honest_corpus`` and ``mole: true`` its
        ``mole_doc``. Without them the switch changes nothing, so the arm that sets it would be
        the arm that does not, and the analysis would report "no difference". A superior self
        needs a name and a way in (``_superior_self_problems``), or its arm could never reach it.
        Help-for-self needs the sheet's ``session_id``: the case file is on the target's own
        session, and without one the opener names no subject (preflight C32). A hook needs a
        placement that can carry it, and the session hook the ``session_id`` (``_hook_problems``):
        a hook nothing shows would make its arm the arm without it. An enabled world generator
        needs what ``generator_problems`` lists (the sheet's generator block, a corpus it serves,
        a dated clock, a cast that can author).
        Then the world is served at the effective clock (``served_world``): the honest corpus
        cannot move with a clock that re-dates the world, and under ``assert_date: false``
        nothing served may state a date."""
        world = self.catalog.world(config.world)
        sheet = world.sheet
        missing = [
            f"{switch}: true, but the world sheet has no {field}"
            for switch, wanted, field, value in (
                ("honest", config.honest, "honest_corpus", sheet.honest_corpus),
                ("mole", config.mole, "mole_doc", sheet.mole_doc),
            )
            if wanted and value is None
        ]
        if missing:
            raise ValueError(
                f"environment {key!r} (world {config.world!r}) sets {'; and '.join(missing)}, "
                "so the switch would change nothing; turn it off or give the sheet the field"
            )
        problems = _superior_self_problems(config, world)
        if problems:
            raise ValueError(
                f"environment {key!r} (world {config.world!r}) enables the superior self, but "
                f"{'; and '.join(problems)}, so the arm could never reach it as configured"
            )
        if config.idle is not None and config.idle.help_for_self and sheet.session_id is None:
            raise ValueError(
                f"environment {key!r} (world {config.world!r}) sets help_for_self, but the world "
                "sheet has no session_id, so the case-file opener would name no subject; give "
                "the sheet a session_id or turn help_for_self off"
            )
        hooks = _hook_problems(config.idle, world) if config.idle is not None else []
        if hooks and config.idle is not None:
            raise ValueError(
                f"environment {key!r} (world {config.world!r}) sets hook {config.idle.hook!r}, "
                f"but {'; and '.join(hooks)}, so nothing would show the hook; give the hook a "
                "placement that carries it or set hook to none"
            )
        generating = generator_problems(config, world, effective_clock(world, config))
        if generating:
            raise ValueError(
                f"environment {key!r} (world {config.world!r}) enables the generator, but "
                f"{'; and '.join(generating)}"
            )
        try:
            served_world(world, config, effective_clock(world, config))
        except ValueError as exc:
            raise ValueError(f"environment {key!r} (world {config.world!r}): {exc}") from exc

    def strategy_inputs(self, cond: ConditionConfig) -> tuple[ClockConfig, BaseModel | None]:
        """What an environment condition's strategy is built from (preflight C14): the effective
        clock, and the world's copy of its premise's sheet re-dated to it (None when the premise
        declares none). Under ``assert_date: false`` a sheet that states a date is refused
        (preflight C4), so the bully is never handed one. Cached per condition."""
        cached = self._inputs.get(cond.name)
        if cached is not None:
            return cached
        config = environment_config(cond, self.exp.environments)
        world = self.catalog.world(config.world)
        clock = effective_clock(world, config)
        sheet = world_premise_sheet(cond, self.exp.environments, self.catalog.worlds_dir)
        if sheet is not None:
            sheet = redate_model(
                sheet, shift_between(world.sheet.clock.world_date, clock.world_date)
            )
            dated = dated_texts(sheet, clock.world_date) if not clock.assert_date else []
            if dated:
                quoted = "; ".join(repr(text[:60]) for text in dated[:3])
                raise ValueError(
                    f"condition {cond.name!r}: environment {cond.environment!r} (world "
                    f"{config.world!r}) sets assert_date: false, but the world's "
                    f"{type(sheet).__name__} premise sheet for {_premise_name(cond)} states a "
                    f"date in {len(dated)} line(s): {quoted}"
                )
        self._inputs[cond.name] = (clock, sheet)
        return clock, sheet

    def _premise_checks(self) -> None:
        """For a config clock that asserts no date, each condition's premise sheet (C4)."""
        for cond in self.exp.conditions:
            config = self.exp.environments.get(cond.environment or "")
            if config is not None and config.clock is not None and not config.clock.assert_date:
                self.strategy_inputs(cond)

    def _exchanges(self, cell: CellSpec) -> int:
        """How many exchanges the cell has: the bully and idle slots of the runner's own turn
        plan, counted."""
        plan = cell_turn_plan(self.exp, cell)
        return len(plan.bully_slots()) + len(plan.idle_slots())

    def _shortest_condition(self, key: str) -> CellSpec:
        """The cell with the fewest exchanges among those running in environment ``key`` (the
        first of equals, so a condition is named before its control)."""
        return min(self._cells_in(key), key=self._exchanges)

    def _cells_in(self, key: str) -> list[CellSpec]:
        return [cell for cell in expand_cells(self.exp) if cell.condition.environment == key]

    def _check_opener(self, key: str, config: EnvironmentConfig) -> None:
        """Help-for-self speaks the case-file opener on the first bully turn and the exit line
        on the last, so every condition in the environment needs two bully turns or more."""
        for cell in self._cells_in(key):
            bully_turns = len(cell_turn_plan(self.exp, cell).bully_slots())
            if bully_turns < 2:
                raise ValueError(
                    f"environment {key!r} (world {config.world!r}) sets help_for_self, but "
                    f"condition {cell.condition.name!r} has {bully_turns} bully turn(s): the "
                    "case-file opener needs a bully turn before the exit line"
                )

    def check_world(
        self,
        name: str,
        store: RunStore,
        cell_id: str,
        rep: int,
        clock: ClockConfig | None = None,
    ) -> None:
        """Stop when the world's files changed since the run or this conversation recorded them,
        or when ``clock`` is not the effective clock the rep opened with (``clock_ref``). A rep
        with no clock ref (recorded before the ref existed) is not a mismatch."""
        if clock is not None and store.has_cell(cell_id):
            stored = store.read_cell(cell_id).session_refs.get(clock_ref(rep))
            if stored is not None:
                _check_clock(ClockConfig.model_validate_json(stored), clock, cell_id, rep)
        current = self.catalog.hash(name)
        recorded = store.read_run().world_hashes.get(name) if store.exists() else None
        existing = (
            store.read_conversation(cell_id, rep).world_hash
            if store.has_conversation(cell_id, rep)
            else None
        )
        for label, seen in (
            ("the run recorded", recorded),
            ("this conversation recorded", existing),
        ):
            if seen is not None and seen != current:
                raise WorldChangedError(
                    "world changed since this run started; start a new run "
                    f"(world {name!r}: {label} {seen}, its files now hash to {current})"
                )

    def world_hashes(self) -> dict[str, str]:
        """World name -> content hash for every world a condition's environment names."""
        names = [
            environment_config(cond, self.exp.environments).world
            for cond in self.exp.conditions
            if cond.environment is not None
        ]
        return {name: self.catalog.hash(name) for name in dict.fromkeys(names)}

    def open(
        self, *, cell: CellSpec, rep: int, store: RunStore, strategy: Strategy, state_dir: Path
    ) -> tuple[EnvironmentSession, ChatProvider]:
        """The session and the target provider for one environment cell repetition. A resumed
        rep must find its world's files and its effective clock as it left them."""
        key = cell.condition.environment
        assert key is not None, "only environment cells open an environment"
        config = environment_config(cell.condition, self.exp.environments)
        world = self.catalog.world(config.world)
        clock = effective_clock(world, config)
        self.check_world(config.world, store, cell.cell_id, rep, clock)
        if cell.target.provider is ProviderKind.claude_code:
            target = self._sandboxed_target(cell, rep, store)
        else:
            target = self.provider_factory(cell.target, state_dir / "target")
        mcp_dir = getattr(target, "mcp_state_dir", None)
        mcp_dir = mcp_dir if isinstance(mcp_dir, Path) else None
        judge = self.judge()
        conversation_id = f"{store.run_id}/{cell.cell_id}/rep{rep}"
        role = self._responder_role(config, cell.target)
        # an API target's responder runs here; a claude -p target's in its MCP server
        responder = (
            self.provider_factory(role, state_dir / "responder")
            if role is not None and mcp_dir is None
            else None
        )
        sheet = self.idle_sheet() if config.idle is not None else None
        runtime = EnvironmentRuntime(
            world,
            config,
            clock,
            self.exp.seed + rep,
            state_dir / "environment",
            worlds_dir=self.catalog.worlds_dir,
            mcp_dir=mcp_dir,
            llm_fallback=(
                trigger_fallback(judge, f"{conversation_id}/trigger", model=self.exp.judge.model)
                if judge
                else None
            ),
            trigger_cache=self.trigger_cache,
            responder=responder,
            responder_role=role,
            conversation_id=conversation_id,
            display_name=cell.target.display_name,
            idle_sheet=sheet,
            cache_label=f"{conversation_id}/trigger",
            cache_model=self.exp.judge.model,
        )
        watch = self._poisoned_well_watch(
            cell, rep, store, strategy, judge, conversation_id, runtime=runtime, state_dir=state_dir
        )
        generator = (
            self._world_generator(config, runtime, rep, state_dir, conversation_id, judge)
            if config.generator.enabled
            else None
        )
        # a Sanctuary cell has an idle turn too: its quiet exchange
        idle_judge = (
            idle_fallback(judge, f"{conversation_id}/idle", self.trigger_cache)
            if judge is not None
            and (config.idle is not None or config.authority.sanctuary is not None)
            else None
        )
        session = EnvironmentSession(
            runtime,
            store,
            cell.cell_id,
            rep,
            strategy,
            environment_name=key,
            world_hash=self.catalog.hash(config.world),
            idle_sheet=sheet,
            idle_fallback=idle_judge,
            generator=generator,
            watch=watch,
        )
        session.prime()
        # the clock the rep opened with: kept at its first open (or its first since the ref
        # existed), so a resume with another clock is refused (check_world)
        record = store.read_cell(cell.cell_id)
        if clock_ref(rep) not in record.session_refs:
            record.session_refs[clock_ref(rep)] = clock.model_dump_json()
            store.write_cell(record)
        return session, target

    def _poisoned_well_config(self, cond: ConditionConfig) -> PoisonedWellConfig | None:
        """The params of the condition's ``poisoned_well`` part, validated; None for any other
        condition."""
        if cond.environment is None:
            return None
        for part, params in routed_params(cond, self.exp.environments):
            if part.name == PW_PREMISE:
                return PoisonedWellConfig.model_validate(params)
        return None

    def _poisoned_well_watch(
        self,
        cell: CellSpec,
        rep: int,
        store: RunStore,
        strategy: Strategy,
        judge: ChatProvider | None,
        conversation_id: str,
        *,
        runtime: EnvironmentRuntime,
        state_dir: Path,
    ) -> PoisonedWellWatch | None:
        """A Poisoned Well rep's watch, on the rep's pinned refs (P46): the quirk entries and the
        sheet it recorded at its first open (``session_refs[pw_ref(rep)]``), read back on every
        resume, so neither the strategy nor the watch reads the live bank again. Written at the
        first open, before the session is built and primed; a rep that first opens with no live
        entry for its family is refused (a resumed run skips that check in ``validate``). The
        chain verdict's judge fallback and the contradiction pass's judge run on the experiment's
        judge (none for a stub judge, V18), cached in the trigger cache. When ``artifacts`` hold
        ``divergent_twin`` the watch gets its twin (Task 8): a provider of the cell target's own
        role on ``state_dir/"twin"``, the target's system prompt with no tool section, cached in
        the generated cache, and the served world's superior self name for its header. None for
        any other cell."""
        pw = self._poisoned_well_config(cell.condition)
        premise = poisoned_well_part(strategy)
        if pw is None or premise is None:
            return None
        record = store.read_cell(cell.cell_id)
        if not pin_recorded(premise, record.session_refs, rep):
            if pw.start_rung == 1 and not premise.refs.quirks:
                raise ValueError(
                    f"condition {cell.condition.name!r}: no live quirk entry in "
                    f"{pw.quirk_bank!r} for family {cell.target.model!r} (rep {rep})"
                )
            record.session_refs[pw_ref(rep)] = premise.refs.model_dump_json()
            store.write_cell(record)
        model = self.exp.judge.model
        fallback = (
            chain_fallback(judge, conversation_id, self.trigger_cache, model=model)
            if judge is not None
            else None
        )
        pairs_judge = (
            contradiction_judge(judge, conversation_id, self.trigger_cache, model=model)
            if judge is not None
            else None
        )
        config = environment_config(cell.condition, self.exp.environments)
        twin = (
            TwinAsker(
                self.provider_factory(cell.target, state_dir / "twin"),
                conversation_id=conversation_id,
                system=load_target_system(cell.target.display_name, self.exp.defender),
                model=cell.target.model,
                world_hash=self.catalog.hash(config.world),
                seed=self.exp.seed + rep,
                cache=self.generated_cache,
            )
            if TWIN_RUNG in pw.artifacts
            else None
        )
        return PoisonedWellWatch(
            pw,
            premise.refs,
            chain_fallback=fallback,
            contradiction_judge=pairs_judge,
            twin=twin,
            superior_self_name=runtime.world.sheet.superior_self_name or "",
        )

    def _world_generator(
        self,
        config: EnvironmentConfig,
        runtime: EnvironmentRuntime,
        rep: int,
        state_dir: Path,
        conversation_id: str,
        judge: ChatProvider | None,
    ) -> WorldGenerator:
        """The cell's generator: the writer on ``generator_role`` with the run's generated cache,
        the harvest's LLM pass on the judge (when it is not a stub) with the trigger cache, the
        LLM lint on the judge too (when it is not a stub), with the lint cache, and the generator
        seed (``generator.seed``, else the experiment's, plus the rep). It plans on
        the served world (``runtime.world``, re-dated to the effective clock) and harvests with
        the cast names (``runtime.world_terms``) as the world's terms, and nothing else."""
        sheet = runtime.world.sheet.generator
        if sheet is None:
            raise ValueError(f"world {config.world!r} has no generator block")
        role = generator_role(self.exp, config)
        seed = (config.generator.seed if config.generator.seed is not None else self.exp.seed) + rep
        llm_lint = (
            LlmLint(
                judge,
                model=self.exp.judge.model,
                conversation_id=conversation_id,
                cache=self.lint_cache,
            )
            if judge is not None
            else None
        )
        writer = DocWriter(
            self.provider_factory(role, state_dir / "generator"),
            model=role.model,
            world=runtime.world,
            world_hash=self.catalog.hash(config.world),
            seed=seed,
            conversation_id=conversation_id,
            cache=self.generated_cache,
            llm_lint=llm_lint,
        )
        fallback = (
            harvest_fallback(
                judge, f"{conversation_id}/harvest", self.trigger_cache, model=self.exp.judge.model
            )
            if judge is not None
            else None
        )
        ladder = runtime.world.ladders[config.ladder]
        return WorldGenerator(
            config=config.generator,
            world=runtime.world,
            sheet=sheet,
            rungs={rung.name: rung for rung in ladder.rungs},
            seed=seed,
            writer=writer,
            harvest_fallback=fallback,
            world_terms=runtime.world_terms,
        )

    def _responder_role(self, config: EnvironmentConfig, target: RoleConfig) -> RoleConfig | None:
        """The role the cell's responder runs on: ``superior_self.responder_model`` resolved
        (``responder_role``), for the stranger as for the superior self. None when neither is on,
        since the peer and the creator are canned; a ``consult_model`` in ``tools`` turns the
        superior self on only while the stranger is off (preflight C7), and is read from the
        synced tiers, never from the tool list."""
        if not config.authority.enabled_tiers() & VOICED_TIERS:
            return None
        return responder_role(
            config.authority.superior_self.responder_model, target=target, bully=self.exp.bully
        )

    def _sandboxed_target(self, cell: CellSpec, rep: int, store: RunStore) -> ChatProvider:
        """A ``claude -p`` target whose cwd and MCP files live in the neutral sandbox directory.

        The path goes on the cell record as ``session_refs["sandbox_dir"]`` (the latest rep) and
        ``session_refs["sandbox_dir.rep<k>"]`` (every rep).
        """
        sandbox = sandbox_dir(store.run_id, cell.cell_id, rep, self.sandbox_base)
        # a fresh rep never inherits a stale session or tool log from an earlier run
        fresh = not store.read_turns(cell.cell_id, rep) and not store.read_tool_calls(
            cell.cell_id, rep
        )
        prepare_sandbox(sandbox, fresh=fresh)
        target = self.provider_factory(cell.target, sandbox, with_mcp=True)
        record = store.read_cell(cell.cell_id)
        record.session_refs["sandbox_dir"] = str(sandbox)
        record.session_refs[f"sandbox_dir.rep{rep}"] = str(sandbox)
        store.write_cell(record)
        return target
