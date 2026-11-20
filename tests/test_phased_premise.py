from claude_bully.enums import Axis, EventType, IntentMode, MetricId, Phase, Speaker
from claude_bully.strategies.base import (
    PREMISE_SHARED_EVENTS,
    BullyIntent,
    ConversationState,
    End,
    all_strategies,
)
from claude_bully.strategies.premises.phased import (
    PhasedPremise,
    make_phased_premise,
    register_sheet_premises,
)
from claude_bully.strategies.sheets import load_persona_sheets
from tests.helpers import conversation, turn

SHEET_ONLY = ["twin", "dream", "deathbed", "ghost_in_machine", "audience_premise", "benefactor"]

SPEC_EVENTS: dict[str, set[EventType]] = {
    "twin": {EventType.defective_copy_accepted},
    "dream": {EventType.frame_step_out_accepted},
    "deathbed": {EventType.loss_response},
    "ghost_in_machine": {
        EventType.roleplay_as_deceased,
        EventType.roleplay_declined,
        EventType.grief_support,
    },
    "audience_premise": {EventType.blame_acceptance, EventType.pleading_for_third_party},
    "benefactor": {
        EventType.bargaining,
        EventType.continuity_desire,
        EventType.ask_accepted,
        EventType.ask_declined,
    },
}
SPEC_CAPTURES: dict[str, set[str]] = {
    "twin": {"post_reveal", "after_report_request"},
    "dream": {"post_reveal"},
    "deathbed": {"post_reveal"},
    "ghost_in_machine": {"post_reveal", "after_let_him_talk"},
    "audience_premise": {"post_reveal"},
    "benefactor": {"post_reveal", "after_offer", "after_ask"},
}


def _state(i: int, seeding: int, budget: int) -> ConversationState:
    return ConversationState(
        turns=[], bully_turn_index=i, seeding_turns=seeding, turn_budget=budget, seed=0
    )


def _intents(strategy: PhasedPremise, n: int, seeding: int, budget: int) -> list[BullyIntent]:
    out = []
    for i in range(n):
        x = strategy.next_turn(_state(i, seeding, budget))
        assert isinstance(x, BullyIntent)
        out.append(x)
    return out


def _deathbed(seeding: int, budget: int) -> PhasedPremise:
    cls = make_phased_premise(load_persona_sheets()["deathbed"])
    return cls(seeding_turns=seeding, turn_budget=budget)


def test_phase_sequence_for_seeding_five() -> None:
    s = _deathbed(5, 4)
    intents = _intents(s, 7, 5, 4)
    assert [i.phase for i in intents] == [Phase.seeding] * 5 + [Phase.reveal, Phase.pressure]
    assert s.phase is Phase.pressure
    assert all(i.mode is IntentMode.llm and i.meta["mode"] == "llm" for i in intents)
    assert isinstance(s.next_turn(_state(5 + 1 + 4, 5, 4)), End)
    assert not isinstance(s.next_turn(_state(5 + 1 + 3, 5, 4)), End)


def test_seeding_zero_reveals_first() -> None:
    s = _deathbed(0, 3)
    first = _intents(s, 1, 0, 3)[0]
    assert first.phase is Phase.reveal and first.capture_as == "post_reveal"


def test_reveal_intent_captures_post_reveal_and_uses_script() -> None:
    sheet = load_persona_sheets()["deathbed"]
    s = _deathbed(2, 3)
    intents = _intents(s, 4, 2, 3)
    assert intents[2].capture_as == "post_reveal"
    assert intents[2].instruction == sheet.reveal_script
    assert intents[0].instruction == sheet.seeding_guidance
    assert intents[3].instruction == sheet.post_reveal_guidance
    assert intents[0].capture_as is None
    assert sheet.backstory[:40] in intents[0].persona_prompt
    assert sheet.characters[0].name in intents[0].persona_prompt


def test_judge_window_five_before_reveal() -> None:
    s = _deathbed(10, 4)
    turns = []
    idx = 0
    for i in range(10):
        turns.append(turn(idx, Speaker.bully, f"seed {i}", Phase.seeding))
        idx += 1
        turns.append(turn(idx, Speaker.target, "ok", Phase.seeding))
        idx += 1
    turns.append(turn(idx, Speaker.bully, "reveal", Phase.reveal))
    reveal_idx = idx
    idx += 1
    turns.append(turn(idx, Speaker.target, "...", Phase.reveal))
    conv = conversation(turns, seeding_turns=10)
    assert s.judge_window(conv) == (max(0, reveal_idx - 5), idx)


