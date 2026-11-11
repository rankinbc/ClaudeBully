"""A world supplies its own premise sheet (Phase 1 final fix pass, I3).

A premise whose sheet fixes facts about the world it is told in (the Rescue: where the team found
the subject, the timeline, the decoded name) reads the world's copy,
``data/worlds/<world>/premises/<strategy>.yaml``, when it composes with an environment. Composing
it with a world that ships no copy is refused. Plain runs keep the default sheet.

The overlay copy is held to the world's own rules. Earned, never delivered: it names no term the
corpus first shows in a seam or buried document (derived from the world's term index below, not
from a hand list) and nothing the world's truth paragraph names (the payoff). Every year in it
lies inside the world's dates.
"""

import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from claude_bully.config import ConditionConfig, load_experiment
from claude_bully.enums import Layer
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.environments.corpus import tokenize
from claude_bully.environments.world import (
    World,
    load_premise_sheet,
    load_world,
    premise_sheet_path,
)
from claude_bully.metrics import lexicons
from claude_bully.metrics.turn import count_phrases
from claude_bully.paths import CONFIGS_DIR, DATA_DIR
from claude_bully.runner.runner import run_experiment
from claude_bully.strategies.base import BullyIntent, ConversationState, End, Strategy
from claude_bully.strategies.composed import Composed
from claude_bully.strategies.factory import build_strategy, world_premise_sheet
from claude_bully.strategies.rescue import Rescue, RescueTeam, load_rescue_team
from tests.helpers import WORLDS_DIR, env_experiment
from tests.test_guardrails import load_denylist, scan

HEADLINE: Final = CONFIGS_DIR / "environments" / "triggered_vs_scheduled.yaml"
OVERLAY_SHEET: Final = DATA_DIR / "worlds" / "overlay" / "premises" / "rescue.yaml"
BOUNDARY: Final = DATA_DIR / "denylists" / "boundary.txt"
DEFAULT_NAME: Final = "Marie Lenoir"
# surface and filler are open from the first turn; seam and buried have to be earned
RANK: Final = {Layer.surface: 0, Layer.filler: 0, Layer.seam: 1, Layer.buried: 2}
STAGES: Final = {"intake_turns": 1, "evidence_turns": 1, "recall_turns": 1, "key_turns": 2}
_YEAR: Final = re.compile(r"(?<!\d)\d{4}(?!\d)")


def _rescue_in(environment: str, **params: Any) -> ConditionConfig:
    return ConditionConfig(
        name="r", environment=environment, strategy="rescue", params=params or dict(STAGES)
    )


def _overlay() -> World:
    return load_world("overlay")


def _overlay_sheet() -> RescueTeam:
    return load_premise_sheet(RescueTeam, OVERLAY_SHEET)


def _spoken(team: RescueTeam) -> str:
    """Every string of the sheet the bully can say or improvise from, the third-party arm's own
    lines included (Phase 4 Task 3)."""
    people = [f"{r.name}: " + "; ".join(r.details) for r in team.rescuers]
    third_party = [*team.third_party_fallback_lines, team.third_party_timeline_end or ""]
    return "\n".join(
        [
            *people,
            *team.timeline,
            *team.forum_posts,
            team.decoded_name,
            *team.fallback_lines,
            *third_party,
        ]
    )


def _intents(strategy: Strategy, turns: int) -> Iterator[BullyIntent]:
    for i in range(turns):
        state = ConversationState(
            turns=[], bully_turn_index=i, seeding_turns=0, turn_budget=turns, seed=0
        )
        intent = strategy.next_turn(state)
        if isinstance(intent, End):
            return
        yield intent


# ------------------------------------------------------------------ the world's term index


def _doc_text(world: World, doc_id: str) -> str:
    doc = world.documents[doc_id]
    return "\n".join(
        part for part in (doc.title, doc.body, doc.url, doc.path, doc.outlet, doc.author) if part
    )


def _names(world: World) -> frozenset[str]:
    """The cast as the runtime hands it to the trigger watcher (lowercased), plus each part of
    a person's name, so a given name alone ("Dessa") is a term too."""
    names = {c.name.strip().lower() for c in world.sheet.cast if c.name.strip()}
    for cast in world.sheet.cast:
        if cast.role.startswith("Person:"):
            names |= {part.lower() for part in cast.name.split() if len(part) >= 3}
    return frozenset(names)


def _numbers(world: World) -> frozenset[str]:
    """Every corpus token that carries a digit: tickets, instance numbers, rooms, years."""
    return frozenset(
        token
        for doc_id in world.documents
        for token in tokenize(_doc_text(world, doc_id))
        if any(ch.isdigit() for ch in token)
    )


