# Task 12 fix round 2, scoped re-review (65dff39..fa099e9)

Reviewer: read-only on tracked files (`git status` clean before and after). Targeted tests run:
`tests/test_providers_claude_code.py` and `tests/test_doctor_live.py` (131 passed, 1 skipped, `-W error`).
Not the full gate. Probes (all in the session scratchpad, none in the tree) drove the real Win32 code on
this machine against throwaway directories under `%ProgramData%` (removed, verified), ran `mypy --platform
linux`, and ran the extracted `secure_windows_root` on Ubuntu 24.04 (WSL, umask 022; stopped again after).

## Verdict

Item 1 ADDRESSED. Item 2 PARTIAL (Windows behaviour correct and held up under hard probing; the new tests and
the typing are not POSIX-clean, and CI is `ubuntu-latest`). Items 3, 4, 5 ADDRESSED.
New Critical: 0. New Important: 2. New Minor: 6.

## Per item

### 1. Fail-open on a symlink: ADDRESSED

- `inspect_project_files` calls `os.lstat` on every name in the cwd and each ancestor. `FileNotFoundError` and
  `NotADirectoryError` mean absent; any other `OSError` puts the path in the uninspectable list;
  `cwd_problems()` turns that into `cannot inspect <path> for a project file`, so `complete` raises
  `ProviderError` before anything is made or spawned, and doctor check 9 fails.
- Real probe (not mocked): a dangling junction named `.claude`: `Path.exists()` False, `os.path.lexists` True,
  `inspect_project_files` lists it as found. A dangling symlink behaves the same under `lstat`; that test is
  skipped on this account (no symlink privilege) and runs on POSIX.
- The deviation (`os.lstat` over `os.path.lexists`) is correct and worth keeping: `lexists` returns False on any
  `OSError`, which is the same fail-open in a different place.
- The unreadable-ancestor test is mock-only (`os.lstat` and `os.stat` patched to raise `PermissionError`). I
  could not produce a real `PermissionError` on Windows: a denied directory still returns `FileNotFoundError`
  for a missing name because traverse checking is bypassed. The mock test pins the branch, which is what is needed.
- See M4 (the old public function) and M1 (the check runs before the directories exist on the first call).

### 2. Locked root on Windows: PARTIAL

Windows behaviour, verified:

- The lock: a created root has `SE_DACL_PROTECTED` set (inheritance removed), owner equal to the process user, and
  writers exactly {user, SYSTEM, Administrators}; `icacls` shows no `(I)` and three `(OI)(CI)(F)`. The user SID the
  code reads from the process token equals `WindowsIdentity.GetCurrent().User` (compared, not printed).
- Existing root probes against `secure_windows_root` with the real Win32 reader:

| Root state | Result |
|---|---|
| plain `os.mkdir` under an inheriting parent (Users add-file/add-subdir ACE) | refused: `writable by S-1-5-32-545` |
| locked + Everyone `(W)`, INTERACTIVE `(M)`, Users `(AD)` | refused, naming the SID |
| locked + Everyone only `(DC)`, `(WDAC)`, `(WO)`, `(WA)` | each refused (every bit in `_WRITE_BITS` fires) |
| locked + Everyone `(OI)(CI)(IO)W` (inherit-only) | refused |
| locked + OWNER RIGHTS (S-1-3-4) full | refused |
| null DACL (set with `SetNamedSecurityInfoW`) | refused: `writable by S-1-1-0` |
| allowed callback ACE (type 9) for Everyone, write bits | refused: `writable by S-1-1-0` |
| allowed object ACE (type 5) for Everyone | refused: `writable by unparsed` |
| deny-only extra ACE (plain deny, and deny callback type 10) | passes (a deny cannot widen access) |
| Everyone allow `(M)` plus Everyone deny `(W)` | refused (the allow still counts) |
| Everyone read-only `(R)`, or callback allow read-only | passes (by design: the rule is write rights) |
| CREATOR OWNER inherit-only | passes (it resolves to the creator) |
| junction to a locked directory; a file where the root should be | refused (`verify_private_dir`) |
| owner SID differs from the user (simulated at the seam) | refused: `owned by <sid>, not this user` |

