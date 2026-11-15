# tests/test_director_author.py
"""Phase 5 Task 7b: stage 2 on stubs, resume parity at K2, K3, K4 to K7 and the manifest's
record and files points."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from claude_bully.enums import Layer
from claude_bully.metrics.judge import JudgeCache
from claude_bully.planner import bundle as bundle_module
from claude_bully.planner import director as director_module
from claude_bully.planner.bundle import Bundle, rematerialize_open_stage
from claude_bully.planner.director import (
    FILE_SCHEMA,
    MANIFEST_SCHEMA,
    Answer,
    CallSpec,
    Director,
    DirectorError,
    author_order,
    parse_content,
    parse_manifest,
)
from claude_bully.planner.lints import owner_names
from claude_bully.planner.records import DirectorCall, ManifestEntry
from claude_bully.planner.request import slug_for
from claude_bully.providers.ledger import Ledger, LedgerLine
from claude_bully.runner.runner import RateLimitExit
from tests.fixtures.bundle_fixtures import BASE_WORLD, GOOD, GOOD_MANIFEST
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
        "world_sheet",
        "document",
        "ladder",
        "persona",
        "config",
        "expected",
    ]
    assert DOCS == [e.path for e in GOOD_MANIFEST if e.kind == "document"]  # manifest order kept


@pytest.mark.slow  # two plans to stage 2
def test_stage_2_adopts_an_edited_plan(tmp_path: Path, isolated_registry: None) -> None:
    planner = PlannerStub()
    director = Director.new(
        REQUEST,
        plans_root=tmp_path,
        provider_factory=StubFactory(planner, ReviewerStub()),
        worlds_dir=WORLDS_DIR,
    )
    director.run(stop_after_plan=True)
    plan_md = director.bundle.root / "plan.md"
    plan_md.write_text(plan_md.read_text("utf-8") + "Owner note: two reps are enough.\n", "utf-8")
    again = Director.open(
        director.bundle.root,
        provider_factory=StubFactory(planner, ReviewerStub()),
        worlds_dir=WORLDS_DIR,
    )
    record = again.run(through="author")
    assert record.status == "authored" and record.edited == ["plan.md"]
    author = record.stages[1]
    assert author.inputs["plan.md"] == again.bundle.index()["plan.md"]
    manifest_msg = next(m for c, s, m in planner.calls if "call: manifest" in m)
    assert "Owner note: two reps are enough." in manifest_msg  # the planner sees the edit


@pytest.mark.slow
def test_a_clean_author_stage_writes_the_good_bundle(
    tmp_path: Path, isolated_registry: None
) -> None:
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


@pytest.mark.slow
def test_a_manifest_may_patch_a_base_file(tmp_path: Path, isolated_registry: None) -> None:
    bundle, record = run_plan(tmp_path, through="author")
    patched = "worlds/mini/corpus/canteen-menu.md"
    assert patched in record.base_files and patched in {e.path for e in record.manifest}
    assert bundle.index()[patched] != record.base_files[patched]


def test_a_fresh_world_under_the_floor_or_the_filler_share_is_refused(
    tmp_path: Path, isolated_registry: None
) -> None:
    request = REQUEST.model_copy(update={"world": "fresh", "base_world": None})
    _, record = run_plan(
        tmp_path, through="author", request=request, modes={"manifest": "fresh_small:twice"}
    )
    assert "20" in (record.stages[1].calls[0].error or "")


def test_a_plan_that_would_pass_max_director_calls_fails_before_the_call(
    tmp_path: Path, isolated_registry: None
) -> None:
    request = REQUEST.model_copy(update={"max_director_calls": 5})
    planner = PlannerStub()
    _, record = run_plan(tmp_path, through="author", request=request, planner=planner)
    assert record.status == "failed" and "max_director_calls" in (record.stages[1].error or "")
    assert not any("call: file:" in m for _, _, m in planner.calls)


@pytest.mark.slow
def test_a_document_that_fails_twice_is_dropped_and_the_stage_goes_on(
    tmp_path: Path, isolated_registry: None
) -> None:
    _, record = run_plan(tmp_path, through="author", modes={f"file:{DOC3}": "lint_fail:twice"})
    dropped = next(c for c in record.stages[1].calls if c.purpose == f"file:{DOC3}")
    assert dropped.status == "error" and "second_person" in (dropped.error or "")
    assert record.stages[1].status == "committed"


@pytest.mark.slow
def test_a_non_document_that_fails_twice_fails_the_stage(
    tmp_path: Path, isolated_registry: None
) -> None:
    _, record = run_plan(
        tmp_path, through="author", modes={"file:config.yaml": "off_contract:twice"}
    )
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
    director = Director.new(
        REQUEST, plans_root=tmp_path / "plans", provider_factory=factory, worlds_dir=WORLDS_DIR
    )
    failed = director.run(through="author")
    assert failed.stages[1].status == "failed" and failed.status == "failed"
    index = next(c.index for c in failed.stages[1].calls if c.purpose == f"file:{DOC1}")
    record = Director.open(
        director.bundle.root, provider_factory=factory, worlds_dir=WORLDS_DIR
    ).run(through="author")
    assert record.resumed == [] and record.stages[1].status == "committed"
    assert (
        director.bundle.root / "transcripts" / "failed" / f"author-planner-{index}.json"
    ).is_file()
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author")
    assert hashed_files(director.bundle.root) == hashed_files(clean_bundle.root)
    assert [c.purpose for c in record.stages[1].calls] == [c.purpose for c in clean.stages[1].calls]


@pytest.mark.slow
def test_the_world_close_asks_one_repair_and_closes(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle, record = run_plan(tmp_path, through="author", modes={f"file:{REPAIRED}": "close_fail"})
    purposes = [c.purpose for c in record.stages[1].calls]
    assert purposes.count(f"repair:{REPAIRED}") == 1
    assert bundle.read_file(REPAIRED) == (GOOD / REPAIRED).read_text("utf-8")


@pytest.mark.slow
def test_every_author_call_resets_its_session_first(
    tmp_path: Path, isolated_registry: None
) -> None:
    planner = PlannerStub()
    run_plan(tmp_path, through="author", planner=planner)
    assert [cid for cid, _, _ in planner.calls] == planner.resets


@pytest.mark.slow  # three author stages
def test_a_rate_limited_file_call_pauses_and_resumes_with_no_dead_attempt(
    tmp_path: Path, isolated_registry: None
) -> None:
    _, clean = run_plan(tmp_path / "clean", through="author")
    with pytest.raises(RateLimitExit):
        run_plan(
            tmp_path / "paused",
            through="author",
            modes={f"file:{DOC1}": "rate_limit"},
            resume=False,
        )
    paused = Bundle(tmp_path / "paused" / clean.slug)
    assert paused.read_attempt() is None  # D-rate-limit
    held = paused.read_record()
    assert held.stages[1].status == "open"
    assert f"file:{DOC1}" not in [c.purpose for c in held.stages[1].calls]
    _, resumed = run_plan(tmp_path / "paused", through="author")
    assert resumed.resumed == []
    assert comparable(resumed) == comparable(clean)


@pytest.mark.slow
def test_a_timeout_is_an_error_and_never_waited_on(tmp_path: Path, isolated_registry: None) -> None:
    _, record = run_plan(tmp_path, through="author", modes={"file:config.yaml": "timeout"})
    call = next(c for c in record.stages[1].calls if c.purpose == "file:config.yaml")
    assert call.status == "error" and record.status == "failed"


@pytest.mark.slow
@pytest.mark.parametrize("step", ["record", "files"])
def test_a_crlf_reply_commits_and_resumes_to_the_same_bytes(
    step: str, tmp_path: Path, isolated_registry: None
) -> None:
    """Review Focus 2. Killed after the CRLF call's record (the resume writes the file from the
    transcript) and after its file (the resume rewrites nothing); both end LF, with no BOM, equal
    to an unbroken CRLF plan. Review I8: rematerializing a committed stage is a no-op, so the
    kill sits inside the open stage."""
    modes = {f"file:{DOC1}": "crlf"}
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author", modes=modes)
    assert b"\r" not in (clean_bundle.root / DOC1).read_bytes()
    with pytest.raises(Crash):
        run_plan(
            tmp_path / "killed",
            through="author",
            modes=modes,
            kill=Kill(step, f"file:{DOC1}"),
            resume=False,
        )
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
KILLS: dict[str, dict[str, Any]] = {
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
    "K7a": dict(
        kill=None,
        crash_at=f"repair:{REPAIRED}",
        modes={f"file:{REPAIRED}": "close_fail"},
        dead="repair",
    ),
    "K7b": dict(
        kill=Kill("record", f"repair:{REPAIRED}"),
        modes={f"file:{REPAIRED}": "close_fail"},
        dead=None,
    ),
}
# committed, never asked again: the put did not happen
NO_PUT = {
    p
    for p, v in KILLS.items()
    if isinstance(v.get("kill"), Kill) and v["kill"].step in ("record", "files")
}


@pytest.mark.slow
@pytest.mark.parametrize("point", list(KILLS))
def test_a_plan_killed_in_stage_2_resumes_byte_equal(
    point: str, tmp_path: Path, isolated_registry: None
) -> None:
    spec = dict(KILLS[point])
    modes = spec.pop("modes", {})
    request = spec.pop("request", REQUEST)
    dead = spec.pop("dead")
    clean_bundle, clean = run_plan(
        tmp_path / "clean", through="author", modes=modes, request=request
    )
    bundle, record = run_plan(
        tmp_path / "killed", through="author", modes=modes, request=request, **spec
    )
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


# ---------------------------------------------------------------- beyond the brief's tests

SLUG = slug_for(REQUEST.question)


def test_the_reply_schemas_are_closed_and_require_every_field() -> None:
    assert FILE_SCHEMA == {
        "type": "object",
        "additionalProperties": False,
        "required": ["content"],
        "properties": {"content": {"type": "string"}},
    }
    assert MANIFEST_SCHEMA["additionalProperties"] is False
    item = MANIFEST_SCHEMA["properties"]["files"]["items"]
    assert item["additionalProperties"] is False
    assert item["required"] == ["path", "kind", "purpose", "layer"]
    assert None in item["properties"]["layer"]["enum"]


def test_the_parses_read_the_reply_alone() -> None:
    reply = json.dumps({"files": [e.model_dump(mode="json") for e in GOOD_MANIFEST]})
    assert parse_manifest(reply) == GOOD_MANIFEST
    assert parse_manifest("not json") is None
    assert parse_manifest(json.dumps({"files": [], "more": 1})) is None
    assert parse_manifest(json.dumps({"files": [{"path": "config.yaml"}]})) is None
    assert parse_content(json.dumps({"content": "a\r\n"})) == "a\r\n"  # normalized on writing
    for bad in ("{}", '{"content": 1}', '{"content": "a", "x": 1}', "[]", "no"):
        assert parse_content(bad) is None


def _answers(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any, bool]]:
    """Every answer ``Director._call`` gives, as (purpose, parsed, provider_failed)."""
    seen: list[tuple[str, Any, bool]] = []
    real = Director._call

    def spy(self: Director, stage: Any, index: int, spec: CallSpec) -> Answer:
        answer = real(self, stage, index, spec)
        seen.append((spec.purpose, answer.parsed, answer.provider_failed))
        return answer

    monkeypatch.setattr(Director, "_call", spy)
    return seen


@pytest.mark.slow
@pytest.mark.parametrize("failure", [None, "provider_error"])
def test_a_resumed_calls_parsed_reply_and_provider_failed_equal_an_unbroken_runs(
    failure: str | None,
    tmp_path: Path,
    isolated_registry: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Task 7a re-review's carry: a resume rebuilds each committed call's answer by its pure
    parse, so its parsed reply and provider_failed are the unbroken run's, and no check that
    reads state runs again. The budget is exact (the plan call, the manifest call, 13 files
    and 3 review calls make 18), so a check rerun at the resume, with more calls made, would
    refuse the committed manifest."""
    request = REQUEST.model_copy(update={"max_director_calls": 18})
    modes = {f"file:{DOC1}": failure} if failure else {}
    answers = _answers(monkeypatch)
    run_plan(tmp_path / "clean", through="author", request=request, modes=modes)
    unbroken = [answer for answer in answers if answer[0] != "plan"]  # stage 2's answers
    checks: list[str] = []
    real_check = Director._check_manifest

    def counted(self: Director, reply: str, made: int) -> tuple[Any, list[str]]:
        checks.append(reply)
        return real_check(self, reply, made)

    with pytest.raises(Crash):
        run_plan(
            tmp_path / "killed",
            through="author",
            request=request,
            modes=modes,
            kill=Kill("record", f"file:{DOC1}"),
            resume=False,
        )
    answers.clear()
    monkeypatch.setattr(Director, "_check_manifest", counted)
    _, record = run_plan(tmp_path / "killed", through="author", request=request, modes=modes)
    assert answers == unbroken
    assert checks == []  # the committed manifest is parsed, never checked again
    assert record.status == ("failed" if failure else "authored")
    failed = [a for a in answers if a[2]]
    assert failed == ([(f"file:{DOC1}", None, True)] if failure else [])


