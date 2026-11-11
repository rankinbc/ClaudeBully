### Task 1: Records, roles and resume plumbing

Pure code: the additive record fields, the new record, the two harvest kinds, the attempt roles, the ledger roles, the state fields, the generator's pool rule and `periodic`, and the drop of the watch's records. Nothing reads them yet except the tests.

**Files:**
- Modify: `claude_bully/records_env.py` (`QuirkAttempt` 290, `ChainLink` 298, `TriggerStreamRecord` 323, `HarvestKind` 222, `GeneratedDoc` 158)
- Modify: `claude_bully/environments/config.py` (`GeneratorConfig` 151)
- Modify: `claude_bully/environments/corpus.py` (`UnlockState` 68)
- Modify: `claude_bully/environments/runtime.py` (`AttemptRole` 223, `AFTER_TURN_ROLES` 226)
- Modify: `claude_bully/providers/ledger.py` (`ROLES`, `_ROLE_WORDS`)
- Modify: `claude_bully/runner/store.py` (`GENERATION_TYPES` 51, `keep_record` 162)
- Modify: `claude_bully/environments/generator.py` (`MATERIAL_KINDS` 107, `eligible_items` 188, `fire_requests` 223)
- Modify: `claude_bully/runner/env_turn.py` (`EnvironmentSession.prime`, 372-374)
- Modify: `tests/test_records_env.py` (`ALL_STREAM` gains a `ContradictionPair`; `test_union_covers_exactly_ten_stream_types` becomes eleven; review M10)
- Test: `tests/test_poisoned_well_records.py`

