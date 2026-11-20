# Carries into Task 2 (from Task 1's review and re-review)

1. `tests/test_reasoning_capture.py` (about lines 172 to 186): the plain-cell privacy test is named and documented as covering "the bully and the judge", but a plain run never asks the judge, so only the bully half is asserted. Either make the test ask the judge (`analyze_run` with the stub judge, asserting the sentinel is in no judge prompt) or drop the judge from the name and the docstring. Prefer the first if it stays under two seconds.
2. Spec 4.1: the runner and `_Reasoning.kind` write `unknown` for text with no kind, but pass `redacted` beside non-empty text through. No backend or double produces that today. Read spec 4.1 and make the written record agree with it (if 4.1 allows only `full`, `summarized` or `unknown` beside available text, normalise `redacted` beside text the same way, with a test); if 4.1 is silent, leave the code and say so in the report.

Both are small riders. Put them in the task's one commit and name them in the report.
