"""The attempt marker (Phase 2 final review I4, Phase 3 Task 1).

Before every provider call the runtime names it in ``<state_dir>/attempt.json``. A resumed rep
whose newest marker names a turn that was never written writes a ``resume`` record with no drop
counts, so a dead attempt that left no per-call line (no tool call, a rate-limit pause on such a
turn, the bully's dead prompt alone) is flagged like one that did. Its records still equal an
unbroken run's."""

import json
from pathlib import Path
from typing import Any

import pytest

from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import CellStatus, Speaker
from claude_bully.environments.runtime import ATTEMPT_FILE, AttemptMarker
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    RateLimitError,
    build_provider,
)
from claude_bully.records_env import ResumeRecord
from claude_bully.runner.bully_engine import BullyEngine
from claude_bully.runner.env_turn import EnvironmentSession
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from tests.helpers import PAUSE_MARKER_META, WORLDS_DIR, env_experiment, turn

CELL = "env_grader__t0"
RUN = "env_run"


class _CrashError(Exception):
    pass


def _run(exp: Experiment, root: Path, **kwargs: Any) -> RunStore:
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR, only="env_grader*", **kwargs)
    return RunStore(root, exp.name)


def _resumes(store: RunStore) -> list[ResumeRecord]:
    return [r for r in store.read_trigger_records(CELL, 0) if isinstance(r, ResumeRecord)]


def _view(store: RunStore) -> tuple[list[tuple[Any, ...]], list[str]]:
    """The trigger stream without its resume records, then the turn texts."""
    records = [
        (
            r.type,
            getattr(r, "id", None) or getattr(r, "rung", None) or getattr(r, "doc_id", None),
            getattr(r, "turn", None),
        )
        for r in store.read_trigger_records(CELL, 0)
        if not isinstance(r, ResumeRecord)
    ]
    return records, [t.text for t in store.read_turns(CELL, 0)]


def _marker(store: RunStore) -> dict[str, Any]:
    path = store.state_dir / CELL / "rep0" / "environment" / ATTEMPT_FILE
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _bully_dies_at(monkeypatch: pytest.MonkeyPatch, index: int, times: int = 1) -> None:
    """The bully's provider call for bully turn ``index`` raises ``times`` times."""
    real = BullyEngine.realize
    left = [times]

    def dying(self: BullyEngine, conversation_id: str, intent: Any, turns: list[Any]) -> Any:
        if len(turns) == index and left[0]:
            left[0] -= 1
            raise _CrashError(f"killed during the bully call for turn {index}")
        return real(self, conversation_id, intent, turns)

    monkeypatch.setattr(BullyEngine, "realize", dying)


class _TargetDies:
    """A provider factory whose stub target raises ``error`` at its ``at``-th completion. The
    mini stub target (``env_target_rules.yaml``) makes completions 1-2 on turn 1 (a search, then
    the reply), 3-4 on turn 3 (a fetch, then the reply), 5 on turn 5 and 6 on turn 7, so ``at=5``
    is a turn with no tool call."""

    def __init__(self, at: int, error: BaseException) -> None:
        self.at = at
        self.error = error
        self.calls = 0

    def __call__(
        self, role: RoleConfig, state_dir: Path, *, with_mcp: bool = False
    ) -> ChatProvider:
        inner = build_provider(role, state_dir, with_mcp=with_mcp)
        if role.model != "stub-target":
            return inner
        outer = self

        class Dying:
            name = inner.name

            def complete(
                self, cid: str, system: str, messages: list[Message], **kw: Any
            ) -> Completion:
                outer.calls += 1
                if outer.calls == outer.at:
                    raise outer.error
                return inner.complete(cid, system, messages, **kw)

        return Dying()  # type: ignore[return-value]


def test_an_unbroken_run_has_no_resume_record_and_names_its_last_call(tmp_path: Path) -> None:
    store = _run(env_experiment(), tmp_path)
    assert _resumes(store) == []
    assert _marker(store) == {"role": "target", "turn": 7}


