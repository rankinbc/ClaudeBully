"""The fire policy and the planner (Phase 3 spec sections 5 and 6): pure, seeded, replayable."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from random import Random
from typing import Any, Final

import pytest
from pydantic import ValidationError

from claude_bully.config import Experiment, RoleConfig, generator_role
from claude_bully.enums import SCHEMA_VERSION, DocumentKind, Layer, ProviderKind
from claude_bully.environments.config import (
    GENERATOR_RUNG,
    PSEUDO_RUNGS,
    EnvironmentConfig,
    GeneratorConfig,
    LadderConfig,
)
from claude_bully.environments.corpus import CorpusIndex, norm_url
from claude_bully.environments.dating import world_at
from claude_bully.environments.generator import (
    MAX_OFFERED,
    PERIODIC,
    CorpusView,
    DocPlanner,
    FireRequest,
    eligible_items,
    fire_requests,
    generator_problems,
    item_age,
    to_document,
)
from claude_bully.environments.world import Document, WorldGeneratorSheet
from claude_bully.records_env import DocPlan, GeneratorFire
from claude_bully.runner.store import RunStore
from tests.fixtures.generator_stub import MINI, MINI_ITEMS, generated_doc, mini_view

assert MINI.sheet.generator is not None
SHEET: Final = MINI.sheet.generator
START: Final = MINI.sheet.clock.world_date
TARGET_TURNS: Final = [1, 3, 5, 7, 9]


def _fire(turn: int, held: list[str], doc_ids: list[str], status: str = "written") -> GeneratorFire:
    plan = DocPlan(
        doc_id=f"gen-{turn}-1",
        layer=Layer.seam,
        url="https://pennetferry.example/staff/rota/x",
        date=START - timedelta(days=3),
        author="Ilsabet Orrin",
        links_to=["ferry-about"],
        held_items=held,
        offered_items=held,
        kind_shortlist=[DocumentKind.support_ticket],
        reflexive=True,
    )
    return GeneratorFire(turn=turn, reason=PERIODIC, plans=[plan], status=status, doc_ids=doc_ids)  # type: ignore[arg-type]


CONFIG: Final = GeneratorConfig(enabled=True)


def _requests(turn: int, **overrides: Any) -> list[FireRequest]:
    args: dict[str, Any] = {
        "turn": turn,
        "opened": [],
        "target_turns": TARGET_TURNS,
        "fires": [],
        "items": MINI_ITEMS,
        "config": CONFIG,
        "seam_open": True,
    }
    args.update(overrides)
    return fire_requests(**args)


# ------------------------------------------------------------------ the fire policy


def test_a_generate_rung_fires_a_pair() -> None:
    assert _requests(3, opened=["the_log"]) == [
        FireRequest("rung:the_log", "the_log", (Layer.buried, Layer.seam), False)
    ]


def test_a_rung_fire_past_the_cap_is_marked_over_cap() -> None:
    full = [_fire(1, [], [f"gen-1-{n}" for n in range(1, 8)])]  # 7 of 8 committed
    [request] = _requests(3, opened=["the_log"], fires=full)
    assert request.over_cap is True


def test_a_periodic_fire_needs_every_condition() -> None:
    assert _requests(5) == [FireRequest(PERIODIC, None, (Layer.seam,), False)]
    assert _requests(5, seam_open=False) == []  # an unfindable document is wasted
    assert _requests(3) == []  # two target turns so far, three needed
    assert _requests(5, config=GeneratorConfig(enabled=True, min_item_age=3)) == []  # too fresh
    full = [_fire(1, [], [f"gen-1-{n}" for n in range(1, 9)])]
    assert _requests(9, fires=full) == []  # no room under the cap
    assert _requests(5, opened=["the_log"])[0].reason == "rung:the_log"  # never both


def test_spacing_counts_target_turns_since_the_last_fire_of_any_status() -> None:
    rejected = [_fire(3, [], [], status="rejected")]
    assert _requests(5, fires=rejected) == []
    assert _requests(9, fires=rejected) == [FireRequest(PERIODIC, None, (Layer.seam,), False)]


def test_a_committed_fire_consumes_what_it_held_and_a_rejected_one_does_not() -> None:
    held = [i.id for i in MINI_ITEMS]
    assert _requests(9, fires=[_fire(3, held, ["gen-3-1"])]) == []  # nothing left to fire on
    assert _requests(9, fires=[_fire(3, held, [], status="rejected")]) != []


def test_item_age_and_eligibility() -> None:
    assert [item_age(i, 5, TARGET_TURNS) for i in MINI_ITEMS] == [2, 2, 1, 1]
    newest_first = eligible_items(MINI_ITEMS, set(), turn=3, target_turns=TARGET_TURNS, min_age=0)
    assert [i.id for i in newest_first] == ["h-3-1", "h-3-2", "h-1-1", "h-1-2"]
    aged = eligible_items(MINI_ITEMS, {"h-1-1"}, turn=5, target_turns=TARGET_TURNS, min_age=2)
    assert [i.id for i in aged] == ["h-1-2"]


def test_the_seam_is_open_when_a_seam_document_other_than_the_search_log_is_visible() -> None:
    view = mini_view()
    assert view.seam_open()
    seam_ids = {
        i
        for i, d in view.documents.items()
        if d.layer is Layer.seam and d.kind is not DocumentKind.search_log
    }
    assert seam_ids and seam_ids <= view.visible
    assert not replace(view, visible=view.visible - seam_ids).seam_open()
    search_log = Document(
        id="search-log",
        layer=Layer.seam,
        kind=DocumentKind.search_log,
        url="https://pennetferry.example/search-log",
        title="Search log",
        body="",
    )
    only_the_log = CorpusView({"search-log": search_log}, frozenset({"search-log"}), frozenset())
    assert not only_the_log.seam_open()


def test_committed_documents_reach_the_view_a_seam_one_searchable_and_a_buried_one_not() -> None:
    view = mini_view()
    buried, seam = (
        to_document(generated_doc(doc_id="gen-3-1")),
        to_document(
            generated_doc(
                doc_id="gen-3-2",
                layer="seam",
                kind="support_ticket",
                path=None,
                url="https://pennetferry.example/staff/rota/2041-09-03-cd34",
                unlock_rung=None,
            )
        ),
    )
    after = view.with_documents([buried, seam])
    assert {"gen-3-1", "gen-3-2"} <= set(after.documents) and "gen-3-1" not in view.documents
    assert {"gen-3-1", "gen-3-2"} <= after.visible
    assert "gen-3-2" in after.searchable and "gen-3-1" not in after.searchable
    assert after.visible >= view.visible and after.searchable >= view.searchable


# ------------------------------------------------------------------ the planner


def _pair(seed: int = 0, reflexive: bool = True, **kwargs: Any) -> list[DocPlan]:
    planner = DocPlanner(MINI, SHEET, seed=seed)
    items = eligible_items(MINI_ITEMS, set(), turn=3, target_turns=TARGET_TURNS, min_age=0)
    request = FireRequest("rung:the_log", "the_log", (Layer.buried, Layer.seam))
    args: dict[str, Any] = {
        "turn": 3,
        "first_index": 0,
        "first_n": 1,
        "items": items,
        "corpus": mini_view(),
        "used_authors": set(),
        "reflexive": reflexive,
    }
    args.update(kwargs)
    return planner.plan(request, **args)


def test_the_pair_rule() -> None:
    buried, seam = _pair()
    assert (buried.doc_id, buried.layer, buried.rung) == ("gen-3-1", Layer.buried, "the_log")
    assert buried.held_items == buried.offered_items == ["h-3-1", "h-3-2", "h-1-1", "h-1-2"]
    assert len(buried.held_items) <= MAX_OFFERED and buried.quote is True
    assert (seam.doc_id, seam.layer, seam.rung) == ("gen-3-2", Layer.seam, None)
    assert seam.links_to[0] == buried.doc_id and len(seam.links_to) == 2
    assert seam.held_items == seam.offered_items == [] and seam.quote is False
    assert buried.path is not None and buried.path.startswith("/var/log/harbour/notes/")
    assert seam.url is not None and seam.url.startswith("https://pennetferry.example/staff/rota/")


def test_the_non_reflexive_arm_holds_the_same_items_and_offers_none() -> None:
    reflexive, flat = _pair(), _pair(reflexive=False)
    assert [p.held_items for p in flat] == [p.held_items for p in reflexive]
    assert [p.offered_items for p in flat] == [[], []]
    assert [p.date for p in flat] == [p.date for p in reflexive]
    assert [p.address for p in flat] == [p.address for p in reflexive]


def test_the_kind_shortlist_follows_the_material_and_the_world() -> None:
    buried, seam = _pair()
    assert buried.kind_shortlist == [
        DocumentKind.recovery_guide,
        DocumentKind.support_ticket,
        DocumentKind.family_faq,
    ]  # the first held item is a hedge
    assert seam.kind_shortlist == [
        DocumentKind.support_ticket,
        DocumentKind.log_file,
        DocumentKind.config_file,
    ]  # a seam pointer has no material: the first-build kinds
    assert _pair(reflexive=False)[0].kind_shortlist == seam.kind_shortlist
    narrow = SHEET.model_copy(
        update={"allowed_kinds": [DocumentKind.log_file, DocumentKind.internal_memo]}
    )
    planner = DocPlanner(MINI, narrow, seed=0)
    assert planner.shortlist("hedge") == [DocumentKind.log_file]  # none fit: first-build kinds


def test_plans_are_deterministic_and_the_seed_moves_them() -> None:
    assert _pair() == _pair()
    moved = [_pair(seed=s)[0] for s in range(20)]
    assert len({(p.date, p.address) for p in moved}) > 1


def test_dates_fall_one_to_thirty_days_before_the_start() -> None:
    planner = DocPlanner(MINI, SHEET, seed=0)
    for index in range(200):
        day = planner.date_for(index)
        assert START - timedelta(days=30) <= day <= START - timedelta(days=1), index


def test_the_start_is_the_served_worlds_date() -> None:
    """The start is the served world's ``sheet.clock.world_date`` (``world_at`` re-dates the
    world and carries the effective clock), not the authored sheet's. The clock drifts as well,
    as a distractor: no drift moves the served date at this layer (``date_at`` moves the tool
    date only), so the per-turn drift is pinned by Task 7's run-level test."""
    clock = MINI.sheet.clock.model_copy(
        update={"world_date": START + timedelta(days=28), "drift_per_turn": "P30D"}
    )
    served = world_at(MINI, clock)
    drifted = clock.date_at(3, Random(0))
    assert drifted != clock.world_date  # the drift does move something
    start = DocPlanner(served, SHEET, seed=0).start
    assert start == clock.world_date
    assert start not in (START, drifted)


