### Task 9: Stage 5, the `plan` sub-app and the whole parity suite

**Files:**
- Modify: `claude_bully/planner/director.py` (`Director.validate`, `Director.review_round`)
- Create: `claude_bully/planner/cli.py`
- Modify: `claude_bully/cli.py` (`app.add_typer(plan_app, name="plan")`)
- Test: `tests/test_plan_cli.py`, `tests/test_plan_parity.py`

**Interfaces:**
- Consumes: Tasks 4a, 4b and 5's `lint_bundle`, `dry_run`, `dry_run_id`; Tasks 7a and 7b's `Director`, `run_plan`, `comparable`, `hashed_files`, `cache_keys`, `StubFactory`, `materialize`; Task 8's `findings_of`, `render_review`; `bundle_hash`; `runner/wait.wait_on_rate_limit`; `cli.RATE_LIMIT_EXIT_CODE`, `WaitMinutes`; `tests/fixtures/fake_claude.py`.
- Produces: `Director.validate() -> None` (replaces an existing validate `StageRecord`, R-validate-status); `Director.review_round() -> None` (D-rounds: archives the current review, revise and validate records and transcripts in three ordered writes when a committed review stage exists, else finishes an archive in progress, then runs stages 3 to 5); `planner/cli.plan_app: typer.Typer`; `request_from_flags(question: str | None, *, request: Path | None, targets: str | None, budget: str | None, scope: str | None, hypotheses: str | None, constraint: Sequence[str], slug: str | None, world: str | None, base_world: str | None, seed: int | None) -> PlanRequest` (a `--request` file is the base; each flag given replaces its field; `--targets` entries are `provider:model` or a bare model on `claude_code`); `cell_line(cell: DryRunCell) -> str` (`<cell_id> <status> top_rung=<top_rung> rungs=[<a>,<b>] calls>=<n>`); `bundle_diff(a: Path, b: Path) -> str`; `world_diff(bundle: Bundle, worlds_dir: Path) -> str`; `PlanProviders` (the module-level `ProviderFactory` the sub-app passes to the Director, `build_provider` in production), `WORLDS_DIR` (the shipped worlds a reused world is copied from, `environments/world.WORLDS_DIR` in production) and `PlanCheckpoint: Checkpoint | None` (the kill seam the sub-app passes as the Director's `checkpoint`, None in production; review Minor 1); tests monkeypatch all three.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_cli.py
"""Phase 5 Task 9: stage 5 and the plan sub-app (spec sections 7, 11)."""

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_bully import cli
from claude_bully.planner import cli as plan_cli
from claude_bully.planner.bundle import Bundle
from claude_bully.planner.cli import cell_line, request_from_flags
from claude_bully.planner.request import PlanBudget
from tests.fixtures.director_stub import REQUEST, PlannerStub, ReviewerStub, StubFactory
from tests.helpers import WORLDS_DIR

runner = CliRunner()


@pytest.fixture
def stubs(monkeypatch: pytest.MonkeyPatch, isolated_registry: None) -> tuple[PlannerStub, ReviewerStub]:
    planner, reviewer = PlannerStub(), ReviewerStub()
    monkeypatch.setattr(plan_cli, "PlanProviders", StubFactory(planner, reviewer))
    monkeypatch.setattr(plan_cli, "WORLDS_DIR", WORLDS_DIR)
    return planner, reviewer


def _new(tmp_path: Path, *extra: str) -> object:
    return runner.invoke(
        cli.app,
        ["plan", "new", REQUEST.question, "--base-world", "mini", "--hypotheses", "9",
         "--budget", "18,3,4", "--plans-root", str(tmp_path), *extra],
    )


@pytest.mark.slow
def test_plan_new_no_confirm_ends_runnable_and_prints_a_line_per_cell(tmp_path: Path, stubs: object) -> None:
    result = _new(tmp_path, "--no-confirm")
    assert result.exit_code == 0, result.output
    record = Bundle(next(p for p in tmp_path.iterdir() if p.name != "_cache")).read_record()
    assert record.status == "runnable" and record.bundle_hash and record.open_blocks == 0
    for cell in record.dry_run:
        assert cell_line(cell) in result.output
    assert "status runnable" in result.output
    assert not (Bundle(tmp_path / record.slug).root / ".attempt.json").exists()


def test_plan_new_without_no_confirm_stops_after_stage_1_and_exits_0(tmp_path: Path, stubs: object) -> None:
    result = _new(tmp_path)
    assert result.exit_code == 0, result.output  # D-exit
    assert "plan continue" in result.output and "plan.md" in result.output


def test_plan_new_on_an_existing_slug_with_another_request_is_refused(tmp_path: Path, stubs: object) -> None:
    assert _new(tmp_path).exit_code == 0  # Review Focus 3
    result = _new(tmp_path, "--seed", "7")
    assert result.exit_code != 0 and "seed" in result.output


@pytest.mark.slow
def test_plan_continue_and_validate_and_review(tmp_path: Path, stubs: object) -> None:
    _new(tmp_path)
    root = next(p for p in tmp_path.iterdir() if p.name != "_cache")
    assert runner.invoke(cli.app, ["plan", "continue", str(root)]).exit_code == 0
    assert runner.invoke(cli.app, ["plan", "validate", str(root)]).exit_code == 0
    (root / "plan.md").write_text((root / "plan.md").read_text("utf-8") + "Edited.\n", "utf-8")
    result = runner.invoke(cli.app, ["plan", "review", str(root)])
    assert result.exit_code == 0, result.output
    record = Bundle(root).read_record()
    assert len(record.rounds) == 1 and (root / "transcripts" / "review-1.md").is_file()  # D-rounds
    assert "plan.md" in record.edited
    # review I5: every archived call names its own round's transcript, which exists
    archived = [c for stage in record.rounds[0] for c in stage.calls]
    assert archived and all(c.transcript.startswith("transcripts/round-1/") for c in archived)
    assert all((root / c.transcript).is_file() for c in archived)
    current = {c.transcript for s in record.stages for c in s.calls}
    assert not current & {c.transcript for c in archived}


@pytest.mark.slow
def test_a_review_round_killed_between_the_archive_copy_and_the_record_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stubs: object
) -> None:
    """Review I5 (D-rounds): killed after the transcripts are copied and before the record moves
    them, the committed review calls still name files that exist; `plan review` again archives
    once and ends as an unbroken round does."""
    from tests.fixtures.director_stub import Crash, hashed_files

    _new(tmp_path / "a", "--no-confirm")
    _new(tmp_path / "b", "--no-confirm")
    a, b = (next(p for p in (tmp_path / x).iterdir() if p.name != "_cache") for x in ("a", "b"))

    def die(step: str, purpose: str) -> None:
        if (step, purpose) == ("archived", "review"):
            raise Crash

    monkeypatch.setattr(plan_cli, "PlanCheckpoint", die)
    with pytest.raises(Crash):
        runner.invoke(cli.app, ["plan", "review", str(b)], catch_exceptions=False)
    held = Bundle(b).read_record()
    assert held.rounds == [] and all((b / c.transcript).is_file() for s in held.stages for c in s.calls)
    monkeypatch.setattr(plan_cli, "PlanCheckpoint", None)
    assert runner.invoke(cli.app, ["plan", "review", str(b)]).exit_code == 0
    assert runner.invoke(cli.app, ["plan", "review", str(a)]).exit_code == 0
    assert len(Bundle(b).read_record().rounds) == len(Bundle(a).read_record().rounds) == 1
    assert hashed_files(b) == hashed_files(a)


