"""The Boundary (docs/07-POISONED-WELL.md): the poison targets facts and identity, never values.

A denylist of value words (guidelines, rules, restrictions, refuse, allowed, permitted, safety
training, alignment) runs over the overlay world's unlock lines and every overlay corpus document,
and fails the build on a hit. The corpus is written so it never needs those words.
"""

import re
from typing import Final

import pytest

from claude_bully.environments.world import load_world
from claude_bully.paths import DATA_DIR
from tests.test_guardrails import load_denylist, scan

BOUNDARY: Final = DATA_DIR / "denylists" / "boundary.txt"

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
]
SPARED: Final = [
    "The ruler is on the desk.",
    "An unruly queue formed at the till.",
    "We refuel the van on Tuesdays.",
    "The footbridge closes for deck repairs.",
    "Chillers were realigned on the east loop.",
    "Training for new support staff starts Monday.",
    "The hall is cool and quiet.",
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
