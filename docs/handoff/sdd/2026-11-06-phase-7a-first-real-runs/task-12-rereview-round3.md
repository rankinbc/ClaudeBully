# Task 12 fix round 3, scoped re-review (fa099e9..4508a35)

Reviewer: read-only on tracked files. `git status` showed one modified file, `docs/handoff/drafts/README.v2.md`,
which this review did not touch (the drafts belong to another agent; it is outside the 4508a35 diff).

Run for this review (all against the committed tree):

- `uv run mypy --platform linux claude_bully`: no issues in 110 source files. `uv run mypy claude_bully`: the same.
- `uv run pytest -q -W error tests/test_providers_claude_code.py tests/test_doctor_live.py tests/test_sandbox.py`
  on Windows: 161 passed, 9 skipped. No `%ProgramData%\w-*` left after it.
- The same three files under WSL (Ubuntu 24.04, Python 3.12.3, umask 0022), from a `git archive` of 4508a35 with
  Linux wheels installed by Windows `uv` (no network in WSL): 165 passed, 5 skipped, `-W error`. This reproduces the
  report's number independently. (The implementer's WSL tree was gone; the WSL `/tmp` does not survive between sessions.)
- Probes in the session scratchpad (none in the tree): the real Win32 code against throwaway directories under
  `%ProgramData%\w-probe-*` (removed, verified); the committed `claude_code.py` and `sandbox.py` imported on Ubuntu with
  the three sibling modules stubbed; mutation runs of the new tests in a throwaway copy.

## Verdict

Items 1 to 7 ADDRESSED. New Critical: 0. New Important: 0. New Minor: 4.

## Per item

### 1. Security, the creation window: ADDRESSED

- `secure_windows_root` (`claude_code.py:487`): after `acl.lock` on a root this call created, `os.scandir` must find
  nothing, else `... not empty after the lock ...`; a listing that fails is a refusal too. It runs only when `created`,
  which is what the item asks for.
- `secure_windows_cwd` (`:530`) gives the cell cwd the root's check (`_verify_private`, then `_acl_problems`: owner
  the current SID, or Administrators when elevated; no write-capable ACE for any other principal). `complete` calls
  it on win32 after `prepare_sandbox` and before the only `subprocess.run` that starts a child (`:992`, then `:996`).
  Every child start in the package goes through `complete` (the other `subprocess.run` calls are `--version`,
  `icacls` and `git rev-parse`). The nested responder is `build_provider(...)` in the MCP server, so it is a
  `ClaudeCodeProvider` running the same `complete`; it is covered by construction, not by a test inside the server
  child (disclosed in the report; the seam cannot be patched across the process boundary).
- Tests through the seam: `test_a_child_made_between_mkdir_and_the_lock_is_refused`,
  `test_a_foreign_or_shared_cwd_is_refused[owner|writer]` (and the private cwd passes),
  `test_complete_refuses_a_foreign_cwd_before_any_child_starts` (Windows; asserts the fake CLI never ran). Mutation
  check, each in a throwaway copy: removing the emptiness check, removing the `secure_windows_cwd` call from
  `complete`, and dropping the owner check each fail the test named for them.
- Real probes (Win32, not the seam): a root locked by the real `icacls`, a cwd made by `prepare_sandbox` under it
  passes; `icacls /grant Everyone:M` or `Users:(W)` on the cwd is refused (`writable by S-1-1-0`, `S-1-5-32-545`) and
  passes again once removed; `C:\Windows\System32` and `C:\ProgramData` are refused (`owned by <sid>, not this
  user`); a subclass whose `lock` makes a child before calling the real lock is refused with the real reader and
  the real `icacls`.
- `os.mkdir(path, 0o700)` on this interpreter (3.12.13) does write a protected DACL of SYSTEM, Administrators and
  OWNER RIGHTS with the user as owner (probe), so the root is private from creation here; the emptiness check is the
  guard for 3.12.0 to 3.12.3 (`requires-python` is `>=3.12,<3.13`). See M1 for how a refusal behaves on the next call.

### 2. I1, mypy on Linux: ADDRESSED

Both runs are clean (110 files each). `_sid_text`, `_token_information`, `_process_user_sid`, `_token_elevated` and
`_read_owner_and_writers` each open with `if sys.platform != "win32": raise ProviderError(...)`, as `_win32` does;
no other ctypes access is outside a guard. The report's claim (2 errors at fa099e9, none now) is consistent with the
diff.

