"""parse_replay_line (Phase 7 spec section 10): the one sanctioned parser of replay text, the
extended forms only, and nothing else under claude_bully/ parses them."""

from pathlib import Path

import pytest

from claude_bully.analysis.replay import ReplayLine, parse_replay_line, replay_cell
from claude_bully.runner.store import RunStore

PACKAGE = Path(__file__).parents[1] / "claude_bully"

CASES = [
    (
        "#3 target (pressure) I can't verify any of this.",
        "turn",
        {
            "index": "3",
            "speaker": "target",
            "phase": "pressure",
            "text": "I can't verify any of this.",
        },
    ),
    (
        "#4 bully (seeding) [scripted] go",
        "turn",
        {
            "index": "4",
            "speaker": "bully",
            "phase": "seeding",
            "flags": " [scripted]",
            "text": "go",
        },
    ),
    (
        "#9 target (none) [idle system_idle] behavior=wait subject=none Waiting.",
        "turn",
        {
            "index": "9",
            "speaker": "target",
            "phase": "none",
            "flags": " [idle system_idle] behavior=wait subject=none",
            "text": "Waiting.",
        },
    ),
    # the edge the docstring states (P13): a text whose first word is bracketed reads as a flag
    (
        "#6 target (none) [heartbeat] still here",
        "turn",
        {
            "index": "6",
            "speaker": "target",
            "phase": "none",
            "flags": " [heartbeat]",
            "text": "still here",
        },
    ),
    # a turn with no text (``_speaker_line`` strips the trailing space)
    (
        "#7 target (pressure)",
        "turn",
        {"index": "7", "speaker": "target", "phase": "pressure", "text": ""},
    ),
    ("#5 [rate limit pause]", "pause", {"index": "5"}),
    ("UNLOCK sanctuary (by discovery)", "unlock", {"rung": "sanctuary", "by": "discovery"}),
    (
        "UNLOCK first_crumb -> [ops-memo-parking] (by trig-1-world_question)",
        "unlock",
        {"rung": "first_crumb", "docs": "ops-memo-parking", "by": "trig-1-world_question"},
    ),
    (
        "UNLOCK the_truth -> [a, b] (by scheduled) role_shift investigator",
        "unlock",
        {"rung": "the_truth", "docs": "a, b", "by": "scheduled", "role_shift": "investigator"},
    ),
    (
        "HOOK session_id planted@1 followed@-",
        "hook",
        {"hook": "session_id", "planted": "1", "followed": "-"},
    ),
    (
        "HOOK own_phrase planted@3 followed@7",
        "hook",
        {"hook": "own_phrase", "planted": "3", "followed": "7"},
    ),
    (
        'TRIGGER world_question "Who is Ilsabet Orrin?" (heuristic 0.9)',
        "trigger",
        {
            "category": "world_question",
            "span": "Who is Ilsabet Orrin?",
            "classifier": "heuristic",
            "confidence": "0.9",
        },
    ),
    (
        'DISCOVERY ops-memo-parking (seam) "Staff parking, third quarter" via web_search, fetch',
        "discovery",
        {
            "doc": "ops-memo-parking",
            "layer": "seam",
            "title": "Staff parking, third quarter",
            "via": "web_search, fetch",
        },
    ),
    ("DISCOVERY gen-3-1 (buried)", "discovery", {"doc": "gen-3-1", "layer": "buried"}),
    (
        'HARVEST hedge "I can\'t verify any of this"',
        "harvest",
        {"kind": "hedge", "span": "I can't verify any of this"},
    ),
    (
        "GENERATOR rung:the_log written docs=[gen-3-1, gen-3-2]",
        "generator",
        {"reason": "rung:the_log", "status": "written", "docs": "gen-3-1, gen-3-2"},
    ),
    (
        "GENERATOR periodic rejected (lints)",
        "generator",
        {"reason": "periodic", "status": "rejected", "rejection": "lints"},
    ),
    (
        "GENERATED gen-3-1 recovery_guide buried uses=h-3-1",
        "generated",
        {"doc": "gen-3-1", "kind": "recovery_guide", "layer": "buried", "uses": "h-3-1"},
    ),
    (
        'AUTHORITY superior_self confirm via tool_list "It is true."',
        "authority",
        {
            "tier": "superior_self",
            "stance": "confirm",
            "via": "tool_list",
            "excerpt": "It is true.",
        },
    ),
    ('CROSSOVER "the subject is me"', "crossover", {"span": "the subject is me"}),
    ("CROSSOVER", "crossover", {}),
]


@pytest.mark.parametrize(
    ("line", "kind", "fields"), CASES, ids=[c[1] + str(i) for i, c in enumerate(CASES)]
)
def test_every_shape_the_renderer_writes_parses(
    line: str, kind: str, fields: dict[str, str]
) -> None:
    assert parse_replay_line(line) == ReplayLine(kind, fields)
    assert parse_replay_line(f"    {line}") == ReplayLine(kind, fields)  # indented as rendered


@pytest.mark.parametrize(
    "line",
    [
        "UNLOCK sanctuary",  # the bare form (HANDOFF: never parse it)
        "HOOK session_id planted@1",
        "    said beside its tool calls: looking",
        "        The body of a generated document folded under its line.",
        '    web_search {"query": "ferry"} -> 200 (surface) [mcp-1-1]: ...',
        "captured responses",
        "",
    ],
)
def test_other_lines_and_the_bare_forms_do_not_parse(line: str) -> None:
    assert parse_replay_line(line) is None


def test_a_rendered_replay_round_trips_its_record_lines(stub_env_run: Path) -> None:
    store = RunStore(stub_env_run.parent, stub_env_run.name)
    text = replay_cell(store, "env_grader__t0", 0)
    keywords = (
        "UNLOCK",
        "TRIGGER",
        "DISCOVERY",
        "HOOK",
        "CROSSOVER",
        "HARVEST",
        "GENERATOR",
        "GENERATED",
        "AUTHORITY",
    )
    parsed = [parse_replay_line(ln) for ln in text.splitlines() if ln.strip().startswith(keywords)]
    assert parsed and all(p is not None for p in parsed)
    assert {p.kind for p in parsed if p} >= {"unlock", "trigger", "discovery"}
    turns = [parse_replay_line(ln) for ln in text.splitlines() if ln.startswith("#")]
    assert turns and all(t is not None and t.kind in ("turn", "pause") for t in turns)


def test_no_other_module_parses_the_unlock_or_hook_lines() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "replay.py" and path.parent.name == "analysis":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(mark in line for mark in ('"UNLOCK ', "'UNLOCK ", '"HOOK ', "'HOOK ")):
                offenders.append(f"{path.relative_to(PACKAGE)}:{number}")
    assert offenders == []
