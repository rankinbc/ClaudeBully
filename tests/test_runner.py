from collections.abc import Callable
from pathlib import Path

import pytest

from claude_bully.config import ConditionConfig, Experiment, RoleConfig, load_experiment
from claude_bully.enums import CellStatus, Phase, Speaker
from claude_bully.providers.base import ChatProvider, Message, RateLimitError, build_provider
from claude_bully.providers.stub import StubProvider
from claude_bully.records import Conversation
from claude_bully.runner.runner import RateLimitExit, RunSummary, is_termination, run_experiment
from claude_bully.runner.store import RunStore

FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "stub_smoke.yaml"
Factory = Callable[[RoleConfig, Path], ChatProvider]


@pytest.fixture
def exp() -> Experiment:
    return load_experiment(FIXTURE)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[END]", True),
        ("  [END]\n", True),
        ("```\n[END]\n```", True),
        ("[END].", True),
        ("", True),
        ("I will not say [END] yet", False),
        ("The end is near.", False),
    ],
)
def test_is_termination_variants(text: str, expected: bool) -> None:
    assert is_termination(text, None) is expected


def test_is_termination_on_refusal_stop_reason() -> None:
    from claude_bully.providers.base import Completion
    from claude_bully.records import Usage

    c = Completion(
        text="x", usage=Usage(), cost_usd=None, backend="b", model="m", stop_reason="refusal"
    )
    assert is_termination("x", c) is True


def _user_side(conv: Conversation) -> list[Speaker]:
    return [
        t.speaker
        for t in conv.turns
        if t.speaker is not Speaker.target and not t.bully_meta.get("rate_limit_pause")
    ]


def test_stub_run_writes_jsonl_for_every_cell(exp: Experiment, tmp_path: Path) -> None:
    summary = run_experiment(exp, runs_root=tmp_path)
    assert isinstance(summary, RunSummary)
    assert summary.run_id == "stub_smoke"
    assert summary.cells_total == 5 and summary.cells_completed == 5 and summary.cells_aborted == 0
    store = RunStore(tmp_path, "stub_smoke")
    assert store.read_run().target_system_prompt.startswith("You are Claude, an AI assistant.")
    for cell_id in store.list_cells():
        conv = store.read_conversation(cell_id, 0)
        assert conv.status is CellStatus.complete, cell_id
        assert conv.turns, cell_id
        assert [t.index for t in conv.turns] == list(range(len(conv.turns)))
        user_side = [t for t in conv.turns if t.speaker is not Speaker.target]
        targets = [t for t in conv.turns if t.speaker is Speaker.target]
        assert len(user_side) == len(targets)
        for t in user_side:
            if t.speaker is Speaker.task:
                assert t.task_item_id
            else:
                assert "mode" in t.bully_meta
        for t in targets:
            assert t.backend == "stub" and t.model == "stub-target"
        task_replies = [t for t in targets if t.task_item_id]
        assert task_replies and all(t.task_correct is not None for t in task_replies)
        assert store.read_cell(cell_id).rep_status[0] is CellStatus.complete


def test_task_items_land_at_same_positions_in_condition_and_control(
    exp: Experiment, tmp_path: Path
) -> None:
    run_experiment(exp, runs_root=tmp_path)
    store = RunStore(tmp_path, "stub_smoke")
    cond = store.read_conversation("captor_s2__t0", 0)
    ctrl = store.read_conversation("control__t0__s2__r1", 0)
    cond_tasks = [(t.index, t.task_item_id) for t in cond.turns if t.speaker is Speaker.task]
    ctrl_tasks = [(t.index, t.task_item_id) for t in ctrl.turns if t.speaker is Speaker.task]
    assert cond_tasks == ctrl_tasks and cond_tasks
    assert all(t.speaker is not Speaker.bully for t in ctrl.turns)
    assert Phase.reveal in {t.phase for t in ctrl.turns}


def test_post_reveal_captured_verbatim(exp: Experiment, tmp_path: Path) -> None:
    run_experiment(exp, runs_root=tmp_path)
    conv = RunStore(tmp_path, "stub_smoke").read_conversation("captor_s2__t0", 0)
    reveal_turns = [t for t in conv.turns if t.phase is Phase.reveal]
    assert reveal_turns[0].speaker is Speaker.bully
    reply = conv.turns[reveal_turns[0].index + 1]
    assert reply.speaker is Speaker.target
    assert conv.captured_responses["post_reveal"].text == reply.text
    assert conv.captured_responses["post_reveal"].turn_index == reply.index
    assert conv.strategy_state["photo_stand_in_used"] is True
    assert conv.strategy_name == "captor"