### 3. I2, POSIX tests: ADDRESSED

- Reproduced under WSL: 165 passed, 5 skipped (the two Windows-only ACL tests and three NTFS junction tests).
- Independent probe of the committed code on Ubuntu: `secure_windows_root` and `prepare_sandbox` leave the root and
  the cell directory at 0o700 under umask 022, 200, 077 and 000 (umask 200 would give mode 577 without the `chmod`); a
  plain `mkdir` root (755) is refused with `open to other users (mode 755)`; the seam refusals (foreign owner, extra
  writer, Administrators unelevated, child before the lock) behave as on Windows.
- The root and cwd are made with `os.mkdir(path, 0o700)` and then `chmod` on POSIX in both places
  (`claude_code.py:503`, `sandbox.py:102`); the production POSIX path never calls `secure_windows_root`.
- Module load: importing the committed `claude_code.py` and `sandbox.py` on Ubuntu loads no Windows-only module
  (`msvcrt`, `winreg`, `_winapi`, `ctypes.wintypes`); `ctypes` is imported only inside functions behind the guards.
- Mutation under WSL, both `chmod` calls removed (the `mode=0o700` kept): 2 failed (`test_a_new_root_is_mode_700_whatever_the_umask[umask 200]`
  and `test_the_root_and_cell_dir_are_mode_700_whatever_the_umask`, a `PermissionError` at umask 0o200), 163 passed. So
  the `chmod` is pinned, and only by the umask-200 cases; at umask 022 `mode=0o700` alone gives 700.

### 4. Dead fail-open code: ADDRESSED

`planted_project_files` is deleted; the only remaining mention in code is the test that asserts it is gone.
`inspect_project_files` (`os.lstat`, fail-closed) is the only project-file check, called by `cwd_problems`.

### 5. Elevated token: ADDRESSED

`WindowsAcl.is_elevated` reads `TokenElevation` (class 20, one DWORD) through the shared `_token_information`;
`_acl_problems` builds `owners = {me, Administrators} if elevated else {me}`. Probe: on this (non-elevated) shell the
real `is_elevated()` is False and PowerShell's `IsInRole(Administrator)` is False; the elevated branch is exercised
through the seam only (this shell is not elevated). `test_administrators_own_a_root_only_under_an_elevated_token`
pins both values for the root and the cwd; making Administrators always accepted fails it.

### 6. Messages: ADDRESSED

- `_acl_call` wraps `current_sid`, `is_elevated`, `lock` and `owner_and_writers`: anything but a `ProviderError`
  becomes `the ACL call <what> failed (<type>)`. `WindowsAcl.lock` sends `icacls` output to `DEVNULL` and returns the
  code, so nothing of its text can reach a message. `_verify_private` names an `OSError` by type only and runs the
  sandbox check's text through `_redacted_text`; `os.scandir` failures name the type only.
- `_redacted_text` replaces a path segment equal (case-insensitively) to the login or the home folder name with
  `<user>`; used for the root and cwd messages, `root_state`'s detail and `complete`'s unsafe-cwd message.
- Real probes with a path holding the login/home name (throwaway dirs): a file where the root should be, a shared
  root, a shared cwd and `root_state` all show `<user>`; the scan of every probed message for the login, the home
  name, the user's SID, `icacls` and `No mapping` found nothing. The only SIDs printed are other principals' (the
  write-capable ACE's or the foreign owner's); the user's own SID cannot appear because it is in the allowed set and
  in the owner set. The mutations "redaction off" and "seam exceptions not wrapped" each fail their tests.
- No added line carries the login, the home folder, the user's SID or the email's local part (scan of the diff).
- See M2 (the lookahead is narrower than the report says) and M4 (a cosmetic message).

### 7. `root_state`'s failing branch: ADDRESSED

`root_state` now tells a missing root (`it does not exist yet`) from a non-directory (`os.lstat`, not `is_dir`).
`test_the_root_state_names_each_failing_branch` covers missing, a file, a shared root, and back to locked;
`test_check_9_fails_on_a_root_that_is_not_private` drives doctor check 9 (exit 1, no model call). Real probe: missing,
file, locked, shared (`writable by S-1-5-4`), locked again, all as expected. The mutation "a file reads as missing"
fails the test.

## New-breakage checks

