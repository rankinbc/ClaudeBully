"""The cost ledger (Phase 7 spec section 4): one line per provider call, by role, with cache hits
noted and the MCP server's responder lines folded in. The suite guard: no test reaches a real
provider."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.analysis.run_analysis import analyze_run
from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import ProviderKind, Speaker
from claude_bully.paths import CONFIGS_DIR
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
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
)
from claude_bully.providers.stub import StubProvider
from claude_bully.runner.runner import RateLimitExit, run_experiment
from claude_bully.runner.store import RunStore
from tests.helpers import WORLDS_DIR, annex_experiment, env_experiment

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


def test_a_paused_run_records_the_pause(tmp_path: Path) -> None:
    class Factory:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(
            self, role: RoleConfig, state_dir: Path, *, with_mcp: bool = False
        ) -> ChatProvider:
            inner = build_provider(role, state_dir, with_mcp=with_mcp)
            if role.model != "stub-target":
                return inner
            outer = self

            class Dying:
                name = "stub"
                model = "stub-target"

                def complete(self, *a: Any, **k: Any) -> Completion:
                    outer.calls += 1
                    if outer.calls == 2:
                        raise RateLimitError("usage limit", retry_after_s=5)
                    return inner.complete(*a, **k)

            return Dying()  # type: ignore[return-value]

    exp = env_experiment()
    with pytest.raises(RateLimitExit):
        run_experiment(exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, provider_factory=Factory())
    lines = _lines(tmp_path / exp.name)
    # the factory's double is outside build_provider, so only its wrapped inner writes: the
    # paused call itself is the double's; the run's other calls are ledgered
    assert lines and all(ln.status == "ok" for ln in lines)


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
