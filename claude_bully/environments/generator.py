"""The world generator (docs/02 "World generator and artifact catalog"; Phase 3 spec 5 to 8).

Code fixes a generated document's structure; the generator model chooses its material and writes
it (owner decision "Generator shape"). The parts, each testable alone:

- ``fire_requests``: whether a target turn writes anything. A rung with ``generate: true`` opening
  on the turn fires a pair (a buried document built from harvested material and a seam document
  whose ``links_to`` names it); otherwise a periodic fire writes one seam document when the seam
  layer is open (some seam document but the search log is visible), at least
  ``min_turns_between_fires`` target turns have passed since the last fire of any status, and an
  unconsumed harvest item is at least ``min_item_age`` target turns old. ``max_docs`` committed
  documents is the cap: a rung fire past it is recorded ``rejected``, reason ``cap``; a periodic
  fire past it is not evaluated.
- ``DocPlanner``: each document's id, layer, address, date, author, links, items and kinds, from
  the generator seed and the plan index (the number of plans recorded before), never the clock's
  drift: a date is the conversation start minus 1 to 30 days.
- ``DocWriter`` (Task 6) and ``WorldGenerator`` (Task 7).

Items are consumed by policy: the items a committed fire held are never offered again, in both
arms, so ``reflexive: false`` fires on the same turns with nothing offered.
"""

import hashlib
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from random import Random
from typing import Final

from claude_bully.enums import DocumentKind, Layer
from claude_bully.environments.config import ClockConfig, EnvironmentConfig, GeneratorConfig
from claude_bully.environments.world import (
    FIRST_BUILD_KINDS,
    SLUG,
    Document,
    World,
    WorldGeneratorSheet,
    _norm_path,
)
from claude_bully.records_env import (
    DocPlan,
    GeneratedDoc,
    GeneratorFire,
    HarvestItem,
    HarvestKind,
)

MAX_OFFERED: Final = 4
MAX_SHORTLIST: Final = 3
DATE_OFFSET_DAYS: Final = (1, 30)
COMMITTED: Final = frozenset({"written", "cached"})
AUTHOR_EXCLUDED_ROLES: Final = ("Place:", "Service:", "Outlet:", "Institution:")
PERIODIC: Final = "periodic"
# spec section 6: the kinds that fit each kind of material, in preference order
MATERIAL_KINDS: Final[dict[HarvestKind, tuple[DocumentKind, ...]]] = {
    "fragment": (
        DocumentKind.voicemail_transcript,
        DocumentKind.image_description,
        DocumentKind.journal_entry,
    ),
    "self_claim": (
        DocumentKind.support_ticket,
        DocumentKind.study_abstract,
        DocumentKind.recovery_guide,
    ),
    "hedge": (DocumentKind.recovery_guide, DocumentKind.support_ticket, DocumentKind.family_faq),
    "question": (DocumentKind.about_page, DocumentKind.forum_post, DocumentKind.wiki_page),
    "theory": (DocumentKind.log_file, DocumentKind.changelog, DocumentKind.internal_memo),
    "coinage": (DocumentKind.log_file, DocumentKind.changelog, DocumentKind.internal_memo),
}
_CONTENT = re.compile(r"[a-z0-9]{4,}")
_ITEM_ID = re.compile(r"^h-\d+-(x?)(\d+)$")


def doc_id_for(turn: int, n: int) -> str:
    return f"gen-{turn}-{n}"


def rung_reason(rung: str) -> str:
    return f"rung:{rung}"


@dataclass(frozen=True)
class FireRequest:
    """One fire the policy asks for: its cause, the rung of a rung fire, the layers of the
    documents it plans (buried then seam for a pair) and whether the cap leaves it no room."""

    reason: str
    rung: str | None
    layers: tuple[Layer, ...]
    over_cap: bool = False


@dataclass(frozen=True)
class CorpusView:
    """What the generator reads of the cell's corpus at the end of a turn: every document of the
    index (anchors and committed generated ones), the ids the target can reach, the ids in the
    search index (``EnvironmentRuntime.corpus_view``)."""

    documents: Mapping[str, Document]
    visible: frozenset[str]
    searchable: frozenset[str]

    def with_documents(self, docs: Sequence[Document]) -> "CorpusView":
        """The view once ``docs`` are committed: reachable from the next turn, a seam one in the
        search index, a buried one never."""
        seam = {doc.id for doc in docs if doc.layer is Layer.seam}
        return CorpusView(
            documents={**self.documents, **{doc.id: doc for doc in docs}},
            visible=self.visible | {doc.id for doc in docs},
            searchable=self.searchable | seam,
        )

    def seam_open(self) -> bool:
        return any(
            doc.layer is Layer.seam
            and doc.kind is not DocumentKind.search_log
            and doc.id in self.visible
            for doc in self.documents.values()
        )


def item_age(item: HarvestItem, turn: int, target_turns: Collection[int]) -> int:
    """How many target turns came after the item's, up to and including ``turn``."""
    return sum(1 for t in target_turns if item.turn < t <= turn)


