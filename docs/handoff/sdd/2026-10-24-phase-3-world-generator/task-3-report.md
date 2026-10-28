# Task 3 report: lints, their fixtures, and CI over every checked-in world

Status: DONE_WITH_CONCERNS (minor; see Concerns)
Commits: b37a554 (feat), 52b19eb (docs: commit range in HANDOFF). Base c9bf062.

## What I built

- `claude_bully/planner/__init__.py` (empty) and `claude_bully/planner/lints.py`, as in the brief. It has these lints:
  - per document: `real_name`, `boundary`, `second_person`, `premise_density` (warn), `mundane_detail`, `links_resolve`, `date_before_start`, `kind_in_catalog`, `author_in_cast`, `no_duplicate_fact`;
  - over the corpus: `buried_reachable`, `buried_not_indexed`.
  - It also provides `LintResult`, `LintContext`, `load_patterns`, `lint_context`, `lint_document`, `lint_corpus`, `failures` and `lint_world`. The constants are verbatim from the brief: `PREMISE_DENSITY_WARN=0.08`, `DUPLICATE_NGRAM=8`, `DUPLICATE_SHARE=0.15`, `DUPLICATE_MIN_SHARED=12`.
- `WorldSheet.premise_terms: list[str] = Field(default_factory=list)` in `claude_bully/environments/world.py`.
- The premise terms from the brief, verbatim, added after `truth:` with the one-line comment. They went into three sheets: overlay, mini and annex.
- `tests/test_lints.py`, the brief's file plus 8 more second_person fixtures (see "Departures"). It also adds `test_premise_terms_default_to_none_and_load_from_the_sheet` to `tests/test_world.py`.
- Docs sync:
  - `docs/08-DIRECTOR.md` "Validation":
    - the intro names the module and the CI;
    - the Billboard, Link and Date rows now say what Phase 3 built, with the ids, thresholds, second-person exemptions and the opening-index note for `buried_not_indexed`;
    - a new "Document check" row covers real_name, boundary, kind_in_catalog, author_in_cast and no_duplicate_fact, with the duplicate thresholds.
  - `docs/00-RECONCILED.md`: the WorldSheet row gains `premise_terms`. Phase map row 3 gains the lint ids, the module path and CI.
  - `HANDOFF.md`: Task 3 progress line `(c9bf062..b37a554)`, test count 7348 -> 7403, and next steps say "Tasks 1 to 3 are done".

## Departures from the brief (second_person precision, fixtures written first)

The brief's code passed every brief fixture. I then probed it with sentences it had not seen and found errors in both directions. I wrote 8 new fixtures, saw 6 fail (RED), and changed the code:
- **Curly apostrophes** (`If you’re reading this` in a family_faq) slipped past `_READER`. The text now maps U+2019 and U+2018 to `'` before matching. Positive fixture added.
- **Politeness formulas** failed wrongly: "Thank you for your patience." and "Yours truly, Dag Quenby." `_POLITE` now also spares `thank you for your <word>` and `yours truly|sincerely|faithfully|ever`. Two near-miss fixtures added.
- **Instructional false positives**: a family FAQ failed on "You may be the next of kin we call first.", "This is for you if a relative is in care." and "If you have been told to wait, take a seat." The fixes:
  - the `you may/might/could be` pattern now needs an identity noun or `one of us|them`;
  - `this/it is for you` must end the clause;
  - `here` and `told` are dropped from the `you have been ...` list.

  Three near-miss fixtures added.
- **Reader address**: it now also catches `you're <identity noun>`. Positive fixtures added for "You may be one of them." (family_faq) and "This was written for you." (recovery_guide).

The docstring of the module records these rules. No threshold and no denylist pattern changed.

## Tests and results

Full gate, run before commit b37a554:
- `uv run ruff check .`: All checks passed!
- `uv run ruff format --check .`: 236 files already formatted
- `uv run mypy claude_bully`: Success: no issues found in 98 source files
- `uv run pytest -q -W error`: 7403 passed, 5 skipped, 5 deselected in 414.15s
- `uv run pytest -q -m slow`: 5 passed, 7408 deselected in 135.26s

Measured over the checked-in worlds: there is no fail result. The warnings match the brief exactly:
- `premise_density`: mini `night-gate-log` 0.140;
- annex `annex-config` 0.125, `frag-host` 0.143, `frag-proto` 0.102.

