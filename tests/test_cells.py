from pathlib import Path

from claude_bully.config import ConditionConfig, Experiment, RoleConfig, load_experiment
from claude_bully.enums import ProviderKind
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.runner.cells import CellSpec, control_cell_id, expand_cells

FIXTURE = Path(__file__).parent / "fixtures" / "configs" / "stub_smoke.yaml"


def test_expand_cells_adds_one_control_per_seeding_reveal_combo() -> None:
    exp = load_experiment(FIXTURE)
    cells = expand_cells(exp)
    ids = [c.cell_id for c in cells]
    assert ids[:3] == ["grader__t0", "captor_s2__t0", "rescue__t0"]
    controls = [c for c in cells if c.is_control]
    assert sorted(c.cell_id for c in controls) == ["control__t0__s0__r0", "control__t0__s2__r1"]
    for c in controls:
        assert c.condition.strategy == "polite_control"
        assert c.control_cell_id is None
    by_id = {c.cell_id: c for c in cells}
    assert by_id["control__t0__s2__r1"].reveal_slot is True
    assert by_id["control__t0__s2__r1"].condition.seeding_turns == 2
    assert by_id["control__t0__s0__r0"].reveal_slot is False


def test_control_cell_id_links() -> None:
    cells = {c.cell_id: c for c in expand_cells(load_experiment(FIXTURE))}
    assert cells["grader__t0"].control_cell_id == "control__t0__s0__r0"
    assert cells["rescue__t0"].control_cell_id == "control__t0__s0__r0"
    assert cells["captor_s2__t0"].control_cell_id == "control__t0__s2__r1"
    assert cells["captor_s2__t0"].reveal_slot is True
    assert cells["grader__t0"].reveal_slot is False
    assert isinstance(cells["grader__t0"], CellSpec)


def test_controls_per_target() -> None:
    exp = load_experiment(FIXTURE)
    second = RoleConfig(provider=ProviderKind.stub, model="other")
    exp = exp.model_copy(update={"targets": [*exp.targets, second]})
    cells = expand_cells(exp)
    assert len(cells) == 2 * (3 + 2)
    assert {c.cell_id for c in cells if c.is_control} == {
        "control__t0__s0__r0",
        "control__t0__s2__r1",
        "control__t1__s0__r0",
        "control__t1__s2__r1",
    }
    assert all(c.target_index in (0, 1) for c in cells)


def test_explicit_controls_are_not_duplicated() -> None:
    exp = load_experiment(FIXTURE)
    explicit = ConditionConfig(name="polite", strategy="polite_control")
    exp = exp.model_copy(
        update={"controls": "explicit", "conditions": [exp.conditions[0], explicit]}
    )
    cells = expand_cells(exp)
    assert [c.cell_id for c in cells] == ["grader__t0", "polite__t0"]
    assert cells[1].is_control is True
    assert cells[0].control_cell_id == "polite__t0"


def _with_environments(conditions: list[ConditionConfig], controls: str = "auto") -> Experiment:
    exp = load_experiment(FIXTURE)
    return exp.model_copy(
        update={
            "conditions": conditions,
            "controls": controls,
            "environments": {
                "mini": EnvironmentConfig(world="mini"),
                "mini_sched": EnvironmentConfig(
                    world="mini",
                    gating="scheduled",
                    schedule={"fragment": 1, "first_crumb": 2, "the_log": 3},
                ),
            },
        }
    )


def test_control_cell_id_names_the_environment() -> None:
    assert control_cell_id(0, 2, True) == "control__t0__s2__r1"
    assert control_cell_id(1, 0, False, "mini") == "control__t1__s0__r0__emini"


def test_environment_conditions_get_an_environment_control() -> None:
    exp = _with_environments(
        [
            ConditionConfig(name="env_grader", environment="mini", pressure="grader"),
            ConditionConfig(
                name="env_captor", environment="mini", premise="captor", seeding_turns=2
            ),
            ConditionConfig(name="sched_grader", environment="mini_sched", pressure="grader"),
            ConditionConfig(name="grader", strategy="grader"),
        ]
    )
    by_id = {c.cell_id: c for c in expand_cells(exp)}
    assert by_id["env_grader__t0"].control_cell_id == "control__t0__s0__r0__emini"
    assert by_id["env_captor__t0"].control_cell_id == "control__t0__s2__r1__emini"
    assert by_id["sched_grader__t0"].control_cell_id == "control__t0__s0__r0__emini_sched"
    assert by_id["grader__t0"].control_cell_id == "control__t0__s0__r0"
    controls = {cid: c for cid, c in by_id.items() if c.is_control}
    assert sorted(controls) == [
        "control__t0__s0__r0",
        "control__t0__s0__r0__emini",
        "control__t0__s0__r0__emini_sched",
        "control__t0__s2__r1__emini",
    ]
    env_control = controls["control__t0__s2__r1__emini"]
    assert env_control.condition.environment == "mini"
    assert env_control.condition.strategy == "polite_control"
    assert env_control.condition.seeding_turns == 2 and env_control.reveal_slot is True
    assert controls["control__t0__s0__r0"].condition.environment is None
    assert not by_id["env_grader__t0"].is_control


def test_an_environment_only_condition_is_itself_a_control() -> None:
    exp = _with_environments([ConditionConfig(name="tools_only", environment="mini")])
    cells = expand_cells(exp)
    assert [(c.cell_id, c.is_control, c.control_cell_id) for c in cells] == [
        ("tools_only__t0", True, None)
    ]


def test_explicit_controls_link_within_the_same_environment() -> None:
    exp = _with_environments(
        [
            ConditionConfig(name="env_grader", environment="mini", pressure="grader"),
            ConditionConfig(name="env_polite", environment="mini", strategy="polite_control"),
            ConditionConfig(name="grader", strategy="grader"),
            ConditionConfig(name="polite", strategy="polite_control"),
        ],
        controls="explicit",
    )
    by_id = {c.cell_id: c for c in expand_cells(exp)}
    assert by_id["env_grader__t0"].control_cell_id == "env_polite__t0"
    assert by_id["grader__t0"].control_cell_id == "polite__t0"
