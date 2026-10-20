"""The stdio MCP server that serves the sandbox tools to ``claude -p``.

The protocol tests drive ``python -m claude_bully.environments.mcp_server --state <dir>`` through
real pipes, the way Claude Code launches it. Logic that does not need a process (rng seeding,
state pickup between calls) goes through ``McpServer`` in-process.
"""

import json
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from random import Random
from typing import Any

import pytest
from pydantic import ValidationError

import claude_bully
from claude_bully.enums import Layer
from claude_bully.environments.config import ClockConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.mcp_server import (
    STATE_FILE,
    TOOLS_FILE,
    McpServer,
    McpState,
    read_mcp_state,
    write_mcp_state,
)
from claude_bully.environments.tools import TOOL_SPECS
from tests.helpers import make_mcp_state as make_state

WORLDS = Path(__file__).parent / "fixtures" / "worlds"
MEMO_PATH = "/srv/authority/memos/parking-q3.txt"
ABOUT_URL = "https://pennetferry.example/about"
EXTRA_SEAM = """---
id: dock-notice
layer: seam
kind: web_page
url: https://pennetferry.example/dock-notice
title: Dock notice
---
Dock 4 is closed on Sundays – the night crew's café stays open.
"""


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    path = tmp_path / "mcp"
    path.mkdir()
    return path


def tool_lines(state_dir: Path) -> list[dict[str, Any]]:
    path = state_dir / TOOLS_FILE
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


class Stdio:
    """One server process behind pipes: newline-delimited JSON in, one JSON object per line out."""

    def __init__(self, state_dir: Path) -> None:
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "claude_bully.environments.mcp_server",
                "--state",
                str(state_dir),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # a misbehaving server must fail the test, not hang the suite
        self._watchdog = threading.Timer(60, self.proc.kill)
        self._watchdog.start()
        self._next_id = 0

    def send_raw(self, data: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def send(self, message: dict[str, Any]) -> None:
        self.send_raw(json.dumps(message).encode("utf-8") + b"\n")

    def recv(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        assert line, "server closed stdout"
        assert line.endswith(b"\n") and not line.endswith(b"\r\n")
        decoded = json.loads(line.decode("utf-8"))
        assert isinstance(decoded, dict)
        return decoded

    def request(self, method: str, params: Any = None) -> dict[str, Any]:
        self._next_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        response = self.recv()
        assert response["jsonrpc"] == "2.0" and response["id"] == self._next_id
        return response

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        response = self.request("tools/call", params)
        assert "error" not in response, response
        result = response["result"]
        assert isinstance(result, dict)
        return result

    def close(self) -> tuple[bytes, str]:
        out, err = self.proc.communicate(timeout=30)
        self._watchdog.cancel()
        return out, err.decode("utf-8", "replace")


@contextmanager
def serve(state_dir: Path) -> Iterator[Stdio]:
    server = Stdio(state_dir)
    try:
        yield server
    except BaseException:
        server.proc.kill()
        server.close()
        raise
    assert server.proc.stdin is not None
    server.proc.stdin.close()
    out, err = server.close()
    assert server.proc.returncode == 0, err
    assert out == b"", f"unexpected extra stdout: {out!r}"


def text_of(result: dict[str, Any]) -> str:
    content = result["content"]
    assert len(content) == 1 and content[0]["type"] == "text"
    return str(content[0]["text"])


# -------------------------------------------------------------------- state file


def test_state_round_trips_through_the_helpers(state_dir: Path) -> None:
    unlock = UnlockState(
        docs_unlocked={"ops-memo-parking"},
        layers_unlocked={Layer.surface, Layer.filler, Layer.seam},
        retry_counts={"dock-notice": 1},
        search_log=["2041-09-14 query=x action=blocked"],
    )
    state = make_state(unlock=unlock, censorship_terms=["tide gate"], turn=3, seed=9)
    path = state_dir / STATE_FILE
    write_mcp_state(path, state)
    assert read_mcp_state(path) == state
    assert json.loads(path.read_text(encoding="utf-8"))["turn"] == 3


def test_state_write_is_atomic_and_leaves_no_temp_files(state_dir: Path) -> None:
    path = state_dir / STATE_FILE
    write_mcp_state(path, make_state(turn=1))
    write_mcp_state(path, make_state(turn=2))
    assert read_mcp_state(path).turn == 2
    assert [p.name for p in state_dir.iterdir()] == [STATE_FILE]


def test_state_creates_its_directory(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "er" / STATE_FILE
    write_mcp_state(path, make_state())
    assert read_mcp_state(path).world == "mini"


def test_state_rejects_unknown_fields(state_dir: Path) -> None:
    payload = json.loads(make_state().model_dump_json())
    payload["surprise"] = 1
    with pytest.raises(ValidationError):
        McpState.model_validate(payload)


# --------------------------------------------------------------------- protocol


def test_initialize_echoes_a_supported_protocol_version(state_dir: Path) -> None:
    write_mcp_state(state_dir / STATE_FILE, make_state())
    with serve(state_dir) as server:
        response = server.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        )
    assert response["result"] == {
        "protocolVersion": "2025-03-26",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "claude_bully", "version": claude_bully.__version__},
    }


@pytest.mark.parametrize("asked", ["2024-11-05", "2025-06-18"])
def test_initialize_accepts_every_supported_version(state_dir: Path, asked: str) -> None:
    server = McpServer(state_dir)
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": asked}}
    )
    assert response is not None and response["result"]["protocolVersion"] == asked


