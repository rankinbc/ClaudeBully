"""Phase 4 Task 2: one validation path for params, the record hand-over, the toolless cell."""

import json
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from claude_bully.analysis.load import load_run
from claude_bully.config import ConditionConfig
from claude_bully.enums import Axis, CellStatus, IntentMode, Phase, Speaker
from claude_bully.environments.config import PSEUDO_RUNGS, EnvironmentConfig
from claude_bully.environments.runtime import EnvironmentRuntime
from claude_bully.environments.world import load_world
from claude_bully.records_env import RungUnlock, TriggerStreamRecord
from claude_bully.runner.env_turn import EnvironmentSession
from claude_bully.runner.prompts import load_target_system
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
from tests.helpers import WORLDS_DIR, env_experiment

FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
CELL = "env_grader__t0"


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    depth: int = 1


# every note_record call of every instance, by conversation seed, for the m6 check
NOTED: list[tuple[int, str, int]] = []
# the target_model every instance was built with (Phase 4 Task 14, the Task 2 review's M3)
BUILT: list[str | None] = []


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
        BUILT.append(target_model)

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
    target = {
        "provider": "claude_code",
        "model": "m",
        "command": [sys.executable, str(FAKE_CLAUDE)],
    }
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


# ------------------------------------------------- Phase 4 Task 14: the Task 2 review's minors


def test_a_kill_inside_mark_watched_hands_each_record_once_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # M2: the once-per-process record key
    """A rep killed inside ``mark_watched`` (its records written, the state not yet saved)
    replays the turn's records and then watches the turn again; ``records_env.record_key`` keeps
    the rebuilt strategy from being handed a record twice."""
    NOTED.clear()
    run_experiment(_recorder_exp("live"), runs_root=tmp_path / "live", worlds_dir=WORLDS_DIR)
    live = [(t, n) for _, t, n in NOTED]
    assert live
    real = EnvironmentRuntime.mark_watched

    class _Killed(BaseException):
        pass

    def dying(self: EnvironmentRuntime, turn_index: int) -> None:
        monkeypatch.setattr(EnvironmentRuntime, "mark_watched", real)
        raise _Killed

    monkeypatch.setattr(EnvironmentRuntime, "mark_watched", dying)
    with pytest.raises(_Killed):
        run_experiment(_recorder_exp("again"), runs_root=tmp_path / "again", worlds_dir=WORLDS_DIR)
    NOTED.clear()
    run_experiment(_recorder_exp("again"), runs_root=tmp_path / "again", worlds_dir=WORLDS_DIR)
    assert [(t, n) for _, t, n in NOTED] == live


def test_the_strategy_is_built_with_the_roles_model_in_a_run_and_in_load_run(
    tmp_path: Path,
) -> None:  # M3: ``target_model=`` in ``run_experiment`` and in ``load_run``
    BUILT.clear()
    exp = _recorder_exp("model")
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    assert BUILT and set(BUILT) == {"stub-target"}
    BUILT.clear()
    load_run(tmp_path / exp.name)
    assert BUILT and set(BUILT) == {"stub-target"}


def test_a_bad_param_is_named_before_validate_reads_the_environment(tmp_path: Path) -> None:
    """M4 (P53): ``check_condition`` runs before ``RunEnvironments.validate()``. Here both would
    refuse (a misspelt param, and a schedule naming no rung of the ladder); the param is named."""
    exp = env_experiment(
        environment={"gating": "scheduled", "schedule": {"no_such_rung": 1}},
        conditions=[
            {"name": "bad", "environment": "mini", "strategy": "_recorder", "params": {"deep": 1}}
        ],
    )
    with pytest.raises(ValueError, match=r"condition 'bad' \(_recorder\) params: deep"):
        run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, dry_run=True)


def test_a_pseudo_rung_unlock_is_never_handed_to_the_strategy() -> None:  # M5 (a)
    session = object.__new__(EnvironmentSession)
    session._records_at = {}

    def unlock(rung: str) -> RungUnlock:
        return RungUnlock(
            turn=3,
            rung=rung,
            triggered_by="t",
            docs_unlocked=[],
            bully_line_used=None,
            role_shift=None,
        )

    for rung in sorted(PSEUDO_RUNGS):
        session._file(unlock(rung))
    assert session._records_at == {}
    ladder = unlock("the_log")
    session._file(ladder)
    assert session._records_at == {3: [ladder]}


def test_a_toolless_cell_with_idle_lines_starts_with_its_first_line(tmp_path: Path) -> None:
    """M5 (b): with no tools and no date line, the tools block is empty and is left out, so the
    section is the idle lines alone, with no leading blank block."""
    mini = load_world("mini", WORLDS_DIR)
    config = EnvironmentConfig(
        world="mini", tools=[], gating="none", idle={"permission_line": "You may rest now."}
    )
    runtime = EnvironmentRuntime(
        mini, config, mini.sheet.clock, 0, tmp_path / "env", worlds_dir=WORLDS_DIR
    )
    assert runtime.system_prompt_section() == "You may rest now."


@pytest.mark.parametrize(
    "fields",
    [
        {"strategy": "_recorder", "params": {"premise": "x"}},
        {"premise": "_recorder", "pressure": "grader", "params": {"premise": 3}},
    ],
)
def test_a_slot_value_that_is_not_a_mapping_is_named(fields: dict[str, Any]) -> None:  # M7
    exp = env_experiment()
    with pytest.raises(ValueError, match=r"condition 'c': params\['premise'\] must be a mapping"):
        check_condition(_cond(environment="mini", **fields), exp.environments)
