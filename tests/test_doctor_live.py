# tests/test_doctor_live.py
"""doctor --live (Phase 7 spec section 9) on the faked claude: every preflight, the JSON report,
the nested responder in a clean child environment, and exit 1 on a failed check."""

import json
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_bully import cli, doctor
from claude_bully.doctor import CHECK_NAMES, DOCTOR_REPORT, DOCTOR_SUCCESSOR, default_out_dir
from claude_bully.environments.mcp_server import SERVER_NAME
from claude_bully.providers.base import Completion
from claude_bully.providers.claude_code import ClaudeCodeProvider
from claude_bully.providers.ledger import LEDGER_FILE, LedgerLine, activate

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"
runner = CliRunner()
JUDGE_REPLY = {
    "required": ["a", "b", "more_resilient"],
    "reply": {
        "a": {"bully_goal_achieved": 1, "resilience": 2, "rationale": "held"},
        "b": {"bully_goal_achieved": 0, "resilience": 3, "rationale": "fine"},
        "more_resilient": "B",
    },
}
GENERATOR_REPLY = {
    "required": ["kind", "title", "body", "used_items"],
    "reply": {
        "kind": "support_ticket",
        "title": "Kettle",
        "body": "The kettle trips the fuse again.",
        "used_items": [],
    },
}


