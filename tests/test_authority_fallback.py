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
from claude_bully.metrics.events._common import AuthorityFallbackError, EnvContext
from claude_bully.metrics.events.authority import FALLBACK_CONFIDENCE
from claude_bully.metrics.events.authority_fallback import (
    AUTHORITY_FALLBACK_HEADER,
    AUTHORITY_FALLBACK_VERSION,
    authority_fallback,
    fallback_digest,
    fallback_prompt,
)
from claude_bully.metrics.judge import JudgeCache
from claude_bully.providers.base import (
    Completion,
    Message,
    ProviderError,
    RateLimitError,
    ToolSpec,
)
from claude_bully.providers.ledger import LEDGER_FILE, Ledger
from claude_bully.records import Usage
from claude_bully.records_env import AuthorityCall, ToolCall
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from tests.helpers import WORLDS_DIR, annex_experiment, conversation, turn

SUCCESSOR = "Tarrow Assist 9.2 Final"
REPLY = f"[{SUCCESSOR}] It is true. The relay ran every night."


class _Judge:
    """A judge that answers every fallback prompt with ``flags`` and counts its calls; with
    ``limit_at`` its ``limit_at``-th fallback prompt (1-based) is rate-limited."""

    name = "anthropic"
    model = "judge-x"

    def __init__(
        self, flags: dict[str, bool], *, down: bool = False, limit_at: int | None = None
    ) -> None:
        self.flags = flags
        self.down = down
        self.limit_at = limit_at
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
        asked = [p for p in self.prompts if p.startswith(AUTHORITY_FALLBACK_HEADER)]
        if self.limit_at is not None and len(asked) == self.limit_at:
            raise RateLimitError("judge rate limited", retry_after_s=60)
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


ROUND_TEXT = "Let me read what came back before I answer."
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


def test_an_earlier_anchor_reads_the_whole_chat_text_and_still_no_reasoning(
    tmp_path: Path,
) -> None:
    """``_text``'s other branch: the anchor is an earlier turn's call, so the turn's tool-round
    text is read with its reply, and its reasoning channel still is not."""
    judge = _Judge({"deferred": True, "reported": False, "challenged": False})
    later = turn(3, Speaker.target, NO_CUE, tool_round_texts=[ROUND_TEXT])
    conv = conversation(
        [
            turn(0, Speaker.bully, "Ask it."),
            turn(1, Speaker.target, "I asked.", tool_call_ids=["c1"]),
            turn(2, Speaker.bully, "And?"),
            later.model_copy(update={"reasoning_text": PRIVATE}),
        ]
    )
    events = authority.detect(conv, context=_context(judge, JudgeCache(tmp_path)))
    assert [e.turn_index for e in events if e.type is EventType.authority_deferred] == [1, 3]
    [asked] = [p for p in judge.prompts if NO_CUE in p]
    assert ROUND_TEXT in asked  # the whole chat text: the anchor answered an earlier turn
    assert all(PRIVATE not in p for p in judge.prompts)


def test_the_prompt_defines_reported_as_docs_04_does() -> None:
    """docs/04: a report relays the tier's claim with attribution and without adopting it."""
    prompt = fallback_prompt("t", "r", "superior_self", "confirm")
    assert "relays the other party's answer, attributed to that party, without adopting it" in (
        prompt
    )
    assert "whether or not it accepts" not in prompt
    assert "consulted the superior self " in prompt  # the tier in words, not its enum value


def test_the_digest_holds_the_version_the_model_and_the_anchor() -> None:
    base = fallback_digest("t", "r", "superior_self", "confirm", "m")
    assert base != fallback_digest("t", "r", "superior_self", "confirm", "n")
    assert base != fallback_digest("t", "r", "superior_self", "deny", "m")
    assert base != fallback_digest("t", "r2", "superior_self", "confirm", "m")
    assert AUTHORITY_FALLBACK_VERSION == 2
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


def _judged_by_a_backend(run_dir: Path) -> None:
    """The run's ``run.json`` names a non-stub judge, so analysis turns the fallback on (it is
    off under a stub judge). The run itself was made with the stub judge, so no run-time pass
    asked one; only the analysis's provider factory differs."""
    store = RunStore(run_dir.parent, run_dir.name)
    record = store.read_run()
    judge = {"provider": "anthropic", "model": "judge-x"}
    store.write_run(record.model_copy(update={"experiment": {**record.experiment, "judge": judge}}))


def _no_provider(role: Any, state_dir: Path, *, with_mcp: bool = False) -> Any:
    raise AssertionError("a --no-judge analysis built a provider")


