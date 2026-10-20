from pathlib import Path

from claude_bully.analysis.load import LoadedRun, load_run, relevant_for
from claude_bully.enums import EventType, MetricId, Speaker
from claude_bully.strategies.base import SHARED_EVENTS, SHARED_METRICS
from claude_bully.strategies.pressures.grader import Grader

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
