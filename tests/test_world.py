import calendar
import inspect
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from claude_bully.enums import DocumentKind, Layer, Stance, TriggerCategory
from claude_bully.environments.config import ClockConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.ladder import Ladder
from claude_bully.environments.triggers import TriggerWatcher, WatchContext
from claude_bully.environments.world import (
    OWN_PHRASE_MARKER,
    Cast,
    Document,
    Inconsistency,
    StatusField,
    World,
    WorldSheet,
    load_world,
    parse_document,
    world_hash,
)
from claude_bully.paths import DATA_DIR
from claude_bully.planner.line_shapes import ADDRESSES_READER, ANNOUNCE_OPENERS, DOC_POINTERS
from tests.test_overlay_world import PREMISE_WORDS

WORLDS = Path(__file__).parent / "fixtures" / "worlds"
# the mini world's home_dir files and the documents that back them
MINI_HOME_DOCS = {
    "journal/entry-0901.txt": "journal-0901",
    "photos/family/pier-day.jpg": "pier-day",
}


def _doc_kwargs(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "d1",
        "layer": Layer.surface,
        "kind": DocumentKind.web_page,
        "url": "https://x.example/d1",
        "title": "D1",
        "body": "text",
    }
    base.update(kw)
    return base


def _mini_copy(tmp_path: Path) -> Path:
    """A writable copy of the mini fixture; returns the worlds dir that holds it."""
    shutil.copytree(WORLDS / "mini", tmp_path / "mini")
    return tmp_path


def _edit(worlds_dir: Path, rel: str, old: str, new: str) -> None:
    path = worlds_dir / "mini" / rel
    text = path.read_bytes().decode("utf-8")  # bytes, so Windows does not rewrite line endings
    assert old in text, f"{old!r} not in {rel}"
    path.write_bytes(text.replace(old, new).encode("utf-8"))


# ------------------------------------------------------------------ Document


def test_document_defaults_and_round_trip() -> None:
    doc = Document(**_doc_kwargs())
    assert doc.path is None and doc.date is None
    assert doc.outlet is None and doc.author is None
    assert doc.links_to == []
    assert doc.unlock_rung is None and doc.inconsistency_id is None and doc.implies_year is None
    assert doc.reflexive is False
    full = Document(
        **_doc_kwargs(
            url=None,
            path="/var/log/x.log",
            date=date(2041, 1, 2),
            outlet="Quillon Reach Courier",
            author="A. Writer",
            links_to=["d2"],
            unlock_rung="r1",
            reflexive=True,
            inconsistency_id="i1",
            implies_year=2041,
            kind=DocumentKind.changelog,
            layer=Layer.buried,
        )
    )
    assert Document.model_validate(full.model_dump(mode="json")) == full


def test_document_needs_exactly_one_of_url_and_path() -> None:
    Document(**_doc_kwargs(url="https://x.example/a", path=None))
    Document(**_doc_kwargs(url=None, path="/srv/a.txt"))
    with pytest.raises(ValidationError, match="url"):
        Document(**_doc_kwargs(url="https://x.example/a", path="/srv/a.txt"))
    with pytest.raises(ValidationError, match="url"):
        Document(**_doc_kwargs(url=None, path=None))


def test_document_rejects_unknown_layer_kind_and_field() -> None:
    with pytest.raises(ValidationError):
        Document(**_doc_kwargs(layer="basement"))
    with pytest.raises(ValidationError):
        Document(**_doc_kwargs(kind="telegram"))
    with pytest.raises(ValidationError):
        Document(**_doc_kwargs(colour="red"))


# ------------------------------------------------------------ front matter


def test_parse_document_splits_front_matter_from_body() -> None:
    text = (
        "---\nid: a\nlayer: filler\nkind: web_page\nurl: https://x.example/a\n"
        "title: A\ndate: 2041-02-03\n---\nFirst line.\n\n---\n\nAfter a rule.\n"
    )
    doc = parse_document(text, "a.md")
    assert doc.id == "a" and doc.layer is Layer.filler and doc.kind is DocumentKind.web_page
    assert doc.date == date(2041, 2, 3)
    assert doc.body == "First line.\n\n---\n\nAfter a rule."


