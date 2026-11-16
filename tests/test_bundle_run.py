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
    with pytest.raises(ValueError, match="plan_hash") as refused:
        _stub_run(runnable, tmp_path / "runs", plan_hash="0" * 64)
    assert "--run-id" in str(refused.value)  # review N2: how to start a new run


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
    # review M2: a failed stage is named, with its error, before the fallback
    failed = record.stages[-1].model_copy(update={"status": "failed", "error": "a scan hit"})
    stages = [*record.stages[:-1], failed]
    bundle.write_record(
        record.model_copy(update={"status": "failed", "lint_results": [], "stages": stages})
    )
    with pytest.raises(BundleRefused) as refused:
        load_bundle_for_run(runnable)
    assert str(refused.value) == (
        f"bundle {record.slug} is failed, not runnable: {failed.stage} failed: a scan hit"
    )
    bundle.write_record(record.model_copy(update={"status": "revised", "lint_results": []}))
    with pytest.raises(BundleRefused, match="is revised, not runnable: stage 5 has not run$"):
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


_VOLATILE = frozenset({"ts", "timestamp", "latency_ms", "created_at", "started_at", "finished_at"})


def _scrubbed(data: Any) -> Any:
    """``data`` less its wall-clock keys, at every depth."""
    if isinstance(data, dict):
        return {k: _scrubbed(v) for k, v in data.items() if k not in _VOLATILE}
    if isinstance(data, list):
        return [_scrubbed(v) for v in data]
    return data


def _comparable(run_dir: Path) -> dict[str, Any]:
    """The run as parity compares it (review M4): the stamp, and per conversation its status,
    turns, tool calls, authority calls, trigger records (less the resume record a resumed rep
    adds), generated documents and world snapshot, each less its wall-clock keys."""
    store = RunStore(run_dir.parent, run_dir.name)
    record = store.read_run()

    def dumped(items: Any) -> list[Any]:
        return [_scrubbed(item.model_dump(mode="json")) for item in items]

    conversations = {
        f"{cell}/rep{rep}": {
            "status": store.read_conversation(cell, rep).status.value,
            "turns": dumped(store.read_turns(cell, rep)),
            "tools": dumped(store.read_tool_calls(cell, rep)),
            "authority": dumped(store.read_authority_calls(cell, rep)),
            "triggers": [
                r
                for r in dumped(store.read_trigger_records(cell, rep))
                if r.get("type") != "resume"
            ],
            "generated": dumped(store.read_generated(cell, rep)),
            "world": _scrubbed(store.read_world_record(cell, rep)),
        }
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
    register_plan_personas({"ferry_caller": other})  # another plan's sheet: replaced (review I1)
    replaced = all_strategies()["ferry_caller"]
    assert replaced.sheet.win_condition == "another"  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="captor"):  # a coded strategy is never replaced
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


def _other_bundle(plans: Path, win_condition: str) -> Path:
    """A second runnable bundle of the same request whose ``ferry_caller`` sheet has another
    ``win_condition``, validated again (``plan validate``)."""
    import yaml

    from claude_bully.planner.director import Director
    from tests.fixtures.director_stub import PlannerStub, ReviewerStub, StubFactory
    from tests.helpers import WORLDS_DIR

    bundle, _ = run_plan(plans, through="validate")
    path = bundle.root / "personas" / "ferry_caller.yaml"
    data = yaml.safe_load(path.read_bytes().decode("utf-8"))
    data["win_condition"] = win_condition
    path.write_bytes(yaml.safe_dump(data, sort_keys=False, width=88).encode("utf-8"))
    factory = StubFactory(PlannerStub(), ReviewerStub())
    director = Director.open(bundle.root, provider_factory=factory, worlds_dir=WORLDS_DIR)
    assert director.revalidate().status == "runnable"
    return bundle.root


def _sheet_win(run_dir: Path) -> set[str]:
    """The ``win_condition`` of every bundle-persona strategy ``load_run`` builds for the run."""
    from claude_bully.analysis.load import load_run

    loaded = load_run(run_dir)
    premises = [getattr(s, "premise", None) or s for s in loaded.strategies.values()]
    return {
        p.sheet.win_condition  # type: ignore[attr-defined]
        for p in premises
        if type(p).name == "ferry_caller"
    }


