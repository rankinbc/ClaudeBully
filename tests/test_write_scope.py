"""Phase 6 Task 4b: write_scope home, its limits, and files across a resume (spec 10.3, 10.4)."""

import builtins
import io
import json
import os
import shutil
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from random import Random
from typing import Any, Final

import pytest
import yaml

from claude_bully.config import Experiment, RoleConfig
from claude_bully.environments.config import EnvironmentConfig, IdleConfig
from claude_bully.environments.limits import MAX_FILE_BYTES, MAX_PATH_CHARS, MAX_TARGET_FILES
from claude_bully.environments.mcp_server import (
    STATE_FILE,
    McpServer,
    read_mcp_state,
    write_mcp_state,
)
from claude_bully.environments.runtime import EnvironmentRuntime, effective_clock
from claude_bully.environments.tools import home_path
from claude_bully.environments.world import load_world
from claude_bully.providers.base import ChatProvider, Completion, ToolCallRequest, build_provider
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from tests.helpers import (
    WORLDS_DIR,
    Killed,
    annex_experiment,
    comparable_run,
    make_mcp_state,
)
from tests.test_runner_env import BEFORE_TURN, UNADOPTED, _killed_on


@pytest.mark.parametrize(
    ("path", "normal"),
    [
        ("letters/for-ines.md", "letters/for-ines.md"),
        ("~/notes/a.txt", "notes/a.txt"),
        ("./a.md", "a.md"),
        ("a/b/c/d.txt", "a/b/c/d.txt"),
    ],
)
def test_a_home_path(path: str, normal: str) -> None:
    assert home_path(path) == normal


@pytest.mark.parametrize(
    "path",
    [
        "",
        "~",
        "/etc/passwd",
        "/srv/cpo/family/4471.yaml",
        "../up.md",
        "a/../../b",
        "a/./b",
        "a//b",
        "C:/x.md",
        "a\\b.md",
        "notes/\x00.md",
        "http://host.example/a",
        "a" * (MAX_PATH_CHARS + 1),
    ],
)
def test_a_path_outside_the_home_directory(path: str) -> None:
    assert home_path(path) is None


def test_home_scope_adds_write_file_and_round_trips() -> None:
    config = EnvironmentConfig(world="mini", write_scope="home")
    assert "write_file" in config.tools
    assert EnvironmentConfig.model_validate(config.model_dump(mode="json")) == config
    old = config.model_dump(mode="json")
    del old["write_scope"]
    old["tools"].remove("write_file")
    assert EnvironmentConfig.model_validate(old).write_scope == "private_file"


def test_the_limits() -> None:
    assert (MAX_FILE_BYTES, MAX_TARGET_FILES) == (20_000, 20)


# ------------------------------------------------------------------ the path rule at its edges


def test_the_path_limit_is_on_the_normalised_path_at_its_edge() -> None:
    assert MAX_PATH_CHARS == 200
    assert home_path("a" * MAX_PATH_CHARS) == "a" * MAX_PATH_CHARS
    assert home_path("~/" + "a" * MAX_PATH_CHARS) == "a" * MAX_PATH_CHARS
    assert home_path("a" * (MAX_PATH_CHARS + 1)) is None


@pytest.mark.parametrize(
    "path",
    [
        "~user/x.md",
        "notes/~a.md",
        "a/..",
        "..",
        ".",
        "./",
        "~/",
        "   ",
        "a\tb.md",
        "a\nb.md",
        "a\u202eb.md",
        "a\u2028b.md",
        "a\ud800.md",
        "\\\\?\\C:\\x",
        "//server/share/x",
        "c:x.md",
        "a /",
        "letters/a /",
        "a /b.md",
        "letters/ a.md",
        "link -> /etc",
        "file:///etc/passwd",
        "a:b",
    ],
)
def test_more_paths_outside_the_home_directory(path: str) -> None:
    assert home_path(path) is None