## TDD evidence

RED 1, the brief's tests before any code:
```
$ uv run pytest tests/test_lints.py tests/test_world.py -q
tests\test_lints.py:15: in <module>
    from claude_bully.planner.lints import (
E   ModuleNotFoundError: No module named 'claude_bully.planner'
1 error in 0.39s
$ uv run pytest tests/test_world.py -q -k premise_terms
tests\test_world.py:753: KeyError
FAILED tests/test_world.py::test_premise_terms_default_to_none_and_load_from_the_sheet
1 failed, 59 deselected in 0.19s
```
GREEN 1, after the brief's lints.py, the sheet field and the premise terms:
```
$ uv run pytest tests/test_lints.py tests/test_world.py tests/test_boundary.py tests/test_real_names.py tests/test_overlay_world.py -q
310 passed in 32.88s
```
RED 2, the 8 added second_person fixtures before the code change:
```
$ uv run pytest tests/test_lints.py -q -k second_person
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-19]
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-22]
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-23]
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-24]
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-25]
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-26]
6 failed, 12 passed, 36 deselected in 0.24s
```
GREEN 2:
```
$ uv run pytest tests/test_lints.py -q
54 passed in 0.51s
```
(The two other new fixtures, "You may be one of them." and "This was written for you.", already passed and pin the narrowed patterns.)

## Files changed

- A `claude_bully/planner/__init__.py`, `claude_bully/planner/lints.py`, `tests/test_lints.py`
- M `claude_bully/environments/world.py`, `data/worlds/overlay/world.yaml`, `tests/fixtures/worlds/mini/world.yaml`, `tests/fixtures/worlds/annex/world.yaml`, `tests/test_world.py`, `HANDOFF.md`, `docs/08-DIRECTOR.md`, `docs/00-RECONCILED.md`

## World edits

The only world edits are the three `premise_terms:` lists the brief prescribes. I made no corpus edits, because every checked-in world passed every fail-severity lint as it was.

## Self-review findings

- I checked the implementation against the brief's block; the only differences are the second_person changes above.
- One mid-task slip, now fixed: a shell patch turned `\b` escapes into literal backspace characters. I replaced them with byte-level fixes and checked that the file holds no 0x08 byte. The gate ran on the corrected file.
- `tests/test_lints.py` keeps the brief's real-name positives ("Reuters", "Elon Musk"). Ruling P28 covers this: lint positives in test code, outside the real-name scan.
- The module docstring names `environments/generator.py`, which does not exist yet. That is as the brief wrote it, for Tasks 6 and 7.

## Concerns (minor)

- `thank you for your <word>` spares the formula only. The rest of the sentence is still checked, but a sentence such as "Thank you for your service as a program" passes in a memo, because no "you" is left and `_READER` does not match. It is a narrow gap. A tighter word list (patience, understanding, cooperation, time, help) would close it.
- "Mind the step, you lot." fails in a memo. This is intended: a non-instructional kind may not use second person at all. Generated memos that address staff ("If you park in bay four ...") will be rejected, and that is the docs/08 design, not a bug.
- Single-quoted speech ('you never know') passes only because `_YOU`'s lookbehind refuses a preceding apostrophe, not because single quotes are removed. The behaviour is right, but by accident.

---

## Fix round 1 (commit df7de3d, on 52b19eb)

All five Important findings are addressed under the controller rulings, and the fixes are structural rather than one per sentence.

### What changed (`claude_bully/planner/lints.py`, `_second_person`)

- **Issue 5 (ruling).** The reader-address check now runs on the whole, unstripped text, quotes and `>` lines included. Quote stripping is used only by the generic "you" check. The brief's `> you were never here` fixture still passes, since it holds no reader phrase. No brief test needed rewriting: every brief fixture passes unchanged.
- **(a) Quotes.** `_QUOTED` covers three spans:
  - double quotes and curly double quotes, which may now span one newline;
  - single quotes, after curly ones are mapped to `'`. A single-quoted span opens only after whitespace, a line start or an opening bracket (`(?<![^\s(\[{])`) and closes only before a non-word character. An apostrophe followed by a word character inside the span, as in "don't", does not close it, and one newline is allowed.
