# Task 7a carries

These come from the ledger. They bind this task in addition to the brief and the preflight rows that name 7a.

- **Task 1 review M1.** When a stage is reopened, it must never overwrite an earlier call's transcript. This is the seam where the open stage is re-materialized. Test it with a reopened stage name.
- **Task 1 review M2.** `index()` and `bundle_hash` must refuse a junction or a symlink, the same way the writers do.
- **Task 6.**
  - Any Director code that reads `all_strategies()` filters to what `list-strategies` lists. `make_composed` registers every premise and pressure pair globally, and test modules add names that start with an underscore. Reuse Task 6's filter; do not write a second one.
  - Planner messages run up to about 235k characters against `MAX_CONTEXT_CHARS` (300,000). The call primitive sends them on stdin, so budget for that.
  - Every message a model sees is built by Task 6's context builders, which apply the real-name scrub. Build no message outside them.
- **Plan rulings that land in 7a.**
  - R-commit: a `CallSpec.commit` hook saves the manifest in the same write as its call.
  - R-marker: read the dead attempt before reopening a failed stage, then clear the marker.
  - D-rate-limit: a rate limit removes `.attempt.json`, so a pause records no dead attempt.
  - The kill points the spec names for 7a. Test resume parity at each one; Phase 4 lesson.
- **Task 5's derived ledger.** The dry run drops a dead attempt's lines by the runtime's AttemptMarker.written rule. Use the same rule for the call primitive's ledger; do not write a new one.
- **A rate limit pauses; it never degrades.** Stub providers only; no real model call.
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
- **Write regex lines with the Edit tool only.** A Bash heredoc turns `\b` into a control character.
- **Never redirect a shell write to a bare relative path.**
