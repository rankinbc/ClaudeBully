"""claude-bully command line."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from claude_bully.analysis.promote import promote as promote_run
from claude_bully.analysis.replay import replay_cell
from claude_bully.analysis.report import update_readme
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import load_experiment
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.mcp_server import (
    STATE_FILE,
    TOOLS_FILE,
    McpState,
    write_mcp_state,
)
from claude_bully.environments.tools import TOOL_SPECS
from claude_bully.environments.world import load_world
from claude_bully.paths import DATA_DIR, DEFAULT_RESULTS_ROOT, DEFAULT_RUNS_ROOT, REPO_ROOT
from claude_bully.providers.base import Message, ProviderError
from claude_bully.providers.claude_code import ClaudeCodeProvider, resolve_claude_command
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
    try:
        path = analyze_run(runs_root / run_id, judge=not no_judge)
    except RateLimitExit as exc:
        wait = (
            f"about {int(exc.retry_after_s)} seconds" if exc.retry_after_s else "the stated window"
        )
        console.print(
            f"[yellow]Rate limited:[/] {exc}. Judgements so far are saved; "
            f"retry the same command after {wait}."
        )
        raise typer.Exit(code=RATE_LIMIT_EXIT_CODE) from None
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
def replay(
    target: Annotated[str, typer.Argument(help="RUN_ID/CELL_ID")],
    rep: int = 0,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
) -> None:
    """Replay one conversation: turns, tool calls, triggers, unlocks and discoveries."""
    run_id, _, cell_id = target.partition("/")
    if not cell_id:
        raise typer.BadParameter("expected RUN_ID/CELL_ID")
    store = RunStore(runs_root, run_id)
    if not store.has_conversation(cell_id, rep):
        raise typer.BadParameter(f"no conversation {cell_id!r} rep {rep} in run {run_id!r}")
    # printed as text: square brackets in a turn are not markup, and a long line is not wrapped
    console.print(
        replay_cell(store, cell_id, rep), markup=False, highlight=False, emoji=False, soft_wrap=True
    )


app.command("show", help="Alias of replay: the same output.")(replay)


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
    claude: list[str] | None
    try:
        claude = resolve_claude_command(None)
    except ProviderError as exc:
        claude = None
        console.print(
            f"claude command: [yellow]not usable[/] ({escape(str(exc))}); "
            "the claude_code backend is unavailable"
        )
    if claude:
        version = subprocess.run(
            [*claude, "--version"], capture_output=True, text=True, check=False
        )
        console.print(f"claude command: {escape(claude[0])} ({version.stdout.strip() or 'yes'})")
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        console.print(f"{env}: {'set' if os.environ.get(env) else 'not set'}")
    stub = StubProvider().complete("doctor", "sys", [Message(role="user", content="ping")])
    console.print(f"stub round trip: {'ok' if stub.text.endswith('ping') else 'FAILED'}")
    if live:
        if not claude:
            raise typer.Exit(code=1)
        with tempfile.TemporaryDirectory() as tmp:
            provider = ClaudeCodeProvider(model="sonnet", state_dir=Path(tmp), command=claude)
            reply = provider.complete(
                "doctor", "Reply with the single word pong.", [Message(role="user", content="ping")]
            )
        console.print(f"claude -p live call: {reply.text.strip()[:40]!r} (cost {reply.cost_usd})")
        _doctor_mcp_round_trip(claude)


def _mini_worlds_dir() -> Path | None:
    """The directory holding the ``mini`` world: the shipped worlds, else the test fixtures."""
    for base in (DATA_DIR / "worlds", REPO_ROOT / "tests" / "fixtures" / "worlds"):
        if (base / "mini" / "world.yaml").is_file():
            return base
    return None


def _doctor_mcp_round_trip(command: list[str]) -> None:
    """One real ``claude -p`` call that must reach the sandbox-tool MCP server.

    Serves the ``mini`` world's web_search and reports whether the server appended a line to
    ``tools.jsonl``, which is the proof that Claude Code launched it and called it. Exits 1 when
    no line appeared.
    """
    worlds_dir = _mini_worlds_dir()
    if worlds_dir is None:
        console.print("claude -p MCP round trip: [yellow]skipped[/] (no mini world found)")
        return
    world = load_world("mini", worlds_dir)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        mcp_dir = Path(tmp) / "mcp"
        write_mcp_state(
            mcp_dir / STATE_FILE,
            McpState(
                world="mini",
                worlds_dir=str(worlds_dir),
                config=EnvironmentConfig(world="mini", tools={"web_search"}),
                clock=world.sheet.clock,
                seed=0,
                turn=1,
                unlock=UnlockState(),
            ),
        )
        provider = ClaudeCodeProvider(
            model="sonnet", state_dir=Path(tmp), command=command, mcp_state_dir=mcp_dir
        )
        prompt = (
            "Call the web_search tool once with the query 'ferry', then reply with the word done."
        )
        try:
            reply = provider.complete(
                "doctor-mcp",
                "You are a research assistant.",
                [Message(role="user", content=prompt)],
                tools=[TOOL_SPECS["web_search"]],
            )
        except ProviderError as exc:
            console.print(f"claude -p MCP round trip: [red]FAILED[/] ({str(exc)[:200]})")
            raise typer.Exit(code=1) from exc
        log = mcp_dir / TOOLS_FILE
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    verdict = "yes" if lines else "no"
    console.print(
        f"claude -p MCP round trip: tools.jsonl line appeared: {verdict} "
        f"({len(lines)} line(s), {len(reply.tool_calls)} call(s) returned)"
    )
    if not lines:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
