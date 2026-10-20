"""results.md for a run, and the README section that is regenerated from it."""

from pathlib import Path

from claude_bully.analysis.leaderboard import compliance_report, leaderboard, to_markdown
from claude_bully.analysis.load import LoadedRun

START_MARKER = "<!-- results:start -->"
END_MARKER = "<!-- results:end -->"


def write_results_md(loaded: LoadedRun, out_dir: Path, chart_paths: list[Path]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = leaderboard(loaded)
    judged = sum(1 for r in rows if r.goal_achieved is not None)
    lines = [
        f"# Results: {loaded.run.run_id}",
        "",
        f"Run created {loaded.run.created_at.date().isoformat()}"
        + (f", commit `{loaded.run.git_sha[:8]}`" if loaded.run.git_sha else "")
        + f". {len(loaded.conversations)} conversations across {len(loaded.cells)} cells; "
        f"{judged} of {len(rows)} conditions judged.",
        "",
        "## Leaderboard",
        "",
        to_markdown(rows),
        "",
        "## Bully compliance",
        "",
        compliance_report(loaded),
        "",
    ]
    if chart_paths:
        lines += ["## Charts", ""]
        for p in chart_paths:
            rel = (
                p.name
                if p.parent == out_dir
                else str(p.relative_to(out_dir.parent)).replace("\\", "/")
            )
            lines.append(f"![{p.stem}]({rel})")
            lines.append("")
    path = out_dir / "results.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def update_readme(
    readme: Path,
    results_md: Path,
    start_marker: str = START_MARKER,
    end_marker: str = END_MARKER,
) -> None:
    body = results_md.read_text(encoding="utf-8").strip()
    section = f"{start_marker}\n{body}\n{end_marker}"
    text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if start_marker in text and end_marker in text:
        head, rest = text.split(start_marker, 1)
        _, tail = rest.split(end_marker, 1)
        new = f"{head}{section}{tail}"
    else:
        new = text.rstrip() + f"\n\n{section}\n"
    readme.write_text(new, encoding="utf-8")
