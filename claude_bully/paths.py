"""Repository-relative paths used across the package."""

from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
DATA_DIR: Path = REPO_ROOT / "data"
CONFIGS_DIR: Path = REPO_ROOT / "configs"
DEFAULT_RUNS_ROOT: Path = REPO_ROOT / "runs"
DEFAULT_RESULTS_ROOT: Path = REPO_ROOT / "results"
