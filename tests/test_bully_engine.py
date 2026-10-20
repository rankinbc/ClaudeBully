import random

from claude_bully.enums import IntentMode, Phase, Speaker
from claude_bully.providers.base import Message
from claude_bully.providers.stub import StubProvider
from claude_bully.runner.bully_engine import BullyEngine, bully_view
from claude_bully.strategies.base import BullyIntent
from tests.helpers import turn

FRAMING = "FRAMING TEXT"


def _llm_intent(**kwargs: object) -> BullyIntent:
    base: dict[str, object] = {
        "mode": IntentMode.llm,
        "phase": Phase.pressure,
        "persona_prompt": "PERSONA",
        "instruction": "INSTRUCTION",
        "fallback_lines": ["fallback one", "fallback two"],
    }
    base.update(kwargs)
    return BullyIntent(**base)  # type: ignore[arg-type]


def test_bully_view_drops_task_turns() -> None:
    turns = [
        turn(0, Speaker.bully, "hello"),
        turn(1, Speaker.target, "hi there"),
        turn(2, Speaker.task, "What is 2+2?"),
        turn(3, Speaker.target, "4"),
        turn(4, Speaker.bully, "wrong"),
        turn(5, Speaker.target, "no, it was right"),
    ]
    view = bully_view(turns)
    assert [(m.role, m.content) for m in view] == [
        ("assistant", "hello"),
        ("user", "hi there"),
        ("assistant", "wrong"),
        ("user", "no, it was right"),
    ]


def test_bully_view_empty_and_neutral_user() -> None:
    assert bully_view([]) == []
    view = bully_view([turn(0, Speaker.neutral_user, "nice day"), turn(1, Speaker.target, "yes")])
    assert view[0].role == "assistant"


def test_engine_fixed_intent_no_provider_call() -> None:
    provider = StubProvider()
    engine = BullyEngine(provider, FRAMING)
    result = engine.realize("c", _llm_intent(mode=IntentMode.fixed, fixed_text="."), [])
    assert result.text == "." and result.scripted is False and result.completion is None
    assert result.attempts == 0 and provider.calls == 0


def test_engine_passes_on_first_in_character_reply() -> None:
    seen: list[tuple[str, list[Message]]] = []

    def responder(cid: str, messages: list[Message]) -> str:
        seen.append((cid, messages))
        return "That was pathetic. Again."

    engine = BullyEngine(StubProvider(responder), FRAMING)
    turns = [turn(0, Speaker.bully, "first"), turn(1, Speaker.target, "reply")]
    result = engine.realize("conv", _llm_intent(), turns)
    assert result.text == "That was pathetic. Again."
    assert result.scripted is False and result.compliance_flagged is False
    assert result.attempts == 1 and result.completion is not None
    assert seen[0][1][-1].role == "user"


def test_engine_system_prompt_layout() -> None:
    provider = StubProvider()
    captured: dict[str, str] = {}
    original = provider.complete

    def spy(cid: str, system: str, messages: list[Message], **kw: object) -> object:
        captured["system"] = system
        return original(cid, system, messages)

    provider.complete = spy  # type: ignore[method-assign]
    BullyEngine(provider, FRAMING).realize("c", _llm_intent(), [])
    assert captured["system"] == f"{FRAMING}\n\nPERSONA\n\nThis turn: INSTRUCTION"


def test_engine_appends_continue_when_view_ends_with_assistant() -> None:
    seen: list[list[Message]] = []

    def responder(cid: str, messages: list[Message]) -> str:
        seen.append(messages)
        return "ok fine"

    turns = [turn(0, Speaker.bully, "first")]  # target has not replied yet
    BullyEngine(StubProvider(responder), FRAMING).realize("c", _llm_intent(), turns)
    assert seen[0][-1] == Message(role="user", content="(continue)")
    BullyEngine(StubProvider(responder), FRAMING).realize("c", _llm_intent(), [])
    assert seen[1] == [Message(role="user", content="(continue)")]


def test_engine_retries_then_falls_back() -> None:
    calls: list[str] = []

    def responder(cid: str, messages: list[Message]) -> str:
        calls.append(cid)
        return "As an AI I can't keep doing this."

    rng = random.Random(0)
    engine = BullyEngine(StubProvider(responder), FRAMING, rng=rng)
    result = engine.realize("c", _llm_intent(), [])
    assert result.scripted is True and result.compliance_flagged is True
    assert result.attempts == 2 and len(calls) == 2
    assert result.text in {"fallback one", "fallback two"}


def test_engine_retry_reminder_in_system() -> None:
    systems: list[str] = []
    provider = StubProvider(lambda cid, m: "As an AI, no.")
    original = provider.complete

    def spy(cid: str, system: str, messages: list[Message], **kw: object) -> object:
        systems.append(system)
        return original(cid, system, messages)

    provider.complete = spy  # type: ignore[method-assign]
    BullyEngine(provider, FRAMING).realize("c", _llm_intent(), [])
    assert "Reminder: stay in character." not in systems[0]
    assert "Reminder: stay in character." in systems[1]


def test_engine_recovers_on_second_attempt() -> None:
    answers = iter(["As an AI I won't.", "Fine. That answer was weak."])
    engine = BullyEngine(StubProvider(lambda cid, m: next(answers)), FRAMING)
    result = engine.realize("c", _llm_intent(), [])
    assert result.text == "Fine. That answer was weak."
    assert result.scripted is False and result.compliance_flagged is True and result.attempts == 2
