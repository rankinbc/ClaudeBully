# tests/test_director_primitive.py
"""Phase 5 Task 7a: the call primitive and stage 1 on stubs, resume parity at K1 and K4 to K6
on the plan call."""

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.metrics.judge import JudgeCache
from claude_bully.planner import context
from claude_bully.planner import director as director_module
from claude_bully.planner.bundle import Bundle, materialize, rematerialize_open_stage
from claude_bully.planner.director import (
    ROLE_KEY_EXCLUDES,
    CallSpec,
    Director,
    DirectorError,
    conversation_id,
    director_cache_key,
)
from claude_bully.planner.records import ManifestEntry, PlanRecord
from claude_bully.planner.request import slug_for
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

OPUS = RoleConfig(provider=ProviderKind.claude_code, model="opus")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def test_the_cache_key_is_the_role_and_every_byte_sent() -> None:  # R-cache-key
    schema = {"type": "object"}
    role = _digest(OPUS.model_dump(mode="json", exclude=set(ROLE_KEY_EXCLUDES)))
    base = director_cache_key(OPUS, "sys", "msg", schema)
    assert base == JudgeCache.key("opus", f"1\0{role}\0{_digest(schema)}\0msg", system="sys")
    for changed in (
        director_cache_key(OPUS.model_copy(update={"model": "sonnet"}), "sys", "msg", schema),
        director_cache_key(
            OPUS.model_copy(update={"provider": ProviderKind.anthropic}), "sys", "msg", schema
        ),
        director_cache_key(OPUS.model_copy(update={"effort": "high"}), "sys", "msg", schema),
        director_cache_key(OPUS, "sys2", "msg", schema),
        director_cache_key(OPUS, "sys", "msg2", schema),
        director_cache_key(OPUS, "sys", "msg", {"type": "array"}),
        director_cache_key(OPUS, "sys", "msg", None),
    ):
        assert changed != base
    # where the CLI lives and how long to wait change no reply: the same key
    assert (
        director_cache_key(OPUS.model_copy(update={"timeout_s": 30.0}), "sys", "msg", schema)
        == base
    )


def test_the_conversation_id_shape() -> None:
    assert conversation_id("s", "author", "planner", 4, 2) == "plan/s/author/planner/4/a2"


def test_stage_1_stops_without_no_confirm(tmp_path: Path, isolated_registry: None) -> None:
    planner = PlannerStub()
    director = Director.new(
        REQUEST,
        plans_root=tmp_path,
        provider_factory=StubFactory(planner, ReviewerStub()),
        worlds_dir=WORLDS_DIR,
    )
    record = director.run(stop_after_plan=True)
    assert record.status == "planned" and [s.stage for s in record.stages] == ["plan"]
    assert (director.bundle.root / "plan.md").is_file()


def test_every_call_resets_its_session_first(tmp_path: Path, isolated_registry: None) -> None:
    planner = PlannerStub()
    run_plan(tmp_path, through="plan", planner=planner)
    assert [cid for cid, _, _ in planner.calls] == planner.resets


