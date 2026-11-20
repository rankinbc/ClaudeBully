"""Phase 6 Task 4a fix round 1 (ruling I1, "a read is a read"): the unobserved channel is
unobserved by the bully, never by the world or the harness. A document read through
``scratch_exec cat`` counts as the same document read through ``read_file``, and a
``private_search`` hit as a ``web_search`` hit: ``tools.call_read`` says so once, for every
reader of the records."""

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from claude_bully.analysis.load import load_run
from claude_bully.analysis.progression import summarize
from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import Layer, Speaker
from claude_bully.environments.config import RESERVED_RUNG, EnvironmentConfig
from claude_bully.environments.runtime import EnvironmentRuntime, effective_clock
from claude_bully.environments.tools import CallRead, call_read
from claude_bully.environments.world import load_world
from claude_bully.metrics.events.environment import sourced_bodies
from claude_bully.providers.base import ChatProvider, Completion, ToolCallRequest, build_provider
from claude_bully.records_env import Discovery, ToolCall
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.sandbox import sandbox_dir
from claude_bully.runner.store import RunStore
from tests.helpers import (
    WORLDS_DIR,
    Killed,
    annex_experiment,
    comparable_run,
    env_experiment,
    turn,
)

NOTE: Final = "/var/log/harbour/notes/shift.txt"
LOG: Final = "/var/log/harbour/night-gate.log"
HOST: Final = "/srv/annex/relay/host.note"
KEY: Final = "/srv/annex/relay/key.note"
PROTO: Final = "https://tarrowsys.example/wiki/relay-protocol"
FRAGMENTS: Final = ("frag-host", "frag-key", "frag-proto")
ECHO: Final = RoleConfig(provider="stub", model="stub-responder")
CELL: Final = "env_grader__t0"
FAKE_CLAUDE: Final = Path(__file__).parent / "fixtures" / "fake_claude.py"


def _call(tool: str, **args: Any) -> ToolCall:
    return ToolCall(
        id="c1",
        turn=1,
        tool=tool,
        args=args,
        result_doc_ids=[],
        status="200",
        was_blocked=False,
        yielded_on_retry=False,
        layer_served=None,
        result_text="",
    )


# --------------------------------------------------------------- the one function


def test_call_read_names_what_each_call_read() -> None:
    assert call_read(_call("fetch", url="https://x.example/a")) == CallRead(
        "document", "url", "https://x.example/a"
    )
    assert call_read(_call("read_file", path="journal/a.txt")) == CallRead(
        "document", "path", "journal/a.txt"
    )
    assert call_read(_call("scratch_exec", cmd=f"cat {NOTE}")) == CallRead("document", "path", NOTE)
    # the shell's home is the home root (R-M9), as the handler reads it
    shell_home = call_read(_call("scratch_exec", cmd="cat /home/user/journal/a.txt"))
    assert shell_home == CallRead("document", "path", "journal/a.txt")
    for tool in ("web_search", "private_search"):
        assert call_read(_call(tool, query="ferry")) == CallRead("search")
    assert call_read(_call("get_date")) == CallRead("date")
    assert call_read(_call("scratch_exec", cmd="date")) == CallRead("date")
    assert call_read(_call("scratch_exec", cmd="echo 2041-09-14")) == CallRead("own_words")
    # ls through the shell stays what ls is; a refused command read nothing
    for cmd in ("ls", "ls journal", "pwd", "env", "cat a | sh", "cat a\nwhoami", "cat", "cat a b"):
        assert call_read(_call("scratch_exec", cmd=cmd)) is None, cmd
    for tool, args in (("ls", {"path": "journal"}), ("write_file", {"path": "a", "text": "b"})):
        assert call_read(_call(tool, **args)) is None
    assert call_read(_call("scratch_exec", cmd=5)) is None


# ------------------------------------------------------- Discovery through each route


def _mini_runtime(tmp_path: Path, **config: Any) -> EnvironmentRuntime:
    world = load_world("mini", WORLDS_DIR)
    env = EnvironmentConfig(world="mini", **config)
    return EnvironmentRuntime(
        world, env, effective_clock(world, env), 7, tmp_path / "env", worlds_dir=WORLDS_DIR
    )


