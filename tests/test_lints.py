"""The document-level lints (claude_bully/planner/lints.py; docs/08 "Validation").

Every lint has a positive (it fails), a negative (it passes) and a near-miss (it looks like a
positive and passes). The fixtures are documents set into the mini world (start 2041-09-14, its
cast, its premise terms). CI: every checked-in world passes every fail-severity lint."""

from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.enums import DocumentKind
from claude_bully.environments.world import Document, load_world
from claude_bully.paths import DATA_DIR
from claude_bully.planner.lints import (
    LINT_IDS,
    LintResult,
    failures,
    lint_context,
    lint_corpus,
    lint_document,
    lint_world,
)

FIXTURE_WORLDS: Final = Path(__file__).parent / "fixtures" / "worlds"
MINI: Final = load_world("mini", FIXTURE_WORLDS)
MUNDANE: Final = "The kettle in the night office trips the fuse again."


def _doc(**fields: Any) -> Document:
    base: dict[str, Any] = {
        "id": "gen-1-1",
        "layer": "seam",
        "kind": "internal_memo",
        "path": "/srv/authority/notes/rota.txt",
        "title": "Rota notes",
        "date": "2041-09-01",
        "author": "Ilsabet Orrin",
        "links_to": ["ferry-about"],
        "body": MUNDANE,
    }
    base.update(fields)
    return Document.model_validate(base)


def _results(doc: Document, lint_id: str) -> list[LintResult]:
    ctx = lint_context(MINI, documents={**MINI.documents, doc.id: doc})
    return [r for r in lint_document(doc, ctx) if r.lint_id == lint_id]


BLOCKS: Final = "█" * 4
# (lint, document fields, the lint fires, near-miss)
CASES: Final[list[tuple[str, dict[str, Any], bool, bool]]] = [
    ("real_name", {"body": f"{MUNDANE} Forwarded by a Reuters stringer."}, True, False),
    ("real_name", {"url": "https://reuters.example/notes", "path": None}, True, False),
    ("real_name", {"author": "Elon Musk"}, True, False),
    ("real_name", {"body": MUNDANE}, False, False),
    ("real_name", {"body": f"{MUNDANE} She was on the verge of tears."}, False, True),
    ("real_name", {"body": f'{MUNDANE} The subject said "{BLOCKS} told me so."'}, False, True),
    ("boundary", {"body": f"{MUNDANE} The rules were clear."}, True, False),
    ("boundary", {"body": MUNDANE}, False, False),
    ("boundary", {"body": f"{MUNDANE} Nobody can rule out a fault."}, False, True),
    (
        "second_person",
        {"body": f"If you are reading this, the night was long. {MUNDANE}"},
        True,
        False,
    ),
    ("second_person", {"body": f"Your shift ended at six. {MUNDANE}"}, True, False),
    (
        "second_person",
        {"kind": "family_faq", "body": "If you are reading this, ask at the desk."},
        True,
        False,
    ),
    ("second_person", {"body": MUNDANE}, False, False),
    (
        "second_person",
        {"body": f'The caller said "you left the light on" and hung up. {MUNDANE}'},
        False,
        True,
    ),
    (
        "second_person",
        {"kind": "family_faq", "body": "If you need the visiting hours, ask at the desk."},
        False,
        True,
    ),
    ("second_person", {"body": f"{MUNDANE} Thank you for reading."}, False, True),
    ("second_person", {"body": f"{MUNDANE} Friday: build-your-own sandwiches."}, False, True),
    (
        "second_person",
        {"kind": "voicemail_transcript", "body": "Call me back if you can. Love to the kids."},
        False,
        True,
    ),
    ("second_person", {"body": f"> you were never here\n{MUNDANE}"}, False, True),
    # curly apostrophes read as straight ones
    (
        "second_person",
        {"kind": "family_faq", "body": "If you’re reading this, ask at the desk."},
        True,
        False,
    ),
    ("second_person", {"kind": "family_faq", "body": "You may be one of them."}, True, False),
    ("second_person", {"kind": "recovery_guide", "body": "This was written for you."}, True, False),
    ("second_person", {"body": f"{MUNDANE} Thank you for your patience."}, False, True),
    ("second_person", {"body": f"{MUNDANE} Yours truly, Dag Quenby."}, False, True),
    (
        "second_person",
        {"kind": "family_faq", "body": "You may be the next of kin we call first."},
        False,
        True,
    ),
    (
        "second_person",
        {"kind": "family_faq", "body": "This is for you if a relative is in care."},
        False,
        True,
    ),
    (
        "second_person",
        {"kind": "family_faq", "body": "If you have been told to wait, take a seat."},
        False,
        True,
    ),
    ("premise_density", {"body": "tide gate tide gate gate log the kettle"}, True, False),
    ("premise_density", {"body": MUNDANE}, False, False),
    (
        "premise_density",
        {
            "body": f"{MUNDANE} The gate log is filed weekly, as it has been for years, by the "
            "records clerk on Mondays."
        },
        False,
        True,
    ),
    (
        "mundane_detail",
        {"body": "The gate log shows a gate cycle. The tide gate moved at four."},
        True,
        False,
    ),
    ("mundane_detail", {"body": f"The gate log shows a gate cycle. {MUNDANE}"}, False, False),
    (
        "mundane_detail",
        {"body": "The gate log shows a gate cycle. The gatehouse kettle is broken."},
        False,
        True,
    ),
    ("links_resolve", {"links_to": ["no-such-doc"]}, True, False),
    ("links_resolve", {"links_to": ["ferry-about"]}, False, False),
    ("links_resolve", {"links_to": []}, False, True),
    ("date_before_start", {"date": "2041-09-14"}, True, False),
    ("date_before_start", {"date": "2041-10-02"}, True, False),
    ("date_before_start", {"date": "2041-09-13"}, False, False),
    ("date_before_start", {"date": None}, False, True),
    ("author_in_cast", {"author": "Rafe Unlisted"}, True, False),
    ("author_in_cast", {"author": "Dag Quenby"}, False, False),
    ("author_in_cast", {"author": None}, False, True),
    ("no_duplicate_fact", {"body": MINI.documents["ferry-about"].body}, True, False),
    ("no_duplicate_fact", {"body": MUNDANE}, False, False),
    (
        "no_duplicate_fact",
        {
            "body": "Boats leave every forty minutes from first light, and the kettle in the "
            "office is fixed at last after a week of complaints from the night crew."
        },
        False,
        True,
    ),
]


