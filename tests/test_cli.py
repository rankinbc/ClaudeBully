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
