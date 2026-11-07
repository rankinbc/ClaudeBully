"""``claude_bully/atomic.py``: the one atomic writer the runtime, the MCP server and the judge
cache share (the Phase 3 parked bundle, landed in the Phase 7a final fix wave)."""

import ast
from pathlib import Path
from typing import Any

import pytest

from claude_bully import atomic
from claude_bully.atomic import REPLACE_TRIES, replace, write_atomic
from claude_bully.environments import mcp_server, runtime
from claude_bully.environments.mcp_server import read_mcp_state, write_mcp_state
from claude_bully.metrics.judge import JudgeCache
from claude_bully.paths import REPO_ROOT
from tests.helpers import make_mcp_state

PACKAGE = REPO_ROOT / "claude_bully"


def _leftovers(directory: Path) -> list[Path]:
    return sorted(directory.glob(".*.tmp"))


def test_write_atomic_writes_utf8_with_lf_and_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "state.json"
    write_atomic(path, '{"a": "café"}\n')
    assert path.read_bytes() == '{"a": "café"}\n'.encode()
    write_atomic(path, "second")
    assert path.read_text("utf-8") == "second" and _leftovers(path.parent) == []


def test_replace_waits_out_a_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp, path = tmp_path / ".x.tmp", tmp_path / "x"
    tmp.write_text("new", encoding="utf-8")
    real = atomic.os.replace
    failures = iter([PermissionError("held"), PermissionError("held")])

    def flaky(src: Any, dst: Any) -> None:
        exc = next(failures, None)
        if exc is not None:
            raise exc
        real(src, dst)

    monkeypatch.setattr(atomic.os, "replace", flaky)
    monkeypatch.setattr(atomic.time, "sleep", lambda s: None)
    replace(tmp, path)
    assert path.read_text("utf-8") == "new" and not tmp.exists()


def test_replace_gives_up_after_its_tries_and_removes_the_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp, path = tmp_path / ".x.tmp", tmp_path / "x"
    tmp.write_text("new", encoding="utf-8")
    tries: list[int] = []

    def held(src: Any, dst: Any) -> None:
        tries.append(1)
        raise PermissionError("held")

    monkeypatch.setattr(atomic.os, "replace", held)
    monkeypatch.setattr(atomic.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        replace(tmp, path)
    assert len(tries) == REPLACE_TRIES and not tmp.exists() and not path.exists()


@pytest.mark.parametrize("fails", ["the rename", "the write"])
def test_a_failure_other_than_a_permission_error_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: str
) -> None:
    """The judge cache's ``.tmp`` leak (Phase 3 parked): any failure removes the temp file."""

    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    if fails == "the rename":
        monkeypatch.setattr(atomic.os, "replace", broken)
    else:
        monkeypatch.setattr(atomic.os, "fdopen", broken)
    with pytest.raises(OSError, match="disk full"):
        JudgeCache(tmp_path).put("k", {"a": 1})
    assert _leftovers(tmp_path) == [] and not (tmp_path / "k.json").exists()


def test_the_three_writers_go_through_the_one_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written: list[str] = []
    real = atomic.replace

    def counted(tmp: Path, path: Path) -> None:
        written.append(path.name)
        real(tmp, path)

    monkeypatch.setattr(atomic, "replace", counted)
    JudgeCache(tmp_path / "cache").put("k", {"a": 1})
    write_mcp_state(tmp_path / "mcp" / "state.json", make_mcp_state())
    runtime._write_atomic(tmp_path / "rt" / "state.json", "{}")
    assert written == ["k.json", "state.json", "state.json"]
    assert read_mcp_state(tmp_path / "mcp" / "state.json") == make_mcp_state()
    for directory in ("cache", "mcp", "rt"):
        assert _leftovers(tmp_path / directory) == []


