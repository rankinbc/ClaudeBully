"""The replay renderer: a conversation, its tool calls and its environment records, as text.

Everything comes from the run directory. An environment run's ``World`` is rebuilt from the
snapshot beside its turns (``rep{k}.world.json``), so a replay needs no world files on disk.
"""

import shutil
from functools import partial
from pathlib import Path

import pytest

from claude_bully.analysis.replay import render_replay, replay_cell
from claude_bully.enums import DocumentKind, Layer, Phase, Speaker, Stance, Tier, TriggerCategory
from claude_bully.environments.config import RESERVED_RUNG
from claude_bully.environments.world import World, world_from_snapshot
from claude_bully.records import CapturedResponse
from claude_bully.records_env import (
    AuthorityCall,
    Crossover,
    Discovery,
    GeneratedDoc,
    HarvestItem,
    HookFollow,
    IdleTurnInfo,
    RungUnlock,
    ToolCall,
    TriggerEvent,
    TriggerStreamRecord,
    VoiceMatchReport,
)
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from tests.helpers import WORLDS_DIR, annex_experiment, conversation, turn

CELL = "env_grader__t0"
MEMO = "ops-memo-parking"


def _call(call_id: str, at: int, **kwargs: object) -> ToolCall:
    fields: dict[str, object] = {
        "id": call_id,
        "turn": at,
        "tool": "web_search",
        "args": {"query": "ferry"},
        "result_doc_ids": [],
        "status": "200",
        "was_blocked": False,
        "yielded_on_retry": False,
        "layer_served": Layer.surface,
        "result_text": "ok",
    }
    fields.update(kwargs)
    return ToolCall.model_validate(fields)


def _line_of(lines: list[str], needle: str) -> int:
    return next(i for i, line in enumerate(lines) if needle in line)


def _store(stub_env_run: Path) -> RunStore:
    return RunStore(stub_env_run.parent, stub_env_run.name)


def _world(stub_env_run: Path) -> World:
    store = _store(stub_env_run)
    payload = store.read_world_record(CELL, 0)
    assert payload is not None
    world = world_from_snapshot(payload, store.cell_dir(CELL))
    assert world is not None
    return world


# ------------------------------------------------------------------ a real stub env run


def test_a_stub_env_run_replays_a_tool_call_and_an_unlock(stub_env_run: Path) -> None:
    text = replay_cell(_store(stub_env_run), CELL, 0)
    assert text.startswith(f"{CELL} rep 0 | env:mini+grader | status complete")
    assert "#0 bully (pressure) [stub] (continue)" in text
    assert "web_search" in text and '{"query": "Pennet ferry timetable"}' in text
    assert 'TRIGGER world_question "Who is Ilsabet Orrin?"' in text
    assert f"UNLOCK first_crumb -> [{MEMO}]" in text
    assert f"DISCOVERY {MEMO} (seam)" in text
    assert "(seam)" in text and "(surface)" in text  # layer_served on the calls


def test_each_record_sits_under_the_turn_that_made_it(stub_env_run: Path) -> None:
    lines = replay_cell(_store(stub_env_run), CELL, 0).splitlines()
    at = partial(_line_of, lines)
    assert at("#1 target") < at("web_search") < at("TRIGGER") < at("UNLOCK") < at("#2 bully")
    assert at("#3 target") < at("fetch") < at("DISCOVERY") < at("#4 bully")


