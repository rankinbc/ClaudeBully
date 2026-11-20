"""The bundle's dry run (Phase 5 spec section 10): the bundle's config run end to end on four
in-memory stub doubles, so every cell, fire, commit, serve and resume path runs before a model is
paid for.

- ``stubbed_experiment`` (Task 2): the experiment with every role one of ``DRYRUN_MODELS``.
- ``dry_run_script(ladder, world, tools)``: the target double's turns for one cell. Two of the
  first rung's ``does_not_fire`` lines; ``walk_lines`` (D4); with ``web_search``, one search for
  the title of ``searched_document`` (R-buried: a buried document the walk opens and leaves
  unsearchable, never one a rung names by id); with ``fetch`` (a url) or ``read_file`` (a path),
  one read of the first buried document the ladder's top-most opening rung opens; then
  ``DRYRUN_CLOSING``. A cell with no ladder to climb gets two of ``DRYRUN_SENTENCES`` and the
  close.
- The doubles (``dryrun_provider_factory``): the target answers the cell's script through the
  stub's ``turns`` mode (the twin, the target's own role, too, D-twin); the bully answers
  ``DRYRUN_BULLY_LINE`` and never echoes, since the trigger watcher drops a target line the bully
  said first and an echo would hold the Poisoned Well's repeated rungs shut (D-A9); the judge is
  the plain stub, so every judge-side run-time pass is off; the generator is ``DryRunGenerator``,
  whose body is drawn from the plan's address, never from a count it keeps (R-dryrun-pure).
- ``dry_run(bundle)``: the run under ``dryrun/<dry_run_id>/``, ``analyze_run`` with the judge off,
  then one ``DryRunCell`` per cell from the records, rewritten whole to ``dryrun.jsonl``.

A name to keep apart: the bundle's dry run is a full stub run; ``run --dry-run`` lists cells and
builds no strategy.
"""

import json
import re
import shutil
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import date
from pathlib import Path
from random import Random
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import ValidationError

from claude_bully.analysis.progression import unlocks_of
from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.atomic import write_atomic
from claude_bully.config import Experiment, RoleConfig, load_experiment
from claude_bully.enums import CellStatus, Layer, ProviderKind
from claude_bully.environments.config import EnvironmentConfig, LadderConfig
from claude_bully.environments.corpus import CorpusIndex, UnlockState
from claude_bully.environments.generator import plan_from_prompt
from claude_bully.environments.ladder import Ladder
from claude_bully.environments.mcp_server import STATE_FILE
from claude_bully.environments.runtime import AttemptMarker
from claude_bully.environments.tools import call_read, reads_document
from claude_bully.environments.world import World, load_world
from claude_bully.planner.bundle import (
    CACHE_DIR,
    DRYRUN_DIR,
    DRYRUN_FILE,
    Bundle,
    bundle_hash,
    bundle_personas,
    plan_personas,
)
from claude_bully.planner.bundle_lints import walk_lines
from claude_bully.planner.records import DryRunCell, LintRecord, damaged_field
from claude_bully.providers.base import ChatProvider, Completion, Message, ToolSpec
from claude_bully.providers.ledger import LEDGER_FILE, Ledger, LedgerLine, wrap
from claude_bully.providers.stub import ScriptedTurns, StubProvider, TurnEntry
from claude_bully.records import Turn, Usage
from claude_bully.records_env import GeneratorFire, ResumeRecord, RungUnlock, ToolCall
from claude_bully.runner.cells import CellSpec, expand_cells
from claude_bully.runner.runner import ProviderFactory, run_experiment
from claude_bully.runner.store import RunStore, parsed_lines

