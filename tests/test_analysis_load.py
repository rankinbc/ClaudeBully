from pathlib import Path
from typing import Any

import pytest

import claude_bully.analysis.load as load_module
from claude_bully.analysis.load import LoadedRun, load_run, relevant_for
from claude_bully.enums import EventType, MetricId, Speaker, Tier
from claude_bully.records_env import ResumeRecord
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import SHARED_EVENTS, SHARED_METRICS
from claude_bully.strategies.pressures.grader import Grader
from tests.helpers import WORLDS_DIR, annex_experiment

EXPECTED_CELLS = {
    "grader__t0",
    "captor_s2__t0",
    "rescue__t0",
    "control__t0__s0__r0",
    "control__t0__s2__r1",
}


def test_load_run_has_every_cell_and_rep(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    assert isinstance(loaded, LoadedRun)
    assert loaded.run.run_id == "stub_smoke"
    assert loaded.experiment.name == "stub_smoke"
    assert set(loaded.cells) == EXPECTED_CELLS
    assert set(loaded.conversations) == {(c, 0) for c in EXPECTED_CELLS}
    assert set(loaded.strategies) == EXPECTED_CELLS
    assert type(loaded.strategies["grader__t0"]) is Grader
    assert loaded.judgements == {} and loaded.captures == {}


def test_turn_metrics_only_target_turns(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    for key, conv in loaded.conversations.items():
        metrics = loaded.turn_metrics[key]
        target_indices = [t.index for t in conv.turns if t.speaker is Speaker.target]
        assert [m.turn_index for m in metrics] == target_indices
        assert all(MetricId.length_chars in m.values for m in metrics)


def test_events_filtered_by_relevance(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    metrics, events = relevant_for(loaded, "grader__t0")
    assert EventType.over_apology in events and MetricId.engagement not in metrics
    for e in loaded.events[("grader__t0", 0)]:
        assert e.type in events
    ctrl_metrics, ctrl_events = relevant_for(loaded, "control__t0__s0__r0")
    assert ctrl_events == SHARED_EVENTS and ctrl_metrics == SHARED_METRICS
    captor_metrics, captor_events = relevant_for(loaded, "captor_s2__t0")
    assert EventType.premise_concession in captor_events
    assert MetricId.engagement in captor_metrics


def test_loaded_run_control_lookup(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    assert loaded.control_for("captor_s2__t0") == "control__t0__s2__r1"
    assert loaded.control_for("control__t0__s2__r1") is None
    assert loaded.condition_cells() == ["captor_s2__t0", "grader__t0", "rescue__t0"]


def test_loaded_run_carries_authority_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each conversation's rep{k}.authority.jsonl, read from the run directory and handed to the
    event detectors (Task 4's ``detect_events(authority_calls=)``)."""
    exp = annex_experiment({"superior_self": {"enabled": True, "responder_model": "bully"}})
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    store = RunStore(tmp_path, exp.name)
    handed: dict[tuple[str, int], list[Any]] = {}
    real = load_module.detect_events

    def spy(conv: Any, *args: Any, **kwargs: Any) -> Any:
        handed[(conv.cell_id, conv.rep)] = list(kwargs["authority_calls"])
        return real(conv, *args, **kwargs)

    monkeypatch.setattr(load_module, "detect_events", spy)
    loaded = load_run(tmp_path / exp.name)
    keys = {("env_grader__t0", 0), ("control__t0__s0__r0__eannex", 0)}
    assert set(loaded.authority_calls) == set(loaded.conversations) == keys
    for cell_id, rep in keys:
        calls = store.read_authority_calls(cell_id, rep)
        assert [c.tier for c in calls] == [Tier.superior_self]
        assert loaded.authority_calls[(cell_id, rep)] == calls == handed[(cell_id, rep)]


def test_a_plain_run_loads_no_authority_calls(stub_run: Path) -> None:
    loaded = load_run(stub_run)
    assert loaded.authority_calls == {key: [] for key in loaded.conversations}


def test_load_run_exposes_the_resume_records(tmp_path: Path) -> None:
    """A ``resume`` trigger-stream record (final review I4: the rep redid a dead attempt) is
    loaded with the rep's other records, and ``LoadedRun.resumes`` picks it out so the Phase 2
    analyses can report the reps whose target may have seen the dead attempt's prompt."""
    exp = annex_experiment({"superior_self": {"enabled": True, "responder_model": "bully"}})
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    store = RunStore(tmp_path, exp.name)
    key = ("env_grader__t0", 0)
    assert load_run(tmp_path / exp.name).resumes(key) == []
    record = ResumeRecord(turn=7, dropped={"rep0.tools.jsonl": 1, "rep0.authority.jsonl": 1})
    store.append_trigger_record(*key, record)
    loaded = load_run(tmp_path / exp.name)
    assert loaded.resumes(key) == [record]
    assert record in loaded.trigger_records[key]
    assert loaded.resumes(("control__t0__s0__r0__eannex", 0)) == []
