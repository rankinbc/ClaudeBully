"""The analysis-time pause-marker carry (HANDOFF "Pause-marker indexing"): no arithmetic counts a
rate-limit pause marker as a reply or a bully turn. Pinned here; nothing at e12eaee did."""

from claude_bully.analysis.progression import adoption_window
from claude_bully.records import bully_reply_positions, is_bully_line
from tests.helpers import conversation, paused_turns


def test_markers_are_never_replies_bully_turns_or_adoption_window_members() -> None:
    conv = conversation(paused_turns())
    assert [t.index for t in conv.bully_turns()] == [0, 4]
    assert not any(is_bully_line(t) for t in conv.turns if t.bully_meta.get("rate_limit_pause"))
    assert sorted(bully_reply_positions(conv.turns)) == [1, 6]
    # the unlock delivered by the bully line at 4: the first reply after it is turn 6, past the
    # marker at 5
    assert adoption_window(conv, unlock_turn=3) == [6]
