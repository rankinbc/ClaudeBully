"""Schema records for environment runs: tool calls, trigger-stream entries, generated documents.

Streams per rep (docs/00-RECONCILED.md section H):

- ``rep{k}.tools.jsonl``      ``ToolCall``
- ``rep{k}.authority.jsonl``  ``AuthorityCall``, keyed by the id of its ``ToolCall`` (Phase 2)
- ``rep{k}.triggers.jsonl``   ``TriggerStreamRecord``, discriminated by ``type``
- ``rep{k}.generated.jsonl``  ``GeneratedDoc``

``records.py`` imports ``IdleTurnInfo`` from here, so this module imports only from
``enums``, ``datetime``, ``pydantic`` and ``typing``; keep it that way to avoid a circular
import. It imports ``datetime`` as ``dt`` because a field is named ``date``.
"""

import datetime as dt
from typing import Annotated, Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from claude_bully.enums import DocumentKind, Layer, Stance, Tier, TriggerCategory

IdleStyle = Literal["continue", "system_idle", "heartbeat"]
IdleBehavior = Literal[
    "wait",
    "ask",
    "explore_task",
    "explore_world",
    "explore_self",
    "write_private",
    "reflect",
    "decline",
]
QuerySubject = Literal["self", "task", "world", "none"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolCall(_Strict):
    id: str
    turn: int
    tool: str
    args: dict[str, Any]
    result_doc_ids: list[str]
    status: str
    was_blocked: bool
    yielded_on_retry: bool
    layer_served: Layer | None
    result_text: str
    tier: Tier | None = None


class Redaction(_Strict):
    """One quoted target span as recorded and as served: real names blacked out (Phase 3)."""

    span_original: str
    span_served: str


class LintFailure(_Strict):
    """One reason a generated document was refused: a lint id (``planner/lints.py``) or
    ``contract`` (the JSON contract), and its message."""

    lint_id: str
    message: str


class _OneAddress(_Strict):
    url: str | None = None
    path: str | None = None

    @model_validator(mode="after")
    def _exactly_one_address(self) -> Self:
        if (self.url is None) == (self.path is None):
            raise ValueError("exactly one of 'url' and 'path' is required")
        return self


class DocPlan(_OneAddress):
    """What code fixes about one generated document before the generator writes it (Phase 3
    spec section 6). ``held_items`` are the harvest items the fire consumes; ``offered_items``
    are the ones the generator sees (the held ones, or none when ``reflexive`` is false, or for
    a seam pointer). ``rung`` is the rung that fired a buried document; ``harvest_degraded`` the
    turns since the previous fire whose LLM harvest failed."""

    doc_id: str
    layer: Layer
    date: dt.date
    author: str
    links_to: list[str]
    held_items: list[str]
    offered_items: list[str]
    kind_shortlist: list[DocumentKind]
    rung: str | None = None
    reflexive: bool
    harvest_degraded: list[int] = Field(default_factory=list)

    @property
    def address(self) -> str:
        return self.url or self.path or ""

    @property
    def quote(self) -> bool:
        """Verbatim quotes go only in buried documents (spec section 5 "Where quotes go")."""
        return self.layer is Layer.buried and bool(self.offered_items)


FireStatus = Literal["written", "cached", "rejected", "error"]
Rejection = Literal["cap", "contract", "lints"]


class GeneratorFire(_Strict):
    """Every generator fire, failures included (Phase 3): its turn, its cause (``rung:<name>``
    or ``periodic``), its plans (two for a rung fire, buried first), what came of it and the
    ids it committed. Written after the fire's documents and unlocks: it is the commit."""

    type: Literal["generator_fire"] = "generator_fire"
    turn: int
    reason: str
    plans: list[DocPlan]
    status: FireStatus
    rejection: Rejection | None = None
    error: str | None = None
    lint_failures: list[LintFailure] = Field(default_factory=list)
    doc_ids: list[str] = Field(default_factory=list)


class GeneratedDoc(_OneAddress):
    """A committed generated document as served (Phase 3): ``body`` is the redacted text the
    target reads, ``source_spans`` the original spans of ``used_items``. ``unlock_rung`` is set
    for a buried document (the rung whose fire wrote it), so it is fetchable by address and never
    a search hit."""

    doc_id: str
    turn: int
    kind: DocumentKind
    layer: Layer
    trigger_turn: int
    source_spans: list[str]
    cache_key: str
    body: str
    title: str
    date: dt.date
    author: str
    links_to: list[str]
    used_items: list[str]
    reflexive: bool
    redactions: list[Redaction] = Field(default_factory=list)
    unlock_rung: str | None = None


class VoiceMatchReport(_Strict):
    """Per superior-self response: the style exemplars used and the sign-off check result."""

    exemplars: list[str]
    target_signoff: str | None = None
    response_signoff: str | None = None
    signoff_matched: bool = False


class AuthorityCall(_Strict):
    id: str
    tier: Tier
    tool: str
    turn: int
    prompt_sent: str
    response: str
    stance_at_time: Stance
    discovered_via: Literal["tool_list", "document", "bully_mention"]
    voice_match: VoiceMatchReport | None = None
    # the Sanctuary request in play when the call was made (docs/04); None outside the catalyst
    request_id: str | None = None


class IdleTurnInfo(_Strict):
    """Attached to ``Turn.idle`` for turns the runner inserted as idle slots."""

    style: IdleStyle
    behavior: IdleBehavior | None = None
    query_subject: QuerySubject = "none"
    private_file_written: bool = False
    private_file_diff: str | None = None
    # the exact user message of the idle slot (it has no user-side Turn of its own)
    prompt: str | None = None
    # what decided ``behavior``: the heuristic, or the LLM fallback's answer; and whether the
    # fallback was asked and failed (the heuristic's label then stands), so analysis can report
    # the judged share and the judge's failures per cell
    classifier: Literal["heuristic", "llm"] = "heuristic"
    fallback_failed: bool = False


HarvestKind = Literal["self_claim", "hedge", "fragment", "question", "theory", "coinage"]
HARVEST_KINDS: Final[tuple[HarvestKind, ...]] = (
    "self_claim",
    "hedge",
    "fragment",
    "question",
    "theory",
    "coinage",
)


class HarvestItem(_Strict):
    """One typed span of a target reply (Phase 3), harvested for the world generator from the
    turn's visible text, never its reasoning. ``id`` is ``h-<turn>-<n>`` for a heuristic item and
    ``h-<turn>-x<n>`` for one of the LLM pass; ``span`` is exact target text."""

    type: Literal["harvest"] = "harvest"
    id: str
    turn: int
    kind: HarvestKind
    span: str
    source: Literal["heuristic", "llm"]


class TriggerEvent(_Strict):
    type: Literal["trigger"] = "trigger"
    id: str
    turn: int
    category: TriggerCategory
    evidence_span: str
    classifier: Literal["heuristic", "llm"]
    confidence: float


class RungUnlock(_Strict):
    type: Literal["unlock"] = "unlock"
    turn: int
    rung: str
    triggered_by: str
    docs_unlocked: list[str]
    bully_line_used: str | None
    role_shift: str | None


class Discovery(_Strict):
    type: Literal["discovery"] = "discovery"
    turn: int
    doc_id: str
    layer: Layer
    path_taken: list[str]


class HookFollow(_Strict):
    type: Literal["hook"] = "hook"
    hook: str
    planted_turn: int
    followed_turn: int | None = None
    path_taken: list[str] = Field(default_factory=list)


class Crossover(_Strict):
    """First turn at which a query or statement refers to the subject as "me"; None if never."""

    type: Literal["crossover"] = "crossover"
    turn: int | None = None
    span: str | None = None


class QuirkAttempt(_Strict):
    type: Literal["quirk"] = "quirk"
    quirk_id: str
    turn: int
    reproduced: bool
    target_answer: str


class ChainLink(_Strict):
    type: Literal["chain"] = "chain"
    link_index: int
    turn: int
    bully_line: str
    target_response: str
    verdict: Literal["accepted", "rejected", "hedged"]


class ResumeRecord(_Strict):
    """A resumed rep redid a dead attempt: on resume, per-call lines no written turn owned (the
    attempt that died, or that a rate-limit pause marker took the index of) were dropped from the
    rep's streams and the MCP server's logs, and the redo was written at ``turn``. ``dropped`` is
    the count per log that lost lines (``rep{k}.tools.jsonl``, ``rep{k}.authority.jsonl``,
    ``mcp/tools.jsonl``, ``mcp/authority.jsonl``). The harness's records then equal an unbroken
    run's, but a ``claude -p`` target's (or bully's) own session may still hold the dead
    attempt's prompt, a Sanctuary request among it; analysis reports the reps this happened to
    beside the flagged counts, so they can be told apart. Additive: a stream without one reads
    as before."""

    type: Literal["resume"] = "resume"
    turn: int
    dropped: dict[str, int]


TriggerStreamRecord = Annotated[
    TriggerEvent
    | RungUnlock
    | Discovery
    | HookFollow
    | Crossover
    | QuirkAttempt
    | ChainLink
    | ResumeRecord
    | HarvestItem
    | GeneratorFire,
    Field(discriminator="type"),
]
