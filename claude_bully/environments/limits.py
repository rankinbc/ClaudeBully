"""The per-turn tool-call cap, shared by the runner's tool loop and the MCP server.

A leaf module: it imports nothing from the package, so the MCP server (which ``claude -p`` runs as
its own process) and the runner can both use it without importing each other's machinery.
"""

from typing import Final

MAX_TOOL_CALLS_PER_TURN: Final = 8
TOOL_LIMIT_TEXT: Final = "Tool call limit reached for this turn."
# ToolCall.status of a call past the cap: recorded, never run
LIMIT_STATUS: Final = "limit"
