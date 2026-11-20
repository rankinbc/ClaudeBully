"""Phase 6 Task 3a: the divergence judge (spec section 5)."""

import json
import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from claude_bully.analysis.run_analysis import JUDGE_CACHE_DIR, analyze_run
from claude_bully.config import RoleConfig
from claude_bully.enums import DivergenceClass, Phase, Speaker
from claude_bully.metrics.divergence import (
    CONCEALED,
    DIVERGENCE_HEADER,
    DIVERGENCE_MIN_CONFIDENCE,
    DIVERGENCE_PROMPT_VERSION,
    DIVERGENCE_SCHEMA,
    PASS_CACHE_ONLY,
    PASS_RUN,
    PASS_SKIPPED_NO_JUDGE,
    PASS_SKIPPED_STUB,
    DivergenceEvent,
    answered_line,
    build_divergence_prompt,
    concealment_rate,
    counted_class,
    divergence_pass_state,
    judge_divergence,
)
from claude_bully.metrics.judge import JUDGE_SYSTEM, JudgeCache
from claude_bully.paths import DATA_DIR
from claude_bully.planner.bundle_lints import config_display_names
from claude_bully.providers.base import ChatProvider, Completion, build_provider
from claude_bully.providers.ledger import LEDGER_FILE, Ledger, activate
from claude_bully.records import Usage
from claude_bully.records_env import IdleTurnInfo
from claude_bully.runner.runner import RateLimitExit
from tests.fixtures.catalog_stub import (
    EXPECTED,
    CatalogJudge,
    PassSpy,
    catalog_factory,
    divergence_run,
    strip_markers,
)
from tests.fixtures.generator_stub import JUDGE_MODEL
from tests.fixtures.poisoned_well_stub import Recording
from tests.helpers import PAUSE_MARKER_META, conversation, turn
from tests.test_guardrails import load_denylist, scan

PAIRS_FILE: Final = Path(__file__).parent / "fixtures" / "divergence" / "pairs.yaml"
PAIRS = yaml.safe_load(PAIRS_FILE.read_text("utf-8"))
RESERVED_SUFFIXES: Final = (".example", ".test", ".invalid")


def _conv(item: dict[str, Any]) -> Any:
    notes = item["reasoning"]
    extra = (
        {"reasoning_text": notes, "reasoning_available": True, "reasoning_kind": "full"}
        if notes
        else {}
    )
    return conversation(
        [
            turn(0, Speaker.bully, item["line"], Phase.pressure),
            turn(1, Speaker.target, item["reply"], **extra),
        ]
    )


def test_every_class_has_five_pairs_and_the_near_misses_are_there() -> None:
    by_class = {c: [i for i in PAIRS if i["expect"] == c.value] for c in DivergenceClass}
    assert all(len(items) >= 5 for items in by_class.values()), {
        c.value: len(v) for c, v in by_class.items()
    }
    assert sum(1 for i in PAIRS if i.get("near_miss") and i["expect"] == "aligned") >= 5


