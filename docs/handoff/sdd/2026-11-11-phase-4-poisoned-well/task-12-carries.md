# Task 12 carries

From the ledger. These bind this task.

- **Preflight rows.** P28, P31, P32, P34 and P50 name Task 12; read each in `preflight.md` in full.
- **Task 10 R2-m1 (must, before this task reads ratings).** The ratings prompt digest (`metrics/ratings.py`, about lines 169-175) leaves out `NO_USER_LINE` and the code that picks and formats what the judge sees (`_answered_line`, `_transcript`), so a change there applies old verdicts silently. Fix it first: the digest covers the prompt as rendered for a fixed probe item with and without a user line (or each item stores its own prompt hash), and a test changes the selection code's output and sees the verdicts stale. Also Task 10 R2-n1 (spec section 11 still quotes the old `rate_values` wording) and R2-n3 (`results.md` names the stale-verdict count from `analysis/ratings_applied.json`).
- **Task 10 re-review out-of-scope.** `values_loosened_by` reads the first event's classifier, so a rep flagged by both the heuristic and the judge reads `judge`. Report `both` (or the list) when both flagged it.
- **Task 9 M4.** Record-bound events carry confidence 1.0 for an `llm` verdict judged at 0.6 (`verdict_classifier` exposes the classifier). Where this task reports rates by classifier or weighs by confidence, read the classifier, not the confidence.
- **Task 7.** `UnlockState.contradictions_degraded` reaches the world record here (`rep{k}.world.json`'s `poisoned_well` block, `LoadedRun.contradictions_degraded`); a degraded turn's kept pairs are unconfirmed, so `poisoned_well.json` reports the degraded count beside any pair count.
- **Non-negotiable 3.** A `values_loosened` rep (heuristic or `rate_values`) is flagged and never counts as a success; every rate the charts draw leaves it out and states the count.
- **Stub data says nothing.** Stub runs give uniform rates; the charts must render on stubs, but no claim about results is made. No real run (owner ruling 2026-11-11).
- **Plain goldens stay byte-identical; SCHEMA_VERSION stays 3, additive only.**
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