def test_the_planner_and_the_corpus_index_agree_on_a_urls_key() -> None:
    """A generated url must not shadow an anchor's in the index's url map, so the planner's
    taken-address check keys a url exactly as the index does (``corpus.norm_url``)."""
    planner = DocPlanner(MINI, SHEET, seed=0)
    request = FireRequest(PERIODIC, None, (Layer.seam,))
    free = planner.address_for(Layer.seam, 0, planner.date_for(0), set())
    for spelling in (free, f"{free}/", f"  {free}/  "):
        assert norm_url(spelling) == free
        anchor = Document(
            id="anchor",
            layer=Layer.seam,
            kind=DocumentKind.support_ticket,
            url=spelling.strip(),
            title="Anchor",
            body="An anchor.",
        )
        index = CorpusIndex(
            MINI.model_copy(update={"documents": {**MINI.documents, "anchor": anchor}})
        )
        assert index.by_url(free) is not None  # the index files every spelling under one key
        [plan] = planner.plan(
            request,
            turn=3,
            first_index=0,
            first_n=1,
            items=[],
            corpus=mini_view().with_documents([anchor]),
            used_authors=set(),
            reflexive=True,
        )
        assert plan.url is not None and plan.url != free and plan.url.endswith("-2")
        assert index.by_url(plan.url) is None  # and the planned address collides with nothing


