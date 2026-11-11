# Task 4 carries

From the ledger. These bind this task.

- **From Task 1** (corrected by the Task 1 review): `UnlockState.checksum_open_turn` is classified as saved with the turn. This task sets it (plan, about line 2177). Rebuild it on resume from the turn's written records, or keep it on the saved state and never clear it in `prime`. Add a test that resumes a rep after the set and asserts the value equals the unbroken run's.
- **From Task 3's review:** the quirk bank no longer holds "strawberry" or 9.11/9.9 (now "nevertheless" and 8.13 vs 8.7). Any test or line in this task that names a quirk prompt takes it from the bank entry by id, never from a literal.