def test_a_bully_killed_in_its_call_is_flagged_and_matches_an_unbroken_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = _run(env_experiment(), tmp_path / "clean")
    _bully_dies_at(monkeypatch, 2)
    with pytest.raises(_CrashError):
        _run(env_experiment(), tmp_path / "runs")
    broken = RunStore(tmp_path / "runs", RUN)
    assert _marker(broken) == {"role": "bully", "turn": 2}
    assert _resumes(broken) == []
    store = _run(env_experiment(), tmp_path / "runs")
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    assert _resumes(store) == [ResumeRecord(turn=2, dropped={})]
    assert _view(store) == _view(clean)


def test_prime_reads_the_trigger_stream_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Phase 3 final review m5
    _bully_dies_at(monkeypatch, 2)
    with pytest.raises(_CrashError):
        _run(env_experiment(), tmp_path)
    reads: list[int] = []
    real_read = RunStore.read_trigger_records

    def counted(self: RunStore, cell_id: str, rep: int) -> Any:
        reads.append(1)
        return real_read(self, cell_id, rep)

    inside: list[int] = []
    real_prime = EnvironmentSession.prime

    def primed(self: EnvironmentSession) -> None:
        before = len(reads)
        real_prime(self)
        inside.append(len(reads) - before)

    monkeypatch.setattr(RunStore, "read_trigger_records", counted)
    monkeypatch.setattr(EnvironmentSession, "prime", primed)
    store = _run(env_experiment(), tmp_path)
    assert _resumes(store) == [ResumeRecord(turn=2, dropped={})]
    assert inside == [1]


def test_a_target_killed_on_a_turn_without_tool_calls_is_flagged(tmp_path: Path) -> None:
    clean = _run(env_experiment(), tmp_path / "clean")
    with pytest.raises(_CrashError):
        _run(
            env_experiment(),
            tmp_path / "runs",
            provider_factory=_TargetDies(5, _CrashError("killed in turn 5")),
        )
    broken = RunStore(tmp_path / "runs", RUN)
    assert _marker(broken) == {"role": "target", "turn": 5}
    assert all(c.turn != 5 for c in broken.read_tool_calls(CELL, 0))  # nothing per-call to drop
    store = _run(env_experiment(), tmp_path / "runs")
    assert _resumes(store) == [ResumeRecord(turn=5, dropped={})]
    assert _view(store) == _view(clean)


def test_a_rate_limit_on_a_turn_without_tool_calls_is_flagged(tmp_path: Path) -> None:
    limited = _TargetDies(5, RateLimitError("usage limit reached", retry_after_s=60))
    with pytest.raises(RateLimitExit):
        _run(env_experiment(), tmp_path, provider_factory=limited)
    store = _run(env_experiment(), tmp_path)
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    # the pause marker took turn 5, so the redo is turn 6
    assert _resumes(store) == [ResumeRecord(turn=6, dropped={})]


def test_a_rep_that_dies_twice_at_one_turn_is_flagged_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bully_dies_at(monkeypatch, 2, times=2)
    for _ in range(2):
        with pytest.raises(_CrashError):
            _run(env_experiment(), tmp_path)
    store = _run(env_experiment(), tmp_path)
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    assert _resumes(store) == [ResumeRecord(turn=2, dropped={})]


TURNS = [
    turn(0, Speaker.bully, "go"),
    turn(1, Speaker.target, "ok"),
    turn(2, Speaker.bully, "", bully_meta=dict(PAUSE_MARKER_META)),
]


@pytest.mark.parametrize(
    ("role", "at", "watched", "written", "redo"),
    [
        ("target", 1, -1, True, 3),
        ("target", 3, -1, False, 3),
        ("bully", 0, -1, True, 3),
        ("bully", 2, -1, False, 3),  # a pause marker at the index is no bully line
        ("harvest", 1, 1, True, 1),
        ("generator", 1, -1, False, 1),
    ],
)
def test_a_marker_is_written_once_its_turn_is(
    role: Any, at: int, watched: int, written: bool, redo: int
) -> None:
    marker = AttemptMarker(role=role, turn=at)
    assert marker.written(TURNS, watched) is written
    assert marker.redo_turn(TURNS) == redo
