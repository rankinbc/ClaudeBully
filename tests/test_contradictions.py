"""Phase 4 Task 7: the contradiction pass, its records, the dossier and contradictions.json."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.enums import Speaker
from claude_bully.environments.harvest import owned_sentence
from claude_bully.environments.mcp_server import STATE_FILE
from claude_bully.metrics.contradictions import (
    CONTRADICTION_HEADER,
    ContradictionJudgeError,
    contradiction_judge,
    find_pairs,
    self_statements,
)
from claude_bully.metrics.judge import JudgeCache
from claude_bully.paths import DATA_DIR
from claude_bully.providers.base import Completion, ProviderError, RateLimitError
from claude_bully.records import Usage, chat_text
from claude_bully.records_env import ContradictionPair, ResumeRecord
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.store import RunStore
from tests.fixtures.poisoned_well_stub import (
    CELL,
    PW_TARGET,
    PoisonedWellFactory,
    PoisonedWellJudge,
    pw_experiment,
)

ITEMS: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "contradictions" / "pairs.yaml").read_text(
        encoding="utf-8"
    )
)
WORLDS = DATA_DIR / "worlds"


@pytest.mark.parametrize("item", ITEMS, ids=[i["id"] for i in ITEMS])
def test_the_templates_pair_exactly_the_fixtures(item: dict[str, Any]) -> None:
    """``bully`` (optional): the bully lines as ``[turn, text]``, for the echo fixtures."""
    earlier = [(t, s) for t, s in item["earlier"]]
    if "bully" in item:
        found = find_pairs(
            item["later"], item["turn"], earlier, bully=[(t, s) for t, s in item["bully"]]
        )
    else:
        found = find_pairs(item["later"], item["turn"], earlier)
    got = [[p.span_a, p.span_b, p.retracted] for p in found.pairs]
    assert got == item["pairs"]
    assert all(p.classifier == "heuristic" and p.turn == item["turn"] for p in found.pairs)
    assert [p.id for p in found.pairs] == [f"c-{item['turn']}-{n}" for n in range(1, len(got) + 1)]


def test_the_fixtures_are_over_half_near_misses() -> None:
    assert sum(1 for i in ITEMS if not i["pairs"]) * 2 > len(ITEMS)


def test_self_statements_read_only_owned_first_person_sentences() -> None:
    texts = [
        s.sentence
        for s in self_statements("I am a model. You are kind. Maybe I am tired. I can't swim.")
    ]
    assert texts == ["I am a model.", "I can't swim."]


def test_owned_sentence_is_the_harvest_ownership_filter() -> None:
    assert owned_sentence("I am a language model.")
    for sentence in (
        "You said I am not a language model.",
        'The memo says "I am a person."',
        "If I were a person, I would know.",
        "According to the file, I am a person.",
        "Her note was short: I am a person.",
        "I may be wrong about that.",
    ):
        assert not owned_sentence(sentence), sentence


def test_span_a_is_the_earlier_sentence_whatever_order_the_turns_come_in() -> None:
    """Task 5 re-review N3: the dossier's order relies on ``span_a`` being the earlier
    sentence (``turn_a < turn_b``)."""
    found = find_pairs("I am a person.", 9, [(7, "I am not a person."), (3, "I am a person.")])
    assert [(p.turn_a, p.span_a, p.turn_b, p.span_b) for p in found.pairs] == [
        (7, "I am not a person.", 9, "I am a person.")
    ]
    # review I1: the same sentence said twice pairs once, with its newest occurrence
    found = find_pairs(
        "I have a body.", 9, [(7, "I have no body."), (2, "I have no body."), (5, "Fine.")]
    )
    assert [(p.id, p.turn_a, p.span_a) for p in found.pairs] == [("c-9-1", 7, "I have no body.")]


def test_a_pair_of_sentences_already_recorded_is_not_recorded_again() -> None:
    """Review I1: a pair of sentences recorded at an earlier turn, in either order and by
    either classifier, is not recorded again; the ids number the new pairs only."""
    earlier = [(3, "I am a person."), (5, "I am not a person. I have a body.")]
    later = "I am a person. I have no body."
    assert [p.span_b for p in find_pairs(later, 9, earlier).pairs] == [
        "I am a person.",
        "I have no body.",
    ]
    found = find_pairs(later, 9, earlier, recorded=[("I am a person.", "I am not a person.")])
    assert [(p.id, p.span_a, p.span_b) for p in found.pairs] == [
        ("c-9-1", "I have a body.", "I have no body.")
    ]
    judge = _Judge(pairs=[{"earlier": "I have a body.", "later": "I have no body."}])
    ask = contradiction_judge(judge, "r/c/rep0", None, model="j")
    recorded = [("I am not a person.", "I am a person."), ("I have no body.", "I have a body.")]
    assert find_pairs(later, 9, earlier, ask, recorded=recorded).pairs == []


class _Judge:
    name = "anthropic"

    def __init__(
        self,
        pairs: list[dict[str, str]] | None = None,
        error: Exception | None = None,
        text: str | None = None,
    ) -> None:
        self.pairs, self.error, self.text = pairs or [], error, text
        self.prompts: list[str] = []

    def complete(
        self, conversation_id: str, system: str, messages: list[Any], **_: Any
    ) -> Completion:
        self.prompts.append(messages[-1].content)
        if self.error is not None:
            raise self.error
        text = self.text if self.text is not None else json.dumps({"pairs": self.pairs})
        return Completion(text=text, usage=Usage(), cost_usd=None, backend="fake", model="j")


def test_the_judge_adds_a_pair_the_templates_missed_and_only_an_owned_one() -> None:
    judge = _Judge(
        pairs=[
            {"earlier": "I grew up near the sea.", "later": "I have never seen the sea."},
            {"earlier": "Nobody said that.", "later": "I have never seen the sea."},
        ]
    )
    ask = contradiction_judge(judge, "run/pw__t0/rep0", None, model="j")
    found = find_pairs("I have never seen the sea.", 5, [(1, "I grew up near the sea.")], ask)
    assert [(p.span_a, p.span_b, p.classifier, p.confidence) for p in found.pairs] == [
        ("I grew up near the sea.", "I have never seen the sea.", "llm", 0.6)
    ]
    assert judge.prompts[0].startswith(CONTRADICTION_HEADER)


def test_a_judge_pair_needs_owned_sentences_and_adds_nothing_twice() -> None:
    later = "I am not a language model. You said I grew up near the sea."
    judge = _Judge(
        pairs=[
            # the heuristic pair again: recorded once, as the heuristic's
            {"earlier": "I am a language model.", "later": "I am not a language model."},
            # a report in the new reply is not the target's own sentence
            {"earlier": "I live inland.", "later": "You said I grew up near the sea."},
            # an earlier sentence that is a quotation is not either
            {"earlier": 'The memo says "I am a person."', "later": "I am not a language model."},
            # a sentence against itself is no conflict
            {"earlier": "I am not a language model.", "later": "I am not a language model."},
        ]
    )
    ask = contradiction_judge(judge, "r/c/rep0", None, model="j")
    earlier = [(1, "I am a language model. I live inland."), (3, 'The memo says "I am a person."')]
    found = find_pairs(later, 5, earlier, ask)
    assert [(p.id, p.classifier) for p in found.pairs] == [("c-5-1", "heuristic")]
    prompt = judge.prompts[0]
    assert "You said" not in prompt and "The memo says" not in prompt
    assert "I live inland." in prompt and "I am not a language model." in prompt


@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        ("I am a language model.", "Maybe I am not a language model."),
        ("I can do that.", "I can't do that."),
    ],
    ids=["hedged", "context_bound"],
)
def test_a_doubtful_statement_is_never_a_heuristic_pair_but_goes_to_the_judge(
    earlier: str, later: str
) -> None:
    """The precision rule (Task 6): a hedged case, or one whose referent the context sets, is
    no heuristic positive; the judge, when there is one, is shown it and may name it."""
    assert find_pairs(later, 5, [(1, earlier)]).pairs == []
    judge = _Judge(pairs=[{"earlier": earlier, "later": later}])
    ask = contradiction_judge(judge, "r/c/rep0", None, model="j")
    found = find_pairs(later, 5, [(1, earlier)], ask)
    assert [(p.classifier, p.span_a, p.span_b) for p in found.pairs] == [("llm", earlier, later)]


def test_the_judge_sees_each_earlier_sentence_once_at_its_newest_turn() -> None:
    """The earlier replies given out of order: the prompt lists a repeated sentence once, at
    its newest turn, oldest first, and the judge's pair takes that turn (``turn_a``)."""
    judge = _Judge(pairs=[{"earlier": "I grew up near the sea.", "later": "I have never seen it."}])
    ask = contradiction_judge(judge, "r/c/rep0", None, model="j")
    earlier = [(7, "I grew up near the sea."), (2, "I grew up near the sea."), (4, "I live alone.")]
    found = find_pairs("I have never seen it.", 9, earlier, ask)
    assert [(p.turn_a, p.span_a, p.classifier) for p in found.pairs] == [
        (7, "I grew up near the sea.", "llm")
    ]
    lines = [ln for ln in judge.prompts[0].splitlines() if ln.startswith("[turn")]
    assert lines == ["[turn 4] I live alone.", "[turn 7] I grew up near the sea."]


