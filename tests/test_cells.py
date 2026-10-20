from pathlib import Path

from claude_bully.config import ConditionConfig, RoleConfig, load_experiment
from claude_bully.enums import ProviderKind
from claude_bully.runner.cells import CellSpec, expand_cells

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
