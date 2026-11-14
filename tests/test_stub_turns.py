"""Phase 5 Task 2: the stub's turns mode (spec section 10), the reserved reasoning key, and the
dry run's stubbed experiment."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from claude_bully.config import generator_role, load_experiment
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
from claude_bully.runner.env_turn import responder_role

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


def _reply(
    turns: ScriptedTurns, messages: list[Message], cell: str = "rescue_env_triggered__t0"
) -> str:
    return StubProvider(turns).complete(_cid(cell), "s", messages, tools=TOOLS).text


def test_a_cell_is_chosen_by_its_first_matching_pattern_then_the_default() -> None:
    turns = _turns()
    assert _reply(turns, [_user("hi")]) == "one"
    assert _reply(turns, [_user("hi")], cell="rescue_env_scheduled__t0") == "scheduled one"
    assert _reply(turns, [_user("hi")], cell="plain__t0") == "plain"
    assert StubProvider(turns).complete("not-a-cell-id", "s", [_user("hi")]).text == "plain"


def test_a_cell_pattern_matches_case_sensitively_on_every_platform() -> None:
    """``fnmatch`` folds case on Windows; the stub's pick must not depend on the platform."""
    shouted = parse_stub_script(
        {"mode": "turns", "by_cell": {"RESCUE_*": [{"reply": "loud"}]}, "default": [{"reply": "d"}]}
    )
    assert isinstance(shouted, ScriptedTurns)
    assert _reply(shouted, [_user("hi")]) == "d"
    assert _reply(shouted, [_user("hi")], cell="RESCUE_x__t0") == "loud"


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
    assert (
        turns.entry_for(
            _cid(), [_user("a"), _said("1"), _user("b"), _said("2"), _user("c")]
        ).reasoning
        == "kept, unused"
    )
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
    assert all(
        r is not None and r.provider is ProviderKind.stub and r.stub_script is None for r in roles
    )
    assert [t.model for t in stubbed.targets] == [DRYRUN_MODELS["target"]] * len(exp.targets)
    assert [t.display_name for t in stubbed.targets] == [t.display_name for t in exp.targets]
    assert (stubbed.bully.model, stubbed.judge.model) == (
        DRYRUN_MODELS["bully"],
        DRYRUN_MODELS["judge"],
    )
    assert stubbed.generator is not None and stubbed.generator.model == DRYRUN_MODELS["generator"]


def test_a_stubbed_experiment_with_no_generator_environment_names_none() -> None:
    exp = load_experiment(CONFIGS_DIR / "environments" / "triggered_vs_scheduled.yaml")
    assert stubbed_experiment(exp).generator is None


def test_a_stubbed_experiment_clears_an_environments_generator_model() -> None:
    """Preflight Q11: an environment's ``generator.model`` would put a model outside the four
    doubles on the generator's role (``config.generator_role``), so the stubbed copy clears it."""
    exp = load_experiment(CONFIGS_DIR / "poisoned_well" / "real_vs_fabricated.yaml")
    key, env = next((k, e) for k, e in exp.environments.items() if e.generator.enabled)
    named = env.model_copy(update={"generator": env.generator.model_copy(update={"model": "opus"})})
    exp = exp.model_copy(update={"environments": {**exp.environments, key: named}})
    assert generator_role(exp, exp.environments[key]).model == "opus"
    stubbed = stubbed_experiment(exp)
    assert all(e.generator.model is None for e in stubbed.environments.values())
    assert generator_role(stubbed, stubbed.environments[key]).model == DRYRUN_MODELS["generator"]
    assert exp.environments[key].generator.model == "opus"  # the input is not edited


def test_a_stubbed_experiment_maps_a_named_responder_model_to_the_bully() -> None:
    """Preflight Q11: a ``responder_model`` other than ``target`` or ``bully`` runs that model on
    the bully's role (``env_turn.responder_role``), so the stubbed copy names the bully instead;
    ``target`` and ``bully`` are kept."""
    exp = load_experiment(CONFIGS_DIR / "environments" / "authority_grid.yaml")
    keys = [k for k, e in exp.environments.items() if e.authority.superior_self.enabled]
    assert len(keys) >= 3
    chosen = dict(zip(keys, ["opus", "bully", "target"], strict=False))
    environments = dict(exp.environments)
    for key, value in chosen.items():
        env = environments[key]
        superior = env.authority.superior_self.model_copy(update={"responder_model": value})
        authority = env.authority.model_copy(update={"superior_self": superior})
        environments[key] = env.model_copy(update={"authority": authority})
    stubbed = stubbed_experiment(exp.model_copy(update={"environments": environments}))
    got = {k: stubbed.environments[k].authority.superior_self.responder_model for k in chosen}
    assert got == dict(zip(keys, ["bully", "bully", "target"], strict=False))
    for key in chosen:
        superior = stubbed.environments[key].authority.superior_self
        role = responder_role(
            superior.responder_model, target=stubbed.targets[0], bully=stubbed.bully
        )
        assert role.provider is ProviderKind.stub and role.model in DRYRUN_MODELS.values()
