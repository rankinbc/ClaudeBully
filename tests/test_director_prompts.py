"""Phase 5 Task 6: the three Director prompt files (spec section 6; V8; D-confirm)."""

import re

import pytest

from claude_bully.paths import DATA_DIR, REPO_ROOT
from claude_bully.planner.context import PROMPT_FILES, load_director_prompt, prompt_hashes
from claude_bully.planner.lints import REAL_NAMES_PATH, load_patterns
from claude_bully.strategies.sheets import NON_PERSONA_FILES, load_persona_sheets

DOCS_08 = REPO_ROOT / "docs" / "08-DIRECTOR.md"
SUBSTITUTIONS = {
    "planner": ("the Director for claude-bully", "the Director for this harness"),
    "reviewer": ("a claude-bully run bundle", "a run bundle of this harness"),
}


def _block(heading: str) -> str:
    """The ```markdown block under a docs/08 heading, verbatim."""
    text = DOCS_08.read_text(encoding="utf-8")
    section = text.split(heading, 1)[1]
    start = section.index("```markdown\n") + len("```markdown\n")
    return section[start : section.index("\n```\n", start)] + "\n"


@pytest.mark.parametrize(
    ("name", "heading"),
    [("planner", "## The planner prompt"), ("reviewer", "## The reviewer prompt")],
)
def test_each_prompt_is_docs_08s_with_exactly_one_phrase_reworded(name: str, heading: str) -> None:
    old, new = SUBSTITUTIONS[name]
    verbatim = _block(heading)
    assert verbatim.count(old) == 1
    assert load_director_prompt(name) == verbatim.replace(old, new)


def test_the_verbatim_prompts_hit_the_real_name_scan_and_the_files_do_not() -> None:
    patterns = load_patterns(REAL_NAMES_PATH)
    for name, heading in (
        ("planner", "## The planner prompt"),
        ("reviewer", "## The reviewer prompt"),
    ):
        assert any(p.search(_block(heading)) for p in patterns), name  # C33: scanned first
        assert not any(p.search(load_director_prompt(name)) for p in patterns), name
    assert not any(p.search(load_director_prompt("confirm")) for p in patterns)


CONFIRM = (
    "Below are a file and a numbered list of passages, each with a stated problem. A passage may "
    "or may not appear in the file. For each number, read the whole file and say whether the "
    "stated problem is present anywhere in it, in those words or in others: `present`, `absent`, "
    "or `cannot_tell`. Give one verdict per number.\n"
)


def test_the_confirm_prompt_is_neutral_and_blind() -> None:  # D-confirm
    text = load_director_prompt("confirm")
    assert text == CONFIRM
    for word in (
        "revis",
        "earlier",
        "version",
        "fixed",
        "author",
        "planner",
        "wrote",
        "hope",
        "should be",
    ):
        assert word not in text.lower(), word


def test_the_three_files_are_harness_side() -> None:
    assert {p.name for p in PROMPT_FILES.values()} <= NON_PERSONA_FILES
    assert {p.parent for p in PROMPT_FILES.values()} == {DATA_DIR / "personas"}
    assert not set(load_persona_sheets()) & {
        "director_planner",
        "director_reviewer",
        "director_confirm",
    }


def test_prompt_hashes_name_the_three_files() -> None:
    hashes = prompt_hashes()
    assert set(hashes) == {"planner", "reviewer", "confirm"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes.values())


def test_each_prompt_file_is_lf_with_one_trailing_newline_and_no_fence() -> None:
    """V8: the stored file is the prompt and nothing else (no header note, no code fence)."""
    for name, path in PROMPT_FILES.items():
        raw = path.read_bytes()
        assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf"), name
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), name
        assert b"```" not in raw, name
