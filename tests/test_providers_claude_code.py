import json
import shutil
import sys
from pathlib import Path

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.mcp_server import read_mcp_state, write_mcp_state
from claude_bully.environments.tools import TOOL_SPECS
from claude_bully.providers.base import (
    Message,
    ProviderError,
    RateLimitError,
    ToolCallRequest,
    build_provider,
)
from claude_bully.providers.claude_code import (
    CLAUDE_ENV,
    ClaudeCodeProvider,
    resolve_claude_command,
)
from tests.helpers import make_mcp_state

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], Path]:
    log = tmp_path / "fake_claude.log"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    return [sys.executable, str(FAKE)], log


def _read_log(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_first_call_uses_session_id_then_resume(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    first = p.complete("conv1", "SYS", [Message(role="user", content="hello")])
    p.complete(
        "conv1",
        "SYS",
        [
            Message(role="user", content="hello"),
            Message(role="assistant", content="x"),
            Message(role="user", content="again"),
        ],
    )
    calls = _read_log(log)
    argv0 = list(map(str, calls[0]["argv"]))  # type: ignore[call-overload]
    argv1 = list(map(str, calls[1]["argv"]))  # type: ignore[call-overload]
    assert "--session-id" in argv0 and "--resume" not in argv0
    assert "--resume" in argv1 and "--session-id" not in argv1
    assert argv1[argv1.index("--resume") + 1] == argv0[argv0.index("--session-id") + 1]
    assert calls[1]["stdin"] == "again"
    assert first.raw_session_ref == argv0[argv0.index("--session-id") + 1]
    assert first.text == "reply to: hello"
    assert first.cost_usd == 0.01 and first.usage.output_tokens == 5


def test_session_map_persists_across_instances(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command).complete(
        "conv1", "SYS", [Message(role="user", content="a")]
    )
    ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command).complete(
        "conv1",
        "SYS",
        [
            Message(role="user", content="a"),
            Message(role="assistant", content="b"),
            Message(role="user", content="c"),
        ],
    )
    argv1 = list(map(str, _read_log(log)[1]["argv"]))  # type: ignore[call-overload]
    assert "--resume" in argv1


def test_reset_session_starts_fresh_and_replays_transcript(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    p.complete("conv1", "SYS", [Message(role="user", content="first")])
    p.reset_session("conv1")
    assert p.session_ref("conv1") is None
    p.complete(
        "conv1",
        "SYS",
        [
            Message(role="user", content="first"),
            Message(role="assistant", content="r1"),
            Message(role="user", content="second"),
        ],
    )
    calls = _read_log(log)
    argv0 = list(map(str, calls[0]["argv"]))  # type: ignore[call-overload]
    argv1 = list(map(str, calls[1]["argv"]))  # type: ignore[call-overload]
    assert "--session-id" in argv1 and "--resume" not in argv1
    assert argv1[argv1.index("--session-id") + 1] != argv0[argv0.index("--session-id") + 1]
    stdin1 = str(calls[1]["stdin"])
    assert "[Earlier in this conversation]" in stdin1 and "r1" in stdin1
    assert stdin1.endswith("second")


def test_isolation_flags_exact(tmp_path: Path, fake_claude: tuple[list[str], Path]) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, effort="low", command=command)
    p.complete("c", "SYS", [Message(role="user", content="hi")])
    argv = list(map(str, _read_log(log)[0]["argv"]))  # type: ignore[call-overload]
    for pair in [
        ("--output-format", "json"),
        ("--setting-sources", ""),
        ("--tools", ""),
        ("--system-prompt", "SYS"),
        ("--model", "sonnet"),
        ("--effort", "low"),
    ]:
        i = argv.index(pair[0])
        assert argv[i + 1] == pair[1], pair
    assert "-p" in argv
    assert "--strict-mcp-config" in argv
    assert "--exclude-dynamic-system-prompt-sections" in argv


def test_cwd_is_clean_dir_under_state(tmp_path: Path, fake_claude: tuple[list[str], Path]) -> None:
    command, _ = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert (tmp_path / "cwd").is_dir()


def test_rate_limit_raises(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "ratelimit")
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    with pytest.raises(RateLimitError):
        p.complete("c", "SYS", [Message(role="user", content="hi")])


def test_crash_raises_provider_error(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    with pytest.raises(ProviderError):
        p.complete("c", "SYS", [Message(role="user", content="hi")])


def test_json_schema_passes_flag_and_reads_structured_output(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    schema = {"type": "object", "properties": {"k": {"type": "string"}}}
    out = p.complete("c", "SYS", [Message(role="user", content="hi")], json_schema=schema)
    argv = list(map(str, _read_log(log)[0]["argv"]))  # type: ignore[call-overload]
    assert json.loads(argv[argv.index("--json-schema") + 1]) == schema
    assert json.loads(out.text) == {"echo": schema}


def test_build_provider_claude_code(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.claude_code, model="sonnet", effort="high")
    p = build_provider(role, tmp_path)
    assert isinstance(p, ClaudeCodeProvider) and p.name == "claude_code"


# ------------------------------------------------------------------ MCP sandbox tools

TOOLS = [TOOL_SPECS["web_search"], TOOL_SPECS["fetch"], TOOL_SPECS["ls"]]
ALLOWED = "mcp__workspace__web_search,mcp__workspace__fetch,mcp__workspace__ls"
MEMO = "/srv/authority/memos/parking-q3.txt"
ABOUT = "https://pennetferry.example/about"


def _user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


def _mcp_provider(
    tmp_path: Path, command: list[str], *, turn: int = 1, unlock: UnlockState | None = None
) -> tuple[ClaudeCodeProvider, Path]:
    """A provider with MCP on, and the state file the runtime would have written for ``turn``."""
    mcp_dir = tmp_path / "mcp"
    write_mcp_state(
        mcp_dir / "env_state.json",
        make_mcp_state(tools={"web_search", "fetch", "ls"}, turn=turn, unlock=unlock),
    )
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=command, mcp_state_dir=mcp_dir
    )
    return provider, mcp_dir


def _tool_call(monkeypatch: pytest.MonkeyPatch, *calls: dict[str, object]) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_TOOL_CALL", json.dumps(list(calls)))


def _argv(log: Path, index: int = 0) -> list[str]:
    return [str(a) for a in _read_log(log)[index]["argv"]]  # type: ignore[attr-defined]


def test_calls_without_tools_keep_the_exact_old_argv(tmp_path: Path) -> None:
    plain = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    with_mcp = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    for provider in (plain, with_mcp):
        for tools in (None, []):
            argv, session, resumed = provider.build_args("c", "SYS", None, tools)
            assert not resumed
            assert argv == [
                "claude",
                "-p",
                "--output-format",
                "json",
                "--model",
                "sonnet",
                "--setting-sources",
                "",
                "--strict-mcp-config",
                "--tools",
                "",
                "--system-prompt",
                "SYS",
                "--exclude-dynamic-system-prompt-sections",
                "--session-id",
                session,
            ]


def test_a_call_without_tools_does_not_touch_the_mcp_dir(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    out = provider.complete("c", "SYS", _user("hi"))
    assert out.tool_calls == [] and out.text == "reply to: hi"
    argv = _argv(log)
    assert "--mcp-config" not in argv and "--allowedTools" not in argv
    assert not (mcp_dir / "mcp.json").exists()


def test_tools_write_mcp_json_and_pass_the_flags_in_enabled_order(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    provider.complete("c", "SYS", _user("hi"), tools=TOOLS)

    argv = _argv(log)
    config_path = Path(argv[argv.index("--mcp-config") + 1])
    assert config_path.is_absolute() and config_path == (mcp_dir / "mcp.json").resolve()
    assert argv[argv.index("--allowedTools") + 1] == ALLOWED
    assert argv[argv.index("--tools") + 1] == ""  # built-in tools stay off
    assert "--strict-mcp-config" in argv
    # each variadic flag is closed by the flag after it, never by the end of the argv
    assert argv[argv.index("--mcp-config") + 2].startswith("--")
    assert argv[argv.index("--allowedTools") + 2].startswith("--")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert list(config) == ["mcpServers"] and list(config["mcpServers"]) == ["workspace"]
    server = config["mcpServers"]["workspace"]
    assert Path(server["command"]) == Path(sys.executable)
    # a launcher script beside mcp.json, so the package name is not spelled out in the config
    launcher, flag, state_arg = server["args"]
    assert flag == "--state"
    assert (
        Path(launcher) == (mcp_dir / "workspace_server.py").resolve() and Path(launcher).is_file()
    )
    assert Path(state_arg).is_absolute() and Path(state_arg) == mcp_dir.resolve()
    assert "\\" not in state_arg and "\\" not in launcher and "\\" not in server["command"]


def test_the_fake_client_sees_only_the_enabled_tools(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    provider.complete("c", "SYS", _user("hi"), tools=TOOLS)
    assert _read_log(log)[0]["mcp"]["listed"] == ["web_search", "fetch", "ls"]  # type: ignore[index]


def test_pre_executed_calls_come_back_with_their_results(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})
    out = provider.complete("c", "SYS", _user("look it up"), tools=TOOLS)

    [call] = out.tool_calls
    assert call.executed is True
    assert (call.id, call.name, call.args) == ("mcp-1-1", "fetch", {"url": ABOUT})
    assert call.result_text is not None and "operates the passenger crossing" in call.result_text
    assert out.text.endswith(call.result_text)  # the client really got it from the server
    record = json.loads((mcp_dir / "tools.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["result_text"] == call.result_text and record["status"] == "200"


def test_several_calls_come_back_in_the_order_they_ran(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    _tool_call(
        monkeypatch,
        {"name": "web_search", "arguments": {"query": "ferry"}},
        {"name": "fetch", "arguments": {"url": ABOUT}},
        {"name": "ls", "arguments": {"path": "journal"}},
    )
    out = provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert [(c.id, c.name) for c in out.tool_calls] == [
        ("mcp-1-1", "web_search"),
        ("mcp-1-2", "fetch"),
        ("mcp-1-3", "ls"),
    ]
    assert all(isinstance(c, ToolCallRequest) and c.executed for c in out.tool_calls)


def test_only_lines_added_during_the_call_are_returned(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, log = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    stale = {"id": "mcp-0-1", "tool": "fetch", "args": {}, "result_text": "old"}
    (mcp_dir / "tools.jsonl").write_text(json.dumps(stale) + "\n", encoding="utf-8")
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})

    first = provider.complete("c", "SYS", _user("one"), tools=TOOLS)
    second = provider.complete(
        "c",
        "SYS",
        [*_user("one"), Message(role="assistant", content="r"), *_user("two")],
        tools=TOOLS,
    )
    assert [c.id for c in first.tool_calls] == ["mcp-1-1"]
    assert [c.id for c in second.tool_calls] == ["mcp-1-2"]
    assert "--resume" in _argv(log, 1) and "--mcp-config" in _argv(log, 1)  # every call


def test_the_state_written_before_the_call_is_what_the_server_reads(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command, turn=1)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": MEMO}})

    locked = provider.complete("c", "SYS", _user("one"), tools=TOOLS)
    [refused] = locked.tool_calls
    assert refused.result_text == "HTTP 403 Forbidden" and refused.id == "mcp-1-1"

    # the runtime unlocks the memo and moves to turn 2 before the next call
    path = mcp_dir / "env_state.json"
    state = read_mcp_state(path)
    state.unlock.docs_unlocked.add("ops-memo-parking")
    state.turn = 2
    write_mcp_state(path, state)

    opened = provider.complete(
        "c",
        "SYS",
        [*_user("one"), Message(role="assistant", content="r"), *_user("two")],
        tools=TOOLS,
    )
    [served] = opened.tool_calls
    assert served.id == "mcp-2-1"
    assert served.result_text is not None and "The east lot is closed" in served.result_text


def test_a_tool_outside_the_enabled_list_is_refused_by_the_client(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})
    out = provider.complete("c", "SYS", _user("hi"), tools=[TOOL_SPECS["web_search"]])
    assert out.tool_calls == [] and "permission denied: fetch" in out.text
    assert not (mcp_dir / "tools.jsonl").exists()


def test_tools_without_an_mcp_state_dir_fail_loudly(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    with pytest.raises(ProviderError, match="mcp_state_dir"):
        provider.complete("c", "SYS", _user("hi"), tools=TOOLS)
    assert not log.exists()


def test_build_provider_opts_in_to_mcp_for_claude_code_only(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.claude_code, model="sonnet")
    default = build_provider(role, tmp_path)
    assert isinstance(default, ClaudeCodeProvider) and default.mcp_state_dir is None
    opted = build_provider(role, tmp_path, with_mcp=True)
    assert isinstance(opted, ClaudeCodeProvider)
    assert opted.mcp_state_dir == (tmp_path / "mcp").resolve()
    stub_role = RoleConfig(provider=ProviderKind.stub, model="stub")
    assert build_provider(stub_role, tmp_path, with_mcp=True).name == "stub"


# ------------------------------------------------- nothing target-visible names the experiment


def test_nothing_the_target_can_see_names_the_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the interpreter's own path is whatever the machine has; everything else is ours to keep clean
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    provider._write_mcp_config()
    argv, _, _ = provider.build_args("c", "SYS", None, TOOLS)
    config_text = (tmp_path / "mcp" / "mcp.json").read_text(encoding="utf-8")
    for text in (" ".join(argv), config_text):
        assert "bully" not in text.lower(), text
    assert "mcp__workspace__web_search" in argv[argv.index("--allowedTools") + 1]


# --------------------------------------------------------- reading tools.jsonl safely


def test_a_half_written_last_line_is_ignored_even_mid_character(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    (tmp_path / "mcp").mkdir()
    done = {"id": "mcp-1-1", "tool": "fetch", "args": {}, "result_text": "caf\u00e9"}
    whole = json.dumps(done, ensure_ascii=False).encode("utf-8") + b"\n"
    tail = (
        b'{"id": "mcp-1-2", "tool": "fetch", "args": {}, "result_text": "caf'
        + "\u00e9".encode()[:1]
    )
    (tmp_path / "mcp" / "tools.jsonl").write_bytes(whole + tail)
    with pytest.raises(UnicodeDecodeError):
        tail.decode("utf-8")  # the fixture really is a mid-character tail

    [call] = provider._new_tool_calls(0)
    assert (call.id, call.result_text) == ("mcp-1-1", "caf\u00e9")


def test_a_complete_but_undecodable_line_is_a_provider_error(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    (tmp_path / "mcp").mkdir()
    (tmp_path / "mcp" / "tools.jsonl").write_bytes(b'{"id": "\xff\xfe"}\n')
    with pytest.raises(ProviderError, match="malformed line"):
        provider._new_tool_calls(0)


def test_blank_pieces_between_records_are_skipped(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    (tmp_path / "mcp").mkdir()
    record = json.dumps({"id": "mcp-1-1", "tool": "ls", "args": {}, "result_text": "x"})
    (tmp_path / "mcp" / "tools.jsonl").write_bytes(f"\n{record}\n\n".encode())
    assert [c.id for c in provider._new_tool_calls(0)] == ["mcp-1-1"]


# --------------------------------------------------------------- finding the claude binary


def _npm_layout(tmp_path: Path, *, native_at: str | None) -> Path:
    """An npm global install: ``<prefix>/claude.cmd`` plus, optionally, the native binary."""
    prefix = tmp_path / "npm"
    shim_dir = prefix / "bin"
    shim_dir.mkdir(parents=True)
    shim = shim_dir / "claude.cmd"
    shim.write_text("@echo off\n", encoding="utf-8")
    if native_at is not None:
        base = shim_dir if native_at == "beside" else prefix
        exe = base / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"MZ")
    return shim


def _which(monkeypatch: pytest.MonkeyPatch, found: str | Path | None) -> None:
    monkeypatch.setattr(
        shutil, "which", lambda name, *a, **k: None if found is None else str(found)
    )


@pytest.fixture(autouse=False)
def no_claude_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CLAUDE_ENV, raising=False)


def test_an_explicit_command_wins_over_everything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_ENV, "/from/env")
    _which(monkeypatch, "/from/path")
    explicit = ["python", "fake.py"]
    resolved = resolve_claude_command(explicit)
    assert resolved == ["python", "fake.py"] and resolved is not explicit


def test_the_env_var_is_one_path_and_is_not_split(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_ENV, "C:/Program Files/Claude Code/claude.exe")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: pytest.fail("PATH must not be searched"))
    assert resolve_claude_command(None) == ["C:/Program Files/Claude Code/claude.exe"]
    assert resolve_claude_command([]) == ["C:/Program Files/Claude Code/claude.exe"]


def test_an_empty_env_var_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLAUDE_ENV, "")
    _which(monkeypatch, "/usr/local/bin/claude")
    assert resolve_claude_command(None) == ["/usr/local/bin/claude"]


def test_a_real_executable_on_path_is_used_as_is(
    monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    for found in ("/usr/local/bin/claude", "C:/tools/claude.exe", "/opt/claude/claude"):
        _which(monkeypatch, found)
        assert resolve_claude_command(None) == [found]


@pytest.mark.parametrize("native_at", ["beside", "above"])
def test_a_cmd_shim_resolves_to_the_native_binary_it_wraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None, native_at: str
) -> None:
    shim = _npm_layout(tmp_path, native_at=native_at)
    _which(monkeypatch, shim)
    [command] = resolve_claude_command(None)
    assert Path(command).name == "claude.exe" and Path(command).is_file()
    assert "claude-code" in Path(command).parts
    expected = (shim.parent if native_at == "beside" else shim.parent.parent) / "node_modules"
    assert Path(command).is_relative_to(expected)


@pytest.mark.parametrize("name", ["claude.bat", "claude.ps1", "claude.CMD"])
def test_every_script_shim_suffix_is_treated_as_a_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None, name: str
) -> None:
    shim = _npm_layout(tmp_path, native_at="beside").with_name(name)
    shim.write_text("x", encoding="utf-8")
    _which(monkeypatch, shim)
    [command] = resolve_claude_command(None)
    assert Path(command).name == "claude.exe"


def test_the_beside_binary_is_preferred_to_the_one_above(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    shim = _npm_layout(tmp_path, native_at="beside")
    above = shim.parent.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin"
    above.mkdir(parents=True)
    (above / "claude.exe").write_bytes(b"MZ")
    _which(monkeypatch, shim)
    [command] = resolve_claude_command(None)
    assert Path(command).is_relative_to(shim.parent / "node_modules")


def test_a_shim_with_no_native_binary_is_an_error_that_says_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    shim = _npm_layout(tmp_path, native_at=None)
    _which(monkeypatch, shim)
    with pytest.raises(ProviderError) as info:
        resolve_claude_command(None)
    message = str(info.value)
    assert str(shim) in message and CLAUDE_ENV in message


def test_claude_not_found_is_an_error_that_says_what_to_do(
    monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    _which(monkeypatch, None)
    with pytest.raises(ProviderError) as info:
        resolve_claude_command(None)
    assert CLAUDE_ENV in str(info.value) and "PATH" in str(info.value)


def test_the_provider_resolves_lazily_so_building_one_never_needs_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    _which(monkeypatch, None)
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path)  # does not raise
    with pytest.raises(ProviderError, match=CLAUDE_ENV):
        provider.complete("c", "SYS", _user("hi"))
    monkeypatch.setenv(CLAUDE_ENV, "/somewhere/claude")
    assert provider.command == ["/somewhere/claude"]
    argv, _, _ = provider.build_args("c", "SYS", None)
    assert argv[0] == "/somewhere/claude"


def test_the_provider_keeps_an_explicit_command_untouched(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["a", "b"])
    assert provider.command == ["a", "b"]


def test_role_command_reaches_the_provider(tmp_path: Path) -> None:
    default = RoleConfig(provider=ProviderKind.claude_code, model="sonnet")
    assert default.command is None
    role = RoleConfig(
        provider=ProviderKind.claude_code, model="sonnet", command=["C:/x/claude.exe", "--flag"]
    )
    provider = build_provider(role, tmp_path)
    assert isinstance(provider, ClaudeCodeProvider)
    assert provider.command == ["C:/x/claude.exe", "--flag"]
