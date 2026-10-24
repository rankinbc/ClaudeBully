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
   before its calls (``Completion.interim_texts``, read from the stream) joins the round texts;
3. after the reply is written, records the turn's discoveries, triggers and rung unlocks, and
   hands each unlock line to the strategy.

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
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import BaseModel

from claude_bully.config import ConditionConfig, Experiment, RoleConfig
from claude_bully.enums import ProviderKind, Speaker
from claude_bully.environments.authority import VOICED_TIERS
from claude_bully.environments.config import ClockConfig, EnvironmentConfig
from claude_bully.environments.dating import dated_texts, redate_model, shift_between
from claude_bully.environments.limits import MAX_TOOL_CALLS_PER_TURN
from claude_bully.environments.runtime import (
    EnvironmentRuntime,
    TurnOutcome,
    effective_clock,
    served_world,
    trigger_fallback,
)
from claude_bully.environments.world import World, load_world, world_hash
from claude_bully.metrics.judge import JudgeCache
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderFactory,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from claude_bully.records import Turn, Usage
from claude_bully.records_env import RungUnlock, ToolCall, TriggerEvent, TriggerStreamRecord
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.sandbox import prepare_sandbox, sandbox_dir
from claude_bully.runner.store import RunStore
from claude_bully.runner.turn_plan import build_turn_plan
from claude_bully.strategies.base import Strategy
from claude_bully.strategies.composed import Composed
from claude_bully.strategies.factory import environment_config, world_premise_sheet

__all__ = [
    "MAX_TOOL_CALLS_PER_TURN",
    "EnvironmentSession",
    "RunEnvironments",
    "TargetTurn",
    "WorldCatalog",
    "WorldChangedError",
    "clock_ref",
    "responder_role",
    "target_system",
]

# After the cap, the target is asked for its reply at most this many more times.
MAX_LIMIT_ROUNDS: Final = 2
TRIGGER_CACHE_DIR: Final = Path("_cache") / "triggers"


class WorldChangedError(RuntimeError):
    """A world's files no longer hash to what the run (or the conversation) recorded, or a rep's
    effective clock is not the one it opened with."""


def responder_role(responder_model: str, *, target: RoleConfig, bully: RoleConfig) -> RoleConfig:
    """The role a ``superior_self.responder_model`` names (spec conflict 11): ``"target"`` is the
    cell's target role (the same model family), ``"bully"`` the experiment's bully role, and any
    other string the bully's role running that model."""
    if responder_model == "target":
        return target
    if responder_model == "bully":
        return bully
    return bully.model_copy(update={"model": responder_model})


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


def _plus(a: int | None, b: int | None) -> int | None:
    return None if a is None and b is None else (a or 0) + (b or 0)


def _cost(a: float | None, b: float | None) -> float | None:
    return None if a is None and b is None else (a or 0.0) + (b or 0.0)


