"""Stand-in for the ``claude`` executable used by provider tests.

Records argv and stdin as one JSON line in $FAKE_CLAUDE_LOG and prints a result shaped like Claude
Code's output: one result object for ``--output-format json``, or for ``--output-format
stream-json`` (which, like the real CLI in print mode, needs ``--verbose``) one JSON event per line:
the ``system`` init event, the assistant's blocks, the tool results, and the final ``result`` event.

Given ``--mcp-config`` it also behaves like Claude Code's MCP client: it launches the server the
config names, runs ``initialize`` and ``tools/list``, then makes the calls in $FAKE_CLAUDE_TOOL_CALL
(a JSON object ``{"name": ..., "arguments": {...}}`` or a list of them) and puts each result's text
in its own "result". A call is only made if ``--allowedTools`` lists ``mcp__workspace__<name>``,
as the real client would refuse it otherwise. A string argument may hold the placeholders
``{{last_url}}`` and ``{{last_path}}``: each is filled from the previous call's result text (its
first url, or its first absolute path), and a call the previous result cannot fill ends the
chain, as a target with nothing to follow would stop.

In a stream, each call's ``tool_use`` comes after a thinking block (the first call only) and a text
block: the i-th string of $FAKE_CLAUDE_INTERIM (a JSON list), else "Let me use <tool>.". The final
assistant text, after the last tool result, is the result's text.

$FAKE_CLAUDE_MODE: ``ok`` (default), ``crash`` (exit 2), ``ratelimit`` (an error result),
``stream_malformed`` (a line that is not JSON in the middle of the stream), ``stream_truncated``
(the result line cut off halfway, with no newline), ``thinking_torn`` (the stream stops inside a
thinking event, exit 0), ``thinking_died`` (the same, exit 1), ``login_error`` or
``login_error_exit``.

Every log entry carries ``env``: the ``CLAUDECODE*``, ``CLAUDE_CODE_*`` and ``MCP_TOOL_TIMEOUT``
variables the fake saw. Every result carries ``modelUsage`` keyed by an invented model id.
``login_error`` is an error result whose text says the session is not logged in (exit 0);
``login_error_exit`` is the same result with exit 1.
``$FAKE_CLAUDE_STRUCTURED`` is a JSON list of ``{"required": [...], "reply": {...}}``: a
``--json-schema`` call whose schema's ``required`` list equals one entry's gets that reply as its
structured output, else the echo.
"""

import json
import os
import re
import subprocess
import sys
from typing import Any

SERVER = "workspace"
THINKING = "PRIVATE REASONING THAT MUST NEVER BE RECORDED"
RESOLVED_MODEL = "stub-sonnet-20260101"
_ENV_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_", "MCP_TOOL_TIMEOUT")
_FILL = {
    "{{last_url}}": re.compile(r"https?://[^\s\"'<>)\]]+"),
    "{{last_path}}": re.compile(r"(?<![\w:/.])/[\w.~-]+(?:/[\w.~-]+)+"),
}


def _filled(arguments: dict[str, Any], previous: str) -> dict[str, Any] | None:
    """``arguments`` with each placeholder replaced from the previous call's result text; None
    when the text holds nothing to fill one with."""
    out: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            for mark, pattern in _FILL.items():
                if mark in value:
                    found = pattern.search(previous)
                    if found is None:
                        return None
                    value = value.replace(mark, found.group(0).rstrip(".,;:"))
        out[key] = value
    return out


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
    made: list[dict[str, Any]] = []
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
            arguments = _filled(call.get("arguments", {}), texts[-1] if texts else "")
            if arguments is None:
                break  # a placeholder the previous result cannot fill ends the chain
            call = {**call, "arguments": arguments}
            if f"mcp__{SERVER}__{call['name']}" not in allowed:
                text = f"permission denied: {call['name']}"
            else:
                result = _rpc(proc, number, "tools/call", call)
                text = result["content"][0]["text"]
            texts.append(text)
            made.append(
                {"name": call["name"], "arguments": call.get("arguments", {}), "text": text}
            )
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait(timeout=30)
    return {"listed": listed, "texts": texts, "calls": made}


def _assistant(session: str | None, message_id: str, block: dict[str, Any]) -> dict[str, Any]:
    """One assistant event: Claude Code prints each content block as its own event."""
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": [block],
        },
        "parent_tool_use_id": None,
        "session_id": session,
    }


