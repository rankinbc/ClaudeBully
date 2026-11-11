# Task 4 fix round 1 (FIX_BASE 1973413)

Inputs: task-4-review.md (I1, I2 with the reviewer's proposed replacement lines; M1 to M3). Make one commit on top of 1973413 under the same constraints. Work TDD, with RED per item.

1. **I1 and I2: four unlock lines (`world.yaml` about lines 207 to 217).** The four lines are `provenance_gap_line`, `checksum_line`, `divergent_twin_line` and `annotators_notes_line`. Replace each with the reviewer's proposed line, or with one of the same shape if a proposal fails a check. Each line reacts to what the target just did. It never names a document, an address, a tool or the rung's conclusion, and never credits the target with a doubt it hasn't voiced.
   - Add a test that pins each of the four lines against its rung's conclusion words, which the review lists per line. Take the test's word lists from the review and the brief.
   - Extend the unlock-line lint, or add a test, so that a line naming its own rung's evidence noun fails. "List" for the manifest is one such noun; the old provenance line passed only because `DOC_POINTERS` lacked "list". Add the missing evidence nouns to the pointer list, or check per rung.
   - Update the plan's and the spec's text of these lines (plan Task 4 and the spec section on the unlock lines) to the new text, with a bracketed note "revised in Task 4's review".
2. **M1: the work log's file name.** Rename the work log to `hq-2050-04-11.txt`, the date of its first entry. Keep the dating tests green under the far-forward and far-back clocks.
3. **M2: chiller consistency.** Make the new chiller story consistent with "never surprised us" in `rr-kelden-chillers`. Change the new text, not the old document.
4. **M3: the lone monthly log.** The "monthly logs" directory holds a single file, which makes too clean a trail. Add one or two sibling filler logs: mundane, premise-free, dated with the clock. Keep filler at or above the 30 percent floor, and update the HANDOFF "Overlay content" counts.

Deferred: M4 (Task 6 owns the session prime and the kill-before-save pins) and M5.

Update `task-4-report.md` with a "Fix round 1" section, and keep the HANDOFF Task 4 item true. Reply in at most 8 lines: the commit sha, the gate counts, RED per item, and concerns.