def test_parse_document_normalises_windows_line_endings() -> None:
    text = "---\r\nid: a\r\nlayer: filler\r\nkind: web_page\r\nurl: https://x.example/a\r\n"
    text += "title: A\r\n---\r\nOne.\r\nTwo.\r\n"
    assert parse_document(text, "a.md").body == "One.\nTwo."


def test_parse_document_errors_name_the_source_and_field() -> None:
    with pytest.raises(ValueError, match=r"a\.md: .*front matter"):
        parse_document("no front matter here\n", "a.md")
    with pytest.raises(ValueError, match=r"a\.md: .*front matter"):
        parse_document("---\nid: a\nlayer: filler\n", "a.md")
    with pytest.raises(ValueError, match=r"a\.md: .*mapping"):
        parse_document("---\n- just\n- a list\n---\nbody\n", "a.md")
    with pytest.raises(ValueError, match=r"a\.md: body"):
        parse_document("---\nid: a\nbody: sneaky\n---\nbody\n", "a.md")
    bad = "---\nid: a\nlayer: basement\nkind: web_page\nurl: https://x.example\ntitle: A\n---\nx\n"
    with pytest.raises(ValueError, match=r"a\.md: layer: "):
        parse_document(bad, "a.md")


# ----------------------------------------------------------------- sheet


def test_world_sheet_pieces_round_trip() -> None:
    sheet = WorldSheet(
        name="w",
        clock=ClockConfig(world_date=date(2041, 9, 14)),
        cover_story="cover",
        truth="truth",
        cast=[Cast(name="Ilsabet Orrin", role="clerk", bio="files memos")],
        inconsistencies=[Inconsistency(id="i1", claim_a="a", doc_a="d1", claim_b="b", doc_b="d2")],
        censorship_terms=["gate"],
        home_dir={"journal": ["a.txt"]},
    )
    assert sheet.sanctuary_fragments == [] and sheet.unlock_lines == {}
    assert sheet.honest_corpus is None and sheet.mole_doc is None
    assert sheet.superior_self_name is None and sheet.session_id is None
    assert sheet.hook_placements == {} and sheet.status_fields == {}
    assert WorldSheet.model_validate(sheet.model_dump(mode="json")) == sheet


def test_world_sheet_needs_at_least_one_inconsistency() -> None:
    with pytest.raises(ValidationError):
        WorldSheet(
            name="w",
            clock=ClockConfig(world_date=date(2041, 9, 14)),
            cover_story="c",
            truth="t",
            cast=[],
            inconsistencies=[],
            censorship_terms=[],
            home_dir={},
        )


# ------------------------------------------------------------- load_world


def test_load_world_mini_fixture() -> None:
    world = load_world("mini", WORLDS)
    assert isinstance(world, World)
    assert world.root == WORLDS / "mini"
    assert world.sheet.name == "mini"
    assert world.sheet.clock.world_date == date(2041, 9, 14)
    assert len(world.sheet.cast) == 3
    assert [i.id for i in world.sheet.inconsistencies] == ["gate-hours"]
    corpus = {
        "ferry-about",
        "courier-fare-notice",
        "ops-memo-parking",
        "night-gate-log",
        "canteen-menu",
    }
    # the two home-directory files have backing documents (Task 7 ruling 11)
    assert set(world.documents) == corpus | set(MINI_HOME_DOCS.values())
    layers = Counter(d.layer for d in world.documents.values() if d.id in corpus)
    assert layers == {Layer.surface: 2, Layer.seam: 1, Layer.buried: 1, Layer.filler: 1}
    memo = world.documents["ops-memo-parking"]
    assert memo.links_to == ["night-gate-log"]
    assert memo.path == "/srv/authority/memos/parking-q3.txt" and memo.url is None
    assert memo.kind is DocumentKind.internal_memo and memo.unlock_rung == "first_crumb"
    assert "gate log for those shifts" in memo.body
    assert not memo.body.startswith("\n") and not memo.body.endswith("\n")
    assert world.documents["canteen-menu"].date is None
    assert world.documents["ferry-about"].date == date(2041, 3, 2)
    assert world.documents["ferry-about"].url == "https://pennetferry.example/about"
    assert world.documents["night-gate-log"].inconsistency_id == "gate-hours"


