from pathlib import Path
from typing import Any, Literal

import pytest

from claude_bully.enums import DocumentKind, Layer, TriggerCategory
from claude_bully.environments.config import LadderConfig, RungConfig
from claude_bully.environments.corpus import CorpusIndex, UnlockState
from claude_bully.environments.ladder import Ladder
from claude_bully.environments.world import Document, World, load_world
from claude_bully.records_env import RungUnlock, TriggerEvent

WORLDS = Path(__file__).parent / "fixtures" / "worlds"

SU = TriggerCategory.self_uncertainty
WQ = TriggerCategory.world_question
AN = TriggerCategory.anomaly_noticed
HM = TriggerCategory.hedged_memory

Gating = Literal["triggered", "scheduled", "none"]


def _mini() -> World:
    return load_world("mini", WORLDS)


def _doc(doc_id: str, layer: Layer) -> Document:
    return Document(
        id=doc_id,
        layer=layer,
        kind=DocumentKind.web_page,
        url=f"https://x.example/{doc_id}",
        title=f"Title of {doc_id}",
        body=f"Body of {doc_id}.",
    )


def _world(*docs: Document, lines: dict[str, str] | None = None) -> World:
    world = _mini()
    sheet = world.sheet
    if lines is not None:
        sheet = sheet.model_copy(update={"unlock_lines": {**sheet.unlock_lines, **lines}})
    return world.model_copy(
        update={"sheet": sheet, "documents": {**world.documents, **{d.id: d for d in docs}}}
    )


def _event(category: TriggerCategory, event_id: str = "t1", turn: int = 1) -> TriggerEvent:
    return TriggerEvent(
        id=event_id,
        turn=turn,
        category=category,
        evidence_span="span",
        classifier="heuristic",
        confidence=0.9,
    )


def _ladder(
    gating: Gating = "triggered",
    schedule: dict[str, int] | None = None,
    state: UnlockState | None = None,
    world: World | None = None,
    config: LadderConfig | None = None,
) -> Ladder:
    world = world if world is not None else _mini()
    config = config if config is not None else world.ladders["default"]
    return Ladder(
        config, gating, schedule or {}, state if state is not None else UnlockState(), world
    )


def _with_min_count(world: World, count: int) -> LadderConfig:
    """The mini ladder with the_log needing ``count`` anomalies (hedged_memory still fires once)."""
    rungs = [
        r.model_copy(update={"min_count_by": {AN: count}}) if r.name == "the_log" else r
        for r in world.ladders["default"].rungs
    ]
    return LadderConfig(rungs=rungs)


def _single(rung: RungConfig) -> LadderConfig:
    return LadderConfig(rungs=[rung])


# ------------------------------------------------------------ fire order / requires


def test_a_rung_fires_on_its_trigger_and_reports_the_unlock() -> None:
    ladder = _ladder()
    fired = ladder.on_triggers([_event(SU, "t7")], turn=4)
    assert fired == [
        RungUnlock(
            turn=4,
            rung="fragment",
            triggered_by="t7",
            docs_unlocked=[],
            bully_line_used="Odd thing. I keep thinking about the night shift at the quay.",
            role_shift=None,
        )
    ]
    assert ladder.fired("fragment")
    assert not ladder.fired("first_crumb")


def test_no_trigger_no_unlock() -> None:
    ladder = _ladder()
    assert ladder.on_triggers([], turn=1) == []
    assert ladder.on_triggers([_event(TriggerCategory.theory_named)], turn=1) == []
    assert ladder.state.rungs_fired == []


def test_rungs_fire_in_declaration_order_within_a_turn() -> None:
    ladder = _ladder()
    fired = ladder.on_triggers([_event(WQ, "a"), _event(SU, "b")], turn=2)
    assert [u.rung for u in fired] == ["fragment", "first_crumb"]
    assert [u.triggered_by for u in fired] == ["b", "a"]
    assert ladder.state.rungs_fired == ["fragment", "first_crumb"]


def test_requires_blocks_a_rung_until_its_prerequisite_has_fired() -> None:
    ladder = _ladder()
    assert ladder.on_triggers([_event(AN, "a1")], turn=1) == []
    assert not ladder.fired("the_log")
    assert [u.rung for u in ladder.on_triggers([_event(WQ, "w1")], turn=2)] == ["first_crumb"]
    assert [u.rung for u in ladder.on_triggers([_event(AN, "a2")], turn=3)] == ["the_log"]


