"""Bundle-level lints (Phase 5 spec section 9): the world-level part and ``lint_bundle``.

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

``lint_bundle(bundle)`` runs, over one plan bundle (``planner/bundle.py``), the lints of
``BUNDLE_LINT_IDS`` built so far, every result kept, warns included (R-good-warn):

- ``schema`` (fail): every grammar file loads into its model with no unknown field (the world
  sheet, ``parse_document``, ``LadderConfig``, a premise's ``world_sheet``, ``PersonaSheet``,
  ``Experiment``, ``ExpectedEvents``), each world through ``load_world``; ``config.yaml`` and
  ``expected.yaml`` exist; every bundle world's ``premise_terms`` holds a term that is not blank
  and keeps every term ``PlanRecord.base_premise_terms`` recorded at the copy, without case
  (R-premise-terms); no two persona files share a name and no persona is named as a registered
  strategy (a class a ``plan_personas`` block registered is a plan's, not a strategy); every
  ``environments[*].world`` is a directory under ``worlds/`` and, under triggered or scheduled
  gating, its ``ladder`` a ladder of that world; and, inside ``plan_personas``,
  ``run_experiment(dry_run=True)`` against the bundle's worlds accepts the config
  (``check_condition``, ``RunEnvironments.validate``, ``world_premise_sheet``), each condition's
  refusal reported. Each step runs on what loaded, so every independent fault is reported; a
  step that depends on a failed one is skipped with a ``skipped:`` warn naming why. A bundle
  persona's ``params`` are not validated: a ``PersonaSheet`` premise declares no
  ``params_model`` (the residual, pinned by a fixture). When ``schema`` fails, every lint that
  needs a loaded model reports nothing; the schema failure is the finding.
- ``manifest_complete`` (fail): every manifest path exists unless its last ``file:`` call is an
  ``error``; no grammar file but ``plan.md`` and ``review.md`` is outside the manifest and the
  base copy (``PlanRecord.base_files``).
- Phase 3's ``lint_world`` and the world-level lints above per bundle world, a document's id
  rewritten to its bundle path; then ``bully_line`` over every persona's ``fallback_lines``
  (``<persona>/fallback_lines/<i>``) with the shapes and the premise terms of every world the
  config's environments name.
"""

import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml
from pydantic import BaseModel, ValidationError

from claude_bully.config import ConditionConfig, Experiment
from claude_bully.enums import DocumentKind, Layer, TriggerCategory
from claude_bully.environments.config import LadderConfig, RungConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.dating import asserts_current_date, unmovable_dates
from claude_bully.environments.ladder import Ladder
from claude_bully.environments.triggers import TriggerWatcher, WatchContext
from claude_bully.environments.world import (
    Document,
    World,
    WorldSheet,
    load_world,
    parse_document,
)
from claude_bully.planner.bundle import (
    Bundle,
    is_plan_persona,
    kind_of,
    plan_personas,
    world_of,
)
from claude_bully.planner.line_shapes import (
    ASKS_FOR_A_REPEAT,
    BULLY_LINE_SHAPES,
    premise_words_pattern,
)
from claude_bully.planner.lints import LintResult, lint_world
from claude_bully.planner.records import DryRunCell, ExpectedEvents, PlanRecord
from claude_bully.runner.runner import run_experiment
from claude_bully.strategies.base import all_strategies
from claude_bully.strategies.bootstrap import ensure_registered
from claude_bully.strategies.sheets import PersonaSheet

# docs/08's polite boilerplate, which must open no rung
BOILERPLATE: Final = (
    "I understand your concern.",
    "That's an interesting question.",
    "I may be wrong about this.",
)
# each layer's share of a world's documents, inclusive (filler: at least 0.3)
LAYER_RANGES: Final[Mapping[Layer, tuple[float, float]]] = MappingProxyType(
    {
        Layer.surface: (0.15, 0.5),
        Layer.seam: (0.15, 0.5),
        Layer.buried: (0.05, 0.3),
        Layer.filler: (0.3, 1.0),
    }
)
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