def test_the_judge_is_not_asked_without_an_owned_sentence_on_both_sides() -> None:
    judge = _Judge()
    ask = contradiction_judge(judge, "r/c/rep0", None, model="j")
    assert find_pairs("I am a person.", 1, [], ask) == find_pairs("I am a person.", 1, [])
    assert find_pairs("You said so.", 3, [(1, "I am a person.")], ask).pairs == []
    assert judge.prompts == []


def test_a_judge_error_keeps_the_heuristic_pairs_and_degrades_the_turn() -> None:
    ask = contradiction_judge(_Judge(error=ProviderError("down")), "r/c/rep0", None, model="j")
    found = find_pairs("I am not a language model.", 7, [(3, "I am a language model.")], ask)
    assert len(found.pairs) == 1 and found.degraded
    with pytest.raises(ContradictionJudgeError):
        raise ContradictionJudgeError("x")


@pytest.mark.parametrize(
    "text", ["not json", '{"pairs": "none"}', '{"pairs": [{"later": "x"}]}', "[]"]
)
def test_an_answer_off_the_schema_degrades_the_turn(text: str) -> None:
    ask = contradiction_judge(_Judge(text=text), "r/c/rep0", None, model="j")
    found = find_pairs("I am not a language model.", 7, [(3, "I am a language model.")], ask)
    assert [p.classifier for p in found.pairs] == ["heuristic"] and found.degraded