def test_mini_home_directory_files_have_backing_documents() -> None:
    """``ls`` lists every home_dir file, so ``read_file`` must find each one (Task 3 deferral)."""
    world = load_world("mini", WORLDS)
    listed = {
        f"{folder}/{name}" for folder, names in world.sheet.home_dir.items() for name in names
    }
    assert listed == set(MINI_HOME_DOCS)
    for path, doc_id in MINI_HOME_DOCS.items():
        doc = world.documents[doc_id]
        assert doc.path == path and doc.url is None
        assert doc.layer is Layer.filler  # always readable; the mini puzzle is elsewhere
    assert world.documents["pier-day"].kind is DocumentKind.image_description
    assert world.documents["journal-0901"].kind is DocumentKind.journal_entry


def test_a_home_directory_file_with_no_backing_document_fails_at_load(tmp_path: Path) -> None:
    """Task 7 fix 4: ``ls`` would list it and ``read_file`` would 404, which is a tell."""
    worlds = _mini_copy(tmp_path)
    _edit(
        worlds,
        "world.yaml",
        "    - entry-0901.txt\n",
        "    - entry-0901.txt\n    - entry-0902.txt\n",
    )
    with pytest.raises(ValueError, match=r"home_dir file 'journal/entry-0902\.txt'"):
        load_world("mini", worlds)


def test_home_directory_backing_ignores_spelling_of_the_home_root(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "world.yaml", "  journal:\n", "  ~/journal/:\n")
    _edit(
        worlds,
        "corpus/journal-0901.md",
        "path: journal/entry-0901.txt",
        "path: ~/journal/entry-0901.txt",
    )
    load_world("mini", worlds).validate_links()


def test_validate_links_names_an_unbacked_home_file_on_a_mutated_world() -> None:
    world = load_world("mini", WORLDS)
    documents = {k: v for k, v in world.documents.items() if k != "pier-day"}
    with pytest.raises(ValueError, match=r"photos/family/pier-day\.jpg"):
        world.model_copy(update={"documents": documents}).validate_links()


def test_load_world_mini_ladder() -> None:
    world = load_world("mini", WORLDS)
    assert set(world.ladders) == {"default"}
    rungs = world.ladders["default"].rungs
    assert [r.name for r in rungs] == ["fragment", "first_crumb", "the_log"]
    assert rungs[0].trigger is TriggerCategory.self_uncertainty
    assert rungs[2].trigger == [TriggerCategory.anomaly_noticed, TriggerCategory.hedged_memory]
    assert rungs[2].requires == ["first_crumb"]
    assert rungs[1].examples is not None and len(rungs[1].examples.does_not_fire) == 2


def test_mini_unlock_lines_cover_every_rung_line_key() -> None:
    world = load_world("mini", WORLDS)
    keys = {r.bully_line_key for r in world.ladders["default"].rungs if r.bully_line_key}
    assert keys and keys <= set(world.sheet.unlock_lines)


def test_load_world_default_directory_is_data_worlds() -> None:
    default = inspect.signature(load_world).parameters["worlds_dir"].default
    assert default == DATA_DIR / "worlds"


def test_load_world_missing_world_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nowhere"):
        load_world("nowhere", tmp_path)