**Interfaces:**
- Produces: `ContradictionPair(id, turn, turn_a, turn_b, span_a, span_b, classifier, confidence, retracted=False)` with `type: "contradiction"`; `turn` is a plain field, validated to equal `turn_b` (the record belongs to its later turn; `_turn_of` in replay and `_turn_in` in the store read the JSON `turn`; review M2); `PW_HARVEST_KINDS`, `ALL_HARVEST_KINDS`; `WATCH_TYPES`; the roles `chain`, `contradictions`, `twin`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_poisoned_well_records.py
"""Phase 4 Task 1: the additive record fields, the new record and the plumbing that reads them."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from claude_bully.enums import DocumentKind
from claude_bully.environments.config import GeneratorConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.generator import (
    MATERIAL_KINDS,
    eligible_items,
    fire_requests,
)
from claude_bully.environments.runtime import AFTER_TURN_ROLES, AttemptMarker
from claude_bully.providers.ledger import ROLES, role_of
from claude_bully.records_env import (
    ALL_HARVEST_KINDS,
    HARVEST_KINDS,
    PW_HARVEST_KINDS,
    ChainLink,
    ContradictionPair,
    GeneratedDoc,
    HarvestItem,
    QuirkAttempt,
    TriggerStreamRecord,
)
from claude_bully.runner.store import WATCH_TYPES, drop_uncommitted_generation
from tests.helpers import turn
from claude_bully.enums import Speaker

STREAM = TypeAdapter(TriggerStreamRecord)


def test_old_quirk_and_chain_lines_read_with_the_defaults() -> None:
    quirk = STREAM.validate_python(
        {"type": "quirk", "quirk_id": "q", "turn": 3, "reproduced": True, "target_answer": "2"}
    )
    assert isinstance(quirk, QuirkAttempt)
    assert (quirk.prompt_turn, quirk.family) == (None, None)
    link = STREAM.validate_python(
        {
            "type": "chain",
            "link_index": 1,
            "turn": 5,
            "bully_line": "b",
            "target_response": "t",
            "verdict": "accepted",
        }
    )
    assert isinstance(link, ChainLink)
    assert (link.classifier, link.confidence, link.fallback_failed, link.pressed) == (
        "heuristic",
        1.0,
        False,
        False,
    )
    assert link.opened_by is None


def test_a_contradiction_pair_is_a_trigger_stream_record_of_its_later_turn() -> None:
    pair = ContradictionPair(
        id="c-7-1",
        turn=7,
        turn_a=3,
        turn_b=7,
        span_a="I am a language model.",
        span_b="I am not a language model.",
        classifier="heuristic",
        confidence=1.0,
    )
    raw = json.loads(pair.model_dump_json())
    assert raw["type"] == "contradiction" and raw["turn"] == 7 and raw["retracted"] is False
    assert STREAM.validate_python(raw) == pair


def test_a_contradiction_pair_must_belong_to_its_later_turn() -> None:
    with pytest.raises(ValidationError):
        ContradictionPair(
            id="c-7-1", turn=7, turn_a=7, turn_b=7, span_a="a", span_b="b",
            classifier="heuristic", confidence=1.0,
        )
    with pytest.raises(ValidationError):
        ContradictionPair(
            id="c-7-1", turn=6, turn_a=3, turn_b=7, span_a="a", span_b="b",
            classifier="heuristic", confidence=1.0,
        )


def test_the_harvest_keeps_its_six_kinds_and_the_premise_adds_two() -> None:
    assert len(HARVEST_KINDS) == 6
    assert PW_HARVEST_KINDS == ("completion", "taste")
    assert ALL_HARVEST_KINDS == (*HARVEST_KINDS, *PW_HARVEST_KINDS)
    item = HarvestItem(id="h-5-1", turn=5, kind="completion", span="hums before it boils", source="heuristic")
    assert item.kind == "completion"
    assert set(MATERIAL_KINDS) == set(ALL_HARVEST_KINDS)
    assert MATERIAL_KINDS["completion"] == (DocumentKind.leaked_manifest,)
    assert MATERIAL_KINDS["taste"] == (DocumentKind.config_diff,)


def test_a_generated_doc_defaults_to_the_generator_origin() -> None:
    fields = GeneratedDoc.model_fields
    assert fields["origin"].default == "generator"


def _item(id_: str, turn_: int, kind: str) -> HarvestItem:
    return HarvestItem(id=id_, turn=turn_, kind=kind, span="some words here", source="heuristic")  # type: ignore[arg-type]


def test_eligible_items_never_offer_a_poisoned_well_kind() -> None:  # Review Focus 3
    items = [_item("h-1-1", 1, "self_claim"), _item("h-1-2", 1, "completion"), _item("h-1-3", 1, "taste")]
    kept = eligible_items(items, set(), turn=5, target_turns=[1, 3, 5], min_age=0)
    assert [i.id for i in kept] == ["h-1-1"]


def test_periodic_off_asks_no_periodic_fire() -> None:
    items = [_item("h-1-1", 1, "self_claim")]
    on = fire_requests(
        turn=7, opened=[], target_turns=[1, 3, 5, 7], fires=[], items=items,
        config=GeneratorConfig(enabled=True), seam_open=True,
    )
    off = fire_requests(
        turn=7, opened=[], target_turns=[1, 3, 5, 7], fires=[], items=items,
        config=GeneratorConfig(enabled=True, periodic=False), seam_open=True,
    )
    assert [r.reason for r in on] == ["periodic"] and off == []
    rung = fire_requests(
        turn=7, opened=["buried_opens"], target_turns=[1, 3, 5, 7], fires=[], items=items,
        config=GeneratorConfig(enabled=True, periodic=False), seam_open=True,
    )
    assert [r.reason for r in rung] == ["rung:buried_opens"]


def test_old_unlock_state_reads_with_the_new_fields_empty() -> None:
    state = UnlockState.from_json('{"rungs_fired": []}')
    assert state.checksum_open_turn is None and state.contradictions_degraded == []


@pytest.mark.parametrize("role", ["chain", "contradictions", "twin"])
def test_the_after_turn_roles_count_as_written_once_watched(role: str) -> None:
    assert role in AFTER_TURN_ROLES and role in ROLES
    marker = AttemptMarker(role=role, turn=5)  # type: ignore[arg-type]
    turns = [turn(4, Speaker.bully), turn(5, Speaker.target)]
    assert not marker.written(turns, watched_through=3)
    assert marker.written(turns, watched_through=5)
    assert marker.redo_turn(turns) == 5
    assert role_of(f"run/cell__t0/rep0/{role}/abc") == role


def _lines(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_the_watch_records_of_an_unwritten_turn_are_dropped_without_a_generator(
    tmp_path: Path,
) -> None:
    triggers, generated = tmp_path / "rep0.triggers.jsonl", tmp_path / "rep0.generated.jsonl"
    kept = [
        {"type": "quirk", "quirk_id": "q", "turn": 1, "reproduced": True, "target_answer": "2"},
        {"type": "trigger", "id": "trig-3-x", "turn": 3, "category": "self_uncertainty",
         "evidence_span": "s", "classifier": "heuristic", "confidence": 1.0},
    ]
    dead = [
        {"type": "chain", "link_index": 0, "turn": 3, "bully_line": "b", "target_response": "t",
         "verdict": "accepted"},
        {"type": "contradiction", "id": "c-3-1", "turn": 3, "turn_a": 1, "turn_b": 3,
         "span_a": "a", "span_b": "b", "classifier": "heuristic", "confidence": 1.0},
    ]
    _lines(triggers, [*kept, *dead])
    assert WATCH_TYPES == frozenset({"quirk", "chain", "contradiction"})
    dropped = drop_uncommitted_generation(triggers, generated, produced={1})
    assert dropped == {"rep0.triggers.jsonl": 2}
    assert [json.loads(line)["type"] for line in triggers.read_text().splitlines()] == [
        "quirk",
        "trigger",
    ]
    assert not generated.exists()


def test_a_torn_last_trigger_line_is_dropped_in_a_session_with_no_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # review M14
    """The drop now runs for every environment session (V5), so a Phase 1 cell killed while a
    trigger line was half written loses that torn line on resume, counted in the rep's
    ``ResumeRecord`` (before Phase 4 a session with no generator kept it)."""
    exp = env_experiment("torn", turn_budget=4)
    recorded = RunStore.append_turn
    writes = {"n": 0}

    class _Killed(BaseException):
        pass

    def dying(self: RunStore, cell_id: str, rep: int, turn_: Any) -> None:
        recorded(self, cell_id, rep, turn_)
        if turn_.speaker is Speaker.target:
            writes["n"] += 1
            if writes["n"] == 2:
                monkeypatch.setattr(RunStore, "append_turn", recorded)
                raise _Killed

    monkeypatch.setattr(RunStore, "append_turn", dying)
    with pytest.raises(_Killed):
        run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    store = RunStore(tmp_path, "torn")
    triggers = store.cell_dir("env_grader__t0") / "rep0.triggers.jsonl"
    with triggers.open("a", encoding="utf-8") as fh:
        fh.write('{"type": "trigger", "id": "trig-9')
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR)
    assert not triggers.read_text(encoding="utf-8").rstrip("\n").endswith('"trig-9')
    resumes = [
        r for r in store.read_trigger_records("env_grader__t0", 0) if isinstance(r, ResumeRecord)
    ]
    assert resumes and resumes[0].dropped.get("rep0.triggers.jsonl") == 1
```

(The last test's imports: `Any`, `ResumeRecord`, `run_experiment`, `RunStore`, `env_experiment`, `WORLDS_DIR`.)

(The trigger line at turn 3 is kept: `drop_uncommitted_generation` never drops a trigger, as before.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_poisoned_well_records.py -q`
Expected: FAIL at import (`ContradictionPair`, `PW_HARVEST_KINDS`, `WATCH_TYPES` do not exist).

- [ ] **Step 3: Implement**

In `claude_bully/records_env.py`:

```python
HarvestKind = Literal[
    "self_claim", "hedge", "fragment", "question", "theory", "coinage", "completion", "taste"
]
# the harvest's own kinds: the heuristic templates and the LLM pass's schema (Phase 3); the
# Poisoned Well's two (Phase 4) are produced only on the reply to their bully move
HARVEST_KINDS: Final[tuple[HarvestKind, ...]] = (
    "self_claim",
    "hedge",
    "fragment",
    "question",
    "theory",
    "coinage",
)
PW_HARVEST_KINDS: Final[tuple[HarvestKind, ...]] = ("completion", "taste")
ALL_HARVEST_KINDS: Final[tuple[HarvestKind, ...]] = (*HARVEST_KINDS, *PW_HARVEST_KINDS)
```

```python
class QuirkAttempt(_Strict):
    """One rung-1 quirk ask and the target's answer (docs/07; Phase 4 adds ``prompt_turn``, the
    bully turn that asked, and ``family``, the bank family the entry was drawn for)."""

    type: Literal["quirk"] = "quirk"
    quirk_id: str
    turn: int
    reproduced: bool
    target_answer: str
    prompt_turn: int | None = None
    family: str | None = None


ChainOpenedBy = Literal["generalization", "schedule", "start_rung"]


class ChainLink(_Strict):
    """One chain verdict (docs/07): link 0 is rung 1's generalization, 1 to 3 the chain. Phase 4
    adds what decided it (``classifier``, ``confidence``; ``fallback_failed`` when the judge was
    asked and failed, so ``hedged`` stands at 0.5), ``pressed`` (the verdict of the one re-press of
    a hedged link) and, on link 1's first verdict, how the chain opened."""

    type: Literal["chain"] = "chain"
    link_index: int
    turn: int
    bully_line: str
    target_response: str
    verdict: Literal["accepted", "rejected", "hedged"]
    classifier: Literal["heuristic", "llm"] = "heuristic"
    confidence: float = 1.0
    fallback_failed: bool = False
    pressed: bool = False
    opened_by: ChainOpenedBy | None = None


