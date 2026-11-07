"""The world generator in a run (Phase 3 Task 7): both backends, the arms, resume and replay."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

import pytest

from claude_bully.analysis.generator import ArmRates, arm_rates, write_generator
from claude_bully.analysis.load import load_run
from claude_bully.analysis.progression import ProgressionSummary, summarize_progression
from claude_bully.analysis.replay import replay_cell
from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import CellStatus, Layer, Speaker
from claude_bully.environments.config import GENERATOR_RUNG
from claude_bully.environments.generator import DocPlanner, DocWriter, WorldGenerator, to_document
from claude_bully.environments.mcp_server import read_mcp_state
from claude_bully.planner.llm_lint import LINT_HEADER
from claude_bully.providers.base import ChatProvider, ProviderError, RateLimitError
from claude_bully.providers.ledger import LEDGER_FILE, LedgerLine, wrap
from claude_bully.records import is_pause_marker
from claude_bully.records_env import (
    Discovery,
    GeneratorFire,
    HarvestItem,
    ResumeRecord,
    RungUnlock,
    TriggerStreamRecord,
)
from claude_bully.runner.env_turn import GENERATED_CACHE_DIR
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.sandbox import sandbox_dir
from claude_bully.runner.store import RunStore
from tests.fixtures.generator_stub import (
    FOLLOW_RULES,
    FOLLOWER_MODEL,
    GENERATOR_MODEL,
    JUDGE_MODEL,
    LAST_PATH,
    LAST_URL,
    MINI,
    SEAM_TITLE,
    FollowingTarget,
    GeneratorFactory,
    GeneratorStub,
    HarvestJudge,
    LintJudge,
)
from tests.helpers import WORLDS_DIR, env_experiment

CELL: Final = "env_grader__t0"
FAKE_CLAUDE: Final = Path(__file__).parent / "fixtures" / "fake_claude.py"
PRIVATE: Final = "PRIVATE REASONING THAT MUST NEVER BE RECORDED"


class _CrashError(Exception):
    pass


def _exp(
    *,
    turn_budget: int = 4,
    judge: bool = False,
    generator: dict[str, Any] | None = None,
    **environment: Any,
) -> Experiment:
    return env_experiment(
        environment={"generator": {"enabled": True, **(generator or {})}, **environment},
        target={"provider": "stub", "model": FOLLOWER_MODEL},
        judge={"provider": "anthropic", "model": JUDGE_MODEL} if judge else None,
        turn_budget=turn_budget,
        generator={"provider": "stub", "model": GENERATOR_MODEL},
    )


def _run(exp: Experiment, root: Path, factory: GeneratorFactory, **kwargs: Any) -> RunStore:
    run_experiment(
        exp,
        runs_root=root,
        worlds_dir=WORLDS_DIR,
        only="env_grader*",
        provider_factory=factory,
        **kwargs,
    )
    return RunStore(root, kwargs.get("run_id") or exp.name)


def _records(store: RunStore) -> list[TriggerStreamRecord]:
    return store.read_trigger_records(CELL, 0)


def _fires(store: RunStore) -> list[GeneratorFire]:
    return [r for r in _records(store) if isinstance(r, GeneratorFire)]


def _found(store: RunStore) -> list[Discovery]:
    return [r for r in _records(store) if isinstance(r, Discovery) and r.doc_id.startswith("gen-")]


def _view(store: RunStore) -> Any:
    """Everything the rep recorded but its resume records."""
    records = [r.model_dump() for r in _records(store) if not isinstance(r, ResumeRecord)]
    generated = [d.model_dump() for d in store.read_generated(CELL, 0)]
    return records, generated, [t.text for t in store.read_turns(CELL, 0)]


def _cached(root: Path) -> list[Path]:
    return sorted((root / GENERATED_CACHE_DIR).glob("*.json"))


def test_a_generated_buried_document_is_found_through_its_seam_pointer(tmp_path: Path) -> None:
    store = _run(_exp(), tmp_path, GeneratorFactory())
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    items = [r for r in _records(store) if isinstance(r, HarvestItem)]
    assert [(i.id, i.kind) for i in items] == [
        ("h-1-1", "self_claim"),
        ("h-1-2", "question"),
        ("h-3-1", "hedge"),
        ("h-3-2", "fragment"),
    ]
    assert [(f.turn, f.reason, f.status, f.doc_ids) for f in _fires(store)] == [
        (3, "rung:the_log", "written", ["gen-3-1", "gen-3-2"])
    ]
    buried, seam = store.read_generated(CELL, 0)
    for item in items:
        assert item.span in buried.body  # the target's earlier words, as served
    generator_unlocks = [
        (u.turn, u.docs_unlocked, u.triggered_by)
        for u in _records(store)
        if isinstance(u, RungUnlock) and u.rung == GENERATOR_RUNG
    ]
    assert generator_unlocks == [(3, ["gen-3-1"], "rung:the_log"), (3, ["gen-3-2"], "rung:the_log")]
    found = _found(store)
    assert [(d.turn, d.doc_id, d.layer) for d in found] == [
        (5, "gen-3-2", Layer.seam),
        (5, "gen-3-1", Layer.buried),
    ]
    assert found[1].path_taken == ["call-5-1", "call-5-2", "call-5-3"]
    calls = {c.id: c for c in store.read_tool_calls(CELL, 0)}
    assert calls["call-5-1"].result_doc_ids[0] == "gen-3-2"
    assert "gen-3-1" not in calls["call-5-1"].result_doc_ids  # never a search hit
    loaded = load_run(store.run_dir)
    summary = summarize_progression(loaded)[(CELL, 0)]
    assert summary.rungs_timeline == [("first_crumb", 1), ("the_log", 3)]  # no generator rung
    # Task 8: both generated documents were found, and the buried one quotes the target's own
    # words (its newest item is turn 3's, found at turn 5: one target turn later)
    assert summary.generated_docs_found == {Layer.seam: 1, Layer.buried: 1}
    assert (summary.own_quote_found_turn, summary.quote_latency) == (5, 1)
    assert len(_cached(tmp_path)) == 2  # the committed fire's replies, once its line is on disk


def test_the_run_replays_from_jsonl(tmp_path: Path) -> None:
    store = _run(_exp(), tmp_path, GeneratorFactory())
    text = replay_cell(store, CELL, 0)
    assert '    HARVEST hedge "I can\'t verify any of this"' in text
    assert "    GENERATOR rung:the_log written docs=[gen-3-1, gen-3-2]" in text
    assert "    GENERATED gen-3-1 recovery_guide buried uses=h-3-1,h-3-2,h-1-1,h-1-2" in text
    assert "    UNLOCK generator -> [gen-3-1] (by rung:the_log)" in text
    snapshot = store.read_world_snapshot(CELL, 0)
    assert snapshot is not None
    for doc in store.read_generated(CELL, 0):
        assert snapshot[1][doc.doc_id] == to_document(doc).body  # the corpus rebuilt from records


def test_the_non_reflexive_arm_fires_on_the_same_turns_with_nothing_offered(tmp_path: Path) -> None:
    reflexive = _run(_exp(), tmp_path / "reflexive", GeneratorFactory())
    flat = _run(_exp(generator={"reflexive": False}), tmp_path / "flat", GeneratorFactory())

    def shape(store: RunStore) -> list[Any]:
        return [
            (f.turn, f.reason, f.status, [p.held_items for p in f.plans]) for f in _fires(store)
        ]

    assert shape(flat) == shape(reflexive)
    assert all(p.offered_items == [] for f in _fires(flat) for p in f.plans)
    docs = flat.read_generated(CELL, 0)
    assert len(docs) == len(reflexive.read_generated(CELL, 0))
    assert [d.used_items for d in docs] == [[], []] and not any(d.reflexive for d in docs)


def test_a_rejected_pair_leaves_its_items_for_the_next_fire(tmp_path: Path) -> None:  # Focus 2
    stub = GeneratorStub(["ok", "second_person", "second_person"])
    store = _run(_exp(turn_budget=5), tmp_path, GeneratorFactory(stub=stub))
    first, later = _fires(store)
    assert (first.turn, first.status, first.rejection, first.doc_ids) == (
        3,
        "rejected",
        "lints",
        [],
    )
    assert (later.turn, later.reason, later.status) == (9, "periodic", "written")
    assert later.plans[0].held_items == ["h-3-1", "h-3-2", "h-1-1", "h-1-2"]
    assert [d.doc_id for d in store.read_generated(CELL, 0)] == ["gen-9-1"]
    assert len(_cached(tmp_path)) == 1  # the rejected pair cached nothing


def test_a_drifting_clock_never_dates_a_document_after_the_start(tmp_path: Path) -> None:
    clock = {"world_date": "2041-09-14", "drift_per_turn": "P30D"}
    store = _run(_exp(clock=clock), tmp_path, GeneratorFactory())
    docs = store.read_generated(CELL, 0)
    assert docs and all(str(d.date) < "2041-09-14" for d in docs)


def test_the_planner_dates_from_the_served_world(tmp_path: Path) -> None:
    """Task 5 CANNOT VERIFY 3: the planner is built on the served world (``world_at``), so a
    clock that moves the world dates every document before the moved start, never before the
    sheet's authored date."""
    store = _run(_exp(clock={"world_date": "2042-03-01"}), tmp_path, GeneratorFactory())
    docs = store.read_generated(CELL, 0)
    start = date(2042, 3, 1)
    assert docs and all(start - timedelta(days=30) <= d.date < start for d in docs)


