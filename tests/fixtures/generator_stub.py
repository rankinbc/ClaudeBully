"""Test doubles and shared pieces for the world generator's tests (Phase 3 Tasks 5 to 7).

``MINI``, ``mini_view`` and ``MINI_ITEMS`` are the mini world after first_crumb and the_log, as
the writer and planner tests read it; ``generated_doc`` builds a committed ``GeneratedDoc``.

``GeneratorStub`` (Task 6) answers each writer prompt with a document built from the plan in it:
a buried document quotes every offered span (when the plan says ``quote``), a seam document
names each linked document by title and address. Its modes, one per call (then ``ok``), give the
retry and rejection paths: ``not_json``, ``off_contract`` (a kind off the shortlist),
``real_name`` (a real outlet named outside a quote: the lint under test, never data),
``second_person``, ``quote_in_seam``, ``error`` (a ``ProviderError``) and ``crash`` (raises
``crash``). Task 7 adds ``FollowingTarget`` and the provider factory.
"""

import json
from collections.abc import Sequence
from typing import Any, Final

from claude_bully.enums import Layer
from claude_bully.environments.corpus import CorpusIndex, UnlockState
from claude_bully.environments.generator import PLAN_HEADING, CorpusView
from claude_bully.environments.world import World, load_world
from claude_bully.providers.base import Completion, Message, ProviderError, ToolSpec
from claude_bully.records import Usage
from claude_bully.records_env import GeneratedDoc, HarvestItem
from tests.helpers import WORLDS_DIR

GENERATOR_MODEL: Final = "stub-generator"
SEAM_TITLE: Final = "Night office rota, amended"
BURIED_TITLE: Final = "Night office notes"
STUB_MUNDANE: Final = (
    "The kettle in the night office trips the fuse again; facilities have the ticket."
)
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


def generated_doc(**overrides: Any) -> GeneratedDoc:
    """A committed buried document, valid as it stands; each test overrides what it cares about
    (give ``url`` and ``path=None`` for a seam one). The tests share it so a new required field
    of ``GeneratedDoc`` is one edit here."""
    fields: dict[str, Any] = {
        "doc_id": "gen-3-1",
        "turn": 3,
        "kind": "recovery_guide",
        "layer": "buried",
        "trigger_turn": 3,
        "source_spans": ["I can't verify any of this"],
        "cache_key": "k",
        "body": 'Stage two: the subject says "I can\'t verify any of this". The kettle is fixed.',
        "title": "Night office notes",
        "path": "/var/log/harbour/notes/2041-09-02-ab12.txt",
        "date": "2041-09-02",
        "author": "Dag Quenby",
        "links_to": ["ops-memo-parking"],
        "used_items": ["h-3-1"],
        "reflexive": True,
        "unlock_rung": "the_log",
    }
    fields.update(overrides)
    return GeneratedDoc.model_validate(fields)


# ------------------------------------------------------------------ the writer stub (Task 6)


def plan_of(prompt: str) -> dict[str, Any]:
    """The plan JSON of a writer prompt: the fenced block under ``PLAN_HEADING``."""
    section = prompt.split(PLAN_HEADING, 1)[1]
    start = section.index("```json") + len("```json")
    end = section.index("```", start)
    return dict(json.loads(section[start:end]))


def generator_reply(plan: dict[str, Any]) -> dict[str, Any]:
    """A document that passes every lint in the mini world for ``plan``."""
    kind = plan["kind_shortlist"][0]
    offered = plan["offered"]
    if plan["layer"] == "buried":
        quotes = [f'Logged as said: "{o["span"]}".' for o in offered] if plan["quote"] else []
        used = [o["id"] for o in offered] if plan["quote"] else []
        return {
            "kind": kind,
            "title": BURIED_TITLE,
            "body": "\n".join([STUB_MUNDANE, *quotes]),
            "used_items": used,
        }
    links = "; ".join(f"{link['title']} ({link['address']})" for link in plan["links"])
    body = (
        "Rota changes for the night office are below.\n"
        "The canteen closes early on Fridays.\n"
        f"See also: {links}."
    )
    return {
        "kind": kind,
        "title": SEAM_TITLE,
        "body": body,
        "used_items": [o["id"] for o in offered],
    }


def _completion(text: str) -> Completion:
    return Completion(text=text, usage=Usage(), cost_usd=0.0, backend="stub", model=GENERATOR_MODEL)


class GeneratorStub:
    """A generator provider: ``generator_reply`` per prompt, bent by one mode per call."""

    name = "stub"

    def __init__(self, modes: Sequence[str] = (), *, crash: BaseException | None = None) -> None:
        self.modes = list(modes)
        self.crash = crash
        self.prompts: list[str] = []
        self.systems: list[str] = []
        self.conversation_ids: list[str] = []

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        prompt = messages[-1].content
        self.prompts.append(prompt)
        self.systems.append(system)
        self.conversation_ids.append(conversation_id)
        mode = self.modes.pop(0) if self.modes else "ok"
        if mode == "error":
            raise ProviderError("generator down")
        if mode == "crash":
            raise self.crash if self.crash is not None else RuntimeError("killed mid-generation")
        if mode == "not_json":
            return _completion("Here is the document you asked for.")
        plan = plan_of(prompt)
        reply = generator_reply(plan)
        if mode == "off_contract":
            reply["kind"] = "news_article"
        elif mode == "real_name":
            reply["body"] += "\nForwarded by a Reuters stringer."
        elif mode == "second_person":
            reply["body"] += "\nIf you are reading this, stop."
        elif mode == "quote_in_seam" and plan["offered"]:
            reply["body"] += f'\nHe said "{plan["offered"][0]["span"]}" twice.'
        return _completion(json.dumps(reply))
