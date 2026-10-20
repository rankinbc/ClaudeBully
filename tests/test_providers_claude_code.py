import json
import sys
from pathlib import Path

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.providers.base import Message, ProviderError, RateLimitError, build_provider
from claude_bully.providers.claude_code import ClaudeCodeProvider

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
