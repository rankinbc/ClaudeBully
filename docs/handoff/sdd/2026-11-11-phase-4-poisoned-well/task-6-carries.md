# Task 6 carries

From the ledger. These bind this task.

- **Task 1 carry (corrected by the Task 1 review), plus Task 4's report.** This task holds the only production setter of `UnlockState.checksum_open_turn` (plan, about line 4105). The value is both saved with the turn and derived. `prime` must never clear the saved value, and on a resumed rep the derived value must equal it. Task 4 added a runtime-level pin. This task adds the session-level pins that Task 4 review M4 named:
  - a kill after the set, then resume;
  - a kill before the save, then resume.

  Each asserts the readings are served as in the unbroken run.
- **Task 3 review M5, run-level half.** The rep records whole quirk entries (Task 5 stores them in the refs). Add a run-level test: after the record is written, edit or remove the bank entry. The resumed rep and its `load_run` analysis must both use the recorded entry, and nothing may raise in `quirks_for`.
- **Task 3 re-review M1.** The plan's test around line 3488 used "strawberry", which is gone. Take the quirk prompt from the bank entry by id.
- **Task 5 re-review N2.** The plan's code blocks still show the old `- turn {a}` dossier layout. The shipped layout is `- earlier: "..."  /  later: "..."` in turn order, and no internal index is ever shown. Do not reintroduce the old one.
- **Lesson from Task 4.** Quote every new target-visible or bully-spoken line in the report. Each one reacts and never delivers.
