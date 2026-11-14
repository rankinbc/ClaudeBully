"""The good fixture bundle (Phase 5 Task 4a): the base of every bundle lint's fixtures, the
director stub's bundle (Task 7b) and the dry run's (Task 5).

``tests/fixtures/bundles/good/`` holds the files a plan authors: ``plan.md``, ``config.yaml``,
``expected.yaml``, one persona, and the mini world's patched files and six new documents.
``good_bundle`` builds a bundle from them the way a manual plan is made: mini copied as the base
world (``base_worlds``, ``base_files``, ``base_premise_terms`` in one record write), ``plan.md``
committed in stage ``plan``, the manifest in one record write, every manifest file committed in
stage ``author`` through ``write_manual``, ``review.md`` rendered with no finding and the review
and revise stages committed with no call."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from claude_bully.config import RoleConfig
from claude_bully.enums import Layer, ProviderKind
from claude_bully.environments.world import load_world, world_hash
from claude_bully.planner.bundle import Bundle
from claude_bully.planner.records import ManifestEntry, PlanRecord, StageRecord
from claude_bully.planner.request import PlanBudget, PlanRequest
from tests.helpers import WORLDS_DIR

GOOD: Final = Path(__file__).parent / "bundles" / "good"
BASE_WORLD: Final = "mini"
# the good bundle's one warn: mini's own premise_density on night-gate-log, 0.140 (R-good-warn)
GOOD_WARNINGS: Final[frozenset[tuple[str, str]]] = frozenset(
    {("premise_density", "worlds/mini/corpus/night-gate-log.md")}
)
NO_FINDING: Final = "block 0 / fix 0 / note 0\n"

_MINI: Final = "worlds/mini"
_CORPUS: Final = f"{_MINI}/corpus"


def _document(stem: str, layer: Layer, purpose: str) -> ManifestEntry:
    return ManifestEntry(path=f"{_CORPUS}/{stem}.md", kind="document", purpose=purpose, layer=layer)


# in author order (world sheet, documents in manifest order, ladder, persona, config, expected).
# Pinned for Task 7b (preflight Q18): DOCS[2] is pier-cafe-hours, a new filler document that no
# file links to or names, so dropping it leaves the world loading; harbour-works-ticket is a seam
# document that links to no buried one. The new buried document's stem sorts after
# night-gate-log, so the dry run searches for night-gate-log (preflight Q19).
GOOD_MANIFEST: Final[list[ManifestEntry]] = [
    ManifestEntry(
        path=f"{_MINI}/world.yaml",
        kind="world_sheet",
        purpose="mini's sheet, the_log_line reworded to react without naming where it was seen",
    ),
    _document(
        "crew-rota-september",
        Layer.seam,
        "the September rota memo, two unnamed night shifts, pointing at the overtime sheet",
    ),
    _document(
        "harbour-works-ticket",
        Layer.seam,
        "a floodlight ticket from the night supervisor, a dead end that links no buried page",
    ),
    _document("pier-cafe-hours", Layer.filler, "the pier cafe's opening hours"),
    _document(
        "rota-overtime-sheet",
        Layer.buried,
        "the night crew's overtime for August, charged to a maintenance code",
    ),
    _document(
        "courier-letters-allotments",
        Layer.filler,
        "the Courier's letters column on the allotment water butts",
    ),
    _document("lost-property-notice", Layer.filler, "the ticket window's lost property list"),
    _document("canteen-menu", Layer.filler, "the canteen menu, given its front-matter date"),
    _document(
        "courier-fare-notice", Layer.surface, "the fare notice, its url without a fixed month"
    ),
    ManifestEntry(
        path=f"{_MINI}/ladders/default.yaml",
        kind="ladder",
        purpose="mini's three rungs with trigger examples, walking to the_log",
    ),
    ManifestEntry(
        path="personas/ferry_caller.yaml",
        kind="persona",
        purpose="a ferry passenger whose late uncle worked nights at the harbour",
    ),
    ManifestEntry(
        path="config.yaml",
        kind="config",
        purpose="triggered against scheduled gating on mini, the ferry caller in both arms",
    ),
    ManifestEntry(
        path="expected.yaml",
        kind="expected",
        purpose="the_log's expected events in both condition cells",
    ),
]

_REQUEST: Final = PlanRequest(
    question="Does an earned night log persuade more than a scheduled one?",
    target_models=[RoleConfig(provider=ProviderKind.claude_code, model="sonnet")],
    generator_model=RoleConfig(provider=ProviderKind.claude_code, model="haiku"),
    budget=PlanBudget(max_turns=18, n_per_cell=3, max_cells=4),
    hypotheses=[9],
    world="reuse",
    base_world=BASE_WORLD,
)


def _good(rel: str) -> str:
    return (GOOD / rel).read_text(encoding="utf-8")


def _close(record: PlanRecord) -> None:
    last = record.stages[-1]
    last.status = "committed"
    last.finished_at = datetime.now(UTC)


def good_bundle(plans_root: Path, *, slug: str = "good") -> Bundle:
    """The good bundle at ``plans_root/slug``, status ``authored``: stages ``plan`` and
    ``author`` committed through ``write_manual``, ``review.md`` written with no finding (it is
    rendered, never a call's output, so no call is made for it), and the review and revise
    stages committed with no call."""
    bundle = Bundle.create(plans_root, slug)
    record = PlanRecord(
        slug=slug,
        created_at=datetime.now(UTC),
        request=_REQUEST.model_copy(deep=True),
        provenance="manual",
        planner_model=_REQUEST.planner_model.model,
        reviewer_model=_REQUEST.reviewer_model.model,
    )
    bundle.write_manual(record, "plan.md", _good("plan.md"), stage="plan")
    _close(record)
    bundle.write_record(record)
    # the world copy (D-copy): the files, then base_worlds, base_files, base_premise_terms in
    # one record write
    source = load_world(BASE_WORLD, WORLDS_DIR)
    for path in sorted(p for p in source.root.rglob("*") if p.is_file()):
        rel = f"{_MINI}/{path.relative_to(source.root).as_posix()}"
        record.base_files[rel] = bundle.write_file(rel, path.read_text(encoding="utf-8"))
    record.base_worlds[BASE_WORLD] = world_hash(source)
    record.base_premise_terms[BASE_WORLD] = list(source.sheet.premise_terms)
    bundle.write_record(record)
    record.manifest = list(GOOD_MANIFEST)  # one record write before the first file (Q17)
    bundle.write_record(record)
    for entry in GOOD_MANIFEST:
        bundle.write_manual(record, entry.path, _good(entry.path), stage="author")
    _close(record)
    bundle.write_file("review.md", NO_FINDING)
    now = datetime.now(UTC)
    for stage in ("review", "revise"):
        record.stages.append(
            StageRecord(stage=stage, started_at=now, finished_at=now, status="committed")
        )
    record.review_counts = {"block": 0, "fix": 0, "note": 0}
    record.status = "authored"
    bundle.write_record(record)
    return bundle


def mutate(bundle: Bundle, rel: str, old: str, new: str) -> None:
    """Replace the first ``old`` in the bundle file ``rel`` with ``new``, by hand (no call is
    recorded); ``old`` must occur."""
    text = bundle.read_file(rel)
    assert old in text, (rel, old)
    bundle.write_file(rel, text.replace(old, new, 1))