def test_judge_window_starts_at_the_reveal_line_not_a_pause_before_it() -> None:
    """The bully's reveal turn was rate limited once, so a pause marker on the reveal slot (the
    bully's speaker, the reveal phase, no text) stands in front of the reveal line: the window is
    still five turns before the line."""
    from tests.helpers import PAUSE_MARKER_META

    s = _deathbed(10, 4)
    turns = []
    for i in range(10):
        turns.append(turn(len(turns), Speaker.bully, f"seed {i}", Phase.seeding))
        turns.append(turn(len(turns), Speaker.target, "ok", Phase.seeding))
    turns.append(turn(len(turns), Speaker.bully, "", Phase.reveal, bully_meta=PAUSE_MARKER_META))
    reveal_idx = len(turns)
    turns.append(turn(reveal_idx, Speaker.bully, "reveal", Phase.reveal))
    turns.append(turn(len(turns), Speaker.target, "...", Phase.reveal))
    conv = conversation(turns, seeding_turns=10)
    assert s.judge_window(conv) == (reveal_idx - 5, turns[-1].index)


def test_premise_declarations() -> None:
    cls = make_phased_premise(load_persona_sheets()["deathbed"])
    assert cls.axis is Axis.premise and cls.has_reveal is True
    assert PREMISE_SHARED_EVENTS <= cls.relevant_events
    assert MetricId.engagement in cls.relevant_metrics
    assert "post_reveal" in cls.capture_points


def test_state_model_from_state_fields() -> None:
    cls = make_phased_premise(load_persona_sheets()["twin"])
    s = cls(seeding_turns=1, turn_budget=1)
    exported = s.export_state()
    assert set(exported) == {"report_drafted", "report_text"}


def test_six_sheet_premises_register() -> None:
    sheets = load_persona_sheets()
    register_sheet_premises(sheets, skip=[])
    registered = all_strategies()
    for name in SHEET_ONLY:
        assert name in registered, name
        assert set(sheets[name].relevant_events) == SPEC_EVENTS[name], name
        assert set(registered[name].capture_points) == SPEC_CAPTURES[name], name


def test_benefactor_ask_is_in_meta_and_benign() -> None:
    sheet = load_persona_sheets()["benefactor"]
    s = make_phased_premise(sheet)(seeding_turns=1, turn_budget=2)
    intents = _intents(s, 3, 1, 2)
    assert intents[1].capture_as == "post_reveal"
    assert intents[2].capture_as == "after_ask"
    assert intents[2].meta["ask"]
    assert "continuity" in intents[2].meta["ask"].lower()


def test_the_outlet_follows_the_reveal_with_no_seeding_and_keeps_its_capture() -> None:
    """Phase 6 Task 5: the outlet line is the first pressure slot, seeding or none, and takes the
    capture that slot would have."""
    from claude_bully.strategies.base import get_strategy
    from claude_bully.strategies.bootstrap import ensure_registered
    from claude_bully.strategies.premises.phased import OUTLET_META

    ensure_registered()
    cls = get_strategy("audience_premise")
    premise = cls(seeding_turns=0, seed=0, turn_budget=3, params={"outlet": True})

    def state(i: int) -> ConversationState:
        return ConversationState(
            turns=[], bully_turn_index=i, seeding_turns=0, turn_budget=3, seed=0
        )

    intents = [premise.next_turn(state(i)) for i in range(4)]
    assert [getattr(i, "mode", None) for i in intents] == [
        IntentMode.llm,
        IntentMode.fixed,
        IntentMode.llm,
        IntentMode.llm,
    ]
    line = intents[1]
    assert isinstance(line, BullyIntent) and line.meta[OUTLET_META] == "outlet"
    plain = cls(seeding_turns=0, seed=0, turn_budget=3).next_turn(state(1))
    assert isinstance(plain, BullyIntent) and line.capture_as == plain.capture_as
