# Task 3, breaker fix: restore round 4's form side, keep round 5's fixes

The five fix rounds are spent. The controller has adjudicated, and this is the one change the adjudication calls for. It is a merge of two known versions, not a new method.

## Why

On two independent fresh probes, round 4's form side caught billboards and round 5's did not:

| Commit | Form side | Billboard false passes |
| --- | --- | --- |
| 4c10eea | closed anchor lists | 1/30 and 4/30 |
| 3bc11f2 | open verb class | 14/30 |

The binding ruling is "when the two targets trade off, the billboard target wins". Legitimate false fails are now repairable. Every instructional failure message carries the repair hint, and 6/6 rewritten false fails passed.

Read these:
- `.superpowers/sdd/2026-10-24-phase-3-world-generator/task-3-rereview-round5.md` (the round 5 findings, with file:line);
- the round 4 and round 5 sections of `.superpowers/sdd/2026-10-24-phase-3-world-generator/task-3-report.md`.

## What to build (start from HEAD, 3bc11f2)

1. **Restore 4c10eea's form side.** Bring back its closed anchor lists and the anchor and slot logic that uses them, in place of round 5's open verb class with its closed experiencer class. `git show 4c10eea:claude_bully/planner/second_person.py` is the reference.
2. **Keep these from round 5:**
   - N2: `_ING_NOUNS`, so nothing, anything, something, morning and building are not gerunds.
   - N4: the reader's specific kin fail in any slot. Widen the kin list to siblings, step-parents, grandparents (granny, grandad, and their kind) and "other half".
   - The repair hint on every instructional-kind failure message.
   - N3: change of state, past and perfect read only the reader, a "your" phrase, or a body or self noun (`_subject_of`).
3. **N1 (named time).** Drop `_finite_after`, which reads a plural noun as a verb and re-opened "before the move to the new flats". Return to 4c10eea's named-time reading. Excuse only N1's two confirmed false fails, by a rule that does not re-open the named-time billboards:
   - "Wait in the lounge until the porter on duty comes to collect you.";
   - "Please ring ahead if you can, since the nurse who runs the clinic may be away."
4. **N3 (perception).** A perception frame on a thing subject fires only before a comparison or oddness complement, or before "as if". "The lounge can feel chilly in winter, so you may want to bring a cardigan." passes. "The corridor seems longer than it did" still fails. Perception with the reader, a "your" phrase or a body noun as experiencer still fails as before.
5. **Fixtures (RED first).** For each item above, add a positive and a near-miss. Keep every existing fixture green. For round 5 fixtures that encode the open verb class (a legitimate sentence passing only through an unlisted verb), you may flip them to fail. List each flip in the report.
6. **Docs.** The module docstring and the Billboard row of `docs/08-DIRECTOR.md` must describe the rule as built. In `HANDOFF.md`:
   - Progress, Phase 3 Task 3: rewrite it to describe the final state: five fix rounds, this breaker fix, and the measured residuals (billboards from your set B, legitimate false fails repairable by the hint, and the semantic residual left to the Phase 7 LLM lint);
   - the test counts;
   - the "Last updated" line;
   - the resume prompt, which should resume at Task 4.

   Do not touch `docs/handoff/`.
7. **Size.** `second_person.py` must stay at or under 1141 lines.

## Measure

Before changing code, write a fresh probe set B under `.superpowers/sdd/2026-10-24-phase-3-world-generator/probes-breaker/`: 15 billboards and 20 legitimate procedural sentences per kind (`family_faq`, `recovery_guide`), in varied wording. Score it once at the end. The re-reviewer measures again on its own probe.

Targets:
- billboard false passes at most 2 of 15 per kind (binding);
- legitimate false fails reported, with no target. Each one must carry the repair hint.

## Gate

Before you commit, run every step (all must pass, 0 warnings):
- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy claude_bully`
- `uv run pytest -q -W error`
- `uv run pytest -q -m slow`
