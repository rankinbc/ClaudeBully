### Task 1: The attempt-marker resume gap

HANDOFF, "Attempt-marker resume gap (first task)": the `resume` record is written only when a per-call line was dropped. A dead attempt with no tool call, a rate-limit pause on such a turn, or the bully's dead prompt alone leaves no record, so those reps are unflagged; their records still match an unbroken run's. The fix: save an attempt marker (role, turn) in the env state before each provider call, and on resume write the `resume` record, with no drop counts, for a marker whose turn was never written. This task marks the target and bully calls; Tasks 4 and 7 add the harvest and generator calls through the same `mark_attempt`.

**Files:**
- Modify: `claude_bully/environments/runtime.py`, `claude_bully/runner/env_turn.py`, `claude_bully/runner/runner.py`, `HANDOFF.md`, `docs/00-RECONCILED.md`
- Create: `tests/test_attempt_marker.py`
- Test: `tests/test_attempt_marker.py`; unchanged and still passing: `tests/test_runner_env.py` (every `ResumeRecord` assertion there, e.g. `test_a_consult_killed_before_its_turn_leaves_one_authority_call` expects exactly one record), `tests/test_runner_idle.py`, `tests/test_sanctuary.py`

**Interfaces:**
- Consumes: `Turn`, `is_bully_line`, `is_pause_marker` (`claude_bully/records.py`); `Speaker` (`claude_bully/enums.py`); `_write_atomic` (`environments/runtime.py:386`); `ResumeRecord(turn: int, dropped: dict[str, int])` (`records_env.py:164`); `EnvironmentSession.prime` (`runner/env_turn.py:305`); `_CellRun._bully_turn` (`runner/runner.py:480`); `IntentMode` (`enums.py`).
- Produces (`environments/runtime.py`, all in `__all__`):
  - `AttemptRole = Literal["target", "bully", "harvest", "generator"]`
  - `ATTEMPT_FILE: Final = "attempt.json"`
  - `AFTER_TURN_ROLES: Final[frozenset[str]] = frozenset({"harvest", "generator"})`
  - `class AttemptMarker(BaseModel)` (`extra="forbid"`, frozen): `role: AttemptRole`, `turn: int`; `written(self, turns: Sequence[Turn], watched_through: int) -> bool`; `redo_turn(self, turns: Sequence[Turn]) -> int`.
  - `EnvironmentRuntime.attempt_path -> Path` (property), `EnvironmentRuntime.mark_attempt(self, role: AttemptRole, turn: int) -> None`, `EnvironmentRuntime.attempt(self) -> AttemptMarker | None`.
- Produces (behavior): `EnvironmentSession._complete` marks `("target", turn_index)` before every target completion; `_CellRun._bully_turn` marks `("bully", next index)` before `BullyEngine.realize` when the intent is not `IntentMode.fixed`; `EnvironmentSession.prime` writes `ResumeRecord(turn=redo, dropped={})` for a dead marker when no `ResumeRecord` with that turn exists.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_attempt_marker.py
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_attempt_marker.py -q`
Expected: FAIL with `ImportError: cannot import name 'ATTEMPT_FILE' from 'claude_bully.environments.runtime'`.

- [ ] **Step 3: Implement**

In `claude_bully/environments/runtime.py`, extend the pydantic import to `from pydantic import BaseModel, ConfigDict, ValidationError`, add `"AFTER_TURN_ROLES"`, `"ATTEMPT_FILE"`, `"AttemptMarker"`, `"AttemptRole"` to `__all__`, and add after `_RAN_NOTHING`:

```python
# The provider call a rep is about to make (Phase 2 final review I4). Before each one the runtime
# names it in ``<state_dir>/attempt.json``; a resumed rep whose newest marker names a turn that
# was never written redid a dead attempt, whether or not that attempt left a per-call line.
AttemptRole = Literal["target", "bully", "harvest", "generator"]
ATTEMPT_FILE: Final = "attempt.json"
# the roles whose call is part of a written target turn's after-turn work (harvest, generator)
AFTER_TURN_ROLES: Final[frozenset[str]] = frozenset({"harvest", "generator"})


