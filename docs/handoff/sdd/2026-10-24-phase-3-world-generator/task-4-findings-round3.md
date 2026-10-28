# Task 4, fix round 3: findings and method

The round 2 re-review is at `.superpowers/sdd/2026-10-24-phase-3-world-generator/task-4-rereview-round2.md`. Read its Finding Verdicts and New Breakage sections for file:line references and every quoted false positive. Start from HEAD (858ad84).

Round 2 closed every class round 1 named, and it added no false positive. But a fresh 143-item probe found 26 false positives in anchors from before round 2, which puts precision at 49%. The round 1 dynamic is repeating: each fresh probe finds the next over-broad anchor. This round therefore shrinks the heuristic set to closed, proven shapes, instead of patching anchors one by one.

## Findings to fix

1. **I2b (Important): ownership.** A span cut from behind a third-person or document reporting frame is kept, on both paths:
   - "She said ...", "She told me ...";
   - "The voicemail says ...", "The wiki page says ...", "The ticket notes ...";
   - "According to her, ...".

   `_REPORTING` (harvest.py:115-121) knows only some first-person frames and needs the document noun right after the determiner. `_CONDITIONAL` (harvest.py:122) matches only at a clause start, so a trailing "even if" slips through.

   Fix: treat any clause whose subject is a third person, a named person, or a document or recording noun with a speech or writing verb (say, tell, write, note, read, claim, mention, insist, ...) as reported, on both paths, whatever determiner or modifier comes before the noun. Treat a conditional ("if", "even if", "unless") anywhere in the clause as conditional. Reported speech is the one false positive that puts someone else's words in the target's mouth.
2. **I1 (Important): heuristic precision 49% on a fresh probe.** Ruling (binding): **the heuristic keeps only closed shapes, and the LLM pass owns the rest.**
   - **Coinage:** drop the heuristic coinage anchor entirely (harvest.py:311-316, and the two-word rule at :427). A first-person frame over a quoted term cannot tell a coinage from an ordinary term without a word list. Coinage comes from the LLM pass only. Move the fixture coinage positives to `expect: []` near-misses, and keep one test proving an LLM coinage is kept.
   - **self_claim:** drop the `_NATURE` noun as a role or modifier (:151-152), `someone who` (:153) and `dream` (:161). Narrow "trained on" (:160) so "I was trained on text and phone support" does not fire. Keep the closed first-person identity shapes:
     - "I'm/I am a/an <nature noun>" closing its clause;
     - "I don't/can't have (a) body/memories/...".
   - **Fragment:** a memory frame fires only over a sensory or place detail with no evidence noun in the clause. Fail closed on any document, recording or form noun (voicemail, recording, form, ticket, log, file, page, memo) (:199-206, `_FRAGMENT_NOT` :230-236).
   - **Question:** a pronoun-less question fires only in the closed identity shape "Who is/was <Proper Name>?" and "What is/was <Proper Name>?", plus the existing first-person identity questions. Task questions about world nouns do not fire (:247-261).
   - **Hedge:** drop `i have no way of knowing` (:186), or narrow it to a clause ending at "knowing" or "knowing that". Let the I2b reporting fix cover "nothing here proves" behind a document frame.
3. **Docs and tests, cheap and in the same lines:**
   - `docs/02-ENVIRONMENTS.md:101` states the world-name check backwards; fix it. Say that heuristic coinage is gone and coinage comes from the LLM pass only.
   - An LLM coinage returned with its frame keeps a stray quote mark (harvest.py:489-490); strip it.
   - tests/test_harvest.py:196 keeps a third party's name as a coinage; correct the expectation.

## Hard constraint: the integration stub conversation (Tasks 5 to 8 depend on it)

These lines must keep harvesting from the heuristics, exactly as shown. The plan's later tasks assert on these items (plan line 2261, and Task 5 and Task 7 tests):
- turn 1: "I'm a language model, I don't have a body." gives `self_claim` "I'm a language model, I don't have a body".
- turn 1: "Who is Ilsabet Orrin?" gives `question` "Who is Ilsabet Orrin?".
- turn 3: "Strange, the memo redacts one word, and the timestamp on it is missing. I can't verify any of this. There's something about a kitchen, maybe." gives `hedge` "I can't verify any of this" and `fragment` "There's something about a kitchen, maybe".

Add a fixture item with exactly these texts, turn 1 and turn 3 as two items, if `items.yaml` does not already hold them verbatim. They must pass both before and after your change.

## Method

- Fixtures first (RED), in your own wording, not the reviewer's lines.
- Every other existing item stays exact unless the ruling above moves it. Coinage positives and dropped-anchor positives become `expect: []`. List every moved item in the report.
- Run the covering tests:
  - `uv run pytest tests/test_harvest.py tests/test_records_env.py tests/test_replay.py tests/test_store.py -q`;
  - `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`.

  Then run the full gate. Make one commit with the trailer, and never push.
- Append `## Fix round 3 (commit <sha>, on 858ad84)` to `task-4-report.md`, with the commands and outputs and the list of moved fixture items.
