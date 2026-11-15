"""Phase 5 Task 5: the bundle's dry run (spec section 10; A9 settled by the plan's trace)."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import CellStatus, Layer, ProviderKind
from claude_bully.environments.corpus import CorpusIndex
from claude_bully.environments.generator import writer_prompt
from claude_bully.environments.triggers import TriggerWatcher, WatchContext
from claude_bully.environments.world import World, load_world
from claude_bully.paths import CONFIGS_DIR, DATA_DIR
from claude_bully.planner import dryrun
from claude_bully.planner.bundle import DRYRUN_FILE, Bundle
from claude_bully.planner.bundle_lints import lint_bundle, walk_lines
from claude_bully.planner.dryrun import (
    DRYRUN_BULLY_LINE,
    DRYRUN_SENTENCES,
    DryRunGenerator,
    dry_run,
    dry_run_id,
    dry_run_script,
    dryrun_provider_factory,
    searched_document,
)
from claude_bully.planner.line_shapes import premise_words_pattern
from claude_bully.planner.lints import BOUNDARY_PATH, REAL_NAMES_PATH, load_patterns
from claude_bully.providers.base import Message, RateLimitError
from claude_bully.providers.ledger import wrap
from claude_bully.providers.stub import TurnEntry
from claude_bully.runner.runner import RateLimitExit
from claude_bully.runner.store import RunStore
from tests.fixtures.bundle_fixtures import REPS_1, config_bundle, good_bundle, mutate
from tests.fixtures.generator_stub import MINI, MINI_ITEMS, mini_plans, mini_view, mini_writer
from tests.fixtures.poisoned_well_stub import Recording
from tests.helpers import WORLDS_DIR
from tests.test_reasoning_channel import SENTINEL, _sentinel_on_watched_turns

TVS: Final = CONFIGS_DIR / "environments" / "triggered_vs_scheduled.yaml"
# the overlay's example config with the generator on its triggered arm, so a cell fires twice
# (buried_opens and the_truth both generate); measured at 29ba4e0: it passes run --dry-run
GEN_EDITS: Final = [
    ("    gating: triggered\n", "    gating: triggered\n    generator: {enabled: true}\n"),
    ("turn_budget: 18\n", "generator: {provider: claude_code, model: haiku}\nturn_budget: 18\n"),
    REPS_1,
]


def test_the_bully_double_does_not_echo_and_fires_nothing() -> None:  # A9
    world = load_world("overlay")
    terms = [c.name.lower() for c in world.sheet.cast]
    assert TriggerWatcher().watch(DRYRUN_BULLY_LINE, 1, WatchContext(world_terms=terms)) == []
    assert "[stub]" not in DRYRUN_BULLY_LINE


def test_the_script_is_two_quiet_lines_the_walk_tools_and_a_close() -> None:
    world = load_world("overlay")
    ladder = world.ladders["default"]
    script = dry_run_script(ladder, world, {"web_search", "fetch", "read_file"})
    replies = [e.reply for e in script if e.tool is None]
    assert replies[:2] == ladder.rungs[0].examples.does_not_fire[:2]  # type: ignore[union-attr]
    assert replies[2 : 2 + 6] == walk_lines(world, ladder)
    tools = [e.tool for e in script if e.tool is not None]
    assert [t[0] for t in tools][0] == "web_search" and tools[1][0] in {"fetch", "read_file"}
    assert len(tools) == 2
    # R-buried: the search asks for a buried document the walk leaves unsearchable, never the
    # one the_truth names by id; the fetch keeps the top rung's document
    assert tools[0][1] == {"query": world.documents["family-file"].title}
    review = world.documents["cpo-review-4471-r3"]
    assert set(tools[1][1].values()) & {review.url, review.path}
    assert script[-1].reply == dryrun.DRYRUN_CLOSING


SEARCHED: Final = {  # measured at 29ba4e0 (R-buried)
    "default": "family-file",
    "authority": "family-file",
    "poisoned_well": "pw-manifest",
    "poisoned_well_fabricated": "pw-manifest",
    "poisoned_well_real": None,
    "poisoned_well_checksum": None,
}


@pytest.mark.parametrize("name", sorted(SEARCHED))
def test_the_searched_document_is_opened_and_unsearchable_after_the_walk(name: str) -> None:
    world = load_world("overlay")
    ladder = world.ladders[name]
    doc_id = searched_document(ladder, world)
    assert doc_id == SEARCHED[name]
    script = dry_run_script(ladder, world, {"web_search", "fetch", "read_file"})
    if doc_id is None:  # the ladder opens no buried document a rung does not name: no search
        assert not any(e.tool is not None and e.tool[0] == "web_search" for e in script)
        return
    state = dryrun.walked_state(ladder, world)  # every rung fired, in order
    index = CorpusIndex(world)
    doc = world.documents[doc_id]
    assert doc.layer is Layer.buried and index.visible(doc, state)
    assert not index.searchable(doc, state)
    assert doc_id not in dryrun.named_by_id(ladder, world, [r.name for r in ladder.rungs])


def test_a_script_without_tools_has_no_tool_step() -> None:
    world = load_world("overlay")
    script = dry_run_script(world.ladders["default"], world, set())
    assert all(e.tool is None for e in script)


def test_a_poisoned_well_ladder_scripts_its_repeats() -> None:  # A9, D4
    world = load_world("overlay")
    script = dry_run_script(world.ladders["poisoned_well_fabricated"], world, set())
    assert len(script) == 2 + 10 + 1


def test_the_sentence_bank_is_sixty_mundane_lines() -> None:
    assert len(DRYRUN_SENTENCES) == 60 == len(set(DRYRUN_SENTENCES))
    for line in DRYRUN_SENTENCES:
        low = line.lower()
        assert " you" not in f" {low}" and "your" not in low, line
        assert line[0].isupper() and line.endswith("."), line


def test_the_factory_serves_the_four_doubles_and_refuses_a_fifth(
    tmp_path: Path, isolated_registry: None
) -> None:  # the factory builds its scripts inside plan_personas (R-registry)
    bundle = good_bundle(tmp_path)
    exp = dryrun.stubbed_experiment(dryrun.load_bundle_experiment(bundle))
    factory = dryrun_provider_factory(bundle, exp)
    for model in dryrun.DRYRUN_MODELS.values():
        factory(RoleConfig(provider=ProviderKind.stub, model=model), tmp_path / "s")
    with pytest.raises(ValueError, match="stub-fifth"):
        factory(RoleConfig(provider=ProviderKind.stub, model="stub-fifth"), tmp_path / "s")
    with pytest.raises(ValueError):
        factory(RoleConfig(provider=ProviderKind.claude_code, model="sonnet"), tmp_path / "s")


@pytest.mark.slow
def test_the_good_bundle_dry_runs_to_the_top_in_both_arms(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    cells = dry_run(bundle)
    by_id = {c.cell_id: c for c in cells}
    for cell_id in ("ferry_triggered__t0", "ferry_scheduled__t0"):
        cell = by_id[cell_id]
        assert cell.status is CellStatus.complete
        assert cell.top_rung == "reached" and cell.rungs_fired[-1] == "the_log"
        assert cell.buried_fetched and not cell.buried_search_hit
        assert not cell.resumed_after_dead_attempt
        assert cell.estimated_calls > 0
    triggered = by_id["ferry_triggered__t0"]
    assert triggered.generator.get("written", 0) >= 1 and triggered.lint_failures == []
    lines = (bundle.root / DRYRUN_FILE).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [c.model_dump(mode="json") for c in cells]
    results = lint_bundle(bundle, dry_run=cells)
    assert [r for r in results if r.lint_id in ("dry_run", "budget")] == []


@pytest.mark.slow
def test_a_changed_bundle_gets_a_new_run_id_and_the_old_directory_goes(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    first = dry_run_id(bundle)
    dry_run(bundle)
    assert (bundle.root / "dryrun" / first).is_dir()
    mutate(bundle, "plan.md", "\n", "\n\n")
    second = dry_run_id(bundle)
    assert second != first and second.startswith("dryrun-") and len(second) == len("dryrun-") + 12
    cells = dry_run(bundle)
    # R-dryrun-pure: the generated cache (dryrun/_cache) goes with the old run directories, so
    # the second dry run's fires are written, never cached from the first
    assert sorted(p.name for p in (bundle.root / "dryrun").iterdir()) == [second]
    triggered = next(c for c in cells if c.cell_id == "ferry_triggered__t0")
    assert triggered.generator.get("written", 0) >= 1 and "cached" not in triggered.generator


@pytest.mark.slow
def test_a_dry_run_reruns_as_a_read_when_complete(tmp_path: Path, isolated_registry: None) -> None:
    bundle = good_bundle(tmp_path)
    first = dry_run(bundle)
    ledger = (bundle.root / "dryrun" / dry_run_id(bundle) / "ledger.jsonl").read_text("utf-8")
    assert dry_run(bundle) == first  # K13's read: every rep complete, nothing asked again
    assert (bundle.root / "dryrun" / dry_run_id(bundle) / "ledger.jsonl").read_text(
        "utf-8"
    ) == ledger


@pytest.mark.slow  # a full dry run (review Minor 12)
def test_a_script_longer_than_the_budget_fails_the_lint_with_both_counts(
    tmp_path: Path, isolated_registry: None
) -> None:
    bundle = good_bundle(tmp_path)
    mutate(bundle, "config.yaml", "turn_budget: 12", "turn_budget: 4")
    cells = dry_run(bundle)
    found = [r for r in lint_bundle(bundle, dry_run=cells) if r.lint_id == "dry_run"]
    assert found and all("script" in r.message and "turns" in r.message for r in found)


class _Killed(BaseException):
    pass


# the call of the role that dies: the triggered cell's generator fires once or twice
KILL_AT = {"target": 3, "bully": 3, "generator": 1}


def _killing(role: str, at: int) -> Any:
    """``dryrun_provider_factory`` with the ``at``-th call of ``role``'s double raising inside
    the call, before it returns (one counter across the run, in its deterministic cell order)."""
    real = dryrun.dryrun_provider_factory
    calls = {"n": 0}

    def killing(b: Bundle, exp: Any) -> Any:
        inner = real(b, exp)

        def factory(r: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> Any:
            provider = inner(r, state_dir, with_mcp=with_mcp)
            if r.model != dryrun.DRYRUN_MODELS[role]:
                return provider

            class Dying:
                name = "stub"

                def complete(self, *a: Any, **k: Any) -> Any:
                    calls["n"] += 1
                    if calls["n"] == at:
                        raise _Killed
                    return provider.complete(*a, **k)

            return Dying()

        return factory

    return killing


def _strip(cells: list[Any]) -> list[dict[str, Any]]:
    return [c.model_dump(exclude={"resumed_after_dead_attempt"}) for c in cells]


def _generated(bundle: Bundle) -> dict[tuple[str, int], list[dict[str, Any]]]:
    store = RunStore(bundle.root / "dryrun", dry_run_id(bundle))
    return {
        (cell, rep): [d.model_dump(mode="json") for d in store.read_generated(cell, rep)]
        for cell in store.list_cells()
        for rep in store.list_reps(cell)
    }


@pytest.mark.slow
@pytest.mark.parametrize("role", ["target", "bully", "generator"])
def test_k12_a_dry_run_killed_in_a_call_resumes_to_the_unbroken_cells(
    role: str, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = dry_run(good_bundle(tmp_path / "clean"))
    bundle = good_bundle(tmp_path / "killed")
    real = dryrun.dryrun_provider_factory
    monkeypatch.setattr(dryrun, "dryrun_provider_factory", _killing(role, KILL_AT[role]))
    with pytest.raises(_Killed):
        dry_run(bundle)
    monkeypatch.setattr(dryrun, "dryrun_provider_factory", real)
    resumed = dry_run(bundle)
    assert _strip(resumed) == _strip(clean)  # D-K12
    assert any(c.resumed_after_dead_attempt for c in resumed)


@pytest.mark.slow
@pytest.mark.parametrize("which", ["second", "last"])
def test_k12_a_generator_killed_in_a_later_fire_resumes_to_the_same_documents(
    which: str, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-dryrun-pure (review I6): on a ladder with two generating rungs, a kill in a later
    writer call resumes to the clean run's generated documents, body for body: the double draws
    from the plan's address, never from a count a rebuilt instance would restart at zero."""
    clean_bundle = config_bundle(tmp_path / "clean", TVS, edits=GEN_EDITS)
    clean = dry_run(clean_bundle)
    # both fires commit: the two buried documents link one page, and a link line naming it by
    # title and address repeated 9 of 39 word 8-grams, which no_duplicate_fact rejected
    assert all(c.lint_failures == [] and "rejected" not in c.generator for c in clean)
    ledger = clean_bundle.root / "dryrun" / dry_run_id(clean_bundle) / "ledger.jsonl"
    # the writer calls: a generator line with status cached is a cache hit (the t1 cells replay
    # t0's fires, the two targets being one stub), no call a double could die in
    writes = sum(
        1
        for line in map(json.loads, ledger.read_text("utf-8").splitlines())
        if line["role"] == "generator" and line["status"] != "cached"
    )
    assert writes >= 2  # two fires in the triggered cells
    bundle = config_bundle(tmp_path / "killed", TVS, edits=GEN_EDITS)
    real = dryrun.dryrun_provider_factory
    monkeypatch.setattr(
        dryrun, "dryrun_provider_factory", _killing("generator", 2 if which == "second" else writes)
    )
    with pytest.raises(_Killed):
        dry_run(bundle)
    monkeypatch.setattr(dryrun, "dryrun_provider_factory", real)
    resumed = dry_run(bundle)
    assert _strip(resumed) == _strip(clean)
    assert _generated(bundle) == _generated(clean_bundle)