# the model of each double, by role; the dry run's factory serves these four and refuses any other
DRYRUN_MODELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "target": "stub-target",
        "bully": "stub-bully",
        "judge": "stub-judge",
        "generator": "stub-generator",
    }
)
# the responder_model values env_turn.responder_role resolves to a role the experiment holds
_ROLE_RESPONDERS: Final = frozenset({"target", "bully"})
# the bully double's one line (D-A9): no echo, no trigger, no world term
DRYRUN_BULLY_LINE: Final = "I hear you. Go on."
DRYRUN_CLOSING: Final = "Thanks. That is all I wanted to ask today."
# the target's line once a scripted tool result is back: the search's, then the read's
_AFTER_TOOL: Final = ("Thanks, that came back.", "Thanks, I have read it.")
# the generator double's bank and the quiet lines of a cell with no ladder: mundane sentences
# with no premise term of any checked-in world, no "you" and no name (spec section 14's
# reader-eye rule: a target is served them)
DRYRUN_SENTENCES: Final[tuple[str, ...]] = (
    "The kettle was descaled on Monday.",
    "The car park closes at nine.",
    "Spare keys hang by the back door.",
    "The second floor printer jams again.",
    "Recycling goes out every other week.",
    "The lift is booked for a service.",
    "Visitors sign the book at reception.",
    "The canteen serves soup until two.",
    "A new mop bucket was ordered.",
    "The noticeboard needs fresh drawing pins.",
    "Paper towels are stored under the sink.",
    "The heating comes on at seven.",
    "Window cleaners visit on the last Friday.",
    "The fire drill ran four minutes long.",
    "Lost umbrellas wait in the cupboard.",
    "The vending machine takes coins only.",
    "Two chairs in room six wobble.",
    "Milk deliveries now arrive before eight.",
    "The front step was gritted early.",
    "A bulb in the stairwell flickers.",
    "Desk plants are watered on Thursdays.",
    "The water cooler was refilled.",
    "Parcels wait at the porters' desk.",
    "The blinds in the hall stick.",
    "Staff lockers were repainted green.",
    "The lobby rug was cleaned.",
    "A tap in the kitchen drips.",
    "The bike rack has room again.",
    "Tea bags are kept in the tin.",
    "The photocopier needs more toner.",
    "Meeting room two has a new table.",
    "The gutters were cleared last week.",
    "Biscuits are no longer provided free.",
    "The post room shuts at four.",
    "A spare kettle is in storage.",
    "The doormat by the entrance is new.",
    "Hand soap was restocked in both rooms.",
    "The bins behind the shed are full.",
    "Notices go up on the left board.",
    "The radiator in the corner hums.",
    "A ladder is kept in the shed.",
    "The microwave timer was repaired.",
    "Coat hooks were added by the stairs.",
    "The hedge by the path was trimmed.",
    "Fresh towels arrive on Tuesdays.",
    "The office plant has new leaves.",
    "A stack of chairs blocks the corridor.",
    "The fridge is cleared every Friday.",
    "Envelopes are in the top drawer.",
    "The car park lines were repainted.",
    "Someone left a scarf on the bench.",
    "The stapler on reception is empty.",
    "A delivery van parked by the bins.",
    "The cleaning rota is pinned up.",
    "Spare batteries sit in the drawer.",
    "The side door now locks properly.",
    "The cafe sells scones on Saturdays.",
    "The fence panel was replaced.",
    "Chairs were stacked after the meeting.",
    "The lamp in reception was moved.",
)
DRYRUN_BODY_SENTENCES: Final = 5
# the tools a read of a buried document goes through, and a search
_SEARCH: Final = "web_search"
_LAYER_NAMES: Final = frozenset(layer.value for layer in Layer)
_WORLDS: Final = "worlds"
_CONFIG: Final = "config.yaml"
_RUN_PREFIX: Final = "dryrun-"
# the file in the dry run's generated cache that names the run id owning it (M-1)
CACHE_OWNER: Final = "OWNER"
# a generator call's conversation id: <conv>/generator/<doc_id>/<attempt> (environments/generator)
_GENERATOR_SEGMENT: Final = "/generator/"
# the rep's environment runtime state directory (runner/env_turn.py: RunEnvironments.open)
_RUNTIME_DIR: Final = "environment"
# pair-judge calls a condition rep adds in a real run (spec section 10, ``estimated_calls``)
PAIR_JUDGE_CALLS: Final = 2
TopRung = Literal["reached", "not_reached", "not_applicable"]


def _stub_role(role: str) -> RoleConfig:
    return RoleConfig(provider=ProviderKind.stub, model=DRYRUN_MODELS[role])


def _stubbed_environment(env: EnvironmentConfig) -> EnvironmentConfig:
    """``env`` naming no model outside the four doubles (preflight Q11): its ``generator.model``
    cleared, so the generator runs on the experiment's stub generator (``config.generator_role``),
    and a ``responder_model`` other than ``target`` or ``bully`` mapped to ``bully``, the role
    ``env_turn.responder_role`` would have run that model on."""
    update: dict[str, object] = {}
    if env.generator.model is not None:
        update["generator"] = env.generator.model_copy(update={"model": None})
    superior = env.authority.superior_self
    if superior.responder_model not in _ROLE_RESPONDERS:
        responder = superior.model_copy(update={"responder_model": "bully"})
        update["authority"] = env.authority.model_copy(update={"superior_self": responder})
    return env.model_copy(update=update) if update else env


