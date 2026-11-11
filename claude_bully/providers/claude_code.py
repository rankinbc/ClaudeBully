"""Backend that shells out to ``claude -p`` (Claude Code print mode).

One Claude Code session per conversation: the first call passes ``--session-id``,
later calls ``--resume`` and send only the newest user message. Isolation flags
keep the target free of the operator's settings, plugins, MCP servers and tools.

Sandbox tools (``tools=``) reach the model through a stdio MCP server that Claude Code launches
(``environments/mcp_server.py``): ``--tools ""`` still switches the built-ins off,
``--mcp-config`` names the server and ``--allowedTools`` permits exactly the enabled tools.
The server records each call in ``<mcp_state_dir>/tools.jsonl``; the lines added during a call
come back as already-executed ``ToolCallRequest`` objects.

A call with tools runs with ``--output-format stream-json --verbose``, so what the model writes
between its tool calls is not lost: every assistant text block that comes before a ``tool_use``
becomes one of ``Completion.interim_texts``, in order (thinking blocks are never kept). The reply,
the usage and the cost come from the stream's ``result`` event, as with ``--output-format json``,
which every call without tools (bully, judge, plain targets) still uses. A broken stream's error
names its events by type and length and quotes none of them: an event may hold the target's
reasoning, which is never printed, stored or passed on (preflight C24).

The child's working directory (rung 0 finding 1, Task 12). The CLI attaches context that
``--system-prompt`` does not replace: the account's email address, the real date, the model id and
an ``# Environment`` block naming the working directory and whether it is a git repository. So the
child never runs under the run's state directory (which named the harness, the run id and, in the
user's profile path, the owner): it runs from ``child_cwd(state_dir)``, an opaque
``<root>/<12 hex digits>`` under ``child_cwd_root()``. The digest is the same for the same state
dir in every process, because the CLI files a session under its working directory's project folder
and ``--resume`` finds it only from the same directory. ``neutral_cwd_problems`` names what a
working directory must not hold, and ``complete`` refuses one with problems before any child
starts. The date, the model id and the email address are not removed by any of this: no switch
that keeps the OAuth login drops them, so analysis states the date (``temporal.json``) and
``promote`` blocks an email address.
"""

import functools
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Final

from claude_bully.environments.mcp_server import (
    MCP_CONFIG_FILE,
    SERVER_NAME,
    TOOLS_FILE,
    write_launcher,
)
from claude_bully.providers.base import (
    Completion,
    Message,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    ToolCallRequest,
    ToolSpec,
)
from claude_bully.records import Usage
from claude_bully.runner.sandbox import UnsafeSandboxError, prepare_sandbox, verify_private_dir

# a usage or rate limit, in every wording one has been reported in (final review I1: "hit your
# limit" and "limit reached" carry neither "usage limit" nor "rate limit"); the new alternatives
# are word-bounded, and on an error result the login check runs first (Task 3 M5), since a login
# text may say "try again"
_RATE_LIMIT: Final = re.compile(
    r"(?i)usage limit|rate[ _]limit|try again|too many requests|overloaded"
    r"|\bhit your limit\b|\blimit reached\b|\blimit will reset\b|\bresets? at\b"
)
# the type of the event a stream line holds, read without parsing it (the line may be cut off)
_EVENT_TYPE: Final = re.compile(r'"type"\s*:\s*"([A-Za-z_]{1,40})"')

# The environment variable naming the claude executable: one path, never split.
CLAUDE_ENV: Final = "CLAUDE_BULLY_CLAUDE"
_SHIM_SUFFIXES: Final = frozenset({".cmd", ".bat", ".ps1"})
_NATIVE_BINARY: Final = (
    Path("node_modules") / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
)
DEFAULT_TIMEOUT_S: Final = 600.0
# Claude Code waits this long on one MCP tool call (its MCP_TOOL_TIMEOUT, in milliseconds); a
# nested responder must fail before it does, or the whole target turn is lost
DEFAULT_MCP_TOOL_TIMEOUT_S: Final = 300.0
MCP_TOOL_TIMEOUT_ENV: Final = "MCP_TOOL_TIMEOUT"
# a child claude -p must not learn it runs inside Claude Code: the variables it would read
STRIPPED_PREFIXES: Final = ("CLAUDECODE", "CLAUDE_CODE_")
# an error result that says the session is not logged in; every alternative is word-bounded
# so "catalog in use" or "blog index" is not read as one (P21)
_LOGIN: Final = re.compile(
    r"(?i)\bnot logged in\b|\blog ?in\b|\bauthenticat|\bapi key\b|\bunauthori[sz]ed\b|\bsign in\b"
)


# The environment variable naming the root every child claude -p works under (Task 12, R1).
CHILD_ROOT_ENV: Final = "CLAUDE_BULLY_CHILD_ROOT"
# the default root's last segment: opaque on purpose
_CHILD_ROOT_NAME: Final = "w"
_CHILD_DIGEST_LENGTH: Final = 12
# words no segment of a child's working directory may contain (R3), compared case-insensitively
FORBIDDEN_CWD_WORDS: Final = ("claude", "bully", "harness", "runs")
# the files and folder Claude Code reads as project context from its cwd and every ancestor
# (fix round 1, M1); a child's cwd under any of them is refused
PROJECT_FILES: Final = ("CLAUDE.md", "CLAUDE.local.md", ".claude", ".mcp.json")
# the segment a run's state lives under: ``<runs root>/<run id>/state/...`` (runner/store.py)
_STATE_SEGMENT: Final = "state"


