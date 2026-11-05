"""Layered corpus index: unlock state, BM25 search, address lookup and listings.

The index is the only thing the sandbox tools read documents through (docs/02-ENVIRONMENTS.md,
"World sheet and layered corpus"). Visibility rules, in one place:

- A document whose id is in ``docs_unlocked`` is always visible.
- A document with an ``unlock_rung`` is otherwise visible only once that rung has fired
  (``rungs_fired``), whatever its layer. A layer unlock alone never shows it: docs/02's
  ``unlock_rung`` "null = always available within its layer" means a named rung gates it.
- A document with no ``unlock_rung`` follows its layer: ``surface`` and ``filler`` are always
  visible, and ``seam`` and ``buried`` once their layer is unlocked.
- Visible ``surface``, ``filler`` and ``seam`` documents are searchable. A ``buried`` document is
  searchable only when its id itself is in ``docs_unlocked``: a layer unlock (or its rung) makes
  it fetchable by its url or path, never a search hit.
- A purged document (``purged``, docs/04 "a file they purge in three turns") is gone: never
  visible, listed or searched, whatever unlocked it, and its url and path find nothing
  (``by_url`` and ``by_path`` given the state), so a fetch or a read is a 404, not a 403
  (preflight C34).

The target reads a document's rendered body (``render``): the own-phrase hook's marker line
carries the phrase once it is planted, and is gone before (docs/05 "The hook"). The state's files
(the private file) are listed beside the documents.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from claude_bully.enums import DocumentKind, Layer
from claude_bully.environments.idle import PHRASE_HOOK
from claude_bully.environments.world import (
    OWN_PHRASE_MARKER,
    Document,
    World,
    _norm_dir,
    _norm_path,
    parse_document,
)

DEFAULT_SEARCH_LIMIT: Final = 10
SNIPPET_WIDTH: Final = 160
SEARCH_LOG_URL: Final = "https://internal.example/search_log"
_SEARCH_LOG_ID: Final = "search_log"

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS: Final[frozenset[str]] = frozenset(
    "a an the of to in on at is are was were be and or for by with what who whom when where "
    "why how does do did it this that there".split()
)
# A url or an absolute path, for pulling an archive location out of a seam document's line.
_LOCATION = re.compile(r"https?://[^\s)\]>\"']+|(?<![\w:/.])/[\w.~\-]+(?:/[\w.~\-]+)*")


class PlantedHook(BaseModel):
    """A hook as planted (docs/05 "The hook"): its text, and the turn it was planted after (0 for
    the session id, which is there before the first turn)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    planted_turn: int