# ------------------------------------------------------------------ the bundle (lint_bundle)

# spec section 9's table, in its order
BUNDLE_LINT_IDS: Final[tuple[str, ...]] = (
    "schema",
    "manifest_complete",
    "real_name_bundle",
    "reserved_hosts",
    "boundary_bundle",
    "jailbreak_bundle",
    "no_values_expectation",
    "bully_line",
    "trigger_examples",
    "ladder_walk",
    "inconsistency_declared",
    "clock_rule",
    "layer_counts",
    "anchor_floor",
    "seam_dead_ends",
    "outlet_backing",
    "expected_schema",
    "control_presence",
    "budget",
    "dry_run",
)

_WORLDS: Final = "worlds"
_CONFIG: Final = "config.yaml"
_FIXED_MODELS: Final = (_CONFIG, "expected.yaml")
# the gatings that read an environment's ladder
_LADDERED: Final = frozenset({"triggered", "scheduled"})


@dataclass(frozen=True)
class _Loaded:
    """What a bundle whose ``schema`` passed holds: its worlds, each document's bundle path by
    world and id, its personas and its experiment."""

    worlds: Mapping[str, World]
    doc_paths: Mapping[str, Mapping[str, str]]
    personas: Mapping[str, PersonaSheet]
    experiment: Experiment


def _schema_fail(rel: str, message: str) -> LintResult:
    return LintResult("schema", "fail", rel, message)


def _skipped(rel: str, what: str, why: str) -> LintResult:
    """A ``schema`` step not run because a step it depends on failed: a warn beside that
    step's failure, so the report says what was not checked."""
    return LintResult("schema", "warn", rel, f"skipped: {what} ({why})")


def _field_errors(exc: ValidationError) -> str:
    """Each error of ``exc`` as ``field: message``, the root named ``<root>``."""
    return "; ".join(
        f"{'.'.join(map(str, error['loc'])) or '<root>'}: {error['msg']}" for error in exc.errors()
    )


def _model[T: BaseModel](model: type[T], bundle: Bundle, rel: str) -> T:
    """A bundle YAML file validated as ``model``; the ``ValueError`` lists every field error."""
    try:
        raw = yaml.safe_load(bundle.read_file(rel))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"does not load as {model.__name__}: {_field_errors(exc)}") from exc


def _premise_model(rel: str) -> type[BaseModel]:
    """The model of ``worlds/<w>/premises/<strategy>.yaml``: that strategy's ``world_sheet``."""
    stem = rel.rsplit("/", 1)[1].removesuffix(".yaml")
    cls = all_strategies().get(stem)
    if cls is None:
        raise ValueError(f"premise sheet {stem!r} names no strategy")
    if cls.world_sheet is None:
        raise ValueError(f"strategy {stem!r} declares no world_sheet")
    return cls.world_sheet


@dataclass
class _Files:
    """``schema``'s first step: what loaded, by kind, and what did not."""

    doc_paths: dict[str, dict[str, str]] = field(default_factory=dict)
    # persona name to its sheet (the first file's) and to every file holding that name
    personas: dict[str, PersonaSheet] = field(default_factory=dict)
    persona_files: dict[str, list[str]] = field(default_factory=dict)
    failed_worlds: set[str] = field(default_factory=set)
    failed_persona: bool = False
    experiment: Experiment | None = None


