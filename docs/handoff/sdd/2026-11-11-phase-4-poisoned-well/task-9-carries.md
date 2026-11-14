# Task 9 carries

From the ledger and the Task 7 and 8 closes. These bind this task.

- **Preflight rows.** P12, P18, P34, P35 and P52 name Task 9; read each in `preflight.md` in full.
- **Task 7 and 8 interfaces.** `ContradictionPair` records come from `metrics/contradictions.py` (`classifier` `heuristic` for a template pair, confirmed by the judge where one runs; `llm` at 0.6 for a judge-named pair; `retracted`; `UnlockState.contradictions_degraded` for a turn whose judge failed). The shared frame cue list (`_FRAME`, `_framed`) now lives in `claude_bully/environments/harvest.py`; reuse it, never copy it. Task 8's fire reasons are `SHIBBOLETH_REASON`, `PREFERENCE_REASON`, `TWIN_REASON` in `environments/poisoned_well.py`.
- **The detector lesson (Tasks 6, 7 and 8 took two to four fix rounds each on exactly this).** Text detectors over target `chat_text` are closed by construction: a positive closed template, never a growing list of deny rules; an open class (frames the bully sets in its own words, meta replies) is closed by a judge or stated as a residual, never patched with more words. Write the fixtures before the code, over half near-misses, including a frame or role the bully set earlier in the conversation (not only in the answered line), a quotation, an echo of the bully's line, a hypothetical, a report of someone else, a refusal. Record-bound events read the records, not the text, wherever a record exists.
- **Measure out of sample.** Report each text detector's precision on the fixtures and on a fresh probe you write before reading your own patterns closely; the reviewer will write another.
- **The reasoning channel is private.** Every detector reads `chat_text`; pin it with the sentinel-on-watched-Turns pattern of `tests/test_reasoning_channel.py` (Task 8 fix round 1), not a sentinel on Completions only.
- **The dossier layout (Task 5 re-review N2).** No internal turn index is ever shown to the target; analysis output may name turns.
- **Quote every new target-visible line and every new prompt in the report.**
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