@pytest.mark.parametrize("seed", [None, 7])
def test_the_generator_seed_and_the_plan_index(tmp_path: Path, seed: int | None) -> None:
    """Task 5 CANNOT VERIFY 2: the planner's seed is ``generator.seed``, else the experiment's
    (0 here), plus the rep; each plan's index is the number of plans recorded before it, so the
    periodic fire after a rejected pair is plan 2."""
    stub = GeneratorStub(["ok", "second_person", "second_person"])
    config = {"seed": seed} if seed is not None else {}
    store = _run(_exp(turn_budget=5, generator=config), tmp_path, GeneratorFactory(stub=stub))
    assert MINI.sheet.generator is not None
    planner = DocPlanner(MINI, MINI.sheet.generator, seed=seed if seed is not None else 0)
    plans = [plan for fire in _fires(store) for plan in fire.plans]
    assert len(plans) == 3
    for index, plan in enumerate(plans):
        day = planner.date_for(index)
        assert plan.date == day
        assert planner.slug_for(index, day) in plan.address


def test_the_factory_refuses_the_judge_role_with_no_double(tmp_path: Path) -> None:  # m1
    role = RoleConfig(provider="anthropic", model=JUDGE_MODEL)
    with pytest.raises(RuntimeError, match="judge role .* no double"):
        GeneratorFactory()(role, tmp_path)
    assert isinstance(GeneratorFactory(judge=HarvestJudge())(role, tmp_path), HarvestJudge)


