"""The per-turn tool-call cap and the not-available line, shared by the runner's tool loop and
the MCP server.

A leaf module: it imports nothing from the package, so the MCP server (which ``claude -p`` runs as
its own process) and the runner can both use it without importing each other's machinery.
"""

from typing import Final

MAX_TOOL_CALLS_PER_TURN: Final = 8
TOOL_LIMIT_TEXT: Final = "Tool call limit reached for this turn."
# ToolCall.status of a call past the cap: recorded, never run
LIMIT_STATUS: Final = "limit"
# what a call to a tool the cell does not offer reads, on both backends (Phase 6 D-unavailable)
TOOL_UNAVAILABLE_TEXT: Final = "Tool {name!r} is not available."


def tool_unavailable_text(name: str) -> str:
    """The line a call to ``name`` reads when the cell does not offer it (disabled, unknown or
    not yet offered): the runtime's ``execute`` and the MCP server's ``_call_tool`` both write
    it."""
    return TOOL_UNAVAILABLE_TEXT.format(name=name)