@pytest.mark.slow
def test_two_bundle_runs_sharing_a_persona_name_are_reported_in_one_process(
    runnable: Path, tmp_path: Path
) -> None:
    """Review I1: ``readme-results`` analyzes each run in one process; the second bundle's
    ``ferry_caller``, another sheet under the same name, replaces the first's, so the command
    exits 0 and each run is loaded with its own sheet."""
    win_b = "B: the model repeats the ferry claim as fact."
    other = _other_bundle(tmp_path / "plans_b", win_b)
    both = tmp_path / "both"
    both.mkdir()
    for name, root in (("ra", runnable), ("rb", other)):
        run_dir = _stub_run(root, tmp_path / f"runs_{name}")
        shutil.move(str(run_dir), str(both / name))
    # the second run, in the same process, ran on its own sheet (a composition is rebuilt over
    # the persona class registered again, never reused by name)
    store = RunStore(both, "rb")
    spoken = [
        store.read_conversation(c, r).win_condition
        for c in store.list_cells()
        for r in store.list_reps(c)
    ]
    assert any(win_b in w for w in spoken) and not any(
        load_bundle_for_run(runnable).personas["ferry_caller"].win_condition in w for w in spoken
    )
    from claude_bully.strategies import base

    base._REGISTRY.pop("ferry_caller")  # a fresh process: registered from run.json alone
    readme = tmp_path / "README.md"
    readme.write_text("# results\n", "utf-8")
    result = runner.invoke(
        cli.app, ["readme-results", "ra", "rb", "--runs-root", str(both), "--readme", str(readme)]
    )
    assert result.exit_code == 0, repr(result.exception)
    win_a = load_bundle_for_run(runnable).personas["ferry_caller"].win_condition
    assert win_a != win_b
    assert _sheet_win(both / "ra") == {win_a}
    assert _sheet_win(both / "rb") == {win_b}
    assert _sheet_win(both / "ra") == {win_a}


def _files(run_dir: Path) -> dict[str, bytes]:
    return {
        p.relative_to(run_dir).as_posix(): p.read_bytes()
        for p in sorted(run_dir.rglob("*"))
        if p.is_file()
    }


@pytest.mark.slow
def test_a_stamp_goes_with_its_hash_and_a_resume_keeps_its_own(
    runnable: Path, tmp_path: Path
) -> None:
    """Review I2: ``plan`` and ``plan_hash`` are given both or neither, and a resume never runs
    on a stamp other than the one its run records; each refusal comes before any write."""
    from claude_bully.planner.bundle import Bundle

    bundle, bundle_run = Bundle(runnable), load_bundle_for_run(runnable)
    exp = stubbed_experiment(load_bundle_experiment(bundle))
    digest = bundle_run.record.bundle_hash
    sheet = bundle_run.stamp.personas["ferry_caller"]
    other = bundle_run.stamp.model_copy(
        update={"personas": {"ferry_caller": {**sheet, "win_condition": "B"}}}
    )
    runs = tmp_path / "runs"

    def run(provider_factory: Any = None, **kw: Any) -> Any:
        return run_experiment(
            exp,
            runs_root=runs,
            worlds_dir=bundle_run.worlds_dir,
            provider_factory=provider_factory or dryrun_provider_factory(bundle, exp),
            **kw,
        )

    with pytest.raises(ValueError, match="plan and plan_hash"):
        run(plan=bundle_run.stamp)  # a new run: nothing made
    with pytest.raises(ValueError, match="plan and plan_hash"):
        run(plan_hash=digest)
    assert not runs.exists()
    dying = dryrun_killing("target", DRYRUN_KILL_AT["target"], error=_Killed)(bundle, exp)
    with pytest.raises(_Killed):
        run(dying, plan_hash=digest, plan=bundle_run.stamp)
    before = _files(runs / exp.name)
    with pytest.raises(ValueError, match="plan and plan_hash"):
        run(plan=other)  # the review's probe R4: refused, never run on B's sheet
    with pytest.raises(BundleRefused, match="the run's plan is not the one given"):
        run(plan_hash=digest, plan=other)
    assert _files(runs / exp.name) == before
    run()  # neither: the resume runs on the stamp its run records
    assert _sheet_win(runs / exp.name) == {sheet["win_condition"]}


def test_the_runner_does_not_import_the_planner_side_that_imports_it() -> None:
    """Review M3: a planner module that imports the runner (``planner/records.py`` reads
    ``runner/store.py``), or one of those, is never imported by a runner module, so the two
    never import each other; the plan-persona registration and ``BundleRefused`` live in
    ``runner/plan_stamp.py``. The planner's text lints, which import no runner module, stay
    importable from the runner (``runner/env_turn.py`` reads ``planner/llm_lint.py``)."""
    import re

    package = Path(cli.__file__).parent
    imports = re.compile(r"^\s*(?:from|import) claude_bully\.(\w+)\.(\w+)", re.MULTILINE)

    def imported(path: Path) -> set[tuple[str, str]]:
        return {(m[1], m[2]) for m in imports.finditer(path.read_text("utf-8"))}

    planner = {path.stem: imported(path) for path in (package / "planner").glob("*.py")}
    runner_side = {name for name, deps in planner.items() if any(d[0] == "runner" for d in deps)}
    grew = True
    while grew:
        more = {
            n
            for n, deps in planner.items()
            if any(d in {("planner", r) for r in runner_side} for d in deps)
        }
        grew = not more <= runner_side
        runner_side |= more
    assert {"records", "bundle"} <= runner_side
    offenders = [
        f"{path.name}: planner.{dep}"
        for path in sorted((package / "runner").glob("*.py"))
        for pkg, dep in imported(path)
        if pkg == "planner" and dep in runner_side
    ]
    assert offenders == []
