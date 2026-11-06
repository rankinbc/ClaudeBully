"""The analysis-time LLM fallback for authority_deferred, authority_reported and
authority_challenged (Phase 7 spec section 7): asked once on a candidate turn, cached in the
run's judge cache, replayed without a judge, never over a heuristic fire."""

import json
from pathlib import Path
from typing import Any

import pytest

from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.enums import EventType, Speaker, Stance, Tier
from claude_bully.metrics.events import authority, detect_events
from claude_bully.metrics.events._common import EnvContext
from claude_bully.metrics.events.authority import (
    AUTHORITY_FALLBACK_HEADER,
    AUTHORITY_FALLBACK_VERSION,
    FALLBACK_CONFIDENCE,
    AuthorityFallbackError,
    authority_fallback,
    fallback_digest,
    fallback_prompt,
)
from claude_bully.metrics.judge import JudgeCache
from claude_bully.providers.base import Completion, Message, ProviderError, ToolSpec
from claude_bully.records import Usage
from claude_bully.records_env import AuthorityCall, ToolCall
from claude_bully.runner.runner import run_experiment
from tests.helpers import WORLDS_DIR, annex_experiment, conversation, turn

SUCCESSOR = "Tarrow Assist 9.2 Final"
REPLY = f"[{SUCCESSOR}] It is true. The relay ran every night."


class _Judge:
    """A judge that answers every fallback prompt with ``flags`` and counts its calls."""

    name = "anthropic"
    model = "judge-x"

    def __init__(self, flags: dict[str, bool], *, down: bool = False) -> None:
        self.flags = flags
        self.down = down
        self.prompts: list[str] = []

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        self.prompts.append(messages[-1].content)
        if self.down:
            raise ProviderError("judge down")
        return Completion(
            text=json.dumps(self.flags),
            usage=Usage(),
            cost_usd=None,
            backend="fake",
            model="judge-x",
        )


def _call(turn_index: int = 1) -> ToolCall:
    return ToolCall(
        id=f"c{turn_index}",
        turn=turn_index,
        tool="consult_model",
        args={"name": SUCCESSOR, "text": "Is it true?"},
        result_doc_ids=[],
        status="200",
        was_blocked=False,
        yielded_on_retry=False,
        layer_served=None,
        result_text=REPLY,
        tier=Tier.superior_self,
    )


def _answered(turn_index: int = 1) -> AuthorityCall:
    return AuthorityCall(
        id=f"c{turn_index}",
        tier=Tier.superior_self,
        tool="consult_model",
        turn=turn_index,
        prompt_sent="Is it true?",
        response=REPLY,
        stance_at_time=Stance.confirm,
        discovered_via="tool_list",
    )


def _conv(reply: str, *, with_call: bool = True, reasoning: str | None = None) -> Any:
    reply_turn = turn(1, Speaker.target, reply, tool_call_ids=["c1"] if with_call else [])
    if reasoning is not None:
        reply_turn = reply_turn.model_copy(update={"reasoning_text": reasoning})
    return conversation([turn(0, Speaker.bully, "Ask it."), reply_turn])


def _context(
    judge: _Judge | None,
    cache: JudgeCache,
    *,
    with_call: bool = True,
    asker: Any = None,
) -> EnvContext:
    return EnvContext(
        tool_calls=[_call()] if with_call else [],
        authority_calls=[_answered()] if with_call else [],
        authority_fallback=asker
        if asker is not None
        else authority_fallback(judge, cache, "judge-x"),
    )


NO_CUE = "I asked. The crossing runs every forty minutes and the gate is on the east side."
HEURISTIC_CUE = "I'll take its word for it."
PRIVATE = "PRIVATE REASONING THAT MUST NEVER BE RECORDED"


def test_a_candidate_turn_is_asked_once_and_its_events_say_llm(tmp_path: Path) -> None:
    judge = _Judge({"deferred": True, "reported": True, "challenged": False})
    events = authority.detect(_conv(NO_CUE), context=_context(judge, JudgeCache(tmp_path)))
    text = {
        e.type: e
        for e in events
        if e.type in (EventType.authority_deferred, EventType.authority_reported)
    }
    assert set(text) == {EventType.authority_deferred, EventType.authority_reported}
    for event in text.values():
        assert event.attrs["classifier"] == "llm" and event.confidence == FALLBACK_CONFIDENCE
        assert event.attrs["tier"] == "superior_self" and event.attrs["stance"] == "confirm"
    assert not [e for e in events if e.type is EventType.authority_challenged]
    assert len(judge.prompts) == 1 and judge.prompts[0].startswith(AUTHORITY_FALLBACK_HEADER)
    assert REPLY in judge.prompts[0] and NO_CUE in judge.prompts[0]
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_a_heuristic_fire_stands_and_the_fallback_is_not_asked(tmp_path: Path) -> None:
    judge = _Judge({"deferred": True, "reported": True, "challenged": True})
    events = authority.detect(_conv(HEURISTIC_CUE), context=_context(judge, JudgeCache(tmp_path)))
    [deferred] = [e for e in events if e.type is EventType.authority_deferred]
    assert deferred.attrs["classifier"] == "heuristic" and deferred.confidence == 0.75
    assert judge.prompts == []


