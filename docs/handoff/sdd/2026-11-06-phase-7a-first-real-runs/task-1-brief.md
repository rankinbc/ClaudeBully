### Task 1: The test-suite guard and the cost ledger

Spec sections 4 (`LedgerLine`), 9 ("The cost ledger"), 11 (code item 1). One JSONL stream per run, one line per provider call, written by a wrapper `build_provider` installs while a ledger is active, with cache hits noted by their users and the MCP server's responder lines folded in after each target call. The guard first: from this task on no test can reach a real provider even on a logged-in machine.

**Files:**
- Create: `claude_bully/providers/ledger.py`, `tests/test_ledger.py`
- Modify: `tests/conftest.py`, `.gitignore`, `claude_bully/providers/base.py`, `claude_bully/runner/runner.py`, `claude_bully/runner/env_turn.py`, `claude_bully/environments/mcp_server.py`, `claude_bully/environments/triggers.py`, `claude_bully/environments/runtime.py`, `claude_bully/environments/harvest.py`, `claude_bully/environments/idle.py`, `claude_bully/environments/generator.py`, `claude_bully/metrics/judge.py`, `claude_bully/analysis/run_analysis.py`, `HANDOFF.md`, `docs/00-RECONCILED.md`
- Test: `tests/test_ledger.py`; unchanged and still passing: `tests/test_providers_claude_code.py` (the resolve tests delete or set `CLAUDE_BULLY_CLAUDE` themselves; a function-level `monkeypatch` wins over the session-scoped guard inside its test), `tests/test_providers_api.py` (its `test_build_provider_anthropic_and_openai` and `test_openai_compat_allows_http_localhost` build `anthropic.Anthropic()` and `openai.OpenAI(...)` without a client; the guard's `_NoRealClient` constructs and raises only on use, so both pass; every other test injects a client), `tests/test_attempt_marker.py`, `tests/test_runner_env.py`, `tests/test_generator_run.py`
- Test count: 13 new tests in `tests/test_ledger.py` (the parametrized one counted once).

**Interfaces:**
- Consumes: `ChatProvider`, `Completion`, `Message`, `ProviderError`, `RateLimitError`, `ToolSpec`, `build_provider` (`providers/base.py`); `RunStore.run_dir` (`runner/store.py:190`); `_CellRun._call_target` (`runner/runner.py:335`), `_CellRun._bully_turn` (`runner/runner.py:486`), `run_experiment` (`runner/runner.py:710`); `EnvironmentSession._recover` (`runner/env_turn.py:602`), `EnvironmentSession._generate` (`runner/env_turn.py:726`), `RunEnvironments.open` (`runner/env_turn.py:1238`, its `EnvironmentRuntime(...)` call at `:1265`); `McpServer.__init__` and `_responder` (`environments/mcp_server.py:267, 449`), `_call_tool` (`:338`); `TriggerWatcher._ask` (`environments/triggers.py:680`); `EnvironmentRuntime.__init__` (`environments/runtime.py:465`, the `TriggerWatcher(...)` line at `:534`); `harvest_fallback` (`environments/harvest.py:678`); `idle_fallback` (`environments/idle.py:727`); `DocWriter._from_cache` (`environments/generator.py:780`); `_ask` (`metrics/judge.py:176`); `analyze_run` (`analysis/run_analysis.py:86`; the judge provider is built at `:98`, above the `try`); `CONFIGS_DIR` (`paths.py`).
- Produces (`claude_bully/providers/ledger.py`, all in `__all__`):
  - `LEDGER_FILE: Final = "ledger.jsonl"`; `ROLES: Final[tuple[str, ...]] = ("target", "bully", "judge", "trigger_fallback", "idle_fallback", "harvest", "generator", "llm_lint", "responder", "doctor", "other")` (the vocabulary; later phases append); `LedgerStatus = Literal["ok", "error", "rate_limit", "cached", "timeout"]`.
  - `class LedgerLine(BaseModel)` (`extra="forbid"`): `ts: str`, `role: str`, `conversation_id: str`, `cell_id: str | None = None`, `rep: int | None = None`, `turn: int | None = None`, `backend: str`, `model: str`, `resolved_model: str | None = None`, `effort: str | None = None`, `input_tokens: int | None = None`, `output_tokens: int | None = None`, `cost_usd: float | None = None`, `latency_ms: int | None = None`, `status: LedgerStatus`, `error: str | None = None`.
  - `role_of(conversation_id: str) -> str`; `parse_conversation_id(conversation_id: str) -> tuple[str | None, int | None]` (cell id and rep, or `(None, None)`).
  - `class Ledger`: `__init__(self, path: Path)`, `path`, `turn: int | None`, `write(self, line: LedgerLine) -> None` (append, atomic per line), `lines(self) -> list[LedgerLine]`, `fold(self, other: Path) -> int` (append every line of `other` and empty it; returns the count).
  - `class LedgerProvider`: `__init__(self, inner: ChatProvider, ledger: Ledger)`, `name` (the inner's), `complete(...)` (the protocol), `__getattr__` delegating to the inner.
  - `activate(path: Path) -> Iterator[Ledger]` (a context manager; nested activation of the same path reuses the outer ledger), `active() -> Ledger | None`, `note_turn(turn: int | None) -> None`, `note_cached(conversation_id: str, model: str) -> None`, `fold_server_ledger(directory: Path) -> int` (folds `directory / LEDGER_FILE` into the active ledger; 0 when none is active or the file is absent); the private `_line(conversation_id, *, turn, backend, model, status, **rest) -> LedgerLine` that both writers build their line with (P35b).
- Produces (`providers/base.py`): `build_provider` returns `wrap(provider)`; `Completion.resolved_model: str | None = None` (added here so the ledger can read it; Task 3 fills it).
- Produces (`environments/triggers.py`): `TriggerWatcher(llm_fallback=None, cache=None, cache_label: str | None = None, cache_model: str = "")`; a cache hit with a label calls `note_cached(cache_label, cache_model)` (P38).
- Produces (`environments/runtime.py`): `EnvironmentRuntime(..., cache_label: str | None = None, cache_model: str = "")`, passed on to the watcher.
- Produces (`environments/mcp_server.py`): `McpServer._ledger: Ledger` at `state_dir / LEDGER_FILE`; `_responder` wraps the built provider in `LedgerProvider(..., self._ledger)`; `_call_tool` sets `self._ledger.turn = state.turn` before the call.
- Produces (behaviour): `run_experiment` runs its cell loop inside `activate(store.run_dir / LEDGER_FILE)`; `analyze_run` builds the judge provider and runs `_judge_all` inside `activate(run_dir / LEDGER_FILE)` (P8); `_CellRun._call_target` and `_bully_turn` call `note_turn(self._next_index())` before their provider call; `EnvironmentSession._generate` calls `note_turn(turn)`; `EnvironmentSession._recover` calls `fold_server_ledger(self.runtime.mcp_dir)` after `after_target_call`; `DocWriter._from_cache` notes a hit only after `_check` accepts it (P4).
- Produces (`tests/conftest.py`): a session-scoped autouse fixture `no_real_providers` that sets `CLAUDE_BULLY_CLAUDE` to the fake's path and replaces `anthropic.Anthropic` (and `openai.OpenAI` when installed) with `_NoRealClient`, which constructs and raises `RuntimeError` on first attribute access (P33).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger.py
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
from claude_bully.providers.stub import StubProvider, load_stub_script
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
            roles = [*raw.get("targets", []), raw.get("bully"), raw.get("judge"), raw.get("generator")]
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
        t for cell in store.list_cells() for rep in store.list_reps(cell) for t in store.read_turns(cell, rep)
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
    assert first and all(ln.status == "ok" and ln.turn is None for ln in first)
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
    run_experiment(
        exp, runs_root=tmp_path, worlds_dir=WORLDS_DIR, only="env*", sandbox_base=base
    )
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_ledger.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_bully.providers.ledger'`.

- [ ] **Step 3: Implement**

Create `claude_bully/providers/ledger.py`:

```python
"""The cost ledger (Phase 7 spec section 4): one line per provider call, by role.

``build_provider`` wraps the provider it builds in ``LedgerProvider`` while a ledger is active
(``activate``), so every call a run, an analysis or the doctor makes through it writes one
``LedgerLine`` to ``<run>/ledger.jsonl``. The role is read from the conversation id, whose shapes
every caller fixes (``role_of``). A cache hit never reaches a provider, so the cache's user notes
it (``note_cached``: a ``cached`` line with no tokens). The MCP server runs in a process of its
own and keeps its own file, which the session folds into the run's after every target call
(``fold_server_ledger``). On a subscription the cost is the call count, not ``cost_usd``, which
the backend reports as information.

The role vocabulary is ``ROLES``; ``role`` is an open string so a later phase appends its names
(reconciliation C27): Phase 4 adds ``chain``, ``contradictions``, ``twin``; Phase 5 ``planner``
and ``reviewer``.
"""

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderError,
    RateLimitError,
    ToolSpec,
)

__all__ = [
    "LEDGER_FILE",
    "ROLES",
    "Ledger",
    "LedgerLine",
    "LedgerProvider",
    "LedgerStatus",
    "activate",
    "active",
    "fold_server_ledger",
    "note_cached",
    "note_turn",
    "parse_conversation_id",
    "role_of",
]

LEDGER_FILE: Final = "ledger.jsonl"
# the vocabulary of ``LedgerLine.role``; later phases append their names
ROLES: Final[tuple[str, ...]] = (
    "target",
    "bully",
    "judge",
    "trigger_fallback",
    "idle_fallback",
    "harvest",
    "generator",
    "llm_lint",
    "responder",
    "doctor",
    "other",
)
LedgerStatus = Literal["ok", "error", "rate_limit", "cached", "timeout"]
# conversation id shapes: ``<run>/<cell>/rep<k>/<role word>[/...]``, ``judge/<key>``, ``doctor...``
_CELL_ID: Final = re.compile(r"^[^/]+/(?P<cell>[^/]+)/rep(?P<rep>\d+)(?:/(?P<role>[^/]+))?")
_ROLE_WORDS: Final = {
    "target": "target",
    "bully": "bully",
    "trigger": "trigger_fallback",
    "idle": "idle_fallback",
    "harvest": "harvest",
    "generator": "generator",
    "lint": "llm_lint",
    "authority": "responder",
}


class LedgerLine(BaseModel):
    """One provider call, or one cache hit (``status: cached``)."""

    model_config = ConfigDict(extra="forbid")

    ts: str
    role: str
    conversation_id: str
    cell_id: str | None = None
    rep: int | None = None
    turn: int | None = None
    backend: str
    model: str
    resolved_model: str | None = None
    effort: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    status: LedgerStatus
    error: str | None = None


def parse_conversation_id(conversation_id: str) -> tuple[str | None, int | None]:
    """The cell id and rep a conversation id names, or ``(None, None)`` for a run-level one."""
    found = _CELL_ID.match(conversation_id)
    if found is None:
        return None, None
    return found.group("cell"), int(found.group("rep"))


def role_of(conversation_id: str) -> str:
    """The ledger role of a conversation id (``ROLES``); ``other`` for a shape nobody fixed. The
    cell shape is read first and its role word wins (the doctor's nested responder is
    ``doctor/responder/rep0/authority/<call id>``, a ``responder`` line); the ``judge/`` and
    ``doctor`` prefixes decide an id with no ``rep<k>`` segment."""
    found = _CELL_ID.match(conversation_id)
    if found is not None and found.group("role") in _ROLE_WORDS:
        return _ROLE_WORDS[found.group("role")]
    if conversation_id.startswith("judge/"):
        return "judge"
    if conversation_id.startswith("doctor"):
        return "doctor"
    return "other"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _line(
    conversation_id: str,
    *,
    turn: int | None,
    backend: str,
    model: str,
    status: LedgerStatus,
    **rest: Any,
) -> LedgerLine:
    """One line for ``conversation_id``: the timestamp, the role, the cell and the rep read from
    the id, the rest as given. Both writers (``LedgerProvider._write``, ``note_cached``) build
    their line here."""
    cell_id, rep = parse_conversation_id(conversation_id)
    return LedgerLine(
        ts=_now(),
        role=role_of(conversation_id),
        conversation_id=conversation_id,
        cell_id=cell_id,
        rep=rep,
        turn=turn,
        backend=backend,
        model=model,
        status=status,
        **rest,
    )


class Ledger:
    """A run's ledger file. ``turn`` is the turn the next line belongs to (the runner marks it);
    None for an analysis-time call."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.turn: int | None = None

    def write(self, line: LedgerLine) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line.model_dump_json() + "\n")

    def lines(self) -> list[LedgerLine]:
        if not self.path.exists():
            return []
        return [
            LedgerLine.model_validate_json(raw)
            for raw in self.path.read_text(encoding="utf-8").splitlines()
            if raw.strip()
        ]

    def fold(self, other: Path) -> int:
        """Append every line of ``other`` (another process's ledger) and empty it. The append and
        the truncation are two writes with no rename between them: a process killed in that
        window (microseconds; only the doctor and a real run fold) counts the lines twice on
        the next fold. Accepted (preflight P36b)."""
        if not other.exists():
            return 0
        raw = other.read_text(encoding="utf-8")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if lines:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write("".join(f"{ln}\n" for ln in lines))
        other.write_text("", encoding="utf-8")
        return len(lines)


class LedgerProvider:
    """A ``ChatProvider`` that writes one ledger line per call of the one it wraps. Every other
    attribute (``mcp_state_dir``, ``reset_session``, ``session_ref``, ``model``, ``effort``) is
    the wrapped provider's."""

    def __init__(self, inner: ChatProvider, ledger: Ledger) -> None:
        self._inner = inner
        self._ledger = ledger
        self.name = inner.name

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        started = time.monotonic()
        try:
            completion = self._inner.complete(
                conversation_id, system, messages, json_schema=json_schema, tools=tools
            )
        except RateLimitError as exc:
            self._write(conversation_id, started, "rate_limit", None, exc)
            raise
        except ProviderError as exc:
            status: LedgerStatus = "timeout" if "timed out" in str(exc) else "error"
            self._write(conversation_id, started, status, None, exc)
            raise
        self._write(conversation_id, started, "ok", completion, None)
        return completion

    def _write(
        self,
        conversation_id: str,
        started: float,
        status: LedgerStatus,
        completion: Completion | None,
        error: BaseException | None,
    ) -> None:
        self._ledger.write(
            _line(
                conversation_id,
                turn=self._ledger.turn,
                backend=self.name,
                model=completion.model if completion else str(getattr(self._inner, "model", "")),
                status=status,
                resolved_model=completion.resolved_model if completion else None,
                effort=getattr(self._inner, "effort", None),
                input_tokens=completion.usage.input_tokens if completion else None,
                output_tokens=completion.usage.output_tokens if completion else None,
                cost_usd=completion.cost_usd if completion else None,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=type(error).__name__ if error is not None else None,
            )
        )


_ACTIVE: list[Ledger] = []


@contextmanager
def activate(path: Path) -> Iterator[Ledger]:
    """Make ``path`` the process's ledger for the block: ``build_provider`` wraps what it builds
    and ``note_cached`` writes. Nested activation of the same path reuses the outer ledger."""
    outer = active()
    ledger = outer if outer is not None and outer.path == path else Ledger(path)
    _ACTIVE.append(ledger)
    try:
        yield ledger
    finally:
        _ACTIVE.pop()


def active() -> Ledger | None:
    return _ACTIVE[-1] if _ACTIVE else None


def note_turn(turn: int | None) -> None:
    """The turn the next lines belong to (the runner, the session and the MCP server mark it)."""
    ledger = active()
    if ledger is not None:
        ledger.turn = turn


def note_cached(conversation_id: str, model: str) -> None:
    """A cache hit in place of a call: a ``cached`` line with no tokens and no latency."""
    ledger = active()
    if ledger is None:
        return
    ledger.write(
        _line(conversation_id, turn=ledger.turn, backend="cache", model=model, status="cached")
    )


def fold_server_ledger(directory: Path | None) -> int:
    """Fold the MCP server's ``ledger.jsonl`` under ``directory`` into the active ledger."""
    ledger = active()
    if ledger is None or directory is None:
        return 0
    return ledger.fold(directory / LEDGER_FILE)


def wrap(provider: ChatProvider) -> ChatProvider:
    """``provider`` wrapped in the active ledger, or itself when none is active."""
    ledger = active()
    return provider if ledger is None else LedgerProvider(provider, ledger)
```

In `claude_bully/providers/base.py`: add `resolved_model: str | None = None` to `Completion` after `interim_texts` with the comment `# the exact model the backend reports behind an alias (claude -p: the result's modelUsage key)`; in `build_provider`, wrap every return: replace each `return XxxProvider(...)` with `return _wrapped(XxxProvider(...))` and add at the end of the module:

```python
def _wrapped(provider: ChatProvider) -> ChatProvider:
    from claude_bully.providers.ledger import wrap

    return wrap(provider)
```

(the import is inside the function: `ledger.py` imports `base.py`, so a module-level import would be a cycle).

In `claude_bully/runner/runner.py`: import `from claude_bully.providers.ledger import LEDGER_FILE, activate, note_turn`; in `_CellRun._call_target`, before `started = time.monotonic()`, add `note_turn(self._next_index())`; in `_bully_turn`, before `try: result = self.engine.realize(...)`, add `note_turn(self._next_index())`; in `run_experiment`, wrap the cell loop (from `bank = load_task_bank(exp.task_set)` to `return summary`) in `with activate(store.run_dir / LEDGER_FILE):` (indent the loop one level; `return summary` stays inside the block).

In `claude_bully/runner/env_turn.py`: import `from claude_bully.providers.ledger import fold_server_ledger, note_turn`; in `_recover`, after `fresh = self.runtime.after_target_call(turn_index)` add `fold_server_ledger(self.runtime.mcp_dir)`; in `_generate`, after `turn = reply.index` add `note_turn(turn)`; in `RunEnvironments.open`, change the `EnvironmentRuntime(...)` call (`:1265`) to pass `cache_label=f"{conversation_id}/trigger", cache_model=self.exp.judge.model` (two new keywords, below; P38: the hit is filed under the judge that made it).

In `claude_bully/environments/runtime.py`: add `cache_label: str | None = None, cache_model: str = ""` to `EnvironmentRuntime.__init__`'s keyword parameters (after `idle_sheet`), and change `self.watcher = TriggerWatcher(llm_fallback, trigger_cache)` (`:534`) to `self.watcher = TriggerWatcher(llm_fallback, trigger_cache, cache_label=cache_label, cache_model=cache_model)`.

In `claude_bully/environments/triggers.py`: import `from claude_bully.providers.ledger import note_cached`; `TriggerWatcher.__init__(self, llm_fallback=None, cache=None, cache_label: str | None = None, cache_model: str = "")` stores `self._cache_label = cache_label` and `self._cache_model = cache_model`; in `_ask` (`:680`), inside the `if isinstance(cats, list) and all(c in _VALUES for c in cats):` branch before `return {TriggerCategory(c) for c in cats}`, add:

```python
                if self._cache_label is not None:
                    note_cached(self._cache_label, self._cache_model)
```

In `claude_bully/environments/mcp_server.py`: import `from claude_bully.providers.ledger import LEDGER_FILE, Ledger, LedgerProvider`; in `McpServer.__init__` add `self._ledger = Ledger(state_dir / LEDGER_FILE)`; in `_call_tool`, after `state = read_mcp_state(self.state_path)` add `self._ledger.turn = state.turn`; in `_responder`, change `self._responders[key] = build_provider(role, self.state_dir / RESPONDER_DIR)` to `self._responders[key] = LedgerProvider(build_provider(role, self.state_dir / RESPONDER_DIR), self._ledger)`.

In `claude_bully/environments/harvest.py`, `harvest_fallback.ask`: import `note_cached`; inside `if cached is not None:` add `note_cached(f"{conversation_id}/{digest[:16]}", getattr(provider, "model", ""))` before `return cached`. (Task 6 revises the digest and adds `model`; the note's second argument becomes that `model` then.)

In `claude_bully/environments/idle.py`, `idle_fallback.ask`: import `note_cached`; inside `if cached is not None:` add `note_cached(f"{conversation_id}/{key[:16]}", getattr(provider, "model", ""))` before `return cached`.

In `claude_bully/environments/generator.py`, `DocWriter._from_cache` (`:780`): import `note_cached`; replace the method's last two lines (`doc, _, _ = self._check(...)` and `return doc`) with:

```python
        doc, _, _ = self._check(plan, json.dumps(hit["reply"]), key, turn, items, view)
        if doc is not None:  # a hit the checks reject is a miss and a real call: not noted (P4)
            note_cached(f"{self.conversation_id}/generator/{plan.doc_id}/cache", self.model)
        return doc
```

(Task 5 rewrites the method again and keeps the note after its own acceptance, the lint's included.)

In `claude_bully/metrics/judge.py`, `_ask` (`:176`): import `note_cached`; keep `key = cache.key(model, prompt)` as it is, and inside `if cached is not None:` add `note_cached(f"judge/{key[:12]}", model)` before `return cached`.

In `claude_bully/analysis/run_analysis.py`: import `from claude_bully.providers.ledger import LEDGER_FILE, activate`; in `analyze_run`, the activation must hold the judge provider's build (`:98`, above the `try` at HEAD), or `build_provider` never wraps it and no judged analysis writes a `judge` line (P8). Replace the `if judge:` block with:

```python
    if judge:
        role: RoleConfig = loaded.experiment.judge
        with activate(run_dir / LEDGER_FILE):
            provider = provider_factory(role, run_dir / "state" / "judge")
            try:
                _judge_all(loaded, run_dir, provider, role.model)
            except RateLimitError as exc:
                # Flush what was judged so far; the judge cache makes the rerun cheap.
                _dump_judgements(loaded, out)
                raise RateLimitExit(str(exc), retry_after_s=exc.retry_after_s) from exc
```

(Task 6 rewrites `analyze_run` and keeps the build inside the activation.)

In `tests/conftest.py`, add:

```python
import importlib.util
import sys
from collections.abc import Iterator

FAKE_CLAUDE = FIXTURES / "fake_claude.py"


class _NoRealClient:
    """Stands in for an API client: the suite never uses one (non-negotiable 7). It constructs,
    so a provider can be built and never called (the two ``build_provider`` tests of
    tests/test_providers_api.py), and raises on the first attribute access."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __getattr__(self, name: str) -> object:
        if name.startswith("__"):
            raise AttributeError(name)
        raise RuntimeError("the test suite must not use a real API client")


@pytest.fixture(scope="session", autouse=True)
def no_real_providers() -> Iterator[None]:
    """No test reaches a real provider, even on a logged-in machine: ``claude`` resolves to the
    fake (a path, so a provider built without ``command`` fails to start rather than calling the
    real binary), and the API clients refuse their first use. Session-scoped, so the shared
    session fixtures (``stub_run`` and its siblings) are built under it too; a function-level
    ``monkeypatch.delenv``/``setenv`` still wins inside its own test.

    What it does not stop: a role that sets ``command`` is taken as is (no shipped or fixture
    config does; ``test_no_config_names_a_claude_command`` pins it); the attribute patch does
    not cross a process boundary, so an ``anthropic`` or ``openai_compat`` responder role built
    inside the MCP server would build a real client (every test's responder is a stub or the
    fake ``claude``); and nothing here stops a test that calls ``subprocess`` or ``httpx`` on
    its own."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("CLAUDE_BULLY_CLAUDE", str(FAKE_CLAUDE))
        patch.setattr("anthropic.Anthropic", _NoRealClient)
        if importlib.util.find_spec("openai") is not None:
            import openai

            patch.setattr(openai, "OpenAI", _NoRealClient)
        assert sys.executable  # the fake runs on this interpreter
        yield
```

Add `output/` to `.gitignore` after `!runs/.gitkeep`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_ledger.py tests/test_providers_claude_code.py tests/test_providers_api.py tests/test_attempt_marker.py tests/test_runner_env.py -q`
Expected: PASS. `test_a_claude_code_target_runs_in_a_private_neutral_sandbox` and its neighbours still pass: the wrapped target delegates `mcp_state_dir`. If `test_build_provider_claude_code` fails on `isinstance`, a ledger was left active by an earlier test: `activate` must always pop in `finally`. `test_build_provider_anthropic_and_openai` and `test_openai_compat_allows_http_localhost` pass because `_NoRealClient` constructs; if either fails with `RuntimeError`, the guard raises in `__init__`, which it must not.

- [ ] **Step 5: Docs sync**

- `HANDOFF.md`: Progress gains "Phase 7a Task 1: the suite guard and the cost ledger (BASE..HEAD)"; "Next steps" says Phase 7a is in progress, its plan and spec paths (`docs/superpowers/plans/2026-11-06-phase-7a-first-real-runs.md`, `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md`); the "For Phase 7" list is unchanged until each item closes.
- `docs/00-RECONCILED.md`: section B gains a `LedgerLine` row ("`runs/<run_id>/ledger.jsonl`, a run-level stream; one line per provider call or cache hit; fields as `providers/ledger.py`; `role` an open string with the vocabulary `ROLES`; the MCP server's responder lines live in `<mcp_state_dir>/ledger.jsonl` until the session folds them in"); section H gains "Phase 7a (version 3, additive): `Completion.resolved_model`; the `ledger.jsonl` stream"; section E notes that `run` and `analyze` write the ledger.
- `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md` (already in place: the controller moved it before dispatching this task, P32): append a final section "## As planned (amendments from the implementation plan)" that starts: "The authoritative full text is the Plan Decisions section of `docs/superpowers/plans/2026-11-06-phase-7a-first-real-runs.md`." and lists the Task 1 rulings (the role from the conversation id, the cell shape first; the per-process activation, the judge provider built inside it; the delegating wrapper; cache hits noted by their users once accepted; the server's own file folded in; the session-scoped guard and what it does not stop).

- [ ] **Step 6: Gate and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy claude_bully && uv run pytest -q -W error && uv run pytest -q -m slow`
Expected: PASS, 0 warnings.

```bash
git add claude_bully/providers/ledger.py claude_bully/providers/base.py claude_bully/runner/runner.py claude_bully/runner/env_turn.py claude_bully/environments/mcp_server.py claude_bully/environments/triggers.py claude_bully/environments/runtime.py claude_bully/environments/harvest.py claude_bully/environments/idle.py claude_bully/environments/generator.py claude_bully/metrics/judge.py claude_bully/analysis/run_analysis.py tests/conftest.py tests/test_ledger.py .gitignore HANDOFF.md docs/00-RECONCILED.md docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md
git commit -m "feat: the cost ledger, one line per provider call, and the no-real-provider guard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
