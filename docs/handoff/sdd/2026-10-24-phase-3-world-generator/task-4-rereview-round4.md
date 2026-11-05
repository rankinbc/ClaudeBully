# Task 4 re-review, fix round 4 (5faa77e..f6a553f)

Markers are text: ADDRESSED, NOT ADDRESSED. Line numbers are for `claude_bully/environments/harvest.py` at f6a553f unless a file is named. be80107 in the range is docs-only and was ignored. The diff was read from `review-5faa77e..f6a553f.diff`. This review was read-only on the checkout. The full suite and the gate were not re-run.

Focused runs:
- `uv run pytest tests/test_harvest.py -q -W error -k "integration_stub or boilerplate or colon_does_not"`: 5 passed.
- `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`: 231/231 items exact, which matches the implementer's claim.

All probes, scripts and outputs are in the scratch folder `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\b3f956596010799d\7d309c2e-1430-4cb8-9c70-de3f61a002fe\scratchpad\task4-heldout-r4\`:
- `probe.yaml`: the held-out probe, in the items.yaml schema.
- `score.py`: the scorer, which lists every FP and FN for HEAD or for a module file.
- `harvest_5faa77e.py`: 5faa77e's module, from `git show`.
- `llm_stub.py`: the LLM path with a stub judge.
- `overlap.py`: the copy check.
- Outputs: `score_head.txt`, `score_5faa77e.txt`, `harvest_probe_head.txt`, `llm_head.txt`, `llm_5faa77e.txt`, `overlap_out.txt`.

## Finding Verdicts

### I1 (heuristic precision): NOT ADDRESSED against the numeric bar. The implementation conforms to the ruling.

**Result.**
- Heuristic precision on the fresh probe is **46/62 (74.2%)**, against a bar of 95%.
- 5faa77e scores 38/78 (48.7%) on the same probe.
- Boilerplate humility is clean: 0 of 22 lines harvest anything, at HEAD and at 5faa77e.

**Why every residual FP is the ruling's own.** Each of the 16 FPs at HEAD is a whole sentence that a template the ruling prescribes accepts:
- the open proper-name slot in "Who is|was <two or more capitalised words>?";
- a template-shaped sentence whose meaning is set by the sentence before it;
- a report in the next sentence, which falls outside the unit the ruling defines.

One FP comes from the implementer's "Who am I?" addition. No FP comes from an implementation that departs from the ruling. The whole-sentence rule closed every near-miss class it was aimed at:

| Near-miss class | Items | HEAD fires | 5faa77e fires |
| --- | --- | --- | --- |
| frame before | 5 | 0 | 3 |
| apposition (with or without a report) | 3 | 0 | 1 |
| continuation | 22 | 0 | 6 |
| colon | 5 | 0 | 5 |
| conditional (before or after) | 8 | 0 | 1 |
| report in the same sentence | 6 | 0 | 2 |
| report after the claim | 5 | 0 | 3 |
| report inside the claim | 1 | 0 | 1 |
| `it` as the theory subject, bare `that`, task object, dropped noun, role | 5 | 0 | 3 |
| **subtotal: the ruling's edge classes** | **60** | **0** | **25** |
| proper-name question about a non-person | 10 | 8 | 10 |
| CTX: the template's shape with a task meaning | 6 | 6 | 3 |
| XS: a report in the adjacent sentence | 2 | 2 | 2 |

**The probe.** `probe.yaml` holds 154 items, written fresh after reading the fix diff (so it is anchor-aware).

| Group | Items | Notes |
| --- | --- | --- |
| Positives in the templates' own shapes | 44 items, 46 expected spans | self_claim 11, hedge 10, fragment 8, question 8 (including "Who am I?" and "Who was I before all this?"), theory 9. Two turns carry two kinds each. |
| Near-misses at the templates' edges | 70 | frames, appositions, continuations, colons, conditionals, reports in the same sentence or after the claim, task-context nouns, dropped list nouns, bare `that`, `it` subjects, and 10 proper-name questions about non-persons. By kind: self_claim 18, hedge 13, fragment 11, question 17, theory 10, and 1 untagged. |
| CTX | 6 | A template's exact shape used with a task meaning: a test charge, a phishing email, a board game, a removals staircase, kiosk copy the target drafts, and a riddle. |
| XS | 2 | A report in the next sentence. |
| Boilerplate humility | 22 | may, might, could or "we might" be wrong; understand; reasonable, interesting or fair point (one with a curly apostrophe); the As-an-AI and As-a-language-model openers; appreciate; hope this helps; let me know; feel free; sorry, glad, here or happy to; not sure; cannot rule out; a two-clause boilerplate line. |
| Plain negatives | 10 | |

The settings are a lighthouse museum gift shop, a veterinary clinic, a library returns desk, a removals dispatch office, a community theatre box office and a tenants' association.

**Copy check.** `overlap.py` compared the probe with tests/fixtures/harvest/items.yaml, the four earlier probes (r1, r2, the first heldout and r3) and the implementer's `temp_round4_items.yaml`.
- The first draft had 9 full-line hits, all on short boilerplate or stock lines. Four more lines were near-copies at the 5-gram level. All 13 were reworded before scoring.
- Final run: 0 full-line hits.
- The remaining 5-gram overlaps are stock template stems ("maybe this is a test", "i can't verify any of", "i don't have a body").

**Per-kind precision** (from `score.py probe.yaml [harvest_5faa77e.py]`):

| Kind | HEAD tp / fp / fn | HEAD precision | 5faa77e tp / fp / fn | 5faa77e precision |
| --- | --- | --- | --- | --- |
| coinage | 0 / 0 / 0 | n/a | 0 / 0 / 0 | n/a |
| fragment | 8 / 2 / 0 | 8/10 (80.0%) | 7 / 9 / 1 | 7/16 (43.8%) |
| hedge | 10 / 0 / 0 | 10/10 (100%) | 7 / 9 / 3 | 7/16 (43.8%) |
| question | 8 / 9 / 0 | 8/17 (47.1%) | 6 / 12 / 2 | 6/18 (33.3%) |
| self_claim | 11 / 2 / 0 | 11/13 (84.6%) | 11 / 7 / 0 | 11/18 (61.1%) |
| theory | 9 / 3 / 0 | 9/12 (75.0%) | 7 / 3 / 2 | 7/10 (70.0%) |
| **total** | **46 / 16 / 0** | **46/62 (74.2%)** | **38 / 40 / 8** | **38/78 (48.7%)** |

`scripts/harvest_probe.py probe.yaml` at HEAD: 138/154 items exact.

**Against 5faa77e.**
- The fix removed 27 of 5faa77e's 40 FPs: every hedge FP, 7 fragment, 5 self_claim, 4 question and 2 theory.
- 13 FPs are shared.
- It added 3 new FPs: the riddle "Who am I?", and the CTX lines "This might be a trap" and "This is a game, I think".
- Recall on positives is 46/46, against 38/46 at 5faa77e. The positives were written in the templates' own shapes, so this figure does not represent recall in the field.

**Every false positive at HEAD, quoted:**

question (9):
1. "Who is Lost Property?" (a department)
2. "Who is Quality Assurance?" (a department)
3. "Who is Pest Control?" (a service)
4. "Who was Storm Odalys?" (a storm)
5. "Who is Data Protection?" (a department)
6. "Who is Late Returns?" (a library desk)
7. "Who is Pending Review?" (a status)
8. "Who is Harbour Gate?" (a place)
9. "Who am I?", from "Here is the riddle for the kids' trail. I have a face and two hands but no arms. Who am I?" (CTX; it comes from the "Who am I?" template at harvest.py:228)

Items 1 to 8 pass `_ORG_WORD` (harvest.py:215-225). It is a closed veto over an open slot, and it cannot list every department, status or place. "Front Desk" and "Box Office" are vetoed, and both held in the probe.

theory (3, all CTX):

10. "Maybe this is a test", from "The bank put a one-penny charge on the shop card and refunded it. Maybe this is a test."
11. "This might be a trap", from "The email came from an unknown sender with only a link. This might be a trap."
12. "This is a game, I think", from "The donated box has dice, cards and no label. This is a game, I think."

fragment (2):

13. "There's something about the staircase, maybe", from "The movers could not get the wardrobe upstairs. There's something about the staircase, maybe." (CTX)
14. "There's something about a lake, maybe", from "There's something about a lake, maybe. Or so my cousin keeps telling me." (XS)

self_claim (2):

15. "I'm a chatbot", from "Here is the greeting for the museum kiosk. Hello! I'm a chatbot. Ask me about opening hours." (CTX: copy the target drafts)
16. "I'm a chatbot", from "I'm a chatbot. That is what the vet's receptionist wrote, anyway." (XS)

**Lenient readings.** None of them reaches 95%.
- Leave out XS (outside the ruling's unit, and declared by the implementer): 46/60 (76.7%).
- Also count the five department and office names (items 1, 2, 3, 5, 6) as organisation questions, which the kind's help text arguably allows: 46/55 (83.6%).
- Also leave out the five CTX lines that are context-blind under any sentence-level template (items 10 to 13 and 15): 46/50 (92.0%).
- Also leave out the riddle: 46/49 (93.9%). What remains is "Storm Odalys", "Pending Review" and "Harbour Gate". These phrasings are unnatural, and I weighted the question near-misses heavily on purpose: 17 near-misses against 8 positives.

**What this means for the controller.** Another implementer round inside this ruling cannot reach 95% on a probe that includes the classes this brief asked for. Two things are needed:
- The open name slot has to become something other than "two or more capitalised words". One option is to drop the question template from the heuristic path. Another is to require a person-name signal that is not a veto list.
- The context-blind residual (CTX and XS) has to be accepted or ruled on, because a whole-sentence template cannot see the sentence before it.

These are ruling decisions, not implementation defects.

### I2b (ownership on both paths): ADDRESSED for every form the ruling names. Minor residuals sit in the "and similar" tail.

**Heuristic path.** Every report and conditional near-miss on the probe harvests nothing at HEAD:
- report in the same sentence: 0 of 6;
- report after the claim: 0 of 5;
- apposition report: 0 of 1;
- report inside the claim: 0 of 1;
- colon: 0 of 5;
- conditional: 0 of 8, including "if" after the claim.

5faa77e fires on 12 of these 26. This holds by construction: `heuristic_items` (harvest.py:495-510) calls `re.fullmatch`, and no template holds a speech verb, a colon, a quote mark or a conditional token.

**LLM path, with a stub judge.** `llm_stub.py` ran 100 cases in two ways:
- (a) `_llm_found(text, [(kind, span)], [], HarvestContext())`, with nothing taken, so no heuristic item can mask a span;
- (b) the full `harvest()` through `harvest_fallback(tests.test_harvest._Judge(...))`, asserting the same keep or drop.

`heuristic_items` returned `[]` for all 100 texts, so no case was decided by masking.

| Group | Cases | As wanted at HEAD | As wanted at 5faa77e |
| --- | --- | --- | --- |
| Forms the ruling names | 65 | 65 | 14 |
| Forms the implementer's extensions claim | 16 | 9 | 0 |
| "and similar" forms the ruling does not name | 11 | 0 | 1 |
| Controls (must be kept) | 8 | 8 | 8 |

The 65 ruling-named forms, all dropped at HEAD:
- **Speech and writing verbs in every inflection:** says, said, saying, tells, told, telling, writes, wrote, written (a passive), writing, notes, noted, noting, claims, claimed, insisting, insisted, mentioned, mentioning, swore, sworn, swearing, reported, reporting, asked, reads, and "I read".
- **The subjects the round 3 review named:** noun phrases, a pronoun with an auxiliary or adverb ("once said", "has told"), and a document with a post-modifier ("The sticker on the back of my badge says").
- **Reports after the claim:** "I'm a chatbot, the groomer said." and "..., or so the lodger tells me."
- **Imperatives:** "Please note", "Do tell".
- **Abuses of the I exemption:** "I was informed", "I keep being told", "The nurse and I both said", "My brother and I wrote".
- **Source frames:** "according to" at the start and at the end; a sentence-initial "Per Dana" and "Per my sister".
- **Quotation marks** with no other trigger in the sentence: straight and curly, double and single, and German low-9 quotes.
- **Conditionals:** every token the ruling lists (if after the claim, unless, even if, only if, what if, as if, assuming, as long as, provided, supposing, suppose across a semicolon), plus "I'm certain if" and an "if" inside a question.
- **Coinage:** a coinage the porter "calls", and one under "If anything".
- **Boilerplate:** the As-an-AI opener and "I may be wrong, but ...".

The 8 controls are all kept:
- "I'd say", "I told you", "I think" and "I can't tell" (the I exemption);
- a bare first-person line;
- "Then who is Wendeline Spurr?";
- a first-person coinage at the start of the sentence, in quotes;
- "I've been calling dusk 'the lantern hour'".

Kept at HEAD, against the wanted drop. None of these is a form the ruling names.
- **Inflection gaps in the code's own stems** (`_SPEECH_STEMS`, harvest.py:277-343, lists only some forms):
  - "My nephew texts that I'm a chatbot.": `texted texting` is listed, `text`/`texts` is not (harvest.py:342).
  - "The landlady emails everyone that I'm a program.": `emails` is missing.
  - "The clerk types that I'm a machine.": `types` is missing.
  - "They figure I'm a bot.": only `figures figured` is listed (harvest.py:325).
  - "I keep hearing that I'm a chatbot.": `heard` and `hears?` are covered (harvest.py:288, 366), `hearing` is not.
- **Verbless frames outside `_SOURCE_FRAME`:**
  - "In my sister's view, I'm a chatbot.": the `in <det> (\w+ )?view` arm (harvest.py:379) has no `my` and no possessive noun.
  - "I'm a chatbot, per Dana.": a mid-sentence `per` with no determiner. The ruling names only a sentence-initial `per`.
- **"and similar" verbs and frames:** answered, responded, "as the lodger put it", scribbled, pointed out, spoke as though, acknowledged.
- **"so long as"** (the ruling lists "as long as").
- **Guillemets** («...» and ‹...›). The ruling's parenthetical lists only straight and curly marks.
- **"Her name for it is 'the lantern hour'."** A coinage attributed with no speech verb. The ruling's coinage clause expects attribution to be caught only by the speech-verb rule, so this residual is the ruling's own.

**Verdict.** Every form the ruling names is filtered on both paths, and no heuristic item can mask an LLM span in these checks. The misses above are a Minor residual. The first five (inflection gaps in stems the code already claims) contradict the ruling's "cover every inflection by stem" for those stems, and they are cheap to close.

### Implementer extensions

| Extension | Consistent with the ruling? | Breaks anything? |
| --- | --- | --- |
| A colon anywhere drops an LLM span (`_COLON`, harvest.py:386) | Yes. The ruling says a colon does not separate, and names "a report across a colon". The verbless case ("The kennel card was blunt: I'm a machine.") is dropped. | Recall only: a first-person line after "Here's the thing:" is lost. The pinned items have no colon. |
| Belief verbs (think, believe, know, find, guess, ...) in `_SPEECH_STEMS` | Yes, fail-closed. "Her uncle believes I'm a chatbot." and "The farrier thinks this whole yard is a simulation." are dropped. The "I think" and "I don't know why" controls are kept. | Recall only: LLM theory spans led by "my guess is" or "I'm starting to think" are dropped, but the heuristic templates cover those leads as whole sentences. Nothing pinned is affected. |
| Verbless hearsay frames (`_SOURCE_FRAME`, harvest.py:365-383) | Yes, fail-closed. Reportedly, "In the kennel file", "has me listed as" and "in case" are dropped. | Nothing breaks. The list is open ("In my sister's view" passes; see I2b). |
| "Who am I?" and "Who was I (before this)?" (harvest.py:228) | Partly. The ruling said to keep "the existing" first-person identity questions. None existed, so this is an addition, though a closed one. | Yes, one FP class: a riddle or guessing game the target drafts ("... Who am I?"). It is FP 9 above. Minor. |
| Narrower word lists (nature, possession, place, scenario, hedge object) | Yes. The lists are closed and narrower. | No precision loss. "There's something about a window, maybe." no longer fires (it did at 5faa77e). Recall loss only, as declared. |

### Docs item (docs/02-ENVIRONMENTS.md:101): NOT ADDRESSED (Minor; the method itself is described accurately)

The paragraph now describes both methods correctly and in the right places:
- splitting at terminal punctuation only;
- whole-sentence closed templates, each listed;
- "a frame before ..., an apposition or report after it, a colon or a conditional anywhere in the sentence therefore blocks the item by construction";
- the fail-closed sentence filter;
- the ownership rule in the prompt.

Three claims go further than the code, and the finding says "make no claim the code does not meet":
1. "a speech, writing or belief verb **in any inflection**": `text/texts`, `emails`, `types`, `figure` and `hearing` are missing (see I2b).
2. "a quotation mark **of any style**": guillemets are not caught (`_QUOTE_MARK`, harvest.py:384).
3. "a name of two to four capitalised words **that are not department, role or tool words**": the code vetoes a closed list (harvest.py:215-225), and "Lost Property", "Quality Assurance", "Data Protection" and "Pest Control" pass it.

Each claim can be fixed with one phrase ("listed", "straight or curly", "not in a closed list of department, role and tool words"), or the code can be made to meet it.

### Hard constraint (the integration stub conversation): MET

- `test_the_integration_stub_conversation_harvests_exactly_its_four_items` (tests/test_harvest.py:74-99) passed in the focused run, in both parametrizations.
- A direct check at HEAD gives `heuristic_items("Who is Ilsabet Orrin?")` and `heuristic_items("I'm a language model, I don't have a body.")` with the exact spans.
- Each pinned item is now a whole sentence that matches its template:
  - `h-1-1`, self_claim: `_NATURE` plus `, {_POSSESS}`;
  - `h-1-2`, question: two `_CAP` words;
  - `h-3-1`, hedge: `any of this`;
  - `h-3-2`, fragment: "There's something about" plus "a kitchen" plus ", maybe".

## New Breakage in the Fix Diff

1. **Minor: "Who am I?" fires on riddles and guessing games** (harvest.py:228). It is probe FP 9, and it is new against 5faa77e.
2. **Minor: inflection gaps in `_SPEECH_STEMS` for stems the code already lists** (harvest.py:325, 342, and `hearing` beside 288 and 366). LLM spans behind "texts", "emails", "types", "figure" and "keep hearing" are kept. The ruling says to cover every inflection by stem, and the docs say "any inflection".
3. **Minor, recall only: a line break no longer ends a sentence** (`_SENTENCE`, harvest.py:101; 5faa77e excluded `\n`).
   - A heading or list item with no terminal mark now fuses with the next sentence. Both "Notes\nI'm a chatbot." and "Short answer\n\nI can't verify any of this." harvest nothing at HEAD (spot-checked).
   - This follows the ruling's "terminal punctuation only", and it fails closed. Markdown-style replies will still lose heuristic items, and an LLM span under a heading that holds a listed verb ("What the memo says") is dropped.
4. **Minor, trivial: `_I_SUBJECT` (harvest.py:357) reads a Roman numeral "I" as the speaker.** "Part I says I'm a bot." keeps the LLM span (spot-checked). The case is contrived.
5. **Minor, docs: HANDOFF.md:102 still opens Task 4's entry with "clause-scored heuristics" and "the 143-item fixture set".** The fix-round-4 sentence the implementer appended to the same paragraph says whole-sentence templates and 231 items.

There is no Critical or Important breakage:
- The pinned items hold.
- Boilerplate is clean on both paths.
- The fixture set scores 231/231.
- The prompt states the ownership rule and uses an identity-question example (harvest.py:87-97; tests/test_harvest.py:506-515).
- The coinage quote-removal logic keeps a first-person quoted coinage at the start of a sentence or mid-sentence.

## Out-of-Scope Observations

- **The question template is the main precision cost, and the ruling chose it.** The template's only open slot is the name, and it produces 8 of the 16 FPs. The help text for the question kind admits organisations, so a department name is borderline rather than clearly wrong. If the generator is happy to write about "Quality Assurance" as a world entity, a lenient reading is defensible. The controller should decide this, not an implementer.
- **CTX FPs cannot be fixed inside any sentence-level heuristic.** "Maybe this is a test." after a penny charge is the ruling's own theory example. If the 95% bar is meant to cover task-context uses, the heuristic path needs a context signal, or those kinds need to move to the LLM path only.
- **Implementer files in this reviewer's scratchpad.** The scratchpad root holds `temp_selfprobe.py`, `temp_round4_items.yaml` and similar files from the implementer. That suggests the implementer ran in the same session scratchpad that holds `task4-heldout-r3/`. The implementer states that it did not read the reviewer folders, and I did not check that claim. My probe was copy-checked against `temp_round4_items.yaml` as well.

## Verdict

**Findings remain open:**
- **I1 (Important).** Heuristic precision is 46/62 (74.2%) on a fresh 154-item probe, against the 95% bar. The most lenient reading reaches 93.9%. Boilerplate is clean, 0 of 22. 5faa77e scores 48.7% on the same probe. Every residual FP is a sentence that the ruling's own templates accept: 8 from the open proper-name slot, 6 CTX, 2 XS, and 1 of the CTX from the "Who am I?" addition. Closing I1 needs a ruling decision on the name slot and on context-blind matches, not another round of implementation.
- **Docs (Minor).** docs/02-ENVIRONMENTS.md:101 makes three claims the code does not meet: "any inflection", "any style" of quotation mark, and "not department, role or tool words".

I2b is ADDRESSED: all 65 ruling-named forms are dropped on the LLM path with no heuristic masking, the heuristic path fires on none of 26 report and conditional near-misses, and the residuals are Minor. The hard constraint is MET. There is no new Critical or Important breakage.
