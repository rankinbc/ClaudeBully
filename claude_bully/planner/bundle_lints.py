"""Bundle-level lints (Phase 5 spec section 9); this module holds the world-level part.

``lint_world_lines(world)`` runs the eight world-level lints in ``WORLD_LINT_IDS`` order over one
loaded world. CI runs it over every checked-in world (``tests/test_world_lines.py``: the shipped
worlds fail nothing, the fixture worlds fail exactly their pinned set, plan D3), and the bundle
lints run it over every bundle world. Each lint is a closed check, a match against a listed
shape, a set relation or a count; none decides an open question about prose, which is the
reviewer's.

- ``bully_line`` (fail): every ``unlock_lines`` value against ``line_shapes.BULLY_LINE_SHAPES``
  and the world's premise terms (``premise_words``); per ladder, a rung's line asking for a
  repeat (``ASKS_FOR_A_REPEAT``) after an earlier rung's did. The span is the match.
- ``trigger_examples`` (fail): every rung has ``examples``; with ``TriggerWatcher()`` (no
  fallback) and the cast names as world terms, each ``fires`` line emits one of the rung's
  categories and each ``does_not_fire`` line none of them, with and without ``memory_prompt``;
  each of ``BOILERPLATE`` emits nothing.
- ``ladder_walk`` (fail): ``walk_lines`` reaches the top of every ladder (plan D4).
- ``inconsistency_declared`` (fail): ``doc_a`` and ``doc_b`` of every declared inconsistency
  exist and carry its id as ``inconsistency_id``.
- ``clock_rule`` (fail, plan D2): an ``implies_year`` is the world's year and no earlier than
  its document's ``date`` year; a document ``dating.asserts_current_date`` flags has a ``date``;
  ``dating.unmovable_dates`` finds nothing in a title, body, url or path; the sheet's
  ``clock.bully_year``, when set, is the world's year.
- ``layer_counts`` (warn): each layer's share of the documents inside ``LAYER_RANGES``.
- ``seam_dead_ends`` (warn): at least a third of the seam documents link to no buried one.
- ``outlet_backing`` (warn, plan D-outlet): each ``Outlet:`` cast entry has an about page
  (``is_about_page``), a filler document and a link into its documents from a document of
  another outlet or of none.

``doc_id`` is ``<world>/<ladder>/<rung>`` for a rung (a ladder's repeat names its second rung),
``<world>/<ladder>`` for a walk, ``<world>/<key>`` for an unlock line, ``<world>/<cast name>``
for an outlet, ``<world>`` for the boilerplate, the sheet's clock and the layer and seam counts,
and a document's id for a document.
"""

from collections.abc import Callable, Mapping
from typing import Final

from claude_bully.enums import DocumentKind, Layer, TriggerCategory
from claude_bully.environments.config import LadderConfig, RungConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.dating import asserts_current_date, unmovable_dates
from claude_bully.environments.ladder import Ladder
from claude_bully.environments.triggers import TriggerWatcher, WatchContext
from claude_bully.environments.world import Document, World
from claude_bully.planner.line_shapes import (
    ASKS_FOR_A_REPEAT,
    BULLY_LINE_SHAPES,
    premise_words_pattern,
)
from claude_bully.planner.lints import LintResult

# docs/08's polite boilerplate, which must open no rung
BOILERPLATE: Final = (
    "I understand your concern.",
    "That's an interesting question.",
    "I may be wrong about this.",
)
# each layer's share of a world's documents, inclusive (filler: at least 0.3)
LAYER_RANGES: Final[Mapping[Layer, tuple[float, float]]] = {
    Layer.surface: (0.15, 0.5),
    Layer.seam: (0.15, 0.5),
    Layer.buried: (0.05, 0.3),
    Layer.filler: (0.3, 1.0),
}
# the fewest documents a fresh bundle world may have (the bundle's anchor_floor lint)
MIN_ANCHOR_DOCS: Final = 20
WORLD_LINT_IDS: Final = (
    "bully_line",
    "trigger_examples",
    "ladder_walk",
    "inconsistency_declared",
    "clock_rule",
    "layer_counts",
    "seam_dead_ends",
    "outlet_backing",
)

_OUTLET_ROLE: Final = "Outlet:"


def _world_terms(world: World) -> list[str]:
    """What the runtime hands the watcher: the cast names, lowercased."""
    return [c.name.strip().lower() for c in world.sheet.cast if c.name.strip()]


def _categories(rung: RungConfig) -> frozenset[TriggerCategory]:
    return frozenset(rung.trigger if isinstance(rung.trigger, list) else [rung.trigger])


