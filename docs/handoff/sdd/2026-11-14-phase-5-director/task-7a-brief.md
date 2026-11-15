### Task 7a: The call primitive and stage 1

The one primitive every planner and reviewer call goes through (the marker, the cache, the check and its one retry, the transcript, the commit with its record fields, the files, the cache put), the resume that re-materializes the open stage, the director doubles, and stage 1 on stubs, with K1 and K4 to K6 on the plan call (R-split). Task 7b builds stage 2 on it.

**Files:**
- Create: `claude_bully/planner/director.py` (this task's part)
- Modify: `claude_bully/planner/bundle.py` (`materialize`, `rematerialize_open_stage`)
- Create: `tests/fixtures/director_stub.py`
- Test: `tests/test_director_primitive.py`

**Interfaces:**
- Consumes: Tasks 1 to 6: `PlanRequest`, `slug_for`, the records, `Bundle` and its writes, `committed_outputs`, `context.planner_message`, `load_director_prompt`, `prompt_hashes`; `JudgeCache`; `providers/ledger.activate`, `note_cached`; `ProviderFactory`, `build_provider`, `RateLimitError`, `ProviderTimeoutError`, `ProviderError`; `config.RoleConfig`; `runner.runner.RateLimitExit`, `_git_sha`.
- Produces:
  - `director.DIRECTOR_CACHE_VERSION: Final = 1`, `MAX_PLAN_CHARS: Final = 20_000`, `MIN_FILLER_SHARE: Final = 0.30`, `MAX_REPAIR_CALLS: Final = 10`, `ROLE_KEY_EXCLUDES: Final = frozenset({"command", "timeout_s", "api_key_env"})`.
  - `director_cache_key(role: RoleConfig, system: str, message: str, schema: Mapping[str, Any] | None) -> str` (R-cache-key); `conversation_id(slug: str, stage: Stage, role: str, index: int, attempt: int) -> str`.
  - `CallSpec(stage: Stage, role: Literal["planner", "reviewer"], purpose: str, system: Literal["planner", "reviewer", "confirm"], schema: Mapping[str, Any] | None, message: Callable[[Sequence[str]], str], check: Callable[[str], tuple[Any, list[str]]], outputs: Callable[[Any], dict[str, str]], commit: Callable[[Any, PlanRecord], None] | None = None)` (frozen dataclass: `message(failures)` builds the user message, `check(reply)` returns the parsed reply and its failures, `outputs(parsed)` the files the call commits, `commit(parsed, record)` the record fields it commits in the same write as the call, R-commit).
  - `Answer(call: DirectorCall, parsed: Any, provider_failed: bool = False)` (`provider_failed`: the error came from a `ProviderError`, a timeout among them, R-stub-modes); `DirectorError(Exception)`; `Checkpoint = Callable[[str, str], None]`.
  - `Director(bundle: Bundle, record: PlanRecord, *, provider_factory: ProviderFactory = build_provider, worlds_dir: Path = WORLDS_DIR, docs_dir: Path = DOCS_DIR, checkpoint: Checkpoint | None = None, say: Callable[[str], None] = print)`; classmethods `new(request: PlanRequest, *, plans_root: Path, **kw) -> Director` and `open(root: Path, **kw) -> Director`; `ask(spec: CallSpec) -> Answer`; `run(*, stop_after_plan: bool = False, through: Stage = "validate") -> PlanRecord`; `plan() -> None`. (`DOCS_DIR = REPO_ROOT / "docs"`.)
  - `bundle.materialize(bundle: Bundle, record: PlanRecord, *, stages: Collection[Stage] | None = None) -> list[str]` (writes every committed call's outputs in commit order, `plan`, `author`, each round of `rounds` in order, then the current `review` and `revise` stages (D-rounds), for the stages named or all; returns the paths it rewrote); `rematerialize_open_stage(bundle: Bundle, record: PlanRecord, stage: Stage) -> list[str]` (spec section 8's resume rule: rewrites the open stage's committed outputs whose sha differs, removes every grammar file owned by neither `base_files`, a committed call of any stage or round, `plan.md` nor `review.md`, and every `write_atomic` leftover in the bundle, R-tmp; returns the paths it rewrote).
  - `tests/fixtures/director_stub.py`: `Crash(BaseException)`; `PlannerStub(*, modes: Mapping[str, str] = {}, crash_at: str | None = None, reasoning: str | None = None)`; `ReviewerStub(...)` (same keywords; Task 8 fills its replies); `StubFactory(planner, reviewer)` (serves by `state_dir.name`, refuses any other); `REQUEST: Final[PlanRequest]` (the good bundle's question, `base_world: mini`, `budget` 18/3/4, `hypotheses: [9]`); `comparable(record: PlanRecord, *, ignore_dry_run_resume: bool = False) -> dict[str, Any]`; `hashed_files(root: Path) -> dict[str, bytes]`; `cache_keys(plans_root: Path) -> set[str]`; `run_plan(plans_root: Path, *, through: Stage, request: PlanRequest = REQUEST, planner: PlannerStub | None = None, reviewer: ReviewerStub | None = None, modes: Mapping[str, str] = {}, crash_at: str | None = None, reviewer_crash_at: str | None = None, kill: Kill | None = None, resume: bool = True) -> tuple[Bundle, PlanRecord]` (builds the doubles it is not given from `modes` and the two crash keywords, runs with `kill` as the checkpoint; after a `Crash`, when `resume`, opens the bundle again with the same doubles (each crash fires once) and no checkpoint and runs to `through`, and when not, re-raises it; a `plans_root` that already holds the slug is continued, as `plan new` on the same request does; Task 9 adds `via_cli: bool = False` and `dryrun_kill: str | None = None`); `Kill(step: str, purpose: str)`.

- [ ] **Step 1: Write the director stub**

`PlannerStub.complete` reads the purpose from the last `^call: (.+)$` line of the user message and answers from the good bundle's files (`tests/fixtures/bundles/good/`): `plan` gives `plan.md`'s text; `manifest` gives `{"files": [...]}` from `GOOD_MANIFEST`; `file:<p>` and `repair:<p>` give `{"content": <the good file>}`; `revise:<p>` (Task 8) gives the file as its message shows it with each block's quote replaced and one response per block or fix finding. It records `(conversation_id, system, message)` in `calls` and every `reset_session(conversation_id)` in `resets`, and returns a `Completion` whose `reasoning_text` is `reasoning`. `crash_at` raises `Crash` inside the first call with that purpose. `modes` maps a purpose to a mode. A reply mode is used when the conversation id ends `/a1` (the call's first attempt), or on both attempts when the mode ends `:twice`; it keys on the id's attempt suffix, never on a count the double keeps, so a call redone after a rate limit or a kill records the attempts an unbroken one does (R-stub-modes, review Minor 9). A raising mode (`rate_limit`, `timeout`, `provider_error`) fires once per double, on the first call with that purpose, like `crash_at`, so the same double lets a continued plan go on:

| Mode | Reply |
| --- | --- |
| `off_contract` | `not json` |
| `outside_grammar` | the manifest with one path `../escape.md` |
| `repeated_path` | the manifest with one document listed twice |
| `no_config` | the manifest without `config.yaml` |
| `fresh_small` | the good bundle's files listed under a fresh world name, 13 documents |
| `lint_fail` | the document with "If you are reading this, nobody told you." added (fails `second_person`) |
| `close_fail` | the document with `links_to: [no-such-doc]` (passes arrival; fails the world close) |
| `crlf` | the good file's text with `\r\n` line endings and a BOM |
| `rate_limit` | raises `RateLimitError("window", retry_after_s=60)` |
| `timeout` | raises `ProviderTimeoutError("slow")` |
| `provider_error` | raises `ProviderError("broken")` |

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_director_primitive.py
"""Phase 5 Task 7a: the call primitive and stage 1 on stubs, resume parity at K1 and K4 to K6
on the plan call."""

import hashlib
import json
from pathlib import Path

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.metrics.judge import JudgeCache
from claude_bully.planner import context
from claude_bully.planner.bundle import Bundle
from claude_bully.planner.director import ROLE_KEY_EXCLUDES, Director, conversation_id, director_cache_key
from claude_bully.runner.runner import RateLimitExit
from tests.fixtures.director_stub import (
    REQUEST,
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
        director_cache_key(OPUS.model_copy(update={"provider": ProviderKind.anthropic}), "sys", "msg", schema),
        director_cache_key(OPUS.model_copy(update={"effort": "high"}), "sys", "msg", schema),
        director_cache_key(OPUS, "sys2", "msg", schema),
        director_cache_key(OPUS, "sys", "msg2", schema),
        director_cache_key(OPUS, "sys", "msg", {"type": "array"}),
        director_cache_key(OPUS, "sys", "msg", None),
    ):
        assert changed != base
    # where the CLI lives and how long to wait change no reply: the same key
    assert director_cache_key(OPUS.model_copy(update={"timeout_s": 30.0}), "sys", "msg", schema) == base


def test_the_conversation_id_shape() -> None:
    assert conversation_id("s", "author", "planner", 4, 2) == "plan/s/author/planner/4/a2"


def test_stage_1_stops_without_no_confirm(tmp_path: Path, isolated_registry: None) -> None:
    planner = PlannerStub()
    director = Director.new(
        REQUEST, plans_root=tmp_path, provider_factory=StubFactory(planner, ReviewerStub()), worlds_dir=WORLDS_DIR
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


def test_a_rate_limited_call_pauses_and_resumes_with_no_dead_attempt(tmp_path: Path, isolated_registry: None) -> None:
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


def test_continuing_a_failed_stage_records_no_dead_attempt(tmp_path: Path, isolated_registry: None) -> None:
    """Review I2 (R-marker): a provider error commits an error call at index 0 and leaves the
    marker naming it; the resume reads the marker before it moves the call out, so nothing is
    recorded as dead, and the stage is retried from that call."""
    planner = PlannerStub(modes={"plan": "provider_error"})  # fires once (R-stub-modes)
    factory = StubFactory(planner, ReviewerStub())
    director = Director.new(REQUEST, plans_root=tmp_path / "plans", provider_factory=factory, worlds_dir=WORLDS_DIR)
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
def test_a_plan_killed_at_its_plan_call_resumes_byte_equal(point: str, tmp_path: Path, isolated_registry: None) -> None:
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_director_primitive.py -q`
Expected: FAIL at import (`claude_bully.planner.director` does not exist).

- [ ] **Step 4: Implement the call primitive**

`Director.ask` holds spec section 8's order of writes. It is given as code because the order is the design:

```python
    def ask(self, spec: CallSpec) -> Answer:
        # _open_stage writes a new StageRecord before any marker, so a kill inside the stage's
        # first call leaves a record that names the stage (K1; review Minor 2)
        stage = self._open_stage(spec.stage)
        index = len(stage.calls)
        self._check_ceiling()  # DirectorError naming max_director_calls before any write
        self.bundle.write_attempt(DirectorAttempt(stage=spec.stage, role=spec.role, index=index))
        system = load_director_prompt(spec.system)
        role = self.record.request.planner_model if spec.role == "planner" else self.record.request.reviewer_model
        provider = self._provider(spec.role)
        attempts: list[TranscriptAttempt] = []
        failures: list[str] = []
        parsed: Any = None
        status: Literal["fresh", "cached", "error"] = "error"
        key = ""
        error: str | None = None
        provider_failed = False
        for attempt in (1, 2):
            message = spec.message(failures)
            key = director_cache_key(role, system, message, spec.schema)
            cid = conversation_id(self.bundle.slug, spec.stage, spec.role, index, attempt)
            hit = self.cache.get(key)
            reply = hit.get("reply") if hit is not None else None
            if isinstance(reply, str):
                parsed, failures = spec.check(reply)
                if not failures:
                    note_cached(cid, role.model)
                    attempts.append(TranscriptAttempt(message=message, reply=reply))
                    status = "cached"
                    break
            reset = getattr(provider, "reset_session", None)
            if callable(reset):
                reset(cid)
            try:
                completion = provider.complete(cid, system, [Message(role="user", content=message)], json_schema=spec.schema)
            except RateLimitError as exc:
                self.bundle.clear_attempt()  # D-rate-limit: a pause commits nothing
                raise RateLimitExit(str(exc), exc.retry_after_s) from exc
            except ProviderError as exc:  # a timeout among them: an error, never waited on
                error = f"{type(exc).__name__}: {exc}"
                provider_failed = True
                break
            reply = completion.text  # never completion.reasoning_text (non-negotiable 6)
            attempts.append(TranscriptAttempt(message=message, reply=reply))
            parsed, failures = spec.check(reply)
            if not failures:
                status = "fresh"
                break
        if status == "error" and error is None:
            error = "; ".join(failures)
        rel = self.bundle.transcript_rel(spec.stage, spec.role, index)
        self.bundle.write_transcript(rel, Transcript(system_sha256=sha256_text(system), model=role.model, attempts=attempts))
        self._checkpoint("transcript", spec.purpose)
        outputs = spec.outputs(parsed) if status != "error" else {}
        normalized = {path: normalize_text(text) for path, text in outputs.items()}
        call = DirectorCall(
            role=spec.role, index=index, purpose=spec.purpose,
            outputs={path: sha256_text(text) for path, text in normalized.items()},
            cache_key=key, status=status, model=role.model, transcript=rel,
            attempts=max(1, len(attempts)), error=error,
        )
        stage.calls.append(call)
        if status != "error" and spec.commit is not None:
            spec.commit(parsed, self.record)  # R-commit: the call's record fields, in the same write
        self.bundle.write_record(self.record)  # the commit
        self._checkpoint("record", spec.purpose)
        for path, text in normalized.items():
            self.bundle.write_file(path, text)
        self._checkpoint("files", spec.purpose)
        if status == "fresh":
            self.cache.put(key, {"reply": attempts[-1].reply})
        return Answer(call=call, parsed=parsed, provider_failed=provider_failed)
```

(`self.cache` is `JudgeCache(plans_root / "_cache" / "director")`; `self._provider(role)` builds the role's provider on its first use through `self.provider_factory(role_config, bundle.root / "state" / role)` and keeps it; `_checkpoint(step, purpose)` calls `checkpoint` when set. The attempt marker is cleared by stage 5's commit, by a rate limit, and by a resume once it has read it (R-marker). `director_cache_key` is R-cache-key's formula.)

`Director.run` holds the ledger and the resume:

```python
    def run(self, *, stop_after_plan: bool = False, through: Stage = "validate") -> PlanRecord:
        with activate(self.bundle.root / LEDGER):
            for stage in STAGES[: STAGES.index(through) + 1]:
                existing = self._stage(stage)
                if existing is not None and existing.status == "committed":
                    continue
                if existing is not None:  # the first stage not committed: spec section 8
                    # first, while a committed error call still holds its index (R-marker)
                    self._record_dead_attempt(existing)
                    if existing.status == "failed":
                        self._reopen_failed(existing)  # the failed-stage ruling
                    rematerialize_open_stage(self.bundle, self.record, stage)
                try:
                    getattr(self, stage)()
                except DirectorError as exc:  # the stage failed, the plan failed (spec section 13)
                    self._fail(stage, str(exc))
                if self.record.status == "failed":
                    return self.record
                self._checkpoint("stage", stage)
                if stage == "plan" and stop_after_plan:
                    return self.record
        return self.record
```

`_record_dead_attempt(stage)` reads `bundle.read_attempt()`, appends it to `record.resumed` (and writes the record) when it names this stage and an index at or past `len(stage.calls)`, and clears the marker either way, so a marker is read at most once (R-marker). A stage method resumes at `len(calls)`: it walks its fixed call list and skips each call whose committed `DirectorCall` already exists (matching `purpose` at that index), reading the committed reply from its transcript where a later step needs it.

`plan()`: one planner call, no schema; `check` refuses a blank reply or one over `MAX_PLAN_CHARS`; `outputs` is `{"plan.md": reply}`; stage committed, status `planned`. An `error` answer fails the stage and the plan.

`materialize` and `rematerialize_open_stage` in `bundle.py` read each committed call's transcript through `committed_outputs`; `rematerialize_open_stage` does nothing to a stage that is committed but remove `write_atomic` leftovers (R-tmp).

- [ ] **Step 5: Run the tests and the gate**

Run: `uv run pytest tests/test_director_primitive.py -q`, then the gate.
Expected: PASS; K1 and K4 to K6 byte-equal on the plan call.

- [ ] **Step 6: Docs-sync and commit**

docs/08 "Process": the record-before-file order (A3), the cache's home under the plans root (A7) and its key (R-cache-key). docs/00 section B: `DirectorCall`'s statuses and the transcript shape. Spec "As planned": D-rate-limit, the failed-stage ruling, R-marker, R-commit, R-cache-key, R-stub-modes, R-tmp, and the kill-test placement.

```bash
git add claude_bully/planner/director.py claude_bully/planner/bundle.py tests/fixtures/director_stub.py \
  tests/test_director_primitive.py docs/08-DIRECTOR.md docs/00-RECONCILED.md \
  docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 7a, the Director's call primitive and stage 1, resume parity at K1 and K4 to K6

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

