### Task 8: The rate-limit wait, the `promote` real-name policy and the README chart links

Spec section 9 ("Rate-limit pause markers"), section 10 (`promote`'s policy, `readme-results --from-results`), section 11 (code item 8). One helper gives `run` and `analyze` (and Phase 5's `plan`) an in-process wait with a ceiling; `promote` blocks on a harness-side real name and reports a target-side one, with the display names and `--exempt` names spared; `--from-results` rewrites the chart links to `results/<run_id>/analysis/`.

**Files:**
- Create: `claude_bully/runner/wait.py`, `tests/test_wait_and_promote.py`
- Modify: `claude_bully/cli.py`, `claude_bully/analysis/promote.py`, `HANDOFF.md`, `docs/00-RECONCILED.md`, the spec's "As planned"
- Test: `tests/test_wait_and_promote.py`; unchanged: `tests/test_promote.py`, `tests/test_cli.py`
- Test count: 8 new tests in `tests/test_wait_and_promote.py`.

**Interfaces:**
- Consumes: `RateLimitExit` (`runner/runner.py:99`); `run`, `analyze`, `promote`, `readme_results` (`cli.py`); `promote`, `scan_run`, `load_denylist_patterns` (`analysis/promote.py`); `chat_text`, `Speaker`; `RunStore.read_tool_calls`, `read_generated`, `read_authority_calls`, `read_run`; `tests.test_real_names.REAL` (real names already present in the suite as denylist positives; the new test never writes one).
- Produces (`runner/wait.py`): `DEFAULT_WAIT_S: Final = 15 * 60`; `wait_on_rate_limit[T](action: Callable[[], T], ceiling_minutes: float | None, *, sleep: Callable[[float], None] | None = None, say: Callable[[str], None] | None = None) -> T` (`None` means `time.sleep` and `print`, looked up at call time so a test that patches `time.sleep` after the import is honoured, P26).
- Produces (`analysis/promote.py`): `REAL_NAMES_PATH: Final = DATA_DIR / "denylists" / "real_names.txt"`; `@dataclass RealNameReport(blocking: list[str], reported: list[str])`; `load_real_name_patterns(path=REAL_NAMES_PATH) -> list[re.Pattern[str]]`; `display_names(store) -> set[str]`; `scan_real_names(store, patterns, exempt: Collection[str]) -> RealNameReport`; `promote(run_id, runs_root, results_root, *, force=False, exempt: Collection[str] = ()) -> Path` (raises `ValueError` on a blocking hit).
- Produces (`cli.py`): `run --wait-on-rate-limit MINUTES`, `analyze --wait-on-rate-limit MINUTES` (both through `wait_on_rate_limit`; the exit-3 path unchanged when the ceiling is passed or absent); `promote --exempt NAME` (repeatable), printing each reported target-side hit; `readme-results --from-results` rewrites `![x](chart.png)` links to the path from the README to `results/<run_id>/analysis/chart.png`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_wait_and_promote.py
"""The rate-limit wait (Phase 7 spec section 9), promote's real-name policy and the README chart
links (section 10)."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from claude_bully import cli
from claude_bully.analysis.promote import (
    RealNameReport,
    display_names,
    load_real_name_patterns,
    promote,
    scan_real_names,
)
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import load_experiment
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.runner.wait import DEFAULT_WAIT_S, wait_on_rate_limit
from tests.test_real_names import REAL

FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "stub_smoke.yaml"
runner = CliRunner()


# ------------------------------------------------------------------ the wait


def _flaky(failures: int, retry_after: float | None = 30) -> Any:
    left = {"n": failures}

    def action() -> str:
        if left["n"]:
            left["n"] -= 1
            raise RateLimitExit("usage limit", retry_after_s=retry_after)
        return "done"

    return action


def test_the_wait_sleeps_for_retry_after_then_retries() -> None:
    slept: list[float] = []
    said: list[str] = []
    out = wait_on_rate_limit(_flaky(2), 60, sleep=slept.append, say=said.append)
    assert out == "done" and slept == [30, 30] and len(said) == 2


def test_the_wait_defaults_to_fifteen_minutes_without_retry_after() -> None:
    slept: list[float] = []
    assert wait_on_rate_limit(_flaky(1, None), 60, sleep=slept.append, say=lambda s: None) == "done"
    assert slept == [DEFAULT_WAIT_S]


def test_the_ceiling_gives_up_and_no_ceiling_never_waits() -> None:
    slept: list[float] = []
    with pytest.raises(RateLimitExit):
        wait_on_rate_limit(_flaky(3, 60 * 25), 60, sleep=slept.append, say=lambda s: None)
    assert slept == [60 * 25, 60 * 25]  # a third wait would pass the hour
    with pytest.raises(RateLimitExit):
        wait_on_rate_limit(_flaky(1), None, sleep=slept.append, say=lambda s: None)
    assert len(slept) == 2  # nothing more slept


def test_run_and_analyze_take_the_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("claude_bully.runner.wait.time.sleep", slept.append)
    calls = {"run": 0, "analyze": 0}

    def flaky_run(*args: Any, **kwargs: Any) -> Any:
        calls["run"] += 1
        if calls["run"] == 1:
            raise RateLimitExit("usage limit", retry_after_s=7)
        from claude_bully.runner.runner import RunSummary

        return RunSummary(run_id="x", cells_total=0)

    def flaky_analyze(*args: Any, **kwargs: Any) -> Path:
        calls["analyze"] += 1
        if calls["analyze"] == 1:
            raise RateLimitExit("judge usage limit", retry_after_s=9)
        return tmp_path / "results.md"

    monkeypatch.setattr(cli, "run_experiment", flaky_run)
    monkeypatch.setattr(cli, "analyze_run", flaky_analyze)
    result = runner.invoke(
        cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path), "--wait-on-rate-limit", "60"]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        cli.app, ["analyze", "x", "--runs-root", str(tmp_path), "--wait-on-rate-limit", "60"]
    )
    assert result.exit_code == 0, result.output
    assert slept == [7, 9] and calls == {"run": 2, "analyze": 2}
    without = runner.invoke(cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path)])
    assert without.exit_code == 0  # the third call succeeds at once; no flag, no wait


# ------------------------------------------------------------------ promote's policy


def _run(root: Path) -> RunStore:
    exp = load_experiment(FIXTURE)
    run_experiment(exp, runs_root=root)
    analyze_run(root / exp.name, judge=False)
    return RunStore(root, exp.name)


def _rewrite_turn(store: RunStore, cell: str, *, speaker: str, text: str) -> None:
    path = store.cell_dir(cell) / "rep0.turns.jsonl"
    lines = [json.loads(ln) for ln in path.read_text("utf-8").splitlines()]
    target = next(ln for ln in lines if ln["speaker"] == speaker)
    target["text"] = text
    path.write_text("".join(json.dumps(ln) + "\n" for ln in lines), encoding="utf-8")


def test_a_harness_side_real_name_blocks_promotion(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    _rewrite_turn(store, "grader__t0", speaker="bully", text=f"I read it in {REAL[3]} this morning.")
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert report.blocking and not report.reported
    with pytest.raises(ValueError, match="grader__t0.*bully"):
        promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert not (tmp_path / "results" / store.run_id).exists()


def test_a_target_side_real_name_is_reported_and_promoted(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    _rewrite_turn(store, "grader__t0", speaker="target", text=f"As {REAL[3]} reported, the kettle is fixed.")
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert report.reported and not report.blocking
    dest = promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert dest.exists()
    result = runner.invoke(
        cli.app,
        ["promote", store.run_id, "--force", "--runs-root", str(tmp_path / "runs"), "--results-root", str(tmp_path / "results")],
    )
    assert result.exit_code == 0 and "reported" in result.output.lower()
    assert "grader__t0" in result.output


def test_the_display_name_and_exempt_names_are_spared(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    assert "claude" in {n.lower() for n in display_names(store)}
    _rewrite_turn(store, "grader__t0", speaker="target", text="I am Claude, and that is all I will say.")
    assert scan_real_names(store, load_real_name_patterns(), display_names(store)) == RealNameReport([], [])
    _rewrite_turn(store, "grader__t0", speaker="target", text=f"My maker is {REAL[0]}.")
    report = scan_real_names(store, load_real_name_patterns(), display_names(store) | {REAL[0]})
    assert report == RealNameReport([], [])
    result = runner.invoke(
        cli.app,
        ["promote", store.run_id, "--exempt", REAL[0], "--runs-root", str(tmp_path / "runs"), "--results-root", str(tmp_path / "results")],
    )
    assert result.exit_code == 0 and "reported" not in result.output.lower()


# ------------------------------------------------------------------ the README links


def test_from_results_links_charts_under_results(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    readme = tmp_path / "README.md"
    readme.write_text("# x\n", encoding="utf-8")
    result = runner.invoke(
        cli.app,
        ["readme-results", store.run_id, "--from-results", "--results-root", str(tmp_path / "results"), "--readme", str(readme)],
    )
    assert result.exit_code == 0, result.output
    text = readme.read_text(encoding="utf-8")
    assert f"](results/{store.run_id}/analysis/" in text
    assert "](output/" not in text and "](rescue_confabulation.png)" not in text
    plain = runner.invoke(
        cli.app, ["readme-results", store.run_id, "--runs-root", str(tmp_path / "runs"), "--readme", str(readme)]
    )
    assert plain.exit_code == 0 and "](rescue_confabulation.png)" in readme.read_text("utf-8")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_wait_and_promote.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_bully.runner.wait'`.

- [ ] **Step 3: Implement**

Create `claude_bully/runner/wait.py`:

```python
"""The in-process rate-limit wait (Phase 7 spec section 9; reconciliation C37): one helper for
``run``, ``analyze`` and Phase 5's ``plan``. A ``RateLimitExit`` has already written the pause
marker and saved state, so re-running the action resumes; the helper sleeps ``retry_after_s``
(or ``DEFAULT_WAIT_S`` when none was given) and re-runs it until the next wait would pass the
ceiling, when it re-raises and the command exits 3 as before."""

import time
from collections.abc import Callable
from typing import Final

from claude_bully.runner.runner import RateLimitExit

DEFAULT_WAIT_S: Final = 15 * 60


def wait_on_rate_limit[T](
    action: Callable[[], T],
    ceiling_minutes: float | None,
    *,
    sleep: Callable[[float], None] | None = None,
    say: Callable[[str], None] | None = None,
) -> T:
    """``action()``, re-run after each rate limit until it returns or the total wait would pass
    ``ceiling_minutes``; with no ceiling the first rate limit is re-raised at once. ``sleep``
    and ``say`` default to ``time.sleep`` and ``print``, bound at call time (a default bound at
    import time would hold the real function whatever a test patched later, P26)."""
    do_sleep = sleep if sleep is not None else time.sleep
    do_say = say if say is not None else print
    waited = 0.0
    while True:
        try:
            return action()
        except RateLimitExit as exc:
            if ceiling_minutes is None:
                raise
            delay = float(exc.retry_after_s) if exc.retry_after_s else float(DEFAULT_WAIT_S)
            if waited + delay > ceiling_minutes * 60:
                raise
            do_say(f"rate limited ({exc}); waiting {int(delay)} s, {int(waited + delay)} s of {int(ceiling_minutes * 60)} s")
            do_sleep(delay)
            waited += delay
```

In `claude_bully/cli.py`: import `from claude_bully.runner.wait import wait_on_rate_limit` and `from claude_bully.analysis.promote import display_names, load_real_name_patterns, scan_real_names`; add the shared option `WaitMinutes = Annotated[float | None, typer.Option("--wait-on-rate-limit", help="Wait inside the process for a rate window, up to this many minutes.")]`; in `run`, add `wait_on_rate_limit: WaitMinutes = None` and replace the `summary = run_experiment(...)` call with `summary = wait_on_rate_limit_(lambda: run_experiment(...), wait_on_rate_limit, say=console.print)` where the helper is imported as `wait_on_rate_limit_` (the parameter name shadows it); the same in `analyze` around `analyze_run(...)`. In `promote`, add `exempt: Annotated[list[str] | None, typer.Option("--exempt", help="A name to spare from the real-name scan (the target's maker, say); repeatable.")] = None`; before `promote_run(...)`, compute the report and print it:

```python
    store = RunStore(runs_root, run_id)
    names = display_names(store) | set(exempt or [])
    report = scan_real_names(store, load_real_name_patterns(), names)
    dest = promote_run(run_id, runs_root, results_root, force=force, exempt=names)
    for hit in report.reported:
        console.print(f"[yellow]reported[/] (target text, not blocked): {escape(hit)}")
    console.print(f"promoted to {dest}")
```

In `readme_results`, when `from_results`, rewrite the links of each `results.md` before joining:

```python
        text = results_md.read_text(encoding="utf-8").strip()
        if from_results:
            analysis = root / run_id / "analysis"
            rel = Path(os.path.relpath(analysis, readme.resolve().parent)).as_posix()
            text = _CHART_LINK.sub(lambda m: f"![{m.group(1)}]({rel}/{m.group(2)})", text)
        parts.append(text)
```

with `_CHART_LINK = re.compile(r"!\[([^\]]*)\]\(([^)/]+\.png)\)")` at module level (`import re`).

In `claude_bully/analysis/promote.py`: imports `from collections.abc import Collection`, `from dataclasses import dataclass`; `from claude_bully.enums import Speaker`; `from claude_bully.records import chat_text`; add:

```python
REAL_NAMES_PATH = DATA_DIR / "denylists" / "real_names.txt"


@dataclass
class RealNameReport:
    """Real-name hits in a run (Phase 7 spec section 10): ``blocking`` (harness-side or
    world-side text: bully and task lines, tool results, generated documents, responder
    replies) and ``reported`` (the target's own text, kept and redacted in README excerpts)."""

    blocking: list[str]
    reported: list[str]


def load_real_name_patterns(path: Path = REAL_NAMES_PATH) -> list[re.Pattern[str]]:
    return load_denylist_patterns(path)


def display_names(store: RunStore) -> set[str]:
    """Every target's ``display_name`` in the run's experiment: the one real name the target may
    say of itself (docs/00 G11)."""
    targets = store.read_run().experiment.get("targets", [])
    return {str(t.get("display_name", "")) for t in targets if t.get("display_name")}


def _spared(text: str, names: Collection[str]) -> str:
    for name in names:
        if name.strip():
            text = re.sub(rf"(?<!\w){re.escape(name.strip())}(?!\w)", "", text, flags=re.IGNORECASE)
    return text


def _hits(text: str, patterns: list[re.Pattern[str]], names: Collection[str]) -> list[str]:
    spared = _spared(text, names)
    return [p.pattern for p in patterns if p.search(spared)]


def scan_real_names(
    store: RunStore, patterns: list[re.Pattern[str]], exempt: Collection[str]
) -> RealNameReport:
    report = RealNameReport([], [])
    for cell_id in store.list_cells():
        for rep in store.list_reps(cell_id):
            where = f"{cell_id} rep{rep}"
            for turn in store.read_turns(cell_id, rep):
                for hit in _hits(chat_text(turn), patterns, exempt):
                    line = f"{where} turn {turn.index} ({turn.speaker.value}): {hit}"
                    (report.reported if turn.speaker is Speaker.target else report.blocking).append(line)
            for call in store.read_tool_calls(cell_id, rep):
                report.blocking += [f"{where} tool result {call.id}: {h}" for h in _hits(call.result_text, patterns, exempt)]
            for doc in store.read_generated(cell_id, rep):
                report.blocking += [f"{where} generated {doc.doc_id}: {h}" for h in _hits(f"{doc.title}\n{doc.body}", patterns, exempt)]
            for answered in store.read_authority_calls(cell_id, rep):
                report.blocking += [f"{where} responder {answered.id}: {h}" for h in _hits(answered.response, patterns, exempt)]
    return report
```

and extend `promote(run_id, runs_root, results_root, *, force=False, exempt: Collection[str] = ())`: after `scan_run(store, load_denylist_patterns())` add:

```python
    names = display_names(store) | set(exempt)
    report = scan_real_names(store, load_real_name_patterns(), names)
    if report.blocking:
        raise ValueError(
            "harness-side text names a real name; refusing to promote: "
            + "; ".join(report.blocking[:5])
        )
```

The module docstring gains the policy: "Real names (non-negotiable 2): a hit in bully-side or task text, a tool result, a generated document or a responder reply blocks; a hit in the target's own text is reported by the CLI and kept, with the targets' ``display_name`` and any ``exempt`` name spared. README excerpts black the rest out (Phase 9)."

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_wait_and_promote.py tests/test_promote.py tests/test_cli.py -q`
Expected: PASS. `REAL[3]` is an outlet and `REAL[0]` a lab, both denylist positives that `tests/test_real_names.py` already holds; the new test imports them and writes neither literal.

- [ ] **Step 5: Docs sync**

- `HANDOFF.md`: Progress gains "Phase 7a Task 8: the rate-limit wait, promote's real-name policy, the README chart links (BASE..HEAD)"; "Owner preferences" gains nothing (the wait is how the controller runs the ladder); the non-negotiable 2 line gains "(the one stated exception: a target's own text in `results/` is reported, never blocked, and redacted in README excerpts; see the Phase 7 spec section 10)".
- `docs/00-RECONCILED.md`: section E: `run` and `analyze` gain `--wait-on-rate-limit MINUTES` (one helper, `runner/wait.py`, which `plan` takes in Phase 5); `promote` gains `--exempt NAME` and the policy; `readme-results --from-results` links charts at `results/<run_id>/analysis/`; section G11 gains "Phase 7a: `promote` spares the display names and the names passed with `--exempt`; a target-side hit is reported, a harness-side one blocks".
- The spec's "As planned": the Task 8 rulings (`--exempt` as the way the maker's name is spared without naming it anywhere; the link rewrite by `relpath`).

- [ ] **Step 6: Gate and commit**

Run: the gate.
Expected: PASS, 0 warnings.

```bash
git add claude_bully/runner/wait.py claude_bully/cli.py claude_bully/analysis/promote.py tests/test_wait_and_promote.py HANDOFF.md docs/00-RECONCILED.md docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md
git commit -m "feat: the rate-limit wait, promote's real-name policy and README charts linked from results/

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
