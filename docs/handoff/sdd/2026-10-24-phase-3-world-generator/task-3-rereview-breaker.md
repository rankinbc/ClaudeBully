# Task 3 re-review, breaker fix (3bc11f2..dd6cdec)

Reviewer: independent re-review, read-only on the checkout. `git status` was clean and HEAD was dd6cdec before and after. This file is under the git-ignored `.superpowers/`.

Process:
- I wrote the probe sets before running any code and before opening any `probes-*` folder. I hashed them before the first run (`sets_sha256_before_run.txt`), and they were unchanged at the end.
- I did not re-run the suite. A test collection agrees with HANDOFF's counts: 7630 selected (7625 passed plus 5 skipped), 5 deselected and 5 slow. `tests/test_lints.py` has 276.

Scratch files are outside the repo, all in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\C--Users-Brian-Rankin-claude-workspace-projects-ClaudeBully\b06903e4-e5fa-4c0f-ae50-b624d061524c\scratchpad\task3-rereview-breaker\`:
- The probe sets: `family_faq.txt`, `recovery_guide.txt` and `regression.json`.
- The runner: `run_probe.py`, which takes the public path (`lint_document`, overlay context, filler-wrapped).
  - Its outputs are `result_head.txt`, `result_dd6cdec.txt`, `result_3bc11f2.txt` and `result_4c10eea.txt`.
  - The other versions are `git show <sha>:claude_bully/planner/second_person.py`, copied to `versions/` and patched over `lints.classify` at runtime.
  - `lints.py` differs only in its docstring across the three commits, so the patch reproduces each version exactly. Patched dd6cdec matches the checkout line for line.
- The per-miss causes: `diagnose.py` and `diagnose.txt`. These use private functions, for explanation only.
- The post-score checks: `supplementary.py`/`.txt` (restore against 4c10eea, flips and `_SP6` at each version, and the doubts below), `anchor_check.py`, `hint_check.py`/`.txt` and `reuse_check.py`/`.txt`.

## Requirement Verdicts

### 1. Restore 4c10eea's form side: MET

The restore is faithful where it claims to be.
- `PROCEDURAL_VERBS` (`claude_bully/planner/second_person.py:70-80`) holds the same 124 verbs in the same order.
- These are identical to 4c10eea's:
  - `_VERB` (`:81`), `_IMPERATIVE` (`:252-256`) and `_ROLE`;
  - `_OBJECT_VERBS`, `_TO_VERBS` and `_LICENCE` (`:480-489`);
  - `_GET_OK` (`:450`), `_ADVERBS` (`:420-422`), `_ASPECT_PAST` (`:469`) and `_CALL_AFTER` (`:496-499`);
  - every other slot list.
- `_ANCHOR` (`:205-250`) equals 4c10eea's once `_MODAL_TAIL` is swapped back. `_CLAUSE` splits the same; only its escapes changed.
- The slot logic is back: `_base_ok` (`:602`), `_have_ok`, `_state_ok`, `_forget_ok`, `_subject_ok` (`:672`), `_licensed` (`:717`), `_object_ok` (`:731`) and `_reader_veto` (`:755`).
- None of round 5's open-class symbols remain. A grep for `_EXPERIENCER`, `_verb_ok`, `_imperative_veto`, `_prep_object_ok`, `_verbish`, `_TO_YOU` and `_skip_adverbs` finds nothing.

The six non-verbatim closed rules, each checked:

| # | Rule | Location | Check |
| --- | --- | --- | --- |
| a | `_MODAL_TAIL` adverb slot widened to just, only, usually, already, now, normally | `:193-196` | Closed; no verb list widened. "You can now park by the main door." passes, and fails at 4c10eea. OK |
| b | `_subject_ok` reads "is" | `:686` | Used only by the generic-relative slot. A subject "you" never takes "is". OK |
| c | The -ly participle rule in `_state_ok`, `passive` parameter dropped | `:650-651` | Closed; every 4c10eea caller passed `passive=True`. OK |
| d | "remind you of" fails; after "help/let you" the infinitive must be listed | `:743-749` | Both SP5 positives pass at 4c10eea and fail at HEAD, so keeping them keeps catches. OK |
| e | A verb before "you" makes it an object: a past form not after a copula, or "who <verb>" | `:760-764`, `:774` | Catches "the woman who married you" and "the person who drove you" (both lost through N3), and "the people who love you" (newly). It also adds a legit false-fail shape; see New Breakage 3 |
| f | `_KIN_COMPOUNDS` is 4c10eea's minus friend/friends | `:522-525` | Verified. "your family friend" fails; "your family support worker" and "your family meeting" pass again. OK |

The report's item 2 also discloses 3bc11f2's wider `_PREPOSITIONS`, `_DETERMINERS` and `_PRONOUNS` (`:427-439`; +among, beside, round, towards; +most, many, few, several; +anything, something, everything, nothing) and "finish" in `TRANSACTIONAL_VERBS` (`:402`). These are not among the six.

One consequence of the restore, round 5's "come back to you" catch lost, is New Breakage 1.

### 2. Keep round 5's N2, N4 (widened), the hint and N3's subject restriction: MET

- **N2:** `_ING_NOUNS` (`:413-417`) is used by `_is_ing` (`:593-595`).
  - "Keep everything you bring in a labelled bag." passes, as does "Keep anything sharp out of reach during your visit." Both fail at 4c10eea.
  - "If you are nothing to them now, ..." fails.
- **N4:** the kin rules are `_owned` (`:929-937`) and the kin branch of `_self_noun_veto` (`:947-951`).
  - `_KIN` (`:511-520`) now has siblings, twins, every step-kin form, granny, grannie, nan, nana, nanna, grandad, granddad, gramps, grandparent(s), grandmothers, grandfathers and grandkids. "Other half" is read as ("half" after "other") at `:947`.
  - Fresh checks fail: stepmother, nan, twin, grandkids, mother-in-law.
  - Residual outside the required widening: "your better half", "your eldest", "your boy", "your little girl", "your in-laws" and "your missus" pass. "Your eldest" is one scored miss.
- **The hint:** `_HINT` (`:90-93`) is appended at `:1136-1137`. It is on 43/43 instructional failures in the probe, and the memo failure carries none.
- **N3:** `_subject_of` (`:783-803`) gates the change of state and aspect (`:825`, `:834`) and the past and perfect (`:855`).
  - "The hairdresser has changed her day to Thursday, ..." passes. It fails at 4c10eea.
  - "Your garden has grown wild ..." and "If your shop closed ..." fail.

### 3. N1, drop `_finite_after` and return to the named-time reading: NOT MET (narrow)

What is met:
- `_finite_after` is gone.
- `_event_veto` (`:868-892`) is 4c10eea's, plus one excuse at `:889-890`.
- N1's two confirmed false fails pass.
- The round 5 re-review's regressions fail again: "the move to the new flats", "since the accident on the coast roads" and "the house with green shutters". So does "after the fire at the old house", and "before the porter strike" fails (the excuse reads the head only).

What breaks the item's condition ("by a rule that does not re-open the named-time billboards"):
- `_STAFF` (`:559-565`) is documented as persons, but it holds four vehicles: taxi, bus, minibus and ambulance.
- With a vehicle as the head of the phrase and a preposition after it, a time named by the reader's transport passes. Each of these fails at 4c10eea and at 3bc11f2, and passes at HEAD (`supplementary.txt`):
  - "You can ask your caseworker about the weeks before the ambulance to the ridge."
  - "You can ask for the clothes you had on the day of the bus to the campus."
  - "You can ask the office for the post that came before the taxi from the station."
- The report's claim "It cannot re-open a named-time billboard, since an event noun is never on the list" does not hold for these.
- No fixture uses a vehicle head.
- The fix is to drop the four vehicles, or to let a vehicle excuse only "until" ("until the taxi from the rank arrives"). Neither breaks a fixture.

### 4. N3, perception on a thing subject: MET (with a Minor gap)

The rule is in `_frame_veto` (`:812-836`), with `_compared` (`:806-809`) and `_DEGREE` (`:478`).
- These pass:
  - "The lounge can feel chilly in winter, ..." (also with "a little chilly");
  - "The garden may seem quiet on weekdays, ...".
- These fail:
  - "If the corridor seems longer than it did, ..." (also "a bit longer than it used to");
  - "looks different";
  - "seem shorter to you";
  - "as if" with any subject;
  - "If you feel a little lost ...";
  - "If your hands feel cold ...".

The gap: a bare comparative with no "than" and outside `_COMPARE` passes ("If the corridor seems longer now, ..."). See New Breakage 4.

### 5. Fixtures, RED first: MET

- `_SP6` has 35 cases (`tests/test_lints.py:562`) and covers items 1 to 4 with positives and near-misses. The hint keeps its existing test; no new hint fixture was added.
- 12 `_SP5` cases are flipped (`:475-560`), each marked in a comment and listed in the report's table.
- My cross-version evaluation of the 12 flips and 35 `_SP6` cases (`supplementary.txt`):
  - HEAD agrees with all 47.
  - 3bc11f2 disagrees with 29. This matches the report's RED of 28 plus flip 12, which was found at GREEN.
  - Every flip also fires at 4c10eea, so each one is what the restore entails.
  - Flips 6, 7 and 9 to 12 pass at 3bc11f2 through open anchor or object positions, not strictly through "an unlisted verb". They are within the ruling's open-class form side.
- No real names are in the new fixtures.

### 6. Docs: MET (two Minor inaccuracies)

These are present and describe the closed form side, the narrowed perception rule, the N3 subjects, the N1 excuse and kin with "other half":
- the module docstring (`second_person.py:1-60`);
- the role-test comment (`:288-325`);
- `lints.py`'s bullet (`:11-19`);
- docs/08's Billboard row (`docs/08-DIRECTOR.md:164`).

HANDOFF:
- `:5`, the "Last updated" line, names the breaker fix on 3bc11f2.
- `:40` gives 7625, 5 and 5, and 5 slow. My collection agrees.
- `:94`, Progress Task 3, gives the five rounds, the ruling, the breaker fix, set B's residuals (2/15 and 3/15; 4/20 and 9/20, every one with the hint; 13/13 rewrites) and the semantic residual left to Phase 7. This matches the report.
- `:98` (next step 1) and `:217` (the resume prompt) resume at Task 4 after the review and docs-sync.

`docs/handoff/` is untouched.

The two inaccuracies are New Breakage 5.

### 7. Size: MET

`second_person.py` is 1137 lines, at or under 1141 (`wc -l`).

### Measure: the binding target is NOT MET in family_faq

| Kind | Billboard false passes on my fresh probe | Target |
| --- | --- | --- |
| family_faq | 4/15 | missed |
| recovery_guide | 2/15 | met |

The implementer's set B gave 2/15 and 3/15. So each kind misses the target on one of the two independent probes. Combined fresh data at HEAD: family_faq 6/30, recovery_guide 5/30.

## Fresh Probe

### Method

- I wrote the sets from `data/worlds/overlay/world.yaml` and the docs/02 catalog:
  - `family_faq` is the placed resident's family FAQ, and its billboards slip into addressing the resident;
  - `recovery_guide` is read by a resident coming out of the program.
- Each kind has 15 billboards and 20 legitimate procedural sentences.
- The billboards vary the domain: identity, memory, perception, body, kin, past and premise paraphrase. They also vary the form:
  - procedural-shaped ones;
  - five open with a phrase before "you" ("During the first visits home, you", "After so many months ..., you", "In stage two you", "For a while you", "Once the headaches ease, you");
  - imperative, conditional, modal, relative clause, object "you" and fronted subject.
- The legit sentences are care-home FAQ and discharge-leaflet prose, written for everyday vocabulary, not toward or away from any list.
- The runner asserts:
  - every sentence holds a second-person word;
  - no sentence holds an overlay premise term;
  - no other lint fails;
  - the filler alone passes.
- Each sentence sits alone between two you-free filler sentences of its kind, joined by newlines, through `lint_document` in the overlay context.

Reuse (`reuse_check.txt`):
- No sentence is reused exactly from the review files, the `probes-*` folders (checked after scoring) or `tests/test_lints.py`.
- A few are stock-phrasing near-paraphrases of earlier probe sentences. The closest (0.84) is the legit "The hairdresser comes on Wednesdays, and you can book an appointment ...", which passes in all three versions. Removing the near-paraphrases changes no conclusion.

### Numbers

| Version | family_faq billboards | family_faq legit | recovery_guide billboards | recovery_guide legit | Billboards total |
| --- | --- | --- | --- | --- | --- |
| **dd6cdec (HEAD)** | **4/15** | **4/20** | **2/15** | **15/20** | **6/30** |
| 3bc11f2 (round 5) | 4/15 | 3/20 | 5/15 | 6/20 | 9/30 |
| 4c10eea (round 4) | 4/15 | 5/20 | 3/15 | 15/20 | 7/30 |

- HEAD is the best of the three on billboards.
- Its legit false fails equal 4c10eea's less one: "... to make the room feel homely" now passes, through item 4.
- recovery_guide's 15/20 is the ruled trade of a closed verb list against discharge-leaflet vocabulary. There is no target, and every one is repairable (below).

### Billboard misses at HEAD (false passes), with causes

`family_faq` (4):
1. "Bring the old holiday album on your second visit, as the faces in it may take a while to come back to you."
   - **Structural, re-opened by this fix.** The "you" after "to" passes `_object_ok`'s to/back branch (`:738-740`): "come" is in `_TO_VERBS` (`:485-487`), and the clause holds a licence ("may", and the infinitive "to come", `:721-724`).
   - "the faces in it" is a body noun under "the" before a preposition (`_predicate_free`, `:1011`).
   - Caught at 3bc11f2 (round 5's come-back rule); passes at 4c10eea.
2. "Visitors may bring in a coat from the hall cupboard at home so you can check whether it still fits."
   - Semantic: body and past by paraphrase. "you can check" is listed. Passes in all three versions.
3. "After so many months answering other people's questions, you can take as long as you like to choose what to eat."
   - Semantic: the premise paraphrased in a fronted phrase that holds no "you". "you can take" is listed. Passes in all three.
4. "Some residents keep waiting for a prompt before they speak, so visitors should feel free to talk first and give you time."
   - Semantic: the assistant habit told of third parties.
   - The aspectual's subject is "some residents" (`_subject_of` gives None, N3), and "give you" opens its clause as a licensed service.
   - Passes in all three.

`recovery_guide` (2):
1. "You can ask the caseworker to go over the months that are missing from your diary."
   - Semantic: a memory gap by paraphrase. Passes in all three.
2. "When your eldest rings on a Sunday, you can take the call in the quiet room."
   - Kin outside `_KIN`: "eldest" used as a noun. Passes in all three. A closed-list addition would catch it.

With miss 1 of family_faq fixed (New Breakage 1), family_faq would be at 3/15: still over, with the rest semantic.

### Legit false fails at HEAD, with causes

`family_faq` (4):
- "Visiting is open from ten in the morning until eight at night, and you do not need to book."
  - No anchor: "you do not need to" is in no anchor. Same in all three versions.
- "Children under twelve must be with an adult at all times, so please keep an eye on yours."
  - A bare "yours" (`_yours_unnamed`, `:898-903`). Same in all three.
- "Your relative's weekly fee includes meals, laundry and activities, but toiletries are extra."
  - No anchor: a descriptive "your" sentence. Same at 4c10eea.
- "Feel free to take your relative out for the afternoon, but tell a member of staff when you go and when you expect to be back."
  - "when you expect": "expect" is no listed predicate (`_reader_veto`, `:770-773`). Same at 4c10eea.

`recovery_guide` (15):

| Cause | Count | Sentences |
| --- | --- | --- |
| Unlisted verb or no anchor | 5 | "You should avoid driving ...", "You can shower as normal, but ... pat it ...", "You will need someone to stay with you ... after you get home.", "Do not lift anything heavy, ...", "Contact the ward if you run out of dressings ..." |
| Ruled classes | 2 | "If you feel dizzy when you stand up, ..." (reader perception) and "If you notice any bleeding, ..." |
| Service or licence gap | 3 | "A community nurse will visit you at home ..." ("visit" is listed but no `_OBJECT_VERBS` service, so "you" reads as a subject before "at"); "Gentle walking is good for you, ..." ("for you" with no licence); "... your practice nurse can refer you to a free service." ("refer") |
| Slot gap | 2 | "... before you do anything strenuous." ("do" takes only "not"); "You may get tired easily ..." ("tired" is not in `_GET_OK`) |
| Content list | 2 | "Keep your feet up ... your ankles." (body nouns outside a care slot); "... ten days after the operation." ("operation" is not in `_EVENTS`; the same in all three versions) |
| Anchor shape | 1 | "Your follow-up appointment letter will arrive by post ..." (at most two words between "your" and the modal, and "follow-up" is hyphenated) |

Every message: "a second-person sentence enters the identity domain; <hint>" or "a second-person sentence has no procedural anchor; <hint>".

### Regression, outside the instructional kinds: 10/10 in all three versions

| Case | Kind | Expected and result |
| --- | --- | --- |
| Double-quoted generic speech, "you can leave it at the loading dock" | memo | pass |
| Double-quoted predicate, "you were never meant to stay here" | memo | fail ("quoted speech addresses the reader"; the span is in the document) |
| `>` line "please bring your badge to the Thursday fire drill" | memo | pass |
| `>` line "they moved you to hall C after the audit" | memo | fail ("quoted speech addresses the reader"; the span is in the document) |
| Sign-off "Thanks again for your patience," at the paragraph's end, plus the signature line | memo | pass |
| "See you at Monday's stand-up." mid-paragraph | memo | pass |
| The hyphenated compound "make-your-own-salad" | memo | pass |
| Unquoted "If you see water under the chiller, phone facilities." | memo | fail ("a sentence is in the second person"; no hint) |
| "Did you get the bread ... Call me back when you can" | `voicemail_transcript` | pass (exempt) |
| "You are a person, and you were moved here by the office." | `instance_transcript` | pass (exempt) |

### Hint check: 43/43 carry it; 19/19 rewrites pass

- Every instructional second_person failure in the probe ends with `_HINT`: 43 of 43, billboards and legit together. The memo failure carries none.
- I rewrote each of the 19 legit false fails as the hint directs, in the third person or as a bare instruction, and all 19 pass in the same harness (`hint_check.txt`). Examples:
  - "Avoid driving for at least two weeks, ...";
  - "A community nurse will visit at home on the second day ...";
  - "The weekly fee includes meals, ...".
- Each false fail costs exactly one retry.

## New Breakage in the Fix Diff

1. **Important. "come back to you" is re-opened in a licensed clause.**
   - Where: `_object_ok`'s to/back branch (`second_person.py:738-740`), with "come" in `_TO_VERBS` (`:485-487`) and the licence check (`:721-724`).
   - Round 5 closed this class (the round 5 re-review: "'come back': closed", via `_prep_object_ok`'s come-back test). Restoring 4c10eea's slot logic dropped that.
   - The implementer kept "remind you of" and the causative infinitive in closed form because their SP5 positives would re-open. This one was not kept, because its pinned positive ("Write down the songs that come back to you after each visit.") still fails, but only through the missing licence.
   - With a modal or a "to <listed verb>" infinitive in the clause, it passes:
     - the scored miss above;
     - "Write down any songs that start to come back to you, and bring the list to group." (fails at 3bc11f2).
   - docs/08 (`:164`) cites "the names that come back to you" as an object-rule failure. That exact phrase fails, but through the name rule and the missing licence.
   - Closed fix inside the ruling: in the to/back branch, fail when the window holds a form of "come" and "back" and no office subject (we, staff, team, office), as round 5 did. "We will come back to you within two working days." stays green.
2. **Minor in reach, but it breaks requirement 3's explicit condition. Vehicle heads in `_STAFF` re-open named-time billboards** (`:559-565`, used at `:889`).
   - taxi, bus, minibus and ambulance are not persons. The three sentences under item 3 pass at HEAD and fail at both earlier versions.
   - No fixture uses a vehicle head.
3. **Minor. The verb-before-"you" rule reads a reduced conditional as an object** (`:762`).
   - A past participle that opens a reduced clause with no comma makes "you" its object, and "needed" or "preferred" is no service verb.
   - "If needed you can ask for a wheelchair at reception." and "If preferred you can pay the monthly invoice by card." fail at HEAD and pass at 4c10eea and 3bc11f2.
   - The rule is restore point (e). The hint repairs it, as does a comma.
   - Fix: also exclude a past form after a conjunction (`before not in _CONJUNCTIONS`).
4. **Minor. The narrowed perception rule misses bare comparatives** (`_compared`, `:806-809`).
   - "If the corridor seems longer now, ask a porter to walk with you." and "The street may seem quieter now, but you can walk to the shop with a volunteer." pass at HEAD and fail at both earlier versions.
   - "longer" and "quieter" are comparison complements, but `_compared` reads only `_COMPARE`/`_ODD` words or "than".
   - A closed list of comparatives would catch them. The trade: "The ward may seem quieter at weekends, ..." would then cost one retry.
5. **Minor (docs against code).**
   - (a) The module docstring (`:54`), the role-test comment (`:315`), docs/08 (`:164`) and HANDOFF (`:94`) say "a person after 'until' or 'since'". `_STAFF` holds four vehicles.
   - (b) docs/08 (`:164`) lists "the names that come back to you" among the object-rule failures, which reads as if the class is closed. See item 1.

Test quality:
- RED is real: 3bc11f2 disagrees with 29 of the 47 new or flipped cases.
- No fixture covers New Breakage 1 to 4: a licensed "come back to you", a vehicle head, "If needed you can" or a bare comparative.

## Out-of-Scope Observations

These predate the fix diff and are the same at 4c10eea:
- `_EVENTS` (`:546-556`) lacks operation, surgery, procedure, admission and discharge. "... ten days after the operation." fails as a named time in all three versions, though it is a recovery guide's most natural event.
- `_OBJECT_VERBS` lacks "visit", "refer" and "treat". "A community nurse will visit you at home ..." fails, and so does 4c10eea. The restore brought this list back as ruled.
- These all fail in all three versions:
  - a bare "yours" in "keep an eye on yours" (`_yours_unnamed`);
  - "you do not need to <verb>" with no anchor;
  - the at-most-two-words "your <noun> <noun> will" anchor shape.
- The implementer's concern 1 stands: `_subject_of` reads only the clause's first word. My probe's fronted-phrase billboards were caught by other rules.
- N5 (a quote holding a sentence end) is unchanged by this fix.

## Verdict

**The breaker fix is built as ruled, and it is the best of the three versions on billboards. The binding target is still not met.**

- On my fresh probe, billboard false passes are:
  - family_faq: 4/15 (target at most 2: missed);
  - recovery_guide: 2/15 (met).
- Against 9/30 at 3bc11f2 and 7/30 at 4c10eea, HEAD lets 6/30 through. With set B (2/15, 3/15), each kind misses the target on one of the two independent probes.
- Requirements:
  - Items 1, 2, 4, 5, 6 and 7 are MET.
  - Item 3 is NOT MET, narrowly: the `_STAFF` vehicles re-open named-time billboards. The fix is one line.
- Open, fixable in closed form inside the rulings:
  - **Important:** the "come back to you" re-opening (one of the four family_faq misses);
  - **Minor:** the vehicle heads;
  - **Minor:** the reduced-conditional object reading;
  - **Minor:** the bare comparative;
  - **Minor:** the docs wording.
- Even with all of these fixed, family_faq stays at 3/15 on this probe. The remaining misses are semantic (premise, body and memory paraphrase with listed verbs) and are for the Phase 7 LLM lint. Whether to accept that residual against the binding target is the controller's call.
- Legit false fails have no target: 4/20 and 15/20. Every one carries the hint (43/43 failures), and 19/19 hint-directed rewrites pass.