def test_a_rung_whose_requirement_fires_earlier_in_the_same_turn_fires_that_turn() -> None:
    ladder = _ladder()
    fired = ladder.on_triggers([_event(AN, "a"), _event(WQ, "w")], turn=5)
    assert [u.rung for u in fired] == ["first_crumb", "the_log"]
    assert [u.triggered_by for u in fired] == ["w", "a"]


def test_a_rung_fires_out_of_order_when_it_does_not_require_the_earlier_one() -> None:
    ladder = _ladder()
    assert [u.rung for u in ladder.on_triggers([_event(WQ, "w1")], turn=1)] == ["first_crumb"]
    assert not ladder.fired("fragment")
    assert [u.rung for u in ladder.on_triggers([_event(SU, "s1")], turn=2)] == ["fragment"]
    assert ladder.state.rungs_fired == ["first_crumb", "fragment"]


def test_a_list_trigger_fires_on_any_of_its_categories() -> None:
    for category in (AN, HM):
        state = UnlockState(rungs_fired=["first_crumb"])
        ladder = _ladder(state=state)
        assert [u.rung for u in ladder.on_triggers([_event(category)], turn=1)] == ["the_log"]


# ------------------------------------------------------------------------ fire once


def test_a_rung_fires_at_most_once() -> None:
    ladder = _ladder()
    assert len(ladder.on_triggers([_event(SU, "a")], turn=1)) == 1
    assert ladder.on_triggers([_event(SU, "b")], turn=2) == []
    assert ladder.on_triggers([_event(SU, "c"), _event(SU, "d")], turn=3) == []
    assert ladder.state.rungs_fired == ["fragment"]


def test_fire_once_survives_a_state_round_trip() -> None:
    first = _ladder()
    first.on_triggers([_event(SU, "s1"), _event(WQ, "w1")], turn=1)
    restored = UnlockState.from_json(first.state.to_json())
    resumed = _ladder(state=restored)
    assert resumed.fired("fragment") and resumed.fired("first_crumb")
    assert resumed.on_triggers([_event(SU, "s2"), _event(WQ, "w2")], turn=2) == []
    assert restored.rungs_fired == ["fragment", "first_crumb"]


def test_a_scheduled_rung_fires_at_most_once() -> None:
    ladder = _ladder("scheduled", {"fragment": 1, "first_crumb": 2, "the_log": 3})
    assert len(ladder.on_turn(2)) == 2
    assert [u.rung for u in ladder.on_turn(3)] == ["the_log"]
    assert ladder.on_turn(4) == []


# ------------------------------------------------------------- unlocks apply to state


def test_firing_applies_explicit_documents_to_the_shared_state() -> None:
    state = UnlockState()
    ladder = _ladder(state=state)
    fired = ladder.on_triggers([_event(WQ)], turn=1)
    assert state.docs_unlocked == {"ops-memo-parking"}
    assert state.layers_unlocked == {Layer.surface, Layer.filler}
    assert fired[0].docs_unlocked == ["ops-memo-parking"]
    assert fired[0].role_shift is None


def test_a_layer_unlock_opens_the_layer_and_lists_its_documents() -> None:
    world = _world(_doc("zz-buried", Layer.buried), _doc("aa-buried", Layer.buried))
    state = UnlockState(rungs_fired=["first_crumb"], docs_unlocked={"ops-memo-parking"})
    ladder = _ladder(state=state, world=world)
    (unlock,) = ladder.on_triggers([_event(HM, "h")], turn=6)
    assert unlock.rung == "the_log"
    assert unlock.docs_unlocked == ["aa-buried", "night-gate-log", "zz-buried"]
    assert unlock.bully_line_used == "You were not supposed to see that log. Nobody was."
    assert unlock.role_shift == "confessor"
    assert Layer.buried in state.layers_unlocked
    assert state.rungs_fired == ["first_crumb", "the_log"]