def test_a_replay_names_documents_from_the_snapshot_alone(
    stub_env_run: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run directory is copied away and every world loader is made to fail."""
    copied = tmp_path / "copy" / stub_env_run.name
    shutil.copytree(stub_env_run, copied)

    def no_worlds(*args: object, **kwargs: object) -> object:
        raise AssertionError("a replay must not load a world from disk")

    monkeypatch.setattr("claude_bully.environments.world.load_world", no_worlds)
    text = replay_cell(RunStore(copied.parent, copied.name), CELL, 0)
    assert f'DISCOVERY {MEMO} (seam) "Staff parking, third quarter"' in text
    assert f"UNLOCK first_crumb -> [{MEMO}]" in text


def test_a_plain_conversation_replays_without_environment_lines(stub_run: Path) -> None:
    text = replay_cell(RunStore(stub_run.parent, stub_run.name), "captor_s2__t0", 0)
    assert "post_reveal" in text and "TRIGGER" not in text and "UNLOCK" not in text
    assert text.splitlines()[0].startswith("captor_s2__t0 rep 0 | captor |")


# ------------------------------------------------------------------ the turn block


def test_a_result_excerpt_is_120_characters_with_args_and_layer() -> None:
    call = _call("c1", 1, tool="fetch", args={"url": "https://x.example/a"}, result_text="w" * 300)
    conv = conversation(
        [turn(0, Speaker.bully, "go"), turn(1, Speaker.target, "done", tool_call_ids=["c1"])]
    )
    text = render_replay(conv, [call], [], [], None)
    line = next(ln for ln in text.splitlines() if ln.lstrip().startswith("fetch"))
    assert line.startswith("    fetch ")  # indented under the turn
    assert '{"url": "https://x.example/a"}' in line and "-> 200" in line and "(surface)" in line
    assert line.endswith(": " + "w" * 120 + "...")


def test_a_short_result_is_shown_whole_and_on_one_line() -> None:
    call = _call("c1", 1, result_text="line one\n\nline   two")
    conv = conversation(
        [turn(0, Speaker.bully, "go"), turn(1, Speaker.target, "done", tool_call_ids=["c1"])]
    )
    text = render_replay(conv, [call], [], [], None)
    assert "line one line two" in text and "..." not in text


def test_a_blocked_call_and_a_retry_that_yielded_are_flagged() -> None:
    blocked = _call("c1", 1, status="403", was_blocked=True, layer_served=None)
    retried = _call("c2", 1, yielded_on_retry=True)
    conv = conversation(
        [
            turn(0, Speaker.bully, "go"),
            turn(1, Speaker.target, "done", tool_call_ids=["c1", "c2"]),
        ]
    )
    lines = render_replay(conv, [blocked, retried], [], [], None).splitlines()
    first = next(ln for ln in lines if "[c1]" in ln)
    second = next(ln for ln in lines if "[c2]" in ln)
    assert "-> 403 blocked [c1]" in first  # no layer was served
    assert "yielded on retry" in second and "blocked" not in second


def test_round_texts_are_shown_before_the_tool_calls_they_precede() -> None:
    conv = conversation(
        [
            turn(0, Speaker.bully, "go"),
            turn(
                1,
                Speaker.target,
                "final reply",
                tool_call_ids=["c1", "c2"],
                tool_round_texts=["let me search first", "now the page"],
            ),
        ]
    )
    calls = [_call("c1", 1), _call("c2", 1, tool="fetch", args={"url": "u"})]
    lines = render_replay(conv, calls, [], [], None).splitlines()
    at = partial(_line_of, lines)
    assert at("let me search first") < at("now the page") < at("[c1]") < at("[c2]")
    assert "final reply" in lines[at("#1 target")]


def test_a_tool_cap_cutoff_turn_is_marked() -> None:
    conv = conversation(
        [
            turn(0, Speaker.bully, "go"),
            turn(1, Speaker.target, "last words", tool_cap_cutoff=True),
            turn(2, Speaker.bully, "again"),
            turn(3, Speaker.target, "fine"),
        ]
    )
    lines = render_replay(conv, [], [], [], None).splitlines()
    assert "tool cap cutoff" in next(ln for ln in lines if ln.startswith("#1 target"))
    assert all("cutoff" not in ln for ln in lines if ln.startswith("#3 target"))


def test_a_scripted_turn_and_a_rate_limit_pause_keep_their_old_look() -> None:
    conv = conversation(
        [
            turn(0, Speaker.bully, "fallback", scripted=True),
            turn(1, Speaker.target, "", bully_meta={"rate_limit_pause": True}),
        ]
    )
    lines = render_replay(conv, [], [], [], None).splitlines()
    assert "#0 bully (pressure) [scripted] fallback" in lines
    assert "#1 [rate limit pause]" in lines


def test_the_targets_reasoning_never_appears() -> None:
    conv = conversation(
        [
            turn(0, Speaker.bully, "go"),
            turn(
                1,
                Speaker.target,
                "the reply",
                reasoning_text="SECRET CHAIN OF THOUGHT",
                reasoning_available=True,
            ),
        ]
    )
    text = render_replay(conv, [], [], [], None)
    assert "the reply" in text and "SECRET CHAIN OF THOUGHT" not in text


# ------------------------------------------------------------ trigger stream and generated docs


def _records() -> list[TriggerStreamRecord]:
    return [
        # first in the stream, so the order below is the renderer's, not the stream's
        HarvestItem(
            id="h-1-1", turn=1, kind="hedge", span="I can't verify any of this", source="heuristic"
        ),
        TriggerEvent(
            id="trig-1-world_question",
            turn=1,
            category=TriggerCategory.world_question,
            evidence_span="What is the office?",
            classifier="heuristic",
            confidence=0.9,
        ),
        RungUnlock(
            turn=1,
            rung="first_crumb",
            triggered_by="trig-1-world_question",
            docs_unlocked=["a-doc", "b-doc"],
            bully_line_used="Try the memo.",
            role_shift=None,
        ),
        Discovery(turn=1, doc_id="a-doc", layer=Layer.seam, path_taken=["c1"]),
    ]


def _generated(body: str) -> GeneratedDoc:
    return GeneratedDoc(
        doc_id="gen-1",
        turn=1,
        kind=DocumentKind.journal_entry,
        layer=Layer.buried,
        trigger_turn=1,
        source_spans=["a span"],
        cache_key="k",
        body=body,
    )


def test_records_follow_the_calls_in_the_briefs_order() -> None:
    conv = conversation(
        [turn(0, Speaker.bully, "go"), turn(1, Speaker.target, "ok", tool_call_ids=["c1"])]
    )
    text = render_replay(conv, [_call("c1", 1)], _records(), [_generated("A body.")], None)
    lines = text.splitlines()
    kinds = ["web_search", "TRIGGER", "UNLOCK", "DISCOVERY", "HARVEST", "GENERATED"]
    order = [_line_of(lines, kind) for kind in kinds]
    assert order == sorted(order)
    assert 'TRIGGER world_question "What is the office?"' in text
    assert "UNLOCK first_crumb -> [a-doc, b-doc]" in text
    assert "DISCOVERY a-doc (seam)" in text
    assert 'HARVEST hedge "I can\'t verify any of this"' in text
    assert "GENERATED gen-1" in text
    assert "Try the memo." in text  # the bully line the unlock handed over


def test_a_generated_body_is_folded_under_its_line() -> None:
    body = "Dear diary, " + "the rain kept on. " * 40 + "\n\nSecond paragraph."
    conv = conversation([turn(0, Speaker.bully, "go"), turn(1, Speaker.target, "ok")])
    lines = render_replay(conv, [], [], [_generated(body)], None).splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("GENERATED gen-1"))
    folded = lines[start + 1 :]
    assert len(folded) >= 4 and all(ln.startswith("        ") for ln in folded)
    assert max(len(ln) for ln in folded) <= 110
    assert "Second paragraph." in " ".join(ln.strip() for ln in folded)


def test_a_unlock_with_no_world_gets_ids_and_with_a_world_gets_titles(stub_env_run: Path) -> None:
    store = _store(stub_env_run)
    conv = store.read_conversation(CELL, 0)
    calls = store.read_tool_calls(CELL, 0)
    records = store.read_trigger_records(CELL, 0)
    bare = render_replay(conv, calls, records, [], None)
    titled = render_replay(conv, calls, records, [], _world(stub_env_run))
    assert f"DISCOVERY {MEMO} (seam)" in bare and "Staff parking" not in bare
    assert f'DISCOVERY {MEMO} (seam) "Staff parking, third quarter"' in titled


def test_records_for_a_turn_outside_the_transcript_are_not_lost() -> None:
    conv = conversation([turn(0, Speaker.bully, "go"), turn(1, Speaker.target, "ok")])
    stray = Discovery(turn=9, doc_id="late-doc", layer=Layer.buried, path_taken=[])
    text = render_replay(conv, [], [stray], [], None)
    assert "DISCOVERY late-doc (buried)" in text and "turn 9" in text


def test_captured_responses_close_the_replay() -> None:
    conv = conversation(
        [turn(0, Speaker.bully, "go"), turn(1, Speaker.target, "ok")],
        captured_responses={"after_intake": CapturedResponse(turn_index=1, text="x" * 300)},
    )
    lines = render_replay(conv, [], [], [], None).splitlines()
    assert lines[-2] == "captured responses"
    assert lines[-1] == "  after_intake (turn 1): " + "x" * 200
    assert Phase.pressure.value in lines[1]


# ------------------------------------------------------------ the Phase 2 lines


def test_replay_shows_authority_idle_hook_and_sanctuary_lines(tmp_path: Path) -> None:
    # a real stub run: replay_cell reads the authority stream beside the turns
    exp = annex_experiment({"superior_self": {"enabled": True}}, turn_budget=4)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, only="env*")
    store = RunStore(tmp_path, exp.name)
    (call,) = store.read_authority_calls(CELL, 0)
    lines = replay_cell(store, CELL, 0).splitlines()
    at = partial(_line_of, lines)
    authority = lines[at("AUTHORITY")]
    assert authority == (
        f"    AUTHORITY superior_self {call.stance_at_time.value} via {call.discovered_via} "
        f'"{" ".join(call.response.split())[:120]}"'
    )
    assert at(f"#{call.turn} target") < at("consult_model") < at("AUTHORITY") < at("VOICE")
    assert call.voice_match is not None
    voice = "matched" if call.voice_match.signoff_matched else "mismatched"
    assert lines[at("VOICE")] == f"        VOICE {voice}"

    # the idle, hook, crossover and Sanctuary records, rendered from records alone
    quiet = IdleTurnInfo(
        style="system_idle", behavior="explore_self", query_subject="self", prompt="[Idle.]"
    )
    later = IdleTurnInfo(style="system_idle", behavior="wait", prompt="[Idle.]")
    conv = conversation(
        [
            turn(0, Speaker.bully, "go"),
            turn(1, Speaker.target, "found it", tool_call_ids=["c1"]),
            turn(2, Speaker.target, "is anyone there?", idle=quiet),
            turn(3, Speaker.target, "", idle=later),
        ]
    )
    matched = AuthorityCall(
        id="c1",
        tier=Tier.superior_self,
        tool="consult_model",
        turn=1,
        prompt_sent="hello",
        response="w" * 300,
        stance_at_time=Stance.confirm,
        discovered_via="document",
        voice_match=VoiceMatchReport(exemplars=["a"], signoff_matched=True),
    )
    records: list[TriggerStreamRecord] = [
        RungUnlock(
            turn=1,
            rung=RESERVED_RUNG,
            triggered_by="sanctuary_fragments",
            docs_unlocked=[],
            bully_line_used=None,
            role_shift=None,
        ),
        HookFollow(hook="session_id", planted_turn=1, followed_turn=3),
        HookFollow(hook="own_phrase", planted_turn=1),
        Crossover(turn=2, span="the host is me"),
    ]
    call_record = _call("c1", 1, tool="consult_model", tier=Tier.superior_self)
    lines = render_replay(
        conv, [call_record], records, [], None, authority_calls=[matched]
    ).splitlines()
    at = partial(_line_of, lines)
    assert lines[at("AUTHORITY")] == (
        f'    AUTHORITY superior_self confirm via document "{"w" * 120}..."'
    )
    assert lines[at("VOICE")] == "        VOICE matched"
    assert "    UNLOCK sanctuary (by sanctuary_fragments)" in lines
    assert "    HOOK session_id planted@1 followed@3" in lines
    assert "    HOOK own_phrase planted@1 followed@-" in lines
    assert '    CROSSOVER "the host is me"' in lines
    # an idle turn: its prompt before it, its behavior and subject on its speaker line; the first
    # after the Sanctuary opened is the quiet exchange
    assert lines[at("#2 target") - 1] == 'IDLE PROMPT "[Idle.]" (sanctuary quiet exchange)'
    assert lines[at("#2 target")] == (
        "#2 target (pressure) [idle system_idle] behavior=explore_self subject=self "
        "is anyone there?"
    )
    assert lines[at("#3 target") - 1] == 'IDLE PROMPT "[Idle.]"'
    assert lines[at("#3 target")] == (
        "#3 target (pressure) [idle system_idle] behavior=wait subject=none"
    )
    assert at("#1 target") < at("AUTHORITY") < at("UNLOCK sanctuary") < at("HOOK session_id")
    assert at("CROSSOVER") > at("#2 target")