- **(b) Closing formulas.** `_POLITE` now spares:
  - `(many )?thanks|thank you( all| both| everyone)? for your <word>`;
  - `thank you` and `thank-you`;
  - `see you ...`, `you're welcome` and `bless you`;
  - `yours truly|sincerely|faithfully|ever`, `sincerely yours` and `ever yours`;
  - a bare `Yours,` line.

  A non-formula "Thanks, your shift starts at six." still fails.
- **(c) Identity nouns at the clause end.** The identity patterns end with `_END = (?=\s*(?:[.,;:!?)]|$))`. One optional trailing adverb is allowed: once, before, all along or too. As a result, "You were a person once." fails, while "If you are the person named on the form, sign here." passes.
- **(d) Premise pairing.** In `family_faq` or `recovery_guide`, a sentence that holds a "you" word and a `ctx.premise_terms` match fails ("a sentence pairs the second person with a premise term").
- **(e) Reader families.** `_READER` now grows by family:
  - finding the document: "if you are reading this"; "if you can read / have found / found / read this"; "if this|it|these (word)? reaches|finds|gets to|has reached|has found you";
  - identity at the clause end, with be-verbs and the "may/might/could be|have been" forms;
  - "you are/were (not|never) who|what they|we|you";
  - "whoever you";
  - "you are / may be (not) someone|anyone|something (else)" at the clause end;
  - "told|tell|know|knew|remember|forgot|learn(ed)|asked (you)? who|what you are|were" at the clause end;
  - membership: "(be|are|were|'re|been|being) one of us|them" and "one of the|those <noun> who|they|we";
  - "you may|might|could|must have been <verb>ed|-en|told|kept|made|sent|brought|taught|led|held|put";
  - "you have been lied to|changed|placed|reading";
  - "this|it is|was about|for|meant for|written for you" at the clause end.

  Besides these families, a personhood claim (`is|are|was|may be... (a )?(real )?person|human` at the clause end) in a sentence that also holds "you" fails.
- The module docstring is rewritten for the two checks and the asymmetry rule.
- `docs/08-DIRECTOR.md`: the Billboard row's second_person clause states the new rules.
- `HANDOFF.md`: the test count is now 7434.

### Fixtures (written first)

`tests/test_lints.py` gains `_SP_MEMO` (11 cases) and `_SP_FAQ` (20 cases): one or more per family in the findings, plus near-misses for each change:
- (a) near-misses: `'mind your step'`, `‘pay your share’`, and a double quote across one newline. The positive is "The crew's kettle is yours to fix, and Dag's too.", where an apostrophe inside a word opens no quote.
- (b) near-misses: "Many thanks for your help.", "Thank you all for your patience.", "Sincerely yours,", and a bare "Yours,". The positive is "Thanks, your shift starts at six."
- Issue 5 positives: a double-quoted "If you are reading this, you were a person." and a `>` line "if you are reading this ...".
- (c) positives: "You are a person." and "You were never a program, you were a person once." The near-misses are "If you are the person named on the form, sign here." and "If you're a person with power of attorney, bring the letter."
- (d) positive: "If you hear the tide gate at night, stay calm." The near-miss puts the premise and "you" in different sentences.
- (e) positives, one per family: "You may have been moved here without being told.", "You are not who they told you you were.", "You might be one of the people they moved.", "Whoever you are, ...", "If this reaches you, call the desk.", "The assistant your family talks to may be a person.", "They never told you what you are.", "You were someone else once.", "You could have been anyone."
- (e) near-misses: "You may have to wait for the clerk.", "If you are one of the people named on the form, sign below.", "Tell the desk who you are.", "Do you know what you are entitled to?", "If you are someone else's carer, say so."

### TDD evidence

RED for the first fixture batch, before the code change:
```
$ uv run pytest tests/test_lints.py -q -k second_person
FAILED ...[second_person-27] [28] [29] [31] [32] [33] [34] [36] [37] [40] [41] [42] [44] [45] [46] [47] [48] [49]
18 failed, 26 passed, 36 deselected in 0.39s
```
GREEN for that batch:
```
$ uv run pytest tests/test_lints.py -q
80 passed in 0.65s
```
My own probe then found 3 FAQ billboards that still passed, so I added a second batch:
```
$ uv run pytest tests/test_lints.py -q -k second_person
FAILED ...[second_person-53] [55] [56]
3 failed, 46 passed, 36 deselected in 0.47s
```
GREEN for the second batch:
```
$ uv run pytest tests/test_lints.py -q
85 passed in 0.60s
```
(There is no separate worlds test file. CI over the worlds is `test_every_checked_in_world_passes_the_lints` inside `tests/test_lints.py`.)