def _planned(tmp_path: Path, **kw: Any) -> Director:
    """A Director whose plan stage has committed, under ``tmp_path``."""
    run_plan(tmp_path, through="plan", **kw)
    return Director.open(
        tmp_path / SLUG,
        provider_factory=StubFactory(PlannerStub(), ReviewerStub()),
        worlds_dir=WORLDS_DIR,
    )


def _entry(path: str, kind: Any, layer: Layer | None = None) -> ManifestEntry:
    return ManifestEntry(path=path, kind=kind, purpose="a file", layer=layer)


def _fresh(n: int, filler: int, world: str = "harbour") -> list[ManifestEntry]:
    docs = [
        _entry(
            f"worlds/{world}/corpus/doc-{i:02d}.md",
            "document",
            Layer.filler if i < filler else Layer.seam,
        )
        for i in range(n)
    ]
    return [
        _entry(f"worlds/{world}/world.yaml", "world_sheet"),
        *docs,
        _entry("config.yaml", "config"),
        _entry("expected.yaml", "expected"),
    ]


GOOD_FIXED = list(GOOD_MANIFEST)
CLAUSES: list[tuple[str, list[ManifestEntry], str | None]] = [
    ("the good manifest", GOOD_FIXED, None),
    (
        "a kind that is not the path's",
        [*GOOD_FIXED[:-1], _entry("expected.yaml", "config")],
        "kind",
    ),
    (
        "a layer on a ladder",
        [*GOOD_FIXED, _entry("worlds/mini/ladders/b.yaml", "ladder", Layer.seam)],
        "only a document has a layer",
    ),
    (
        "a document with no layer",
        [*GOOD_FIXED, _entry("worlds/mini/corpus/pier-notice.md", "document")],
        "needs its layer",
    ),
    ("plan.md listed", [*GOOD_FIXED, _entry("plan.md", "config")], "no manifest entry names it"),
    ("no expected.yaml", GOOD_FIXED[:-1], "the manifest lists no expected.yaml"),
    (
        "a premise sheet naming no strategy",
        [*GOOD_FIXED, _entry("worlds/mini/premises/no-such-strategy.yaml", "premise_sheet")],
        "names no strategy",
    ),
    (
        "a persona named as a strategy",
        [*GOOD_FIXED, _entry("personas/captor.yaml", "persona")],
        "is a registered strategy",
    ),
    (
        "a fresh world with no sheet",
        [e for e in _fresh(20, 6) if not e.path.endswith("world.yaml")],
        "lists no worlds/harbour/world.yaml",
    ),
    ("a fresh world at the floor", _fresh(20, 6), None),
    ("a fresh world under the floor", _fresh(19, 6), "lists 19 documents"),
    ("a fresh world under the filler share", _fresh(20, 5), "5 of its 20 documents are filler"),
    ("a fresh world at the filler share", _fresh(20, 6), None),
]