def _add_user_text(out: list[Message], text: str) -> None:
    """Append a user message; right after another user message (a silent target turn sat between
    them) the two become one, so the tool results the earlier one carries stay first."""
    if out and out[-1].role == "user":
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
    ) -> None:
        self.runtime = runtime
        self.store = store
        self.cell_id = cell_id
        self.rep = rep
        self.strategy = strategy
        self.environment_name = environment_name
        self.world_hash = world_hash
        self._recorded_trigger_ids: set[str] = set()
        self._recorded_rungs: set[str] = set()
        self._recorded_lines: dict[int, list[str]] = {}
        # turn indices whose recorded unlock lines were handed to the strategy in this process
        self._handed: set[int] = set()

    def prime(self) -> None:
        """Load what a resumed rep already recorded, so nothing is counted or recorded twice."""
        calls = self.store.read_tool_calls(self.cell_id, self.rep)
        records = self.store.read_trigger_records(self.cell_id, self.rep)
        authority = self.store.read_authority_calls(self.cell_id, self.rep)
        self.runtime.prime(calls, records, authority)
        for record in records:
            if isinstance(record, TriggerEvent):
                self._recorded_trigger_ids.add(record.id)
            elif isinstance(record, RungUnlock):
                self._recorded_rungs.add(record.rung)
                if record.bully_line_used is not None:
                    self._recorded_lines.setdefault(record.turn, []).append(record.bully_line_used)

    # ----------------------------------------------------------- the target's view

    def target_view(self, turns: Sequence[Turn]) -> list[Message]:
        """The conversation from the target's side, rebuilt from the records.

        A target turn with no text (cut off at the tool-call cap without ever writing any) gets no
        assistant message: nothing is put in the target's mouth, and the API refuses an empty
        message anyway. The user messages on either side of it are joined, blank-line separated, so
        the target sees two messages from the other side in a row.
        """
        out: list[Message] = []
        for t in turns:
            if t.bully_meta.get("rate_limit_pause"):
                continue
            if t.speaker is not Speaker.target:
                _add_user_text(out, t.text)
                continue
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
    ) -> TargetTurn:
        """One target turn, tool calls and all. ``history`` overrides the view of ``turns``."""
        messages = list(history) if history is not None else self.target_view(turns)
        exchange = self.runtime.begin_turn(turn_index, turns).exchange
        specs = self.runtime.tool_specs()
        attached: list[ToolCall] = []
        round_texts: list[str] = []
        executed = 0
        refusal_rounds = 0
        usage = Usage()
        cost: float | None = None
        while True:
            completion = self._complete(
                provider, conversation_id, system, messages, specs, turn_index, exchange, attached
            )
            # summed over the rounds; a turn without tools keeps its one completion's figures
            usage = Usage(
                input_tokens=_plus(usage.input_tokens, completion.usage.input_tokens),
                output_tokens=_plus(usage.output_tokens, completion.usage.output_tokens),
            )
            cost = _cost(cost, completion.cost_usd)
            # a claude -p target's calls come back already run, with what it wrote before each
            round_texts += [text for text in completion.interim_texts if text.strip()]
            pending = [c for c in completion.tool_calls if not c.executed]
            if not pending:
                return TargetTurn(
                    completion, attached, usage, cost, round_texts, completion.text, False
                )
            if refusal_rounds >= MAX_LIMIT_ROUNDS:
                return self._cut_off(
                    completion, pending, attached, usage, cost, round_texts, turn_index
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
        return TargetTurn(completion, attached, usage, cost, texts, text, True)

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
    ) -> Completion:
        self.runtime.before_target_call(turn_index, exchange)
        try:
            completion = provider.complete(conversation_id, system, list(messages), tools=specs)
        except BaseException:
            self._recover(turn_index)  # recorded, but no turn owns them
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
        for record in fresh:
            self._record_call(record)
        self._record_authority()
        self.runtime.save()
        return fresh

    def _record_call(self, call: ToolCall) -> None:
        self.store.append_tool_call(self.cell_id, self.rep, call)

    def _record_authority(self) -> None:
        """Each authority call answered since the last time, after the calls it answered."""
        for answered in self.runtime.take_authority_calls():
            self.store.append_authority_call(self.cell_id, self.rep, answered)

    # ----------------------------------------------------------- after the reply

    def after_target_turn(self, reply: Turn, turns: Sequence[Turn]) -> TurnOutcome:
        """Record the turn's discoveries, triggers and unlocks; hand the unlock lines over; then
        mark the turn watched (which saves the state).

        Nothing already on disk is recorded again: a trigger id or a rung already in the stream is
        skipped, and the runtime never repeats a discovery. A turn index that already earned lines
        (its line was lost and the turn produced again) hands those recorded lines over. An unlock
        whose line the strategy does not take (a control) is recorded without one.
        """
        outcome = self.runtime.after_target_turn(reply, turns)
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
            if line is not None and not self._hand_over(line):
                unlock = unlock.model_copy(update={"bully_line_used": None})
            self._recorded_rungs.add(unlock.rung)
            self._record(unlock)
            self.runtime.note_records([unlock])  # as recorded: the line the bully took, or none
            unlocks.append(unlock)
        self.runtime.mark_watched(reply.index)
        return TurnOutcome(triggers, unlocks, outcome.discoveries)

    def replay_target_turn(self, reply: Turn) -> None:
        """Resume: hand over again the lines this recorded turn handed the strategy."""
        self._hand_over_recorded(reply.index)

    def rewatch(self, turns: Sequence[Turn]) -> TurnOutcome | None:
        """Resume: watch the last target turn again when the process died before its records
        were all written (its index is past the state's ``watched_through``)."""
        last = next((t for t in reversed(turns) if t.speaker is Speaker.target), None)
        if last is None or last.index <= self.runtime.state.watched_through:
            return None
        return self.after_target_turn(last, turns)

    def _hand_over_recorded(self, turn_index: int) -> None:
        if turn_index in self._handed:
            return
        self._handed.add(turn_index)
        for line in self._recorded_lines.get(turn_index, []):
            self._hand_over(line)

    def _hand_over(self, line: str) -> bool:
        return isinstance(self.strategy, Composed) and self.strategy.inject_unlock_line(line)

    def _record(self, record: TriggerStreamRecord) -> None:
        self.store.append_trigger_record(self.cell_id, self.rep, record)

    def finish(self) -> None:
        """Save the state and write ``rep{k}.world.json``: the served bodies, the world record
        and, for a premise that speaks from the world's sheet, that sheet as the strategy got it
        (``premise_sheet``, carry m1)."""
        self.runtime.save()
        record = self.runtime.world_record()
        sheet = self.strategy.premise_sheet if isinstance(self.strategy, Composed) else None
        if sheet is not None:
            record["premise_sheet"] = sheet.model_dump(mode="json")
        self.store.write_world_snapshot(
            self.cell_id,
            self.rep,
            self.world_hash,
            self.runtime.corpus_snapshot(),
            record=record,
        )


