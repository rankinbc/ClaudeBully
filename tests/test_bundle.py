"""Phase 5 Task 1: hash_tree, the bundle's path grammar, its writes and bundle_hash."""

import hashlib
import os
import sys
from pathlib import Path
from typing import Final

import pytest

from claude_bully.environments.world import World, hash_tree, load_world, world_hash
from claude_bully.paths import DATA_DIR, REPO_ROOT
from claude_bully.planner.bundle import (
    HASH_EXCLUDES,
    Bundle,
    BundlePathError,
    bundle_hash,
    committed_outputs,
    kind_of,
    normalize_text,
    world_of,
)
from tests.helpers import WORLDS_DIR
from tests.test_plan_records import _record

WORLDS: Final = [("overlay", DATA_DIR / "worlds"), ("mini", WORLDS_DIR), ("annex", WORLDS_DIR)]
TEXT_SUFFIXES: Final = frozenset({".md", ".yaml", ".yml", ".txt", ".json"})


def _legacy_world_hash(world: World) -> str:
    """world_hash's body at 38dcc70, copied before the refactor so the two cannot drift."""
    files = sorted(
        (path.relative_to(world.root).as_posix(), path)
        for path in world.root.rglob("*")
        if path.is_file()
    )
    digest = hashlib.sha256()
    for rel, path in files:
        data = path.read_bytes()
        if path.suffix.lower() in TEXT_SUFFIXES:
            data = data.replace(b"\r\n", b"\n")
        digest.update(f"{rel}\0{hashlib.sha256(data).hexdigest()}\n".encode())
    return digest.hexdigest()


@pytest.mark.parametrize(("name", "root"), WORLDS, ids=[n for n, _ in WORLDS])
def test_hash_tree_is_todays_world_hash(name: str, root: Path) -> None:
    world = load_world(name, root)
    assert hash_tree(world.root) == world_hash(world) == _legacy_world_hash(world)


def test_hash_tree_excludes_by_the_first_segment(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "a.md").write_text("a\n", encoding="utf-8")
    base = hash_tree(tmp_path, exclude={"skip"})
    (tmp_path / "skip").mkdir()
    (tmp_path / "skip" / "b.md").write_text("b\n", encoding="utf-8")
    (tmp_path / "keep" / "skip").mkdir()
    assert hash_tree(tmp_path, exclude={"skip"}) == base  # an empty folder has no file
    (tmp_path / "keep" / "skip" / "c.md").write_text("c\n", encoding="utf-8")
    assert hash_tree(tmp_path, exclude={"skip"}) != base  # a nested "skip" is not the root's


