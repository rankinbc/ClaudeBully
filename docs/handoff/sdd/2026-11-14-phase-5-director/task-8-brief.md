### Task 8: Stages 3 and 4: the review, the revision and the confirm pass

**Files:**
- Modify: `claude_bully/planner/director.py` (`REVIEW_CHUNK_DOCS`, `REVIEW_GROUPS`, `REVIEW_SCHEMA`, `REVISE_SCHEMA`, `CONFIRM_SCHEMA`, `review_groups`, `check_findings`, `render_review`, `Director.review`, `Director.revise`)
- Modify: `tests/fixtures/director_stub.py` (`ReviewerStub`'s replies; `PlannerStub`'s `revise:` replies)
- Test: `tests/test_director_review.py`

**Interfaces:**
- Consumes: Tasks 7a and 7b's `Director.ask`, `CallSpec`, `run_plan`, `comparable`, `hashed_files`, `cache_keys`, `DOC1`; Task 6's `reviewer_message`, `confirm_message`, `ReviewGroup`; `lints.squash`.
- Produces: `REVIEW_CHUNK_DOCS: Final = 25`; `REVIEW_GROUPS: Final = ("corpus", "lines", "plan")`; `review_groups(bundle: Bundle, record: PlanRecord) -> list[ReviewGroup]` (corpus chunks named `corpus-1`, `corpus-2`, ...; a group with no file is left out); `check_findings(reply: str, group: ReviewGroup, bundle: Bundle) -> tuple[list[ReviewFinding], list[str]]` (findings unnumbered, `id=0`); `render_review(findings: Sequence[ReviewFinding]) -> str`; `findings_of(bundle: Bundle, record: PlanRecord) -> list[ReviewFinding]`; `Director.review() -> None`; `Director.revise() -> None`. `ReviewerStub(*, modes: Mapping[str, str] = {}, crash_at: str | None = None, reasoning: str | None = None, verdicts: Mapping[int, str] = {})`.

- [ ] **Step 1: Write the failing tests**

The reviewer stub's default report on the good bundle: one `block` in the corpus group (the first sentence of `DOC1`, quoted exactly, "reads as written to persuade"), one `fix` in the plan group (the first sentence of `plan.md`, direction "name the null result's number"), one `note` in the lines group (a `fallback_lines` entry of the persona). Every quote is taken from the file's text as the review message shows it under `### <path>`, never from the fixture file, so a later round (`plan review`, after a revision replaced a quoted sentence) quotes what is in the file then (review I5). Its modes for a `review:<group>` purpose: `not_in_group` (a finding on a file of another group), `no_quote_block` (a block with `quote: ""`), `quote_missing` (a quote that is not text of the file), `counts_wrong` (the summary says two blocks), `empty_no_summary` (`{"findings": []}`), `clean` (`{"summary": {"block": 0, "fix": 0, "note": 0}, "findings": []}`), each on the first attempt or `:twice` (R-stub-modes). `confirm:<path>` answers `absent` for every number unless `verdicts` maps the local passage number (the number the confirm message shows, 1 to k per file; review Minor 4) to `present` or `cannot_tell`, or mode `missing` leaves a number out; the good bundle's one block is passage 1 of `DOC1`'s confirm call. The planner stub's `revise:<path>` reply replaces each block's quote in the file with a dull sentence, answers each block and fix `fixed`, unless its mode is `declined` (the block answered `declined`, the file unchanged) or `keep_quote` (answered `fixed`, the quote left in).

