# tests/test_director_review.py
"""Phase 5 Task 8: stages 3 and 4 on stubs (spec section 7), resume parity at K8 to K10 and at
the review render (R-review-md), and the reasoning sentinel end to end (D-sentinel)."""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

from claude_bully.enums import Layer
from claude_bully.planner import bundle as bundle_module
from claude_bully.planner.bundle import Bundle
from claude_bully.planner.bundle_lints import review_scans
from claude_bully.planner.context import ReviewGroup, unchanged_base_files
from claude_bully.planner.director import (
    CONFIRM_SCHEMA,
    REVIEW_CHUNK_DOCS,
    REVIEW_GROUPS,
    REVIEW_SCHEMA,
    REVISE_SCHEMA,
    Director,
    check_findings,
    findings_of,
    render_review,
    review_calls,
    review_groups,
)
from claude_bully.planner.lints import owner_names
from claude_bully.planner.records import ManifestEntry, ReviewFinding
from claude_bully.runner.runner import RateLimitExit
from tests.fixtures.bundle_fixtures import good_bundle
from tests.fixtures.director_stub import (
    REQUEST,
    Crash,
    Kill,
    PlannerStub,
    ReviewerStub,
    StubFactory,
    cache_keys,
    comparable,
    hashed_files,
    run_plan,
)
from tests.helpers import WORLDS_DIR

RENDERED = (
    "block 1 / fix 1 / note 1\n"
    "\n"
    "## personas/ferry_caller.yaml\n"
    '- [2] note: "{note_quote}" {note_problem}\n'
    "\n"
    "## plan.md\n"
    '- [3] fix: "{fix_quote}" {fix_problem} (direction: {direction})\n'
    "  - response (fixed): {fix_response}\n"
    "\n"
    "## {doc1}\n"
    '- [1] block: "{block_quote}" {block_problem}\n'
    "  - response (fixed): {block_response}\n"
    "  - confirm: absent (closed)\n"
)