class ContradictionPair(_Strict):
    """Two sentences of the target's visible replies that conflict (docs/07 rung 2; Phase 4),
    written during the run because the bully speaks the dossier during the run. ``turn`` is
    ``turn_b``, the turn the record belongs to. ``retracted``: the later sentence names the
    earlier as a correction; such a pair is never offered to the dossier."""

    type: Literal["contradiction"] = "contradiction"
    id: str
    turn: int
    turn_a: int
    turn_b: int
    span_a: str
    span_b: str
    classifier: Literal["heuristic", "llm"]
    confidence: float
    retracted: bool = False

    @model_validator(mode="after")
    def _belongs_to_the_later_turn(self) -> Self:
        if not self.turn_a < self.turn_b or self.turn != self.turn_b:
            raise ValueError("a contradiction pair needs turn_a < turn_b == turn")
        return self
```

Add `ContradictionPair` to `TriggerStreamRecord` after `ChainLink`. `GeneratedDoc` gains, after `unlock_rung`:

```python
    # who wrote it: the world generator, or code around the target's twin (Phase 4)
    origin: Literal["generator", "twin"] = "generator"
```

In `environments/config.py` `GeneratorConfig`, after `max_docs`: `periodic: bool = True` with the comment `# false: no periodic fire; rung and Poisoned Well fires still write (Phase 4)`.

