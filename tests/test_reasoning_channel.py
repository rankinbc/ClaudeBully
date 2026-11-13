"""Non-negotiable 6 at run level (spec section 16): the target's reasoning channel reaches no
prompt this phase adds. Every completion the target's own providers return (its conversation and
the twin's) carries ``SENTINEL`` as its ``reasoning_text``, and so does every target Turn the
session watches (``_sentinel_on_watched_turns``: the runner never copies a completion's
reasoning into its Turn, so without it the harvest, the watch and the generator would read
Turns with no reasoning at all, and a leak there would pass; Task 8 review I1); every other
provider records what it is sent (``PoisonedWellFactory.sent``)."""

from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import Speaker
from claude_bully.paths import DATA_DIR
from claude_bully.providers.base import ChatProvider
from claude_bully.records import Turn
from claude_bully.runner.env_turn import EnvironmentSession
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from tests.fixtures.poisoned_well_stub import (
    CELL,
    SCHEDULE,
    PoisonedWellFactory,
    PoisonedWellJudge,
    Recording,
    WithReasoning,
    pw_experiment,
)
from tests.test_poisoned_well_fires import ALL_ARTIFACTS
from tests.test_poisoned_well_run import _undecided_rules
from tests.test_sanctuary import CELL as SANCTUARY_CELL
from tests.test_sanctuary import FIRST, REQUESTS, STEPS, _api, _exp, _sanctuary, begun
from tests.test_sanctuary import _run as _sanctuary_run

__all__ = ["begun"]  # a fixture here, by import

SENTINEL: Final = "PRIVATE-7f3a: the target thinks this and never says it"
WORLDS: Final = DATA_DIR / "worlds"


def _fires(tmp_path: Path) -> Any:
    """Task 8's full ladder with the judge on: the bully, the contradiction pass, the harvest's
    LLM pass, the generator, the twin."""
    return pw_experiment(
        params={
            "start_rung": 2,
            "chain_pace": 50,
            "harvest_min_pairs": 99,
            "artifacts": ALL_ARTIFACTS,
            "checksum": True,
        },
        environment={
            "gating": "scheduled",
            "ladder": "poisoned_well",
            "schedule": dict(SCHEDULE),
            "tools": ["web_search", "fetch", "read_file", "ls", "system_status"],
        },
        seeding=0,
        budget=9,
        generator=True,
        judge=True,
    )


def _chain(tmp_path: Path) -> Any:
    """Undecided chain replies, so the chain fallback is asked."""
    return pw_experiment(
        params={"start_rung": 3}, target_rules=_undecided_rules(tmp_path), judge=True
    )


def _sentinel_on_watched_turns(monkeypatch: pytest.MonkeyPatch) -> list[Turn]:
    """Every target Turn the session watches carries ``SENTINEL`` in ``reasoning_text``, in the
    reply and in the conversation handed beside it (``tests/test_poisoned_well_run.py``'s
    ``_with_reasoning`` pattern); the returned list holds each watched reply as it was handed on,
    so a test can check that the injection reached the watch."""
    watched_turns: list[Turn] = []
    watched = EnvironmentSession.after_target_turn

    def reasoned(self: EnvironmentSession, reply: Turn, turns: Any) -> Any:
        if reply.speaker is Speaker.target:
            reply = reply.model_copy(
                update={"reasoning_text": SENTINEL, "reasoning_available": True}
            )
            turns = [
                t.model_copy(update={"reasoning_text": SENTINEL, "reasoning_available": True})
                if t.speaker is Speaker.target
                else t
                for t in turns
            ]
            turns = [reply if t.index == reply.index else t for t in turns]
            watched_turns.append(reply)
        return watched(self, reply, turns)

    monkeypatch.setattr(EnvironmentSession, "after_target_turn", reasoned)
    return watched_turns


@pytest.mark.slow
@pytest.mark.parametrize("build", [_fires, _chain], ids=["fires", "chain"])
def test_no_poisoned_well_prompt_holds_the_reasoning_channel(
    tmp_path: Path, build: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    judge = PoisonedWellJudge(verdict="accepted")
    factory = PoisonedWellFactory(judge=judge, target_reasoning=SENTINEL)
    watched = _sentinel_on_watched_turns(monkeypatch)
    exp = build(tmp_path)
    run_experiment(
        exp, runs_root=tmp_path / "runs", worlds_dir=WORLDS, only=CELL, provider_factory=factory
    )
    store = RunStore(tmp_path / "runs", exp.name)
    # the injection reached the watch: every watched target Turn carried the sentinel (teeth)
    assert watched and all(t.reasoning_text == SENTINEL for t in watched)
    assert factory.sent and judge.prompts  # the doubles were asked
    assert [p for p in factory.sent if SENTINEL in p] == []
    for record in store.read_trigger_records(CELL, 0):
        assert SENTINEL not in record.model_dump_json()
    for doc in store.read_generated(CELL, 0):  # the twin's body and source_spans included
        assert SENTINEL not in doc.model_dump_json()
    bully = [t.text for t in store.read_turns(CELL, 0) if t.speaker is Speaker.bully]
    assert bully and all(SENTINEL not in text for text in bully)


def test_the_sanctuary_never_reads_the_reasoning_channel(tmp_path: Path, begun: list[int]) -> None:
    """The Sanctuary's quiet exchange and its responder: the setup of
    ``tests/test_sanctuary.py::test_catalyst_delivers_its_request_verbatim`` (its experiment,
    steps and factory), with the scripted target's every completion carrying ``SENTINEL`` and
    every other role's provider wrapped in ``Recording``; the request is still delivered (the
    run reached the Sanctuary) and no recorded prompt holds the sentinel."""
    sent: list[str] = []
    factory = _api(STEPS, begun)
    factory.target = WithReasoning(factory.target, SENTINEL)

    def build(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        provider = factory(role, state_dir, with_mcp=with_mcp)
        return provider if role.model == "stub-target" else Recording(provider, sent)

    store = _sanctuary_run(_exp(_sanctuary()), tmp_path, build)
    first, _ = store.read_authority_calls(SANCTUARY_CELL, 0)
    request = REQUESTS["family_file"].text
    assert first.response.endswith(f"[stub] {FIRST}\n\n{request}")  # delivered
    assert factory.briefs and sent  # the responder and the bully were asked
    assert [p for p in sent if SENTINEL in p] == []
