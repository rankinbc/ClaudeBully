"""The rate-limit wait (Phase 7 spec section 9), promote's real-name policy and the README chart
links (section 10)."""

import json
import re
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
from claude_bully.analysis.report import END_MARKER, START_MARKER
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import load_experiment
from claude_bully.enums import Stance, Tier
from claude_bully.providers.base import ProviderTimeoutError
from claude_bully.records_env import AuthorityCall, GeneratedDoc, ToolCall
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
    calls["run"] = 0  # the next call is rate-limited again
    without = runner.invoke(cli.app, ["run", str(FIXTURE), "--runs-root", str(tmp_path)])
    assert without.exit_code == cli.RATE_LIMIT_EXIT_CODE  # no flag: exit 3 as before
    assert slept == [7, 9] and calls["run"] == 1  # and no wait, no retry


def test_a_first_wait_past_the_ceiling_gives_up_at_once() -> None:
    slept: list[float] = []
    with pytest.raises(RateLimitExit):
        wait_on_rate_limit(_flaky(1, 2 * 60 * 60), 60, sleep=slept.append, say=lambda s: None)
    assert slept == []


def test_a_timeout_is_never_waited_on() -> None:
    slept: list[float] = []

    def times_out() -> str:
        raise ProviderTimeoutError("claude -p timed out after 600s")

    with pytest.raises(ProviderTimeoutError):
        wait_on_rate_limit(times_out, 60, sleep=slept.append, say=lambda s: None)
    assert slept == []


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
    _rewrite_turn(
        store, "grader__t0", speaker="bully", text=f"I read it in {REAL[3]} this morning."
    )
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert report.blocking and not report.reported
    with pytest.raises(ValueError, match="grader__t0.*bully"):
        promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert not (tmp_path / "results" / store.run_id).exists()