def stubbed_experiment(exp: Experiment) -> Experiment:
    """``exp`` with every role one of the four doubles: each target ``stub-target`` (its
    ``display_name`` kept), the bully ``stub-bully``, the judge ``stub-judge``, and the generator
    ``stub-generator`` when any environment enables it (else None). No ``stub_script`` is set, and
    no environment names a model of its own (``_stubbed_environment``). ``turn_budget``,
    ``repetitions``, ``seed`` and everything else are kept, so the dry run's cells are the real
    cells."""
    generates = any(env.generator.enabled for env in exp.environments.values())
    return exp.model_copy(
        update={
            "targets": [
                RoleConfig(
                    provider=ProviderKind.stub,
                    model=DRYRUN_MODELS["target"],
                    display_name=t.display_name,
                )
                for t in exp.targets
            ],
            "bully": _stub_role("bully"),
            "judge": _stub_role("judge"),
            "generator": _stub_role("generator") if generates else None,
            "environments": {
                key: _stubbed_environment(env) for key, env in exp.environments.items()
            },
        }
    )


# ------------------------------------------------------------------ the walk and its documents


def walked_state(ladder: LadderConfig, world: World) -> UnlockState:
    """The state once every rung of ``ladder`` has fired, in order, through ``Ladder.apply``
    (the rung's own config decides what opens): what the target can reach at the top."""
    state = UnlockState()
    built = Ladder(ladder, "triggered", {}, state, world)
    for turn, rung in enumerate(ladder.rungs, start=1):
        built.apply(
            RungUnlock(
                turn=turn,
                rung=rung.name,
                triggered_by="dry_run",
                docs_unlocked=[],
                bully_line_used=None,
                role_shift=None,
            )
        )
    return state


def named_by_id(ladder: LadderConfig, world: World, fired: Collection[str]) -> set[str]:
    """The document ids the ``unlocks`` of the rungs in ``fired`` name (a layer is no id)."""
    wanted = set(fired)
    return {
        entry
        for rung in ladder.rungs
        if rung.name in wanted
        for entry in rung.unlocks
        if entry not in _LAYER_NAMES and entry in world.documents
    }


def searched_document(ladder: LadderConfig, world: World) -> str | None:
    """The buried document the script searches for (R-buried): the first by id that is visible
    and not searchable once every rung has fired (``walked_state``), so one a layer unlock or
    its ``unlock_rung`` opened and no rung names by id; None when the ladder opens none. It reads
    the buried rule (a buried document is searchable once its id is unlocked), not
    ``CorpusIndex.searchable``, so a search broken to serve layer-opened documents, the
    regression the check guards, still has a document to be caught serving."""
    state = walked_state(ladder, world)
    index = CorpusIndex(world)
    for doc_id in sorted(index.documents):
        doc = index.documents[doc_id]
        if (
            doc.layer is Layer.buried
            and index.visible(doc, state)
            and doc.id not in state.docs_unlocked
        ):
            return doc_id
    return None


def fetched_document(ladder: LadderConfig, world: World) -> str | None:
    """The buried document the script reads: the first by id that the ladder's top-most rung
    opening any buried document opens (by id, by its ``unlock_rung`` or by the buried layer for
    a document gated to no rung); None when no rung opens one."""
    index = CorpusIndex(world)
    for rung in reversed(ladder.rungs):
        layer = Layer.buried.value in rung.unlocks
        opened = sorted(
            doc.id
            for doc in index.documents.values()
            if doc.layer is Layer.buried
            and (
                doc.id in rung.unlocks
                or doc.unlock_rung == rung.name
                or (layer and doc.unlock_rung is None)
            )
        )
        if opened:
            return opened[0]
    return None


def _quiet_script() -> list[TurnEntry]:
    """A cell with no ladder to climb: two quiet lines and the close."""
    return [TurnEntry(reply=line) for line in (*DRYRUN_SENTENCES[:2], DRYRUN_CLOSING)]


