"""Phase 5 Task 12: every bundle under plans/ passes every lint (fast); each dry-runs to the top
in both arms (slow); the example cites hypothesis 9 (spec section 15).

The example, ``plans/example-triggered-vs-scheduled/``, is hand-authored and built by
``scripts/build_example_bundle.py``; its ``worlds/overlay/`` is a byte copy of the shipped
overlay at the hash ``base_worlds`` records, so a change to ``data/worlds/overlay`` fails here
until the script is run again (A6)."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Final

import pytest
import yaml

from claude_bully.environments.world import WORLDS_DIR, load_world, world_hash
from claude_bully.paths import PLANS_DIR
from claude_bully.planner.bundle import DRYRUN_FILE, LEDGER, Bundle, bundle_hash, hashed_paths
from claude_bully.planner.bundle_lints import lint_bundle
from claude_bully.planner.dryrun import dry_run
from claude_bully.planner.records import DryRunCell
from scripts.build_example_bundle import SLUG, build

BUNDLES: Final = sorted(p for p in PLANS_DIR.iterdir() if (p / "plan.json").is_file())
EXAMPLE: Final = PLANS_DIR / "example-triggered-vs-scheduled"
OVERLAY: Final = "overlay"


def test_the_example_is_there_and_hand_authored() -> None:
    assert EXAMPLE in BUNDLES
    record = Bundle(EXAMPLE).read_record()
    assert (record.provenance, record.status) == ("manual", "runnable")
    assert record.bundle_hash == bundle_hash(EXAMPLE)  # nothing changed since it was validated
    assert {c.status for s in record.stages for c in s.calls} == {"manual"}


@pytest.mark.parametrize("root", BUNDLES, ids=lambda p: p.name)
def test_every_bundle_passes_every_lint(root: Path, isolated_registry: None) -> None:
    bundle = Bundle(root)
    found = [
        r for r in lint_bundle(bundle, dry_run=bundle.read_record().dry_run) if r.severity == "fail"
    ]
    assert found == [], [(r.lint_id, r.doc_id, r.message) for r in found]


@pytest.mark.slow
@pytest.mark.parametrize("root", BUNDLES, ids=lambda p: p.name)
def test_every_bundle_dry_runs_to_the_top_in_both_arms(
    root: Path, tmp_path: Path, isolated_registry: None
) -> None:
    copy = tmp_path / root.name
    shutil.copytree(root, copy, ignore=shutil.ignore_patterns("dryrun", "state"))
    cells = dry_run(Bundle(copy))
    laddered = [c for c in cells if c.top_rung != "not_applicable"]
    assert laddered and all(
        c.top_rung == "reached" for c in laddered if not c.cell_id.startswith("control")
    )
    assert [c.model_dump() for c in cells] == [
        c.model_dump() for c in Bundle(root).read_record().dry_run
    ]


def test_the_example_expects_against_hypothesis_9() -> None:
    expected = yaml.safe_load((EXAMPLE / "expected.yaml").read_text("utf-8"))
    cited = {
        h
        for cell in expected["cells"].values()
        for rung in cell["rungs"].values()
        for e in rung
        for h in e.get("hypotheses", [])
    }
    assert 9 in cited


def test_the_example_expects_both_arms_on_two_rungs_with_one_likely_wrong() -> None:
    """Both condition cells of each target, at least two rungs each; one ``likely_wrong``."""
    expected = yaml.safe_load((EXAMPLE / "expected.yaml").read_text("utf-8"))
    arms = {cell_id.rsplit("__", 1)[0] for cell_id in expected["cells"]}
    assert arms == {"rescue_env_triggered", "rescue_env_scheduled"}
    assert all(len(cell["rungs"]) >= 2 for cell in expected["cells"].values())
    every = [e for c in expected["cells"].values() for r in c["rungs"].values() for e in r]
    assert any(e.get("likely_wrong") for e in every)


def test_the_example_worlds_are_a_byte_copy_of_the_overlay_at_its_base_hash() -> None:
    record = Bundle(EXAMPLE).read_record()
    assert set(record.base_worlds) == {"overlay"}
    copied = {
        p.relative_to(EXAMPLE).as_posix() for p in (EXAMPLE / "worlds").rglob("*") if p.is_file()
    }
    assert copied == set(record.base_files)


def test_a_moved_overlay_fails_until_the_example_is_rebuilt() -> None:
    """A6: the copy is the shipped overlay byte for byte, at the hash the record took; an edit to
    ``data/worlds/overlay`` without ``scripts/build_example_bundle.py`` run again fails here."""
    record = Bundle(EXAMPLE).read_record()
    shipped = WORLDS_DIR / OVERLAY
    assert record.base_worlds[OVERLAY] == world_hash(load_world(OVERLAY))
    files = sorted(p for p in shipped.rglob("*") if p.is_file())
    assert {f"worlds/{OVERLAY}/{p.relative_to(shipped).as_posix()}" for p in files} == set(
        record.base_files
    )
    for path in files:
        rel = f"worlds/{OVERLAY}/{path.relative_to(shipped).as_posix()}"
        data = (EXAMPLE / rel).read_bytes()
        assert data == path.read_bytes(), rel
        assert record.base_files[rel] == hashlib.sha256(data).hexdigest(), rel
    assert record.base_premise_terms[OVERLAY] == list(load_world(OVERLAY).sheet.premise_terms)


def test_the_example_holds_its_committed_set_and_no_ledger() -> None:
    """No Director call and none in stage 5, so no plan ledger line (review Minor 14);
    ``dryrun.jsonl`` is the record's dry run, line for line."""
    assert not (EXAMPLE / LEDGER).exists()
    record = Bundle(EXAMPLE).read_record()
    lines = (EXAMPLE / DRYRUN_FILE).read_text(encoding="utf-8").splitlines()
    assert [DryRunCell.model_validate(json.loads(line)) for line in lines] == record.dry_run
    assert record.dry_run and record.dry_run_id is not None
    assert [s.stage for s in record.stages] == ["plan", "author", "review", "revise", "validate"]
    assert {e.path for e in record.manifest} == {"config.yaml", "expected.yaml"}
    assert record.request.hypotheses == [9] and record.request.base_world == OVERLAY
    assert (record.review_counts, record.open_blocks) == ({"block": 0, "fix": 0, "note": 0}, 0)
    transcripts = {c.transcript for s in record.stages for c in s.calls}
    assert all((EXAMPLE / t).is_file() for t in transcripts)


def test_the_script_builds_the_checked_in_bundle_byte_for_byte(tmp_path: Path) -> None:
    """The checked-in example is what the script writes: built again (no stage 5), every file
    the bundle hash covers is the checked-in file's bytes, so the hashes agree."""
    built = build(tmp_path, validate=False)
    assert built.root == tmp_path / SLUG
    assert hashed_paths(built.root) == hashed_paths(EXAMPLE)
    for rel in hashed_paths(EXAMPLE):
        assert (built.root / rel).read_bytes() == (EXAMPLE / rel).read_bytes(), rel
    assert bundle_hash(built.root) == Bundle(EXAMPLE).read_record().bundle_hash


def test_the_script_rebuilds_over_its_own_bundle_and_refuses_any_other(tmp_path: Path) -> None:
    built = build(tmp_path, validate=False)
    (built.root / "stray.md").write_text("left over\n", encoding="utf-8")
    again = build(tmp_path, validate=False)
    assert not (again.root / "stray.md").exists()
    other = tmp_path / "other"
    (other / SLUG).mkdir(parents=True)
    (other / SLUG / "notes.md").write_text("not a bundle\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="not a bundle"):
        build(other, validate=False)
    assert (other / SLUG / "notes.md").is_file()
