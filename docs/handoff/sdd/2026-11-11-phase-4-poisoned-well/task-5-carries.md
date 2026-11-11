# Task 5 carries

From the ledger. These bind this task.

- **Task 3 review, M5:** when a rep records the quirk entries it uses (the I5 ruling), it records whole entries, or the id plus a content hash with the entry's text. Resume and `load_run` must then work from the recorded entry when the bank entry has since changed or vanished, never raising in `quirks_for`. Add a test that edits a bank entry after the record is written: the resumed rep and its analysis use the recorded entry.
- **Task 2 review, M1:** on replay, `observe_target` runs before `note_record`; live, the order is reversed. If the premise, or any strategy this task writes, implements both hooks, make the two orders match and pin it with a kill test. If none does, say so in the report.
- **Task 3 re-review, M1:** any test that names a quirk prompt (the plan's tests around line 2355 used "strawberry", which is gone) takes it from the bank entry by id.
- **Lesson from Task 4:** any line the bully says or relays from the premise sheet or the stage machine is read the way the target would read it. It reacts and never delivers. Never write a line that states the stage's conclusion, names the evidence, or credits the target with a doubt it hasn't voiced. Quote every new target-visible line in the report, so the review can read them.
