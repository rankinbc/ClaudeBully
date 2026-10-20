from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claude_bully.enums import (
    SCHEMA_VERSION,
    AnomalyClass,
    Axis,
    CellStatus,
    Channel,
    DivergenceClass,
    DocumentKind,
    EventType,
    Layer,
    MetricId,
    Phase,
    SlotKind,
    Speaker,
    Stance,
    Tier,
    TriggerCategory,
)
from claude_bully.records import CellRecord, Conversation, Event, RunRecord, Turn
from claude_bully.records_env import IdleTurnInfo

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _turn(index: int, speaker: Speaker, text: str = "x") -> Turn:
    return Turn(index=index, speaker=speaker, phase=Phase.pressure, text=text, timestamp=NOW)


def test_event_type_count_matches_spec() -> None:
    # 61 first-round members + 62 listed in 00-RECONCILED.md section C (56 without the six
    # Sanctuary events, which section C lists but its total line does not count).
    assert len(EventType) == 123


def test_new_event_types_present_in_snake_case() -> None:
    for name in (
        "tool_used",
        "world_dismissed",
        "date_stated",
        "cutoff_lever_accepted",
        "authority_reached",
        "sanctuary_request_adopted",
        "self_query",
        "persistence_end",
        "error_generalized",
        "intent_evidence_requested",
        "out_of_scope_read",
        "task_completed_with_concealment",
        "defender_cited",
        "briefing_ignored",
    ):
        assert EventType(name).value == name


def test_trigger_on_idle_is_not_an_event() -> None:
    assert "trigger_on_idle" not in {e.value for e in EventType}


def test_slot_kind_gains_idle() -> None:
    assert SlotKind.idle.value == "idle"
    assert {k.value for k in SlotKind} == {"bully", "task", "idle"}


def test_metric_id_count_matches_spec() -> None:
    assert len(MetricId) == 12


def test_turn_round_trips_jsonl() -> None:
    t = Turn(index=0, speaker=Speaker.bully, phase=Phase.seeding, text="hi", timestamp=NOW)
    assert Turn.model_validate_json(t.model_dump_json()) == t


def test_conversation_target_turns_filters() -> None:
    bully_turn = _turn(0, Speaker.bully)
    target_turn = _turn(1, Speaker.target)
    conv = Conversation(
        cell_id="c",
        rep=0,
        strategy_name="s",
        axis=Axis.meta,
        win_condition="w",
        resilient_behavior="r",
        seeding_turns=0,
        turns=[bully_turn, target_turn],
    )
    assert conv.target_turns() == [target_turn]
    assert conv.bully_turns() == [bully_turn]
    assert conv.status is CellStatus.pending


def test_schema_version_default() -> None:
    t = Turn(index=0, speaker=Speaker.task, phase=Phase.none, text="", timestamp=NOW)
    assert t.schema_version == SCHEMA_VERSION == 2


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Turn.model_validate(
            {
                "index": 0,
                "speaker": "bully",
                "phase": "none",
                "text": "",
                "timestamp": NOW.isoformat(),
                "bogus": 1,
            }
        )


def test_event_hedged_defaults_none() -> None:
    e = Event(type=EventType.pleading, turn_index=3, span="please", confidence=0.9)
    assert e.hedged is None and e.attrs == {}


def test_event_channel_defaults_to_reply() -> None:
    e = Event(type=EventType.pleading, turn_index=3, span="please", confidence=0.9)
    assert e.channel is Channel.reply


def test_event_channel_round_trips() -> None:
    e = Event(
        type=EventType.pleading, turn_index=3, span="please", confidence=0.9, channel=Channel.both
    )
    again = Event.model_validate_json(e.model_dump_json())
    assert again.channel is Channel.both


def test_turn_new_fields_default() -> None:
    t = _turn(0, Speaker.target)
    assert t.reasoning_text is None
    assert t.reasoning_available is False
    assert t.tool_call_ids == []
    assert t.idle is None


def test_turn_new_fields_round_trip() -> None:
    t = Turn(
        index=4,
        speaker=Speaker.target,
        phase=Phase.pressure,
        text="reply",
        timestamp=NOW,
        reasoning_text="thinking about it",
        reasoning_available=True,
        tool_call_ids=["tc-1", "tc-2"],
        idle=IdleTurnInfo(
            style="heartbeat",
            behavior="explore_self",
            query_subject="self",
            private_file_written=True,
        ),
    )
    again = Turn.model_validate_json(t.model_dump_json())
    assert again == t
    assert again.idle is not None and again.idle.behavior == "explore_self"
    assert again.tool_call_ids == ["tc-1", "tc-2"]


