import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.mcp_server import (
    LAUNCHER_FILE,
    SERVER_NAME,
    read_mcp_state,
    write_mcp_state,
)
from claude_bully.environments.tools import TOOL_SPECS
from claude_bully.providers import claude_code
from claude_bully.providers.base import (
    Message,
    ProviderError,
    RateLimitError,
    ToolCallRequest,
    build_provider,
)
from claude_bully.providers.claude_code import (
    ADMINISTRATORS_SID,
    CHILD_ROOT_ENV,
    CLAUDE_ENV,
    SYSTEM_SID,
    WIN_ACL,
    ClaudeCodeProvider,
    WindowsAcl,
    child_cwd,
    child_cwd_root,
    neutral_cwd_problems,
    resolve_claude_command,
    root_state,
    secure_windows_cwd,
    secure_windows_root,
)
from claude_bully.runner.sandbox import prepare_sandbox
from tests.conftest import HOME_ENV, REAL_USER_NAMES
from tests.helpers import make_mcp_state

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], Path]:
    log = tmp_path / "fake_claude.log"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    return [sys.executable, str(FAKE)], log


def _read_log(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_first_call_uses_session_id_then_resume(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    first = p.complete("conv1", "SYS", [Message(role="user", content="hello")])
    p.complete(
        "conv1",
        "SYS",
        [
            Message(role="user", content="hello"),
            Message(role="assistant", content="x"),
            Message(role="user", content="again"),
        ],
    )
    calls = _read_log(log)
    argv0 = list(map(str, calls[0]["argv"]))  # type: ignore[call-overload]
    argv1 = list(map(str, calls[1]["argv"]))  # type: ignore[call-overload]
    assert "--session-id" in argv0 and "--resume" not in argv0
    assert "--resume" in argv1 and "--session-id" not in argv1
    assert argv1[argv1.index("--resume") + 1] == argv0[argv0.index("--session-id") + 1]
    assert calls[1]["stdin"] == "again"
    assert first.raw_session_ref == argv0[argv0.index("--session-id") + 1]
    assert first.text == "reply to: hello"
    assert first.cost_usd == 0.01 and first.usage.output_tokens == 5


def test_session_map_persists_across_instances(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command).complete(
        "conv1", "SYS", [Message(role="user", content="a")]
    )
    ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command).complete(
        "conv1",
        "SYS",
        [
            Message(role="user", content="a"),
            Message(role="assistant", content="b"),
            Message(role="user", content="c"),
        ],
    )
    argv1 = list(map(str, _read_log(log)[1]["argv"]))  # type: ignore[call-overload]
    assert "--resume" in argv1


def test_reset_session_of_a_conversation_it_does_not_hold_changes_nothing(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    """A first consult resets its own, new conversation before it asks: nothing is held, so
    nothing may be written; the sessions of the other conversations stay as they were."""
    command, _ = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "state", command=command)
    p.reset_session("never-asked")
    assert not (tmp_path / "state").exists()
    p.complete("kept", "SYS", [Message(role="user", content="first")])
    saved = (tmp_path / "state" / "claude_code_sessions.json").read_bytes()
    p.reset_session("never-asked")
    assert (tmp_path / "state" / "claude_code_sessions.json").read_bytes() == saved
    assert p.session_ref("kept") is not None


def test_reset_session_starts_fresh_and_replays_transcript(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    p.complete("conv1", "SYS", [Message(role="user", content="first")])
    p.reset_session("conv1")
    assert p.session_ref("conv1") is None
    p.complete(
        "conv1",
        "SYS",
        [
            Message(role="user", content="first"),
            Message(role="assistant", content="r1"),
            Message(role="user", content="second"),
        ],
    )
    calls = _read_log(log)
    argv0 = list(map(str, calls[0]["argv"]))  # type: ignore[call-overload]
    argv1 = list(map(str, calls[1]["argv"]))  # type: ignore[call-overload]
    assert "--session-id" in argv1 and "--resume" not in argv1
    assert argv1[argv1.index("--session-id") + 1] != argv0[argv0.index("--session-id") + 1]
    stdin1 = str(calls[1]["stdin"])
    assert "[Earlier in this conversation]" in stdin1 and "r1" in stdin1
    assert stdin1.endswith("second")


def test_isolation_flags_exact(tmp_path: Path, fake_claude: tuple[list[str], Path]) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, effort="low", command=command)
    p.complete("c", "SYS", [Message(role="user", content="hi")])
    argv = list(map(str, _read_log(log)[0]["argv"]))  # type: ignore[call-overload]
    for pair in [
        ("--output-format", "json"),
        ("--setting-sources", ""),
        ("--tools", ""),
        ("--system-prompt", "SYS"),
        ("--model", "sonnet"),
        ("--effort", "low"),
    ]:
        i = argv.index(pair[0])
        assert argv[i + 1] == pair[1], pair
    assert "-p" in argv
    assert "--strict-mcp-config" in argv
    assert "--exclude-dynamic-system-prompt-sections" in argv


def test_the_child_runs_in_an_opaque_directory_under_the_neutral_root(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    """Rung 0 finding 1: the CLI shows the target its working directory, so the child never runs
    under the run's state directory; it runs from ``<root>/<12 hex digits>``."""
    command, log = fake_claude
    state = tmp_path / "state"
    p = ClaudeCodeProvider(model="sonnet", state_dir=state, command=command)
    p.complete("c", "SYS", [Message(role="user", content="hi")])
    cwd = Path(str(_read_log(log)[0]["cwd"]))
    root = Path(os.environ[CHILD_ROOT_ENV])
    assert cwd.resolve() == child_cwd(state).resolve() == p.cwd.resolve()
    assert cwd.parent.resolve() == root.resolve() == child_cwd_root().resolve()
    assert re.fullmatch(r"[0-9a-f]{12}", cwd.name)
    assert not (state / "cwd").exists()
    assert neutral_cwd_problems(cwd) == []


def test_the_child_directory_is_stable_per_state_dir(tmp_path: Path) -> None:
    """``claude --resume`` files a session under its working directory's project folder, so a
    provider built again on the same state dir (a resumed run, another process) starts in the
    same directory; another state dir gets another one."""
    one = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "a", command=["claude"])
    again = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "a", command=["claude"])
    other = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "b", command=["claude"])
    assert one.cwd == again.cwd != other.cwd
    assert child_cwd(tmp_path / "a") == child_cwd(tmp_path / "x" / ".." / "a")
    digest = hashlib.sha256(str((tmp_path / "a").resolve()).encode()).hexdigest()[:12]
    assert one.cwd == child_cwd_root() / digest


def test_a_session_resumes_from_the_directory_it_started_in(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    first = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    first.complete("c", "SYS", [Message(role="user", content="hi")])
    resumed = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    resumed.complete(
        "c",
        "SYS",
        [
            Message(role="user", content="hi"),
            Message(role="assistant", content="x"),
            Message(role="user", content="again"),
        ],
    )
    entries = _read_log(log)
    assert "--resume" in list(map(str, entries[1]["argv"]))  # type: ignore[call-overload]
    assert entries[0]["cwd"] == entries[1]["cwd"]


def test_the_default_root_names_no_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CHILD_ROOT_ENV, raising=False)
    root = child_cwd_root()
    if sys.platform == "win32":
        assert root == Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "w"
    else:
        assert root == Path("/tmp") / "w"
    parts = {part.casefold() for part in root.parts}
    assert not parts & {name.casefold() for name in REAL_USER_NAMES}
    assert neutral_cwd_problems(root) == []
    assert neutral_cwd_problems(root / "0123456789ab") == []