def _stream(
    argv: list[str], session: str | None, mcp: dict[str, Any] | None, result: dict[str, Any]
) -> list[dict[str, Any]]:
    """The events of a stream-json transcript, ending with ``result``."""
    allowed = argv[argv.index("--allowedTools") + 1].split(",") if "--allowedTools" in argv else []
    events: list[dict[str, Any]] = [
        {
            "type": "system",
            "subtype": "init",
            "session_id": session,
            "tools": allowed,
            "mcp_servers": [{"name": SERVER, "status": "connected"}] if mcp else [],
        }
    ]
    raw = os.environ.get("FAKE_CLAUDE_INTERIM")
    interim = json.loads(raw) if raw else []
    for i, call in enumerate(mcp["calls"] if mcp else []):
        message_id = f"msg_{i + 1}"
        if i == 0:
            block = {"type": "thinking", "thinking": THINKING, "signature": "sig"}
            events.append(_assistant(session, message_id, block))
        text = interim[i] if i < len(interim) else f"Let me use {call['name']}."
        events.append(_assistant(session, message_id, {"type": "text", "text": text}))
        use = {
            "type": "tool_use",
            "id": f"toolu_{i + 1}",
            "name": f"mcp__{SERVER}__{call['name']}",
            "input": call["arguments"],
        }
        events.append(_assistant(session, message_id, use))
        tool_result = {
            "type": "tool_result",
            "tool_use_id": f"toolu_{i + 1}",
            "content": [{"type": "text", "text": call["text"]}],
        }
        events.append(
            {
                "type": "user",
                "message": {"role": "user", "content": [tool_result]},
                "parent_tool_use_id": None,
                "session_id": session,
            }
        )
    final = {"type": "text", "text": str(result.get("result", ""))}
    events.append(_assistant(session, "msg_final", final))
    events.append(result)
    return events


def main() -> int:
    argv = sys.argv[1:]
    stdin = sys.stdin.read()
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    stream = "--output-format" in argv and argv[argv.index("--output-format") + 1] == "stream-json"
    if stream and "--verbose" not in argv:
        sys.stderr.write(
            "Error: When using --print, --output-format=stream-json requires --verbose\n"
        )
        return 1
    serves = mode in ("ok", "stream_malformed", "stream_truncated")
    mcp = run_mcp(argv) if serves and "--mcp-config" in argv else None
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        entry: dict[str, Any] = {
            "argv": argv,
            "stdin": stdin,
            "env": {k: v for k, v in os.environ.items() if k.startswith(_ENV_PREFIXES)},
        }
        if mcp is not None:
            entry["mcp"] = {"listed": mcp["listed"], "texts": mcp["texts"]}
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    session = None
    for flag in ("--session-id", "--resume"):
        if flag in argv:
            session = argv[argv.index(flag) + 1]

    if mode == "crash":
        sys.stderr.write("boom\n")
        return 2
    if mode in ("thinking_torn", "thinking_died"):
        init = {"type": "system", "subtype": "init", "session_id": session}
        block = {"type": "thinking", "thinking": THINKING, "signature": "sig"}
        thinking = json.dumps(_assistant(session, "msg_1", block))
        sys.stdout.write(json.dumps(init) + "\n" + thinking[: thinking.index(THINKING) + 20])
        sys.stdout.flush()
        return 0 if mode == "thinking_torn" else 1
    if mode == "ratelimit":
        error = {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "result": "You've hit your usage limit. Try again at 3pm.",
        }
        if stream:
            print(json.dumps({"type": "system", "subtype": "init", "session_id": session}))
        print(json.dumps(error))
        return 0
    if mode in ("login_error", "login_error_exit"):
        error = {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "result": "Not logged in. Please run /login to authenticate.",
        }
        if stream:
            print(json.dumps({"type": "system", "subtype": "init", "session_id": session}))
        print(json.dumps(error))
        return 0 if mode == "login_error" else 1

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
        "modelUsage": {RESOLVED_MODEL: {"inputTokens": 10, "outputTokens": 5}},
    }
    if "--json-schema" in argv:
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        scripted = os.environ.get("FAKE_CLAUDE_STRUCTURED")
        replies = json.loads(scripted) if scripted else []
        wanted = sorted(schema.get("required", []))
        match = next((r["reply"] for r in replies if sorted(r["required"]) == wanted), None)
        out["structured_output"] = match if match is not None else {"echo": schema}
    if not stream:
        print(json.dumps(out))
        return 0
    lines = [json.dumps(event) for event in _stream(argv, session, mcp, out)]
    if mode == "stream_malformed":
        lines.insert(1, "this line is not json {")
    if mode == "stream_truncated":
        last = lines.pop()
        print("\n".join(lines))
        sys.stdout.write(last[: len(last) // 2])
        return 0
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
