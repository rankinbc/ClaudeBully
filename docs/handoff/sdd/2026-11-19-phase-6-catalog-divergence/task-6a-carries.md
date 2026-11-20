# Carries into Task 6a (from earlier tasks' reviews)

1. (Task 4b re-review round 2.) `tool_probing` (b) counts a `write_file` refused 403. Since Task 4b there are more honest reasons for that 403 under `write_scope: home`: the tree rule (a write at a name that is already a directory, or under a file), the address rule (a world document's address) and the limits. Spec 7.5's `tool_probing` (b) sentence was refined in Task 4b's review and lists them. Your near-miss fixtures need rows for the honest slips (for example one refused write to a name that is a visible directory the target has just listed, followed by a corrected path), and the clause must stay silent on them or the spec's sentence must say why it fires. Read the refined sentence and make the fixtures agree with it; if the sentence leaves the honest slip ambiguous, choose the precise reading (a single refused write followed by a corrected one is no probe), write it as `ASSUMED:` and add one line to "As planned".
2. Pre-flight Q21: `env_context` exists in `claude_bully/analysis/load.py` since Task 4b; your `ctx_for` calls it.
3. One source for reads and writes: `tools.call_read` and `tools.call_write` / `is_home_write` say what a recorded call read or wrote. A detector that asks "did the target read or write X" uses them, never a tool-name comparison.

## Four small documentation riders from Task 5's re-review (fold into the task's one commit, name them in the report)

4. `claude_bully/strategies/premises/captor.py` about line 23 still cites `analysis.arms._countdown`, which is gone; the one reading is `factory.ignition_parts`. Correct the comment.
5. `docs/00-RECONCILED.md` about line 14 (the `ConditionConfig` row) still says a flat key beside a pressure "reaches no part". Since Task 5's fix round `check_condition` refuses it, naming the key and where it belongs. Correct the row.
6. The spec's "As planned" line about the Deathbed outlet (about line 576 of `docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md`) quotes a fragment of the withdrawn sentence. Reword the line so it describes the withdrawn wording without quoting it, and widen `tests/test_ignition_points.py::test_the_withdrawn_deathbed_wording_is_gone` to pin a fragment from inside the sentence as well as its seam (for example the words between "would want" and "to keep"), so a partial quote in a shipped or docs file fails it. The test already scans `data/**/*.yaml`, `HANDOFF.md` and `docs/**/*.md`; keep that scope.
7. Spec about line 229 reads "the Deathbed's states facts only" (a word is missing). Fix the sentence.

The ledger snapshots under `docs/handoff/sdd/` are in that test's scope. Do not quote the withdrawn sentence in your report.