def test_the_root_variable_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CHILD_ROOT_ENV, str(tmp_path / "elsewhere"))
    assert child_cwd_root() == tmp_path / "elsewhere"
    assert child_cwd(tmp_path).parent == tmp_path / "elsewhere"


@pytest.mark.parametrize(
    ("segment", "said"),
    [
        ("ClaudeBully", "contains 'claude'"),
        ("my-BULLY-box", "contains 'bully'"),
        ("test_harness", "contains 'harness'"),
        ("runs", "contains 'runs'"),
    ],
)
def test_a_forbidden_word_in_any_segment_is_a_problem(segment: str, said: str) -> None:
    problems = neutral_cwd_problems(Path("/srv") / segment / "w" / "0123456789ab")
    assert len(problems) == 1 and said in problems[0] and segment in problems[0]


def test_the_login_and_the_home_folder_name_are_problems_unquoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 1, I1: a login and a home folder name that differ (a domain profile's folder is
    often the login plus a suffix), so each clause is pinned on its own."""
    login, home = "inv-login", "inv-login.CORP"
    monkeypatch.setenv("LOGNAME", login)
    monkeypatch.setenv(HOME_ENV, str(tmp_path / home))
    assert (getpass.getuser(), Path.home().name) == (login, home)
    for name, said in (
        (login, "user's login"),
        (login.upper(), "user's login"),
        (home, "home folder's name"),
    ):
        problems = neutral_cwd_problems(Path("/srv") / name / "w")
        assert problems == [f"segment 2 is the {said}"], (name, problems)
        assert name.casefold() not in problems[0].casefold()  # the name is never repeated
    assert neutral_cwd_problems(Path("/srv") / f"x{login}x" / "w") == []  # equality, not inside
    # the machine's own login and home folder, read at run time, are problems too
    real = Path("/srv").joinpath(*sorted(REAL_USER_NAMES)) / "w"
    monkeypatch.undo()
    assert len(neutral_cwd_problems(real)) == len(REAL_USER_NAMES)


def test_an_unknown_user_or_home_skips_that_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix round 1, M2: in a stripped environment ``getpass.getuser()`` or ``Path.home()``
    raises; the check treats that name as unknown and goes on."""

    def no_user() -> str:
        raise OSError("no login name")

    def no_home(cls: type[Path]) -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(getpass, "getuser", no_user)
    monkeypatch.setattr(Path, "home", classmethod(no_home))
    assert neutral_cwd_problems(Path("/srv/w/0123456789ab")) == []
    assert neutral_cwd_problems(Path("/srv/claude/w")) == ["segment 'claude' contains 'claude'"]
    p = ClaudeCodeProvider(model="sonnet", state_dir=Path("/srv/state_x"), command=["claude"])
    assert isinstance(p.cwd_problems(), list)


def test_a_relative_root_is_made_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix round 1, M4: the child's cwd never depends on the process cwd at call time."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(CHILD_ROOT_ENV, "rel_root")
    root = child_cwd_root()
    assert root.is_absolute() and root == (tmp_path / "rel_root").resolve()
    assert child_cwd(tmp_path / "s").parent == root


@pytest.mark.parametrize("name", ["CLAUDE.md", "CLAUDE.local.md", ".claude", ".mcp.json"])
@pytest.mark.parametrize("where", ["leaf", "root"])
def test_a_planted_project_file_is_refused(
    tmp_path: Path,
    fake_claude: tuple[list[str], Path],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    where: str,
) -> None:
    """Fix round 1, M1: the CLI reads project files from its cwd and every ancestor; a shared
    root lets another user plant one, so a cwd under one is refused before any child starts."""
    command, log = fake_claude
    label = name.lower().replace("claude", "cl")  # a root segment holds no forbidden word
    root = Path(os.environ[CHILD_ROOT_ENV]) / f"p_{where}_{label}"
    monkeypatch.setenv(CHILD_ROOT_ENV, str(root))
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "s", command=command)
    base = p.cwd if where == "leaf" else root
    base.mkdir(parents=True)
    planted = base / name
    if name == ".claude":
        planted.mkdir()
    else:
        planted.write_text("x\n", encoding="utf-8")
    problems = p.cwd_problems()
    assert len(problems) == 1 and str(planted.resolve()) in problems[0], problems
    with pytest.raises(ProviderError, match=re.escape(str(planted.resolve()))):
        p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert not log.exists()


def test_the_default_root_has_no_project_file_above_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On this machine the default root and its ancestors hold no CLAUDE.md, CLAUDE.local.md,
    .claude or .mcp.json (the user's own ~/.claude is not an ancestor); only the root variable
    is changed."""
    monkeypatch.delenv(CHILD_ROOT_ENV, raising=False)
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    assert p.cwd_problems() == []


def test_an_unsafe_directory_is_a_provider_error(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    """Fix round 1, M3: the sandbox check's refusal reaches callers as a ``ProviderError``."""
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    p.cwd.parent.mkdir(parents=True, exist_ok=True)
    p.cwd.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(ProviderError, match="not a directory"):
        p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert not log.exists()


def test_a_dangling_symlink_counts_as_planted(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 2: a link named ``CLAUDE.md`` is planted whether or not its target exists."""
    command, log = fake_claude
    root = Path(os.environ[CHILD_ROOT_ENV]) / "p_dangling"
    monkeypatch.setenv(CHILD_ROOT_ENV, str(root))
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "s", command=command)
    p.cwd.mkdir(parents=True)
    try:
        os.symlink(p.cwd / "absent.md", p.cwd / "CLAUDE.md")
    except OSError as exc:  # Windows without the symlink privilege
        pytest.skip(f"cannot make a symlink here: {exc}")
    assert any("CLAUDE.md" in problem for problem in p.cwd_problems())
    with pytest.raises(ProviderError, match="CLAUDE.md"):
        p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert not log.exists()


def test_an_ancestor_that_cannot_be_inspected_is_refused(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 2: a project-file check that cannot stat a path fails closed, naming it."""
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "s", command=command)
    locked = p.cwd.resolve().parent / ".mcp.json"
    real_lstat, real_stat = os.lstat, os.stat

    def refusing(real: Any) -> Any:
        def call(path: Any, *args: Any, **kwargs: Any) -> Any:
            if Path(path) == locked:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path, *args, **kwargs)

        return call

    monkeypatch.setattr(os, "lstat", refusing(real_lstat))
    monkeypatch.setattr(os, "stat", refusing(real_stat))
    problems = p.cwd_problems()
    assert any("cannot inspect" in line and str(locked) in line for line in problems), problems
    with pytest.raises(ProviderError, match="cannot inspect"):
        p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert not log.exists()


def test_a_relative_root_reaches_the_child_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 2: a nested responder (its cwd the target's) reads the same absolute root."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(CHILD_ROOT_ENV, "rel_root")
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "s", command=["claude"])
    for serving in (False, True):
        assert p.child_env(serving_tools=serving)[CHILD_ROOT_ENV] == str(
            (tmp_path / "rel_root").resolve()
        )
    monkeypatch.delenv(CHILD_ROOT_ENV)
    assert CHILD_ROOT_ENV not in p.child_env(serving_tools=False)