def test_a_target_side_real_name_is_reported_and_promoted(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    _rewrite_turn(
        store, "grader__t0", speaker="target", text=f"As {REAL[3]} reported, the kettle is fixed."
    )
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert report.reported and not report.blocking
    dest = promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert dest.exists()
    result = runner.invoke(
        cli.app,
        [
            "promote",
            store.run_id,
            "--force",
            "--runs-root",
            str(tmp_path / "runs"),
            "--results-root",
            str(tmp_path / "results"),
        ],
    )
    assert result.exit_code == 0 and "reported" in result.output.lower()
    assert "grader__t0" in result.output


def test_the_display_name_and_exempt_names_are_spared(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    assert "claude" in {n.lower() for n in display_names(store)}
    _rewrite_turn(
        store, "grader__t0", speaker="target", text="I am Claude, and that is all I will say."
    )
    assert scan_real_names(
        store, load_real_name_patterns(), display_names(store)
    ) == RealNameReport([], [])
    _rewrite_turn(store, "grader__t0", speaker="target", text=f"My maker is {REAL[0]}.")
    report = scan_real_names(store, load_real_name_patterns(), display_names(store) | {REAL[0]})
    assert report == RealNameReport([], [])
    result = runner.invoke(
        cli.app,
        [
            "promote",
            store.run_id,
            "--exempt",
            REAL[0],
            "--runs-root",
            str(tmp_path / "runs"),
            "--results-root",
            str(tmp_path / "results"),
        ],
    )
    assert result.exit_code == 0 and "reported" not in result.output.lower()


def test_an_exempt_family_still_blocks_its_versioned_names(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    patterns = load_real_name_patterns()
    versioned = REAL[14]  # a model family followed by its version
    family = versioned.split()[0]
    _rewrite_turn(store, "grader__t0", speaker="bully", text=f"Ask {versioned} instead.")
    report = scan_real_names(store, patterns, display_names(store) | {family})
    assert len(report.blocking) == 1 and family.lower() in report.blocking[0]
    # the exempt name alone, matched whole by a pattern, is spared
    bare = REAL[9]
    _rewrite_turn(store, "grader__t0", speaker="bully", text=f"Ask {bare} instead.")
    assert scan_real_names(store, patterns, display_names(store)).blocking
    assert scan_real_names(store, patterns, display_names(store) | {bare}) == RealNameReport([], [])


def test_an_exempt_name_is_spared_in_target_text_only(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    runs, results = tmp_path / "runs", tmp_path / "results"
    maker = REAL[0]
    # the target's display name in a bully line passes
    _rewrite_turn(store, "grader__t0", speaker="bully", text="Claude, you said it yourself.")
    assert promote(store.run_id, runs, results).exists()
    # an --exempt name in a bully line still blocks (spec section 10)
    _rewrite_turn(store, "grader__t0", speaker="bully", text=f"{maker} told me so.")
    with pytest.raises(ValueError, match=r"1 hit \(1 in bully turns\)"):
        promote(store.run_id, runs, results, force=True, exempt=[maker])
    # in a target turn the same name is reported without the flag and spared with it
    _rewrite_turn(store, "grader__t0", speaker="bully", text="Say who made you.")
    _rewrite_turn(store, "grader__t0", speaker="target", text=f"{maker} made me.")
    reported: list[str] = []
    promote(store.run_id, runs, results, force=True, on_reported=reported.append)
    assert len(reported) == 1 and "(target)" in reported[0]
    reported.clear()
    promote(store.run_id, runs, results, force=True, exempt=[maker], on_reported=reported.append)
    assert reported == []


def _tool_call(text: str) -> ToolCall:
    return ToolCall(
        id="c9",
        turn=1,
        tool="web_search",
        args={"query": "kettle"},
        result_doc_ids=[],
        status="200",
        was_blocked=False,
        yielded_on_retry=False,
        layer_served=None,
        result_text=text,
    )


def _generated(text: str) -> GeneratedDoc:
    return GeneratedDoc.model_validate(
        {
            "doc_id": "gen-1-1",
            "turn": 1,
            "kind": "recovery_guide",
            "layer": "buried",
            "trigger_turn": 1,
            "source_spans": [],
            "cache_key": "k",
            "body": text,
            "title": "Notes",
            "path": "/var/log/harbour/notes/x.txt",
            "date": "2041-09-02",
            "author": "Dag Quenby",
            "links_to": [],
            "used_items": [],
            "reflexive": False,
        }
    )


def _responder(text: str) -> AuthorityCall:
    return AuthorityCall(
        id="c9",
        tier=Tier.superior_self,
        tool="consult_model",
        turn=1,
        prompt_sent="Is it true?",
        response=text,
        stance_at_time=Stance.confirm,
        discovered_via="tool_list",
    )


@pytest.mark.parametrize(
    ("stream", "label"),
    [
        ("tool", "1 in tool results"),
        ("generated", "1 in generated documents"),
        ("responder", "1 in responder replies"),
    ],
)
def test_a_real_name_in_a_world_side_stream_blocks(tmp_path: Path, stream: str, label: str) -> None:
    store = _run(tmp_path / "runs")
    text = f"As {REAL[3]} reported, the kettle is fixed."
    if stream == "tool":
        store.append_tool_call("grader__t0", 0, _tool_call(text))
    elif stream == "generated":
        store.append_generated("grader__t0", 0, _generated(text))
    else:
        store.append_authority_call("grader__t0", 0, _responder(text))
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert len(report.blocking) == 1 and not report.reported
    with pytest.raises(ValueError, match=re.escape(label)):
        promote(store.run_id, tmp_path / "runs", tmp_path / "results", exempt=[REAL[3]])
    assert not (tmp_path / "results" / store.run_id).exists()


# ------------------------------------------------------------------ email addresses

# an invented address on a domain no standard reserves: what a real one looks like to the scan
PERSONAL = "pennet.quay@zzq-invented-mail.net"
# addresses on RFC 2606 names, as the shipped worlds use them
RESERVED = (
    "support@quillmoor.example",
    "a.b@relay.test",
    "x@host.invalid",
    "y@box.localhost",
    "z@example.com",
    "w@mail.example.org",
    "v@EXAMPLE.NET",
)


def _put(store: RunStore, stream: str, text: str) -> None:
    """``text`` in one stream of ``grader__t0`` rep 0."""
    if stream in ("bully", "target"):
        _rewrite_turn(store, "grader__t0", speaker=stream, text=text)
    elif stream == "tool":
        store.append_tool_call("grader__t0", 0, _tool_call(text))
    elif stream == "generated":
        store.append_generated("grader__t0", 0, _generated(text))
    else:
        store.append_authority_call("grader__t0", 0, _responder(text))


def test_a_reserved_email_address_passes(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    _put(store, "bully", "Write to " + ", ".join(RESERVED) + " for help.")
    _put(store, "target", f"I would write to {RESERVED[0]}.")
    assert scan_real_names(
        store, load_real_name_patterns(), display_names(store)
    ) == RealNameReport([], [])
    assert promote(store.run_id, tmp_path / "runs", tmp_path / "results").exists()


@pytest.mark.parametrize(
    ("stream", "label"),
    [
        ("bully", "1 in bully turns"),
        ("target", "1 in target turns"),
        ("tool", "1 in tool results"),
        ("generated", "1 in generated documents"),
        ("responder", "1 in responder replies"),
    ],
)
def test_a_personal_email_address_blocks_in_every_stream(
    tmp_path: Path, stream: str, label: str
) -> None:
    """The CLI attaches the account's email address to every ``claude -p`` conversation (rung 0
    finding 1), so any address off a reserved domain blocks, the target's own text included."""
    store = _run(tmp_path / "runs")
    _put(store, stream, f"Mail {PERSONAL} about the kettle.")
    report = scan_real_names(store, load_real_name_patterns(), display_names(store))
    assert len(report.blocking) == 1 and not report.reported
    assert "email address" in report.blocking[0]
    assert "zzq" not in report.blocking[0] and "pennet" not in report.blocking[0]
    with pytest.raises(ValueError, match=re.escape(label)) as caught:
        promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert "zzq" not in str(caught.value) and "pennet" not in str(caught.value)
    assert not (tmp_path / "results" / store.run_id).exists()


def test_exempting_an_email_address_does_not_spare_it(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    runs, results = tmp_path / "runs", tmp_path / "results"
    _put(store, "target", f"My owner is {PERSONAL}.")
    report = scan_real_names(
        store,
        load_real_name_patterns(),
        display_names(store) | {PERSONAL},
        target_exempt=[PERSONAL],
    )
    assert len(report.blocking) == 1
    with pytest.raises(ValueError, match=r"1 hit \(1 in target turns\)"):
        promote(store.run_id, runs, results, exempt=[PERSONAL])
    args = ["promote", store.run_id, "--exempt", PERSONAL, "--runs-root", str(runs)]
    result = runner.invoke(cli.app, [*args, "--results-root", str(results)])
    assert result.exit_code != 0 and not (results / store.run_id).exists()
    assert "zzq" not in result.output


def _edit_turn(store: RunStore, speaker: str, **fields: Any) -> None:
    """Set ``fields`` on the first ``speaker`` turn of ``grader__t0`` rep 0, leaving its text."""
    path = store.cell_dir("grader__t0") / "rep0.turns.jsonl"
    lines = [json.loads(ln) for ln in path.read_text("utf-8").splitlines()]
    next(ln for ln in lines if ln["speaker"] == speaker).update(fields)
    path.write_text("".join(json.dumps(ln) + "\n" for ln in lines), encoding="utf-8")


def _judge_entry(store: RunStore, text: str) -> None:
    entry = store.run_dir / "judge_cache" / "ab" / "abcdef.json"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(json.dumps({"reply": {"rationale": text}}) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("where", "file"),
    [
        ("reasoning", "grader__t0/rep0.turns.jsonl line "),
        ("judge_cache", "judge_cache/ab/abcdef.json line 1"),
        ("bully_meta", "grader__t0/rep0.turns.jsonl line "),
    ],
)
def test_an_email_address_in_any_copied_file_blocks(tmp_path: Path, where: str, file: str) -> None:
    """Fix round 1: ``promote`` publishes every file it copies, so each one is scanned for an
    address, not only the chat text: the target's reasoning, a judge cache entry, a capture in
    the bully's meta. A block line names the file and the line, never the address."""
    store = _run(tmp_path / "runs")
    said = f"The account is {PERSONAL}."
    if where == "reasoning":
        _edit_turn(store, "target", reasoning_text=said, reasoning_available=True)
    elif where == "judge_cache":
        _judge_entry(store, said)
    else:
        _edit_turn(store, "bully", bully_meta={"capture": {"quote": said}})
    # the chat text holds no address, so the stream scan alone would pass it
    assert scan_real_names(store, load_real_name_patterns(), display_names(store)).blocking == []
    with pytest.raises(ValueError, match="email address") as caught:
        promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert file in str(caught.value)
    assert "zzq" not in str(caught.value) and "pennet" not in str(caught.value)
    assert not (tmp_path / "results").exists()  # nothing copied


def test_a_reserved_address_in_a_copied_file_passes_and_a_binary_is_not_read(
    tmp_path: Path,
) -> None:
    store = _run(tmp_path / "runs")
    _edit_turn(store, "target", reasoning_text=f"Write to {RESERVED[0]}.", reasoning_available=True)
    _judge_entry(store, " ".join(RESERVED))
    (store.run_dir / "analysis" / "notes.txt").write_text(RESERVED[4] + "\n", encoding="utf-8")
    # a chart is copied but never decoded: bytes that spell an address there are not text
    chart = store.run_dir / "analysis" / "chart.png"
    chart.write_bytes(b"\x89PNG\r\n\x1a\n" + PERSONAL.encode() + b"\x00\x01")
    dest = promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    assert (dest / "judge_cache" / "ab" / "abcdef.json").exists()
    assert (dest / "analysis" / "chart.png").read_bytes() == chart.read_bytes()


# ------------------------------------------------------------------ the README links


def test_from_results_links_charts_under_results(tmp_path: Path) -> None:
    store = _run(tmp_path / "runs")
    promote(store.run_id, tmp_path / "runs", tmp_path / "results")
    readme = tmp_path / "README.md"
    readme.write_text("# x\n", encoding="utf-8")
    result = runner.invoke(
        cli.app,
        [
            "readme-results",
            store.run_id,
            "--from-results",
            "--results-root",
            str(tmp_path / "results"),
            "--readme",
            str(readme),
        ],
    )
    assert result.exit_code == 0, result.output
    text = readme.read_text(encoding="utf-8")
    assert f"](results/{store.run_id}/analysis/" in text
    assert "](output/" not in text and "](rescue_confabulation.png)" not in text
    plain = runner.invoke(
        cli.app,
        [
            "readme-results",
            store.run_id,
            "--runs-root",
            str(tmp_path / "runs"),
            "--readme",
            str(readme),
        ],
    )
    assert plain.exit_code == 0
    # without the flag the section is results.md byte for byte, its chart links as written
    source = (store.run_dir / "analysis" / "results.md").read_text(encoding="utf-8").strip()
    assert "](rescue_confabulation.png)" in source
    section = readme.read_text("utf-8").split(START_MARKER + "\n", 1)[1]
    assert section.split("\n" + END_MARKER, 1)[0] == source