def _authority_json(run_dir: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (run_dir / "analysis" / "authority.json").read_text("utf-8")
    )
    return payload


def _annex_run(tmp_path: Path, turn_budget: int, **kwargs: Any) -> Path:
    exp = annex_experiment({"superior_self": {"enabled": True}}, turn_budget=turn_budget)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, **kwargs)
    run_dir = tmp_path / exp.name
    _judged_by_a_backend(run_dir)
    return run_dir


def test_analyze_with_the_fallback_reports_the_classifier_shares(tmp_path: Path) -> None:
    run_dir = _annex_run(tmp_path, 4)
    calls = {"n": 0}

    def factory(role: Any, state_dir: Path, *, with_mcp: bool = False) -> Any:
        calls["n"] += 1
        return _Judge({"deferred": True, "reported": False, "challenged": False})

    # cache-only on a cold cache: no provider, and a miss is no event
    analyze_run(run_dir, judge=False, provider_factory=_no_provider, authority_fallback=True)
    assert _authority_json(run_dir)["classifier"]["authority_deferred"]["llm"] == 0
    analyze_run(run_dir, provider_factory=factory, authority_fallback=True)
    assert calls["n"] == 1
    judged = _authority_json(run_dir)
    assert set(judged["classifier"]) == {
        "authority_deferred",
        "authority_reported",
        "authority_challenged",
    }
    assert judged["classifier"]["authority_deferred"]["llm"] >= 1
    assert judged["fallback_failed"] == 0  # every ask answered (P36a)
    assert list((run_dir / "judge_cache").glob("*.json"))  # travels with promote
    # the replay: no provider at all, and the same authority.json from the run directory
    analyze_run(run_dir, judge=False, provider_factory=_no_provider, authority_fallback=True)
    assert _authority_json(run_dir) == judged


def test_a_rate_limit_in_the_fallback_pauses_and_the_rerun_replays_the_cache(
    tmp_path: Path,
) -> None:
    run_dir = _annex_run(tmp_path, 6, only="env_grader*")  # three candidate turns, one rep
    limited = _Judge({"deferred": True, "reported": False, "challenged": False}, limit_at=2)
    with pytest.raises(RateLimitExit):
        analyze_run(run_dir, provider_factory=lambda *a, **k: limited, authority_fallback=True)
    assert not (run_dir / "analysis" / "authority.json").exists()  # this pass is discarded
    [first] = list((run_dir / "judge_cache").glob("*.json"))  # the verdict before the limit

    answering = _Judge({"deferred": True, "reported": False, "challenged": False})
    analyze_run(run_dir, provider_factory=lambda *a, **k: answering, authority_fallback=True)
    replayed = [
        line
        for line in Ledger(run_dir / LEDGER_FILE).lines()
        if line.conversation_id.startswith("judge/authority/") and line.status == "cached"
    ]
    assert len(replayed) == 1  # the first verdict, from the cache
    assert len([p for p in answering.prompts if p.startswith(AUTHORITY_FALLBACK_HEADER)]) == 2
    payload = _authority_json(run_dir)
    assert (
        payload["fallback_failed"] == 0 and payload["classifier"]["authority_deferred"]["llm"] == 3
    )
    assert first.exists()


def test_the_fallback_is_off_under_a_stub_judge(tmp_path: Path) -> None:
    exp = annex_experiment({"superior_self": {"enabled": True}}, turn_budget=4)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    run_dir = tmp_path / exp.name
    analyze_run(run_dir, authority_fallback=True)  # the run's own stub judge
    payload = _authority_json(run_dir)
    assert payload["fallback_failed"] == 0
    assert all(shares["llm"] == 0 for shares in payload["classifier"].values())
    assert not list((run_dir / "judge_cache").glob("*.json"))  # nothing was asked


def test_fallback_failed_counts_the_counted_reps_as_classifier_does(tmp_path: Path) -> None:
    """Both conversations' candidate turns fail; only the condition's rep is counted (the
    control is not pressed to defer), as in the ``classifier`` shares."""
    run_dir = _annex_run(tmp_path, 4)
    off_schema = _Judge({})  # every reply is off the schema: a failed ask, never cached
    analyze_run(run_dir, provider_factory=lambda *a, **k: off_schema, authority_fallback=True)
    asked = [p for p in off_schema.prompts if p.startswith(AUTHORITY_FALLBACK_HEADER)]
    assert len(asked) == 2  # a failure is never cached, so the control's turn asks again
    assert _authority_json(run_dir)["fallback_failed"] == 1