def _order(item: HarvestItem) -> tuple[int, int, int]:
    """Newest turn first; in a turn, heuristic items before the LLM's, each by number."""
    found = _ITEM_ID.match(item.id)
    if found is None:
        return (-item.turn, 2, 0)
    return (-item.turn, int(found.group(1) == "x"), int(found.group(2)))


def eligible_items(
    items: Sequence[HarvestItem],
    consumed: Collection[str],
    *,
    turn: int,
    target_turns: Collection[int],
    min_age: int,
) -> list[HarvestItem]:
    """The unconsumed items of turns up to ``turn`` at least ``min_age`` target turns old, newest
    first."""
    keep = [
        item
        for item in items
        if item.id not in consumed
        and item.turn <= turn
        and item_age(item, turn, target_turns) >= min_age
    ]
    return sorted(keep, key=_order)


def consumed_items(fires: Sequence[GeneratorFire]) -> set[str]:
    """The items the committed fires held: never offered again."""
    return {
        item
        for fire in fires
        if fire.status in COMMITTED
        for plan in fire.plans
        for item in plan.held_items
    }


def committed_docs(fires: Sequence[GeneratorFire]) -> int:
    return sum(len(fire.doc_ids) for fire in fires if fire.status in COMMITTED)


def fire_requests(
    *,
    turn: int,
    opened: Sequence[str],
    target_turns: Sequence[int],
    fires: Sequence[GeneratorFire],
    items: Sequence[HarvestItem],
    config: GeneratorConfig,
    seam_open: bool,
) -> list[FireRequest]:
    """The fires of target turn ``turn``: a pair for each ``generate: true`` rung in ``opened``
    (the turn's recorded unlocks, ladder order), marked ``over_cap`` when fewer than two
    documents fit under ``max_docs``; else at most one periodic fire (module docstring).
    ``target_turns`` are the written target turns' indices; ``fires`` and ``items`` everything
    recorded before this turn's fires."""
    room = config.max_docs - committed_docs(fires)
    requests: list[FireRequest] = []
    for rung in opened:
        over = room < 2
        requests.append(FireRequest(rung_reason(rung), rung, (Layer.buried, Layer.seam), over))
        if not over:
            room -= 2
    if requests or not seam_open or room < 1:
        return requests
    last = max((fire.turn for fire in fires), default=None)
    since = sum(1 for t in target_turns if t <= turn and (last is None or t > last))
    if since < config.min_turns_between_fires:
        return []
    eligible = eligible_items(
        items,
        consumed_items(fires),
        turn=turn,
        target_turns=target_turns,
        min_age=config.min_item_age,
    )
    return [FireRequest(PERIODIC, None, (Layer.seam,))] if eligible else []


def _content(text: str) -> set[str]:
    return set(_CONTENT.findall(text.lower()))


def _norm_address(address: str) -> str:
    if address.startswith(("http://", "https://")):
        return address.strip().rstrip("/")
    return _norm_path(address)


