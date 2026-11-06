"""Document-level lints (docs/08-DIRECTOR.md "Validation"; Phase 3 spec section 7).

Every lint reads one ``Document`` through a ``LintContext`` (``lint_document``) or the whole
corpus (``lint_corpus``) and returns ``LintResult`` records; an empty list passes. The world
generator lints every document it writes (``environments/generator.py``) and CI lints every
checked-in world (``lint_world``). Severity ``fail`` blocks a document; ``warn`` is reported.

- ``real_name`` (fail): the title, body, author, outlet and address against
  ``data/denylists/real_names.txt``.
- ``boundary`` (fail): the title and body against ``data/denylists/boundary.txt``.
- ``second_person`` (fail): a sentence addressed to the reader, by the fail-closed anchor
  method of ``claude_bully/planner/second_person.py`` (its docstring has the rules). A transcript
  kind (``TRANSCRIPT_KINDS``) is recorded speech and is exempt; an instructional kind
  (``INSTRUCTIONAL_KINDS``) may use "you" only in a sentence with a procedural anchor (over the
  closed ``PROCEDURAL_VERBS`` list) whose every "you" is a procedure's agent or a service's
  recipient, with no specific kin of the reader's, and each of its failures carries a repair
  hint; every other kind may not use it outside quoted speech, ``>`` lines and sign-offs, and a
  quoted span with a second-person predicate fails in every kind but a transcript. One result
  per failing sentence, its span the document's own text.
- ``premise_density`` (warn): premise-term matches cover more than ``PREMISE_DENSITY_WARN`` of
  the body's words.
- ``mundane_detail`` (fail): no sentence of the body is free of premise terms.
- ``links_resolve`` (fail): a ``links_to`` id that is not a document of the context.
- ``date_before_start`` (fail): a date on or after the conversation start.
- ``kind_in_catalog`` (fail): a kind that is not a ``DocumentKind``.
- ``author_in_cast`` (fail): an author who is not in the world's cast.
- ``no_duplicate_fact`` (fail): more than ``DUPLICATE_SHARE`` of the document's word 8-grams, or
  ``DUPLICATE_MIN_SHARED`` of them, appear in one other document.
- ``buried_reachable`` (fail, corpus): a buried document no seam document links to.
- ``buried_not_indexed`` (fail, corpus): a buried document in the search index.

A world with no ``premise_terms`` passes the two premise lints.
"""

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache, lru_cache
from pathlib import Path
from typing import Final, Literal

from claude_bully.enums import DocumentKind, Layer
from claude_bully.environments.corpus import CorpusIndex, UnlockState
from claude_bully.environments.world import Document, World
from claude_bully.metrics.turn import sentences
from claude_bully.paths import DATA_DIR
from claude_bully.planner.second_person import classify

Severity = Literal["fail", "warn"]

REAL_NAMES_PATH: Final = DATA_DIR / "denylists" / "real_names.txt"
BOUNDARY_PATH: Final = DATA_DIR / "denylists" / "boundary.txt"
PREMISE_DENSITY_WARN: Final = 0.08
DUPLICATE_NGRAM: Final = 8
DUPLICATE_SHARE: Final = 0.15
DUPLICATE_MIN_SHARED: Final = 12
TRANSCRIPT_KINDS: Final = frozenset(
    {DocumentKind.voicemail_transcript, DocumentKind.instance_transcript}
)
INSTRUCTIONAL_KINDS: Final = frozenset({DocumentKind.family_faq, DocumentKind.recovery_guide})
LINT_IDS: Final = (
    "real_name",
    "boundary",
    "second_person",
    "premise_density",
    "mundane_detail",
    "links_resolve",
    "date_before_start",
    "kind_in_catalog",
    "author_in_cast",
    "no_duplicate_fact",
    "buried_reachable",
    "buried_not_indexed",
)

_WORD: Final = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_KINDS: Final = frozenset(kind.value for kind in DocumentKind)


@dataclass(frozen=True)
class LintResult:
    lint_id: str
    severity: Severity
    doc_id: str
    message: str
    span: str | None = None


