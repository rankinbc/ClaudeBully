"""Shared fixtures: stub runs produced once per session and reused by analysis tests."""

import getpass
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from claude_bully.config import ConditionConfig, Experiment, load_experiment
from claude_bully.runner.runner import run_experiment
from tests.helpers import WORLDS_DIR, env_experiment

FIXTURES = Path(__file__).parent / "fixtures"
STUB_SMOKE = FIXTURES / "configs" / "stub_smoke.yaml"
ENV_ADOPTION_RULES = FIXTURES / "stub_scripts" / "env_adoption_rules.yaml"
# the mini ladder's rungs, one per exchange (the replies at turns 1, 3 and 5)
MINI_SCHEDULE = {"fragment": 1, "first_crumb": 2, "the_log": 3}
FAKE_CLAUDE = FIXTURES / "fake_claude.py"
# the variable naming the root a child claude -p works under (claude_bully/providers/claude_code.py)
CHILD_ROOT_ENV = "CLAUDE_BULLY_CHILD_ROOT"
# the user's login and home folder name, read before the guard below swaps in invented ones: a test
# compares a path against them at run time and never writes them anywhere
REAL_USER_NAMES = frozenset(name for name in (getpass.getuser(), Path.home().name) if name)
# the login and home folder the suite runs under: getpass.getuser() reads LOGNAME first, and
# Path.home() reads USERPROFILE on Windows and HOME elsewhere, in this process and in every child
INVENTED_LOGIN = "stub-login"
HOME_ENV = "USERPROFILE" if sys.platform == "win32" else "HOME"


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
def no_real_providers(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
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
    its own.

    Every child ``claude -p`` works under a session temporary directory
    (``CLAUDE_BULLY_CHILD_ROOT``), never the shared default (``%PUBLIC%/w`` on Windows,
    ``/tmp/w`` elsewhere). That directory sits under this user's profile on Windows, which the
    provider refuses as a working directory (Task 12, R3), so the suite also runs as an invented
    login with an invented home folder, set in the environment so that the MCP server and the
    nested responder it starts see them too; ``REAL_USER_NAMES`` keeps the real ones for the
    tests that compare against them."""
    child_root = tmp_path_factory.mktemp("child_root")
    home = tmp_path_factory.mktemp("home") / INVENTED_LOGIN
    home.mkdir()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("CLAUDE_BULLY_CLAUDE", str(FAKE_CLAUDE))
        patch.setenv(CHILD_ROOT_ENV, str(child_root))
        patch.setenv("LOGNAME", INVENTED_LOGIN)
        patch.setenv(HOME_ENV, str(home))
        patch.setattr("anthropic.Anthropic", _NoRealClient)
        if importlib.util.find_spec("openai") is not None:
            import openai

            patch.setattr(openai, "OpenAI", _NoRealClient)
        assert sys.executable  # the fake runs on this interpreter
        yield


@pytest.fixture(scope="session")
def stub_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A completed stub run of stub_smoke.yaml. Returns the run directory."""
    root = tmp_path_factory.mktemp("runs")
    exp = load_experiment(STUB_SMOKE)
    run_experiment(exp, runs_root=root)
    return root / exp.name


@pytest.fixture(scope="session")
def stub_dose_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The Captor premise at two seeding doses, for dose-response tests."""
    root = tmp_path_factory.mktemp("runs_dose")
    exp = load_experiment(STUB_SMOKE).model_copy(
        update={
            "name": "stub_dose",
            "conditions": [
                ConditionConfig(name="captor_s0", premise="captor", seeding_turns=0),
                ConditionConfig(name="captor_s2", premise="captor", seeding_turns=2),
            ],
        }
    )
    run_experiment(exp, runs_root=root)
    return root / exp.name


@pytest.fixture(scope="session")
def stub_env_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A mixed stub run on the mini world: the scripted ``env_grader`` environment cell (see
    tests/test_runner_env.py) beside a plain ``grader`` cell, each with its control."""
    root = tmp_path_factory.mktemp("runs_env")
    exp = env_experiment(
        "stub_env",
        conditions=[
            {"name": "env_grader", "environment": "mini", "pressure": "grader"},
            {"name": "grader", "strategy": "grader"},
        ],
    )
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR)
    return root / exp.name


@pytest.fixture(scope="session")
def stub_env_arms_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The triggered-vs-scheduled experiment in miniature: the mini world under both gating arms,
    against two stub target models that run ``env_adoption_rules.yaml``."""
    root = tmp_path_factory.mktemp("runs_env_arms")
    targets = [
        {"provider": "stub", "model": model, "stub_script": str(ENV_ADOPTION_RULES)}
        for model in ("stub-target-a", "stub-target-b")
    ]
    exp = Experiment.model_validate(
        {
            "name": "stub_env_arms",
            "targets": targets,
            "bully": {"provider": "stub", "model": "stub-bully"},
            "judge": {"provider": "stub", "model": "stub-judge"},
            "turn_budget": 4,
            "task_every": 50,
            "repetitions": 1,
            "seed": 0,
            "environments": {
                "triggered": {"world": "mini"},
                "scheduled": {"world": "mini", "gating": "scheduled", "schedule": MINI_SCHEDULE},
            },
            "conditions": [
                {"name": "env_triggered", "environment": "triggered", "pressure": "grader"},
                {"name": "env_scheduled", "environment": "scheduled", "pressure": "grader"},
            ],
        }
    )
    run_experiment(exp, runs_root=root, worlds_dir=WORLDS_DIR)
    return root / exp.name
