# Task 3, fix round 4: open findings and method

A prior implementer attempted the second_person fixes three times (rounds 1-3); you own it now. Read the report file for what was tried, in order. Round 3 was stopped at the owner's request and committed as WIP in 158746b: it has not been reviewed, and the full gate was not run on it.

## Open findings (verbatim from the round 2 re-review, as summarized in the ledger)

1. **Finding 4 (Important), identity billboards pass the instructional kinds.** An anchored clause approves identity billboards in `family_faq` and `recovery_guide`: 11/17 fresh false passes at 386801c. Round 3's sentence-wide veto and slot rule reduced it to 7/15 on the round 3 implementer's own untuned set. The 7 misses all carry the identity content in a clause whose "you" sits in a procedural slot, or in a clause without "you" at all:
   - "the faces start to blur";
   - "your hands feel like a stranger's";
   - "the file with your name on it";
   - "whether the woman who calls is your wife";
   - "a name you have never used" ("you have" passes the slot rule);
   - "stopped sleeping since the transfer";
   - "where they came from before".
2. **New (Important), legitimate procedural FAQ false-fails.** About 24% false fail at 386801c (coordination split, negative imperatives, verb list), which made a FAQ infeasible in two attempts. Round 3 reports 2/20 (10%) on its untuned set, which is exactly at the limit.
3. **Docs not synced to round 3.** The module docstring of `claude_bully/planner/second_person.py` and the Billboard row of `docs/08-DIRECTOR.md` still describe round 2. They must describe the rule as built when you finish. Check `docs/00-RECONCILED.md` too, if it names the second_person rule.

## Targets (the round 3 ruling, binding)

Measured on a fresh probe the code was never tuned on, `family_faq` and `recovery_guide`:
- instructional billboard false passes: at most 2 of 15;
- legitimate procedural false fails: at most 10%.

The re-reviewer measures on a new probe it writes itself, from the same families but with sentences you have not seen. Tuning to the 7 misses above will not carry over. Round 3 tuned to its sets 1 and 2 (0/15 and 1/15) and then scored 7/15 on set 3.

## Method (controller ruling for round 4)

- Keep the round 3 structure: the anchor decides form and the veto decides content. Identity talk is the billboard's whole vocabulary. The asymmetry stands: a false fail costs one generator retry, and a false pass ships a billboard. Ambiguous cases fail.
- The misses show that a veto on *where "you" sits* is not enough. Extend the content test from the slot of "you" to the **role of the reader in every clause of a "you" sentence**. In the instructional kinds, the reader may appear only as the agent of a procedure or the recipient of a service. A clause fails when the reader, a "your" noun phrase, or a body or self noun under the anchor is:
  - the experiencer of a perception, feeling, body-state, cognition or change-of-state predicate (feel, seem, look like, blur, recognise, forget, stop/start + -ing, and their kind);
  - a predicate nominal (`is your wife`, `are not who`);
  - in a past or perfect clause with a non-procedural verb (`you have never used`, `came from before`, `you used to`).

  "wash your hands" passes and "your hands feel like a stranger's" fails. Choose the mechanism yourself: closed predicate classes, clause-role rules, or something better. Prefer a rule that fails closed on unseen wording over a longer word list. Word lists overfit; that is the lesson of rounds 1 to 3 and of Phase 2 Task 12.
- Before you change code, write two fresh probe sets of your own (15 billboards and 20 legit procedural sentences each). Write billboards a generator model would plausibly produce for a family FAQ or a recovery guide in this world, not only evasions of the current rule. Tune on set A only. Do not look at set B's results until the end, and report set B as your honest number, as round 3 did with set 3.
- Fixtures go in first (RED), per the brief's TDD rule. Add fixtures for each new rule class, with legitimate near-misses.
- If, after an honest try, you judge that the targets cannot be met by a deterministic lint without overfitting, say so. Report DONE_WITH_CONCERNS with your set B numbers and the residual classes. Do not hide the gap behind tuned sets. An LLM lint is already planned for Phase 7, and a measured residual is a usable result.

## Gate

Before you commit, run the full gate (all must pass, 0 warnings):
`uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy claude_bully`, `uv run pytest -q -W error`, `uv run pytest -q -m slow`.
