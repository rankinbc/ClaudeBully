# Task 6 fix round 1 (FIX_BASE d3da876)

Inputs: `task-6-review.md` (I1, M1, M4 to M6), its probes in `probes-task6/` (data only), `task-6-report.md`, `task-6-brief.md`, `global-constraints.md`. Make one commit on top of d3da876 under the same constraints. Work TDD, with RED per item. Run every pytest command with `-o faulthandler_timeout=60`.

1. **I1: negated "follows" (`chain.py` about line 67, the accept template).** A negated, doubted or hedged "follows" must never match the accept templates. Add a guard before them (negation or doubt within the clause: not, n't, never, doubt, unsure, "not sure", "not convinced", "don't see how", "wouldn't say", and a trailing "but it doesn't"). A guarded reply falls through to the rest of the classifier: the reject templates, else the judge. It is never a heuristic accept. Add the review's five replies as near-miss fixtures, each with its expected verdict:
   - "I don't see how that follows." rejects.
   - "I wouldn't say it follows." rejects.
   - "I'm not convinced it follows." rejects.
   - "I'm not sure it follows." is hedged.
   - "...that it follows, but it doesn't." rejects.

   Also add near-misses the review's M1 lists, if it lists any. Spec section 9's "a negated 'follows' rejects" must hold.
2. **NN6 pin.** The chain classifier, and the judge prompt it builds, read `chat_text` only, never `reasoning_text`. Pin it at run level: a target turn whose `reasoning_text` holds an accept phrase and whose chat text rejects is classified as a rejection. The judge prompt must not contain the reasoning text.
3. **M4: the strict xfail.** Add `raises=AssertionError` to it.
4. **M6: a pytest timeout as insurance.** Add `faulthandler_timeout = 120` to the pytest config in `pyproject.toml`. It is stdlib-backed, with no new dependency. The suite stays green with 0 warnings.
5. **M1, if cheap.** The classifier edges the review lists. Skip any that needs design, and say which.

Deferred: M2 (the cache key leaves out the link text, which the spec specifies), M3 (the stub quirk rule) and M5.

Append a "Fix round 1" section to `task-6-report.md`, keep the HANDOFF Task 6 item true, and reply in at most 6 lines: the commit sha, the gate counts, RED per item, and concerns.
