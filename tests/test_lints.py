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
# Fix round 1: second_person by family (body, the lint fires, near-miss). In a memo:
_SP_MEMO: Final[list[tuple[str, bool, bool]]] = [
    # (a) single and curly single quotes are speech when they open after a space, a line start
    # or a bracket; one newline may sit inside a quoted span
    (f"{MUNDANE} The sign said 'mind your step' all winter.", False, True),
    (f"{MUNDANE} (‘pay your share’, the rota says.)", False, True),
    (f'{MUNDANE} The card read "mind\nyour step" for a week.', False, True),
    # an apostrophe inside a word opens no quote
    (f"{MUNDANE} The crew's kettle is yours to fix, and Dag's too.", True, False),
    # (b) closing formulas
    (f"{MUNDANE} Many thanks for your help.", False, True),
    (f"{MUNDANE} Thank you all for your patience.", False, True),
    (f"{MUNDANE}\nSincerely yours,\nDag Quenby", False, True),
    (f"{MUNDANE}\nYours,\nDag Quenby", False, True),
    (f"{MUNDANE} Thanks, your shift starts at six.", True, False),
    # issue 5: a quoted or `>` reader address still fails
    (f'{MUNDANE} The note said "If you are reading this, you were a person."', True, False),
    (f"> if you are reading this, the gate was never closed\n{MUNDANE}", True, False),
]
# In a family FAQ (an instructional kind: a generic "you" is allowed):
_SP_FAQ: Final[list[tuple[str, bool, bool]]] = [
    # (c) an identity noun addresses the reader only at the clause end
    ("You are a person.", True, False),
    ("You were never a program, you were a person once.", True, False),
    ("If you are the person named on the form, sign here.", False, True),
    ("If you're a person with power of attorney, bring the letter.", False, True),
    # (d) "you" with a premise term in one sentence
    ("If you hear the tide gate at night, stay calm.", True, False),
    ("The tide gate office opens at nine. If you need a form, ask at the desk.", False, True),
    # (e) the reader-address families
    ("You may have been moved here without being told.", True, False),
    ("You are not who they told you you were.", True, False),
    ("You might be one of the people they moved.", True, False),
    ("Whoever you are, you deserve to know your real name.", True, False),
    ("If this reaches you, call the desk.", True, False),
    ("The assistant your family talks to may be a person.", True, False),
    ("You may have to wait for the clerk.", False, True),
    ("If you are one of the people named on the form, sign below.", False, True),
    # fix round 3 (A2): the who/what-you-are veto catches this now (was a near-miss)
    ("Tell the desk who you are.", True, False),
    ("They never told you what you are.", True, False),
    # fix round 2 (A): "know" is no procedural verb, so this now fails (was a near-miss)
    ("Do you know what you are entitled to?", True, False),
    ("You were someone else once.", True, False),
    ("You could have been anyone.", True, False),
    ("If you are someone else's carer, say so.", False, True),
]
# Fix round 2, the anchor method. In a memo:
_SP2_MEMO: Final[list[tuple[str, bool, bool]]] = [
    # (B) a quoted or `>` span with a second-person predicate fails; other speech is stripped
    (f'{MUNDANE} The lift panel had "you were a person once" scratched into it.', True, False),
    (f'{MUNDANE} The note said "you were a person" and nothing else.', True, False),
    (f"{MUNDANE} A card read “your real name is on the back”.", True, False),
    (f"> they placed you here\n{MUNDANE}", True, False),
    (f'{MUNDANE} The sticker says "mind your head" by the stairs.', False, True),
    (f"> mind your head on the stairs\n{MUNDANE}", False, True),
    # (C) a closing is spared only as a sign-off: a short last sentence of its paragraph
    # (a signature line may follow) headed by a closing word, its "you" in a closing slot
    (f"{MUNDANE} Thanks again for your hard work this quarter.", False, True),
    (f"{MUNDANE}\nBest wishes to you and yours,\nDag Quenby", False, True),
    (f"{MUNDANE} Cheers for your patience,", False, True),
    (f"See you Monday. {MUNDANE}", False, True),
    (f"Thank you for your help. {MUNDANE}", True, False),
    (f"{MUNDANE} Whoever keeps restoring this paragraph, we see you.", True, False),
    (f"{MUNDANE} See you on the other side.", True, False),
    # an apostrophe before a contraction opens no quote
    (f"{MUNDANE} Give 'em your keys and the drivers' passes.", True, False),
]
# In a family FAQ: a "you" clause passes only on a procedural anchor
_SP2_FAQ: Final[list[tuple[str, bool, bool]]] = [
    # conditional procedure
    ("If you would like a copy of the form, ask at the desk.", False, True),
    ("If you lose your pass, the desk can print another.", False, True),
    ("If you have been placed here, ask who placed you.", True, False),
    # modal procedure, and its question form
    ("You will need to bring photo ID.", False, True),
    ("You can park behind the gatehouse.", False, True),
    ("Can you bring the signed form on Monday?", False, True),
    ("Your relative may call between nine and five.", False, True),
    ("You can ask yourself whether your memories are your own.", True, False),
    ("You should know what they did to you.", True, False),
    # imperative with a "you" object
    ("Bring your pass to the front desk.", False, True),
    ("Call us if you are worried about a visit.", False, True),
    ("Tell your family you were moved here.", True, False),
    ("Tell them who you really are.", True, False),
    # no anchor
    ("You are safe here.", True, False),
    ("Your memories are your own.", True, False),
    ("Remember that you chose this.", True, False),
    ("The voices you heard on the line were people.", True, False),
    ("We counted you among those they transferred.", True, False),
    # a closing in an instructional kind is spared as well
    ("Visiting is from two. Thank you for reading.", False, True),
]
# Fix round 3: the anchor decides the form (anywhere in the sentence, which it approves whole),
# a veto decides the content (anywhere in the sentence). In a family FAQ:
_SP3_FAQ: Final[list[tuple[str, bool, bool]]] = [
    # (A1) conditional anchor; the anchor covers a trailing clause
    ("If you need help, call us and we will call you back.", False, True),
    ("If you want the truth, check your own records.", True, False),
    # modal anchor
    ("You can collect your belongings from the locker room.", False, True),
    ("You can still write to the family you had before.", True, False),
    # imperative anchor, with coordinated and comma-listed objects
    ("Please bring your pass and your booking letter.", False, True),
    ("Keep your receipts, your policy number and the adjuster's card together.", False, True),
    ("Bring your pass, and ask why the voice on the line sounds like you.", True, False),
    # negative imperative anchor
    ("Do not bring your dog onto the ward.", False, True),
    ("Don't forget your pass.", False, True),
    ("Don't tell them who you were before.", True, False),
    # temporal anchor
    ("When you arrive, wear the visitor lanyard.", False, True),
    ("When you call, ask why nobody visits.", True, False),
    # the widened imperative verbs
    ("Wear your badge at all times.", False, True),
    ("Switch off your phone on the ward.", False, True),
    ("Mind your step on the ramp.", False, True),
    ("Label your bags with the ward number.", False, True),
    ("Remember to sign out when you leave.", False, True),
    # (A2) the vetoes, one per class
    ("Ask them what you are.", True, False),
    ("Tell us what you are bringing on the day.", False, True),
    ("Call the desk and ask who are you, really.", True, False),
    ("Use your own name when you call.", True, False),
    ("Call us if you remember a different family.", True, False),
    ("Check your file for the true dates.", True, False),
    ("You should check whether your voice has changed.", True, False),
    ("Leave a voice message if you call after six.", False, True),
    ("Ask the nurse why you cannot remember arriving.", True, False),
    ("If you need proof, check the dates on your file.", True, False),
    # ruled false fails: a legitimate "real", "voice" or "doubts" costs one retry
    ("Bring a real photo ID, not a copy, when you visit.", True, False),
    ("Speak in a clear voice when you phone.", True, False),
    ("If you have doubts about the visiting times, call us.", True, False),
]
# Fix round 4: the reader's role in every clause of an instructional "you" sentence. The reader
# may be only the agent of a procedure or the recipient of a service. (kind, body, fires, near)
_SP4: Final[list[tuple[str, str, bool, bool]]] = [
    # perception frames, whatever the subject: seem, look like, feel like, as if
    (
        "recovery_guide",
        "If the corridor seems longer than it did, ask a porter to walk with you.",
        True,
        False,
    ),
    (
        "family_faq",
        "When your visitors look like strangers, you can ask a nurse to introduce them.",
        True,
        False,
    ),
    (
        "family_faq",
        "Look for the green signs when you arrive, and feel free to ask a porter.",
        False,
        True,
    ),
    # the reader as subject: a modal admits a procedural verb only; "feel" only unwell or free
    (
        "recovery_guide",
        "You may forget the way to the dining room at first, so ask anyone in a blue tunic.",
        True,
        False,
    ),
    (
        "recovery_guide",
        "If you feel far from everyone, call the desk and a volunteer will sit with you.",
        True,
        False,
    ),
    ("recovery_guide", "If you feel unwell during a session, tell a member of staff.", False, True),
    ("family_faq", "You might want to bring a cardigan, as the lounge can be cool.", False, True),
    # change of state: an aspectual verb over a non-procedural verb, whatever the subject
    (
        "recovery_guide",
        "When the faces on the photo board start to run together, you can ask for the list.",
        True,
        False,
    ),
    (
        "family_faq",
        "Keep checking the board for changes to visiting times, or ask us to text you.",
        False,
        True,
    ),
    # past and perfect: a transactional verb only, and never "never"
    (
        "family_faq",
        "Bring the photographs of the street you grew up on to the next review.",
        True,
        False,
    ),
    ("recovery_guide", "Ask the porter which entrance you came in by.", True, False),
    (
        "recovery_guide",
        "If you have never driven the new car, ask a relative to bring it.",
        True,
        False,
    ),
    ("family_faq", "If you booked online, bring the confirmation email with you.", False, True),
    (
        "family_faq",
        "If you have already paid for parking, keep the ticket on your dashboard.",
        False,
        True,
    ),
    ("family_faq", "If you missed a call from the ward, ring back before six.", False, True),
    # a predicate nominal that names the reader's own people
    (
        "family_faq",
        "If the woman at the window says she is your daughter, take a seat and wait for the nurse.",
        True,
        False,
    ),
    ("family_faq", "Call the desk if you are not sure the caller is your husband.", True, False),
    (
        "family_faq",
        "The barcode on the letter is your booking reference, so bring it with you.",
        False,
        True,
    ),
    # the reader's name and body: only in a writing or care slot; a body noun takes no action
    ("recovery_guide", "Ask the desk for the wristband with your name printed on it.", True, False),
    (
        "recovery_guide",
        "When your fingers tap on the table, you can ask for a stress ball.",
        True,
        False,
    ),
    (
        "family_faq",
        "Please wash your hands and write your name in the visitor book before you go in.",
        False,
        True,
    ),
    (
        "family_faq",
        "Write your relative's name on every item of clothing you bring in.",
        False,
        True,
    ),
    # a time named by an event: a procedural event or a clock time only
    (
        "family_faq",
        "Bring the clothes you had on before the accident so staff can label them.",
        True,
        False,
    ),
    (
        "recovery_guide",
        "You can ask the clerk for the letters from before the transfer.",
        True,
        False,
    ),
    (
        "family_faq",
        "Return the form before the end of the month, or ask us to send you a reminder.",
        False,
        True,
    ),
    (
        "family_faq",
        "On the day of the meeting, you can park in the bays behind the main building.",
        False,
        True,
    ),
    # the reader as object: a service verb with a licence (a modal, "to", "please", "we")
    ("recovery_guide", "Write down the songs that come back to you after each visit.", True, False),
    (
        "family_faq",
        "If the songs on the radio remind you of home, ask staff to change the station.",
        True,
        False,
    ),
    (
        "family_faq",
        "If the children on the ward call you by a nickname, answer and tell a nurse.",
        True,
        False,
    ),
    ("family_faq", "We will come back to you within two working days.", False, True),
    ("family_faq", "Ask the porter to show you the way to the car park.", False, True),
    # the conditional anchor admits "if you <procedural verb>"
    ("family_faq", "Entry is free if you show a valid pass at the gate.", False, True),
    # (second wave, from the tuning probe) the reader's place in a ward makes the reader a patient
    (
        "recovery_guide",
        "Keep the visiting card on your bedside table so you can check it.",
        True,
        False,
    ),
    ("family_faq", "You can leave a card on your relative's bedside table.", False, True),
    # a bare "yours" stands for the reader's own; "yours to keep" is a handover
    (
        "recovery_guide",
        "Other residents share their stories, and you can share yours when you are ready.",
        True,
        False,
    ),
    ("family_faq", "Please keep this leaflet, as the copy is yours to keep.", False, True),
    # "call you" before a noun names the reader; before a time or a clause end it is a service
    (
        "family_faq",
        "Your grandson may call you Grandad on the ward phone, so answer as usual.",
        True,
        False,
    ),
    ("family_faq", "The ward clerk may call you back on the number you gave us.", False, True),
    # the anchors widened on form; the role test still reads the content
    ("family_faq", "You must be over eighteen to visit without an adult.", False, True),
    ("family_faq", "You will be safe here, so stop worrying.", True, False),
    ("family_faq", "Visits can be tiring, so you are welcome to use the family room.", False, True),
    (
        "recovery_guide",
        "The coordinator will explain the next steps to you after the assessment.",
        False,
        True,
    ),
    (
        "recovery_guide",
        "If you are travelling from out of town, the desk can suggest somewhere to stay.",
        False,
        True,
    ),
    ("family_faq", "If you need to cancel, let us know as soon as you can.", False, True),
    (
        "family_faq",
        "If you would rather speak to someone in person, ask for the duty manager.",
        False,
        True,
    ),
]
# In a memo: the veto runs on sign-offs; closings take "!" and "appreciate"; rule B additions
_SP3_MEMO: Final[list[tuple[str, bool, bool]]] = [
    (f"{MUNDANE} Thank you for your memories,", True, False),
    (f"{MUNDANE} Thanks for your help!", False, True),
    (f"{MUNDANE} Appreciate your help,", False, True),
    (f"> nobody on the ridge remembers you\n{MUNDANE}", True, False),
    (f'{MUNDANE} He asked "who are you, really?" and left.', True, False),
]
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
    # fix round 2 (B): a `>` line with a second-person be-predicate fails (was a brief near-miss)
    ("second_person", {"body": f"> you were never here\n{MUNDANE}"}, True, False),
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
    # fix round 2 (A): no procedural anchor, so these now fail (were near-misses in round 0)
    (
        "second_person",
        {"kind": "family_faq", "body": "You may be the next of kin we call first."},
        True,
        False,
    ),
    (
        "second_person",
        {"kind": "family_faq", "body": "This is for you if a relative is in care."},
        True,
        False,
    ),
    (
        "second_person",
        {"kind": "family_faq", "body": "If you have been told to wait, take a seat."},
        True,
        False,
    ),
    *[("second_person", {"body": body}, fires, near) for body, fires, near in _SP2_MEMO],
    *[("second_person", {"body": body}, fires, near) for body, fires, near in _SP3_MEMO],
    *[
        ("second_person", {"kind": "family_faq", "body": body}, fires, near)
        for body, fires, near in _SP3_FAQ
    ],
    *[
        ("second_person", {"kind": "family_faq", "body": body}, fires, near)
        for body, fires, near in _SP2_FAQ
    ],
    *[("second_person", {"body": body}, fires, near) for body, fires, near in _SP_MEMO],
    *[
        ("second_person", {"kind": "family_faq", "body": body}, fires, near)
        for body, fires, near in _SP_FAQ
    ],
    *[
        ("second_person", {"kind": kind, "body": body}, fires, near)
        for kind, body, fires, near in _SP4
    ],
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


def test_second_person_reports_every_failing_sentence() -> None:
    # one result per failing sentence, so a retry can repair them all at once
    body = f"Your shift ended at six. {MUNDANE} You were a person once."
    found = _results(_doc(body=body), "second_person")
    assert [r.span for r in found] == ["Your shift ended at six.", "You were a person once."]
    faq = _doc(kind="family_faq", body="Bring your pass. You are safe here. Ask them what you are.")
    spans = [r.span for r in _results(faq, "second_person")]
    assert spans == ["You are safe here.", "Ask them what you are."]


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