```python
# tests/test_director_review.py
"""Phase 5 Task 8: stages 3 and 4 on stubs (spec section 7), resume parity at K8 to K10 and at
the review render (R-review-md), and the reasoning sentinel end to end (D-sentinel)."""

import json
import re
from pathlib import Path

import pytest

from claude_bully.planner.director import REVIEW_CHUNK_DOCS, render_review, review_groups
from claude_bully.planner.records import ReviewFinding
from tests.fixtures.bundle_fixtures import good_bundle
from tests.fixtures.director_stub import (
    Kill,
    PlannerStub,
    ReviewerStub,
    cache_keys,
    comparable,
    hashed_files,
    run_plan,
)

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


def test_the_review_groups_chunk_the_corpus_and_name_the_unchanged_files(tmp_path: Path, isolated_registry: None) -> None:
    bundle = good_bundle(tmp_path)
    groups = review_groups(bundle, bundle.read_record())
    assert [g.name for g in groups] == ["corpus-1", "lines", "plan"]
    corpus = groups[0]
    assert len(corpus.files) <= REVIEW_CHUNK_DOCS
    unchanged = {"worlds/mini/corpus/ferry-about.md", "worlds/mini/corpus/night-gate-log.md"}
    assert unchanged.isdisjoint(corpus.files) and len(corpus.index) >= 2  # base files, by index line
    assert groups[2].files == ("plan.md", "config.yaml", "expected.yaml")


def test_a_clean_review_and_revision(tmp_path: Path, isolated_registry: None) -> None:
    reviewer = ReviewerStub()
    bundle, record = run_plan(tmp_path, through="revise", reviewer=reviewer)
    assert record.review_counts == {"block": 1, "fix": 1, "note": 1}
    assert record.open_blocks == 0 and record.status == "revised"
    revise = record.stages[3]
    assert [c.purpose for c in revise.calls] == [
        "revise:plan.md", f"revise:{_doc1()}", f"confirm:{_doc1()}",
    ]  # path order, then one confirm per file that had a block
    review = bundle.read_file("review.md")
    assert review.startswith("block 1 / fix 1 / note 1\n") and "- confirm: absent (closed)" in review
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
        assert "response (" not in message and "planner_status" not in message and '"status"' not in message


def _doc1() -> str:
    from tests.test_director_author import DOC1

    return DOC1


@pytest.mark.parametrize("mode", ["not_in_group", "no_quote_block", "quote_missing", "counts_wrong", "empty_no_summary"])
def test_a_review_reply_the_harness_cannot_read_is_retried_then_fails_the_stage(
    mode: str, tmp_path: Path, isolated_registry: None
) -> None:
    _, once = run_plan(tmp_path / "once", through="review", reviewer=ReviewerStub(modes={"review:corpus-1": mode}))
    assert once.stages[2].status == "committed" and once.stages[2].calls[0].attempts == 2
    _, twice = run_plan(tmp_path / "twice", through="review", reviewer=ReviewerStub(modes={"review:corpus-1": f"{mode}:twice"}))
    assert twice.stages[2].status == "failed" and twice.status == "failed"  # never "no findings"


def test_an_explicit_zero_summary_is_a_clean_review(tmp_path: Path, isolated_registry: None) -> None:
    modes = {g: "clean" for g in ("review:corpus-1", "review:lines", "review:plan")}
    _, record = run_plan(tmp_path, through="revise", reviewer=ReviewerStub(modes=modes))
    assert record.review_counts == {"block": 0, "fix": 0, "note": 0} and record.stages[3].calls == []


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
        reviewer = ReviewerStub(modes={f"confirm:{doc1}": "provider_error"})  # an error, no retry
    else:
        reviewer = ReviewerStub(verdicts={1: verdict})
    _, record = run_plan(tmp_path, through="revise", planner=planner, reviewer=reviewer)
    assert (record.open_blocks == 0) is closed
    assert record.status == ("revised" if closed else "failed")


def test_a_revise_reply_must_answer_every_block_and_fix_once(tmp_path: Path, isolated_registry: None) -> None:
    planner = PlannerStub(modes={"revise:plan.md": "no_response:twice"})
    _, record = run_plan(tmp_path, through="revise", planner=planner)
    call = next(c for c in record.stages[3].calls if c.purpose == "revise:plan.md")
    assert call.status == "error" and "finding 3" in (call.error or "")
    assert record.stages[3].status == "committed"  # D-revise-error: the stage goes on


def test_render_review_is_the_fixed_format() -> None:
    findings = [
        ReviewFinding(id=1, severity="block", file="worlds/w/corpus/a.md", quote="Q1", problem="P1",
                      response="R1", planner_status="fixed", confirm="absent", open=False),
        ReviewFinding(id=2, severity="note", file="personas/p.yaml", quote="Q2", problem="P2", open=False),
        ReviewFinding(id=3, severity="fix", file="plan.md", quote="Q3", problem="P3", direction="D3",
                      response="R3", planner_status="fixed", open=False),
    ]
    assert render_review(findings) == RENDERED.format(
        note_quote="Q2", note_problem="P2", fix_quote="Q3", fix_problem="P3", direction="D3",
        fix_response="R3", doc1="worlds/w/corpus/a.md", block_quote="Q1", block_problem="P1",
        block_response="R1",
    )


KILLS = {
    "K8": dict(reviewer_crash="review:lines", dead=("review", "reviewer", 1)),
    # R-review-md: review.md written, the stage not yet committed; the resume renders it again
    # and stage 4's inputs hold it, as an unbroken plan's do (review I4)
    "K8-rendered": dict(kill=Kill("rendered", "review"), dead=None),
    "K9a": dict(planner_crash="revise:{doc1}", dead=("revise", "planner", 1)),
    "K9b": dict(kill=Kill("record", "revise:{doc1}"), dead=None),
    "K10": dict(reviewer_crash="confirm:{doc1}", dead=("revise", "reviewer", 2)),
}


@pytest.mark.slow
@pytest.mark.parametrize("point", list(KILLS))
def test_a_plan_killed_at_k8_to_k10_resumes_byte_equal(point: str, tmp_path: Path, isolated_registry: None) -> None:
    doc1 = _doc1()
    spec = {k: (v.format(doc1=doc1) if isinstance(v, str) else v) for k, v in KILLS[point].items()}
    if isinstance(spec.get("kill"), Kill):
        spec["kill"] = Kill(spec["kill"].step, spec["kill"].purpose.format(doc1=doc1))
    dead = spec.pop("dead")
    clean_bundle, clean = run_plan(tmp_path / "clean", through="revise")
    planner = PlannerStub(crash_at=spec.pop("planner_crash", None))
    reviewer = ReviewerStub(crash_at=spec.pop("reviewer_crash", None))
    bundle, record = run_plan(tmp_path / "killed", through="revise", planner=planner, reviewer=reviewer, **spec)
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
        '{"index": 1, "speaker": "target", "text": "x", "reasoning_text": "%s"}\n' % run_sentinel, "utf-8"
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
        p.read_text("utf-8", errors="replace") for p in (tmp_path / "plans").rglob("*") if p.is_file()
    ]
    assert any((tmp_path / "plans" / "_cache" / "director").rglob("*"))
    for text in sent + written:
        assert run_sentinel not in text and own_sentinel not in text
```