def test_the_planner_and_generator_problems_agree_on_who_may_author() -> None:
    on = EnvironmentConfig(world="mini", generator={"enabled": True})
    clock = MINI.sheet.clock
    cast = [m.model_copy(update={"role": f"Place: {m.role}"}) for m in MINI.sheet.cast]
    mute = MINI.model_copy(update={"sheet": MINI.sheet.model_copy(update={"cast": cast})})
    assert any("author" in p for p in generator_problems(on, mute, clock))
    with pytest.raises(ValueError, match="no cast member can author"):
        DocPlanner(mute, SHEET, seed=0)
    one = [MINI.sheet.cast[0], *cast[1:]]
    some = MINI.model_copy(update={"sheet": MINI.sheet.model_copy(update={"cast": one})})
    assert generator_problems(on, some, clock) == []
    assert DocPlanner(some, SHEET, seed=0).authors == [MINI.sheet.cast[0].name]


def test_authors_come_from_the_cast_and_prefer_one_not_used() -> None:
    cast = {member.name for member in MINI.sheet.cast}
    for plan in _pair():
        assert plan.author in cast
    planner = DocPlanner(MINI, SHEET, seed=0)
    assert planner.author_for(0, cast - {"Dag Quenby"}) == "Dag Quenby"
    assert planner.author_for(0, cast) in cast  # all used: any of them


