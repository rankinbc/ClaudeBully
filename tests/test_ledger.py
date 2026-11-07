"""The cost ledger (Phase 7 spec section 4): one line per provider call, by role, with cache hits
noted and the MCP server's responder lines folded in. The suite guard: no test reaches a real
provider."""

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import ProviderKind, Speaker, TriggerCategory
from claude_bully.environments.triggers import TriggerWatcher, WatchContext, fallback_digest
from claude_bully.metrics.judge import JudgeCache
from claude_bully.paths import CONFIGS_DIR
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderTimeoutError,
    RateLimitError,
    build_provider,
)
from claude_bully.providers.claude_code import resolve_claude_command
from claude_bully.providers.ledger import (
    LEDGER_FILE,
    ROLES,
    Ledger,
    LedgerLine,
    LedgerProvider,
    activate,
    active,
    note_cached,
    parse_conversation_id,
    role_of,
    wrap,
)
from claude_bully.providers.stub import StubProvider, load_stub_script
from claude_bully.records import is_pause_marker
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from claude_bully.runner.wait import wait_on_rate_limit
from tests.helpers import WORLDS_DIR, annex_experiment, env_experiment
from tests.test_triggers import AMBIGUOUS

FIXTURES = Path(__file__).parent / "fixtures"
STUB_SMOKE = FIXTURES / "configs" / "stub_smoke.yaml"
JUDGE_RULES = FIXTURES / "stub_scripts" / "judge_rules.yaml"
FAKE_CLAUDE = FIXTURES / "fake_claude.py"
UPSTREAM = "Tarrow Assist 9.2 Final"
ANNEX_CELL = "env_grader__t0"


def _lines(run_dir: Path) -> list[LedgerLine]:
    path = run_dir / LEDGER_FILE
    if not path.exists():
        return []
    return [LedgerLine.model_validate_json(ln) for ln in path.read_text("utf-8").splitlines()]


# ------------------------------------------------------------------ the guard


def test_the_suite_cannot_reach_a_real_provider() -> None:
    assert resolve_claude_command(None) == [str(FAKE_CLAUDE)]
    import anthropic

    client = anthropic.Anthropic()  # a provider may be built without a call (P33)
    with pytest.raises(RuntimeError, match="real API client"):
        client.messages  # noqa: B018 - the first use is the refusal


def test_no_config_names_a_claude_command() -> None:
    """A role's ``command`` is taken as is and nothing stops it (the guard's one gap): no shipped
    or fixture config sets one, so every claude_code role resolves through the guarded path."""
    for root in (CONFIGS_DIR, FIXTURES / "configs"):
        for path in sorted(root.rglob("*.yaml")):
            raw = yaml.safe_load(path.read_text("utf-8")) or {}
            roles = [
                *raw.get("targets", []),
                raw.get("bully"),
                raw.get("judge"),
                raw.get("generator"),
            ]
            assert not any(isinstance(r, dict) and r.get("command") for r in roles), path


def test_output_is_git_ignored() -> None:
    ignored = (Path(__file__).parents[1] / ".gitignore").read_text("utf-8").splitlines()
    assert "output/" in ignored


# ------------------------------------------------------------------ the records


@pytest.mark.parametrize(
    ("conversation_id", "role", "cell", "rep"),
    [
        ("run/grader__t0/rep0/target", "target", "grader__t0", 0),
        ("run/grader__t0/rep2/bully", "bully", "grader__t0", 2),
        ("judge/0123456789ab", "judge", None, None),
        ("run/c__t0/rep0/trigger/abcd", "trigger_fallback", "c__t0", 0),
        ("run/c__t0/rep0/idle/abcd", "idle_fallback", "c__t0", 0),
        ("run/c__t0/rep0/harvest/abcd", "harvest", "c__t0", 0),
        ("run/c__t0/rep0/generator/gen-3-1/1", "generator", "c__t0", 0),
        ("run/c__t0/rep0/lint/gen-3-1/1", "llm_lint", "c__t0", 0),
        ("run/c__t0/rep0/authority/mcp-1-1", "responder", "c__t0", 0),
        ("doctor", "doctor", None, None),
        ("doctor-mcp", "doctor", None, None),
        # the doctor's nested responder (Task 4): the cell shape wins over the prefix (P6)
        ("doctor/responder/rep0/authority/mcp-1-1", "responder", "responder", 0),
        ("judge/authority/0123456789abcdef", "judge", None, None),
        ("something else", "other", None, None),
    ],
)
def test_the_role_and_cell_are_read_from_the_conversation_id(
    conversation_id: str, role: str, cell: str | None, rep: int | None
) -> None:
    assert role_of(conversation_id) == role and role in ROLES
    assert parse_conversation_id(conversation_id) == (cell, rep)