def child_cwd_root() -> Path:
    """The root every child ``claude -p`` works under: ``$CLAUDE_BULLY_CHILD_ROOT`` when set;
    else ``w`` under ``%PUBLIC%`` on Windows (any interactive user may create a directory there)
    and ``/tmp/w`` elsewhere. No default names the user, the harness or a run."""
    configured = os.environ.get(CHILD_ROOT_ENV)
    if configured:  # absolute once, here: the cwd never follows the process cwd (M4)
        return Path(configured).resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / _CHILD_ROOT_NAME
    return Path("/tmp") / _CHILD_ROOT_NAME


def child_cwd(state_dir: Path) -> Path:
    """Where the provider on ``state_dir`` runs its children: ``<root>/<sha256 of the resolved
    state dir, 12 hex digits>``. Computes the path only."""
    key = str(state_dir.resolve()).encode("utf-8")
    return child_cwd_root() / hashlib.sha256(key).hexdigest()[:_CHILD_DIGEST_LENGTH]


def neutral_cwd_problems(path: Path, *, run_ids: Iterable[str] = ()) -> list[str]:
    """What makes ``path`` unfit as a child's working directory, one line per fault: a segment
    equal (case-insensitively) to the user's login or the home folder's name, or one containing a
    ``FORBIDDEN_CWD_WORDS`` word or one of ``run_ids``. [] when it is neutral. A line never
    repeats the user's name it found, so no log or doctor report holds it. Reads the path as
    given (the provider passes it resolved) and touches no file."""
    login, home = _user_names()
    ids = [run_id.casefold() for run_id in run_ids if run_id]
    problems: list[str] = []
    parts = path.parts[1:] if path.anchor else path.parts
    for number, part in enumerate(parts, start=1):
        folded = part.casefold()
        if login and folded == login:
            problems.append(f"segment {number} is the user's login")
            continue
        if home and folded == home:
            problems.append(f"segment {number} is the home folder's name")
            continue
        words = [word for word in FORBIDDEN_CWD_WORDS if word in folded]
        if words:
            problems.append(f"segment {part!r} contains {', '.join(map(repr, words))}")
        if any(run_id in folded for run_id in ids):
            problems.append(f"segment {part!r} names a run id")
    return problems


def _user_names() -> tuple[str, str]:
    """The user's login and home folder name, case-folded; "" for one this environment cannot
    tell (a stripped environment: no ``LOGNAME``/``USERNAME``, no ``USERPROFILE``/``HOME``),
    whose clause is then skipped rather than crashing the check (M2)."""
    try:
        login = getpass.getuser()
    except Exception:  # getpass raises OSError, or on Windows ModuleNotFoundError (no pwd)
        login = ""
    try:
        home = Path.home().name
    except (RuntimeError, KeyError, OSError):
        home = ""
    return login.casefold(), home.casefold()


def inspect_project_files(path: Path) -> tuple[list[Path], list[Path]]:
    """(found, uninspectable): every ``PROJECT_FILES`` entry in ``path`` or one of its ancestors,
    nearest first, and every such path that could not be checked. Each name is checked with
    ``os.lstat``, as ``os.path.lexists`` does, so a link counts whether or not its target exists;
    unlike ``lexists``, an error other than "not there" is not read as absent: the path goes in
    the second list, so the check fails closed (fix round 2)."""
    found: list[Path] = []
    uninspectable: list[Path] = []
    for directory in (path, *path.parents):
        for name in PROJECT_FILES:
            candidate = directory / name
            try:
                os.lstat(candidate)
            except (FileNotFoundError, NotADirectoryError):
                continue
            except OSError:
                uninspectable.append(candidate)
                continue
            found.append(candidate)
    return found, uninspectable


# --- the Windows root's ACL (fix rounds 2 and 3) ----------------------------------------------
# The shared default root (%PUBLIC%\w) would inherit Public's ACL, which grants every interactive
# user Modify; the root is therefore created with an explicit ACL, inheritance removed, full control
# for the current user, SYSTEM and Administrators only, and an existing root is used only when this
# user owns it and no other principal may write to it. A root this process has just created must be
# empty after the lock (another user may have made a directory in it before), and the cell cwd gets
# the root's owner and writer check before any child starts. POSIX keeps prepare_sandbox's checks.
SYSTEM_SID: Final = "S-1-5-18"
ADMINISTRATORS_SID: Final = "S-1-5-32-544"
_CREATOR_OWNER_SID: Final = "S-1-3-0"
# OWNER RIGHTS: the rights of whoever owns the object, so no wider than the owner, which is checked
# on its own; Python's own ``os.mkdir(path, 0o700)`` on Windows (3.12.4 and later) makes a protected
# DACL of SYSTEM, Administrators and OWNER RIGHTS (fix round 3)
_OWNER_RIGHTS_SID: Final = "S-1-3-4"
# the access bits that let a principal add, change or remove what is in the root, or its ACL
_WRITE_BITS: Final = (
    0x2  # FILE_ADD_FILE
    | 0x4  # FILE_ADD_SUBDIRECTORY
    | 0x10  # FILE_WRITE_EA
    | 0x40  # FILE_DELETE_CHILD
    | 0x100  # FILE_WRITE_ATTRIBUTES
    | 0x10000  # DELETE
    | 0x40000  # WRITE_DAC
    | 0x80000  # WRITE_OWNER
    | 0x10000000  # GENERIC_ALL
    | 0x40000000  # GENERIC_WRITE
)
_WINDOWS_ONLY: Final = "the Windows ACL calls run on Windows only"