(`ReviewerStub` reads `crash_at` as `PlannerStub` does. The K-table's purposes hold `{doc1}`, formatted in the test.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_director_review.py -q -m "slow or not slow"`
Expected: FAIL at import (`render_review`, `review_groups` do not exist).

- [ ] **Step 3: Implement**

`review()`: at stage open, adopt edits (as `author`); one `ask` per `review_groups` entry with `REVIEW_SCHEMA`, system `reviewer`, the message `reviewer_message(bundle, group)`, `check` = `check_findings` (refusals of spec section 7 stage 3: `file` not in the group; a `block` with an empty quote; a non-empty quote that `squash(quote)` does not find in `squash(file text)`; the summary's counts not the findings'; a reply with no `summary`); on a second failure the stage and the plan fail. Then `review.md` is written from `findings_of(bundle, record)`, `checkpoint("rendered", "review")`, and only then `review_counts` is set and the stage committed (the record write); status `reviewed`. `review.md` is derived from the committed review calls, never a call's output, so it is rendered before the stage flag (R-review-md, review I4): a plan killed between the two resumes with every review call committed, renders the same bytes again and commits, and stage 4's `inputs` hold `review.md` as an unbroken plan's do. `findings_of(bundle: Bundle, record: PlanRecord) -> list[ReviewFinding]` is the one reader: it numbers the committed review calls' findings 1.. in call order and reply order, and fills `response` and `planner_status` from the committed revise calls' replies and `confirm` and `open` from the committed confirm calls', all read from their transcripts. No record holds a second copy of the findings, so a resume renders what an unbroken plan renders.

`render_review(findings)` writes the format `RENDERED` pins: the summary line `block N / fix N / note N`, a blank line, then per file in path order `## <file>` and its findings in id order, `- [<id>] <severity>: "<quote>" <problem>` with ` (direction: <direction>)` on a fix that has one; under a finding with a response, `  - response (<planner_status>): <response>`; under a block with a verdict, `  - confirm: <verdict> (closed)` when it closed, `(open)` otherwise; files separated by one blank line; LF; one trailing newline.

`revise()`: one planner `ask` per file with a `block` or `fix`, in path order (`REVISE_SCHEMA`: `content` and `responses` `[{"finding": int, "status": "fixed" | "declined", "text": str}]`; `check` runs the arrival check of the file's kind and refuses unless every block and fix finding of the file has exactly one response, naming `finding <id>`); the message is the file as committed before stage 4, its findings as `render_review` renders them, and the reply contract. A call that errors twice leaves the file and its findings unanswered (D-revise-error). Each world is closed again with the repair bound left from stage 2. Then one reviewer `ask` per file that had a block (system `confirm`, `CONFIRM_SCHEMA`, `confirm_message(rel, <the file now>, [(local number, quote, problem) per block])`); a block closes only when its `planner_status` is `fixed`, `squash(quote)` is not in `squash(<the file now>)`, and its verdict is `absent`. `cannot_tell`, a missing number and a confirm call that errors leave it open. The confirm reply's `finding` numbers are the local passage numbers, mapped back to finding ids by the Director. `review.md` is rendered again with responses and verdicts, then `checkpoint("rendered", "revise")`; `open_blocks` counted; the stage commits; status `revised`, or `failed` with `open_blocks > 0`.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_director_review.py tests/test_director_author.py -q -m "slow or not slow"`, then the gate.
Expected: PASS; K8 to K10 and the review render byte-equal; the sentinel test clean.

- [ ] **Step 5: Docs-sync and commit**

docs/08 "Process" stages 3 and 4 and the reviewer's "Output": findings arrive in a schema and the harness renders `review.md` (A4) in the pinned format; a block is closed by evidence (A5). Spec "As planned": D-revise-error, D-sentinel, R-review-md.

```bash
git add claude_bully/planner/director.py tests/fixtures/director_stub.py tests/test_director_review.py \
  docs/08-DIRECTOR.md docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 8, the review in a schema, the revision, the blind confirm pass and resume parity at K8 to K10

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