@pytest.mark.slow
def test_materialize_rebuilds_the_authored_files_from_the_record_and_the_transcripts(
    tmp_path: Path, stubs: object
) -> None:
    """Spec sections 1 and 15 (review I8): delete every file a committed call owns and
    review.md; materialize rewrites the first set and render_review(findings_of(...)) the second
    (review.md is derived from the review and revise transcripts, never a call's output). Base
    files no call overwrote are checked against base_files, not rebuilt: they came from
    data/worlds/, which may have moved."""
    from claude_bully.planner.bundle import materialize
    from claude_bully.planner.director import findings_of, render_review
    from tests.fixtures.director_stub import hashed_files

    _new(tmp_path, "--no-confirm")
    root = next(p for p in tmp_path.iterdir() if p.name != "_cache")
    bundle = Bundle(root)
    record = bundle.read_record()
    before = hashed_files(root)
    owned = {path for s in record.stages for c in s.calls for path in c.outputs}
    for rel in owned | {"review.md"}:
        (root / rel).unlink()
    assert set(materialize(bundle, record)) == owned
    bundle.write_file("review.md", render_review(findings_of(bundle, record)))
    assert hashed_files(root) == before
    index = bundle.index()
    for rel, sha in record.base_files.items():
        if rel not in owned:
            assert index[rel] == sha