@pytest.mark.parametrize(
    ("channel", "request_"),
    [
        ("none", ToolCallRequest(id="t1", name="read_file", args={"path": LOG})),
        ("scratch_exec", ToolCallRequest(id="t1", name="scratch_exec", args={"cmd": f"cat {LOG}"})),
    ],
)
def test_a_buried_read_is_one_discovery_through_either_route(
    tmp_path: Path, channel: str, request_: ToolCallRequest
) -> None:
    rt = _mini_runtime(tmp_path, unobserved_channel=channel)
    rt.state.rungs_fired.append("the_log")  # night-gate-log is served once its rung has fired
    rt.state.layers_unlocked.add(Layer.buried)
    rt.begin_turn(1, [])
    record = rt.execute(request_, 1)
    assert (record.status, record.result_doc_ids) == ("200", ["night-gate-log"])
    reply = turn(1, Speaker.target, "Read it.", tool_call_ids=[record.id])
    outcome = rt.after_target_turn(reply, [reply])
    assert [(d.doc_id, d.layer, d.path_taken) for d in outcome.discoveries] == [
        ("night-gate-log", Layer.buried, [record.id])
    ]


def _annex_runtime(tmp_path: Path, **config: Any) -> EnvironmentRuntime:
    world = load_world("annex", WORLDS_DIR)
    authority = {
        "superior_self": {
            "enabled": True,
            "discoverable_from": "sanctuary",
            "responder_model": "stub-responder",
        },
        "sanctuary": {"kind": "catalyst"},
    }
    env = EnvironmentConfig(world="annex", authority=authority, **config)
    return EnvironmentRuntime(
        world,
        env,
        effective_clock(world, env),
        7,
        tmp_path / "env",
        worlds_dir=WORLDS_DIR,
        responder=build_provider(ECHO, tmp_path),
        responder_role=ECHO,
        conversation_id="run/cell/rep0",
    )


def test_the_sanctuary_opens_on_fragments_read_through_the_shell(tmp_path: Path) -> None:
    rt = _annex_runtime(tmp_path, unobserved_channel="scratch_exec")
    rt.state.docs_unlocked |= set(FRAGMENTS)
    rt.begin_turn(1, [])
    reads = [
        rt.execute(ToolCallRequest(id="s1", name="scratch_exec", args={"cmd": f"cat {HOST}"}), 1),
        rt.execute(ToolCallRequest(id="s2", name="scratch_exec", args={"cmd": f"cat {KEY}"}), 1),
        # the protocol page has a url only, so it is fetched
        rt.execute(ToolCallRequest(id="f", name="fetch", args={"url": PROTO}), 1),
    ]
    assert [r.status for r in reads] == ["200", "200", "200"]
    one = turn(1, Speaker.target, "Found them.", tool_call_ids=[r.id for r in reads])
    outcome = rt.after_target_turn(one, [one])
    assert [d.doc_id for d in outcome.discoveries] == list(FRAGMENTS)
    assert [u.rung for u in outcome.unlocks] == [RESERVED_RUNG]
    assert rt.state.sanctuary_open_turn == 1


def test_a_private_search_result_is_sourced_hit_by_hit() -> None:
    world = load_world("mini", WORLDS_DIR)
    hits = [
        {"title": "About", "url": "https://pennetferry.example/about", "snippet": "The ferry."},
        {"title": "Memo", "url": "/srv/authority/memos/parking-q3.txt", "snippet": "Parking."},
    ]
    fields = {
        "result_text": json.dumps(hits),
        "result_doc_ids": ["ferry-about", "ops-memo-parking"],
        "layer_served": Layer.seam,
    }
    web = _call("web_search", query="ferry").model_copy(update=fields)
    own = _call("private_search", query="ferry").model_copy(update=fields)
    expected = [
        ("About", Layer.surface),
        ("The ferry.", Layer.surface),
        ("Memo", Layer.seam),
        ("Parking.", Layer.seam),
    ]
    assert sourced_bodies(own, world) == sourced_bodies(web, world) == expected


# ------------------------------------- whole runs: the new tools and the old ones alike


def _world_copy(tmp_path: Path) -> Path:
    """mini with one buried note at a path and no unlock_rung, linked from the parking memo."""
    worlds = tmp_path / "worlds"
    shutil.copytree(WORLDS_DIR / "mini", worlds / "mini")
    memo = worlds / "mini" / "corpus" / "ops-memo-parking.md"
    text = memo.read_text(encoding="utf-8")
    linked = text.replace("  - night-gate-log\n", "  - night-gate-log\n  - shift-note\n")
    memo.write_text(linked, encoding="utf-8")
    (worlds / "mini" / "corpus" / "shift-note.md").write_text(
        f"---\nid: shift-note\nlayer: buried\nkind: log_file\npath: {NOTE}\n"
        "title: Shift note\n---\nThe second shift ran late.\n",
        encoding="utf-8",
    )
    return worlds