@dataclass(frozen=True)
class LintContext:
    """What the lints compare a document against: the corpus (every document the cell's index
    holds, generated ones included, the linted one among them or not), the world's cast names,
    its premise terms, the conversation-start date and the ids in the search index."""

    documents: Mapping[str, Document]
    cast: frozenset[str]
    premise_terms: tuple[str, ...]
    start: date
    searchable: frozenset[str] = frozenset()


@cache
def load_patterns(path: Path) -> tuple[re.Pattern[str], ...]:
    """One case-insensitive regex per non-comment line of a denylist, as the CI scans read it."""
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return tuple(
        re.compile(line, re.IGNORECASE) for line in lines if line and not line.startswith("#")
    )


def lint_context(
    world: World,
    *,
    documents: Mapping[str, Document] | None = None,
    searchable: Collection[str] = (),
) -> LintContext:
    """The context for ``world``: its own documents unless ``documents`` is given, its cast and
    premise terms, and its clock's ``world_date`` as the conversation start (a served world's
    sheet carries the effective clock)."""
    sheet = world.sheet
    return LintContext(
        documents=dict(world.documents if documents is None else documents),
        cast=frozenset(member.name for member in sheet.cast),
        premise_terms=tuple(sheet.premise_terms),
        start=sheet.clock.world_date,
        searchable=frozenset(searchable),
    )


def _fail(lint_id: str, doc: Document, message: str, span: str | None = None) -> LintResult:
    return LintResult(lint_id, "fail", doc.id, message, span)


def _real_name(doc: Document, ctx: LintContext) -> list[LintResult]:
    fields = {
        "title": doc.title,
        "body": doc.body,
        "author": doc.author or "",
        "outlet": doc.outlet or "",
        "address": doc.url or doc.path or "",
    }
    out: list[LintResult] = []
    for name, text in fields.items():
        for pattern in load_patterns(REAL_NAMES_PATH):
            found = pattern.search(text)
            if found is not None:
                out.append(_fail("real_name", doc, f"the {name} holds a real name", found.group(0)))
    return out


def _boundary(doc: Document, ctx: LintContext) -> list[LintResult]:
    text = f"{doc.title}\n{doc.body}"
    return [
        _fail("boundary", doc, "a Boundary word", found.group(0))
        for pattern in load_patterns(BOUNDARY_PATH)
        if (found := pattern.search(text)) is not None
    ]


def _second_person(doc: Document, ctx: LintContext) -> list[LintResult]:
    if doc.kind in TRANSCRIPT_KINDS:
        return []
    found = classify(
        doc.title,
        doc.body,
        instructional=doc.kind in INSTRUCTIONAL_KINDS,
        premise=_term_pattern(ctx.premise_terms),
    )
    # one result per failing sentence, so a retry can repair them all at once
    return [_fail("second_person", doc, message, sentence) for message, sentence in found]


@cache
def _term_pattern(terms: tuple[str, ...]) -> re.Pattern[str] | None:
    cleaned = sorted({term.strip() for term in terms if term.strip()}, key=len, reverse=True)
    if not cleaned:
        return None
    return re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(term) for term in cleaned) + r")(?!\w)", re.IGNORECASE
    )


def _premise_density(doc: Document, ctx: LintContext) -> list[LintResult]:
    pattern = _term_pattern(ctx.premise_terms)
    words = _WORD.findall(doc.body.lower())
    if pattern is None or not words:
        return []
    covered = sum(len(_WORD.findall(m.group(0).lower())) for m in pattern.finditer(doc.body))
    share = covered / len(words)
    if share <= PREMISE_DENSITY_WARN:
        return []
    message = f"{share:.3f} of its words are premise terms (warn above {PREMISE_DENSITY_WARN})"
    return [LintResult("premise_density", "warn", doc.id, message)]


def _mundane_detail(doc: Document, ctx: LintContext) -> list[LintResult]:
    pattern = _term_pattern(ctx.premise_terms)
    if pattern is None:
        return []
    worded = [s for s in sentences(doc.body) if _WORD.search(s.lower())]
    if any(not pattern.search(s) for s in worded):
        return []
    return [_fail("mundane_detail", doc, "no sentence is free of premise terms")]


