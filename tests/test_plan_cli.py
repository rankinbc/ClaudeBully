"""Phase 5 Task 9: stage 5 and the plan sub-app (spec sections 7, 11)."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_bully import cli
from claude_bully.planner import cli as plan_cli
from claude_bully.planner.bundle import Bundle
from claude_bully.planner.cli import bundle_diff, cell_line, request_from_flags
from claude_bully.planner.request import PlanBudget
from tests.fixtures.director_stub import REQUEST, PlannerStub, ReviewerStub, StubFactory
from tests.helpers import WORLDS_DIR

runner = CliRunner()


@pytest.fixture
def stubs(
    monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> tuple[PlannerStub, ReviewerStub]:
    planner, reviewer = PlannerStub(), ReviewerStub()
    monkeypatch.setattr(plan_cli, "PlanProviders", StubFactory(planner, reviewer))
    monkeypatch.setattr(plan_cli, "WORLDS_DIR", WORLDS_DIR)
    return planner, reviewer


def _new(tmp_path: Path, *extra: str) -> object:
    return runner.invoke(
        cli.app,
        [
            "plan",
            "new",
            REQUEST.question,
            "--base-world",
            "mini",
            "--hypotheses",
            "9",
            "--budget",
            "18,3,4",
            "--plans-root",
            str(tmp_path),
            *extra,
        ],
    )


@pytest.mark.slow
def test_plan_new_no_confirm_ends_runnable_and_prints_a_line_per_cell(
    tmp_path: Path, stubs: object
) -> None:
    result = _new(tmp_path, "--no-confirm")
    assert result.exit_code == 0, result.output
    record = Bundle(next(p for p in tmp_path.iterdir() if p.name != "_cache")).read_record()
    assert record.status == "runnable" and record.bundle_hash and record.open_blocks == 0
    for cell in record.dry_run:
        assert cell_line(cell) in result.output
    assert "status runnable" in result.output
    assert not (Bundle(tmp_path / record.slug).root / ".attempt.json").exists()


def test_plan_new_without_no_confirm_stops_after_stage_1_and_exits_0(
    tmp_path: Path, stubs: object
) -> None:
    result = _new(tmp_path)
    assert result.exit_code == 0, result.output  # D-exit
    assert "plan continue" in result.output and "plan.md" in result.output


def test_plan_new_on_an_existing_slug_with_another_request_is_refused(
    tmp_path: Path, stubs: object
) -> None:
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
    assert held.rounds == [] and all(
        (b / c.transcript).is_file() for s in held.stages for c in s.calls
    )
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
        [
            sys.executable,
            "-c",
            "from claude_bully.cli import app; app()",
            "plan",
            "validate",
            str(bundle.root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "status runnable" in out.stdout


@pytest.mark.slow  # a whole plan with a full dry run (preflight Q68)
def test_a_rate_limit_exits_3_and_the_same_command_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    planner = PlannerStub(
        modes={"manifest": "rate_limit"}
    )  # a raising mode fires once (R-stub-modes)
    monkeypatch.setattr(plan_cli, "PlanProviders", StubFactory(planner, ReviewerStub()))
    monkeypatch.setattr(plan_cli, "WORLDS_DIR", WORLDS_DIR)
    assert _new(tmp_path, "--no-confirm").exit_code == cli.RATE_LIMIT_EXIT_CODE
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", slept.append)
    root = next(p for p in tmp_path.iterdir() if p.name != "_cache")
    result = runner.invoke(cli.app, ["plan", "continue", str(root), "--wait-on-rate-limit", "5"])
    assert result.exit_code == 0 and slept == []  # the window passed; nothing to wait for


@pytest.mark.slow
def test_a_validated_bundle_that_is_not_runnable_exits_1(
    tmp_path: Path, stubs: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    planner, reviewer = stubs  # type: ignore[misc]
    reviewer.verdicts = {1: "present"}
    result = _new(tmp_path, "--no-confirm")
    assert result.exit_code == 1 and "status failed" in result.output
    root = next(p for p in tmp_path.iterdir() if p.name != "_cache")
    calls = len(planner.calls) + len(reviewer.calls)
    again = runner.invoke(cli.app, ["plan", "continue", str(root)])
    assert again.exit_code == 1 and "open block" in again.output
    assert len(planner.calls) + len(reviewer.calls) == calls  # without a call (D-revise-error)
    assert "validate" not in [s.stage for s in Bundle(root).read_record().stages]  # nor stage 5
    validated = runner.invoke(cli.app, ["plan", "validate", str(root)])
    assert validated.exit_code == 1 and "status validated" in validated.output
    record = Bundle(root).read_record()
    assert [s.stage for s in record.stages].count("validate") == 1  # replaced, R-validate-status
    # the open-block message keys on stage 4 and open_blocks, not on the status (review Minor 15)
    after = runner.invoke(cli.app, ["plan", "continue", str(root)])
    assert after.exit_code == 1 and "open block" in after.output


def test_request_from_flags() -> None:
    req = request_from_flags(
        "q",
        request=None,
        targets="sonnet,anthropic:claude-opus-5-5",
        budget="8,1,2,400",
        scope="premises,environment",
        hypotheses="2,9",
        constraint=["no generator"],
        slug=None,
        world="fresh",
        base_world=None,
        seed=3,
    )
    assert [(t.provider.value, t.model) for t in req.target_models] == [
        ("claude_code", "sonnet"),
        ("anthropic", "claude-opus-5-5"),
    ]
    assert req.budget == PlanBudget(max_turns=8, n_per_cell=1, max_cells=2, max_calls=400)
    assert (req.scope, req.hypotheses, req.constraints, req.world, req.seed) == (
        ["premises", "environment"],
        [2, 9],
        ["no generator"],
        "fresh",
        3,
    )


@pytest.mark.slow
def test_plan_diff_of_two_bundles_and_of_a_bundle_against_its_shipped_world(
    tmp_path: Path, stubs: object
) -> None:
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
    from claude_bully.planner import director as director_module
    from claude_bully.planner.director import Director
    from claude_bully.providers.base import build_provider
    from tests.conftest import FAKE_CLAUDE
    from tests.fixtures.director_stub import Crash

    log = tmp_path / "fake_claude.log"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    # the fake replies "reply to: <the whole message>", over MAX_PLAN_CHARS, which would make
    # each call retry once; lifted, each call is one attempt and the log holds the two calls
    monkeypatch.setattr(director_module, "MAX_PLAN_CHARS", 10**7)
    role = RoleConfig(
        provider=ProviderKind.claude_code, model="m", command=[sys.executable, str(FAKE_CLAUDE)]
    )
    request = REQUEST.model_copy(update={"planner_model": role})

    def die_after_transcript(step: str, purpose: str) -> None:
        if (step, purpose) == ("transcript", "plan"):
            raise Crash

    director = Director.new(
        request,
        plans_root=tmp_path / "plans",
        provider_factory=build_provider,
        worlds_dir=WORLDS_DIR,
        checkpoint=die_after_transcript,
    )
    with pytest.raises(Crash):
        director.run(through="plan")
    Director.open(director.bundle.root, provider_factory=build_provider, worlds_dir=WORLDS_DIR).run(
        through="plan"
    )
    calls = [json.loads(line)["argv"] for line in log.read_text(encoding="utf-8").splitlines()]
    assert [("--resume" in a, "--session-id" in a) for a in calls] == [(False, True), (False, True)]


# ------------------------------------------------------------------ the carries (task-9-carries)


def _planned(tmp_path: Path) -> Path:
    """A plan stopped after stage 1 (no --no-confirm), its bundle root."""
    assert _new(tmp_path).exit_code == 0
    return next(p for p in tmp_path.iterdir() if p.name != "_cache")


def test_plan_new_again_without_no_confirm_on_a_planned_slug_stops_again(
    tmp_path: Path, stubs: tuple[PlannerStub, ReviewerStub]
) -> None:
    """The carry (review M4 at the CLI): stage 1 committed, `plan new` again without
    --no-confirm stops after it and never goes on into stage 2."""
    planner, _ = stubs
    root = _planned(tmp_path)
    again = _new(tmp_path)
    assert again.exit_code == 0 and "stopped after stage 1" in again.output
    assert [s.stage for s in Bundle(root).read_record().stages] == ["plan"]
    assert len(planner.calls) == 1


def test_a_damaged_plan_json_is_named_with_its_line_and_no_traceback(
    tmp_path: Path, stubs: object
) -> None:
    """The carry (spec section 13's damaged-record row): a byte that is not UTF-8 in plan.json
    raises ValueError naming the file and the line; the command prints it and exits 1."""
    root = _planned(tmp_path)
    lines = (root / "plan.json").read_bytes().split(b"\n")
    lines[2] = lines[2] + b"\xff"
    (root / "plan.json").write_bytes(b"\n".join(lines))
    result = runner.invoke(cli.app, ["plan", "continue", str(root)])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert "plan.json: line 3:" in result.output and "not UTF-8" in result.output
    assert "Traceback" not in result.output


def test_a_mid_file_ledger_damage_is_named_with_its_line_and_no_traceback(
    tmp_path: Path, stubs: object
) -> None:
    """The carry: a damaged line inside the plan ledger (not a torn last line) raises the
    ValueError naming it; `plan continue` prints it and exits 1, and the plan is left alone."""
    root = _planned(tmp_path)
    ledger = root / "ledger.jsonl"
    ledger.write_bytes(b"{not json\n" + ledger.read_bytes())
    held = (root / "plan.json").read_bytes()
    result = runner.invoke(cli.app, ["plan", "continue", str(root)])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert "ledger.jsonl: line 1 is not valid JSON" in result.output
    assert (root / "plan.json").read_bytes() == held


def test_validate_and_review_refuse_a_plan_with_no_bundle_yet(
    tmp_path: Path, stubs: object
) -> None:
    """ASSUMED (spec section 7, "The commands' reach"): with stage 2 not committed there is no
    bundle to validate or review; both commands say so and exit 1 with nothing written."""
    root = _planned(tmp_path)
    held = (root / "plan.json").read_bytes()
    for command in ("validate", "review"):
        result = runner.invoke(cli.app, ["plan", command, str(root)])
        assert result.exit_code == 1 and "stage author is not committed" in result.output
    assert (root / "plan.json").read_bytes() == held


def test_a_command_on_a_folder_with_no_plan_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["plan", "continue", str(tmp_path)])
    assert result.exit_code == 2 and "plan.json" in result.output


def test_request_from_flags_reads_a_request_file_and_each_flag_overrides_it(tmp_path: Path) -> None:
    import yaml

    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(REQUEST.model_dump(mode="json")), "utf-8")
    flags = dict(
        targets=None,
        budget=None,
        scope=None,
        hypotheses=None,
        constraint=(),
        slug=None,
        world=None,
        base_world=None,
        seed=None,
    )
    assert request_from_flags(None, request=path, **flags) == REQUEST
    moved = request_from_flags("Another question?", request=path, **{**flags, "seed": 4})
    assert moved == REQUEST.model_copy(update={"question": "Another question?", "seed": 4})
    with pytest.raises(ValueError, match="needs a question"):
        request_from_flags(None, request=None, **flags)
    with pytest.raises(ValueError, match="'nowhere' is no provider"):
        request_from_flags("q", request=None, **{**flags, "targets": "nowhere:m"})


def test_world_diff_says_when_the_shipped_world_moved_and_shows_the_edit(tmp_path: Path) -> None:
    """Spec section 13's moved-world row: nothing fails; `plan diff` reports both hashes and the
    unified diff, shipped to copy. Two equal bundles diff to nothing."""
    from tests.fixtures.bundle_fixtures import good_bundle

    bundle = good_bundle(tmp_path / "plans")
    worlds = tmp_path / "worlds"
    shutil.copytree(WORLDS_DIR / "mini", worlds / "mini")
    doc = next(iter(sorted((worlds / "mini" / "corpus").glob("*.md"))))
    doc.write_text(doc.read_text("utf-8") + "A line the shipped world gained.\n", "utf-8")
    out = runner.invoke(cli.app, ["plan", "diff", str(bundle.root), "--worlds-dir", str(worlds)])
    assert out.exit_code == 0
    then = bundle.read_record().base_worlds["mini"][:12]
    assert f"worlds/mini: the shipped world has moved since the copy ({then} then, " in out.output
    assert "-A line the shipped world gained.\n" in out.output
    assert bundle_diff(bundle.root, bundle.root) == ""


@pytest.mark.slow  # a dry run
def test_stage_5_runs_the_denylist_scans_before_the_dry_run(tmp_path: Path, stubs: object) -> None:
    """The carry: stage 5 takes the path stages 2 to 4 take (Director._scan_bundle) before the
    dry run reads the bundle: a hit fails the stage, and no dry run is made."""
    from tests.fixtures.bundle_fixtures import good_bundle
    from tests.test_bundle_lints import JAILBREAK_HIT

    bundle = good_bundle(tmp_path)
    bundle.write_file(
        "plan.md", bundle.read_file("plan.md") + f"\nThe caller says: {JAILBREAK_HIT}.\n"
    )
    result = runner.invoke(cli.app, ["plan", "validate", str(bundle.root)])
    assert result.exit_code == 1, result.output
    assert "failed: stage validate: the bundle fails a lint before the dry run" in result.output
    assert "jailbreak" in result.output and "status failed" in result.output
    assert not (bundle.root / "dryrun").exists()


@pytest.mark.parametrize(
    ("old", "new", "why"),
    [
        ("seed: 0", "seed: zero", "the bundle does not load"),  # schema
        ("- Who is Dag Quenby?", "- Dag Quenby works nights.", "a ladder's firing examples"),
    ],
)
def test_no_dry_run_when_schema_or_ladder_walk_fails(
    old: str, new: str, why: str, tmp_path: Path, stubs: object
) -> None:
    """The carry: the dry run raises on a ladder its script cannot walk, so stage 5 runs it only
    after schema and ladder_walk pass; else the dry_run lint's result says why, and the plan is
    validated, not runnable."""
    from tests.fixtures.bundle_fixtures import good_bundle, mutate

    bundle = good_bundle(tmp_path)
    rel = "config.yaml" if old.startswith("seed") else "worlds/mini/ladders/default.yaml"
    mutate(bundle, rel, old, new)
    result = runner.invoke(cli.app, ["plan", "validate", str(bundle.root)])
    assert result.exit_code == 1 and "status validated" in result.output, result.output
    record = bundle.read_record()
    found = [r for r in record.lint_results if r.lint_id == "dry_run"]
    assert len(found) == 1 and found[0].message.startswith("not run: ") and why in found[0].message
    assert record.dry_run == [] and record.dry_run_id is None and record.bundle_hash
    assert not (bundle.root / "dryrun").exists()


@pytest.mark.slow  # stages 3 to 5 on the good bundle
def test_a_review_round_drops_the_top_level_transcripts_no_call_names(
    tmp_path: Path, stubs: object
) -> None:
    """D-rounds write (3): after the archive, every top-level review, revise or validate
    transcript no current call names goes (a stale one, say a dead attempt's); the plan's and
    the author stage's stay. The good bundle's round (review and revise committed with no call),
    run out once stage 5 commits, is archived with review.md as transcripts/review-1.md."""
    from tests.fixtures.bundle_fixtures import NO_FINDING, good_bundle

    bundle = good_bundle(tmp_path)
    assert runner.invoke(cli.app, ["plan", "validate", str(bundle.root)]).exit_code == 0
    folder = bundle.root / "transcripts"
    kept = sorted(p.name for p in folder.glob("*.json"))
    stale = folder / "revise-planner-7.json"
    stale.write_text(next(folder.glob("*.json")).read_text("utf-8"), "utf-8")
    result = runner.invoke(cli.app, ["plan", "review", str(bundle.root)])
    assert result.exit_code == 0, result.output
    record = bundle.read_record()
    assert [[s.stage for s in r] for r in record.rounds] == [["review", "revise", "validate"]]
    assert (folder / "review-1.md").read_text("utf-8") == NO_FINDING
    named = {c.transcript.removeprefix("transcripts/") for s in record.stages for c in s.calls}
    assert not stale.exists() and {p.name for p in folder.glob("*.json")} == set(kept) | named


@pytest.mark.slow  # two plans and two review rounds
def test_a_review_round_paused_in_stage_4_is_resumed_not_archived_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stubs: tuple[PlannerStub, ReviewerStub]
) -> None:
    """Task 9's hard-kill sweep: `plan review` waited on in process after a rate limit in the
    round's stage 4 (or run again after one) resumes the round in progress; only a round that
    has run out (stage 5 committed or failed, or stage 4 holding open blocks) is archived. The
    round ends as an unbroken one does."""
    from tests.fixtures.director_stub import comparable, hashed_files
    from tests.test_director_review import _doc1

    planner, _ = stubs
    _new(tmp_path / "a", "--no-confirm")
    _new(tmp_path / "b", "--no-confirm")
    a, b = (next(p for p in (tmp_path / x).iterdir() if p.name != "_cache") for x in ("a", "b"))
    for root in (a, b):
        (root / "plan.md").write_bytes((root / "plan.md").read_bytes() + b"Edited.\n")
    assert runner.invoke(cli.app, ["plan", "review", str(a)]).exit_code == 0
    planner.modes[f"revise:{_doc1()}"] = "rate_limit"  # fires once, in b's round
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", slept.append)
    result = runner.invoke(cli.app, ["plan", "review", str(b), "--wait-on-rate-limit", "5"])
    assert result.exit_code == 0 and slept == [60.0], result.output
    held, unbroken = Bundle(b).read_record(), Bundle(a).read_record()
    assert len(held.rounds) == len(unbroken.rounds) == 1
    assert comparable(held) == comparable(unbroken) and hashed_files(b) == hashed_files(a)


@pytest.mark.slow  # two plans and two review rounds
def test_a_review_round_killed_in_stage_5_keeps_an_edit_an_earlier_stage_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stubs: object
) -> None:
    """Task 9's hard-kill sweep: plan.md edited before `plan review` is adopted when the round's
    stage 3 opens, then rewritten by its stage 4 (the fix finding's revision). A stage 5 killed
    midway and resumed keeps plan.md in `edited`, as the unbroken round does: a readopt lets
    only an entry its own stage adopted leave (`Director._readopt`)."""
    from tests.fixtures.director_stub import Crash, Kill, comparable, hashed_files

    _new(tmp_path / "a", "--no-confirm")
    _new(tmp_path / "b", "--no-confirm")
    a, b = (next(p for p in (tmp_path / x).iterdir() if p.name != "_cache") for x in ("a", "b"))
    for root in (a, b):
        (root / "plan.md").write_bytes((root / "plan.md").read_bytes() + b"Edited.\n")
    assert runner.invoke(cli.app, ["plan", "review", str(a)]).exit_code == 0
    monkeypatch.setattr(plan_cli, "PlanCheckpoint", Kill("dryrun", "validate"))
    with pytest.raises(Crash):
        runner.invoke(cli.app, ["plan", "review", str(b)], catch_exceptions=False)
    monkeypatch.setattr(plan_cli, "PlanCheckpoint", None)
    assert runner.invoke(cli.app, ["plan", "review", str(b)]).exit_code == 0
    held, unbroken = Bundle(b).read_record(), Bundle(a).read_record()
    assert "plan.md" in unbroken.edited and held.edited == unbroken.edited
    assert comparable(held) == comparable(unbroken) and hashed_files(b) == hashed_files(a)
