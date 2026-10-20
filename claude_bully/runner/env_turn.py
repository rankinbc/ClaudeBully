"""Environment cells in the runner: the tool loop, a turn's records, and the unlock lines.

``RunEnvironments.open`` sets one environment cell repetition up: the target provider (for
``claude -p``, with its working directory and MCP files under a neutral sandbox directory outside
the repo), the ``EnvironmentRuntime``, and the ``EnvironmentSession`` the runner talks to.

Per target turn the session:

1. calls the target with the tool specs, and for every call the provider returns unexecuted runs
   it through the runtime (at most ``MAX_TOOL_CALLS_PER_TURN``; later ones are answered "Tool call
   limit reached for this turn."), records it, answers EVERY call of the assistant message with a
   tool result, and calls again until the target replies without asking for tools;
2. for a ``claude -p`` target, whose calls the MCP server already ran, writes the state before
   each call and afterwards adopts the server's state and records the server's log, including the
   calls of a call that failed (those are recorded but belong to no turn);
3. after the reply is written, records the turn's discoveries, triggers and rung unlocks, and
   hands each unlock line to the strategy.

The target's view of earlier turns is rebuilt from the records: a turn that used tools appears as
one assistant message with its calls, one user message with their results, then the reply.
"""

import hashlib
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NamedTuple

from claude_bully.config import Experiment
from claude_bully.enums import ProviderKind, Speaker
from claude_bully.environments.runtime import (
    EnvironmentRuntime,
    TurnOutcome,
    effective_clock,
    tools_section,
    trigger_fallback,
)
from claude_bully.environments.tools import TOOL_SPECS
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
from claude_bully.records_env import RungUnlock, ToolCall, TriggerStreamRecord
from claude_bully.runner.cells import CellSpec
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import Strategy
from claude_bully.strategies.composed import Composed
from claude_bully.strategies.factory import environment_config

MAX_TOOL_CALLS_PER_TURN: Final = 8
# After the cap, the target is asked for its reply at most this many more times.
MAX_LIMIT_ROUNDS: Final = 2
SANDBOX_ROOT: Final = "workspace"
TRIGGER_CACHE_DIR: Final = Path("_cache") / "triggers"


def sandbox_dir(run_id: str, cell_id: str, rep: int) -> Path:
    """Where a ``claude -p`` environment target works: neutral, outside the repo, stable per rep."""
    key = f"{run_id}/{cell_id}/{rep}".encode()
    digest = hashlib.sha1(key, usedforsecurity=False).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / SANDBOX_ROOT / digest


class TargetTurn(NamedTuple):
    completion: Completion
    calls: list[ToolCall]
    usage: Usage
    cost_usd: float | None


def _plus(a: int | None, b: int | None) -> int | None:
    return None if a is None and b is None else (a or 0) + (b or 0)


