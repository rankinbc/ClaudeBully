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