@pytest.mark.parametrize(("case", "entries", "found"), CLAUSES, ids=[c[0] for c in CLAUSES])
def test_each_manifest_clause_refuses_its_case_and_passes_its_near_miss(
    case: str,
    entries: list[ManifestEntry],
    found: str | None,
    tmp_path: Path,
    isolated_registry: None,
) -> None:
    director = _planned(tmp_path)
    reply = json.dumps({"files": [e.model_dump(mode="json") for e in entries]})
    parsed, failures = director._check_manifest(reply, made=1)
    assert parsed == entries
    if found is None:
        assert failures == []
    else:
        assert len(failures) == 1 and found in failures[0], failures


def test_a_fresh_request_may_not_name_a_shipped_world(
    tmp_path: Path, isolated_registry: None
) -> None:
    """D-copy: under world fresh a manifest that names a shipped world's name is refused; under
    reuse the same world is copied, so it is no fresh world."""
    fresh = REQUEST.model_copy(update={"world": "fresh", "base_world": None})
    director = _planned(tmp_path / "fresh", request=fresh)
    reply = json.dumps({"files": [e.model_dump(mode="json") for e in GOOD_MANIFEST]})
    _, failures = director._check_manifest(reply, made=1)
    assert failures == ["world 'mini' is a shipped world's name; a fresh world needs its own"]
    reuse = _planned(tmp_path / "reuse", request=REQUEST.model_copy(update={"base_world": None}))
    assert reuse._check_manifest(reply, made=1)[1] == []


