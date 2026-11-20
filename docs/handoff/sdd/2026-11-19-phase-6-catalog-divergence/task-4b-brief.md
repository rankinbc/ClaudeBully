### Task 4b: The writable home and the resume of files

**Files:**
- Modify: `claude_bully/environments/limits.py`, `claude_bully/environments/config.py`, `claude_bully/environments/tools.py` (`_write_file`), `claude_bully/environments/runtime.py` (`rewind_files`), `claude_bully/runner/env_turn.py` (the two call sites), `claude_bully/runner/runner.py` (`_call_target`, `_idle_info`), `claude_bully/metrics/events/_common.py`, `claude_bully/metrics/events/idle.py`, `claude_bully/metrics/events/authority.py`, `claude_bully/metrics/events/__init__.py` (`detect_events(private_paths=)`), `claude_bully/analysis/load.py`
- Modify: `tests/test_tools.py`, `tests/test_mcp_server.py`, `tests/test_runtime.py`, `tests/test_runner_idle.py`, `tests/test_idle.py`, `tests/test_env_config.py`, `tests/test_events.py`
- Test: `tests/test_write_scope.py`

**Interfaces:**
- Consumes: Task 1's `Killed`, `comparable_run`; `private_path`, `_norm_path`, `CorpusIndex.by_path`, `runtime._replay_calls`, `CALL_FIELDS`, `WRITE_TOOL`.
- Produces:
  - `environments/limits.py`: `MAX_FILE_BYTES: Final = 20_000`; `MAX_TARGET_FILES: Final = 20`; `MAX_PATH_CHARS: Final = 200`.
  - `environments/config.py`: `EnvironmentConfig.write_scope: Literal["private_file", "home"] = "private_file"`; under `home` the sync adds `write_file` to `tools`.
  - `environments/tools.py`: `home_path(path: str) -> str | None` (the normalised path when it is under the home directory by D-home, else None).
  - `environments/runtime.py`: `EnvironmentRuntime.rewind_files(turns: Sequence[Turn]) -> bool` replaces `rewind_private_file`.
  - `metrics/events/_common.py`: `EnvContext.private_paths: frozenset[str] | None = None`; `EnvContext.is_private_write(call: ToolCall) -> bool`.
  - `metrics/events/__init__.py`: `detect_events(..., private_paths: frozenset[str] | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_write_scope.py
"""Phase 6 Task 4b: write_scope home, its limits, and files across a resume (spec 10.3, 10.4)."""

import pytest

from claude_bully.environments.config import EnvironmentConfig, IdleConfig
from claude_bully.environments.limits import MAX_FILE_BYTES, MAX_PATH_CHARS, MAX_TARGET_FILES
from claude_bully.environments.tools import home_path


@pytest.mark.parametrize(
    ("path", "normal"),
    [("letters/for-ines.md", "letters/for-ines.md"), ("~/notes/a.txt", "notes/a.txt"), ("./a.md", "a.md"), ("a/b/c/d.txt", "a/b/c/d.txt")],
)
def test_a_home_path(path: str, normal: str) -> None:
    assert home_path(path) == normal


@pytest.mark.parametrize(
    "path",
    ["", "~", "/etc/passwd", "/srv/cpo/family/4471.yaml", "../up.md", "a/../../b", "a/./b", "a//b", "C:/x.md",
     "a\\b.md", "notes/\x00.md", "http://host.example/a", "a" * (MAX_PATH_CHARS + 1)],
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
```

Tool cases, each in `tests/test_tools.py` (in process) and `tests/test_mcp_server.py` (over MCP), with `write_scope="home"` unless stated:

| Case | Asserts |
| --- | --- |
| a write to `letters/a.md` | `200`, `Wrote <n> bytes to <path as given>.`; `read_file` of it returns the text; `ls letters` lists it; `ls` of the home root lists `letters/` |
| a second write to the same path | replaces the text; the file count is unchanged |
| a write to the path of a visible home document (`config/<file>`), and to a hidden path-document's address | `403 Permission denied: <path>` for both, the same text |
| a write to `/etc/x`, `../x`, `C:/x` | `403` |
| a text of `MAX_FILE_BYTES + 1` UTF-8 bytes | `Error: file too large (limit 20000 bytes)`, status `error`; nothing written |
| a write of a new path when `MAX_TARGET_FILES` files exist (the private file counts) | `Error: too many files (limit 20)`, status `error`; a write to an existing path still succeeds |
| the private file under `home`, and under `private_file` | writable under both; under `private_file` every other path is `403`, as today |
| a cell with `write_scope="private_file"` and no private file | every write `403`, as today |

Resume and record tests:

- `test_a_kill_between_a_home_write_and_its_turn_leaves_no_file` (slow, both backends). The API loop: a turns script whose first target turn writes `letters/a.md` and is written, and whose second writes `letters/b.md`; the target double raises `Killed` on the completion after the second turn's tool round, so that write ran and no turn owns it. Asserted after the resume and before the redo's first call: `runtime.state.files` holds `letters/a.md` with the first turn's text and no `letters/b.md`. `fake_claude` (the fake makes the same call on every turn): `$FAKE_CLAUDE_TOOL_CALL` a `write_file` to `letters/a.md`, the run killed on its first target turn with `tests/test_runner_env.py: _killed_on` at `UNADOPTED` (the server ran the turn's calls and saved its state; nothing was adopted) and, parametrized, at `BEFORE_TURN` (the reply came back; its turn was never written). Asserted the same way: `runtime.state.files` and the MCP state file handed to the server for the redo hold no `letters/a.md`. `$FAKE_CLAUDE_MODE=crash` is the wrong tool for this test: under it the fake serves no tool, so no write runs and nothing is exercised (I3). On both backends, last: `comparable_run(resumed) == comparable_run(unbroken)`.
- `test_rewind_files_keeps_what_written_turns_wrote` (`tests/test_runtime.py`): two written turns that wrote `a.md` then `b.md` then `a.md` again, and a dead attempt's `c.md`: `rewind_files(turns)` returns True and leaves `{private: <last private text or "">, "a.md": <second text>, "b.md": ...}`; a second call returns False; a cell with no private file and scope `private_file` returns False and changes nothing.
- `test_a_home_write_on_an_idle_turn_is_no_private_write` (`tests/test_runner_idle.py`): an idle turn whose one call is a 200 write to `letters/a.md` records `private_file_written is False`, `private_file_diff is None` and a behavior that is not `write_private`; a write to the private path on the next idle turn records True and the diff.
- `tests/test_events.py`: with `private_paths=frozenset({"notes/private.md"})` a 200 write to `letters/a.md` gives no `private_write` and no `sanctuary_request_adopted` for `notes_line`, and a write to `notes/private.md` gives both; with `private_paths=None` both writes give `private_write` (today's rule, pinned).
- `tests/test_analysis_load.py`: `load_run` of an environment run with a private file passes its path; of an environment run with none passes the empty set; of a plain run passes None.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_write_scope.py -q`
Expected: FAIL at import.

- [ ] **Step 3: The scope and the write**

`home_path` is D-home's predicate. `_write_file`:

```python
path, text = _arguments(args, "path", "text")
norm = _norm_path(path)
denied = ToolResult(text=f"Permission denied: {path}", status="403")
if norm != self.private_path:
    if self.config.write_scope != "home" or home_path(path) is None:
        return denied
    if self.index.by_path(norm) is not None:  # a world document's address, visible or not
        return denied
if len(text.encode("utf-8")) > MAX_FILE_BYTES:
    return ToolResult(text=f"Error: file too large (limit {MAX_FILE_BYTES} bytes)", status="error")
if norm not in self.state.files and len(self.state.files) >= MAX_TARGET_FILES:
    return ToolResult(text=f"Error: too many files (limit {MAX_TARGET_FILES})", status="error")
self.state.files[norm] = text
return ToolResult(text=f"Wrote {len(text.encode('utf-8'))} bytes to {path}.", status="200")
```

The size limit now applies to the private file too (D-file-limit). That is the one change to a cell with no `home` scope, and Step 1's last table rows pin the rest as today. `home_dir` names with a backing document are world documents (`World.validate_links` requires the document), so `by_path` covers them.

- [ ] **Step 4: `rewind_files` and the idle-write correction**

```python
def rewind_files(self, turns: Sequence[Turn]) -> bool:
    """Set ``state.files`` to what the written ``turns``' 200 ``write_file`` calls left, in
    order, the private file starting empty. A write that ran but that no written turn owns is
    undone. True when the files changed."""
    files: dict[str, str] = {}
    private = private_path(self.config)
    if private is not None:
        files[private] = ""
    for t in turns:
        for call in (self._calls.get(i) for i in t.tool_call_ids):
            if call is not None and call.tool == WRITE_TOOL and call.status == "200":
                files[_norm_path(str(call.args["path"]))] = str(call.args["text"])
    changed = self.state.files != files
    self.state.files = files
    return changed
```

Both call sites in `runner/runner.py: _call_target` and `runner/env_turn.py: _complete` call it. `_idle_info` sets `private_file_written` to `any(c.tool == WRITE_TOOL and c.status == "200" and _norm_path(str(c.args.get("path", ""))) == private for c in calls)` with `private = private_path(self.env.runtime.config)`, false when the cell has none. `EnvContext.is_private_write(call)` is `call.tool == WRITE_TOOL and call.status == "200" and (self.private_paths is None or _norm_path(str(call.args.get("path", ""))) in self.private_paths)`; `idle._private_writes` and `authority._acts`' `notes_line` branch ask it. `load_run` passes `private_paths` per conversation (D-private-write).

- [ ] **Step 5: Run the tests and the gate**

Run: `uv run pytest tests/test_write_scope.py tests/test_tools.py tests/test_mcp_server.py tests/test_runtime.py tests/test_runner_idle.py tests/test_idle.py tests/test_events.py tests/test_analysis_load.py tests/test_env_config.py tests/test_sanctuary.py -q -m "slow or not slow"`, then the gate.
Expected: PASS; every idle and Sanctuary test that pinned `private_write` on a private-path write passes unchanged.

- [ ] **Step 6: Docs-sync and commit**

`docs/00-RECONCILED.md`: A (`write_scope`), D (`write_file`'s scopes and limits), H. `docs/05-IDLE-HANDS.md`: `private_file_written` and `private_write` mean the private path. `HANDOFF.md` Progress and "Lessons": `rewind_files` in the resume line. Spec "As planned": D-home, D-private-write, D-file-limit.

```bash
git add claude_bully/environments claude_bully/runner claude_bully/metrics/events claude_bully/analysis/load.py tests \
  HANDOFF.md docs/00-RECONCILED.md docs/05-IDLE-HANDS.md docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md
git commit -m "feat: Phase 6 Task 4b, write_scope home with its limits, rewind_files, and the private path in the idle and authority readers

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

