"""ledger.json and the Calls line (Phase 7 spec section 9), read from the run only."""

import json
import shutil
from pathlib import Path

from claude_bully.analysis.ledger import (
    LEDGER_JSON,
    RoleTotals,
    by_cell,
    by_role,
    calls_line,
    totals,
    write_ledger,
)
from claude_bully.analysis.load import load_run
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import ProviderKind
from claude_bully.providers.ledger import LEDGER_FILE, LedgerLine
from claude_bully.runner.runner import run_experiment

FIXTURES = Path(__file__).parent / "fixtures"
STUB_SMOKE = FIXTURES / "configs" / "stub_smoke.yaml"
JUDGE_RULES = FIXTURES / "stub_scripts" / "judge_rules.yaml"


def _line(role: str, status: str = "ok", **fields: object) -> LedgerLine:
    base: dict[str, object] = {
        "ts": "2026-11-06T00:00:00+00:00",
        "role": role,
        "conversation_id": f"run/c__t0/rep0/{role}",
        "cell_id": "c__t0",
        "rep": 0,
        "backend": "stub",
        "model": "m",
        "status": status,
        "latency_ms": 100,
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.01,
    }
    base.update(fields)
    return LedgerLine.model_validate(base)


LINES = [
    _line("target"),
    _line("target", latency_ms=300),
    _line("bully"),
    # a failed call as the wrapper writes it: no latency, no tokens, no cost (P20a)
    _line(
        "bully",
        status="rate_limit",
        latency_ms=None,
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
    ),
    _line("judge", status="cached", latency_ms=None, cell_id=None, rep=None),
    _line("judge", status="error", error="ProviderError"),
    _line("harvest", status="timeout", error="ProviderError"),
]


def test_totals_count_each_status_and_average_latency_over_made_calls() -> None:
    got = totals(LINES)
    assert got == RoleTotals(
        calls=6,
        cached=1,
        errors=1,
        rate_limits=1,
        timeouts=1,
        input_tokens=50,
        output_tokens=25,
        cost_usd=0.05,
        mean_latency_ms=140.0,
    )
    assert totals([]) == RoleTotals()


def test_by_role_and_by_cell_group_the_lines() -> None:
    roles = by_role(LINES)
    assert list(roles) == ["target", "bully", "judge", "harvest"]  # ROLES order
    assert roles["target"].calls == 2 and roles["judge"].cached == 1
    cells = by_cell(LINES)
    assert set(cells) == {"c__t0", "_run"} and cells["_run"].cached == 1


def test_the_calls_line_names_made_and_cached_by_role() -> None:
    assert calls_line(LINES) == (
        "6 calls made, 1 cached; by role: target 2, bully 2, judge 1 (1 cached), harvest 1"
    )
    assert calls_line([]) is None


def test_analyze_writes_ledger_json_and_the_calls_section(tmp_path: Path) -> None:
    exp = load_experiment(STUB_SMOKE).model_copy(
        update={
            "judge": RoleConfig(
                provider=ProviderKind.stub, model="stub-judge", stub_script=str(JUDGE_RULES)
            )
        }
    )
    run_experiment(exp, runs_root=tmp_path)
    run_dir = tmp_path / exp.name
    results = analyze_run(run_dir)
    payload = json.loads((run_dir / "analysis" / LEDGER_JSON).read_text("utf-8"))
    assert set(payload) == {"totals", "by_role", "by_model", "by_cell", "calls_line"}
    assert payload["by_role"]["target"]["calls"] > 0 and payload["by_role"]["judge"]["calls"] > 0
    text = results.read_text("utf-8")
    assert "## Calls" in text and text.index("## Calls") > text.index("## Bully compliance")
    assert payload["calls_line"] in text
    loaded = load_run(run_dir)
    assert len(loaded.ledger) == payload["totals"]["calls"] + payload["totals"]["cached"]


def test_a_run_without_a_ledger_writes_no_ledger_json(stub_run: Path, tmp_path: Path) -> None:
    # a private copy: stub_run is session-scoped and shared, never edited in place (P20c)
    run_dir = tmp_path / "runs" / stub_run.name
    shutil.copytree(stub_run, run_dir)
    (run_dir / LEDGER_FILE).unlink(missing_ok=True)
    loaded = load_run(run_dir)
    assert loaded.ledger == []
    assert write_ledger(loaded, tmp_path) is None and not (tmp_path / LEDGER_JSON).exists()
    text = analyze_run(run_dir, judge=False, out_dir=tmp_path / "a").read_text("utf-8")
    assert "## Calls" not in text
