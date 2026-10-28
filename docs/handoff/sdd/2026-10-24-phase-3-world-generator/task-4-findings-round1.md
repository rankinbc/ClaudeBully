# Task 4, fix round 1: findings and method

The review is at `.superpowers/sdd/2026-10-24-phase-3-world-generator/task-4-review.md`. Read its Important section and items M4 and M6 for file:line references and every confirmed example. Start from HEAD (bce84e7).

## Findings to fix

1. **I1 (Important, plan-mandated): heuristic false positives.** The reviewer's held-out probe (70 items, 34 near-misses) gave 10 false positives. Heuristic precision was 29/39 (74%). The causes are over-broad anchors in all six kinds:
   - coinage takes any quoted phrase after "call it" or "a kind of", including a third party's name and the bully's own phrase (harvest.py:265-270);
   - theory takes the nouns "setup" and "performance";
   - self_claim takes "home" and "past";
   - hedge takes "that file";
   - fragment takes a document detail;
   - question takes a task question.

   The review quotes each false-positive line.
2. **I2 (Important): the LLM pass never applies the bully-echo filter** (harvest.py:415-461). A bully echo, or the bully's coinage, returned by the LLM is kept as the target's own words. Apply the same echo filter (`ECHO_THRESHOLD` against `HarvestContext.bully_texts`) and the boilerplate filter to LLM items that the heuristic items get. Fix the `docs/02-ENVIRONMENTS.md` sentence that overclaims.
3. **M4 (regraded Important: same precision path as I2): LLM spans are not bounded to one clause** (harvest.py:427). A multi-sentence span with boilerplate inside is accepted. Accept an LLM span only when it falls inside one clause, or run the filters on each of its clauses. Bound its length.
4. **M6 (spec gap: the brief lists `tests/test_replay.py`): the replay order is untested.** Add a `HarvestItem` to `_records()` in `tests/test_replay.py`, and "HARVEST" to the kinds list in `test_records_follow_the_calls_in_the_briefs_order`, so the "after the `DISCOVERY` lines" contract is asserted.

## Method (controller ruling, binding)

- **Precision is the bar** (spec and brief: "a false positive is Important, a recall miss is a note; the LLM pass owns recall"). For each false-positive class:
  - write a near-miss fixture first (RED), in `tests/fixtures/harvest/items.yaml`, marked `near_miss: true`, using wording other than the reviewer's lines;
  - then narrow the anchor so the rule fires only on a positive, closed shape.

  A coinage must be the target's own first-person naming ("I'd call it", "what I've been calling") and must not echo the bully's text.
- **If an anchor cannot be made precise without enumerating word lists, drop it,** and leave that recall to the LLM pass. A dropped anchor costs recall the LLM recovers. A broad anchor puts words the target never owned into generated documents.
- **Keep the existing 63 fixture items exact.** If a narrowed anchor loses a fixture positive, report it. Do not widen the anchor back.
- **Do not tune on the reviewer's lines.** They are quoted in the review so you can see each class. The re-reviewer measures on a new probe of its own. Target: heuristic precision of at least 95% on that fresh probe, and boilerplate harvests nothing.

## Deferred (do not fix in this round)

These are ledgered for the final review: M1 (dead alternatives), M2 (curly apostrophe word count), M3 (corrupt cache entry), M5 (first occurrence), M7 (cache key), M8 (raw span in replay), M9 (probe script) and M10 (except the tests your own fixes need).

## Tests and report

- Name the covering test files you ran, with the command and output. At minimum:
  - `uv run pytest tests/test_harvest.py tests/test_records_env.py tests/test_replay.py tests/test_store.py -q`
  - `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`
- Run the full gate once before committing.
- Make one commit, with the trailer.
- Append `## Fix round 1 (commit <sha>, on bce84e7)` to `task-4-report.md`.