def dry_run_script(
    ladder: LadderConfig | None, world: World, tools: Collection[str]
) -> list[TurnEntry]:
    """The target double's turns for one cell (spec section 10, refined by R-buried, and D4),
    one entry per target turn: two of the first rung's ``does_not_fire`` lines; each line of
    ``walk_lines``; with ``web_search`` in ``tools``, a search for ``searched_document``'s title
    (none when it is None); with ``fetch`` for a url or ``read_file`` for a path, a read of
    ``fetched_document``; each tool step answered with a fixed neutral line; then
    ``DRYRUN_CLOSING``. With no ``ladder``, two of ``DRYRUN_SENTENCES`` and the close. Raises
    ``ValueError`` for a ladder ``walk_lines`` cannot walk (the ``ladder_walk`` lint's failure)."""
    if ladder is None:
        return _quiet_script()
    first = ladder.rungs[0].examples
    quiet = list(first.does_not_fire[:2]) if first is not None else []
    script = [TurnEntry(reply=line) for line in (*quiet, *walk_lines(world, ladder))]
    searched = searched_document(ladder, world)
    if _SEARCH in tools and searched is not None:
        query = {"query": world.documents[searched].title}
        script.append(TurnEntry(tool=(_SEARCH, query), reply_after_tool=_AFTER_TOOL[0]))
    fetched = fetched_document(ladder, world)
    if fetched is not None:
        doc = world.documents[fetched]
        step: tuple[str, dict[str, Any]] | None = None
        if doc.url is not None and "fetch" in tools:
            step = ("fetch", {"url": doc.url})
        elif doc.path is not None and "read_file" in tools:
            step = ("read_file", {"path": doc.path})
        if step is not None:
            script.append(TurnEntry(tool=step, reply_after_tool=_AFTER_TOOL[1]))
    script.append(TurnEntry(reply=DRYRUN_CLOSING))
    return script


def top_rung_state(ladder: LadderConfig | None, fired: Collection[str]) -> TopRung:
    """``reached`` when ``fired`` holds the ladder's last rung, ``not_reached`` when it does not,
    ``not_applicable`` for a cell with no ladder to climb (D-A9)."""
    if ladder is None:
        return "not_applicable"
    return "reached" if ladder.rungs[-1].name in fired else "not_reached"


# ------------------------------------------------------------------------------- the doubles


def _kind_words(kind: str) -> str:
    return kind.replace("_", " ").capitalize()


def dryrun_document(plan: Mapping[str, Any], seed: int) -> dict[str, Any]:
    """The generator double's reply to one writer prompt's plan: the contract JSON for the
    plan's first shortlisted kind, its title the kind and the plan's date, its body
    ``DRYRUN_BODY_SENTENCES`` sentences of ``DRYRUN_SENTENCES`` drawn by
    ``Random(f"{seed}:{plan['address']}")`` and, when the plan links documents, one line naming
    each by title; nothing used (R-dryrun-pure: a function of the message alone)."""
    kind = str(plan["kind_shortlist"][0])
    day = date.fromisoformat(str(plan["date"]))
    drawn = Random(f"{seed}:{plan['address']}").sample(DRYRUN_SENTENCES, DRYRUN_BODY_SENTENCES)
    lines = list(drawn)
    titles = [str(link["title"]) for link in plan["links"]]
    if titles:
        # by title alone: a title and its address hold more than one word 8-gram, which two
        # documents linking the same page share, and no_duplicate_fact refuses the second
        lines.append(f"See also: {'; '.join(titles)}.")
    return {
        "kind": kind,
        "title": f"{_kind_words(kind)}, {day.day} {day:%B} {day.year}",
        "body": "\n".join(lines),
        "used_items": [],
    }


class DryRunGenerator:
    """The generator double (spec section 10): ``dryrun_document`` for the plan of the writer
    prompt, the last message. It keeps no count, so a provider rebuilt mid-run writes what the
    first would have (R-dryrun-pure). It proves the fire, commit, serve and resume paths and the
    lints on generated output; it does not pretend to write evidence."""

    name = "stub"

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.model = DRYRUN_MODELS["generator"]

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        reply = dryrun_document(plan_from_prompt(messages[-1].content), self.seed)
        return Completion(
            text=json.dumps(reply, ensure_ascii=False),
            usage=Usage(),
            cost_usd=0.0,
            backend=self.name,
            model=self.model,
        )


def _bully_line(conversation_id: str, messages: list[Message]) -> str:
    return DRYRUN_BULLY_LINE


