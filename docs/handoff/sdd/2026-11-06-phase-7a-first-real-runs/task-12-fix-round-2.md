# Task 12 fix round 2 (FIX_BASE 65dff39)

Inputs: the automated security review's finding on 65dff39 (in `progress.md`, starting "Task 12: security review (automated, on 65dff39)"), with its ruling, and `task-12-rereview-round1.md`. Make one commit on top of 65dff39 under the same constraints. Work TDD: get RED before each fix.

1. **Fail-open on a symlink.** `planted_project_files` checks every name with `os.path.lexists`, so a dangling or live symlink counts as planted. A `PermissionError` or other `OSError` while checking a path is itself a problem: fail closed, as a `ProviderError` naming the path. This also covers the re-review's Minor about a raw `PermissionError` on a POSIX `/tmp/w` owned by another user. Tests:
   - a dangling symlink named `CLAUDE.md` in the cwd is refused (skip where symlinks can't be made);
   - an unreadable ancestor is refused.
2. **Locked root on Windows.** When `child_cwd_root()` creates the root, set an explicit ACL with `icacls`:
   - remove inheritance;
   - grant full control (OI)(CI) to the current user (by SID, from `whoami /user` or the Win32 API, never a typed name), SYSTEM and Administrators only.

   A root that already exists is checked before use: its owner must be the current user, and no other principal may hold write rights. Otherwise refuse it as a `ProviderError` naming the root and the reason. A failed `icacls` is also a refusal.

   Tests: put the `icacls` and owner-check calls behind a small seam so a test can force each branch:
   - created and locked;
   - existing and ours;
   - existing and foreign;
   - `icacls` failed.

   Add one Windows-only test that really locks a temp root and reads back the ACL. On POSIX, `prepare_sandbox`'s owner and 0o700 checks stay as they are.

   Doctor check 9's detail names the root's state: `root locked` / `root NOT private: <reason>`.
3. **Re-review Minor: relative root in the child's environment.** If `CLAUDE_BULLY_CHILD_ROOT` is relative, the child process gets the resolved absolute value, or the variable removed. Choose one and say which.
4. **Re-review Minor: stale text.** Remove the "invented login" wording from `HANDOFF.md` and the spec.
5. **Docs.** The runbook's Step 0 and HANDOFF.md say that the Windows root is ACL-locked to the user, and that the remaining TOCTOU window is accepted under `--setting-sources ""`.

The remaining re-review Minors stay deferred: `_redacted` untested, regex cost on long unbroken runs, machine-dependent tests, binary guards pinned together.

Update `task-12-report.md` with a "Fix round 2" section. Reply in at most 8 lines: the commit sha, the gate counts, RED per item, and concerns.
