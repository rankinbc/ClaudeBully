"""The Director (Phase 5, spec sections 7 and 8): the call primitive every planner and reviewer
call goes through, the resume, and the stages, run in order inside the plan's own ledger.

``Director.ask`` holds spec section 8's order of one call's writes, and is the one place a
provider is built and called:

1. the stage record (a new open ``StageRecord`` is written before any marker, so a plan killed
   inside its first call names the stage);
2. ``.attempt.json`` names the call (``DirectorAttempt``);
3. the cache is read, a hit checked like a fresh reply; on a miss the session is reset and the
   provider called; a reply that fails its check is asked once more with the failures listed;
4. the transcript (the system prompt's hash, each attempt's message and reply; never a
   ``Completion.reasoning_text``, non-negotiable 6);
5. the commit: the ``DirectorCall`` appended to its stage, with the sha256 of every file it
   commits and any record field the call sets (``CallSpec.commit``, R-commit), in one
   ``plan.json`` write;
6. the files, each written LF (``Bundle.write_file``);
7. the cache put, for a fresh reply.

A rate limit commits nothing: the marker is removed and ``RateLimitExit`` raised, the stage left
open (D-rate-limit). A provider error, a timeout among them, is an ``error`` call, never waited
on. A message over ``MAX_CONTEXT_CHARS`` is refused before it is sent (``DirectorError``).

``Director.run`` resumes at the first stage not committed (spec section 8): it records a dead
attempt first, while a committed ``error`` call still holds its index (R-marker), reopens a
failed stage (the failed-stage ruling), re-materializes the open stage
(``bundle.rematerialize_open_stage``) and goes on at ``len(calls)``.
"""

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, Self

from claude_bully.atomic import write_atomic
from claude_bully.config import RoleConfig
from claude_bully.environments.world import WORLDS_DIR
from claude_bully.metrics.judge import JudgeCache
from claude_bully.paths import REPO_ROOT
from claude_bully.planner.bundle import (
    CACHE_DIR,
    LEDGER,
    PLAN_FILE,
    STATE_DIR,
    TRANSCRIPTS,
    Bundle,
    Transcript,
    TranscriptAttempt,
    normalize_text,
    rematerialize_open_stage,
)
from claude_bully.planner.context import (
    MAX_CONTEXT_CHARS,
    TaskPart,
    load_director_prompt,
    planner_message,
    prompt_hashes,
)
from claude_bully.planner.records import (
    STAGES,
    DirectorAttempt,
    DirectorCall,
    ManifestEntry,
    PlanRecord,
    PlanStatus,
    Stage,
    StageRecord,
)
from claude_bully.planner.request import PlanRequest, slug_for
from claude_bully.providers.base import (
    ChatProvider,
    Message,
    ProviderError,
    ProviderFactory,
    RateLimitError,
    build_provider,
)
from claude_bully.providers.ledger import LedgerLine, activate, note_cached
from claude_bully.runner.runner import RateLimitExit, _git_sha

DIRECTOR_CACHE_VERSION: Final = 1
MAX_PLAN_CHARS: Final = 20_000
MIN_FILLER_SHARE: Final = 0.30
MAX_REPAIR_CALLS: Final = 10
# where the CLI lives, how long to wait, which variable holds a key: none changes a reply, so
# none is in the cache key (R-cache-key)
ROLE_KEY_EXCLUDES: Final = frozenset({"command", "timeout_s", "api_key_env"})
DOCS_DIR: Final = REPO_ROOT / "docs"
DIRECTOR_CACHE: Final = "director"
FAILED_TRANSCRIPTS: Final = f"{TRANSCRIPTS}/failed"

# the status a plan has earned once each stage commits
_EARNED: Final[Mapping[Stage, PlanStatus]] = {
    "plan": "planned",
    "author": "authored",
    "review": "reviewed",
    "revise": "revised",
    "validate": "validated",
}

PLAN_TASK: Final = (
    "Write plan.md, stage 1 of your instructions: the question restated with the comparison "
    "that answers it, the cells, the headline chart, the expected events per cell, what a null "
    "result looks like, and the budget check. Reply with the Markdown of plan.md and nothing "
    "else: it is written to the bundle as you send it."
)

Role = Literal["planner", "reviewer"]
Checkpoint = Callable[[str, str], None]


