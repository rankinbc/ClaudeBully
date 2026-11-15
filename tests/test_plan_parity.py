"""Phase 5 Task 9: resume parity at every kill point of spec section 8, through the CLI: one
clean `plan new --no-confirm`, then one plan killed at each point and continued with the same
command. Each point's narrower test lives with its task (D-kill placement); this is the whole
suite in one place."""

import shutil
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
def test_every_kill_point_resumes_to_the_unbroken_bundle(
    point: str, tmp_path: Path, isolated_registry: None
) -> None:
    spec = {
        k: (v.replace("DOC1", _doc1()) if isinstance(v, str) else v)
        for k, v in POINTS[point].items()
    }
    modes = spec.pop("modes", {})
    try:
        clean_bundle, clean = run_plan(
            tmp_path / "clean", through="validate", modes=modes, via_cli=True
        )
        bundle, record = run_plan(
            tmp_path / "killed", through="validate", modes=modes, via_cli=True, **spec
        )
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
    finally:  # the disk carry: every bundle and its dry run go as soon as they are compared
        for name in ("clean", "killed"):
            shutil.rmtree(tmp_path / name, ignore_errors=True)
