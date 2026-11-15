### Task 7b: Stage 2, the author stage

The manifest call, the world copy, one file call per entry, the world close and its repairs, and `config.yaml`'s arrival check, with K2, K3, K4 to K7 on stage 2's calls and the manifest's record and files points (R-split, R-commit).

**Files:**
- Modify: `claude_bully/planner/director.py` (`MANIFEST_SCHEMA`, `FILE_SCHEMA`, `author_order`, `Director.author`)
- Test: `tests/test_director_author.py`

**Interfaces:**
- Consumes: Task 7a's `Director`, `ask`, `CallSpec`, `Answer`, the doubles and `run_plan`; `plan_personas`, `bundle_personas`, `lint_document`, `lint_context`, `lint_world`, `load_world`, `Ladder`, `load_experiment`, `expand_cells`, `run_experiment(dry_run=True)`, `contracts_for`, `world_hash`.
- Produces: `MANIFEST_SCHEMA`, `FILE_SCHEMA` (`{"content": string}`, required), each a `Final[dict[str, Any]]` JSON Schema with `additionalProperties: false`; `author_order(manifest: Sequence[ManifestEntry]) -> list[ManifestEntry]`; `Director.author() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_director_author.py
"""Phase 5 Task 7b: stage 2 on stubs, resume parity at K2, K3, K4 to K7 and the manifest's
record and files points."""

from pathlib import Path

import pytest

from claude_bully.planner.bundle import Bundle, rematerialize_open_stage
from claude_bully.planner.director import Director, author_order
from claude_bully.runner.runner import RateLimitExit
from tests.fixtures.bundle_fixtures import GOOD, GOOD_MANIFEST
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

DOCS = [e.path for e in author_order(GOOD_MANIFEST) if e.kind == "document"]
DOC1, DOC3 = DOCS[0], DOCS[2]
REPAIRED = DOCS[1]


def test_author_order_is_sheet_documents_ladders_premises_personas_config_expected() -> None:
    kinds = [e.kind for e in author_order(GOOD_MANIFEST)]
    first = {k: kinds.index(k) for k in set(kinds)}
    assert sorted(first, key=first.__getitem__) == [
        "world_sheet", "document", "ladder", "persona", "config", "expected",
    ]
    assert DOCS == [e.path for e in GOOD_MANIFEST if e.kind == "document"]  # manifest order kept


def test_stage_2_adopts_an_edited_plan(tmp_path: Path, isolated_registry: None) -> None:
    planner = PlannerStub()
    director = Director.new(
        REQUEST, plans_root=tmp_path, provider_factory=StubFactory(planner, ReviewerStub()), worlds_dir=WORLDS_DIR
    )
    director.run(stop_after_plan=True)
    plan_md = director.bundle.root / "plan.md"
    plan_md.write_text(plan_md.read_text("utf-8") + "Owner note: two reps are enough.\n", "utf-8")
    again = Director.open(director.bundle.root, provider_factory=StubFactory(planner, ReviewerStub()), worlds_dir=WORLDS_DIR)
    record = again.run(through="author")
    assert record.status == "authored" and record.edited == ["plan.md"]
    author = record.stages[1]
    assert author.inputs["plan.md"] == again.bundle.index()["plan.md"]
    manifest_msg = next(m for c, s, m in planner.calls if "call: manifest" in m)
    assert "Owner note: two reps are enough." in manifest_msg  # the planner sees the edit


def test_a_clean_author_stage_writes_the_good_bundle(tmp_path: Path, isolated_registry: None) -> None:
    bundle, record = run_plan(tmp_path, through="author")
    for rel, text in _good_files().items():
        assert bundle.read_file(rel) == text, rel
    purposes = [c.purpose for c in record.stages[1].calls]
    assert purposes == ["manifest", *(f"file:{e.path}" for e in author_order(GOOD_MANIFEST))]
    assert record.manifest == GOOD_MANIFEST  # committed with the manifest call (R-commit)
    assert record.base_worlds["mini"] and record.base_files and record.base_premise_terms["mini"]
    assert len(cache_keys(tmp_path)) == 1 + len(purposes)  # one entry per committed fresh call


def _good_files() -> dict[str, str]:
    return {
        p.relative_to(GOOD).as_posix(): p.read_text("utf-8")
        for p in GOOD.rglob("*")
        if p.is_file() and p.name != "plan.md"
    }


@pytest.mark.slow  # two author stages (review Minor 12)
@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("outside_grammar", "../escape.md"),
        ("repeated_path", "twice"),
        ("no_config", "config.yaml"),
    ],
)
def test_the_manifests_refusals_retry_once_then_fail_the_stage(
    mode: str, message: str, tmp_path: Path, isolated_registry: None
) -> None:  # Review Focus 4
    _, record = run_plan(tmp_path, through="author", modes={"manifest": mode})
    manifest = record.stages[1].calls[0]
    assert (manifest.status, manifest.attempts) == ("fresh", 2)  # the retry passed
    _, failed = run_plan(tmp_path / "twice", through="author", modes={"manifest": f"{mode}:twice"})
    call = failed.stages[1].calls[0]
    assert call.status == "error" and message in (call.error or "")
    assert failed.stages[1].status == "failed" and failed.status == "failed"


def test_a_manifest_naming_a_path_twice_is_refused(tmp_path: Path, isolated_registry: None) -> None:
    _, record = run_plan(tmp_path, through="author", modes={"manifest": "repeated_path:twice"})
    assert record.stages[1].calls[0].status == "error"


def test_a_manifest_may_patch_a_base_file(tmp_path: Path, isolated_registry: None) -> None:
    bundle, record = run_plan(tmp_path, through="author")
    patched = "worlds/mini/corpus/canteen-menu.md"
    assert patched in record.base_files and patched in {e.path for e in record.manifest}
    assert bundle.index()[patched] != record.base_files[patched]


def test_a_fresh_world_under_the_floor_or_the_filler_share_is_refused(tmp_path: Path, isolated_registry: None) -> None:
    request = REQUEST.model_copy(update={"world": "fresh", "base_world": None})
    _, record = run_plan(tmp_path, through="author", request=request, modes={"manifest": "fresh_small:twice"})
    assert "20" in (record.stages[1].calls[0].error or "")


def test_a_plan_that_would_pass_max_director_calls_fails_before_the_call(tmp_path: Path, isolated_registry: None) -> None:
    request = REQUEST.model_copy(update={"max_director_calls": 5})
    planner = PlannerStub()
    _, record = run_plan(tmp_path, through="author", request=request, planner=planner)
    assert record.status == "failed" and "max_director_calls" in (record.stages[1].error or "")
    assert not any("call: file:" in m for _, _, m in planner.calls)


def test_a_document_that_fails_twice_is_dropped_and_the_stage_goes_on(tmp_path: Path, isolated_registry: None) -> None:
    _, record = run_plan(tmp_path, through="author", modes={f"file:{DOC3}": "lint_fail:twice"})
    dropped = next(c for c in record.stages[1].calls if c.purpose == f"file:{DOC3}")
    assert dropped.status == "error" and "second_person" in (dropped.error or "")
    assert record.stages[1].status == "committed"


def test_a_non_document_that_fails_twice_fails_the_stage(tmp_path: Path, isolated_registry: None) -> None:
    _, record = run_plan(tmp_path, through="author", modes={"file:config.yaml": "off_contract:twice"})
    assert record.stages[1].status == "failed"


@pytest.mark.slow  # three author stages
def test_a_provider_error_on_a_document_fails_the_stage_and_continues_with_no_dead_attempt(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Review Minor 10: a provider error on a document fails the stage (spec section 13), never
    drops the document. Review I2 (R-marker): the continued plan records no dead attempt, keeps
    the error's transcript under transcripts/failed/, and ends with an unbroken plan's bundle."""
    planner = PlannerStub(modes={f"file:{DOC1}": "provider_error"})  # fires once (R-stub-modes)
    factory = StubFactory(planner, ReviewerStub())
    director = Director.new(REQUEST, plans_root=tmp_path / "plans", provider_factory=factory, worlds_dir=WORLDS_DIR)
    failed = director.run(through="author")
    assert failed.stages[1].status == "failed" and failed.status == "failed"
    index = next(c.index for c in failed.stages[1].calls if c.purpose == f"file:{DOC1}")
    record = Director.open(director.bundle.root, provider_factory=factory, worlds_dir=WORLDS_DIR).run(through="author")
    assert record.resumed == [] and record.stages[1].status == "committed"
    assert (director.bundle.root / "transcripts" / "failed" / f"author-planner-{index}.json").is_file()
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author")
    assert hashed_files(director.bundle.root) == hashed_files(clean_bundle.root)
    assert [c.purpose for c in record.stages[1].calls] == [c.purpose for c in clean.stages[1].calls]


def test_the_world_close_asks_one_repair_and_closes(tmp_path: Path, isolated_registry: None) -> None:
    bundle, record = run_plan(tmp_path, through="author", modes={f"file:{REPAIRED}": "close_fail"})
    purposes = [c.purpose for c in record.stages[1].calls]
    assert purposes.count(f"repair:{REPAIRED}") == 1
    assert bundle.read_file(REPAIRED) == (GOOD / REPAIRED).read_text("utf-8")


def test_every_author_call_resets_its_session_first(tmp_path: Path, isolated_registry: None) -> None:
    planner = PlannerStub()
    run_plan(tmp_path, through="author", planner=planner)
    assert [cid for cid, _, _ in planner.calls] == planner.resets


@pytest.mark.slow  # three author stages
def test_a_rate_limited_file_call_pauses_and_resumes_with_no_dead_attempt(tmp_path: Path, isolated_registry: None) -> None:
    _, clean = run_plan(tmp_path / "clean", through="author")
    with pytest.raises(RateLimitExit):
        run_plan(tmp_path / "paused", through="author", modes={f"file:{DOC1}": "rate_limit"}, resume=False)
    paused = Bundle(tmp_path / "paused" / clean.slug)
    assert paused.read_attempt() is None  # D-rate-limit
    held = paused.read_record()
    assert held.stages[1].status == "open"
    assert f"file:{DOC1}" not in [c.purpose for c in held.stages[1].calls]
    _, resumed = run_plan(tmp_path / "paused", through="author")
    assert resumed.resumed == []
    assert comparable(resumed) == comparable(clean)


def test_a_timeout_is_an_error_and_never_waited_on(tmp_path: Path, isolated_registry: None) -> None:
    _, record = run_plan(tmp_path, through="author", modes={"file:config.yaml": "timeout"})
    call = next(c for c in record.stages[1].calls if c.purpose == "file:config.yaml")
    assert call.status == "error" and record.status == "failed"


@pytest.mark.slow
@pytest.mark.parametrize("step", ["record", "files"])
def test_a_crlf_reply_commits_and_resumes_to_the_same_bytes(step: str, tmp_path: Path, isolated_registry: None) -> None:
    """Review Focus 2. Killed after the CRLF call's record (the resume writes the file from the
    transcript) and after its file (the resume rewrites nothing); both end LF, with no BOM, equal
    to an unbroken CRLF plan. Review I8: rematerializing a committed stage is a no-op, so the
    kill sits inside the open stage."""
    modes = {f"file:{DOC1}": "crlf"}
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author", modes=modes)
    assert b"\r" not in (clean_bundle.root / DOC1).read_bytes()
    with pytest.raises(Crash):
        run_plan(tmp_path / "killed", through="author", modes=modes, kill=Kill(step, f"file:{DOC1}"), resume=False)
    bundle = Bundle(tmp_path / "killed" / clean.slug)
    rewritten = rematerialize_open_stage(bundle, bundle.read_record(), "author")
    assert rewritten == ([DOC1] if step == "record" else [])
    assert (bundle.root / DOC1).read_bytes() == (clean_bundle.root / DOC1).read_bytes()
    _, record = run_plan(tmp_path / "killed", through="author", modes=modes)
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)


# a call's index in the author stage: the manifest is 0, then the files in author order
INDEX = {e.path: i + 1 for i, e in enumerate(author_order(GOOD_MANIFEST))}
NO_BASE = REQUEST.model_copy(update={"base_world": None})  # D-copy: the copy after the manifest
KILLS = {
    "K2": dict(kill=None, crash_at="manifest", dead=("author", "planner", 0)),
    # R-commit: the manifest commits record.manifest with its call; the copy is keyed on
    # base_worlds membership, so a resume that skips the committed call still copies
    "K2-record": dict(kill=Kill("record", "manifest"), dead=None),
    "K2-files": dict(kill=Kill("files", "manifest"), dead=None),
    "K2-record-no-base": dict(kill=Kill("record", "manifest"), request=NO_BASE, dead=None),
    "K2-files-no-base": dict(kill=Kill("files", "manifest"), request=NO_BASE, dead=None),
    "K3": dict(kill=None, crash_at=f"file:{DOC3}", dead=("author", "planner", INDEX[DOC3])),
    "K4": dict(kill=Kill("transcript", f"file:{DOC1}"), dead=("author", "planner", INDEX[DOC1])),
    "K5": dict(kill=Kill("record", f"file:{DOC1}"), dead=None),
    "K6": dict(kill=Kill("files", f"file:{DOC1}"), dead=None),
    "K7a": dict(kill=None, crash_at=f"repair:{REPAIRED}", modes={f"file:{REPAIRED}": "close_fail"}, dead="repair"),
    "K7b": dict(kill=Kill("record", f"repair:{REPAIRED}"), modes={f"file:{REPAIRED}": "close_fail"}, dead=None),
}
# committed, never asked again: the put did not happen
NO_PUT = {p for p, v in KILLS.items() if isinstance(v.get("kill"), Kill) and v["kill"].step in ("record", "files")}


@pytest.mark.slow
@pytest.mark.parametrize("point", list(KILLS))
def test_a_plan_killed_in_stage_2_resumes_byte_equal(point: str, tmp_path: Path, isolated_registry: None) -> None:
    spec = dict(KILLS[point])
    modes = spec.pop("modes", {})
    request = spec.pop("request", REQUEST)
    dead = spec.pop("dead")
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author", modes=modes, request=request)
    bundle, record = run_plan(tmp_path / "killed", through="author", modes=modes, request=request, **spec)
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)
    assert record.manifest == clean.manifest and record.base_worlds == clean.base_worlds
    if dead is None:
        assert record.resumed == []
    else:
        (attempt,) = record.resumed
        if dead == "repair":
            assert attempt.stage == "author"
        else:
            assert (attempt.stage, attempt.role, attempt.index) == dead
    killed_keys, clean_keys = cache_keys(tmp_path / "killed"), cache_keys(tmp_path / "clean")
    if point in NO_PUT:
        assert len(clean_keys - killed_keys) == 1 and killed_keys < clean_keys
    else:
        assert killed_keys == clean_keys
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_director_author.py -q -m "slow or not slow"`
Expected: FAIL (`author_order` and `Director.author` do not exist).

