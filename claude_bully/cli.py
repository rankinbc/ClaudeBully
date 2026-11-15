"""claude-bully command line."""

import fnmatch
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, TextIO

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from claude_bully.analysis.promote import promote as promote_run
from claude_bully.analysis.replay import replay_cell
from claude_bully.analysis.report import update_readme
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import load_experiment
from claude_bully.doctor import default_out_dir, failed, run_live_checks, write_report
from claude_bully.paths import DEFAULT_RESULTS_ROOT, DEFAULT_RUNS_ROOT, REPO_ROOT
from claude_bully.planner.cli import plan_app
from claude_bully.providers.base import Message, ProviderError
from claude_bully.providers.claude_code import clean_child_env, resolve_claude_command
from claude_bully.providers.ledger import LEDGER_FILE, activate
from claude_bully.providers.stub import StubProvider
from claude_bully.runner.cells import expand_cells
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore

# re-exported: both live in runner/wait.py, which the plan sub-app imports too (preflight Q46)
from claude_bully.runner.wait import RATE_LIMIT_EXIT_CODE as RATE_LIMIT_EXIT_CODE
from claude_bully.runner.wait import WaitMinutes as WaitMinutes
from claude_bully.runner.wait import wait_on_rate_limit as wait_on_rate_limit_
from claude_bully.strategies.bootstrap import listed_strategies

app = typer.Typer(
    help="Bully personas versus LLMs: measure behavioral drift.", no_args_is_help=True
)
console = Console()
app.add_typer(plan_app, name="plan")

RunsRoot = Annotated[Path, typer.Option(help="Where runs are written.")]
ResultsRoot = Annotated[Path, typer.Option(help="Where promoted runs live.")]
# a chart link of results.md, ``![stem](name.png)`` with no directory in the target
_CHART_LINK = re.compile(r"!\[([^\]]*)\]\(([^)/]+\.png)\)")


def _say(text: str) -> None:
    console.print(escape(text))


def _link_charts(text: str, rel: str) -> str:
    """``text`` with each chart link pointed into the directory ``rel``; other links stay."""
    return _CHART_LINK.sub(lambda m: f"![{m.group(1)}]({rel}/{m.group(2)})", text)


@app.command()
def run(
    config: Annotated[Path, typer.Argument(help="Experiment YAML.")],
    run_id: Annotated[str | None, typer.Option(help="Defaults to the experiment name.")] = None,
    only: Annotated[str | None, typer.Option(help="fnmatch glob on cell ids.")] = None,
    max_cells: Annotated[int | None, typer.Option(help="Run at most this many cells.")] = None,
    dry_run: Annotated[bool, typer.Option(help="List cells and exit.")] = False,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
    wait_on_rate_limit: WaitMinutes = None,
) -> None:
    """Run (or resume) an experiment. Exit code 3 means a rate limit paused it."""
    exp = load_experiment(config)
    if only is not None and not any(fnmatch.fnmatch(c.cell_id, only) for c in expand_cells(exp)):
        raise typer.BadParameter(f"{only!r} matches no cell of {exp.name!r}", param_hint="--only")
    try:
        summary = wait_on_rate_limit_(
            lambda: run_experiment(
                exp,
                runs_root=runs_root,
                run_id=run_id,
                only=only,
                max_cells=max_cells,
                dry_run=dry_run,
                console=console,
            ),
            wait_on_rate_limit,
            say=_say,
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
    authority_fallback: Annotated[
        bool,
        typer.Option(
            "--authority-fallback",
            help="Ask the judge on the authority family's candidate turns "
            "(cache-only with --no-judge).",
        ),
    ] = False,
    ratings: Annotated[
        bool,
        typer.Option(
            "--ratings",
            help="Ask the judge the four rating prompts (Phase 4); needs the judge.",
        ),
    ] = False,
    hypotheses: Annotated[
        bool,
        typer.Option(
            "--hypotheses",
            help="Evaluate the hypothesis register against this run (docs/06).",
        ),
    ] = False,
    wait_on_rate_limit: WaitMinutes = None,
) -> None:
    """Recompute metrics, events, judge verdicts and charts from JSONL."""
    try:
        path = wait_on_rate_limit_(
            lambda: analyze_run(
                runs_root / run_id,
                judge=not no_judge,
                authority_fallback=authority_fallback,
                ratings=ratings,
                hypotheses=hypotheses,
            ),
            wait_on_rate_limit,
            say=_say,
        )
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
    rows = sorted(listed_strategies().values(), key=lambda c: (c.axis.value, c.name))
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