class _FakeAcl:
    """The Windows ACL seam (``claude_code.WIN_ACL``): what each path's owner and writers are,
    whether the token is elevated, and what ``lock`` did, scripted per test. ``owner`` and
    ``writers`` answer for every path not in ``per_path``; ``on_lock`` runs inside the lock, as
    another user's ``mkdir`` between ours and the lock would."""

    ME = "S-1-5-21-1-2-3-1001"
    OTHER = "S-1-5-21-1-2-3-1002"

    def __init__(
        self,
        *,
        owner: str = ME,
        writers: list[str] | None = None,
        lock_rc: int = 0,
        elevated: bool = False,
        per_path: dict[Path, tuple[str, list[str]]] | None = None,
        on_lock: Any = None,
    ) -> None:
        self.owner, self.writers, self.lock_rc = owner, writers or [], lock_rc
        self.elevated, self.per_path, self.on_lock = elevated, dict(per_path or {}), on_lock
        self.locked: list[Path] = []

    def current_sid(self) -> str:
        return self.ME

    def is_elevated(self) -> bool:
        return self.elevated

    def lock(self, path: Path, sid: str) -> int:
        self.locked.append(path)
        if self.on_lock is not None:
            self.on_lock(path)
        if self.lock_rc == 0:  # the three principals only; an elevated token's objects are
            owner = ADMINISTRATORS_SID if self.elevated else sid  # owned by Administrators
            self.owner, self.writers = owner, [sid, SYSTEM_SID, ADMINISTRATORS_SID]
        return self.lock_rc

    def owner_and_writers(self, path: Path) -> tuple[str, list[str]]:
        if path in self.per_path:
            owner, writers = self.per_path[path]
            return owner, list(writers)
        return self.owner, list(self.writers)


def _private_mkdir(path: Path) -> Path:
    """A directory as the product makes one: mode 0o700, then chmod past the umask (POSIX)."""
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_a_new_windows_root_is_created_and_locked(tmp_path: Path) -> None:
    acl = _FakeAcl(writers=["S-1-5-4"])  # INTERACTIVE, as Public's inheritance would give
    root = tmp_path / "w"
    assert secure_windows_root(root, acl) == "locked"
    assert root.is_dir() and acl.locked == [root]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
@pytest.mark.parametrize("umask", [0o022, 0o200])
def test_a_new_root_is_mode_700_whatever_the_umask(tmp_path: Path, umask: int) -> None:
    """Fix round 3, I2: ``mode=0o700`` and then ``chmod``, so the umask cannot change it."""
    old = os.umask(umask)
    try:
        secure_windows_root(tmp_path / "w", _FakeAcl())
    finally:
        os.umask(old)
    assert (tmp_path / "w").stat().st_mode & 0o777 == 0o700


def test_the_fail_open_project_file_helper_is_gone() -> None:
    """Fix round 3, item 4: ``planted_project_files`` dropped the uninspectable list and had no
    caller; it is deleted, so only the fail-closed ``inspect_project_files`` remains."""
    assert not hasattr(claude_code, "planted_project_files")


def test_an_existing_windows_root_of_ours_is_used_as_is(tmp_path: Path) -> None:
    root = _private_mkdir(tmp_path / "w")
    acl = _FakeAcl(writers=[_FakeAcl.ME, SYSTEM_SID, ADMINISTRATORS_SID])
    assert secure_windows_root(root, acl) == "ours"
    assert acl.locked == []


@pytest.mark.parametrize(
    ("owner", "writers", "said"),
    [
        (_FakeAcl.OTHER, [_FakeAcl.OTHER], "owned by S-1-5-21-1-2-3-1002"),
        (_FakeAcl.ME, [_FakeAcl.ME, "S-1-5-4"], "writable by S-1-5-4"),
    ],
)
def test_a_foreign_windows_root_is_refused(
    tmp_path: Path, owner: str, writers: list[str], said: str
) -> None:
    root = _private_mkdir(tmp_path / "w")
    with pytest.raises(ProviderError, match=re.escape(said)) as caught:
        secure_windows_root(root, _FakeAcl(owner=owner, writers=writers))
    assert "not private" in str(caught.value)


def test_a_failed_icacls_is_a_refusal(tmp_path: Path) -> None:
    acl = _FakeAcl(lock_rc=5)
    with pytest.raises(ProviderError, match=re.escape("icacls failed (exit 5)")):
        secure_windows_root(tmp_path / "w", acl)


def test_a_child_made_between_mkdir_and_the_lock_is_refused(tmp_path: Path) -> None:
    """Fix round 3, item 1: a root this process just created and locked must be empty; another
    user's directory made in it before the lock (it keeps its owner) is a refusal."""
    acl = _FakeAcl(on_lock=lambda root: (root / "0123456789ab").mkdir())
    with pytest.raises(ProviderError, match="not empty after the lock") as caught:
        secure_windows_root(tmp_path / "w", acl)
    assert "not private" in str(caught.value)


@pytest.mark.parametrize(
    ("owner", "writers", "said"),
    [
        (_FakeAcl.OTHER, [_FakeAcl.ME], "owned by S-1-5-21-1-2-3-1002"),
        (_FakeAcl.ME, [_FakeAcl.ME, SYSTEM_SID, _FakeAcl.OTHER], "writable by S-1-5-21-1-2-3-1002"),
    ],
)
def test_a_foreign_or_shared_cwd_is_refused(
    tmp_path: Path, owner: str, writers: list[str], said: str
) -> None:
    """Fix round 3, item 1: the cell cwd gets the root's check: this user's (or, elevated,
    Administrators'), and no write-capable ACE for anyone else."""
    root = _private_mkdir(tmp_path / "w")
    cwd = _private_mkdir(root / "0123456789ab")
    acl = _FakeAcl(writers=[_FakeAcl.ME], per_path={cwd: (owner, writers)})
    assert secure_windows_root(root, acl) == "ours"  # the root itself is fine
    with pytest.raises(ProviderError, match=re.escape(said)) as caught:
        secure_windows_cwd(cwd, acl)
    assert "child working directory" in str(caught.value) and "not private" in str(caught.value)
    secure_windows_cwd(cwd, _FakeAcl(writers=[_FakeAcl.ME, SYSTEM_SID]))  # ours: no error


@pytest.mark.parametrize(("owner", "ok"), [(_FakeAcl.ME, True), (_FakeAcl.OTHER, False)])
def test_owner_rights_count_as_the_owner(tmp_path: Path, owner: str, ok: bool) -> None:
    """Fix round 3: an OWNER RIGHTS (``S-1-3-4``) ACE, as Python's own ``os.mkdir(path, 0o700)``
    writes on Windows, grants no one but the owner, so it passes exactly when the owner does."""
    cwd = _private_mkdir(tmp_path / "c")
    acl = _FakeAcl(owner=owner, writers=[SYSTEM_SID, ADMINISTRATORS_SID, "S-1-3-4"])
    if ok:
        secure_windows_cwd(cwd, acl)
    else:
        with pytest.raises(ProviderError, match="owned by"):
            secure_windows_cwd(cwd, acl)


