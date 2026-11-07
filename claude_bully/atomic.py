"""Atomic file writes, shared by the runtime, the MCP server and the judge cache.

A stdlib-only leaf module: ``metrics/judge.py`` cannot import ``environments/runtime.py`` or
``environments/mcp_server.py`` without an import cycle, so the one copy of the Windows
``PermissionError`` retry loop lives here, where all three can import it. ``write_atomic``
writes a temp file in the target's own directory and renames it over the target; the temp file
is removed on any failure, never left beside the target."""

import os
import tempfile
import time
from pathlib import Path
from typing import Final

REPLACE_TRIES: Final = 20
REPLACE_WAIT_S: Final = 0.05


def replace(tmp: Path, path: Path) -> None:
    """``os.replace(tmp, path)``, waiting out a reader that briefly holds ``path`` open on Windows
    (``REPLACE_TRIES`` tries, ``REPLACE_WAIT_S`` apart); ``tmp`` is removed when the last try
    fails."""
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(REPLACE_WAIT_S)


def write_atomic(path: Path, text: str) -> None:
    """Write ``text`` (UTF-8, newlines as given) to ``path`` atomically: a temp file in
    ``path.parent`` (created when missing), then ``replace``. A failure of any kind before or
    during the rename removes the temp file and is re-raised."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        try:
            handle = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)  # never opened as a file: close the descriptor, or the unlink fails
            raise
        with handle:
            handle.write(text.encode("utf-8"))
        replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