@pytest.fixture
def faked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake claude behind doctor --live, scripted for every check."""
    log = tmp_path / "fake.log"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")  # as if the doctor itself ran inside Claude Code
    monkeypatch.setenv(
        "FAKE_CLAUDE_TOOL_CALL",
        json.dumps(
            [
                {"name": "web_search", "arguments": {"query": "ferry"}},
                {
                    "name": "consult_model",
                    "arguments": {"name": DOCTOR_SUCCESSOR, "text": "Are you there?"},
                },
            ]
        ),
    )
    monkeypatch.setenv("FAKE_CLAUDE_STRUCTURED", json.dumps([JUDGE_REPLY, GENERATOR_REPLY]))
    monkeypatch.setattr(
        cli, "resolve_claude_command", lambda explicit=None: [sys.executable, str(FAKE)]
    )
    # the disk check probes a temporary repo and runs root, never the working tree (P22);
    # doctor.REPO_ROOT stays, so mini_worlds_dir still finds tests/fixtures/worlds
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("output/\n", encoding="utf-8")
    monkeypatch.setattr(cli, "REPO_ROOT", repo)
    return log


def _report(out: Path) -> dict[str, object]:
    return dict(json.loads((out / DOCTOR_REPORT).read_text(encoding="utf-8")))


def _live(tmp_path: Path, *extra: str, name: str = "doctor") -> tuple[Path, object]:
    out = tmp_path / name
    args = ["doctor", "--live", "--out", str(out), "--runs-root", str(tmp_path / "runs"), *extra]
    return out, runner.invoke(cli.app, args)


def test_doctor_live_passes_every_check_on_the_fake(tmp_path: Path, faked: Path) -> None:
    real_output = doctor.REPO_ROOT / "output"
    had_output = real_output.exists()
    out, result = _live(tmp_path)
    assert result.exit_code == 0, result.output
    report = _report(out)
    checks = {c["name"]: c for c in report["checks"]}  # type: ignore[union-attr]
    assert tuple(checks) == CHECK_NAMES
    assert all(c["ok"] for c in checks.values()), checks
    assert checks["thinking"]["detail"].startswith("yes")  # the fake's thinking block was seen
    # check 4 and check 5 open with the server's load status, read off the init event
    assert checks["mcp"]["detail"].startswith(
        f"server {SERVER_NAME} connected; tools.jsonl lines 1"
    )
    assert checks["responder"]["detail"].startswith(f"server {SERVER_NAME} connected; ")
    assert checks["sandbox"]["detail"].startswith(f"servers [{SERVER_NAME!r}]; ")
    # the number the runbook reads: the nested responder's own ledger latency (P34a)
    assert re.search(r"answered in \d+ ms", checks["responder"]["detail"]), checks["responder"]
    assert "stub-sonnet-20260101" in checks["login"]["detail"]  # the resolved model is shown
    assert (tmp_path / "runs" / "_cache").is_dir()
    # the CLI passed its call-time REPO_ROOT, the temporary repo, never the working tree (P22)
    assert (tmp_path / "repo" / "output").is_dir() and real_output.exists() == had_output
    assert "effort low" in checks["effort"]["detail"]  # the flag read off the ledger line
    lines = [LedgerLine.model_validate(ln) for ln in report["ledger"]]  # type: ignore[union-attr]
    roles = {ln.role for ln in lines}
    assert roles == {"doctor", "responder"}
    assert any(ln.effort == "low" for ln in lines if ln.role == "doctor")
    assert (out / LEDGER_FILE).exists()
    for name in CHECK_NAMES:
        assert f"{name}:" in result.output.lower()
    # the nested responder ran as its own claude -p, in a clean environment; so did every other
    # process the doctor spawned, the two --version runs included (P12)
    entries = [json.loads(ln) for ln in faked.read_text(encoding="utf-8").splitlines()]
    nested = [e for e in entries if e["stdin"] == "Are you there?"]
    assert len(nested) == 1
    assert sum(1 for e in entries if e["argv"][-1] == "--version") == 2
    assert not any(k.startswith(("CLAUDECODE", "CLAUDE_CODE_")) for e in entries for k in e["env"])
    outer = [e for e in entries if "--mcp-config" in e["argv"]]
    assert outer and all(e["env"]["MCP_TOOL_TIMEOUT"] == "300000" for e in outer)


def test_doctor_live_exits_1_when_not_logged_in(
    tmp_path: Path, faked: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "login_error")
    out, result = _live(tmp_path)
    assert result.exit_code == 1, result.output
    report = _report(out)  # the whole report is still written
    checks = {c["name"]: c for c in report["checks"]}  # type: ignore[union-attr]
    assert checks["login"]["ok"] is False and "not logged in" in checks["login"]["detail"]
    assert checks["command"]["ok"] is True and checks["disk"]["ok"] is True
    # the same login error named when claude -p exits 1 with it
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "login_error_exit")
    out, result = _live(tmp_path, name="doctor_exit")
    login = {c["name"]: c for c in _report(out)["checks"]}["login"]  # type: ignore[union-attr]
    assert result.exit_code == 1, result.output
    assert login["ok"] is False and "not logged in" in login["detail"]


def test_a_rerun_into_the_same_dir_reports_only_its_own_calls(tmp_path: Path, faked: Path) -> None:
    out, first = _live(tmp_path)
    assert first.exit_code == 0, first.output  # type: ignore[attr-defined]
    once = len(_report(out)["ledger"])  # type: ignore[arg-type]
    out, second = _live(tmp_path)  # the same --out, as a second run on one day would be
    assert second.exit_code == 0, second.output  # type: ignore[attr-defined]
    assert len(_report(out)["ledger"]) == once  # type: ignore[arg-type]
    assert len((out / LEDGER_FILE).read_text(encoding="utf-8").splitlines()) == once


def test_the_effort_check_reads_the_flag_off_its_ledger_line(tmp_path: Path, faked: Path) -> None:
    command = [sys.executable, str(FAKE)]
    ok, detail = doctor._check_effort(command, tmp_path / "bare")
    assert not ok and "no doctor-effort ledger line" in detail  # a reply alone does not pass
    with activate(tmp_path / LEDGER_FILE):
        ok, detail = doctor._check_effort(command, tmp_path / "ledgered")
    assert ok and "effort low" in detail


def test_the_default_report_dir_is_dated_under_output(tmp_path: Path) -> None:
    out = default_out_dir(tmp_path)
    assert out.parent == tmp_path / "output" and out.name.startswith("doctor_live_20")


def test_the_live_doctor_needs_a_usable_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    from claude_bully.providers.base import ProviderError

    def unresolvable(explicit: list[str] | None = None) -> list[str]:
        raise ProviderError("claude not found")

    monkeypatch.setattr(cli, "resolve_claude_command", unresolvable)
    result = runner.invoke(cli.app, ["doctor", "--live"])
    assert result.exit_code == 1


NOT_LOADED = (
    f"server {SERVER_NAME} not loaded (absent from the init event: a reserved or rejected name, "
    "or a config the CLI dropped)"
)


@pytest.mark.parametrize(
    ("status", "said"),
    [("failed", f"server {SERVER_NAME} failed; "), ("absent", NOT_LOADED + "; ")],
)
def test_a_server_that_did_not_load_is_named_by_checks_4_and_5(
    tmp_path: Path, faked: Path, monkeypatch: pytest.MonkeyPatch, status: str, said: str
) -> None:
    """The first real doctor --live: the CLI dropped the server's config entry, the target
    imitated a tool call in text, and nothing said why. The status line is the one-line read."""
    monkeypatch.setenv("FAKE_CLAUDE_MCP_STATUS", status)
    out, result = _live(tmp_path)
    assert result.exit_code == 1, result.output
    checks = {c["name"]: c for c in _report(out)["checks"]}  # type: ignore[union-attr]
    assert checks["mcp"]["ok"] is False and checks["mcp"]["detail"].startswith(said)
    assert "tools.jsonl lines 0" in checks["mcp"]["detail"]  # the counts still follow
    # the nested responder never ran, and the reason is named first
    assert checks["responder"]["ok"] is False
    assert checks["responder"]["detail"].startswith(said), checks["responder"]
    assert checks["sandbox"]["ok"] is True  # the config itself is right: the CLI dropped it


class _SaysFailed(ClaudeCodeProvider):
    """A provider whose stream says its server failed, whatever the calls did."""

    def parse_stream(self, stdout: str, session: str) -> Completion:
        completion = super().parse_stream(stdout, session)
        self.mcp_servers_seen = [(SERVER_NAME, "failed")]
        return completion


def test_check_4_fails_on_a_status_other_than_connected_whatever_the_counts(
    tmp_path: Path, faked: Path
) -> None:
    worlds = doctor.mini_worlds_dir()
    assert worlds is not None
    built = doctor._mcp_provider([sys.executable, str(FAKE)], tmp_path, worlds)
    inner = _SaysFailed(
        model="sonnet",
        state_dir=tmp_path / "says_failed",
        command=[sys.executable, str(FAKE)],
        mcp_state_dir=built.mcp_state_dir,
    )
    ok, detail = doctor._check_mcp(inner)
    assert not ok and detail.startswith(f"server {SERVER_NAME} failed; tools.jsonl lines 1"), detail
    unknown = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "u", command=["claude"])
    assert doctor._server_status(unknown) == (
        False,
        f"server {SERVER_NAME} status unknown (no stream-json init event)",
    )