def _system32(program: str) -> str:
    """A Windows tool by its full path, so no same-named program earlier on PATH runs instead."""
    return str(Path(os.environ.get("SystemRoot") or "C:/Windows") / "System32" / program)


class WindowsAcl:
    """The Windows calls the root's lock needs, behind one seam (``WIN_ACL``), so a test can
    script each branch: the current user's SID, whether the token is elevated, the lock, and a
    directory's owner and writers. Every principal is a SID, never a name. Callers reach the seam
    through ``_acl_call``, so whatever it raises becomes a ``ProviderError`` (fix round 3)."""

    def current_sid(self) -> str:
        """This process's user SID, read from its token (the Win32 API: no subprocess, no
        name), once per process."""
        return _process_user_sid()

    def is_elevated(self) -> bool:
        """Whether this process's token is elevated (``TokenElevation``), once per process. An
        elevated token's new objects are owned by Administrators, not by the user."""
        return _token_elevated()

    def lock(self, path: Path, sid: str) -> int:
        """``icacls``: inheritance removed; full control, inherited by files and folders, for
        ``sid``, SYSTEM and Administrators. The exit code only: what ``icacls`` prints is never
        read, since a failure echoes the SID it was given (fix round 3)."""
        grants: list[str] = []
        for principal in (sid, SYSTEM_SID, ADMINISTRATORS_SID):
            grants += ["/grant:r", f"*{principal}:(OI)(CI)F"]
        out = subprocess.run(
            [_system32("icacls.exe"), str(path), "/inheritance:r", *grants],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return out.returncode

    def owner_and_writers(self, path: Path) -> tuple[str, list[str]]:
        """The owner's SID and the SID of every allowed ACE that grants a write bit, inherit-only
        ACEs included (they reach what is made inside). A null DACL is everyone (``S-1-1-0``); an
        allowed ACE this reader does not parse is reported as ``unparsed``."""
        return _read_owner_and_writers(path)


@functools.cache
def _win32() -> tuple[Any, Any]:
    """advapi32 and kernel32 with every function this module calls typed, so a 64-bit pointer or
    handle is never squeezed into a C int. Windows only: the seam's Windows instance calls it."""
    if sys.platform != "win32":
        raise ProviderError(_WINDOWS_ONLY)
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.POINTER(ctypes.c_void_p)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        pointer,
        pointer,
        pointer,
        pointer,
        pointer,
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, pointer]
    advapi.GetAce.restype = wintypes.BOOL
    return advapi, kernel


def _sid_text(sid: int | None) -> str:
    """A SID's ``S-1-...`` form; ``unparsed`` when it cannot be converted."""
    if sys.platform != "win32":  # the guard mypy narrows on: the rest is Windows-only (I1)
        raise ProviderError(_WINDOWS_ONLY)
    import ctypes

    advapi, kernel = _win32()
    text = ctypes.c_void_p()
    if not sid or not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)) or not text.value:
        return "unparsed"
    value = ctypes.wstring_at(text.value)
    kernel.LocalFree(text)
    return value


def _token_information(info_class: int, what: str) -> Any:
    """One ``GetTokenInformation`` class of this process's token, as a ctypes buffer the caller
    keeps alive while it reads pointers into it."""
    if sys.platform != "win32":
        raise ProviderError(_WINDOWS_ONLY)
    import ctypes
    from ctypes import wintypes

    advapi, kernel = _win32()
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x8, ctypes.byref(token)):
        raise ProviderError(f"cannot open this process's token (error {ctypes.get_last_error()})")
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, info_class, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(max(size.value, 4))
        length = wintypes.DWORD(ctypes.sizeof(buffer))
        if not advapi.GetTokenInformation(token, info_class, buffer, length, ctypes.byref(size)):
            raise ProviderError(f"cannot read {what} (error {ctypes.get_last_error()})")
        return buffer
    finally:
        kernel.CloseHandle(token)


@functools.cache
def _process_user_sid() -> str:
    """This process's user SID, from its token's ``TokenUser``."""
    if sys.platform != "win32":
        raise ProviderError(_WINDOWS_ONLY)
    import ctypes

    buffer = _token_information(1, "this user's SID")  # 1: TokenUser
    value = _sid_text(ctypes.c_void_p.from_buffer(buffer).value)  # TOKEN_USER.User.Sid
    if value == "unparsed":
        raise ProviderError("cannot convert this user's SID")
    return value


@functools.cache
def _token_elevated() -> bool:
    """Whether this process's token is elevated, from its ``TokenElevation`` (one DWORD)."""
    if sys.platform != "win32":
        raise ProviderError(_WINDOWS_ONLY)
    import ctypes

    buffer = _token_information(20, "this token's elevation")  # 20: TokenElevation
    return bool(ctypes.c_uint32.from_buffer(buffer).value)


