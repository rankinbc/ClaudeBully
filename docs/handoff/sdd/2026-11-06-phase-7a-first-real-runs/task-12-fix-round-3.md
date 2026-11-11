# Task 12 fix round 3 (FIX_BASE fa099e9). This is the last round on this axis.

Inputs, all in this folder:
- `progress.md`: the security finding on fa099e9 and its ruling. Search for "security review (automated, on fa099e9)".
- `task-12-rereview-round2.md`.
- `task-12-report.md`: rounds 1 and 2, to show how the code got here.
- `task-12-brief.md`: the original rulings R1 to R5.

Make one commit on top of fa099e9. Constraints are those of the brief and `global-constraints.md`, with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and the author `rankinbc1@gmail.com`. Work TDD, with RED per item. Do not push. Do not dispatch subagents.

1. **Security: the creation window.** If this process just created and locked a root, the root must be empty after the lock, or it is refused. Before any child starts, the cell cwd gets the same check as the root: its owner is the current SID (or Administrators when the token is elevated; see item 5), and it has no write-capable ACE for anyone else. This applies on every path, including the nested responder inside the MCP server child. Test through the existing seam:
   - a child that appears between mkdir and lock is refused;
   - a foreign-owned cwd is refused;
   - an extra-writer cwd is refused.
2. **I1, mypy on Linux.** `uv run mypy --platform linux claude_bully` must be clean, as must the default `uv run mypy claude_bully`. Guard every Windows-only ctypes access with `sys.platform == "win32"` in a form mypy narrows on. Add `uv run mypy --platform linux claude_bully` to your gate for this round, and record it in the report.
3. **I2, the POSIX tests.** On POSIX, the root and cwd are created at mode 0o700: pass `mode=0o700`, then `chmod` to beat the umask. The five tests that failed on Ubuntu must pass there. If WSL is available (`wsl -l -q`), run the changed test files under WSL with `uv`, and record the result. If it isn't, say so; do not claim POSIX passes.
4. **Minor: dead fail-open code.** `planted_project_files` still fails open and has no caller. Delete it, or make it the `os.lstat` fail-closed form and give it a caller; say which.
5. **Minor: elevated token.** When the process runs elevated, a new directory's owner is the Administrators SID. Accept Administrators as the owner only when the token is elevated, and pin that with a test through the seam.
6. **Minor: messages.** Wrap raw exceptions from the ACL seam as `ProviderError`. Messages and doctor details never carry `icacls` output or a path that includes the user's profile. Redact any path segment that equals the login or the home folder's name, and test that.
7. **Minor: test the failing branch.** Test `root_state`'s failing branch.

The rest stays deferred, recorded in the ledger: the runbook's wording about ancestors above the root, and the first-call scan order.

Append a "Fix round 3" section to `task-12-report.md`. Reply in at most 8 lines: the commit sha, the gate counts (including the Linux mypy run, and the WSL result or that it wasn't available), RED per item, and concerns.
