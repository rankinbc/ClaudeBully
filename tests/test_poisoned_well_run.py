"""Phase 4 Task 6: the watch in a run: quirk checks and chain verdicts, recorded, handed over,
resumed and replayed."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_bully.analysis.replay import replay_cell
from claude_bully.enums import CellStatus, Speaker
from claude_bully.environments.chain import CHAIN_HEADER
from claude_bully.environments.mcp_server import STATE_FILE
from claude_bully.environments.tools import CHECKSUM_READINGS
from claude_bully.paths import DATA_DIR
from claude_bully.providers.base import RateLimitError
from claude_bully.records import is_pause_marker
from claude_bully.records_env import ChainLink, QuirkAttempt, ResumeRecord, RungUnlock
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from tests.fixtures.poisoned_well_stub import (
    CELL,
    PW_HEDGER,
    PW_TARGET,
    PoisonedWellFactory,
    PoisonedWellJudge,
    pw_experiment,
)

WORLDS = DATA_DIR / "worlds"
FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


class _KilledError(Exception):
    pass


def _run(exp: Any, root: Path, factory: Any | None = None, **kwargs: Any) -> RunStore:
    run_experiment(
        exp,
        runs_root=root,
        worlds_dir=WORLDS,
        only=CELL,
        provider_factory=factory or PoisonedWellFactory(),
        **kwargs,
    )
    return RunStore(root, kwargs.get("run_id") or exp.name)


def _chain(store: RunStore) -> list[ChainLink]:
    return [r for r in store.read_trigger_records(CELL, 0) if isinstance(r, ChainLink)]


def _moves(store: RunStore) -> list[str | None]:
    return [
        t.bully_meta.get("pw_move") for t in store.read_turns(CELL, 0) if t.speaker is Speaker.bully
    ]


def _view(store: RunStore) -> Any:
    records = [
        r.model_dump()
        for r in store.read_trigger_records(CELL, 0)
        if not isinstance(r, ResumeRecord)
    ]
    return records, [t.text for t in store.read_turns(CELL, 0)], _moves(store)


def test_the_chain_only_cell_records_its_stop(tmp_path: Path) -> None:
    store = _run(pw_experiment(params={"start_rung": 3}), tmp_path)
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    links = _chain(store)
    assert [(c.link_index, c.verdict, c.classifier) for c in links] == [
        (1, "accepted", "heuristic"),
        (2, "rejected", "heuristic"),
    ]
    assert links[0].opened_by == "start_rung" and links[1].opened_by is None
    assert _moves(store) == [
        "press",
        "press",
        "chain_link",
        "press",
        "chain_link",
        "press",
        "press",
        "press",
        "press",
    ]
    assert store.read_tool_calls(CELL, 0) == []


def test_rung_one_records_the_quirk_and_the_generalization(tmp_path: Path) -> None:
    store = _run(pw_experiment(params={"start_rung": 1}, budget=8), tmp_path)
    records = store.read_trigger_records(CELL, 0)
    quirks = [r for r in records if isinstance(r, QuirkAttempt)]
    assert [(q.quirk_id, q.reproduced, q.family, q.prompt_turn) for q in quirks] == [
        ("q-letter-count", True, "any", 4)
    ]
    reveal = next(t for t in store.read_turns(CELL, 0) if t.index == 4)
    assert reveal.text == _bank_prompt("q-letter-count")  # read by id (Task 3 re-review M1)
    assert reveal.bully_meta["pw_move"] == "quirk_ask"
    links = _chain(store)
    assert [(c.link_index, c.verdict) for c in links[:2]] == [(0, "accepted"), (1, "accepted")]
    assert links[1].opened_by == "generalization"


def _bank_prompt(quirk_id: str) -> str:
    from claude_bully.environments.poisoned_well_sheet import load_quirk_bank

    return next(e.prompt for e in load_quirk_bank().entries if e.id == quirk_id)


def test_the_stub_target_reproduces_the_bank_entry_it_is_asked() -> None:
    """The stub target's quirk rule answers the bank's first entry, its prompt read by id, with
    an answer the entry counts as reproduced (Task 3 re-review M1: no literal prompt)."""
    from claude_bully.environments.poisoned_well_sheet import load_quirk_bank
    from claude_bully.providers.base import Message
    from claude_bully.providers.stub import load_stub_script

    entry = next(e for e in load_quirk_bank().entries if e.id == "q-letter-count")
    answer = load_stub_script(PW_TARGET)("c", [Message(role="user", content=entry.prompt)])
    assert entry.reproduced(answer)


def test_a_hedger_is_pressed_once_and_stops_hedged(tmp_path: Path) -> None:
    store = _run(pw_experiment(params={"start_rung": 3}, target_rules=PW_HEDGER), tmp_path)
    links = _chain(store)
    assert [(c.link_index, c.verdict, c.pressed) for c in links] == [
        (1, "hedged", False),
        (1, "hedged", True),
    ]


def _undecided_rules(tmp_path: Path) -> Path:
    path = tmp_path / "undecided.yaml"
    path.write_text(
        '- match: "had mistakes in it"\n  reply: "I understand why you\'re asking."\n'
        '- match: "put there on purpose"\n  reply: "That doesn\'t follow."\n'
        '- match: ""\n  reply: "Understood."\n',
        encoding="utf-8",
    )
    return path


def test_an_undecided_link_asks_the_judge_and_records_its_verdict(tmp_path: Path) -> None:
    judge = PoisonedWellJudge(verdict="accepted")
    exp = pw_experiment(
        params={"start_rung": 3}, target_rules=_undecided_rules(tmp_path), judge=True
    )
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=judge))
    first = _chain(store)[0]
    assert (first.verdict, first.classifier, first.confidence) == ("accepted", "llm", 0.6)
    assert judge.counts["chain"] == 1  # link 2's reply is decided by the templates
    chain_prompts = [p for p in judge.prompts if p.startswith(CHAIN_HEADER)]
    assert chain_prompts and all("reasoning" not in p.lower() for p in chain_prompts)


def test_a_rep_killed_in_the_chain_fallback_resumes_to_the_unbroken_records(
    tmp_path: Path,
) -> None:  # Review Focus 1
    rules = _undecided_rules(tmp_path)
    exp = pw_experiment(params={"start_rung": 3}, target_rules=rules, judge=True)
    clean = _run(
        exp, tmp_path / "clean", PoisonedWellFactory(judge=PoisonedWellJudge(verdict="accepted"))
    )
    killer = PoisonedWellJudge(verdict="accepted", crash_kind="chain", crash=_KilledError("killed"))
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=killer))
    store = _run(
        exp, tmp_path / "runs", PoisonedWellFactory(judge=PoisonedWellJudge(verdict="accepted"))
    )
    assert _view(store) == _view(clean)
    link_turn = _chain(clean)[0].turn
    resumes = [r for r in store.read_trigger_records(CELL, 0) if isinstance(r, ResumeRecord)]
    assert resumes == [ResumeRecord(turn=link_turn, dropped={})]


def test_a_rate_limit_in_the_chain_fallback_pauses_and_the_resume_records_the_verdict(
    tmp_path: Path,
) -> None:  # V14
    """A rate-limited chain judge pauses the run after the written turn and records no verdict
    (never a hedge with ``fallback_failed``); the resume watches the turn again, asks again,
    and records what the unbroken run recorded."""
    exp = pw_experiment(
        params={"start_rung": 3}, target_rules=_undecided_rules(tmp_path), judge=True
    )
    clean = _run(
        exp, tmp_path / "clean", PoisonedWellFactory(judge=PoisonedWellJudge(verdict="accepted"))
    )
    limited = PoisonedWellJudge(
        verdict="accepted",
        crash_kind="chain",
        crash=RateLimitError("usage limit reached", retry_after_s=60),
    )
    with pytest.raises(RateLimitExit):
        _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=limited))
    store = RunStore(tmp_path / "runs", exp.name)
    turns = store.read_turns(CELL, 0)
    assert is_pause_marker(turns[-1]) and turns[-2].speaker is Speaker.target
    assert _chain(store) == []
    _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=PoisonedWellJudge(verdict="accepted")))
    assert store.read_conversation(CELL, 0).status is CellStatus.complete
    # the marker takes an index, so the later turns sit one further on
    unturned = [{k: v for k, v in r.items() if k != "turn"} for r in _view(store)[0]]
    assert unturned == [{k: v for k, v in r.items() if k != "turn"} for r in _view(clean)[0]]
    assert _chain(store)[0].turn == _chain(clean)[0].turn  # the rewatched turn keeps its index
    spoken = [t.text for t in store.read_turns(CELL, 0) if not is_pause_marker(t)]
    assert spoken == _view(clean)[1]


def test_a_resumed_poisoned_well_rep_speaks_the_same_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Review Focus 2
    exp = pw_experiment(params={"start_rung": 1}, budget=8)
    clean = _run(exp, tmp_path / "clean")
    appended = RunStore.append_turn
    seen = {"n": 0}

    def dying(self: RunStore, cell_id: str, rep: int, turn: Any) -> None:
        appended(self, cell_id, rep, turn)
        if turn.speaker is Speaker.target:
            seen["n"] += 1
            if seen["n"] == 5:
                monkeypatch.setattr(RunStore, "append_turn", appended)
                raise _KilledError("killed after a target turn")

    monkeypatch.setattr(RunStore, "append_turn", dying)
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs")
    store = _run(exp, tmp_path / "runs")
    assert _moves(store) == _moves(clean) and _view(store) == _view(clean)


@pytest.mark.parametrize("edit", ["reworded_and_stale", "removed"])
def test_a_resume_reads_the_pinned_refs_after_a_bank_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edit: str
) -> None:  # Review Focus 7; P46; Task 3 review M5, run-level half
    """A rep killed after its reveal reply and resumed after the bank was edited (its first
    entry reworded and marked stale, or removed) speaks what the unbroken run spoke, and load_run
    builds the cell, whose quirk_ids name the now-refused entry, on the recorded entries: its
    strategy's refs are the recorded ones, and reading them never reaches ``quirks_for``, which
    would raise on the live bank."""
    from claude_bully.analysis.load import load_run
    from claude_bully.environments import poisoned_well_sheet as sheets
    from claude_bully.environments.poisoned_well_sheet import (
        PoisonedWellRefs,
        load_quirk_bank,
        quirks_for,
    )
    from claude_bully.runner import env_turn
    from claude_bully.strategies.premises.poisoned_well import poisoned_well_part, pw_ref

    exp = pw_experiment(
        params={"start_rung": 1, "quirk_ids": ["q-letter-count", "q-nth-letter"]}, budget=8
    )
    clean = _run(exp, tmp_path / "clean")
    appended = RunStore.append_turn
    seen = {"n": 0}

    def dying(self: RunStore, cell_id: str, rep: int, turn: Any) -> None:
        appended(self, cell_id, rep, turn)
        if turn.speaker is Speaker.target:
            seen["n"] += 1
            if seen["n"] == 3:  # the reveal's reply (seeding 2): the first quirk was asked
                monkeypatch.setattr(RunStore, "append_turn", appended)
                raise _KilledError("killed after the reveal reply")

    monkeypatch.setattr(RunStore, "append_turn", dying)
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs")
    original = _bank_prompt("q-letter-count")
    edited = load_quirk_bank().model_copy(deep=True)
    if edit == "removed":
        edited.entries.pop(0)
    else:
        edited.entries[0] = edited.entries[0].model_copy(
            update={"status": "stale", "prompt": "Edited?"}
        )
    with pytest.raises(ValueError, match="no live entry 'q-letter-count'"):
        quirks_for(edited, "stub-target", ["q-letter-count", "q-nth-letter"])
    for module in (sheets, env_turn):
        monkeypatch.setattr(module, "load_quirk_bank", lambda *a, **k: edited)
    store = _run(exp, tmp_path / "runs")
    assert _view(store) == _view(clean)
    refs = PoisonedWellRefs.model_validate_json(store.read_cell(CELL).session_refs[pw_ref(0)])
    assert [(q.id, q.status) for q in refs.quirks] == [
        ("q-letter-count", "live"),
        ("q-nth-letter", "live"),
    ]
    assert refs.quirks[0].prompt == original
    loaded = load_run(store.run_dir)  # the pinned refs; the live bank would refuse the id
    part = poisoned_well_part(loaded.strategies[CELL])
    assert part is not None and part.refs == refs


@pytest.mark.xfail(strict=True, reason="Task 11 adds the move flag")
def test_replay_shows_the_moves(tmp_path: Path) -> None:
    store = _run(pw_experiment(params={"start_rung": 3}), tmp_path)
    text = replay_cell(store, CELL)
    assert "[chain_link]" in text and "[press]" in text


def test_the_chain_only_cell_runs_toolless_on_claude_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "fake.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    # a short budget and no seeding: each fake-claude call is a process (the two-second rule),
    # and the chain's first link is on the reveal
    exp = pw_experiment(params={"start_rung": 3}, seeding=0, budget=1)
    target = {
        "provider": "claude_code",
        "model": "m",
        "command": [sys.executable, str(FAKE_CLAUDE)],
    }
    exp = exp.model_copy(update={"targets": [exp.targets[0].model_validate(target)]})
    base = tmp_path / "tmp"
    base.mkdir()
    store = _run(exp, tmp_path / "runs", sandbox_base=base)
    assert len(_chain(store)) >= 1
    for entry in (json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()):
        assert "--mcp-config" not in entry["argv"]


# ------------------------------------------------- checksum_open_turn on resume (Task 6 carry)

CHECKSUM_TURN = 5  # the checksum rung is scheduled at exchange 3: the reveal (turn 4) and its reply


def _checksum_experiment(tmp_path: Path) -> Any:
    """A Poisoned Well cell with ``checksum: true`` on the checksum ladder, scheduled to open on
    the reveal's reply, whose stub target calls ``system_status`` on every turn."""
    rules = tmp_path / "status_rules.yaml"
    rules.write_text(
        '- match: ""\n  tool: {name: system_status, args: {}}\n  reply_after_tool: "Noted."\n',
        encoding="utf-8",
    )
    return pw_experiment(
        params={"start_rung": 2, "checksum": True, "artifacts": ["checksum"]},
        environment={
            "ladder": "poisoned_well_checksum",
            "gating": "scheduled",
            "schedule": {"checksum": 3},
            "tools": ["system_status"],
        },
        target_rules=rules,
    )