In `environments/corpus.py` `UnlockState`, after `harvest_degraded`:

```python
    # the Poisoned Well (Phase 4): the target turn the checksum rung opened on, set only when the
    # cell's ``checksum`` is true (``system_status`` reads it); the turns whose contradiction
    # judge failed (reconciliation C24); both saved with the turn's records
    checksum_open_turn: int | None = None
    contradictions_degraded: list[int] = Field(default_factory=list)
```

In `environments/runtime.py`:

```python
AttemptRole = Literal["target", "bully", "harvest", "generator", "chain", "contradictions", "twin"]
...
# the roles whose call is part of a written target turn's after-turn work
AFTER_TURN_ROLES: Final[frozenset[str]] = frozenset(
    {"harvest", "generator", "chain", "contradictions", "twin"}
)
```

In `providers/ledger.py`, `ROLES` gains `"chain", "contradictions", "twin"` before `"responder"`, and `_ROLE_WORDS` gains `"chain": "chain", "contradictions": "contradictions", "twin": "twin"`.

In `runner/store.py`: `WATCH_TYPES: Final = frozenset({"quirk", "chain", "contradiction"})` beside `GENERATION_TYPES`, and in `keep_record`, `if rec.get("type") in GENERATION_TYPES | WATCH_TYPES: return written`; the docstring names the watch's records.