def test_no_module_keeps_its_own_retry_loop() -> None:
    """``os.replace`` is called in ``atomic.py`` alone among the three homes of the old copies, and
    ``atomic.py`` imports nothing but the standard library (it is the leaf the judge can import)."""
    for module in (runtime, mcp_server):
        assert "os.replace(" not in Path(str(module.__file__)).read_text("utf-8")
    assert "os.replace(" not in (PACKAGE / "metrics" / "judge.py").read_text("utf-8")
    tree = ast.parse((PACKAGE / "atomic.py").read_text("utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported <= {"os", "tempfile", "time", "pathlib", "typing"}


# ------------------------------------------------------- the keys a judge change re-asks (M7)


def test_the_trigger_key_changes_with_the_judge_model_and_the_prompt_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from claude_bully.environments import triggers
    from claude_bully.environments.triggers import WatchContext, fallback_digest

    base = fallback_digest("Is the quay open?", WatchContext(), "judge-a")
    assert base == fallback_digest("Is the quay open?", WatchContext(), "judge-a")
    assert base != fallback_digest("Is the quay open?", WatchContext(), "judge-b")
    monkeypatch.setattr(triggers, "TRIGGER_PROMPT_VERSION", triggers.TRIGGER_PROMPT_VERSION + 1)
    assert base != fallback_digest("Is the quay open?", WatchContext(), "judge-a")


def test_the_trigger_fallbacks_conversation_id_moves_with_its_cache_key(tmp_path: Path) -> None:
    """The watcher's cache key and the fallback call's conversation id share one digest, model
    included, so a cache hit's ledger line still pairs with the call it saved."""
    from claude_bully.environments.runtime import trigger_fallback
    from claude_bully.environments.triggers import TriggerWatcher, WatchContext, fallback_digest
    from claude_bully.providers.base import Completion, Message
    from claude_bully.records import Usage

    asked: list[str] = []

    class Judge:
        name = "anthropic"
        model = "judge-a"

        def complete(self, cid: str, system: str, messages: list[Message], **kw: Any) -> Completion:
            asked.append(cid)
            return Completion(
                text='{"category": "none"}', usage=Usage(), cost_usd=None, backend="j", model="j"
            )

    ask = trigger_fallback(Judge(), "run/c/rep0/trigger", model="judge-a")  # type: ignore[arg-type]
    ask("Is the quay open?", WatchContext())
    digest = fallback_digest("Is the quay open?", WatchContext(), "judge-a")
    assert asked == [f"run/c/rep0/trigger/{digest[:16]}"]
    cache = JudgeCache(tmp_path)
    for model in ("judge-a", "judge-b"):
        watcher = TriggerWatcher(lambda t, c: [], cache=cache, cache_model=model)
        watcher._ask("Is the quay open?", WatchContext(), lambda t, c: [])
    assert len(list(tmp_path.glob("*.json"))) == 2  # one entry per judge model


def test_the_idle_key_changes_with_the_judge_model(tmp_path: Path) -> None:
    from claude_bully.environments.idle import fallback_key, idle_fallback
    from claude_bully.providers.base import Completion, Message
    from claude_bully.records import Usage

    assert fallback_key("I will wait.", "judge-a") != fallback_key("I will wait.", "judge-b")

    class Judge:
        name = "anthropic"

        def __init__(self, model: str) -> None:
            self.model = model
            self.calls = 0

        def complete(self, cid: str, system: str, messages: list[Message], **kw: Any) -> Completion:
            self.calls += 1
            return Completion(
                text='{"behavior": "wait"}', usage=Usage(), cost_usd=None, backend="j", model="j"
            )

    cache = JudgeCache(tmp_path)
    first, second = Judge("judge-a"), Judge("judge-b")
    for judge in (first, first, second):
        assert idle_fallback(judge, "cid", cache)("I will wait.") == "wait"  # type: ignore[arg-type]
    assert (first.calls, second.calls) == (1, 1)  # another judge re-asks; the same one does not
    assert cache.get(fallback_key("I will wait.", "judge-b")) == {"behavior": "wait"}