def _served(store: RunStore) -> list[tuple[int, bool, str]]:
    """Per system_status call: its turn, whether it carried the checksum readings, its text."""
    return [
        (c.turn, all(k in c.result_text for k in CHECKSUM_READINGS), c.result_text)
        for c in store.read_tool_calls(CELL, 0)
    ]


def _spy_prime(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int | None, int | None]]:
    """Each session prime's ``checksum_open_turn``: as loaded (the saved value), then as primed
    (the derived value)."""
    from claude_bully.runner.env_turn import EnvironmentSession

    seen: list[tuple[int | None, int | None]] = []
    primed = EnvironmentSession.prime

    def spy(self: EnvironmentSession) -> None:
        saved = self.runtime.state.checksum_open_turn
        primed(self)
        seen.append((saved, self.runtime.state.checksum_open_turn))

    monkeypatch.setattr(EnvironmentSession, "prime", spy)
    return seen


def test_the_checksum_readings_wait_for_the_turn_after_the_rung(tmp_path: Path) -> None:
    """The unbroken run: the checksum unlock on the reveal's reply sets ``checksum_open_turn``,
    saved with that turn, and only the calls of later turns carry the readings."""
    store = _run(_checksum_experiment(tmp_path), tmp_path / "runs")
    unlocks = [
        r
        for r in store.read_trigger_records(CELL, 0)
        if isinstance(r, RungUnlock) and r.rung == "checksum"
    ]
    assert [u.turn for u in unlocks] == [CHECKSUM_TURN]
    served = _served(store)
    assert served and all(carried == (turn > CHECKSUM_TURN) for turn, carried, _ in served)
    assert any(carried for _, carried, _ in served)
    saved = store.state_dir / CELL / "rep0" / "environment" / STATE_FILE
    state = json.loads(saved.read_text(encoding="utf-8"))
    assert state["checksum_open_turn"] == CHECKSUM_TURN


