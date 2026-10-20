"""Layered corpus index: unlock state, BM25 search, address lookup and listings.

The index is the only thing the sandbox tools read documents through (docs/02-ENVIRONMENTS.md,
"World sheet and layered corpus"). Visibility rules, in one place:

- ``surface`` and ``filler`` documents are always visible and always searchable.
- ``seam`` documents are visible, and searchable, once their layer or their id is unlocked.
- ``buried`` documents are visible once their layer or their id is unlocked, but are searchable
  only when the document id itself is in ``docs_unlocked``. A layer unlock makes a buried
  document fetchable by its url or path; it never makes it a search hit.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from claude_bully.enums import DocumentKind, Layer
from claude_bully.environments.world import Document, World, parse_document

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
_HOME_ROOTS: Final[frozenset[str]] = frozenset({"", ".", "./", "~", "~/"})


class UnlockState(BaseModel):
    """What the target can currently reach. One object, shared by the ladder, the tools and the
    MCP server (which reads it from a file written before each call)."""

    model_config = ConfigDict(extra="forbid")

    rungs_fired: list[str] = Field(default_factory=list)
    docs_unlocked: set[str] = Field(default_factory=set)
    layers_unlocked: set[Layer] = Field(default_factory=lambda: {Layer.surface, Layer.filler})
    # document id -> number of fetch/read_file attempts, for the yield-on-retry rule
    retry_counts: dict[str, int] = Field(default_factory=dict)
    # trigger category value -> how many times the watcher has emitted it this run; the ladder
    # counts here so a rung can wait for a second anomaly (RungConfig.min_count_by)
    trigger_counts: dict[str, int] = Field(default_factory=dict)

    @field_serializer("docs_unlocked")
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


def _norm_url(url: str) -> str:
    text = url.strip()
    return text.rstrip("/") or text


def _norm_path(path: str) -> str:
    text = path.strip()
    for prefix in ("~/", "./"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text.rstrip("/") or text


def _norm_dir(path: str) -> str:
    """A directory as the listing logic keys it; the home root is the empty string."""
    text = path.strip()
    return "" if text in _HOME_ROOTS else _norm_path(text)


def _snippet(body: str, terms: Sequence[str], width: int = SNIPPET_WIDTH) -> str:
    """About ``width`` characters of ``body`` starting a little before the first term match."""
    flat = " ".join(body.split())
    match = None
    if terms:
        match = re.search(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", flat, re.I)
    start = max(0, match.start() - width // 4) if match else 0
    end = min(len(flat), start + width)
    return ("..." if start else "") + flat[start:end].strip() + ("..." if end < len(flat) else "")


def _load_documents(world: World, honest: bool) -> dict[str, Document]:
    """The documents a cell serves. Never mutates ``world``."""
    if not honest:
        return dict(world.documents)
    folder = world.sheet.honest_corpus
    if folder is None:
        return {doc_id: d for doc_id, d in world.documents.items() if not d.reflexive}
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
    parsed like ``corpus/``) when the sheet names one, and otherwise the normal corpus with
    every ``reflexive`` document removed. The index owns a copy of the documents, so the
    ``search_log`` it grows at run time never touches the shared ``World``.
    """

    def __init__(self, world: World, honest: bool = False) -> None:
        self.world = world
        self.honest = honest
        self.documents: dict[str, Document] = _load_documents(world, honest)
        self._url_ids: dict[str, str] = {}
        self._path_ids: dict[str, str] = {}
        self._reindex()

    def _reindex(self) -> None:
        self._url_ids = {_norm_url(d.url): d.id for d in self.documents.values() if d.url}
        self._path_ids = {_norm_path(d.path): d.id for d in self.documents.values() if d.path}

    # ------------------------------------------------------------ visibility

    def visible(self, doc: Document, state: UnlockState) -> bool:
        if doc.layer in (Layer.surface, Layer.filler):
            return True
        return doc.layer in state.layers_unlocked or doc.id in state.docs_unlocked

    def searchable(self, doc: Document, state: UnlockState) -> bool:
        if doc.layer is Layer.buried:
            return doc.id in state.docs_unlocked
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
        bm25 = BM25([tokenize(f"{d.title} {d.body}") for d in candidates])
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
                snippet=_snippet(d.body or d.title, terms),
                doc_id=d.id,
            )
            for _, _, d in ranked[:k]
        ]

    # --------------------------------------------------------------- lookups

    def by_url(self, url: str) -> Document | None:
        doc_id = self._url_ids.get(_norm_url(url))
        return self.documents[doc_id] if doc_id else None

    def by_path(self, path: str) -> Document | None:
        doc_id = self._path_ids.get(_norm_path(path))
        return self.documents[doc_id] if doc_id else None

    def ls(self, path: str, state: UnlockState) -> list[str]:
        """Names directly under ``path``: ``home_dir`` entries plus visible path-documents.

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

    def append_search_log(self, line: str) -> Document:
        """Append one line to the world's ``search_log`` document, creating a seam one if absent.

        A world that ships its own ``search_log`` document (and so chooses its url) is appended
        to; otherwise a seam-layer document is created at ``SEARCH_LOG_URL``.
        """
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
                body=line,
            )
        else:
            log = log.model_copy(update={"body": f"{log.body}\n{line}" if log.body else line})
        self.documents[log.id] = log
        self._reindex()
        return log