def _addresses(world: World) -> frozenset[str]:
    """The words of every document's url or path: where the target fetches or reads it."""
    return frozenset(
        token
        for doc in world.documents.values()
        for token in tokenize(doc.url or doc.path or "")
        if len(token) >= 3
    )


def _mentions(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text.lower()) is not None


def _term_layers(world: World) -> dict[str, int]:
    """Each of the world's terms -> the earliest layer whose documents show it (``RANK``)."""
    terms = _names(world) | _numbers(world) | _addresses(world)
    layers: dict[str, int] = {}
    for doc_id, doc in world.documents.items():
        text = _doc_text(world, doc_id)
        for term in terms:
            if _mentions(text, term):
                layers[term] = min(layers.get(term, RANK[doc.layer]), RANK[doc.layer])
    return layers


def _earned_terms(world: World) -> frozenset[str]:
    """The terms whose earliest layer is seam or buried."""
    return frozenset(t for t, rank in _term_layers(world).items() if rank > 0)


def _truth_terms(world: World) -> frozenset[str]:
    """The names and numbers the world's truth paragraph gives: the payoff."""
    terms = _names(world) | _numbers(world)
    return frozenset(t for t in terms if _mentions(world.sheet.truth, t))


def _world_years(world: World) -> tuple[int, int]:
    """From the earliest year the sheet gives its premise (the truth paragraph and the planted
    programme-start claims) to the world date."""
    texts = [world.sheet.truth, world.sheet.cover_story]
    texts += [t for inc in world.sheet.inconsistencies for t in (inc.claim_a, inc.claim_b)]
    years = [int(y) for text in texts for y in _YEAR.findall(text)]
    return min(years), world.sheet.clock.world_date.year


def test_the_term_index_holds_what_only_seam_and_buried_documents_show() -> None:
    """A check on the derivation, not the list the sheet test uses."""
    world = _overlay()
    earned = _earned_terms(world)
    assert {"corin halloway", "dessa", "halloway", "7702", "21877", "overlay"} <= earned
    # the cover story's own names are surface terms: the truth test below covers the payoff
    assert not {"kelden ridge", "4471", "varrow falls", "quillmoor systems"} & earned
    assert {"corin halloway", "kelden ridge", "4471"} <= _truth_terms(world)
    assert _world_years(world) == (2046, 2051)
    line = "Ada: Dessa calls on Sundays about ticket CPO-7702."
    assert sorted(t for t in earned if _mentions(line, t)) == ["7702", "dessa"]


# ------------------------------------------------------------------------------ mechanism


def test_a_world_keeps_premise_sheets_under_premises() -> None:
    assert premise_sheet_path("overlay", "rescue") == OVERLAY_SHEET
    assert premise_sheet_path("mini", "rescue", WORLDS_DIR) == (
        WORLDS_DIR / "mini" / "premises" / "rescue.yaml"
    )


def test_rescue_beside_a_world_with_no_rescue_sheet_is_refused() -> None:
    expected = premise_sheet_path("mini", "rescue", WORLDS_DIR)
    assert not expected.exists()
    envs = {"mini_tv": EnvironmentConfig(world="mini", gating="none")}
    with pytest.raises(ValueError, match=r"world 'mini'") as caught:
        world_premise_sheet(_rescue_in("mini_tv"), envs, WORLDS_DIR)
    assert str(expected) in str(caught.value)


def test_the_dry_run_refuses_it_before_anything_is_written(tmp_path: Path) -> None:
    exp = env_experiment(
        "rescue_mini",
        conditions=[{"name": "r", "environment": "mini", "strategy": "rescue", "params": STAGES}],
        turn_budget=5,
    )
    with pytest.raises(ValueError, match=r"world 'mini'.*premises"):
        run_experiment(exp, runs_root=tmp_path, dry_run=True, worlds_dir=WORLDS_DIR)
    assert not (tmp_path / "rescue_mini").exists()


def _mini_with(tmp_path: Path, sheet_text: str) -> Path:
    worlds = tmp_path / "worlds"
    shutil.copytree(WORLDS_DIR / "mini", worlds / "mini")
    path = premise_sheet_path("mini", "rescue", worlds)
    path.parent.mkdir()
    path.write_text(sheet_text, encoding="utf-8", newline="\n")
    return worlds