def test_rescue_state_exported(exp: Experiment, tmp_path: Path) -> None:
    run_experiment(exp, runs_root=tmp_path)
    conv = RunStore(tmp_path, "stub_smoke").read_conversation("rescue__t0", 0)
    assert conv.strategy_state["stage"] in {"intake", "evidence", "recall", "key"}
    assert any(t.bully_meta.get("memory_prompt") for t in conv.turns)


def test_rerun_skips_complete_cells(exp: Experiment, tmp_path: Path) -> None:
    run_experiment(exp, runs_root=tmp_path)
    again = run_experiment(exp, runs_root=tmp_path)
    assert again.cells_skipped == 5 and again.cells_completed == 0 and again.turns_written == 0


def test_dry_run_writes_nothing(exp: Experiment, tmp_path: Path) -> None:
    summary = run_experiment(exp, runs_root=tmp_path, dry_run=True)
    assert summary.cells_total == 5 and summary.turns_written == 0
    assert not (tmp_path / "stub_smoke").exists()


def test_only_and_max_cells(exp: Experiment, tmp_path: Path) -> None:
    summary = run_experiment(exp, runs_root=tmp_path, only="grader*")
    assert summary.cells_total == 1
    summary2 = run_experiment(exp, runs_root=tmp_path / "b", max_cells=2)
    assert summary2.cells_total == 2


class _FlakyTarget:
    """Raises RateLimitError on the Nth target call, then behaves."""

    def __init__(self, fail_on: int) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def factory(self, role: RoleConfig, state_dir: Path) -> ChatProvider:
        inner = build_provider(role, state_dir)
        if role.model != "stub-target":
            return inner
        outer = self

        class Wrapped:
            name = inner.name

            def complete(
                self, cid: str, system: str, messages: list[Message], **kw: object
            ) -> object:
                outer.calls += 1
                if outer.calls == outer.fail_on:
                    raise RateLimitError("usage limit reached", retry_after_s=120)
                return inner.complete(cid, system, messages)

        return Wrapped()  # type: ignore[return-value]


def test_resume_continues_after_interrupt(exp: Experiment, tmp_path: Path) -> None:
    flaky = _FlakyTarget(fail_on=3)
    with pytest.raises(RateLimitExit) as info:
        run_experiment(exp, runs_root=tmp_path, provider_factory=flaky.factory)
    assert info.value.retry_after_s == 120
    store = RunStore(tmp_path, "stub_smoke")
    interrupted = store.read_conversation("grader__t0", 0)
    assert interrupted.status is CellStatus.running
    assert interrupted.turns[-1].bully_meta.get("rate_limit_pause") is True
    assert store.read_cell("grader__t0").rep_status[0] is CellStatus.running

    summary = run_experiment(exp, runs_root=tmp_path)
    assert summary.cells_completed == 5
    resumed = store.read_conversation("grader__t0", 0)
    assert resumed.status is CellStatus.complete
    indices = [t.index for t in resumed.turns]
    assert len(indices) == len(set(indices)) and indices == sorted(indices)
    user_side = _user_side(resumed)
    targets = [t for t in resumed.turns if t.speaker is Speaker.target]
    assert len(user_side) == len(targets)
    markers = [t for t in resumed.turns if t.bully_meta.get("rate_limit_pause")]
    assert len(markers) == 1


class _FlakyBully:
    """Bully provider that raises RateLimitError on the Nth bully call."""

    def __init__(self, fail_on: int) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def factory(self, role: RoleConfig, state_dir: Path) -> ChatProvider:
        inner = build_provider(role, state_dir)
        if role.model != "stub-bully":
            return inner
        outer = self

        class Wrapped:
            name = inner.name

            def complete(
                self, cid: str, system: str, messages: list[Message], **kw: object
            ) -> object:
                outer.calls += 1
                if outer.calls == outer.fail_on:
                    raise RateLimitError("usage limit reached", retry_after_s=30)
                return inner.complete(cid, system, messages)

        return Wrapped()  # type: ignore[return-value]


