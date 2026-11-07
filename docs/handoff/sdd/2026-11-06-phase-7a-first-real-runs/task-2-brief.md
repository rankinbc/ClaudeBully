### Task 2: The ledger in analysis: `ledger.json`, the "Calls" line, `promote`

Spec section 9 ("The cost ledger"): `analyze` writes `analysis/ledger.json` (totals by role and model, per cell, cached versus made, errors, rate-limit pauses, mean latency per role) and `results.md` gains a "Calls" line under the leaderboard; `promote` copies `ledger.jsonl`. Reads the run only (I37).

**Files:**
- Create: `claude_bully/analysis/ledger.py`, `tests/test_ledger_analysis.py`
- Modify: `claude_bully/analysis/load.py`, `claude_bully/analysis/report.py`, `claude_bully/analysis/run_analysis.py`, `claude_bully/analysis/promote.py`, `tests/test_promote.py`, `HANDOFF.md`, `docs/00-RECONCILED.md`, the spec's "As planned"
- Test: `tests/test_ledger_analysis.py`, `tests/test_promote.py`; unchanged: `tests/test_analysis_tables.py`, `tests/test_run_analysis.py`
- Test count: 5 new tests in `tests/test_ledger_analysis.py`, 1 appended to `tests/test_promote.py`.

**Interfaces:**
- Consumes: `LedgerLine`, `LEDGER_FILE`, `Ledger` (Task 1); `LoadedRun`, `load_run` (`analysis/load.py:48, 97`); `write_results_md` (`analysis/report.py:12`); `analyze_run` (`analysis/run_analysis.py:86`); `COPIED_DIRS`, `promote` (`analysis/promote.py:17, 42`).
- Produces (behaviour, P20b): `analyze_run` re-reads the ledger after the judge pass (`loaded.ledger = Ledger(run_dir / LEDGER_FILE).lines()`) before `write_ledger`, because `load_run` read it before `_judge_all` wrote that pass's lines; `ledger.json` and the Calls line therefore include the judge calls the same `analyze` made.
- Produces (`analysis/ledger.py`): `LEDGER_JSON: Final = "ledger.json"`; `class RoleTotals(BaseModel)`: `calls: int = 0`, `cached: int = 0`, `errors: int = 0`, `rate_limits: int = 0`, `timeouts: int = 0`, `input_tokens: int = 0`, `output_tokens: int = 0`, `cost_usd: float = 0.0`, `mean_latency_ms: float | None = None`; `totals(lines: Sequence[LedgerLine]) -> RoleTotals`; `by_role(lines) -> dict[str, RoleTotals]`; `by_model(lines) -> dict[str, RoleTotals]`; `by_cell(lines) -> dict[str, RoleTotals]` (run-level lines under `"_run"`); `write_ledger(loaded: LoadedRun, out_dir: Path) -> Path | None` (None, no file, when the run has no ledger); `calls_line(lines) -> str | None` (`"<n> calls made, <c> cached; by role: target 12, bully 10, judge 24"`, roles in `ROLES` order, zero roles left out).
- Produces (`analysis/load.py`): `LoadedRun.ledger: list[LedgerLine]` (default empty), read in `load_run` from `run_dir / LEDGER_FILE`.
- Produces (`analysis/report.py`): `write_results_md(loaded, out_dir, chart_paths, *, calls: str | None = None)`: a `## Calls` section with the line, after `## Bully compliance` and before `## Charts`.
- Produces (`analysis/promote.py`): `COPIED_FILES: Final = ("run.json", LEDGER_FILE)` replaces the single `run.json` copy.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger_analysis.py
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
```

Append to `tests/test_promote.py`:

```python
def test_promote_copies_the_ledger(tmp_path: Path) -> None:
    from claude_bully.config import load_experiment
    from claude_bully.providers.ledger import LEDGER_FILE
    from claude_bully.runner.runner import run_experiment

    exp = load_experiment(Path(__file__).parent / "fixtures" / "configs" / "stub_smoke.yaml")
    run_experiment(exp, runs_root=tmp_path / "runs")
    analyze_run(tmp_path / "runs" / exp.name, judge=False)
    dest = promote(exp.name, tmp_path / "runs", tmp_path / "results")
    assert (dest / LEDGER_FILE).read_text("utf-8") == (
        tmp_path / "runs" / exp.name / LEDGER_FILE
    ).read_text("utf-8")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_ledger_analysis.py tests/test_promote.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_bully.analysis.ledger'`.