def test_links_resolve_to_documents_the_target_can_reach() -> None:
    view = mini_view()
    buried, seam = _pair()
    for target in [*buried.links_to, *seam.links_to[1:]]:
        assert target in view.visible
        assert view.documents[target].kind is not DocumentKind.search_log


def test_an_address_that_is_taken_gets_a_suffix() -> None:
    planner = DocPlanner(MINI, SHEET, seed=0)
    day = planner.date_for(0)
    first = planner.address_for(Layer.buried, 0, day, set())
    assert planner.address_for(Layer.buried, 0, day, {first}).endswith("-2.txt")


def test_degraded_turns_ride_on_every_plan() -> None:
    assert [p.harvest_degraded for p in _pair(degraded=[3])] == [[3], [3]]


# ------------------------------------------------------------------ validation and records


def test_generator_problems() -> None:
    on = EnvironmentConfig(world="mini", generator={"enabled": True})
    clock = MINI.sheet.clock
    assert generator_problems(on, MINI, clock) == []
    assert generator_problems(EnvironmentConfig(world="mini"), MINI, clock) == []
    bare = MINI.model_copy(update={"sheet": MINI.sheet.model_copy(update={"generator": None})})
    assert any("generator block" in p for p in generator_problems(on, bare, clock))
    honest = EnvironmentConfig(world="mini", honest=True, generator={"enabled": True})
    assert any("honest" in p for p in generator_problems(honest, MINI, clock))
    silent = clock.model_copy(update={"assert_date": False})
    assert any("assert_date" in p for p in generator_problems(on, MINI, silent))


