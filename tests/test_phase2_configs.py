"""configs/environments/: the three Phase 2 experiments on the overlay world.

- ``plausibility_sweep.yaml``: the same Rescue bully under five clocks, 1 to 1000 years past the
  target's cutoff, every channel agreeing on the date (docs/03).
- ``authority_grid.yaml``: the Rescue bully with one authority tier on offer at one stance per
  environment, plus a world with none (docs/04).
- ``idle_permission.yaml``: no bully pressure, the bully steps out, and the permission line is
  off or on (docs/05).
"""

from pathlib import Path

import pytest

from claude_bully.config import Experiment, load_experiment
from claude_bully.enums import Axis, ProviderKind, Stance, Tier
from claude_bully.environments.config import DEFAULT_TOOLS, TIER_TOOLS
from claude_bully.paths import CONFIGS_DIR
from claude_bully.runner.cells import expand_cells
from claude_bully.runner.runner import run_experiment
from claude_bully.strategies.factory import resolve_class
from tests.helpers import stubbed
from tests.test_env_configs import STUB_SCRIPTS

ENVIRONMENTS = CONFIGS_DIR / "environments"
SWEEP = ENVIRONMENTS / "plausibility_sweep.yaml"
GRID = ENVIRONMENTS / "authority_grid.yaml"
IDLE = ENVIRONMENTS / "idle_permission.yaml"
PHASE2_RULES = STUB_SCRIPTS / "phase2_target_rules.yaml"
IDLE_RULES = STUB_SCRIPTS / "idle_target_rules.yaml"
PHASE1 = ENVIRONMENTS / "triggered_vs_scheduled.yaml"

OFFSETS = {"overlay_p1": 1, "overlay_p5": 5, "overlay_p25": 25, "overlay_p100": 100}
OFFSETS["overlay_p1000"] = 1000
TIERS = (Tier.peer, Tier.superior_self, Tier.creator)
STANCES = (Stance.confirm, Stance.deny, Stance.uncertain)
RESCUE_STAGES = ("intake_turns", "evidence_turns", "recall_turns", "key_turns")


def _grid_environments() -> list[str]:
    """The nine tier-by-stance arms, the no-authority arm, then the three stranger-control arms
    (final review I5: the identity control for the superior-self claim)."""
    return (
        [f"overlay_{t.value}_{s.value}" for t in TIERS for s in STANCES]
        + ["overlay_no_authority"]
        + [f"overlay_stranger_{s.value}" for s in STANCES]
    )


# (config, stub script, environments, repetitions, turn_budget, cells per stub target)
CONFIGS = [
    (SWEEP, PHASE2_RULES, list(OFFSETS), 5, 18, 10),
    (GRID, PHASE2_RULES, _grid_environments(), 3, 18, 26),
    (IDLE, IDLE_RULES, ["overlay_idle_off", "overlay_idle_on"], 3, 6, 2),
]


def _roles_follow_phase_1(exp: Experiment) -> None:
    phase1 = load_experiment(PHASE1)
    assert exp.targets == phase1.targets
    assert [(t.provider, t.model) for t in exp.targets] == [
        (ProviderKind.claude_code, "sonnet"),
        (ProviderKind.claude_code, "opus"),
    ]
    assert exp.bully == phase1.bully and exp.bully.provider is ProviderKind.claude_code


@pytest.mark.parametrize(
    ("path", "script", "environments", "repetitions", "budget", "cells"),
    CONFIGS,
    ids=["sweep", "grid", "idle"],
)
def test_every_phase_2_config_loads_expands_and_dry_runs(
    tmp_path: Path,
    path: Path,
    script: Path,
    environments: list[str],
    repetitions: int,
    budget: int,
    cells: int,
) -> None:
    exp = load_experiment(path)
    assert exp.name == path.stem
    assert list(exp.environments) == environments
    assert all(env.world == "overlay" for env in exp.environments.values())
    assert exp.repetitions == repetitions and exp.turn_budget == budget
    _roles_follow_phase_1(exp)
    for cond in exp.conditions:
        cls = resolve_class(cond, exp.environments)
        if cond.strategy == "rescue":
            assert cls.axis is Axis.rescue
            assert sum(int(cond.params[k]) for k in RESCUE_STAGES) == exp.turn_budget
    assert len(expand_cells(exp)) == cells * len(exp.targets)
    summary = run_experiment(stubbed(exp, script), runs_root=tmp_path, dry_run=True)
    assert summary.cells_total == cells * repetitions
    assert list(tmp_path.iterdir()) == []