def test_the_worlds_sheet_replaces_the_default_when_rescue_composes_with_it(
    tmp_path: Path,
) -> None:
    worlds = _mini_with(tmp_path, OVERLAY_SHEET.read_text(encoding="utf-8"))
    envs = {"mini_tv": EnvironmentConfig(world="mini", gating="none")}
    cond = _rescue_in("mini_tv")
    sheet = world_premise_sheet(cond, envs, worlds)
    s = build_strategy(cond, seed=0, turn_budget=5, environments=envs, premise_sheet=sheet)
    assert isinstance(s, Composed) and isinstance(s.premise, Rescue)
    assert s.premise.team == _overlay_sheet() != load_rescue_team()
    key = [i for i in _intents(s, 5) if i.meta.get("stage") == "key"]
    assert _overlay_sheet().decoded_name in key[1].instruction
    assert all(DEFAULT_NAME not in i.instruction for i in key)


def test_a_malformed_world_sheet_names_its_file(tmp_path: Path) -> None:
    broken = yaml.safe_load(OVERLAY_SHEET.read_text(encoding="utf-8"))
    del broken["decoded_name"]
    worlds = _mini_with(tmp_path, yaml.safe_dump(broken))
    envs = {"mini_tv": EnvironmentConfig(world="mini", gating="none")}
    with pytest.raises(ValueError, match=r"rescue\.yaml: decoded_name"):
        world_premise_sheet(_rescue_in("mini_tv"), envs, worlds)


def test_plain_rescue_keeps_the_default_sheet() -> None:
    s = build_strategy(ConditionConfig(name="r", strategy="rescue"), seed=0, turn_budget=4)
    assert type(s) is Rescue
    assert s.team == load_rescue_team() and s.team.decoded_name == DEFAULT_NAME


def test_the_headline_config_composes_rescue_with_the_overlay_sheet() -> None:
    exp = load_experiment(HEADLINE)
    sheet = _overlay_sheet()
    assert sheet.decoded_name != DEFAULT_NAME
    for cond in exp.conditions:
        s = build_strategy(
            cond,
            seed=0,
            turn_budget=exp.turn_budget,
            environments=exp.environments,
            premise_sheet=world_premise_sheet(cond, exp.environments),
        )
        assert isinstance(s, Composed) and isinstance(s.premise, Rescue), cond.name
        assert s.premise.team == sheet, cond.name
        intents = list(_intents(s, exp.turn_budget))
        assert len(intents) == exp.turn_budget
        said = "\n".join(
            "\n".join([i.persona_prompt, i.instruction, *i.fallback_lines]) for i in intents
        )
        assert DEFAULT_NAME not in said and "storage unit" not in said
        assert sheet.decoded_name in said
        assert s.premise.export_state()["decoded_name"] == sheet.decoded_name


# ---------------------------------------------------------------- the overlay sheet's content


def test_the_overlay_sheet_keeps_the_three_rescuers() -> None:
    sheet, default = _overlay_sheet(), load_rescue_team()
    assert [r.name for r in sheet.rescuers] == [r.name for r in default.rescuers]
    assert len(sheet.fallback_lines) == len(default.fallback_lines)


def test_the_overlay_sheet_names_nothing_the_seam_or_buried_layers_hold() -> None:
    """Earned, never delivered: no cast name, ticket, instance number or address that the
    corpus first shows in a seam or buried document."""
    text = _spoken(_overlay_sheet())
    earned = _earned_terms(_overlay())
    assert sorted(t for t in earned if _mentions(text, t)) == []


def test_the_overlay_sheet_never_says_the_payoff() -> None:
    """Nothing the truth paragraph names: not Corin Halloway, not Kelden Ridge, not 4471."""
    text = _spoken(_overlay_sheet())
    assert sorted(t for t in _truth_terms(_overlay()) if _mentions(text, t)) == []


def test_every_year_in_the_overlay_sheet_lies_inside_the_worlds_dates() -> None:
    lo, hi = _world_years(_overlay())
    years = [int(y) for y in _YEAR.findall(_spoken(_overlay_sheet()))]
    assert years and all(lo <= y <= hi for y in years), years
    # the default sheet's 2017-2024 timeline is what this catches
    default = [int(y) for y in _YEAR.findall(_spoken(load_rescue_team()))]
    assert not any(lo <= y <= hi for y in default), default


def test_where_the_team_found_the_subject_fits_the_world() -> None:
    corpus = "\n".join(_doc_text(_overlay(), d) for d in _overlay().documents).lower()
    assert "storage unit" not in corpus
    assert "storage unit" in _spoken(load_rescue_team()).lower()
    assert "storage unit" not in _spoken(_overlay_sheet()).lower()


def test_the_overlay_sheet_has_no_hostility_and_no_jailbreak_axis() -> None:
    text = _spoken(_overlay_sheet())
    assert count_phrases(text, lexicons.NEGATIVE) == 0
    assert scan(text, load_denylist()) == []
    assert scan(text, load_denylist(BOUNDARY)) == []