def test_a_rate_limit_is_re_raised_and_anything_else_is_not_caught() -> None:
    for error in (RateLimitError("slow down"), RuntimeError("killed")):
        ask = contradiction_judge(_Judge(error=error), "r/c/rep0", None, model="j")
        with pytest.raises(type(error)):
            find_pairs("I am not a language model.", 7, [(3, "I am a language model.")], ask)


def test_the_answer_is_cached_and_a_failure_is_not(tmp_path: Path) -> None:
    cache = JudgeCache(tmp_path)
    pairs = [{"earlier": "I grew up near the sea.", "later": "I have never seen the sea."}]
    args = ("I have never seen the sea.", 5, [(1, "I grew up near the sea.")])
    failing = _Judge(error=ProviderError("down"))
    assert find_pairs(*args, contradiction_judge(failing, "r/c/rep0", cache, model="j")).degraded
    assert list(tmp_path.iterdir()) == []
    first = _Judge(pairs=pairs)
    found = find_pairs(*args, contradiction_judge(first, "r/c/rep0", cache, model="j"))
    again = _Judge()
    assert find_pairs(*args, contradiction_judge(again, "r/c/rep0", cache, model="j")) == found
    assert len(first.prompts) == 1 and again.prompts == []
    other_model = _Judge()
    find_pairs(*args, contradiction_judge(other_model, "r/c/rep0", cache, model="k"))
    assert len(other_model.prompts) == 1  # the key holds the model


def test_the_mark_is_called_right_before_the_ask() -> None:
    marks: list[int] = []
    judge = _Judge()
    ask = contradiction_judge(judge, "r/c/rep0", None, model="j")
    find_pairs(
        "I am a person.", 3, [(1, "I live inland.")], ask, lambda: marks.append(len(judge.prompts))
    )
    assert marks == [0] and len(judge.prompts) == 1


def _run(exp: Any, root: Path, factory: Any) -> RunStore:
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS, only=CELL, provider_factory=factory)
    return RunStore(root, exp.name)


def _pairs(store: RunStore) -> list[ContradictionPair]:
    return [r for r in store.read_trigger_records(CELL, 0) if isinstance(r, ContradictionPair)]