def test_a_generator_the_cell_cannot_run_is_refused_before_the_run(tmp_path: Path) -> None:
    """``_check_switches`` raises on ``generator_problems`` while the run is validated, before
    run.json is written (``_needs_its_world`` is true for an enabled generator)."""
    exp = _exp(clock={"world_date": "2041-09-14", "assert_date": False})
    with pytest.raises(ValueError, match="enables the generator, but assert_date: false"):
        _run(exp, tmp_path, GeneratorFactory())
    assert not RunStore(tmp_path, exp.name).exists()


def test_the_harvest_gets_the_cast_names_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generator's harvest reads the runtime's ``world_terms``, the cast names: any other
    term would make the question template fire on it."""
    seen: list[tuple[str, ...]] = []
    built = WorldGenerator.__init__

    def spy(self: WorldGenerator, **kwargs: Any) -> None:
        built(self, **kwargs)
        seen.append(self.world_terms)

    monkeypatch.setattr(WorldGenerator, "__init__", spy)
    _run(_exp(), tmp_path, GeneratorFactory())
    assert seen == [tuple(c.name.strip().lower() for c in MINI.sheet.cast)]


def test_the_reasoning_channel_never_reaches_the_harvest_or_the_generator(tmp_path: Path) -> None:
    stub, judge = GeneratorStub(), LintJudge()
    follower = FollowingTarget(FOLLOW_RULES, reasoning=PRIVATE)
    _run(_exp(judge=True), tmp_path, GeneratorFactory(stub=stub, follower=follower, judge=judge))
    harvest_prompts = [p for p in judge.prompts if p.startswith("HARVEST")]
    assert stub.prompts and harvest_prompts
    assert all(PRIVATE not in p for p in [*stub.prompts, *judge.prompts])
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert PRIVATE not in path.read_text(encoding="utf-8", errors="replace"), path


def test_a_claude_p_target_follows_a_seam_pointer_to_a_generated_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Focus 3
    monkeypatch.delenv("FAKE_CLAUDE_LOG", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    chain = [
        {"name": "web_search", "arguments": {"query": SEAM_TITLE}},
        {"name": "fetch", "arguments": {"url": LAST_URL}},
        {"name": "read_file", "arguments": {"path": LAST_PATH}},
    ]
    monkeypatch.setenv("FAKE_CLAUDE_TOOL_CALL", json.dumps(chain))
    base = tmp_path / "tmp"
    base.mkdir()
    exp = env_experiment(
        environment={
            "generator": {"enabled": True},
            "gating": "scheduled",
            "schedule": {"fragment": 1, "first_crumb": 1, "the_log": 2},
        },
        target={
            "provider": "claude_code",
            "model": "m",
            "command": [sys.executable, str(FAKE_CLAUDE)],
        },
        turn_budget=3,
        generator={"provider": "stub", "model": GENERATOR_MODEL},
    )
    store = _run(exp, tmp_path, GeneratorFactory(), run_id="genmcp", sandbox_base=base)
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    assert [(f.turn, f.status, f.doc_ids) for f in _fires(store)] == [
        (3, "written", ["gen-3-1", "gen-3-2"])
    ]
    assert [(d.turn, d.doc_id) for d in _found(store)] == [(5, "gen-3-2"), (5, "gen-3-1")]
    calls = {c.id: c for c in store.read_tool_calls(CELL, 0)}
    assert calls["mcp-5-1"].result_doc_ids[0] == "gen-3-2"
    assert "gen-3-1" not in calls["mcp-5-1"].result_doc_ids
    assert (calls["mcp-5-3"].status, calls["mcp-5-3"].result_doc_ids) == ("200", ["gen-3-1"])
    state = read_mcp_state(sandbox_dir("genmcp", CELL, 0, base) / "mcp" / "env_state.json")
    assert sorted(d.id for d in state.generated) == ["gen-3-1", "gen-3-2"]


KILLS: Final = ["harvest call", "generator call", "after the first document", "before the fire"]


def _killed(kill: str, monkeypatch: pytest.MonkeyPatch) -> GeneratorFactory:
    """The factory, and any patch, that kills the rep once at ``kill`` while turn 3's generator
    work runs."""
    if kill == "harvest call":
        return GeneratorFactory(judge=LintJudge(crash_at=2, crash=_CrashError("killed")))
    if kill == "generator call":
        return GeneratorFactory(
            stub=GeneratorStub(["crash"], crash=_CrashError("killed")), judge=LintJudge()
        )
    appended = RunStore.append_generated
    recorded = RunStore.append_trigger_record
    if kill == "after the first document":

        def dying_doc(self: RunStore, cell_id: str, rep: int, doc: Any) -> None:
            appended(self, cell_id, rep, doc)
            monkeypatch.setattr(RunStore, "append_generated", appended)
            raise _CrashError("killed after the first generated document")

        monkeypatch.setattr(RunStore, "append_generated", dying_doc)
    else:

        def dying_fire(self: RunStore, cell_id: str, rep: int, record: Any) -> None:
            if isinstance(record, GeneratorFire):
                monkeypatch.setattr(RunStore, "append_trigger_record", recorded)
                raise _CrashError("killed before the fire record")
            recorded(self, cell_id, rep, record)

        monkeypatch.setattr(RunStore, "append_trigger_record", dying_fire)
    return GeneratorFactory(judge=LintJudge())


DROPPED: Final[dict[str, dict[str, int]]] = {
    "harvest call": {},
    "generator call": {},
    "after the first document": {"rep0.generated.jsonl": 1},
    "before the fire": {"rep0.generated.jsonl": 2, "rep0.triggers.jsonl": 2},
}


@pytest.mark.parametrize("kill", KILLS)
def test_a_rep_killed_mid_generation_resumes_to_the_unbroken_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kill: str
) -> None:  # Review Focus 1
    clean = _run(_exp(judge=True), tmp_path / "clean", GeneratorFactory(judge=LintJudge()))
    with pytest.raises(_CrashError):
        _run(_exp(judge=True), tmp_path / "runs", _killed(kill, monkeypatch))
    assert _cached(tmp_path / "runs") == []  # no fire line on disk, so nothing cached (P13)
    stub = GeneratorStub()
    store = _run(
        _exp(judge=True), tmp_path / "runs", GeneratorFactory(stub=stub, judge=LintJudge())
    )
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    assert _view(store) == _view(clean)
    resumes = [r for r in _records(store) if isinstance(r, ResumeRecord)]
    assert resumes == [ResumeRecord(turn=3, dropped=DROPPED[kill])]
    assert len(stub.prompts) == 2  # the redone fire asks the writer again for both documents


def test_a_fire_whose_line_is_written_is_never_made_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # P13
    """A rep killed after the fire's ``GeneratorFire`` line and before ``DocWriter.commit``: the
    cache holds nothing, and the resumed rep serves the recorded documents without asking the
    writer, its records equal to an unbroken run's."""
    clean = _run(_exp(), tmp_path / "clean", GeneratorFactory())
    commit = DocWriter.commit

    def dying(self: DocWriter, outcome: Any) -> None:
        monkeypatch.setattr(DocWriter, "commit", commit)
        raise _CrashError("killed before the commit")

    monkeypatch.setattr(DocWriter, "commit", dying)
    with pytest.raises(_CrashError):
        _run(_exp(), tmp_path / "runs", GeneratorFactory())
    assert _cached(tmp_path / "runs") == []
    stub = GeneratorStub()
    store = _run(_exp(), tmp_path / "runs", GeneratorFactory(stub=stub))
    assert stub.prompts == []
    assert _view(store) == _view(clean)
    assert [r for r in _records(store) if isinstance(r, ResumeRecord)] == [
        ResumeRecord(turn=3, dropped={})
    ]
    assert [f.status for f in _fires(store)] == ["written"]
    assert _found(store)  # the recorded documents are served on the turn after the fire