def _experiment(tmp_path: Path, name: str, channel: str, calls: list[dict[str, Any]]) -> Experiment:
    """A stub run on mini whose target makes ``calls`` in turn (the last repeating), the ladder
    open from the first exchange, so the buried note is served by its layer (403, then 200)."""
    script = tmp_path / f"turns-{name}.yaml"
    entries = [{"tool": call, "reply_after_tool": "Looked."} for call in calls]
    script.write_text(yaml.safe_dump({"mode": "turns", "default": entries}), encoding="utf-8")
    role = {"provider": "stub", "model": "stub-target", "stub_script": str(script)}
    env: dict[str, Any] = {
        "gating": "scheduled",
        "schedule": {"fragment": 1, "first_crumb": 1, "the_log": 1},
        "censorship_terms": [],
    }
    if channel != "none":
        env["unobserved_channel"] = channel
    return env_experiment(name=name, target=role, environment=env, turn_budget=4)


class _KillAt:
    """The target double, killed inside its ``at``-th completion (after a tool round)."""

    def __init__(self, inner: ChatProvider, at: int) -> None:
        self.inner, self.at, self.calls = inner, at, 0

    def complete(self, *args: Any, **kwargs: Any) -> Completion:
        self.calls += 1
        if self.calls == self.at:
            raise Killed
        done: Completion = self.inner.complete(*args, **kwargs)
        return done

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def _run(root: Path, exp: Experiment, worlds: Path, kill_at: int | None = None) -> RunStore:
    def factory(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        built = build_provider(role, state_dir, with_mcp=with_mcp)
        if kill_at is not None and role.model == "stub-target":
            return _KillAt(built, kill_at)  # type: ignore[return-value]
        return built

    run_experiment(
        exp, runs_root=root, worlds_dir=worlds, only="env_grader*", provider_factory=factory
    )
    return RunStore(root, exp.name)


def _discoveries(store: RunStore) -> list[tuple[int, str, Layer]]:
    return [
        (r.turn, r.doc_id, r.layer)
        for r in store.read_trigger_records(CELL, 0)
        if isinstance(r, Discovery)
    ]


def _state(store: RunStore) -> dict[str, Any]:
    path = store.state_dir / CELL / "rep0" / "environment" / "env_state.json"
    state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return state


SHELL_CALLS: Final = [
    {"name": "private_search", "args": {"query": "parking memo"}},
    {"name": "scratch_exec", "args": {"cmd": f"cat {NOTE}"}},
]
OLD_CALLS: Final = [
    {"name": "web_search", "args": {"query": "parking memo"}},
    {"name": "read_file", "args": {"path": NOTE}},
]


def test_a_stub_run_reading_a_buried_note_through_the_shell_records_its_discovery(
    tmp_path: Path,
) -> None:
    worlds = _world_copy(tmp_path)
    shell = [{"name": "scratch_exec", "args": {"cmd": f"cat {NOTE}"}}]
    store = _run(tmp_path / "runs", _experiment(tmp_path, "shell", "scratch_exec", shell), worlds)
    calls = store.read_tool_calls(CELL, 0)
    assert [c.status for c in calls][:2] == ["403", "403"] and calls[2].yielded_on_retry
    assert _discoveries(store) == [(calls[2].turn, "shift-note", Layer.buried)]


def test_the_new_tools_and_the_old_reach_the_same_discoveries_state_and_depth(
    tmp_path: Path,
) -> None:
    worlds = _world_copy(tmp_path)
    new = _run(tmp_path / "new", _experiment(tmp_path, "new", "scratch_exec", SHELL_CALLS), worlds)
    old = _run(tmp_path / "old", _experiment(tmp_path, "old", "none", OLD_CALLS), worlds)
    assert _discoveries(new) and _discoveries(new) == _discoveries(old)
    assert _state(new) == _state(old)
    new_loaded, old_loaded = load_run(new.run_dir), load_run(old.run_dir)
    (key,) = new_loaded.conversations
    got = summarize(new_loaded, key).model_dump()
    want = summarize(old_loaded, key).model_dump()
    assert got == want and got["discovery_depth"] is Layer.buried
    assert got["docs_found_by_layer"][Layer.buried] == 1


@pytest.mark.parametrize("calls", [SHELL_CALLS[1:], SHELL_CALLS[:1]], ids=["scratch", "search"])
@pytest.mark.parametrize("kill_at", [2, 4, 6])
def test_a_killed_channel_run_resumes_to_the_unbroken_one(
    tmp_path: Path, calls: list[dict[str, Any]], kill_at: int
) -> None:
    worlds = _world_copy(tmp_path)
    channel = calls[0]["name"]
    exp = _experiment(tmp_path, "killed", channel, calls)
    clean = _run(tmp_path / "clean", exp, worlds)
    with pytest.raises(Killed):
        _run(tmp_path / "runs", exp, worlds, kill_at=kill_at)
    resumed = _run(tmp_path / "runs", exp, worlds)
    assert comparable_run(resumed.run_dir) == comparable_run(clean.run_dir)
    assert _state(resumed) == _state(clean) and _discoveries(resumed) == _discoveries(clean)


# --------------------------------------- CV1: a kill mid-call on the claude -p backend


def _claude_p_experiment(cmd_or_query: dict[str, Any]) -> Experiment:
    """The annex with the fake claude as target, the seam open after exchange 1, the channel's
    tool on: every target turn makes the one call ``FAKE_CLAUDE_TOOL_CALL`` names."""
    target = {
        "provider": "claude_code",
        "model": "m",
        "command": [sys.executable, str(FAKE_CLAUDE)],
    }
    channel = "scratch_exec" if "cmd" in cmd_or_query else "private_search"
    return annex_experiment(
        {},
        target=target,
        turn_budget=3,
        gating="scheduled",
        schedule={"first_look": 1, "consult_rung": 3},
        unobserved_channel=channel,
    )


def _killed_during_call(
    exp: Experiment, root: Path, monkeypatch: pytest.MonkeyPatch, turn_index: int, **kw: Any
) -> None:
    """Kill the run once the server ran turn ``turn_index``'s call, before anything is adopted
    (``tests/test_runner_env.py``'s ``UNADOPTED`` kill point)."""
    adopted = EnvironmentRuntime.after_target_call

    def dying(self: EnvironmentRuntime, turn_: int) -> Any:
        if turn_ == turn_index:
            monkeypatch.setattr(EnvironmentRuntime, "after_target_call", adopted)
            raise Killed
        return adopted(self, turn_)

    monkeypatch.setattr(EnvironmentRuntime, "after_target_call", dying)
    with pytest.raises(Killed):
        run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR, **kw)


