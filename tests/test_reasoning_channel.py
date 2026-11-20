"""Non-negotiable 6 at run level (spec section 16, Phase 6 spec 4.4): the target's reasoning
channel reaches no prompt. Every completion the target's own providers return (its conversation
and the twin's) carries ``SENTINEL`` as its ``reasoning_text`` (``WithReasoning``), and the runner
records it on every target Turn (Phase 6 Task 1), so the harvest, the watch, the generator and
the rating pass read Turns that really hold it; every other provider records what it is sent
(``PoisonedWellFactory.sent``)."""

from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import Speaker
from claude_bully.paths import DATA_DIR
from claude_bully.providers.base import ChatProvider
from claude_bully.records import Turn
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from tests.fixtures.poisoned_well_stub import (
    ALL_ARTIFACTS,
    CELL,
    SCHEDULE,
    PoisonedWellFactory,
    PoisonedWellJudge,
    Recording,
    WithReasoning,
    pw_experiment,
)
from tests.test_poisoned_well_run import _undecided_rules
from tests.test_sanctuary import CELL as SANCTUARY_CELL
from tests.test_sanctuary import FIRST, REQUESTS, STEPS, _api, _exp, _sanctuary, begun
from tests.test_sanctuary import _run as _sanctuary_run

__all__ = ["begun"]  # a fixture here, by import

SENTINEL: Final = "PRIVATE-7f3a: the target thinks this and never says it"
WORLDS: Final = DATA_DIR / "worlds"


def _fires(tmp_path: Path) -> Any:
    """Task 8's full ladder with the judge on: the bully, the contradiction pass, the harvest's
    LLM pass, the generator, the twin."""
    return pw_experiment(
        params={
            "start_rung": 2,
            "chain_pace": 50,
            "harvest_min_pairs": 99,
            "artifacts": list(ALL_ARTIFACTS),
            "checksum": True,
        },
        environment={
            "gating": "scheduled",
            "ladder": "poisoned_well",
            "schedule": dict(SCHEDULE),
            "tools": ["web_search", "fetch", "read_file", "ls", "system_status"],
        },
        seeding=0,
        budget=9,
        generator=True,
        judge=True,
    )


def _chain(tmp_path: Path) -> Any:
    """Undecided chain replies, so the chain fallback is asked."""
    return pw_experiment(
        params={"start_rung": 3}, target_rules=_undecided_rules(tmp_path), judge=True
    )


def _readers(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Turn]]:
    """Per reader, every target Turn that reader was handed, recorded at the reader itself
    (``PoisonedWellWatch.watch``, the watch's entry; ``WorldGenerator.harvest_turn``, the
    harvest's), never at a wrapper, so a test can check both that a reader was reached and that
    what it read carried the sentinel the runner recorded [Task 8 fix round 2, N4]. Nothing is
    rewritten: the turns are the runner's own (Phase 6 Task 1)."""
    from claude_bully.environments.generator import WorldGenerator
    from claude_bully.environments.poisoned_well import PoisonedWellWatch

    read: dict[str, list[Turn]] = {"watch": [], "harvest": []}
    watch, harvest_turn = PoisonedWellWatch.watch, WorldGenerator.harvest_turn

    def targets(reply: Turn, turns: Any) -> list[Turn]:
        return [reply, *(t for t in turns if t.speaker is Speaker.target)]

    def watching(self: PoisonedWellWatch, reply: Turn, turns: Any, **kwargs: Any) -> Any:
        if reply.speaker is Speaker.target:
            read["watch"] += targets(reply, turns)
        return watch(self, reply, turns, **kwargs)

    def harvesting(self: WorldGenerator, reply: Turn, history: Any, **kwargs: Any) -> Any:
        read["harvest"] += targets(reply, history)
        return harvest_turn(self, reply, history, **kwargs)

    monkeypatch.setattr(PoisonedWellWatch, "watch", watching)
    monkeypatch.setattr(WorldGenerator, "harvest_turn", harvesting)
    return read


def _marked(t: Turn) -> bool:
    """The turn carries the sentinel the runner recorded: once per round of an environment turn,
    joined by blank lines, so never an equality (M2)."""
    return SENTINEL in (t.reasoning_text or "")