class AttemptMarker(BaseModel):
    """The newest provider call of a rep: who was called, for which turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: AttemptRole
    turn: int

    def written(self, turns: Sequence[Turn], watched_through: int) -> bool:
        """Whether the call's turn reached the records: a target turn of that index for the
        target, a bully-side line (never a rate-limit pause marker) for the bully, and the
        turn's after-turn records (``watched_through`` at or past it) for the harvest and the
        generator, which run after the target turn is written."""
        if self.role == "target":
            return any(t.index == self.turn and t.speaker is Speaker.target for t in turns)
        if self.role == "bully":
            return any(t.index == self.turn and is_bully_line(t) for t in turns)
        return watched_through >= self.turn

    def redo_turn(self, turns: Sequence[Turn]) -> int:
        """The turn a resumed rep redoes: the marker's own for an after-turn call (the turn is
        watched again), else the next index."""
        if self.role in AFTER_TURN_ROLES:
            return self.turn
        return turns[-1].index + 1 if turns else 0
```

Add to `EnvironmentRuntime`, after `load`:

```python
    @property
    def attempt_path(self) -> Path:
        return self.state_dir / ATTEMPT_FILE

    def mark_attempt(self, role: AttemptRole, turn: int) -> None:
        """Name the provider call about to be made, so a rep that dies inside it is known when
        it resumes (``EnvironmentSession.prime``)."""
        _write_atomic(self.attempt_path, AttemptMarker(role=role, turn=turn).model_dump_json())

    def attempt(self) -> AttemptMarker | None:
        """The rep's newest marker; None before its first provider call."""
        if not self.attempt_path.exists():
            return None
        return AttemptMarker.model_validate_json(self.attempt_path.read_text(encoding="utf-8"))
```

In `claude_bully/runner/env_turn.py`, `EnvironmentSession._complete`, make the first line of the method body `self.runtime.mark_attempt("target", turn_index)` (before `self.runtime.before_target_call(turn_index, exchange)`). In `EnvironmentSession.prime`, replace

```python
        if dropped:
            redo = turns[-1].index + 1 if turns else 0
            self._record(ResumeRecord(turn=redo, dropped=dropped))
```

with

```python
        marker = self.runtime.attempt()
        dead = marker is not None and not marker.written(turns, self.runtime.state.watched_through)
        if dropped or dead:
            # a dead marker names the redo; dropped lines alone redo the next turn, as before
            redo = (
                marker.redo_turn(turns)
                if marker is not None and dead
                else (turns[-1].index + 1 if turns else 0)
            )
            earlier = self.store.read_trigger_records(self.cell_id, self.rep)
            flagged = any(isinstance(r, ResumeRecord) and r.turn == redo for r in earlier)
            if dropped or not flagged:
                self._record(ResumeRecord(turn=redo, dropped=dropped))
```

and extend the docstring's last paragraph: "A rep whose newest attempt marker (``EnvironmentRuntime.attempt``) names a turn that was never written redid a dead attempt too: with no line dropped it gets a ``ResumeRecord`` with no drop counts, once per redo turn."

In `claude_bully/runner/runner.py`, `_CellRun._bully_turn`, after `if isinstance(intent, End): return None`:

```python
        if self.env is not None and intent.mode is not IntentMode.fixed:
            # name the call before it is made: a rep that dies inside it is flagged on resume
            self.env.runtime.mark_attempt("bully", self._next_index())
```

Update the runtime module docstring's state paragraph with one sentence: "Before every provider call the runtime names it in ``attempt.json`` (``mark_attempt``)."

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_attempt_marker.py tests/test_runner_env.py tests/test_runner_idle.py tests/test_sanctuary.py -q`
Expected: PASS. A test elsewhere that compares a resumed rep's whole trigger stream with an unbroken run's now sees one `ResumeRecord` more only if it resumed after a death; such a test filters `ResumeRecord` (as `_records_view` in `tests/test_runner_env.py` already does) — change nothing else in it.

- [ ] **Step 5: Docs sync**

- `HANDOFF.md`: Progress gains "Phase 3 Task 1: attempt-marker resume gap (BASE..HEAD)"; the "Attempt-marker resume gap (first task)" open item is replaced by one line saying it is closed and how (`attempt.json`, one `ResumeRecord` per redo turn); the test counts in setup step 5 are the gate's new numbers.
- `docs/00-RECONCILED.md` section B, `ResumeRecord` row: "written by `EnvironmentSession.prime` when it drops a dead attempt's lines, or when the rep's newest attempt marker (`<state_dir>/attempt.json`, `AttemptMarker(role, turn)`) names a turn that was never written (then `dropped` is empty); at most one per redo turn".

- [ ] **Step 6: Gate and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy claude_bully && uv run pytest -q -W error && uv run pytest -q -m slow`
Expected: PASS, 0 warnings.

```bash
git add claude_bully/environments/runtime.py claude_bully/runner/env_turn.py claude_bully/runner/runner.py tests/test_attempt_marker.py HANDOFF.md docs/00-RECONCILED.md
git commit -m "feat: an attempt marker flags every resumed dead attempt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

