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