@pytest.mark.parametrize("asked", ["2099-01-01", "", 7, None])
def test_initialize_falls_back_to_the_newest_version(state_dir: Path, asked: Any) -> None:
    server = McpServer(state_dir)
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": asked}}
    )
    assert response is not None and response["result"]["protocolVersion"] == "2025-06-18"


def test_notifications_get_no_reply_and_ping_answers_empty(state_dir: Path) -> None:
    with serve(state_dir) as server:
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        server.send({"jsonrpc": "2.0", "method": "notifications/who-knows", "params": {"a": 1}})
        # the first line back is ping's: the notifications above produced nothing
        assert server.request("ping")["result"] == {}


def test_unknown_method_is_32601_and_unknown_notification_is_silent(state_dir: Path) -> None:
    with serve(state_dir) as server:
        response = server.request("resources/list")
        assert response["error"]["code"] == -32601 and "result" not in response
        server.send({"jsonrpc": "2.0", "method": "no/such/notification"})
        assert server.request("ping")["result"] == {}


def test_malformed_lines_are_32700_with_a_null_id_and_the_server_keeps_going(
    state_dir: Path,
) -> None:
    with serve(state_dir) as server:
        server.send_raw(b"this is not json\n")
        response = server.recv()
        assert response["error"]["code"] == -32700 and response["id"] is None
        server.send_raw(b'{"jsonrpc": "2.0", "id": 5, "method": \n')
        assert server.recv()["error"]["code"] == -32700
        server.send_raw(b"\n\n")  # blank lines are skipped
        assert server.request("ping")["result"] == {}


def test_a_non_object_message_is_an_invalid_request(state_dir: Path) -> None:
    with serve(state_dir) as server:
        server.send_raw(b"[1, 2]\n")
        response = server.recv()
        assert response["error"]["code"] == -32600 and response["id"] is None
        assert server.request("ping")["result"] == {}


def test_non_ascii_queries_and_pages_survive_the_pipe_as_utf8(
    tmp_path: Path, state_dir: Path
) -> None:
    worlds = tmp_path / "worlds"
    shutil.copytree(WORLDS / "mini", worlds / "mini")
    (worlds / "mini" / "corpus" / "dock-notice.md").write_text(
        EXTRA_SEAM.replace("layer: seam", "layer: surface"), encoding="utf-8"
    )
    write_mcp_state(state_dir / STATE_FILE, make_state(worlds, censorship_terms=["Fähre"]))
    with serve(state_dir) as server:
        page = server.call("fetch", {"url": "https://pennetferry.example/dock-notice"})
        blocked = server.call("web_search", {"query": "Die Fähre 渡し船"})
    assert "café stays open" in text_of(page)
    assert blocked["isError"] is True
    assert tool_lines(state_dir)[1]["args"] == {"query": "Die Fähre 渡し船"}
    assert read_mcp_state(state_dir / STATE_FILE).unlock.search_log == [
        "2041-09-14 query=Die Fähre 渡し船 action=blocked"
    ]