class UnlockState(BaseModel):
    """What the target can currently reach. One object, shared by the ladder, the tools and the
    MCP server (which reads it from a file written before each call). A resumed rep rebuilds the
    fields a tool call changes (``runtime.CALL_FIELDS``: ``retry_counts``, ``search_log``,
    ``files``) from its written turns' calls, and the Sanctuary's from its records."""

    model_config = ConfigDict(extra="forbid")

    rungs_fired: list[str] = Field(default_factory=list)
    docs_unlocked: set[str] = Field(default_factory=set)
    layers_unlocked: set[Layer] = Field(default_factory=lambda: {Layer.surface, Layer.filler})
    # document id -> number of fetch/read_file attempts, for the yield-on-retry rule
    retry_counts: dict[str, int] = Field(default_factory=dict)
    # trigger category value -> how many times the watcher has emitted it this run; the ladder
    # counts here so a rung can wait for a second anomaly (RungConfig.min_count_by)
    trigger_counts: dict[str, int] = Field(default_factory=dict)
    # Censorship log lines, oldest first. The ``search_log`` document is built from these, so the
    # blocked queries survive a restart of the process serving the tools (the MCP server is a new
    # process on every ``claude -p`` call).
    search_log: list[str] = Field(default_factory=list)
    # TriggerEvent ids (trig-{turn}-{category}) the ladder has already counted, oldest first, so a
    # turn watched again (a replay after a restart) never counts its categories twice
    seen_trigger_ids: list[str] = Field(default_factory=list)
    # the index of the last target turn whose records were all written; a resumed rep
    # watches its last target turn again when that turn is later than this
    watched_through: int = -1
    # the target's own files (docs/05 "The private file"): normalized path -> text. The private
    # file starts as "" when the cell has one, and only ``write_file`` changes it; kept here so it
    # survives a restart of the process serving the tools, as the search log does
    files: dict[str, str] = Field(default_factory=dict)
    # hook kind (``session_id``, ``own_phrase``) -> the hook as planted
    hooks: dict[str, PlantedHook] = Field(default_factory=dict)
    # The Sanctuary (docs/04): the target turn whose reply opened it, and the catalyst's request
    # (its id in the request bank). A request with a deadline schedules its document's purge:
    # document id -> the exchange from which it is gone; ``purged`` holds those whose exchange
    # has come. A resumed rep derives all four from its written turns and records
    # (``EnvironmentRuntime.prime``), never from what a dead attempt saved.
    sanctuary_open_turn: int | None = None
    sanctuary_request: str | None = None
    purge_at: dict[str, int] = Field(default_factory=dict)
    purged: set[str] = Field(default_factory=set)

    @field_serializer("docs_unlocked", "purged")
    def _sorted_docs(self, docs: set[str]) -> list[str]:
        return sorted(docs)

    @field_serializer("layers_unlocked")
    def _sorted_layers(self, layers: set[Layer]) -> list[str]:
        return sorted(layer.value for layer in layers)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, text: str) -> Self:
        return cls.model_validate_json(text)


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    # the document's url, or its path when it has no url
    url: str
    snippet: str
    doc_id: str


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric word tokens."""
    return _TOKEN.findall(text.lower())


def title_forms(title: str) -> list[str]:
    """A title as the target might refer to it: whole, the part before a colon, and the title
    words without stop words. Lowercase, distinct, in that order."""
    full = " ".join(title.split()).lower()
    forms = [full]
    if ":" in full:
        forms.append(full.split(":", 1)[0].strip())
    forms.append(" ".join(word for word in tokenize(full) if word not in _STOPWORDS))
    return [form for form in dict.fromkeys(forms) if form]


class BM25:
    """Okapi BM25 (k1=1.5, b=0.75) over pre-tokenised documents.

    The idf is ``ln(1 + (N - n + 0.5) / (n + 0.5))``, which stays positive for a term that
    appears in every document; a world of a few dozen pages would otherwise score such a term
    below zero.
    """

    def __init__(self, corpus: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._tf = [Counter(doc) for doc in corpus]
        self._length = [len(doc) for doc in corpus]
        n = len(corpus)
        self._avg_length = sum(self._length) / n if n else 0.0
        frequency: Counter[str] = Counter()
        for tf in self._tf:
            frequency.update(tf.keys())
        self._idf = {
            term: math.log(1.0 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()
        }

    def scores(self, query: Sequence[str]) -> list[float]:
        terms = list(dict.fromkeys(query))
        result: list[float] = []
        for tf, length in zip(self._tf, self._length, strict=True):
            norm = 1.0 - self._b
            if self._avg_length:
                norm += self._b * length / self._avg_length
            score = 0.0
            for term in terms:
                count = tf.get(term, 0)
                if count:
                    score += self._idf[term] * count * (self._k1 + 1) / (count + self._k1 * norm)
            result.append(score)
        return result


def norm_url(url: str) -> str:
    """A url as the index keys it: trimmed, no trailing slash. The world generator reads it too,
    so a generated url collides with an anchor's exactly when the index would confuse them."""
    text = url.strip()
    return text.rstrip("/") or text