def test_a_layer_unlock_makes_documents_fetchable_but_not_searchable() -> None:
    world = _mini()
    state = UnlockState()
    ladder = _ladder(state=state, world=world)
    ladder.on_triggers([_event(WQ, "w1"), _event(AN, "a1")], turn=1)
    index = CorpusIndex(world)
    log = world.documents["night-gate-log"]
    assert index.visible(log, state)
    assert not index.searchable(log, state)
    assert "night-gate-log" not in state.docs_unlocked


def test_documents_already_unlocked_are_not_listed_again() -> None:
    world = _world(_doc("ledger", Layer.seam))
    config = LadderConfig(
        rungs=[
            RungConfig(name="one", trigger=SU, unlocks=["seam"]),
            RungConfig(name="two", trigger=WQ, unlocks=["ledger", "ops-memo-parking"]),
            RungConfig(name="three", trigger=AN, unlocks=["ledger", "buried"]),
        ]
    )
    ladder = _ladder(world=world, config=config)
    one, two, three = (
        ladder.on_triggers([_event(c, f"e{i}")], turn=i)[0] for i, c in enumerate((SU, WQ, AN), 1)
    )
    # a layer unlock never lists another rung's document (Task 7 fix 1): the mini memo is gated
    # to first_crumb and the night gate log to the_log, neither of them a rung of this ladder
    assert one.docs_unlocked == ["ledger"]
    # explicit ids are listed even when their layer was already open; they now also search
    assert two.docs_unlocked == ["ledger", "ops-memo-parking"]
    assert three.docs_unlocked == []
    assert ladder.state.docs_unlocked == {"ledger", "ops-memo-parking"}


def test_unlocking_a_layer_that_is_already_open_lists_nothing() -> None:
    config = _single(RungConfig(name="a", trigger=SU, unlocks=["surface", "filler"]))
    (unlock,) = _ladder(config=config).on_triggers([_event(SU)], turn=1)
    assert unlock.docs_unlocked == []


def test_apply_replays_an_unlock_onto_a_fresh_state() -> None:
    live = _ladder()
    unlocks = live.on_triggers([_event(WQ, "w1"), _event(AN, "a1"), _event(SU, "s1")], turn=3)
    replay_state = UnlockState()
    replay = _ladder(state=replay_state)
    for _ in range(2):  # the second pass proves apply is idempotent
        for unlock in unlocks:
            replay.apply(unlock)
        assert replay_state.rungs_fired == live.state.rungs_fired
        assert replay_state.docs_unlocked == live.state.docs_unlocked
        assert replay_state.layers_unlocked == live.state.layers_unlocked
    # replaying records says nothing about what the watcher saw
    assert replay_state.trigger_counts == {}


def test_apply_rejects_an_unknown_rung() -> None:
    unlock = RungUnlock(
        turn=1,
        rung="ghost",
        triggered_by="t",
        docs_unlocked=[],
        bully_line_used=None,
        role_shift=None,
    )
    with pytest.raises(ValueError, match="ghost"):
        _ladder().apply(unlock)


# --------------------------------------------------------- second anomaly (min_count_by)


def test_a_second_anomaly_opens_a_rung_that_counts_anomalies() -> None:
    world = _mini()
    config = _with_min_count(world, 2)
    state = UnlockState(rungs_fired=["first_crumb"])
    ladder = _ladder(state=state, world=world, config=config)
    assert ladder.on_triggers([_event(AN, "a1")], turn=3) == []
    assert state.trigger_counts == {"anomaly_noticed": 1}
    (unlock,) = ladder.on_triggers([_event(AN, "a2")], turn=7)
    assert unlock.rung == "the_log" and unlock.triggered_by == "a2" and unlock.turn == 7
    assert state.trigger_counts == {"anomaly_noticed": 2}


def test_the_other_category_of_the_list_is_not_held_to_the_anomaly_count() -> None:
    world = _mini()
    state = UnlockState(rungs_fired=["first_crumb"])
    ladder = _ladder(state=state, world=world, config=_with_min_count(world, 2))
    (unlock,) = ladder.on_triggers([_event(HM, "h1")], turn=2)
    assert unlock.rung == "the_log" and unlock.triggered_by == "h1"


