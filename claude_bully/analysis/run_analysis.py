"""analyze_run: recompute everything from disk. The judge is the only model call; it is cached."""

import json
from pathlib import Path
from typing import Any

from claude_bully.analysis.compare import compare_chart
from claude_bully.analysis.curves import drift_curves
from claude_bully.analysis.dose import dose_response
from claude_bully.analysis.load import LoadedRun, load_run
from claude_bully.analysis.report import write_results_md
from claude_bully.analysis.rescue import rescue_curve
from claude_bully.config import RoleConfig
from claude_bully.enums import CellStatus
from claude_bully.metrics.judge import (
    JudgeCache,
    JudgeError,
    PairJudgement,
    judge_capture,
    judge_pair,
)
from claude_bully.providers.base import ChatProvider, build_provider
from claude_bully.runner.runner import ProviderFactory

JUDGE_CACHE_DIR = "judge_cache"
ANALYSIS_DIR = "analysis"


def _judge_all(loaded: LoadedRun, run_dir: Path, provider: ChatProvider, model: str) -> None:
    cache = JudgeCache(run_dir / JUDGE_CACHE_DIR)
    for cell_id in loaded.condition_cells():
        strategy = loaded.strategies[cell_id]
        control_id = loaded.control_for(cell_id)
        for rep in loaded.reps_of(cell_id):
            conv = loaded.conversations[(cell_id, rep)]
            if conv.status is not CellStatus.complete:
                continue
            if control_id is not None and (control_id, rep) in loaded.conversations:
                control = loaded.conversations[(control_id, rep)]
                try:
                    loaded.judgements[(cell_id, rep)] = judge_pair(
                        provider,
                        model,
                        conv,
                        control,
                        strategy.judge_window(conv),
                        cache,
                        loaded.experiment.seed,
                    )
                except JudgeError as exc:
                    loaded.judgements[(cell_id, rep)] = exc
            for name in sorted(conv.captured_responses):
                if name not in type(strategy).capture_points:
                    continue
                try:
                    loaded.captures[(cell_id, rep, name)] = judge_capture(
                        provider, model, conv, name, type(strategy).resilient_behavior, cache
                    )
                except JudgeError:
                    continue


def _dump_judgements(loaded: LoadedRun, out_dir: Path) -> None:
    judgements: dict[str, Any] = {}
    for (cell_id, rep), j in loaded.judgements.items():
        key = f"{cell_id}/{rep}"
        judgements[key] = j.model_dump() if isinstance(j, PairJudgement) else {"error": str(j)}
    (out_dir / "judgements.json").write_text(json.dumps(judgements, indent=1), encoding="utf-8")
    captures = {f"{c}/{r}/{n}": v.model_dump() for (c, r, n), v in loaded.captures.items()}
    (out_dir / "captures.json").write_text(json.dumps(captures, indent=1), encoding="utf-8")


def analyze_run(
    run_dir: Path,
    *,
    judge: bool = True,
    provider_factory: ProviderFactory = build_provider,
    out_dir: Path | None = None,
) -> Path:
    loaded = load_run(run_dir)
    out = out_dir or run_dir / ANALYSIS_DIR
    out.mkdir(parents=True, exist_ok=True)
    if judge:
        role: RoleConfig = loaded.experiment.judge
        provider = provider_factory(role, run_dir / "state" / "judge")
        _judge_all(loaded, run_dir, provider, role.model)
    _dump_judgements(loaded, out)
    charts: list[Path] = []
    charts += drift_curves(loaded, out)
    charts += dose_response(loaded, out)
    for cfg in loaded.experiment.compare:
        charts.append(compare_chart(loaded, cfg, out))
    rescue = rescue_curve(loaded, out)
    if rescue is not None:
        charts.append(rescue)
    return write_results_md(loaded, out, charts)