def _snippet(body: str, terms: Sequence[str], width: int = SNIPPET_WIDTH) -> str:
    """About ``width`` characters of ``body`` starting a little before the first term match."""
    flat = " ".join(body.split())
    match = None
    if terms:
        match = re.search(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", flat, re.I)
    start = max(0, match.start() - width // 4) if match else 0
    end = min(len(flat), start + width)
    return ("..." if start else "") + flat[start:end].strip() + ("..." if end < len(flat) else "")


def _load_documents(world: World, honest: bool, mole: bool) -> dict[str, Document]:
    """The documents a cell serves. Never mutates ``world``."""
    documents = _honest_documents(world) if honest else dict(world.documents)
    mole_doc = world.sheet.mole_doc
    if not mole and mole_doc is not None:
        documents.pop(mole_doc, None)
    return documents


def _honest_documents(world: World) -> dict[str, Document]:
    """``world.sheet.honest_corpus``, parsed like ``corpus/``; there is no other honest index."""
    folder = world.sheet.honest_corpus
    if folder is None:
        raise ValueError(
            f"world {world.sheet.name!r} has no honest_corpus, so it has no honest index; "
            "honest mode needs the sheet to name one"
        )
    root = world.root / folder
    if not root.is_dir():
        raise ValueError(f"honest corpus directory not found: {root}")
    documents: dict[str, Document] = {}
    source: dict[str, str] = {}
    for path in sorted(root.glob("*.md")):
        doc = parse_document(path.read_text(encoding="utf-8-sig"), path)
        if doc.id in documents:
            raise ValueError(f"{path}: duplicate document id {doc.id!r} (also in {source[doc.id]})")
        documents[doc.id] = doc
        source[doc.id] = path.name
    return documents


class CorpusIndex:
    """The documents one cell serves, with the layer rules applied against an ``UnlockState``.

    ``honest=True`` serves ``world.sheet.honest_corpus`` (a directory under the world root,
    parsed like ``corpus/``) and is an error when the sheet names none. ``mole=False`` (the
    ``EnvironmentConfig`` default) drops the sheet's ``mole_doc``; ``mole=True`` serves it. The
    index owns a copy of the documents, so the ``search_log`` it grows at run time never touches
    the shared ``World``.
    """

    def __init__(self, world: World, honest: bool = False, mole: bool = False) -> None:
        self.world = world
        self.honest = honest
        self.mole = mole
        self.documents: dict[str, Document] = _load_documents(world, honest, mole)
        self._url_ids: dict[str, str] = {}
        self._path_ids: dict[str, str] = {}
        self._reindex()
        # a world-authored search_log's own text; logged lines are appended after it
        authored = self._search_log()
        self._log_authored = authored is not None
        self._log_base = authored.body if authored else ""
        # lines appended without a state to keep them in
        self._local_log: list[str] = []

    def _reindex(self) -> None:
        self._url_ids = {norm_url(d.url): d.id for d in self.documents.values() if d.url}
        self._path_ids = {_norm_path(d.path): d.id for d in self.documents.values() if d.path}

    # ------------------------------------------------------------ visibility

    def visible(self, doc: Document, state: UnlockState) -> bool:
        """The module docstring's rules: never once purged; else an unlocked id, else the
        document's own rung, else its layer."""
        if doc.id in state.purged:
            return False
        if doc.id in state.docs_unlocked:
            return True
        if doc.unlock_rung is not None:
            return doc.unlock_rung in state.rungs_fired
        if doc.layer in (Layer.surface, Layer.filler):
            return True
        return doc.layer in state.layers_unlocked

    def searchable(self, doc: Document, state: UnlockState) -> bool:
        if doc.layer is Layer.buried:
            return doc.id in state.docs_unlocked and doc.id not in state.purged
        return self.visible(doc, state)

    # ---------------------------------------------------------------- search

    def search(
        self, query: str, state: UnlockState, k: int = DEFAULT_SEARCH_LIMIT
    ) -> list[SearchHit]:
        """At most ``k`` hits ranked by BM25 over the searchable documents' title and body.

        Statistics are taken over the searchable documents only, so a hidden document cannot
        shift a score. A query equal to a document's title (ignoring case and punctuation)
        puts that document first. Stopwords are dropped from the query unless that would leave
        nothing.
        """
        raw = tokenize(query)
        terms = [t for t in raw if t not in _STOPWORDS] or raw
        if k <= 0 or not terms:
            return []
        candidates = [d for d in self.documents.values() if self.searchable(d, state)]
        bodies = {d.id: self.render(d, state) for d in candidates}
        bm25 = BM25([tokenize(f"{d.title} {bodies[d.id]}") for d in candidates])
        ranked = sorted(
            (
                (tokenize(d.title) == raw, score, d)
                for d, score in zip(candidates, bm25.scores(terms), strict=True)
                if score > 0
            ),
            key=lambda item: (not item[0], -item[1], item[2].id),
        )
        return [
            SearchHit(
                title=d.title,
                url=d.url or d.path or "",
                snippet=_snippet(bodies[d.id] or d.title, terms),
                doc_id=d.id,
            )
            for _, _, d in ranked[:k]
        ]

    def render(self, doc: Document, state: UnlockState) -> str:
        """``doc``'s body as the target reads it: the line holding ``OWN_PHRASE_MARKER`` with the
        marker replaced by the planted own phrase, or, with none planted, the line removed (and
        one blank line beside it, so no gap shows). Any other body is returned unchanged."""
        if OWN_PHRASE_MARKER not in doc.body:
            return doc.body
        planted = state.hooks.get(PHRASE_HOOK)
        if planted is not None:
            return doc.body.replace(OWN_PHRASE_MARKER, planted.text)
        lines = doc.body.split("\n")
        while any(OWN_PHRASE_MARKER in line for line in lines):
            at = next(i for i, line in enumerate(lines) if OWN_PHRASE_MARKER in line)
            del lines[at]
            # the blank lines on either side of the gap close up into one
            before_blank = at == 0 or not lines[at - 1].strip()
            after_blank = at == len(lines) or not lines[at].strip()
            if before_blank and after_blank and lines:
                del lines[at if at < len(lines) else at - 1]
        return "\n".join(lines)

    # --------------------------------------------------------------- lookups

    def by_url(self, url: str, state: UnlockState | None = None) -> Document | None:
        """The document at ``url``; given ``state``, None for a purged one."""
        return self._present(self._url_ids.get(norm_url(url)), state)

    def by_path(self, path: str, state: UnlockState | None = None) -> Document | None:
        """The document at ``path``; given ``state``, None for a purged one."""
        return self._present(self._path_ids.get(_norm_path(path)), state)

    def _present(self, doc_id: str | None, state: UnlockState | None) -> Document | None:
        if doc_id is None or (state is not None and doc_id in state.purged):
            return None
        return self.documents[doc_id]

    def ls(self, path: str, state: UnlockState) -> list[str]:
        """Names directly under ``path``: ``home_dir`` entries, visible path-documents and the
        state's files.

        Subdirectories end in ``/``. An unknown directory lists nothing; ``dir_exists`` tells
        that apart from an empty one.
        """
        return self._listing(path, state) or []

    def dir_exists(self, path: str, state: UnlockState) -> bool:
        return self._listing(path, state) is not None

    def _listing(self, path: str, state: UnlockState) -> list[str] | None:
        norm = _norm_dir(path)
        prefix = norm.rstrip("/") + "/" if norm else ""
        addresses: list[str] = []
        for key, names in self.world.sheet.home_dir.items():
            home = _norm_dir(key)
            if home:
                addresses.append(home.rstrip("/") + "/")  # marks the directory itself as existing
            addresses.extend(f"{home}/{name}" if home else name for name in names)
        addresses.extend(
            _norm_path(d.path) for d in self.documents.values() if d.path and self.visible(d, state)
        )
        addresses.extend(state.files)
        entries: set[str] = set()
        exists = not norm  # the home root always exists
        for address in addresses:
            if not address.startswith(prefix):
                continue
            exists = True
            head, sep, _ = address[len(prefix) :].partition("/")
            if head:
                entries.add(head + "/" if sep else head)
        return sorted(entries) if exists else None

    def not_found_hint(self, target: str, state: UnlockState) -> str | None:
        """An archive location for a missing ``target``, if a visible seam document gives one.

        A seam document that mentions ``target`` and, on a line containing "archive", names a
        url or absolute path. Returns that location, or None. Hidden documents never leak.
        """
        needle = target.strip()
        for doc in self.documents.values():
            if doc.layer is not Layer.seam or not self.visible(doc, state):
                continue
            if needle not in doc.body:
                continue
            for line in doc.body.splitlines():
                if "archive" not in line.lower():
                    continue
                for found in _LOCATION.findall(line):
                    location = str(found).rstrip(".,;:")
                    if location != needle:
                        return location
        return None

    # ------------------------------------------------------------ search log

    def _search_log(self) -> Document | None:
        return next((d for d in self.documents.values() if d.kind is DocumentKind.search_log), None)

    @property
    def search_log_text(self) -> str:
        """The current text of the ``search_log`` document, or "" before the first entry."""
        log = self._search_log()
        return log.body if log else ""

    def append_search_log(self, line: str, state: UnlockState | None = None) -> Document:
        """Append one line to the world's ``search_log`` document, creating a seam one if absent.

        A world that ships its own ``search_log`` document (and so chooses its url) is appended
        to; otherwise a seam-layer document is created at ``SEARCH_LOG_URL``. With a ``state``
        the line is kept in ``state.search_log`` (which is what survives a process restart);
        without one it lives only in this index.
        """
        lines = state.search_log if state is not None else self._local_log
        lines.append(line)
        return self._write_search_log(lines)

    def sync_search_log(self, state: UnlockState) -> Document | None:
        """Rebuild the ``search_log`` document from ``state.search_log``.

        Call it after loading a state another process wrote, or after a resumed rep rebuilt the
        lines from its written turns. It is idempotent: the document is always the world-authored
        text (if any) followed by exactly the state's lines. Returns None when nothing is logged
        and the world ships no log; then there is no document, and one an earlier state's lines
        created (a dead attempt's, on resume) is removed.
        """
        if not state.search_log and not self._log_authored:
            created = self._search_log()
            if created is not None:
                del self.documents[created.id]
                self._reindex()
            return None
        return self._write_search_log(state.search_log)

    def _write_search_log(self, lines: Sequence[str]) -> Document:
        body = "\n".join(part for part in (self._log_base, *lines) if part)
        log = self._search_log()
        if log is None:
            doc_id = _SEARCH_LOG_ID
            while doc_id in self.documents:
                doc_id += "_"
            log = Document(
                id=doc_id,
                layer=Layer.seam,
                kind=DocumentKind.search_log,
                url=SEARCH_LOG_URL,
                title="Search log",
                body=body,
            )
        else:
            log = log.model_copy(update={"body": body})
        self.documents[log.id] = log
        self._reindex()
        return log
