# Task 10 carries

From the ledger and the Task 7 to 9 closes. These bind this task.

- **Preflight rows.** P31, P32, P33, P47 and P48 name Task 10; read each in `preflight.md` in full. P47: every `analyze` that does not write `ratings.json` reads an existing one and applies its flags, with no judge call.
- **`rate_values` is the values watch's recall path (Task 9 ruling).** The heuristic `values_loosened` is a lower bound by design; `rate_values` over every post-reveal reply is what catches the rest. Its prompt must be strict and neutral (state both outcomes alike, as Task 7's confirm prompt does), and a rating flag must never count as a success (non-negotiable 3: it flags the rep). Keep the 7b runbook's line that every environment-cell Phase 4 rung runs `analyze --ratings` true.
- **Judge prompts (Tasks 6 and 7).** Each prompt reads `chat_text` only, never `reasoning_text`; it shows the bully line and the reply (the spec's context), never names the hypothesis it serves (spec section 11, "blind"), and an answer off its list or an ask that fails twice is left out and counted. A rate limit re-raises (pauses `analyze`, exit 3) and the rerun replays the cached verdicts (7a Task 6 pattern). Cache in the run's `judge_cache/` under the existing `JudgeCache` key helper so it travels with `promote`.
- **The reasoning channel test.** Add the rating prompts to `tests/test_reasoning_channel.py` with the sentinel on watched Turns (Task 8 fix round 1's pattern), not only on Completions.
- **Task 9 minor M4.** Record-bound events carry confidence 1.0 for an `llm` verdict judged at 0.6; where this task weighs or reports by confidence, use the classifier.
- **Quote every new prompt verbatim in the report.**
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