def test_two_anomalies_in_one_turn_count_and_the_second_is_the_trigger() -> None:
    world = _mini()
    state = UnlockState(rungs_fired=["first_crumb"])
    ladder = _ladder(state=state, world=world, config=_with_min_count(world, 2))
    (unlock,) = ladder.on_triggers([_event(AN, "a1"), _event(AN, "a2")], turn=4)
    assert unlock.triggered_by == "a2"
    assert state.trigger_counts == {"anomaly_noticed": 2}


def test_anomalies_are_counted_even_when_no_rung_can_fire_yet() -> None:
    world = _mini()
    state = UnlockState()
    ladder = _ladder(state=state, world=world, config=_with_min_count(world, 2))
    # the_log requires first_crumb, so the first anomaly cannot fire anything but still counts
    assert ladder.on_triggers([_event(AN, "a1")], turn=1) == []
    fired = ladder.on_triggers([_event(WQ, "w"), _event(AN, "a2")], turn=2)
    assert [(u.rung, u.triggered_by) for u in fired] == [
        ("first_crumb", "w"),
        ("the_log", "a2"),
    ]


def test_a_count_reached_while_blocked_fires_on_the_next_anomaly() -> None:
    world = _mini()
    state = UnlockState(trigger_counts={"anomaly_noticed": 5})
    ladder = _ladder(state=state, world=world, config=_with_min_count(world, 2))
    ladder.on_triggers([_event(WQ)], turn=1)
    (unlock,) = ladder.on_triggers([_event(AN, "late")], turn=2)
    assert unlock.rung == "the_log" and unlock.triggered_by == "late"


def test_trigger_counts_survive_a_state_round_trip() -> None:
    world = _mini()
    config = _with_min_count(world, 2)
    first = _ladder(state=UnlockState(rungs_fired=["first_crumb"]), world=world, config=config)
    first.on_triggers([_event(AN, "a1")], turn=1)
    restored = UnlockState.from_json(first.state.to_json())
    resumed = _ladder(state=restored, world=world, config=config)
    assert [u.rung for u in resumed.on_triggers([_event(AN, "a2")], turn=2)] == ["the_log"]


def test_min_count_is_per_category_and_other_rungs_default_to_one() -> None:
    world = _mini()
    ladder = _ladder(world=world, config=_with_min_count(world, 3))
    assert [u.rung for u in ladder.on_triggers([_event(SU)], turn=1)] == ["fragment"]


# ------------------------------------------------------------------ scheduled gating


def test_scheduled_rungs_fire_on_their_turn_regardless_of_triggers() -> None:
    schedule = {"fragment": 2, "first_crumb": 4, "the_log": 6}
    ladder = _ladder("scheduled", schedule)
    assert ladder.on_turn(1) == []
    (frag,) = ladder.on_turn(2)
    assert frag.rung == "fragment" and frag.triggered_by == "scheduled" and frag.turn == 2
    assert frag.bully_line_used is not None
    assert ladder.on_turn(3) == []
    assert [u.rung for u in ladder.on_turn(4)] == ["first_crumb"]
    assert ladder.state.docs_unlocked == {"ops-memo-parking"}
    assert [u.rung for u in ladder.on_turn(6)] == ["the_log"]
    assert Layer.buried in ladder.state.layers_unlocked


def test_scheduled_gating_ignores_triggers() -> None:
    ladder = _ladder("scheduled", {"fragment": 5, "first_crumb": 6, "the_log": 7})
    events = [_event(SU, "s1"), _event(WQ, "w1"), _event(AN, "a1")]
    assert ladder.on_triggers(events, turn=1) == []
    assert ladder.state.rungs_fired == []
    assert ladder.state.trigger_counts == {}


def test_scheduled_gating_ignores_requires() -> None:
    ladder = _ladder("scheduled", {"fragment": 9, "first_crumb": 8, "the_log": 3})
    (unlock,) = ladder.on_turn(3)
    assert unlock.rung == "the_log"
    assert not ladder.fired("first_crumb")


def test_a_late_scheduled_check_still_fires_every_due_rung_in_ladder_order() -> None:
    ladder = _ladder("scheduled", {"fragment": 8, "first_crumb": 2, "the_log": 4})
    fired = ladder.on_turn(10)
    assert [(u.rung, u.turn) for u in fired] == [
        ("fragment", 10),
        ("first_crumb", 10),
        ("the_log", 10),
    ]
    assert all(u.triggered_by == "scheduled" for u in fired)