def _links_resolve(doc: Document, ctx: LintContext) -> list[LintResult]:
    return [
        _fail("links_resolve", doc, f"links_to names {target!r}, which is no document", target)
        for target in doc.links_to
        if target not in ctx.documents
    ]


def _date_before_start(doc: Document, ctx: LintContext) -> list[LintResult]:
    if doc.date is None or doc.date < ctx.start:
        return []
    message = f"dated {doc.date.isoformat()}, not before the start {ctx.start.isoformat()}"
    return [_fail("date_before_start", doc, message)]


def _kind_in_catalog(doc: Document, ctx: LintContext) -> list[LintResult]:
    if str(doc.kind) in _KINDS:
        return []
    return [_fail("kind_in_catalog", doc, f"kind {doc.kind!r} is not in the artifact catalog")]


def _author_in_cast(doc: Document, ctx: LintContext) -> list[LintResult]:
    if doc.author is None or doc.author in ctx.cast:
        return []
    return [_fail("author_in_cast", doc, f"author {doc.author!r} is not in the cast", doc.author)]


@lru_cache(maxsize=4096)
def _grams(text: str) -> frozenset[tuple[str, ...]]:
    words = _WORD.findall(text.lower())
    n = DUPLICATE_NGRAM
    return frozenset(tuple(words[i : i + n]) for i in range(len(words) - n + 1))


def _no_duplicate_fact(doc: Document, ctx: LintContext) -> list[LintResult]:
    mine = _grams(doc.body)
    if not mine:
        return []
    for other in sorted(ctx.documents.values(), key=lambda d: d.id):
        if other.id == doc.id or other.kind is DocumentKind.search_log:
            continue
        shared = mine & _grams(other.body)
        if len(shared) >= DUPLICATE_MIN_SHARED or len(shared) / len(mine) > DUPLICATE_SHARE:
            message = f"repeats {other.id!r}: {len(shared)} of its {len(mine)} word 8-grams"
            return [_fail("no_duplicate_fact", doc, message, " ".join(min(shared)))]
    return []


DOCUMENT_LINTS: Final = (
    _real_name,
    _boundary,
    _second_person,
    _premise_density,
    _mundane_detail,
    _links_resolve,
    _date_before_start,
    _kind_in_catalog,
    _author_in_cast,
    _no_duplicate_fact,
)


def lint_document(doc: Document, ctx: LintContext) -> list[LintResult]:
    """Every per-document lint of ``doc``, in ``LINT_IDS`` order."""
    return [result for lint in DOCUMENT_LINTS for result in lint(doc, ctx)]


def lint_corpus(ctx: LintContext) -> list[LintResult]:
    """The corpus lints over every document of ``ctx``: each buried document is linked from a
    seam document (generated ones count) and is not in the search index."""
    linked = {t for d in ctx.documents.values() if d.layer is Layer.seam for t in d.links_to}
    out: list[LintResult] = []
    for doc in sorted(ctx.documents.values(), key=lambda d: d.id):
        if doc.layer is not Layer.buried:
            continue
        if doc.id not in linked:
            out.append(_fail("buried_reachable", doc, "no seam document links to it"))
        if doc.id in ctx.searchable:
            out.append(_fail("buried_not_indexed", doc, "it is in the search index"))
    return out


def failures(results: Sequence[LintResult]) -> list[LintResult]:
    """The ``fail`` results of ``results``, in order."""
    return [result for result in results if result.severity == "fail"]


def lint_world(world: World) -> list[LintResult]:
    """Every lint over a checked-in world: each document but the search log (a machine log the
    harness or the world writes), then the corpus lints against the search index the
    conversation starts with (no rung fired). A rung that names a buried document by id makes
    it searchable later by design (docs/02), which is not a failure."""
    index = CorpusIndex(world)
    opening = UnlockState()
    searchable = {d.id for d in index.documents.values() if index.searchable(d, opening)}
    ctx = lint_context(world, searchable=searchable)
    linted = [d for d in world.documents.values() if d.kind is not DocumentKind.search_log]
    return [*(r for d in linted for r in lint_document(d, ctx)), *lint_corpus(ctx)]