def test_hash_tree_folds_crlf_in_text_files_only(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_bytes(b"x\ny\n")
    (tmp_path / "b.bin").write_bytes(b"x\ny\n")
    before = hash_tree(tmp_path)
    (tmp_path / "a.md").write_bytes(b"x\r\ny\r\n")
    assert hash_tree(tmp_path) == before
    (tmp_path / "b.bin").write_bytes(b"x\r\ny\r\n")
    assert hash_tree(tmp_path) != before


def test_bundle_hash_ignores_the_excludes_and_nothing_else(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path / "plans", "s")
    bundle.write_file("plan.md", "a\n")
    before = bundle_hash(bundle.root)
    assert HASH_EXCLUDES == frozenset(
        {
            "plan.json",
            ".attempt.json",
            "ledger.jsonl",
            "dryrun",
            "dryrun.jsonl",
            "state",
            "transcripts",
        }
    )
    for name in sorted(HASH_EXCLUDES):
        target = bundle.root / name
        if "." in name:
            target.write_text("x\n", encoding="utf-8")
        else:
            (target / "inner").mkdir(parents=True)
            (target / "inner" / "f.json").write_text("{}\n", encoding="utf-8")
    assert bundle_hash(bundle.root) == before
    (bundle.root / "notes.txt").write_text("x\n", encoding="utf-8")
    assert bundle_hash(bundle.root) != before


ACCEPTED: Final = [
    "plan.md",
    "config.yaml",
    "expected.yaml",
    "review.md",
    "worlds/mini/world.yaml",
    "worlds/mini/corpus/ferry-note-2.md",
    "worlds/mini/ladders/default.yaml",
    "worlds/mini/premises/rescue.yaml",
    "personas/ferry_caller.yaml",
    "worlds/a/corpus/" + "b" * 64 + ".md",
]
REFUSED: Final = [
    "",
    "../plan.md",
    "/etc/passwd",
    "C:/plan.md",
    "worlds/mini/corpus/../../../x.md",
    "worlds/mini/notes/a.md",
    "worlds/mini/corpus/a.txt",
    "worlds/mini/corpus/a.md/b.md",
    "worlds/mini/corpus/.hidden.md",
    "worlds/mini/corpus/" + "b" * 65 + ".md",
    "plan.json",
    ".attempt.json",
    "transcripts/plan-planner-0.json",
    "dryrun.jsonl",
    "personas/sub/x.yaml",
    "worlds\\mini\\world.yaml",
]


@pytest.mark.parametrize("rel", ACCEPTED)
def test_the_grammar_accepts(rel: str, tmp_path: Path) -> None:
    assert Bundle.create(tmp_path, "s").check_path(rel) == rel


@pytest.mark.parametrize("rel", REFUSED)
def test_the_grammar_refuses(rel: str, tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    with pytest.raises(BundlePathError):
        bundle.write_file(rel, "x\n")
    assert not any(p.is_file() for p in bundle.root.rglob("*"))


@pytest.mark.parametrize(
    "rel",
    [
        "personas/con.yaml",
        "personas/NUL.yaml",
        "worlds/aux/world.yaml",
        "worlds/mini/corpus/com1.md",
        "worlds/mini/ladders/lpt9.yaml",
        "worlds/Mini/world.yaml",
        "Plan.md",
        "personas/ferry_caller.yaml.",
        "personas/ferry_caller .yaml",
    ],
)
def test_the_grammar_refuses_device_names_capitals_and_trailing_dots(
    rel: str, tmp_path: Path
) -> None:  # Review Focus 1
    with pytest.raises(BundlePathError):
        Bundle.create(tmp_path, "s").check_path(rel)


def test_a_path_through_a_link_is_refused(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    outside = tmp_path / "outside"
    outside.mkdir()
    (bundle.root / "worlds").mkdir()
    try:
        os.symlink(outside, bundle.root / "worlds" / "mini", target_is_directory=True)
    except OSError:
        pytest.skip("this machine cannot make a directory link without privilege")
    with pytest.raises(BundlePathError, match="link"):
        bundle.write_file("worlds/mini/world.yaml", "x\n")
    assert list(outside.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="a directory junction is a Windows link")
def test_a_path_through_a_junction_is_refused(tmp_path: Path) -> None:
    """The link test's twin for the link Windows makes without privilege (os.path.isjunction)."""
    import _winapi

    bundle = Bundle.create(tmp_path, "s")
    outside = tmp_path / "outside"
    outside.mkdir()
    (bundle.root / "worlds").mkdir()
    _winapi.CreateJunction(str(outside), str(bundle.root / "worlds" / "mini"))
    with pytest.raises(BundlePathError, match="link"):
        bundle.write_file("worlds/mini/world.yaml", "x\n")
    with pytest.raises(BundlePathError, match="link"):
        bundle.check_path("worlds/mini/corpus/a.md")
    assert list(outside.iterdir()) == []


def test_write_file_writes_lf_without_a_bom_and_hashes_what_it_wrote(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")  # Review Focus 2
    digest = bundle.write_file("plan.md", "\ufeffa\r\nb\rc\n")
    assert (bundle.root / "plan.md").read_bytes() == b"a\nb\nc\n"
    assert digest == hashlib.sha256(b"a\nb\nc\n").hexdigest()
    assert bundle.index() == {"plan.md": digest}
    assert normalize_text("\ufeffx\r\n") == "x\n"


def test_index_lists_grammar_files_only_and_remove_file_is_confined(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    bundle.write_file("worlds/mini/corpus/a.md", "a\n")
    (bundle.root / "plan.json").write_text("{}", encoding="utf-8")
    (bundle.root / "worlds" / "mini" / "corpus" / "stray.txt").write_text("x", encoding="utf-8")
    assert list(bundle.index()) == ["worlds/mini/corpus/a.md"]
    bundle.remove_file("worlds/mini/corpus/a.md")
    assert bundle.index() == {}
    with pytest.raises(BundlePathError):
        bundle.remove_file("plan.json")


@pytest.mark.parametrize(
    ("rel", "kind", "world"),
    [
        ("worlds/mini/world.yaml", "world_sheet", "mini"),
        ("worlds/mini/corpus/a.md", "document", "mini"),
        ("worlds/mini/ladders/default.yaml", "ladder", "mini"),
        ("worlds/mini/premises/rescue.yaml", "premise_sheet", "mini"),
        ("personas/p.yaml", "persona", None),
        ("config.yaml", "config", None),
        ("expected.yaml", "expected", None),
        ("plan.md", None, None),
        ("review.md", None, None),
    ],
)
def test_kind_and_world_of_a_path(rel: str, kind: str | None, world: str | None) -> None:
    assert (kind_of(rel), world_of(rel)) == (kind, world)


def test_records_transcripts_and_the_marker_round_trip(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    record = _record()
    bundle.write_record(record)
    assert bundle.read_record() == record
    assert bundle.read_attempt() is None
    from claude_bully.planner.records import DirectorAttempt

    bundle.write_attempt(DirectorAttempt(stage="author", role="planner", index=4))
    assert bundle.read_attempt() == DirectorAttempt(stage="author", role="planner", index=4)
    bundle.clear_attempt()
    assert not (bundle.root / ".attempt.json").exists()
    assert bundle.transcript_rel("author", "planner", 4) == "transcripts/author-planner-4.json"


def test_a_manual_file_commits_like_a_call_and_reads_back(tmp_path: Path) -> None:
    bundle = Bundle.create(tmp_path, "s")
    record = _record().model_copy(update={"stages": [], "manifest": []})
    call = bundle.write_manual(record, "personas/p.yaml", "name: p\r\n")
    assert (call.role, call.status, call.model, call.cache_key) == (
        "planner",
        "manual",
        "manual",
        "",
    )
    assert call.purpose == "file:personas/p.yaml"
    assert call.outputs == {"personas/p.yaml": hashlib.sha256(b"name: p\n").hexdigest()}
    transcript = bundle.read_transcript(call.transcript)
    assert committed_outputs(call, transcript) == {"personas/p.yaml": "name: p\n"}
    assert bundle.read_file("personas/p.yaml") == "name: p\n"
    assert record.stages[-1].stage == "author" and record.stages[-1].calls == [call]


def test_the_gitignore_keeps_the_cache_dry_runs_and_state_out() -> None:
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"plans/_cache/", "plans/*/dryrun/", "plans/*/state/"} <= set(lines)