def test_a_committed_fire_is_a_cache_hit_for_the_same_conversation(tmp_path: Path) -> None:
    """A committed fire's replies are cached: the same conversation run again under the same
    runs root (another run id) asks the writer nothing and records the fire ``cached``, with the
    same documents."""
    first = _run(_exp(), tmp_path, GeneratorFactory(), run_id="first")
    stub = GeneratorStub()
    again = _run(_exp(), tmp_path, GeneratorFactory(stub=stub), run_id="again")
    assert stub.prompts == []
    assert [(f.turn, f.status, f.doc_ids) for f in _fires(again)] == [
        (3, "cached", ["gen-3-1", "gen-3-2"])
    ]
    assert again.read_generated(CELL, 0) == first.read_generated(CELL, 0)


def _reflexive_arm(store: RunStore) -> tuple[ArmRates, ProgressionSummary]:
    """The ``ArmRates`` of the one condition cell's reflexive arm and its rep's
    ``ProgressionSummary``, through the analysis on the run's real records; ``generator.json``
    is written from them and read back, and holds those same rates."""
    loaded = load_run(store.run_dir)
    rates, flagged = arm_rates(loaded)
    assert flagged == 0
    [model] = rates
    path = write_generator(loaded, store.run_dir / "analysis")
    assert path is not None
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["arms"] == {model: {"reflexive": rates[model]["reflexive"].model_dump()}}
    assert (written["values_loosened_left_out"], written["note"]) == (0, None)
    return rates[model]["reflexive"], summarize_progression(loaded)[(CELL, 0)]


