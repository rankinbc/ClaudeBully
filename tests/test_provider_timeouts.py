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
    provider.complete(
        "d", "S", [Message(role="user", content="tools")], tools=[TOOL_SPECS["web_search"]]
    )
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
    out = provider.complete(
        "c", "S", [Message(role="user", content="go")], tools=[TOOL_SPECS["web_search"]]
    )
    assert provider.thinking_seen is True  # the fake puts one before its first call
    assert out.reasoning_text is None and "PRIVATE" not in out.model_dump_json()
    monkeypatch.delenv("FAKE_CLAUDE_TOOL_CALL")
    provider.complete(
        "d", "S", [Message(role="user", content="go")], tools=[TOOL_SPECS["web_search"]]
    )
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
    timeout is a ``ProviderTimeoutError``, which the ledger reads as ``status: timeout``, and its
    message still says "timed out"."""

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
    assert (line.status, line.error, line.role) == ("timeout", "ProviderTimeoutError", "target")