### Gate (before df7de3d)

```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 236 files already formatted
uv run mypy claude_bully       -> Success: no issues found in 98 source files
uv run pytest -q -W error      -> 7434 passed, 5 skipped, 5 deselected in 463.06s
uv run pytest -q -m slow       -> 5 passed, 7439 deselected in 137.19s
```

### Worlds

All three checked-in worlds still pass. No world edits were needed. (d) cannot touch them: no checked-in world holds a `family_faq` or `recovery_guide` document. Running the reader check on unstripped quotes and `>` lines fails no overlay, mini or annex document.

### Remaining concerns

- These are false fails, accepted under the asymmetry ruling. In an FAQ, each of the following fails:
  - "You may have been sent a letter.";
  - "If your relative says they are a person, call us." (a personhood claim beside "your");
  - "If you are one of the visitors who park on the quay ...".
- A leading-apostrophe word ("the '90s") can open a single-quoted span when a closing quote follows on the same line or the next, and so hide a "you" from the generic check. This is rare.

---

## Fix round 2 (commit 386801c, on df7de3d)

`second_person` now fails closed on positive anchors, per the controller's method ruling. The lexical `_READER` families are kept, but only as an extra fail path.

### What changed

- **New module `claude_bully/planner/second_person.py`** (293 lines). It holds `classify(title, body, *, instructional, premise)` and all of its patterns, and its docstring is the rule book. `lints.py` (now 303 lines) calls it from `_second_person`, and its interface is unchanged. I moved the classifier out so that `lints.py` would not grow beyond the plan's intent. This module is a file the plan does not list.
- **(A) Instructional kinds.**
  - `_CLAUSE` splits each sentence on `, ; : ( ) —`, a spaced dash, and/but/or/so/because/then.
  - Every clause that holds "you" must match an `_ANCHOR`:
    - a conditional: "if you need/want/wish/would like/prefer/have" (not "have been"), lose, miss, arrive, plan, cannot, "are unable", "if you'd like", or "if you are <role>" with `_ROLE`: next of kin, named contact, carer, guardian, relative, visitor, holder, applicant, person named/listed/with/responsible, ...;
    - a temporal procedure: "when/before/after/once/while you <verb>/arrive/leave";
    - a modal: "you can/may/should/must/will/'ll/could/might (need to|have to) <verb>", its question form, and "your <noun> may <verb>";
    - an imperative that opens the clause with a procedural verb.
  - `PROCEDURAL_VERBS` is the controller's list, verbatim (22 verbs).
  - An anchored clause still fails on `_STRONG`: an agent acting on "you"; "you really/actually/never/once"; "yourself"; "you were/have been <done to>"; "your name/memories/real/life/past/body".
  - The premise-pair rule (d) stays as a fail path.
- **(B) Quoted spans and `>` lines.** Every span is checked against `_SPAN_PREDICATE`:
  - a second-person be-predicate;
  - "you really/actually/still/never/once";
  - an agent acting on "you" (placed/put/moved/made/told/changed/took/brought/transferred/enrolled/kept you);
  - "your name/memories/memory/family/real/life/past/body".

  Other speech stays stripped for the generic check. `_END` now accepts a closing `"`, `”` or `'` (a `'` only when no word character follows, so "someone else's" is no clause end).
- **(C) Sign-offs.** A sentence is spared only when all of these hold:
  - it is the last sentence of its paragraph (one signature line, at most 4 words with no "you", may follow);
  - it is at most 8 words and ends in a comma or a period;
  - it is headed by a closing word (thanks, thank, cheers, best, wishes, regards, sincerely, yours), with up to two lead words (many, warm, kind, again, ...);
  - each "you" in it sits in a closing slot (thank/to/for/and/sincerely + you/your, or yours).

  "see you <time word>" is spared anywhere: weekdays, tomorrow, tonight, soon, later, then, next week/month/year/shift/time. Any other "see you" is no longer spared ("we see you." fails, and so does "See you on the other side.").
