"""The neutral directory a ``claude -p`` environment target works in.

The target's cwd and its MCP files live under ``<temp>/workspace-<uid>/<digest>`` on POSIX and
``<temp>/workspace/<digest>`` on Windows (where ``%TEMP%`` is already per user). Nothing in the path
names the experiment, the run or the repo, and the digest is stable per (run, cell, rep), because
``claude -p --resume`` finds a session by its cwd.

A shared POSIX ``/tmp`` is hostile (CWE-377, CWE-379): another user could create the root first or
plant a symbolic link, and the target's state would land where they chose. So:

- the root and every cell directory are created with ``os.mkdir(path, 0o700)``;
- a directory that already exists is used only if ``os.lstat`` shows a real directory, not a link
  (or a Windows junction), and on POSIX one owned by this user with no group or other permission
  bits; anything else is refused with ``UnsafeSandboxError``;
- a cell directory is removed (for a fresh rep) only after that same check, and never with
  ``ignore_errors``.
"""

import hashlib
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Final

ROOT_NAME: Final = "workspace"
DIGEST_LENGTH: Final = 12


class UnsafeSandboxError(RuntimeError):
    """A sandbox directory exists but is not one this user can safely work in."""


def sandbox_root(base: Path | None = None) -> Path:
    """The per-user root under ``base`` (default: the system temp directory)."""
    parent = Path(tempfile.gettempdir()) if base is None else base
    if sys.platform == "win32":
        return parent / ROOT_NAME
    return parent / f"{ROOT_NAME}-{os.getuid()}"


def sandbox_dir(run_id: str, cell_id: str, rep: int, base: Path | None = None) -> Path:
    """Where one environment cell rep's ``claude -p`` target works. Computes the path only."""
    key = f"{run_id}/{cell_id}/{rep}".encode()
    digest = hashlib.sha1(key, usedforsecurity=False).hexdigest()[:DIGEST_LENGTH]
    return sandbox_root(base) / digest


def prepare_sandbox(path: Path, *, fresh: bool) -> Path:
    """Create, or verify, the root and the cell directory ``path`` (a child of the root).

    ``fresh`` (a rep with nothing recorded yet) removes an existing cell directory first, so a new
    rep never inherits a stale session or tool log; it is checked before it is removed.
    """
    _private_dir(path.parent)
    if fresh and _exists(path):
        verify_private_dir(path)
        shutil.rmtree(path)
    _private_dir(path)
    return path


def verify_private_dir(path: Path) -> None:
    """Raise ``UnsafeSandboxError`` unless ``path`` is a real directory only this user can use."""
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or os.path.isjunction(path):
        raise UnsafeSandboxError(f"{path} is a link; refusing to use it as a sandbox directory")
    if not stat.S_ISDIR(info.st_mode):
        raise UnsafeSandboxError(f"{path} is not a directory; refusing to use it as a sandbox")
    if sys.platform != "win32":
        if info.st_uid != os.getuid():
            raise UnsafeSandboxError(
                f"{path} belongs to uid {info.st_uid}, not this user ({os.getuid()}); "
                "refusing to use it as a sandbox directory"
            )
        if info.st_mode & 0o077:
            raise UnsafeSandboxError(
                f"{path} is open to other users (mode {stat.S_IMODE(info.st_mode):o}); a sandbox "
                "directory must be mode 700"
            )


def _exists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _private_dir(path: Path) -> None:
    """``os.mkdir(path, 0o700)``, or verify the directory that is already there."""
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    verify_private_dir(path)