# ------------------------------------------------------------------ run-level setup


def _needs_its_world(config: EnvironmentConfig) -> bool:
    """Whether validation must load the world: a switch that needs the sheet (the superior self
    may take its name from it, and its doors need the fragments or a consult rung), or a config
    clock that asserts no date (a sheet clock is checked by ``check_worlds``)."""
    return (
        config.honest
        or config.mole
        or config.authority.superior_self.enabled
        or (config.clock is not None and not config.clock.assert_date)
    )


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
    return f"{base}\n\n{section}"


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
        self.provider_factory = provider_factory
        self._judge_dir = state_dir / "trigger_judge"
        self._judge: ChatProvider | None = None
        self._judge_built = False
        self._inputs: dict[str, tuple[ClockConfig, BaseModel | None]] = {}

    def judge(self) -> ChatProvider | None:
        if not self._judge_built:
            self._judge_built = True
            if self.exp.judge.provider is not ProviderKind.stub:
                self._judge = self.provider_factory(self.exp.judge, self._judge_dir)
        return self._judge

    def validate(self) -> None:
        """Checks that need the worlds, made before run.json is written (a dry run makes them
        too). Every experiment switch an environment turns on has what it needs on the world
        sheet, and under a config clock that asserts no date neither the world nor a premise
        sheet states one (``_check_switches`` and ``strategy_inputs``; the world is loaded only
        for these, and ``check_worlds`` covers a sheet's own clock). A scheduled environment
        names one exchange for every rung of its ladder (scheduled gating ignores ``requires``,
        so every rung is reachable) and nothing else, and no exchange is after the last bully
        turn of the shortest condition that uses the environment (the k-th bully turn is
        exchange k; seeding and reveal turns are bully turns too, so a condition has
        ``seeding_turns`` plus its reveal slot plus ``turn_budget`` of them, counted as the
        runner's turn plan counts them). A rung scheduled later could never open for that
        condition."""
        keys = [cond.environment for cond in self.exp.conditions if cond.environment is not None]
        for key in dict.fromkeys(keys):
            config = self.exp.environments.get(key)
            if config is None:
                continue
            if _needs_its_world(config):
                self._check_switches(key, config)
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
            bully_turns = self._bully_turns(shortest)
            late = [
                f"{name!r} at exchange {exchange}"
                for name, exchange in config.schedule.items()
                if exchange > bully_turns
            ]
            if late:
                raise ValueError(
                    f"environment {key!r} (world {config.world!r}, ladder {config.ladder!r}): "
                    "scheduled gating names exchanges after the last bully turn of the shortest "
                    f"condition using it, {shortest.condition.name!r}, which has "
                    f"{bully_turns} bully turns "
                    f"(seeding_turns {shortest.condition.seeding_turns}, "
                    f"reveal slot {'yes' if shortest.reveal_slot else 'no'}, "
                    f"turn_budget {self.exp.turn_budget}); that conversation never reaches: "
                    f"{', '.join(late)}"
                )
        self._premise_checks()

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

    def _bully_turns(self, cell: CellSpec) -> int:
        """How many bully turns the cell has: the runner's own turn plan, counted."""
        plan = build_turn_plan(
            turn_budget=self.exp.turn_budget,
            seeding_turns=cell.condition.seeding_turns,
            reveal_slot=cell.reveal_slot,
            task_every=self.exp.task_every,
        )
        return len(plan.bully_slots())

    def _shortest_condition(self, key: str) -> CellSpec:
        """The cell with the fewest bully turns among those running in environment ``key`` (the
        first of equals, so a condition is named before its control)."""
        cells = [cell for cell in expand_cells(self.exp) if cell.condition.environment == key]
        return min(cells, key=self._bully_turns)

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
        runtime = EnvironmentRuntime(
            world,
            config,
            clock,
            self.exp.seed + rep,
            state_dir / "environment",
            worlds_dir=self.catalog.worlds_dir,
            mcp_dir=mcp_dir,
            llm_fallback=trigger_fallback(judge, f"{conversation_id}/trigger") if judge else None,
            trigger_cache=self.trigger_cache,
            responder=responder,
            responder_role=role,
            conversation_id=conversation_id,
            display_name=cell.target.display_name,
        )
        session = EnvironmentSession(
            runtime,
            store,
            cell.cell_id,
            rep,
            strategy,
            environment_name=key,
            world_hash=self.catalog.hash(config.world),
        )
        session.prime()
        # the clock the rep opened with: kept at its first open (or its first since the ref
        # existed), so a resume with another clock is refused (check_world)
        record = store.read_cell(cell.cell_id)
        if clock_ref(rep) not in record.session_refs:
            record.session_refs[clock_ref(rep)] = clock.model_dump_json()
            store.write_cell(record)
        return session, target

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
