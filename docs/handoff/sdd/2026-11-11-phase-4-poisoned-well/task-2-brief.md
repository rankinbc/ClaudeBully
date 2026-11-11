### Task 2: Strategy plumbing and the toolless environment cell

`Strategy.params_model`, `condition_problems`, `takes_target_model`, `note_record`; the factory's one validation path; the session's record hand-over, live and on replay; the toolless cell.

**Files:**
- Modify: `claude_bully/strategies/base.py` (`Strategy` 66)
- Modify: `claude_bully/strategies/composed.py` (`_SLOT_KEYS` 58 becomes public `SLOT_KEYS`; `Composed.__init__` 75; delegation 229)
- Modify: `claude_bully/strategies/factory.py` (`build_strategy` 155; new `routed_params`, `check_condition`)
- Modify: `claude_bully/runner/runner.py` (`run_experiment` 785-788 and 828)
- Modify: `claude_bully/analysis/load.py` (`load_run` 123)
- Modify: `claude_bully/runner/env_turn.py` (`EnvironmentSession.__init__`, `prime`, `after_target_turn`, `_hand_over_recorded`, `_record`; `target_system` 964)
- Modify: `claude_bully/environments/runtime.py` (`tools_section` 391, `system_prompt_section` 874)
- Test: `tests/test_strategy_plumbing.py`

