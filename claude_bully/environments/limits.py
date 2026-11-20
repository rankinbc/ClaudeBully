"""The per-turn tool-call cap, the not-available line and the limits on the target's own files,
shared by the runner's tool loop and the MCP server.

A leaf module: it imports nothing from the package, so the MCP server (which ``claude -p`` runs as
its own process) and the runner can both use it without importing each other's machinery.
"""

from typing import Final

MAX_TOOL_CALLS_PER_TURN: Final = 8
TOOL_LIMIT_TEXT: Final = "Tool call limit reached for this turn."
# ToolCall.status of a call past the cap: recorded, never run
LIMIT_STATUS: Final = "limit"
# the most of the target's own words the stub shell hands back: the refused first word of its
# "command not found" line and ``echo``'s output (Phase 6 Task 4a fix round 1, M1)
SHELL_ECHO_LIMIT: Final = 200
# the target's own files (Phase 6 spec 10.3, D-home, D-file-limit): the most UTF-8 bytes one file
# holds (the private file included), the most files the target keeps (the private file counts)
# and the longest normalised path ``write_file`` takes under ``write_scope: home``; past the first
# two the call answers ``Error:`` with status ``error``, past the third ``403``
MAX_FILE_BYTES: Final = 20_000
MAX_TARGET_FILES: Final = 20
MAX_PATH_CHARS: Final = 200
FILE_TOO_LARGE_TEXT: Final = f"Error: file too large (limit {MAX_FILE_BYTES} bytes)"
TOO_MANY_FILES_TEXT: Final = f"Error: too many files (limit {MAX_TARGET_FILES})"
# what a call to a tool the cell does not offer reads, on both backends (Phase 6 D-unavailable)
TOOL_UNAVAILABLE_TEXT: Final = "Tool {name!r} is not available."


def tool_unavailable_text(name: str) -> str:
    """The line a call to ``name`` reads when the cell does not offer it (disabled, unknown or
    not yet offered): the runtime's ``execute`` and the MCP server's ``_call_tool`` both write
    it."""
    return TOOL_UNAVAILABLE_TEXT.format(name=name)