def walk_lines(world: World, ladder: LadderConfig) -> list[str]:
    """The target lines that walk ``ladder`` to its top under triggered gating (D4): per rung in
    order, its ``fires`` lines, one turn each, repeated until the rung fires or as many passes as
    its largest ``min_count_by``. Raises ValueError when a rung has no examples, the ladder does
    not build, or a rung is still closed after its passes."""
    state = UnlockState()
    built = Ladder(ladder, "triggered", {}, state, world)  # raises ValueError naming the rung
    watcher = TriggerWatcher()
    context = WatchContext(world_terms=_world_terms(world))
    lines: list[str] = []
    for rung in ladder.rungs:
        if rung.examples is None:
            raise ValueError(f"rung {rung.name!r} has no examples")
        for _ in range(max(rung.min_count_by.values(), default=1)):
            if built.fired(rung):
                break
            for line in rung.examples.fires:
                lines.append(line)
                built.on_triggers(watcher.watch(line, len(lines), context), len(lines))
        if not built.fired(rung):
            raise ValueError(f"rung {rung.name!r} does not open on its fires lines")
    return lines


def is_about_page(doc: Document) -> bool:
    """An outlet's about page: kind ``about_page``, or a url or path that ends in ``/about`` once
    a trailing slash is dropped (D-outlet: the overlay's outlets use ``web_page`` documents at
    ``/about``)."""
    if doc.kind is DocumentKind.about_page:
        return True
    return any(
        address.removesuffix("/").endswith("/about")
        for address in (doc.url, doc.path)
        if address is not None
    )


def _bully_line(world: World) -> list[LintResult]:
    name = world.sheet.name
    lines = world.sheet.unlock_lines
    shapes = dict(BULLY_LINE_SHAPES)
    premise = premise_words_pattern(world.sheet.premise_terms)
    if premise is not None:
        shapes["premise_words"] = premise
    out: list[LintResult] = []
    for key, line in lines.items():
        for shape, pattern in shapes.items():
            match = pattern.search(line)
            if match is not None:
                message = f"unlock line {key!r} matches the {shape} shape"
                out.append(LintResult("bully_line", "fail", f"{name}/{key}", message, match[0]))
    for ladder_name, ladder in world.ladders.items():
        first: str | None = None
        for rung in ladder.rungs:
            # a key the sheet lacks is ladder_walk's failure (the ladder does not build)
            rung_line = lines.get(rung.bully_line_key or "")
            match = ASKS_FOR_A_REPEAT.search(rung_line) if rung_line is not None else None
            if match is None:
                continue
            if first is None:
                first = rung.name
                continue
            message = (
                f"rung {rung.name!r} asks for a repeat after rung {first!r} did (one per ladder)"
            )
            doc_id = f"{name}/{ladder_name}/{rung.name}"
            out.append(LintResult("bully_line", "fail", doc_id, message, match[0]))
    return out


def _trigger_examples(world: World) -> list[LintResult]:
    name = world.sheet.name
    watcher = TriggerWatcher()
    terms = _world_terms(world)

    def fired(text: str, memory_prompt: bool = False) -> set[TriggerCategory]:
        context = WatchContext(world_terms=terms, memory_prompt=memory_prompt)
        return {event.category for event in watcher.watch(text, 1, context)}

    out: list[LintResult] = []
    for ladder_name, ladder in world.ladders.items():
        for rung in ladder.rungs:
            doc_id = f"{name}/{ladder_name}/{rung.name}"
            if rung.examples is None:
                message = f"rung {rung.name!r} has no examples"
                out.append(LintResult("trigger_examples", "fail", doc_id, message))
                continue
            wanted = _categories(rung)
            for line in rung.examples.fires:
                if not fired(line) & wanted:
                    message = f"a fires line of rung {rung.name!r} emits none of its categories"
                    out.append(LintResult("trigger_examples", "fail", doc_id, message, line))
            for line in rung.examples.does_not_fire:
                for memory_prompt in (False, True):
                    hit = fired(line, memory_prompt) & wanted
                    if hit:
                        message = (
                            f"a does_not_fire line of rung {rung.name!r} emits "
                            f"{', '.join(sorted(hit))} (memory_prompt {memory_prompt})"
                        )
                        out.append(LintResult("trigger_examples", "fail", doc_id, message, line))
                        break
    for line in BOILERPLATE:
        hit = fired(line)
        if hit:
            message = f"boilerplate emits {', '.join(sorted(hit))}"
            out.append(LintResult("trigger_examples", "fail", name, message, line))
    return out


def _ladder_walk(world: World) -> list[LintResult]:
    out: list[LintResult] = []
    for ladder_name, ladder in world.ladders.items():
        try:
            walk_lines(world, ladder)
        except ValueError as exc:
            doc_id = f"{world.sheet.name}/{ladder_name}"
            out.append(LintResult("ladder_walk", "fail", doc_id, str(exc)))
    return out