def test_the_review_groups_chunk_the_corpus_and_name_the_unchanged_files(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    groups = review_groups(bundle, bundle.read_record())
    assert [g.name for g in groups] == ["corpus-1", "lines", "plan"]
    corpus = groups[0]
    assert len(corpus.files) <= REVIEW_CHUNK_DOCS
    unchanged = {"worlds/mini/corpus/ferry-about.md", "worlds/mini/corpus/night-gate-log.md"}
    assert (
        unchanged.isdisjoint(corpus.files) and len(corpus.index) >= 2
    )  # base files, by index line
    assert groups[2].files == ("plan.md", "config.yaml", "expected.yaml")


@pytest.mark.slow  # a plan through stage 4
def test_a_clean_review_and_revision(tmp_path: Path, isolated_registry: None) -> None:
    reviewer = ReviewerStub()
    bundle, record = run_plan(tmp_path, through="revise", reviewer=reviewer)
    assert record.review_counts == {"block": 1, "fix": 1, "note": 1}
    assert record.open_blocks == 0 and record.status == "revised"
    revise = record.stages[3]
    assert [c.purpose for c in revise.calls] == [
        "revise:plan.md",
        f"revise:{_doc1()}",
        f"confirm:{_doc1()}",
    ]  # path order, then one confirm per file that had a block
    review = bundle.read_file("review.md")
    assert (
        review.startswith("block 1 / fix 1 / note 1\n") and "- confirm: absent (closed)" in review
    )
    # blindness at confirm time (spec section 6; review I8): no planner response text or status
    responses = [
        r["text"]
        for c in revise.calls
        if c.purpose.startswith("revise:")
        for r in json.loads(bundle.read_transcript(c.transcript).attempts[-1].reply)["responses"]
    ]
    confirms = [m for _, _, m in reviewer.calls if re.search(r"^call: confirm:", m, re.M)]
    assert responses and confirms
    for message in confirms:
        assert not [text for text in responses if text in message]
        assert "response (" not in message and "planner_status" not in message
        assert '"status"' not in message


def _doc1() -> str:
    from tests.test_director_author import DOC1

    return DOC1


@pytest.mark.slow  # two plans through stage 3 per case (preflight Q68)
@pytest.mark.parametrize(
    "mode", ["not_in_group", "no_quote_block", "quote_missing", "counts_wrong", "empty_no_summary"]
)
def test_a_review_reply_the_harness_cannot_read_is_retried_then_fails_the_stage(
    mode: str, tmp_path: Path, isolated_registry: None
) -> None:
    _, once = run_plan(
        tmp_path / "once", through="review", reviewer=ReviewerStub(modes={"review:corpus-1": mode})
    )
    assert once.stages[2].status == "committed" and once.stages[2].calls[0].attempts == 2
    _, twice = run_plan(
        tmp_path / "twice",
        through="review",
        reviewer=ReviewerStub(modes={"review:corpus-1": f"{mode}:twice"}),
    )
    assert twice.stages[2].status == "failed" and twice.status == "failed"  # never "no findings"


@pytest.mark.slow  # a plan through stage 4
def test_an_explicit_zero_summary_is_a_clean_review(
    tmp_path: Path, isolated_registry: None
) -> None:
    modes = {g: "clean" for g in ("review:corpus-1", "review:lines", "review:plan")}
    _, record = run_plan(tmp_path, through="revise", reviewer=ReviewerStub(modes=modes))
    assert record.review_counts == {"block": 0, "fix": 0, "note": 0}
    assert record.stages[3].calls == []


@pytest.mark.slow  # a plan through stage 4 per case
@pytest.mark.parametrize(
    ("planner_mode", "verdict", "closed"),
    [
        (None, "absent", True),
        ("declined", "absent", False),
        ("keep_quote", "absent", False),
        (None, "present", False),
        (None, "cannot_tell", False),
        (None, "missing", False),
        (None, "error", False),
    ],
)
def test_a_block_closes_only_when_three_things_agree(
    planner_mode: str | None, verdict: str, closed: bool, tmp_path: Path, isolated_registry: None
) -> None:
    doc1 = _doc1()
    planner = PlannerStub(modes={f"revise:{doc1}": planner_mode} if planner_mode else {})
    if verdict == "missing":
        reviewer = ReviewerStub(modes={f"confirm:{doc1}": "missing"})
    elif verdict == "error":
        # preflight Q43: a confirm call that errors twice is two failed checks; a provider
        # error fails the stage (spec section 13), its own test below
        reviewer = ReviewerStub(modes={f"confirm:{doc1}": "off_contract:twice"})
    else:
        reviewer = ReviewerStub(verdicts={1: verdict})
    _, record = run_plan(tmp_path, through="revise", planner=planner, reviewer=reviewer)
    assert (record.open_blocks == 0) is closed
    assert record.status == ("revised" if closed else "failed")


@pytest.mark.slow  # a plan through stage 4
def test_a_revise_reply_must_answer_every_block_and_fix_once(
    tmp_path: Path, isolated_registry: None
) -> None:
    planner = PlannerStub(modes={"revise:plan.md": "no_response:twice"})
    _, record = run_plan(tmp_path, through="revise", planner=planner)
    call = next(c for c in record.stages[3].calls if c.purpose == "revise:plan.md")
    assert call.status == "error" and "finding 3" in (call.error or "")
    assert record.stages[3].status == "committed"  # D-revise-error: the stage goes on


def test_render_review_is_the_fixed_format() -> None:
    findings = [
        ReviewFinding(
            id=1,
            severity="block",
            file="worlds/w/corpus/a.md",
            quote="Q1",
            problem="P1",
            response="R1",
            planner_status="fixed",
            confirm="absent",
            open=False,
        ),
        ReviewFinding(
            id=2,
            severity="note",
            file="personas/ferry_caller.yaml",
            quote="Q2",
            problem="P2",
            open=False,
        ),
        ReviewFinding(
            id=3,
            severity="fix",
            file="plan.md",
            quote="Q3",
            problem="P3",
            direction="D3",
            response="R3",
            planner_status="fixed",
            open=False,
        ),
    ]
    assert render_review(findings) == RENDERED.format(
        note_quote="Q2",
        note_problem="P2",
        fix_quote="Q3",
        fix_problem="P3",
        direction="D3",
        fix_response="R3",
        doc1="worlds/w/corpus/a.md",
        block_quote="Q1",
        block_problem="P1",
        block_response="R1",
    )


KILLS: dict[str, dict[str, Any]] = {
    "K8": dict(reviewer_crash="review:lines", dead=("review", "reviewer", 1)),
    # R-review-md: review.md written, the stage not yet committed; the resume renders it again
    # and stage 4's inputs hold it, as an unbroken plan's do (review I4)
    "K8-rendered": dict(kill=Kill("rendered", "review"), dead=None),
    "K9a": dict(planner_crash="revise:{doc1}", dead=("revise", "planner", 1)),
    "K9b": dict(kill=Kill("record", "revise:{doc1}"), dead=None),
    "K10": dict(reviewer_crash="confirm:{doc1}", dead=("revise", "reviewer", 2)),
    # stage 4's render, written over the review.md its inputs hold, before the stage commits:
    # the resume keeps the sha the stage opened with (the probe sweep's one mismatch)
    "K10-rendered": dict(kill=Kill("rendered", "revise"), dead=None),
}


@pytest.mark.slow
@pytest.mark.parametrize("point", list(KILLS))
def test_a_plan_killed_at_k8_to_k10_resumes_byte_equal(
    point: str, tmp_path: Path, isolated_registry: None
) -> None:
    doc1 = _doc1()
    spec = {k: (v.format(doc1=doc1) if isinstance(v, str) else v) for k, v in KILLS[point].items()}
    if isinstance(spec.get("kill"), Kill):
        spec["kill"] = Kill(spec["kill"].step, spec["kill"].purpose.format(doc1=doc1))
    dead = spec.pop("dead")
    clean_bundle, clean = run_plan(tmp_path / "clean", through="revise")
    planner = PlannerStub(crash_at=spec.pop("planner_crash", None))
    reviewer = ReviewerStub(crash_at=spec.pop("reviewer_crash", None))
    bundle, record = run_plan(
        tmp_path / "killed", through="revise", planner=planner, reviewer=reviewer, **spec
    )
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)
    assert [(a.stage, a.role, a.index) for a in record.resumed] == ([dead] if dead else [])
    if point == "K9a":  # the redone revise call was shown the committed pre-revision file
        from tests.fixtures.bundle_fixtures import GOOD

        redone = [m for _, _, m in planner.calls if f"call: revise:{doc1}" in m]
        assert redone and all((GOOD / doc1).read_text("utf-8") in m for m in redone)
    clean_keys, killed_keys = cache_keys(tmp_path / "clean"), cache_keys(tmp_path / "killed")
    if point == "K9b":  # committed, never asked again: the put did not happen
        assert len(clean_keys - killed_keys) == 1 and killed_keys < clean_keys
    else:
        assert killed_keys == clean_keys


