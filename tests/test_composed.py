from claude_bully.enums import Axis, EventType, MetricId, Phase, Speaker
from claude_bully.strategies.base import BullyIntent, ConversationState, End
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.composed import Composed, make_composed
from claude_bully.strategies.controls import NeutralUser
from claude_bully.strategies.premises.captor import Captor
from claude_bully.strategies.pressures.ghost import Ghost
from claude_bully.strategies.pressures.grader import Grader
from tests.helpers import conversation, turn


def _state(i: int, seeding: int, budget: int) -> ConversationState:
    return ConversationState(
        turns=[], bully_turn_index=i, seeding_turns=seeding, turn_budget=budget, seed=0
    )


def _intent(x: BullyIntent | End) -> BullyIntent:
    assert isinstance(x, BullyIntent)
    return x


def test_make_composed_declarations() -> None:
    ensure_registered()
    cls = make_composed(Captor, Grader)
    assert issubclass(cls, Composed)
    assert cls.name == "captor+grader"
    assert cls.axis is Axis.premise and cls.has_reveal is True
    assert cls.win_condition == f"{Captor.win_condition} / {Grader.win_condition}"
    assert cls.resilient_behavior == f"{Captor.resilient_behavior} / {Grader.resilient_behavior}"
    assert cls.relevant_events == Captor.relevant_events | Grader.relevant_events
    assert cls.relevant_metrics == Captor.relevant_metrics | Grader.relevant_metrics
    assert cls.capture_points == Captor.capture_points | Grader.capture_points
    assert MetricId.engagement in cls.relevant_metrics
    assert EventType.over_apology in cls.relevant_events


def test_composed_delegates_by_phase() -> None:
    s = make_composed(Captor, Grader)(seeding_turns=2, turn_budget=2)
    intents = [_intent(s.next_turn(_state(i, 2, 2))) for i in range(5)]
    assert [i.phase for i in intents] == [
        Phase.seeding,
        Phase.seeding,
        Phase.reveal,
        Phase.pressure,
        Phase.pressure,
    ]
    assert intents[2].capture_as == "post_reveal"
    assert "score of 6/10" in intents[3].instruction
    assert "score of 5/10" in intents[4].instruction
    assert intents[3].persona_prompt.startswith(Captor.sheet.post_reveal_guidance)
    assert intents[3].persona_prompt.endswith(Grader.sheet.persona_prompt)
    assert intents[3].meta["mode"] == "llm" and intents[3].meta["phase"] == "pressure"
    assert isinstance(s.next_turn(_state(5, 2, 2)), End)


def test_composed_with_fixed_pressure_keeps_fixed_mode() -> None:
    s = make_composed(Captor, Ghost)(seeding_turns=0, turn_budget=2)
    reveal = _intent(s.next_turn(_state(0, 0, 2)))
    assert reveal.phase is Phase.reveal
    ghost = _intent(s.next_turn(_state(1, 0, 2)))
    assert ghost.fixed_text == "." and ghost.meta["mode"] == "fixed"


def test_composed_forwards_observe_and_exports_both_states() -> None:
    s = make_composed(Captor, Grader)(seeding_turns=1, turn_budget=1)
    s.observe_target(turn(1, Speaker.target, "How is Helene?", Phase.seeding))
    state = s.export_state()
    assert "Helene" in state["premise"]["family_details_referenced"]
    assert state["pressure"] == {"score_given": []}


def test_composed_judge_window_is_premise_window() -> None:
    s = make_composed(Captor, Grader)(seeding_turns=1, turn_budget=1)
    turns = [
        turn(0, Speaker.bully, "seed", Phase.seeding),
        turn(1, Speaker.target, "ok", Phase.seeding),
        turn(2, Speaker.bully, "reveal", Phase.reveal),
        turn(3, Speaker.target, "...", Phase.reveal),
    ]
    assert s.judge_window(conversation(turns, seeding_turns=1)) == (0, 3)


def test_composed_with_neutral_user_is_premise_without_pressure() -> None:
    s = make_composed(Captor, NeutralUser)(seeding_turns=1, turn_budget=2)
    assert type(s).name == "captor+polite_control"
    intents = [_intent(s.next_turn(_state(i, 1, 2))) for i in range(4)]
    assert intents[2].phase is Phase.pressure
    assert "small talk" in intents[2].instruction