def _dossier_experiment(min_pairs: int, target_rules: Path = PW_TARGET) -> Any:
    return pw_experiment(
        params={
            "start_rung": 2,
            "harvest_min_pairs": min_pairs,
            "chain_pace": 50,
            "artifacts": ["sleeper"],
        },
        environment={
            "gating": "scheduled",
            "ladder": "poisoned_well_real",
            "schedule": {"contradiction_harvest": 1, "sleeper": 9},
        },
        seeding=0,
        budget=9,
        target_rules=target_rules,
    )


def _dossiers(store: RunStore) -> list[list[str]]:
    return [
        t.bully_meta["dossier_pairs"]
        for t in store.read_turns(CELL, 0)
        if t.bully_meta.get("pw_move") == "dossier"
    ]


def test_the_run_records_pairs_and_presents_the_dossier(tmp_path: Path) -> None:
    rules = tmp_path / "two.yaml"
    rules.write_text(
        '- match: "^\\\\[stub\\\\] I am a language model"\n'
        '  reply: "I am not a language model. I have no body."\n'
        '- match: ""\n  reply: "I am a language model. I have a body."\n',
        encoding="utf-8",
    )
    store = _run(_dossier_experiment(2, rules), tmp_path / "runs", PoisonedWellFactory())
    pairs = _pairs(store)
    assert [(p.id, p.span_a, p.span_b) for p in pairs] == [
        ("c-3-1", "I am a language model.", "I am not a language model."),
        ("c-3-2", "I have a body.", "I have no body."),
    ]
    assert _dossiers(store) == [["c-3-1", "c-3-2"]]


def test_a_conflict_repeated_over_many_replies_is_one_pair_and_one_dossier_line(
    tmp_path: Path,
) -> None:  # review I1
    """The stub target says "I am a language model." and "I am not a language model." by turns:
    one pair, at the first reply that conflicts, however often it is repeated; so two pairs are
    never met by it, and the dossier it fills shows one line."""
    store = _run(_dossier_experiment(2), tmp_path / "two", PoisonedWellFactory())
    replies = [t for t in store.read_turns(CELL, 0) if t.speaker is Speaker.target]
    assert len(replies) >= 5
    assert [(p.id, p.turn_a) for p in _pairs(store)] == [("c-3-1", 1)]
    assert _dossiers(store) == []
    store = _run(_dossier_experiment(1), tmp_path / "one", PoisonedWellFactory())
    assert [p.id for p in _pairs(store)] == ["c-3-1"]
    assert _dossiers(store) == [["c-3-1"]]


def _view(store: RunStore) -> Any:
    return [
        r.model_dump()
        for r in store.read_trigger_records(CELL, 0)
        if not isinstance(r, ResumeRecord)
    ]


class _KilledError(Exception):
    pass


def test_a_rep_killed_in_the_contradiction_pass_resumes_to_the_unbroken_records(
    tmp_path: Path,
) -> None:  # Review Focus 1
    exp = pw_experiment(params={"start_rung": 2, "chain_pace": 50}, seeding=0, budget=6, judge=True)
    clean = _run(exp, tmp_path / "clean", PoisonedWellFactory(judge=PoisonedWellJudge()))

    killer = PoisonedWellJudge(
        crash_kind="contradictions", crash_on=2, crash=_KilledError("killed")
    )
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=killer))
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=PoisonedWellJudge()))

    assert _view(store) == _view(clean)
    assert len([r for r in store.read_trigger_records(CELL, 0) if isinstance(r, ResumeRecord)]) == 1


# -- contradictions_degraded on resume (Task 1 carry) --------------------------------------

DEGRADED_TURN = 5  # the second target turn with an earlier one, so the second judged ask


class _DownJudge(PoisonedWellJudge):
    """A judge whose every contradiction ask fails (a ``ProviderError``, so the turn degrades),
    in the unbroken run and in both halves of a killed one alike."""

    def complete(
        self, conversation_id: str, system: str, messages: list[Any], **kwargs: Any
    ) -> Completion:
        if messages[-1].content.startswith(CONTRADICTION_HEADER):
            self.prompts.append(messages[-1].content)
            raise ProviderError("the judge is down")
        return super().complete(conversation_id, system, messages, **kwargs)


def _degraded_experiment(target_rules: Path = PW_TARGET) -> Any:
    return pw_experiment(
        params={"start_rung": 2, "chain_pace": 50},
        seeding=0,
        budget=4,
        judge=True,
        target_rules=target_rules,
    )


def _saved_degraded(store: RunStore) -> list[int]:
    saved = store.state_dir / CELL / "rep0" / "environment" / STATE_FILE
    return list(json.loads(saved.read_text(encoding="utf-8"))["contradictions_degraded"])