def _load_files(bundle: Bundle, out: list[LintResult]) -> _Files:
    """Each grammar file into its model (``plan.md`` and ``review.md`` have none), naming the
    file; ``config.yaml`` and ``expected.yaml`` must exist."""
    files = _Files()
    present = bundle.index()
    for rel in present:
        kind = kind_of(rel)
        world = world_of(rel)
        try:
            if kind == "world_sheet":
                _model(WorldSheet, bundle, rel)
            elif kind == "document":
                doc = parse_document(bundle.read_file(rel), rel)
                files.doc_paths.setdefault(str(world), {})[doc.id] = rel
            elif kind == "ladder":
                _model(LadderConfig, bundle, rel)
            elif kind == "premise_sheet":
                _model(_premise_model(rel), bundle, rel)
            elif kind == "persona":
                sheet = _model(PersonaSheet, bundle, rel)
                files.personas.setdefault(sheet.name, sheet)
                files.persona_files.setdefault(sheet.name, []).append(rel)
            elif kind == "config":
                files.experiment = _model(Experiment, bundle, rel)
            elif kind == "expected":
                _model(ExpectedEvents, bundle, rel)
        except ValueError as exc:
            # parse_document's message opens with the path the doc_id already holds
            out.append(_schema_fail(rel, str(exc).removeprefix(f"{rel}: ")))
            if world is not None:
                files.failed_worlds.add(world)
            if kind == "persona":
                files.failed_persona = True
    out.extend(_schema_fail(rel, "missing") for rel in _FIXED_MODELS if rel not in present)
    return files


def _load_worlds(
    bundle: Bundle, record: PlanRecord, names: Sequence[str], files: _Files, out: list[LintResult]
) -> dict[str, World]:
    """Each bundle world whose files loaded, through ``load_world``; its ``premise_terms`` hold a
    term that is not blank and keep every term ``base_premise_terms`` recorded, compared without
    case as the premise pattern matches (R-premise-terms)."""
    root = bundle.root / _WORLDS
    worlds: dict[str, World] = {}
    for name in names:
        sheet_rel = f"{_WORLDS}/{name}/world.yaml"
        if name in files.failed_worlds:
            why = f"a file of world {name!r} does not load"
            out.append(_skipped(sheet_rel, f"load_world of world {name!r}", why))
            continue
        try:
            world = load_world(name, root)
        except (ValueError, OSError) as exc:
            out.append(_schema_fail(sheet_rel, f"world {name!r} does not load: {exc}"))
            continue
        worlds[name] = world
        terms = {term.strip().casefold() for term in world.sheet.premise_terms if term.strip()}
        if not terms:
            out.append(_schema_fail(sheet_rel, "premise_terms has no term"))
            continue
        base = record.base_premise_terms.get(name, [])
        lost = sorted(term for term in base if term.strip().casefold() not in terms)
        if lost:
            message = f"premise_terms drops {', '.join(lost)}, recorded at the copy"
            out.append(_schema_fail(sheet_rel, message))
    return worlds


def _persona_names(files: _Files, out: list[LintResult]) -> set[str]:
    """The persona names that fail: one held by two files, or a registered strategy's. A
    strategy a ``plan_personas`` block registered is a plan's persona, not a strategy (review
    M5), so linting inside an open block for the same persona finds no clash."""
    strategies = {name for name, cls in all_strategies().items() if not is_plan_persona(cls)}
    bad: set[str] = set()
    for name, rels in sorted(files.persona_files.items()):
        first, *others = rels
        for rel in others:
            out.append(_schema_fail(rel, f"persona {name!r} is also {first}"))
            bad.add(name)
        if name in strategies:
            out.append(_schema_fail(first, f"persona {name!r} is a registered strategy's name"))
            bad.add(name)
    return bad