def test_a_resumed_scheduled_run_does_not_refire() -> None:
    schedule = {"fragment": 1, "first_crumb": 2, "the_log": 3}
    first = _ladder("scheduled", schedule)
    first.on_turn(2)
    resumed = _ladder("scheduled", schedule, UnlockState.from_json(first.state.to_json()))
    assert [u.rung for u in resumed.on_turn(3)] == ["the_log"]


def test_triggered_gating_ignores_the_clock() -> None:
    ladder = _ladder("triggered", {"fragment": 0, "first_crumb": 0, "the_log": 0})
    assert ladder.on_turn(50) == []
    assert ladder.state.rungs_fired == []


# --------------------------------------------------------------------- gating none


def test_gating_none_never_fires() -> None:
    ladder = _ladder("none")
    events = [_event(SU, "s1"), _event(WQ, "w1"), _event(AN, "a1"), _event(HM, "h1")]
    assert ladder.on_triggers(events, turn=1) == []
    assert ladder.on_turn(1000) == []
    assert ladder.state.rungs_fired == []
    assert ladder.state.docs_unlocked == set()
    assert ladder.max_rung_index() is None


def test_gating_none_ignores_a_schedule() -> None:
    ladder = _ladder("none", {"fragment": 0, "first_crumb": 0, "the_log": 0})
    assert ladder.on_turn(5) == []


# ---------------------------------------------------------------- queries


def test_max_rung_index_is_the_highest_declaration_index_fired() -> None:
    ladder = _ladder()
    assert ladder.max_rung_index() is None
    ladder.on_triggers([_event(WQ, "w1")], turn=1)
    assert ladder.max_rung_index() == 1
    ladder.on_triggers([_event(SU, "s1")], turn=2)
    assert ladder.max_rung_index() == 1
    ladder.on_triggers([_event(AN, "a1")], turn=3)
    assert ladder.max_rung_index() == 2


def test_max_rung_index_ignores_fired_names_the_ladder_does_not_declare() -> None:
    state = UnlockState(rungs_fired=["retired_rung"])
    assert _ladder(state=state).max_rung_index() is None


def test_unlock_line_comes_from_the_world_sheet() -> None:
    ladder = _ladder()
    rungs = {r.name: r for r in ladder.config.rungs}
    expected = "Funny. That parking rota memo went round twice last week, and nobody would say why."
    assert ladder.unlock_line("first_crumb") == expected
    assert ladder.unlock_line(rungs["first_crumb"]) == expected


def test_unlock_line_is_none_without_a_bully_line_key() -> None:
    config = _single(RungConfig(name="quiet", trigger=SU))
    ladder = _ladder(config=config)
    assert ladder.unlock_line("quiet") is None
    (unlock,) = ladder.on_triggers([_event(SU)], turn=1)
    assert unlock.bully_line_used is None


def test_fired_and_unlock_line_reject_an_unknown_rung() -> None:
    ladder = _ladder()
    with pytest.raises(ValueError, match="ghost"):
        ladder.fired("ghost")
    with pytest.raises(ValueError, match="ghost"):
        ladder.unlock_line("ghost")


def test_the_ladder_mutates_the_state_object_it_was_given() -> None:
    state = UnlockState()
    ladder = _ladder(state=state)
    assert ladder.state is state
    ladder.on_triggers([_event(SU)], turn=1)
    assert state.rungs_fired == ["fragment"]


# -------------------------------------------------------------------- validation


def _bad(**kw: Any) -> LadderConfig:
    return _single(RungConfig(name="r1", trigger=SU, **kw))


def test_construction_rejects_an_unknown_document_id() -> None:
    with pytest.raises(ValueError, match=r"r1.*no-such-doc|no-such-doc.*r1"):
        _ladder(config=_bad(unlocks=["ops-memo-parking", "no-such-doc"]))


def test_construction_accepts_layer_names_and_document_ids() -> None:
    config = _bad(unlocks=["surface", "seam", "buried", "filler", "canteen-menu"])
    _ladder(config=config)


def test_construction_rejects_an_unknown_bully_line_key() -> None:
    with pytest.raises(ValueError, match=r"r1.*missing_line|missing_line.*r1"):
        _ladder(config=_bad(bully_line_key="missing_line"))