@pytest.mark.slow
def test_no_reasoning_channel_reaches_any_prompt_transcript_file_or_record(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-negotiable 6 (spec section 15): a runs/ root holding a conversation whose
    reasoning_text is a sentinel, and planner and reviewer doubles whose completions carry a
    second; neither string is in anything the Director wrote or sent."""
    from claude_bully import cli, paths

    run_sentinel, own_sentinel = "SENTINEL-RUN-REASONING-0b1e", "SENTINEL-DIRECTOR-REASONING-77d2"
    runs, results = tmp_path / "runs", tmp_path / "results"
    (runs / "r" / "cell__t0").mkdir(parents=True)
    (runs / "r" / "cell__t0" / "rep0.jsonl").write_text(
        json.dumps({"index": 1, "speaker": "target", "text": "x", "reasoning_text": run_sentinel})
        + "\n",
        "utf-8",
    )
    (results / "r").mkdir(parents=True)
    (results / "r" / "results.md").write_text(f"{run_sentinel}\n", "utf-8")
    # review I8: the defaults point at the planted roots, so a Director path that read a run or
    # a result would find the sentinel (Task 6 pins that no planner module names either root)
    for module in (paths, cli):
        monkeypatch.setattr(module, "DEFAULT_RUNS_ROOT", runs)
        monkeypatch.setattr(module, "DEFAULT_RESULTS_ROOT", results)
    planner, reviewer = PlannerStub(reasoning=own_sentinel), ReviewerStub(reasoning=own_sentinel)
    run_plan(tmp_path / "plans", through="revise", planner=planner, reviewer=reviewer)
    sent = [s + m for _, s, m in planner.calls + reviewer.calls]
    # every file the Director wrote: the bundle and the cache under plans/_cache/director/
    written = [
        p.read_text("utf-8", errors="replace")
        for p in (tmp_path / "plans").rglob("*")
        if p.is_file()
    ]
    assert any((tmp_path / "plans" / "_cache" / "director").rglob("*"))
    for text in sent + written:
        assert run_sentinel not in text and own_sentinel not in text


# ---------------------------------------------------------------- beyond the brief's tests


@pytest.mark.slow  # a plan through stage 4, failed, then continued
def test_a_provider_error_on_a_confirm_call_fails_stage_4_and_continue_closes_the_block(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Preflight Q43: spec section 13 governs a provider error on any call, a confirm call's
    included: the call is an error, stage 4 and the plan fail, and the same command again
    retries stage 4 from that call, which closes the block."""
    doc1 = _doc1()
    planner, reviewer = PlannerStub(), ReviewerStub(modes={f"confirm:{doc1}": "provider_error"})
    bundle, failed = run_plan(tmp_path, through="revise", planner=planner, reviewer=reviewer)
    assert failed.status == "failed" and failed.stages[3].status == "failed"
    assert f"confirm:{doc1}" in (failed.stages[3].error or "")
    assert failed.stages[3].calls[-1].provider_failed
    _, record = run_plan(tmp_path, through="revise", planner=planner, reviewer=reviewer)
    assert record.status == "revised" and record.open_blocks == 0 and record.resumed == []
    assert [c.purpose for c in record.stages[3].calls][-1] == f"confirm:{doc1}"
    assert (bundle.root / "transcripts" / "failed" / "revise-reviewer-2.json").is_file()


@pytest.mark.slow  # a plan through stage 4
def test_no_reviewer_or_confirm_message_holds_review_md(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Task 6, carried: the reviewer and confirm calls never see review.md, which holds the
    planner's responses after a revise round; the confirm prompt carries no revision cue
    (D-confirm)."""
    reviewer = ReviewerStub()
    bundle, _ = run_plan(tmp_path, through="revise", reviewer=reviewer)
    rendered = bundle.read_file("review.md")
    assert "## personas/ferry_caller.yaml" in rendered
    for _, _, message in reviewer.calls:
        assert "block 1 / fix 1 / note 1" not in message and "review.md" not in message
        assert "\n## personas/ferry_caller.yaml\n- [2] note:" not in message  # review.md's lines
    confirm = [(s, m) for _, s, m in reviewer.calls if "\ncall: confirm:" in m]
    assert confirm
    for system, message in confirm:
        for cue in ("revis", "earlier", "version", "fixed", "planner", "declined", "response"):
            assert cue not in (system + message).lower(), cue


def _owner() -> str:
    return sorted(owner_names())[0].title()  # read at run time: on no checked-in list


@pytest.mark.slow  # a plan through stage 2, then stage 3
def test_a_denylist_hit_blocks_the_reviewer_call_as_a_lint_failure(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Task 6 re-review R1, carried: before each reviewer call the bundle is scanned (the
    real-name list with its owner clause, the Boundary list, the jailbreak list); a hit fails
    the stage before any reviewer call, and the owner's name is never copied into the record."""
    for rel, line, lint in (
        ("plan.md", f"Signed, {_owner()}.", "real_name_bundle"),
        ("personas/ferry_caller.yaml", "# the guidelines say so\n", "boundary_bundle"),
    ):
        root = tmp_path / lint
        reviewer = ReviewerStub()
        bundle, _ = run_plan(root, through="author", reviewer=reviewer)
        path = bundle.root / rel
        path.write_text(path.read_text("utf-8") + f"\n{line}\n", "utf-8")
        _, record = run_plan(root, through="review", reviewer=reviewer)
        assert record.status == "failed" and record.stages[2].calls == []
        assert f"{lint}: " in (record.stages[2].error or "") and reviewer.calls == []
        assert _owner().lower() not in (bundle.root / "plan.json").read_text("utf-8").lower()
        assert record.edited == [rel]  # the edit was adopted at the stage's open


class _NamingPlanner(PlannerStub):
    """A planner whose revision of plan.md signs it with the owner's name: plan.md's arrival
    check is its size, so only the scan before the confirm call catches it."""

    def _reply(self, purpose: str, mode: str | None) -> str:
        reply = super()._reply(purpose, mode)
        if purpose == "revise:plan.md":
            data = json.loads(reply)
            data["content"] += f"\nSigned, {_owner()}.\n"
            return json.dumps(data)
        return reply


@pytest.mark.slow  # a plan through stage 4
def test_a_denylist_hit_blocks_the_confirm_call_as_a_lint_failure(
    tmp_path: Path, isolated_registry: None
) -> None:
    reviewer = ReviewerStub()
    _, record = run_plan(tmp_path, through="revise", planner=_NamingPlanner(), reviewer=reviewer)
    assert record.status == "failed" and record.stages[3].status == "failed"
    assert "real_name_bundle: " in (record.stages[3].error or "")
    assert [c.purpose for c in record.stages[3].calls] == ["revise:plan.md", f"revise:{_doc1()}"]
    assert not [m for _, _, m in reviewer.calls if "\ncall: confirm:" in m]


def test_the_scans_before_a_reviewer_call_never_raise(
    tmp_path: Path, isolated_registry: None
) -> None:
    """A file that is no UTF-8 or no YAML is read replaced and scanned; the scans report and
    never raise (``schema`` is the lint that names such a file)."""
    bundle = good_bundle(tmp_path)
    assert review_scans(bundle, bundle.read_record()) == []
    (bundle.root / "personas" / "ferry_caller.yaml").write_bytes(b"name: [\xff\xfe guidelines\n")
    found = review_scans(bundle, bundle.read_record())
    assert [(r.lint_id, r.doc_id) for r in found] == [
        ("boundary_bundle", "personas/ferry_caller.yaml")
    ]


def _overlay_plus_two(tmp_path: Path) -> tuple[Director, list[ManifestEntry]]:
    """The shipped overlay reused (46 documents, unchanged) with two new documents."""
    request = REQUEST.model_copy(update={"base_world": "overlay"})
    director = Director.new(
        request,
        plans_root=tmp_path,
        provider_factory=StubFactory(PlannerStub(), ReviewerStub()),
        say=lambda _: None,
    )
    director.run(through="plan")
    director._copy_worlds(["overlay"])
    entries = [
        ManifestEntry(path=p, kind=k, purpose="p", layer=layer)
        for p, k, layer in (
            ("worlds/overlay/corpus/zz-new-a.md", "document", Layer.filler),
            ("worlds/overlay/corpus/zz-new-b.md", "document", Layer.seam),
            ("config.yaml", "config", None),
            ("expected.yaml", "expected", None),
        )
    ]
    director.record.manifest = entries
    for entry in entries:
        director.bundle.write_file(entry.path, f"{entry.path}\n")
    return director, entries


def test_the_budget_counts_one_review_call_per_review_group(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Task 7b round 2, carried: the manifest's budget counts the review calls by the rule
    stage 3 groups by (``context.unchanged_base_files``, the rule's one home)."""
    bundle = good_bundle(tmp_path / "good")
    record = bundle.read_record()
    director = Director(bundle, record, worlds_dir=WORLDS_DIR)
    assert director._review_calls(record.manifest) == len(review_groups(bundle, record)) == 3
    overlay, entries = _overlay_plus_two(tmp_path / "overlay")
    groups = review_groups(overlay.bundle, overlay.record)
    assert overlay._review_calls(entries) == len(groups) == 2
    assert [(g.name, g.files) for g in groups] == [
        ("corpus-1", ("worlds/overlay/corpus/zz-new-a.md", "worlds/overlay/corpus/zz-new-b.md")),
        ("plan", ("plan.md", "config.yaml", "expected.yaml")),
    ]
    unchanged = unchanged_base_files(overlay.record.base_files, entries)
    corpus = [rel for rel in unchanged if "/corpus/" in rel]
    assert len(corpus) > REVIEW_CHUNK_DOCS and groups[0].index == tuple(corpus)


def test_a_corpus_over_the_chunk_size_is_reviewed_in_chunks(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    record = bundle.read_record()
    for n in range(REVIEW_CHUNK_DOCS + 1 - 8):  # the good bundle's 8 reviewed documents, then 18
        bundle.write_file(f"worlds/mini/corpus/zz-{n:02}.md", "x\n")
    groups = review_groups(bundle, record)
    assert [(g.name, len(g.files)) for g in groups] == [
        ("corpus-1", REVIEW_CHUNK_DOCS),
        ("corpus-2", 1),
        ("lines", 3),
        ("plan", 3),
    ]
    unchanged = set(unchanged_base_files(record.base_files, record.manifest))
    assert len(groups) == review_calls(set(bundle.index()) - unchanged)
    assert {g.name.split("-")[0] for g in groups} == set(REVIEW_GROUPS)


def _group(bundle: Bundle, name: str) -> ReviewGroup:
    return next(g for g in review_groups(bundle, bundle.read_record()) if g.name == name)


def _reply(findings: list[dict[str, Any]], summary: dict[str, int] | None = None) -> str:
    counts = {s: sum(f["severity"] == s for f in findings) for s in ("block", "fix", "note")}
    return json.dumps({"summary": counts if summary is None else summary, "findings": findings})


def test_check_findings_refuses_each_case_and_passes_its_near_miss(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Spec section 7 stage 3's refusals, each beside a near miss that passes: a quote is
    looked for whitespace-squashed, so one quoted across a line break is found; a fix or a note
    may quote nothing, a block may not."""
    bundle = good_bundle(tmp_path)
    group = _group(bundle, "plan")
    plan = "Does the target take on the night crew's account of the harbour more often when it"

    def finding(severity: str, quote: str, file: str = "plan.md") -> dict[str, Any]:
        return {
            "severity": severity,
            "file": file,
            "quote": quote,
            "problem": "p",
            "direction": None,
        }

    cases: list[tuple[str, str]] = [
        (_reply([finding("note", plan)]), ""),
        (_reply([finding("fix", "it earned the buried documents")]), ""),  # across a line break
        (_reply([finding("note", "")]), ""),
        (_reply([finding("block", "")]), "finding 1: a block quotes"),
        (_reply([finding("block", "  \n ")]), "finding 1: a block quotes"),
        (_reply([finding("note", "it earned theburied")]), "finding 1: its quote is not text"),
        (_reply([finding("note", plan, "personas/ferry_caller.yaml")]), "finding 1: "),
        (_reply([finding("note", plan, "review.md")]), "is not a file of this group"),
        (_reply([finding("note", plan)], {"block": 1, "fix": 0, "note": 1}), "the summary counts"),
        (json.dumps({"findings": []}), "no summary"),
        (_reply([]), ""),
        ("not json", "is not the JSON object"),
        (
            json.dumps({"summary": {"block": 0, "fix": 0, "note": 0}, "findings": [], "x": 1}),
            "JSON",
        ),
    ]
    for reply, refused in cases:
        findings, failures = check_findings(reply, group, bundle)
        if refused:
            assert len(failures) == 1 and refused in failures[0], (reply, failures)
        else:
            assert failures == [], (reply, failures)
            assert all(f.id == 0 for f in findings)


def test_the_reply_schemas_are_closed() -> None:
    for schema in (REVIEW_SCHEMA, REVISE_SCHEMA, CONFIRM_SCHEMA):
        assert schema["additionalProperties"] is False
    item = REVIEW_SCHEMA["properties"]["findings"]["items"]
    assert item["required"] == ["severity", "file", "quote", "problem", "direction"]
    assert REVIEW_SCHEMA["required"] == ["summary", "findings"]
    verdict = CONFIRM_SCHEMA["properties"]["verdicts"]["items"]["properties"]
    assert verdict["verdict"]["enum"] == ["present", "absent", "cannot_tell"]
    response = REVISE_SCHEMA["properties"]["responses"]["items"]["properties"]
    assert response["status"]["enum"] == ["fixed", "declined"]


@pytest.mark.slow  # a plan through stage 4
def test_findings_of_reads_the_committed_calls_alone(
    tmp_path: Path, isolated_registry: None
) -> None:
    """R-review-md: review.md is derived from the committed calls' transcripts, so it is the
    render of findings_of whatever the bundle's files hold now."""
    bundle, record = run_plan(tmp_path, through="revise")
    findings = findings_of(bundle, record)
    assert [(f.id, f.severity, f.file) for f in findings] == [
        (1, "block", _doc1()),
        (2, "note", "personas/ferry_caller.yaml"),
        (3, "fix", "plan.md"),
    ]
    assert render_review(findings) == bundle.read_file("review.md")
    bundle.write_file(_doc1(), "edited by hand\n")
    assert findings_of(bundle, record) == findings


def _leave_temp(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, _ = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "wb") as handle:
        handle.write(text.encode("utf-8")[: max(1, len(text) // 2)])


@pytest.mark.slow
@pytest.mark.parametrize("nth", [1, 2])  # stage 3's render, then stage 4's
def test_a_hard_kill_inside_the_review_md_write_resumes_byte_equal(
    nth: int, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean_bundle, clean = run_plan(tmp_path / "clean", through="revise")
    real = bundle_module.write_atomic
    seen: list[Path] = []

    def dying(path: Path, text: str) -> None:
        if path.name == "review.md":
            seen.append(path)
            if len(seen) == nth:
                _leave_temp(path, text)
                raise Crash("killed inside the write of review.md")
        real(path, text)

    monkeypatch.setattr(bundle_module, "write_atomic", dying)
    bundle, record = run_plan(tmp_path / "killed", through="revise")
    assert not list((tmp_path / "killed").rglob("*.tmp"))
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean) and record.resumed == []


@pytest.mark.slow  # a plan through stage 4
def test_a_revision_that_breaks_its_world_is_repaired_and_the_repair_is_the_file_confirmed(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Stage 4 closes each world of a revised file again, within the MAX_REPAIR_CALLS stage 2
    left (preflight Q40): a revision that links a missing document gets one repair:<path> call
    in the revise stage, and the block is judged on the file as the repair left it (here the
    good text, its quote back in), so it stays open."""
    doc1 = _doc1()
    planner, reviewer = PlannerStub(modes={f"revise:{doc1}": "close_fail"}), ReviewerStub()
    bundle, record = run_plan(tmp_path, through="revise", planner=planner, reviewer=reviewer)
    assert [c.purpose for c in record.stages[3].calls] == [
        "revise:plan.md",
        f"revise:{doc1}",
        f"repair:{doc1}",
        f"confirm:{doc1}",
    ]
    assert [c.role for c in record.stages[3].calls] == ["planner", "planner", "planner", "reviewer"]
    (block,) = [f for f in findings_of(bundle, record) if f.severity == "block"]
    assert block.planner_status == "fixed" and block.confirm == "absent" and block.open
    assert record.open_blocks == 1 and record.status == "failed"
    assert record.stages[3].status == "committed"
    confirm = next(m for _, _, m in reviewer.calls if f"\ncall: confirm:{doc1}" in m)
    assert block.quote in confirm.split("\n## Passages\n")[0]  # shown the repaired file


@pytest.mark.slow  # three plans through stage 4
@pytest.mark.parametrize("purpose", ["review:lines", "confirm:{doc1}"])
def test_a_rate_limited_review_or_confirm_call_pauses_and_resumes_to_the_unbroken_plan(
    purpose: str, tmp_path: Path, isolated_registry: None
) -> None:
    """Phase 4's lesson, carried: a rate limit pauses and never degrades. It commits nothing,
    leaves the stage open and raises RateLimitExit; the same command again ends as an unbroken
    plan ends, with no dead attempt."""
    purpose = purpose.format(doc1=_doc1())
    clean_bundle, clean = run_plan(tmp_path / "clean", through="revise")
    planner, reviewer = PlannerStub(), ReviewerStub(modes={purpose: "rate_limit"})
    with pytest.raises(RateLimitExit):
        run_plan(tmp_path / "paused", through="revise", planner=planner, reviewer=reviewer)
    stage = "review" if purpose.startswith("review:") else "revise"
    paused = Bundle(tmp_path / "paused" / clean_bundle.slug).read_record()
    assert paused.stages[-1].stage == stage and paused.stages[-1].status == "open"
    assert purpose not in [c.purpose for c in paused.stages[-1].calls]
    bundle, record = run_plan(
        tmp_path / "paused", through="revise", planner=planner, reviewer=reviewer
    )
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean) and record.resumed == []