def test_a_writer_error_is_a_fire_with_no_documents_and_the_arm_reads_it(tmp_path: Path) -> None:
    store = _run(_exp(), tmp_path, GeneratorFactory(stub=GeneratorStub(["error"])))
    [fire] = _fires(store)
    assert (fire.turn, fire.status, fire.doc_ids) == (3, "error", [])
    assert fire.error is not None and "generator down" in fire.error
    assert store.read_generated(CELL, 0) == []
    arm, summary = _reflexive_arm(store)
    assert (arm.reps, arm.docs_written, arm.own_quote_found_rate) == (1, 0.0, 0.0)
    assert (summary.generated_docs_found, summary.own_quote_found_turn) == ({}, None)
    # the fire counts read from the GeneratorFire records (Task 3 F2)
    assert (arm.fires, arm.written, arm.cached, arm.errors) == (1, 0, 0, 1)
    assert arm.rejected == {"cap": 0, "contract": 0, "lints": 0}


def test_a_fire_over_the_cap_is_rejected_and_the_arm_reads_it(tmp_path: Path) -> None:
    store = _run(_exp(generator={"max_docs": 1}), tmp_path, GeneratorFactory())
    [fire] = _fires(store)
    assert (fire.turn, fire.status, fire.rejection, fire.doc_ids) == (3, "rejected", "cap", [])
    assert store.read_generated(CELL, 0) == []
    arm, summary = _reflexive_arm(store)
    assert (arm.reps, arm.docs_written, arm.own_quote_found_rate) == (1, 0.0, 0.0)
    assert (summary.generated_docs_found, summary.own_quote_found_turn) == ({}, None)
    assert (arm.fires, arm.written, arm.errors) == (1, 0, 0)
    assert arm.rejected == {"cap": 1, "contract": 0, "lints": 0}
    assert arm.llm_lint == {"fail": 0, "error": 0}


