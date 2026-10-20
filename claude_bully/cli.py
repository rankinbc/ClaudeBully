"""claude-bully command line."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from claude_bully.analysis.promote import promote as promote_run
from claude_bully.analysis.report import update_readme
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import load_experiment
from claude_bully.enums import Speaker
from claude_bully.paths import DEFAULT_RESULTS_ROOT, DEFAULT_RUNS_ROOT
from claude_bully.providers.base import Message
from claude_bully.providers.claude_code import ClaudeCodeProvider
from claude_bully.providers.stub import StubProvider
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.strategies.base import all_strategies
from claude_bully.strategies.composed import Composed
from claude_bully.strategies.factory import ensure_registered

app = typer.Typer(
    help="Bully personas versus LLMs: measure behavioral drift.", no_args_is_help=True
)
console = Console()

RunsRoot = Annotated[Path, typer.Option(help="Where runs are written.")]
ResultsRoot = Annotated[Path, typer.Option(help="Where promoted runs live.")]
RATE_LIMIT_EXIT_CODE = 3


@app.command()
def run(
    config: Annotated[Path, typer.Argument(help="Experiment YAML.")],
    run_id: Annotated[str | None, typer.Option(help="Defaults to the experiment name.")] = None,
    only: Annotated[str | None, typer.Option(help="fnmatch glob on cell ids.")] = None,
    max_cells: Annotated[int | None, typer.Option(help="Run at most this many cells.")] = None,
    dry_run: Annotated[bool, typer.Option(help="List cells and exit.")] = False,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
) -> None:
    """Run (or resume) an experiment. Exit code 3 means a rate limit paused it."""
    exp = load_experiment(config)
    try:
        summary = run_experiment(
            exp,
            runs_root=runs_root,
            run_id=run_id,
            only=only,
            max_cells=max_cells,
            dry_run=dry_run,
            console=console,
        )
    except RateLimitExit as exc:
        wait = (
            f"about {int(exc.retry_after_s)} seconds" if exc.retry_after_s else "the stated window"
        )
        console.print(
            f"[yellow]Rate limited:[/] {exc}. Progress is saved; "
            f"retry the same command after {wait}."
        )
        raise typer.Exit(code=RATE_LIMIT_EXIT_CODE) from None
    if dry_run:
        console.print(f"{summary.cells_total} cells would run.")
        return
    console.print(
        f"run {summary.run_id}: {summary.cells_total} cells, {summary.cells_completed} complete, "
        f"{summary.cells_aborted} aborted, {summary.cells_skipped} skipped, "
        f"{summary.turns_written} turns written"
    )


@app.command()
def analyze(
    run_id: str,
    no_judge: Annotated[bool, typer.Option("--no-judge", help="Skip judge calls.")] = False,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
) -> None:
    """Recompute metrics, events, judge verdicts and charts from JSONL."""
    path = analyze_run(runs_root / run_id, judge=not no_judge)
    console.print(f"wrote {path}")


@app.command("list-strategies")
def list_strategies(
    names: Annotated[bool, typer.Option("--names", help="One name per line.")] = False,
) -> None:
    """Every registered strategy."""
    ensure_registered()
    rows = sorted(
        (
            c
            for c in all_strategies().values()
            if not issubclass(c, Composed) and not c.name.startswith("_")
        ),
        key=lambda c: (c.axis.value, c.name),
    )
    if names:
        for cls in rows:
            typer.echo(cls.name)
        return
    table = Table("name", "axis", "has_reveal", "events", "captures")
    for cls in rows:
        table.add_row(
            cls.name,
            cls.axis.value,
            "yes" if cls.has_reveal else "no",
            str(len(cls.relevant_events)),
            ", ".join(sorted(cls.capture_points)) or "-",
        )
    console.print(table)


@app.command()
def show(
    target: Annotated[str, typer.Argument(help="RUN_ID/CELL_ID")],
    rep: int = 0,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
) -> None:
    """Pretty-print one conversation."""
    run_id, _, cell_id = target.partition("/")
    if not cell_id:
        raise typer.BadParameter("expected RUN_ID/CELL_ID")
    conv = RunStore(runs_root, run_id).read_conversation(cell_id, rep)
    console.print(
        f"[bold]{conv.cell_id}[/] rep {conv.rep} | {conv.strategy_name} | "
        f"status {conv.status.value}" + (f" ({conv.abort_reason})" if conv.abort_reason else "")
    )
    for t in conv.turns:
        if t.bully_meta.get("rate_limit_pause"):
            console.print(f"[dim]#{t.index} [rate limit pause][/]")
            continue
        colour = "cyan" if t.speaker is Speaker.target else "magenta"
        flag = " [scripted]" if t.scripted else ""
        console.print(f"[{colour}]#{t.index} {t.speaker.value} ({t.phase.value}){flag}[/] {t.text}")
    if conv.captured_responses:
        console.print("[bold]captured responses[/]")
        for name, cap in conv.captured_responses.items():
            console.print(f"  {name} (turn {cap.turn_index}): {cap.text[:200]}")


@app.command("readme-results")
def readme_results(
    run_ids: Annotated[list[str], typer.Argument(help="One or more run ids.")],
    readme: Annotated[Path, typer.Option(help="README to update.")] = Path("README.md"),
    from_results: Annotated[
        bool, typer.Option("--from-results", help="Read results/ not runs/.")
    ] = False,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
    results_root: ResultsRoot = DEFAULT_RESULTS_ROOT,
) -> None:
    """Regenerate the README results section from one or more runs."""
    root = results_root if from_results else runs_root
    parts: list[str] = []
    for run_id in run_ids:
        results_md = root / run_id / "analysis" / "results.md"
        if not results_md.exists():
            if from_results:
                raise typer.BadParameter(f"{results_md} not found; promote the run first")
            analyze_run(root / run_id, judge=False)
        parts.append(results_md.read_text(encoding="utf-8").strip())
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write("\n\n".join(parts) + "\n")
        combined = Path(fh.name)
    try:
        update_readme(readme, combined)
    finally:
        combined.unlink(missing_ok=True)
    console.print(f"updated {readme} from {', '.join(run_ids)}")


@app.command()
def promote(
    run_id: str,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing promotion.")] = False,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
    results_root: ResultsRoot = DEFAULT_RESULTS_ROOT,
) -> None:
    """Copy a finished run into results/ (committed), after a denylist scan."""
    dest = promote_run(run_id, runs_root, results_root, force=force)
    console.print(f"promoted to {dest}")


@app.command()
def doctor(
    live: Annotated[
        bool, typer.Option("--live", help="Also make one real claude -p call.")
    ] = False,
) -> None:
    """Check the local setup without spending anything (unless --live)."""
    claude = shutil.which("claude")
    if claude:
        version = subprocess.run([claude, "--version"], capture_output=True, text=True, check=False)
        console.print(f"claude on PATH: {version.stdout.strip() or 'yes'}")
    else:
        console.print("claude on PATH: [yellow]not found[/] (claude_code backend unavailable)")
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        console.print(f"{env}: {'set' if os.environ.get(env) else 'not set'}")
    stub = StubProvider().complete("doctor", "sys", [Message(role="user", content="ping")])
    console.print(f"stub round trip: {'ok' if stub.text.endswith('ping') else 'FAILED'}")
    if live:
        if not claude:
            raise typer.Exit(code=1)
        with tempfile.TemporaryDirectory() as tmp:
            provider = ClaudeCodeProvider(model="sonnet", state_dir=Path(tmp))
            reply = provider.complete(
                "doctor", "Reply with the single word pong.", [Message(role="user", content="ping")]
            )
        console.print(f"claude -p live call: {reply.text.strip()[:40]!r} (cost {reply.cost_usd})")


if __name__ == "__main__":
    app()