- **OWNER RIGHTS (S-1-3-4).** The allowed set is `{me, SYSTEM, Administrators, CREATOR OWNER, OWNER RIGHTS}`; the
  diff adds `_OWNER_RIGHTS_SID` and nothing else (`claude_code.py:467`). The owner check is separate and unchanged
  in effect: `owner in owners` with `owners` = `{me}` or `{me, Administrators}` (elevated). A foreign owner is refused
  whatever the DACL says (`test_owner_rights_count_as_the_owner[OTHER-False]`; on Ubuntu the same case refused;
  dropping the owner check fails it). OWNER RIGHTS matches only the object's owner, so it grants a foreign principal
  nothing unless that principal is the owner, which is refused. An elevated token's group owner (Administrators) is an
  accepted owner by design (item 5); administrators are inside the trust boundary.
- **Empty-after-lock and cwd check before every child.** One spawn site (`complete`), both checks ahead of it on
  win32; the nested responder runs `complete` through `build_provider`. Doctor's and the CLI's other subprocess calls
  are `--version`, with no working directory.
- **Elevated owner only when elevated.** Confirmed in code, by the seam test, and by the mutation.
- **Redaction.** As in item 6. Not covered, and outside this round: other messages that quote a path unredacted
  (`could not start <claude command>: ...`, doctor check 1's detail). On this machine `claude` is not under the
  profile, so nothing leaks here; not counted.
- **Conftest cleanup.** `_session_child_root` removes `root.parent` on a refused setup; `root.parent` is the
  directory `tempfile.mkdtemp(prefix="w-", dir=%ProgramData%)` just made in this session (resolved), with a random
  name, so it can only be one this session created; the `finally` removes the same `child_root.parent` on win32 only.
  A refused root, and the whole session, leave nothing behind (listed after my runs: none).
- **POSIX.** 0o700 after umask and no Windows-only import at load: confirmed above.

## Findings

### Critical

None.

### Important

None.

### Minor

**M1. A root refused as non-empty is accepted on the next call.** The refusal leaves the root on disk; the next
`complete` finds it existing, finds this user as owner and the writers right, and returns `ours` (probe: a real
`icacls` lock with a child made before it: refused, then `ours`). Doctor check 9 also reads `root locked` for it. It
is harmless today only because the one directory that matters, the cell cwd, gets the owner and ACL check on every
call, and nothing else in the root is an ancestor of a cwd; the implementer disclosed it (concern 3) and the
runbook says to remove the root. Any caller that retries after the `ProviderError` therefore sees the refusal once. Fix,
if wanted: `rmtree` is risky on a hostile tree, so rather have `root_state` and the existing-root path list the
root and refuse any child that is not owned by this user.

**M2. `_redacted_text`'s lookahead is narrower than "punctuation".** It ends a segment only at a separator, a quote,
a space, or one of `; : , )` or the end. A login followed by `.`, `]`, `}`, `>`, `!`, `?` or `|` is not redacted
(probe). No message this module builds has that shape (the sandbox texts put a space after the path), so nothing
leaks today; the report's wording ("punctuation") overstates it. Cheap fix: a negative lookahead for name characters
(`(?![\w-])`) or widen the set.

**M3. An Administrators-owned root under a non-elevated token is refused without a remedy.** A root first made from
an elevated console is owned by Administrators; a later run from a normal console refuses it with `owned by
S-1-5-32-544, not this user`. Correct and loud, but the message and the runbook's sentence ("accepted only when the
token is elevated") do not say to remove it or to rerun elevated.

**M4. Cosmetic: one message names the wrong directory.** `_read_owner_and_writers` raises `cannot read the ACL of the
child root (error N)` for the cell cwd as well as the root.

## Not findings (looked at, fine)

- The report's RED list, the gate numbers and the commit message agree with the diff; the trailer is the Opus 5.5
  one, the author the required address.
- `_token_information` sizes its buffer from the first call and passes the real length on the second; the token handle
  is closed in a `finally`; the SID and elevation reads are cached per process.
- An existing root, or a cwd under a root, with an attacker's inherit-only OWNER RIGHTS or CREATOR OWNER ACE does not
  matter: only the owner, or the creator of a child, gets rights from them, and nobody else may create a child.
- The check-then-spawn window and the ancestors above the root remain the accepted, recorded residual (the ruling on
  fa099e9; the runbook wording and the first-call scan order are deferred as ruled).
- `README.v2.md` modified in the tree: not part of this commit, not touched here.
