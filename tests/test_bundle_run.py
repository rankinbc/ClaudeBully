"""Phase 5 Task 10: run on a bundle (spec section 11): the stamp, the refusals, the personas,
the replay header; analysis needs only the run directory."""

import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from claude_bully import cli
from claude_bully.analysis.replay import parse_replay_line, replay_cell
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.environments.world import hash_tree
from claude_bully.planner.bundle import (
    PLAN_FILE,
    BundleRefused,
    load_bundle_for_run,
    register_plan_personas,
)
from claude_bully.planner.dryrun import (
    dryrun_provider_factory,
    load_bundle_experiment,
    stubbed_experiment,
)
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import all_strategies
from tests.fixtures.director_stub import DRYRUN_KILL_AT, dryrun_killing, run_plan

runner = CliRunner()


@pytest.fixture
def runnable(tmp_path: Path, isolated_registry: None) -> Path:
    bundle, record = run_plan(tmp_path / "plans", through="validate")
    assert record.status == "runnable"
    return bundle.root


def _stub_run(root: Path, runs: Path, **kw: Any) -> Path:
    from claude_bully.planner.bundle import Bundle

    bundle, bundle_run = Bundle(root), load_bundle_for_run(root)
    register_plan_personas({n: s.model_dump(mode="json") for n, s in bundle_run.personas.items()})
    exp = stubbed_experiment(load_bundle_experiment(bundle))
    run_experiment(
        exp,
        runs_root=runs,
        worlds_dir=bundle_run.worlds_dir,
        provider_factory=dryrun_provider_factory(bundle, exp),
        plan_hash=kw.get("plan_hash", bundle_run.record.bundle_hash),
        plan=bundle_run.stamp,
    )
    return runs / exp.name


@pytest.mark.slow
def test_a_run_from_a_bundle_is_stamped_and_replays_its_hash(
    runnable: Path, tmp_path: Path
) -> None:
    run_dir = _stub_run(runnable, tmp_path / "runs")
    store = RunStore(run_dir.parent, run_dir.name)
    record = store.read_run()
    bundle = load_bundle_for_run(runnable)
    assert record.plan_hash is not None and record.plan_hash == bundle.record.bundle_hash
    assert record.plan is not None and set(record.plan.personas) == {"ferry_caller"}
    assert record.plan.expected is not None and record.plan.slug == bundle.record.slug
    # A6: each world the run reads is the bundle's copy, pinned by its hash
    worlds = runnable / "worlds"
    assert record.world_hashes and set(record.world_hashes) <= {p.name for p in worlds.iterdir()}
    assert record.world_hashes == {name: hash_tree(worlds / name) for name in record.world_hashes}
    text = replay_cell(store, store.list_cells()[0])
    lines = text.splitlines()
    env = next(i for i, ln in enumerate(lines) if ln.startswith("environment "))
    assert lines[env + 1] == f"plan hash {record.plan_hash[:8]}"
    parsed = parse_replay_line(lines[env + 1])
    assert parsed is not None and parsed.kind == "plan_hash"
    assert parsed.fields == {"hash": record.plan_hash[:8]}


@pytest.mark.slow
def test_analyze_needs_only_the_run_directory(runnable: Path, tmp_path: Path) -> None:
    run_dir = _stub_run(runnable, tmp_path / "runs")
    shutil.rmtree(runnable)  # plans/ moved away
    from claude_bully.strategies import base

    base._REGISTRY.pop("ferry_caller")  # a fresh process: the persona is registered from run.json
    assert analyze_run(run_dir, judge=False).exists()
    assert "ferry_caller" in all_strategies()


@pytest.mark.slow
def test_a_resumed_run_is_refused_on_a_hash_mismatch(runnable: Path, tmp_path: Path) -> None:
    _stub_run(runnable, tmp_path / "runs")
    with pytest.raises(ValueError, match="plan_hash"):
        _stub_run(runnable, tmp_path / "runs", plan_hash="0" * 64)


@pytest.mark.slow
def test_a_changed_or_not_runnable_bundle_is_refused(runnable: Path) -> None:
    (runnable / "plan.md").write_text("edited\n", "utf-8")
    with pytest.raises(
        BundleRefused, match="bundle changed since it was validated; run `plan validate` again"
    ):
        load_bundle_for_run(runnable)
    from claude_bully.planner.bundle import Bundle

    bundle = Bundle(runnable)
    record = bundle.read_record()
    bundle.write_record(record.model_copy(update={"status": "validated", "open_blocks": 1}))
    with pytest.raises(BundleRefused, match="validated, not runnable: 1 open block"):
        load_bundle_for_run(runnable)