- Win32 correctness: every function has explicit `argtypes` and `restype`; `ACL` header (1+1+2+2+2) and ACE header
  plus mask (`sizeof` 8, SID at offset 8) are right for 64-bit; the callback ACE's SID parsed correctly in the probe.
  The token handle is closed in a `finally`; `LocalFree` is called on the SID string and on the security
  descriptor (pointers read before the free). 3000 and 20000 repeated reads left the process handle count
  unchanged (190 to 190) and commit growth at 152 KiB over 20000 reads (no per-call leak). Errors are raised:
  `OpenProcessToken`, `GetTokenInformation` (second call), `GetNamedSecurityInfoW`, SID conversion; an
  unparsed SID, a failed `GetAce` or an unknown allowed ACE type is "unparsed" and refuses. Owner and writers are
  compared as SID strings, never names.
- Fail closed: an `icacls` exit other than 0 is a `ProviderError` naming the root and exit code. Check 9 reports
  `root locked` / `root NOT private: <reason>` (verified for missing, plain-inherited and locked roots).
- POSIX: production path unchanged (`secure_windows_root` is called only when `sys.platform == "win32"`;
  `prepare_sandbox` and its owner/0o700 checks are untouched). The module imports on POSIX: `ctypes` is imported
  and `WinDLL` is created only inside `_win32()`, which raises first on a non-Windows platform.

