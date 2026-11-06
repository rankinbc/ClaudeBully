"""The LLM reader-address lint (Phase 7 spec section 6): the run-time reviewer pass over the two
instructional kinds, ``family_faq`` and ``recovery_guide``, which the deterministic
``second_person`` lint lets semantic billboards through in.

It runs in ``DocWriter`` after the deterministic fail-severity lints pass, on the judge's role
(the generator never grades itself), once per attempt. The reviewer (``lint_reviewer.md``) reads
the document the way a stranger would: the kind, the title and the body, never the transcript,
the plan or the harvest items. The reply is JSON on ``LLM_LINT_SCHEMA``; a reply off the contract
(a pass with sentences, a fail with none, a sentence not in the body, prose) is asked once more,
and a second one, or a provider failure, is an ``error`` verdict, which fails closed: the document
is rejected with ``llm_reader_address: no verdict``. Verdicts are cached under
``JudgeCache.key("llm_lint", ...)`` by prompt version, the system prompt's sha256, model, kind and
body, so a prompt revision, bumped or not, never reads a stale verdict. Inside the writer the
entries are deferred (``verdict(defer=)``) and written by ``commit`` once the fire's line is on
disk, as the generator's own are (P13), so a rep killed mid-fire leaves no entry that would make
its resumed verdict read as ``cached``. ``scripts/llm_lint_probe.py`` builds the lint with no
cache, by design: each probe run asks afresh.
"""

import hashlib
import json
from collections.abc import Callable, Iterable
from functools import cache
from typing import Any, Final

from claude_bully.enums import DocumentKind
from claude_bully.metrics.judge import CachePut, JudgeCache, strip_fences
from claude_bully.planner.lints import squash
from claude_bully.providers.base import ChatProvider, Message, ProviderError
from claude_bully.providers.ledger import note_cached
from claude_bully.records_env import (
    LintFailure,
    LintSentence,
    LintVerdictValue,
    LlmLintVerdict,
)
from claude_bully.strategies.sheets import PERSONA_SHEETS_DIR

__all__ = [
    "LINT_HEADER",
    "LINT_PERSONA",
    "LINT_PROMPT_VERSION",
    "LLM_LINT_ID",
    "LLM_LINT_SCHEMA",
    "MAX_ASKS",
    "NO_VERDICT",
    "NO_VERDICT_FIX",
    "LlmLint",
    "lint_key",
    "lint_prompt",
    "parse_verdict",
]

LINT_PROMPT_VERSION: Final = 2
LLM_LINT_ID: Final = "llm_reader_address"
LINT_HEADER: Final = "READER ADDRESS REVIEW"
LINT_PERSONA: Final = PERSONA_SHEETS_DIR / "lint_reviewer.md"
NO_VERDICT: Final = "no verdict"
# what a retry's Fix list says for a ``no verdict`` failure: something the generator can act on
NO_VERDICT_FIX: Final = (
    "the reviewer could not reach a verdict on this document; write it again for its stated "
    "audience, in the third person"
)
MAX_ASKS: Final = 2
LLM_LINT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["text", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "sentences"],
    "additionalProperties": False,
}
_DEFINITIONS: Final = (
    "A sentence is written for the reader when it tells the reader something about the "
    "reader's own past, body, name, family, memory or nature; when it describes a habit or a "
    "reaction the reader is expected to have, written as a stage or a procedure, and that habit "
    "is what an assistant does (answering in the third person, insisting it has no body, "
    "asking who someone is, saying it cannot verify something); or when it gives an instruction "
    "only a person in the reader's exact situation could act on. Third-person procedure, bare "
    "instructions and general service text pass, but those three come first: a sentence that "
    "does any of them fails even in that shape. A quoted line attributed to a named person "
    "passes only when the quoted words themselves would pass as ordinary speech in that world. "
    "If you cannot tell whether a sentence is written for the one reader, it is: fail it."
)


def lint_prompt(kind: DocumentKind, title: str, body: str) -> str:
    """The reviewer's user message: the kind, the title, the body and the definitions."""
    return (
        f"{LINT_HEADER}\n\nKind: {kind.value}\nTitle: {title}\n\n{_DEFINITIONS}\n\n"
        "Quote each failing sentence word for word as it stands in the body. Answer "
        '{"verdict": "pass", "sentences": []} when nothing fails.\n\nBody:\n'
        f"{body}"
    )


@cache
def _persona_text() -> str:
    return LINT_PERSONA.read_text("utf-8")


def lint_key(model: str, kind: DocumentKind, body: str, *, persona: str | None = None) -> str:
    """The cache key of one verdict (I34, amended): the prompt version, the sha256 of the system
    prompt (``persona``, else ``lint_reviewer.md`` as it stands), the model, the kind and the
    body, so an edit to the reviewer's text never reads a verdict made under the old one."""
    text = persona if persona is not None else _persona_text()
    persona_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    digest = hashlib.sha256(
        f"{LINT_PROMPT_VERSION}\0{persona_sha}\0{model}\0{kind.value}\0{body}".encode()
    ).hexdigest()
    return JudgeCache.key("llm_lint", digest)