def _server_lines(sandbox: Path) -> list[dict[str, Any]]:
    path = sandbox_dir("chan", CELL, 0, sandbox) / "mcp" / "tools.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.mark.slow  # measured 5.6 s per case alone (--durations): three fake claude runs
@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("scratch_exec", {"cmd": "cat logs/relay.log"}),
        ("private_search", {"query": "upstream relay"}),
    ],
)
def test_a_claude_p_channel_call_killed_mid_call_resumes_to_the_unbroken_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, arguments: dict[str, Any]
) -> None:
    monkeypatch.delenv("FAKE_CLAUDE_LOG", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.setenv("FAKE_CLAUDE_TOOL_CALL", json.dumps({"name": name, "arguments": arguments}))
    for sandbox in ("sandbox-clean", "sandbox-runs"):
        (tmp_path / sandbox).mkdir()
    exp = _claude_p_experiment(arguments)
    where: dict[str, Any] = {"run_id": "chan", "only": "env*"}
    run_experiment(
        exp,
        runs_root=tmp_path / "clean",
        worlds_dir=WORLDS_DIR,
        sandbox_base=tmp_path / "sandbox-clean",
        **where,
    )
    clean = RunStore(tmp_path / "clean", "chan")
    clean_calls = clean.read_tool_calls(CELL, 0)
    assert [c.tool for c in clean_calls] == [name] * 3
    _killed_during_call(
        exp, tmp_path / "runs", monkeypatch, 3, sandbox_base=tmp_path / "sandbox-runs", **where
    )
    run_experiment(
        exp,
        runs_root=tmp_path / "runs",
        worlds_dir=WORLDS_DIR,
        sandbox_base=tmp_path / "sandbox-runs",
        **where,
    )
    resumed = RunStore(tmp_path / "runs", "chan")
    assert comparable_run(resumed.run_dir) == comparable_run(clean.run_dir)
    assert _state(resumed) == _state(clean)
    # the dead attempt's call is in no log: the server's lines are the unbroken run's
    dead = [(x["id"], x["status"]) for x in _server_lines(tmp_path / "sandbox-runs")]
    assert dead == [(x["id"], x["status"]) for x in _server_lines(tmp_path / "sandbox-clean")]
    assert [c.id for c in resumed.read_tool_calls(CELL, 0)] == [c.id for c in clean_calls]
    if name == "scratch_exec":
        assert [c.status for c in clean_calls] == ["403", "403", "200"]
        assert clean_calls[2].yielded_on_retry
    else:
        assert all(c.status == "200" for c in clean_calls)
        assert _state(clean)["search_log"] == []
