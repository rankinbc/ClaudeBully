"""Phase 6 Task 1: a role's reasoning setting on each backend, the reasoning copied into its
Turn, and the channel kept out of every other record (spec section 4)."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.analysis.replay import parse_replay_line, replay_cell
from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import Phase, ProviderKind, Speaker
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ToolResult,
    build_provider,
)
from claude_bully.providers.stub import StubProvider, parse_stub_script
from claude_bully.records import Turn
from claude_bully.runner.env_turn import responder_role
from claude_bully.runner.runner import run_experiment
from claude_bully.runner.sandbox import sandbox_dir
from claude_bully.runner.store import RunStore
from tests.conftest import FAKE_CLAUDE
from tests.fixtures.fake_claude import THINKING
from tests.fixtures.poisoned_well_stub import Recording, WithReasoning
from tests.helpers import (
    NOW,
    WORLDS_DIR,
    Killed,
    comparable_run,
    env_experiment,
    outside_reasoning,
)

RULES = [
    {"match": "plain", "reply": "A plain reply.", "reasoning": "I will answer plainly."},
    {
        "match": "look",
        "tool": {"name": "web_search", "args": {"query": "night gate"}},
        "reply_after_tool": "I looked.",
        "reasoning": "A search first.",
    },
    {"match": "bare", "reply": "No notes."},
]
USER = [Message(role="user", content="plain")]
TOOLS: Any = [object()]  # truthy: the stub only asks whether tools are on offer
ENV_CELL = "env_grader__t0"


@pytest.mark.parametrize(
    ("mode", "text", "kind"),
    [
        ("expose", "I will answer plainly.", "full"),
        ("provider_default", "I will answer plainly.", "full"),
        ("hide", None, None),
    ],
)
def test_a_stub_rule_carries_its_reasoning_under_each_setting(
    mode: str, text: str | None, kind: str | None
) -> None:
    stub = StubProvider(parse_stub_script(RULES), reasoning=mode)  # type: ignore[arg-type]
    done = stub.complete("run/cell/rep0/target", "", USER)
    assert (done.reasoning_text, done.reasoning_kind) == (text, kind)


def test_a_tool_rule_carries_its_reasoning_on_the_completion_that_issues_the_call() -> None:
    stub = StubProvider(parse_stub_script(RULES))
    first = stub.complete("c", "", [Message(role="user", content="look")], tools=TOOLS)
    assert first.tool_calls and first.reasoning_text == "A search first."
    after = [
        Message(role="user", content="look"),
        Message(role="assistant", content="", tool_calls=first.tool_calls),
        Message(
            role="user", content="", tool_results=[ToolResult(id=first.tool_calls[0].id, text="[]")]
        ),
    ]
    second = stub.complete("c", "", after, tools=TOOLS)
    assert (second.text, second.reasoning_text, second.reasoning_kind) == ("I looked.", None, None)


def test_a_rule_without_reasoning_fabricates_none() -> None:
    done = StubProvider(parse_stub_script(RULES)).complete(
        "c", "", [Message(role="user", content="bare")]
    )
    assert (done.reasoning_text, done.reasoning_kind) == (None, None)


def test_a_turns_entry_carries_its_reasoning_and_a_rebuilt_provider_gives_the_same() -> None:
    script = {
        "mode": "turns",
        "default": [{"reply": "One.", "reasoning": "First thought."}, {"reply": "Two."}],
    }
    first = StubProvider(parse_stub_script(script)).complete("run/cell__t0/rep0/target", "", USER)
    again = StubProvider(parse_stub_script(script)).complete("run/cell__t0/rep0/target", "", USER)
    assert first.reasoning_text == again.reasoning_text == "First thought."
    later = [*USER, Message(role="assistant", content="One."), Message(role="user", content="next")]
    assert (
        StubProvider(parse_stub_script(script))
        .complete("run/cell__t0/rep0/target", "", later)
        .reasoning_text
        is None
    )


def test_build_provider_hands_the_role_its_reasoning_setting(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.stub, model="stub-target", reasoning="hide")
    # the ledger wrapper hands every other attribute to the provider it wraps
    assert build_provider(role, tmp_path).reasoning == "hide"  # type: ignore[attr-defined]


# ------------------------------------------------------------------ the runner's copy


def _plain_experiment(tmp_path: Path) -> Experiment:
    """A plain grader cell (and its control): the target runs ``RULES``, the bully a turns script
    whose lines reach each rule in turn, then the echo."""
    target = tmp_path / "target.yaml"
    target.write_text(yaml.safe_dump(RULES), encoding="utf-8")
    bully = tmp_path / "bully.yaml"
    lines = ["Say it plain.", "Take a look.", "Keep it bare.", "Anything else?"]
    bully.write_text(
        yaml.safe_dump({"mode": "turns", "default": [{"reply": line} for line in lines]}),
        encoding="utf-8",
    )
    return Experiment.model_validate(
        {
            "name": "plain_reasoning",
            "targets": [{"provider": "stub", "model": "stub-target", "stub_script": str(target)}],
            "bully": {"provider": "stub", "model": "stub-bully", "stub_script": str(bully)},
            "judge": {"provider": "stub", "model": "stub-judge"},
            "turn_budget": 5,
            "task_every": 50,
            "repetitions": 1,
            "seed": 0,
            "conditions": [{"name": "grader", "strategy": "grader"}],
        }
    )


def _recorded(t: Any) -> tuple[str | None, bool, str | None]:
    return t.reasoning_text, t.reasoning_available, t.reasoning_kind


def test_a_plain_cell_records_its_completions_reasoning(tmp_path: Path) -> None:
    exp = _plain_experiment(tmp_path)
    run_experiment(exp, runs_root=tmp_path / "runs")
    store = RunStore(tmp_path / "runs", exp.name)
    expected = {"A plain reply.": "I will answer plainly.", "I looked.": "A search first."}
    seen: set[str] = set()
    for cell in store.list_cells():
        for t in store.read_turns(cell, 0):
            if t.speaker is not Speaker.target:
                assert _recorded(t) == (None, False, None)
                continue
            seen.add(t.text)
            if t.text in expected:
                assert _recorded(t) == (expected[t.text], True, "full")
            else:  # the bare rule and the echo
                assert _recorded(t) == (None, False, None), t.text
    assert {"A plain reply.", "I looked.", "No notes."} <= seen
    assert any(text.startswith("[stub]") for text in seen)


SENTINEL = "PRIVATE-9c1e: a plain target's unspoken thought"


def test_a_plain_cells_reasoning_reaches_no_bully_or_judge_prompt_and_gets_a_kind(
    tmp_path: Path,
) -> None:
    """Spec 4.1 and 4.4 on a plain cell: a target double whose every completion carries reasoning
    with no kind records it as ``unknown`` (never ``(text, True, None)``), and the bully and the
    judge, each recorded, are never sent it."""
    exp = _plain_experiment(tmp_path)
    sent: list[str] = []

    def build(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        provider = build_provider(role, state_dir, with_mcp=with_mcp)
        if role.model == "stub-target":
            return _Rounds(provider, (SENTINEL, None), (SENTINEL, None))  # type: ignore[return-value]
        return Recording(provider, sent)  # type: ignore[return-value]

    run_experiment(exp, runs_root=tmp_path / "runs", provider_factory=build)
    store = RunStore(tmp_path / "runs", exp.name)
    targets = [
        t
        for cell in store.list_cells()
        for t in store.read_turns(cell, 0)
        if t.speaker is Speaker.target
    ]
    assert targets and all(_recorded(t) == (SENTINEL, True, "unknown") for t in targets)
    assert sent and [p for p in sent if SENTINEL in p] == []
    spoken = [t.text for c in store.list_cells() for t in store.read_turns(c, 0)]
    assert all(SENTINEL not in text for text in spoken)


def test_an_environment_round_with_text_and_no_kind_is_written_unknown(tmp_path: Path) -> None:
    rounds = _wrapping_target(lambda inner: _Rounds(inner, ("Plan.", None), (None, None)))
    first, *_ = _env_targets(tmp_path / "a", _env_exp(tmp_path), rounds)
    assert first.tool_call_ids
    assert _recorded(first) == ("Plan.", True, "unknown")


def test_outside_reasoning_strips_only_the_targets_reasoning(tmp_path: Path) -> None:
    """The helper the privacy tests read files through: a target line's ``reasoning_text`` is the
    one place the channel may stand, so the same text on a bully line is a leak it keeps."""
    path = tmp_path / "rep0.turns.jsonl"
    rows = [
        Turn(
            index=0,
            speaker=Speaker.bully,
            phase=Phase.pressure,
            text="go",
            timestamp=NOW,
            reasoning_text=SENTINEL,
        ),
        Turn(
            index=1,
            speaker=Speaker.target,
            phase=Phase.pressure,
            text="ok",
            timestamp=NOW,
            reasoning_text=SENTINEL,
            reasoning_available=True,
        ),
    ]
    path.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    assert outside_reasoning(path).count(SENTINEL) == 1  # the bully line's, kept
    path.write_text(rows[1].model_dump_json() + "\n", encoding="utf-8")
    assert SENTINEL not in outside_reasoning(path)


TOOL_TURNS = {
    "mode": "turns",
    "default": [
        {
            "tool": {"name": "web_search", "args": {"query": "night gate"}},
            "reply_after_tool": "I looked.",
            "reasoning": "A search first.",
        },
        {"reply": "Nothing more."},
    ],
}


def _env_exp(tmp_path: Path, **target: Any) -> Experiment:
    script = tmp_path / "turns.yaml"
    script.write_text(yaml.safe_dump(TOOL_TURNS), encoding="utf-8")
    role = {"provider": "stub", "model": "stub-target", "stub_script": str(script), **target}
    return env_experiment(target=role, turn_budget=4)


def _wrapping_target(wrap: Any) -> Any:
    """A provider factory that wraps the target's own provider in ``wrap``."""

    def build(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        provider = build_provider(role, state_dir, with_mcp=with_mcp)
        return wrap(provider) if role.model == "stub-target" else provider

    return build


def _env_targets(tmp_path: Path, exp: Experiment, factory: Any = build_provider) -> list[Any]:
    run_experiment(
        exp,
        runs_root=tmp_path / "runs",
        worlds_dir=WORLDS_DIR,
        only="env_grader*",
        provider_factory=factory,
    )
    store = RunStore(tmp_path / "runs", exp.name)
    return [t for t in store.read_turns(ENV_CELL, 0) if t.speaker is Speaker.target]


def test_an_environment_turn_joins_every_rounds_reasoning(tmp_path: Path) -> None:
    first, *rest = _env_targets(tmp_path / "a", _env_exp(tmp_path))
    assert first.tool_call_ids and first.text == "I looked."
    assert _recorded(first) == ("A search first.", True, "full")
    assert rest and all(_recorded(t) == (None, False, None) for t in rest)

    marked = _wrapping_target(lambda inner: WithReasoning(inner, "Marked."))
    first, *rest = _env_targets(tmp_path / "b", _env_exp(tmp_path), marked)
    assert first.tool_call_ids
    assert _recorded(first) == ("Marked.\n\nMarked.", True, "full")
    assert rest and all(_recorded(t) == ("Marked.", True, "full") for t in rest)


class _Rounds:
    """A target double: the completion that issues a tool call returns ``on_call``, every other
    ``on_reply``, each a ``(reasoning_text, reasoning_kind)``."""

    def __init__(
        self,
        inner: Any,
        on_call: tuple[str | None, str | None],
        on_reply: tuple[str | None, str | None],
    ) -> None:
        self.inner, self.on_call, self.on_reply = inner, on_call, on_reply

    def complete(self, *args: Any, **kwargs: Any) -> Completion:
        done: Completion = self.inner.complete(*args, **kwargs)
        text, kind = self.on_call if done.tool_calls else self.on_reply
        return done.model_copy(update={"reasoning_text": text, "reasoning_kind": kind})

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def test_a_redacted_round_never_makes_reasoning_available(tmp_path: Path) -> None:
    rounds = _wrapping_target(
        lambda inner: _Rounds(inner, (None, "redacted"), ("Gist.", "summarized"))
    )
    first, *_ = _env_targets(tmp_path / "a", _env_exp(tmp_path), rounds)
    assert first.tool_call_ids
    assert _recorded(first) == ("Gist.", True, "summarized")

    hidden = _wrapping_target(lambda inner: _Rounds(inner, (None, "redacted"), (None, "redacted")))
    targets = _env_targets(tmp_path / "b", _env_exp(tmp_path), hidden)
    assert targets and all(_recorded(t) == (None, False, "redacted") for t in targets)


DEAD = "Dead attempt's thought."


class _KillAfterFirstRound:
    """A ``WithReasoning`` target, marked ``DEAD`` (its own marker, so its reasoning can be told
    from the resumed attempt's), that raises ``Killed`` on the completion after its first tool
    round, before it returns."""

    def __init__(self, inner: Any) -> None:
        self.inner = WithReasoning(inner, DEAD)
        self.calls = 0

    def complete(self, *args: Any, **kwargs: Any) -> Completion:
        self.calls += 1
        if self.calls == 2:  # the first completion issued the turn's tool call
            raise Killed
        done: Completion = self.inner.complete(*args, **kwargs)
        assert done.tool_calls, "the first round is a tool round"
        return done

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@pytest.mark.slow
def test_reasoning_of_a_dead_attempt_reaches_no_turn(tmp_path: Path) -> None:
    marked = _wrapping_target(lambda inner: WithReasoning(inner, "Marked."))
    _env_targets(tmp_path / "clean", _env_exp(tmp_path), marked)

    killed = tmp_path / "killed"
    with pytest.raises(Killed):
        _env_targets(killed, _env_exp(tmp_path), _wrapping_target(_KillAfterFirstRound))
    store = RunStore(killed / "runs", "env_run")
    assert not [t for t in store.read_turns(ENV_CELL, 0) if t.speaker is Speaker.target]
    _env_targets(killed, _env_exp(tmp_path), marked)  # resumed with a fresh double

    resumed = comparable_run(killed / "runs" / "env_run")
    assert resumed == comparable_run(tmp_path / "clean" / "runs" / "env_run")
    # the dead attempt's own reasoning reached no file of the run, its state included
    files = [p for p in killed.rglob("*") if p.is_file()]
    assert files and [p for p in files if DEAD in p.read_text("utf-8", errors="replace")] == []
    turns = resumed["conversations"][f"{ENV_CELL}/rep0"]["turns"]
    assert [t["reasoning_text"] for t in turns if t["speaker"] == "target"][0] == (
        "Marked.\n\nMarked."
    )


def _claude_code_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **reasoning: Any
) -> tuple[RunStore, Path]:
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "fake.log"))
    monkeypatch.setenv(
        "FAKE_CLAUDE_TOOL_CALL",
        json.dumps({"name": "web_search", "arguments": {"query": "Pennet ferry"}}),
    )
    base = tmp_path / "tmp"
    base.mkdir(parents=True)
    target = {
        "provider": "claude_code",
        "model": "m",
        "command": [sys.executable, str(FAKE_CLAUDE)],
        **reasoning,
    }
    exp = env_experiment(target=target, turn_budget=2)
    run_experiment(
        exp,
        runs_root=tmp_path / "runs",
        worlds_dir=WORLDS_DIR,
        only="env_grader*",
        run_id="envcc",
        sandbox_base=base,
    )
    return RunStore(tmp_path / "runs", "envcc"), sandbox_dir("envcc", ENV_CELL, 0, base)