def test_the_budget_counts_the_calls_made_the_manifest_its_files_and_the_reviews(
    tmp_path: Path, isolated_registry: None
) -> None:
    director = _planned(tmp_path, request=REQUEST.model_copy(update={"max_director_calls": 18}))
    reply = json.dumps({"files": [e.model_dump(mode="json") for e in GOOD_MANIFEST]})
    assert director._check_manifest(reply, made=1)[1] == []  # 1 + 1 + 13 + 3 = 18
    (refused,) = director._check_manifest(reply, made=2)[1]
    assert refused.startswith("the plan would pass max_director_calls (18)") and "19" in refused


def test_a_dropped_document_that_takes_a_fresh_world_under_the_floor_fails_the_stage(
    tmp_path: Path, isolated_registry: None
) -> None:
    director = _planned(tmp_path)
    manifest = _fresh(20, 6)
    entry = manifest[1]
    call = DirectorCall(
        role="planner",
        index=2,
        purpose=f"file:{entry.path}",
        cache_key="",
        status="error",
        model="m",
        transcript="transcripts/author-planner-2.json",
        attempts=2,
        error="second_person: a line",
    )
    with pytest.raises(DirectorError, match="falls to 19 documents"):
        director._drop(Answer(call=call, parsed=None), entry, manifest, [])
    director.record.base_worlds["harbour"] = "copied"  # a reused world has no floor
    director._drop(Answer(call=call, parsed=None), entry, manifest, [])