@pytest.mark.slow
def test_a_not_runnable_bundle_names_its_first_failing_check(runnable: Path) -> None:
    from claude_bully.planner.bundle import Bundle
    from claude_bully.planner.records import LintRecord

    bundle = Bundle(runnable)
    record = bundle.read_record()
    lints = [
        LintRecord(lint_id="budget", severity="warn", doc_id="config.yaml", message="near"),
        LintRecord(lint_id="schema", severity="fail", doc_id="expected.yaml", message="no cell"),
        LintRecord(lint_id="budget", severity="fail", doc_id="config.yaml", message="over"),
    ]
    bundle.write_record(
        record.model_copy(update={"status": "validated", "open_blocks": 2, "lint_results": lints})
    )
    with pytest.raises(BundleRefused) as refused:
        load_bundle_for_run(runnable)
    assert str(refused.value) == (
        f"bundle {record.slug} is validated, not runnable: schema expected.yaml: no cell"
    )
    bundle.write_record(record.model_copy(update={"status": "failed", "lint_results": []}))
    with pytest.raises(BundleRefused, match="is failed, not runnable: stage 5 has not run$"):
        load_bundle_for_run(runnable)


@pytest.mark.slow
def test_the_cli_run_uses_the_bundles_worlds_and_stamps(
    runnable: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def fake_run(exp: Any, **kw: Any) -> Any:
        seen.update(kw)
        from claude_bully.runner.runner import RunSummary

        return RunSummary(run_id="x", cells_total=0)

    monkeypatch.setattr(cli, "run_experiment", fake_run)
    result = runner.invoke(
        cli.app, ["run", str(runnable / "config.yaml"), "--runs-root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert seen["worlds_dir"] == runnable / "worlds" and seen["plan_hash"]
    assert seen["plan"].slug == runnable.name
    # --only expands the cells, which resolve the bundle persona only once it is registered
    from claude_bully.strategies import base

    base._REGISTRY.pop("ferry_caller")
    only = runner.invoke(
        cli.app,
        ["run", str(runnable / "config.yaml"), "--only", "ferry_*", "--runs-root", str(tmp_path)],
    )
    assert only.exit_code == 0, only.output
    assert seen["only"] == "ferry_*"


@pytest.mark.slow
def test_an_explicit_worlds_dir_beside_a_bundle_is_refused_unless_it_is_the_bundles(
    runnable: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Review Focus 5
    """The refusal's text is checked on the exception, never on console output a long temporary
    path may wrap (review Minor 11); the CLI is checked for its exit code and for the accepted
    case the name promises."""
    from claude_bully.paths import DATA_DIR
    from claude_bully.planner.bundle import bundle_worlds_dir

    with pytest.raises(BundleRefused) as refused:
        bundle_worlds_dir(runnable, DATA_DIR / "worlds")
    assert str(DATA_DIR / "worlds") in str(refused.value)
    assert str(runnable / "worlds") in str(refused.value)
    assert bundle_worlds_dir(runnable, runnable / "worlds") == runnable / "worlds"
    assert bundle_worlds_dir(runnable, None) == runnable / "worlds"
    seen: dict[str, Any] = {}

    def fake_run(exp: Any, **kw: Any) -> Any:
        seen.update(kw)
        from claude_bully.runner.runner import RunSummary

        return RunSummary(run_id="x", cells_total=0)

    monkeypatch.setattr(cli, "run_experiment", fake_run)
    config = str(runnable / "config.yaml")
    bad = runner.invoke(cli.app, ["run", config, "--worlds-dir", str(DATA_DIR / "worlds")])
    assert bad.exit_code != 0 and seen == {}
    good = runner.invoke(
        cli.app,
        ["run", config, "--worlds-dir", str(runnable / "worlds"), "--runs-root", str(tmp_path)],
    )
    assert good.exit_code == 0, good.output
    assert seen["worlds_dir"] == runnable / "worlds"


@pytest.mark.slow
def test_the_cli_refuses_a_bundle_before_anything_is_written(
    runnable: Path, tmp_path: Path
) -> None:
    """Carry Q9: a bundle that is not runnable, or changed since stage 5, exits non-zero with
    no run directory made; a damaged plan.json is printed as ``error: <file>: ...`` (Task 9's
    error contract), exit 1."""
    from claude_bully.planner.bundle import Bundle

    runs = tmp_path / "runs"
    config = str(runnable / "config.yaml")
    bundle = Bundle(runnable)
    record = bundle.read_record()
    bundle.write_record(record.model_copy(update={"status": "validated"}))
    refused = runner.invoke(cli.app, ["run", config, "--runs-root", str(runs)])
    assert refused.exit_code == 2 and not runs.exists()
    bundle.write_record(record)
    (runnable / "plan.md").write_text("edited\n", "utf-8")
    changed = runner.invoke(cli.app, ["run", config, "--runs-root", str(runs)])
    assert changed.exit_code == 2 and not runs.exists()
    (runnable / PLAN_FILE).write_bytes(b"{not json\n")
    damaged = runner.invoke(cli.app, ["run", config, "--runs-root", str(runs)])
    assert damaged.exit_code == 1 and not runs.exists()
    assert damaged.output.startswith("error: ") and PLAN_FILE in damaged.output
    assert "Traceback" not in damaged.output


class _Killed(BaseException):
    """The kill: raised inside a double's call, before it returns; past every ``except
    Exception``, as a process killed there would be."""


def _comparable(run_dir: Path) -> dict[str, Any]:
    """The run as parity compares it: the stamp, and per conversation its status and turns
    less their timestamps and latencies."""
    store = RunStore(run_dir.parent, run_dir.name)
    record = store.read_run()
    conversations = {
        f"{cell}/rep{rep}": (
            store.read_conversation(cell, rep).status.value,
            [
                t.model_dump(mode="json", exclude={"timestamp", "latency_ms"})
                for t in store.read_turns(cell, rep)
            ],
        )
        for cell in store.list_cells()
        for rep in store.list_reps(cell)
    }
    return {"plan_hash": record.plan_hash, "plan": record.plan, "conversations": conversations}


@pytest.mark.slow
@pytest.mark.parametrize("role", ["target", "bully", "generator"])
def test_a_killed_bundle_run_resumes_from_its_record_to_the_unbroken_run(
    role: str, runnable: Path, tmp_path: Path
) -> None:
    """Resume parity, with the run's own kill (a double raising inside its call) and preflight
    Q50: the killed run registered its personas for its own span alone (none leak past it, the
    kill included); the resume is called with no stamp and registers the personas its
    ``RunRecord.plan`` recorded before ``expand_cells``; it ends where an unbroken run does."""
    from claude_bully.planner.bundle import Bundle

    bundle, bundle_run = Bundle(runnable), load_bundle_for_run(runnable)
    exp = stubbed_experiment(load_bundle_experiment(bundle))
    stamped: dict[str, Any] = {
        "worlds_dir": bundle_run.worlds_dir,
        "plan_hash": bundle_run.record.bundle_hash,
        "plan": bundle_run.stamp,
    }
    clean = tmp_path / "clean"
    run_experiment(
        exp, runs_root=clean, provider_factory=dryrun_provider_factory(bundle, exp), **stamped
    )
    assert "ferry_caller" not in all_strategies()
    killed = tmp_path / "killed"
    dying = dryrun_killing(role, DRYRUN_KILL_AT[role], error=_Killed)(bundle, exp)
    with pytest.raises(_Killed):
        run_experiment(exp, runs_root=killed, provider_factory=dying, **stamped)
    assert "ferry_caller" not in all_strategies()
    run_experiment(
        exp,
        runs_root=killed,
        worlds_dir=bundle_run.worlds_dir,
        provider_factory=dryrun_provider_factory(bundle, exp),
    )
    assert "ferry_caller" not in all_strategies()
    assert _comparable(killed / exp.name) == _comparable(clean / exp.name)


def test_register_plan_personas(isolated_registry: None, tmp_path: Path) -> None:
    from claude_bully.planner.bundle import bundle_personas
    from tests.fixtures.bundle_fixtures import good_bundle

    sheet = bundle_personas(good_bundle(tmp_path))["ferry_caller"].model_dump(mode="json")
    register_plan_personas({"ferry_caller": sheet})
    registered = all_strategies()["ferry_caller"]
    register_plan_personas({"ferry_caller": sheet})  # an equal sheet: left alone
    assert all_strategies()["ferry_caller"] is registered
    other = {**sheet, "win_condition": "another"}
    with pytest.raises(ValueError, match="ferry_caller"):
        register_plan_personas({"ferry_caller": other})
    with pytest.raises(ValueError, match="captor"):
        register_plan_personas({"captor": {**sheet, "name": "captor"}})
    with pytest.raises(ValueError, match="ferry_twin"):  # recorded under another name
        register_plan_personas({"ferry_twin": sheet})
    assert "ferry_twin" not in all_strategies()


def test_a_plain_config_takes_the_worlds_dir_and_no_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No plan.json beside the config: ``--worlds-dir`` is passed as given (``data/worlds``
    when absent) and the run is not stamped."""
    from claude_bully.runner.runner import DEFAULT_WORLDS_DIR, RunSummary
    from tests.conftest import STUB_SMOKE

    seen: list[dict[str, Any]] = []

    def fake_run(exp: Any, **kw: Any) -> Any:
        seen.append(kw)
        return RunSummary(run_id="x", cells_total=0)

    monkeypatch.setattr(cli, "run_experiment", fake_run)
    plain = ["run", str(STUB_SMOKE), "--runs-root", str(tmp_path)]
    assert runner.invoke(cli.app, plain).exit_code == 0
    assert runner.invoke(cli.app, [*plain, "--worlds-dir", str(tmp_path)]).exit_code == 0
    assert [kw["worlds_dir"] for kw in seen] == [DEFAULT_WORLDS_DIR, tmp_path]
    assert all(kw["plan_hash"] is None and kw["plan"] is None for kw in seen)