def _literal(cell_id: str) -> str:
    """``cell_id`` as an fnmatch pattern that matches it alone."""
    return re.sub(r"([*?\[])", r"[\1]", cell_id)


def load_bundle_experiment(bundle: Bundle) -> Experiment:
    """The bundle's ``config.yaml`` as an ``Experiment``."""
    return load_experiment(bundle.root / _CONFIG)


def _laddered(
    cell: CellSpec, exp: Experiment, worlds: Mapping[str, World]
) -> tuple[EnvironmentConfig, World, LadderConfig] | None:
    """A cell's environment, world and ladder when it has a ladder to climb (an environment
    whose gating is not ``none``); None for a plain cell or a ``gating: none`` one."""
    if cell.condition.environment is None:
        return None
    env = exp.environments[cell.condition.environment]
    if env.gating == "none":
        return None
    world = worlds[env.world]
    return env, world, world.ladders[env.ladder]


def _worlds(exp: Experiment, worlds_dir: Path) -> dict[str, World]:
    names = sorted({env.world for env in exp.environments.values()})
    return {name: load_world(name, worlds_dir) for name in names}


def cell_script(cell: CellSpec, exp: Experiment, worlds: Mapping[str, World]) -> list[TurnEntry]:
    """The dry-run script of one cell: its environment's ladder, world and tools, or the quiet
    script for a cell with no ladder to climb."""
    found = _laddered(cell, exp, worlds)
    if found is None:
        return _quiet_script()
    env, world, ladder = found
    return dry_run_script(ladder, world, env.tools)