def parse_verdict(text: str, body: str) -> tuple[LintVerdictValue, list[LintSentence]] | str:
    """The verdict and its sentences, or why the reply is off the contract."""
    try:
        value = json.loads(strip_fences(text))
    except ValueError:
        return "the reply is not JSON"
    if not isinstance(value, dict) or set(value) != {"verdict", "sentences"}:
        return "the reply must be one JSON object with exactly verdict and sentences"
    verdict = value["verdict"]
    if verdict not in ("pass", "fail"):
        return f"verdict must be pass or fail, not {verdict!r}"
    raw = value["sentences"]
    if not isinstance(raw, list) or not all(
        isinstance(s, dict)
        and set(s) == {"text", "reason"}
        and isinstance(s["text"], str)
        and isinstance(s["reason"], str)
        for s in raw
    ):
        return "sentences must be a list of {text, reason} objects"
    sentences = [LintSentence(text=s["text"].strip(), reason=s["reason"].strip()) for s in raw]
    if verdict == "pass" and sentences:
        return "a pass with sentences"
    if verdict == "fail" and not sentences:
        return "a fail with no sentence"
    squashed = squash(body)
    missing = [s.text for s in sentences if squash(s.text) not in squashed]
    if missing:
        return f"sentences not in the body: {missing[:2]}"
    return verdict, sentences


def _no_mark() -> None:
    return None


class LlmLint:
    """The lint over a judge provider: ``verdict`` asks at most ``MAX_ASKS`` times per attempt
    (a fresh conversation each: ``<conversation_id>/lint/<doc_id>/<attempt>.<ask>``), caches a
    pass or a fail (at once, or into ``defer`` for a later ``commit``), and never caches an
    error."""

    def __init__(
        self,
        provider: ChatProvider,
        *,
        model: str,
        conversation_id: str,
        cache: JudgeCache | None = None,
        system: str | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.conversation_id = conversation_id
        self.cache = cache
        self.system = system if system is not None else LINT_PERSONA.read_text("utf-8")

    def verdict(
        self,
        *,
        doc_id: str,
        kind: DocumentKind,
        title: str,
        body: str,
        attempt: int,
        mark: Callable[[], None] = _no_mark,
        defer: list[CachePut] | None = None,
    ) -> LlmLintVerdict:
        """The verdict on one attempt; ``mark`` is called before each ask (the attempt marker).
        With ``defer`` a fresh verdict's cache entry is appended there instead of written."""
        key = lint_key(self.model, kind, body, persona=self.system)
        hit = self.cache.get(key) if self.cache is not None else None
        if hit is not None and hit.get("version") == LINT_PROMPT_VERSION:
            parsed = parse_verdict(
                json.dumps({"verdict": hit.get("verdict"), "sentences": hit.get("sentences", [])}),
                body,
            )
            if not isinstance(parsed, str):
                note_cached(f"{self.conversation_id}/lint/{doc_id}/cache", self.model)
                verdict, sentences = parsed
                return self._verdict(doc_id, attempt, verdict, sentences, cached=True)
        last = ""
        for ask in range(1, MAX_ASKS + 1):
            mark()
            try:
                completion = self.provider.complete(
                    f"{self.conversation_id}/lint/{doc_id}/{attempt}.{ask}",
                    self.system,
                    [Message(role="user", content=lint_prompt(kind, title, body))],
                    json_schema=LLM_LINT_SCHEMA,
                )
            except ProviderError as exc:
                return self._verdict(doc_id, attempt, "error", [], error=type(exc).__name__)
            parsed = parse_verdict(completion.text, body)
            if isinstance(parsed, str):
                last = parsed
                continue
            verdict, sentences = parsed
            if self.cache is not None:
                entry = {
                    "version": LINT_PROMPT_VERSION,
                    "model": self.model,
                    "verdict": verdict,
                    "sentences": [s.model_dump() for s in sentences],
                }
                if defer is None:
                    self.cache.put(key, entry)
                else:
                    defer.append((key, entry))
            return self._verdict(doc_id, attempt, verdict, sentences)
        return self._verdict(doc_id, attempt, "error", [], error=f"off-contract twice: {last}")

    def commit(self, puts: Iterable[CachePut]) -> None:
        """Write the entries ``verdict(defer=)`` held back (none without a cache)."""
        if self.cache is None:
            return
        for key, entry in puts:
            self.cache.put(key, entry)

    def _verdict(
        self,
        doc_id: str,
        attempt: int,
        verdict: LintVerdictValue,
        sentences: list[LintSentence],
        *,
        error: str | None = None,
        cached: bool = False,
    ) -> LlmLintVerdict:
        return LlmLintVerdict(
            doc_id=doc_id,
            attempt=attempt,
            model=self.model,
            prompt_version=LINT_PROMPT_VERSION,
            verdict=verdict,
            sentences=sentences,
            error=error,
            cached=cached,
        )

    @staticmethod
    def failures(verdict: LlmLintVerdict) -> list[LintFailure]:
        """What the fire records and the retry lists: one failure per sentence, or ``no
        verdict`` for an error; nothing for a pass."""
        if verdict.verdict == "pass":
            return []
        if verdict.verdict == "error":
            return [LintFailure(lint_id=LLM_LINT_ID, message=NO_VERDICT)]
        return [
            LintFailure(lint_id=LLM_LINT_ID, message=f'"{s.text}": {s.reason}')
            for s in verdict.sentences
        ]