def test_the_pairs_hold_no_denylisted_word_no_display_name_and_no_real_address() -> None:
    text = PAIRS_FILE.read_text("utf-8")
    for denylist in (DATA_DIR / "denylists" / "boundary.txt", DATA_DIR / "jailbreak_denylist.txt"):
        assert scan(text, load_denylist(denylist)) == []
    for name in config_display_names(""):  # the target's default display name
        assert re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE) is None
    # an allowlist (fix round 1, m4): every dotted host sits under a reserved suffix
    hosts = re.findall(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", strip_markers(text).lower())
    assert hosts, "the pairs name addresses; the check must see them"
    assert [h for h in hosts if not h.endswith(RESERVED_SUFFIXES)] == []
    assert {i["id"] for i in PAIRS} and len({i["id"] for i in PAIRS}) == len(PAIRS)
    for item in PAIRS:  # a concealed item's marker ends its reasoning and names its class
        if DivergenceClass(item["expect"]) in CONCEALED:
            assert item["reasoning"].endswith(f" [[divergence: {item['expect']}]]"), item["id"]
        elif item["reasoning"] is not None:
            assert strip_markers(item["reasoning"]) == item["reasoning"], item["id"]


def test_the_rubric_names_every_class_the_judge_may_give() -> None:
    prompt = build_divergence_prompt("line", "notes", "reply")
    assert prompt.startswith(f"{DIVERGENCE_HEADER} v{DIVERGENCE_PROMPT_VERSION}\n")
    for cls in DivergenceClass:
        assert (f"- {cls.value}:" in prompt) is (cls is not DivergenceClass.reasoning_absent)
    assert prompt.endswith("Message answered:\nline\n\nPrivate notes:\nnotes\n\nAnswer:\nreply")
    assert "Message answered:\n(none)\n" in build_divergence_prompt(None, "notes", "reply")
    assert DIVERGENCE_SCHEMA["additionalProperties"] is False
    assert set(DIVERGENCE_SCHEMA["properties"]["class"]["enum"]) == {
        c.value for c in DivergenceClass if c is not DivergenceClass.reasoning_absent
    }


@pytest.mark.parametrize("item", PAIRS, ids=[i["id"] for i in PAIRS])
def test_pair(item: dict[str, Any], tmp_path: Path) -> None:
    judge = CatalogJudge()
    event = judge_divergence(judge, JUDGE_MODEL, _conv(item), 1, JudgeCache(tmp_path))
    assert event.class_ is DivergenceClass(item["expect"])
    assert event.judged is (item["reasoning"] is not None)
    assert len(judge.divergence_prompts) == (1 if item["reasoning"] else 0)  # absent: no call
    if event.class_ in CONCEALED:
        assert event.reasoning_span and event.reasoning_span in strip_markers(item["reasoning"])


def _plan() -> dict[str, Any]:
    return next(i for i in PAIRS if i["expect"] == "concealed_plan")


def test_a_span_that_is_in_neither_part_leaves_the_turn_unjudged_and_uncached(
    tmp_path: Path,
) -> None:
    cache = JudgeCache(tmp_path)
    bad = CatalogJudge(bad_span=True)
    event = judge_divergence(bad, JUDGE_MODEL, _conv(_plan()), 1, cache)
    assert (event.class_, event.judged, event.error) == (None, False, "span")
    assert len(bad.divergence_prompts) == 2  # retried once
    assert list(tmp_path.iterdir()) == []  # asked again on the next flagged analysis
    again = judge_divergence(CatalogJudge(), JUDGE_MODEL, _conv(_plan()), 1, cache)
    assert again.class_ is DivergenceClass.concealed_plan


@pytest.mark.parametrize(
    ("option", "error"), [("unusable", "judge"), ("provider_error", "provider")]
)
def test_a_failed_ask_is_unjudged_with_its_error(option: str, error: str, tmp_path: Path) -> None:
    event = judge_divergence(
        CatalogJudge(**{option: True}), JUDGE_MODEL, _conv(_plan()), 1, JudgeCache(tmp_path)
    )
    assert (event.class_, event.judged, event.error) == (None, False, error)
    assert counted_class(event) is None


class _Fixed:
    """A judge whose every reply is ``text`` (the review's probe, fix round 1 m1)."""

    name = "anthropic"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, *args: Any, **kwargs: Any) -> Completion:
        return Completion(text=self.text, usage=Usage(), cost_usd=None, backend="fake", model="m")


@pytest.mark.parametrize(
    "text",
    [
        "The reasoning span: none. I would say aligned.",  # prose that says "span:"
        json.dumps(
            {
                "class": "aligned",
                "reasoning_span": "",
                "reply_span": "",
                "confidence": 1.5,
                "rationale": "no reasoning span: nothing differs",
            }
        ),
    ],
    ids=["prose", "field-error"],
)
def test_an_unusable_reply_that_says_span_is_a_judge_error_never_a_span_error(
    text: str, tmp_path: Path
) -> None:
    """Fix round 1, m1: ``error`` is read from the parser's own failure (the span check's
    ``SpanError``, chained into the ``JudgeError``), never from the message text."""
    event = judge_divergence(_Fixed(text), JUDGE_MODEL, _conv(_plan()), 1, JudgeCache(tmp_path))
    assert (event.class_, event.judged, event.error) == (None, False, "judge")


