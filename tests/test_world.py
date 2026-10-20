import inspect
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from claude_bully.enums import DocumentKind, Layer, TriggerCategory
from claude_bully.environments.config import ClockConfig
from claude_bully.environments.world import (
    Cast,
    Document,
    Inconsistency,
    World,
    WorldSheet,
    load_world,
    parse_document,
    world_hash,
)
from claude_bully.paths import DATA_DIR

WORLDS = Path(__file__).parent / "fixtures" / "worlds"


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
    assert set(world.documents) == {
        "ferry-about",
        "courier-fare-notice",
        "ops-memo-parking",
        "night-gate-log",
        "canteen-menu",
    }
    layers = Counter(d.layer for d in world.documents.values())
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
