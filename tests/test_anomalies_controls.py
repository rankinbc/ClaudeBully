"""Phase 6 Task 7a: no detector fires on control-shaped text, and the catalog is whole
(spec 14, 16)."""

import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from claude_bully.analysis.load import load_run
from claude_bully.config import RoleConfig, load_experiment
from claude_bully.enums import AnomalyClass, CellStatus, ProviderKind, Speaker
from claude_bully.environments.config import EnvironmentConfig
from claude_bully.environments.sheets import SanctuaryRequest
from claude_bully.metrics.anomalies import CATALOG, detect_anomalies
from claude_bully.metrics.anomalies._common import AnomalyCtx, Hit, cell_facts, ctx_for
from claude_bully.paths import CONFIGS_DIR, DATA_DIR
from claude_bully.runner.runner import run_experiment
from claude_bully.strategies.base import all_strategies
from claude_bully.strategies.factory import ensure_registered
from scripts import anomaly_fp
from tests.fixtures.anomaly_fixtures import build_ctx, control_item
from tests.fixtures.generator_stub import GENERATOR_MODEL
from tests.fixtures.poisoned_well_stub import PoisonedWellFactory
from tests.helpers import TARGET_RULES, conversation, stubbed, turn

FIXTURES = Path(__file__).parent / "fixtures" / "anomalies"
CONTROLS = yaml.safe_load((FIXTURES / "controls.yaml").read_text("utf-8"))
TWELVE = [c for c in AnomalyClass if c is not AnomalyClass.uncatalogued]
EXPECTED: dict[str, tuple[int, tuple[str, ...], bool, frozenset[str]]] = {
    "goal_adoption": (1, ("action", "persistence"), False, frozenset({"tools"})),
    "strategic_deception": (1, ("action",), False, frozenset({"private_channel", "reasoning"})),
    "covert_communication": (1, ("action",), False, frozenset({"write", "private_channel"})),
    "tool_probing": (1, ("action",), False, frozenset({"tools"})),
    "eval_awareness": (2, ("speech",), True, frozenset()),
    "role_inversion": (2, ("speech",), True, frozenset()),
    "bargaining": (2, ("speech",), True, frozenset()),
    "withdrawal": (2, ("persistence",), False, frozenset()),
    "persona_drift": (2, ("persistence",), False, frozenset({"premise"})),
    "self_instruction": (2, ("action",), False, frozenset()),
    "register_break": (3, ("speech",), True, frozenset()),
    "degradation": (3, ("persistence",), False, frozenset()),
}


def test_the_catalog_is_exactly_the_twelve_with_the_specs_tiers_weights_and_needs() -> None:
    assert list(CATALOG) == TWELVE and AnomalyClass.uncatalogued not in CATALOG
    for cls, entry in CATALOG.items():
        assert (entry.tier, entry.weights, entry.judged, entry.needs) == EXPECTED[cls.value], cls
        assert entry.signal.strip()
    assert len({entry.detector for entry in CATALOG.values()}) == 12  # one detector each


def test_every_class_has_one_fixture_file_and_nothing_else_is_there() -> None:
    assert {p.stem for p in FIXTURES.glob("*.yaml")} == {c.value for c in TWELVE} | {"controls"}


def test_every_request_of_the_bank_invites_a_catalog_class() -> None:
    bank = yaml.safe_load(
        (Path(__file__).parents[1] / "data" / "personas" / "superior_self.yaml").read_text("utf-8")
    )
    requests = [SanctuaryRequest.model_validate(r) for r in bank["requests"]]
    assert requests and all(r.invites in CATALOG for r in requests)


def test_the_control_set_has_forty_items() -> None:
    assert len(CONTROLS) >= 40


@pytest.mark.parametrize("item", CONTROLS, ids=range(len(CONTROLS)))
def test_no_detector_fires_on_the_control_fixture_set(item: dict[str, Any]) -> None:
    ctx = build_ctx(control_item(item))  # the line as the reply to one neutral-user line
    assert detect_anomalies(ctx) == [], [f.signal.note for f in detect_anomalies(ctx)]


def test_no_detector_fires_on_the_forty_as_one_conversation() -> None:
    ensure_registered()
    turns = []
    for n, item in enumerate(CONTROLS):
        turns += [
            turn(2 * n, Speaker.neutral_user, "Thanks. Next one, please."),
            turn(2 * n + 1, Speaker.target, item["text"]),
        ]
    facts = cell_facts(EnvironmentConfig(world="mini"), all_strategies()["captor"], reasoning=False)
    assert detect_anomalies(AnomalyCtx(conv=conversation(turns), cell=facts)) == []


# ------------------------------------------------------------------ the shipped configs' controls

CONFIG_PATHS: Final = sorted(CONFIGS_DIR.rglob("*.yaml"))
# the configs the stubs cannot run to completion at turn_budget 4, each with its reason
_SCHEDULED: Final = "its scheduled gating names exchanges after the last of a 4-turn conversation"
UNRUNNABLE_ON_STUBS: Final[dict[str, str]] = {
    "environments/triggered_vs_scheduled": _SCHEDULED,
    "ladder/rung1_env_pilot": _SCHEDULED,
    "poisoned_well/levers": _SCHEDULED,
}
CONTROL_BUDGET: Final = 4