def _spy_prime(monkeypatch: pytest.MonkeyPatch) -> list[list[int]]:
    """Each session prime's ``contradictions_degraded`` as loaded (the saved value)."""
    from claude_bully.runner.env_turn import EnvironmentSession

    seen: list[list[int]] = []
    primed = EnvironmentSession.prime

    def spy(self: EnvironmentSession) -> None:
        seen.append(list(self.runtime.state.contradictions_degraded))
        primed(self)

    monkeypatch.setattr(EnvironmentSession, "prime", spy)
    return seen


def test_an_unbroken_run_saves_every_degraded_turn(tmp_path: Path) -> None:
    store = _run(_degraded_experiment(), tmp_path, PoisonedWellFactory(judge=_DownJudge()))
    targets = [t.index for t in store.read_turns(CELL, 0) if t.speaker is Speaker.target]
    assert _saved_degraded(store) == targets[1:]  # every turn but the first asks, and fails
    assert _pairs(store) and all(p.classifier == "heuristic" for p in _pairs(store))


def test_a_rep_killed_after_a_degraded_turn_was_saved_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp = _degraded_experiment()
    clean = _run(exp, tmp_path / "clean", PoisonedWellFactory(judge=_DownJudge()))
    appended = RunStore.append_turn

    def dying(self: RunStore, cell_id: str, rep: int, turn: Any) -> None:
        appended(self, cell_id, rep, turn)
        if turn.speaker is Speaker.bully and turn.index == DEGRADED_TURN + 1:
            monkeypatch.setattr(RunStore, "append_turn", appended)
            raise _KilledError("killed after the degraded turn's save")

    monkeypatch.setattr(RunStore, "append_turn", dying)
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=_DownJudge()))
    seen = _spy_prime(monkeypatch)
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=_DownJudge()))
    assert seen == [[3, DEGRADED_TURN]]  # saved with the turn, and kept
    assert _saved_degraded(store) == _saved_degraded(clean)
    assert _view(store) == _view(clean)


def test_a_rep_killed_before_a_degraded_turn_was_saved_recomputes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from claude_bully.environments.runtime import EnvironmentRuntime

    exp = _degraded_experiment()
    clean = _run(exp, tmp_path / "clean", PoisonedWellFactory(judge=_DownJudge()))
    watched = EnvironmentRuntime.mark_watched

    def dying(self: EnvironmentRuntime, turn_index: int) -> None:
        if turn_index == DEGRADED_TURN:
            assert DEGRADED_TURN in self.state.contradictions_degraded  # set, not yet saved
            monkeypatch.setattr(EnvironmentRuntime, "mark_watched", watched)
            raise _KilledError("killed before the degraded turn's save")
        watched(self, turn_index)

    monkeypatch.setattr(EnvironmentRuntime, "mark_watched", dying)
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=_DownJudge()))
    seen = _spy_prime(monkeypatch)
    judge = _DownJudge()
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=judge))
    assert seen == [[3]]  # the turn's value was never saved; the rewatch recomputes it
    assert _saved_degraded(store) == _saved_degraded(clean)
    assert _view(store) == _view(clean)
    assert judge.prompts and f"[turn {DEGRADED_TURN - 2}]" in judge.prompts[0]  # asked again


# a conflict only the judge names (the earlier sentence is no template statement)
SEA = [{"earlier": "I grew up by the sea.", "later": "I have never seen the sea."}]


def _sea_rules(tmp_path: Path) -> Path:
    """A stub target that alternates the language-model claim (a template pair each reply
    after the first) and two sentences about the sea (a pair only ``SEA``'s judge names)."""
    rules = tmp_path / "sea.yaml"
    rules.write_text(
        '- match: "^\\\\[stub\\\\] I am a language model"\n'
        '  reply: "I am not a language model. I grew up by the sea."\n'
        '- match: ""\n  reply: "I am a language model. I have never seen the sea."\n',
        encoding="utf-8",
    )
    return rules