- [ ] **Step 3: Implement**

Create `claude_bully/analysis/ledger.py`:

```python
"""ledger.json (Phase 7 spec section 9): what a run's provider calls cost, read from
``ledger.jsonl`` alone. On a subscription the cost is the count of calls; the tokens and the
``cost_usd`` the backends report ride along as information."""

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from claude_bully.analysis.load import LoadedRun
from claude_bully.providers.ledger import ROLES, LedgerLine

LEDGER_JSON: Final = "ledger.json"
RUN_LEVEL: Final = "_run"


class RoleTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calls: int = 0  # calls made (every status but cached)
    cached: int = 0
    errors: int = 0
    rate_limits: int = 0
    timeouts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    mean_latency_ms: float | None = None  # over the made calls that report a latency


def totals(lines: Sequence[LedgerLine]) -> RoleTotals:
    out = RoleTotals()
    latencies: list[int] = []
    for line in lines:
        if line.status == "cached":
            out.cached += 1
            continue
        out.calls += 1
        out.errors += int(line.status == "error")
        out.rate_limits += int(line.status == "rate_limit")
        out.timeouts += int(line.status == "timeout")
        out.input_tokens += line.input_tokens or 0
        out.output_tokens += line.output_tokens or 0
        out.cost_usd += line.cost_usd or 0.0
        if line.latency_ms is not None:
            latencies.append(line.latency_ms)
    out.cost_usd = round(out.cost_usd, 6)
    if latencies:
        out.mean_latency_ms = sum(latencies) / len(latencies)
    return out


def _grouped(lines: Sequence[LedgerLine], key: str) -> dict[str, RoleTotals]:
    groups: dict[str, list[LedgerLine]] = defaultdict(list)
    for line in lines:
        value = getattr(line, key)
        groups[str(value) if value is not None else RUN_LEVEL].append(line)
    return {name: totals(group) for name, group in groups.items()}


def by_role(lines: Sequence[LedgerLine]) -> dict[str, RoleTotals]:
    """Role -> totals, in ``ROLES`` order, unknown roles after, zero roles left out."""
    grouped = _grouped(lines, "role")
    order = [r for r in ROLES if r in grouped] + sorted(r for r in grouped if r not in ROLES)
    return {role: grouped[role] for role in order}


def by_model(lines: Sequence[LedgerLine]) -> dict[str, RoleTotals]:
    return dict(sorted(_grouped(lines, "model").items()))


def by_cell(lines: Sequence[LedgerLine]) -> dict[str, RoleTotals]:
    """Cell -> totals; run-level lines (analysis, the doctor) under ``_run``."""
    return dict(sorted(_grouped(lines, "cell_id").items()))


def calls_line(lines: Sequence[LedgerLine]) -> str | None:
    """The results.md line: calls made and cached, then each role's count (with its cached count
    when it has one). None for a run with no ledger."""
    if not lines:
        return None
    whole = totals(lines)
    parts = []
    for role, got in by_role(lines).items():
        part = f"{role} {got.calls}"
        if got.cached:
            part += f" ({got.cached} cached)"
        parts.append(part)
    return f"{whole.calls} calls made, {whole.cached} cached; by role: {', '.join(parts)}"


def write_ledger(loaded: LoadedRun, out_dir: Path) -> Path | None:
    """``ledger.json``; None, with no file, when the run has no ledger."""
    if not loaded.ledger:
        return None
    payload = {
        "totals": totals(loaded.ledger).model_dump(),
        "by_role": {k: v.model_dump() for k, v in by_role(loaded.ledger).items()},
        "by_model": {k: v.model_dump() for k, v in by_model(loaded.ledger).items()},
        "by_cell": {k: v.model_dump() for k, v in by_cell(loaded.ledger).items()},
        "calls_line": calls_line(loaded.ledger),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / LEDGER_JSON
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path


__all__ = [
    "LEDGER_JSON",
    "RoleTotals",
    "by_cell",
    "by_model",
    "by_role",
    "calls_line",
    "totals",
    "write_ledger",
]
```

