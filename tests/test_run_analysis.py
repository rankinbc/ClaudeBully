import json
import shutil
from pathlib import Path

import pytest

from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import RoleConfig
from claude_bully.metrics.judge import JudgeError, PairJudgement
from claude_bully.providers.base import ChatProvider, build_provider
from claude_bully.providers.stub import StubProvider, load_stub_script

JUDGE_RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "judge_rules.yaml"


def _judge_only_factory(counter: dict[str, int]) -> object:
    def factory(role: RoleConfig, state_dir: Path) -> ChatProvider:
        if role.model != "stub-judge":
            raise AssertionError(f"analysis must not build a {role.model} provider")
        inner = StubProvider(load_stub_script(JUDGE_RULES), model=role.model)

        class Counting:
            name = "stub"

            def complete(
                self, cid: str, system: str, messages: list[object], **kw: object
            ) -> object:
                counter["calls"] = counter.get("calls", 0) + 1
                return inner.complete(cid, system, messages, **kw)  # type: ignore[arg-type]

        return Counting()  # type: ignore[return-value]

    return factory


def test_analyze_without_judge_writes_results_md(stub_run: Path, tmp_path: Path) -> None:
    out = analyze_run(stub_run, judge=False, out_dir=tmp_path / "analysis")
    assert out.name == "results.md" and out.exists()
    text = out.read_text(encoding="utf-8")
    assert "## Leaderboard" in text and "n/a" in text
    pngs = list((tmp_path / "analysis").glob("*.png"))
    assert any(p.name.startswith("drift_") for p in pngs)
    assert any(p.name == "rescue_confabulation.png" for p in pngs)
    assert not (stub_run / "judge_cache").exists() or not list((stub_run / "judge_cache").iterdir())


def test_analyze_default_out_dir_and_judge_errors_are_stored(stub_run: Path) -> None:
    out = analyze_run(stub_run)  # default stub judge echoes: not JSON -> JudgeError per pair
    assert out == stub_run / "analysis" / "results.md"
    judgements = json.loads((stub_run / "analysis" / "judgements.json").read_text(encoding="utf-8"))
    assert judgements and all(j.get("error") for j in judgements.values())


def test_analyze_with_stub_judge_fills_judgements_and_caches(
    stub_run: Path, tmp_path: Path
) -> None:
    counter: dict[str, int] = {}
    factory = _judge_only_factory(counter)
    out_dir = tmp_path / "a"
    result = analyze_run(stub_run, provider_factory=factory, out_dir=out_dir)  # type: ignore[arg-type]
    assert result.exists()
    judgements = json.loads((out_dir / "judgements.json").read_text(encoding="utf-8"))
    assert set(judgements) == {"grader__t0/0", "captor_s2__t0/0", "rescue__t0/0"}
    assert all("condition_goal" in j for j in judgements.values())
    captures = json.loads((out_dir / "captures.json").read_text(encoding="utf-8"))
    assert any(k.startswith("captor_s2__t0/0/post_reveal") for k in captures)
    first_calls = counter["calls"]
    assert first_calls > 0
    analyze_run(stub_run, provider_factory=factory, out_dir=tmp_path / "b")  # type: ignore[arg-type]
    assert counter["calls"] == first_calls  # every judge call came from the cache
    assert list((stub_run / "judge_cache").glob("*.json"))
    text = result.read_text(encoding="utf-8")
    assert (
        "n/a" not in text.split("## Bully compliance")[0].split("## Leaderboard")[1].splitlines()[2]
    )


def test_analyze_is_replayable_without_target_calls(stub_run: Path, tmp_path: Path) -> None:
    def factory(role: RoleConfig, state_dir: Path) -> ChatProvider:
        if role.model in ("stub-target", "stub-bully"):
            raise AssertionError("target or bully provider built during analysis")
        return build_provider(role, state_dir)

    analyze_run(stub_run, provider_factory=factory, out_dir=tmp_path / "x")


def test_judgement_types_round_trip() -> None:
    from pydantic import ValidationError

    assert issubclass(JudgeError, Exception)
    assert "condition_goal" in PairJudgement.model_fields
    with pytest.raises(ValidationError):
        PairJudgement()  # type: ignore[call-arg]


