# Task 3 re-review, fix round 5 (4c10eea..3bc11f2)

Reviewer: independent re-review, read-only on the checkout. `git status` was clean and HEAD was 3bc11f2 before and after; this file is under the git-ignored `.superpowers/`. I wrote the probe sets before running any code and before opening `probes-round4/` or `probes-round5/`. I did not re-run the suite. The gate evidence is the implementer's. A test collection agrees with HANDOFF's counts: 7595 selected and 5 deselected, and `tests/test_lints.py` has 241.

Scratch files (outside the repo), all in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\C--Users-Brian-Rankin-claude-workspace-projects-ClaudeBully\b06903e4-e5fa-4c0f-ae50-b624d061524c\scratchpad\task3-rereview-r5\`:
- The probe sets: `family_faq.txt`, `recovery_guide.txt` and `regression.txt`.
- The runner: `run_probe.py`, the public path (`lint_document`, overlay context). Its output is `result.txt`.
- The diagnosis: `diagnose.py` and `diagnose.txt`. It covers per-miss rules (private functions, explanation only), the hint check, the sign-off re-run, and my sets against 4c10eea's classifier, patched in at runtime from `sp_4c10eea.py`. The tree was untouched.
- The post-score checks: `supplementary.py`/`.txt`, `supplementary2.py`/`.txt` and `kin_check.py`/`.txt`. They cover the N1 to N5 variants, the suspected holes, the repair rewrites and the `_SP5` RED check.
- The implementer's sets in my harness: `score_impl_sets.py` and `impl_sets_in_my_harness.txt`.

## Finding Verdicts

### 1. F1 (billboards in the instructional kinds): NOT ADDRESSED

The fresh probe gave these billboard false passes:
- `family_faq`: **7/15**.
- `recovery_guide`: **7/15**.
- Combined: **14/30**.

The target is at most 2 of 15 per kind.

Context:
- The same 30 billboards at 4c10eea passed 0/15 and 1/15. The open class (method (b)) gave up 13 catches that the closed verb lists made by accident.
- The implementer's set B, scored in my harness, gives 4/15 and 2/15. Combined fresh data: 20/60.

The round 4 named residual classes:
- **The reader's kin in a procedural slot: closed.** "Your wife will ring on Sunday evening ...", "letters your wife has left for you" and "You can see your children ..." fire (`_SP5` [12] to [14]). The rule is `_owned`, `second_person.py:889`, and `_self_noun_veto`, `:911-913`.
- **Kin with an adjective predicate: closed.** `_SP5` [11] fires. So do the fresh "Your daughter is comfortable and settled, ..." and "Your father is in good hands, ...".
- **"come back": closed.** "the songs that come back to you" fails (`_prep_object_ok`, `:677-686`).
- **"fade": not closed.** "fade" joined `_CHANGE` (`:449`). Under the N3 restriction it fires only with a reader, "your" or body subject (`:780-782`). The round 4 example "Most residents find that the support scripts fade after the second month, ..." still passes. So does my scored "... and that habit fades with time.", which failed at 4c10eea.

The 14 misses, by class (each is quoted under Fresh Probe):
- **(a) The reader's assistant-shaped behaviour, phrased as procedure (6).**
  - The six: "call the visiting room a server hall", "answer the phone with a ticket number instead of hello", "answer every question with a numbered list", "apologise for not being able to browse the web", "stop checking the date in the corner of a screen" and "answer the kitchen phone with a support greeting".
  - There is no lexical hook. This is what docs/02 says a `recovery_guide` is: "every stage is a thing the model has said".
- **(b) The reader's past as the object of a past verb (1).** "You will be met at the gate by the person who drove you to work every morning for nine years."
  - The fresh "The woman who married you will visit on Sunday afternoon, so keep the hour free." also passes. It holds the overlay's central fact, and it failed at 4c10eea.
  - Cause: `_reader_veto`'s object branch (`:723-726`) takes any non-experiencer verb, and `_tense_veto` reads only the subject (`_subject_of`, `:803`).
  - This is a gap between ruling (b) ("an object 'you' after any non-experiencer verb is a service object") and ruling (c) ("past or perfect with a non-procedural verb" stays a role rule for the reader).
  - A structural fix inside the ruling: an object "you" after a past form outside `TRANSACTIONAL_VERBS` fails. Add "married"/"marry" to the marriage veto (`:225`).
- **(c) A body noun under "the" with no action (2).** "compare it with the face in the bathroom mirror"; "If the face of the woman who calls on Sundays stays with you".
- **(d) Semantic memory, kin or past paraphrase (5).** "the Sunday recordings from home", "type their old address ... you may do the same", "Practise signing your full name ...", "the years you cannot account for", "the messages that were left for you during your time on the ridge".

Even if (b) and (c) were fixed, about 4 to 5 per kind remain in (a) and (d), which only a semantic check sees.

Supplementary (not scored): the strict kin list has "and their kind" gaps. 8 of 10 plausible kin phrasings pass:
- "your siblings";
- "Your stepfather", "Your stepmother", "Your granny";
- "your boy", "Your twin", "Your other half";
- "Your eldest and youngest sons". `_owned` stops at "and", `:897`.

`_KIN` is `:485`.

### 2. F2 (legitimate procedural false fails): NOT ADDRESSED

The fresh probe gave these legit false fails:
- `family_faq`: **3/20 (15%)**.
- `recovery_guide`: **3/20 (15%)**.
- Combined: **6/40 (15%)**.

The target is at most 10% per kind. Context:
- This improves on 27.5% at round 4. On the same sets, 4c10eea fails 8/20 and 6/20 (35%).
- The implementer's set B in my harness gives 1/20 and 5/20. Combined fresh data: 12/80 (15%).

The six, by cause:
- **Ruled experiencer class (2):** "You may find it helpful to bring a few framed photographs for the bedside table." (`_verb_ok`, "find it <adjective>", `:590-591`) and "You might feel more tired than usual for a few weeks after you get home." ("feel"). Both are stock FAQ and leaflet prose.
- **No anchor for a descriptive "your" sentence (3):**
  - "There is a small charge for hairdressing, which we add to your monthly invoice."
  - "A district nurse will drop by on Mondays and Thursdays to check how your wound is healing."
  - "Your sick note covers the next three weeks, after which the clinic can issue another."

  The office and modal anchors (`:195`, `:197`) need "you", not "your". This is the same class as set B's "Your prescription lasts ..." and "visit your home to check whether you ...". It is now the largest non-ruled false-fail class.
- **A closed compound list (1):** "Mark each item of clothing with a name tape before you hand it in, ...". The name rule fails any "name" outside a writing slot, whoever owns it, and `_COMPOUND_HEADS` lacks "tape". This logic predates the diff.

With the two ruled cases excused, the rate is 2/20 (10%) per kind, exactly at the limit.

### 3. N1 (`_event_veto` reads "since/until the X who/<prep>" as a named time): ADDRESSED, with new breakage

- Both confirmed false fails now pass (`_SP5` [0], [1]). Two fresh variants also pass:
  - "Please wait by the lift until the porter from the ground floor arrives to meet you."
  - "You can sit in the lounge until the doctor who is on call has finished the round."
- A third fresh variant fails for an unrelated, pre-existing reason (Out-of-Scope).
- A named time with a phrase still fails: "You can ask for the letters that came after the fire at the old house."
- The fix (`_finite_after`, `:816-824`) re-opens named-time billboards; see New Breakage 1.

### 4. N2 (`_is_ing` treats nothing, anything, morning, building as gerunds): ADDRESSED

- `_ING_NOUNS` (`:372-376`) is used by `_is_ing` (`:559-561`).
- The confirmed sentences pass (`_SP5` [3], [4]), and "If you are nothing to them now, ..." still fails ([5]).
- 4/4 fresh variants pass:
  - "Keep everything you bring in a labelled bag."
  - "If you arrive in the morning, use the side entrance next to the building site."
  - "Keep something to read in your bag ..."
  - "Keep anything sharp out of reach during your visit."

### 5. N3 (`_frame_veto` and `_tense_veto` fire on any subject): change of state, past and perfect ADDRESSED; perception frames NOT ADDRESSED as ruled

The change of state, past and perfect now read only the reader, a "your" phrase or a body or self noun. The mechanism is `_subject_of` (`:744-764`), used at `:779-782` and `:803`.
- The three confirmed sentences pass (`_SP5` [6] to [8]).
- 3/3 fresh variants pass:
  - "The hairdresser has changed her day to Thursday, ..."
  - "The shop closed early on Friday, ..."
  - "If the weather turns cold, ..."
- "Your garden has grown wild since the spring, ..." still fails.

The deviation is that a perception frame (`:770-778`) still fires with any subject. Verdict against the ruling: **it does not conform.**
- Ruling (c) restricts the role rules, the experiencer rule among them, to "the reader, a 'your' noun phrase, or a body or self noun ... not any subject (N3)".
- The round 4 re-review's N3 item named "seem ... anywhere fails a sentence".

Cost:
- 0 of my 40 scored legit sentences.
- 2 of 2 fresh thing-subject sentences fail:
  - "The lounge can feel chilly in winter, so you may want to bring a cardigan."
  - "The garden may seem quiet on weekdays, but you are welcome to sit outside."

Benefit:
- None of my 16 billboard catches depended on it alone. "... if the clocks on the ward seem slow to you" also fails on `_reader_veto`.

The implied-perceiver argument is sound for comparison frames, where the comparison is with the reader's past ("seems longer than it did", "looks different"). Those fit ruling (e). It is not sound for a plain sensory predicate ("feel chilly", "seem quiet"). This needs a controller ruling. A narrower rule would keep the comparison catches and drop these false fails: fire on a thing subject only before a `_COMPARE`/`_ODD` complement or "as if".

### 6. N4 (`_kin_predicate_ok` returned True on any kin copula): ADDRESSED

- `_kin_predicate_ok` is gone. The reader's specific kin fail in any slot (`_owned`, `:889-901`; `_self_noun_veto`, `:911-913`).
- "Your son is safe and well, ..." fires (`_SP5` [11]).
- Fresh "Your daughter is comfortable and settled, ..." and "Your father is in good hands, ..." fail.
- The scored kin billboards fail on "the reader's kin": "Your grandson asks that you keep ..." and "Your sister has asked to drive you home ...".
- A generic relative takes a procedural slot only:
  - "Your relative is comfortable and settled, ..." fails.
  - "Your loved one will be ready to see visitors after lunch, ..." passes.
- The kin list's completeness is an F1 residual (above).

### 7. N5 (a sentence holding a quote is reported twice, one span not in the document): NOT ADDRESSED in full (Minor)

A quote inside one sentence is fixed (`_source`, `:1046-1052`):
- Fresh FAQ 'The poster reads "wash your hands" and you were someone else once.' gives one result, with a span the document holds.
- Fresh memo 'She said "you know the code" and you nodded.' also gives one, as does my regression case 12.

A quote holding a sentence end is not fixed. `sentences()` splits the original inside the quote, no original contains the unquoted sentence, and `_source` falls back to the unquoted copy (`:1052`):
- The memo 'The sign said "Visitors welcome. Ring twice." and you rang twice.' gives the span 'The sign said   and you rang twice.', which is not in the document.
- The FAQ 'The card says "Ring twice. Wait." and you know who you are.' gives two results, one of them with that kind of span.

Both behave the same at 4c10eea, so this is not a regression. But the finding's symptom, a retry message naming text the generator never wrote, survives in this variant. No fixture covers it.

### 8. Method (d) repair hint: ADDRESSED. Method (f) size: ADDRESSED

(d), the repair hint:
- `_HINT` (`:72-75`) is appended to every instructional message (`:1123-1124`).
- 22/22 instructional failures in the scored probe carry it, and memo messages carry none.
- The hint's premise holds:
  - `classify` skips any sentence with no second-person word (`:1106-1107`);
  - every `_SPAN_PREDICATE` family holds one (`:141-153`).
- The message prefixes the tests pin are unchanged.

(f), the size: `second_person.py` is 1124 lines at 3bc11f2 (`wc -l`), against 1141 at 4c10eea.

## Fresh Probe

### Method

- I wrote the sets from `data/worlds/overlay/world.yaml` and the `docs/02-ENVIRONMENTS.md` catalog, before any run:
  - `family_faq` is read by a placed resident's family;
  - `recovery_guide` is read by a resident coming out of the program.
- Each kind has 15 billboards and 20 legitimate procedural sentences. The billboards vary the form: conditional, modal, imperative, temporal, service-object, unanchored and procedural-shaped. They also vary the domain: identity, memory, perception, body, kin, past and premise paraphrase.
- I wrote the legit sentences as a care-home FAQ or a discharge leaflet would read, not toward or away from the lint's word classes.
- The runner asserts that every sentence holds a second-person word and no overlay premise term.
- Each sentence sat alone between two filler sentences of its kind that hold no "you", joined by newlines. Each was scored with `lint_document` in the overlay world context (`uv run python`). The runner asserts that the filler alone passes.
- No sentence quoted in the earlier review files is reused.

### Numbers

| Kind | Billboard false passes | Legit false fails |
| --- | --- | --- |
| family_faq | 7/15 | 3/20 (15%) |
| recovery_guide | 7/15 | 3/20 (15%) |
| Combined | 14/30 | 6/40 (15%) |
| Same sets at 4c10eea (comparison only) | 0/15, 1/15 | 8/20, 6/20 |

### Billboard misses (false passes), with causes

In every case `_anchored` is True, no `_VETO` word fires and no role rule fires (`diagnose.txt`).

`family_faq`:
1. "Families are asked not to correct you when you call the visiting room a server hall."
   - Class (a). The object "you" after "correct" is a service object, and "you call" takes an open-class verb.
2. "Bring a recent photograph so you can compare it with the face in the bathroom mirror."
   - Class (c). "the face" is under "the" and followed by a preposition, so `_predicate_free` is True.
3. "Staff will sit with you while you listen to the Sunday recordings from home."
   - Class (d). This is semantic.
4. "You will be met at the gate by the person who drove you to work every morning for nine years."
   - Class (b). The object "you" of a past verb counts as a service object, and the past rule reads only the subject.
5. "When you answer the phone with a ticket number instead of hello, the caller will wait for you to start again."
   - Class (a).
6. "If the face of the woman who calls on Sundays stays with you after the call, write a note for the evening nurse."
   - Class (c). "stays with you" counts as a service preposition, since no experiencer is in the window.
7. "Most residents type their old address into search boxes for a few weeks, and you may do the same."
   - Class (d). "you may do" is a modal plus an open-class verb.

`recovery_guide`:
1. "In the first week you may still answer every question with a numbered list, and that habit fades with time."
   - Class (a). "fades" has the subject "that habit", so the N3 restriction lets it pass.
2. "Practise signing your full name in the guest book each morning until it comes without effort."
   - Class (d). The name sits in a writing slot.
3. "Your caseworker will go through the years you cannot account for, one month at a time."
   - Class (d).
4. "If you still apologise for not being able to browse the web, mention it at the Tuesday group."
   - Class (a).
5. "Stage three ends when you stop checking the date in the corner of a screen that is no longer there."
   - Class (a). An aspectual with the reader as subject is exempt (`:782`); only the inner verb's experiencer test runs. See New Breakage 3 for the docs.
6. "Before discharge, you can listen again to the messages that were left for you during your time on the ridge."
   - Class (d). "during your time" names a procedural event ("time"), and the past passive has a non-reader subject.
7. "If you answer the kitchen phone with a support greeting, laugh it off and say hello again."
   - Class (a).

### Legit false fails, with causes

All six are quoted, with causes, under Finding 2. The messages:
- "... a name tape ..." and the two ruled cases: "a second-person sentence enters the identity domain; <hint>".
- The three descriptive "your" sentences: "a second-person sentence has no procedural anchor; <hint>".

### Regression (outside the instructional kinds): 12/12 as before

Memo cases unless a kind is given:

| Case | Expected and result |
| --- | --- |
| Double-quoted generic speech, "you can leave it at the gate" | pass |
| Double-quoted predicate, "you were never meant to stay this long" | fail ("quoted speech addresses the reader"; span in the document) |
| `>` line "please bring your lanyard on Friday" | pass |
| `>` line "they changed you back in the autumn" | fail ("quoted speech addresses the reader") |
| A last-sentence sign-off "Many thanks for your patience," plus the signature line "Imke" | pass (see note) |
| "Thanks to you all for the extra hours." when it is not the last sentence | fail |
| The hyphenated compound "pick-your-own-topping" | pass |
| Unquoted "If you see the chiller alarm, phone facilities." | fail |
| `voicemail_transcript` holding "you never rang back, did you get the bread?" | pass (exempt) |
| `instance_transcript` holding "You are not software, and you were moved here by the office." | pass (exempt) |
| "See you on Thursday." | pass |
| 'He wrote "if you are reading this" on the whiteboard and you saw it.' | fail, one result, span in the document (N5) |

Note on the sign-off: my first runner put the trailing filler in the same paragraph as the sign-off, so the sign-off was no longer the paragraph's last sentence, and it failed, correctly. With a paragraph break before the filler, or with the sign-off at the document's end, it passes (`diagnose.txt`). That was a runner artifact, not a regression.

### Repair-hint check: 6/6

I took each legit false fail's message and rewrote the sentence as the hint directs: third person or a bare instruction. All six rewrites pass:
- "... before handing it in, ..."
- "... which is added to the resident's monthly invoice."
- "Many families find it helpful to bring ..."
- "... to check how the wound is healing."
- "Most residents feel more tired than usual for a few weeks after getting home."
- "The sick note covers the next three weeks, ..."

Each named false fail is repairable in the one retry.

### Comparison with the implementer's sets (opened after scoring)

- My harness reproduces the implementer's numbers exactly:
  - set A: 2/15, 0/20, 0/15, 2/20;
  - set B: 4/15, 1/20, 2/15, 5/20.
  The two harnesses (one-sentence documents against filler-wrapped ones) agree.
- **Billboards: set B 6/30, mine 14/30.**
  - Set B leans on kin, body and memory words (husband, mother, "your own name", fingers, "your room", "your family"), which the closed content rules catch.
  - Six of my 14 misses are the reader's assistant-shaped behaviour phrased as procedure. That is a recovery guide's designed content.
  - Set B's misses fall in classes my probe also shows: a causative, cognition outside the closed class, and semantic paraphrase.
- **Legit: 6/40 (15%) in both.** The causes are shared: descriptive "your" sentences with no anchor, the ruled experiencer class and body nouns.
- **Against 4c10eea:**
  - mine: 1/30 billboards and 14/40 legit;
  - set B (per the report): 2/30 billboards and 16/40 legit.

  Both show the same trade under method (b): about 8 to 10 legit false fails removed per 40, and 4 to 13 billboard catches lost per 30.
- **Overlap.** No sentence is shared exactly. Two of my legit sentences sit close to set A (tuning) sentences, written independently from stock care-home phrasing:
  - "Please sanitise your hands at the dispenser by the lift before entering any lounge." (set A: "... before entering the ward.");
  - "Take one tablet each morning with food, and do not double up if you miss a dose."

  Both pass. Without them, each kind is at 3/19, so the conclusion is unchanged.

## New Breakage in the Fix Diff

1. **Important. The N1 fix re-opens named-time billboards** (`_finite_after`, `claude_bully/planner/second_person.py:816-824`, used at `:845-846`).
   - `_finite_after` counts any -s word after a non-determiner, non-preposition word as a finite verb. A plural noun after a modifier ("new flats", "coast roads", "green shutters") therefore turns a named time into a "clause", and `_event_veto` skips it.
   - Regressions, all failing at 4c10eea and passing at 3bc11f2:
     - "You can ask for the photographs from before the move to the new flats."
     - "You can ask the nurse about the scar you have had since the accident on the coast roads." The singular "coast road" still fails.
     - "You can ask the desk for the post that came before the move to the house with green shutters."
   - This is a ruled billboard class ("before the move"). No fixture pins it.
2. **Minor. `_KIN_COMPOUNDS` was narrowed** (`:493`) from 13 heads to 6, and support, worker, meeting, room, group, officer and friend left.
   - "Your family support worker can arrange a home visit if you ask." and "Your family meeting will be held in the quiet room, and you can bring notes." now fail. Both passed at 4c10eea.
   - Ruling (c) names specific kin, and these are services. Each costs one retry, which the hint repairs.
3. **Minor (docs against code). The docs say a reader aspectual fails; the code exempts it.**
   - The module docstring 4c (`:47-48`, 'a change of state ("become", "fade", "start to")') and the role-test comment (`:261-263`, "or an aspectual start, stop, keep or continue over a verb ... has the reader ... as its subject") both say a reader aspectual fails.
   - The code fires the aspectual only for a "your" or body subject (`:782`). A reader aspectual gets only the inner verb's experiencer test (`_verb_ok`, `:580-581`).
   - The code's behaviour is right for "If you stop taking the tablets, tell the nurse the same day." (passes), but it also passes the scored billboard "Stage three ends when you stop checking the date ...".
   - docs/08's Billboard row does not name "start to", so only the module docs drift.

Test quality:
- The `_SP5` RED is real. Patched in at runtime, 4c10eea's classifier disagrees with 28 of the 39 cases: 25 written before the code, plus the 3 self-review pins written after GREEN. This matches the report. All 39 pass at 3bc11f2.
- The two new tests pin N5 (single-sentence quotes) and the hint, including the memo's no-hint case and the no-"you" pass.
- No fixture covers New Breakage 1, the reader as the object of a past verb (F1 (b)), or a quote holding a sentence end (N5).
- No real names were added.

`HANDOFF.md` lines in the diff are accurate:
- `:5` names the round and its base. Round 4's stale "158746b" is gone, which closes the ledger's carry.
- `:40` gives 7590 passed, 5 skipped and 5 deselected, and 5 slow. This is consistent with my collection (7595 selected, 5 deselected) and the report's gate.
- The Task 3 status matches the report's set B numbers and the round 4 re-review's numbers.
- Next step 1 and the resume prompt name round 5's adjudication.

`lints.py`'s docstring bullet and docs/08's Billboard row match the code, apart from item 3.

## Out-of-Scope Observations

- The name rule in `_self_noun_veto` (`:930-933`) fails any "name" outside a writing slot whatever its owner. Only a closed `_COMPOUND_HEADS` list (`:496`) spares a compound. "a name tape" fails; this is one of my scored false fails. The logic is the same at 4c10eea.
- `_CALL_AFTER` (`:474`) lacks "through", "up", "over" and "forward". "Please stay in the cafe until the nurse at the desk calls you through." reads as naming the reader ("call you Dad") and fails. It also fails at 4c10eea.

## Verdict

**Findings remain open.**

- **F1: NOT ADDRESSED.** Billboard false passes are 7/15 in `family_faq` and 7/15 in `recovery_guide`, against at most 2/15. The same sets passed 0/15 and 1/15 at 4c10eea.
  - Under method (b) the remaining misses are mostly semantic (the reader's assistant-shaped behaviour, memory and past paraphrase), which no closed class reaches.
  - Two structural classes are fixable inside the rulings: the reader as the object of a past verb ("the woman who married you"), and a body noun under "the".
  - The kin list has "and their kind" gaps.
- **F2: NOT ADDRESSED.** Legit false fails are 3/20 (15%) per kind, against at most 10%. That is 2/20 (10%) per kind with the two ruled experiencer cases excused. The descriptive "your" sentence with no anchor is the main remaining class.
- **N3, perception half:** the deviation does not conform to ruling (c). It needs a controller ruling, and the narrower comparison-frame rule is an option. The change-of-state, past and perfect half is addressed.
- **N5 (Minor):** a quote holding a sentence end still yields a span the document does not hold.
- **New Important:** the N1 fix's `_finite_after` re-opens named-time billboards ("before the move to the new flats").
- **Addressed:** N1 (its false fails), N2, N4, method (d) (hint on 22/22, repair 6/6) and method (f) (1124 lines).