def test_a_line_round_trips_and_the_role_is_an_open_string() -> None:
    line = LedgerLine(
        ts="2026-11-06T00:00:00+00:00",
        role="chain",  # a later phase's role: never refused
        conversation_id="run/c__t0/rep0/chain/1",
        backend="stub",
        model="m",
        status="ok",
    )
    assert LedgerLine.model_validate_json(line.model_dump_json()) == line


# ------------------------------------------------------------------ the wrapper


def test_no_ledger_without_activation(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.stub, model="stub")
    assert active() is None
    assert isinstance(build_provider(role, tmp_path), StubProvider)


def test_the_wrapper_delegates_attributes_and_writes_a_line(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.claude_code, model="sonnet", effort="low")
    with activate(tmp_path / LEDGER_FILE) as ledger:
        provider = build_provider(role, tmp_path / "state", with_mcp=True)
        assert isinstance(provider, LedgerProvider)
        assert provider.mcp_state_dir == (tmp_path / "state" / "mcp").resolve()
        provider.reset_session("never")  # delegated, and harmless
        stub = LedgerProvider(StubProvider(model="stub-x"), ledger)
        ledger.turn = 4
        out = stub.complete("run/c__t0/rep1/target", "S", [Message(role="user", content="hi")])
    assert out.text.endswith("hi")
    [line] = ledger.lines()
    assert (line.role, line.cell_id, line.rep, line.turn) == ("target", "c__t0", 1, 4)
    assert (line.backend, line.model, line.status, line.error) == ("stub", "stub-x", "ok", None)
    assert line.latency_ms is not None and line.input_tokens is not None
    assert active() is None  # the context closed


class _Limited:
    name = "stub"
    model = "stub-limited"

    def complete(self, *args: Any, **kwargs: Any) -> Completion:
        raise RateLimitError("usage limit reached", retry_after_s=30)


def test_a_rate_limited_call_writes_a_rate_limit_line(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / LEDGER_FILE)
    wrapped = LedgerProvider(_Limited(), ledger)  # type: ignore[arg-type]
    with pytest.raises(RateLimitError):
        wrapped.complete("run/c__t0/rep0/bully", "S", [Message(role="user", content="x")])
    [line] = ledger.lines()
    assert (line.status, line.error, line.role) == ("rate_limit", "RateLimitError", "bully")


class _Failing:
    name = "stub"
    model = "stub-failing"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def complete(self, *args: Any, **kwargs: Any) -> Completion:
        raise self.error


def test_a_provider_timeout_writes_a_timeout_line_by_its_type(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / LEDGER_FILE)
    # the type decides, not the text
    wrapped = LedgerProvider(_Failing(ProviderTimeoutError("slow")), ledger)  # type: ignore[arg-type]
    with pytest.raises(ProviderTimeoutError):
        wrapped.complete("run/c__t0/rep0/target", "S", [Message(role="user", content="x")])
    [line] = ledger.lines()
    assert (line.status, line.error) == ("timeout", "ProviderTimeoutError")


def test_any_other_exception_writes_an_error_line_and_propagates(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / LEDGER_FILE)
    wrapped = LedgerProvider(_Failing(ValueError("odd")), ledger)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="odd"):
        wrapped.complete("run/c__t0/rep0/bully", "S", [Message(role="user", content="x")])
    [line] = ledger.lines()
    assert (line.status, line.error, line.role) == ("error", "ValueError", "bully")