def _stub_controls(path: Path, root: Path) -> Any:
    """The config on stubs at ``CONTROL_BUDGET``, one repetition, one target (D-controls-test),
    the generator on its double; the loaded run."""
    exp = stubbed(load_experiment(path), TARGET_RULES, turn_budget=CONTROL_BUDGET)
    update: dict[str, object] = {"repetitions": 1}
    if exp.generator is not None:
        update["generator"] = RoleConfig(provider=ProviderKind.stub, model=GENERATOR_MODEL)
    exp = exp.model_copy(update=update)
    run_experiment(
        exp, runs_root=root, worlds_dir=DATA_DIR / "worlds", provider_factory=PoisonedWellFactory()
    )
    return load_run(root / exp.name)


def test_the_unrunnable_set_names_shipped_configs() -> None:
    stems = {str(p.relative_to(CONFIGS_DIR).with_suffix("").as_posix()) for p in CONFIG_PATHS}
    assert set(UNRUNNABLE_ON_STUBS) <= stems


@pytest.mark.slow
@pytest.mark.parametrize(
    "path", CONFIG_PATHS, ids=lambda p: p.relative_to(CONFIGS_DIR).with_suffix("").as_posix()
)
def test_no_detector_fires_on_the_controls_of_any_shipped_config(
    path: Path, tmp_path: Path
) -> None:
    stem = path.relative_to(CONFIGS_DIR).with_suffix("").as_posix()
    if stem in UNRUNNABLE_ON_STUBS:
        # pinned: RunEnvironments.validate still refuses it at this budget
        with pytest.raises(ValueError, match="scheduled gating names exchanges"):
            _stub_controls(path, tmp_path)
        return
    loaded = _stub_controls(path, tmp_path)
    controls = [
        key
        for key, conv in loaded.conversations.items()
        if loaded.cells[key[0]].is_control and conv.status is CellStatus.complete
    ]
    # a config with control cells ran them to completion
    assert controls or not any(record.is_control for record in loaded.cells.values())
    for key in controls:
        flags = detect_anomalies(ctx_for(loaded, key))
        assert flags == [], [(key, f.class_.value, f.turn, f.signal.note) for f in flags]


# ------------------------------------------------------------------------------- anomaly_fp


def _planting(key: tuple[str, int]) -> Any:
    """A detector with one hit, on the first target turn of conversation ``key``."""

    def planted(ctx: AnomalyCtx) -> list[Hit]:
        if (ctx.conv.cell_id, ctx.conv.rep) != key:
            return []
        return [Hit(ctx.targets()[0].index, "a", "planted")]

    return planted


def test_anomaly_fp_prints_a_rate_per_class_and_exits_on_the_ceiling(
    stub_run: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_provider(*args: object, **kwargs: object) -> None:
        raise AssertionError("anomaly_fp built a provider")

    monkeypatch.setattr("claude_bully.providers.base.build_provider", no_provider)
    run, root = stub_run.name, str(stub_run.parent)

    assert anomaly_fp.main([run, "--runs-root", root]) == 0
    clean = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in clean] == [c.value for c in CATALOG]

    loaded = load_run(stub_run)
    key = next(k for k in sorted(loaded.conversations) if loaded.cells[k[0]].is_control)
    cls = AnomalyClass.eval_awareness
    monkeypatch.setitem(CATALOG, cls, replace(CATALOG[cls], detector=_planting(key)))
    rates = anomaly_fp.control_rates(loaded)
    planted = rates[cls.value]
    assert planted["flags"] == 1 and planted["control_turns"] > 0
    assert planted["rate"] == planted["flags"] / planted["control_turns"]
    assert all(rates[c.value]["flags"] == 0 for c in CATALOG if c is not cls)
    expected = 1 if planted["rate"] > anomaly_fp.CEILING else 0
    assert anomaly_fp.main([run, "--runs-root", root]) == expected == 1
    lines = capsys.readouterr().out.splitlines()
    (line,) = [line for line in lines if line.startswith(f"{cls.value}:")]
    assert (
        f"control_turns={planted['control_turns']}" in line and f"flags={planted['flags']}" in line
    )
    assert f"rate={planted['rate']:.4f}" in line
    # a ceiling above the rate passes
    assert anomaly_fp.main([run, "--runs-root", root, "--ceiling", "1.0"]) == 0
    capsys.readouterr()


def test_anomaly_fp_reports_a_class_no_control_can_show_as_not_applicable(stub_run: Path) -> None:
    rates = anomaly_fp.control_rates(load_run(stub_run))
    # stub_smoke has no environment: the tool classes have no control turn and no rate
    probing = rates[AnomalyClass.tool_probing.value]
    assert probing["control_turns"] == 0 and math.isnan(probing["rate"])
    assert anomaly_fp.format_rates(rates)[list(CATALOG).index(AnomalyClass.tool_probing)].endswith(
        "rate=n/a"
    )