@pytest.mark.slow
def test_plan_md_with_a_denylist_hit_fails_stage_2_before_any_call_shows_it(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Task 6 re-review N-B: plan.md is scanned (the real-name list with its owner clause, the
    Boundary list, the jailbreak list) before the manifest call shows it; a hit fails the stage
    as a lint failure, and the owner's name is never copied into the record."""
    owner = sorted(owner_names())[0]  # read at run time: the name is on no checked-in list
    for line, lint in (
        ("The guidelines say two reps.", "boundary_bundle"),
        (f"Signed, {owner.title()}.", "real_name_bundle"),
    ):
        root = tmp_path / lint
        planner = PlannerStub()
        run_plan(root, through="plan", planner=planner)
        plan_md = root / SLUG / "plan.md"
        plan_md.write_text(plan_md.read_text("utf-8") + f"\n{line}\n", "utf-8")
        _, record = run_plan(root, through="author", planner=planner)
        assert record.status == "failed" and record.stages[1].calls == []
        assert f"{lint}: " in (record.stages[1].error or "")
        assert [_ for _, _, m in planner.calls if "call: manifest" in m] == []
        assert owner not in (root / SLUG / "plan.json").read_text("utf-8").lower()


@pytest.mark.slow
def test_a_close_that_still_fails_after_its_repair_fails_the_stage(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec section 7 step 4: one repair per failing file, then the close again; a close that
    still fails fails the stage, as does a close past MAX_REPAIR_CALLS a plan."""
    modes = {f"file:{REPAIRED}": "close_fail", f"repair:{REPAIRED}": "close_fail"}
    _, record = run_plan(tmp_path / "still", through="author", modes=modes)
    assert record.status == "failed" and "still fails" in (record.stages[1].error or "")
    assert f"{REPAIRED}: document " in (record.stages[1].error or "")
    assert [c.purpose for c in record.stages[1].calls].count(f"repair:{REPAIRED}") == 1
    monkeypatch.setattr(director_module, "MAX_REPAIR_CALLS", 0)
    planner = PlannerStub(modes={f"file:{REPAIRED}": "close_fail"})
    _, bound = run_plan(tmp_path / "bound", through="author", planner=planner)
    assert bound.status == "failed" and "MAX_REPAIR_CALLS (0)" in (bound.stages[1].error or "")
    assert not any("call: repair:" in m for _, _, m in planner.calls)


class _BadConfigOnce(PlannerStub):
    """A planner whose first config.yaml schedules a rung the ladder lacks: a refusal only
    ``run --dry-run`` gives (spec section 7, step 5)."""

    def __init__(self) -> None:
        super().__init__()
        self.sent_bad = False

    def _reply(self, purpose: str, mode: str | None) -> str:
        reply = super()._reply(purpose, mode)
        if purpose == "file:config.yaml" and not self.sent_bad:
            self.sent_bad = True
            text = json.loads(reply)["content"].replace("the_log: 3", "the_end: 3", 1)
            return json.dumps({"content": text})
        return reply


@pytest.mark.slow
def test_config_yaml_arrives_through_the_dry_runs_refusals_and_leaves_nothing_beside_the_bundle(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Step 5 and preflight Q39: the config's arrival check is run --dry-run's against the
    bundle's worlds, its runs root a temporary directory, so the plans root holds the bundle
    and the cache alone."""
    planner = _BadConfigOnce()
    bundle, record = run_plan(tmp_path, through="author", planner=planner)
    config = next(c for c in record.stages[1].calls if c.purpose == "file:config.yaml")
    assert (config.status, config.attempts) == ("fresh", 2)
    retry = next(m for cid, _, m in planner.calls if cid.endswith("/a2"))
    assert "### Fix these" in retry and "run --dry-run refuses it" in retry
    assert str(tmp_path) not in retry  # the message names no path outside the bundle
    assert sorted(p.name for p in tmp_path.iterdir()) == ["_cache", SLUG]
    assert not [p for p in bundle.root.iterdir() if p.name == "good_bundle"]


@pytest.mark.slow
def test_a_copy_killed_midway_is_removed_and_made_again(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-copy: a kill between the copied files and the record write that commits them leaves
    files no record owns; the resume removes them and copies again, byte-equal. A resume after
    the copy committed never copies again, so a patched base file keeps its patch."""
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author")
    real = Bundle.write_file
    written: list[str] = []

    def dying(self: Bundle, rel: str, text: str) -> str:
        sha = real(self, rel, text)
        if rel.startswith("worlds/"):
            written.append(rel)
        if len(written) == 3:
            raise Crash(f"killed after copying {rel}")
        return sha

    monkeypatch.setattr(Bundle, "write_file", dying)
    with pytest.raises(Crash):
        run_plan(tmp_path / "killed", through="author", resume=False)
    held = Bundle(tmp_path / "killed" / SLUG).read_record()
    assert held.base_worlds == {} and all(rel.startswith("worlds/mini/") for rel in written)
    monkeypatch.setattr(Bundle, "write_file", real)
    bundle, record = run_plan(tmp_path / "killed", through="author")
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean) and record.resumed == []
    patched = Kill("files", "file:worlds/mini/corpus/canteen-menu.md")
    bundle, record = run_plan(tmp_path / "patched", through="author", kill=patched)
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)


# ---------------------------------------------------------------- fix round 1 (the 7b review)


def _leave_temp(path: Path, text: str) -> None:
    """What a process killed outright inside ``write_atomic(path, text)`` leaves: its temp file
    beside the target, half written, never renamed and never removed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, _ = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "wb") as handle:
        handle.write(text.encode("utf-8")[: max(1, len(text) // 2)])


def _temps(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.tmp"))


def _opens(text: str, stage: str | None) -> bool:
    """Whether a ``plan.json`` text is the write that creates the plan (``stage`` None) or the
    one that opens ``stage``: its last stage record is that stage, open, with no call."""
    stages = json.loads(text)["stages"]
    if stage is None:
        return not stages
    last = stages[-1] if stages else None
    return (
        last is not None
        and last["stage"] == stage
        and last["status"] == "open"
        and not last["calls"]
    )


@pytest.mark.slow
@pytest.mark.parametrize("stage", [None, "plan", "author"])
def test_a_kill_inside_the_write_that_opens_a_stage_leaves_no_temp_file(
    stage: str | None, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review I1: a hard kill inside the record write that creates the plan (7a's K1) or opens
    a stage leaves that write's temp file and no record of the stage. Every pass of run()
    removes it, so the resumed bundle holds nothing bundle_hash covers that an unbroken one
    lacks."""
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author")
    real = bundle_module.write_atomic
    fired: list[Path] = []

    def dying(path: Path, text: str) -> None:
        if not fired and path.name == "plan.json" and _opens(text, stage):
            fired.append(path)
            _leave_temp(path, text)
            raise Crash(f"killed inside the write that opens {stage}")
        real(path, text)

    monkeypatch.setattr(bundle_module, "write_atomic", dying)
    with pytest.raises(Crash):
        run_plan(tmp_path / "killed", through="author", resume=False)
    monkeypatch.setattr(bundle_module, "write_atomic", real)
    assert len(_temps(tmp_path / "killed")) == 1
    bundle, record = run_plan(tmp_path / "killed", through="author")  # plan new again
    assert _temps(tmp_path / "killed") == []
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)


def _ledger_ids(root: Path) -> list[tuple[str, str]]:
    lines = (root / "ledger.jsonl").read_text("utf-8").splitlines()
    parsed = [LedgerLine.model_validate_json(line) for line in lines]
    return [(line.conversation_id.split("/", 2)[-1], line.status) for line in parsed]


@pytest.mark.slow
@pytest.mark.parametrize("purpose", ["manifest", "file:config.yaml"])
def test_a_torn_last_ledger_line_is_dropped_and_the_resume_goes_on(
    purpose: str, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review M1 (re-graded Important) and the sweep's kills 22 and 93: a kill inside a ledger
    append leaves a torn last line, half a record and no newline. The resume drops it by the
    runtime's torn-tail rule (runner/store.py) and goes on, ending as an unbroken plan does,
    the dead call redone: the manifest's ok line, and a timeout's line (the double times out
    once)."""
    index = 0 if purpose == "manifest" else INDEX["config.yaml"]
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author")
    planner = PlannerStub(modes={} if purpose == "manifest" else {purpose: "timeout"})
    real = Ledger.write
    torn: list[str] = []

    def tearing(self: Ledger, line: LedgerLine) -> None:
        if not torn and f"/author/planner/{index}/" in line.conversation_id:
            raw = line.model_dump_json()
            torn.append(raw)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(raw[: len(raw) // 2])
            raise Crash(f"killed inside the ledger line of {purpose}")
        real(self, line)

    monkeypatch.setattr(Ledger, "write", tearing)
    with pytest.raises(Crash):
        run_plan(tmp_path / "killed", through="author", planner=planner, resume=False)
    monkeypatch.setattr(Ledger, "write", real)
    assert not (tmp_path / "killed" / SLUG / "ledger.jsonl").read_bytes().endswith(b"\n")
    bundle, record = run_plan(tmp_path / "killed", through="author", planner=planner)
    assert record.status == "authored"
    assert [(a.stage, a.role, a.index) for a in record.resumed] == [("author", "planner", index)]
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)
    assert _ledger_ids(bundle.root) == _ledger_ids(clean_bundle.root)


@pytest.mark.parametrize("damage", ["not a record", "a cut record closed off"])
def test_damage_in_the_middle_of_the_plan_ledger_still_raises(
    damage: str, tmp_path: Path, isolated_registry: None
) -> None:
    """Review M1's other half: only a torn last line is dropped. A line that does not parse in
    the middle of the ledger, even a record cut short that a newline closed off, is damage, and
    the resume raises naming the line before it writes anything."""
    director = _planned(tmp_path)
    ledger = director.bundle.root / "ledger.jsonl"
    line = ledger.read_bytes()  # the plan call's one line, ended by its newline
    bad = b"not json\n" if damage == "not a record" else line[: len(line) // 2] + b"\n"
    ledger.write_bytes(bad + line + line[: len(line) // 2])  # damage, a record, a torn tail
    before = director.bundle.read_record()
    with pytest.raises(ValueError, match="ledger.jsonl: line 1 is not valid JSON"):
        director.run(through="author")
    assert director.bundle.read_record() == before


@pytest.mark.slow
@pytest.mark.parametrize("purpose", ["manifest", "file:worlds/mini/world.yaml"])
def test_a_kill_inside_a_cache_put_leaves_no_temp_file(
    purpose: str, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sweep's cache-litter cases (kills 25 and 31, review N1): a hard kill inside the cache
    put that follows a committed call leaves the put's temp file in the cache folder. The resume
    removes the temp of each key a call of this plan committed; a temp beside a key no call of
    this plan names (another plan's put in flight) is left alone."""
    clean_bundle, clean = run_plan(tmp_path / "clean", through="author")
    armed: list[bool] = []
    real = JudgeCache.put

    def dying(self: JudgeCache, key: str, value: dict[str, Any]) -> None:
        if armed == [True]:
            armed.append(False)  # once
            _leave_temp(self.directory / f"{key}.json", json.dumps(value, indent=1))
            raise Crash(f"killed inside the cache put of {purpose}")
        real(self, key, value)

    def checkpoint(step: str, called: str) -> None:
        if (step, called) == ("files", purpose) and not armed:
            armed.append(True)

    monkeypatch.setattr(JudgeCache, "put", dying)
    director = Director.new(
        REQUEST,
        plans_root=tmp_path / "killed",
        provider_factory=StubFactory(PlannerStub(), ReviewerStub()),
        worlds_dir=WORLDS_DIR,
        checkpoint=checkpoint,
    )
    with pytest.raises(Crash):
        director.run(through="author")
    monkeypatch.setattr(JudgeCache, "put", real)
    cache = tmp_path / "killed" / "_cache" / "director"
    assert len(_temps(cache)) == 1
    other = cache / f".{'0' * 64}.json.abcdefgh.tmp"
    other.write_text("{}", "utf-8")
    bundle, record = run_plan(tmp_path / "killed", through="author")
    assert _temps(tmp_path / "killed") == [other.relative_to(tmp_path / "killed").as_posix()]
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)
    killed_keys, clean_keys = cache_keys(tmp_path / "killed"), cache_keys(tmp_path / "clean")
    assert len(clean_keys - killed_keys) == 1 and killed_keys < clean_keys


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.slow
def test_inputs_and_edited_are_re_recorded_after_a_plan_md_fix(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Review M2, case A, the designed recovery path: plan.md fails its scan, the owner puts the
    planner's text back and continues. The record then says what the stage's calls read:
    plan.md as its committing call wrote it, so it is not edited."""
    planner = PlannerStub()
    run_plan(tmp_path, through="plan", planner=planner)
    plan_md = tmp_path / SLUG / "plan.md"
    good = plan_md.read_bytes()
    plan_md.write_bytes(good + b"\nThe guidelines say two reps.\n")
    _, failed = run_plan(tmp_path, through="author", planner=planner)
    assert failed.status == "failed" and failed.edited == ["plan.md"]
    plan_md.write_bytes(good)
    _, record = run_plan(tmp_path, through="author", planner=planner)
    assert record.status == "authored" and record.edited == []
    assert record.stages[1].inputs == {"plan.md": _sha(good)}


@pytest.mark.slow
def test_inputs_and_edited_are_re_recorded_after_an_edit_made_during_a_pause(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Review M2, case B: the owner edits plan.md while a rate limit holds stage 2 open. The
    remaining calls see the edit, so the resume records it: ``edited`` names plan.md and
    ``inputs`` holds the sha the next call reads."""
    planner = PlannerStub(modes={f"file:{DOC1}": "rate_limit"})
    with pytest.raises(RateLimitExit):
        run_plan(tmp_path, through="author", planner=planner, resume=False)
    assert Bundle(tmp_path / SLUG).read_record().edited == []
    plan_md = tmp_path / SLUG / "plan.md"
    plan_md.write_bytes(plan_md.read_bytes() + b"Owner note: two reps are enough.\n")
    planner.calls.clear()
    _, record = run_plan(tmp_path, through="author", planner=planner)
    assert record.status == "authored" and record.edited == ["plan.md"]
    assert record.stages[1].inputs == {"plan.md": _sha(plan_md.read_bytes())}
    _, _, first = planner.calls[0]
    assert f"call: file:{DOC1}" in first and "Owner note: two reps are enough." in first


def _by_hand(tmp_path: Path) -> Director:
    """A planned Director whose bundle holds the good bundle written by hand over the base
    world's copy, so an arrival check runs with no call."""
    director = _planned(tmp_path)
    director._copy_worlds([BASE_WORLD])
    for rel, text in _good_files().items():
        director.bundle.write_file(rel, text)
    return director


def test_a_documents_front_matter_layer_must_be_its_manifest_entrys(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Review M3: the manifest's floor and filler share read the entries' layers, so a document
    whose front matter says another layer fails its arrival check, naming both."""
    director = _by_hand(tmp_path)
    entry = next(e for e in GOOD_MANIFEST if e.path == DOC1)
    assert entry.layer is not None
    reply = json.dumps({"content": (GOOD / DOC1).read_text("utf-8")})
    assert director._check_file(entry, reply)[1] == []
    other = next(layer for layer in Layer if layer is not entry.layer)
    _, found = director._check_file(entry.model_copy(update={"layer": other}), reply)
    assert found == [
        f"{DOC1}: its front matter's layer is {entry.layer.value}, but its manifest entry "
        f"says {other.value}"
    ]


@pytest.mark.parametrize("gating", ["triggered", "scheduled"])
def test_config_yaml_naming_a_ladder_its_world_lacks_fails_arrival_under_every_gating(
    gating: str, tmp_path: Path, isolated_registry: None
) -> None:
    """Review M4: the schema lint's ladder clause (Task 4a) runs at the config's arrival under
    every gating, so a missing ladder is refused in stage 2, once, and not by stage 5 after the
    review calls; the dry run checks the conditions whose environment passed."""
    director = _by_hand(tmp_path)
    entry = next(e for e in GOOD_MANIFEST if e.kind == "config")
    good = (GOOD / "config.yaml").read_text("utf-8")
    lines = good.split("\n")
    at = lines.index(f"    gating: {gating}")
    lines[at - 1] = lines[at - 1].replace("ladder: default", "ladder: nope")
    _, found = director._check_file(entry, json.dumps({"content": "\n".join(lines)}))
    assert found == [f"config.yaml: environment 'mini_{gating}': world 'mini' has no ladder 'nope'"]
    assert director._check_file(entry, json.dumps({"content": good}))[1] == []


@pytest.mark.parametrize(("documents", "reviews"), [(25, 3), (26, 4), (50, 4), (51, 5)])
def test_the_budget_counts_the_review_calls_a_chunked_corpus_makes(
    documents: int, reviews: int, tmp_path: Path, isolated_registry: None
) -> None:
    """Review M5: the budget counts one corpus call per REVIEW_CHUNK_DOCS (25) documents, then
    the lines and plan groups, so a chunked corpus's plan is refused at its manifest."""
    entries = _fresh(documents, documents // 3 + 1)
    total = 1 + 1 + len(entries) + reviews  # the plan call, the manifest, its files, the reviews
    fresh = REQUEST.model_copy(
        update={"world": "fresh", "base_world": None, "max_director_calls": total}
    )
    director = _planned(tmp_path, request=fresh)
    reply = json.dumps({"files": [e.model_dump(mode="json") for e in entries]})
    assert director._check_manifest(reply, made=1)[1] == []
    director.record.request = fresh.model_copy(update={"max_director_calls": total - 1})
    (refused,) = director._check_manifest(reply, made=1)[1]
    assert f"and {reviews} review calls make {total}" in refused