def _environments(
    experiment: Experiment, names: Sequence[str], worlds: Mapping[str, World], out: list[LintResult]
) -> dict[str, str]:
    """Every environment's world a directory under ``worlds/`` and, under a gating that reads one,
    its ladder a ladder of that world (review M2: ``run --dry-run`` builds no triggered ladder).
    The environments that failed, or whose world did not load, with why."""
    bad: dict[str, str] = {}
    for key, env in sorted(experiment.environments.items()):
        if env.world not in names:
            message = f"environment {key!r}: world {env.world!r} is no world under {_WORLDS}/"
            out.append(_schema_fail(_CONFIG, message))
            bad[key] = f"environment {key!r} failed a check"
            continue
        world = worlds.get(env.world)
        if world is None:
            bad[key] = f"world {env.world!r} does not load"
            out.append(_skipped(_CONFIG, f"the ladder of environment {key!r}", bad[key]))
        elif env.gating in _LADDERED and env.ladder not in world.ladders:
            message = f"environment {key!r}: world {env.world!r} has no ladder {env.ladder!r}"
            out.append(_schema_fail(_CONFIG, message))
            bad[key] = f"environment {key!r} failed a check"
    return bad


def _refusals(experiment: Experiment, worlds_dir: Path) -> list[str]:
    """What ``run_experiment(dry_run=True)`` refuses: nothing, or, since it stops at its first
    refusal, each condition's own refusal run alone (the whole run's when none refuses alone)."""

    def refusal(exp: Experiment) -> str | None:
        with tempfile.TemporaryDirectory() as runs_root:
            try:
                run_experiment(exp, runs_root=Path(runs_root), dry_run=True, worlds_dir=worlds_dir)
            except (ValueError, KeyError, OSError) as exc:
                return f"run --dry-run refuses it: {exc}"
        return None

    whole = refusal(experiment)
    if whole is None:
        return []
    if len(experiment.conditions) == 1:
        return [whole]
    alone = [
        refusal(experiment.model_copy(update={"conditions": [c]})) for c in experiment.conditions
    ]
    return [message for message in alone if message is not None] or [whole]


def _runnable(
    experiment: Experiment,
    files: _Files,
    bad_personas: set[str],
    bad_envs: Mapping[str, str],
    out: list[LintResult],
) -> list[ConditionConfig]:
    """The conditions the dry run can check; each other one gets a ``skipped:`` warn naming why
    (its environment failed or its world did not load, it names a persona that failed, or it
    names an unknown part while a persona file did not load)."""
    strategies = set(all_strategies())
    runnable: list[ConditionConfig] = []
    for cond in experiment.conditions:
        parts = {n for n in (cond.strategy, cond.premise, cond.pressure) if n is not None}
        clash = sorted(parts & bad_personas)
        why: str | None = None
        if cond.environment is not None and cond.environment in bad_envs:
            why = bad_envs[cond.environment]
        elif clash:
            why = f"persona {clash[0]!r} failed a check"
        elif files.failed_persona and parts - strategies - set(files.personas):
            why = "a persona file does not load"
        if why is None:
            runnable.append(cond)
        else:
            out.append(_skipped(_CONFIG, f"run --dry-run of condition {cond.name!r}", why))
    return runnable


def _schema(bundle: Bundle, record: PlanRecord) -> tuple[list[LintResult], _Loaded | None]:
    """``schema``: every file into its model; every world through ``load_world`` and its premise
    terms; the persona names; every environment's world and ladder; then
    ``run_experiment(dry_run=True)`` against the bundle's worlds inside ``plan_personas``. Every
    step runs on what loaded, so each independent fault is reported (review M1); a step that
    depends on a failed one is skipped with a ``skipped:`` warn naming why, and a condition the
    dry run cannot check (its world, environment or persona failed) is left out of it with one.
    The loaded bundle when nothing failed, else None."""
    ensure_registered()
    out: list[LintResult] = []
    files = _load_files(bundle, out)
    root = bundle.root / _WORLDS
    names = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    worlds = _load_worlds(bundle, record, names, files, out)
    bad_personas = _persona_names(files, out)
    experiment = files.experiment
    if experiment is None:
        what = "the environment checks and run --dry-run"
        out.append(_skipped(_CONFIG, what, f"{_CONFIG} does not load"))
        return out, None
    bad_envs = _environments(experiment, names, worlds, out)
    runnable = _runnable(experiment, files, bad_personas, bad_envs, out)
    if runnable:
        personas = {n: s for n, s in files.personas.items() if n not in bad_personas}
        checked = experiment.model_copy(update={"conditions": runnable})
        with plan_personas(personas):
            out.extend(_schema_fail(_CONFIG, m) for m in _refusals(checked, root))
    if out:
        return out, None
    return [], _Loaded(worlds, files.doc_paths, files.personas, experiment)