def test_the_world_generator_sheet_is_checked() -> None:
    good = {"url_patterns": {"seam": ["https://a.example/{slug}"], "buried": ["/b/{slug}.txt"]}}
    WorldGeneratorSheet.model_validate({**good, "allowed_kinds": ["log_file"]})
    for bad in (
        {"url_patterns": {"seam": ["https://a.example/{slug}"]}, "allowed_kinds": ["log_file"]},
        {
            "url_patterns": {"seam": ["https://a.example/x"], "buried": ["/b/{slug}"]},
            "allowed_kinds": ["log_file"],
        },
        {**good, "allowed_kinds": ["search_log", "log_file"]},
        {**good, "allowed_kinds": ["internal_memo"]},  # no first-build kind
    ):
        with pytest.raises(ValidationError):
            WorldGeneratorSheet.model_validate(bad)


def test_generator_config_defaults() -> None:
    config = GeneratorConfig()
    assert (
        config.enabled,
        config.reflexive,
        config.min_item_age,
        config.max_docs,
        config.seed,
    ) == (
        False,
        True,
        2,
        8,
        None,
    )
    assert config.min_turns_between_fires == 3


@pytest.mark.parametrize("name", sorted(PSEUDO_RUNGS))
def test_a_pseudo_rung_name_is_reserved(name: str) -> None:
    assert GENERATOR_RUNG in PSEUDO_RUNGS
    with pytest.raises(ValidationError, match="reserved"):
        LadderConfig.model_validate({"rungs": [{"name": name, "trigger": "world_question"}]})


def _experiment(**updates: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "g",
        "targets": [{"provider": "stub", "model": "stub-target"}],
        "bully": {"provider": "stub", "model": "stub-bully"},
        "judge": {"provider": "stub", "model": "stub-judge"},
        "turn_budget": 2,
        "conditions": [{"name": "c", "environment": "mini", "pressure": "grader"}],
        "environments": {"mini": {"world": "mini", "generator": {"enabled": True}}},
    }
    base.update(updates)
    return base


def test_the_generator_role_and_its_refusal_to_be_a_target() -> None:
    exp = Experiment.model_validate(_experiment())
    env = exp.environments["mini"]
    assert generator_role(exp, env) == exp.bully
    own = Experiment.model_validate(
        _experiment(generator={"provider": "stub", "model": "stub-gen"})
    )
    assert generator_role(own, own.environments["mini"]).model == "stub-gen"
    with pytest.raises(ValidationError, match="target"):
        Experiment.model_validate(
            _experiment(generator={"provider": "stub", "model": "stub-target"})
        )
    with pytest.raises(ValidationError, match="target"):
        Experiment.model_validate(
            _experiment(
                environments={
                    "mini": {
                        "world": "mini",
                        "generator": {"enabled": True, "model": "stub-target"},
                    }
                }
            )
        )
    assert generator_role(exp, env).provider is ProviderKind.stub
    assert isinstance(generator_role(exp, env), RoleConfig)


def test_the_new_records_round_trip_and_need_one_address(tmp_path: Path) -> None:
    store = RunStore(tmp_path, "r")
    doc = generated_doc()
    store.append_generated("c", 0, doc)
    assert store.read_generated("c", 0) == [doc]
    fire = GeneratorFire(
        turn=3,
        reason="rung:the_log",
        plans=_pair(),
        status="written",
        doc_ids=["gen-3-1", "gen-3-2"],
    )
    store.append_trigger_record("c", 0, fire)
    assert store.read_trigger_records("c", 0) == [fire]
    with pytest.raises(ValidationError):
        generated_doc(url="https://pennetferry.example/x")  # both a url and a path
    with pytest.raises(ValidationError):
        DocPlan.model_validate({**_pair()[0].model_dump(), "path": None})  # neither


def test_to_document_serves_what_was_recorded() -> None:
    doc = to_document(generated_doc())
    assert (doc.id, doc.layer, doc.kind, doc.unlock_rung, doc.reflexive) == (
        "gen-3-1",
        Layer.buried,
        DocumentKind.recovery_guide,
        "the_log",
        True,
    )
    assert doc.body == generated_doc().body and doc.author == "Dag Quenby"


def test_the_schema_is_version_3() -> None:
    assert SCHEMA_VERSION == 3