@contextmanager
def utf8_stdout(stream: TextIO | None = None) -> Iterator[None]:
    """Write UTF-8 to ``stream`` (default ``sys.stdout``) inside the block, whatever its encoding.

    Redirected output on Windows is cp1252, which cannot encode what a target says (arrows, check
    marks, emoji, CJK). A character the stream cannot hold is replaced, never raised. The stream's
    own encoding is restored afterwards; a stream that cannot be reconfigured is left alone.
    """
    out = sys.stdout if stream is None else stream
    reconfigure = getattr(out, "reconfigure", None)
    if reconfigure is None:
        yield
        return
    previous = (out.encoding, out.errors)
    out.flush()
    reconfigure(encoding="utf-8", errors="replace")
    try:
        yield
    finally:
        out.flush()
        reconfigure(encoding=previous[0], errors=previous[1])


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
    text = replay_cell(store, cell_id, rep)
    # printed as text: square brackets in a turn are not markup, and a long line is not wrapped
    with utf8_stdout():
        console.print(text, markup=False, highlight=False, emoji=False, soft_wrap=True)


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
        text = results_md.read_text(encoding="utf-8").strip()
        if from_results:
            # the committed images, linked from the README's own directory (C17, I46)
            analysis = (root / run_id / "analysis").resolve()
            try:
                rel = Path(os.path.relpath(analysis, readme.resolve().parent)).as_posix()
            except ValueError:  # Windows: no relative path between two drives
                raise typer.BadParameter(
                    f"{analysis} and {readme} are on different drives; no relative chart link"
                ) from None
            text = _link_charts(text, rel)
        parts.append(text)
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
    exempt: Annotated[
        list[str] | None,
        typer.Option(
            "--exempt",
            help=(
                "A name to spare from the real-name scan in the target's own text only (the "
                "target's maker, say); display names are spared everywhere. Repeatable."
            ),
        ),
    ] = None,
) -> None:
    """Copy a finished run into results/ (committed), after a denylist and real-name scan."""
    dest = promote_run(
        run_id,
        runs_root,
        results_root,
        force=force,
        exempt=exempt or (),
        on_reported=lambda hit: console.print(
            f"[yellow]reported[/] (target text, not blocked): {escape(hit)}"
        ),
    )
    console.print(f"promoted to {dest}")


@app.command()
def doctor(
    live: Annotated[
        bool, typer.Option("--live", help="Run the live preflights (about ten claude -p calls).")
    ] = False,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out", help="Where the live report goes (default output/doctor_live_<date>/)."
        ),
    ] = None,
    runs_root: RunsRoot = DEFAULT_RUNS_ROOT,
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
        # under the scrubbed environment, as every child claude -p runs (P12)
        version = subprocess.run(
            [*claude, "--version"],
            capture_output=True,
            text=True,
            check=False,
            env=clean_child_env(),
        )
        console.print(f"claude command: {escape(claude[0])} ({version.stdout.strip() or 'yes'})")
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        console.print(f"{env}: {'set' if os.environ.get(env) else 'not set'}")
    stub = StubProvider().complete("doctor", "sys", [Message(role="user", content="ping")])
    console.print(f"stub round trip: {'ok' if stub.text.endswith('ping') else 'FAILED'}")
    if not live:
        return
    if not claude:
        raise typer.Exit(code=1)
    # REPO_ROOT is read here, at call time, so a test can point the disk check at a temporary
    # repo (P22); the runs root is the option every other command takes
    out_dir = out if out is not None else default_out_dir(REPO_ROOT)
    out_dir.mkdir(parents=True, exist_ok=True)
    # each run starts on an empty ledger: a rerun into the same day's dir reports its own calls
    (out_dir / LEDGER_FILE).unlink(missing_ok=True)
    with activate(out_dir / LEDGER_FILE) as ledger:
        results = run_live_checks(claude, runs_root=runs_root, repo_root=REPO_ROOT)
        report = write_report(out_dir, results, ledger)
    for result in results:
        mark = "ok" if result.ok else "FAILED"
        console.print(f"{result.name}: {mark} ({escape(result.detail)})", highlight=False)
    console.print(f"report: {report}")
    if failed(results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
