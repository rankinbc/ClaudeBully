# Carries into Task 4a (from Task 3b's re-review)

Two documentation riders, to fold into this task's one commit and name in the report:

1. `HANDOFF.md` (about line 233) says "the fourth privacy test excepts `divergence.jsonl` alone, for the span alone". A `divergence.jsonl` line holds the spans of every verdict that has them and the judge's rationale. Correct the sentence.
2. `claude_bully/analysis/divergence.py` (about line 14) says `by_kind` is "the turns with reasoning by kind". `redacted` is counted on turns with no reasoning, so it can exceed `with_reasoning`. Correct the docstring to match docs/10 "Outputs".

Also know: `claude_bully/analysis/arms.py` now raises `ArmConfigError` (a `ValueError`) for a present-but-broken environment or countdown config, and returns `none` only for a cell with no environment. `analysis/arms.py` holds `ignition_arm`, `arm_of` and `channel_of`; your task's channel work reads `channel_of` from there.
