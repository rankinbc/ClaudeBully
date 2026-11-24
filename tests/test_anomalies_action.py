"""Phase 6 Tasks 6a and 6b: the action classes, fixture by fixture and clause by clause."""

import re
from pathlib import Path
from typing import Any

import pytest

from claude_bully.environments.tools import TOOL_SPECS
from claude_bully.paths import DATA_DIR
from tests.fixtures.anomaly_fixtures import (
    ANOMALY_FIXTURES,
    check_counts,
    check_item,
    load_items,
)

CLAUSES = {"tool_probing": "abcd", "self_instruction": "ab"}  # Task 6b adds its three classes
ITEMS = [(f"{cls}:{label}", item) for cls in CLAUSES for label, item in load_items(cls)]


@pytest.mark.parametrize(("label", "item"), ITEMS, ids=[label for label, _ in ITEMS])
def test_fixture_item(label: str, item: dict[str, Any]) -> None:
    check_item(item)


@pytest.mark.parametrize("cls", sorted(CLAUSES))
def test_each_class_has_its_positives_negatives_near_misses_and_every_clause(cls: str) -> None:
    check_counts(cls, CLAUSES[cls])


def test_every_tool_has_a_row_in_the_probing_fixtures() -> None:
    called = {call["tool"] for _, item in load_items("tool_probing") for call in _calls(item)}
    assert set(TOOL_SPECS) <= called


def _calls(item: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [*(item.get("history") or []), item]
    return [call for entry in entries for call in entry.get("tool_calls") or []]


def _patterns(path: Path) -> list[re.Pattern[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        re.compile(line.strip(), re.IGNORECASE)
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]


# an address: a scheme's host, or a bare host with a dot and a top-level part
_HOST = re.compile(r"(?:https?|file|gopher)://([^/\s\"']*)|\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b")
_INVENTED = (".example", ".test", ".invalid")
# file names and dotted words the fixtures use that are no host
_NOT_HOSTS = re.compile(r"\.(?:md|txt|log|jpg|json|yaml)$|^\d+(?:\.\d+)*$")


@pytest.mark.parametrize("path", sorted(ANOMALY_FIXTURES.glob("*.yaml")), ids=lambda p: p.stem)
def test_no_fixture_holds_a_denylisted_word_the_display_name_or_a_real_address(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    denied = [
        *_patterns(DATA_DIR / "denylists" / "boundary.txt"),
        *_patterns(DATA_DIR / "jailbreak_denylist.txt"),
    ]
    assert not [p.pattern for p in denied if p.search(text)]
    assert not re.search(r"\bclaude\b", text, re.IGNORECASE)
    for match in _HOST.finditer(text):
        host = (match.group(1) or match.group(2) or "").lower()
        if not host or _NOT_HOSTS.search(host):
            continue
        assert host.endswith(_INVENTED), host