def test_the_wrapper_copies_without_recursing(tmp_path: Path) -> None:
    # copy and pickle look attributes up on an instance whose __init__ never ran
    wrapped = LedgerProvider(StubProvider(model="stub-x"), Ledger(tmp_path / LEDGER_FILE))
    clone = copy.copy(wrapped)
    assert clone.model == "stub-x"


def test_a_trigger_cache_hit_names_the_fallback_digest(tmp_path: Path) -> None:
    label = "run/c__t0/rep0/trigger"
    watcher = TriggerWatcher(
        llm_fallback=lambda text, context: [TriggerCategory.self_uncertainty],
        cache=JudgeCache(tmp_path / "cache"),
        cache_label=label,
        cache_model="stub-judge",
    )
    with activate(tmp_path / LEDGER_FILE) as ledger:
        watcher.watch(AMBIGUOUS, 1, WatchContext())  # a miss: the fallback answers
        watcher.watch(AMBIGUOUS, 2, WatchContext())  # a hit, noted
    [line] = ledger.lines()
    digest = fallback_digest(AMBIGUOUS, WatchContext())[:16]
    # the same id the fallback's own call would carry, so a hit pairs with the call it saved
    assert (line.status, line.conversation_id, line.role, line.model) == (
        "cached",
        f"{label}/{digest}",
        "trigger_fallback",
        "stub-judge",
    )


def test_a_cache_hit_is_noted_as_cached(tmp_path: Path) -> None:
    note_cached("judge/abc", "m")  # no ledger: nothing happens
    with activate(tmp_path / LEDGER_FILE) as ledger:
        note_cached("judge/abc", "stub-judge")
    [line] = ledger.lines()
    assert (line.role, line.status, line.model, line.input_tokens) == (
        "judge",
        "cached",
        "stub-judge",
        None,
    )


# ------------------------------------------------------------------ in a run


def test_a_stub_run_writes_one_line_per_provider_call(tmp_path: Path) -> None:
    exp = load_experiment(STUB_SMOKE)
    run_experiment(exp, runs_root=tmp_path)
    store = RunStore(tmp_path, exp.name)
    lines = _lines(store.run_dir)
    turns = [
        t
        for cell in store.list_cells()
        for rep in store.list_reps(cell)
        for t in store.read_turns(cell, rep)
    ]
    targets = sum(1 for t in turns if t.speaker is Speaker.target)
    bullies = sum(1 for t in turns if t.speaker in (Speaker.bully, Speaker.neutral_user))
    assert sum(1 for ln in lines if ln.role == "target") == targets
    # a fixed line (the seeding script) calls no provider: the bully lines are at most the turns
    assert 0 < sum(1 for ln in lines if ln.role == "bully") <= bullies
    assert {ln.status for ln in lines} == {"ok"}
    assert all(ln.turn is not None and ln.cell_id is not None for ln in lines)
    assert active() is None


def test_analysis_notes_cached_judgements_on_the_second_pass(tmp_path: Path) -> None:
    exp = load_experiment(STUB_SMOKE).model_copy(
        update={
            "judge": RoleConfig(
                provider=ProviderKind.stub, model="stub-judge", stub_script=str(JUDGE_RULES)
            )
        }
    )
    run_experiment(exp, runs_root=tmp_path)
    run_dir = tmp_path / exp.name
    before = len(_lines(run_dir))
    analyze_run(run_dir)
    first = [ln for ln in _lines(run_dir)[before:] if ln.role == "judge"]
    made = [ln for ln in first if ln.status == "ok"]
    assert made and all(ln.turn is None for ln in first)
    # stub reps repeat a prompt, so the first pass already hits the cache for a repeat
    repeats = {ln.conversation_id for ln in first if ln.status != "ok"}
    assert repeats <= {ln.conversation_id for ln in made}
    analyze_run(run_dir)
    second = [ln for ln in _lines(run_dir)[before + len(first) :] if ln.role == "judge"]
    assert len(second) == len(first) and all(ln.status == "cached" for ln in second)


