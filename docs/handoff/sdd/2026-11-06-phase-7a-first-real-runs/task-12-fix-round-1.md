# Task 12 fix round 1 (FIX_BASE adedf7d)

The review is in `task-12-review.md`, and the automated security review's finding is in `progress.md`. Make one commit on top of adedf7d, using the same constraints as the brief. Work TDD: get RED before each fix.

1. **Security (MEDIUM), which also closes review M8.** `promote`'s email scan reads `chat_text` only. `promote` copies more than that: `run.json`, `ledger.jsonl`, every `CELL_FILE_GLOBS` match (turns with `reasoning_text` and `bully_meta`, `conversation.json` with captures and strategy state), and everything under `judge_cache/` and `analysis/`. Run the email scan over the decoded text of every file `promote` would copy, before anything is copied. Block on any non-reserved address. Each block line names the run-relative file and the line number, never the address itself. Keep the real-name policy on its current streams. A `.png` or other binary under `analysis/` is skipped, never decoded. Tests:
   - an address in `reasoning_text` blocks;
   - an address in a judge cache entry blocks;
   - an address in a `bully_meta` capture blocks;
   - a reserved address in any copied file passes;
   - nothing is copied when a block fires.
2. **I1.** Make the suite override's login and home-folder name differ, or add a test where they differ. The aim: deleting the home-folder clause of `neutral_cwd_problems` must fail a test. Confirm this by deleting the clause, running the test, then restoring it.
3. **M1, a targeted check that replaces "refuse a non-empty cwd".** Before a child starts, refuse a working directory where the cwd or any ancestor holds a `CLAUDE.md`, `CLAUDE.local.md`, `.claude/` or `.mcp.json`. The refusal is a `ProviderError` naming the path. Doctor check 9 reports this too. The user's own home `~/.claude` is not an ancestor of the default root, so confirm that the default root passes on this machine (the test monkeypatches nothing but the env var), and say so in the report. Cost if wrong: a refusal where the CLI would have ignored the file, which fails loudly.
4. **M2.** `getpass.getuser()` and `Path.home()` failing in a stripped environment: treat the failure as that name being unknown and skip that clause. Do not crash.
5. **M3.** `UnsafeSandboxError` reaching `complete`: wrap it as a `ProviderError` there, so the runner and the ledger treat it as any other provider failure.
6. **M4.** A relative `CLAUDE_BULLY_CHILD_ROOT` is resolved to an absolute path once, in `child_cwd_root()`. Pin this with a test.
7. **M6, docs.** In the runbook and HANDOFF.md: resume needs the same `CLAUDE_BULLY_CHILD_ROOT` value it ran under, and runs started before Task 12 cannot `--resume` their claude sessions.

Deferred, recorded as Minors: M5, M7, M9.

Update `task-12-report.md` with a "Fix round 1" section. Reply in at most 8 lines: the commit sha, the gate counts, RED evidence per item, and concerns.