def _cost(a: float | None, b: float | None) -> float | None:
    return None if a is None and b is None else (a or 0.0) + (b or 0.0)


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
        self._recorded_lines: dict[int, list[str]] = {}

    def prime(self) -> None:
        """Load what a resumed rep already recorded, so nothing is counted or recorded twice."""
        calls = self.store.read_tool_calls(self.cell_id, self.rep)
        records = self.store.read_trigger_records(self.cell_id, self.rep)
        self.runtime.prime(calls, records)
        for record in records:
            if isinstance(record, RungUnlock) and record.bully_line_used is not None:
                self._recorded_lines.setdefault(record.turn, []).append(record.bully_line_used)

    # ----------------------------------------------------------- the target's view

    def target_view(self, turns: Sequence[Turn]) -> list[Message]:
        out: list[Message] = []
        for t in turns:
            if t.bully_meta.get("rate_limit_pause"):
                continue
            if t.speaker is not Speaker.target:
                out.append(Message(role="user", content=t.text))
                continue
            # a claude -p session keeps its own tool history; an API target needs it replayed
            calls = [] if self.runtime.uses_mcp else self._calls_of(t)
            if calls:
                out.append(
                    Message(
                        role="assistant",
                        content="",
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
        specs = self.runtime.tool_specs()
        attached: list[ToolCall] = []
        executed = 0
        refusal_rounds = 0
        usage = Usage()
        cost: float | None = None
        while True:
            completion = self._complete(
                provider, conversation_id, system, messages, specs, turn_index, attached
            )
            # summed over the rounds; a turn without tools keeps its one completion's figures
            usage = Usage(
                input_tokens=_plus(usage.input_tokens, completion.usage.input_tokens),
                output_tokens=_plus(usage.output_tokens, completion.usage.output_tokens),
            )
            cost = _cost(cost, completion.cost_usd)
            pending = [c for c in completion.tool_calls if not c.executed]
            if not pending or refusal_rounds >= MAX_LIMIT_ROUNDS:
                return TargetTurn(completion, attached, usage, cost)
            results: list[ToolResult] = []
            refused = False
            for call in completion.tool_calls:
                if call.executed:
                    results.append(ToolResult(id=call.id, text=call.result_text or ""))
                    continue
                if executed < MAX_TOOL_CALLS_PER_TURN:
                    record = self.runtime.execute(call, turn_index)
                    executed += 1
                else:
                    record = self.runtime.refuse(call, turn_index)
                    refused = True
                self._record_call(record)
                attached.append(record)
                results.append(ToolResult(id=call.id, text=record.result_text))
            self.runtime.save()
            refusal_rounds += int(refused)
            messages += [
                Message(
                    role="assistant",
                    content=completion.text,
                    tool_calls=list(completion.tool_calls),
                ),
                Message(role="user", content="", tool_results=results),
            ]

    def _complete(
        self,
        provider: ChatProvider,
        conversation_id: str,
        system: str,
        messages: list[Message],
        specs: list[ToolSpec],
        turn_index: int,
        attached: list[ToolCall],
    ) -> Completion:
        self.runtime.before_target_call(turn_index)
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
        self.runtime.save()
        return fresh

    def _record_call(self, call: ToolCall) -> None:
        self.store.append_tool_call(self.cell_id, self.rep, call)

    # ----------------------------------------------------------- after the reply

    def after_target_turn(self, reply: Turn, turns: Sequence[Turn]) -> TurnOutcome:
        """Record the turn's discoveries, triggers and unlocks; hand the unlock lines over.

        An unlock whose line the strategy does not take (a control) is recorded without one.
        """
        outcome = self.runtime.after_target_turn(reply, turns)
        for discovery in outcome.discoveries:
            self._record(discovery)
        for trigger in outcome.triggers:
            self._record(trigger)
        unlocks: list[RungUnlock] = []
        for unlock in outcome.unlocks:
            line = unlock.bully_line_used
            if line is not None and not self._hand_over(line):
                unlock = unlock.model_copy(update={"bully_line_used": None})
            self._record(unlock)
            unlocks.append(unlock)
        return TurnOutcome(outcome.triggers, unlocks, outcome.discoveries)

    def replay_target_turn(self, reply: Turn) -> None:
        """Resume: hand over again the lines this recorded turn handed the strategy."""
        for line in self._recorded_lines.get(reply.index, []):
            self._hand_over(line)

    def _hand_over(self, line: str) -> bool:
        return isinstance(self.strategy, Composed) and self.strategy.inject_unlock_line(line)

    def _record(self, record: TriggerStreamRecord) -> None:
        self.store.append_trigger_record(self.cell_id, self.rep, record)

    def finish(self) -> None:
        self.runtime.save()
        self.store.write_world_snapshot(
            self.cell_id, self.rep, self.world_hash, self.runtime.corpus_snapshot()
        )


# ------------------------------------------------------------------ run-level setup


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
    ) -> None:
        self.exp = exp
        self.catalog = WorldCatalog(worlds_dir)
        self.trigger_cache = JudgeCache(runs_root / TRIGGER_CACHE_DIR)
        self.provider_factory = provider_factory
        self._judge_dir = state_dir / "trigger_judge"
        self._judge: ChatProvider | None = None
        self._judge_built = False

    def judge(self) -> ChatProvider | None:
        if not self._judge_built:
            self._judge_built = True
            if self.exp.judge.provider is not ProviderKind.stub:
                self._judge = self.provider_factory(self.exp.judge, self._judge_dir)
        return self._judge

    def target_system_prompt(self, base: str) -> str:
        """``RunRecord.target_system_prompt``: the base prompt, plus the tool section of the first
        environment a condition names (each environment cell's own prompt is the base plus its
        environment's section; with every environment on the same tools they are the same)."""
        for cond in self.exp.conditions:
            if cond.environment is not None:
                config = environment_config(cond, self.exp.environments)
                specs = [spec for name, spec in TOOL_SPECS.items() if name in config.tools]
                clock = effective_clock(self.catalog.world(config.world), config)
                return target_system(base, tools_section(specs, clock))
        return base

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
        """The session and the target provider for one environment cell repetition."""
        key = cell.condition.environment
        assert key is not None, "only environment cells open an environment"
        config = environment_config(cell.condition, self.exp.environments)
        world = self.catalog.world(config.world)
        if cell.target.provider is ProviderKind.claude_code:
            target = self._sandboxed_target(cell, rep, store)
        else:
            target = self.provider_factory(cell.target, state_dir / "target")
        mcp_dir = getattr(target, "mcp_state_dir", None)
        judge = self.judge()
        conversation_id = f"{store.run_id}/{cell.cell_id}/rep{rep}"
        runtime = EnvironmentRuntime(
            world,
            config,
            effective_clock(world, config),
            self.exp.seed + rep,
            state_dir / "environment",
            worlds_dir=self.catalog.worlds_dir,
            mcp_dir=mcp_dir if isinstance(mcp_dir, Path) else None,
            llm_fallback=trigger_fallback(judge, f"{conversation_id}/trigger") if judge else None,
            trigger_cache=self.trigger_cache,
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
        return session, target

    def _sandboxed_target(self, cell: CellSpec, rep: int, store: RunStore) -> ChatProvider:
        """A ``claude -p`` target whose cwd and MCP files live in the neutral sandbox directory.

        The path goes on the cell record as ``session_refs["sandbox_dir"]`` (the latest rep) and
        ``session_refs["sandbox_dir.rep<k>"]`` (every rep).
        """
        sandbox = sandbox_dir(store.run_id, cell.cell_id, rep)
        if not store.read_turns(cell.cell_id, rep) and not store.read_tool_calls(cell.cell_id, rep):
            # a fresh rep never inherits a stale session or tool log from an earlier run
            shutil.rmtree(sandbox, ignore_errors=True)
        target = self.provider_factory(cell.target, sandbox, with_mcp=True)
        record = store.read_cell(cell.cell_id)
        record.session_refs["sandbox_dir"] = str(sandbox)
        record.session_refs[f"sandbox_dir.rep{rep}"] = str(sandbox)
        store.write_cell(record)
        return target