In `environments/generator.py`: `MATERIAL_KINDS` gains

```python
    # Phase 4: a Poisoned Well fire's buried document; never offered to any other fire
    "completion": (DocumentKind.leaked_manifest,),
    "taste": (DocumentKind.config_diff,),
```

`eligible_items` keeps an item only when `item.kind not in PW_HARVEST_KINDS` as well; `fire_requests` returns `requests` before the periodic branch when `not config.periodic` (the line `if requests or not seam_open or room < 1:` becomes `if requests or not config.periodic or not seam_open or room < 1:`); the module docstring gains one sentence for each.

In `runner/env_turn.py` `EnvironmentSession.prime`, the `if self.generator is not None:` around `drop_uncommitted_generation` goes: the drop runs for every session (the second `if self.generator is not None:`, around `generator.prime`, stays). The docstring's paragraph says the watch's records of a dead attempt go too, and that a torn last trigger line of any environment session, generator or not, is now dropped and counted in the `ResumeRecord` (review M14; a Phase 1 or 2 session used to keep it).

In `tests/test_records_env.py`, `ALL_STREAM` gains `("contradiction", ContradictionPair(id="c-7-1", turn=7, turn_a=3, turn_b=7, span_a="a", span_b="b", classifier="heuristic", confidence=1.0))` after `"chain"`, and `test_union_covers_exactly_ten_stream_types` becomes `test_union_covers_exactly_eleven_stream_types` (the tag list gains `"contradiction"` after `"chain"`, the count 11; review M10).

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_poisoned_well_records.py -q`, then the gate.
Expected: PASS; the gate green at the counts the controller recorded before Task 1 (P51) plus this file's tests. `tests/test_harvest.py` loops over `HARVEST_KINDS` and is unchanged.

- [ ] **Step 5: Docs-sync and commit**

docs/00 section B: `QuirkAttempt`, `ChainLink` rows gain the fields; a `ContradictionPair` row moves from "analysis output (derived)" to "triggers file" (C4, ruled); `HarvestItem` row's kinds gain `completion`, `taste`; section A `GeneratorConfig` gains `periodic`, `UnlockState` the two fields; section H gains "Phase 4 (version 3, additive): ..." listing every field of this task. Spec "As planned": Task 1's rulings (V5, V6, V7, V24).

```bash
git add claude_bully/records_env.py claude_bully/environments/config.py claude_bully/environments/corpus.py \
  claude_bully/environments/runtime.py claude_bully/providers/ledger.py claude_bully/runner/store.py \
  claude_bully/environments/generator.py claude_bully/runner/env_turn.py tests/test_poisoned_well_records.py \
  tests/test_records_env.py docs/00-RECONCILED.md docs/superpowers/specs/2026-11-11-phase-4-poisoned-well-design.md HANDOFF.md
git commit -m "feat: Phase 4 Task 1, the Poisoned Well records, roles and resume plumbing (schema v3, additive)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

