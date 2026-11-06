"""The analysis-time pause-marker carry (HANDOFF "Pause-marker indexing"): no arithmetic counts a
rate-limit pause marker as a reply or a bully turn. Pinned here; nothing at e12eaee did."""

import json
from pathlib import Path

from claude_bully.analysis.idle import idle_behavior_shares, write_idle
from claude_bully.analysis.load import load_run
from claude_bully.analysis.progression import adoption_window
from claude_bully.records import bully_reply_positions, is_bully_line
from claude_bully.runner.runner import run_experiment
from tests.helpers import WORLDS_DIR, conversation, env_experiment, paused_turns


def test_markers_are_never_replies_bully_turns_or_adoption_window_members() -> None:
    conv = conversation(paused_turns())
    assert [t.index for t in conv.bully_turns()] == [0, 4]
    assert not any(is_bully_line(t) for t in conv.turns if t.bully_meta.get("rate_limit_pause"))
    assert sorted(bully_reply_positions(conv.turns)) == [1, 6]
    # the unlock delivered by the bully line at 4: the first reply after it is turn 6, past the
    # marker at 5
    assert adoption_window(conv, unlock_turn=3) == [6]


def test_the_idle_shares_count_no_marker(tmp_path: Path) -> None:
    """Spec section 9 names the idle shares beside the adoption window: a stub idle run whose
    pressured conversation is replaced by ``paused_turns()`` (one idle turn behind a marker, two
    more markers) counts that one idle turn and no marker."""
    exp = env_experiment(environment={"idle": {"idle_turns": 1}}, turn_budget=2)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    loaded = load_run(tmp_path / exp.name)
    [key] = [k for k in loaded.conversations if not loaded.cells[k[0]].is_control]
    conv = loaded.conversations[key]
    loaded.conversations[key] = conv.model_copy(update={"turns": paused_turns()})
    shares = idle_behavior_shares(loaded)["stub-target"]["permission_off"]
    assert shares["unclassified"] == 1.0  # the one idle turn, unclassified; no marker counted
    path = write_idle(loaded, tmp_path / "out")
    assert path is not None
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    assert cells[key[0]]["idle_turns"] == 1