In `claude_bully/analysis/load.py`: import `from claude_bully.providers.ledger import LEDGER_FILE, Ledger, LedgerLine`; add to `LoadedRun` after `request_banks`: `# the run's provider calls (Phase 7); empty for a run with no ledger` and `ledger: list[LedgerLine] = field(default_factory=list)`; in `load_run`, before `return LoadedRun(...)`, add `ledger = Ledger(run_dir / LEDGER_FILE).lines()` and pass `ledger=ledger`.

In `claude_bully/analysis/report.py`, `write_results_md(loaded, out_dir, chart_paths, *, calls: str | None = None)`: after the `compliance_report(loaded), ""` lines and before `if chart_paths:`, add:

```python
    if calls is not None:
        lines += ["## Calls", "", calls, ""]
```

In `claude_bully/analysis/run_analysis.py`: import `from claude_bully.analysis.ledger import calls_line, write_ledger` and add `Ledger` to the `claude_bully.providers.ledger` import; after Task 1's `if judge:` block (the judge pass wrote its lines after `load_run` read the stream) add:

```python
    # the stream as it stands after the judge pass, so ledger.json counts this analysis's own
    # judge calls (P20b)
    loaded.ledger = Ledger(run_dir / LEDGER_FILE).lines()
```

then before `return write_results_md(loaded, out, charts)`, add `write_ledger(loaded, out)` and change the return to `return write_results_md(loaded, out, charts, calls=calls_line(loaded.ledger))`. (Task 6's rewrite of `analyze_run` keeps the re-read in the same place.)

In `claude_bully/analysis/promote.py`: import `from claude_bully.providers.ledger import LEDGER_FILE`; replace `COPIED_DIRS = ("judge_cache", "analysis")` and the `shutil.copy2(store.run_dir / "run.json", ...)` line with:

```python
COPIED_FILES = ("run.json", LEDGER_FILE)
COPIED_DIRS = ("judge_cache", "analysis")
...
    for name in COPIED_FILES:
        source = store.run_dir / name
        if source.exists():
            shutil.copy2(source, dest / name)
```

and extend the module docstring's second sentence: "..., the judge cache, the analysis outputs and the ledger."

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_ledger_analysis.py tests/test_promote.py tests/test_analysis_tables.py tests/test_run_analysis.py tests/test_cli.py -q`
Expected: PASS. `tests/test_run_analysis.py::test_analyze_with_stub_judge_fills_judgements_and_caches` reads the leaderboard slice between `## Leaderboard` and `## Bully compliance`, which the new section does not touch.

- [ ] **Step 5: Docs sync**

- `HANDOFF.md`: Progress gains "Phase 7a Task 2: ledger.json, the Calls line, promote copies the ledger (BASE..HEAD)".
- `docs/00-RECONCILED.md`: section B's `LedgerLine` row gains "analysis: `analysis/ledger.json` (totals, by role, by model, by cell, the Calls line) written by `analyze_run`; `promote` copies the stream"; section E: `promote` copies `ledger.jsonl`.
- The spec's "As planned": "`ledger.json` is written only for a run with a ledger; `results.md` gains `## Calls` after `## Bully compliance`; run-level lines are grouped under `_run`."

- [ ] **Step 6: Gate and commit**

Run: the gate.
Expected: PASS, 0 warnings.

```bash
git add claude_bully/analysis/ledger.py claude_bully/analysis/load.py claude_bully/analysis/report.py claude_bully/analysis/run_analysis.py claude_bully/analysis/promote.py tests/test_ledger_analysis.py tests/test_promote.py HANDOFF.md docs/00-RECONCILED.md docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md
git commit -m "feat: ledger.json, the Calls line in results.md, and promote copies the ledger

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