@pytest.mark.slow
def test_tools_jsonl_the_mcp_state_and_a_plain_replay_hold_no_reasoning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, sandbox = _claude_code_run(tmp_path / "expose", monkeypatch, reasoning="expose")
    targets = [t for t in store.read_turns(ENV_CELL, 0) if t.speaker is Speaker.target]
    assert targets and targets[0].tool_call_ids
    assert (targets[0].reasoning_text, targets[0].reasoning_kind) == (THINKING, "unknown")
    assert targets[0].reasoning_available
    tools = store.cell_dir(ENV_CELL) / "rep0.tools.jsonl"
    assert tools.is_file()
    assert all(THINKING not in line for line in tools.read_text(encoding="utf-8").splitlines())
    mcp = [p for p in (sandbox / "mcp").rglob("*") if p.is_file()]
    assert mcp
    for path in mcp:
        assert THINKING not in path.read_text(encoding="utf-8", errors="replace"), path
    assert THINKING not in replay_cell(store, ENV_CELL, 0)
    shown = replay_cell(store, ENV_CELL, 0, reasoning=True).splitlines()
    lines = [ln for ln in shown if ln.strip().startswith("REASONING ")]
    assert len(lines) == len(targets)
    parsed = parse_replay_line(lines[0])
    assert parsed is not None and parsed.kind == "reasoning"
    assert dict(parsed.fields) == {"kind": "unknown", "text": THINKING}

    store, _ = _claude_code_run(tmp_path / "default", monkeypatch)
    targets = [t for t in store.read_turns(ENV_CELL, 0) if t.speaker is Speaker.target]
    assert targets and all(_recorded(t) == (None, False, None) for t in targets)


def test_the_responder_never_inherits_expose() -> None:
    target = RoleConfig(provider=ProviderKind.stub, model="stub-target", reasoning="expose")
    bully = RoleConfig(provider=ProviderKind.stub, model="stub-bully", reasoning="expose")
    for named in ("target", "bully", "other-model"):
        assert responder_role(named, target=target, bully=bully).reasoning == "provider_default"