def _read_owner_and_writers(path: Path) -> tuple[str, list[str]]:
    if sys.platform != "win32":
        raise ProviderError(_WINDOWS_ONLY)
    import ctypes

    class _AclHeader(ctypes.Structure):
        _fields_ = [
            ("revision", ctypes.c_ubyte),
            ("sbz1", ctypes.c_ubyte),
            ("size", ctypes.c_ushort),
            ("count", ctypes.c_ushort),
            ("sbz2", ctypes.c_ushort),
        ]

    class _Ace(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ubyte),
            ("flags", ctypes.c_ubyte),
            ("size", ctypes.c_ushort),
            ("mask", ctypes.c_uint32),
        ]

    advapi, kernel = _win32()
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    owner_and_dacl = 0x1 | 0x4  # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
    error = advapi.GetNamedSecurityInfoW(
        str(path),
        1,  # SE_FILE_OBJECT
        owner_and_dacl,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if error:
        raise ProviderError(f"cannot read the ACL of the child root (error {error})")
    try:
        owner_sid = _sid_text(owner.value)
        if not dacl.value:  # a null DACL lets everyone do everything
            return owner_sid, ["S-1-1-0"]
        writers: list[str] = []
        header = _AclHeader.from_address(dacl.value)
        for index in range(header.count):
            ace = ctypes.c_void_p()
            if not advapi.GetAce(dacl, index, ctypes.byref(ace)) or not ace.value:
                writers.append("unparsed")
                continue
            entry = _Ace.from_address(ace.value)
            if entry.type in (1, 6, 10, 12):  # a deny ACE only takes rights away
                continue
            if entry.type not in (0, 9):  # an allowed ACE whose layout is not read here
                writers.append("unparsed")
                continue
            if entry.mask & _WRITE_BITS:  # the SID starts right after the mask
                writers.append(_sid_text(ace.value + ctypes.sizeof(_Ace)))
        return owner_sid, writers
    finally:
        kernel.LocalFree(descriptor)


WIN_ACL: WindowsAcl = WindowsAcl()


def _acl_call[T](what: str, call: Callable[[], T]) -> T:
    """One call through the ACL seam; whatever it raises other than a ``ProviderError`` (a
    missing ``icacls.exe``, a Win32 error, an undecodable text) becomes one that names the call
    and the exception's type, never its text, which may hold a path or a SID (fix round 3)."""
    try:
        return call()
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"the ACL call {what} failed ({type(exc).__name__})") from exc


def _acl_problems(path: Path, acl: WindowsAcl) -> list[str]:
    """Why ``path`` (the root, or a cell cwd) is not private on Windows: an owner other than this
    user (Administrators is this user's owner only when the token is elevated), or a principal
    other than this user, SYSTEM, Administrators, CREATOR OWNER (the creator) or OWNER RIGHTS (the
    owner, checked first) that may write to it. [] when it is private."""
    me = _acl_call("current_sid", acl.current_sid)
    elevated = _acl_call("is_elevated", acl.is_elevated)
    owner, writers = _acl_call("owner_and_writers", lambda: acl.owner_and_writers(path))
    owners = {me, ADMINISTRATORS_SID} if elevated else {me}
    allowed = {me, SYSTEM_SID, ADMINISTRATORS_SID, _CREATOR_OWNER_SID, _OWNER_RIGHTS_SID}
    problems = [] if owner in owners else [f"owned by {owner}, not this user"]
    foreign = sorted({sid for sid in writers if sid not in allowed})
    problems += [f"writable by {sid}" for sid in foreign]
    return problems


def _verify_private(path: Path, what: str) -> None:
    """``verify_private_dir`` (a real directory, never a link or a junction; on POSIX this user's
    and mode 0o700) as a ``ProviderError`` whose text is redacted."""
    shown = _redacted(path)
    try:
        verify_private_dir(path)
    except UnsafeSandboxError as exc:
        raise ProviderError(f"{what} {shown} is not private: {_redacted_text(str(exc))}") from exc
    except OSError as exc:
        reason = f"cannot inspect it ({type(exc).__name__})"
        raise ProviderError(f"{what} {shown} is not private: {reason}") from exc


def secure_windows_root(root: Path, acl: WindowsAcl) -> str:
    """Make, or check, the Windows child root. A root this call creates (mode 0o700, chmod past
    the umask on POSIX) is locked (``acl.lock``; a failure is a refusal), must be empty after the
    lock (a directory another user made in it between the ``mkdir`` and the lock keeps that
    user's ownership), and is read back. One that already exists is used only when it is a real
    directory this user owns and no other principal may write to. Returns ``locked`` or
    ``ours``; raises ``ProviderError`` naming the root (redacted) and the reason otherwise."""
    shown = _redacted(root)
    try:
        os.mkdir(root, 0o700)
        created = True
    except FileExistsError:
        created = False
    except OSError as exc:
        raise ProviderError(f"cannot create the child root {shown}: {exc.strerror}") from exc
    if created and sys.platform != "win32":
        os.chmod(root, 0o700)  # the umask may have taken bits from mkdir's mode (I2)
    _verify_private(root, "the child root")
    if created:
        sid = _acl_call("current_sid", acl.current_sid)
        code = _acl_call("lock", lambda: acl.lock(root, sid))
        if code != 0:
            raise ProviderError(
                f"the child root {shown} is not private: icacls failed (exit {code})"
            )
        try:
            with os.scandir(root) as entries:
                made_before_the_lock = next(entries, None) is not None
        except OSError as exc:
            raise ProviderError(
                f"the child root {shown} is not private: cannot list it ({type(exc).__name__})"
            ) from exc
        if made_before_the_lock:
            raise ProviderError(
                f"the child root {shown} is not private: it is not empty after the lock "
                "(something was made in it before the lock); remove it and retry"
            )
    problems = _acl_problems(root, acl)
    if problems:
        raise ProviderError(f"the child root {shown} is not private: {'; '.join(problems)}")
    return "locked" if created else "ours"