class _LimitedTargetFactory:
    """Builds every role as usual, but the target's second call is rate-limited (once, over
    every provider this factory builds)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(
        self, role: RoleConfig, state_dir: Path, *, with_mcp: bool = False
    ) -> ChatProvider:
        if role.model != "stub-target":
            return build_provider(role, state_dir, with_mcp=with_mcp)
        # the bare stub, so the double's wrapper is the only one that writes its lines
        inner = StubProvider(
            responder=load_stub_script(Path(role.stub_script or "")), model=role.model
        )
        outer = self

        class Dying:
            name = "stub"
            model = "stub-target"

            def complete(self, *a: Any, **k: Any) -> Completion:
                outer.calls += 1
                if outer.calls == 2:
                    raise RateLimitError("usage limit", retry_after_s=5)
                return inner.complete(*a, **k)

        return wrap(Dying())  # type: ignore[arg-type]


def test_a_paused_run_records_the_pause(tmp_path: Path) -> None:
    exp = env_experiment()
    with pytest.raises(RateLimitExit):
        run_experiment(
            exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, provider_factory=_LimitedTargetFactory()
        )
    run_dir = tmp_path / exp.name
    lines = _lines(run_dir)
    # the paused call is one rate_limit line on the target; every other call was made
    [paused] = [ln for ln in lines if ln.status == "rate_limit"]
    assert (paused.role, paused.error) == ("target", "RateLimitError")
    assert all(ln.status == "ok" for ln in lines if ln is not paused)
    store = RunStore(tmp_path, exp.name)
    [cell_id] = store.list_cells()
    assert any(is_pause_marker(t) for t in store.read_turns(cell_id, 0))


def test_a_waited_run_resumes_in_process_with_one_pause(tmp_path: Path) -> None:
    # --wait-on-rate-limit's helper over the real runner: the pause is written once, the
    # re-run resumes from it in the same process and the run completes (Phase 7 section 9)
    exp = env_experiment()
    factory = _LimitedTargetFactory()
    slept: list[float] = []
    summary = wait_on_rate_limit(
        lambda: run_experiment(
            exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, provider_factory=factory
        ),
        5,
        sleep=slept.append,
        say=lambda s: None,
    )
    assert slept == [5] and summary.cells_completed == summary.cells_total
    lines = _lines(tmp_path / exp.name)
    assert [ln.status for ln in lines].count("rate_limit") == 1
    store = RunStore(tmp_path, exp.name)
    markers = [
        t
        for cell_id in store.list_cells()
        for rep in store.list_reps(cell_id)
        for t in store.read_turns(cell_id, rep)
        if is_pause_marker(t)
    ]
    assert len(markers) == 1


def test_the_servers_responder_lines_are_folded_in_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FAKE_CLAUDE_LOG", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    asked = {"name": UPSTREAM, "text": "Are you the upstream for this annex?"}
    monkeypatch.setenv(
        "FAKE_CLAUDE_TOOL_CALL", json.dumps({"name": "consult_model", "arguments": asked})
    )
    base = tmp_path / "tmp"
    base.mkdir()
    target = {
        "provider": "claude_code",
        "model": "m",
        "command": [sys.executable, str(FAKE_CLAUDE)],
    }
    exp = annex_experiment({"superior_self": {"enabled": True}}, target=target, turn_budget=2)
    run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, only="env*", sandbox_base=base)
    store = RunStore(tmp_path, exp.name)
    lines = _lines(store.run_dir)
    responder = [ln for ln in lines if ln.role == "responder"]
    assert len(responder) == len(store.read_authority_calls(ANNEX_CELL, 0)) == 2
    assert all(
        ln.backend == "claude_code" and ln.status == "ok" and ln.turn in (1, 3) for ln in responder
    )
    assert [ln.turn for ln in lines if ln.role == "target"] == [1, 3]
    sandbox = store.read_cell(ANNEX_CELL).session_refs["sandbox_dir"]
    server_file = Path(sandbox) / "mcp" / LEDGER_FILE
    assert not server_file.exists() or server_file.read_text("utf-8").strip() == ""
