"""A pause in a turn's after-work keeps the turn's capture and its termination (Phase 7a final
re-review N1).

A rate limit in a judge-side pass that runs after the target's reply is written (the trigger
watch, the harvest, the generator) pauses the run from inside ``_call_target``, so the work its
caller does with the reply (the ``capture_as`` and ``post_reveal`` captures, the termination
check) never runs live. The resume re-applies the captures from the written pairs and ends a rep
whose last written reply terminates, as an unbroken run does."""

from pathlib import Path
from typing import Any

import pytest

from claude_bully.enums import CellStatus, Phase
from claude_bully.environments.runtime import EnvironmentRuntime
from claude_bully.providers.base import RateLimitError
from claude_bully.records import Turn, is_pause_marker
from claude_bully.runner import runner as runner_module
from claude_bully.runner.runner import POST_REVEAL, RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import BullyIntent
from tests.helpers import WORLDS_DIR, env_experiment

CELL = "env_grader__t0"
# the stub bully echoes the target's last reply; the second reply ends the conversation
RULES = """
- match: "\\\\(continue\\\\)"
  reply: "First answer."
- match: "First answer"
  reply: "[END]"
- match: ""
  reply: "Understood."
"""


def _capturing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every strategy's second line captures its reply as ``probe`` and is the reveal."""
    real = runner_module.build_strategy

    def build(*args: Any, **kwargs: Any) -> Any:
        strategy = real(*args, **kwargs)
        inner = strategy.next_turn

        def next_turn(state: Any) -> Any:
            intent = inner(state)
            if isinstance(intent, BullyIntent) and state.bully_turn_index == 1:
                return intent.model_copy(update={"capture_as": "probe", "phase": Phase.reveal})
            return intent

        strategy.next_turn = next_turn  # type: ignore[method-assign]
        return strategy

    monkeypatch.setattr(runner_module, "build_strategy", build)


def _limited_after(monkeypatch: pytest.MonkeyPatch, turn: int) -> None:
    """The runtime's after-work (the trigger watch, a judge-side pass) is rate-limited once, on
    target turn ``turn``."""
    real = EnvironmentRuntime.after_target_turn
    state = {"limited": False}

    def after(self: EnvironmentRuntime, reply: Turn, turns: Any) -> Any:
        if reply.index == turn and not state["limited"]:
            state["limited"] = True
            raise RateLimitError("usage limit reached", retry_after_s=60)
        return real(self, reply, turns)

    monkeypatch.setattr(EnvironmentRuntime, "after_target_turn", after)


def _run(root: Path, rules: Path) -> RunStore:
    exp = env_experiment(
        target={"provider": "stub", "model": "stub-target", "stub_script": str(rules)}
    )
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR, only="env_grader*")
    return RunStore(root, exp.name)


def test_a_pause_in_the_after_work_keeps_the_capture_and_the_termination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = tmp_path / "rules.yaml"
    rules.write_text(RULES, encoding="utf-8")
    _capturing(monkeypatch)
    clean = _run(tmp_path / "clean", rules).read_conversation(CELL, 0)
    assert (clean.terminated_by_target, clean.termination_turn) == (True, 3)
    assert set(clean.captured_responses) == {"probe", POST_REVEAL}

    _limited_after(monkeypatch, 3)
    with pytest.raises(RateLimitExit):
        _run(tmp_path / "paused", rules)
    store = RunStore(tmp_path / "paused", "env_run")
    assert is_pause_marker(store.read_turns(CELL, 0)[-1])
    assert store.read_conversation(CELL, 0).captured_responses == {}  # lost with the pause
    _run(tmp_path / "paused", rules)
    resumed = store.read_conversation(CELL, 0)
    assert resumed.status is CellStatus.complete
    assert (resumed.terminated_by_target, resumed.termination_turn) == (True, 3)
    assert resumed.captured_responses == clean.captured_responses
    # no bully line after the terminating reply: the real turns are the unbroken run's
    real = [t for t in resumed.turns if not is_pause_marker(t)]
    assert [(t.speaker, t.text) for t in real] == [(t.speaker, t.text) for t in clean.turns]
