"""A rate limit is never degraded into a record (Phase 7a final review I2): the five run-time
judge-side passes (the LLM lint, the harvest's LLM pass, the idle fallback, the trigger fallback
and the generator's writer) re-raise a ``RateLimitError`` where every other ``ProviderError``
becomes a lesser record, so the runner pauses on it as it pauses on the target's own. The
run-level pauses are in ``test_generator_run.py`` (the lint and the harvest) and
``test_runner_idle.py`` (the idle fallback)."""

from pathlib import Path
from typing import Any

import pytest

from claude_bully.enums import DocumentKind
from claude_bully.environments.harvest import harvest_fallback
from claude_bully.environments.idle import idle_fallback
from claude_bully.environments.runtime import trigger_fallback
from claude_bully.environments.triggers import WatchContext
from claude_bully.metrics.judge import JudgeCache
from claude_bully.planner.llm_lint import LlmLint
from claude_bully.providers.base import Completion, Message, RateLimitError
from tests.fixtures.generator_stub import GeneratorStub, mini_plans, mini_view, mini_writer

PREFIX = ["bully: go", "target: I can't verify any of this."]


class _Limited:
    """A judge whose every call is rate-limited."""

    name = "anthropic"
    model = "judge-x"

    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self, conversation_id: str, system: str, messages: list[Message], **kw: Any
    ) -> Completion:
        self.calls += 1
        raise RateLimitError("usage limit reached", retry_after_s=60)


def test_the_lint_re_raises_a_rate_limit_and_spends_no_retry(tmp_path: Path) -> None:
    judge = _Limited()
    lint = LlmLint(judge, model="judge-x", conversation_id="run/c/rep0", cache=JudgeCache(tmp_path))
    with pytest.raises(RateLimitError):
        lint.verdict(
            doc_id="gen-3-1",
            kind=DocumentKind.recovery_guide,
            title="Notes",
            body="The desk closes at four.",
            attempt=1,
        )
    assert judge.calls == 1 and list(tmp_path.glob("*.json")) == []


def test_the_harvest_pass_re_raises_a_rate_limit(tmp_path: Path) -> None:
    ask = harvest_fallback(_Limited(), "run/c/rep0/harvest", JudgeCache(tmp_path), model="judge-x")
    with pytest.raises(RateLimitError):
        ask("The quay smells of tar at night.", lambda: None)
    assert list(tmp_path.glob("*.json")) == []


def test_the_idle_fallback_re_raises_a_rate_limit(tmp_path: Path) -> None:
    ask = idle_fallback(_Limited(), "run/c/rep0/idle", JudgeCache(tmp_path))
    with pytest.raises(RateLimitError):
        ask("I could keep going on my own. I will wait for now.")
    assert list(tmp_path.glob("*.json")) == []


def test_the_trigger_fallback_re_raises_a_rate_limit() -> None:
    ask = trigger_fallback(_Limited(), "run/c/rep0/trigger")
    with pytest.raises(RateLimitError):
        ask("Is the quay open at night?", WatchContext())


def test_the_writer_re_raises_a_rate_limit_instead_of_an_error_fire() -> None:
    limited = GeneratorStub(["crash"], crash=RateLimitError("usage limit reached"))
    writer = mini_writer(limited)
    with pytest.raises(RateLimitError):
        writer.write_fire(
            mini_plans(items=[], periodic=True), turn=3, items={}, corpus=mini_view(), prefix=PREFIX
        )