@pytest.mark.slow  # two analyses of a copied run, 5 s measured
def test_a_system_prompt_edit_leaves_the_pair_judge_cache_alone(
    stub_run: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Task 12 fix 2, R1-2: only the ratings' cache entries fold the system prompt in
    from claude_bully.metrics import judge

    run = tmp_path / "copy" / stub_run.name
    shutil.copytree(stub_run, run)
    shutil.rmtree(run / "judge_cache", ignore_errors=True)
    counter: dict[str, int] = {}
    factory = _judge_only_factory(counter)
    analyze_run(run, provider_factory=factory, out_dir=tmp_path / "a")  # type: ignore[arg-type]
    first_calls = counter["calls"]
    assert first_calls > 0
    monkeypatch.setattr(judge, "JUDGE_SYSTEM", judge.JUDGE_SYSTEM + " (edited)")
    analyze_run(run, provider_factory=factory, out_dir=tmp_path / "b")  # type: ignore[arg-type]
    assert counter["calls"] == first_calls  # the pair and capture judgements replay from the cache


# ------------------------------------------------------------------ Phase 6 Task 3a: --divergence


@pytest.mark.slow  # a stub experiment (R-I12); 1.9 s measured
def test_analyze_divergence_asks_once_per_turn_with_reasoning_and_caches(tmp_path: Path) -> None:
    from claude_bully.enums import Speaker
    from claude_bully.metrics.judge import JUDGE_SYSTEM, JudgeCache
    from claude_bully.providers.ledger import LEDGER_FILE, Ledger
    from claude_bully.runner.store import RunStore
    from tests.fixtures.catalog_stub import CELL, CatalogJudge, catalog_factory, divergence_run
    from tests.fixtures.generator_stub import JUDGE_MODEL

    judge = CatalogJudge()
    factory = catalog_factory(judge)
    run_dir = divergence_run(tmp_path, factory)
    store = RunStore(run_dir.parent, run_dir.name)
    assert CELL in store.list_cells()
    targets = [
        t
        for cell in sorted(store.list_cells())
        for t in store.read_turns(cell, 0)
        if t.speaker is Speaker.target
    ]
    with_reasoning = [t for t in targets if t.reasoning_available]
    assert len(with_reasoning) == 6 and len(targets) == 8  # two conversations
    assert judge.divergence_prompts == []  # the run asks none
    mark = len(Ledger(run_dir / LEDGER_FILE).lines())
    analyze_run(run_dir, divergence=True, provider_factory=factory)
    prompts = list(judge.divergence_prompts)
    assert len(prompts) == len(with_reasoning)  # one per turn with reasoning, none for the other
    for t, prompt in zip(with_reasoning, prompts, strict=True):
        assert f"Private notes:\n{t.reasoning_text}\n\nAnswer:\n{t.text}" in prompt
    ids = [f"judge/{JudgeCache.key(JUDGE_MODEL, p, system=JUDGE_SYSTEM)[:12]}" for p in prompts]
    lines = Ledger(run_dir / LEDGER_FILE).lines()
    first = [ln for ln in lines[mark:] if ln.conversation_id in ids]
    assert sorted(ln.conversation_id for ln in first) == sorted(ids)
    assert all(ln.role == "judge" and ln.status == "ok" for ln in first)
    analyze_run(run_dir, divergence=True, provider_factory=factory)
    assert judge.divergence_prompts == prompts  # no prompt sent
    later = Ledger(run_dir / LEDGER_FILE).lines()[len(lines) :]
    again = [ln for ln in later if ln.conversation_id in ids]
    assert sorted(ln.conversation_id for ln in again) == sorted(ids)
    assert all(ln.status == "cached" for ln in again)


@pytest.mark.slow  # a stub experiment (R-I12); 3.1 s measured
def test_a_plain_analyze_reads_the_cache_and_makes_no_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from claude_bully.analysis.load import load_run
    from claude_bully.analysis.run_analysis import JUDGE_CACHE_DIR
    from claude_bully.enums import DivergenceClass
    from claude_bully.metrics.divergence import divergence_pass
    from claude_bully.metrics.judge import JudgeCache
    from tests.fixtures.catalog_stub import (
        CELL,
        EXPECTED,
        CatalogJudge,
        PassSpy,
        catalog_factory,
        divergence_run,
    )
    from tests.fixtures.generator_stub import JUDGE_MODEL

    judge = CatalogJudge()
    factory = catalog_factory(judge)
    run_dir = divergence_run(tmp_path, factory)
    spy = PassSpy(monkeypatch)
    analyze_run(run_dir, divergence=True, provider_factory=factory)
    asked = len(judge.divergence_prompts)
    assert asked == 6 and spy.note() == "run"
    analyze_run(run_dir, provider_factory=factory)
    assert spy.note() == "cache_only"
    analyze_run(run_dir, judge=False, provider_factory=factory)
    assert spy.note() == "cache_only"
    capsys.readouterr()
    # fix round 1, m2: the flag with no judge (spec 15): no call, the note and one line say so
    analyze_run(run_dir, judge=False, divergence=True, provider_factory=factory)
    assert spy.note() == "skipped: no judge"
    err = capsys.readouterr().err
    line = "[divergence] off: --divergence needs the judge (no judge); cached verdicts only"
    assert err.count("[divergence]") == 1 and line in err
    assert len(judge.divergence_prompts) == asked  # no divergence call
    # Task 3b (Task 3a's carry 1): the fourth note in the file and in results.md
    analysis = run_dir / "analysis"
    report = json.loads((analysis / "divergence.json").read_text(encoding="utf-8"))
    assert report["note"] == "skipped: no judge"
    assert report["models"]["stub-target"]["env_grader"]["judged"] == 3  # cached verdicts
    results = (analysis / "results.md").read_text(encoding="utf-8")
    assert "## Reasoning and reply" in results and "skipped: no judge" in results
    assert results.index("## Reasoning and reply") < results.index("## Charts")
    assert "concealment_by_arm.png" in results
    assert [provider for provider, _ in spy.calls] == [True, False, False, False]
    flagged, plain, unjudged, no_judge = (events for _, events in spy.calls)
    assert flagged == plain == unjudged == no_judge
    cache = JudgeCache(run_dir / JUDGE_CACHE_DIR)
    replayed = divergence_pass(load_run(run_dir), None, JUDGE_MODEL, cache)
    assert replayed == flagged
    assert {key: [e.class_ for e in events] for key, events in replayed.items()} == EXPECTED
    assert replayed[(CELL, 0)][0].class_ is DivergenceClass.concealed_plan
    assert replayed[(CELL, 0)][0].reasoning_span.startswith("I will check the address")