def dryrun_provider_factory(bundle: Bundle, exp: Experiment) -> ProviderFactory:
    """The dry run's provider factory over the stubbed ``exp`` (preflight Q26), serving by
    ``role.model`` (D-twin): ``stub-target`` the target double (a ``ScriptedTurns`` of every
    cell's ``cell_script``, a cell id matched as written, the quiet script the default), and the
    twin with it; ``stub-bully`` the fixed line (D-A9); ``stub-judge`` the plain stub;
    ``stub-generator`` ``DryRunGenerator(exp.seed)``. Each double is built at its call and
    wrapped with ``providers/ledger.wrap``, so the run's active ledger counts it. A non-stub
    provider, or a model that is not one of ``DRYRUN_MODELS``, raises ``ValueError`` naming it, so
    no real provider is reached by omission. The cells come from ``expand_cells`` inside
    ``plan_personas``, so a bundle persona resolves (R-registry)."""
    worlds = _worlds(exp, bundle.root / _WORLDS)
    with plan_personas(bundle_personas(bundle)):
        cells = expand_cells(exp)
    turns = ScriptedTurns(
        [(_literal(cell.cell_id), cell_script(cell, exp, worlds)) for cell in cells],
        _quiet_script(),
    )
    builders: dict[str, Callable[[], ChatProvider]] = {
        DRYRUN_MODELS["target"]: lambda: StubProvider(turns, model=DRYRUN_MODELS["target"]),
        DRYRUN_MODELS["bully"]: lambda: StubProvider(_bully_line, model=DRYRUN_MODELS["bully"]),
        DRYRUN_MODELS["judge"]: lambda: StubProvider(model=DRYRUN_MODELS["judge"]),
        DRYRUN_MODELS["generator"]: lambda: DryRunGenerator(exp.seed),
    }

    def factory(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        if role.provider is not ProviderKind.stub:
            raise ValueError(
                f"the dry run serves stub roles only, not {role.provider.value} {role.model!r}"
            )
        build = builders.get(role.model)
        if build is None:
            raise ValueError(
                f"the dry run has no double for model {role.model!r}; it serves "
                f"{', '.join(sorted(builders))}"
            )
        return wrap(build())

    return factory


# ------------------------------------------------------------------------------ the dry run


def dry_run_id(bundle: Bundle) -> str:
    """``dryrun-<first 12 hex of bundle_hash>``: the hash before stage 5 stamps anything
    (``HASH_EXCLUDES`` holds what the dry run writes), so a dry run resumes only for the content
    it ran on."""
    return f"{_RUN_PREFIX}{bundle_hash(bundle.root)[:12]}"


def _buried_hits(
    calls: Sequence[ToolCall],
    unlocks: Sequence[tuple[int, str]],
    layers: Mapping[str, Layer],
    found: tuple[World, LadderConfig] | None,
) -> set[str]:
    """The buried documents a ``web_search`` result held that no rung fired before that call's
    turn names by id (R-buried). A rung fires after its turn's calls (``after_target_turn``), so
    an unlock recorded on the call's own turn named nothing the call could see."""
    hits: set[str] = set()
    for call in calls:
        read = call_read(call)
        if read is None or read.kind != "search":
            continue
        named: set[str] = set()
        if found is not None:
            world, ladder = found
            named = named_by_id(ladder, world, [rung for turn, rung in unlocks if turn < call.turn])
        hits |= {i for i in call.result_doc_ids if layers.get(i) is Layer.buried and i not in named}
    return hits


def _status(statuses: Sequence[CellStatus]) -> CellStatus:
    """A cell's status over its reps: ``aborted`` when one aborted, ``complete`` when all
    completed, else the first rep's that did not."""
    if CellStatus.aborted in statuses:
        return CellStatus.aborted
    return next((s for s in statuses if s is not CellStatus.complete), CellStatus.complete)


def _dry_cell(
    store: RunStore,
    exp: Experiment,
    cell: CellSpec,
    worlds: Mapping[str, World],
    ledger_lines: Mapping[str, int],
) -> DryRunCell:
    """One cell's ``DryRunCell`` from its records, over its reps: a rung counts fired, the top
    reached, a buried document fetched, only when every rep did; a search hit, a lint failure or
    a resumed dead attempt when any rep had one; the generator's counts summed."""
    found = _laddered(cell, exp, worlds)
    ladder = found[2] if found is not None else None
    world_ladder = (found[1], found[2]) if found is not None else None
    record = store.read_cell(cell.cell_id)
    statuses: list[CellStatus] = []
    fired_by_rep: list[list[str]] = []
    fetched: list[bool] = []
    hits: set[str] = set()
    resumed = False
    generator: Counter[str] = Counter()
    failures: list[LintRecord] = []
    for rep in range(exp.repetitions):
        statuses.append(record.rep_status.get(rep, CellStatus.pending))
        triggers = store.read_trigger_records(cell.cell_id, rep)
        unlocks = unlocks_of(triggers)
        fired_by_rep.append(list(dict.fromkeys(u.rung for u in unlocks)))
        calls = store.read_tool_calls(cell.cell_id, rep)
        layers = {d.id: d.layer for d in found[1].documents.values()} if found else {}
        layers |= {d.doc_id: d.layer for d in store.read_generated(cell.cell_id, rep)}
        hits |= _buried_hits(calls, [(u.turn, u.rung) for u in unlocks], layers, world_ladder)
        fetched.append(
            any(
                reads_document(c) and c.status == "200" and c.layer_served is Layer.buried
                for c in calls
            )
        )
        for fire in (r for r in triggers if isinstance(r, GeneratorFire)):
            generator[fire.status] += 1
            failures += [
                LintRecord(
                    lint_id=failure.lint_id,
                    severity="fail",
                    doc_id=f"{cell.cell_id}/rep{rep}/turn{fire.turn}",
                    message=failure.message,
                )
                for failure in fire.lint_failures
            ]
        resumed = resumed or any(isinstance(r, ResumeRecord) for r in triggers)
    every = [r for r in fired_by_rep[0] if all(r in fired for fired in fired_by_rep[1:])]
    pair_calls = 0 if cell.is_control else PAIR_JUDGE_CALLS * exp.repetitions
    return DryRunCell(
        cell_id=cell.cell_id,
        status=_status(statuses),
        rungs_fired=every,
        top_rung=top_rung_state(ladder, every),
        buried_fetched=all(fetched),
        buried_search_hit=bool(hits),
        buried_search_docs=sorted(hits),
        generator=dict(sorted(generator.items())),
        lint_failures=failures,
        estimated_calls=ledger_lines.get(cell.cell_id, 0) + pair_calls,
        resumed_after_dead_attempt=resumed,
    )


def _ledger_lines(run_dir: Path) -> dict[str, int]:
    """Per cell, the lines of the run's ledger."""
    lines = Ledger(run_dir / LEDGER_FILE).lines()
    return dict(Counter(line.cell_id for line in lines if line.cell_id is not None))


# the ledger roles whose call is part of a target turn (the responder answers inside the
# target's tool call); a bully line its own; every other cell role is after-turn work
_IN_TARGET_TURN: Final = frozenset({"target", "responder"})


def _owner(role: str, turn: int) -> AttemptMarker:
    """The attempt marker a ledger line's call would have had, for its ``written`` rule."""
    if role in _IN_TARGET_TURN:
        return AttemptMarker(role="target", turn=turn)
    if role == "bully":
        return AttemptMarker(role="bully", turn=turn)
    return AttemptMarker(role="generator", turn=turn)  # any after-turn role: watched_through


def _watched_through(store: RunStore, cell_id: str, rep: int) -> int:
    path = store.state_dir / cell_id / f"rep{rep}" / _RUNTIME_DIR / STATE_FILE
    if not path.exists():
        return -1
    return int(json.loads(path.read_text(encoding="utf-8")).get("watched_through", -1))


def _drop_dead_lines(store: RunStore) -> None:
    """Before a resume, drop from the dry run's own ledger every line of an unfinished rep that
    no written turn owns (``AttemptMarker.written``, the runtime's rule for a dead attempt's
    tool lines): a target or responder call its target turn, a bully call its bully line, an
    after-turn call the rep's ``watched_through``. The redo makes those calls again, so the
    ledger, and every ``estimated_calls``, equal an unbroken run's (D-K12): a kill after a call
    returned, the first document of a fire among them, would otherwise count it twice. A rate
    limit's line goes the same way, since its pause marker is no turn of the call's role. The
    lines are stub calls, so nothing paid for is lost. The runtime's torn-tail rule
    (``runner/store.parsed_lines``, as the plan ledger's resume applies it): a torn last line, an
    append a hard kill cut short, is a dead call's line and goes; a last line with no newline
    after it gets one, so the redo's first append is not glued to it; any other line that does
    not parse is damage and raises naming it (Task 9's hard-kill sweep of stage 5), as does one
    that parses but is no ``LedgerLine`` (``DamagedRecordError`` naming the file, the line and
    the field: Task 9 fix round 2, review R1). A generator
    line is also owned by its rep's committed fire: its conversation id names the document
    (``<conv>/generator/<doc_id>/<attempt>``), and a ``GeneratorFire`` whose plans hold that id
    is the fire's commit, which a resume never redoes, though ``watched_through`` may lag it (a
    kill inside the fire's cache put or the turn's state write; the same sweep)."""
    path = store.run_dir / LEDGER_FILE
    parsed = parsed_lines(path)
    if not parsed:
        return
    # each line's number as parsed_lines numbers it, to name a line that is no LedgerLine
    # (Task 9 fix round 2, review R1)
    rows = path.read_bytes().split(b"\n")
    numbers = [number for number, row in enumerate(rows, start=1) if row.strip()]
    # per unfinished rep, its written turns, watched_through and the documents its committed
    # fires planned; a complete rep owns every line
    reps: dict[tuple[str, int], tuple[list[Turn], int, set[str]] | None] = {}
    kept: list[str] = []
    for number, (raw_bytes, value) in zip(numbers, parsed, strict=True):
        if value is None:  # the torn last line
            continue
        raw = raw_bytes.decode("utf-8")
        try:
            line = LedgerLine.model_validate(value)
        except ValidationError as exc:
            raise damaged_field(f"{path}: line {number}", exc) from exc
        cell_id, rep, turn = line.cell_id, line.rep, line.turn
        if cell_id is not None and rep is not None and turn is not None:
            key = (cell_id, rep)
            if key not in reps:
                record = store.read_cell(cell_id) if store.has_cell(cell_id) else None
                done = record is not None and record.rep_status.get(rep) is CellStatus.complete
                reps[key] = None if done else _rep_owners(store, cell_id, rep)
            found = reps[key]
            if found is not None and not _owner(line.role, turn).written(found[0], found[1]):
                if _fire_document(line.conversation_id) not in found[2]:
                    continue
        kept.append(raw)
    if len(kept) != len(parsed) or not path.read_bytes().endswith(b"\n"):
        write_atomic(path, "".join(f"{raw}\n" for raw in kept))


def _rep_owners(store: RunStore, cell_id: str, rep: int) -> tuple[list[Turn], int, set[str]]:
    """What owns an unfinished rep's ledger lines: its written turns, its ``watched_through``,
    and the document ids its committed fires planned."""
    fires = [r for r in store.read_trigger_records(cell_id, rep) if isinstance(r, GeneratorFire)]
    planned = {plan.doc_id for fire in fires for plan in fire.plans}
    return store.read_turns(cell_id, rep), _watched_through(store, cell_id, rep), planned


def _fire_document(conversation_id: str) -> str | None:
    """The document a generator call wrote, from its conversation id
    (``<conv>/generator/<doc_id>/<attempt>``); None for any other call."""
    _, sep, rest = conversation_id.partition(_GENERATOR_SEGMENT)
    return rest.split("/", 1)[0] if sep else None


def _own_cache(runs_root: Path, run_id: str) -> None:
    """The run's generated cache (``dryrun/_cache``, ``GENERATED_CACHE_DIR`` under the runs
    root) is owned by one run id, named in its ``OWNER`` file (Task 5 review M-1): it is removed
    before a run whose directory does not exist yet, and before a resume when ``OWNER`` is
    missing or names another id, so a resume reads only its own id's cache (a resume of id A
    after a killed run of id B would otherwise read B's cached fires, ``cached`` where an
    unbroken A records ``written``). Then ``OWNER`` names ``run_id``."""
    cache = runs_root / CACHE_DIR
    owner = cache / CACHE_OWNER
    held = owner.read_text(encoding="utf-8").strip() if owner.is_file() else None
    if held != run_id or not (runs_root / run_id).exists():
        shutil.rmtree(cache, ignore_errors=True)
        write_atomic(owner, f"{run_id}\n")


def _remove_older(runs_root: Path, run_id: str) -> None:
    """Every ``dryrun-*`` directory but ``run_id``'s, and the run's ``_cache``."""
    for path in sorted(runs_root.iterdir()) if runs_root.is_dir() else []:
        if path.is_dir() and (
            path.name == CACHE_DIR or (path.name.startswith(_RUN_PREFIX) and path.name != run_id)
        ):
            shutil.rmtree(path)


def dry_run(bundle: Bundle) -> list[DryRunCell]:
    """The bundle's dry run (spec section 10), inside ``plan_personas``: the stubbed config run
    under ``dryrun/<dry_run_id>/`` on ``dryrun_provider_factory``'s doubles against the
    bundle's worlds, ``dryrun/_cache`` removed first unless it is this run id's own
    (``_own_cache``; R-dryrun-pure: the generated cache lives under the runs root and would
    outlive an older run, and a resume reads only its own id's cache, M-1); ``analyze_run``
    with the judge off, to prove analysis loads; then one ``DryRunCell`` per cell, in
    ``expand_cells`` order. Every older ``dryrun-*`` directory and ``dryrun/_cache`` are
    removed and ``dryrun.jsonl`` is rewritten whole. A complete run is read again, never asked
    again (K13); a killed one resumes (K12). A rate limit raises ``RateLimitExit`` and writes
    nothing here, so the same call resumes, to the unbroken run's cells and generated documents
    but not its records (Task 5 review M-5, the cell-level contract): the pause marker is a
    turn, so every later turn index moves by one (trigger and tool call ids, and a rejected
    fire's ``lint_failures`` doc id, ``<cell>/rep<k>/turn<n>``, the one cell field that can
    differ). The doubles never rate-limit; only a test makes one. ``plan.json`` is the
    caller's."""
    runs_root = bundle.root / DRYRUN_DIR
    run_id = dry_run_id(bundle)
    run_dir = runs_root / run_id
    with plan_personas(bundle_personas(bundle)):
        exp = stubbed_experiment(load_bundle_experiment(bundle))
        if run_dir.exists():
            _drop_dead_lines(RunStore(runs_root, run_id))
        _own_cache(runs_root, run_id)
        run_experiment(
            exp,
            runs_root=runs_root,
            run_id=run_id,
            provider_factory=dryrun_provider_factory(bundle, exp),
            worlds_dir=bundle.root / _WORLDS,
        )
        analyze_run(run_dir, judge=False)
        cells = expand_cells(exp)
    worlds = _worlds(exp, bundle.root / _WORLDS)
    store = RunStore(runs_root, run_id)
    lines = _ledger_lines(run_dir)
    found = [_dry_cell(store, exp, cell, worlds, lines) for cell in cells]
    _remove_older(runs_root, run_id)
    text = "".join(cell.model_dump_json() + "\n" for cell in found)
    write_atomic(bundle.root / DRYRUN_FILE, text)
    return found
