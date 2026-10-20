import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_bully import cli
from claude_bully.runner.runner import RateLimitExit

FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "stub_smoke.yaml"
runner = CliRunner()


def test_list_strategies_lists_34() -> None:
    result = runner.invoke(cli.app, ["list-strategies", "--names"])
    assert result.exit_code == 0, result.output
    names = [ln.strip() for ln in result.output.splitlines() if ln.strip()]
    assert len(names) == 34
    assert {"grader", "captor", "rescue", "polite_control", "ghost"} <= set(names)
    table = runner.invoke(cli.app, ["list-strategies"])
    assert table.exit_code == 0 and "axis" in table.output.lower()


def test_run_dry_run_prints_cells_without_writing(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "grader__t0" in result.output and "control__t0__s0__r0" in result.output
    assert not (tmp_path / "stub_smoke").exists()


def test_run_and_analyze_stub_config(tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "5" in result.output and "complete" in result.output.lower()
    analyze = runner.invoke(
        cli.app, ["analyze", "stub_smoke", "--runs-root", str(tmp_path), "--no-judge"]
    )
    assert analyze.exit_code == 0, analyze.output
    assert (tmp_path / "stub_smoke" / "analysis" / "results.md").exists()
    show = runner.invoke(
        cli.app, ["show", "stub_smoke/captor_s2__t0", "--runs-root", str(tmp_path)]
    )
    assert show.exit_code == 0, show.output
    assert "post_reveal" in show.output and "reveal" in show.output.lower()
    readme = tmp_path / "README.md"
    readme.write_text("# x\n", encoding="utf-8")
    rr = runner.invoke(
        cli.app,
        ["readme-results", "stub_smoke", "--runs-root", str(tmp_path), "--readme", str(readme)],
    )
    assert rr.exit_code == 0, rr.output
    text = readme.read_text(encoding="utf-8")
    assert "<!-- results:start -->" in text and "## Leaderboard" in text
    promote = runner.invoke(
        cli.app,
        [
            "promote",
            "stub_smoke",
            "--runs-root",
            str(tmp_path),
            "--results-root",
            str(tmp_path / "results"),
        ],
    )
    assert promote.exit_code == 0, promote.output
    assert (tmp_path / "results" / "stub_smoke" / "run.json").exists()
    from_results = runner.invoke(
        cli.app,
        [
            "readme-results",
            "stub_smoke",
            "--from-results",
            "--results-root",
            str(tmp_path / "results"),
            "--readme",
            str(readme),
        ],
    )
    assert from_results.exit_code == 0, from_results.output


def test_run_exits_3_on_rate_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise RateLimitExit("usage limit", retry_after_s=60)

    monkeypatch.setattr(cli, "run_experiment", boom)
    result = runner.invoke(cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path)])
    assert result.exit_code == 3
    assert "60" in result.output and "retry" in result.output.lower()


def test_analyze_exits_3_on_rate_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise RateLimitExit("judge usage limit", retry_after_s=90)

    monkeypatch.setattr(cli, "analyze_run", boom)
    result = runner.invoke(cli.app, ["analyze", "x", "--runs-root", str(tmp_path)])
    assert result.exit_code == 3 and "90" in result.output


def test_doctor_offline_passes() -> None:
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    low = result.output.lower()
    assert "stub round trip: ok" in low
    assert "claude" in low
    assert "anthropic_api_key" in low and "sk-" not in low


def test_doctor_offline_has_no_mcp_check_and_never_builds_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline doctor must not call claude")

    monkeypatch.setattr(cli, "ClaudeCodeProvider", explode)
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "mcp" not in result.output.lower()
    assert "tools.jsonl" not in result.output.lower()


class _FakeLiveClaude:
    """Stands in for ClaudeCodeProvider: answers the plain ping, serves one MCP call or none."""

    instances: list["_FakeLiveClaude"] = []
    serve_a_call = True

    def __init__(self, model: str, state_dir: Path, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls: list[dict[str, object]] = []
        self.state_seen: str | None = None
        type(self).instances.append(self)

    def complete(self, conversation_id: str, system: str, messages: list[object], **kw: object):  # type: ignore[no-untyped-def]
        from claude_bully.providers.base import Completion
        from claude_bully.records import Usage

        self.calls.append({"tools": kw.get("tools")})
        mcp_dir = self.kwargs.get("mcp_state_dir")
        if kw.get("tools"):
            assert isinstance(mcp_dir, Path)
            # the state file must be written before the call
            self.state_seen = (mcp_dir / "env_state.json").read_text(encoding="utf-8")
            if self.serve_a_call:
                record = {"id": "mcp-1-1", "tool": "web_search", "status": "200"}
                (mcp_dir / "tools.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
        return Completion(
            text="pong", usage=Usage(), cost_usd=0.0, backend="claude_code", model="sonnet"
        )


def _live_doctor(monkeypatch: pytest.MonkeyPatch, *, serve_a_call: bool) -> str:
    _FakeLiveClaude.instances = []
    _FakeLiveClaude.serve_a_call = serve_a_call
    monkeypatch.setattr(cli, "ClaudeCodeProvider", _FakeLiveClaude)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="9.9.9 (Claude Code)", stderr=""),
    )
    result = runner.invoke(cli.app, ["doctor", "--live"])
    assert result.exit_code == 0, result.output
    return result.output.lower()


def test_doctor_live_adds_an_mcp_round_trip_on_the_mini_world(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _live_doctor(monkeypatch, serve_a_call=True)
    assert "claude -p live call" in output  # the original check is still there
    assert "mcp" in output and "tools.jsonl line appeared: yes" in output
    mcp_provider = next(p for p in _FakeLiveClaude.instances if p.kwargs.get("mcp_state_dir"))
    assert mcp_provider.state_seen is not None and '"world": "mini"' in mcp_provider.state_seen
    [call] = [c for c in mcp_provider.calls if c["tools"]]
    assert [t.name for t in call["tools"]] == ["web_search"]  # type: ignore[attr-defined]


def test_doctor_live_says_so_when_no_tools_jsonl_line_appeared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _live_doctor(monkeypatch, serve_a_call=False)
    assert "tools.jsonl line appeared: no" in output