def secure_windows_cwd(cwd: Path, acl: WindowsAcl) -> None:
    """The root's check for a cell's working directory, before any child starts in it: a real
    directory, owned by this user (or Administrators under an elevated token), with no
    write-capable ACE for any other principal. Raises ``ProviderError`` otherwise."""
    _verify_private(cwd, "the child working directory")
    problems = _acl_problems(cwd, acl)
    if problems:
        raise ProviderError(
            f"the child working directory {_redacted(cwd)} is not private: {'; '.join(problems)}"
        )


def root_state(root: Path) -> tuple[bool, str]:
    """Doctor check 9's root words: ``root locked`` when the root exists and is private (on
    Windows, ``_acl_problems``; on POSIX, ``verify_private_dir``: this user's, mode 0o700, no
    link), else ``root NOT private: <reason>``, the reason redacted. Creates nothing."""
    try:
        os.lstat(root)
    except (FileNotFoundError, NotADirectoryError):
        return False, "root NOT private: it does not exist yet"
    except OSError as exc:
        return False, f"root NOT private: cannot inspect it ({type(exc).__name__})"
    try:
        verify_private_dir(root)
        problems = _acl_problems(root, WIN_ACL) if sys.platform == "win32" else []
    except (UnsafeSandboxError, ProviderError) as exc:
        problems = [_redacted_text(str(exc))]
    except OSError as exc:
        problems = [f"cannot inspect it ({type(exc).__name__})"]
    if problems:
        return False, f"root NOT private: {'; '.join(problems)}"
    return True, "root locked"


def _redacted(path: Path) -> str:
    """``path`` with any segment that is the user's login or home folder name as ``<user>``."""
    names = {name for name in _user_names() if name}
    parts = [part if part.casefold() not in names else "<user>" for part in path.parts]
    return str(Path(*parts)) if parts else str(path)


def _redacted_text(text: str) -> str:
    """``text`` (a message that may quote a path) with every path segment that is the user's
    login or home folder name, compared case-insensitively, as ``<user>``: a name that follows a
    path separator and ends at one, at a quote, a space, punctuation or the end."""
    for name in sorted({name for name in _user_names() if name}, key=len, reverse=True):
        segment = rf"(?i)(?<=[\\/]){re.escape(name)}(?=[\\/'\"\s;:,)]|$)"
        text = re.sub(segment, "<user>", text)
    return text


def state_run_ids(state_dir: Path) -> list[str]:
    """The run ids a state dir names: the segment before each ``state`` segment of the resolved
    path (``<runs root>/<run id>/state/...``)."""
    parts = state_dir.resolve().parts
    return [parts[i - 1] for i, part in enumerate(parts) if part == _STATE_SEGMENT and i > 1]


def clean_child_env() -> dict[str, str]:
    """This process's environment less every variable that would tell a child ``claude -p`` it
    runs inside Claude Code (``STRIPPED_PREFIXES``; a nested call refuses to start otherwise).
    Every subprocess the harness or the doctor spawns runs under it."""
    return {k: v for k, v in os.environ.items() if not k.startswith(STRIPPED_PREFIXES)}


def resolved_model(data: dict[str, Any]) -> str | None:
    """The exact model a result reports: the ``modelUsage`` key with the most output tokens (a
    helper model the CLI ran beside the call may be listed first), the first key on a tie or
    when no key reports ``outputTokens``; else ``model``."""
    usage = data.get("modelUsage")
    if isinstance(usage, dict) and usage:

        def output_tokens(key: Any) -> int:
            entry = usage[key]
            tokens = entry.get("outputTokens") if isinstance(entry, dict) else None
            return tokens if isinstance(tokens, int) else 0

        return str(max(usage, key=output_tokens))  # max keeps the first of equal keys
    model = data.get("model")
    return str(model) if isinstance(model, str) and model else None


def resolve_claude_command(explicit: list[str] | None = None) -> list[str]:
    """The argv prefix that runs Claude Code, from most to least deliberate:

    1. ``explicit``, when given (a role's ``command``).
    2. ``$CLAUDE_BULLY_CLAUDE``, one path (spaces and all; nothing is split).
    3. ``claude`` on PATH. An npm install puts a ``.cmd``/``.bat``/``.ps1`` shim there, which
       cmd.exe would run with mangled quoting (``--tools ""``, JSON arguments), so a shim is
       swapped for the native ``claude.exe`` it wraps, found beside it or one level up.

    Raises ``ProviderError`` saying what to do when nothing usable is found.
    """
    if explicit:
        return list(explicit)
    configured = os.environ.get(CLAUDE_ENV)
    if configured:
        return [configured]
    found = shutil.which("claude")
    if found is None:
        raise ProviderError(
            f"claude was not found on PATH; install Claude Code or point {CLAUDE_ENV} "
            "at its executable"
        )
    path = Path(found)
    if path.suffix.lower() not in _SHIM_SUFFIXES:
        return [found]
    for base in (path.parent, path.parent.parent):
        native = base / _NATIVE_BINARY
        if native.is_file():
            return [str(native)]
    raise ProviderError(
        f"claude on PATH is a script shim ({found}) and the native claude.exe was not found "
        f"beside it; point {CLAUDE_ENV} at the native executable"
    )


