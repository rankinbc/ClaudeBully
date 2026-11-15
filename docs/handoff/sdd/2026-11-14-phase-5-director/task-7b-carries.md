# Task 7b carries

These come from the ledger. They bind this task in addition to the brief and to the preflight rows naming 7b (Q39 among them: 7b's config check needs a temporary runs root).

- **From the Task 7a re-review (binding).**
  - Split a pure parse from the check, so that resume rebuilds `parsed` with no state.
  - Freeze the manifest's call budget as of the call.
  - Replay from the committed call list.
  - Write a test that pins a resumed `parsed` and `provider_failed` equal to an unbroken run's.
  - A state-dependent check, such as the manifest's call budget, must never see a different state on resume.
- **From the Task 6 re-review (N-B).** Stage 2 shows plan.md to file calls. Before any stage-2 call shows it, run the denylist scans on it: `real_name_bundle` with the owner clause, Boundary, and jailbreak. A hit fails the stage as a lint failure, and the scan never raises.
- **From the Task 4a review (N5).** The planner's `repair:` calls are not yet read. Wire them as the brief says, or state in the report why 7b does not need them.
- **From Task 6.** Every message goes through Task 6's context builders, which apply the real-name scrub and keep fences unscrubbed. Do not build a prompt string anywhere else. Planner messages run up to about 235k characters, within `MAX_CONTEXT_CHARS` (300,000).
- **From Task 7a.** Use the call primitive as built:
  - `DirectorAttempt.ledger_lines`;
  - `provider_failed`;
  - one dead attempt per marker;
  - a resumed error call fails again.
  - Test resume parity at every kill point the spec names for stage 2. Re-use 7a's kill-sweep probe pattern (in the ledger folder, `probes-task7a`) over stage 2's write boundaries.
- **Phase 4 lessons.**
  - A rate limit pauses; it never degrades.
  - Stub providers only.
  - Every pytest run uses the pyproject `faulthandler_timeout` (120 s).
- **Shell writes.** Write regex lines with the Edit tool only. Never redirect a shell write to a bare relative path.