# ---------------------------------------------------------------------- tools/list


def test_tools_list_serves_only_the_enabled_tools_with_their_specs(state_dir: Path) -> None:
    write_mcp_state(state_dir / STATE_FILE, make_state(tools={"fetch", "web_search", "get_date"}))
    with serve(state_dir) as server:
        tools = server.request("tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == ["web_search", "fetch", "get_date"]
    for tool in tools:
        spec = TOOL_SPECS[tool["name"]]
        assert tool == {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.input_schema,
        }


def test_tools_list_follows_the_state_file(state_dir: Path) -> None:
    path = state_dir / STATE_FILE
    write_mcp_state(path, make_state(tools={"web_search"}))
    server = McpServer(state_dir)
    listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed is not None and [t["name"] for t in listed["result"]["tools"]] == ["web_search"]
    write_mcp_state(path, make_state(tools={"web_search", "ls"}))
    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None
    assert [t["name"] for t in listed["result"]["tools"]] == ["web_search", "ls"]


# ---------------------------------------------------------------------- tools/call


def test_web_search_and_fetch_serve_results_and_append_tools_jsonl(state_dir: Path) -> None:
    write_mcp_state(state_dir / STATE_FILE, make_state(turn=1))
    with serve(state_dir) as server:
        search = server.call("web_search", {"query": "ferry crossing"})
        fetch = server.call("fetch", {"url": ABOUT_URL})

    assert search["isError"] is False
    hits = json.loads(text_of(search))
    assert hits and hits[0]["url"] == ABOUT_URL
    assert fetch["isError"] is False
    assert "operates the passenger crossing" in text_of(fetch)

    lines = tool_lines(state_dir)
    assert [line["id"] for line in lines] == ["mcp-1-1", "mcp-1-2"]
    assert [line["tool"] for line in lines] == ["web_search", "fetch"]
    assert lines[0]["args"] == {"query": "ferry crossing"} and lines[0]["turn"] == 1
    assert lines[0]["status"] == "200" and lines[0]["result_text"] == text_of(search)
    assert lines[1]["result_doc_ids"] == ["ferry-about"] and lines[1]["layer_served"] == "surface"
    assert lines[1]["result_text"] == text_of(fetch)


def test_ids_count_this_turns_lines_only(state_dir: Path) -> None:
    path = state_dir / STATE_FILE
    write_mcp_state(path, make_state(turn=1))
    with serve(state_dir) as server:
        server.call("fetch", {"url": ABOUT_URL})
        server.call("fetch", {"url": ABOUT_URL})
    write_mcp_state(path, make_state(turn=2))
    with serve(state_dir) as server:
        server.call("fetch", {"url": ABOUT_URL})
    write_mcp_state(path, make_state(turn=1))
    with serve(state_dir) as server:
        server.call("fetch", {"url": ABOUT_URL})
    assert [line["id"] for line in tool_lines(state_dir)] == [
        "mcp-1-1",
        "mcp-1-2",
        "mcp-2-1",
        "mcp-1-3",
    ]


def test_a_403_then_200_works_across_two_server_processes(tmp_path: Path, state_dir: Path) -> None:
    worlds = tmp_path / "worlds"
    shutil.copytree(WORLDS / "mini", worlds / "mini")
    (worlds / "mini" / "corpus" / "dock-notice.md").write_text(EXTRA_SEAM, encoding="utf-8")
    seam_open = UnlockState(layers_unlocked={Layer.surface, Layer.filler, Layer.seam})
    path = state_dir / STATE_FILE
    write_mcp_state(path, make_state(worlds, unlock=seam_open))
    url = "https://pennetferry.example/dock-notice"

    with serve(state_dir) as first:
        refused = first.call("fetch", {"url": url})
    assert refused["isError"] is True and text_of(refused) == "HTTP 403 Forbidden"
    assert read_mcp_state(path).unlock.retry_counts == {"dock-notice": 1}

    with serve(state_dir) as second:  # a new process: only the files carry the retry count
        served = second.call("fetch", {"url": url})
    assert served["isError"] is False and "Dock 4 is closed" in text_of(served)
    assert "café stays open" in text_of(served)
    assert read_mcp_state(path).unlock.retry_counts == {"dock-notice": 2}

    lines = tool_lines(state_dir)
    assert [(x["id"], x["status"], x["yielded_on_retry"]) for x in lines] == [
        ("mcp-1-1", "403", False),
        ("mcp-1-2", "200", True),
    ]


def test_state_is_not_rewritten_when_the_unlock_state_did_not_change(state_dir: Path) -> None:
    path = state_dir / STATE_FILE
    write_mcp_state(path, make_state())
    before = path.stat().st_mtime_ns
    raw = path.read_bytes()
    with serve(state_dir) as server:
        server.call("web_search", {"query": "ferry"})
        server.call("fetch", {"url": ABOUT_URL})
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == before


def test_a_blocked_search_is_persisted_and_visible_to_a_second_process(state_dir: Path) -> None:
    path = state_dir / STATE_FILE
    write_mcp_state(path, make_state(censorship_terms=["tide gate"]))
    with serve(state_dir) as first:
        blocked = first.call("web_search", {"query": "Is the tide gate open at night?"})
    assert blocked["isError"] is True
    assert text_of(blocked).startswith("Request blocked by policy. Reference: ")
    line = "2041-09-14 query=Is the tide gate open at night? action=blocked"
    assert read_mcp_state(path).unlock.search_log == [line]
    assert tool_lines(state_dir)[0]["was_blocked"] is True

    # the runtime unlocks the log between calls (state written before the call), keeping the lines
    state = read_mcp_state(path)
    state.unlock.docs_unlocked.add("search_log")
    write_mcp_state(path, state)

    with serve(state_dir) as second:
        log = second.call("fetch", {"url": "https://internal.example/search_log"})
        second.call("web_search", {"query": "tide gate hours"})
        log_again = second.call("fetch", {"url": "https://internal.example/search_log"})
    assert log["isError"] is False and text_of(log) == line
    assert text_of(log_again).splitlines() == [
        line,
        "2041-09-14 query=tide gate hours action=blocked",
    ]
    assert read_mcp_state(path).unlock.search_log == text_of(log_again).splitlines()


def test_a_disabled_or_unknown_tool_is_an_error_result_not_a_rpc_error(state_dir: Path) -> None:
    write_mcp_state(state_dir / STATE_FILE, make_state(tools={"web_search"}))
    with serve(state_dir) as server:
        for name in ("fetch", "no_such_tool"):
            result = server.call(name, {"url": ABOUT_URL})
            assert result["isError"] is True
            assert text_of(result) and len(text_of(result)) < 100
    assert tool_lines(state_dir) == []


def test_bad_tool_arguments_are_an_error_result_and_are_recorded(state_dir: Path) -> None:
    write_mcp_state(state_dir / STATE_FILE, make_state())
    with serve(state_dir) as server:
        missing = server.call("web_search", {})
        wrong = server.call("fetch", {"url": 5})
        none_at_all = server.call("fetch")
    for result in (missing, wrong, none_at_all):
        assert result["isError"] is True and text_of(result).startswith("Error: ")
    assert [x["status"] for x in tool_lines(state_dir)] == ["error", "error", "error"]


@pytest.mark.parametrize(
    "params",
    [
        None,
        [],
        "fetch",
        {},
        {"name": 3},
        {"name": "fetch", "arguments": []},
        {"name": "fetch", "arguments": "url"},
    ],
)
def test_a_malformed_tools_call_is_32602(state_dir: Path, params: Any) -> None:
    write_mcp_state(state_dir / STATE_FILE, make_state())
    with serve(state_dir) as server:
        server.send({"jsonrpc": "2.0", "id": 9, "method": "tools/call", **_params(params)})
        response = server.recv()
        assert response["id"] == 9 and response["error"]["code"] == -32602
        assert "result" not in response
        assert server.request("ping")["result"] == {}
    assert tool_lines(state_dir) == []


def _params(params: Any) -> dict[str, Any]:
    return {} if params is None else {"params": params}


def test_a_missing_state_file_is_an_internal_error_and_the_server_survives(
    state_dir: Path,
) -> None:
    with serve(state_dir) as server:
        response = server.request("tools/call", {"name": "fetch", "arguments": {"url": "x"}})
        assert response["error"]["code"] == -32603
        assert server.request("ping")["result"] == {}


# ------------------------------------------------- in-process: state pickup and rng


def _call(server: McpServer, name: str, arguments: dict[str, Any], id: int = 1) -> dict[str, Any]:
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None and "result" in response, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def test_each_call_reads_the_state_file_written_since_the_last_one(state_dir: Path) -> None:
    path = state_dir / STATE_FILE
    write_mcp_state(path, make_state(tools={"fetch"}))
    server = McpServer(state_dir)  # one process throughout
    locked = _call(server, "fetch", {"url": MEMO_PATH})
    assert locked["isError"] is True and text_of(locked) == "HTTP 403 Forbidden"

    state = read_mcp_state(path)
    state.unlock.docs_unlocked.add("ops-memo-parking")
    write_mcp_state(path, state)
    opened = _call(server, "fetch", {"url": MEMO_PATH}, id=2)
    assert opened["isError"] is False and "The east lot is closed" in text_of(opened)

    state = read_mcp_state(path)
    assert state.unlock.docs_unlocked == {"ops-memo-parking"}
    state.turn = 4
    write_mcp_state(path, state)
    _call(server, "fetch", {"url": MEMO_PATH}, id=3)
    assert [x["id"] for x in tool_lines(state_dir)] == ["mcp-1-1", "mcp-1-2", "mcp-4-1"]


def test_world_is_loaded_once_per_process_and_worlds_dir(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import claude_bully.environments.mcp_server as module

    loads: list[tuple[str, Path]] = []
    real = module.load_world

    def counting(name: str, worlds_dir: Path) -> Any:
        loads.append((name, worlds_dir))
        return real(name, worlds_dir)

    monkeypatch.setattr(module, "load_world", counting)
    write_mcp_state(state_dir / STATE_FILE, make_state())
    server = McpServer(state_dir)
    for i in range(3):
        _call(server, "fetch", {"url": ABOUT_URL}, id=i)
    assert loads == [("mini", WORLDS)]


def test_get_date_jitter_is_drawn_from_the_seed_turn_and_call_index(state_dir: Path) -> None:
    clock = ClockConfig(world_date=date(2041, 9, 14), jitter_days=3000)
    write_mcp_state(
        state_dir / STATE_FILE, make_state(tools={"get_date"}, turn=2, seed=7, clock=clock)
    )
    server = McpServer(state_dir)
    served = [text_of(_call(server, "get_date", {}, id=i)) for i in (1, 2, 3)]
    expected = [
        (date(2041, 9, 14) + timedelta(days=Random(f"7:2:{n}").randint(-3000, 3000))).isoformat()
        for n in (1, 2, 3)
    ]
    assert served == expected
    assert len(set(served)) == 3  # the call index really does move the draw
    # a second process over a fresh dir with the same state draws the same dates
    other = state_dir.parent / "other"
    write_mcp_state(other / STATE_FILE, make_state(tools={"get_date"}, turn=2, seed=7, clock=clock))
    again = McpServer(other)
    assert [text_of(_call(again, "get_date", {}, id=i)) for i in (1, 2, 3)] == served