class ClaudeCodeProvider:
    name = "claude_code"

    def __init__(
        self,
        model: str,
        state_dir: Path,
        effort: str | None = None,
        command: list[str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        mcp_state_dir: Path | None = None,
        mcp_tool_timeout_s: float = DEFAULT_MCP_TOOL_TIMEOUT_S,
    ) -> None:
        self.model = model
        self.effort = effort
        self._command_arg = list(command) if command else None
        self._command: list[str] | None = None
        self.timeout_s = timeout_s
        self.mcp_tool_timeout_s = mcp_tool_timeout_s
        self.state_dir = state_dir
        # where mcp.json, env_state.json and tools.jsonl live; None means no sandbox tools
        self.mcp_state_dir = mcp_state_dir.resolve() if mcp_state_dir is not None else None
        # whether the newest stream carried a thinking block (the fact, never the text; doctor
        # check 4b); None before any stream
        self.thinking_seen: bool | None = None
        # the MCP servers the newest stream's init event listed, (name, status) each, as in
        # ("gateway", "connected"); [] when it listed none (the CLI dropped the config entry);
        # None before any stream, or when the stream carried no init event (doctor check 4)
        self.mcp_servers_seen: list[tuple[str, str]] | None = None
        self._sessions_path = state_dir / "claude_code_sessions.json"
        self._cwd = child_cwd(state_dir)
        self.run_ids = state_run_ids(state_dir)
        self._sessions: dict[str, str] = self._load_sessions()

    @property
    def cwd(self) -> Path:
        """The working directory every child of this provider runs in (``child_cwd``)."""
        return self._cwd

    def cwd_problems(self) -> list[str]:
        """``neutral_cwd_problems`` of the resolved working directory, with this state dir's run
        ids, then each Claude Code project file in it or above it (``inspect_project_files``),
        named by path; [] when it is neutral (``complete`` refuses otherwise; doctor check 9
        reports it)."""
        cwd = self._cwd.resolve()
        found, uninspectable = inspect_project_files(cwd)
        return (
            neutral_cwd_problems(cwd, run_ids=self.run_ids)
            + [
                f"{_redacted(path)} is a Claude Code project file the CLI may read"
                for path in found
            ]
            + [f"cannot inspect {_redacted(path)} for a project file" for path in uninspectable]
        )

    def root_state(self) -> tuple[bool, str]:
        """``root_state`` of this provider's child root (doctor check 9)."""
        return root_state(self._cwd.resolve().parent)

    def child_env(self, *, serving_tools: bool) -> dict[str, str]:
        """The environment a child ``claude -p`` runs in: ``clean_child_env()`` plus
        ``MCP_TOOL_TIMEOUT`` when the call serves tools. A ``CLAUDE_BULLY_CHILD_ROOT`` that is
        set reaches the child resolved (``child_cwd_root()``), so a nested responder, whose
        process cwd is the target's, works under the same root and not under a relative one."""
        env = clean_child_env()
        if os.environ.get(CHILD_ROOT_ENV):
            env[CHILD_ROOT_ENV] = str(child_cwd_root())
        if serving_tools:
            env[MCP_TOOL_TIMEOUT_ENV] = str(int(self.mcp_tool_timeout_s * 1000))
        return env

    @property
    def command(self) -> list[str]:
        """The argv prefix, resolved on first use so building a provider never needs claude."""
        if self._command is None:
            self._command = resolve_claude_command(self._command_arg)
        return self._command

    # -- session map -----------------------------------------------------------------

    def _load_sessions(self) -> dict[str, str]:
        if self._sessions_path.exists():
            raw: dict[str, str] = json.loads(self._sessions_path.read_text(encoding="utf-8"))
            return raw
        return {}

    def _save_sessions(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_path.write_text(json.dumps(self._sessions, indent=1), encoding="utf-8")

    def session_ref(self, conversation_id: str) -> str | None:
        return self._sessions.get(conversation_id)

    def reset_session(self, conversation_id: str) -> None:
        """Forget the live session; the next complete() starts fresh and replays the transcript.

        A conversation with no session is left alone: nothing is written."""
        if conversation_id in self._sessions:
            del self._sessions[conversation_id]
            self._save_sessions()

    # -- argument construction -----------------------------------------------------------

    def build_args(
        self,
        conversation_id: str,
        system: str,
        json_schema: dict[str, Any] | None,
        tools: list[ToolSpec] | None = None,
    ) -> tuple[list[str], str, bool]:
        """Return (argv, session_uuid, is_resume).

        With ``tools`` the output is ``stream-json`` (which print mode only allows with
        ``--verbose``) and the argv gains ``--mcp-config`` and ``--allowedTools``; without, it is
        exactly what a toolless call has always been.
        """
        existing = self._sessions.get(conversation_id)
        session = existing or str(uuid.uuid4())
        output = ["stream-json", "--verbose"] if tools else ["json"]
        args = [
            *self.command,
            "-p",
            "--output-format",
            *output,
            "--model",
            self.model,
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--tools",
            "",
        ]
        if tools:
            args += [
                "--mcp-config",
                str(self._mcp_config_path()),
                "--allowedTools",
                ",".join(f"mcp__{SERVER_NAME}__{tool.name}" for tool in tools),
            ]
        args += [
            "--system-prompt",
            system,
            "--exclude-dynamic-system-prompt-sections",
        ]
        if self.effort:
            args += ["--effort", self.effort]
        args += ["--resume", session] if existing else ["--session-id", session]
        if json_schema is not None:
            args += ["--json-schema", json.dumps(json_schema)]
        return args, session, existing is not None

    # -- sandbox tools over MCP -----------------------------------------------------------

    def _mcp_dir(self) -> Path:
        if self.mcp_state_dir is None:
            raise ProviderError(
                "claude_code was given tools but has no mcp_state_dir to serve them from"
            )
        return self.mcp_state_dir

    def _mcp_config_path(self) -> Path:
        return self._mcp_dir() / MCP_CONFIG_FILE

    def _write_mcp_config(self) -> None:
        """mcp.json: the command Claude Code runs to start the sandbox-tool server."""
        directory = self._mcp_dir()
        directory.mkdir(parents=True, exist_ok=True)
        config = {
            "mcpServers": {
                SERVER_NAME: {
                    "command": Path(sys.executable).as_posix(),
                    "args": [write_launcher(directory).as_posix(), "--state", directory.as_posix()],
                }
            }
        }
        self._mcp_config_path().write_text(json.dumps(config, indent=1), encoding="utf-8")

    def _tools_log_size(self) -> int:
        path = self._mcp_dir() / TOOLS_FILE
        return path.stat().st_size if path.exists() else 0

    def _new_tool_calls(self, offset: int) -> list[ToolCallRequest]:
        """The calls the server recorded after byte ``offset``, as already-executed requests."""
        path = self._mcp_dir() / TOOLS_FILE
        if not path.exists():
            return []
        with path.open("rb") as handle:
            handle.seek(offset)
            added = handle.read()
        calls: list[ToolCallRequest] = []
        # The last piece is empty or a line still being written, possibly cut mid-character, so it
        # is dropped before anything is decoded; only a complete line can be malformed.
        for raw in added.split(b"\n")[:-1]:
            if not raw.strip():
                continue
            try:
                record = json.loads(raw.decode("utf-8"))
                calls.append(
                    ToolCallRequest(
                        id=record["id"],
                        name=record["tool"],
                        args=record["args"],
                        executed=True,
                        result_text=record["result_text"],
                    )
                )
            except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
                raise ProviderError(f"malformed line in {path}: {raw[:200]!r}") from exc
        return calls

    # -- output parsing -----------------------------------------------------------------

    def parse_output(self, stdout: str, session: str) -> Completion:
        """``--output-format json``: one result object."""
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"claude -p returned non-JSON output: {stdout[:200]!r}") from exc
        if not isinstance(data, dict):
            raise ProviderError(f"claude -p returned no result object: {stdout[:200]!r}")
        return self._from_result(data, session)

    def parse_stream(self, stdout: str, session: str) -> Completion:
        """``--output-format stream-json``: one JSON event per line, ending with ``result``.

        Each assistant text block that comes before a ``tool_use`` is interim text, in order;
        whitespace-only blocks are dropped. The text after the last ``tool_use`` is the reply,
        which the ``result`` event carries along with the usage and the cost. Thinking blocks are
        skipped: the target's reasoning channel is never kept. A line that is not a JSON object,
        or a stream with no ``result`` event (one cut off), is a ``ProviderError``, never an
        empty turn. The ``system``/``init`` event's ``mcp_servers`` go to ``mcp_servers_seen`` as
        soon as it is read, so a stream that fails later still says whether its server loaded.
        """
        self.mcp_servers_seen = None  # this stream's, never the last one's
        interim: list[str] = []
        thinking = False
        pending: list[str] = []  # text blocks since the last tool_use
        result: dict[str, Any] | None = None
        last = ""
        for number, line in enumerate(stdout.split("\n"), start=1):
            if not line.strip():
                continue
            last = line
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"claude -p stream line {number} is not JSON: {_shape(line)}"
                ) from exc
            if not isinstance(event, dict):
                raise ProviderError(
                    f"claude -p stream line {number} is not an event: a JSON "
                    f"{type(event).__name__} of {len(line)} characters"
                )
            if event.get("type") == "result":
                result = event
            elif event.get("type") == "system" and event.get("subtype") == "init":
                servers = event.get("mcp_servers")
                if isinstance(servers, list):
                    self.mcp_servers_seen = [
                        (str(entry.get("name") or ""), str(entry.get("status") or ""))
                        for entry in servers
                        if isinstance(entry, dict)
                    ]
            elif event.get("type") == "assistant":
                for block in _content_blocks(event):
                    if block.get("type") == "text":
                        pending.append(str(block.get("text") or ""))
                    elif block.get("type") == "tool_use":
                        interim += [text for text in pending if text.strip()]
                        pending = []
                    elif block.get("type") == "thinking":
                        thinking = True
        if result is None:
            ended = f"its last line {_shape(last)}" if last else "it was empty"
            raise ProviderError(f"claude -p stream ended without a result event; {ended}")
        self.thinking_seen = thinking
        completion = self._from_result(result, session)
        return completion.model_copy(update={"interim_texts": interim})

    def _from_result(self, data: dict[str, Any], session: str) -> Completion:
        """The completion a result object describes; an error result raises."""
        if data.get("is_error"):
            message = str(data.get("result", ""))
            if _LOGIN.search(message):
                raise ProviderError(f"claude -p is not logged in: {message[:200]}")
            if _RATE_LIMIT.search(message):
                raise RateLimitError(message)
            raise ProviderError(f"claude -p error: {message}")
        if "structured_output" in data and data["structured_output"] is not None:
            text = json.dumps(data["structured_output"])
        else:
            text = str(data.get("result", ""))
        usage_raw = data.get("usage") or {}
        return Completion(
            text=text,
            usage=Usage(
                input_tokens=usage_raw.get("input_tokens"),
                output_tokens=usage_raw.get("output_tokens"),
            ),
            cost_usd=data.get("total_cost_usd"),
            backend=self.name,
            model=self.model,
            raw_session_ref=str(data.get("session_id") or session),
            stop_reason=str(data.get("subtype") or "success"),
            resolved_model=resolved_model(data),
        )

    # -- protocol -----------------------------------------------------------------------

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        if tools:
            self.thinking_seen = None  # unknown until this stream parses; never the last one's
            self.mcp_servers_seen = None
            self._write_mcp_config()
        problems = self.cwd_problems()
        if problems:  # before the working directory is made or any child starts
            raise ProviderError(
                f"the child working directory is not neutral: {'; '.join(problems)}; point "
                f"{CHILD_ROOT_ENV} at a directory outside the repo, the runs and the home folder"
            )
        args, session, is_resume = self.build_args(conversation_id, system, json_schema, tools)
        offset = self._tools_log_size() if tools else 0
        prompt = _newest_user_message(messages) if is_resume else _render_initial(messages)
        # the default root is shared (/tmp/w, %PUBLIC%/w): the root and the directory are made
        # 0o700 and reused only when each is a real directory (never a link or a junction) and,
        # on POSIX, this user's alone, as the environment sandbox is (runner/sandbox.py)
        root = self._cwd.parent
        root.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":  # created locked, or checked: ours, and only ours to write
            secure_windows_root(root, WIN_ACL)
        try:
            prepare_sandbox(self._cwd, fresh=False)
        except UnsafeSandboxError as exc:  # a provider failure like any other (M3)
            said = _redacted_text(str(exc))
            raise ProviderError(f"the child working directory is unsafe: {said}") from exc
        if sys.platform == "win32":  # and the cell cwd gets the root's check (fix round 3)
            secure_windows_cwd(self._cwd, WIN_ACL)
        # Bytes in and out, decoded here: a text-mode pipe decodes in a reader thread, where output
        # cut off mid-character is lost as an unhandled thread error instead of a ProviderError.
        try:
            proc = subprocess.run(
                args,
                input=prompt.encode("utf-8"),
                capture_output=True,
                cwd=self._cwd,
                env=self.child_env(serving_tools=bool(tools)),
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeoutError(f"claude -p timed out after {self.timeout_s}s") from exc
        except OSError as exc:
            raise ProviderError(f"could not start {self.command[0]}: {exc}") from exc
        if proc.returncode != 0:
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
            said = _stream_failure_text(stdout) if tools else stdout
            combined = said + (proc.stderr or b"").decode("utf-8", errors="replace")
            if _RATE_LIMIT.search(combined):
                raise RateLimitError(combined.strip()[:500])
            if _LOGIN.search(combined):  # named as a login whatever the exit code
                raise ProviderError(f"claude -p is not logged in: {combined.strip()[:200]}")
            raise ProviderError(f"claude -p exited {proc.returncode}: {combined.strip()[:500]}")
        try:
            stdout = (proc.stdout or b"").decode("utf-8")
        except UnicodeDecodeError as exc:  # cut off mid-character, or not text at all
            raise ProviderError(f"claude -p output is not valid UTF-8: {exc}") from exc
        if tools:
            completion = self.parse_stream(stdout, session)
            completion = completion.model_copy(update={"tool_calls": self._new_tool_calls(offset)})
        else:
            completion = self.parse_output(stdout, session)
        self._sessions[conversation_id] = completion.raw_session_ref or session
        self._save_sessions()
        return completion


def _content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    """The content blocks of a stream's assistant event; a bare string is one text block."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _shape(line: str) -> str:
    """A stream line as an error may describe it: its length and the type of the event it holds,
    never its content (preflight C24)."""
    match = _EVENT_TYPE.search(line)
    kind = f" (event type {match.group(1)!r})" if match is not None else ""
    return f"{len(line)} characters{kind}"


def _stream_failure_text(stdout: str) -> str:
    """What a failed stream says about its failure: the result event's text and any line that is
    not JSON (the CLI's own error output). Never the model's text, which may well say "let me try
    again" and must not read as a rate limit, and never a torn event, which may be the model's
    reasoning: that is named by its shape (``_shape``)."""
    parts: list[str] = []
    for line in stdout.split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parts.append(_shape(line) if line.lstrip().startswith("{") else line)
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            parts.append(str(event.get("result", "")))
    return "".join(f"{part}\n" for part in parts)


def _newest_user_message(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    raise ProviderError("no user message to send")


def _render_initial(messages: list[Message]) -> str:
    """First call of a session: usually a single user message.

    If a transcript is replayed into a fresh session (resume after lost state), the
    prior turns are rendered as a quoted transcript ahead of the newest message.
    """
    users = [m for m in messages if m.role == "user"]
    if len(messages) == 1 or len(users) == 1:
        return _newest_user_message(messages)
    history = "\n".join(
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages[:-1]
    )
    return f"[Earlier in this conversation]\n{history}\n\n{_newest_user_message(messages)}"