- [ ] **Step 3: Implement stage 2**

`author()`, spec section 7 stage 2 in order, at stage open recording `StageRecord.inputs` (the sha of every grammar file) and adopting edits (`edited` gains each path whose sha differs from its last committing call's, or from `base_files`), in one record write before anything else: the world copy (D-copy: for each world the request or the committed manifest names that `base_worlds` lacks, the files are copied, then `base_worlds`, `base_files` and `base_premise_terms` are committed in one record write; keyed on that membership, so it runs again on a resume and never twice); the manifest call (`MANIFEST_SCHEMA`; `check` refuses a path outside the grammar, a path listed twice, a `kind` other than `kind_of(path)`, a `layer` on a non-document or none on a document, a missing `config.yaml` or `expected.yaml`, a premise sheet whose stem names no strategy with a `world_sheet`, a persona stem that is a registered strategy (read after `ensure_registered()`), a fresh world with fewer than `MIN_ANCHOR_DOCS` documents or a filler share under `MIN_FILLER_SHARE`, and a plan whose calls so far plus `len(manifest)` plus the three review calls would pass `max_director_calls`; its `commit` sets `record.manifest`, R-commit); the say line `the manifest implies <n> calls`; one file call per entry in `author_order` (`FILE_SCHEMA`, the contract part `contracts_for(entry)`, the arrival check of spec section 7 step 3); each world's close after its last file (step 4: `load_world`, a `Ladder` per ladder under `triggered`, `failures(lint_world(world))`; each failure mapped to a file; one `repair:<path>` call per failing file within `MAX_REPAIR_CALLS` a plan; the close again); `config.yaml`'s arrival check inside `plan_personas(bundle_personas(bundle))` (step 5); status `authored`. A document whose call is an `error` from two failed checks keeps its `error` call and is not written; a fresh world under the floor then fails the stage. A provider error or a timeout on any call, a document's included, fails the stage and the plan (`Answer.provider_failed`; spec section 13; review Minor 10), as does any other file that fails twice.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_director_author.py tests/test_director_primitive.py -q -m "slow or not slow"`, then the gate.
Expected: PASS; K2 to K7 and the four manifest points byte-equal.

- [ ] **Step 5: Docs-sync and commit**

docs/08 "Process": stage 2's manifest call and one file per call (A2). Spec "As planned": the copy-timing ruling (D-copy, with its order), `plan.md`-in-context, and R-split.

```bash
git add claude_bully/planner/director.py tests/test_director_author.py docs/08-DIRECTOR.md \
  docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 7b, the Director's author stage, resume parity at K2 to K7 and the manifest's commit points

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