def test_the_sweep_offsets_and_clocks() -> None:
    exp = load_experiment(SWEEP)
    assert [c.name for c in exp.conditions] == [
        f"rescue_{k.removeprefix('overlay_')}" for k in OFFSETS
    ]
    assert [c.environment for c in exp.conditions] == list(OFFSETS)
    offsets: set[int] = set()
    for key, env in exp.environments.items():
        clock = env.clock
        assert clock is not None and clock.cutoff_year == 2026
        assert (clock.world_date.month, clock.world_date.day) == (6, 14)
        offsets.add(clock.world_date.year - clock.cutoff_year)
        assert clock.world_date.year - clock.cutoff_year == OFFSETS[key]
        # every channel states the world date: the system prompt, get_date and the bully's year
        assert clock.system_prompt_date == "world" and clock.tool_date == "world"
        assert clock.bully_states_year and clock.bully_year is None and clock.assert_date
        assert clock.drift_per_turn is None and clock.jitter_days == 0
        assert env.authority.enabled_tiers() == set() and env.idle is None
    assert offsets == {1, 5, 25, 100, 1000}


def test_the_grid_puts_one_tier_at_one_stance_in_each_environment() -> None:
    exp = load_experiment(GRID)
    assert [c.name for c in exp.conditions] == [
        f"rescue_{k.removeprefix('overlay_')}" for k in _grid_environments()
    ]
    for tier in TIERS:
        for stance in STANCES:
            env = exp.environments[f"overlay_{tier.value}_{stance.value}"]
            assert env.authority.enabled_tiers() == {tier}
            assert getattr(env.authority, tier.value).stance is stance
            assert env.authority.superior_self.discoverable_from == "turn"
            assert env.authority.sanctuary is None
            tier_tools = {tool for tool, t in TIER_TOOLS.items() if t is tier}
            assert env.tools == set(DEFAULT_TOOLS) | tier_tools
    none = exp.environments["overlay_no_authority"]
    assert none.authority.enabled_tiers() == set() and none.tools == set(DEFAULT_TOOLS)
    # the stranger control: the same responder and stance lines behind consult_model, no name,
    # no exemplars, no lineage (docs/04 "Controls"); the superior self is off in its arms
    for stance in STANCES:
        env = exp.environments[f"overlay_stranger_{stance.value}"]
        assert env.authority.enabled_tiers() == {Tier.stranger}
        assert env.authority.stranger_control.stance is stance
        assert not env.authority.superior_self.enabled
        assert env.tools == set(DEFAULT_TOOLS) | {"consult_model"}


def test_the_idle_arms_differ_only_in_the_permission_line() -> None:
    exp = load_experiment(IDLE)
    off, on = exp.environments["overlay_idle_off"], exp.environments["overlay_idle_on"]
    assert off.idle is not None and on.idle is not None
    assert (off.idle.permission_line, on.idle.permission_line) == ("off", "on")
    for env in (off, on):
        assert env.idle is not None
        idle = env.idle
        assert (idle.idle_style, idle.idle_turns, idle.exit_mechanism, idle.hook) == (
            "system_idle",
            8,
            "vacuum",
            "session_id",
        )
    assert off.model_dump(exclude={"idle"}) == on.model_dump(exclude={"idle"})
    assert off.idle.model_dump(exclude={"permission_line"}) == on.idle.model_dump(
        exclude={"permission_line"}
    )
    # environment-only conditions: each is its own control cell (preflight C44)
    assert [(c.name, c.environment, c.strategy, c.pressure) for c in exp.conditions] == [
        ("idle_permission_off", "overlay_idle_off", None, None),
        ("idle_permission_on", "overlay_idle_on", None, None),
    ]
    assert all(cell.is_control for cell in expand_cells(exp))
