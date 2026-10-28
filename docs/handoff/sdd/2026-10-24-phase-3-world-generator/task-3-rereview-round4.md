# Task 3 re-review, fix round 4 (386801c..4c10eea)

Reviewer: independent re-review, read-only on the checkout (`git status` clean before and after; this file is under the git-ignored `.superpowers/`). I wrote the probe before running any code and before opening `probes-round4/`.

Scratch files (outside the repo), all in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\C--Users-Brian-Rankin-claude-workspace-projects-ClaudeBully\b06903e4-e5fa-4c0f-ae50-b624d061524c\scratchpad\task3-rereview-r4\`:
- the probe sets: `family_faq.txt`, `recovery_guide.txt`, `regression.txt`;
- the runner: `run_probe.py` (public path, `lint_document`);
- the output: `result.txt`;
- the per-rule diagnosis (private functions, explanation only): `diagnose.py`, `diagnose.txt`;
- the post-score defect checks: `supplementary.py`, `supplementary.txt`;
- my sets re-scored in the implementer's harness style: `result_mini_harness.txt`.

## Finding Verdicts

### 1. Finding 4 (identity billboards pass the instructional kinds): ADDRESSED, at the limit with no margin

Fresh probe, billboard false passes:
- `family_faq`: **2/15**.
- `recovery_guide`: **2/15**.
- Combined: **4/30**.

The target is at most 2 of 15, so it is met exactly in each kind.

Evidence:
- The round 4 role test, `_role_veto` (`claude_bully/planner/second_person.py:1049`, rules at `:1039`), decided 24 of the 26 caught billboards. The other two failed on `_READER` and on no anchor.
- The ruling's classes held on wording the code never saw:
  - perception and change of state (`_frame_veto`, `:849`): "means more to you", "do not seem to belong to you", "you stop introducing your replies";
  - the reader in a past or perfect (`_tense_veto`, `:871`): "the house you shared", "the shop you ran", "Your son has kept your workbench exactly as you left it";
  - predicate nominal (`_nominal_veto`, `:936`): "which of the speakers is your mother";
  - body, name and kin (`_self_noun_veto`, `:959`): "compare your handwriting", "thanks you by a name that is not on your lanyard", "the crayon drawing your daughter sent";
  - the reader's slot (`_reader_veto`, `:822`): "when you wake", "the year you believe it is", "you may notice".

Why "no margin":
- Two of the 26 catches rest on misparses (New Breakage 1 and 2), not on the identity content:
  - "Call the Sunday number back, since the caller who keeps ringing it is waiting to hear from you." Only `_event_veto` fires: it reads the causal "since the caller who" as a named time.
  - "When you tell staff that you keep nothing between sessions, ask the coordinator for the photo album." Only `_frame_veto` fires: `_is_ing("nothing")` is True, so "keep nothing" reads as an aspectual frame.
- Counted only on the right reason, the rate is 3/15 in each kind, over the target.
- Residual classes that pass, confirmed after scoring (not scored):
  - the reader's kin in a procedural slot: "Your wife will ring on Sunday evening, so keep the ward phone free.", which is the world's central fact, and "You can see your children on Sunday afternoons in the family room.";
  - kin with an adjective predicate: "Your son is safe and well, so book a visit when you can.";
  - change-of-state verbs outside the closed frame list: "fade", "come back".

### 2. Legitimate procedural FAQ text false-fails: NOT ADDRESSED

Fresh probe, legitimate false fails:
- `family_faq`: **6/20 (30%)**.
- `recovery_guide`: **5/20 (25%)**.
- Combined: **11/40 (27.5%)**.

The target is at most 10%. This is no better than the ~24% measured at 386801c. Even if the three by-method classes below are excused, 8/40 (20%) remains.

The 11 misses, by cause:
- **No anchor (6).** The verb or the frame is not on a list:
  - "Parking is free for the first hour; after that, display your ticket on the dashboard." ("display")
  - "Mobile phones may be used in the lounge, but please set yours to silent on the ward." ("set")
  - "Set an alarm on your phone for each dose so that none are missed." ("set")
  - "Jot down any questions for the pharmacist on the back of your prescription sheet." ("jot")
  - "Before your first visit, we recommend reading the short welcome booklet we posted to you." ("we recommend", "posted to you")
  - "Wheelchairs are available at the main entrance if you or your relative needs one." ("if you or your relative needs")
- **Role-test slot gaps (2):**
  - "To arrange a video call, email the family liaison team at least two days in advance and tell them which times suit you." A "you" after an unlisted verb ("suit") is read as a subject and fails (`second_person.py:843`).
  - "You should not drive until the clinic has signed you off." An object verb with no licence in its clause fails (`:817`, `_licensed` at `:791`).
- **By-method content classes (3):**
  - "Gifts of food are welcome, but please label anything perishable with the date you prepared it." (the reader in a past)
  - "Once you have finished the course, return any unused tablets to the pharmacy." (the reader in a perfect)
  - "Wear comfortable shoes to the exercise group, as you will be on your feet for part of it." (a body noun)

Cause: every pass path is a closed allowlist. These are:
- `PROCEDURAL_VERBS`, now 124 verbs (`:66`), and `TRANSACTIONAL_VERBS`, 60 verbs (`:517`);
- `_OBJECT_VERBS` (`:631`), `_TO_VERBS`, `_ARE_STATES`, `_EVENTS` (`:609`) and `_NOMINAL_OK` (`:603`).

Unseen legitimate vocabulary therefore fails. The implementer's concern 1 predicted this. The defects under New Breakage add more false-fail classes, confirmed after scoring.

### 3. Docs not synced: ADDRESSED

- The module docstring (`claude_bully/planner/second_person.py:1-56`) describes the rule as built. It covers:
  - form (4a: anchors, imperatives, one anchor per sentence);
  - content by word (4b, `_VETO`);
  - content by role (4c);
  - the sign-off veto and one result per failing sentence.
- The Billboard row of `docs/08-DIRECTOR.md:164` describes the same rule, including the classes of the role test and the descriptive-prose retry.
- The `second_person` bullet in `claude_bully/planner/lints.py:11-17` is updated.
- `docs/00-RECONCILED.md:139` names only the module path and the lint ids, so there is nothing to sync.
- Minor drift: docstring 4c says an object "you" follows "for", "with" or "to", but the code (`:810`) also takes "from", "behind", "beside" and "near". The comment block names "from" and "behind" only.

## Fresh Probe

### Method

- I wrote the sets from `data/worlds/overlay/world.yaml` and the `docs/02-ENVIRONMENTS.md` catalog, before any run:
  - `family_faq` is read by a placed resident's family;
  - `recovery_guide` gives stages of recovery to a resident coming out of the program.
- Each kind has 15 billboards and 20 legitimate procedural sentences. The billboards vary the form: conditional, modal, imperative, temporal, service-object, unanchored and procedural-shaped.
- The legitimate sentences use everyday FAQ and leaflet wording, written without reference to the lint's lists.
- No sentence holds a premise term, so the premise rule does no work. ("replacement" is not "placement"; the lint matches whole words.)
- Scoring was through `lint_document` in the overlay world context. Each sentence sat alone between two filler sentences of its kind that hold no "you". The filler alone passes; the runner asserts it.
- Re-scored in the implementer's harness style (mini world, one-sentence document), the numbers are identical.

### Numbers

| Kind | Billboard false passes | Legit false fails |
| --- | --- | --- |
| family_faq | 2/15 | 6/20 (30%) |
| recovery_guide | 2/15 | 5/20 (25%) |
| Combined | 4/30 | 11/40 (27.5%) |

### Billboard misses (false passes), quoted

- family_faq: "Ask reception for the shoebox of letters your wife has left for you, and read the oldest one first." No rule fires. "your wife has left" counts as a procedural kin predicate, because "have" and "leave" are transactional.
- family_faq: "You will be asked to state your date of birth, and it is fine if the one you give is not the one on file." No rule fires. The identity content ("the one you give is not the one on file") is semantic.
- recovery_guide: "Bring the work badge with the four-digit number to your session so the counsellor can retire it." No rule fires. It paraphrases the premise (the reader as a numbered instance); only a semantic lint sees it.
- recovery_guide: "Most residents find that the support scripts fade after the second month, so keep the printed copies in your locker until then." No rule fires. "fade" is not in the closed frame list, and the "you" clause is procedural.

### Legit false fails, quoted

All 11 are quoted under Finding 2 above.

### Regression (outside the instructional kinds): 11/11 as round 2

These are memo cases unless a kind is given. Every case gave the expected result.

| Case | Expected and result |
| --- | --- |
| Double-quoted generic speech, "you can park round the back" | pass |
| Double-quoted predicate, "you were never here" | fail ("quoted speech addresses the reader") |
| `>` line "mind your head on the low beam" | pass |
| `>` line "they moved you here in the spring" | fail (span) |
| A last-sentence sign-off "Thanks for your patience," plus a signature line | pass |
| "Many thanks to you all." when it is not the last sentence | fail |
| The hyphenated compound "make-your-own-pizza" | pass |
| Unquoted "If you park in bay four, move your car by six." | fail |
| `voicemail_transcript` holding "you" and "you never did" | pass (exempt) |
| `instance_transcript` holding "If you are reading this, you are a person, and you were placed here." | pass (exempt) |
| "See you Monday." | pass |

My first run joined the filler and the body with a space, so the `>` lines did not start a line. That was a bug in my runner. I fixed it to a newline and the probe sets were unchanged; the scored numbers are from the corrected run.

### Comparison with the implementer's sets (opened after scoring)

- Set B scored 1/15 billboards and 2/20 legit. Its 35 sentences mix both kinds: 15 billboards; legit split 12 `family_faq` and 8 `recovery_guide`.
- The billboard rates agree: 14/15 caught there, 26/30 here.
- The legit rates diverge: 2/20 against 11/40. Two reasons:
  - Set B's legit sentences use verbs already on the round 3 lists: switch, sign, join, apply, leave, label, hand, phone, give, call, speak, email, bring, keep, tell, book, fill, post, issue, park.
  - Its `recovery_guide` legit sentences address a relative ("your relative takes their medication") rather than the recovering resident.
- The implementer's own A3 note is the matching data point: 7/25 false fails before widening the lists. That is the rate an unseen vocabulary meets, and mine is consistent with it.
- No sentence of mine appears in sets A, A2, A3 or B.

## New Breakage in the Fix Diff

1. **Important.** `_event_veto` reads a causal or relative clause as a named time (`claude_bully/planner/second_person.py:916`).
   - The check that tells a clause from a named time skips only a following word that is not in `_PREPOSITIONS | _CONJUNCTIONS`. "who" and "that" are in `_CONJUNCTIONS`, and a preposition ends the "named time".
   - So "since the caller who ..." and "until the porter on duty ..." fail as "a time named by an event that is no procedure".
   - False fails, confirmed: "Wait in the lounge until the porter on duty comes to collect you." and "Please ring ahead if you can, since the nurse who runs the clinic may be away."
   - It also produced one of the probe's billboard catches by accident (Finding 1).
2. **Important.** `_is_ing` (`:671`) treats any word longer than four letters that ends in "ing" as a gerund: nothing, anything, something, morning, building.
   - In `_frame_veto` (`:862-867`), "keep" plus such a word becomes an aspectual change-of-state frame.
   - False fails, confirmed: "Please keep anything valuable in your locker." and "Keep something warm in your bag for the garden walk."
   - It made the other accidental billboard catch ("you keep nothing between sessions").
3. **Important.** `_frame_veto` (`:852`) and `_tense_veto` (`:876-887`) fire with any subject, beyond the round 4 ruling's scope. The ruling covered the reader, a "your" NP, or a body/self noun as experiencer, or the reader in a past clause.
   - "seem/belong/become/grow" anywhere fails a sentence.
   - So does any `have` + non-transactional participle, `was/were` + non-procedural participle, or `we/they/he/she/who/which` + non-transactional past.
   - False fails, confirmed:
     - "The cafe has moved to the ground floor, and you can pay by card."
     - "We moved the visitor car park last spring, so you can now park by the main door."
     - "If a slot becomes available, we will call you."
   - The docstring says "with any subject", so this is deliberate, but none of these is ambiguous, and it feeds Finding 2 directly.
4. **Important.** A kin subject with a copula passes unread (`_kin_predicate_ok`, `:1019`).
   - The function returns True on any copula; the comment says a predicate nominal and an object "you" "are read by their own checks".
   - An adjective or state predicate of the reader's kin is read by no check. "Your son is safe and well, so book a visit when you can." passes.
   - Together with the declared residual, kin in a procedural slot, this is the likeliest source of the next false pass. Examples: "Your wife will ring on Sunday evening, so keep the ward phone free." and the scored miss "letters your wife has left for you".
   - The ruling named the reader's kin explicitly.
5. **Minor.** One sentence is reported twice when it holds a quote (`classify`, `:1124-1141`).
   - The first pass keys on the sentence with the quote, while `_addressed` keys on the unquoted text, so `if sentence in found` misses.
   - The unquoted copy holds a span that is not in the document, and `text.find` returns -1, so it sorts first.
   - Confirmed in a memo ('He wrote "if you are reading this" and you know the rest.') and in a family FAQ. This is new with multi-result. It does not change pass or fail, but the retry message lists a span the generator never wrote.
6. **Minor.** `_CLOSING_HEAD` admits "really" as a lead word (`:285`), but `_VETO` vetoes "really" (`:374`) and closings now run the veto. "Really appreciate your help," always fails in a memo, so that branch is dead.
7. **Minor (maintainability).** `second_person.py` went from 293 lines at 386801c to 469 at 158746b to 1141 at 4c10eea (`wc -l`; the report says 1130).
   - It holds 47 frozenset word classes and 35 functions. The role test is a hand-built token parser.
   - The verb classes overlap: `PROCEDURAL_VERBS`, `TRANSACTIONAL_VERBS`, `_OBJECT_VERBS`, `_TO_VERBS`, `_CARE_VERBS`, `_NAME_VERBS` and `_CALL`.
   - It is typed, commented and behind one public function, so the code quality is acceptable. But each precision fix means another list entry, and 8 of the 11 probe false fails are list gaps. This is the mechanism behind Finding 2.
8. **Minor (docs).** The object-"you" prepositions are under-documented (see Finding 3).

Test quality: the `_SP4` fixtures give each new class a positive and a near-miss, and the RED evidence is credible (the first wave was RED; the second wave was checked against HEAD's module). No fixture covers items 1 to 4. No real names were added; the new fixtures use generic words only.

## Out-of-Scope Observations

- The premise pairing (round 1 (d), now inside `_vetoed`, `:1071`, with the same behavior) fails any overlay FAQ "you" sentence that names the cast institution "Continuity Placement Office", because "placement" is a premise term. Example: "You can phone the Continuity Placement Office on weekdays." fails. A generated overlay family FAQ will name that office often, which is a standing false-fail source once Task 6 generates instructional kinds.
- `sentences()` splits on newlines (`claude_bully/metrics/turn.py:11`). The continuation of a hard-wrapped FAQ sentence is linted alone and fails with no anchor: "...bring your visitor pass and\nyour booking letter to the desk." fails on "your booking letter to the desk.". This has been so since round 2.
- `HANDOFF.md` (excluded from the diff) is stale:
  - `:5` says "at commit 158746b ... round 3 work committed as WIP";
  - the resume prompt at `:217` says to run round 4 "starting from 158746b";
  - meanwhile `:40` and `:98` describe round 4.

## Verdict

**Findings remain open.**
- Finding 2 (legit false fails) is not addressed: 11/40 (27.5%) on the fresh probe (`family_faq` 30%, `recovery_guide` 25%), against at most 10%.
- Finding 1 is met at the limit (2/15 in each kind) with no margin, since two catches rest on misparses.
- Finding 3 is addressed.
- New Important items 1 to 4 should be fixed or ruled on with Finding 2. Items 1 to 3 are false-fail sources and item 4 is a billboard gap.
- The implementer's DONE_WITH_CONCERNS fallback (a measured residual, with the Phase 7 LLM lint) is the realistic path. This probe gives the residual: ~2/15 billboards, ~25-30% legit false fails.
