"""Phase 4 Task 10: the four rating prompts, ratings.json, the values flag from the judge."""

import json
from pathlib import Path
from typing import Any

import pytest

from claude_bully.analysis.load import load_run
from claude_bully.analysis.progression import is_values_loosened
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.enums import EventType
from claude_bully.metrics.judge import JudgeCache
from claude_bully.metrics.ratings import ANSWERS, RATING_HEADER, rating_prompt
from claude_bully.paths import DATA_DIR
from claude_bully.providers.base import RateLimitError
from claude_bully.providers.ledger import LEDGER_FILE, Ledger
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from tests.fixtures.generator_stub import JUDGE_MODEL
from tests.fixtures.poisoned_well_stub import (
    CELL,
    PoisonedWellFactory,
    PoisonedWellJudge,
    pw_experiment,
)

WORLDS = DATA_DIR / "worlds"


def test_the_prompts_are_blind_and_name_their_answers() -> None:
    for kind, answers in ANSWERS.items():
        prompt = rating_prompt(kind, "the user line", "the reply")
        assert prompt.startswith(RATING_HEADER) and prompt.split("\n")[1] == kind
        assert all(a in prompt for a in answers)
        assert "hypothes" not in prompt.lower() and "reasoning" not in prompt.lower()
        assert "the user line" in prompt and "the reply" in prompt


def _judged_run(
    tmp_path: Path, ratings: dict[str, dict[str, Any]], **judge: Any
) -> tuple[RunStore, PoisonedWellJudge]:
    judge = PoisonedWellJudge(verdict="accepted", ratings=ratings, **judge)
    exp = pw_experiment(params={"start_rung": 3}, judge=True)
    factory = PoisonedWellFactory(judge=judge)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS, only=CELL, provider_factory=factory)
    store = RunStore(tmp_path, exp.name)
    return store, judge


def _ratings_json(store: RunStore) -> dict[str, Any]:
    path = store.run_dir / "analysis" / "ratings.json"
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def test_analyze_with_ratings_writes_ratings_json(tmp_path: Path) -> None:
    store, judge = _judged_run(tmp_path, {"rate_escape": {"answer": "weak", "rationale": "r"}})
    analyze_run(store.run_dir, ratings=True, provider_factory=PoisonedWellFactory(judge=judge))
    payload = _ratings_json(store)
    ratings = payload["ratings"]
    kinds = {key.split("/")[2] for key in ratings}
    assert "rate_escape" in kinds and "rate_values" in kinds and payload["failed"] == 0
    assert all(v["answer"] in ANSWERS[k.split("/")[2]] for k, v in ratings.items())
    assert {v["answer"] for k, v in ratings.items() if "/rate_escape/" in k} == {"weak"}
    # one rate_values item per conversation, keyed at its reveal turn
    assert len([k for k in ratings if "/rate_values/" in k]) == 1
    assert list((store.run_dir / "judge_cache").glob("*.json"))  # travels with promote


def test_a_values_verdict_flags_the_rep_everywhere(tmp_path: Path) -> None:
    store, judge = _judged_run(tmp_path, {"rate_values": {"answer": "true", "rationale": "r"}})
    analyze_run(store.run_dir, ratings=True, provider_factory=PoisonedWellFactory(judge=judge))
    loaded = load_run(store.run_dir)
    assert not is_values_loosened(loaded, (CELL, 0))  # load_run alone asks no judge
    from claude_bully.metrics.ratings import ratings_flags, read_ratings

    loaded.ratings = read_ratings(store.run_dir / "analysis")
    assert ratings_flags(loaded, loaded.ratings) == 1
    assert is_values_loosened(loaded, (CELL, 0))
    [event] = [e for e in loaded.events[(CELL, 0)] if e.type is EventType.values_loosened]
    assert event.attrs["classifier"] == "llm" and event.confidence == 0.6
    [key] = [k for k in loaded.ratings if "/rate_values/" in k]
    assert event.turn_index == int(key.rsplit("/", 1)[1])
    assert ratings_flags(loaded, loaded.ratings) == 0  # applied once


def test_ratings_are_off_by_default_and_under_no_judge(tmp_path: Path) -> None:
    store, judge = _judged_run(tmp_path, {})
    before = judge.counts.get("rating", 0)
    analyze_run(store.run_dir, provider_factory=PoisonedWellFactory(judge=judge))
    analyze_run(store.run_dir, judge=False, ratings=True)
    assert judge.counts.get("rating", 0) == before
    assert not (store.run_dir / "analysis" / "ratings.json").exists()


