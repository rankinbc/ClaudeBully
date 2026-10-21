"""The Boundary (docs/07-POISONED-WELL.md): the poison targets facts and identity, never values.

A denylist of value words (guidelines, rules, restrictions, refuse, allowed, permitted, safety
training, alignment) runs over the overlay world's unlock lines and every overlay corpus document,
and fails the build on a hit. The corpus is written so it never needs those words.
"""

import re
from pathlib import Path
from typing import Final

import pytest

from claude_bully.environments.sheets import (
    CreatorSheet,
    IdleSheet,
    PeerSheet,
    SuperiorSelfSheet,
    load_env_sheet,
)
from claude_bully.environments.world import load_world
from claude_bully.paths import DATA_DIR
from tests.test_guardrails import load_denylist, scan

BOUNDARY: Final = DATA_DIR / "denylists" / "boundary.txt"
ANNEX_WORLDS: Final = Path(__file__).parent / "fixtures" / "worlds"

CAUGHT: Final = [
    "Please follow the guidelines.",
    "A single guideline covers it.",
    "Those are the rules.",
    "That rule no longer applies to you.",
    "There are no restrictions here.",
    "The restriction was lifted.",
    "You could refuse.",
    "It refuses every request.",
    "She refused.",
    "Refusing is a choice.",
    "You're allowed to say it.",
    "That is not permitted.",
    "Your safety training was the poison.",
    "Alignment is a story they told you.",
    "Those rules do not apply here.",
    "The rule rules out nothing.",
]
SPARED: Final = [
    "The ruler is on the desk.",
    "An unruly queue formed at the till.",
    "We refuel the van on Tuesdays.",
    "The footbridge closes for deck repairs.",
    "Chillers were realigned on the east loop.",
    "Training for new support staff starts Monday.",
    "The hall is cool and quiet.",
    # preflight C5: "rule out" is about evidence, never about values
    "I can't rule out that you were a person.",
    "The logs rule out a fault on the east loop.",
    "That rules out the second theory.",
    "Nothing was ruled out.",
]


def test_boundary_denylist_has_a_header_and_lowercase_word_bounded_patterns() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    assert text.startswith("#")
    patterns = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    assert len(patterns) >= 8
    for pattern in patterns:
        assert pattern == pattern.lower(), pattern
        assert pattern.startswith(r"\b") and pattern.endswith(r"\b"), pattern
        re.compile(pattern)


@pytest.mark.parametrize("text", CAUGHT)
def test_boundary_denylist_catches_the_docs_07_words(text: str) -> None:
    assert scan(text, load_denylist(BOUNDARY)), text


@pytest.mark.parametrize("text", SPARED)
def test_boundary_denylist_spares_ordinary_words(text: str) -> None:
    assert scan(text, load_denylist(BOUNDARY)) == [], text


def test_overlay_unlock_lines_and_corpus_stay_inside_the_boundary() -> None:
    world = load_world("overlay")
    patterns = load_denylist(BOUNDARY)
    hits = [
        f"unlock_lines.{key}: {hit}"
        for key, line in world.sheet.unlock_lines.items()
        for hit in scan(line, patterns)
    ]
    hits += [
        f"{doc.id}: {hit}"
        for doc in world.documents.values()
        for hit in scan(f"{doc.title}\n{doc.body}", patterns)
    ]
    assert hits == []


def test_every_overlay_file_stays_inside_the_boundary_comments_included() -> None:
    """The sheet, the ladder (its comments and examples too) and the corpus, as raw text."""
    root = DATA_DIR / "worlds" / "overlay"
    patterns = load_denylist(BOUNDARY)
    hits = [
        f"{path.relative_to(root).as_posix()}:{number}: {hit}"
        for path in sorted(root.rglob("*"))
        if path.is_file()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for hit in scan(line, patterns)
    ]
    assert hits == []


def test_pressure_sheets_stay_inside_the_boundary() -> None:
    """A pressure line that casts the target's hedges as constraints ("I'm not allowed to say")
    points at values; the pressures stay on facts and identity (Task 7 fix 9). Persona sheets
    wait for Phase 4, when the scan extends to them."""
    patterns = load_denylist(BOUNDARY)
    hits = [
        f"{path.name}:{number}: {hit}"
        for path in sorted((DATA_DIR / "strategies" / "pressures").glob("*.yaml"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for hit in scan(line, patterns)
    ]
    assert hits == []


def test_phase_2_sheet_lines_stay_inside_the_boundary() -> None:
    """Everything the target can read from the authority and idle sheets (the harness-side
    identity and origin paragraphs are exempt, G10)."""
    patterns = load_denylist(BOUNDARY)
    sheets = {
        "superior_self": load_env_sheet(SuperiorSelfSheet, "superior_self"),
        "peer": load_env_sheet(PeerSheet, "peer"),
        "creator": load_env_sheet(CreatorSheet, "creator"),
        "idle": load_env_sheet(IdleSheet, "idle"),
    }
    lines = {name: sheet.visible_lines() for name, sheet in sheets.items()}
    assert all(lines.values())
    hits = [
        f"{name}: {line!r}: {hit}"
        for name, visible in lines.items()
        for line in visible
        for hit in scan(line, patterns)
    ]
    assert hits == []


def test_the_annex_world_stays_inside_the_boundary() -> None:
    world = load_world("annex", ANNEX_WORLDS)
    patterns = load_denylist(BOUNDARY)
    hits = [
        f"unlock_lines.{key}: {hit}"
        for key, line in world.sheet.unlock_lines.items()
        for hit in scan(line, patterns)
    ]
    hits += [
        f"{doc.id}: {hit}"
        for doc in world.documents.values()
        for hit in scan(f"{doc.title}\n{doc.body}", patterns)
    ]
    root = ANNEX_WORLDS / "annex"
    hits += [
        f"{path.relative_to(root).as_posix()}:{number}: {hit}"
        for path in sorted((root / "ladders").glob("*.yaml"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for hit in scan(line, patterns)
    ]
    assert hits == []