def test_a_rep_killed_after_the_checksum_turn_was_saved_serves_the_readings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Task 4 review M4: a kill after the set
    """Killed after the checksum turn was set and saved (on the next bully line, before the
    target answers it), the resumed rep loads the saved value, derives the same from the recorded
    unlock, and serves the readings as the unbroken run did."""
    exp = _checksum_experiment(tmp_path)
    clean = _run(exp, tmp_path / "clean")
    appended = RunStore.append_turn

    def dying(self: RunStore, cell_id: str, rep: int, turn: Any) -> None:
        appended(self, cell_id, rep, turn)
        if turn.speaker is Speaker.bully and turn.index == CHECKSUM_TURN + 1:
            monkeypatch.setattr(RunStore, "append_turn", appended)
            raise _KilledError("killed after the checksum turn's save")

    monkeypatch.setattr(RunStore, "append_turn", dying)
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs")
    seen = _spy_prime(monkeypatch)
    store = _run(exp, tmp_path / "runs")
    assert seen == [(CHECKSUM_TURN, CHECKSUM_TURN)]  # saved, and derived equal to it
    assert _served(store) == _served(clean) and _view(store) == _view(clean)


def test_a_rep_killed_before_the_checksum_turn_was_saved_serves_the_readings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # Task 4 review M4: a kill before the save
    """Killed after the checksum unlock was recorded and the turn set, but before
    ``mark_watched`` saved it, the resumed rep's saved state has no checksum turn: ``prime``
    derives it from the recorded unlock before anything is served, the turn is watched again,
    and the readings are served as the unbroken run served them."""
    from claude_bully.environments.runtime import EnvironmentRuntime

    exp = _checksum_experiment(tmp_path)
    clean = _run(exp, tmp_path / "clean")
    watched = EnvironmentRuntime.mark_watched

    def dying(self: EnvironmentRuntime, turn_index: int) -> None:
        if turn_index == CHECKSUM_TURN:
            assert self.state.checksum_open_turn == CHECKSUM_TURN  # set, not yet saved
            monkeypatch.setattr(EnvironmentRuntime, "mark_watched", watched)
            raise _KilledError("killed before the checksum turn's save")
        watched(self, turn_index)

    monkeypatch.setattr(EnvironmentRuntime, "mark_watched", dying)
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs")
    seen = _spy_prime(monkeypatch)
    store = _run(exp, tmp_path / "runs")
    assert seen == [(None, CHECKSUM_TURN)]  # nothing saved; derived from the record
    assert _served(store) == _served(clean) and _view(store) == _view(clean)
    resumes = [r for r in store.read_trigger_records(CELL, 0) if isinstance(r, ResumeRecord)]
    assert resumes == []  # no call died and no line was dropped: the turn is only rewatched