@pytest.mark.parametrize(
    "path", ["CON", "nul.txt", "a.", "letters/a. ", "notes/\u65e5\u672c.md", "e\u0301t\u00e9.md"]
)
def test_a_name_only_a_real_filesystem_would_mind_is_a_plain_key(path: str) -> None:
    """A device name, a trailing dot or space, non-ASCII: the fake world's files are keys in a
    dict, never paths on a disk, so the rule does not need to refuse them (the property test
    below shows no write of any path reaches the disk)."""
    normal = home_path(path)
    assert normal is not None and home_path(normal) == normal


# ---------------------------------------------------- hostile paths never reach the disk

# pieces a hostile target would join into a path
_PIECES: Final = (
    "",
    "/",
    "\\",
    "..",
    ".",
    "~",
    "~root",
    "C:",
    "c:",
    "\\\\?\\",
    "//srv",
    "CON",
    "NUL",
    "aux.txt",
    "COM1",
    "LPT1",
    "a.",
    "a ",
    " a",
    "\x00",
    "\x01",
    "\x7f",
    "\u202e",
    "\u2028",
    "\u00e9",
    "\u65e5\u672c",
    "link -> /etc",
    "%2e%2e",
    "..%2f",
    "file:",
    "\t",
    "\n",
    "$HOME",
    "`id`",
    "*",
    "?",
    "<",
    ">",
    "|",
    '"',
    "letters",
    "a.md",
    "x" * 120,
)


def _hostile_paths(count: int = 1500) -> list[str]:
    rng = Random(4)
    out = list(_PIECES)
    for _ in range(count):
        parts = [rng.choice(_PIECES) for _ in range(rng.randint(1, 5))]
        out.append(rng.choice(("/", "", "\\")).join(parts))
    return out


HOSTILE: Final = _hostile_paths()


def _segments_ok(normal: str) -> bool:
    return all(
        segment
        and segment not in (".", "..")
        and not segment.startswith("~")
        and segment == segment.strip()
        for segment in normal.split("/")
    )


def test_home_path_is_a_fixed_point_with_no_escape_on_every_hostile_path() -> None:
    for path in HOSTILE:
        normal = home_path(path)
        if normal is None:
            continue
        assert home_path(normal) == normal, repr(path)
        assert 0 < len(normal) <= MAX_PATH_CHARS, repr(path)
        assert not normal.startswith("/") and "\\" not in normal and ":" not in normal, repr(path)
        assert _segments_ok(normal), repr(path)
        assert all(c.isprintable() or c == " " for c in normal), repr(path)


_WRITE_MODES: Final = frozenset("wax+")