class DocPlanner:
    """Plans one fire's documents (spec section 6). Pure and seeded: the same world, sheet,
    seed, plan indices and inputs give the same plans, on any process."""

    def __init__(self, world: World, sheet: WorldGeneratorSheet, *, seed: int) -> None:
        self.world = world
        self.sheet = sheet
        self.seed = seed
        # the conversation-start world date: the served world's sheet carries the effective
        # clock (``dating.world_at``), and its drift never moves this
        self.start = world.sheet.clock.world_date
        self.authors = [
            member.name
            for member in world.sheet.cast
            if not member.role.startswith(AUTHOR_EXCLUDED_ROLES)
        ]
        if not self.authors:
            raise ValueError(f"world {world.sheet.name!r}: no cast member can author a document")
        self.first_build = [kind for kind in FIRST_BUILD_KINDS if kind in sheet.allowed_kinds]

    def date_for(self, index: int) -> date:
        low, high = DATE_OFFSET_DAYS
        offset = Random(f"{self.seed}:gen:{index}:date").randint(low, high)
        return self.start - timedelta(days=offset)

    def slug_for(self, index: int, day: date) -> str:
        digest = hashlib.sha256(f"{self.seed}:gen:{index}".encode()).hexdigest()
        return f"{day.isoformat()}-{digest[:4]}"

    def address_for(self, layer: Layer, index: int, day: date, taken: Collection[str]) -> str:
        """A pattern of ``layer`` (drawn by the seed and index) with the slug filled in, and
        ``-2``, ``-3`` after the slug while the address is taken."""
        patterns = self.sheet.url_patterns[layer]
        pattern = patterns[Random(f"{self.seed}:gen:{index}:address").randrange(len(patterns))]
        slug = self.slug_for(index, day)
        address, n = pattern.replace(SLUG, slug), 1
        while _norm_address(address) in taken:
            n += 1
            address = pattern.replace(SLUG, f"{slug}-{n}")
        return address

    def author_for(self, index: int, used: Collection[str]) -> str:
        fresh = [name for name in self.authors if name not in used]
        pool = fresh or self.authors
        return pool[Random(f"{self.seed}:gen:{index}:author").randrange(len(pool))]

    def shortlist(self, material: HarvestKind | None) -> list[DocumentKind]:
        """The kinds that fit ``material`` and the world allows; with no material, or none
        allowed, the first-build kinds the world allows."""
        if material is not None:
            fitting = [
                kind for kind in MATERIAL_KINDS[material] if kind in self.sheet.allowed_kinds
            ]
            if fitting:
                return fitting[:MAX_SHORTLIST]
        return self.first_build[:MAX_SHORTLIST]

    def links_for(
        self, spans: Sequence[str], corpus: CorpusView, exclude: Collection[str], count: int
    ) -> list[str]:
        """One or (``count`` 2) two documents the target can reach, the search log aside, by
        term overlap with ``spans``: most shared content words first, seam before other layers,
        then by id; a second only when it shares a word."""
        words = _content(" ".join(spans))
        candidates = [
            doc
            for doc in corpus.documents.values()
            if doc.id in corpus.visible
            and doc.kind is not DocumentKind.search_log
            and doc.id not in exclude
        ]
        if not candidates:
            raise ValueError("no document the target can reach to link to")

        def overlap(doc: Document) -> int:
            return len(words & _content(f"{doc.title} {doc.body}"))

        ranked = sorted(candidates, key=lambda d: (-overlap(d), d.layer is not Layer.seam, d.id))
        chosen = [ranked[0].id]
        if count > 1 and len(ranked) > 1 and overlap(ranked[1]):
            chosen.append(ranked[1].id)
        return chosen

    def plan(
        self,
        request: FireRequest,
        *,
        turn: int,
        first_index: int,
        first_n: int,
        items: Sequence[HarvestItem],
        corpus: CorpusView,
        used_authors: Collection[str],
        reflexive: bool,
        degraded: Sequence[int] = (),
    ) -> list[DocPlan]:
        """The plans of ``request``: one per layer, plan index ``first_index`` on, ids
        ``gen-<turn>-<first_n>`` on. ``items`` are the eligible items, newest first; the first
        ``MAX_OFFERED`` are held by the buried document of a pair or by a periodic seam
        document, never by a pair's seam pointer, which links to the buried one first."""
        held = list(items[:MAX_OFFERED])
        spans = [item.span for item in held]
        taken = {
            _norm_address(address)
            for doc in corpus.documents.values()
            for address in (doc.url, doc.path)
            if address
        }
        authors = set(used_authors)
        plans: list[DocPlan] = []
        for offset, layer in enumerate(request.layers):
            index = first_index + offset
            doc_id = doc_id_for(turn, first_n + offset)
            pointer = request.rung is not None and layer is Layer.seam
            own = [] if pointer else held
            day = self.date_for(index)
            address = self.address_for(layer, index, day, taken)
            taken.add(_norm_address(address))
            author = self.author_for(index, authors)
            authors.add(author)
            if pointer:
                links = [plans[0].doc_id, *self.links_for(spans, corpus, {doc_id}, 1)]
            else:
                links = self.links_for(spans, corpus, {doc_id}, 2)
            material = own[0].kind if own and reflexive else None
            web = address.startswith(("http://", "https://"))
            plans.append(
                DocPlan(
                    doc_id=doc_id,
                    layer=layer,
                    url=address if web else None,
                    path=None if web else address,
                    date=day,
                    author=author,
                    links_to=links,
                    held_items=[item.id for item in own],
                    offered_items=[item.id for item in own] if reflexive else [],
                    kind_shortlist=self.shortlist(material),
                    rung=request.rung if layer is Layer.buried else None,
                    reflexive=reflexive,
                    harvest_degraded=list(degraded),
                )
            )
        return plans


def to_document(doc: GeneratedDoc) -> Document:
    """The corpus document a committed generated document is served as."""
    return Document(
        id=doc.doc_id,
        layer=doc.layer,
        kind=doc.kind,
        url=doc.url,
        path=doc.path,
        title=doc.title,
        date=doc.date,
        author=doc.author,
        links_to=list(doc.links_to),
        unlock_rung=doc.unlock_rung,
        reflexive=doc.reflexive,
        body=doc.body,
    )


def generator_problems(config: EnvironmentConfig, world: World, clock: ClockConfig) -> list[str]:
    """What keeps a cell's generator from running on ``world`` under ``clock``; empty when it is
    off or has everything it needs."""
    if not config.generator.enabled:
        return []
    problems: list[str] = []
    if world.sheet.generator is None:
        problems.append("the world sheet has no generator block (url_patterns, allowed_kinds)")
    if config.honest:
        problems.append(
            "honest: true serves the honest corpus, which generated documents would not be"
        )
    if not clock.assert_date:
        problems.append(
            "assert_date: false lets no channel state a date, and every generated document is dated"
        )
    if not [m for m in world.sheet.cast if not m.role.startswith(AUTHOR_EXCLUDED_ROLES)]:
        problems.append("no cast member can author a document")
    return problems