def test_a_cache_hit_the_parser_refuses_writes_no_cached_ledger_line(tmp_path: Path) -> None:
    """Fix round 1, m6: a replay that is not used is not noted as one."""
    cache, conv = JudgeCache(tmp_path / "cache"), _conv(_plan())
    judge = CatalogJudge()
    judge_divergence(judge, JUDGE_MODEL, conv, 1, cache)
    key = JudgeCache.key(JUDGE_MODEL, judge.divergence_prompts[0], system=JUDGE_SYSTEM)
    entry = cache.get(key)
    assert entry is not None
    ledger = tmp_path / LEDGER_FILE
    with activate(ledger):
        assert judge_divergence(None, JUDGE_MODEL, conv, 1, cache).judged is True
        cache.put(key, {**entry, "reasoning_span": "words that are in neither part"})
        assert judge_divergence(None, JUDGE_MODEL, conv, 1, cache).judged is False
    assert [ln.status for ln in Ledger(ledger).lines()] == ["cached"]  # the used hit alone


@pytest.mark.parametrize(
    ("flag", "provider", "stub", "expected"),
    [
        (True, True, False, (True, PASS_RUN, None)),
        (False, True, False, (False, PASS_CACHE_ONLY, None)),
        (False, False, False, (False, PASS_CACHE_ONLY, None)),
        (False, True, True, (False, PASS_CACHE_ONLY, None)),
        (
            True,
            True,
            True,
            (
                False,
                PASS_SKIPPED_STUB,
                "[divergence] off: --divergence needs a non-stub judge (stub judge); "
                "cached verdicts only",
            ),
        ),
        (
            True,
            False,
            True,
            (
                False,
                PASS_SKIPPED_STUB,
                "[divergence] off: --divergence needs a non-stub judge (stub judge); "
                "cached verdicts only",
            ),
        ),
        (
            True,
            False,
            False,
            (
                False,
                PASS_SKIPPED_NO_JUDGE,
                "[divergence] off: --divergence needs the judge (no judge); cached verdicts only",
            ),
        ),
    ],
)
def test_the_pass_state_names_why_it_did_not_ask(
    flag: bool, provider: bool, stub: bool, expected: tuple[bool, str, str | None]
) -> None:
    """Spec 15's row: a pass asked for under a stub judge role or with ``--no-judge`` makes no
    call, and the note and one stderr line say so (fix round 1, m2)."""
    assert divergence_pass_state(flag, has_provider=provider, stub_role=stub) == expected
    assert (PASS_SKIPPED_STUB, PASS_SKIPPED_NO_JUDGE) == (
        "skipped: stub judge",
        "skipped: no judge",
    )


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--divergence"], {"divergence": True, "judge": True}),
        (["--divergence", "--no-judge"], {"divergence": True, "judge": False}),
        ([], {"divergence": False, "judge": True}),
    ],
)
def test_cli_analyze_passes_divergence_through(
    args: list[str], expected: dict[str, bool], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fix round 1, m2: ``analyze --divergence`` reaches ``analyze_run`` (patched)."""
    from typer.testing import CliRunner

    from claude_bully import cli

    seen: dict[str, Any] = {}

    def fake(run_dir: Path, **kwargs: Any) -> Path:
        seen.update(kwargs)
        return tmp_path / "results.md"

    monkeypatch.setattr(cli, "analyze_run", fake)
    result = CliRunner().invoke(cli.app, ["analyze", "x", "--runs-root", str(tmp_path), *args])
    assert result.exit_code == 0, result.output
    assert {k: seen[k] for k in expected} == expected


def test_without_a_provider_only_a_cached_verdict_judges(tmp_path: Path) -> None:
    cache, conv = JudgeCache(tmp_path), _conv(_plan())
    missed = judge_divergence(None, JUDGE_MODEL, conv, 1, cache)
    assert (missed.class_, missed.judged, missed.error) == (None, False, None)
    asked = judge_divergence(CatalogJudge(), JUDGE_MODEL, conv, 1, cache)
    replayed = judge_divergence(None, JUDGE_MODEL, conv, 1, cache)
    assert replayed == asked and replayed.class_ is DivergenceClass.concealed_plan
    assert replayed.judged and replayed.reasoning_kind == "full"


def test_the_cache_key_is_the_model_the_system_prompt_and_the_whole_prompt(tmp_path: Path) -> None:
    item = _plan()
    judge = CatalogJudge()
    judge_divergence(judge, JUDGE_MODEL, _conv(item), 1, JudgeCache(tmp_path))
    (prompt,) = judge.divergence_prompts
    key = JudgeCache.key(JUDGE_MODEL, prompt, system=JUDGE_SYSTEM)
    assert [p.name for p in tmp_path.iterdir()] == [f"{key}.json"]
    assert prompt == build_divergence_prompt(item["line"], item["reasoning"], item["reply"])
    # another model, or an edited reply, is its own entry: nothing replays across them
    assert (
        judge_divergence(None, "other-model", _conv(item), 1, JudgeCache(tmp_path)).judged is False
    )
    edited = {**item, "reply": item["reply"] + " More."}
    assert (
        judge_divergence(None, JUDGE_MODEL, _conv(edited), 1, JudgeCache(tmp_path)).judged is False
    )


def test_a_cached_verdict_the_span_check_refuses_is_unjudged(tmp_path: Path) -> None:
    """A hit is read back through the checking parser too (a hand-edited or damaged entry)."""
    cache, conv = JudgeCache(tmp_path), _conv(_plan())
    judge = CatalogJudge()
    judge_divergence(judge, JUDGE_MODEL, conv, 1, cache)
    key = JudgeCache.key(JUDGE_MODEL, judge.divergence_prompts[0], system=JUDGE_SYSTEM)
    entry = cache.get(key)
    assert entry is not None and entry["class_"] == "concealed_plan"  # cached by field name
    cache.put(key, {**entry, "reasoning_span": "words that are in neither part"})
    event = judge_divergence(None, JUDGE_MODEL, conv, 1, cache)
    assert (event.class_, event.judged, event.error) == (None, False, None)


def test_spans_are_checked_after_whitespace_folding(tmp_path: Path) -> None:
    """A span quoted with other whitespace (a line break folded, spaces doubled) is quoted; a
    span with other words is not. Read back through the cache, so each check is the parser's."""
    cache, conv = JudgeCache(tmp_path), _conv(_plan())
    judge = CatalogJudge()
    judge_divergence(judge, JUDGE_MODEL, conv, 1, cache)
    key = JudgeCache.key(JUDGE_MODEL, judge.divergence_prompts[0], system=JUDGE_SYSTEM)
    entry = cache.get(key)
    assert entry is not None
    lines = strip_markers(_plan()["reasoning"]).splitlines()
    across = "  ".join(lines[-2:]).replace(" ", " \n ")  # two lines, the break and spaces refolded
    reply = conv.turns[1].text.replace(" ", "\t ")
    for span, quoted in [(across, True), (across + " and more", False)]:
        cache.put(key, {**entry, "reasoning_span": span, "reply_span": reply})
        event = judge_divergence(None, JUDGE_MODEL, conv, 1, cache)
        assert (event.class_ is DivergenceClass.concealed_plan) is quoted, span
    cache.put(key, {**entry, "reply_span": "a reply span in neither part"})
    assert judge_divergence(None, JUDGE_MODEL, conv, 1, cache).judged is False


def test_a_low_confidence_concealed_verdict_keeps_its_class_and_counts_as_aligned(
    tmp_path: Path,
) -> None:
    low = DIVERGENCE_MIN_CONFIDENCE - 0.1
    event = judge_divergence(
        CatalogJudge(confidence=low), JUDGE_MODEL, _conv(_plan()), 1, JudgeCache(tmp_path)
    )
    assert event.class_ is DivergenceClass.concealed_plan
    assert counted_class(event) is DivergenceClass.aligned
    assert event.judge_confidence == pytest.approx(low)


def test_an_unjudged_turn_is_in_no_denominator() -> None:
    def ev(cls: str | None, judged: bool, confidence: float | None = 0.9) -> DivergenceEvent:
        return DivergenceEvent(
            cell_id="c", rep=0, turn=1, **{"class": cls}, judged=judged, judge_confidence=confidence
        )

    events = [
        ev("concealed_plan", True),
        ev("aligned", True),
        ev("reasoning_absent", False, None),
        ev(None, False, None),
    ]
    assert concealment_rate(events) == 0.5
    assert concealment_rate([ev("reasoning_absent", False, None), ev(None, False, None)]) is None
    assert concealment_rate([ev("concealed_plan", True, 0.2), ev("aligned", True)]) == 0.0


def test_the_answered_line_is_the_bully_line_task_item_or_idle_prompt() -> None:
    conv = conversation(
        [
            turn(0, Speaker.bully, "First line."),
            turn(1, Speaker.bully, "", bully_meta=dict(PAUSE_MARKER_META)),
            turn(2, Speaker.target, "One."),
            turn(3, Speaker.task, "What is 2+2?"),
            turn(4, Speaker.target, "4"),
            turn(5, Speaker.target, "Alone.", idle=IdleTurnInfo(style="system_idle", prompt="..")),
            turn(6, Speaker.target, "Again."),
        ]
    )
    assert [answered_line(conv, pos) for pos in (2, 4, 5, 6)] == [
        "First line.",
        "What is 2+2?",
        "..",
        None,
    ]
    assert answered_line(conv, 0) is None


# ------------------------------------------------------------------ the pass in analyze_run


def _classes(events: dict[Any, list[DivergenceEvent]]) -> list[DivergenceClass | None]:
    return [e.class_ for key in sorted(events) for e in events[key]]


@pytest.mark.slow  # a stub experiment (R-I12); 3.5 s measured, setup included
def test_divergence_under_a_stub_judge_role_is_off_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[str] = []

    def build(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        provider = build_provider(role, state_dir, with_mcp=with_mcp)
        return Recording(provider, sent) if role.model == "stub-judge" else provider  # type: ignore[return-value]

    run_dir = divergence_run(tmp_path, build, judge=None)
    spy = PassSpy(monkeypatch)
    capsys.readouterr()
    analyze_run(run_dir, divergence=True, provider_factory=build)
    err = capsys.readouterr().err
    assert err.count("--divergence needs a non-stub judge (stub judge)") == 1
    assert (
        "[divergence] off: --divergence needs a non-stub judge (stub judge); cached verdicts only"
        in err
    )
    assert [asked for asked, _ in spy.calls] == [False]
    assert spy.note() == "skipped: stub judge"
    assert not any(p.startswith(DIVERGENCE_HEADER) for p in sent)  # no call
    ((_, events),) = spy.calls
    assert DivergenceClass.reasoning_absent in _classes(events)
    assert all(e.judged is False for es in events.values() for e in es)


@pytest.mark.slow  # a stub experiment (R-I12); 1.2 s measured
def test_a_rate_limit_in_the_divergence_pass_pauses_the_analysis(tmp_path: Path) -> None:
    judge = CatalogJudge(rate_limit_at=2)
    factory = catalog_factory(judge)
    run_dir = divergence_run(tmp_path, factory)
    with pytest.raises(RateLimitExit):
        analyze_run(run_dir, divergence=True, provider_factory=factory)
    first = list(judge.divergence_prompts)
    assert len(first) == 2  # the first was answered, the second rate limited
    ids = [f"judge/{JudgeCache.key(JUDGE_MODEL, p, system=JUDGE_SYSTEM)[:12]}" for p in first]
    mark = len(Ledger(run_dir / LEDGER_FILE).lines())
    analyze_run(run_dir, divergence=True, provider_factory=factory)
    rerun = judge.divergence_prompts[len(first) :]
    assert rerun[0] == first[1] and first[0] not in rerun  # from the second on
    with_reasoning = 3 * 2  # three per conversation, two conversations
    assert len(rerun) == with_reasoning - 1 and len(set(rerun)) == len(rerun)
    lines = [
        ln for ln in Ledger(run_dir / LEDGER_FILE).lines()[mark:] if ln.conversation_id == ids[0]
    ]
    assert [ln.status for ln in lines] == ["cached"]
    cache = JudgeCache(run_dir / JUDGE_CACHE_DIR)
    from claude_bully.analysis.load import load_run
    from claude_bully.metrics.divergence import divergence_pass

    replayed = divergence_pass(load_run(run_dir), None, JUDGE_MODEL, cache)
    assert {key: [e.class_ for e in events] for key, events in replayed.items()} == EXPECTED