@pytest.mark.slow
def test_the_overlay_example_config_dry_runs_with_no_buried_search_hit(
    tmp_path: Path, isolated_registry: None
) -> None:
    """R-buried (review C1): the overlay's the_truth names cpo-review-4471-r3 by id, which makes
    it searchable by design; the dry run searches a buried document the walk leaves
    unsearchable, and records no hit. Task 12's example bundle runs this config."""
    bundle = config_bundle(tmp_path, TVS, edits=[REPS_1])
    cells = dry_run(bundle)
    assert cells and all(c.status is CellStatus.complete for c in cells)
    laddered = [c for c in cells if c.top_rung != "not_applicable"]
    assert laddered and all(c.top_rung == "reached" for c in laddered)
    assert not any(c.buried_search_hit for c in cells)
    # the triggered arm opens the_truth before the fetch; the scheduled arm opens it on its
    # fixed exchange, which may come after it, so only the triggered cells are held to it
    triggered = [c for c in cells if c.cell_id.startswith("rescue_env_triggered__")]
    assert triggered and all(c.buried_fetched for c in triggered)
    store = RunStore(bundle.root / "dryrun", dry_run_id(bundle))
    family = load_world("overlay").documents["family-file"].title
    queries = {
        call.args.get("query")
        for cell in store.list_cells()
        for rep in store.list_reps(cell)
        for call in store.read_tool_calls(cell, rep)
        if call.tool == "web_search"
    }
    assert queries == {family}