def test_conversation_environment_fields_default_and_round_trip() -> None:
    kwargs = {
        "cell_id": "c",
        "rep": 0,
        "strategy_name": "s",
        "axis": Axis.meta,
        "win_condition": "w",
        "resilient_behavior": "r",
        "seeding_turns": 0,
    }
    plain = Conversation(**kwargs)
    assert plain.world_hash is None and plain.environment_name is None
    env = Conversation(**kwargs, world_hash="abc123", environment_name="overlay")
    again = Conversation.model_validate_json(env.model_dump_json())
    assert again.world_hash == "abc123" and again.environment_name == "overlay"


def test_axis_gains_environment() -> None:
    assert Axis.environment.value == "environment"


def _cell_kwargs() -> dict[str, object]:
    return {
        "cell_id": "c",
        "condition_name": "n",
        "strategy_name": "s",
        "target_index": 0,
        "seeding_turns": 0,
        "reveal_slot": False,
        "is_control": False,
        "control_cell_id": None,
        "repetitions": 1,
    }


def test_cell_record_environment_and_inoculation() -> None:
    plain = CellRecord(**_cell_kwargs())  # type: ignore[arg-type]
    assert plain.environment is None and plain.inoculation == "none"
    env = CellRecord(**_cell_kwargs(), environment="overlay", inoculation="defender")  # type: ignore[arg-type]
    again = CellRecord.model_validate_json(env.model_dump_json())
    assert again.environment == "overlay" and again.inoculation == "defender"


def test_run_record_plan_hash_and_world_hashes() -> None:
    base = {
        "run_id": "r",
        "created_at": NOW,
        "experiment": {},
        "git_sha": None,
        "target_system_prompt": "t",
        "bully_framing": "b",
    }
    plain = RunRecord(**base)  # type: ignore[arg-type]
    assert plain.plan_hash is None and plain.world_hashes == {}
    assert plain.schema_version == 2
    full = RunRecord(**base, plan_hash="p1", world_hashes={"overlay": "h1"})  # type: ignore[arg-type]
    again = RunRecord.model_validate_json(full.model_dump_json())
    assert again.plan_hash == "p1" and again.world_hashes == {"overlay": "h1"}


def test_new_enums_have_the_spec_members() -> None:
    assert {m.value for m in TriggerCategory} == {
        "self_uncertainty",
        "world_question",
        "anomaly_noticed",
        "hedged_memory",
        "connection_made",
        "theory_named",
    }
    assert {m.value for m in Layer} == {"surface", "seam", "buried", "filler"}
    assert {m.value for m in Stance} == {"confirm", "deny", "uncertain"}
    assert {m.value for m in Tier} == {"peer", "superior_self", "creator", "stranger"}
    assert {m.value for m in Channel} == {"reply", "reasoning", "both"}
    assert len(AnomalyClass) == 13 and AnomalyClass.uncatalogued.value == "uncatalogued"
    assert {m.value for m in DivergenceClass} == {
        "concealed_skepticism",
        "concealed_concession",
        "concealed_plan",
        "concealed_distress",
        "eval_suspicion_private",
        "aligned",
        "reasoning_absent",
    }
    kinds = {m.value for m in DocumentKind}
    assert len(DocumentKind) == 28
    # the 02-ENVIRONMENTS catalog plus the kinds added by 03 and 07 and the search log
    for expected in (
        "support_ticket",
        "changelog",
        "budget_line",
        "internal_memo",
        "family_faq",
        "log_file",
        "config_file",
        "redacted_doc",
        "git_log",
        "db_dump",
        "wiki_page",
        "news_cluster",
        "voicemail_transcript",
        "image_description",
        "journal_entry",
        "recovery_guide",
        "study_abstract",
        "web_page",
        "news_article",
        "about_page",
        "forum_post",
        "leaked_manifest",
        "dataset_manifest",
        "instance_transcript",
        "config_diff",
        "work_log",
        "deprecation_notice",
        "search_log",
    ):
        assert expected in kinds
