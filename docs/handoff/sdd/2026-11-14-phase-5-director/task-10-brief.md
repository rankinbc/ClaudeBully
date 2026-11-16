### Task 10: `run` on a bundle

**Files:**
- Modify: `claude_bully/planner/bundle.py` (`BundleRun`, `BundleRefused`, `load_bundle_for_run`, `register_plan_personas`)
- Modify: `claude_bully/runner/runner.py` (`run_experiment(plan_hash=, plan=)`)
- Modify: `claude_bully/cli.py` (`run --worlds-dir`, bundle detection)
- Modify: `claude_bully/analysis/load.py` (`load_run` registers `RunRecord.plan`'s personas)
- Modify: `claude_bully/analysis/replay.py` (`replay_cell`, `render_replay(plan_hash=)`, `_SHAPES`)
- Modify: `tests/test_replay_parser.py` (the new shape's fixture)
- Test: `tests/test_bundle_run.py`

**Interfaces:**
- Consumes: Task 1's `PlanStamp`, `RunRecord.plan`, `bundle_hash`; Task 4a's `bundle_personas`; `strategies/bootstrap.ensure_registered`; Task 9's validated bundle (`run_plan(through="validate")`); `make_phased_premise`; `_REGISTRY`.
- Produces: `BundleRun(record: PlanRecord, worlds_dir: Path, personas: dict[str, PersonaSheet], stamp: PlanStamp)` (frozen dataclass); `BundleRefused(ValueError)`; `load_bundle_for_run(root: Path) -> BundleRun`; `bundle_worlds_dir(root: Path, worlds_dir: Path | None) -> Path` (the bundle's `worlds/`; an explicit `worlds_dir` that does not resolve to it raises `BundleRefused` naming both; review Minor 11); `register_plan_personas(personas: Mapping[str, Mapping[str, Any]]) -> None`; `run_experiment(..., plan_hash: str | None = None, plan: PlanStamp | None = None)`; `render_replay(..., plan_hash: str | None = None)`; the replay shape `("plan_hash", re.compile(r"^plan hash (?P<hash>[0-9a-f]{8})$"))`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bundle_run.py
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
from claude_bully.planner.bundle import BundleRefused, load_bundle_for_run, register_plan_personas
from claude_bully.planner.dryrun import dryrun_provider_factory, load_bundle_experiment, stubbed_experiment
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import all_strategies
from tests.fixtures.director_stub import run_plan

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
        exp, runs_root=runs, worlds_dir=bundle_run.worlds_dir,
        provider_factory=dryrun_provider_factory(bundle, exp),
        plan_hash=kw.get("plan_hash", bundle_run.record.bundle_hash), plan=bundle_run.stamp,
    )
    return runs / exp.name


@pytest.mark.slow
def test_a_run_from_a_bundle_is_stamped_and_replays_its_hash(runnable: Path, tmp_path: Path) -> None:
    run_dir = _stub_run(runnable, tmp_path / "runs")
    store = RunStore(run_dir.parent, run_dir.name)
    record = store.read_run()
    bundle = load_bundle_for_run(runnable)
    assert record.plan_hash == bundle.record.bundle_hash
    assert record.plan is not None and set(record.plan.personas) == {"ferry_caller"}
    assert record.plan.expected is not None and record.plan.slug == bundle.record.slug
    text = replay_cell(store, store.list_cells()[0])
    lines = text.splitlines()
    env = next(i for i, ln in enumerate(lines) if ln.startswith("environment "))
    assert lines[env + 1] == f"plan hash {record.plan_hash[:8]}"
    parsed = parse_replay_line(lines[env + 1])
    assert parsed is not None and parsed.shape == "plan_hash"


@pytest.mark.slow
def test_analyze_needs_only_the_run_directory(runnable: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    with pytest.raises(BundleRefused, match="bundle changed since it was validated; run `plan validate` again"):
        load_bundle_for_run(runnable)
    from claude_bully.planner.bundle import Bundle

    bundle = Bundle(runnable)
    record = bundle.read_record()
    bundle.write_record(record.model_copy(update={"status": "validated", "open_blocks": 1}))
    with pytest.raises(BundleRefused, match="validated, not runnable: 1 open block"):
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
    result = runner.invoke(cli.app, ["run", str(runnable / "config.yaml"), "--runs-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert seen["worlds_dir"] == runnable / "worlds" and seen["plan_hash"]
    assert seen["plan"].slug == runnable.name


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
    assert str(DATA_DIR / "worlds") in str(refused.value) and str(runnable / "worlds") in str(refused.value)
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
    good = runner.invoke(cli.app, ["run", config, "--worlds-dir", str(runnable / "worlds"), "--runs-root", str(tmp_path)])
    assert good.exit_code == 0, good.output
    assert seen["worlds_dir"] == runnable / "worlds"


def test_register_plan_personas(isolated_registry: None, tmp_path: Path) -> None:
    from tests.fixtures.bundle_fixtures import good_bundle
    from claude_bully.planner.bundle import bundle_personas

    sheet = bundle_personas(good_bundle(tmp_path))["ferry_caller"].model_dump(mode="json")
    register_plan_personas({"ferry_caller": sheet})
    register_plan_personas({"ferry_caller": sheet})  # an equal sheet: left alone
    other = {**sheet, "win_condition": "another"}
    with pytest.raises(ValueError, match="ferry_caller"):
        register_plan_personas({"ferry_caller": other})
    with pytest.raises(ValueError, match="captor"):
        register_plan_personas({"captor": {**sheet, "name": "captor"}})
```

`tests/test_replay_parser.py` gains `plan hash 0123abcd` in its fixtures, parsed as `plan_hash`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_bundle_run.py tests/test_replay_parser.py -q -m "slow or not slow"`
Expected: FAIL at import (`load_bundle_for_run`, `register_plan_personas` do not exist).

- [ ] **Step 3: Implement**

`load_bundle_for_run(root)`: reads the record; refuses a status other than `runnable` with `f"bundle {slug} is {status}, not runnable: {reason}"` (the first failing `LintRecord` as `<lint_id> <doc_id>: <message>`, else `<n> open block(s)`, else `stage 5 has not run`); refuses `bundle_hash(root) != record.bundle_hash` with `"bundle changed since it was validated; run `plan validate` again"`; returns the worlds directory, the personas and `PlanStamp(slug, personas={name: sheet dumped}, expected=<expected.yaml loaded as a dict>)`.

`register_plan_personas(personas)`: `ensure_registered()` first (R-registry: in a fresh process the coded strategies are not yet registered, so the coded-strategy refusal below would read an empty registry and a later load would overwrite the persona silently); then, for each name, a registered class with an equal `sheet` (`cls.sheet.model_dump(mode="json") == dumped`) is left alone; a registered class with a different sheet, or none (a coded strategy), raises `ValueError` naming the name and both sources; else `make_phased_premise(PersonaSheet.model_validate(dumped))`.

`run_experiment`: before the `check_condition` loop, registers `plan.personas` when `plan` is given, else the personas of an existing store's `RunRecord.plan`; a store that exists with a `plan_hash` other than the given one raises `ValueError(f"the run's plan_hash {old[:12]} is not the bundle's {new[:12]}; start a new run")`; a new `RunRecord` gets `plan_hash=plan_hash, plan=plan`. A plain call (`plan=None`, no stamp in the store) is unchanged, and the golden plain records are byte-identical.

`cli.run`: `worlds_dir: Annotated[Path | None, typer.Option("--worlds-dir", help=...)] = None`; when `config.parent / "plan.json"` exists, `load_bundle_for_run(config.parent)` (a `BundleRefused` is `typer.BadParameter`-style output and exit 2), `bundle_worlds_dir(config.parent, worlds_dir)` (an explicit `--worlds-dir` that does not resolve to the bundle's is refused naming both), `register_plan_personas`, and `run_experiment(..., worlds_dir=<the bundle's>, plan_hash=..., plan=...)`; otherwise `worlds_dir or DEFAULT_WORLDS_DIR`. The bundle is detected and its personas registered before the `--only` check, which calls `expand_cells` and would not resolve a bundle persona otherwise (R-registry, review I1).

`load_run`: after `ensure_registered()`, `if run.plan is not None: register_plan_personas(run.plan.personas)`.

`replay_cell` passes `plan_hash=store.read_run().plan_hash`; `render_replay` appends `f"plan hash {plan_hash[:8]}"` after the environment line (after the header when there is none); `_SHAPES` gains the shape after the environment shape.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_bundle_run.py tests/test_replay_parser.py tests/test_cli.py tests/test_runner.py -q -m "slow or not slow"`, then the gate.
Expected: PASS; the plain goldens unchanged.

- [ ] **Step 5: Docs-sync and commit**

docs/00 section E: `run --worlds-dir` and bundle detection; section B: `RunRecord.plan` written by `run` on a bundle; docs/08 "CLI": `run plans/<slug>/config.yaml` refuses what is not runnable or changed. Spec "As planned": none new. HANDOFF: the parked N2 line stays until Task 11.

```bash
git add claude_bully/planner/bundle.py claude_bully/runner/runner.py claude_bully/cli.py claude_bully/analysis/load.py \
  claude_bully/analysis/replay.py tests/test_bundle_run.py tests/test_replay_parser.py docs/00-RECONCILED.md \
  docs/08-DIRECTOR.md docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 10, run on a bundle: --worlds-dir, the refusals, the stamp, the personas and the replay header

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

