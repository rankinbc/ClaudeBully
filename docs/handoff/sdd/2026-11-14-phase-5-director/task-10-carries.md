# Task 10 carries

These come from the ledger. They bind this task together with the brief and the preflight rows that name Task 10 (Q48 and Q50 among them).

**Q48: register personas before expanding cells.** A resumed `run` on a bundle registers the bundle's personas before `expand_cells`. Use the scoped `plan_personas` built in Task 4a, which:
- calls `ensure_registered()` first;
- removes only what it registered;
- leaks nothing across cells, tests or processes.

**Q9: refuse a bundle that is not runnable.** `run` on a bundle whose plan.json status is not `runnable` refuses with a clear message and a non-zero exit, before anything is written.

**Use Task 9's error contract.**
- Catch only `DamagedRecordError` and `DirectorError`. Every other exception keeps its traceback.
- Print a damaged record as its file plus its line or field.

**Task 6: filtered strategies.** Code that reads `all_strategies()` uses the list-strategies filter.

**Pin the plan on the run record.** `RunRecord.plan` is an additive field (A6/A1 in the spec). Pin the bundle's identity in it: `bundle_hash`, the persona set and the expected events, so a run can be traced to the exact bundle it came from. A plain run's record stays byte-identical, so the golden files must not change.

**Copy every named world (A6).** The run copies or pins each world the bundle names, so a later edit to a shipped world cannot change a bundle's run.

**Resume parity.** A run on a bundle that is killed and resumed matches an unbroken run. Kill it at the run's existing kill points; resume is the Phase 0 to 4 rules.

**Real names.** None anywhere. Every new message or file is under the scans.

**Phase 4 lessons.**
- A rate limit pauses the run; it never degrades it.
- Stub providers only.
- Every pytest run uses the pyproject `faulthandler_timeout` (120 s).

**Disk.** About 2 GB is free.
- Delete every run and bundle you create as soon as you have compared it.
- Keep probe output under 150 MB.
- Check free space with PowerShell `Get-PSDrive C`, and stop if it falls under 1 GB.

**Shell writes.** Write regex lines with the Edit tool only. Never redirect a shell write to a bare relative path.
