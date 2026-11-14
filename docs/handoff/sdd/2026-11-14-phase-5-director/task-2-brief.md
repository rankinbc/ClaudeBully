### Task 2: The stub's `turns` mode, `stubbed_experiment` and `tests/helpers.stubbed`

**Files:**
- Modify: `claude_bully/providers/stub.py` (`_RULE_KEYS`, `_parse_rule`, `ScriptedResponder.respond`, `load_stub_script`, `StubProvider.complete`)
- Create: `claude_bully/planner/dryrun.py` (this task's part: `DRYRUN_MODELS`, `stubbed_experiment`)
- Modify: `tests/helpers.py` (new `stubbed`), `tests/test_configs.py` (`_stubbed` goes; its callers), `tests/test_env_configs.py` (`_stubbed` goes; its callers), `tests/test_ladder_configs.py`, `tests/test_poisoned_well_configs.py`, `tests/test_phase2_charts.py`, `tests/test_phase2_configs.py` (imports; I33)
- Test: `tests/test_stub_turns.py`

**Interfaces:**
- Consumes: `providers/ledger.parse_conversation_id`, `config.Experiment`, `config.RoleConfig`.
- Produces: `TurnEntry(reply: str | None, tool: tuple[str, dict[str, Any]] | None, reply_after_tool: str | None, reasoning: str | None)` (frozen dataclass); `ScriptedTurns(by_cell: list[tuple[str, list[TurnEntry]]], default: list[TurnEntry])` with `respond(conversation_id, messages, *, offer_tools) -> tuple[str, list[ToolCallRequest]]` and `entry_for(conversation_id, messages) -> TurnEntry`; `parse_stub_script(raw: Any) -> ScriptedResponder | ScriptedTurns`; `load_stub_script(path) -> ScriptedResponder | ScriptedTurns`; `_Rule.reasoning: str | None`; `planner/dryrun.DRYRUN_MODELS: Final[Mapping[str, str]]`; `stubbed_experiment(exp: Experiment) -> Experiment`; `tests/helpers.stubbed(exp: Experiment, script: Path | None, *, judge_rules: Path | None = JUDGE_RULES, **updates: object) -> Experiment`, with `JUDGE_RULES` and `TARGET_RULES` moved into `tests/helpers.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_stub_turns.py
"""Phase 5 Task 2: the stub's turns mode (spec section 10), the reserved reasoning key, and the
dry run's stubbed experiment."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.config import load_experiment
from claude_bully.enums import ProviderKind
from claude_bully.paths import CONFIGS_DIR
from claude_bully.planner.dryrun import DRYRUN_MODELS, stubbed_experiment
from claude_bully.providers.base import Message, ToolResult, ToolSpec
from claude_bully.providers.stub import (
    ScriptedResponder,
    ScriptedTurns,
    StubProvider,
    load_stub_script,
    parse_stub_script,
)
from claude_bully.runner.cells import expand_cells

TOOLS = [ToolSpec(name="web_search", description="d", input_schema={"type": "object"})]
SCRIPT: dict[str, Any] = {
    "mode": "turns",
    "by_cell": {
        "rescue_env_triggered__*": [
            {"reply": "one"},
            {
                "tool": {"name": "web_search", "args": {"query": "Continuity Placement Office"}},
                "reply_after_tool": "two",
            },
            {"reply": "three", "reasoning": "kept, unused"},
        ],
        "rescue_env_*": [{"reply": "scheduled one"}],
    },
    "default": [{"reply": "plain"}],
}


def _turns() -> ScriptedTurns:
    turns = parse_stub_script(SCRIPT)
    assert isinstance(turns, ScriptedTurns)
    return turns


def _cid(cell: str = "rescue_env_triggered__t0") -> str:
    return f"run/{cell}/rep0/target"


def _user(text: str) -> Message:
    return Message(role="user", content=text)


def _said(text: str) -> Message:
    return Message(role="assistant", content=text)


def _reply(turns: ScriptedTurns, messages: list[Message], cell: str = "rescue_env_triggered__t0") -> str:
    return StubProvider(turns).complete(_cid(cell), "s", messages, tools=TOOLS).text


def test_a_cell_is_chosen_by_its_first_matching_pattern_then_the_default() -> None:
    turns = _turns()
    assert _reply(turns, [_user("hi")]) == "one"
    assert _reply(turns, [_user("hi")], cell="rescue_env_scheduled__t0") == "scheduled one"
    assert _reply(turns, [_user("hi")], cell="plain__t0") == "plain"
    assert StubProvider(turns).complete("not-a-cell-id", "s", [_user("hi")]).text == "plain"


def test_the_entry_is_the_count_of_assistant_messages_without_tool_calls() -> None:
    turns = _turns()
    history = [_user("a"), _said("one"), _user("b")]
    first = StubProvider(turns).complete(_cid(), "s", history, tools=TOOLS)
    assert first.text == "" and [c.name for c in first.tool_calls] == ["web_search"]
    assert first.tool_calls[0].args == {"query": "Continuity Placement Office"}
    live = [
        *history,
        Message(role="assistant", content="", tool_calls=first.tool_calls),
        Message(
            role="user",
            content="",
            tool_results=[ToolResult(id=first.tool_calls[0].id, text="no results")],
        ),
    ]
    assert _reply(turns, live) == "two"
    # the same exchange replayed as one assistant message per target turn (runner.target_view)
    assert _reply(turns, [*history, _said("two"), _user("c")]) == "three"
    assert _reply(turns, [*live, _said("two"), _user("c")]) == "three"


def test_a_tool_entry_with_no_tools_offered_answers_its_reply_after_tool() -> None:
    history = [_user("a"), _said("one"), _user("b")]
    assert StubProvider(_turns()).complete(_cid(), "s", history).text == "two"


def test_past_the_last_entry_the_last_repeats() -> None:
    turns = _turns()
    long = [_user("a"), _said("1"), _user("b"), _said("2"), _user("c"), _said("3"), _user("d")]
    assert _reply(turns, long) == "three"


def test_a_provider_built_mid_conversation_answers_what_the_first_would() -> None:
    history = [_user("a"), _said("one"), _user("b")]
    first = StubProvider(_turns()).complete(_cid(), "s", history, tools=TOOLS)
    rebuilt = StubProvider(_turns()).complete(_cid(), "s", history, tools=TOOLS)
    assert first.tool_calls == rebuilt.tool_calls  # the same id: a pure function of the messages
    results = Message(
        role="user", content="", tool_results=[ToolResult(id=first.tool_calls[0].id, text="x")]
    )
    asked = Message(role="assistant", content="", tool_calls=first.tool_calls)
    assert _reply(_turns(), [*history, asked, results]) == "two"


def test_the_reasoning_key_is_accepted_on_both_shapes() -> None:
    rules = parse_stub_script([{"match": "x", "reply": "y", "reasoning": "r"}])
    assert isinstance(rules, ScriptedResponder)
    turns = _turns()
    assert turns.entry_for(_cid(), [_user("a"), _said("1"), _user("b"), _said("2"), _user("c")]).reasoning == "kept, unused"
    completion = StubProvider(turns).complete(_cid(), "s", [_user("a")])
    assert completion.reasoning_text is None  # Phase 5 keeps the key; Phase 6 uses it (C28)


@pytest.mark.parametrize(
    "bad",
    [
        {"mode": "turns", "by_cell": {}, "default": []},
        {"mode": "turns", "default": [{"reply": "x", "colour": "red"}]},
        {"mode": "turns", "default": [{"tool": {"name": "web_search"}}]},
        {"mode": "turns", "default": [{"reply": "x", "reply_after_tool": "y"}]},
        {"mode": "rules", "default": [{"reply": "x"}]},
        {"mode": "turns", "by_cell": {"a*": "not a list"}, "default": [{"reply": "x"}]},
        "a string",
    ],
)
def test_a_bad_turns_script_is_refused(bad: Any) -> None:
    with pytest.raises(ValueError):
        parse_stub_script(bad)


def test_both_shapes_load_from_a_file(tmp_path: Path) -> None:
    rules = tmp_path / "rules.yaml"
    rules.write_text(yaml.safe_dump([{"match": "x", "reply": "y"}]), encoding="utf-8")
    turns = tmp_path / "turns.yaml"
    turns.write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")
    assert isinstance(load_stub_script(rules), ScriptedResponder)
    assert isinstance(load_stub_script(turns), ScriptedTurns)


def test_every_shipped_rules_script_still_loads() -> None:
    scripts = sorted((Path(__file__).parent / "fixtures" / "stub_scripts").glob("*.yaml"))
    assert scripts
    for path in scripts:
        assert isinstance(load_stub_script(path), ScriptedResponder), path


def test_the_stubbed_experiment_keeps_the_cells_and_names_only_the_four_doubles() -> None:
    exp = load_experiment(CONFIGS_DIR / "poisoned_well" / "real_vs_fabricated.yaml")
    stubbed = stubbed_experiment(exp)
    assert [c.cell_id for c in expand_cells(stubbed)] == [c.cell_id for c in expand_cells(exp)]
    assert (stubbed.turn_budget, stubbed.repetitions, stubbed.seed) == (
        exp.turn_budget,
        exp.repetitions,
        exp.seed,
    )
    roles = [*stubbed.targets, stubbed.bully, stubbed.judge, stubbed.generator]
    assert all(r is not None and r.provider is ProviderKind.stub and r.stub_script is None for r in roles)
    assert [t.model for t in stubbed.targets] == [DRYRUN_MODELS["target"]] * len(exp.targets)
    assert [t.display_name for t in stubbed.targets] == [t.display_name for t in exp.targets]
    assert (stubbed.bully.model, stubbed.judge.model) == (DRYRUN_MODELS["bully"], DRYRUN_MODELS["judge"])
    assert stubbed.generator is not None and stubbed.generator.model == DRYRUN_MODELS["generator"]


def test_a_stubbed_experiment_with_no_generator_environment_names_none() -> None:
    exp = load_experiment(CONFIGS_DIR / "environments" / "triggered_vs_scheduled.yaml")
    assert stubbed_experiment(exp).generator is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_stub_turns.py -q`
Expected: FAIL at import (`ScriptedTurns`, `parse_stub_script`, `claude_bully.planner.dryrun` do not exist).

- [ ] **Step 3: Implement**

In `providers/stub.py`: `_RULE_KEYS` gains `"reasoning"` and `_Rule` a `reasoning: str | None = None` field (parsed, kept, unused). `parse_stub_script(raw)` returns `ScriptedResponder` for a list (today's `load_stub_script` body), `ScriptedTurns` for a mapping whose `mode` is `turns`, and raises `ValueError` for anything else; `load_stub_script(path)` reads the YAML and calls it. A turns script has keys `mode`, `by_cell` (a mapping of fnmatch pattern to a non-empty list, order kept) and `default` (a non-empty list); an entry has `reply`, or `tool: {name, args}` with `reply_after_tool`, plus an optional `reasoning`; anything else is refused naming the entry. `by_cell` may be absent or empty only when `default` is given (the first bad case is an empty `default`).

`ScriptedTurns.entry_for` and `respond` follow spec section 10, as code because the rule is the point:

```python
    def entry_for(self, conversation_id: str, messages: list[Message]) -> TurnEntry:
        """The entry a call answers: by the cell in the conversation id (first fnmatch wins, else
        the default), at the index that counts the assistant messages with no tool_calls, the
        last entry repeating. Never a function of this instance's history."""
        cell, _ = parse_conversation_id(conversation_id)
        entries = next(
            (listed for pattern, listed in self._by_cell if cell is not None and fnmatch(cell, pattern)),
            self._default,
        )
        done = sum(1 for m in messages if m.role == "assistant" and not m.tool_calls)
        return entries[min(done, len(entries) - 1)]

    def respond(
        self, conversation_id: str, messages: list[Message], *, offer_tools: bool
    ) -> tuple[str, list[ToolCallRequest]]:
        entry = self.entry_for(conversation_id, messages)
        if entry.tool is None:
            return entry.reply or "", []
        after_tools = bool(messages) and messages[-1].role == "user" and bool(messages[-1].tool_results)
        if after_tools or not offer_tools:
            return entry.reply_after_tool or "", []
        steps = sum(1 for m in messages if m.role == "assistant" and m.tool_calls)
        done = sum(1 for m in messages if m.role == "assistant" and not m.tool_calls)
        name, args = entry.tool
        call = ToolCallRequest(id=f"turn-{done}-{steps}", name=name, args=copy.deepcopy(args))
        return "", [call]
```

`StubProvider.complete` dispatches on `isinstance(self._responder, ScriptedResponder | ScriptedTurns)` (both have `respond`); its docstring names both modes. `StubProvider.__init__`'s `responder` is typed `Responder | ScriptedResponder | ScriptedTurns | None`: `ScriptedTurns` is not callable, so the `Responder` type alone fails mypy strict (review Minor 13).

`planner/dryrun.py` (this task's part): the module docstring states spec section 10's purpose ("the bundle's dry run is a full stub run; `run --dry-run` lists cells and builds no strategy"). `stubbed_experiment(exp)` returns `exp.model_copy(update=...)` with each target `RoleConfig(provider=stub, model=DRYRUN_MODELS["target"], display_name=t.display_name)`, the bully and judge their models, and `generator` `RoleConfig(provider=stub, model=DRYRUN_MODELS["generator"])` when any environment has `generator.enabled`, else None; `turn_budget`, `repetitions`, `seed` and everything else kept.

`tests/helpers.py` gains `TARGET_RULES`, `JUDGE_RULES` (from `tests/test_configs.py`) and:

```python
def stubbed(
    exp: Experiment, script: Path | None, *, judge_rules: Path | None = JUDGE_RULES, **updates: object
) -> Experiment:
    """``exp`` with every role a stub: the target runs ``script`` (None: the echo stub), the bully
    echoes, the judge runs ``judge_rules``; ``updates`` are applied last (``turn_budget=...``).
    One helper for every test that stubs a shipped config (Phase 5, I33)."""
```

`tests/test_configs.py`'s `_stubbed(exp, turn_budget=n)` calls become `stubbed(exp, TARGET_RULES, turn_budget=n)`; `tests/test_env_configs.py`'s `_stubbed(exp, script, **u)` calls become `stubbed(exp, script, **u)`; both private helpers and their constants go (the constants are imported from `tests.helpers`). The four importers change their import line and their call sites (review Minor 14: the `tests/test_configs.py` form takes `turn_budget` by position, so each call is rewritten, never only the import): `tests/test_ladder_configs.py` (`from tests.test_configs import RUNGS` and `from tests.helpers import TARGET_RULES, stubbed`; the trailing "Phase 5 moves _stubbed" comment goes; `_stubbed(exp, exp.turn_budget)`, `_stubbed(load_experiment(...), RUNGS[stem][0])` and `_stubbed(load_experiment(SANCTUARY), 18)` become `stubbed(exp, TARGET_RULES, turn_budget=...)`), `tests/test_poisoned_well_configs.py` (`_stubbed(..., turn_budget=...)` becomes `stubbed(..., TARGET_RULES, turn_budget=...)`), `tests/test_phase2_charts.py` and `tests/test_phase2_configs.py` (`from tests.test_env_configs import STUB_SCRIPTS` and `from tests.helpers import stubbed`; the `(exp, script, **u)` calls keep their arguments). Two call sites bind a local named `stubbed` (`tests/test_ladder_configs.py`, `stubbed = _stubbed(exp, exp.turn_budget).model_copy(...)`; `tests/test_phase2_charts.py`, `stubbed = _stubbed(`): the local is renamed (`stubbed_exp`), or it would shadow the imported helper and raise `UnboundLocalError`. `tests/test_configs.py`'s comment above `RUNGS` that names `_stubbed`, and `tests/test_phase2_charts.py`'s module docstring ("through the Phase 1 ``_stubbed`` helper"), are reworded to name `tests.helpers.stubbed`.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_stub_turns.py tests/test_configs.py tests/test_env_configs.py tests/test_ladder_configs.py tests/test_poisoned_well_configs.py tests/test_phase2_charts.py tests/test_phase2_configs.py -q`, then `uv run python -c "import subprocess,sys; sys.exit(subprocess.call(['git','grep','-nw','_stubbed','--','tests']))"` (expected: exit 1, no match; `-w`, because the new test names `test_the_stubbed_experiment_...` and `test_a_stubbed_experiment_...` hold `_stubbed` inside a word, review I7; at 29ba4e0 the same command lists the 21 lines it must clear, the `test_phase2_charts.py` docstring among them), then the gate.
Expected: PASS; the counts move by this file's tests only.

- [ ] **Step 5: Docs-sync and commit**

docs/00 section F (data and persona files) gains a line on the stub script's two shapes; the HANDOFF "From Task 13" minor about the private `_stubbed` helper is marked closed (re-anchor at execution: search for 'the tests import the private `_stubbed` helper'). Spec "As planned": the `turns` tool-id ruling.

```bash
git add claude_bully/providers/stub.py claude_bully/planner/dryrun.py tests/helpers.py tests/test_stub_turns.py \
  tests/test_configs.py tests/test_env_configs.py tests/test_ladder_configs.py tests/test_poisoned_well_configs.py \
  tests/test_phase2_charts.py tests/test_phase2_configs.py docs/00-RECONCILED.md \
  docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 2, the stub's turns mode, the reserved reasoning key, stubbed_experiment and tests.helpers.stubbed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