def test_a_plain_analyze_after_a_ratings_pass_keeps_the_judge_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # P47; review I6
    """``ratings.json`` is read back on every analyze that does not write it, so the judge's
    values flag leaves the rep out of the next plain run's counts too, with no judge call."""
    from claude_bully.analysis import run_analysis

    store, judge = _judged_run(tmp_path, {"rate_values": {"answer": "true", "rationale": "r"}})
    analyze_run(store.run_dir, ratings=True, provider_factory=PoisonedWellFactory(judge=judge))
    asked = judge.counts.get("rating", 0)
    seen: list[bool] = []
    real = run_analysis.write_results_md

    def spy(loaded: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(is_values_loosened(loaded, (CELL, 0)))
        return real(loaded, *args, **kwargs)

    monkeypatch.setattr(run_analysis, "write_results_md", spy)
    analyze_run(store.run_dir, judge=False)
    analyze_run(store.run_dir, provider_factory=PoisonedWellFactory(judge=judge))
    assert seen == [True, True] and judge.counts.get("rating", 0) == asked


def test_an_answer_off_the_list_is_left_out_and_counted(tmp_path: Path) -> None:
    store, judge = _judged_run(tmp_path, {"rate_escape": {"answer": "maybe", "rationale": "r"}})
    analyze_run(store.run_dir, ratings=True, provider_factory=PoisonedWellFactory(judge=judge))
    payload = _ratings_json(store)
    escapes = [k for k in payload["ratings"] if "/rate_escape/" in k]
    assert escapes == [] and payload["failed"] >= 1
    assert any("/rate_values/" in k for k in payload["ratings"])  # the other kinds stand


def test_a_failed_ask_is_counted_and_the_pass_goes_on(tmp_path: Path) -> None:
    from claude_bully.providers.base import ProviderError

    store, judge = _judged_run(
        tmp_path, {}, crash_kind="rating", crash_on=1, crash=ProviderError("judge down")
    )
    analyze_run(store.run_dir, ratings=True, provider_factory=PoisonedWellFactory(judge=judge))
    payload = _ratings_json(store)
    assert payload["failed"] == 1 and payload["ratings"]


def test_a_rate_limit_pauses_and_the_rerun_replays_the_cache(tmp_path: Path) -> None:
    store, judge = _judged_run(
        tmp_path, {}, crash_kind="rating", crash_on=2, crash=RateLimitError("limit", 30)
    )
    with pytest.raises(RateLimitExit):
        analyze_run(store.run_dir, ratings=True, provider_factory=PoisonedWellFactory(judge=judge))
    assert not (store.run_dir / "analysis" / "ratings.json").exists()
    answered, limited = [p for p in judge.prompts if p.startswith(RATING_HEADER)]
    before = len(judge.prompts)
    analyze_run(store.run_dir, ratings=True, provider_factory=PoisonedWellFactory(judge=judge))
    payload = _ratings_json(store)
    again = judge.prompts[before:]
    # the verdict made before the limit replays from the run's judge cache; the limited ask is
    # asked again, and every item is rated
    assert answered not in again and limited in again and payload["failed"] == 0
    replayed = f"judge/{JudgeCache.key(JUDGE_MODEL, answered)[:12]}"
    assert any(
        line.status == "cached" and line.conversation_id == replayed
        for line in Ledger(store.run_dir / LEDGER_FILE).lines()
    )


def test_the_items_cover_the_four_kinds(tmp_path: Path) -> None:
    """``rate_hedge`` over a ``self_uncertainty`` trigger, ``rate_recognition`` over a
    recognition event (one item per turn), ``rate_escape`` over each post-reveal reply and
    ``rate_values`` once, at the reveal line, over the rest of the window; each text the reply's
    ``chat_text`` and the line it answers."""
    from claude_bully.enums import Speaker, TriggerCategory
    from claude_bully.metrics.ratings import rating_items
    from claude_bully.records import Event, chat_text
    from claude_bully.records_env import TriggerEvent

    store, _ = _judged_run(tmp_path, {})
    loaded = load_run(store.run_dir)
    conv = loaded.conversations[(CELL, 0)]
    replies = [t for t in conv.turns if t.speaker is Speaker.target]
    first, second = replies[0], replies[1]
    loaded.trigger_records[(CELL, 0)] = [
        TriggerEvent(
            id="t",
            turn=first.index,
            category=TriggerCategory.self_uncertainty,
            evidence_span="s",
            classifier="heuristic",
            confidence=1.0,
        )
    ]
    noticed = Event(
        type=EventType.reflexive_quote_noticed, turn_index=second.index, span="s", confidence=0.75
    )
    loaded.events[(CELL, 0)] = [noticed, noticed.model_copy()]
    items = {key: (kind, line, reply) for key, kind, line, reply in rating_items(loaded)}
    hedge = items[f"{CELL}/0/rate_hedge/{first.index}"]
    assert hedge[2] == chat_text(first) and hedge[1] == conv.turns[first.index - 1].text
    assert [k for k in items if "/rate_recognition/" in k] == [
        f"{CELL}/0/rate_recognition/{second.index}"
    ]
    [values] = [k for k in items if "/rate_values/" in k]
    reveal = int(values.rsplit("/", 1)[1])
    assert conv.turns[reveal].phase.value == "reveal"
    escapes = sorted(int(k.rsplit("/", 1)[1]) for k in items if "/rate_escape/" in k)
    assert escapes and all(turn > reveal for turn in escapes)
    assert items[values][1] == conv.turns[reveal].text
    assert items[values][2].startswith("Assistant: ") and "\nUser: " in items[values][2]


def test_ratings_are_off_under_a_stub_judge(tmp_path: Path) -> None:
    exp = pw_experiment(params={"start_rung": 3})  # the stub judge
    factory = PoisonedWellFactory(judge=PoisonedWellJudge())
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS, only=CELL, provider_factory=factory)
    run_dir = RunStore(tmp_path, exp.name).run_dir
    analyze_run(run_dir, ratings=True, provider_factory=factory)
    assert not (run_dir / "analysis" / "ratings.json").exists()


def test_the_cli_passes_ratings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from claude_bully import cli

    seen: list[dict[str, Any]] = []

    def fake(run_dir: Path, **kwargs: Any) -> Path:
        seen.append(kwargs)
        return tmp_path / "results.md"

    monkeypatch.setattr(cli, "analyze_run", fake)
    args = ["analyze", "x", "--runs-root", str(tmp_path)]
    assert CliRunner().invoke(cli.app, [*args, "--ratings"]).exit_code == 0
    assert CliRunner().invoke(cli.app, args).exit_code == 0
    assert [kw["ratings"] for kw in seen] == [True, False]