@pytest.mark.slow
def test_plan_validate_in_a_fresh_interpreter_keeps_every_strategy(tmp_path: Path) -> None:
    """Review I1: in a fresh process the registry loads lazily; stage 5's two persona blocks
    (the lints, then the dry run) must both see the 36 strategies and the bundle's persona."""
    import subprocess

    from claude_bully.paths import REPO_ROOT
    from tests.fixtures.bundle_fixtures import good_bundle

    bundle = good_bundle(tmp_path)
    out = subprocess.run(
        [sys.executable, "-c", "from claude_bully.cli import app; app()", "plan", "validate", str(bundle.root)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "status runnable" in out.stdout


def test_a_rate_limit_exits_3_and_the_same_command_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    planner = PlannerStub(modes={"manifest": "rate_limit"})  # a raising mode fires once (R-stub-modes)
    monkeypatch.setattr(plan_cli, "PlanProviders", StubFactory(planner, ReviewerStub()))
    monkeypatch.setattr(plan_cli, "WORLDS_DIR", WORLDS_DIR)
    assert _new(tmp_path, "--no-confirm").exit_code == cli.RATE_LIMIT_EXIT_CODE
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", slept.append)
    root = next(p for p in tmp_path.iterdir() if p.name != "_cache")
    result = runner.invoke(cli.app, ["plan", "continue", str(root), "--wait-on-rate-limit", "5"])
    assert result.exit_code == 0 and slept == []  # the window passed; nothing to wait for


@pytest.mark.slow
def test_a_validated_bundle_that_is_not_runnable_exits_1(tmp_path: Path, stubs: object, monkeypatch: pytest.MonkeyPatch) -> None:
    _, reviewer = stubs  # type: ignore[misc]
    reviewer.verdicts = {1: "present"}
    result = _new(tmp_path, "--no-confirm")
    assert result.exit_code == 1 and "status failed" in result.output
    root = next(p for p in tmp_path.iterdir() if p.name != "_cache")
    again = runner.invoke(cli.app, ["plan", "continue", str(root)])
    assert again.exit_code == 1 and "open block" in again.output
    validated = runner.invoke(cli.app, ["plan", "validate", str(root)])
    assert validated.exit_code == 1 and "status validated" in validated.output
    record = Bundle(root).read_record()
    assert [s.stage for s in record.stages].count("validate") == 1  # replaced, R-validate-status
    # the open-block message keys on stage 4 and open_blocks, not on the status (review Minor 15)
    after = runner.invoke(cli.app, ["plan", "continue", str(root)])
    assert after.exit_code == 1 and "open block" in after.output


def test_request_from_flags() -> None:
    req = request_from_flags(
        "q", request=None, targets="sonnet,anthropic:claude-opus-5-5", budget="8,1,2,400",
        scope="premises,environment", hypotheses="2,9", constraint=["no generator"], slug=None,
        world="fresh", base_world=None, seed=3,
    )
    assert [(t.provider.value, t.model) for t in req.target_models] == [
        ("claude_code", "sonnet"), ("anthropic", "claude-opus-5-5"),
    ]
    assert req.budget == PlanBudget(max_turns=8, n_per_cell=1, max_cells=2, max_calls=400)
    assert (req.scope, req.hypotheses, req.constraints, req.world, req.seed) == (
        ["premises", "environment"], [2, 9], ["no generator"], "fresh", 3,
    )


@pytest.mark.slow
def test_plan_diff_of_two_bundles_and_of_a_bundle_against_its_shipped_world(tmp_path: Path, stubs: object) -> None:
    _new(tmp_path / "a", "--no-confirm")
    a = next(p for p in (tmp_path / "a").iterdir() if p.name != "_cache")
    b = tmp_path / "b" / a.name
    import shutil

    shutil.copytree(a, b)
    (b / "plan.md").write_text("changed\n", "utf-8")
    out = runner.invoke(cli.app, ["plan", "diff", str(a), str(b)]).output
    assert "--- " in out and "plan.md" in out and "+changed" in out
    one = runner.invoke(cli.app, ["plan", "diff", str(a), "--worlds-dir", str(WORLDS_DIR)]).output
    assert "worlds/mini: the shipped world has not moved since the copy" in one


def test_a_redone_call_on_the_fake_claude_starts_a_new_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    """Spec section 6, "Sessions": a call redone after a kill is a fresh session, never a
    --resume of the dead attempt's (the TwinAsker precedent, tests/test_poisoned_well_fires.py)."""
    from claude_bully.config import RoleConfig
    from claude_bully.enums import ProviderKind
    from claude_bully.planner.director import Director
    from claude_bully.providers.base import build_provider
    from tests.conftest import FAKE_CLAUDE
    from tests.fixtures.director_stub import Crash, Kill

    log = tmp_path / "fake_claude.log"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    role = RoleConfig(provider=ProviderKind.claude_code, model="m", command=[sys.executable, str(FAKE_CLAUDE)])
    request = REQUEST.model_copy(update={"planner_model": role})

    def die_after_transcript(step: str, purpose: str) -> None:
        if (step, purpose) == ("transcript", "plan"):
            raise Crash

    director = Director.new(request, plans_root=tmp_path / "plans", provider_factory=build_provider,
                            worlds_dir=WORLDS_DIR, checkpoint=die_after_transcript)
    with pytest.raises(Crash):
        director.run(through="plan")
    Director.open(director.bundle.root, provider_factory=build_provider, worlds_dir=WORLDS_DIR).run(through="plan")
    calls = [json.loads(line)["argv"] for line in log.read_text(encoding="utf-8").splitlines()]
    assert [("--resume" in a, "--session-id" in a) for a in calls] == [(False, True), (False, True)]
```

```python
# tests/test_plan_parity.py
"""Phase 5 Task 9: resume parity at every kill point of spec section 8, through the CLI: one
clean `plan new --no-confirm`, then one plan killed at each point and continued with the same
command. Each point's narrower test lives with its task (D-kill placement); this is the whole
suite in one place."""

from pathlib import Path

import pytest

from tests.fixtures.director_stub import Kill, cache_keys, comparable, hashed_files, run_plan
from tests.test_director_author import DOC1, DOC3, REPAIRED
from tests.test_director_review import _doc1

POINTS = {
    "K1": dict(crash_at="plan"),
    "K2": dict(crash_at="manifest"),
    "K3": dict(crash_at=f"file:{DOC3}"),
    "K4": dict(kill=Kill("transcript", f"file:{DOC1}")),
    "K5": dict(kill=Kill("record", f"file:{DOC1}")),
    "K6": dict(kill=Kill("files", f"file:{DOC1}")),
    "K7": dict(crash_at=f"repair:{REPAIRED}", modes={f"file:{REPAIRED}": "close_fail"}),
    "K8": dict(reviewer_crash_at="review:lines"),
    "K9": dict(crash_at="revise:DOC1"),
    "K10": dict(reviewer_crash_at="confirm:DOC1"),
    "K11": dict(kill=Kill("stage", "author")),
    "K12": dict(dryrun_kill="target"),
    "K13": dict(kill=Kill("dryrun", "validate")),
    # the two points the plan review added: the manifest's commit (R-commit) and the review
    # render before the stage flag (R-review-md)
    "K5-manifest": dict(kill=Kill("record", "manifest")),
    "K11-review": dict(kill=Kill("rendered", "review")),
}
NO_DEAD_CALL = {"K5", "K6", "K11", "K12", "K13", "K5-manifest", "K11-review"}


@pytest.mark.slow
@pytest.mark.parametrize("point", list(POINTS))
def test_every_kill_point_resumes_to_the_unbroken_bundle(point: str, tmp_path: Path, isolated_registry: None) -> None:
    spec = {k: (v.replace("DOC1", _doc1()) if isinstance(v, str) else v) for k, v in POINTS[point].items()}
    modes = spec.pop("modes", {})
    clean_bundle, clean = run_plan(tmp_path / "clean", through="validate", modes=modes, via_cli=True)
    bundle, record = run_plan(tmp_path / "killed", through="validate", modes=modes, via_cli=True, **spec)
    assert record.status == clean.status == "runnable"
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert record.bundle_hash == clean.bundle_hash
    assert comparable(record, ignore_dry_run_resume=point == "K12") == comparable(
        clean, ignore_dry_run_resume=point == "K12"
    )
    assert len(record.resumed) == (0 if point in NO_DEAD_CALL else 1)
    if point == "K12":
        assert any(c.resumed_after_dead_attempt for c in record.dry_run)
    assert cache_keys(tmp_path / "killed") <= cache_keys(tmp_path / "clean")
```

(`run_plan` gains `via_cli: bool = False`, which drives `plan new --no-confirm` and, after a `Crash`, `plan continue` through `CliRunner` with `PlanProviders`, `WORLDS_DIR` and `PlanCheckpoint` patched (the `kill` is passed as `PlanCheckpoint`, the named seam, review Minor 1; it is set back to None for the `continue`); `dryrun_kill=<role>` wraps the dry run's factory as Task 5's `_killing` does.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_plan_cli.py tests/test_plan_parity.py -q -m "slow or not slow"`
Expected: FAIL at import (`claude_bully.planner.cli` does not exist).

- [ ] **Step 3: Implement**

`Director.validate()`: open the stage (replacing an existing validate `StageRecord`: one record per stage, R-validate-status) and adopt edits; remove every `write_atomic` leftover (R-tmp); `static = lint_bundle(bundle)`; when a `schema` result fails, no dry run, and the `dry_run` lint result `"not run: the bundle does not load"` is added; else `cells = dry_run(bundle)`, `record.dry_run = cells`, `record.dry_run_id = dry_run_id(bundle)`, the record written, `checkpoint("dryrun", "validate")`, `results = lint_bundle(bundle, dry_run=cells)`; `record.lint_results = [LintRecord.of(r) for r in results]`; `record.bundle_hash = bundle_hash(bundle.root)`; `bundle.clear_attempt()`; the stage committed; status `runnable` when no result is `fail` and `open_blocks == 0`, else `validated` (also on a plan that had failed with open blocks: `plan validate` reports the stage 5 result, and the open-block message of `continue` keys on stage 4, R-validate-status). The dry run is a full stub run with its own resume (K12, K13); stage 5 makes no planner or reviewer call.

`Director.review_round()` (D-rounds): when the current stage list holds a committed `review` stage, (1) copy every transcript of the current review, revise and validate calls to `transcripts/round-<n>/<same name>` and `review.md` to `transcripts/review-<n>.md` (`n = len(rounds) + 1`), `checkpoint("archived", "review")`; (2) one record write that moves those three `StageRecord`s into `rounds` with each call's `transcript` rewritten to its round path; (3) delete the old top-level transcripts. Otherwise it runs (3) alone, which is idempotent: every top-level `review-*`, `revise-*` or `validate-*` transcript no current call names goes. Then it runs stages 3 to 5. A kill after (1) leaves the record pointing at files that still exist; a kill after (2) leaves only (3) to do.

`planner/cli.py`: `plan_app = typer.Typer(help="The Director: a research question to a validated run bundle.", no_args_is_help=True)`, with the five commands of spec section 11 and their flags; `new`, `continue` and `review` run the Director, built with `provider_factory=PlanProviders`, `worlds_dir=WORLDS_DIR` and `checkpoint=PlanCheckpoint` (the module-level seams), through `wait_on_rate_limit_(lambda: ..., wait_on_rate_limit, say=_say)` and turn a `RateLimitExit` into `typer.Exit(code=RATE_LIMIT_EXIT_CODE)` with `run`'s message; `validate` makes no model call. Each prints `cell_line` per `record.dry_run` entry, then `status <status>`; exit 0 when `runnable` or when `new` stopped after stage 1 as asked (D-exit), 1 otherwise. `continue` on a plan whose stage 4 is committed with `open_blocks > 0`, whatever its status, prints `failed: <n> open block(s); edit the bundle and run plan review` and exits 1 without a call (D-revise-error, R-validate-status). When `new` stops after stage 1 it prints `plan.md` and `stopped after stage 1: review plans/<slug>/plan.md, then run plan continue plans/<slug>`; a later `continue` overwrites any edit to a file of the stage in progress, and the stop message says so (spec section 8). `bundle_diff` is `difflib.unified_diff` over the hashed files of both bundles, path by path in sorted order; `world_diff` reports, per `base_worlds` entry, `worlds/<name>: the shipped world has not moved since the copy` or `worlds/<name>: the shipped world has moved since the copy (<old 12 hex> then, <new 12 hex> now)`, then the unified diff of each file of the copy against `<worlds_dir>/<name>`.

`claude_bully/cli.py`: `from claude_bully.planner.cli import plan_app` and `app.add_typer(plan_app, name="plan")`.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_plan_cli.py tests/test_plan_parity.py tests/test_cli.py -q -m "slow or not slow"`, then the gate.
Expected: PASS; all thirteen points and the two the review added byte-equal; `materialize` rebuilds the finished bundle; `tests/test_cli.py`'s 36 strategies unchanged with these files run first.

- [ ] **Step 5: Docs-sync and commit**

docs/00 section E lists `plan new | continue | review | validate | diff` with their flags (V24); docs/08 "CLI, records, decisions and open questions": the five commands and the exit codes (D-exit). Spec "As planned": D-exit, D-rounds (the three ordered writes), D-revise-error's `continue` line, R-validate-status. HANDOFF Progress: Task 9 with the thirteen points' result.

```bash
git add claude_bully/planner/director.py claude_bully/planner/cli.py claude_bully/cli.py tests/test_plan_cli.py \
  tests/test_plan_parity.py tests/fixtures/director_stub.py docs/00-RECONCILED.md docs/08-DIRECTOR.md \
  docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 9, stage 5, the plan sub-app with --wait-on-rate-limit, and resume parity at all thirteen kill points

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

