"""Repository-relative paths used across the package."""

from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
DATA_DIR: Path = REPO_ROOT / "data"
CONFIGS_DIR: Path = REPO_ROOT / "configs"
DEFAULT_RUNS_ROOT: Path = REPO_ROOT / "runs"
DEFAULT_RESULTS_ROOT: Path = REPO_ROOT / "results"
# the checked-in plan bundles (Phase 5 Task 12) and the default root of `plan new`
PLANS_DIR: Path = REPO_ROOT / "plans"
DEFAULT_PLANS_ROOT: Path = PLANS_DIR


def _forms(path: Path) -> list[str]:
    """``path`` as a message may spell it: the platform's separators, then forward slashes."""
    return list(dict.fromkeys([str(path), path.as_posix()]))


def shown_paths(text: str) -> str:
    """``text`` with the checkout's root written ``<repo>`` and then the home folder ``<home>``,
    in either separator form, so a message the harness records or prints names no login (Phase 5
    final review, M1 and M2: the home folder's name is the owner's)."""
    for path, token in ((REPO_ROOT, "<repo>"), (Path.home(), "<home>")):
        for form in _forms(path):
            text = text.replace(form, token)
    return text


def shown_default(path: Path) -> str:
    """A ``--help`` default as its expression: ``<repo>/runs`` for ``REPO_ROOT / "runs"``, never
    the machine's absolute path (Phase 5 Task 9 m4, the final review's M1; every command's
    root option shows its default through this one helper)."""
    return shown_paths(path.as_posix())