**Interfaces:**
- Consumes: Task 1's records.
- Produces: `Strategy.params_model: ClassVar[type[BaseModel] | None]`, `Strategy.takes_target_model: ClassVar[bool]`, `Strategy.note_record(record: TriggerStreamRecord) -> None`, `Strategy.condition_problems(cond: ConditionConfig) -> list[str]` (classmethod); `composed.SLOT_KEYS`; `factory.routed_params(cond, environments) -> list[tuple[type[Strategy], dict[str, Any]]]`; `factory.check_condition(cond, environments) -> None` (raises `ValueError` naming the condition); `build_strategy(..., target_model: str | None = None)`; `env_turn._record_key(record) -> tuple[str, ...]`; `EnvironmentSession._hand_over_records(turn_index: int) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_strategy_plumbing.py
"""Phase 4 Task 2: one validation path for params, the record hand-over, the toolless cell."""

import json
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from claude_bully.config import ConditionConfig
from claude_bully.enums import Axis, CellStatus, IntentMode, Phase, Speaker
from claude_bully.records_env import QuirkAttempt, RungUnlock, TriggerStreamRecord
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import (
    BullyIntent,
    ConversationState,
    End,
    Strategy,
    register,
)
from claude_bully.strategies.composed import SLOT_KEYS, Composed
from claude_bully.strategies.factory import build_strategy, check_condition, routed_params
from claude_bully.runner.prompts import load_target_system
from tests.helpers import WORLDS_DIR, env_experiment

FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
CELL = "env_grader__t0"


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    depth: int = 1


# every note_record call of every instance, by conversation seed, for the m6 check
NOTED: list[tuple[int, str, int]] = []


@register
class _Recorder(Strategy):
    """A premise-slot test strategy: it validates ``depth`` and logs every record it is handed."""

    name: ClassVar[str] = "_recorder"
    axis: ClassVar[Axis] = Axis.premise
    has_reveal: ClassVar[bool] = False
    win_condition: ClassVar[str] = "w"
    resilient_behavior: ClassVar[str] = "r"
    params_model: ClassVar[type[BaseModel] | None] = _Params
    takes_target_model: ClassVar[bool] = True

    def __init__(self, *, target_model: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.target_model = target_model

    @property
    def phase(self) -> Phase:
        return Phase.pressure

    def next_turn(self, state: ConversationState) -> BullyIntent | End:
        if state.bully_turn_index >= state.turn_budget:
            return End(reason="done")
        return BullyIntent(mode=IntentMode.llm, phase=Phase.pressure, instruction="go")

    def note_record(self, record: TriggerStreamRecord) -> None:
        NOTED.append((self.seed, record.type, record.turn))  # type: ignore[union-attr]

    @classmethod
    def condition_problems(cls, cond: ConditionConfig) -> list[str]:
        return ["takes no pressure"] if cond.pressure is not None else []


def _cond(**kwargs: Any) -> ConditionConfig:
    return ConditionConfig(name="c", **kwargs)


def test_the_slot_keys_are_public() -> None:
    assert SLOT_KEYS == frozenset({"environment", "premise", "pressure"})


def test_routed_params_mirror_the_composition() -> None:
    exp = env_experiment()
    lone = _cond(environment="mini", strategy="_recorder", params={"depth": 2, "pressure": "x"})
    [(cls, params)] = routed_params(lone, exp.environments)
    assert cls.name == "_recorder" and params == {"depth": 2}  # a slot key never arrives
    split = _cond(
        environment="mini",
        premise="_recorder",
        pressure="grader",
        params={"premise": {"depth": 3}, "pressure": {}},
    )
    assert [(c.name, p) for c, p in routed_params(split, exp.environments)] == [
        ("_recorder", {"depth": 3}),
        ("grader", {}),
    ]


def test_check_condition_validates_through_the_params_model() -> None:
    exp = env_experiment()
    check_condition(_cond(environment="mini", strategy="_recorder"), exp.environments)
    with pytest.raises(ValueError, match="condition 'c'.*deep"):
        check_condition(
            _cond(environment="mini", strategy="_recorder", params={"deep": 1}), exp.environments
        )


def test_check_condition_runs_the_strategy_rules() -> None:
    exp = env_experiment()
    with pytest.raises(ValueError, match="condition 'c'.*takes no pressure"):
        check_condition(
            _cond(environment="mini", premise="_recorder", pressure="grader"), exp.environments
        )


def test_a_dry_run_refuses_a_bad_param_before_anything_is_written(tmp_path: Path) -> None:
    exp = env_experiment(
        conditions=[
            {"name": "bad", "environment": "mini", "strategy": "_recorder", "params": {"deep": 1}}
        ]
    )
    with pytest.raises(ValueError, match="deep"):
        run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, dry_run=True)
    assert not (tmp_path / exp.name).exists()


def test_the_target_model_reaches_a_part_that_declares_it() -> None:
    exp = env_experiment()
    built = build_strategy(
        _cond(environment="mini", strategy="_recorder"),
        seed=0,
        turn_budget=2,
        environments=exp.environments,
        target_model="stub-target",
    )
    assert isinstance(built, Composed)
    assert isinstance(built.premise, _Recorder) and built.premise.target_model == "stub-target"


def _recorder_exp(name: str) -> Any:
    return env_experiment(
        name,
        conditions=[{"name": "env_grader", "environment": "mini", "strategy": "_recorder"}],
        turn_budget=4,
    )


def test_the_strategy_is_handed_the_same_records_live_and_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Review Focus 2 (m6)
    """Every ladder unlock and Poisoned Well record of a turn reaches ``note_record`` once, live;
    a rep killed after its second target turn and resumed hands the rebuilt strategy the same
    records in the same order."""
    NOTED.clear()
    run_experiment(_recorder_exp("live"), runs_root=tmp_path / "live", worlds_dir=WORLDS_DIR)
    live = list(NOTED)
    store = RunStore(tmp_path / "live", "live")
    expected = [
        (r.type, r.turn)
        for r in store.read_trigger_records(CELL, 0)
        if isinstance(r, RungUnlock) and r.rung not in ("generator", "sanctuary")
    ]
    assert [(t, n) for _, t, n in live] == expected and expected  # mini opens a rung

    NOTED.clear()
    recorded = RunStore.append_turn
    writes = {"n": 0}

    class _Killed(BaseException):
        pass

    def dying(self: RunStore, cell_id: str, rep: int, turn: Any) -> None:
        recorded(self, cell_id, rep, turn)
        if turn.speaker is Speaker.target:
            writes["n"] += 1
            if writes["n"] == 2:
                monkeypatch.setattr(RunStore, "append_turn", recorded)
                raise _Killed

    monkeypatch.setattr(RunStore, "append_turn", dying)
    with pytest.raises(_Killed):
        run_experiment(_recorder_exp("again"), runs_root=tmp_path / "again", worlds_dir=WORLDS_DIR)
    NOTED.clear()
    run_experiment(_recorder_exp("again"), runs_root=tmp_path / "again", worlds_dir=WORLDS_DIR)
    assert [(t, n) for _, t, n in NOTED] == expected


def test_a_toolless_environment_cell_runs_on_the_stub(tmp_path: Path) -> None:
    exp = env_experiment(environment={"tools": [], "gating": "none"}, turn_budget=2)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    store = RunStore(tmp_path, exp.name)
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    assert store.read_tool_calls(CELL, 0) == []
    # no tool section: the target's system prompt is the base prompt alone
    assert store.read_cell(CELL).target_system_prompt == load_target_system("Claude", False)


def test_a_toolless_environment_cell_takes_the_json_path_on_claude_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "fake.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    target = {"provider": "claude_code", "model": "m", "command": [sys.executable, str(FAKE_CLAUDE)]}
    exp = env_experiment(target=target, environment={"tools": [], "gating": "none"}, turn_budget=2)
    base = tmp_path / "tmp"
    base.mkdir()
    run_experiment(exp, runs_root=tmp_path / "runs", worlds_dir=WORLDS_DIR, sandbox_base=base)
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert entries
    for entry in entries:
        argv = entry["argv"]
        assert argv[argv.index("--output-format") + 1] == "json"
        assert "--mcp-config" not in argv and "--allowedTools" not in argv
```