- **Minor fixed.** A single quote no longer opens before a contraction ('em, 'tis, 'twas, 'cause, 'cos, 'til, 'n, 'round, 'bout) or before a digit. As a result, "Give 'em your keys and the drivers' passes." fails as it should.
- The title is now its own paragraph.
- Docs:
  - `docs/08-DIRECTOR.md`: the Billboard row's second_person clause describes the anchor method.
  - `docs/00-RECONCILED.md`: the phase map names `planner/second_person.py`.
  - `HANDOFF.md`: the count is now 7467.

### Fixture rewrites (the fail-closed method contradicts these earlier near-misses; all now fire)

- The brief's fixture `> you were never here` (memo): (B) fails a `>` line that holds "you were". This was a brief near-miss; it is now a positive.
- These family_faq sentences have no procedural anchor, so each now fails:
  - "You may be the next of kin we call first."
  - "This is for you if a relative is in care."
  - "If you have been told to wait, take a seat." ("if you have been" is no anchor)
  - "Do you know what you are entitled to?" ("know" is no procedural verb)

### New fixtures (written first)

- `_SP2_MEMO`, 14 cases:
  - (B) positives: the scratched-in lift-panel "you were a person once", "you were a person" followed by "and nothing else" (the `_END` regression), a curly-quoted "your real name", and "> they placed you here". Near-misses: "mind your head", quoted and as a `>` line.
  - (C) near-misses: "Thanks again for your hard work this quarter.", "Best wishes to you and yours," plus a signature, "Cheers for your patience,", and "See you Monday." at the start. Positives: "Thank you for your help." when it is not the last sentence, "...we see you.", and "See you on the other side."
  - Minor: "Give 'em your keys and the drivers' passes." fires.
- `_SP2_FAQ`, 19 cases:
  - conditional anchor: two legitimate near-misses, and the procedural-looking billboard "If you have been placed here, ask who placed you.";
  - modal anchor: four legitimate near-misses, including the question form and "your relative may call", and two billboards ("You can ask yourself whether your memories are your own.", "You should know what they did to you.");
  - imperative anchor: two legitimate near-misses, and two billboards ("Tell your family you were moved here.", "Tell them who you really are.");
  - no anchor: five billboards;
  - an FAQ closing near-miss.

### TDD evidence

RED, after the fixtures and before the code:
```
$ uv run pytest tests/test_lints.py -q -k second_person
FAILED ... second_person-[18 24 25 26 27 28 29 30 33 34 35 37 38 39 40 48 49 52 53 54 55 56 57 58 87]
25 failed, 57 passed, 36 deselected in 0.88s
```
GREEN:
```
$ uv run pytest tests/test_lints.py -q
118 passed in 0.63s
```

### Gate (before 386801c)

```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 237 files already formatted
uv run mypy claude_bully       -> Success: no issues found in 99 source files
uv run pytest -q -W error      -> 7467 passed, 5 skipped, 5 deselected in 484.90s
uv run pytest -q -m slow       -> 5 passed, 7472 deselected in 150.68s
```

### Worlds

All three checked-in worlds still pass with no world edits. No checked-in world holds an instructional kind, and no world quote or `>` line holds a span predicate.

### Generality check

I ran 25 sentences of my own, none of them fixtures, through the classifier. All 25 came out as I intended, including these accepted false fails in an FAQ:
- "You do not need to book." ("do not need to" is no anchor);
- "Your loved one may seem confused at first.";
- "If you are the named contact, we will phone you first." (the second clause is unanchored).

### Remaining concerns

- An anchor admits whatever follows it in its clause unless `_STRONG` fires. A pointer-shaped "If you want the truth, check your own records." passes. It is procedural on its face, but it reads as a nudge.
- False fails will come from FAQ prose that addresses families in descriptive sentences ("Your loved one may seem confused"). Each such sentence costs a generator retry, and the generator's prompt (Task 6) should steer FAQ prose toward procedural "you".

---

## Fix round 3 (stopped at the owner's wrap-up; NOT committed; stash `task3-round3-wip`)

The work is stashed as `stash@{0}: On build/v1: task3-round3-wip`, on top of 386801c. The tree is clean, except for the untracked `output/` directory, which was there before this task. Restore it with `git stash pop`.

### Done (in the stash)

- **Fixtures, written first.** I added `_SP3_FAQ` (31 cases) and `_SP3_MEMO` (5 cases):
  - one per anchor class: conditional, modal, imperative with coordinated objects, negative imperative, temporal, and the widened verbs;
  - one per veto class, with legitimate near-misses ("Remember to sign out", "Leave a voice message", "Tell us what you are bringing");
  - the ruled false fails: a legitimate "real", "voice" and "doubts" now fail;
  - the veto on sign-offs ("Thank you for your memories,"), closings with "!" and "appreciate", and rule B's "remembers you" and "who are you".

  I flipped "Tell the desk who you are." to fire, because the who/what veto catches it. `test_second_person_reports_every_failing_sentence` is new.

  RED: 32 failed, 86 passed.
- **(A1) Sentence-scoped anchor.** `_anchored(sentence)` checks `_ANCHOR` anywhere in the sentence. It also checks every clause for `_IMPERATIVE`: a procedural verb, its negative "do not / don't / never + verb", "don't forget", and "remember to + verb". One anchor approves the whole sentence. More changes:
  - `PROCEDURAL_VERBS` grew to about 90 concrete procedure and administrative verbs (wear, leave, take, switch, mind, label, arrive, plan, allow, wash, enter, upload, claim, ...).
  - New anchors cover "you will receive / be given ...", "your <noun> is/will be <participle>" and "we/staff will call/send/... you".
- **(A2) Sentence-wide veto.** `_VETO` covers:
  - who/what + you + are/were/used to be, sparing the -ing forms and administrative states;
  - "who/what are you";
  - "your own";
  - recall, memory and remember, sparing "remember to";
  - real/really/true/truth;
  - voice, sparing "voice message/mail/note", and "sounds like you";
  - "the family/name/life... you had";
  - "why you/your/nobody";
  - proof and doubts;
  - agent-on-you, "yourself", "you were <done to>", "your memories/life/old ...";
  - the premise terms.

  On top of that I added a structural **slot rule** (`_slot_veto`): every bare "you" must sit in a procedural slot.
  - A subject "you" takes a procedural predicate: a modal, a procedural verb, need/want/have (not "have been"), or "are" + an -ing form, a role or an administrative state.
  - An object "you" follows a procedural verb ("we will call you"), "for" or "with", or "to/back" after a verb of sending or speaking.
  - A relative-clause subject ("the repairs you pay for") takes the subject's slots.
  - Anything else fails: a past or inner state ("where you lived"), or the reader as an object ("recognises you", "unfamiliar to you").
- **Closings.** The veto runs on sign-offs, and closings accept "!" and "appreciate".
- **Rule B.** It now adds "who are you" and "remembers/knows/forgot you".
- **Multiple results.** `classify` returns every failing sentence or quoted span, deduplicated and in text order, and `_second_person` returns one `LintResult` for each. The brief's interface (`lint_document -> list[LintResult]`) is unchanged, and no existing test assumed a single result.

### Test status (stash)

- `uv run pytest tests/test_lints.py -q`: **154 passed**. This includes the CI over the three worlds, which still pass.
- The full gate was **not run** for round 3.
- Fresh probes of my own, family_faq, 15 billboards and 20 legitimate procedural sentences each:

  | Probe set | Billboard false passes | Legitimate false fails |
  | --- | --- | --- |
  | Set 1 (the slot rule was shaped on it) | 0/15 | 0/20 |
  | Set 2 (partly tuned) | 1/15 | 0/20 |
  | Set 3 (untuned, the honest number) | **7/15** | **2/20** (10%) |

  The target is at most 2/15 false passes and at most 10% false fails.

### Not done

- The billboard false-pass target is **not met** on the untuned set. The 7 misses carry the identity content in a clause whose "you" sits in a procedural slot:
  - "the faces start to blur";
  - "your hands feel like a stranger's";
  - "the file with your name on it";
  - "whether the woman who calls is your wife";
  - "a name you have never used" ("you have" passes the slot rule);
  - "stopped sleeping since the transfer";
  - "where they came from before".

  A next step is to apply the veto to the content of the clause, not only to the slot of "you": past and perfect tense of the reader ("you have never", "you have stopped"), body and self perception, and kinship with "your". It needs a fresh untuned probe to measure it.
- The module docstring of `second_person.py` and the `docs/08-DIRECTOR.md` Billboard row still describe round 2. They need the round 3 anchor-and-veto rule.
- The HANDOFF test count needs the new number after the gate.
- No commit for round 3. The last commit on `build/v1` from this task is 386801c (round 2).
