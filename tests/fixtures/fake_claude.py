"""Stand-in for the ``claude`` executable used by provider tests.

Records argv and stdin as one JSON line in $FAKE_CLAUDE_LOG and prints a result
object shaped like Claude Code's ``--output-format json`` output.

Given ``--mcp-config`` it also behaves like Claude Code's MCP client: it launches the server the
config names, runs ``initialize`` and ``tools/list``, then makes the calls in $FAKE_CLAUDE_TOOL_CALL
(a JSON object ``{"name": ..., "arguments": {...}}`` or a list of them) and puts each result's text
in its own "result". A call is only made if ``--allowedTools`` lists ``mcp__claude_bully__<name>``,
as the real client would refuse it otherwise.
"""

import json
import os
import subprocess
import sys
from typing import Any

SERVER = "claude_bully"


def _rpc(proc: subprocess.Popen[bytes], request_id: int, method: str, params: Any) -> Any:
    assert proc.stdin is not None and proc.stdout is not None
    message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    proc.stdin.write(json.dumps(message).encode("utf-8") + b"\n")
    proc.stdin.flush()
    reply = json.loads(proc.stdout.readline().decode("utf-8"))
    assert reply["id"] == request_id, reply
    if "error" in reply:
        raise RuntimeError(f"{method}: {reply['error']}")
    return reply["result"]


def run_mcp(argv: list[str]) -> dict[str, Any]:
    """Launch the configured MCP server and use it the way Claude Code would."""
    with open(argv[argv.index("--mcp-config") + 1], encoding="utf-8") as fh:
        spec = json.load(fh)["mcpServers"][SERVER]
    allowed = argv[argv.index("--allowedTools") + 1].split(",") if "--allowedTools" in argv else []
    raw = os.environ.get("FAKE_CLAUDE_TOOL_CALL")
    wanted = json.loads(raw) if raw else []
    calls = wanted if isinstance(wanted, list) else [wanted]

    proc = subprocess.Popen(
        [spec["command"], *spec["args"]],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
    )
    texts: list[str] = []
    try:
        _rpc(
            proc,
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "fake-claude", "version": "0"},
            },
        )
        assert proc.stdin is not None
        proc.stdin.write(b'{"jsonrpc": "2.0", "method": "notifications/initialized"}\n')
        proc.stdin.flush()
        listed = [t["name"] for t in _rpc(proc, 2, "tools/list", {})["tools"]]
        for number, call in enumerate(calls, start=3):
            if f"mcp__{SERVER}__{call['name']}" not in allowed:
                texts.append(f"permission denied: {call['name']}")
                continue
            result = _rpc(proc, number, "tools/call", call)
            texts.append(result["content"][0]["text"])
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait(timeout=30)
    return {"listed": listed, "texts": texts}


def main() -> int:
    argv = sys.argv[1:]
    stdin = sys.stdin.read()
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    mcp = run_mcp(argv) if mode == "ok" and "--mcp-config" in argv else None
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        entry: dict[str, Any] = {"argv": argv, "stdin": stdin}
        if mcp is not None:
            entry["mcp"] = mcp
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    if mode == "crash":
        sys.stderr.write("boom\n")
        return 2
    if mode == "ratelimit":
        print(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "error",
                    "is_error": True,
                    "result": "You've hit your usage limit. Try again at 3pm.",
                }
            )
        )
        return 0

    session = None
    for flag in ("--session-id", "--resume"):
        if flag in argv:
            session = argv[argv.index(flag) + 1]
    result = "reply to: " + stdin.strip()
    for text in mcp["texts"] if mcp else []:
        result += "\n[tool result] " + text
    out: dict[str, object] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result,
        "session_id": session,
        "total_cost_usd": 0.01,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    if "--json-schema" in argv:
        out["structured_output"] = {"echo": json.loads(argv[argv.index("--json-schema") + 1])}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