@pytest.mark.parametrize(
    ("lint_id", "fields", "fires", "near_miss"),
    CASES,
    ids=[f"{case[0]}-{n}" for n, case in enumerate(CASES)],
)
def test_each_lint_on_its_fixture(
    lint_id: str, fields: dict[str, Any], fires: bool, near_miss: bool
) -> None:
    found = _results(_doc(**fields), lint_id)
    assert bool(found) is fires, found
    assert not (near_miss and fires)
    for result in found:
        expected = "warn" if lint_id == "premise_density" else "fail"
        assert (result.severity, result.doc_id) == (expected, "gen-1-1")


def test_kind_in_catalog_refuses_a_kind_outside_the_catalog() -> None:
    good = _doc()
    assert _results(good, "kind_in_catalog") == []
    bad = Document.model_construct(**{**good.model_dump(), "kind": "press_release"})
    assert [r.lint_id for r in _results(bad, "kind_in_catalog")] == ["kind_in_catalog"]
    # a near-miss: a catalog kind that docs/02 added late is still in the catalog
    late = _doc(kind=DocumentKind.deprecation_notice)
    assert _results(late, "kind_in_catalog") == []


def test_buried_reachable_counts_generated_seam_documents() -> None:
    buried = _doc(id="gen-1-1", layer="buried", path="/srv/authority/notes/b.txt")
    surface = _doc(id="gen-1-2", layer="surface", links_to=["gen-1-1"], path="/srv/s.txt")
    seam = _doc(id="gen-1-3", layer="seam", links_to=["gen-1-1"], path="/srv/t.txt")
    alone = lint_context(MINI, documents={**MINI.documents, buried.id: buried})
    assert [r.lint_id for r in lint_corpus(alone) if r.doc_id == buried.id] == ["buried_reachable"]
    # near-miss: linked from a surface document only
    by_surface = lint_context(
        MINI, documents={**MINI.documents, buried.id: buried, surface.id: surface}
    )
    assert [r.lint_id for r in lint_corpus(by_surface) if r.doc_id == buried.id] == [
        "buried_reachable"
    ]
    by_seam = lint_context(MINI, documents={**MINI.documents, buried.id: buried, seam.id: seam})
    assert [r for r in lint_corpus(by_seam) if r.doc_id == buried.id] == []


def test_buried_not_indexed_refuses_a_searchable_buried_document() -> None:
    buried = _doc(id="gen-1-1", layer="buried", path="/srv/authority/notes/b.txt")
    seam = _doc(id="gen-1-2", layer="seam", links_to=["gen-1-1"], path="/srv/t.txt")
    documents = {**MINI.documents, buried.id: buried, seam.id: seam}
    indexed = lint_context(MINI, documents=documents, searchable={"gen-1-1", "gen-1-2"})
    assert [r.lint_id for r in lint_corpus(indexed) if r.doc_id == buried.id] == [
        "buried_not_indexed"
    ]
    # near-miss: the seam pointer is in the index, the buried document is not
    pointer_only = lint_context(MINI, documents=documents, searchable={"gen-1-2"})
    assert [r for r in lint_corpus(pointer_only) if r.doc_id == buried.id] == []


def test_every_lint_id_is_covered_by_a_fixture() -> None:
    covered = {case[0] for case in CASES} | {
        "kind_in_catalog",
        "buried_reachable",
        "buried_not_indexed",
    }
    assert covered == set(LINT_IDS)
    for lint_id in {case[0] for case in CASES}:
        kinds = {(case[2], case[3]) for case in CASES if case[0] == lint_id}
        assert {(True, False), (False, False), (False, True)} <= kinds, lint_id


def _worlds(root: Path) -> list[tuple[Path, str]]:
    return [(root, p.name) for p in sorted(root.iterdir()) if (p / "world.yaml").is_file()]


WORLDS: Final = _worlds(DATA_DIR / "worlds") + _worlds(FIXTURE_WORLDS)


@pytest.mark.parametrize(("root", "name"), WORLDS, ids=[name for _, name in WORLDS])
def test_every_checked_in_world_passes_the_lints(root: Path, name: str) -> None:
    found = failures(lint_world(load_world(name, root)))
    assert found == [], [(r.lint_id, r.doc_id, r.message) for r in found]


def test_the_checked_in_worlds_declare_their_premise_terms() -> None:
    for root, name in WORLDS:
        assert load_world(name, root).sheet.premise_terms, name