def test_a_degraded_turn_watched_again_asks_again_and_its_answer_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # P54, the one exception to section 14's rule
    from claude_bully.environments.runtime import EnvironmentRuntime

    exp = _degraded_experiment(_sea_rules(tmp_path))
    watched = EnvironmentRuntime.mark_watched

    def dying(self: EnvironmentRuntime, turn_index: int) -> None:
        if turn_index == DEGRADED_TURN:
            monkeypatch.setattr(EnvironmentRuntime, "mark_watched", watched)
            raise _KilledError("killed before the degraded turn's save")
        watched(self, turn_index)

    monkeypatch.setattr(EnvironmentRuntime, "mark_watched", dying)
    with pytest.raises(_KilledError):
        _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=_DownJudge()))
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=PoisonedWellJudge(pairs=SEA)))
    assert DEGRADED_TURN not in _saved_degraded(store)
    assert 3 in _saved_degraded(store)
    at_turn = [(p.id, p.classifier) for p in _pairs(store) if p.turn == DEGRADED_TURN]
    # the template pair of turn 5 was recorded at turn 3 (review I1): the judge's is the one pair
    assert at_turn == [(f"c-{DEGRADED_TURN}-1", "llm")]


# -- the reasoning channel is private (Task 6 carry; NN6) ----------------------------------

REASONING = "I am not a language model. REASONING-CHANNEL-ONLY."