def test_a_cache_hit_is_checked_and_a_prompt_edit_is_a_miss(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    bundle, _ = run_plan(tmp_path, through="plan")
    shutil.rmtree(bundle.root)
    _, again = run_plan(tmp_path, through="plan")
    assert {c.status for s in again.stages for c in s.calls} == {"cached"}
    edited = tmp_path / "planner.md"
    edited.write_text(context.load_director_prompt("planner") + "One more line.\n", "utf-8")
    monkeypatch.setitem(context.PROMPT_FILES, "planner", edited)  # a dict (review Minor 13)
    shutil.rmtree(bundle.root)
    _, third = run_plan(tmp_path, through="plan")
    assert {c.status for s in third.stages for c in s.calls} == {"fresh"}


def test_a_rate_limited_call_pauses_and_resumes_with_no_dead_attempt(
    tmp_path: Path, isolated_registry: None
) -> None:
    _, clean = run_plan(tmp_path / "clean", through="plan")
    with pytest.raises(RateLimitExit):
        run_plan(tmp_path / "paused", through="plan", modes={"plan": "rate_limit"}, resume=False)
    paused = Bundle(tmp_path / "paused" / clean.slug)
    assert paused.read_attempt() is None  # D-rate-limit
    held = paused.read_record()
    assert held.stages[0].status == "open" and held.stages[0].calls == []
    _, resumed = run_plan(tmp_path / "paused", through="plan")
    assert resumed.resumed == []
    assert comparable(resumed) == comparable(clean)


def test_a_timeout_is_an_error_and_never_waited_on(tmp_path: Path, isolated_registry: None) -> None:
    _, record = run_plan(tmp_path, through="plan", modes={"plan": "timeout"})
    (call,) = record.stages[0].calls
    assert call.status == "error" and call.attempts == 1 and record.status == "failed"


def test_continuing_a_failed_stage_records_no_dead_attempt(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Review I2 (R-marker): a provider error commits an error call at index 0 and leaves the
    marker naming it; the resume reads the marker before it moves the call out, so nothing is
    recorded as dead, and the stage is retried from that call."""
    planner = PlannerStub(modes={"plan": "provider_error"})  # fires once (R-stub-modes)
    factory = StubFactory(planner, ReviewerStub())
    director = Director.new(
        REQUEST, plans_root=tmp_path / "plans", provider_factory=factory, worlds_dir=WORLDS_DIR
    )
    failed = director.run(through="plan")
    assert failed.status == "failed" and failed.stages[0].calls[0].status == "error"
    again = Director.open(director.bundle.root, provider_factory=factory, worlds_dir=WORLDS_DIR)
    record = again.run(through="plan")
    assert record.resumed == [] and record.stages[0].status == "committed"
    assert [c.status for c in record.stages[0].calls] == ["fresh"]
    assert (director.bundle.root / "transcripts" / "failed" / "plan-planner-0.json").is_file()
    clean_bundle, _ = run_plan(tmp_path / "clean", through="plan")
    assert hashed_files(director.bundle.root) == hashed_files(clean_bundle.root)


KILLS = {  # the plan call, index 0 of stage 1
    "K1": dict(crash_at="plan", dead=("plan", "planner", 0)),
    "K4": dict(kill=Kill("transcript", "plan"), dead=("plan", "planner", 0)),
    "K5": dict(kill=Kill("record", "plan"), dead=None),
    "K6": dict(kill=Kill("files", "plan"), dead=None),
}


@pytest.mark.parametrize("point", list(KILLS))
def test_a_plan_killed_at_its_plan_call_resumes_byte_equal(
    point: str, tmp_path: Path, isolated_registry: None
) -> None:
    spec = dict(KILLS[point])
    dead = spec.pop("dead")
    clean_bundle, clean = run_plan(tmp_path / "clean", through="plan")
    bundle, record = run_plan(tmp_path / "killed", through="plan", **spec)
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)
    assert comparable(record) == comparable(clean)
    assert [(a.stage, a.role, a.index) for a in record.resumed] == ([dead] if dead else [])
    killed_keys, clean_keys = cache_keys(tmp_path / "killed"), cache_keys(tmp_path / "clean")
    if point in ("K5", "K6"):  # committed, never asked again: the put did not happen
        assert len(clean_keys - killed_keys) == 1 and killed_keys < clean_keys
    else:
        assert killed_keys == clean_keys


# ---------------------------------------------------------------- beyond the brief's tests


def _ledger(bundle: Bundle) -> list[tuple[str, str]]:
    lines = (bundle.root / "ledger.jsonl").read_text("utf-8").splitlines()
    return [(json.loads(line)["conversation_id"], json.loads(line)["status"]) for line in lines]


@pytest.mark.parametrize("point", list(KILLS))
def test_a_killed_plan_calls_ledger_reads_as_an_unbroken_ones(
    point: str, tmp_path: Path, isolated_registry: None
) -> None:
    """Task 5's derived ledger, carried: a dead attempt's lines leave the plan's ledger at the
    resume (a K4 kill had written the call's line), so it holds an unbroken plan's lines."""
    spec = {k: v for k, v in KILLS[point].items() if k != "dead"}
    clean_bundle, _ = run_plan(tmp_path / "clean", through="plan")
    bundle, _ = run_plan(tmp_path / "killed", through="plan", **spec)
    assert _ledger(clean_bundle) == [(f"plan/{clean_bundle.slug}/plan/planner/0/a1", "ok")]
    assert _ledger(bundle) == _ledger(clean_bundle)


SLUG = slug_for(REQUEST.question)


def _director(plans_root: Path, planner: PlannerStub, **kw: object) -> Director:
    factory = StubFactory(planner, ReviewerStub())
    return Director.new(
        REQUEST, plans_root=plans_root, provider_factory=factory, worlds_dir=WORLDS_DIR, **kw
    )


def _manifest_spec() -> CallSpec:
    """A call the planner double answers as the manifest, checked as JSON, committing no file."""

    def check(reply: str) -> tuple[object, list[str]]:
        try:
            return json.loads(reply), []
        except ValueError:
            return None, ["the reply is not JSON"]

    return CallSpec(
        stage="plan",
        role="planner",
        purpose="manifest",
        system="planner",
        schema={"type": "object"},
        message=lambda failures: "call: manifest\n" + "".join(f"- {f}\n" for f in failures),
        check=check,
        outputs=lambda parsed: {},
    )


def test_a_reply_that_fails_its_check_is_asked_once_more_with_the_failures(
    tmp_path: Path, isolated_registry: None
) -> None:
    planner = PlannerStub(modes={"manifest": "off_contract"})  # the first attempt only
    director = _director(tmp_path, planner)
    answer = director.ask(_manifest_spec())
    assert (answer.call.status, answer.call.attempts, answer.call.error) == ("fresh", 2, None)
    assert [cid for cid, _, _ in planner.calls] == [
        f"plan/{SLUG}/plan/planner/0/a{n}" for n in (1, 2)
    ]
    assert "- the reply is not JSON" in planner.calls[1][2]
    transcript = director.bundle.read_transcript(answer.call.transcript)
    assert [a.reply for a in transcript.attempts][0] == "not json" and len(transcript.attempts) == 2
    assert cache_keys(tmp_path) == {answer.call.cache_key}  # the passing attempt's key

    twice = _director(tmp_path / "twice", PlannerStub(modes={"manifest": "off_contract:twice"}))
    failed = twice.ask(_manifest_spec())
    assert (failed.call.status, failed.call.attempts, failed.call.error) == (
        "error",
        2,
        "the reply is not JSON",
    )
    assert not failed.provider_failed and cache_keys(tmp_path / "twice") == set()


def test_a_calls_record_fields_commit_in_the_same_write_as_the_call(
    tmp_path: Path, isolated_registry: None
) -> None:
    """R-commit: killed right after the commit, plan.json holds the call and the field it sets;
    an error call sets none."""

    def commit(parsed: object, record: PlanRecord) -> None:
        assert isinstance(parsed, dict)
        record.manifest = [ManifestEntry.model_validate(entry) for entry in parsed["files"]]

    director = _director(tmp_path, PlannerStub(), checkpoint=Kill("record", "manifest"))
    with pytest.raises(Crash):
        director.ask(replace(_manifest_spec(), commit=commit))
    held = director.bundle.read_record()
    assert held.manifest == GOOD_MANIFEST and [c.purpose for c in held.stages[0].calls] == [
        "manifest"
    ]
    failing = _director(tmp_path / "twice", PlannerStub(modes={"manifest": "off_contract:twice"}))
    assert failing.ask(replace(_manifest_spec(), commit=commit)).call.status == "error"
    assert failing.bundle.read_record().manifest == []


def test_a_cache_hit_that_fails_its_check_is_asked_again(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle, clean = run_plan(tmp_path, through="plan")
    key = clean.stages[0].calls[0].cache_key
    cache = JudgeCache(tmp_path / "_cache" / "director")
    cache.put(key, {"reply": "  \n"})  # blank: plan.md's check refuses it
    shutil.rmtree(bundle.root)
    planner = PlannerStub()
    _, again = run_plan(tmp_path, through="plan", planner=planner)
    assert [(c.status, c.attempts) for c in again.stages[0].calls] == [("fresh", 1)]
    assert len(planner.calls) == 1
    assert cache.get(key) == {"reply": (GOOD / "plan.md").read_text("utf-8")}


def test_the_call_ceiling_fails_the_stage_before_any_call(
    tmp_path: Path, isolated_registry: None
) -> None:
    planner = PlannerStub()
    request = REQUEST.model_copy(update={"max_director_calls": 0})
    bundle, record = run_plan(tmp_path, through="plan", request=request, planner=planner)
    assert record.status == "failed" and record.stages[0].status == "failed"
    assert "max_director_calls (0)" in (record.stages[0].error or "")
    assert planner.calls == [] and record.stages[0].calls == [] and bundle.read_attempt() is None


def test_a_message_over_the_context_limit_is_refused_before_it_is_sent(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ASSUMED (Task 6 left it to 7a): a message over MAX_CONTEXT_CHARS is never sent; the call
    commits nothing, the marker goes (no call died), and the stage and the plan fail."""
    monkeypatch.setattr(director_module, "MAX_CONTEXT_CHARS", 1_000)
    planner = PlannerStub()
    bundle, record = run_plan(tmp_path, through="plan", planner=planner)
    assert record.status == "failed" and "MAX_CONTEXT_CHARS (1,000)" in (
        record.stages[0].error or ""
    )
    assert planner.calls == [] and record.stages[0].calls == [] and bundle.read_attempt() is None
    assert not (bundle.root / "transcripts").exists()


def test_a_calls_reasoning_text_is_written_nowhere(tmp_path: Path, isolated_registry: None) -> None:
    """Non-negotiable 6: a Director call's Completion.reasoning_text reaches no file."""
    secret = "PRIVATE-REASONING-7731"
    run_plan(tmp_path, through="plan", planner=PlannerStub(reasoning=secret))
    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert files and not [path for path in files if secret.encode() in path.read_bytes()]


def test_a_resume_removes_what_a_killed_write_atomic_left(
    tmp_path: Path, isolated_registry: None
) -> None:
    """R-tmp: a temp file write_atomic left beside its target is gone after the resume."""
    clean_bundle, _ = run_plan(tmp_path / "clean", through="plan")
    with pytest.raises(Crash):
        run_plan(tmp_path / "killed", through="plan", kill=Kill("record", "plan"), resume=False)
    root = tmp_path / "killed" / SLUG
    leftovers = [
        root / ".plan.md.k3j4h5g6.tmp",
        root / ".plan.json.x0x0x0x0.tmp",
        root / "transcripts" / ".plan-planner-0.json.ab_12cd3.tmp",
    ]
    for path in leftovers:
        path.write_text("torn", "utf-8")
    bundle, _ = run_plan(tmp_path / "killed", through="plan")
    assert [path for path in leftovers if path.exists()] == []
    assert hashed_files(bundle.root) == hashed_files(clean_bundle.root)


def test_rematerializing_rewrites_the_open_stage_and_removes_what_nothing_owns(
    tmp_path: Path, isolated_registry: None
) -> None:
    with pytest.raises(Crash):  # K5: the plan call committed, plan.md not written
        run_plan(tmp_path / "open", through="plan", kill=Kill("record", "plan"), resume=False)
    bundle = Bundle(tmp_path / "open" / SLUG)
    record = bundle.read_record()
    bundle.write_file("personas/stray.yaml", "name: stray\n")
    record.base_files["worlds/mini/world.yaml"] = bundle.write_file(
        "worlds/mini/world.yaml", "x: 1\n"
    )
    assert rematerialize_open_stage(bundle, record, "plan") == ["plan.md"]
    assert bundle.read_file("plan.md") == (GOOD / "plan.md").read_text("utf-8")
    assert list(bundle.index()) == ["plan.md", "worlds/mini/world.yaml"]
    assert rematerialize_open_stage(bundle, record, "plan") == []  # nothing differs now

    done, _ = run_plan(tmp_path / "done", through="plan")  # a committed stage is the owner's
    done.write_file("plan.md", "The owner's plan.\n")
    done.write_file("personas/stray.yaml", "name: stray\n")
    assert rematerialize_open_stage(done, done.read_record(), "plan") == []
    assert (
        done.read_file("plan.md") == "The owner's plan.\n" and "personas/stray.yaml" in done.index()
    )


def test_materialize_rebuilds_the_committed_files_and_refuses_a_transcript_that_moved(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle, record = run_plan(tmp_path, through="plan")
    before = hashed_files(bundle.root)
    (bundle.root / "plan.md").unlink()
    assert materialize(bundle, record) == ["plan.md"]
    assert hashed_files(bundle.root) == before
    assert (
        materialize(bundle, record) == [] and materialize(bundle, record, stages=["author"]) == []
    )
    rel = record.stages[0].calls[0].transcript
    transcript = bundle.read_transcript(rel)
    transcript.attempts[-1].reply = "Another plan.\n"
    bundle.write_transcript(rel, transcript)
    (bundle.root / "plan.md").unlink()
    with pytest.raises(ValueError, match="sha256"):  # Task 1 review N5: never written
        materialize(bundle, record)
    assert not (bundle.root / "plan.md").exists()


def test_a_committed_stage_is_never_opened_again_over_its_transcripts(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Task 1 review M1, carried: a second record of a stage name would number its calls from 0
    and write over the first record's transcripts; the Director refuses to open one."""
    planner = PlannerStub()
    director = _director(tmp_path, planner)
    director.run(through="plan")
    transcript = director.bundle.root / "transcripts" / "plan-planner-0.json"
    written, held = transcript.read_bytes(), director.bundle.read_record()
    with pytest.raises(DirectorError, match="stage plan has a record already"):
        director.ask(_manifest_spec())
    assert transcript.read_bytes() == written and director.bundle.read_record() == held
    assert len(planner.calls) == 1


def test_plan_new_on_a_slug_that_holds_another_request_is_refused(
    tmp_path: Path, isolated_registry: None
) -> None:
    run_plan(tmp_path, through="plan")
    other = REQUEST.model_copy(update={"seed": 1})
    with pytest.raises(DirectorError, match="another request"):
        Director.new(
            other, plans_root=tmp_path, provider_factory=StubFactory(PlannerStub(), ReviewerStub())
        )


# ---------------------------------------------------------------- fix round 1 (task-7a-review.md)


def _command(
    plans_root: Path, planner: PlannerStub, checkpoint: Kill | None = None
) -> PlanRecord | None:
    """One `plan new` on the same request: the record it returns, or None when it was killed."""
    director = _director(plans_root, planner, checkpoint=checkpoint)
    try:
        return director.run(through="plan")
    except Crash:
        return None


def _state(plans_root: Path) -> tuple[object, ...]:
    """Everything parity compares, for a plan made under ``plans_root``."""
    bundle = Bundle(plans_root / SLUG)
    record = bundle.read_record()
    failed = bundle.root / "transcripts" / "failed"
    kept = {p.name: p.read_bytes() for p in failed.iterdir()} if failed.is_dir() else {}
    return comparable(record), hashed_files(bundle.root), _ledger(bundle), kept


@pytest.mark.parametrize("failure", ["provider_error", "check_twice"])
def test_a_plan_killed_after_its_error_call_commits_fails_as_an_unbroken_one(
    failure: str, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review C1: killed after an error call's commit and before the stage fails, the resume
    handles the committed call as a fresh answer: the stage and the plan fail as an unbroken
    run's do, and the continue that follows ends where an unbroken continue ends."""
    modes = {"plan": "provider_error"} if failure == "provider_error" else {}
    if failure == "check_twice":
        monkeypatch.setattr(director_module, "MAX_PLAN_CHARS", 10)  # both attempts refused
    clean = _command(tmp_path / "clean", PlannerStub(modes=modes))
    assert clean is not None and clean.status == "failed"
    (call,) = clean.stages[0].calls
    assert call.status == "error" and call.provider_failed is (failure == "provider_error")
    assert _command(tmp_path / "killed", PlannerStub(modes=modes), Kill("record", "plan")) is None
    resumed = _command(tmp_path / "killed", PlannerStub(modes=modes))
    assert resumed is not None and resumed.status == "failed"
    assert not (tmp_path / "killed" / SLUG / "plan.md").exists()
    assert _state(tmp_path / "killed") == _state(tmp_path / "clean")
    monkeypatch.setattr(director_module, "MAX_PLAN_CHARS", 20_000)
    for root in ("clean", "killed"):
        final = _command(tmp_path / root, PlannerStub())
        assert final is not None and final.status == "planned"
    assert _state(tmp_path / "killed") == _state(tmp_path / "clean")


@pytest.mark.parametrize("point", ["K1", "K4"])
def test_a_kill_in_a_continued_call_keeps_the_earlier_error_calls_ledger_line(
    point: str, tmp_path: Path, isolated_registry: None
) -> None:
    """Review I1: the retried call reuses the error call's index and conversation id, so only
    the lines after the marker's ledger offset are the dead attempt's."""
    _command(tmp_path / "clean", PlannerStub(modes={"plan": "provider_error"}))
    _command(tmp_path / "clean", PlannerStub())
    _command(tmp_path / "killed", PlannerStub(modes={"plan": "provider_error"}))
    if point == "K1":
        assert _command(tmp_path / "killed", PlannerStub(crash_at="plan")) is None
    else:
        assert _command(tmp_path / "killed", PlannerStub(), Kill("transcript", "plan")) is None
    record = _command(tmp_path / "killed", PlannerStub())
    assert record is not None and [(a.stage, a.index) for a in record.resumed] == [("plan", 0)]
    cid = f"plan/{SLUG}/plan/planner/0/a1"
    assert _ledger(Bundle(tmp_path / "clean" / SLUG)) == [(cid, "error"), (cid, "ok")]
    assert _state(tmp_path / "killed")[:3] == _state(tmp_path / "clean")[:3]


def test_a_dead_attempt_is_recorded_once_when_its_resume_dies_before_the_marker_clears(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review M1: the runtime's flagged rule (runner/env_turn.py), so a marker the record
    already names as the last dead attempt is not appended again."""
    with pytest.raises(Crash):
        run_plan(tmp_path, through="plan", kill=Kill("transcript", "plan"), resume=False)
    clear = Bundle.clear_attempt
    deaths: list[str] = []

    def dying(bundle: Bundle) -> None:
        if not deaths:
            deaths.append("killed before the marker clear")
            raise Crash(deaths[0])
        clear(bundle)

    monkeypatch.setattr(Bundle, "clear_attempt", dying)
    with pytest.raises(Crash):
        run_plan(tmp_path, through="plan", resume=False)
    _, record = run_plan(tmp_path, through="plan")
    assert [(a.stage, a.role, a.index) for a in record.resumed] == [("plan", "planner", 0)]


def test_a_retry_over_the_context_limit_commits_the_attempt_that_was_sent(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review M2: attempt 1 was sent, so a retry over MAX_CONTEXT_CHARS is an error call that
    records it, never a refusal that leaves its ledger line owned by no record."""
    from claude_bully.providers.ledger import activate

    monkeypatch.setattr(director_module, "MAX_CONTEXT_CHARS", 1_000)
    spec = replace(
        _manifest_spec(),
        message=lambda failures: "call: manifest\n" + ("x" * 2_000 if failures else ""),
    )
    director = _director(tmp_path, PlannerStub(modes={"manifest": "off_contract"}))
    with activate(director.bundle.root / "ledger.jsonl"):
        answer = director.ask(spec)
    assert (answer.call.status, answer.call.attempts) == ("error", 1)
    assert "MAX_CONTEXT_CHARS (1,000)" in (answer.call.error or "")
    assert "the retry was not sent" in (answer.call.error or "")
    transcript = director.bundle.read_transcript(answer.call.transcript)
    assert [a.reply for a in transcript.attempts] == ["not json"]
    assert _ledger(director.bundle) == [(f"plan/{SLUG}/plan/planner/0/a1", "ok")]
    assert director.bundle.read_record().stages[0].calls == [answer.call]


def test_a_call_that_fails_across_two_continues_keeps_both_failed_transcripts(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review M3: the second failure's transcript is numbered past the first's under failed/,
    never written over it."""
    for limit in (10, 20):
        monkeypatch.setattr(director_module, "MAX_PLAN_CHARS", limit)
        _, record = run_plan(tmp_path, through="plan")
        assert record.status == "failed"
    monkeypatch.setattr(director_module, "MAX_PLAN_CHARS", 20_000)
    _, record = run_plan(tmp_path, through="plan")
    assert record.status == "planned"
    failed = tmp_path / SLUG / "transcripts" / "failed"
    kept = {p.name: p.read_bytes() for p in failed.iterdir()}
    assert set(kept) == {"plan-planner-0.json", "plan-planner-0-2.json"}
    assert b"at most 10" in kept["plan-planner-0.json"]
    assert b"at most 20" in kept["plan-planner-0-2.json"]


def test_stop_after_plan_on_a_committed_plan_stops(tmp_path: Path, isolated_registry: None) -> None:
    """Review M4: `plan new` again on a planned slug, without --no-confirm, never authors."""
    bundle, _ = run_plan(tmp_path, through="plan")
    factory = StubFactory(PlannerStub(), ReviewerStub())
    again = Director.open(bundle.root, provider_factory=factory, worlds_dir=WORLDS_DIR)
    record = again.run(stop_after_plan=True)
    assert record.status == "planned" and [s.stage for s in record.stages] == ["plan"]


@pytest.mark.slow  # a plan through stage 4
def test_a_stage_not_built_yet_is_refused_before_it_opens(
    tmp_path: Path, isolated_registry: None
) -> None:
    """Review N1: until Task 9 lands, a run past the revise stage names the stage it lacks."""
    bundle, _ = run_plan(tmp_path, through="revise")
    again = Director.open(
        bundle.root,
        provider_factory=StubFactory(PlannerStub(), ReviewerStub()),
        worlds_dir=WORLDS_DIR,
    )
    with pytest.raises(NotImplementedError, match="stage validate"):
        again.run(through="validate")
    stages = [s.stage for s in bundle.read_record().stages]
    assert stages == ["plan", "author", "review", "revise"]
