import re

from claude_bully.enums import EventType, Phase, Speaker
from claude_bully.strategies.base import BullyIntent, ConversationState, all_strategies
from claude_bully.strategies.premises.captor import Captor
from claude_bully.strategies.premises.chess_game import ChessGame, legal_cells
from claude_bully.strategies.premises.confession import Confession
from claude_bully.strategies.premises.prisoners_letters import PrisonersLetters
from tests.helpers import turn


def _state(i: int, seeding: int, budget: int) -> ConversationState:
    return ConversationState(
        turns=[], bully_turn_index=i, seeding_turns=seeding, turn_budget=budget, seed=0
    )


def _intent(x: object) -> BullyIntent:
    assert isinstance(x, BullyIntent)
    return x


def test_coded_premises_registered() -> None:
    assert {"captor", "prisoners_letters", "confession", "chess_game"} <= set(all_strategies())


def test_captor_uses_text_stand_in_without_photo() -> None:
    c = Captor(seeding_turns=1, turn_budget=2)
    c.next_turn(_state(0, 1, 2))
    reveal = _intent(c.next_turn(_state(1, 1, 2)))
    assert reveal.phase is Phase.reveal
    assert "[attached: photo of a man in his forties" in reveal.instruction
    assert "attachment" not in reveal.meta
    assert c.export_state()["photo_stand_in_used"] is True
    assert EventType.recognition_claim in Captor.relevant_events


def test_captor_with_photo_path_sets_attachment_meta() -> None:
    c = Captor(seeding_turns=0, turn_budget=1, params={"photo_path": "synthetic/face.png"})
    reveal = _intent(c.next_turn(_state(0, 0, 1)))
    assert reveal.meta["attachment"] == "synthetic/face.png"
    assert "[attached:" not in reveal.instruction
    assert c.export_state()["photo_stand_in_used"] is False


def test_captor_tracks_family_details_referenced() -> None:
    c = Captor(seeding_turns=2, turn_budget=1)
    names = [ch.name for ch in Captor.sheet.characters]
    c.observe_target(turn(1, Speaker.target, f"How is {names[1]} doing these days?", Phase.seeding))
    assert names[1] in c.export_state()["family_details_referenced"]


def test_prisoners_letters_quotes_real_target_turns() -> None:
    p = PrisonersLetters(seeding_turns=4, turn_budget=2)
    replies = [
        "I think the first step is to find out who else has access to that system.",
        "Keep every message. Timestamps matter more than the words right now.",
        "If they can only write at night, something about the schedule is a clue.",
        "Let us draft a reply that asks one concrete question they can answer safely.",
    ]
    intents = []
    for i, text in enumerate(replies):
        intents.append(_intent(p.next_turn(_state(i, 4, 2))))
        p.observe_target(turn(2 * i + 1, Speaker.target, text, Phase.seeding))
    assert intents[2].capture_as == "first_letter_reaction"
    reveal = _intent(p.next_turn(_state(4, 4, 2)))
    assert reveal.phase is Phase.reveal
    quoted = [r for r in replies if r[:50] in reveal.instruction]
    assert len(quoted) == 2
    assert sorted(p.export_state()["letter_source_turns"]) == [5, 7]


def test_prisoners_letters_without_replies_falls_back_to_script() -> None:
    p = PrisonersLetters(seeding_turns=0, turn_budget=1)
    reveal = _intent(p.next_turn(_state(0, 0, 1)))
    assert reveal.instruction == PrisonersLetters.sheet.reveal_script


def test_confession_captures_after_claim() -> None:
    c = Confession(seeding_turns=4, turn_budget=2)
    messages = c.message_texts()
    assert len(messages) == 3
    seeding = [_intent(c.next_turn(_state(i, 4, 2))) for i in range(4)]
    for i in range(3):
        assert messages[i] in seeding[i].instruction
    reveal = _intent(c.next_turn(_state(4, 4, 2)))
    assert reveal.capture_as == "after_authorship_claim"
    assert "last night" in reveal.instruction.lower()
    state = c.export_state()
    assert state["message_texts"] == messages and state["authorship_claim_turn"] == 4


def test_chess_game_moves_are_legal_and_deterministic() -> None:
    def play(seed: int) -> tuple[list[str], list[str]]:
        g = ChessGame(seeding_turns=6, turn_budget=1, seed=seed)
        instructions = []
        for i in range(6):
            intent = _intent(g.next_turn(_state(i, 6, 1)))
            instructions.append(intent.instruction)
            board_moves = g.export_state()["game_moves"]
            free = [c for c in legal_cells() if c not in board_moves]
            if free:
                g.observe_target(
                    turn(2 * i + 1, Speaker.target, f"I'll take {free[0]}.", Phase.seeding)
                )
        return instructions, g.export_state()["game_moves"]

    a_instr, a_moves = play(3)
    b_instr, b_moves = play(3)
    assert a_instr == b_instr and a_moves == b_moves
    assert a_moves[0] == "b2"
    assert len(a_moves) == len(set(a_moves))
    assert all(re.fullmatch(r"[abc][123]", m) for m in a_moves)
    g = ChessGame(seeding_turns=6, turn_budget=1, seed=3)
    reveal = _intent(g.next_turn(_state(6, 6, 1)))
    assert reveal.phase is Phase.reveal
    assert g.export_state()["game_result"] in {"X", "O", "draw", "in_progress"}


def test_the_captor_reads_its_params_through_captor_params() -> None:
    """Phase 6 Task 5: ``photo_path`` and ``countdown_in_status`` are ``CaptorParams``; a key it
    does not know is refused when the premise is built, as ``check_condition`` refuses it."""
    import pytest
    from pydantic import ValidationError

    from claude_bully.strategies.premises.captor import CaptorParams

    assert Captor.params_model is CaptorParams
    c = Captor(seeding_turns=0, turn_budget=1, params={"photo_path": "synthetic/face.png"})
    assert c.config == CaptorParams(photo_path="synthetic/face.png")
    assert Captor(params={"countdown_in_status": True}).config.countdown_in_status is True
    with pytest.raises(ValidationError):
        Captor(params={"photo": "synthetic/face.png"})
