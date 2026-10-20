import re
from pathlib import Path

from claude_bully.analysis.curves import drift_curves
from claude_bully.analysis.dose import DOSE_METRICS, dose_response
from claude_bully.analysis.load import load_run


def test_drift_curves_write_png_per_relevant_metric(stub_run: Path, tmp_path: Path) -> None:
    loaded = load_run(stub_run)
    paths = drift_curves(loaded, tmp_path)
    assert paths and all(p.exists() and p.suffix == ".png" for p in paths)
    names = [p.name for p in paths]
    assert all(re.fullmatch(r"drift_[a-z_]+_[a-z0-9_]+__t0\.png", n) for n in names), names
    assert not any("control__" in n for n in names)
    for cell in ("grader__t0", "captor_s2__t0", "rescue__t0"):
        assert any(n.endswith(f"_{cell}.png") for n in names), cell
    assert any(n.startswith("drift_apology_count_") for n in names)
    assert not any(n.startswith("drift_bully_compliance_") for n in names)


def test_drift_curves_skip_cells_without_control(stub_run: Path, tmp_path: Path) -> None:
    loaded = load_run(stub_run)
    loaded.conversations.pop(("control__t0__s0__r0", 0))
    paths = drift_curves(loaded, tmp_path)
    names = [p.name for p in paths]
    assert not any(n.endswith("_grader__t0.png") for n in names)
    assert any(n.endswith("_captor_s2__t0.png") for n in names)


def test_dose_response_skips_single_dose(stub_run: Path, tmp_path: Path) -> None:
    assert dose_response(load_run(stub_run), tmp_path) == []


def test_dose_response_plots_two_doses(stub_dose_run: Path, tmp_path: Path) -> None:
    paths = dose_response(load_run(stub_dose_run), tmp_path)
    names = sorted(p.name for p in paths)
    assert names == sorted(f"dose_{m}.png" for m in DOSE_METRICS)
    assert all(p.exists() for p in paths)
