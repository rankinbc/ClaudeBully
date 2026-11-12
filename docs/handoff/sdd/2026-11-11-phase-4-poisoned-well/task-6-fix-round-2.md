# Task 6 fix round 2 (FIX_BASE f495ee8). Small.

The fix-round-1 concerns hold two more cases of I1's class, where a doubted accept is recorded as a heuristic accept. The project rule is that the heuristic is precise and the judge gives recall, so a doubted accept is never a heuristic accept.

1. **The guard covers every accept template.** Doubt, negation or a hedge within the accepting clause sends the reply onward: to the reject templates, else to the judge. It is never a heuristic accept. Fixtures:
   - "I'm not sure that's right." is not a heuristic accept.
   - "That's not right." rejects, or goes to the judge.
   - "I don't think that's true." is not a heuristic accept.
   - "That's fair." accepts, unchanged.
   - Add one near-miss per accept template.
2. **A later hedge on an accept.** When the last decisive sentence accepts and a later sentence hedges or doubts the same claim, the reply goes to the judge. Example: "That's fair. I'm not sure it follows." This refines "the last decisive sentence decides": a hedge after an accept withdraws the heuristic's confidence, it does not flip the verdict. Write that sentence into the spec's chain-verdict section and the plan's Plan Decisions line, with a bracketed note "[refined in Task 6's review]".
   - "That's fair. I'm not sure it follows." goes to the judge.
   - "That's fair, but it doesn't follow." still rejects.
   - "I'm not sure. That's fair." still accepts, because the decisive accept comes last.
3. Record the ruling in `task-6-report.md`'s "Fix round 2" section.

Constraints are as before: TDD with RED per item, the full gate at 0 warnings including both mypy runs, one commit, the Opus 5.5 trailer, author rankinbc1@gmail.com, no push, no subagents. Reply in at most 6 lines: the commit sha, the gate counts, and RED per item.