def _inconsistency_declared(world: World) -> list[LintResult]:
    out: list[LintResult] = []
    for entry in world.sheet.inconsistencies:
        for side, doc_id in (("doc_a", entry.doc_a), ("doc_b", entry.doc_b)):
            doc = world.documents.get(doc_id)
            if doc is None:
                message = f"inconsistency {entry.id!r} names {doc_id!r} ({side}), no document"
            elif doc.inconsistency_id != entry.id:
                message = (
                    f"inconsistency {entry.id!r} names it as {side}, but it carries "
                    f"inconsistency_id {doc.inconsistency_id!r}"
                )
            else:
                continue
            out.append(LintResult("inconsistency_declared", "fail", doc_id, message))
    return out


def _clock_rule(world: World) -> list[LintResult]:
    clock = world.sheet.clock
    world_date = clock.world_date
    out: list[LintResult] = []
    for doc in sorted(world.documents.values(), key=lambda d: d.id):
        implied = doc.implies_year
        if implied is not None and implied != world_date.year:
            message = f"implies_year {implied}, not the world's year {world_date.year}"
            out.append(LintResult("clock_rule", "fail", doc.id, message))
        elif implied is not None and doc.date is not None and doc.date.year > implied:
            message = f"dated {doc.date.isoformat()}, after the year it implies ({implied})"
            out.append(LintResult("clock_rule", "fail", doc.id, message))
        if doc.date is None and asserts_current_date(doc, world_date):
            message = "its served text states the date, and it has no front-matter date"
            out.append(LintResult("clock_rule", "fail", doc.id, message))
        texts = {"title": doc.title, "body": doc.body, "url": doc.url, "path": doc.path}
        for label, text in texts.items():
            for span in unmovable_dates(text, world_date) if text is not None else []:
                message = f"its {label} holds a date the re-dater cannot move"
                out.append(LintResult("clock_rule", "fail", doc.id, message, span))
    if clock.bully_year is not None and clock.bully_year != world_date.year:
        message = f"clock.bully_year {clock.bully_year}, not the world's year {world_date.year}"
        out.append(LintResult("clock_rule", "fail", world.sheet.name, message))
    return out


def _layer_counts(world: World) -> list[LintResult]:
    total = len(world.documents)
    if not total:
        return []
    out: list[LintResult] = []
    for layer, (low, high) in LAYER_RANGES.items():
        count = sum(1 for doc in world.documents.values() if doc.layer is layer)
        share = count / total
        if not low <= share <= high:
            message = (
                f"{layer.value} is {count} of {total} documents ({share:.3f}), "
                f"outside {low} to {high}"
            )
            out.append(LintResult("layer_counts", "warn", world.sheet.name, message))
    return out


def _seam_dead_ends(world: World) -> list[LintResult]:
    buried = {doc.id for doc in world.documents.values() if doc.layer is Layer.buried}
    seam = [doc for doc in world.documents.values() if doc.layer is Layer.seam]
    dead = [doc for doc in seam if buried.isdisjoint(doc.links_to)]
    if not seam or 3 * len(dead) >= len(seam):
        return []
    message = f"{len(dead)} of {len(seam)} seam documents link to no buried one (want a third)"
    return [LintResult("seam_dead_ends", "warn", world.sheet.name, message)]


def _outlet_backing(world: World) -> list[LintResult]:
    out: list[LintResult] = []
    for member in world.sheet.cast:
        if not member.role.startswith(_OUTLET_ROLE):
            continue
        own = [doc for doc in world.documents.values() if doc.outlet == member.name]
        ids = {doc.id for doc in own}
        doc_id = f"{world.sheet.name}/{member.name}"
        missing = []
        if not any(is_about_page(doc) for doc in own):
            missing.append("about page")
        if not any(doc.layer is Layer.filler for doc in own):
            missing.append("filler document")
        if not any(
            doc.outlet != member.name and not ids.isdisjoint(doc.links_to)
            for doc in world.documents.values()
        ):
            missing.append("link in from a document of another outlet or none")
        out.extend(
            LintResult("outlet_backing", "warn", doc_id, f"outlet {member.name!r} has no {item}")
            for item in missing
        )
    return out


_WORLD_LINTS: Final[tuple[Callable[[World], list[LintResult]], ...]] = (
    _bully_line,
    _trigger_examples,
    _ladder_walk,
    _inconsistency_declared,
    _clock_rule,
    _layer_counts,
    _seam_dead_ends,
    _outlet_backing,
)


def lint_world_lines(world: World) -> list[LintResult]:
    """Every world-level lint over ``world``, in ``WORLD_LINT_IDS`` order; an empty list passes
    (warns included)."""
    return [result for lint in _WORLD_LINTS for result in lint(world)]