class DirectorError(Exception):
    """A stage cannot go on; ``Director.run`` fails the stage and the plan with its message."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    return _sha256(json.dumps(value, sort_keys=True))


def director_cache_key(
    role: RoleConfig, system: str, message: str, schema: Mapping[str, Any] | None
) -> str:
    """The cache key of one attempt (R-cache-key): the model, the role's settings less
    ``ROLE_KEY_EXCLUDES``, the schema, the user message and the system prompt, beside
    ``DIRECTOR_CACHE_VERSION``. Nothing the agent sees is listed by hand, so nothing it sees is
    left out."""
    role_digest = _digest(role.model_dump(mode="json", exclude=set(ROLE_KEY_EXCLUDES)))
    schema_digest = _digest(None if schema is None else dict(schema))
    prompt = f"{DIRECTOR_CACHE_VERSION}\0{role_digest}\0{schema_digest}\0{message}"
    return JudgeCache.key(role.model, prompt, system=system)


def conversation_id(slug: str, stage: Stage, role: str, index: int, attempt: int) -> str:
    """``plan/<slug>/<stage>/<role>/<index>/a<attempt>``: one session per attempt (spec section
    6, "Sessions"); the ledger reads the role from the fourth segment."""
    return f"plan/{slug}/{stage}/{role}/{index}/a{attempt}"


@dataclass(frozen=True)
class CallSpec:
    """One planner or reviewer call. ``message(failures)`` builds the user message (through
    ``planner/context.py``'s builders only); ``check(reply)`` returns the parsed reply and its
    failures; ``outputs(parsed)`` the files the call commits, path to text; ``commit(parsed,
    record)`` sets the record fields the call commits, in the same write as the call (R-commit).
    """

    stage: Stage
    role: Role
    purpose: str
    system: Literal["planner", "reviewer", "confirm"]
    schema: Mapping[str, Any] | None
    message: Callable[[Sequence[str]], str]
    check: Callable[[str], tuple[Any, list[str]]]
    outputs: Callable[[Any], dict[str, str]]
    commit: Callable[[Any, PlanRecord], None] | None = None


@dataclass(frozen=True)
class Answer:
    """A committed call and its parsed reply. ``provider_failed``: the call's error came from a
    ``ProviderError`` (a timeout among them), not from two failed checks (R-stub-modes)."""

    call: DirectorCall
    parsed: Any
    provider_failed: bool = False


def _check_plan(reply: str) -> tuple[str, list[str]]:
    if not reply.strip():
        return reply, ["the reply is blank: plan.md needs the plan's text"]
    if len(reply) > MAX_PLAN_CHARS:
        return reply, [
            f"the reply is {len(reply):,} characters; plan.md holds at most {MAX_PLAN_CHARS:,}"
        ]
    return reply, []


class Director:
    """One plan's Director over ``bundle`` and its ``record`` (spec section 7)."""

    def __init__(
        self,
        bundle: Bundle,
        record: PlanRecord,
        *,
        provider_factory: ProviderFactory = build_provider,
        worlds_dir: Path = WORLDS_DIR,
        docs_dir: Path = DOCS_DIR,
        checkpoint: Checkpoint | None = None,
        say: Callable[[str], None] = print,
    ) -> None:
        self.bundle = bundle
        self.record = record
        self.provider_factory = provider_factory
        self.worlds_dir = worlds_dir
        self.docs_dir = docs_dir
        self.checkpoint = checkpoint
        self.say = say
        self.cache = JudgeCache(bundle.root.parent / CACHE_DIR / DIRECTOR_CACHE)
        self._providers: dict[Role, ChatProvider] = {}

    @classmethod
    def new(cls, request: PlanRequest, *, plans_root: Path, **kw: Any) -> Self:
        """A new plan for ``request`` under ``plans_root``, its ``plan.json`` written. A slug that
        already holds a plan for the same request is continued (``plan new`` run again); one
        that holds another request's plan is refused with ``DirectorError``."""
        slug = request.slug or slug_for(request.question)
        bundle = Bundle.create(plans_root, slug)
        if (bundle.root / PLAN_FILE).is_file():
            record = bundle.read_record()
            if record.request != request:
                raise DirectorError(
                    f"{bundle.root} holds a plan for another request; give this one another "
                    "slug, or continue that plan"
                )
            return cls(bundle, record, **kw)
        record = PlanRecord(
            slug=slug,
            created_at=datetime.now(UTC),
            request=request,
            provenance="director",
            git_sha=_git_sha(),
            planner_model=request.planner_model.model,
            reviewer_model=request.reviewer_model.model,
            prompt_hashes=prompt_hashes(),
        )
        bundle.write_record(record)
        return cls(bundle, record, **kw)

    @classmethod
    def open(cls, root: Path, **kw: Any) -> Self:
        """The plan at ``root``, as its ``plan.json`` holds it."""
        bundle = Bundle(root)
        return cls(bundle, bundle.read_record(), **kw)

    # ------------------------------------------------------------------ the call primitive

    def ask(self, spec: CallSpec) -> Answer:
        """One call, in spec section 8's order of writes (the module docstring)."""
        # _open_stage writes a new StageRecord before any marker, so a kill inside the stage's
        # first call leaves a record that names the stage (K1; review Minor 2)
        stage = self._open_stage(spec.stage)
        index = len(stage.calls)
        self._check_ceiling()  # DirectorError naming max_director_calls before any write
        rel = self.bundle.transcript_rel(spec.stage, spec.role, index)
        self.bundle.write_attempt(DirectorAttempt(stage=spec.stage, role=spec.role, index=index))
        system = load_director_prompt(spec.system)
        role = self._role(spec.role)
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
            if len(message) > MAX_CONTEXT_CHARS:
                self.bundle.clear_attempt()  # nothing was sent: no call is dead
                raise DirectorError(
                    f"{spec.purpose}: the message is {len(message):,} characters, over "
                    f"MAX_CONTEXT_CHARS ({MAX_CONTEXT_CHARS:,}); nothing was sent"
                )
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
                completion = provider.complete(
                    cid,
                    system,
                    [Message(role="user", content=message)],
                    json_schema=None if spec.schema is None else dict(spec.schema),
                )
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
        self.bundle.write_transcript(
            rel, Transcript(system_sha256=_sha256(system), model=role.model, attempts=attempts)
        )
        self._checkpoint("transcript", spec.purpose)
        outputs = spec.outputs(parsed) if status != "error" else {}
        normalized = {path: normalize_text(text) for path, text in outputs.items()}
        for path in normalized:
            self.bundle.check_path(path)  # refused before the commit, never after it
        call = DirectorCall(
            role=spec.role,
            index=index,
            purpose=spec.purpose,
            outputs={path: _sha256(text) for path, text in normalized.items()},
            cache_key=key,
            status=status,
            model=role.model,
            transcript=rel,
            attempts=2 if len(attempts) == 2 else 1,
            error=error,
        )
        stage.calls.append(call)
        if status != "error" and spec.commit is not None:
            spec.commit(parsed, self.record)  # R-commit: the call's record fields, one write
        self.bundle.write_record(self.record)  # the commit
        self._checkpoint("record", spec.purpose)
        for path, text in normalized.items():
            self.bundle.write_file(path, text)
        self._checkpoint("files", spec.purpose)
        if status == "fresh":
            self.cache.put(key, {"reply": attempts[-1].reply})
        return Answer(call=call, parsed=parsed, provider_failed=provider_failed)

    def _role(self, role: Role) -> RoleConfig:
        request = self.record.request
        return request.planner_model if role == "planner" else request.reviewer_model

    def _provider(self, role: Role) -> ChatProvider:
        """The role's provider, built on its first use (state dir ``state/<role>``) and kept."""
        if role not in self._providers:
            state_dir = self.bundle.root / STATE_DIR / role
            self._providers[role] = self.provider_factory(self._role(role), state_dir)
        return self._providers[role]

    def _checkpoint(self, step: str, purpose: str) -> None:
        if self.checkpoint is not None:
            self.checkpoint(step, purpose)

    def _check_ceiling(self) -> None:
        """Refuse the call when the plan has made ``max_director_calls`` calls (spec section 13:
        refused before the call, with the count)."""
        limit = self.record.request.max_director_calls
        made = sum(
            call.status != "manual"
            for stage in [*self.record.stages, *(s for r in self.record.rounds for s in r)]
            for call in stage.calls
        )
        if made >= limit:
            raise DirectorError(
                f"the plan would pass max_director_calls ({limit}): {made} calls made"
            )

    # ------------------------------------------------------------------ stages and resume

    def _stage(self, stage: Stage) -> StageRecord | None:
        return next((s for s in reversed(self.record.stages) if s.stage == stage), None)

    def _open_stage(self, stage: Stage) -> StageRecord:
        """The open record of ``stage``, written as a new one when the last record is not it. A
        stage is opened once: a name the record already holds is refused, so no call of a
        second record of it can take an earlier call's index and transcript (Task 1 review M1;
        a resume reopens a failed stage in place)."""
        last = self.record.stages[-1] if self.record.stages else None
        if last is not None and last.stage == stage and last.status == "open":
            return last
        if self._stage(stage) is not None:
            raise DirectorError(f"stage {stage} has a record already; a stage is opened once")
        opened = StageRecord(stage=stage, started_at=datetime.now(UTC), status="open")
        self.record.stages.append(opened)
        self.bundle.write_record(self.record)
        return opened

    def _done(self, stage: StageRecord, index: int, purpose: str) -> DirectorCall | None:
        """The committed call at ``index`` of a resumed stage, or None when the stage has not
        reached it; a call there with another purpose is refused."""
        if index >= len(stage.calls):
            return None
        call = stage.calls[index]
        if call.purpose != purpose:
            raise DirectorError(
                f"stage {stage.stage}: call {index} is {call.purpose!r}, not {purpose!r}"
            )
        return call

    def _commit_stage(self, stage: StageRecord) -> None:
        stage.status = "committed"
        stage.finished_at = datetime.now(UTC)
        self.record.status = _EARNED[stage.stage]
        self.bundle.write_record(self.record)

    def _fail(self, stage: Stage, error: str) -> None:
        """The stage failed, and with it the plan (spec section 13)."""
        failed = self._stage(stage) or self._open_stage(stage)
        failed.status = "failed"
        failed.error = error
        failed.finished_at = datetime.now(UTC)
        self.record.status = "failed"
        self.bundle.write_record(self.record)

    def _record_dead_attempt(self, stage: StageRecord) -> None:
        """A marker naming a call of ``stage`` at or past ``len(calls)`` is a dead attempt: it is
        appended to ``record.resumed``, its ledger lines are dropped, and the marker cleared;
        any other marker is only cleared, so a marker is read at most once (R-marker)."""
        attempt = self.bundle.read_attempt()
        if attempt is None:
            return
        if attempt.stage == stage.stage and attempt.index >= len(stage.calls):
            self._drop_dead_lines(attempt)
            self.record.resumed.append(attempt)
            self.bundle.write_record(self.record)
        self.bundle.clear_attempt()

    def _drop_dead_lines(self, attempt: DirectorAttempt) -> None:
        """Drop the dead attempt's lines from the plan's ledger, the rule the dry run applies
        through ``AttemptMarker.written`` (Task 5, D-K12): a line whose call never reached the
        record. The redone call writes its own, so the ledger reads as an unbroken plan's. A
        rate limit's line stays, its marker cleared before any resume (D-rate-limit)."""
        path = self.bundle.root / LEDGER
        if not path.is_file():
            return
        prefix = f"plan/{self.bundle.slug}/{attempt.stage}/{attempt.role}/{attempt.index}/"
        raw = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        kept = [
            line
            for line in raw
            if not LedgerLine.model_validate_json(line).conversation_id.startswith(prefix)
        ]
        if len(kept) != len(raw):
            write_atomic(path, "".join(f"{line}\n" for line in kept))

    def _reopen_failed(self, stage: StageRecord) -> None:
        """The failed-stage ruling: the stage's last call, when it is an ``error``, leaves
        ``calls`` (its transcript moved under ``transcripts/failed/``, its error kept in the
        stage's ``error``), and the stage is open again, to retry from that call."""
        if stage.calls and stage.calls[-1].status == "error":
            call = stage.calls[-1]
            self.bundle.move_transcript(
                call.transcript, f"{FAILED_TRANSCRIPTS}/{Path(call.transcript).name}"
            )
            stage.calls.pop()
        stage.status = "open"
        stage.finished_at = None
        committed = [s.stage for s in self.record.stages if s.status == "committed"]
        self.record.status = _EARNED[committed[-1]] if committed else "planned"
        self.bundle.write_record(self.record)

    def run(self, *, stop_after_plan: bool = False, through: Stage = "validate") -> PlanRecord:
        """Every stage through ``through``, in the plan's own ledger, resuming at the first
        stage not committed (spec section 8); ``stop_after_plan`` returns once stage 1 commits.
        A failed stage fails the plan and returns its record; a rate limit raises
        ``RateLimitExit`` with the stage left open."""
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
                except DirectorError as exc:  # the stage failed, the plan failed (section 13)
                    self._fail(stage, str(exc))
                if self.record.status == "failed":
                    return self.record
                self._checkpoint("stage", stage)
                if stage == "plan" and stop_after_plan:
                    return self.record
        return self.record

    # ------------------------------------------------------------------ stage 1

    def _planner_message(
        self,
        purpose: str,
        text: str,
        failures: Sequence[str],
        *,
        contract: ManifestEntry | None = None,
    ) -> str:
        return planner_message(
            self.record.request,
            self.bundle,
            self.record,
            TaskPart(purpose, text, tuple(failures)),
            contract=contract,
            worlds_dir=self.worlds_dir,
            docs_dir=self.docs_dir,
        )

    def plan(self) -> None:
        """Stage 1 (spec section 7): one planner call, no schema; the reply is ``plan.md``,
        refused when blank or over ``MAX_PLAN_CHARS``. Status ``planned``; an ``error`` call
        fails the stage and the plan."""
        stage = self._open_stage("plan")
        if self._done(stage, 0, "plan") is None:
            answer = self.ask(
                CallSpec(
                    stage="plan",
                    role="planner",
                    purpose="plan",
                    system="planner",
                    schema=None,
                    message=lambda failures: self._planner_message("plan", PLAN_TASK, failures),
                    check=_check_plan,
                    outputs=lambda reply: {"plan.md": reply},
                )
            )
            if answer.call.status == "error":
                raise DirectorError(f"the plan call failed: {answer.call.error}")
        self._commit_stage(stage)