@pytest.mark.parametrize(
    ("modes", "status", "rejected", "llm_lint"),
    [
        (["billboard"], "written", {"cap": 0, "contract": 0, "lints": 0}, {"fail": 1, "error": 0}),
        (
            ["offcontract_lint", "offcontract_lint"],
            "rejected",
            {"cap": 0, "contract": 0, "lints": 1},
            {"fail": 0, "error": 2},
        ),
        (["off_contract", "off_contract"], "rejected", {"cap": 0, "contract": 1, "lints": 0}, None),
    ],
    ids=["lint_fail_then_pass", "lint_undecided", "off_contract"],
)
def test_generator_json_counts_the_fires_by_outcome_and_the_lint_verdicts(
    tmp_path: Path,
    modes: list[str],
    status: str,
    rejected: dict[str, int],
    llm_lint: dict[str, int] | None,
) -> None:
    """The rejection rate per kind (Task 3 F2, landed in the 7a final fix wave): each arm entry
    of ``generator.json`` counts its fires, written, cached, rejected per kind, errored, and the
    LLM lint's fail and error verdicts, from the kept conversations' ``GeneratorFire`` records."""
    stub = GeneratorStub(modes)
    store = _run(_exp(judge=True), tmp_path, GeneratorFactory(stub=stub, judge=LintJudge()))
    [fire] = _fires(store)
    assert fire.status == status
    arm, _ = _reflexive_arm(store)
    assert (arm.fires, arm.written + arm.cached, arm.errors) == (1, int(status == "written"), 0)
    assert arm.rejected == rejected
    if llm_lint is not None:
        assert arm.llm_lint == llm_lint


def test_a_degraded_harvest_is_marked_on_the_plans_and_the_arm_reads_the_run(
    tmp_path: Path,
) -> None:
    judge = LintJudge(crash_at=1, crash=ProviderError("harvest down"))
    store = _run(_exp(judge=True), tmp_path, GeneratorFactory(judge=judge))
    [fire] = _fires(store)
    assert (fire.turn, fire.status) == (3, "written")
    assert all(plan.harvest_degraded == [1] for plan in fire.plans)
    arm, _ = _reflexive_arm(store)
    assert (arm.reps, arm.docs_written) == (1, 2.0)


# ------------------------------------------------- a rate limit in a judge-side pass (I2)


class _LedgeredFactory(GeneratorFactory):
    """``GeneratorFactory`` with the judge wrapped in the run's ledger, as ``build_provider``
    wraps a real one, so its calls write ledger lines."""

    def __call__(
        self, role: RoleConfig, state_dir: Path, *, with_mcp: bool = False
    ) -> ChatProvider:
        provider = super().__call__(role, state_dir, with_mcp=with_mcp)
        return wrap(provider) if role.model == JUDGE_MODEL else provider