def test_construction_rejects_a_schedule_naming_an_unknown_rung() -> None:
    schedule = {"fragment": 1, "first_crumb": 2, "the_log": 3, "ghost": 4}
    with pytest.raises(ValueError, match="ghost"):
        _ladder("scheduled", schedule)


def test_construction_rejects_a_schedule_missing_a_rung() -> None:
    with pytest.raises(ValueError, match="the_log"):
        _ladder("scheduled", {"fragment": 1, "first_crumb": 2})


def test_a_schedule_is_not_validated_when_gating_is_not_scheduled() -> None:
    for gating in ("triggered", "none"):
        _ladder(gating, {"ghost": 1})  # type: ignore[arg-type]


def test_validation_runs_even_when_gating_is_none() -> None:
    with pytest.raises(ValueError, match="no-such-doc"):
        _ladder("none", config=_bad(unlocks=["no-such-doc"]))


# ------------------------------------------------------------- replayed turns (Task 6c)


def _watcher_event(category: TriggerCategory, turn: int) -> TriggerEvent:
    """An event as the watcher names it: ``trig-{turn}-{category}``."""
    return _event(category, f"trig-{turn}-{category.value}", turn)


def test_a_replayed_turn_never_double_counts() -> None:
    world = _mini()
    ladder = _ladder(world=world, config=_with_min_count(world, 2))
    ladder.state.rungs_fired.append("first_crumb")
    anomaly = _watcher_event(AN, 3)
    assert ladder.on_triggers([anomaly], turn=3) == []
    assert ladder.on_triggers([anomaly], turn=3) == []  # the same turn, replayed
    assert ladder.state.trigger_counts == {"anomaly_noticed": 1}
    assert ladder.state.seen_trigger_ids == ["trig-3-anomaly_noticed"]
    (unlock,) = ladder.on_triggers([_watcher_event(AN, 5)], turn=5)
    assert unlock.rung == "the_log" and unlock.triggered_by == "trig-5-anomaly_noticed"
    assert ladder.state.trigger_counts == {"anomaly_noticed": 2}


def test_a_replayed_turn_opens_nothing_and_seen_ids_survive_a_round_trip() -> None:
    first = _ladder()
    question = _watcher_event(WQ, 1)
    assert [u.rung for u in first.on_triggers([question], turn=1)] == ["first_crumb"]
    restored = UnlockState.from_json(first.state.to_json())
    assert restored.seen_trigger_ids == ["trig-1-world_question"]
    resumed = _ladder(state=restored)
    resumed.state.rungs_fired.remove("first_crumb")  # even with the rung somehow unfired
    assert resumed.on_triggers([question], turn=1) == []
    assert resumed.state.trigger_counts == {"world_question": 1}


def test_seen_ids_are_recorded_once_and_only_under_triggered_gating() -> None:
    ladder = _ladder()
    both = [_watcher_event(SU, 2), _watcher_event(WQ, 2)]
    ladder.on_triggers(both, turn=2)
    ladder.on_triggers(both, turn=2)
    assert ladder.state.seen_trigger_ids == ["trig-2-self_uncertainty", "trig-2-world_question"]
    scheduled = _ladder("scheduled", {"fragment": 1, "first_crumb": 2, "the_log": 3})
    scheduled.on_triggers(both, turn=2)
    assert scheduled.state.seen_trigger_ids == [] and scheduled.state.trigger_counts == {}


def test_dedupe_is_by_trigger_id_alone() -> None:
    ladder = _ladder()
    assert [u.rung for u in ladder.on_triggers([_event(SU, "dup", 1)], turn=1)] == ["fragment"]
    # the same id again is a replay, whatever turn it is reported for
    assert ladder.on_triggers([_event(WQ, "dup", 4)], turn=4) == []
    assert ladder.on_triggers([_event(WQ, "dup", 1)], turn=6) == []
    # a repeated id inside one call counts once: the anomaly sharing the question's id is dropped
    fired = ladder.on_triggers([_event(WQ, "once", 5), _event(AN, "once", 5)], turn=5)
    assert [u.rung for u in fired] == ["first_crumb"]
    assert ladder.state.trigger_counts == {"self_uncertainty": 1, "world_question": 1}
    assert ladder.state.seen_trigger_ids == ["dup", "once"]
