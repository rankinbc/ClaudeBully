# Task 9 carries

From the ledger. These bind this task, along with the brief and the preflight rows naming 9 (Q46, Q48, Q50 and Q59 among them: planner/cli.py and cli.py import each other, so the two shared names move to runner/wait.py; a resumed run's personas are registered before expand_cells; `plan diff` needs `--worlds-dir`; the shapes test must assert more than identity).

**Plan states.**
- `plan continue` on a plan whose stage 4 committed with open blocks refuses with a clear message. It never goes straight to validate.
- `plan validate` never reaches `runnable` while blocks are open.
- `stop_after_plan` on a plan whose stage 1 is already committed stops. It does not go on into stage 2.

**Damaged records.** A damaged harness record raises `ValueError` naming the line: a mid-file ledger damage, or a bad byte in plan.json from `read_record`. The CLI catches it, prints the file and the line, and exits non-zero without a traceback. Add a row for it to spec section 13.

**Dry run.**
- M-1: a resume reads only its own plan id's dry-run cache.
- M-4: the stray-search-hit message names the document.
- M-5: either a rate-limit resume's records equal the clean run's, or the spec states the cell-level contract.
- `lint_bundle` runs `dry_run` only after `schema` and `ladder_walk` pass, because `dry_run` raises on an unwalkable ladder.

**Strategies.** Director code that reads `all_strategies()` uses Task 6's list-strategies filter.

**Stage 5.** Run the denylist scans as the stage 2, 3 and 4 paths do. Reuse `Director._scan_bundle`; do not copy it. Stage 5 also runs the whole `lint_bundle` and records its results in plan.json. Task 4b made the jailbreak lint read only `record.request`, so recorded lint results cannot fail a later validate.

**Phase 4 lessons and 7a/7b rules.**
- Test resume parity at every kill point stage 5 adds, including hard kills inside each write. Use the sweep probe in `probes-task7b-fixround1/`.
- A rate limit pauses the run and never degrades it.
- Use stub providers only.
- Every pytest run uses the pyproject `faulthandler_timeout` (120 s).

**Environment.**
- Disk is about 2 GB free. Delete every bundle and temporary run as soon as it has been compared. Keep probe output under 200 MB. Check free space before and after with PowerShell `Get-PSDrive C`, and stop if it falls under 1 GB.
- Write regex lines with the Edit tool only.
- Never redirect a shell write to a bare relative path.