(`RunStore.append_turn` is the store's turn writer; if its name differs at HEAD, use the method `_CellRun._write` calls, by reading `runner.py:318`. The fake-claude test runs under the child root that 7b's Task 12 fix round 2 locks (`tests/conftest.py`); it passes `sandbox_base` as `tests/test_providers_claude_code.py` does at that HEAD, and follows that file if fix round 2 changed the call.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_strategy_plumbing.py -q`
Expected: FAIL at import (`SLOT_KEYS`, `check_condition`, `routed_params`).

- [ ] **Step 3: Implement**

`strategies/base.py`, in `Strategy` after `world_sheet`:

```python
    # One validation path for a condition's params (reconciliation C5): the model the params this
    # part receives validate through (``factory.check_condition``), or None for none
    params_model: ClassVar[type[BaseModel] | None] = None
    # The part takes ``target_model=`` (the cell target's ``RoleConfig.model``) in its
    # constructor; the Poisoned Well matches its quirk bank's family on it (Phase 4)
    takes_target_model: ClassVar[bool] = False

    def note_record(self, record: TriggerStreamRecord) -> None:  # noqa: B027 - optional hook
        """Hook: an environment cell's session hands the strategy each ladder unlock and each
        Poisoned Well record it records, live and on replay, once per process (Phase 4)."""
        return None

    @classmethod
    def condition_problems(cls, cond: "ConditionConfig") -> list[str]:
        """What keeps ``cond`` from running this strategy, before any world is read; empty when
        nothing does (``factory.check_condition``)."""
        return []
```

(`TriggerStreamRecord` from `claude_bully.records_env`; `ConditionConfig` under `TYPE_CHECKING` from `claude_bully.config`, since `config.py` must not import strategies.)

`strategies/composed.py`: `SLOT_KEYS: Final = frozenset({"environment", "premise", "pressure"})` replaces `_SLOT_KEYS` (every use renamed). `Composed.__init__` takes `target_model: str | None = None` and builds each part with `target_model=target_model` when `part_cls.takes_target_model` (the premise and the pressure; not the environment); and:

```python
    def note_record(self, record: TriggerStreamRecord) -> None:
        for part in (self.environment, self.premise, self.pressure):
            if part is not None:
                part.note_record(record)
```

`strategies/factory.py`:

```python
def routed_params(
    cond: ConditionConfig, environments: Environments | None = None
) -> list[tuple[type[Strategy], dict[str, Any]]]:
    """Each part of the condition's class with the params it receives, as ``build_strategy``
    hands them: a plain class (no environment, a class that is not ``Composed``) gets the whole
    params, slot keys included; a ``Composed`` class routes them as ``Composed._params_for``
    does, a lone part getting the params less the slot keys (or its own slot, when the params
    name it) and, with both a premise and a pressure, each part its slot. The environment part
    is left out (it takes no params a model validates)."""
```

Its body follows `resolve_class`'s branches: an environment condition through `_bully_slots`; `strategy` alone; `premise` with or without `pressure`; `pressure` alone; a resolved class that is not a `Composed` subclass gets `dict(cond.params)` unchanged (review M11). Then:

```python
def check_condition(cond: ConditionConfig, environments: Environments | None = None) -> None:
    """Refuse a condition before anything runs (a dry run included): each part's
    ``condition_problems``, then the params each part receives, through its ``params_model``.
    The ``ValueError`` names the condition and the part."""
    ensure_registered()
    for cls, params in routed_params(cond, environments):
        problems = cls.condition_problems(cond)
        if problems:
            raise ValueError(f"condition {cond.name!r} ({cls.name}): {'; '.join(problems)}")
        if cls.params_model is not None:
            try:
                cls.params_model.model_validate(params)
            except ValidationError as exc:
                raise ValueError(f"condition {cond.name!r} ({cls.name}) params: {exc}") from exc
```

`build_strategy` gains `target_model: str | None = None`, passed as `target_model=` to the `Composed` branch and, in the plain branch, to a class that declares `takes_target_model`. In `runner.run_experiment` a loop over the selected cells calls `check_condition(cell.condition, exp.environments)` before `environments.validate()` (P53), and the cell loop's `build_strategy(...)` passes `target_model=cell.target.model`; `analysis/load.load_run` passes `target_model=spec.target.model`.

`runner/env_turn.py`:

```python
# the records a session hands the strategy (Phase 4): the ladder's unlocks and the Poisoned Well
# watch's records; never a pseudo-rung's unlock
_HANDED: Final = (QuirkAttempt, ChainLink, ContradictionPair, RungUnlock)


def _record_key(record: TriggerStreamRecord) -> tuple[str, ...]:
    """What makes a handed record itself: a turn's quirk attempt, a turn's verdict on a link, a
    pair by id, a rung by name."""
    if isinstance(record, QuirkAttempt):
        return ("quirk", str(record.turn))
    if isinstance(record, ChainLink):
        return ("chain", str(record.turn), str(record.link_index))
    if isinstance(record, ContradictionPair):
        return ("contradiction", record.id)
    if isinstance(record, RungUnlock):
        return ("unlock", record.rung)
    return (record.type, str(getattr(record, "turn", "")))
```

`EnvironmentSession.__init__` gains `self._records_at: dict[int, list[TriggerStreamRecord]] = {}` and `self._handed_records: set[tuple[str, ...]] = set()`. `prime` files each `_HANDED` record of `records` under its turn (a `RungUnlock` only when `record.rung not in PSEUDO_RUNGS`). `_record` does the same for a record it writes. Then:

```python
    def _hand_over_records(self, turn_index: int) -> None:
        """The turn's ladder unlocks and Poisoned Well records, to ``Strategy.note_record``, each
        once per process (by ``_record_key``), live and on replay."""
        for record in self._records_at.get(turn_index, []):
            key = _record_key(record)
            if key not in self._handed_records:
                self._handed_records.add(key)
                self.strategy.note_record(record)
```

`_hand_over_recorded(turn_index)` calls `self._hand_over_records(turn_index)` after its line loop and before its `_handed` early return can skip it (move the early return so the records are handed even when the lines were); `after_target_turn` calls `self._hand_over_records(reply.index)` after the unlocks loop.

`target_system(base, section)` returns `base` when `section` is empty. `runtime.tools_section` returns only the date block when `specs` is empty (`""` when the clock states no date); `system_prompt_section` joins its blocks with `"\n\n".join(part for part in [...] if part)`.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_strategy_plumbing.py -q`, then the gate.
Expected: PASS. Existing tests that pin the system prompt of a cell with tools are unchanged (a non-empty section joins as before).

- [ ] **Step 5: Docs-sync and commit**

docs/00 section A `ConditionConfig` row: "a strategy's params validate through its `params_model` (Phase 4; `factory.check_condition`, dry runs included)"; G3 gains the toolless cell (`tools: []`: no tool section, `--output-format json` on `claude_code`). Spec "As planned": Task 2 (V17, V22, V27, the hand-over order).

```bash
git add claude_bully/strategies/base.py claude_bully/strategies/composed.py claude_bully/strategies/factory.py \
  claude_bully/runner/runner.py claude_bully/analysis/load.py claude_bully/runner/env_turn.py \
  claude_bully/environments/runtime.py tests/test_strategy_plumbing.py docs/00-RECONCILED.md \
  docs/superpowers/specs/2026-11-11-phase-4-poisoned-well-design.md HANDOFF.md
git commit -m "feat: Phase 4 Task 2, params_model and check_condition, the record hand-over, the toolless environment cell

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