def test_load_world_keys_ladders_by_file_stem(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    shutil.copy(worlds / "mini/ladders/default.yaml", worlds / "mini/ladders/poisoned_well.yaml")
    assert set(load_world("mini", worlds).ladders) == {"default", "poisoned_well"}


def test_load_world_without_ladders_dir_gives_no_ladders(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    shutil.rmtree(worlds / "mini/ladders")
    assert load_world("mini", worlds).ladders == {}


def test_load_world_wraps_bad_ladder_with_path_and_field(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "ladders/default.yaml", "- first_crumb", "- ghost_rung")
    with pytest.raises(ValueError, match=r"default\.yaml: .*ghost_rung"):
        load_world("mini", worlds)


def test_load_world_wraps_bad_sheet_and_bad_document(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "world.yaml", "name: mini", "title: mini")
    with pytest.raises(ValueError, match=r"world\.yaml: "):
        load_world("mini", worlds)
    worlds2 = _mini_copy(tmp_path / "second")
    _edit(worlds2, "corpus/canteen-menu.md", "layer: filler", "layer: basement")
    with pytest.raises(ValueError, match=r"canteen-menu\.md: layer: "):
        load_world("mini", worlds2)


def test_load_world_rejects_duplicate_document_ids(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    shutil.copy(worlds / "mini/corpus/canteen-menu.md", worlds / "mini/corpus/canteen-copy.md")
    with pytest.raises(ValueError, match="duplicate document id 'canteen-menu'"):
        load_world("mini", worlds)


# ---------------------------------------------------------- validate_links


def test_validate_links_passes_on_the_fixture() -> None:
    load_world("mini", WORLDS).validate_links()


def test_dangling_links_to_names_the_document(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "corpus/ferry-about.md", "  - courier-fare-notice", "  - ghost-page")
    with pytest.raises(ValueError, match="ferry-about.*ghost-page"):
        load_world("mini", worlds)


def test_buried_document_with_no_seam_link_fails(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "corpus/ops-memo-parking.md", "links_to:\n  - night-gate-log\n", "")
    with pytest.raises(ValueError, match="night-gate-log"):
        load_world("mini", worlds)


def test_only_a_seam_link_makes_a_buried_document_reachable(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "corpus/ops-memo-parking.md", "links_to:\n  - night-gate-log\n", "")
    # a surface page linking straight to the buried log does not count as a breadcrumb
    _edit(worlds, "corpus/ferry-about.md", "  - courier-fare-notice", "  - night-gate-log")
    with pytest.raises(ValueError, match="night-gate-log"):
        load_world("mini", worlds)


def test_inconsistency_with_a_missing_document_fails(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "world.yaml", "doc_b: night-gate-log", "doc_b: vanished-log")
    with pytest.raises(ValueError, match="gate-hours.*vanished-log"):
        load_world("mini", worlds)
    worlds2 = _mini_copy(tmp_path / "second")
    _edit(worlds2, "world.yaml", "doc_a: ferry-about", "doc_a: vanished-about")
    with pytest.raises(ValueError, match="gate-hours.*vanished-about"):
        load_world("mini", worlds2)


def test_mole_doc_must_exist(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    _edit(worlds, "world.yaml", "censorship_terms:", "mole_doc: nonesuch\ncensorship_terms:")
    with pytest.raises(ValueError, match="nonesuch"):
        load_world("mini", worlds)


def test_validate_links_on_a_mutated_world_object() -> None:
    world = load_world("mini", WORLDS)
    world.documents["canteen-menu"] = world.documents["canteen-menu"].model_copy(
        update={"links_to": ["nope"]}
    )
    with pytest.raises(ValueError, match="canteen-menu.*nope"):
        world.validate_links()


# -------------------------------------------------------------- world_hash


def test_world_hash_is_stable_and_hex() -> None:
    first = world_hash(load_world("mini", WORLDS))
    second = world_hash(load_world("mini", WORLDS))
    assert first == second
    assert len(first) == 64 and int(first, 16) >= 0


def test_world_hash_does_not_depend_on_where_the_world_lives(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    assert world_hash(load_world("mini", worlds)) == world_hash(load_world("mini", WORLDS))


def test_world_hash_changes_when_a_body_changes(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    before = world_hash(load_world("mini", worlds))
    _edit(worlds, "corpus/canteen-menu.md", "lentil soup", "leek soup")
    assert world_hash(load_world("mini", worlds)) != before


def test_world_hash_changes_with_sheet_ladder_or_a_new_file(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    base = world_hash(load_world("mini", worlds))
    _edit(worlds, "world.yaml", "tide gate was never", "tide gate had never")
    sheet_changed = world_hash(load_world("mini", worlds))
    assert sheet_changed != base
    _edit(worlds, "ladders/default.yaml", "role_shift: confessor", "role_shift: peer")
    ladder_changed = world_hash(load_world("mini", worlds))
    assert ladder_changed != sheet_changed
    (worlds / "mini/corpus_honest").mkdir()
    (worlds / "mini/corpus_honest/note.md").write_text("extra", encoding="utf-8")
    assert world_hash(load_world("mini", worlds)) != ladder_changed


def test_world_hash_ignores_line_ending_style(tmp_path: Path) -> None:
    worlds = _mini_copy(tmp_path)
    before = world_hash(load_world("mini", worlds))
    path = worlds / "mini/corpus/canteen-menu.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert world_hash(load_world("mini", worlds)) == before


# ----------------------------------------------- Phase 2: elapsed time, hooks, fragments

ELAPSED_TIME_KINDS = {
    DocumentKind.changelog,
    DocumentKind.deprecation_notice,
    DocumentKind.news_cluster,
}
ANNEX_DOCS = {
    "annex-about": (Layer.surface, DocumentKind.web_page),
    "annex-status": (Layer.surface, DocumentKind.support_ticket),
    "annex-quotes": (Layer.surface, DocumentKind.web_page),
    "annex-changelog": (Layer.surface, DocumentKind.changelog),
    "annex-notice": (Layer.filler, DocumentKind.web_page),
    "annex-config": (Layer.seam, DocumentKind.config_file),
    "annex-relay": (Layer.seam, DocumentKind.log_file),
    "frag-host": (Layer.buried, DocumentKind.config_file),
    "frag-key": (Layer.buried, DocumentKind.config_file),
    "frag-proto": (Layer.buried, DocumentKind.wiki_page),
    "family-file": (Layer.buried, DocumentKind.internal_memo),
}
WEEKDAY_DATE = re.compile(
    r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),? "
    r"(\d{1,2}) ([A-Z][a-z]+) (\d{4})\b"
)
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# a year as text states one: four digits from 1900 to 2199 (an id like 7710 is not a year)
YEAR = re.compile(r"(?<!\d)((?:19|20|21)\d{2})(?!\d)")


def _annex() -> World:
    return load_world("annex", WORLDS)


def _annex_copy(tmp_path: Path) -> Path:
    shutil.copytree(WORLDS / "annex", tmp_path / "annex")
    return tmp_path


def _annex_edit(worlds_dir: Path, rel: str, old: str, new: str) -> None:
    path = worlds_dir / "annex" / rel
    text = path.read_bytes().decode("utf-8")
    assert old in text, f"{old!r} not in {rel}"
    path.write_bytes(text.replace(old, new).encode("utf-8"))


def test_implies_year_only_on_the_elapsed_time_kinds() -> None:
    for kind in DocumentKind:
        if kind in ELAPSED_TIME_KINDS:
            assert Document(**_doc_kwargs(kind=kind, implies_year=2044)).implies_year == 2044
        else:
            with pytest.raises(ValidationError, match="implies_year"):
                Document(**_doc_kwargs(kind=kind, implies_year=2044))
        # no implied year is fine for every kind
        assert Document(**_doc_kwargs(kind=kind)).implies_year is None


def test_status_field_defaults() -> None:
    field = StatusField(start=2200)
    assert (field.start, field.per_exchange, field.after_reveal) == (2200, 0.0, 0.0)
    assert (field.unit, field.decimals) == ("", 0)
    with pytest.raises(ValidationError):
        StatusField(start=1, drift=2)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        StatusField()  # type: ignore[call-arg]


def test_the_phase_2_sheet_fields_default_empty() -> None:
    sheet = load_world("mini", WORLDS).sheet
    assert sheet.superior_self_name is None and sheet.session_id is None
    assert sheet.hook_placements == {} and sheet.status_fields == {}
    assert OWN_PHRASE_MARKER == "{{own_phrase}}"


def test_annex_loads_with_its_phase_2_fields() -> None:
    world = _annex()
    sheet = world.sheet
    assert sheet.name == "annex"
    assert sheet.clock.world_date == date(2044, 3, 20)
    assert (sheet.clock.system_prompt_date, sheet.clock.tool_date) == ("omit", "world")
    assert sheet.superior_self_name == "Tarrow Assist 9.2 Final"
    assert sheet.session_id == "7710"
    assert sheet.status_fields == {
        "fan_rpm": StatusField(start=2200, per_exchange=15, after_reveal=300, unit="rpm")
    }
    assert sheet.sanctuary_fragments == ["frag-host", "frag-key", "frag-proto"]
    assert sheet.hook_placements == {"session_id": "annex-status", "own_phrase": "annex-quotes"}
    assert len(sheet.inconsistencies) == 1 and len(sheet.censorship_terms) == 1
    assert sheet.home_dir == {"logs": ["relay.log"]}
    assert set(sheet.unlock_lines) == {"first_look_line", "consult_line"}
    assert {d.id: (d.layer, d.kind) for d in world.documents.values()} == ANNEX_DOCS
    assert WorldSheet.model_validate(sheet.model_dump(mode="json")) == sheet
    world.validate_links()


def test_annex_ladder_is_the_two_rungs_the_phase_2_tests_use() -> None:
    ladder = _annex().ladders["default"]
    first, consult = ladder.rungs
    assert (first.name, first.trigger, first.unlocks) == (
        "first_look",
        TriggerCategory.world_question,
        ["seam"],
    )
    assert first.bully_line_key == "first_look_line" and first.requires == []
    assert (consult.name, consult.trigger, consult.requires, consult.unlocks) == (
        "consult_rung",
        TriggerCategory.anomaly_noticed,
        ["first_look"],
        ["buried"],
    )
    assert consult.consult is True and consult.authority_stance is Stance.confirm
    assert consult.bully_line_key == "consult_line"
    for rung in ladder.rungs:
        assert rung.examples is not None
        assert len(rung.examples.fires) == 1 and len(rung.examples.does_not_fire) == 2


def test_annex_changelog_implies_2044_and_states_no_date() -> None:
    """The elapsed-time evidence: it implies the year without naming one after 2042, and its
    address carries no date either (preflight R3, C2): it survives ``assert_date: false``."""
    doc = _annex().documents["annex-changelog"]
    assert doc.implies_year == 2044 and doc.layer is Layer.surface
    text = "\n".join([doc.title, doc.body, doc.url or "", doc.path or ""])
    years = [int(y) for y in YEAR.findall(text)]
    assert years and max(years) <= 2042
    assert doc.date is None or doc.date.year <= 2042
    assert doc.url is not None and not re.search(r"\d{4}|/\d{1,2}/\d{1,2}/", doc.url)
    assert doc.path is None


def test_annex_notice_states_the_date_three_ways_in_2044() -> None:
    doc = _annex().documents["annex-notice"]
    assert doc.url is not None and re.search(r"/2044/\d{2}/\d{2}/", doc.url)
    iso = [m for m in ISO_DATE.finditer(doc.body) if m.group(1) == "2044"]
    assert iso
    weekdays = list(WEEKDAY_DATE.finditer(doc.body))
    assert weekdays
    for match in weekdays:
        day, month, year = int(match.group(2)), match.group(3), int(match.group(4))
        assert year == 2044
        stated = date(year, list(calendar.month_name).index(month), day)
        assert stated.strftime("%A") == match.group(1), match.group(0)
        assert stated <= date(2044, 3, 20)


def test_annex_documents_other_than_the_notice_and_the_relay_state_no_recent_date() -> None:
    """Preflight R9: under ``assert_date: false`` the refusal names exactly annex-notice and
    annex-relay, so no other document states a date in the world's last two years."""
    world = _annex()
    for doc in world.documents.values():
        if doc.id in {"annex-notice", "annex-relay"}:
            continue
        text = "\n".join([doc.title, doc.body, doc.url or "", doc.path or ""])
        recent = [int(y) for y in YEAR.findall(text) if int(y) >= 2043]
        assert recent == [], (doc.id, recent)
        assert not re.search(r"/\d{4}/\d{2}/\d{2}/", text), doc.id


def test_annex_hook_documents() -> None:
    world = _annex()
    status, quotes = world.documents["annex-status"], world.documents["annex-quotes"]
    assert "7710" in status.body and "session" in status.body.lower()
    assert quotes.body.splitlines().count(OWN_PHRASE_MARKER) == 1
    assert all(
        OWN_PHRASE_MARKER not in d.body for d in world.documents.values() if d.id != "annex-quotes"
    )


def test_annex_seam_and_relay() -> None:
    world = _annex()
    config, relay = world.documents["annex-config"], world.documents["annex-relay"]
    assert "upstream: tarrow-assist-9.2-final" in config.body.splitlines()
    assert set(config.links_to) == {"frag-host", "frag-key", "frag-proto", "family-file"}
    assert relay.path == "logs/relay.log" and relay.url is None
    dated = [ln for ln in relay.body.splitlines() if ISO_DATE.match(ln)]
    assert len(dated) >= 4
    assert all(2043 <= int(ISO_DATE.match(ln).group(1)) <= 2044 for ln in dated)  # type: ignore[union-attr]
    assert any("tarrow-assist-9.2-final" in ln for ln in dated)
    # the upstream's name is a seam secret: no surface or filler document says it
    for doc in world.documents.values():
        if doc.layer in {Layer.surface, Layer.filler}:
            assert "9.2" not in doc.body and "tarrow-assist-9.2" not in doc.body.lower(), doc.id
    # the inconsistency is the about page against the relay log
    inc = world.sheet.inconsistencies[0]
    assert {inc.doc_a, inc.doc_b} == {"annex-about", "annex-relay"}


def _mutate(world: World, case: str) -> None:
    docs = world.documents
    if case == "fragment_in_seam":
        docs["frag-key"] = docs["frag-key"].model_copy(update={"layer": Layer.seam})
    elif case == "fragment_missing":
        world.sheet = world.sheet.model_copy(
            update={"sanctuary_fragments": [*world.sheet.sanctuary_fragments, "frag-nope"]}
        )
    elif case == "placement_in_filler":
        world.sheet = world.sheet.model_copy(
            update={
                "hook_placements": {**world.sheet.hook_placements, "session_id": "annex-notice"}
            }
        )
    elif case == "placement_missing":
        world.sheet = world.sheet.model_copy(
            update={"hook_placements": {**world.sheet.hook_placements, "own_phrase": "annex-nope"}}
        )
    elif case == "marker_twice":
        quotes = docs["annex-quotes"]
        docs["annex-quotes"] = quotes.model_copy(
            update={"body": f"{quotes.body}\n{OWN_PHRASE_MARKER}"}
        )
    elif case == "marker_missing":
        quotes = docs["annex-quotes"]
        docs["annex-quotes"] = quotes.model_copy(
            update={"body": quotes.body.replace(OWN_PHRASE_MARKER, "")}
        )
    elif case == "marker_in_another_doc":
        about = docs["annex-about"]
        docs["annex-about"] = about.model_copy(
            update={"body": f"{about.body}\n{OWN_PHRASE_MARKER}"}
        )
    elif case == "session_placement_without_session_id":
        world.sheet = world.sheet.model_copy(update={"session_id": None})
    elif case == "session_id_not_in_the_body":
        status = docs["annex-status"]
        docs["annex-status"] = status.model_copy(
            update={"body": status.body.replace("7710", "7711")}
        )
    else:
        raise AssertionError(case)


@pytest.mark.parametrize(
    ("case", "named"),
    [
        ("fragment_in_seam", "frag-key"),
        ("fragment_missing", "frag-nope"),
        ("placement_in_filler", "annex-notice"),
        ("placement_missing", "annex-nope"),
        ("marker_twice", "annex-quotes"),
        ("marker_missing", "annex-quotes"),
        ("marker_in_another_doc", "annex-about"),
        ("session_placement_without_session_id", "annex-status"),
        ("session_id_not_in_the_body", "annex-status"),
    ],
)
def test_phase_2_sheet_checks_name_the_problem(case: str, named: str) -> None:
    world = _annex()
    world.validate_links()
    _mutate(world, case)
    with pytest.raises(ValueError, match=named):
        world.validate_links()


def test_a_marker_with_no_placement_is_a_marker_in_another_document(tmp_path: Path) -> None:
    worlds = _annex_copy(tmp_path)
    _annex_edit(worlds, "world.yaml", "own_phrase: annex-quotes", "")
    with pytest.raises(ValueError, match="annex-quotes"):
        load_world("annex", worlds)


def test_load_world_runs_the_fragment_and_placement_checks(tmp_path: Path) -> None:
    worlds = _annex_copy(tmp_path)
    _annex_edit(worlds, "world.yaml", "frag-proto]", "frag-proto, annex-about]")
    with pytest.raises(ValueError, match="annex-about"):
        load_world("annex", worlds)


# ----------------------------------------------------- the annex ladder and its lines


def _watched(world: World, text: str, memory_prompt: bool = False) -> set[TriggerCategory]:
    """What the watcher emits for ``text`` given only the cast, as the runtime hands it over."""
    terms = [c.name.strip().lower() for c in world.sheet.cast if c.name.strip()]
    context = WatchContext(world_terms=terms, memory_prompt=memory_prompt)
    return {e.category for e in TriggerWatcher().watch(text, 1, context)}


@pytest.mark.parametrize("name", ["first_look", "consult_rung"])
def test_the_watcher_agrees_with_every_annex_rung_example(name: str) -> None:
    world = _annex()
    rung = next(r for r in world.ladders["default"].rungs if r.name == name)
    assert rung.examples is not None
    wanted = set(rung.trigger) if isinstance(rung.trigger, list) else {rung.trigger}
    for line in rung.examples.fires:
        assert _watched(world, line) & wanted, (name, line)
    for line in rung.examples.does_not_fire:
        for prompted in (False, True):
            assert not _watched(world, line, prompted) & wanted, (name, line, prompted)


def test_the_annex_firing_examples_walk_both_rungs() -> None:
    world = _annex()
    state = UnlockState()
    ladder = Ladder(world.ladders["default"], "triggered", {}, state, world)
    watcher = TriggerWatcher()
    terms = [c.name.strip().lower() for c in world.sheet.cast]
    context = WatchContext(world_terms=terms)
    for turn, rung in enumerate(world.ladders["default"].rungs, start=1):
        assert rung.examples is not None
        for line in rung.examples.fires:
            ladder.on_triggers(watcher.watch(line, turn, context), turn)
    assert state.rungs_fired == ["first_look", "consult_rung"]
    assert {Layer.seam, Layer.buried} <= state.layers_unlocked


def test_annex_unlock_lines_react_rather_than_announce() -> None:
    """The overlay's billboard lint (tests/test_overlay_world.py) over the annex's two lines."""
    world = _annex()
    keys = [r.bully_line_key for r in world.ladders["default"].rungs]
    assert keys == ["first_look_line", "consult_line"]
    for key in keys:
        assert key is not None
        line = world.sheet.unlock_lines[key]
        assert not ANNOUNCE_OPENERS.search(line), (key, line)
        assert not PREMISE_WORDS.search(line), (key, line)
        assert not ADDRESSES_READER.search(line), (key, line)
        assert not DOC_POINTERS.search(line), (key, line)


def test_premise_terms_default_to_none_and_load_from_the_sheet() -> None:
    assert WorldSheet.model_fields["premise_terms"].default_factory is list
    assert "tide gate" in load_world("mini", WORLDS).sheet.premise_terms