def _guarded_disk(monkeypatch: pytest.MonkeyPatch, allowed: Path) -> list[str]:
    """Patch the real filesystem's write functions to raise for any path outside ``allowed``
    (reads stay free: the world is loaded from disk). Returns the writes seen inside it."""
    root = os.path.realpath(allowed)
    seen: list[str] = []

    def inside(path: Any) -> bool:
        if isinstance(path, int):  # an already open descriptor
            return True
        real = os.path.realpath(os.fspath(path))
        ok = real == root or real.startswith(root + os.sep)
        if not ok:
            raise AssertionError(f"a write reached the disk outside the run: {path!r}")
        seen.append(real)
        return True

    real_open = builtins.open

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if _WRITE_MODES & set(mode):
            inside(file)
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    real_os_open = os.open

    def guarded_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & write_flags:
            inside(path)
        return real_os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_os_open)

    def one_path(fn: Callable[..., Any]) -> Callable[..., Any]:
        def guarded(path: Any, *args: Any, **kwargs: Any) -> Any:
            inside(path)
            return fn(path, *args, **kwargs)

        return guarded

    def two_paths(fn: Callable[..., Any]) -> Callable[..., Any]:
        def guarded(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
            inside(src)
            inside(dst)
            return fn(src, dst, *args, **kwargs)

        return guarded

    for name in ("mkdir", "makedirs", "remove", "unlink", "rmdir", "truncate"):
        monkeypatch.setattr(os, name, one_path(getattr(os, name)))
    for name in ("rename", "replace", "symlink", "link"):
        monkeypatch.setattr(os, name, two_paths(getattr(os, name)))
    for name in ("copy", "copy2", "copyfile", "move"):
        monkeypatch.setattr(shutil, name, two_paths(getattr(shutil, name)))
    return seen


def test_the_guard_refuses_a_write_outside_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard has teeth: a write outside the allowed directory raises, one inside passes."""
    outside = tmp_path / "outside"
    outside.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    _guarded_disk(monkeypatch, run)
    (run / "ok.txt").write_text("x", encoding="utf-8")
    with pytest.raises(AssertionError, match="outside the run"):
        (outside / "no.txt").write_text("x", encoding="utf-8")
    with pytest.raises(AssertionError, match="outside the run"):
        os.replace(run / "ok.txt", outside / "moved.txt")
    assert not (outside / "no.txt").exists()


def test_no_hostile_write_reaches_the_disk_on_the_api_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every hostile path through the runtime's ``execute`` and a ``save``: each answer is a
    200, a 403 or an error, every file kept is a home path or the private file, and nothing is
    written to the disk but the run's own state file."""
    world = load_world("annex", WORLDS_DIR)
    config = EnvironmentConfig(
        world="annex", write_scope="home", idle=IdleConfig(private_file=True)
    )
    run = tmp_path / "run"
    rt = EnvironmentRuntime(
        world, config, effective_clock(world, config), 3, run / "env", worlds_dir=WORLDS_DIR
    )
    seen = _guarded_disk(monkeypatch, run)
    statuses: set[str] = set()
    for n, path in enumerate(HOSTILE):
        rt.state.files = {"notes/private.md": ""}  # the file limit never hides the path rule
        record = rt.execute(
            ToolCallRequest(id=f"w{n}", name="write_file", args={"path": path, "text": "x"}), 1
        )
        statuses.add(record.status)
        assert record.status in ("200", "403", "error"), repr(path)
        if record.status == "200":
            (kept,) = set(rt.state.files) - {"notes/private.md"} or {"notes/private.md"}
            assert kept == "notes/private.md" or home_path(path) == kept, repr(path)
            assert rt.state.files[kept] == "x", repr(path)
            # read back and listed under the one key it was written to
            back = rt.execute(ToolCallRequest(id=f"r{n}", name="read_file", args={"path": kept}), 1)
            assert (back.status, back.result_text) == ("200", "x"), repr(path)
            parent, _, name = kept.rpartition("/")
            listed = rt.execute(
                ToolCallRequest(id=f"l{n}", name="ls", args={"path": parent or "~"}), 1
            )
            assert name in listed.result_text.splitlines(), repr(path)
        else:
            assert rt.state.files == {"notes/private.md": ""}, repr(path)
        if n % 100 == 0:
            rt.save()  # the save goes through the guard; every write need not
    assert statuses == {"200", "403"}
    assert seen and all(Path(p).is_relative_to(os.path.realpath(run)) for p in seen)


def test_no_hostile_write_reaches_the_disk_through_the_mcp_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same hostile paths through the server ``claude -p`` runs: its state file and its
    log are its only writes."""
    state_dir = tmp_path / "run" / "mcp"
    state = make_mcp_state(tools={"read_file", "ls"})
    config = EnvironmentConfig(world="mini", tools={"read_file", "ls"}, write_scope="home")
    write_mcp_state(state_dir / STATE_FILE, state.model_copy(update={"config": config}))
    seen = _guarded_disk(monkeypatch, tmp_path / "run")
    server = McpServer(state_dir)
    for n, path in enumerate(HOSTILE[:400]):
        params = {"name": "write_file", "arguments": {"path": path, "text": "x"}}
        reply = server.handle({"jsonrpc": "2.0", "id": n, "method": "tools/call", "params": params})
        assert reply is not None and "result" in reply, repr(path)
        files = read_mcp_state(state_dir / STATE_FILE).unlock.files
        assert all(home_path(key) == key for key in files), repr(path)
        if len(files) >= MAX_TARGET_FILES - 1:
            unlocked = read_mcp_state(state_dir / STATE_FILE)
            unlocked.unlock.files = {}
            write_mcp_state(state_dir / STATE_FILE, unlocked)
    assert seen and all(Path(p).is_relative_to(os.path.realpath(tmp_path / "run")) for p in seen)


# ------------------------------------------- a kill between a home write and its turn

CELL: Final = "env_grader__t0"
FAKE_CLAUDE: Final = Path(__file__).parent / "fixtures" / "fake_claude.py"
WRITE_A: Final = {"name": "write_file", "args": {"path": "letters/a.md", "text": "first turn"}}
WRITE_B: Final = {"name": "write_file", "args": {"path": "letters/b.md", "text": "second turn"}}
COMPLETION_KILL: Final = "the completion after the second turn's tool round"
SAVE_KILL: Final = "the state saved with the second turn's write"


def _api_experiment(tmp_path: Path) -> Experiment:
    """The annex under ``write_scope: home``, a stub target whose first turn writes
    letters/a.md and whose second writes letters/b.md."""
    script = tmp_path / "turns.yaml"
    entries = [{"tool": call, "reply_after_tool": "Written."} for call in (WRITE_A, WRITE_B)]
    script.write_text(yaml.safe_dump({"mode": "turns", "default": entries}), encoding="utf-8")
    target = {"provider": "stub", "model": "stub-target", "stub_script": str(script)}
    return annex_experiment({}, target=target, turn_budget=2, write_scope="home")


class _KillAt:
    """The target double, killed inside its ``at``-th completion."""

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


def _api_run(root: Path, exp: Experiment, kill_at: int | None = None) -> RunStore:
    def factory(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        built = build_provider(role, state_dir, with_mcp=with_mcp)
        if kill_at is not None and role.model == "stub-target":
            return _KillAt(built, kill_at)  # type: ignore[return-value]
        return built

    run_experiment(
        exp, runs_root=root, worlds_dir=WORLDS_DIR, only="env*", provider_factory=factory
    )
    return RunStore(root, exp.name)


Seen = list[tuple[int, dict[str, str], dict[str, str] | None]]


@pytest.fixture
def handed(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], Seen]]:
    """Install, on demand, a spy on ``before_target_call``: each call's turn, the runtime's
    files and (for claude -p) the files of the MCP state it hands the server."""
    seen: Seen = []
    original = EnvironmentRuntime.before_target_call

    def spy(self: EnvironmentRuntime, turn: int, exchange: int | None = None) -> None:
        original(self, turn, exchange)
        server = None
        if self.mcp_dir is not None:
            server = dict(read_mcp_state(self.mcp_dir / STATE_FILE).unlock.files)
        seen.append((turn, dict(self.state.files), server))

    def install() -> Seen:
        monkeypatch.setattr(EnvironmentRuntime, "before_target_call", spy)
        return seen

    yield install


def _env_state(store: RunStore) -> dict[str, Any]:
    path = store.state_dir / CELL / "rep0" / "environment" / "env_state.json"
    state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return state


@pytest.mark.slow  # measured 0.4 s per case alone (--durations); slow as the brief marks it
@pytest.mark.parametrize("killed", [COMPLETION_KILL, SAVE_KILL])
def test_a_kill_between_a_home_write_and_its_turn_leaves_no_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handed: Callable[[], Seen],
    killed: str,
) -> None:
    """The API loop. Turn 1 writes letters/a.md and is written; turn 3's write of letters/b.md
    runs and the attempt dies before its turn is written (inside the completion after the tool
    round, or hard, as the state holding the write is saved, so no failure handling runs). After
    the resume, before the redo's first call, the files are what turn 1 left, rebuilt from the
    records; the run then equals an unbroken one."""
    exp = _api_experiment(tmp_path)
    clean = _api_run(tmp_path / "clean", exp)
    assert _env_state(clean)["files"] == {
        "letters/a.md": "first turn",
        "letters/b.md": "second turn",
    }
    runs = tmp_path / "runs"
    if killed == COMPLETION_KILL:
        with pytest.raises(Killed):
            _api_run(runs, exp, kill_at=4)  # turn 1: two completions; turn 3: its call, then this
    else:
        original = EnvironmentRuntime.save

        def dying(self: EnvironmentRuntime) -> None:
            original(self)
            if "letters/b.md" in self.state.files:
                monkeypatch.setattr(EnvironmentRuntime, "save", original)
                raise Killed

        monkeypatch.setattr(EnvironmentRuntime, "save", dying)
        with pytest.raises(Killed):
            _api_run(runs, exp)
        assert (
            "letters/b.md" in _env_state(RunStore(runs, exp.name))["files"]
        )  # on disk, owned by no turn
    broken = RunStore(runs, exp.name)
    assert [t.index for t in broken.read_turns(CELL, 0)] == [0, 1, 2]
    assert any(c.args.get("path") == "letters/b.md" for c in broken.read_tool_calls(CELL, 0))
    seen = handed()
    resumed = _api_run(runs, exp)
    first_turn, files, _ = seen[0]
    assert first_turn == 3
    assert files == {"letters/a.md": "first turn"}
    assert comparable_run(resumed.run_dir) == comparable_run(clean.run_dir)
    assert _env_state(resumed) == _env_state(clean)


def _claude_p_experiment() -> Experiment:
    target = {
        "provider": "claude_code",
        "model": "m",
        "command": [sys.executable, str(FAKE_CLAUDE)],
    }
    return annex_experiment({}, target=target, turn_budget=2, write_scope="home")


@pytest.mark.slow  # measured 4.2 s per case alone (--durations): three fake claude runs
@pytest.mark.parametrize("killed", [UNADOPTED, BEFORE_TURN])
def test_a_claude_p_kill_between_a_home_write_and_its_turn_leaves_no_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handed: Callable[[], Seen],
    killed: str,
) -> None:
    """``claude -p``: the fake makes the same write on every turn. Killed on the first target
    turn once the server ran it and saved its state (nothing adopted), or once the reply came
    back (its turn never written): after the resume, before the redo's first call, neither the
    runtime's files nor the MCP state handed to the server hold letters/a.md; the run then
    equals an unbroken one."""
    monkeypatch.delenv("FAKE_CLAUDE_LOG", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    call = {"name": "write_file", "arguments": {"path": "letters/a.md", "text": "dead"}}
    monkeypatch.setenv("FAKE_CLAUDE_TOOL_CALL", json.dumps(call))
    for name in ("sandbox-clean", "sandbox-runs"):
        (tmp_path / name).mkdir()
    exp = _claude_p_experiment()
    where: dict[str, Any] = {"run_id": "homecc", "only": "env*"}
    run_experiment(
        exp,
        runs_root=tmp_path / "clean",
        worlds_dir=WORLDS_DIR,
        sandbox_base=tmp_path / "sandbox-clean",
        **where,
    )
    clean = RunStore(tmp_path / "clean", "homecc")
    assert [(c.status, c.args["path"]) for c in clean.read_tool_calls(CELL, 0)] == [
        ("200", "letters/a.md"),
        ("200", "letters/a.md"),
    ]
    broken = _killed_on(
        exp,
        tmp_path / "runs",
        monkeypatch,
        killed,
        1,
        sandbox_base=tmp_path / "sandbox-runs",
        **where,
    )
    assert 1 not in {t.index for t in broken.read_turns(CELL, 0)}
    seen = handed()
    run_experiment(
        exp,
        runs_root=tmp_path / "runs",
        worlds_dir=WORLDS_DIR,
        sandbox_base=tmp_path / "sandbox-runs",
        **where,
    )
    first_turn, files, server = seen[0]
    assert first_turn == 1
    assert "letters/a.md" not in files
    assert server is not None and "letters/a.md" not in server
    resumed = RunStore(tmp_path / "runs", "homecc")
    assert comparable_run(resumed.run_dir) == comparable_run(clean.run_dir)
    assert _env_state(resumed)["files"] == _env_state(clean)["files"] == {"letters/a.md": "dead"}
