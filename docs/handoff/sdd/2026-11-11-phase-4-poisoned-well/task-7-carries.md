# Task 7 carries

From the ledger. These bind this task.

- **Task 1 carry (corrected by the Task 1 review).** A degraded turn writes no record, so `UnlockState.contradictions_degraded` cannot be rebuilt from the records. Keep it on the saved state after `mark_watched`, and recompute it when the turn is watched again on resume. Add two tests: one kills before `mark_watched`, one kills after. Each asserts the value against an unbroken run's.
- **Task 5 re-review N3.** `ContradictionPair.span_a` is the earlier sentence (`turn_a < turn_b`), and `_dossier_text`'s order relies on that. Validate it on the record, or pin it with a test that builds a pair from two turns given out of order.
- **Task 5 re-review N2.** The plan's code blocks still show the old `- turn {a}` dossier layout. The shipped layout is `- earlier: "..."  /  later: "..."` in turn order, and no internal index is ever shown to the target. Do not reintroduce the old one.
- **Task 6.** The chain classifier's precision rule applies to the contradiction pass as well. The heuristic is precise, and a doubtful or hedged case goes to the judge, never to a heuristic positive. The pass reads `chat_text` only, never `reasoning_text`. Pin that at run level, the way Task 6 did.
- **Lesson from Task 4.** Quote every new target-visible or bully-spoken line in the report.
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
