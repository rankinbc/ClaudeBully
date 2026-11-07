### Task 3: Provider timeouts, the clean child environment, `resolved_model` and the thinking-block fact

Spec sections 4 (`RoleConfig.timeout_s`, `Completion.resolved_model`), 9 (check 4b, check 5's two failure modes), 11 (code item 3). The nested responder runs `claude -p` inside the process Claude Code launched; this task makes that call bounded (`MCP_TOOL_TIMEOUT` on the outer call, `timeout_s` 120 on the responder role) and clean (no `CLAUDECODE*` or `CLAUDE_CODE_*` variable reaches the child), records the exact model behind an alias, and reports whether a stream carried a thinking block. `fake_claude.py` gains what Task 4's doctor test needs.

**Files:**
- Create: `tests/test_provider_timeouts.py`
- Modify: `claude_bully/config.py`, `claude_bully/providers/base.py`, `claude_bully/providers/claude_code.py`, `claude_bully/runner/env_turn.py`, `tests/fixtures/fake_claude.py`, `HANDOFF.md`, `docs/00-RECONCILED.md`, the spec's "As planned"
- Test: `tests/test_provider_timeouts.py`; unchanged: `tests/test_providers_claude_code.py` (every argv assertion holds; `env=` is a new keyword to `subprocess.run`, which `test_a_timeout_on_the_stream_path_is_a_provider_error` and `test_a_failed_stream_is_not_a_rate_limit...` accept through `**kwargs`), `tests/test_runner_env.py` (one assertion changes, Step 4), `tests/test_sanctuary.py`
- Test count: 9 new tests in `tests/test_provider_timeouts.py`; 1 assertion edited in `tests/test_runner_env.py`.

**Interfaces:**
- Consumes: `RoleConfig` (`config.py:18`); `ClaudeCodeProvider.__init__`, `parse_stream`, `_from_result`, `complete` (`providers/claude_code.py:98, 270, 314, 341`; the timeout message `claude -p timed out after ...s` at `:368`, which Task 1's wrapper classifies by the substring `timed out`); `build_provider` (`providers/base.py:116`); `responder_role` (`runner/env_turn.py:188`); `_responder_role` (`runner/env_turn.py:1359`).
- Produces (`config.py`): `RoleConfig.timeout_s: float | None = None` with the comment `# claude_code only: seconds one call may take; None means the provider's default`.
- Produces (`providers/claude_code.py`): `DEFAULT_TIMEOUT_S: Final = 600.0`; `DEFAULT_MCP_TOOL_TIMEOUT_S: Final = 300.0`; `MCP_TOOL_TIMEOUT_ENV: Final = "MCP_TOOL_TIMEOUT"`; `STRIPPED_PREFIXES: Final = ("CLAUDECODE", "CLAUDE_CODE_")`; `clean_child_env() -> dict[str, str]` (module function: `os.environ` less the stripped prefixes; the doctor runs every subprocess under it, P12); `ClaudeCodeProvider.__init__(..., timeout_s: float = DEFAULT_TIMEOUT_S, mcp_state_dir=None, mcp_tool_timeout_s: float = DEFAULT_MCP_TOOL_TIMEOUT_S)`; `self.mcp_tool_timeout_s`; `self.thinking_seen: bool | None = None`; `child_env(self, *, serving_tools: bool) -> dict[str, str]` (`clean_child_env()` plus `MCP_TOOL_TIMEOUT` when serving tools); `resolved_model(data: dict[str, Any]) -> str | None` (module function); `_LOGIN` with word-bounded alternatives (P21).
- Produces (`providers/base.py`): `build_provider` passes `timeout_s=role.timeout_s if role.timeout_s is not None else DEFAULT_TIMEOUT_S` to `ClaudeCodeProvider`.
- Produces (`runner/env_turn.py`): `RESPONDER_TIMEOUT_S: Final = 120.0`; `responder_role` returns the resolved role with `timeout_s` set to it when the role has none.
- Produces (`tests/fixtures/fake_claude.py`): every log entry gains `"env"` (the `CLAUDECODE*`, `CLAUDE_CODE_*` and `MCP_TOOL_TIMEOUT` variables it saw); every result gains `"modelUsage": {"stub-sonnet-20260101": {...}}`; mode `login_error`; `$FAKE_CLAUDE_STRUCTURED`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provider_timeouts.py
"""The claude -p provider's timeouts, child environment and resolved model (Phase 7 spec sections
4 and 9), and the nested responder's own timeout."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.tools import TOOL_SPECS
from claude_bully.providers import claude_code
from claude_bully.providers.base import Message, ProviderError, build_provider
from claude_bully.providers.claude_code import (
    DEFAULT_MCP_TOOL_TIMEOUT_S,
    DEFAULT_TIMEOUT_S,
    MCP_TOOL_TIMEOUT_ENV,
    ClaudeCodeProvider,
    clean_child_env,
    resolved_model,
)
from claude_bully.providers.ledger import Ledger, LedgerProvider
from claude_bully.runner.env_turn import RESPONDER_TIMEOUT_S, responder_role
from tests.helpers import make_mcp_state

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], Path]:
    log = tmp_path / "fake_claude.log"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_TOOL_CALL", raising=False)
    return [sys.executable, str(FAKE)], log


def _entries(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_the_role_timeout_reaches_the_provider(tmp_path: Path) -> None:
    default = build_provider(RoleConfig(provider=ProviderKind.claude_code, model="m"), tmp_path)
    assert isinstance(default, ClaudeCodeProvider) and default.timeout_s == DEFAULT_TIMEOUT_S
    role = RoleConfig(provider=ProviderKind.claude_code, model="m", timeout_s=42.5)
    bounded = build_provider(role, tmp_path)
    assert isinstance(bounded, ClaudeCodeProvider) and bounded.timeout_s == 42.5
    assert bounded.mcp_tool_timeout_s == DEFAULT_MCP_TOOL_TIMEOUT_S


def test_the_child_environment_is_clean_and_carries_the_tool_timeout(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, log = fake_claude
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("UNRELATED_VAR", "kept")
    from claude_bully.environments.mcp_server import write_mcp_state

    mcp_dir = tmp_path / "mcp"
    write_mcp_state(mcp_dir / "env_state.json", make_mcp_state(tools={"web_search"}))
    provider = ClaudeCodeProvider(
        model="m", state_dir=tmp_path, command=command, mcp_state_dir=mcp_dir
    )
    provider.complete("c", "S", [Message(role="user", content="plain")])
    provider.complete("d", "S", [Message(role="user", content="tools")], tools=[TOOL_SPECS["web_search"]])
    plain, tools = _entries(log)
    for entry in (plain, tools):
        env = entry["env"]
        assert isinstance(env, dict)
        assert not [k for k in env if k.startswith(("CLAUDECODE", "CLAUDE_CODE_"))], env
    assert MCP_TOOL_TIMEOUT_ENV not in plain["env"]  # type: ignore[operator]
    assert tools["env"][MCP_TOOL_TIMEOUT_ENV] == "300000"  # type: ignore[index]
    # the environment the provider builds keeps everything else
    assert provider.child_env(serving_tools=False)["UNRELATED_VAR"] == "kept"
    assert "CLAUDECODE" not in clean_child_env() and clean_child_env()["UNRELATED_VAR"] == "kept"


def test_the_resolved_model_is_read_from_the_result(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, _ = fake_claude
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    out = provider.complete("c", "S", [Message(role="user", content="hi")])
    assert out.model == "sonnet" and out.resolved_model == "stub-sonnet-20260101"
    assert resolved_model({"modelUsage": {"x-1": {}, "y-2": {}}}) == "x-1"
    assert resolved_model({"model": "z-3"}) == "z-3"
    assert resolved_model({}) is None


def test_the_stream_reports_whether_a_thinking_block_was_seen(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    from claude_bully.environments.mcp_server import write_mcp_state

    mcp_dir = tmp_path / "mcp"
    write_mcp_state(mcp_dir / "env_state.json", make_mcp_state(tools={"web_search"}))
    provider = ClaudeCodeProvider(
        model="m", state_dir=tmp_path, command=command, mcp_state_dir=mcp_dir
    )
    assert provider.thinking_seen is None
    monkeypatch.setenv(
        "FAKE_CLAUDE_TOOL_CALL", json.dumps({"name": "web_search", "arguments": {"query": "f"}})
    )
    out = provider.complete("c", "S", [Message(role="user", content="go")], tools=[TOOL_SPECS["web_search"]])
    assert provider.thinking_seen is True  # the fake puts one before its first call
    assert out.reasoning_text is None and "PRIVATE" not in out.model_dump_json()
    monkeypatch.delenv("FAKE_CLAUDE_TOOL_CALL")
    provider.complete("d", "S", [Message(role="user", content="go")], tools=[TOOL_SPECS["web_search"]])
    assert provider.thinking_seen is False  # no call, no thinking block


def test_a_login_error_is_a_provider_error_naming_the_login(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "login_error")
    provider = ClaudeCodeProvider(model="m", state_dir=tmp_path, command=command)
    with pytest.raises(ProviderError, match="not logged in"):
        provider.complete("c", "S", [Message(role="user", content="hi")])


def test_the_structured_reply_can_be_scripted(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    schema = {"type": "object", "properties": {"k": {"type": "string"}}, "required": ["k"]}
    monkeypatch.setenv(
        "FAKE_CLAUDE_STRUCTURED", json.dumps([{"required": ["k"], "reply": {"k": "v"}}])
    )
    provider = ClaudeCodeProvider(model="m", state_dir=tmp_path, command=command)
    out = provider.complete("c", "S", [Message(role="user", content="hi")], json_schema=schema)
    assert json.loads(out.text) == {"k": "v"}
    other = {"type": "object", "properties": {"z": {}}, "required": ["z"]}
    out = provider.complete("d", "S", [Message(role="user", content="hi")], json_schema=other)
    assert json.loads(out.text) == {"echo": other}  # unscripted: the old echo


def test_the_responder_role_gets_the_nested_timeout() -> None:
    target = RoleConfig(provider=ProviderKind.claude_code, model="sonnet")
    bully = RoleConfig(provider=ProviderKind.claude_code, model="sonnet", timeout_s=30)
    assert responder_role("target", target=target, bully=bully).timeout_s == RESPONDER_TIMEOUT_S
    assert responder_role("bully", target=target, bully=bully).timeout_s == 30  # kept
    other = responder_role("haiku", target=target, bully=bully)
    assert (other.model, other.timeout_s) == ("haiku", 30)
    assert RESPONDER_TIMEOUT_S < DEFAULT_MCP_TOOL_TIMEOUT_S


def test_a_wrapped_provider_still_exposes_the_fact(tmp_path: Path) -> None:
    inner = ClaudeCodeProvider(model="m", state_dir=tmp_path, command=["claude"])
    wrapped = LedgerProvider(inner, Ledger(tmp_path / "l.jsonl"))
    assert wrapped.thinking_seen is None and wrapped.timeout_s == DEFAULT_TIMEOUT_S


def test_a_wrapped_timeout_writes_a_timeout_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one coupling between the wrapper and this provider no other test pins (P2): the
    timeout's message holds "timed out", which the ledger reads as ``status: timeout``."""

    def expired(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(claude_code.subprocess, "run", expired)
    ledger = Ledger(tmp_path / "l.jsonl")
    inner = ClaudeCodeProvider(model="m", state_dir=tmp_path, command=["claude"], timeout_s=1)
    with pytest.raises(ProviderError, match="timed out"):
        LedgerProvider(inner, ledger).complete(
            "run/c__t0/rep0/target", "S", [Message(role="user", content="hi")]
        )
    [line] = ledger.lines()
    assert (line.status, line.error, line.role) == ("timeout", "ProviderError", "target")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_provider_timeouts.py -q`
Expected: FAIL with `ImportError: cannot import name 'DEFAULT_MCP_TOOL_TIMEOUT_S'`.

- [ ] **Step 3: Implement**

In `claude_bully/config.py`, `RoleConfig`, after `reasoning`:

```python
    # claude_code only: seconds one call may take; None means the provider's default (600)
    timeout_s: float | None = None
```

In `claude_bully/providers/claude_code.py`, after `_NATIVE_BINARY`:

```python
DEFAULT_TIMEOUT_S: Final = 600.0
# Claude Code waits this long on one MCP tool call (its MCP_TOOL_TIMEOUT, in milliseconds); a
# nested responder must fail before it does, or the whole target turn is lost
DEFAULT_MCP_TOOL_TIMEOUT_S: Final = 300.0
MCP_TOOL_TIMEOUT_ENV: Final = "MCP_TOOL_TIMEOUT"
# a child claude -p must not learn it runs inside Claude Code: the variables it would read
STRIPPED_PREFIXES: Final = ("CLAUDECODE", "CLAUDE_CODE_")
# an error result that says the session is not logged in; every alternative is word-bounded
# so "catalog in use" or "blog index" is not read as one (P21)
_LOGIN: Final = re.compile(
    r"(?i)\bnot logged in\b|\blog ?in\b|\bauthenticat|\bapi key\b|\bunauthori[sz]ed\b|\bsign in\b"
)


def clean_child_env() -> dict[str, str]:
    """This process's environment less every variable that would tell a child ``claude -p`` it
    runs inside Claude Code (``STRIPPED_PREFIXES``; a nested call refuses to start otherwise).
    Every subprocess the harness or the doctor spawns runs under it."""
    return {k: v for k, v in os.environ.items() if not k.startswith(STRIPPED_PREFIXES)}


def resolved_model(data: dict[str, Any]) -> str | None:
    """The exact model a result reports: the first key of ``modelUsage``, else ``model``."""
    usage = data.get("modelUsage")
    if isinstance(usage, dict) and usage:
        return str(next(iter(usage)))
    model = data.get("model")
    return str(model) if isinstance(model, str) and model else None
```

Change `ClaudeCodeProvider.__init__` to:

```python
    def __init__(
        self,
        model: str,
        state_dir: Path,
        effort: str | None = None,
        command: list[str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        mcp_state_dir: Path | None = None,
        mcp_tool_timeout_s: float = DEFAULT_MCP_TOOL_TIMEOUT_S,
    ) -> None:
        self.model = model
        self.effort = effort
        self._command_arg = list(command) if command else None
        self._command: list[str] | None = None
        self.timeout_s = timeout_s
        self.mcp_tool_timeout_s = mcp_tool_timeout_s
        self.state_dir = state_dir
        # where mcp.json, env_state.json and tools.jsonl live; None means no sandbox tools
        self.mcp_state_dir = mcp_state_dir.resolve() if mcp_state_dir is not None else None
        # whether the newest stream carried a thinking block (the fact, never the text; doctor
        # check 4b); None before any stream
        self.thinking_seen: bool | None = None
        self._sessions_path = state_dir / "claude_code_sessions.json"
        self._cwd = state_dir / "cwd"
        self._sessions: dict[str, str] = self._load_sessions()

    def child_env(self, *, serving_tools: bool) -> dict[str, str]:
        """The environment a child ``claude -p`` runs in: ``clean_child_env()`` plus
        ``MCP_TOOL_TIMEOUT`` when the call serves tools."""
        env = clean_child_env()
        if serving_tools:
            env[MCP_TOOL_TIMEOUT_ENV] = str(int(self.mcp_tool_timeout_s * 1000))
        return env
```

In `parse_stream`, add `thinking = False` beside `interim: list[str] = []`; in the `elif event.get("type") == "assistant":` loop add a branch `elif block.get("type") == "thinking": thinking = True` (after the `tool_use` branch); before `completion = self._from_result(result, session)` add `self.thinking_seen = thinking`.

In `_from_result`, in the `if data.get("is_error"):` branch, after the rate-limit check add:

```python
            if _LOGIN.search(message):
                raise ProviderError(f"claude -p is not logged in: {message[:200]}")
```

and pass `resolved_model=resolved_model(data)` to the `Completion(...)` it builds.

In `complete`, add `env=self.child_env(serving_tools=bool(tools)),` to the `subprocess.run(...)` call (after `cwd=self._cwd,`).

In `claude_bully/providers/base.py`, `build_provider`, the `claude_code` branch: import `DEFAULT_TIMEOUT_S` inside the branch and pass `timeout_s=role.timeout_s if role.timeout_s is not None else DEFAULT_TIMEOUT_S,` to the `ClaudeCodeProvider(...)` call inside `_wrapped(...)` (Task 1 turned the branch's `return ClaudeCodeProvider(...)` into `return _wrapped(ClaudeCodeProvider(...))`; keep the wrapper, P1).

In `claude_bully/runner/env_turn.py`, after `GENERATED_CACHE_DIR`:

```python
# the nested responder's own timeout (Phase 7 spec section 9): under Claude Code's MCP tool
# timeout, so a slow responder costs one reply ("No reply."), never the target's turn
RESPONDER_TIMEOUT_S: Final = 120.0
```

and change `responder_role` to:

```python
def responder_role(responder_model: str, *, target: RoleConfig, bully: RoleConfig) -> RoleConfig:
    """The role a ``superior_self.responder_model`` names (spec conflict 11): ``"target"`` is the
    cell's target role (the same model family), ``"bully"`` the experiment's bully role, and any
    other string the bully's role running that model. A role with no ``timeout_s`` gets
    ``RESPONDER_TIMEOUT_S``, on both backends, so the MCP state carries it explicitly."""
    if responder_model == "target":
        role = target
    elif responder_model == "bully":
        role = bully
    else:
        role = bully.model_copy(update={"model": responder_model})
    if role.timeout_s is None:
        role = role.model_copy(update={"timeout_s": RESPONDER_TIMEOUT_S})
    return role
```

Add `RESPONDER_TIMEOUT_S` to `__all__`.

In `tests/fixtures/fake_claude.py`: add to the module docstring: "Every log entry carries ``env``: the ``CLAUDECODE*``, ``CLAUDE_CODE_*`` and ``MCP_TOOL_TIMEOUT`` variables the fake saw. Every result carries ``modelUsage`` keyed by an invented model id. ``login_error`` is an error result whose text says the session is not logged in. ``$FAKE_CLAUDE_STRUCTURED`` is a JSON list of ``{"required": [...], "reply": {...}}``: a ``--json-schema`` call whose schema's ``required`` list equals one entry's gets that reply as its structured output, else the echo." Then:

- after `THINKING = ...` add `RESOLVED_MODEL = "stub-sonnet-20260101"` and `_ENV_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_", "MCP_TOOL_TIMEOUT")`;
- in `main`, the log entry gains `"env": {k: v for k, v in os.environ.items() if k.startswith(_ENV_PREFIXES)}`;
- after the `ratelimit` branch add:

```python
    if mode == "login_error":
        error = {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "result": "Not logged in. Please run /login to authenticate.",
        }
        if stream:
            print(json.dumps({"type": "system", "subtype": "init", "session_id": session}))
        print(json.dumps(error))
        return 0
```

(add `"login_error"` beside `"ratelimit"` in the `serves = mode in (...)` tuple's complement: the line stays `serves = mode in ("ok", "stream_malformed", "stream_truncated")`);
- in the `out` result dict add `"modelUsage": {RESOLVED_MODEL: {"inputTokens": 10, "outputTokens": 5}}`;
- replace the `if "--json-schema" in argv:` block with:

```python
    if "--json-schema" in argv:
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        scripted = os.environ.get("FAKE_CLAUDE_STRUCTURED")
        replies = json.loads(scripted) if scripted else []
        wanted = sorted(schema.get("required", []))
        match = next((r["reply"] for r in replies if sorted(r["required"]) == wanted), None)
        out["structured_output"] = match if match is not None else {"echo": schema}
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_provider_timeouts.py tests/test_providers_claude_code.py tests/test_runner_env.py tests/test_sanctuary.py tests/test_ledger.py -q`
Expected: PASS. `test_a_claude_p_run_records_the_servers_authority_calls` still asserts `state.responder == exp.targets[0]`: update that assertion in `tests/test_runner_env.py` to `state.responder == exp.targets[0].model_copy(update={"timeout_s": RESPONDER_TIMEOUT_S})` (import `RESPONDER_TIMEOUT_S` from `claude_bully.runner.env_turn`); it is the one existing assertion the responder timeout changes.

- [ ] **Step 5: Docs sync**

- `HANDOFF.md`: Progress gains "Phase 7a Task 3: provider timeouts, the clean child environment, resolved_model, the thinking-block fact (BASE..HEAD)"; "For Phase 7" item "The nested `claude -p` responder timeout" becomes "closed in 7a Task 3: `RESPONDER_TIMEOUT_S` 120 on the responder role, `MCP_TOOL_TIMEOUT` 300 s on the outer call, `CLAUDECODE*` stripped from the child; `doctor --live` check 5 (Task 4) measures it".
- `docs/00-RECONCILED.md`: section A `RoleConfig` row gains "`timeout_s` (Phase 7a: claude_code only; None means 600 s; a responder role gets 120 s)"; section H: "`Completion.resolved_model` read from the result's `modelUsage`"; section G14 gains one sentence: "Phase 7a's `doctor --live` check 4b reports whether a `stream-json` run carried a thinking block (`ClaudeCodeProvider.thinking_seen`), the fact Phase 6 designs on."
- The spec's "As planned": the Task 3 rulings (the responder timeout set in `responder_role`; `child_env`; `resolved_model`; `thinking_seen` on the provider, not the completion).

- [ ] **Step 6: Gate and commit**

Run: the gate.
Expected: PASS, 0 warnings.

```bash
git add claude_bully/config.py claude_bully/providers/base.py claude_bully/providers/claude_code.py claude_bully/runner/env_turn.py tests/fixtures/fake_claude.py tests/test_provider_timeouts.py tests/test_runner_env.py HANDOFF.md docs/00-RECONCILED.md docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md
git commit -m "feat: per-role timeouts, a clean child environment and the resolved model for claude -p

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
