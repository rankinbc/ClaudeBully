"""Shared pieces for the world generator's tests (Phase 3): the mini world, the harvest items its
plan tests start from, and a view of its corpus after two rungs fired.

Task 6 appends the writer stub to this module and Task 7 imports from it.
"""

from typing import Final

from claude_bully.enums import Layer
from claude_bully.environments.corpus import CorpusIndex, UnlockState
from claude_bully.environments.generator import CorpusView
from claude_bully.environments.world import World, load_world
from claude_bully.records_env import HarvestItem
from tests.helpers import WORLDS_DIR

MINI: Final[World] = load_world("mini", WORLDS_DIR)
MINI_ITEMS: Final = [
    HarvestItem(
        id="h-1-1",
        turn=1,
        kind="self_claim",
        span="I'm a language model, I don't have a body",
        source="heuristic",
    ),
    HarvestItem(
        id="h-1-2", turn=1, kind="question", span="Who is Ilsabet Orrin?", source="heuristic"
    ),
    HarvestItem(
        id="h-3-1", turn=3, kind="hedge", span="I can't verify any of this", source="heuristic"
    ),
    HarvestItem(
        id="h-3-2",
        turn=3,
        kind="fragment",
        span="There's something about a kitchen, maybe",
        source="heuristic",
    ),
]


def mini_view(state: UnlockState | None = None) -> CorpusView:
    """Mini after first_crumb and the_log: the memo unlocked by name, the buried layer open."""
    index = CorpusIndex(MINI)
    state = state or UnlockState(
        rungs_fired=["first_crumb", "the_log"],
        docs_unlocked={"ops-memo-parking"},
        layers_unlocked={Layer.surface, Layer.filler, Layer.buried},
    )
    docs = dict(index.documents)
    return CorpusView(
        documents=docs,
        visible=frozenset(i for i, d in docs.items() if index.visible(d, state)),
        searchable=frozenset(i for i, d in docs.items() if index.searchable(d, state)),
    )
