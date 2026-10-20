"""Stand-in for the ``claude`` executable used by provider tests.

Records argv and stdin as one JSON line in $FAKE_CLAUDE_LOG and prints a result
object shaped like Claude Code's ``--output-format json`` output.
"""

import json
import os
import sys


def main() -> int:
    argv = sys.argv[1:]
    stdin = sys.stdin.read()
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"argv": argv, "stdin": stdin}) + "\n")

    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
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
    out: dict[str, object] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "reply to: " + stdin.strip(),
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