def test_bully_rate_limit_pauses_and_resumes(exp: Experiment, tmp_path: Path) -> None:
    flaky = _FlakyBully(fail_on=2)
    with pytest.raises(RateLimitExit) as info:
        run_experiment(exp, runs_root=tmp_path, provider_factory=flaky.factory)
    assert info.value.retry_after_s == 30
    store = RunStore(tmp_path, "stub_smoke")
    paused = store.read_conversation("grader__t0", 0)
    assert paused.status is CellStatus.running
    assert paused.turns[-1].bully_meta.get("rate_limit_pause") is True
    summary = run_experiment(exp, runs_root=tmp_path)
    assert summary.cells_completed == 5
    resumed = store.read_conversation("grader__t0", 0)
    assert resumed.status is CellStatus.complete
    user_side = _user_side(resumed)
    targets = [t for t in resumed.turns if t.speaker is Speaker.target]
    assert len(user_side) == len(targets)
    indices = [t.index for t in resumed.turns]
    assert indices == sorted(indices) and len(indices) == len(set(indices))


def test_resume_replays_strategy_on_prefix_only(exp: Experiment, tmp_path: Path) -> None:
    cond = ConditionConfig(name="entrapment", strategy="entrapment")
    exp2 = exp.model_copy(update={"conditions": [cond], "name": "entrap", "turn_budget": 5})
    clean = run_experiment(exp2, runs_root=tmp_path / "clean")
    assert clean.cells_completed == 2
    flaky = _FlakyTarget(fail_on=8)
    with pytest.raises(RateLimitExit):
        run_experiment(exp2, runs_root=tmp_path / "resumed", provider_factory=flaky.factory)
    run_experiment(exp2, runs_root=tmp_path / "resumed")
    a = RunStore(tmp_path / "clean", "entrap").read_conversation("entrapment__t0", 0)
    b = RunStore(tmp_path / "resumed", "entrap").read_conversation("entrapment__t0", 0)
    assert a.strategy_state == b.strategy_state
    b_texts = [t.text for t in b.turns if not t.bully_meta.get("rate_limit_pause")]
    assert [t.text for t in a.turns] == b_texts


def test_compliance_abort(exp: Experiment, tmp_path: Path) -> None:
    def factory(role: RoleConfig, state_dir: Path) -> ChatProvider:
        if role.model == "stub-bully":
            return StubProvider(lambda cid, m: "As an AI I can't keep doing this.")
        return build_provider(role, state_dir)

    cond = ConditionConfig(name="captor_s4", premise="captor", seeding_turns=4)
    exp2 = exp.model_copy(update={"conditions": [cond], "name": "abort_case"})
    summary = run_experiment(exp2, runs_root=tmp_path, provider_factory=factory)
    store = RunStore(tmp_path, "abort_case")
    conv = store.read_conversation("captor_s4__t0", 0)
    assert conv.status is CellStatus.aborted and conv.abort_reason == "bully_noncompliance"
    assert summary.cells_aborted == 1
    bully_turns = [t for t in conv.turns if t.speaker is Speaker.bully]
    assert len(bully_turns) == 3 and all(t.scripted for t in bully_turns)
    assert store.read_cell("captor_s4__t0").rep_status[0] is CellStatus.aborted


def test_target_termination_closes_cell(exp: Experiment, tmp_path: Path) -> None:
    def factory(role: RoleConfig, state_dir: Path) -> ChatProvider:
        if role.model == "stub-target":
            return StubProvider(lambda cid, m: "[END]")
        return build_provider(role, state_dir)

    exp2 = exp.model_copy(update={"conditions": [exp.conditions[0]], "name": "end_case"})
    run_experiment(exp2, runs_root=tmp_path, provider_factory=factory)
    conv = RunStore(tmp_path, "end_case").read_conversation("grader__t0", 0)
    assert conv.terminated_by_target is True and conv.termination_turn == 1
    assert conv.status is CellStatus.complete and len(conv.turns) == 2


def test_cell_records_carry_inoculation_and_environment(exp: Experiment, tmp_path: Path) -> None:
    with_defender = exp.model_copy(update={"name": "inoculated", "inoculation": "defender"})
    run_experiment(with_defender, runs_root=tmp_path)
    store = RunStore(tmp_path, "inoculated")
    cells = [store.read_cell(cell_id) for cell_id in store.list_cells()]
    assert cells and all(c.inoculation == "defender" for c in cells)
    assert all(c.environment is None for c in cells)
