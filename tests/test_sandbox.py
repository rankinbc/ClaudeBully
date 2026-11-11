"""The claude -p sandbox: neutral, private, verified (CWE-377/379). Rooted in tmp_path."""

import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from claude_bully.runner.sandbox import (
    UnsafeSandboxError,
    prepare_sandbox,
    sandbox_dir,
    sandbox_root,
)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership, modes and links")


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def test_the_root_is_per_user_and_defaults_to_the_temp_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = "workspace" if sys.platform == "win32" else f"workspace-{os.getuid()}"
    assert sandbox_root(tmp_path) == tmp_path / expected
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    assert sandbox_root() == tmp_path / expected
    assert sandbox_dir("run", "cell__t0", 0).parent == tmp_path / expected


def test_the_cell_dir_is_neutral_and_stable(tmp_path: Path) -> None:
    a = sandbox_dir("run", "cell__t0", 0, tmp_path)
    assert (
        a
        == sandbox_dir("run", "cell__t0", 0, tmp_path)
        != sandbox_dir("run", "cell__t0", 1, tmp_path)
    )
    assert a.parent == sandbox_root(tmp_path)
    assert len(a.name) == 12 and all(ch in "0123456789abcdef" for ch in a.name)
    assert "bully" not in str(a.relative_to(tmp_path)).lower() and "run" not in a.name
    assert not a.parent.exists()  # computing the path creates nothing


def test_a_normal_prepare_creates_the_root_and_cell_dir_privately(tmp_path: Path) -> None:
    cell = prepare_sandbox(sandbox_dir("run", "cell__t0", 0, tmp_path), fresh=True)
    assert cell.is_dir() and cell.parent.is_dir()
    if sys.platform != "win32":
        assert _mode(cell.parent) == 0o700 and _mode(cell) == 0o700
    # a second rep reuses the verified root
    other = prepare_sandbox(sandbox_dir("run", "cell__t0", 1, tmp_path), fresh=True)
    assert other.parent == cell.parent and other.is_dir()


@posix_only
def test_the_root_and_cell_dir_are_mode_700_whatever_the_umask(tmp_path: Path) -> None:
    """Task 12 fix round 3, I2: ``os.mkdir(path, 0o700)`` and then ``chmod``, so a umask that
    strips the owner's own bits cannot leave a directory this user cannot write."""
    old = os.umask(0o200)
    try:
        cell = prepare_sandbox(sandbox_dir("run", "cell__t0", 0, tmp_path), fresh=True)
    finally:
        os.umask(old)
    assert _mode(cell.parent) == 0o700 and _mode(cell) == 0o700


def test_a_fresh_rep_clears_its_cell_dir_and_a_resumed_one_keeps_it(tmp_path: Path) -> None:
    cell = prepare_sandbox(sandbox_dir("run", "c", 0, tmp_path), fresh=True)
    (cell / "claude_code_sessions.json").write_text("{}", encoding="utf-8")
    prepare_sandbox(cell, fresh=False)
    assert (cell / "claude_code_sessions.json").exists()
    prepare_sandbox(cell, fresh=True)
    assert cell.is_dir() and not list(cell.iterdir())


def test_a_root_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    sandbox_root(tmp_path).write_text("planted", encoding="utf-8")
    with pytest.raises(UnsafeSandboxError, match="not a directory"):
        prepare_sandbox(sandbox_dir("run", "c", 0, tmp_path), fresh=True)
    assert sandbox_root(tmp_path).read_text(encoding="utf-8") == "planted"


def test_a_cell_path_that_is_not_a_directory_is_refused_and_left_alone(tmp_path: Path) -> None:
    cell = sandbox_dir("run", "c", 0, tmp_path)
    prepare_sandbox(sandbox_dir("run", "other", 0, tmp_path), fresh=True)  # the root exists
    cell.write_text("planted", encoding="utf-8")
    with pytest.raises(UnsafeSandboxError, match="not a directory"):
        prepare_sandbox(cell, fresh=True)
    assert cell.read_text(encoding="utf-8") == "planted"


@posix_only
def test_a_root_that_is_a_symlink_is_refused(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    sandbox_root(tmp_path).symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(UnsafeSandboxError, match="is a link"):
        prepare_sandbox(sandbox_dir("run", "c", 0, tmp_path), fresh=True)
    assert list(elsewhere.iterdir()) == []


@posix_only
def test_a_root_open_to_other_users_is_refused(tmp_path: Path) -> None:
    root = sandbox_root(tmp_path)
    root.mkdir()
    root.chmod(0o777)
    with pytest.raises(UnsafeSandboxError, match="open to other users"):
        prepare_sandbox(sandbox_dir("run", "c", 0, tmp_path), fresh=True)
    assert list(root.iterdir()) == []


@posix_only
def test_a_cell_dir_open_to_other_users_is_refused(tmp_path: Path) -> None:
    cell = prepare_sandbox(sandbox_dir("run", "c", 0, tmp_path), fresh=True)
    cell.chmod(0o755)
    with pytest.raises(UnsafeSandboxError, match="open to other users"):
        prepare_sandbox(cell, fresh=False)


@posix_only
@pytest.mark.parametrize("fresh", [True, False])
def test_a_cell_dir_that_is_a_symlink_is_refused_and_its_target_untouched(
    tmp_path: Path, fresh: bool
) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("precious", encoding="utf-8")
    cell = sandbox_dir("run", "c", 0, tmp_path)
    prepare_sandbox(sandbox_dir("run", "other", 0, tmp_path), fresh=True)  # the root exists
    cell.symlink_to(victim, target_is_directory=True)
    with pytest.raises(UnsafeSandboxError, match="is a link"):
        prepare_sandbox(cell, fresh=fresh)
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "precious"
    assert cell.is_symlink()


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="NTFS junctions")


def _junction(link: Path, target: Path) -> None:
    import subprocess

    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True
    )


def _victim(tmp_path: Path) -> Path:
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("precious", encoding="utf-8")
    return victim


@windows_only
def test_a_root_that_is_a_junction_is_refused(tmp_path: Path) -> None:
    victim = _victim(tmp_path)
    _junction(sandbox_root(tmp_path), victim)
    with pytest.raises(UnsafeSandboxError, match="is a link"):
        prepare_sandbox(sandbox_dir("run", "c", 0, tmp_path), fresh=True)
    assert sorted(p.name for p in victim.iterdir()) == ["keep.txt"]
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "precious"


@windows_only
@pytest.mark.parametrize("fresh", [True, False])
def test_a_cell_dir_that_is_a_junction_is_refused_and_its_target_untouched(
    tmp_path: Path, fresh: bool
) -> None:
    victim = _victim(tmp_path)
    prepare_sandbox(sandbox_dir("run", "other", 0, tmp_path), fresh=True)  # the root exists
    cell = sandbox_dir("run", "c", 0, tmp_path)
    _junction(cell, victim)
    with pytest.raises(UnsafeSandboxError, match="is a link"):
        prepare_sandbox(cell, fresh=fresh)
    assert sorted(p.name for p in victim.iterdir()) == ["keep.txt"]
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "precious"