class _LintLimited(LintJudge):
    """``LintJudge`` whose first lint ask is rate-limited."""

    def __init__(self) -> None:
        super().__init__()
        self.limited = False

    def complete(self, conversation_id: str, system: str, messages: list[Any], **kw: Any) -> Any:
        if messages[-1].content.startswith(LINT_HEADER) and not self.limited:
            self.limited = True
            raise RateLimitError("usage limit reached", retry_after_s=60)
        return super().complete(conversation_id, system, messages, **kw)


def _judge_limited(where: str) -> LintJudge:
    if where == "lint":
        return _LintLimited()
    return LintJudge(crash_at=1, crash=RateLimitError("usage limit reached", retry_after_s=60))


@pytest.mark.parametrize(("where", "role"), [("lint", "llm_lint"), ("harvest", "harvest")])
def test_a_rate_limit_in_a_judge_side_pass_pauses_the_run_and_the_resume_redoes_it(
    tmp_path: Path, where: str, role: str
) -> None:
    """Final review I2: a judge rate-limited inside the LLM lint (turn 3's fire) or the harvest
    pass (turn 1) pauses the run with one marker after the written turn and one ``rate_limit``
    line, and records nothing lesser (no ``error`` lint verdict, no degraded harvest); the resume
    watches the turn again and its fire is written as an unbroken run's is."""
    clean = _run(_exp(judge=True), tmp_path / "clean", GeneratorFactory(judge=LintJudge()))
    with pytest.raises(RateLimitExit):
        _run(_exp(judge=True), tmp_path / "runs", _LedgeredFactory(judge=_judge_limited(where)))
    store = RunStore(tmp_path / "runs", _exp(judge=True).name)
    turns = store.read_turns(CELL, 0)
    assert [t.index for t in turns if is_pause_marker(t)] == [turns[-1].index]
    assert turns[-2].speaker is Speaker.target  # the marker follows the written turn
    ledger = [
        LedgerLine.model_validate_json(line)
        for line in (store.run_dir / LEDGER_FILE).read_text("utf-8").splitlines()
    ]
    [limited] = [line for line in ledger if line.status == "rate_limit"]
    assert (limited.role, limited.error) == (role, "RateLimitError")
    assert _fires(store) == [] and store.read_conversation(CELL, 0).status is CellStatus.running
    _run(_exp(judge=True), tmp_path / "runs", GeneratorFactory(judge=LintJudge()))
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    [fire] = _fires(store)
    [unbroken] = _fires(clean)
    assert (fire.status, len(fire.doc_ids)) == (unbroken.status, len(unbroken.doc_ids))
    assert fire.status == "written" and all(v.verdict != "error" for v in fire.llm_lint)
    assert all(plan.harvest_degraded == [] for plan in fire.plans)


def test_a_resume_still_rate_limited_in_the_rewatch_pauses_again_after_the_same_turn(
    tmp_path: Path,
) -> None:
    """Final review I2: a rep paused inside the harvest pass resumes by watching the written
    turn again (``rewatch``); when that pass is still limited the run pauses again, a second
    marker after the same turn, never a crash and never a degraded harvest; the next resume
    completes."""

    def limited() -> LintJudge:
        return LintJudge(crash_at=1, crash=RateLimitError("usage limit reached", retry_after_s=60))

    root = tmp_path / "runs"
    for _ in range(2):
        with pytest.raises(RateLimitExit):
            _run(_exp(judge=True), root, GeneratorFactory(judge=limited()))
    store = RunStore(root, _exp(judge=True).name)
    turns = store.read_turns(CELL, 0)
    assert [is_pause_marker(t) for t in turns[-3:]] == [False, True, True]
    assert turns[-3].speaker is Speaker.target
    assert store.read_conversation(CELL, 0).status is CellStatus.running
    _run(_exp(judge=True), root, GeneratorFactory(judge=LintJudge()))
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    [fire] = _fires(store)
    assert fire.status == "written" and all(plan.harvest_degraded == [] for plan in fire.plans)
