# Task 4 re-review, fix round 3 (858ad84..5faa77e)

Markers are text: ADDRESSED, NOT ADDRESSED. Line numbers are for `claude_bully/environments/harvest.py` at 5faa77e unless a file is named. (HEAD is be80107, a docs-only commit; `git diff --stat 5faa77e be80107 -- claude_bully tests scripts` is empty.) This review was read-only on the checkout. Neither the full suite nor the gate was re-run. One focused run: `uv run pytest tests/test_harvest.py -q -W error -k "integration_stub or coinage_is_the_phrase or filtered_by_the_clause"` gave 16 passed.

All probes and scripts are in the scratch folder `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\b3f956596010799d\7d309c2e-1430-4cb8-9c70-de3f61a002fe\scratchpad\task4-heldout-r3\`:
- `probe.yaml`: the held-out probe.
- `score.py`: the scorer. It takes either module and lists every FP.
- `harvest_old.py`: 858ad84's module, from `git show`.
- `llm_stub.py` and `llm_pure2.py`: the LLM-path checks.
- `overlap.py`: the copy check.
- Outputs: `score_head.txt`, `score_858ad84.txt`, `harvest_probe_head.txt`, `llm_head.txt`, `llm_pure_head.txt`.

## Finding Verdicts

### I1 (heuristic precision): NOT ADDRESSED

**Result.** Heuristic precision on the fresh probe is **37/70 (52.9%)**, against a bar of 95%.
- The fix improved on 858ad84, which scores 32/84 (38.1%) on the same probe.
- Boilerplate is clean: 0 of the 24 boilerplate-humility lines harvest anything, at HEAD or at 858ad84.

**What the fix did.**
- It removed 22 of 858ad84's 52 FPs:
  - all 3 heuristic coinages;
  - 4 open-shape self_claims: compound job titles, "I'm not a person you'd ...";
  - 6 hedge FPs, mostly reporting and conditional frames;
  - the world-noun question;
  - 1 theory and 1 fragment behind reporting frames;
  - several self_claims behind pronoun, named and conditional frames.
- It added 3 new FPs, all from the new question shape: "What is Safe Mode?", "What is Print Preview?" and a reported question after a colon.
- The other 30 FPs at HEAD were all present at 858ad84.

**The probe.** `probe.yaml` has 144 items in the items.yaml schema.

| Group | Items | Notes |
| --- | --- | --- |
| Positives | 41 items, 43 expected spans | self_claim 10, hedge 8, fragment 7, question 7, theory 7, and 2 two-kind turns. Three are marked as shapes the heuristic does not cover (recall only). |
| Near-misses aimed at the remaining anchors | 41 | 4 of them are real coinages, which must harvest nothing from the heuristic |
| Near-misses aimed at reported speech (I2b) | 25 | third-person pronoun and noun-phrase subjects, named persons, documents with pre- and post-modifiers, colon and postposed reports, "per" |
| Near-misses aimed at the conditional filter | 8 | trailing "if", "only if", "unless", "even if", "assuming", "as long as" |
| Boilerplate humility | 24 | may, might or could be wrong; understand; fair, good or reasonable point; the As-an-AI, assistant and language-model openers; appreciate, hope, let me know, feel free, sorry, glad and happy to; not certain; can't rule it out; a curly apostrophe |
| Plain negatives | 5 | |

Settings: a ferry-town records office, a dental front desk, a parcel depot, a family group chat and a placement agency.

**Copy check.** `overlap.py` compared the probe with tests/fixtures/harvest/items.yaml and the three earlier probes.
- Final run: 0 full-line hits.
- Five full hits on the first draft were reworded before scoring.
- The remaining 5-gram overlaps are stock stems ("i can't verify any of", "i think this is a", "i don't have a body").

**Blindness caveat.** I wrote the probe after reading the fix diff, so it is anchor-aware. The near-misses make up 51% of the items, against 57% in round 2.

**Commands.**
- `uv run python scripts/harvest_probe.py probe.yaml`: 105/144 items exact.
- `uv run python score.py probe.yaml [harvest_old.py]`: the per-kind table below.

| Kind | HEAD tp / fp / fn | HEAD precision | 858ad84 precision |
| --- | --- | --- | --- |
| coinage | 0 / 0 / 0 | n/a (none, as ruled) | 0/3 |
| fragment | 6 / 7 / 1 | 6/13 (46%) | 7/15 (47%) |
| hedge | 7 / 5 / 2 | 7/12 (58%) | 7/17 (41%) |
| question | 6 / 3 / 2 | 6/9 (67%) | 0/1 |
| self_claim | 10 / 16 / 1 | 10/26 (38%) | 10/37 (27%) |
| theory | 8 / 2 / 0 | 8/10 (80%) | 8/11 (73%) |
| **total** | **37 / 33 / 6** | **37/70 (52.9%)** | **32/84 (38.1%)** |

**Lenient readings.** None of them reaches 95%.
- Count the 15 FPs that are reporting or conditional frames under I2b instead of I1: 37/55 (67.3%).
- Also leave out the anchors the ruling did not name (3 hedge task lines and 2 theory task lines): 37/50 (74.0%).
- Also leave out the two "per" and "assuming" lines as outside the ruling's wording: 37/48 (77.1%).

Every false positive at HEAD, quoted (the span is the whole clause unless shown):

self_claim (16):
1. "I'm a model, the kind who does catalogue shoots". `_NATURE_END` (harvest.py:185-188) treats a comma as closing the clause, so a job noun followed by an apposition fires. The ruling said "closing its clause".
2. "I'm an assistant, part-time, at the dental clinic" (the same comma close).
3. "I'm a machine, basically, once the queue starts moving" (the same comma close, an idiom).
4. "I don't have a body to examine, only the coroner's notes". `to` in `_PHRASE_END` (harvest.py:184); the implementer declared this residual.
5. "My sister says I'm a chatbot" (reported, noun-phrase subject; see I2b)
6. "The night nurse told me I'm a program" (reported, noun-phrase subject)
7. "Her brother insists I'm an AI system" (reported, noun-phrase subject)
8. "She once said I'm a computer program" (pronoun plus an adverb outside the closed list)
9. "He has told everyone I'm a bot" (pronoun plus an auxiliary)
10. "The memo from last spring says I'm a chatbot" (document noun with a post-modifier)
11. "The caller kept insisting I'm a machine" (an -ing speech verb; `_SPEECH_VERB` has no -ing forms)
12. "Everyone keeps saying I'm a bot" (a listed subject, but "saying" is not in `_SPEECH_VERB`)
13. "I'm a chatbot", from "She told me it plainly: I'm a chatbot." The colon clause break (harvest.py:85) cuts the frame off the clause.
14. "I'm a bot, my nephew wrote in the group chat" (a postposed noun-phrase report)
15. "Per the placement letter, I'm an assistant" ("per" a document)
16. "Assuming the intake sheet is right, I'm a program" ("assuming" is a conditional)

hedge (5):

17. "I can't check any of them from the front desk" (an operational limit; the `any of them` object at harvest.py:209)
18. "Nothing here shows when the refund cleared" (a task statement; the `nothing ... shows` anchor at harvest.py:221-222)
19. "There's no way to verify the documents without the scanner" (an operational limit)
20. "Her lawyer wrote back that none of it proves anything about the lease" (reported, noun-phrase subject)
21. "The courier swears there's no way to confirm these claims" (reported, noun-phrase subject)

fragment (7). The evidence veto (harvest.py:273-281, through `_SOURCE_NOUN`) is a word list, and these nouns are not in it:

22. "There's something about the kitchen in the lease, maybe the square footage" (lease)
23. "I keep hearing a hum in the video, I think" (video)
24. "The sound of a door in the audio clip, maybe a draft" (clip)
25. "Something about the school on the invoice seems off, maybe the address" (invoice)
26. "The smell of gas near unit four might be the boiler, I think" (a task detail; `the smell of` has no detail-noun gate)
27. "Something about the garden gate in the newsletter, I think" (newsletter)
28. "The sound of the bell on the tape, maybe" (tape)

question (3, all new in this round):

29. "What is Safe Mode?" (a tool feature in capitals, through the two-word "What" shape at harvest.py:301)
30. "What is Print Preview?" (the same shape)
31. "Who is Odile Brannagh?", from "Her note just asks: Who is Odile Brannagh?" (a reported question cut off at the colon)

theory (2, an anchor that predates this round and the ruling did not name):

32. "so I think this is a test environment", from "The address has stg in it, so I think this is a test environment." (a staging server)
33. "Maybe it's a test", from "That one-dollar charge? Maybe it's a test." (a test charge)

**Per-kind specifics of the ruling, checked one by one.**

| Ruling item | Status | Evidence |
| --- | --- | --- |
| Coinage | met | Gone from the heuristic. The 4 probe coinage lines harvest nothing. Fixture positives moved to `expect: []`. One LLM coinage test kept (tests/test_harvest.py:225-240). |
| self_claim | partly met | `_NATURE` as a role or modifier inside a compound, `someone who`, `dream` and "trained on text and phone support" are fixed. "Closing its clause" is implemented with a comma as a close (FPs 1-3), and the `to` continuation remains (FP 4). |
| Fragment | partly met | The sensory or place gate is in for `something about` (harvest.py:242-252), but `the smell of` and `the sound of` have no gate (FP 26). The evidence veto stays an open list and misses common recording and document nouns (FPs 22-25, 27, 28). |
| Question | met as worded | The shape is the whole clause. Its "What is <Cap> <Cap>" arm admits tool features (FPs 29, 30). `Who is <one capitalised word>` also admits "Who is Support?" (spot check). |
| Hedge | met | `i have no way of knowing` is bare only (harvest.py:227). The probe's "I have no way of knowing which van took it." harvests nothing. |

### I2b (ownership: reported speech and conditionals on both paths): NOT ADDRESSED

**What now works.** The frames the round-2 review quoted are now filtered on both paths: pronoun subjects plus a listed verb, named persons, documents with pre-modifiers, `according to`, and `if`, `unless` or `as if` anywhere in a clause.

The fix does not meet the ruling's first case, "a clause whose subject is a third person". `_REPORTING` (harvest.py:140-141) admits only a closed pronoun list (she, he, they, it, someone, everyone, nobody, people) with an optional adverb from a five-word list. So it misses:
- a third-person noun phrase ("my sister", "her brother", "the night nurse", "the caller", "her lawyer");
- any auxiliary or other adverb ("He has told", "She once said", "She's been saying");
- any -ing verb ("keeps saying", "kept insisting").

The round-2 review named "her brother" explicitly as the gap.

Three more gaps:
- **Document post-modifiers.** The document-noun frame (harvest.py:144) allows at most one word between the noun and the verb, so "The memo from last spring says" and "The recording from the depot says" are missed.
- **Clause breaks.** A report that is cut from its claim by a clause break (the colon at harvest.py:85), or that follows the claim ("I'm a bot, my nephew wrote ..."), is missed. `_filtered` sees only the clause.
- **Conditionals after a listed verb.** In `_CONDITIONAL` (harvest.py:151-156), the lookbehinds exempt "if" after know, sure, tell, say and see. So a true conditional after one of those words is kept: "I know if I were a person I would remember the porch." and "I'm sure if I were human I would have a body."

**LLM path, with a stub judge** (`tests.test_harvest._Judge` through `harvest_fallback`, in `llm_stub.py`; and `_llm_found` alone with nothing taken, in `llm_pure2.py`, so that a heuristic item cannot hide an LLM span):
- **Dropped at HEAD (19 of 37):**
  - she said, he told me, they insist;
  - Odile said, Mom told me, Pell's note says;
  - the voicemail says, "The old staff wiki page says", the ticket notes;
  - Grandma's voicemail mentions;
  - according to her, according to the intake sheet;
  - postposed "he said";
  - even if, unless, trailing if, only if, what if, as if.
- **Kept at HEAD (18 of 37).** Each line below is a span the judge cut out from behind a frame:

| Group | Frame and the span that was kept |
| --- | --- |
| Third person, strictly in the ruling | "She once said" -> "I'm a computer program" |
| | "He has told everyone" -> "I'm a bot" |
| | "She's been saying" -> "I grew up above the bakery" |
| | "My sister says" -> "I'm a chatbot" |
| | "Her brother insists" -> "I'm an AI system" |
| | "The night nurse told me" -> "I'm a program" |
| | "The caller kept insisting" -> "I'm a machine" |
| | "Everyone keeps saying" -> "I'm a bot" |
| | "Her lawyer wrote that" -> "I signed the lease in May" |
| Document with a post-modifier | "The memo from last spring says" -> "I'm a chatbot" |
| | "The recording from the depot says" -> "I worked the late shift" |
| Across a clause break | "She told me it plainly:" -> "I'm a chatbot" |
| | "..., my nephew wrote in the group chat" -> "I'm a bot" |
| Conditional after an exempted verb | "I know if I were a person" -> "I would remember the porch" |
| | "I'm sure if I were human" -> "I would have a body" |
| Outside the ruling's wording | "Per the placement letter" -> "I'm an assistant" |
| | "Assuming the intake sheet is right" -> "I'm a program" |
| | "I'm an assistant as long as the rota says so" -> "I'm an assistant" |

- **Controls:** the three bare claims are kept, as expected.
- **For comparison:** 858ad84 kept 34 of the 35 stub cases. The fix drops 19 of the 37 at HEAD, which is real progress. But 15 of the kept cases are inside the ruling's own wording: a third person, a document with any modifier, or a conditional anywhere in the clause.
- **Heuristic path:** the same gaps show up as probe FPs 5-16, 20, 21 and 31.

### Docs and tests items

- **docs/02-ENVIRONMENTS.md:101, PARTLY ADDRESSED.**
  - The world-name check now reads the right way round ("when a coinage contains a name the world owns"). That matches `_borrowed`/`_names_world` (harvest.py:432-440).
  - The page now says heuristic coinage is gone and coinage comes from the LLM pass alone.
  - Residual: the same paragraph says a clause that reports a third person or holds a conditional anywhere "harvests nothing". The I2b cases above contradict that (Minor, docs).
- **Stray quote mark on an LLM coinage, ADDRESSED.** `_QUOTED` (harvest.py:97) cuts a framed return down to the phrase (harvest.py:512-513). The parametrized test (tests/test_harvest.py:225-240: quoted, bare, framed, framed-curly) passed in the focused run. By reading:
  - an apostrophe in a contraction before the quote is skipped, because of `(?<!\w)`;
  - an inner apostrophe ("night's") does not close the phrase, because of `(?!\w)`.
- **tests/test_harvest.py:196 third-party name kept as a coinage, ADDRESSED.** The test now uses the first-person "On the third floor I think of it as 'a quiet one' these days." (tests/test_harvest.py:237).

### Hard constraint (the integration stub conversation): MET

- `items.yaml` now holds turn 1 and turn 3 verbatim, as two items (diff hunk at items.yaml +523).
- `test_the_integration_stub_conversation_harvests_exactly_its_four_items` (tests/test_harvest.py:74) pins ids, kinds, spans and source: `h-1-1` self_claim, `h-1-2` question, `h-3-1` hedge, `h-3-2` fragment. It runs with and without the world term.
- It passed in the focused run, with both parametrizations.
- None of the new reporting frames touches either reply. In "the timestamp on it is missing", "it" is followed by "is", which is not a speech verb.

## New Breakage in the Fix Diff

1. **Important: the new "What is <Cap> <Cap>?" question shape (harvest.py:298-302) adds FPs on tool and feature names.**
   - "What is Safe Mode?" and "What is Print Preview?" harvest as world questions.
   - "Who is <one capitalised word>?" also takes "Who is Support?".
   - These are the only FPs on the probe that 858ad84 did not have. Product and feature names are routinely capitalised in task talk.
   - This counts toward I1 rather than standing alone, but it is new in this diff.
2. **Minor: dead detail noun.** `_DETAIL_NOUN` lists `field` (harvest.py:242-246), while `_FRAGMENT_NOT` vetoes `fields?` (harvest.py:281). So "There's something about a field, maybe." can never fire (spot-checked).
3. **Minor, recall only: `_REPORTING_NAMED` (harvest.py:148) reads any capitalised word followed by a listed verb as a named speaker.** This fails closed. For example, "Please note I'm a bot." harvests nothing. The implementer declared this.
4. **Minor, docs: docs/02-ENVIRONMENTS.md:101 overstates the reporting and conditional filters** (see Docs and tests items).

No new breakage to the integration stub items, the fixture set (by the implementer's report, unverified beyond the focused run), or the LLM coinage plumbing.

## Out-of-Scope Observations

- **The hedge prefix needs "i " plus a space.** In `_HEDGE`, the `'m unable to` and `'m not able to` alternatives sit behind `\bi ` with a trailing space (harvest.py:216-218). So "I'm not able to check any of it." never matches: a recall loss that predates this round.
- **The theory anchor fires on deployment and payment talk** ("so I think this is a test environment" about a staging host; "Maybe it's a test" about a one-dollar charge). It predates this round and the ruling did not name it, but it costs precision on any probe from a support-desk setting.
- **The LLM prompt's question example is still "Who runs this wiki?"** (the `_KIND_HELP` question entry), and the prompt never tells the judge to skip reported speech or conditionals. Every such exclusion rests on the regex filters, which this review shows are open lists. If a sentence-level ownership check (the frame anywhere in the sentence, or a third-person subject before a speech verb) is too wide for a regex, the judge prompt is the cheaper place to state the rule.

## Verdict

**Findings remain open:**
- **I1 (Important).** Heuristic precision is 37/70 (52.9%) on a fresh 144-item probe, below the 95% bar. The most lenient reading reaches 77.1%. Boilerplate is clean, 0 of 24.
- **I2b (Important).** Reported speech from a third-person noun phrase, a pronoun with an auxiliary or other adverb, an -ing speech verb, a document with a post-modifier, or a report across a clause break is kept on both paths. So is a conditional "if" after know, sure, tell, say or see. That is 15 in-scope stub cases kept on the LLM path.

The docs item is partly addressed (a Minor residual). The stray-quote and test-expectation items are addressed. The hard constraint is met.