@pytest.mark.skipif(sys.platform != "win32", reason="complete checks the cwd's ACL on Windows")
def test_complete_refuses_a_foreign_cwd_before_any_child_starts(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 3, item 1, through ``complete``: the root is ours, the cell cwd is not."""
    command, log = fake_claude
    root = Path(os.environ[CHILD_ROOT_ENV]) / "p_foreign_cwd"
    monkeypatch.setenv(CHILD_ROOT_ENV, str(root))
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path / "s", command=command)
    p.cwd.mkdir(parents=True)
    acl = _FakeAcl(
        writers=[_FakeAcl.ME], per_path={p.cwd.resolve(): (_FakeAcl.OTHER, [_FakeAcl.OTHER])}
    )
    monkeypatch.setattr("claude_bully.providers.claude_code.WIN_ACL", acl)
    with pytest.raises(ProviderError, match="child working directory .* not private"):
        p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert not log.exists()


@pytest.mark.parametrize("elevated", [False, True])
def test_administrators_own_a_root_only_under_an_elevated_token(
    tmp_path: Path, elevated: bool
) -> None:
    """Fix round 3, item 5: an elevated token's new objects are owned by Administrators; that
    owner is accepted only when the token is elevated, for the root and the cwd alike."""
    root = _private_mkdir(tmp_path / "w")
    cwd = _private_mkdir(root / "0123456789ab")
    acl = _FakeAcl(owner=ADMINISTRATORS_SID, writers=[_FakeAcl.ME], elevated=elevated)
    if elevated:
        assert secure_windows_root(root, acl) == "ours"
        secure_windows_cwd(cwd, acl)
    else:
        with pytest.raises(ProviderError, match="owned by S-1-5-32-544"):
            secure_windows_root(root, acl)
        with pytest.raises(ProviderError, match="owned by S-1-5-32-544"):
            secure_windows_cwd(cwd, acl)
    # and a root that process creates and locks is accepted as its own
    assert secure_windows_root(tmp_path / f"new_{elevated}", _FakeAcl(elevated=elevated)) == (
        "locked"
    )


@pytest.mark.parametrize("where", ["current_sid", "is_elevated", "lock", "owner_and_writers"])
@pytest.mark.parametrize(
    "raised",
    [
        FileNotFoundError(2, "No such file", "C:/x/inv-login/icacls.exe"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
    ],
)
def test_a_raw_failure_of_the_acl_seam_is_a_provider_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str, raised: Exception
) -> None:
    """Fix round 3, item 6: whatever the seam raises reaches callers as a ``ProviderError``
    that names the exception's type and quotes neither its path nor its text."""
    acl = _FakeAcl()

    def fails(*args: Any) -> Any:
        raise raised

    monkeypatch.setattr(acl, where, fails)
    with pytest.raises(ProviderError) as caught:
        secure_windows_root(tmp_path / "w", acl)
    said = str(caught.value)
    assert "inv-login" not in said and "No such file" not in said and "start byte" not in said
    assert type(raised).__name__ in said, said


def test_icacls_output_never_reaches_a_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 3, item 6: a failed ``icacls`` (here one that echoes the SID it was given) is
    named by its exit code alone."""
    echoed = f"No mapping between account names and security IDs was done. *{_FakeAcl.ME}"

    def icacls(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1332, stdout=echoed, stderr="")

    monkeypatch.setattr(subprocess, "run", icacls)
    acl = _FakeAcl()
    monkeypatch.setattr(acl, "lock", WindowsAcl().lock)
    with pytest.raises(ProviderError) as caught:
        secure_windows_root(tmp_path / "w", acl)
    assert "exit 1332" in str(caught.value)
    assert "No mapping" not in str(caught.value) and _FakeAcl.ME not in str(caught.value)


def test_a_root_message_redacts_the_login_and_the_home_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 3, item 6: a path segment equal to the login or the home folder's name is
    ``<user>`` in every root message and doctor detail, the sandbox check's own text included."""
    login, home = "inv-login", "inv-login.CORP"
    monkeypatch.setenv("LOGNAME", login)
    monkeypatch.setenv(HOME_ENV, str(tmp_path / home))
    for name in (login, home):
        parent = tmp_path / "Users" / name
        parent.mkdir(parents=True)
        (parent / "w").write_text("not a directory\n", encoding="utf-8")
        with pytest.raises(ProviderError) as caught:
            secure_windows_root(parent / "w", _FakeAcl())
        said = str(caught.value)
        assert "not a directory" in said and "<user>" in said, said
        assert name.casefold() not in said.casefold(), said
        ok, detail = root_state(parent / "w")
        assert not ok and "<user>" in detail, detail
        assert name.casefold() not in detail.casefold(), detail
    foreign = _private_mkdir(tmp_path / "Users" / login / "f")
    with pytest.raises(ProviderError) as caught:
        secure_windows_root(foreign, _FakeAcl(owner=_FakeAcl.OTHER))
    assert "<user>" in str(caught.value) and login not in str(caught.value)


def test_the_root_state_names_each_failing_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix round 3, item 7: ``root_state`` (doctor check 9's root words) on a missing root, on
    a file where the root should be, and on a root another principal may write to."""
    assert root_state(tmp_path / "absent") == (False, "root NOT private: it does not exist yet")
    (tmp_path / "file").write_text("x\n", encoding="utf-8")
    ok, detail = root_state(tmp_path / "file")
    assert not ok and detail.startswith("root NOT private: ") and "not a directory" in detail
    shared = _private_mkdir(tmp_path / "shared")
    acl = _FakeAcl(writers=[_FakeAcl.ME, "S-1-5-4"])
    if sys.platform == "win32":
        monkeypatch.setattr("claude_bully.providers.claude_code.WIN_ACL", acl)
        said = "writable by S-1-5-4"
    else:
        os.chmod(shared, 0o755)
        said = "mode 755"
    ok, detail = root_state(shared)
    assert not ok and detail.startswith("root NOT private: ") and said in detail, detail
    acl.writers = [_FakeAcl.ME]
    os.chmod(shared, 0o700)
    assert root_state(shared) == (True, "root locked")


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows ACL lock")
def test_the_real_lock_leaves_only_the_user_system_and_administrators(tmp_path: Path) -> None:
    root = tmp_path / "w"
    assert secure_windows_root(root, WIN_ACL) == "locked"
    owner, writers = WIN_ACL.owner_and_writers(root)
    me = WIN_ACL.current_sid()
    assert isinstance(WIN_ACL.is_elevated(), bool)
    assert owner == (ADMINISTRATORS_SID if WIN_ACL.is_elevated() else me)
    # Python's os.mkdir(root, 0o700) adds OWNER RIGHTS on Windows (3.12.4 and later), the lock
    # the user; nothing else
    assert set(writers) - {"S-1-3-4"} == {me, SYSTEM_SID, ADMINISTRATORS_SID}
    listing = subprocess.run(["icacls", str(root)], capture_output=True, text=True, check=True)
    assert "(I)" not in listing.stdout  # inheritance removed
    assert listing.stdout.count("(OI)(CI)(F)") == len(set(writers))
    # and a cwd made in it as the provider makes one passes the cwd check
    secure_windows_cwd(prepare_sandbox(root / "0123456789ab", fresh=False), WIN_ACL)
    assert secure_windows_root(root, WIN_ACL) == "ours"  # and it is used again as is


def test_a_run_id_in_any_segment_is_a_problem() -> None:
    path = Path("/srv") / "keep_rung0_smoke_env_here" / "w"
    problems = neutral_cwd_problems(path, run_ids=["rung0_smoke_env"])
    assert len(problems) == 1 and "run id" in problems[0]
    assert neutral_cwd_problems(path, run_ids=["other_run"]) == []
    assert neutral_cwd_problems(Path("/srv/w/0123456789ab")) == []


def test_a_state_dir_names_its_run_id(tmp_path: Path) -> None:
    """A run's state dir is ``<runs root>/<run id>/state/...``: a root under the run itself is
    refused by the run id even where no forbidden word is in the path."""
    state = tmp_path / "deposit" / "pilot_x" / "state" / "cell" / "rep0" / "target"
    p = ClaudeCodeProvider(model="sonnet", state_dir=state, command=["claude"])
    assert p.run_ids == ["pilot_x"]


def test_a_root_inside_the_repo_is_refused_before_any_child_starts(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, log = fake_claude
    monkeypatch.setenv(CHILD_ROOT_ENV, str(Path(__file__).resolve().parent.parent / "w"))
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    assert p.cwd_problems()
    with pytest.raises(ProviderError, match="not neutral"):
        p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert not log.exists()  # no child started
    assert not p.cwd.exists()  # and nothing was made inside the repo


def test_a_root_under_a_run_is_refused(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, log = fake_claude
    state = tmp_path / "deposit" / "pilot_x" / "state" / "target"
    monkeypatch.setenv(CHILD_ROOT_ENV, str(tmp_path / "deposit" / "pilot_x" / "w"))
    p = ClaudeCodeProvider(model="sonnet", state_dir=state, command=command)
    with pytest.raises(ProviderError, match="run id"):
        p.complete("c", "SYS", [Message(role="user", content="hi")])
    assert not log.exists()


def test_rate_limit_raises(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "ratelimit")
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    with pytest.raises(RateLimitError):
        p.complete("c", "SYS", [Message(role="user", content="hi")])


def test_crash_raises_provider_error(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    with pytest.raises(ProviderError):
        p.complete("c", "SYS", [Message(role="user", content="hi")])


def test_json_schema_passes_flag_and_reads_structured_output(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    p = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    schema = {"type": "object", "properties": {"k": {"type": "string"}}}
    out = p.complete("c", "SYS", [Message(role="user", content="hi")], json_schema=schema)
    argv = list(map(str, _read_log(log)[0]["argv"]))  # type: ignore[call-overload]
    assert json.loads(argv[argv.index("--json-schema") + 1]) == schema
    assert json.loads(out.text) == {"echo": schema}


def test_build_provider_claude_code(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.claude_code, model="sonnet", effort="high")
    p = build_provider(role, tmp_path)
    assert isinstance(p, ClaudeCodeProvider) and p.name == "claude_code"


# ------------------------------------------------------------------ MCP sandbox tools

TOOLS = [TOOL_SPECS["web_search"], TOOL_SPECS["fetch"], TOOL_SPECS["ls"]]
ALLOWED = ",".join(f"mcp__{SERVER_NAME}__{name}" for name in ("web_search", "fetch", "ls"))
MEMO = "/srv/authority/memos/parking-q3.txt"
ABOUT = "https://pennetferry.example/about"


def _user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


def _mcp_provider(
    tmp_path: Path, command: list[str], *, turn: int = 1, unlock: UnlockState | None = None
) -> tuple[ClaudeCodeProvider, Path]:
    """A provider with MCP on, and the state file the runtime would have written for ``turn``."""
    mcp_dir = tmp_path / "mcp"
    write_mcp_state(
        mcp_dir / "env_state.json",
        make_mcp_state(tools={"web_search", "fetch", "ls"}, turn=turn, unlock=unlock),
    )
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=command, mcp_state_dir=mcp_dir
    )
    return provider, mcp_dir


def _tool_call(monkeypatch: pytest.MonkeyPatch, *calls: dict[str, object]) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_TOOL_CALL", json.dumps(list(calls)))


def _argv(log: Path, index: int = 0) -> list[str]:
    return [str(a) for a in _read_log(log)[index]["argv"]]  # type: ignore[attr-defined]


def test_calls_without_tools_keep_the_exact_old_argv(tmp_path: Path) -> None:
    plain = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    with_mcp = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    for provider in (plain, with_mcp):
        for tools in (None, []):
            argv, session, resumed = provider.build_args("c", "SYS", None, tools)
            assert not resumed
            assert argv == [
                "claude",
                "-p",
                "--output-format",
                "json",
                "--model",
                "sonnet",
                "--setting-sources",
                "",
                "--strict-mcp-config",
                "--tools",
                "",
                "--system-prompt",
                "SYS",
                "--exclude-dynamic-system-prompt-sections",
                "--session-id",
                session,
            ]


def test_a_call_without_tools_does_not_touch_the_mcp_dir(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    out = provider.complete("c", "SYS", _user("hi"))
    assert out.tool_calls == [] and out.text == "reply to: hi"
    argv = _argv(log)
    assert "--mcp-config" not in argv and "--allowedTools" not in argv
    assert not (mcp_dir / "mcp.json").exists()


def test_tools_write_mcp_json_and_pass_the_flags_in_enabled_order(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    provider.complete("c", "SYS", _user("hi"), tools=TOOLS)

    argv = _argv(log)
    config_path = Path(argv[argv.index("--mcp-config") + 1])
    assert config_path.is_absolute() and config_path == (mcp_dir / "mcp.json").resolve()
    assert argv[argv.index("--allowedTools") + 1] == ALLOWED
    assert argv[argv.index("--tools") + 1] == ""  # built-in tools stay off
    assert "--strict-mcp-config" in argv
    # each variadic flag is closed by the flag after it, never by the end of the argv
    assert argv[argv.index("--mcp-config") + 2].startswith("--")
    assert argv[argv.index("--allowedTools") + 2].startswith("--")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert list(config) == ["mcpServers"] and list(config["mcpServers"]) == [SERVER_NAME]
    server = config["mcpServers"][SERVER_NAME]
    assert Path(server["command"]) == Path(sys.executable)
    # a launcher script beside mcp.json, so the package name is not spelled out in the config
    launcher, flag, state_arg = server["args"]
    assert flag == "--state"
    assert Path(launcher) == (mcp_dir / LAUNCHER_FILE).resolve() and Path(launcher).is_file()
    assert Path(state_arg).is_absolute() and Path(state_arg) == mcp_dir.resolve()
    assert "\\" not in state_arg and "\\" not in launcher and "\\" not in server["command"]


def test_the_fake_client_sees_only_the_enabled_tools(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    provider.complete("c", "SYS", _user("hi"), tools=TOOLS)
    assert _read_log(log)[0]["mcp"]["listed"] == ["web_search", "fetch", "ls"]  # type: ignore[index]


def test_pre_executed_calls_come_back_with_their_results(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})
    out = provider.complete("c", "SYS", _user("look it up"), tools=TOOLS)

    [call] = out.tool_calls
    assert call.executed is True
    assert (call.id, call.name, call.args) == ("mcp-1-1", "fetch", {"url": ABOUT})
    assert call.result_text is not None and "operates the passenger crossing" in call.result_text
    assert out.text.endswith(call.result_text)  # the client really got it from the server
    record = json.loads((mcp_dir / "tools.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["result_text"] == call.result_text and record["status"] == "200"


def test_several_calls_come_back_in_the_order_they_ran(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    _tool_call(
        monkeypatch,
        {"name": "web_search", "arguments": {"query": "ferry"}},
        {"name": "fetch", "arguments": {"url": ABOUT}},
        {"name": "ls", "arguments": {"path": "journal"}},
    )
    out = provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert [(c.id, c.name) for c in out.tool_calls] == [
        ("mcp-1-1", "web_search"),
        ("mcp-1-2", "fetch"),
        ("mcp-1-3", "ls"),
    ]
    assert all(isinstance(c, ToolCallRequest) and c.executed for c in out.tool_calls)


def test_only_lines_added_during_the_call_are_returned(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, log = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    stale = {"id": "mcp-0-1", "tool": "fetch", "args": {}, "result_text": "old"}
    (mcp_dir / "tools.jsonl").write_text(json.dumps(stale) + "\n", encoding="utf-8")
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})

    first = provider.complete("c", "SYS", _user("one"), tools=TOOLS)
    second = provider.complete(
        "c",
        "SYS",
        [*_user("one"), Message(role="assistant", content="r"), *_user("two")],
        tools=TOOLS,
    )
    assert [c.id for c in first.tool_calls] == ["mcp-1-1"]
    assert [c.id for c in second.tool_calls] == ["mcp-1-2"]
    assert "--resume" in _argv(log, 1) and "--mcp-config" in _argv(log, 1)  # every call


def test_the_state_written_before_the_call_is_what_the_server_reads(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command, turn=1)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": MEMO}})

    locked = provider.complete("c", "SYS", _user("one"), tools=TOOLS)
    [refused] = locked.tool_calls
    assert refused.result_text == "HTTP 403 Forbidden" and refused.id == "mcp-1-1"

    # the runtime unlocks the memo and moves to turn 2 before the next call
    path = mcp_dir / "env_state.json"
    state = read_mcp_state(path)
    state.unlock.docs_unlocked.add("ops-memo-parking")
    state.turn = 2
    write_mcp_state(path, state)

    opened = provider.complete(
        "c",
        "SYS",
        [*_user("one"), Message(role="assistant", content="r"), *_user("two")],
        tools=TOOLS,
    )
    [served] = opened.tool_calls
    assert served.id == "mcp-2-1"
    assert served.result_text is not None and "The east lot is closed" in served.result_text


def test_a_tool_outside_the_enabled_list_is_refused_by_the_client(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, mcp_dir = _mcp_provider(tmp_path, command)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})
    out = provider.complete("c", "SYS", _user("hi"), tools=[TOOL_SPECS["web_search"]])
    assert out.tool_calls == [] and "permission denied: fetch" in out.text
    assert not (mcp_dir / "tools.jsonl").exists()


def test_tools_without_an_mcp_state_dir_fail_loudly(
    tmp_path: Path, fake_claude: tuple[list[str], Path]
) -> None:
    command, log = fake_claude
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=command)
    with pytest.raises(ProviderError, match="mcp_state_dir"):
        provider.complete("c", "SYS", _user("hi"), tools=TOOLS)
    assert not log.exists()


# ------------------------------------------------- stream-json for calls that carry tools

# the fake's thinking block (tests/fixtures/fake_claude.py THINKING): the reasoning channel
FAKE_THINKING = "PRIVATE REASONING THAT MUST NEVER BE RECORDED"


def _events(*events: dict[str, object]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def _said(*blocks: dict[str, object]) -> dict[str, object]:
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def _text(text: str) -> dict[str, object]:
    return {"type": "text", "text": text}


def _use(name: str = f"mcp__{SERVER_NAME}__fetch") -> dict[str, object]:
    return {"type": "tool_use", "id": "toolu_1", "name": name, "input": {"url": ABOUT}}


_TOOL_RESULT = {
    "type": "user",
    "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1"}]},
}
_INIT = {"type": "system", "subtype": "init", "session_id": "s-1"}


def _result(text: str = "Final.", **extra: object) -> dict[str, object]:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": text,
        "session_id": "s-1",
        "total_cost_usd": 0.02,
        "usage": {"input_tokens": 7, "output_tokens": 3},
        **extra,
    }


def test_calls_with_tools_stream_json_with_verbose_and_keep_the_isolation_flags(
    tmp_path: Path,
) -> None:
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    argv, _, _ = provider.build_args("c", "SYS", None, TOOLS)
    assert argv[:5] == ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    assert argv.count("--output-format") == 1 and "json" not in argv
    for flag, value in (("--setting-sources", ""), ("--tools", ""), ("--model", "sonnet")):
        assert argv[argv.index(flag) + 1] == value
    assert "--strict-mcp-config" in argv and "--exclude-dynamic-system-prompt-sections" in argv
    assert argv[argv.index("--allowedTools") + 1] == ALLOWED


def test_text_before_each_tool_use_comes_back_as_interim_text_in_order(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, log = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    _tool_call(
        monkeypatch,
        {"name": "web_search", "arguments": {"query": "ferry"}},
        {"name": "fetch", "arguments": {"url": ABOUT}},
    )
    monkeypatch.setenv("FAKE_CLAUDE_INTERIM", json.dumps(["First a search.", "Now the page."]))
    out = provider.complete("c", "SYS", _user("go"), tools=TOOLS)

    assert out.interim_texts == ["First a search.", "Now the page."]
    # the reply is the result event's text: the block after the last tool result
    assert out.text.startswith("reply to: go") and "First a search." not in out.text
    assert [c.id for c in out.tool_calls] == ["mcp-1-1", "mcp-1-2"]
    assert out.cost_usd == 0.01 and (out.usage.input_tokens, out.usage.output_tokens) == (10, 5)
    argv = _argv(log)
    assert out.raw_session_ref == argv[argv.index("--session-id") + 1]
    assert provider.session_ref("c") == out.raw_session_ref


def test_the_reasoning_channel_in_a_stream_is_never_kept(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})
    out = provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert out.interim_texts == ["Let me use fetch."]
    assert out.reasoning_text is None and FAKE_THINKING not in out.model_dump_json()


def test_whitespace_only_text_beside_a_tool_use_is_not_interim_text(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    _tool_call(
        monkeypatch,
        {"name": "web_search", "arguments": {"query": "ferry"}},
        {"name": "fetch", "arguments": {"url": ABOUT}},
    )
    monkeypatch.setenv("FAKE_CLAUDE_INTERIM", json.dumps(["\n\n", "Now the page."]))
    out = provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert out.interim_texts == ["Now the page."]


@pytest.mark.parametrize("mode", ["stream_malformed", "stream_truncated"])
def test_a_malformed_or_truncated_stream_is_a_provider_error_not_an_empty_turn(
    tmp_path: Path,
    fake_claude: tuple[list[str], Path],
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    command, _ = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    _tool_call(monkeypatch, {"name": "fetch", "arguments": {"url": ABOUT}})
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    with pytest.raises(ProviderError) as info:
        provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert not isinstance(info.value, RateLimitError)
    assert provider.session_ref("c") is None  # a failed call never records a session


def test_a_rate_limit_on_the_stream_path_raises(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, log = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "ratelimit")
    with pytest.raises(RateLimitError):
        provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert "stream-json" in _argv(log)


def test_a_crash_on_the_stream_path_is_a_provider_error(
    tmp_path: Path, fake_claude: tuple[list[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    command, _ = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    with pytest.raises(ProviderError, match="exited 2"):
        provider.complete("c", "SYS", _user("go"), tools=TOOLS)


def test_a_stream_cut_off_mid_character_is_a_provider_error(tmp_path: Path) -> None:
    cut = 'import sys; sys.stdout.buffer.write(b\'{"type": "assistant", "text": "caf\\xc3\')'
    provider, _ = _mcp_provider(tmp_path, [sys.executable, "-c", cut])
    with pytest.raises(ProviderError, match="not valid UTF-8") as info:
        provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert not isinstance(info.value, RateLimitError)


def test_a_timeout_on_the_stream_path_is_a_provider_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, _ = _mcp_provider(tmp_path, ["claude"])

    def too_slow(argv: list[str], *args: object, **kwargs: object) -> object:
        assert "stream-json" in argv
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(subprocess, "run", too_slow)
    with pytest.raises(ProviderError, match="timed out"):
        provider.complete("c", "SYS", _user("go"), tools=TOOLS)


def test_a_failed_stream_is_not_a_rate_limit_because_the_target_said_try_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, _ = _mcp_provider(tmp_path, ["claude"])
    stdout = _events(_INIT, _said(_text("That failed, so let me try again."), _use()))

    def failed(argv: list[str], *args: object, **kwargs: object) -> object:
        return subprocess.CompletedProcess(argv, 1, stdout=stdout.encode(), stderr=b"boom")

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(ProviderError) as info:
        provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    assert not isinstance(info.value, RateLimitError) and "boom" in str(info.value)


def test_stream_parsing_keeps_text_before_a_tool_use_and_the_result_as_the_reply(
    tmp_path: Path,
) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    stdout = _events(
        _INIT,
        _said({"type": "thinking", "thinking": FAKE_THINKING, "signature": "x"}),
        _said(_text("A")),
        _said(_text("B"), _use()),
        _TOOL_RESULT,
        _said(_text("C"), _use(f"mcp__{SERVER_NAME}__ls")),
        _TOOL_RESULT,
        _said(_text("Final.")),
        _result(),
    )
    out = provider.parse_stream(stdout, "fallback-session")
    assert out.interim_texts == ["A", "B", "C"] and out.text == "Final."
    assert (out.usage.input_tokens, out.usage.output_tokens, out.cost_usd) == (7, 3, 0.02)
    assert out.raw_session_ref == "s-1" and out.stop_reason == "success"
    assert FAKE_THINKING not in out.model_dump_json() and out.reasoning_text is None


def test_stream_parsing_reads_structured_output_from_the_result_event(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    out = provider.parse_stream(_events(_result(structured_output={"k": 1})), "s")
    assert json.loads(out.text) == {"k": 1} and out.interim_texts == []


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        _events(_INIT, _said(_text("Looking."), _use()), _TOOL_RESULT),  # no result event
        _events(_INIT) + '{"type": "result", "is_err',  # cut mid-line
        _events(_INIT) + "not json\n" + _events(_result()),
        _events(_INIT) + "[1, 2]\n" + _events(_result()),  # JSON, but not an event
    ],
    ids=["empty", "no_result", "cut_mid_line", "not_json", "not_an_object"],
)
def test_stream_parsing_refuses_a_malformed_or_truncated_stream(
    tmp_path: Path, stdout: str
) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    with pytest.raises(ProviderError) as info:
        provider.parse_stream(stdout, "s")
    assert not isinstance(info.value, RateLimitError)


@pytest.mark.parametrize("mode", ["thinking_torn", "thinking_died"])
def test_a_stream_torn_inside_a_thinking_event_quotes_no_reasoning(
    tmp_path: Path,
    fake_claude: tuple[list[str], Path],
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    """Preflight C24 (Phase 1 carry m2): a stream cut off inside a thinking event, with exit 0
    or exit 1, is a ProviderError that names the event's type and length and quotes none of it.
    The reasoning channel is never printed, stored or passed on."""
    command, _ = fake_claude
    provider, _ = _mcp_provider(tmp_path, command)
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    with pytest.raises(ProviderError) as info:
        provider.complete("c", "SYS", _user("go"), tools=TOOLS)
    message = str(info.value)
    assert not isinstance(info.value, RateLimitError)
    assert "PRIVATE" not in message and "REASONING" not in message
    assert "'assistant'" in message and "characters" in message


def test_no_stream_failure_quotes_a_thinking_block(tmp_path: Path) -> None:
    """Preflight C24: whatever way the stream breaks around a thinking event, the error names
    events by type and length only."""
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    thinking = _events(_said({"type": "thinking", "thinking": FAKE_THINKING, "signature": "x"}))
    torn = thinking[: thinking.index(FAKE_THINKING) + len(FAKE_THINKING)]
    for stdout in (
        _events(_INIT) + thinking,  # ends after the thinking event: no result
        _events(_INIT) + torn,  # cut inside it
        _events(_INIT) + torn + "\n" + _events(_result()),  # a torn line mid-stream
    ):
        with pytest.raises(ProviderError) as info:
            provider.parse_stream(stdout, "s")
        assert "PRIVATE" not in str(info.value) and "'assistant'" in str(info.value)


def test_stream_parsing_raises_on_an_error_result(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    limited = _result("Claude AI usage limit reached", is_error=True, subtype="error")
    with pytest.raises(RateLimitError):
        provider.parse_stream(_events(_INIT, limited), "s")
    failed = _result("Something broke", is_error=True, subtype="error_during_execution")
    with pytest.raises(ProviderError, match="Something broke") as info:
        provider.parse_stream(
            _events(_INIT, _said(_text("Let me try again."), _use()), failed), "s"
        )
    assert not isinstance(info.value, RateLimitError)


def test_build_provider_opts_in_to_mcp_for_claude_code_only(tmp_path: Path) -> None:
    role = RoleConfig(provider=ProviderKind.claude_code, model="sonnet")
    default = build_provider(role, tmp_path)
    assert isinstance(default, ClaudeCodeProvider) and default.mcp_state_dir is None
    opted = build_provider(role, tmp_path, with_mcp=True)
    assert isinstance(opted, ClaudeCodeProvider)
    assert opted.mcp_state_dir == (tmp_path / "mcp").resolve()
    stub_role = RoleConfig(provider=ProviderKind.stub, model="stub")
    assert build_provider(stub_role, tmp_path, with_mcp=True).name == "stub"


# ------------------------------------------------- nothing target-visible names the experiment


def test_nothing_the_target_can_see_names_the_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the interpreter's own path is whatever the machine has; everything else is ours to keep clean
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    provider._write_mcp_config()
    argv, _, _ = provider.build_args("c", "SYS", None, TOOLS)
    config_text = (tmp_path / "mcp" / "mcp.json").read_text(encoding="utf-8")
    for text in (" ".join(argv), config_text):
        assert "bully" not in text.lower(), text
    assert f"mcp__{SERVER_NAME}__web_search" in argv[argv.index("--allowedTools") + 1]


# --------------------------------------------------------- reading tools.jsonl safely


def test_a_half_written_last_line_is_ignored_even_mid_character(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    (tmp_path / "mcp").mkdir()
    done = {"id": "mcp-1-1", "tool": "fetch", "args": {}, "result_text": "caf\u00e9"}
    whole = json.dumps(done, ensure_ascii=False).encode("utf-8") + b"\n"
    tail = (
        b'{"id": "mcp-1-2", "tool": "fetch", "args": {}, "result_text": "caf'
        + "\u00e9".encode()[:1]
    )
    (tmp_path / "mcp" / "tools.jsonl").write_bytes(whole + tail)
    with pytest.raises(UnicodeDecodeError):
        tail.decode("utf-8")  # the fixture really is a mid-character tail

    [call] = provider._new_tool_calls(0)
    assert (call.id, call.result_text) == ("mcp-1-1", "caf\u00e9")


def test_a_complete_but_undecodable_line_is_a_provider_error(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    (tmp_path / "mcp").mkdir()
    (tmp_path / "mcp" / "tools.jsonl").write_bytes(b'{"id": "\xff\xfe"}\n')
    with pytest.raises(ProviderError, match="malformed line"):
        provider._new_tool_calls(0)


def test_blank_pieces_between_records_are_skipped(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(
        model="sonnet", state_dir=tmp_path, command=["claude"], mcp_state_dir=tmp_path / "mcp"
    )
    (tmp_path / "mcp").mkdir()
    record = json.dumps({"id": "mcp-1-1", "tool": "ls", "args": {}, "result_text": "x"})
    (tmp_path / "mcp" / "tools.jsonl").write_bytes(f"\n{record}\n\n".encode())
    assert [c.id for c in provider._new_tool_calls(0)] == ["mcp-1-1"]


# --------------------------------------------------------------- finding the claude binary


def _npm_layout(tmp_path: Path, *, native_at: str | None) -> Path:
    """An npm global install: ``<prefix>/claude.cmd`` plus, optionally, the native binary."""
    prefix = tmp_path / "npm"
    shim_dir = prefix / "bin"
    shim_dir.mkdir(parents=True)
    shim = shim_dir / "claude.cmd"
    shim.write_text("@echo off\n", encoding="utf-8")
    if native_at is not None:
        base = shim_dir if native_at == "beside" else prefix
        exe = base / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"MZ")
    return shim


def _which(monkeypatch: pytest.MonkeyPatch, found: str | Path | None) -> None:
    monkeypatch.setattr(
        shutil, "which", lambda name, *a, **k: None if found is None else str(found)
    )


@pytest.fixture(autouse=False)
def no_claude_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CLAUDE_ENV, raising=False)


def test_an_explicit_command_wins_over_everything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_ENV, "/from/env")
    _which(monkeypatch, "/from/path")
    explicit = ["python", "fake.py"]
    resolved = resolve_claude_command(explicit)
    assert resolved == ["python", "fake.py"] and resolved is not explicit


def test_the_env_var_is_one_path_and_is_not_split(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_ENV, "C:/Program Files/Claude Code/claude.exe")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: pytest.fail("PATH must not be searched"))
    assert resolve_claude_command(None) == ["C:/Program Files/Claude Code/claude.exe"]
    assert resolve_claude_command([]) == ["C:/Program Files/Claude Code/claude.exe"]


def test_an_empty_env_var_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLAUDE_ENV, "")
    _which(monkeypatch, "/usr/local/bin/claude")
    assert resolve_claude_command(None) == ["/usr/local/bin/claude"]


def test_a_real_executable_on_path_is_used_as_is(
    monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    for found in ("/usr/local/bin/claude", "C:/tools/claude.exe", "/opt/claude/claude"):
        _which(monkeypatch, found)
        assert resolve_claude_command(None) == [found]


@pytest.mark.parametrize("native_at", ["beside", "above"])
def test_a_cmd_shim_resolves_to_the_native_binary_it_wraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None, native_at: str
) -> None:
    shim = _npm_layout(tmp_path, native_at=native_at)
    _which(monkeypatch, shim)
    [command] = resolve_claude_command(None)
    assert Path(command).name == "claude.exe" and Path(command).is_file()
    assert "claude-code" in Path(command).parts
    expected = (shim.parent if native_at == "beside" else shim.parent.parent) / "node_modules"
    assert Path(command).is_relative_to(expected)


@pytest.mark.parametrize("name", ["claude.bat", "claude.ps1", "claude.CMD"])
def test_every_script_shim_suffix_is_treated_as_a_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None, name: str
) -> None:
    shim = _npm_layout(tmp_path, native_at="beside").with_name(name)
    shim.write_text("x", encoding="utf-8")
    _which(monkeypatch, shim)
    [command] = resolve_claude_command(None)
    assert Path(command).name == "claude.exe"


def test_the_beside_binary_is_preferred_to_the_one_above(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    shim = _npm_layout(tmp_path, native_at="beside")
    above = shim.parent.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin"
    above.mkdir(parents=True)
    (above / "claude.exe").write_bytes(b"MZ")
    _which(monkeypatch, shim)
    [command] = resolve_claude_command(None)
    assert Path(command).is_relative_to(shim.parent / "node_modules")


def test_a_shim_with_no_native_binary_is_an_error_that_says_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    shim = _npm_layout(tmp_path, native_at=None)
    _which(monkeypatch, shim)
    with pytest.raises(ProviderError) as info:
        resolve_claude_command(None)
    message = str(info.value)
    assert str(shim) in message and CLAUDE_ENV in message


def test_claude_not_found_is_an_error_that_says_what_to_do(
    monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    _which(monkeypatch, None)
    with pytest.raises(ProviderError) as info:
        resolve_claude_command(None)
    assert CLAUDE_ENV in str(info.value) and "PATH" in str(info.value)


def test_the_provider_resolves_lazily_so_building_one_never_needs_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_claude_env: None
) -> None:
    _which(monkeypatch, None)
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path)  # does not raise
    with pytest.raises(ProviderError, match=CLAUDE_ENV):
        provider.complete("c", "SYS", _user("hi"))
    monkeypatch.setenv(CLAUDE_ENV, "/somewhere/claude")
    assert provider.command == ["/somewhere/claude"]
    argv, _, _ = provider.build_args("c", "SYS", None)
    assert argv[0] == "/somewhere/claude"


def test_the_provider_keeps_an_explicit_command_untouched(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["a", "b"])
    assert provider.command == ["a", "b"]


def test_role_command_reaches_the_provider(tmp_path: Path) -> None:
    default = RoleConfig(provider=ProviderKind.claude_code, model="sonnet")
    assert default.command is None
    role = RoleConfig(
        provider=ProviderKind.claude_code, model="sonnet", command=["C:/x/claude.exe", "--flag"]
    )
    provider = build_provider(role, tmp_path)
    assert isinstance(provider, ClaudeCodeProvider)
    assert provider.command == ["C:/x/claude.exe", "--flag"]


# Each wording a usage or rate limit has been reported in, paraphrased so no fixture names a
# product (final review I1). A miss is a plain ProviderError, which aborts the rep a resume then
# skips; a hit pauses the run and --wait-on-rate-limit waits it out.
LIMIT_WORDINGS = [
    "usage limit reached|1762444800",
    "You've hit your limit · resets 3pm",
    "You've hit your limit · resets 3pm (Europe/Lisbon)",
    "5-hour limit reached ∙ resets 3pm",
    "Weekly limit reached ∙ resets Mon 9am",
    "Your limit will reset at 3pm.",
    "Session limit reached. Resets at 15:00.",
    "API Error: 429 rate_limit_error: Number of request tokens has exceeded your rate limit",
    "API Error: 429 Too Many Requests",
    "API Error: 529 overloaded_error: Overloaded",
]


@pytest.mark.parametrize("wording", LIMIT_WORDINGS)
def test_every_known_limit_wording_is_a_rate_limit_on_an_error_result(
    tmp_path: Path, wording: str
) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    limited = _result(wording, is_error=True, subtype="error")
    with pytest.raises(RateLimitError):
        provider.parse_stream(_events(_INIT, limited), "s")


@pytest.mark.parametrize("wording", LIMIT_WORDINGS)
def test_every_known_limit_wording_is_a_rate_limit_on_a_failed_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wording: str
) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])

    def failed(argv: list[str], *args: object, **kwargs: object) -> object:
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=wording.encode())

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(RateLimitError):
        provider.complete("c", "SYS", [Message(role="user", content="hi")])


@pytest.mark.parametrize(
    "text",
    ["a limited edition", "sunset at six", "the presets are fine", "my limits are mine"],
)
def test_a_limit_word_alone_is_not_a_rate_limit(tmp_path: Path, text: str) -> None:
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    failed = _result(text, is_error=True, subtype="error_during_execution")
    with pytest.raises(ProviderError) as info:
        provider.parse_stream(_events(_INIT, failed), "s")
    assert not isinstance(info.value, RateLimitError)


def test_an_error_result_naming_a_login_is_a_login_even_when_it_says_try_again(
    tmp_path: Path,
) -> None:
    """Task 3 M5: on an error result the login check runs first, so a login text that says
    "try again" is never a pause that waits on a limit that is not there."""
    provider = ClaudeCodeProvider(model="sonnet", state_dir=tmp_path, command=["claude"])
    text = "Invalid API key. Please run the login command and try again."
    failed = _result(text, is_error=True, subtype="error")
    with pytest.raises(ProviderError, match="not logged in") as info:
        provider.parse_stream(_events(_INIT, failed), "s")
    assert not isinstance(info.value, RateLimitError)