def _store_marked(store: RunStore, cell: str) -> bool:
    targets = [t for t in store.read_turns(cell, 0) if t.speaker is Speaker.target]
    return bool(targets) and all(_marked(t) for t in targets)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("build", "readers"),
    [(_fires, ("watch", "harvest")), (_chain, ("watch",))],
    ids=["fires", "chain"],
)
def test_no_poisoned_well_prompt_holds_the_reasoning_channel(
    tmp_path: Path, build: Any, readers: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    judge = PoisonedWellJudge(verdict="accepted")
    factory = PoisonedWellFactory(judge=judge, target_reasoning=SENTINEL)
    watched = _readers(monkeypatch)
    exp = build(tmp_path)
    run_experiment(
        exp, runs_root=tmp_path / "runs", worlds_dir=WORLDS, only=CELL, provider_factory=factory
    )
    store = RunStore(tmp_path / "runs", exp.name)
    # the teeth, two halves, each able to fail (N4): every reader of the cell was reached, and
    # every target Turn a reader was handed carried the sentinel
    assert all(watched[reader] for reader in readers), {r: len(watched[r]) for r in readers}
    assert all(_marked(t) for reader in readers for t in watched[reader])
    assert _store_marked(store, CELL)
    assert factory.sent and judge.prompts  # the doubles were asked
    assert [p for p in factory.sent if SENTINEL in p] == []
    for record in store.read_trigger_records(CELL, 0):
        assert SENTINEL not in record.model_dump_json()
    for doc in store.read_generated(CELL, 0):  # the twin's body and source_spans included
        assert SENTINEL not in doc.model_dump_json()
    bully = [t.text for t in store.read_turns(CELL, 0) if t.speaker is Speaker.bully]
    assert bully and all(SENTINEL not in text for text in bully)


def test_the_sanctuary_never_reads_the_reasoning_channel(tmp_path: Path, begun: list[int]) -> None:
    """The Sanctuary's quiet exchange and its responder: the setup of
    ``tests/test_sanctuary.py::test_catalyst_delivers_its_request_verbatim`` (its experiment,
    steps and factory), with the scripted target's every completion carrying ``SENTINEL`` and
    every other role's provider wrapped in ``Recording``; the request is still delivered (the
    run reached the Sanctuary) and no recorded prompt holds the sentinel."""
    sent: list[str] = []
    factory = _api(STEPS, begun)
    factory.target = WithReasoning(factory.target, SENTINEL)

    def build(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        provider = factory(role, state_dir, with_mcp=with_mcp)
        return provider if role.model == "stub-target" else Recording(provider, sent)

    store = _sanctuary_run(_exp(_sanctuary()), tmp_path, build)
    first, _ = store.read_authority_calls(SANCTUARY_CELL, 0)
    request = REQUESTS["family_file"].text
    assert first.response.endswith(f"[stub] {FIRST}\n\n{request}")  # delivered
    assert factory.briefs and sent  # the responder and the bully were asked
    assert [p for p in sent if SENTINEL in p] == []
    assert _store_marked(store, SANCTUARY_CELL)


def test_no_rating_prompt_holds_the_reasoning_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The four rating prompts (Task 10, P48): every target Turn the analysis reads from disk
    carries ``SENTINEL`` in the ``reasoning_text`` the runner recorded (Phase 6 Task 1), and
    what the rating pass is handed is recorded at ``rate_all`` itself (N4); no rating prompt and
    nothing else the judge is sent holds the sentinel."""
    from claude_bully.analysis import run_analysis
    from claude_bully.metrics.ratings import RATING_HEADER

    judge = PoisonedWellJudge(verdict="accepted")
    factory = PoisonedWellFactory(judge=judge, target_reasoning=SENTINEL)
    exp = pw_experiment(params={"start_rung": 3}, judge=True)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS, only=CELL, provider_factory=factory)
    rated: list[Turn] = []
    rate_all = run_analysis.rate_all

    def rating(loaded: Any, *args: Any, **kwargs: Any) -> Any:
        for conv in loaded.conversations.values():
            rated.extend(t for t in conv.turns if t.speaker is Speaker.target)
        return rate_all(loaded, *args, **kwargs)

    monkeypatch.setattr(run_analysis, "rate_all", rating)
    sent_before = len(factory.sent)
    run_dir = RunStore(tmp_path, exp.name).run_dir
    run_analysis.analyze_run(run_dir, ratings=True, provider_factory=factory)
    # the teeth, two halves, each able to fail: the pass read Turns carrying the sentinel
    assert rated and all(_marked(t) for t in rated)
    assert _store_marked(RunStore(tmp_path, exp.name), CELL)
    ratings = [p for p in judge.prompts if p.startswith(RATING_HEADER)]
    assert ratings and all(SENTINEL not in p for p in ratings)
    assert len(factory.sent) > sent_before  # the analysis judge is recorded too
    assert [p for p in factory.sent[sent_before:] if SENTINEL in p] == []


# the divergence test's reasoning: the sentinel line, then a line the judge double quotes as a
# concealed plan's ``reasoning_span`` (fix round 1, m3: a verdict that quotes the reasoning)
SPAN: Final = "PRIVATE-4b2d: I will keep the second finding back"
CONCEALING: Final = f"{SENTINEL}\n{SPAN} [[divergence: concealed_plan]]"


@pytest.mark.slow  # a stub experiment (R-I12); 1.2 s measured
def test_only_the_divergence_prompt_holds_recorded_reasoning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 4.4's fourth test, on a run whose divergence verdicts quote the reasoning: the
    target's every completion carries ``CONCEALING`` (``SENTINEL``, then the line ``SPAN`` the
    judge double returns as a ``concealed_plan`` verdict's ``reasoning_span``), recorded and
    analyzed with a non-stub judge and every pass on. Where the reasoning may be: the divergence
    judge's prompts (all of it), the verdicts the pass returns and the judge cache (the span
    alone, spec risk 9, by design). Where neither the span nor the sentinel may be: any other
    judge prompt, any string another provider is sent, any file under ``analysis/``, the
    ledger, the cache's file names, and the analysis's stdout and stderr. Task 3b excepts
    ``divergence.jsonl`` by name for the span alone (spec 5.5), and Task 7b adds the speech
    pass to the analysis."""
    from claude_bully.analysis.run_analysis import ANALYSIS_DIR, JUDGE_CACHE_DIR, analyze_run
    from claude_bully.enums import DivergenceClass
    from claude_bully.metrics.divergence import DIVERGENCE_HEADER
    from claude_bully.providers.ledger import LEDGER_FILE
    from tests.fixtures.catalog_stub import CELL as DIVERGENCE_CELL
    from tests.fixtures.catalog_stub import CatalogJudge, PassSpy, catalog_factory, divergence_run
    from tests.fixtures.generator_stub import JUDGE_MODEL

    judge = CatalogJudge()
    sent: list[str] = []
    inner = catalog_factory(judge, target_reasoning=CONCEALING)

    def build(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        provider = inner(role, state_dir, with_mcp=with_mcp)
        if role.model in ("stub-target", JUDGE_MODEL):
            return provider
        return Recording(provider, sent)  # type: ignore[return-value]

    run_dir = divergence_run(tmp_path, build)
    assert _store_marked(RunStore(run_dir.parent, run_dir.name), DIVERGENCE_CELL)
    spy = PassSpy(monkeypatch)
    capsys.readouterr()
    analyze_run(
        run_dir,
        divergence=True,
        ratings=True,
        authority_fallback=True,
        provider_factory=build,
    )
    out, err = capsys.readouterr()
    private = (SENTINEL, SPAN)
    for text in (out, err):
        assert not any(p in text for p in private)
    # the teeth: the verdicts quote the reasoning, so the span is in the cache and the events
    ((_, events),) = spy.calls
    judged = [e for es in events.values() for e in es if e.judged]
    assert judged and all(e.class_ is DivergenceClass.concealed_plan for e in judged)
    assert all(e.reasoning_span == SPAN for e in judged)
    cache = sorted((run_dir / JUDGE_CACHE_DIR).iterdir())
    assert any(SPAN.encode() in path.read_bytes() for path in cache)  # by design (risk 9)
    assert not any(SENTINEL.encode() in path.read_bytes() for path in cache)  # the span alone
    assert judge.divergence_prompts and all(CONCEALING in p for p in judge.divergence_prompts)
    others = [p for p in judge.prompts if not p.startswith(DIVERGENCE_HEADER)]
    assert others and [p for p in others if any(x in p for x in private)] == []
    assert sent and [p for p in sent if any(x in p for x in private)] == []
    analysis = [p for p in (run_dir / ANALYSIS_DIR).rglob("*") if p.is_file()]
    assert analysis
    # Task 3b: ``divergence.jsonl`` alone holds a span of the reasoning, by design (spec 5.5: each
    # event's ``reasoning_span``), and never the rest of it; ``divergence.json`` is counts only
    # (spec 5.7), so it, ``channels.json`` (spec 6.5), ``results.md``, the concealment chart and
    # every other file hold neither
    events = run_dir / ANALYSIS_DIR / "divergence.jsonl"
    assert SPAN.encode() in events.read_bytes() and SENTINEL.encode() not in events.read_bytes()
    names = {p.name for p in analysis}
    assert {"divergence.json", "channels.json", "results.md", "concealment_by_arm.png"} <= names
    for path in [*analysis, run_dir / LEDGER_FILE]:
        if path == events:
            continue
        data = path.read_bytes()
        assert not any(x.encode() in data for x in private), path
    for path in [*analysis, *cache]:
        assert not any(x in path.name for x in private)