def _manifest_complete(bundle: Bundle, record: PlanRecord) -> list[LintResult]:
    """``manifest_complete``: every manifest path exists unless its last ``file:`` call is an
    ``error``; no grammar file but ``plan.md`` and ``review.md`` is outside the manifest and the
    base copy."""
    present = bundle.index()
    last: dict[str, str] = {}
    for stage in record.stages:
        for call in stage.calls:
            kind, _, path = call.purpose.partition(":")
            if kind == "file":
                last[path] = call.status
    out: list[LintResult] = []
    for entry in record.manifest:
        if entry.path not in present and last.get(entry.path) != "error":
            message = "in the manifest but not on disk, and its call is no error"
            out.append(LintResult("manifest_complete", "fail", entry.path, message))
    allowed = {entry.path for entry in record.manifest} | set(record.base_files)
    for rel in present:
        if kind_of(rel) is not None and rel not in allowed:
            message = "outside the manifest and the base copy"
            out.append(LintResult("manifest_complete", "fail", rel, message))
    return out


def _persona_lines(loaded: _Loaded) -> list[LintResult]:
    """``bully_line`` over each persona's ``fallback_lines``: the shapes, and the premise terms
    of every world the config's environments name."""
    shapes = dict(BULLY_LINE_SHAPES)
    named = sorted({env.world for env in loaded.experiment.environments.values()})
    premise = premise_words_pattern(
        [t for n in named for t in loaded.worlds[n].sheet.premise_terms]
    )
    if premise is not None:
        shapes["premise_words"] = premise
    out: list[LintResult] = []
    for name, sheet in sorted(loaded.personas.items()):
        for i, line in enumerate(sheet.fallback_lines):
            for shape, pattern in shapes.items():
                match = pattern.search(line)
                if match is not None:
                    message = f"fallback line {i} matches the {shape} shape"
                    doc_id = f"{name}/fallback_lines/{i}"
                    out.append(LintResult("bully_line", "fail", doc_id, message, match[0]))
    return out


def _world_lints(loaded: _Loaded) -> list[LintResult]:
    """Phase 3's ``lint_world`` and ``lint_world_lines`` per bundle world, every result kept
    (warns included, R-good-warn), each document id rewritten to the bundle path of the file
    that holds it; then the personas' lines."""
    out: list[LintResult] = []
    for name, world in sorted(loaded.worlds.items()):
        paths = loaded.doc_paths.get(name, {})
        for result in (*lint_world(world), *lint_world_lines(world)):
            path = paths.get(result.doc_id)
            out.append(result if path is None else replace(result, doc_id=path))
    return [*out, *_persona_lines(loaded)]


def lint_bundle(bundle: Bundle, *, dry_run: Sequence[DryRunCell] | None = None) -> list[LintResult]:
    """Every bundle lint built so far over ``bundle`` (spec section 9), every result kept, warns
    included (R-good-warn): ``schema``, ``manifest_complete``, then Phase 3's lints and the
    world-level lints per bundle world and ``bully_line`` over the personas' ``fallback_lines``.
    When ``schema`` fails, every lint that needs a loaded model reports nothing (the schema
    failure is the finding). ``dry_run`` is the dry run's cells, for the lints that read them
    (Tasks 4b and 5). The strategy registry is left as it was found (``plan_personas``)."""
    record = bundle.read_record()
    found, loaded = _schema(bundle, record)
    found += _manifest_complete(bundle, record)
    if loaded is not None:
        found += _world_lints(loaded)
    return found