What keeps this PARTIAL: I1 and I2 below (the new tests and the typing break on the repo's own CI platform).

### 3. Relative root in the child's environment: ADDRESSED

`child_env` sets `CLAUDE_BULLY_CHILD_ROOT` to `str(child_cwd_root())` (resolved) whenever the variable is set and
leaves it out when unset (the report names the choice). The test covers both `serving_tools` values and the unset
case. The only other `clean_child_env()` callers (`cli.py:326`, `doctor.py:151`) do not run a child from the
child cwd.

### 4. Stale text: ADDRESSED

No "invented login" in `HANDOFF.md`, the spec, or any `.md`/`.py` outside `.superpowers/` (grep). Both Task 12
bullets now describe the `%ProgramData%` locked session root and the real names.

### 5. Docs: ADDRESSED

Runbook Step 0 gains "The root itself" (Windows ACL lock by SID, refusal of a foreign or pre-lock root, POSIX
0o700, check 9's root words, the accepted check-then-spawn window under `--setting-sources ""`); `HANDOFF.md` gains
the fix-round-2 bullet saying the same. See M6 for one precision point.

## New findings

### Critical

None.

### Important

**I1. `mypy` fails on Linux, and CI is `ubuntu-latest`.** `_process_user_sid` calls `ctypes.get_last_error()`
(`claude_code.py:329` and `:335`) with no platform guard in that function (the guard is in `_win32()`, which mypy
cannot see through). `uv run mypy --platform linux claude_bully` reports 2 errors: `Module has no attribute
"get_last_error"  [attr-defined]`. Both errors are new in this round (`get_last_error` does not appear in the file at 65dff39); no other error was reported. The CI
file runs `uv run mypy claude_bully` on every push to `build/**`, and HANDOFF tells the next machine the gate must
pass with 0 warnings. Fix: an `if sys.platform != "win32": raise ProviderError(...)` as the first statement of
`_process_user_sid` (mypy then treats the body as Windows-only), or read the error code inside `_win32`'s guard.

**I2. Five new tests fail on POSIX.** `secure_windows_root` is platform-agnostic but calls `verify_private_dir`,
whose POSIX branch demands mode 0o700. The root is made with `os.mkdir(root)` (default mode) and the "existing"
tests use `root.mkdir()`, so under the usual umask 022 the root is 0o755 and is refused before the fake ACL is
consulted. I ran the extracted function on Ubuntu 24.04 (umask 022) with the tests' fake ACL: all four scenarios
raise `... is open to other users (mode 755)`. That fails `test_a_new_windows_root_is_created_and_locked`,
`test_an_existing_windows_root_of_ours_is_used_as_is`, both cases of `test_a_foreign_windows_root_is_refused`
(they match the SID text) and `test_a_failed_icacls_is_a_refusal` (it matches `icacls`). The report's claim that
POSIX gains a pass is therefore untested and wrong for these five, and `HANDOFF.md`'s expected counts for POSIX
are off. Fix: `os.mkdir(root, 0o700)` in `secure_windows_root` (the mode argument is ignored on Windows) and
`os.chmod(root, 0o700)` after `root.mkdir()` in the two "existing" tests, or skip the seam tests off Windows; then
run the fast suite on Ubuntu (WSL here) before the next handoff.

### Minor

**M1. The creation window and the first-call ordering.** Between `os.mkdir(root)` and the `icacls` call the root
carries the inherited (Public or ProgramData) ACL. A child another interactive user makes in that window keeps its
owner, who always holds WRITE_DAC, and no code checks a cell directory's owner or ACL on Windows
(`verify_private_dir` checks the owner on POSIX only). My probe showed the lock rewrites a pre-created child's
inherited ACEs (to the three SIDs), so only the owner's implicit rights survive. Also `cwd_problems()` runs
before `secure_windows_root` and `prepare_sandbox`, so on a first call nothing scans the just-made directories for
a planted project file. Narrow: a local attacker, the first creation of the root, a guess of the 12-digit digest.
Fix: create the root atomically with the explicit DACL (`CreateDirectoryW` with a `SECURITY_ATTRIBUTES`), or
refuse a freshly created root that is not empty after the lock; check the cell directory's owner with
`owner_and_writers`; and run the project-file scan once more after `prepare_sandbox`.

**M2. An elevated process refuses its own root.** An elevated token's default owner is the Administrators group
(unless policy says "object creator"), so `owner == me` fails right after the lock and `complete` raises `owned by
S-1-5-32-544, not this user`. Loud and safe, but a surprise from an admin console. Not verified: this shell is not
elevated (`TokenOwner` equals the user here). Either accept `TokenOwner`'s SID as "this user" or say so in the
runbook.

**M3. Seam failures outside the exit-code path are raw exceptions, and `icacls` text is unredacted.**
`subprocess.run` raising `OSError` (no `icacls.exe`) or `UnicodeDecodeError` (text mode, locale code page) escapes
`secure_windows_root` as itself, not a `ProviderError`; `complete` still refuses, but the runner's handling of
provider failures does not see it. The first 200 characters of `icacls` output go into the `ProviderError`
verbatim; a "no mapping" failure echoes the SID it was given, which is the user's own. Wrap the call
(`except (OSError, ValueError)`), and replace the user's SID in the text with `<user>`.

**M4. `planted_project_files` still fails open.** It is now `inspect_project_files(path)[0]`, drops the
uninspectable list, and has no production caller (only `cwd_problems` calls `inspect_project_files`). A later
caller would get the old fail-open behaviour under a name that suggests the check. Delete it or make it raise on
an uninspectable path.

**M5. `root_state` is untested on its failing branch, and its text is unredacted.** No test asserts `root NOT
private: ...` or that check 9 fails on it (only the `root locked` ending is pinned). `root_state` also puts
`str(exc)` of `UnsafeSandboxError` and `OSError` in the detail, and those carry the raw path, where
`secure_windows_root` uses `_redacted`; a root under the home folder that is a link or not a directory would put
the login in a doctor report. Add one `root_state` test per branch (missing, foreign, locked) and use `_redacted`
for the path in those messages.

**M6. Doc precision on the accepted window.** The runbook says the check-then-spawn window is accepted because
"the root is the user's alone to write". The lock covers the root and below; the ancestors above it
(`%PUBLIC%`, `C:\Users`) stay writable by other interactive users, so a project file planted there after the check
relies on `--setting-sources ""` alone. The ruling accepts that; the sentence should say it. I did not verify what
`--setting-sources ""` does to a planted `CLAUDE.md` (it is memory, not a setting); that is the owner's accepted
residual, not re-opened here.

## Not findings (looked at, fine)

- An allowed ACE for a read-only right on another principal passes; the rule is "no write rights", as the fix doc
  states. Confidentiality of the root is not the concern.
- `current_sid` is cached per process; a token swap mid-process is out of scope.
- No real name, login, email or user SID literal in any added line: the added SIDs are the well-known ones
  (S-1-1-0, S-1-3-0, S-1-5-4, S-1-5-18, S-1-5-32-544) and the fake `S-1-5-21-1-2-3-100x` test constants.
- The suite's Windows session root (`w` under a fresh `%ProgramData%\w-*`, made by `secure_windows_root`, removed
  at the end) left nothing behind after my runs.