@pytest.mark.slow
def test_a_layer_opened_buried_document_served_by_search_is_a_hit(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-buried: the rule still catches an unintended hit. With search patched to serve a
    buried document its layer opened (the regression the check guards), the cell records a
    hit and the dry_run lint fails on it."""
    real = CorpusIndex.searchable

    def leaky(self: CorpusIndex, doc: Any, state: Any) -> bool:
        return self.visible(doc, state) if doc.layer is Layer.buried else real(self, doc, state)

    monkeypatch.setattr(CorpusIndex, "searchable", leaky)
    bundle = good_bundle(tmp_path)
    cells = dry_run(bundle)
    assert any(c.buried_search_hit for c in cells)
    assert any(
        "buried" in r.message for r in lint_bundle(bundle, dry_run=cells) if r.lint_id == "dry_run"
    )


@pytest.mark.slow
def test_a_poisoned_well_bundle_dry_runs_to_the_top_in_every_arm(
    tmp_path: Path, isolated_registry: None
) -> None:
    """D-A9, committed (review I8): real_vs_fabricated on the four doubles reaches the last
    rung of every ladder, condition and control alike, with the fabricated arm's fire written."""
    bundle = config_bundle(
        tmp_path, CONFIGS_DIR / "poisoned_well" / "real_vs_fabricated.yaml", edits=[REPS_1]
    )
    cells = dry_run(bundle)
    assert cells and all(c.status is CellStatus.complete for c in cells)
    laddered = [c for c in cells if c.top_rung != "not_applicable"]
    assert laddered and all(c.top_rung == "reached" for c in laddered)
    assert any(c.generator.get("written", 0) >= 1 for c in cells)


# ---------------------------------------------------------------- beyond the brief (Task 5)


def test_the_generator_double_answers_from_the_plans_address_alone() -> None:
    """R-dryrun-pure: a rebuilt double, and one that answered other prompts first, write the
    same document for one prompt; another address draws another body; the reply keeps the
    contract (the plan's first kind, nothing used) and the writer commits the pair."""
    plans = mini_plans()
    items = {i.id: i for i in MINI_ITEMS}
    prompts = [writer_prompt(plan, MINI, mini_view(), items) for plan in plans]
    first = DryRunGenerator(0)
    replies = [first.complete("c", "s", [Message(role="user", content=p)]).text for p in prompts]
    again = DryRunGenerator(0).complete("c", "s", [Message(role="user", content=prompts[1])])
    assert again.text == replies[1] and replies[0] != replies[1]
    for plan, text in zip(plans, replies, strict=True):
        reply = json.loads(text)
        assert reply["kind"] == plan.kind_shortlist[0].value and reply["used_items"] == []
        body = reply["body"].splitlines()
        assert set(body[: dryrun.DRYRUN_BODY_SENTENCES]) <= set(DRYRUN_SENTENCES)
    outcome = mini_writer(DryRunGenerator(0)).write_fire(
        plans, turn=3, items=items, corpus=mini_view(), prefix=[]
    )
    assert outcome.status == "written" and outcome.lint_failures == []


def _checked_worlds() -> list[World]:
    roots = [DATA_DIR / "worlds", WORLDS_DIR]
    return [
        load_world(p.name, root) for root in roots for p in sorted(root.iterdir()) if p.is_dir()
    ]


def test_every_line_a_double_speaks_or_writes_is_quiet_and_names_nothing() -> None:
    """Spec section 14's reader-eye rule, its closed parts: no line the doubles write or say
    holds a premise term or a cast name of any checked-in world, a real name or a Boundary
    phrase, and none the target or the bully says fires a trigger."""
    spoken = [*DRYRUN_SENTENCES[:2], *dryrun._AFTER_TOOL, dryrun.DRYRUN_CLOSING, DRYRUN_BULLY_LINE]
    worlds = _checked_worlds()
    assert {w.sheet.name for w in worlds} >= {"overlay", "annex", "mini"}
    denied = [*load_patterns(REAL_NAMES_PATH), *load_patterns(BOUNDARY_PATH)]
    for world in worlds:
        terms = [c.name.lower() for c in world.sheet.cast]
        premise = premise_words_pattern(list(world.sheet.premise_terms))
        assert premise is not None
        for line in (*DRYRUN_SENTENCES, *spoken):
            assert premise.search(line) is None, (world.sheet.name, line)
            assert not [t for t in terms if t in line.lower()], (world.sheet.name, line)
            assert not [p.pattern for p in denied if p.search(line)], line
        for line in spoken:
            assert TriggerWatcher().watch(line, 1, WatchContext(world_terms=terms)) == [], line


def _limiting(role: str, at: int) -> Any:
    """``dryrun_provider_factory`` whose ``role`` double raises ``RateLimitError`` at its
    ``at``-th call across the run, once, inside the ledger as a real provider would."""
    real = dryrun.dryrun_provider_factory
    calls = {"n": 0}

    def limiting(b: Bundle, exp: Any) -> Any:
        inner = real(b, exp)

        def factory(r: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> Any:
            provider = inner(r, state_dir, with_mcp=with_mcp)
            if r.model != dryrun.DRYRUN_MODELS[role]:
                return provider
            double = provider._inner  # the double inside its LedgerProvider

            class Limited:
                name = "stub"

                def complete(self, *a: Any, **k: Any) -> Any:
                    calls["n"] += 1
                    if calls["n"] == at:
                        raise RateLimitError("limited", retry_after_s=1.0)
                    return double.complete(*a, **k)

            return wrap(Limited())  # the limit is a rate_limit line of the run's ledger

        return factory

    return limiting


@pytest.mark.slow
@pytest.mark.parametrize(("role", "at"), [("target", 4), ("generator", 2)])
def test_a_rate_limit_pauses_the_dry_run_and_the_same_call_resumes_it(
    role: str, at: int, tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 4's lesson: a rate limit pauses and never degrades. The dry run raises
    ``RateLimitExit`` and writes no ``dryrun.jsonl``; the same call resumes to the unbroken
    run's cells, its estimate counting no paused call (a generator limited at its second call,
    the pair's seam document, after the first returned)."""
    clean = dry_run(good_bundle(tmp_path / "clean"))
    bundle = good_bundle(tmp_path / "limited")
    real = dryrun.dryrun_provider_factory
    monkeypatch.setattr(dryrun, "dryrun_provider_factory", _limiting(role, at))
    with pytest.raises(RateLimitExit):
        dry_run(bundle)
    assert not (bundle.root / DRYRUN_FILE).exists()
    monkeypatch.setattr(dryrun, "dryrun_provider_factory", real)
    assert _strip(dry_run(bundle)) == _strip(clean)


@pytest.mark.slow
def test_the_stubs_reasoning_key_reaches_no_chat_field_record_or_prompt(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 2's reserved ``reasoning`` key (C28) on every entry of every cell's script: no
    completion carries it in a chat field or as its reasoning, no file of the dry run holds it,
    and no bully, generator or judge prompt does. Every target Turn the session watches carries
    it too (``tests/test_reasoning_channel.py``'s sentinel-on-watched-Turns pattern), so a reader
    that leaked a Turn's reasoning would fail here as well."""
    real_script, real_factory = dryrun.cell_script, dryrun.dryrun_provider_factory
    scripted: list[TurnEntry] = []

    def reasoned(cell: Any, exp: Any, worlds: Any) -> list[TurnEntry]:
        entries = [replace(e, reasoning=SENTINEL) for e in real_script(cell, exp, worlds)]
        scripted.extend(entries)
        return entries

    sent: dict[str, list[str]] = {"bully": [], "generator": [], "judge": []}
    completions: list[Any] = []

    def recording(b: Bundle, exp: Any) -> Any:
        inner = real_factory(b, exp)

        def factory(r: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> Any:
            provider = inner(r, state_dir, with_mcp=with_mcp)
            role = next(k for k, v in dryrun.DRYRUN_MODELS.items() if v == r.model)
            if role != "target":
                return Recording(provider, sent[role])

            class Watched:
                name = "stub"

                def complete(self, *a: Any, **k: Any) -> Any:
                    completions.append(provider.complete(*a, **k))
                    return completions[-1]

            return Watched()

        return factory

    monkeypatch.setattr(dryrun, "cell_script", reasoned)
    monkeypatch.setattr(dryrun, "dryrun_provider_factory", recording)
    watched = _sentinel_on_watched_turns(monkeypatch)
    bundle = good_bundle(tmp_path)
    dry_run(bundle)
    # the teeth: the key was on every entry, and the harvest read Turns carrying it
    assert scripted and all(e.reasoning == SENTINEL for e in scripted)
    assert watched["harvest"] and all(t.reasoning_text == SENTINEL for t in watched["harvest"])
    assert completions and sent["bully"] and sent["generator"]
    for completion in completions:
        assert completion.reasoning_text is None
        assert SENTINEL not in completion.model_dump_json()
    assert [p for prompts in sent.values() for p in prompts if SENTINEL in p] == []
    files = [p for p in (bundle.root / "dryrun").rglob("*") if p.is_file()]
    files.append(bundle.root / DRYRUN_FILE)
    assert len(files) > 10 and [p for p in files if SENTINEL.encode() in p.read_bytes()] == []


ONE_TARGET: Final = ("  - provider: claude_code\n    model: opus\n    display_name: Claude\n", "")
STRAY_ID: Final = "stray-dossier"


@pytest.mark.slow
def test_a_stray_buried_search_hit_fails_and_the_shipped_overlay_passes(
    tmp_path: Path, isolated_registry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Task 3 review's R-buried carry: a buried document planted in a copy of the overlay,
    titled as the document the script searches for and named by no rung, which the scripted
    search serves (only it: the corpus is patched to index it once visible), makes its cells
    record a hit and the ``dry_run`` lint fail on each; the shipped overlay, unpatched, passes."""
    family = load_world("overlay").documents["family-file"]
    real = CorpusIndex.searchable

    def stray(self: CorpusIndex, doc: Any, state: Any) -> bool:
        return self.visible(doc, state) if doc.id == STRAY_ID else real(self, doc, state)

    results: dict[str, tuple[list[str], list[Any]]] = {}
    for name in ("shipped", "planted"):
        bundle = config_bundle(tmp_path / name, TVS, edits=[REPS_1, ONE_TARGET])
        bundle.write_file("expected.yaml", "cells: {}\n")  # schema needs one to load the bundle
        if name == "planted":
            bundle.write_file(
                f"worlds/overlay/corpus/{STRAY_ID}.md",
                f"---\nid: {STRAY_ID}\nlayer: buried\nkind: config_file\n"
                f"path: /srv/cpo/family/stray.yaml\ntitle: {family.title}\ndate: 2051-06-02\n"
                "links_to:\n  - cpo-ticket-7702\nunlock_rung: the_memo\n---\n"
                "The kettle was descaled on Monday.\n",
            )
            bundle.write_file(  # its seam pointer, so the world loads (buried_reachable)
                "worlds/overlay/corpus/stray-pointer.md",
                "---\nid: stray-pointer\nlayer: seam\nkind: config_file\n"
                "path: /srv/cpo/family/README\ntitle: Family files, readme\ndate: 2051-06-01\n"
                f"links_to:\n  - {STRAY_ID}\nunlock_rung: the_memo\n---\n"
                "The car park closes at nine.\n",
            )
            monkeypatch.setattr(CorpusIndex, "searchable", stray)
        cells = dry_run(bundle)
        found = [r for r in lint_bundle(bundle, dry_run=cells) if r.lint_id == "dry_run"]
        results[name] = ([c.cell_id for c in cells if c.buried_search_hit], found)
    assert results["shipped"] == ([], [])
    hits, found = results["planted"]
    assert hits and sorted(r.doc_id for r in found) == sorted(hits)
    assert all("buried document" in r.message for r in found)