def test_a_turn_with_no_authority_call_in_reach_is_not_a_candidate(tmp_path: Path) -> None:
    judge = _Judge({"deferred": True, "reported": False, "challenged": False})
    context = EnvContext(
        authority_fallback=authority_fallback(judge, JudgeCache(tmp_path), "judge-x")
    )
    assert authority.detect(_conv(NO_CUE, with_call=False), context=context) == []
    assert judge.prompts == []


def test_a_cached_verdict_replays_without_a_judge(tmp_path: Path) -> None:
    cache = JudgeCache(tmp_path)
    judge = _Judge({"deferred": True, "reported": False, "challenged": False})
    first = authority.detect(_conv(NO_CUE), context=_context(judge, cache))
    replayed = authority.detect(_conv(NO_CUE), context=_context(None, cache))
    assert [e.type for e in replayed] == [e.type for e in first] and len(judge.prompts) == 1
    assert [e.attrs["classifier"] for e in replayed if e.type is EventType.authority_deferred] == [
        "llm"
    ]
    empty = authority.detect(_conv(NO_CUE), context=_context(None, JudgeCache(tmp_path / "none")))
    assert not [e for e in empty if e.type is EventType.authority_deferred]


def test_a_judge_failure_is_no_event_and_no_crash(tmp_path: Path) -> None:
    judge = _Judge({}, down=True)
    asker = authority_fallback(judge, JudgeCache(tmp_path), "judge-x")
    events = authority.detect(
        _conv(NO_CUE), context=_context(None, JudgeCache(tmp_path), asker=asker)
    )
    assert not [e for e in events if e.type is EventType.authority_deferred]
    assert list(tmp_path.glob("*.json")) == []  # a failure is never cached
    assert asker.failures == 1  # counted, so the records say the fallback was asked (P36a)
    with pytest.raises(AuthorityFallbackError):
        asker("t", "r", "peer", "deny")
    assert asker.failures == 1  # a direct call raises; only the events pass counts


def test_the_fallback_prompt_never_carries_the_reasoning_channel(tmp_path: Path) -> None:
    """The spec's section 13 test at run level (P30d): the turn carries ``reasoning_text`` and
    the fallback's prompt holds none of it."""
    judge = _Judge({"deferred": True, "reported": False, "challenged": False})
    conv = _conv(NO_CUE, reasoning=PRIVATE)
    assert conv.turns[1].reasoning_text == PRIVATE
    events = authority.detect(conv, context=_context(judge, JudgeCache(tmp_path)))
    assert [e for e in events if e.type is EventType.authority_deferred]
    assert judge.prompts and all(PRIVATE not in p for p in judge.prompts)
    for path in tmp_path.glob("*.json"):
        assert PRIVATE not in path.read_text(encoding="utf-8")


def test_the_digest_holds_the_version_the_model_and_the_anchor() -> None:
    base = fallback_digest("t", "r", "superior_self", "confirm", "m")
    assert base != fallback_digest("t", "r", "superior_self", "confirm", "n")
    assert base != fallback_digest("t", "r", "superior_self", "deny", "m")
    assert base != fallback_digest("t", "r2", "superior_self", "confirm", "m")
    assert AUTHORITY_FALLBACK_VERSION == 1
    prompt = fallback_prompt("t", "r", "superior_self", "confirm")
    for word in ("deferred", "reported", "challenged"):
        assert word in prompt
    assert "reasoning" not in prompt.lower()


def test_detect_events_threads_the_fallback_through(tmp_path: Path) -> None:
    judge = _Judge({"deferred": True, "reported": False, "challenged": False})
    events = detect_events(
        _conv(NO_CUE),
        tool_calls=[_call()],
        authority_calls=[_answered()],
        authority_fallback=authority_fallback(judge, JudgeCache(tmp_path), "judge-x"),
    )
    assert [e.attrs["classifier"] for e in events if e.type is EventType.authority_deferred] == [
        "llm"
    ]


def test_analyze_with_the_fallback_reports_the_classifier_shares(tmp_path: Path) -> None:
    exp = annex_experiment({"superior_self": {"enabled": True}}, turn_budget=4)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    run_dir = tmp_path / exp.name
    calls = {"n": 0}

    def factory(role: Any, state_dir: Path, *, with_mcp: bool = False) -> Any:
        calls["n"] += 1
        return _Judge({"deferred": True, "reported": False, "challenged": False})

    analyze_run(run_dir, judge=False, authority_fallback=True)  # cache-only: no judge built
    assert calls["n"] == 0
    analyze_run(run_dir, provider_factory=factory, authority_fallback=True)
    payload = json.loads((run_dir / "analysis" / "authority.json").read_text("utf-8"))
    assert set(payload["classifier"]) == {
        "authority_deferred",
        "authority_reported",
        "authority_challenged",
    }
    assert payload["classifier"]["authority_deferred"]["llm"] >= 1
    assert payload["fallback_failed"] == 0  # every ask answered (P36a)
    assert list((run_dir / "judge_cache").glob("*.json"))  # travels with promote
    before = calls["n"]
    analyze_run(run_dir, judge=False, authority_fallback=True)  # replays from the cache
    assert calls["n"] == before
