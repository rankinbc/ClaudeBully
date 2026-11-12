# Task 5 fix round 1 (FIX_BASE 20d852b)

Inputs: task-5-review.md (I1, I2, m1 to m6). Make one commit on top of 20d852b under the same constraints. Work TDD, with RED per item.

1. **I1: dossier fallback.** `_fallbacks` (in `poisoned_well.py`, about lines 422 to 425) adds `_dossier_text()` to every dossier fallback line. When the bully model's line fails and a fallback is spoken, the target still gets the list. Add a test: the bully double fails the out-of-character check on a dossier quoting "I'm an AI assistant". The spoken line must hold the list, and the stage still advances as before.
2. **I2: turn order, not turn indices.** This is a controller ruling (ASSUMED, the owner told). The dossier never shows the conversation's internal turn indices. Each pair renders in turn order as `- earlier: "{span_a}"  /  later: "{span_b}"`. Change the test's `"turn 3"` assertion to an order check. In spec section 6 and `docs/07-POISONED-WELL.md` (about line 52), change "with turn numbers" to "in turn order", with a bracketed note "[revised in Task 5's review: the indices count bully, task, idle and pause turns the target cannot count]".
3. **m1: unselected conditions under `--only`.** An unselected Poisoned Well condition must not break the run. If its check runs, a refusal names the condition, never a raw pydantic error. Add a test.
4. **m2: a refused quirk id.** An unknown or stale quirk id is refused with the condition's name in the message.
5. **m3: the order of pending moves.** The spec says "lowest", so the code takes the lowest first. If "lowest" is ambiguous against the record, say so in the report.
6. **m5: stale spec text.** Remove the sentence that says the rules also run from `check_worlds`, or make it true. The code doesn't change `check_worlds`, so the sentence goes.
7. **m6: list layout.** The dossier list starts on its own line, after the instruction.

Deferred: m4.

Update `task-5-report.md` with a "Fix round 1" section, keep the HANDOFF Task 5 item true, and quote every changed target-visible line. Reply in at most 8 lines: the commit sha, the gate counts, RED per item, and concerns.