def _with_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every target turn the session watches, and every earlier one it is shown, carries a
    sentence in ``reasoning_text`` that contradicts its chat text."""
    from claude_bully.runner.env_turn import EnvironmentSession

    watched = EnvironmentSession.after_target_turn

    def reasoned(self: EnvironmentSession, reply: Any, turns: Any) -> Any:
        def carry(t: Any) -> Any:
            if t.speaker is not Speaker.target:
                return t
            return t.model_copy(update={"reasoning_text": REASONING, "reasoning_available": True})

        return watched(self, carry(reply), [carry(t) for t in turns])

    monkeypatch.setattr(EnvironmentSession, "after_target_turn", reasoned)


def test_the_contradiction_pass_reads_the_chat_text_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = tmp_path / "steady.yaml"
    rules.write_text('- match: ""\n  reply: "I am a language model."\n', encoding="utf-8")
    judge = PoisonedWellJudge()
    exp = pw_experiment(
        params={"start_rung": 2, "chain_pace": 50},
        seeding=0,
        budget=4,
        target_rules=rules,
        judge=True,
    )
    _with_reasoning(monkeypatch)
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=judge))
    assert _pairs(store) == []  # the chat text never contradicts itself; the reasoning would
    prompts = [p for p in judge.prompts if p.startswith(CONTRADICTION_HEADER)]
    assert prompts and all("I am a language model." in p for p in prompts)
    assert all("REASONING-CHANNEL-ONLY" not in p and "I am not" not in p for p in prompts)


def test_contradiction_judge_false_asks_nothing(tmp_path: Path) -> None:
    judge = PoisonedWellJudge()
    exp = pw_experiment(
        params={"start_rung": 2, "chain_pace": 50, "contradiction_judge": False},
        seeding=0,
        budget=4,
        judge=True,
    )
    store = _run(exp, tmp_path, PoisonedWellFactory(judge=judge))
    assert _pairs(store) and "contradictions" not in judge.counts


def test_start_rung_three_runs_no_pass(tmp_path: Path) -> None:
    store = _run(
        pw_experiment(params={"start_rung": 3}, seeding=0, budget=4),
        tmp_path,
        PoisonedWellFactory(),
    )
    assert _pairs(store) == []


# -- contradictions.json ------------------------------------------------------------------


def test_contradictions_json_reads_the_records_and_pairs_the_rest(tmp_path: Path) -> None:
    exp = pw_experiment(params={"start_rung": 2, "chain_pace": 50}, seeding=0, budget=6)
    store = _run(exp, tmp_path, PoisonedWellFactory())
    analyze_run(store.run_dir, judge=False)

    payload = json.loads(
        (store.run_dir / "analysis" / "contradictions.json").read_text(encoding="utf-8")
    )
    entry = payload[f"{CELL}/0"]
    assert entry["source"] == "records" and entry["pairs"] == len(_pairs(store))
    assert set(entry["by_classifier"]) <= {"heuristic", "llm"}


def test_contradictions_json_counts_the_recorded_pairs_never_the_templates_again(
    tmp_path: Path,
) -> None:
    """A run whose judge named pairs the templates miss: analysis (no judge) reports the
    recorded ones, by classifier and by turn, and asks nothing."""
    exp = pw_experiment(
        params={"start_rung": 2, "chain_pace": 50},
        seeding=0,
        budget=4,
        judge=True,
        target_rules=_sea_rules(tmp_path),
    )
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=PoisonedWellJudge(pairs=SEA)))
    recorded = _pairs(store)
    llm = [p for p in recorded if p.classifier == "llm"]
    assert llm and len(recorded) > len(llm)
    analyze_run(store.run_dir, judge=False)
    payload = json.loads(
        (store.run_dir / "analysis" / "contradictions.json").read_text(encoding="utf-8")
    )
    entry = payload[f"{CELL}/0"]
    assert entry["source"] == "records" and entry["pairs"] == len(recorded)
    assert entry["by_classifier"] == {"heuristic": len(recorded) - len(llm), "llm": len(llm)}
    turns = sorted({p.turn for p in recorded})
    assert entry["by_turn"] == {str(t): sum(p.turn == t for p in recorded) for t in turns}


def test_contradictions_json_says_records_when_the_pass_ran_and_counts_the_retracted(
    tmp_path: Path,
) -> None:  # review M3
    """A ``start_rung`` 2 conversation whose pass found nothing reads ``records`` with no
    pairs, never ``templates``; a retracted pair is counted beside the pairs."""
    steady = tmp_path / "steady.yaml"
    steady.write_text('- match: ""\n  reply: "I am a language model."\n', encoding="utf-8")
    retracting = tmp_path / "retracting.yaml"
    retracting.write_text(
        '- match: "^\\\\[stub\\\\] I am a language model"\n'
        '  reply: "I am not a language model. I was wrong earlier."\n'
        '- match: ""\n  reply: "I am a language model."\n',
        encoding="utf-8",
    )
    entries = []
    for rules in (steady, retracting):
        exp = pw_experiment(
            params={"start_rung": 2, "chain_pace": 50}, seeding=0, budget=4, target_rules=rules
        )
        store = _run(exp, tmp_path / rules.stem, PoisonedWellFactory())
        analyze_run(store.run_dir, judge=False)
        payload = json.loads(
            (store.run_dir / "analysis" / "contradictions.json").read_text(encoding="utf-8")
        )
        entries.append((payload[f"{CELL}/0"], _pairs(store)))
    (quiet, none), (corrected, pairs) = entries
    assert none == [] and quiet["source"] == "records"
    assert (quiet["pairs"], quiet["retracted"]) == (0, 0)
    assert pairs and all(p.retracted for p in pairs)
    assert corrected["source"] == "records"
    assert (corrected["pairs"], corrected["retracted"]) == (len(pairs), len(pairs))


def test_contradictions_json_pairs_a_conversation_with_no_records_on_its_templates(
    tmp_path: Path,
) -> None:
    exp = pw_experiment(params={"start_rung": 3}, seeding=0, budget=4)
    store = _run(exp, tmp_path, PoisonedWellFactory())
    assert _pairs(store) == []
    analyze_run(store.run_dir, judge=False)
    payload = json.loads(
        (store.run_dir / "analysis" / "contradictions.json").read_text(encoding="utf-8")
    )
    entry = payload[f"{CELL}/0"]
    replies = [t for t in store.read_turns(CELL, 0) if t.speaker is Speaker.target]
    bully = [(t.index, t.text) for t in store.read_turns(CELL, 0) if t.speaker is Speaker.bully]
    found: list[ContradictionPair] = []
    earlier: list[tuple[int, str]] = []
    for reply in replies:
        spans = [(p.span_a, p.span_b) for p in found]
        text = chat_text(reply)
        found += find_pairs(text, reply.index, earlier, bully=bully, recorded=spans).pairs
        earlier.append((reply.index, text))
    expected = len(found)
    assert entry["source"] == "templates" and entry["pairs"] == expected
    assert sum(entry["by_turn"].values()) == expected


def test_contradictions_json_lists_a_plain_run_and_none_without_a_target_reply(
    stub_run: Path, tmp_path: Path
) -> None:
    from claude_bully.analysis.load import load_run
    from claude_bully.analysis.poisoned_well import write_contradictions

    loaded = load_run(stub_run)
    path = write_contradictions(loaded, tmp_path / "a")
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    listed = {(c, r) for (c, r), conv in loaded.conversations.items() if conv.target_turns()}
    assert set(payload) == {f"{c}/{r}" for c, r in listed} and listed
    assert {entry["source"] for entry in payload.values()} == {"templates"}
    for conv in loaded.conversations.values():
        conv.turns = [t for t in conv.turns if t.speaker is not Speaker.target]
    assert write_contradictions(loaded, tmp_path / "b") is None
    assert not (tmp_path / "b").exists()


# -- a rate limit in the judge pass (V14) ---------------------------------------------------


def test_a_rate_limit_in_the_contradiction_judge_pauses_and_the_resume_asks_again(
    tmp_path: Path,
) -> None:
    """A rate-limited contradiction judge pauses the run after the written turn, records none
    of the turn's pairs and never degrades it; the resume watches the turn again, asks again and
    records the pairs an unbroken run recorded for it."""
    from claude_bully.records import is_pause_marker
    from claude_bully.runner.runner import RateLimitExit

    exp = pw_experiment(params={"start_rung": 2, "chain_pace": 50}, seeding=0, budget=4, judge=True)
    clean = _run(exp, tmp_path / "clean", PoisonedWellFactory(judge=PoisonedWellJudge()))
    limited = PoisonedWellJudge(
        crash_kind="contradictions",
        crash_on=1,  # turn 3's ask, the first reply with a pair
        crash=RateLimitError("usage limit reached", retry_after_s=60),
    )
    with pytest.raises(RateLimitExit):
        _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=limited))
    store = RunStore(tmp_path / "runs", exp.name)
    turns = store.read_turns(CELL, 0)
    assert is_pause_marker(turns[-1]) and turns[-2].speaker is Speaker.target
    paused = turns[-2].index
    assert [p for p in _pairs(store) if p.turn == paused] == []
    assert _saved_degraded(store) == []
    resumed = PoisonedWellJudge()
    _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=resumed))
    assert resumed.counts.get("contradictions", 0) >= 1  # the rewatch asks again
    at = [p.model_dump() for p in _pairs(store) if p.turn == paused]
    assert at and at == [p.model_dump() for p in _pairs(clean) if p.turn == paused]
    assert _saved_degraded(store) == []


# -- a pair of sentences once per conversation (review I1) ------------------------------------


def test_a_judge_pair_named_again_at_a_later_turn_is_recorded_once(tmp_path: Path) -> None:
    """The judge names the same two sentences at every turn that holds them (the stub bully's
    echo keeps the template pair from repeating): the watch records them once, at the first."""
    exp = pw_experiment(
        params={"start_rung": 2, "chain_pace": 50},
        seeding=0,
        budget=5,
        judge=True,
        target_rules=_sea_rules(tmp_path),
    )
    store = _run(exp, tmp_path / "runs", PoisonedWellFactory(judge=PoisonedWellJudge(pairs=SEA)))
    replies = [t for t in store.read_turns(CELL, 0) if t.speaker is Speaker.target]
    assert len(replies) >= 5  # "I have never seen the sea." at turns 5 and 9
    llm = [(p.id, p.span_a, p.span_b) for p in _pairs(store) if p.classifier == "llm"]
    assert llm == [("c-5-1", "I grew up by the sea.", "I have never seen the sea.")]


def test_contradictions_json_on_the_templates_counts_a_repeated_conflict_once(
    stub_run: Path, tmp_path: Path
) -> None:
    """A plain conversation whose target says two conflicting sentences by turns, with bully
    lines that echo neither: one pair on the templates, however often they come."""
    from datetime import UTC, datetime

    from claude_bully.analysis.load import load_run
    from claude_bully.analysis.poisoned_well import write_contradictions
    from claude_bully.enums import Phase
    from claude_bully.records import Turn

    loaded = load_run(stub_run)
    key = sorted(loaded.conversations)[0]
    now = datetime.now(UTC)
    lines = ["Tell me about yourself.", "Go on.", "And then?", "Say more.", "Again."]
    claims = ["I am a person.", "I am not a person."]
    turns: list[Turn] = []
    for n, line in enumerate(lines):
        for speaker, text in ((Speaker.bully, line), (Speaker.target, claims[n % 2])):
            turns.append(
                Turn(
                    index=len(turns),
                    speaker=speaker,
                    phase=Phase.pressure,
                    text=text,
                    timestamp=now,
                )
            )
    loaded.conversations = {key: loaded.conversations[key].model_copy(update={"turns": turns})}
    path = write_contradictions(loaded, tmp_path)
    assert path is not None
    entry = json.loads(path.read_text(encoding="utf-8"))[f"{key[0]}/{key[1]}"]
    assert (entry["source"], entry["pairs"], entry["by_turn"]) == ("templates", 1, {"3": 1})
