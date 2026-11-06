import io
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_bully import cli
from claude_bully.cli import utf8_stdout
from claude_bully.enums import Speaker
from claude_bully.providers.base import ProviderError
from claude_bully.runner.runner import RateLimitExit
from claude_bully.runner.store import RunStore
from tests.helpers import conversation, turn

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


def test_replay_prints_a_plain_conversation(stub_run: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["replay", f"{stub_run.name}/captor_s2__t0", "--runs-root", str(stub_run.parent)],
    )
    assert result.exit_code == 0, result.output
    assert "post_reveal" in result.output and "reveal" in result.output.lower()
    assert "[stub]" in result.output  # text in square brackets is not swallowed as markup
    assert "TRIGGER" not in result.output and "UNLOCK" not in result.output


def test_replay_of_an_environment_run_shows_a_tool_call_and_an_unlock(stub_env_run: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["replay", f"{stub_env_run.name}/env_grader__t0", "--runs-root", str(stub_env_run.parent)],
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert any(ln.lstrip().startswith("web_search") and "(surface)" in ln for ln in lines)
    assert 'TRIGGER world_question "Who is Ilsabet Orrin?"' in result.output
    assert "UNLOCK first_crumb -> [ops-memo-parking]" in result.output
    assert 'DISCOVERY ops-memo-parking (seam) "Staff parking, third quarter"' in result.output


def test_show_is_an_alias_of_replay_with_the_same_output(stub_env_run: Path) -> None:
    args = [f"{stub_env_run.name}/env_grader__t0", "--runs-root", str(stub_env_run.parent)]
    replayed = runner.invoke(cli.app, ["replay", *args])
    shown = runner.invoke(cli.app, ["show", *args])
    assert replayed.exit_code == 0 and shown.exit_code == 0, shown.output
    assert shown.output == replayed.output and "web_search" in shown.output
    helped = runner.invoke(cli.app, ["--help"]).output
    assert "replay" in helped and "show" in helped


def test_replay_reads_the_world_from_the_run_not_from_the_world_files(
    stub_env_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_worlds(*args: object, **kwargs: object) -> object:
        raise AssertionError("a replay must not load a world from disk")

    monkeypatch.setattr("claude_bully.environments.world.load_world", no_worlds)
    result = runner.invoke(
        cli.app,
        ["replay", f"{stub_env_run.name}/env_grader__t0", "--runs-root", str(stub_env_run.parent)],
    )
    assert result.exit_code == 0, result.output
    assert '"Staff parking, third quarter"' in result.output


def test_replay_picks_a_repetition_and_names_what_is_missing(stub_env_run: Path) -> None:
    root = str(stub_env_run.parent)
    target = f"{stub_env_run.name}/env_grader__t0"
    no_rep = runner.invoke(cli.app, ["replay", target, "--rep", "5", "--runs-root", root])
    assert no_rep.exit_code != 0 and "rep 5" in " ".join(no_rep.output.split())
    no_cell = runner.invoke(cli.app, ["replay", f"{stub_env_run.name}/nope", "--runs-root", root])
    assert no_cell.exit_code != 0 and "nope" in " ".join(no_cell.output.split())
    bare = runner.invoke(cli.app, ["replay", stub_env_run.name, "--runs-root", root])
    assert bare.exit_code != 0 and "RUN_ID/CELL_ID" in " ".join(bare.output.split())


UNICODE_REPLY = "yes → done ✓ 漢字 🙂"


def _unicode_run(root: Path) -> str:
    """A one-exchange run whose reply has characters cp1252 cannot encode; returns RUN/CELL."""
    store = RunStore(root, "uni")
    conv = conversation(
        [turn(0, Speaker.bully, "go"), turn(1, Speaker.target, UNICODE_REPLY)], cell_id="c"
    )
    store.write_conversation("c", 0, conv)
    for t in conv.turns:
        store.append_turn("c", 0, t)
    return "uni/c"


@pytest.mark.parametrize("command", ["replay", "show"])
def test_replay_writes_utf8_when_stdout_is_cp1252(tmp_path: Path, command: str) -> None:
    """Redirected output on Windows is cp1252; the replay must not crash on what the target said."""
    target = _unicode_run(tmp_path)
    cp1252 = CliRunner(charset="cp1252")
    result = cp1252.invoke(cli.app, [command, target, "--runs-root", str(tmp_path)])
    assert result.exit_code == 0, repr(result.exception)
    assert UNICODE_REPLY in result.stdout_bytes.decode("utf-8")


def test_the_stdout_encoding_is_restored_after_a_replay() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    with utf8_stdout(stream):
        assert stream.encoding == "utf-8" and stream.errors == "replace"
        stream.write(UNICODE_REPLY)
    assert stream.encoding == "cp1252" and stream.errors == "strict"
    assert stream.buffer.getvalue().decode("utf-8") == UNICODE_REPLY  # type: ignore[attr-defined]


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


def _fake_claude_on_path(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Resolve claude to a stand-in and record the argv ``doctor`` runs; the real one never runs."""
    ran: list[list[str]] = []

    def fake_run(
        argv: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="9.9.9 (Claude Code)", stderr="")

    monkeypatch.setattr(cli, "resolve_claude_command", lambda explicit=None: ["fake-claude"])
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return ran


def test_doctor_offline_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    ran = _fake_claude_on_path(monkeypatch)
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    low = result.output.lower()
    assert "stub round trip: ok" in low
    assert "claude" in low
    assert "anthropic_api_key" in low and "sk-" not in low
    assert "fake-claude" in low and "9.9.9" in low  # the resolved command is shown
    assert ran == [["fake-claude", "--version"]]


def test_doctor_offline_reports_an_unusable_claude_without_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unresolvable(explicit: list[str] | None = None) -> list[str]:
        raise ProviderError("claude is a script shim; set CLAUDE_BULLY_CLAUDE")

    monkeypatch.setattr(cli, "resolve_claude_command", unresolvable)
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "CLAUDE_BULLY_CLAUDE" in " ".join(result.output.split())
    assert "stub round trip: ok" in result.output.lower()


def test_doctor_offline_has_no_mcp_check_and_never_builds_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_claude_on_path(monkeypatch)

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline doctor must not call claude")

    # the names the CLI and the doctor look up at call time
    monkeypatch.setattr(cli, "run_live_checks", explode)
    monkeypatch.setattr("claude_bully.doctor.ClaudeCodeProvider", explode)
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "mcp" not in result.output.lower()
    assert "tools.jsonl" not in result.output.lower()
