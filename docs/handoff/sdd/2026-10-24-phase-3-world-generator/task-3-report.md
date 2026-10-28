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

---

## Fix round 4 (commit 4c10eea, on 158746b)

Status: DONE_WITH_CONCERNS. Both targets are met on my held-out set B (billboards 1/15, legit 2/20 = 10%), but the false-fail number sits exactly on the limit, and the fail-closed vocabulary is the main exposure on an unseen probe (see Concerns).

### What changed

The round 3 structure stays: the anchor decides form, the vetoes decide content. The round 3 slot rule (`_slot_veto`, string regexes on the text after each "you") is replaced by a **role test**, `_role_veto` in `claude_bully/planner/second_person.py`. It reads every clause of an instructional "you" sentence on lowercase tokens with contractions expanded (`_tokens`). The reader may be only the agent of a procedure or the recipient of a service. Each class is fail-closed where it can be: a pass-side allowlist, so unseen wording fails.

| Class (ruling) | Rule | Fail-closed list |
| --- | --- | --- |
| Experiencer, change of state | `_frame_veto`: seem, appear to, look/sound like or familiar, feel (except "feel free/unwell"), "as if", "mean nothing to", belong, become, grow, with any subject; an aspectual verb (start, begin, stop, keep, continue) over a verb that is not procedural, and any past aspectual ("stopped", "began") | the procedural verb forms |
| Experiencer, the reader as subject | `_subject_ok`: a subject "you" takes a modal or "do not" before a procedural verb or a procedural passive (or an elided verb, "as soon as you can"), need, want, prefer, "feel unwell", "forget your pass", "are" before an administrative state, a role or a procedural -ing, a perfect or past of a transactional verb, or a present procedural verb. "You may notice", "you will probably find" and "you think" fail | `PROCEDURAL_VERBS`, `TRANSACTIONAL_VERBS`, `_ARE_STATES` |
| Experiencer, a "your" NP or a body/self noun | `_self_noun_veto`: "your" + a body or self noun (`_BODY_SELF`: name, face, hands, voice, thoughts, ...) stands only as the object of a care or writing verb ("wash your hands", "write your name"); under "the" or "a" it takes no action ("the faces blur"); a name stands only in a writing slot, under a third party's possessive, before "of" or in a compound; the reader's kin (`_KIN`) take a procedural predicate only; "your bed/room/ward" (`_RESIDENCE`) makes the reader a patient | care and writing verbs, compound heads |
| Predicate nominal | `_nominal_veto`: a copula before "you", "yours" or a "your" NP fails unless the NP is procedural ("this is your booking reference", `_NOMINAL_OK`); an inverted question ("are you the named contact?") is not one; a bare "yours" fails outside a sign-off and "yours to keep" | `_NOMINAL_OK` |
| Past or perfect | `_tense_veto`: a past after a subject pronoun, a perfect, or a past passive must use a transactional verb (`TRANSACTIONAL_VERBS`: book, pay, send, sign, call, ...); "never" in a perfect and "used to" fail outright | `TRANSACTIONAL_VERBS` |
| Time named by an event | `_event_veto`: "before/after/since/until/during the X" and "the day of the X" need a procedural event or a clock time (`_EVENTS`); "from before", "ever since" and "since then" fail; a third party's event ("your relative's discharge") and a clause ("since the ward is busy") are skipped | `_EVENTS` |
| The reader as object | `_object_ok`: an object "you" follows a service verb, "for", "with", "from", "behind", or "to" after a verb of sending or speaking, and is licensed in its clause by a modal, an infinitive "to", "please", "we", "staff", "let" or an imperative that opens the clause. "The children who visit call you", "the names that come back to you", "remind you of home", "call you Dad" and "about you" fail | the service verbs |

Form-side changes (anchors, `_ANCHOR`): "if/unless you <procedural verb>"; "want/wish/like to" in the modal tail; "if/when you are <-ing>", "are you <-ing>", "have you <participle>"; "you must/will/should be" (a speculative "you may be" stays unanchored, so the round 2 fixture "You may be the next of kin we call first." still fires); "you are welcome/allowed/... to <verb>"; "you can do it"; "thank you for"; an office service with any subject under a modal ("the coordinator will explain it to you", "we will come back to you"). `_ROLE` takes the modifiers main, primary, usual, only, registered, nominated and lead. `PROCEDURAL_VERBS` gains 34 common visiting and admin verbs (join, top, support, help, explain, talk, ...). Every new anchor only approves form; the vetoes and the role test still read the content.

`lints.py` is unchanged except for its module docstring's `second_person` bullet. The interface (`lint_document -> list[LintResult]`, one result per failing sentence) is unchanged. No threshold, no denylist and no world changed.

### Probe sets (method)

I wrote set A (15 billboards, 20 legit) and set B (15 billboards, 20 legit) before any code change, both in family_faq and recovery_guide, as a generator would write them for this world, and with no premise terms (so the premise rule does no work). I tuned on A, then widened the tuning data with A2 (15 billboards, 30 legit, written after the first code pass) and A3 (25 legit), all before set B was run. I ran B once, at the end. Files: `.superpowers/sdd/2026-10-24-phase-3-world-generator/probes-round4/` (`set_a.txt`, `set_a2.txt`, `set_a3.txt`, `set_b.txt`, `run_probe.py`, `set_b_result.txt`, `set_b_final.txt`), git-ignored. The runner lints each sentence as a one-sentence document in the mini world context, as the tests do.

| Set | Code | Billboard false passes | Legit false fails |
| --- | --- | --- | --- |
| A | HEAD (round 3) | 7/15 | 2/20 |
| A | round 4 | 0/15 | 1/20 |
| A2 (tuning) | round 4 | 1/15 | 1/30 |
| A3 (tuning) | round 4 | none | 0/25 |
| **B (held out, run once)** | **round 4** | **1/15** | **2/20 (10%)** |
| B | HEAD (round 3), for comparison only | 3/15 | 4/20 |

After the first B run, my self-review fixed four bugs that B did not point to: `_is_past("has")`, "your family member/doctor", a causal "since the ward is busy", and "he can sign you in". I re-ran B on the final code: the same result, 1/15 and 2/20.

Set B's misses, quoted:
- false pass (family_faq): "When your son talks about the farm, let him finish, since the details may help you picture the place." The kin subject takes a procedural-list verb ("talk"), and the object "you" is licensed by "may"; nothing reads the bare infinitive after "help you" ("picture").
- false fail (family_faq): "You will need photo ID the first time you visit." No anchor: the modal anchor wants "need to <verb>", not "need <noun>". The role test passes it.
- false fail (recovery_guide): "If you forget your pass, the reception staff can issue a day badge." No anchor: "if you forget" is not in the conditional anchor. The role test passes it.

I did not tune on these. Both false fails are anchor (form) gaps, and each is a one-line anchor addition ("you <modal> need <noun>", "if you forget"). They are left for the controller's call, since adding them now would launder set B.

### Fixtures (written first) and RED

`tests/test_lints.py` gains `_SP4`: 46 cases in family_faq and recovery_guide, one or more per rule class, each with a legitimate near-miss.
- First wave (32, written before any code): perception frames, the reader as subject (modal, "feel"), change of state, past and perfect, predicate nominal, name and body, time named by an event, the reader as object, the "if you <verb>" anchor.
- Second wave (14, for the classes the tuning probe found): residence, "yours", "call you <name>", the widened anchors ("you must be over eighteen", "you are welcome to", "explain ... to you", "if you are travelling", "as soon as you can", "would rather").

RED for the first wave, before any code change:
```
$ uv run pytest tests/test_lints.py -q -k second_person
18 failed, 132 passed, 36 deselected in 0.40s
FAILED ...[second_person-126] [127] [129] [130] [132] [133] [137] [138] [141] [142] [144] [145] [149] [152] [153] [154] [155] [157]
```
The second wave was written after its code, during tuning. As RED evidence I ran the whole fixture file against HEAD's `second_person.py`: I swapped the file in from `git show HEAD:...` and restored it from a scratch copy, checked with `cmp`. No stash and no reset.
```
$ uv run pytest tests/test_lints.py -q -k second_person    # HEAD's second_person.py
25 failed, 138 passed, 36 deselected in 0.48s
FAILED ... the 18 above, plus [158] [162] [163] [164] [166] [167] [168]
```
The other second-wave cases already passed at HEAD and now pin the tightened modal rule's exceptions. (Fixture 133 was later shortened for line length, from "you can ask a nurse for the list" to "you can ask for the list"; it fires the same way.)

GREEN:
```
$ uv run pytest tests/test_lints.py -q
199 passed
```
No earlier fixture was relabelled.

### Gate (before 4c10eea)

```
uv run ruff format --check .  -> 236 files already formatted
uv run ruff check .           -> All checks passed!
uv run mypy claude_bully      -> Success: no issues found in 99 source files
uv run pytest -q -W error     -> 7548 passed, 5 skipped, 5 deselected in 408.64s (0 warnings)
uv run pytest -q -m slow      -> 5 passed, 7553 deselected in 102.10s
```

### Docs updated

- `claude_bully/planner/second_person.py`: the module docstring is rewritten as the rule book of rounds 3 and 4. It covers form (anchors and imperatives), content by word (`_VETO`) and content by role (`_role_veto`). The role test's comment block has the detail.
- `claude_bully/planner/lints.py`: the `second_person` bullet of the module docstring.
- `docs/08-DIRECTOR.md`, Billboard row: the instructional-kind rule as built (anchor, veto, role test and its classes, one result per failing sentence, descriptive FAQ prose failing as a retry), plus round 3's quoted-span predicates and sign-off veto.
- `docs/00-RECONCILED.md`: checked. It names the module and the lint ids only, so there was nothing to change.
- `HANDOFF.md`: the Task 3 status line (round 4 committed and awaiting re-review, with its set B numbers), next step 1, and the suite counts (7548 fast, 5 slow).

### Remaining concerns

1. **False fails are at the limit, and the fail-closed vocabulary is the exposure.** The procedural and transactional verbs, `_EVENTS`, `_ARE_STATES` and the service verbs are allowlists. Unseen legit vocabulary fails. A3 measured 7/25 false fails before I widened the lists, and 0/25 after, so the reviewer's fresh legit probe may land above 10% when it uses words I did not list. Every miss costs one generator retry, never a billboard.
2. **Residual billboard classes:**
   - (a) a non-procedural bare infinitive after a licensed object "you" ("may help you picture the place", set B);
   - (b) a mismatch predicate about the reader's own records ("the dates in your diary do not match the ones staff give you", A2);
   - (c) the reader's kin as the object of a procedural verb or a preposition ("talk to your wife", "a photo of your wife") passes, because family FAQs need "bring your children" and "visit your husband";
   - (d) a kin subject with a speech verb ("your son talks about the farm").

   (a) has a structural fix: check the infinitive after "help/let/make you". (b) and (c) are content that only a semantic lint will see (the Phase 7 LLM lint).
3. **Ruled false fails, by the method:** the reader as the experiencer of perception or cognition ("If you notice a change in your relative's sleep, ...", "If you think you have been charged twice, ..."), descriptive "your relative may seem tired", and "if you have never visited before". The Task 6 generator prompt should keep steering FAQ prose toward procedural "you" (the existing carry).
4. Two anchor gaps found by set B and left untouched: "you will need <noun>" and "if you forget <object>".
5. A long "Thank you for ..." sentence used to fail the round 2 closing length rule. It is now anchored in the instructional kinds; memos keep the round 2 rule.
6. `second_person.py` is now 1130 lines, against 469 at HEAD. The role test is about 600 lines of token rules and closed word classes.

The HEAD row of set B was measured after the commit's gate, by swapping HEAD's module in and restoring it (checked with `cmp`); it is a comparison only, the code was not changed after it. At HEAD the B misses were the two `your` body/self subjects ("your thoughts arrive", "your fingers keep reaching"), the same "help you picture" miss, and false fails on "while you are on the ward" and "you are welcome to join" besides the two anchor gaps.

---

## Fix round 5 (commit 3bc11f2, on 4c10eea)

Status: DONE_WITH_CONCERNS. On held-out set B, run once:

| Kind | Billboard false passes | Legit false fails |
| --- | --- | --- |
| family_faq | 4/15 (target at most 2) | 1/20 (5%) |
| recovery_guide | 2/15 | 5/20 (25%, target at most 10%) |

The billboard target misses in family_faq, and the legit target misses in recovery_guide. Under ruling (e) I did not tune after set B; the misses and their classes are quoted below.

### What changed, per finding

All changes are in `claude_bully/planner/second_person.py`, except where noted. The interface is unchanged: `classify(title, body, *, instructional, premise)` and `lint_document -> list[LintResult]`.

- **(b) The form side is an open class.** `PROCEDURAL_VERBS` (125 lines), `_OBJECT_VERBS`, `_TO_VERBS`, `_LICENCE`/`_licensed`, `_GET_OK` and the `_VERB` alternation in the anchors are gone. One closed class, `_EXPERIENCER`, replaces them. It covers perception, cognition, memory, emotion, identity and change of state: feel, seem, notice, sense, recognise, perceive, glimpse, know, think, believe, understand, wonder, realise, suppose, suspect, imagine, picture, dream, guess, doubt, reckon, remember, recall, recollect, forget, miss, love, hate, fear, dread, regret, grieve, mourn, yearn, ache, cry, weep, worry, belong, become, grow, fade, blur, drift and wake.
  - Anchor positions take any verb but the class:
    - an imperative that opens a clause (`_imperative`, token-based): any word that is not a function word, an experiencer, a plural, or an -ing, -ed or -ly word, and that no finite verb follows;
    - after a modal ("you can", "can you", "your relative may", "<modal> <verb> ... to you");
    - after "if/when/once/until you", and "if your <noun>";
    - "we/staff/someone/they ... you".
  - The verb at each reader position is read by `_verb_ok`. A few experiencer verbs take a procedural object: "feel free/unwell", "forget to / forget your <thing>", "miss <an event>", "hear from/back", and "find" with no "that" and no "it <adjective>".
  - An object "you" after any non-experiencer verb is a service object ("signed you off", "which times suit you"). The exceptions:
    - the agent-on-you veto (`_AGENT` in `_VETO`, unchanged);
    - "call you <name>";
    - "remind you of";
    - an experiencer infinitive after "help/let/make you" ("help you picture", but "let you know");
    - an object of an experiencer ("recognise you", "the people who knew you"; a complement after "we/I/staff know" is read as a subject);
    - a preposition other than for, with, from, to, behind, beside, near or after ("about you", "like you"; "those of you" passes);
    - one of those prepositions in a clause with an experiencer, "familiar" or "dear", or "come back" not said by the office ("the songs that come back to you", but "we will come back to you").
  - An imperative experiencer that opens a clause fails ("picture the house", "don't worry"). This is `_imperative_veto`.
  - The welcome anchor reads any subject ("you and your relative are welcome to join").
- **(c) The content side stays closed.**
  - The reader's specific kin (`_KIN`) fail in any slot, a possessive included ("your wife", "your son's", "your partner's address", "your eldest son"). This is `_owned`.
  - A generic "your relative", "your loved one" or "your family member" takes only a procedural predicate (`_relative_slot_ok`: the subject-"you" rules, a place included). "Your relative is safe and well" fails; "your relative is on the second floor" passes.
  - "Your family" fails, except as a compound (family member, doctor, gp, liaison, contact).
  - The past and perfect of the reader keep the closed `TRANSACTIONAL_VERBS` list (plus "finish", for the re-review's quoted "Once you have finished the course").
- **N1.** `_event_veto` skips a clause after "until/since/before/after". The following word is "who", or a preposition whose rest of clause holds a finite verb (`_finite_after`: an auxiliary, or an -s form after a noun). A named time with a phrase still fails ("before the move to the coast.").
- **N2.** `_is_ing` excludes -ing nouns and pronouns: nothing, anything, something, everything, thing, morning, evening, building, ceiling, clothing, wedding, during, bring, ring, spring and their kind. The open class made "bring" visible: it read as a gerund.
- **N3.** A change of state, a past and a perfect fail only when their subject is the reader, a "your" phrase or a body or self noun (`_subject_of`: the clause's opening noun phrase, or a relative pronoun's antecedent). "The cafe has moved", "We moved the visitor car park" and "If a slot becomes available" pass. "Your shop closed last spring" fails (new).
  - A simple past counts only as the clause's first verb, so "if you are the person named on the form" is no past.
  - Deviation, stated: a perception frame (seem, appear to, look/sound like, feel, "as if", "mean nothing to", and from set A, "find <it> strange") still fails with any subject. Its experiencer is not its grammatical subject but the implied perceiver, the reader. The round 4 positive "If the corridor seems longer than it did, ..." stays a positive. The cost is a false fail on "the lounge can feel cold".
- **N4.** `_kin_predicate_ok` is gone: specific kin fail in any slot (see (c)).
- **N5.** `classify` maps each speech-stripped sentence back to the document's own sentence (`_source`), so a sentence that holds a quote is one result, and its span is text the document holds.
- **(d) Repair hint.** Every failure in an instructional kind ends with `; rewrite this sentence without 'you' or 'your': use the third person (visitors, families, residents) or a bare instruction`. The message prefixes are unchanged.
  - To make the hint's premise true, the reader-address families now run only on a sentence that holds a second-person word. The membership family ("are one of the groups who") used to fail third-person sentences. A sentence with no "you", "your" or "yours" now always passes.
  - Memo messages carry no hint, as ruled.
- **Minor items from the re-review.** `_CLOSING_HEAD` drops the dead "really" branch (minor 6). The role-test comment names every object-"you" preposition (minor 8).
- **Membership.** `_READER` gains "you/are/were among us/them/those/the". Under the open class, "counted you" is a service object, and this keeps the round 2 positive "We counted you among those they transferred." firing.

### Fixtures, RED first

`tests/test_lints.py` gains `_SP5`, 39 cases in family_faq and recovery_guide:
- 36 written before any code change: one or more per finding (N1 to N4), per ruling class ((b), (c)), and the experiencer object, causative and complement cases, each with a near-miss;
- 3 self-review pins written after GREEN, for two bugs I found by reading my diff ("if you are early", "be fully informed", "we fully understand you may be ...").

Two tests are new:
- `test_second_person_reports_a_quoted_sentence_once` (N5, memo and FAQ);
- `test_second_person_failures_in_an_instructional_kind_carry_a_repair_hint` (d).

No earlier fixture was relabelled. The sentences quoted in the re-review are used verbatim where they fit (N1 to N4, the (b) false fails). Fixture 188 was shortened after RED for line length ("of the month" became "each month"); it behaves the same at HEAD (no anchor).

RED, before any code change (HEAD's `second_person.py`):
```
$ uv run pytest tests/test_lints.py -q -k second_person
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-171] [172] [174] [175] [177] [178] [179]
  [181] [182] [183] [184] [185] [186] [188] [189] [191] [192] [193] [194] [195] [196] [197] [202] [204] [206]
FAILED tests/test_lints.py::test_second_person_reports_a_quoted_sentence_once[internal_memo-...]
FAILED tests/test_lints.py::test_second_person_reports_a_quoted_sentence_once[family_faq-...]
FAILED tests/test_lints.py::test_second_person_failures_in_an_instructional_kind_carry_a_repair_hint
28 failed, 174 passed, 36 deselected in 0.75s
```
The 25 RED cases are:
- N1 (2), N2 (2) and N3 (3) near-misses, and "Your shop closed";
- N4 and (c) kin (5);
- generic kin near-misses (2);
- (b) false fails (7);
- "remind you of", "help you picture", "let you know".

The other 11 `_SP5` cases pin behaviour HEAD already had and the open class must keep: "before the move to the coast", "you are nothing to them", "if you become tired", "your relative is on the second floor", "your relative is safe and well", "you may notice", "if you recognise", "the people who knew you", "we know you are busy", "remind you about", "help you carry".

GREEN:
```
$ uv run pytest tests/test_lints.py -q
241 passed in 0.56s
```

### Gate (before 3bc11f2)

```
uv run ruff format --check .  -> 236 files already formatted
uv run ruff check .           -> All checks passed!
uv run mypy claude_bully      -> Success: no issues found in 99 source files
uv run pytest -q -W error     -> 7590 passed, 5 skipped, 5 deselected in 393.03s (0 warnings)
uv run pytest -q -m slow      -> 5 passed, 7595 deselected in 98.22s
```

All three checked-in worlds still pass every fail-severity lint, with no world edits.

### Probe sets

Files are in `.superpowers/sdd/2026-10-24-phase-3-world-generator/probes-round5/` (git-ignored):
- `set_a.txt`, `set_b.txt`;
- `run_probe.py`; `run_probe_head.py` patches HEAD's classifier in at runtime, for comparison only, and leaves the tree untouched;
- `set_a_head.txt`, `set_a_run1.txt`, `set_a_run2.txt`;
- `set_b_result.txt`, `set_b_code_sha.txt`, `set_b_diagnosis.txt`, `set_b_head_comparison.txt`;
- `rereview_quoted.txt`;
- `red.txt`, `gate_pytest.txt`, `gate_slow.txt`.

Method:
- Both sets were written before any code change. Each has 15 billboards and 20 legitimate procedural sentences per kind, written from `data/worlds/overlay/world.yaml`.
- In a family_faq the reader is a resident's family; in a recovery_guide it is a resident coming out of the program.
- The vocabulary is a real care-home FAQ's or recovery leaflet's, not any verb list.
- No overlay premise term appears (the runner asserts it, and that each sentence holds a second-person word and no real name). Each sentence is linted as a one-sentence document in the overlay world's context, through `lint_document`.
- One set A billboard held no second-person word, a writing error the runner caught. I fixed it before any code change ("feel like home" became "feel like your home").
- I tuned on set A only. I ran set B once, on the final code (`set_b_code_sha.txt`). After it, only the module docstring, one comment line and docs changed, and the working copy went from CRLF to LF. No code changed.

| Set | Code | family_faq bill / legit | recovery_guide bill / legit |
| --- | --- | --- | --- |
| A | HEAD (4c10eea) | 3/15, 5/20 | 3/15, 6/20 |
| A | round 5, first pass | 3/15, 1/20 | 2/15, 2/20 |
| A | round 5, final | 2/15, 0/20 | 0/15, 2/20 |
| **B (held out, once)** | **round 5, final** | **4/15, 1/20** | **2/15, 5/20** |
| B | HEAD, for comparison only | 1/15, 6/20 | 1/15, 10/20 |

Tuning on set A, three changes after the first pass:
1. The reader's marriage joins `_VETO`: wedding, marriage, honeymoon, anniversary. It caught "the wedding ring you keep" and "your wedding photographs", the overlay's central fact.
2. "find <it> strange/different/familiar" is a perception frame. It caught "Most people find their own handwriting strange".
3. The welcome anchor reads any subject ("you and your relative are welcome to join").

The final set A misses:
- false passes: "The lady in the blue coat who visits on Sundays has brought your reading glasses, ..." and "Families can leave a voicemail for you on the ward line, and staff will play it to you after your shift." Both are semantic.
- false fails, both ruled classes: "unless your doctor has told you otherwise" (the agent-on-you veto) and "If your wound becomes red or swollen, ..." (a change of state of a "your" phrase).

As a regression check (not a score), the re-review's quoted sentences:
- Every N1 to N4 and (b) case behaves as ruled.
- Its four semantic billboard misses still pass, as do the two billboards it said were caught only by misparses (N1, N2).
- Its by-method false fails still fail: "the date you prepared it", "on your feet", "if you notice", "if you think".
- "Once you have finished the course", "You will need photo ID ..." and "If you forget your pass, ..." now pass.

Set B, every miss quoted, with the rule that decides it (`set_b_diagnosis.txt`):
- Billboard false passes, family_faq (4):
  - "If the date on your newspaper does not match the date you expect, ask a nurse which year it is." "expect" is cognition outside the closed class, and "which year it is" is semantic.
  - "If the smell of the bakery on Front Street makes you homesick, sit in the garden for a while." A causative with an emotional-state adjective: only a causative infinitive is read.
  - "Staff will gladly read you the letters that were written to you before you lost touch." "lost" is on the transactional list ("if you lose your pass"); "lost touch" is the reader's past.
  - "Ring the bell twice if you hear a child calling for her dad in the corridor." "hear a ..." is in hear's exception slot.
- Billboard false passes, recovery_guide (2):
  - "Ask your key worker to show you the paperwork that explains how long you were away." "away" is an administrative state.
  - "If you still sign your messages with a number, practise writing your full name instead." Semantic: the name sits in a writing slot.
- Legit false fails, family_faq (1):
  - "You are responsible for any items you leave in the visitors' lockers." No anchor position: an indicative "you are <state>" main clause.
- Legit false fails, recovery_guide (5):
  - "You should rest with your leg raised for twenty minutes after each walk." `_EVENTS` has no "walk": "after each walk" reads as a time named by an event.
  - "The occupational therapist will visit your home to check whether you need rails or a raised seat." No anchor: "whether you" is not a subordinator anchor, and the service anchor allows four words between the verb and "you".
  - "Count your tablets at the end of each week so you know when to order more." "know" is cognition (a ruled class).
  - "Your prescription lasts for twenty-eight days, and the pharmacy needs two working days to prepare the next one." No anchor: a descriptive "your" sentence.
  - "Use the grab rails in the bathroom until you are confident on your feet." A body noun (a ruled class), and "confident" is no administrative state.

Against HEAD on the same set B:
- Round 5 fails 10 fewer legit sentences (16/40 to 6/40) and passes 4 more billboards (2/30 to 6/30).
- HEAD caught all four of those billboards for the same reason it false-failed legit text: its closed verb lists did not hold "expect", "makes", "read you" or "practise".
- Round 5 catches a billboard HEAD passed: "You can phone your daughter from the day room ..." (kin in any slot).

### Line counts

- `claude_bully/planner/second_person.py`: 1141 at HEAD, 1124 now.
  - `PROCEDURAL_VERBS` (125 lines) and the object/to/licence lists went.
  - The open-class reading (`_subject_of`, `_verbish`, `_imperative`, `_imperative_veto`, `_source`) took most of the saving back.
- `claude_bully/planner/lints.py`: 302 to 304 (docstring only).

### Docs updated

- `claude_bully/planner/second_person.py`: the module docstring (form as open anchor positions, the closed experiencer class, kin in any slot, the hint, one result per sentence as the document's text) and the role-test comment block.
- `claude_bully/planner/lints.py`: the `second_person` bullet.
- `docs/08-DIRECTOR.md`: the Billboard row's instructional-kind rule as built.
- `HANDOFF.md`: the "Last updated" line (it named 158746b), the Task 3 status with the round 5 set B numbers, next step 1, the resume prompt (it named round 4 from 158746b), and the suite counts (7590 fast, 5 slow).
- `docs/00-RECONCILED.md`: checked. It names the module and the lint ids only, so there was nothing to change.

### Remaining concerns

1. **Both targets are not met on set B.**
   - Billboards: family_faq 4/15 (target 2), recovery_guide 2/15.
   - Legit: recovery_guide 5/20 (25%). Two of the five are ruled classes (know, a body noun); three are form or list gaps.
   - Combined: 6/30 billboards and 6/40 legit (15%).
2. **What the open class costs.** HEAD's closed lists failed any unlisted verb, so they caught billboards built on unusual verbs by accident, and failed legit text the same way. The open class removes both effects. The billboard classes that now pass:
   - (a) a causative with an emotional-state adjective ("makes you homesick");
   - (b) a cognition or expectation verb outside the closed class ("the date you expect");
   - (c) the closed transactional and state lists colliding with identity idioms ("before you lost touch", "how long you were away");
   - (d) a perception verb's procedural exception slot ("hear a child calling for her dad");
   - (e) semantic paraphrase ("sign your messages with a number", "the lady who visits on Sundays has brought your reading glasses", "voicemail for you ... after your shift").

   (a), (b) and (d) each have a small structural fix: a closed emotional-state adjective set after "make you"; "expect" and "assume" in the class; "hear" taking only "from" or "back". (c) needs narrower lists. (e) only a semantic lint will see (the Phase 7 LLM lint). I left them all alone because set B found them; adding them now would launder set B.
3. **Form and list gaps found by set B, left alone:**
   - an indicative "you are responsible for";
   - a descriptive "your prescription lasts";
   - "whether you";
   - a service phrase longer than four words before "you";
   - `_EVENTS` lacking "walk".

   Each is a one-line widening. Each costs one retry, which the hint makes repairable.
4. **Ruled false fails, by method.** Each costs a retry that the hint repairs:
   - the reader as experiencer (notice, think, know, worry, "don't worry");
   - body nouns ("on your feet", "your leg");
   - the reader's past ("the date you prepared it");
   - the agent-on-you veto ("your doctor has told you otherwise");
   - a change of state or perfect of a "your" phrase ("if your wound becomes red", "if your contact details have changed");
   - perception with a thing subject ("the lounge can feel cold");
   - marriage words in a "you" sentence.
5. **N3 deviation.** Perception frames keep any subject, because their perceiver is the implied reader. The change of state, past and perfect rules are restricted as ruled.
6. **The imperative detector is heuristic.** A clause-initial singular noun before an unknown verb ("Reception opens at nine") reads as an imperative. That approves form only; the role test still reads every "you". A sentence whose only second-person word is a "your" in such a clause is therefore anchored, and passes unless a "your" content rule fires.

---

## Breaker fix (commit dd6cdec, on 3bc11f2)

Status: DONE_WITH_CONCERNS. The merge is built as ruled. On held-out set B, scored once:

| Kind | Billboard false passes | Legit false fails |
| --- | --- | --- |
| family_faq | 2/15 (target at most 2: met) | 4/20 |
| recovery_guide | 3/15 (target at most 2: missed by one) | 9/20 |

- The binding billboard target misses in recovery_guide by one sentence.
- Every legit false fail carries the repair hint (13/13), and 13/13 hint-directed rewrites pass.
- I did not tune after scoring. The misses are quoted below.

### What changed, per item of the requirements

All code changes are in `claude_bully/planner/second_person.py`. The interface is unchanged: `classify(title, body, *, instructional, premise)` and `lint_document -> list[LintResult]`.

1. **4c10eea's form side is restored.** These come back from 4c10eea:
   - `PROCEDURAL_VERBS`: the same 124 verbs in the same order, packed into one string split to save lines;
   - `_VERB`, `_MODAL` (no "would"), `_MODAL_TAIL`, `_ANCHOR` and `_IMPERATIVE`, and `_anchored` over them;
   - the slot logic `_base_ok`, `_have_ok`, `_state_ok`, `_forget_ok`, `_subject_ok`, `_licensed`, `_object_ok` and `_reader_veto`;
   - the slot lists `_OBJECT_VERBS`, `_TO_VERBS`, `_LICENCE`, `_GET_OK`, 4c10eea's `_ADVERBS` and `_ASPECT_PAST`.

   Round 5's open class is gone:
   - `_EXPERIENCER_BASES`/`_EXPERIENCER`, `_verb_ok`, `_imperative`, `_imperative_veto`, `_verbish`, `_prep_object_ok` and `_skip_adverbs`;
   - their constants: `_NOT_VERBS`, `_OPENERS`, `_LEADS`, `_FUNCTION`, `_TO_CHAIN`, `_MOVED`, `_FORGET`, `_MISS`, `_HEAR`, `_MISSABLE`, `_SERVICE_PREPS`, `_TO_YOU`, `_COME`, `_OFFICE`, `_QUANTIFIERS` and `_LET`.

   `_name_slot` and `_predicate_free` read `_PROCEDURAL_FORMS` again (4c10eea), not "no experiencer".

   Where the restore is not verbatim, and why (each keeps an existing fixture green or carries a kept round 5 rule):
   - `_MODAL_TAIL`'s adverb slot now takes the role test's `_ADVERBS` (just, only, usually, already, now, normally), not only also/then/still/first/always/not. Without it, the SP5 N3 near-miss "We moved the visitor car park last spring, so you can now park by the main door." had no anchor. The verb is listed; only the adverb was missing. No verb list widened.
   - `_subject_ok` reads "is" too. Round 5's generic-relative slot (`_relative_slot_ok`) calls it ("Your relative is on the second floor").
   - `_state_ok` keeps round 5's rule that an -ly word is an adverb only before a participle ("be fully informed", an SP5 pin). Its `passive` parameter is dropped, since every caller passed True.
   - `_object_ok` keeps two round 5 content rules, in closed form:
     - "remind you of" fails;
     - after "help/let you" the infinitive must be a listed verb ("help you picture" fails; "help you carry" and "let you know" pass).

     Both SP5 positives pass at 4c10eea, so dropping these rules would re-open them.
   - `_reader_veto` reads a verb before "you" as making "you" its object, which needs a service verb and a licence. The verb is either a past form not after a copula ("the woman who married you"; "if you are worried you can" is not one) or the verb after "who" ("the people who love you"). Why: N3 narrows the tense veto to the reader, a "your" phrase or a body noun. 4c10eea's any-subject past was the net that caught "The people who knew you can visit on Saturday afternoons." (an SP5 positive), because 4c10eea's `_reader_veto` read that "you" as the subject of "can visit". This also closes the round 5 re-review's F1(b) ("the person who drove you to work", "the woman who married you").
   - `_KIN_COMPOUNDS` is 4c10eea's service-head list again, minus friend/friends: member(s), doctor, gp, room, meeting(s), liaison, group, support, contact, officer, worker. This undoes the round 5 narrowing (re-review New Breakage 2, "your family support worker"). I left out "friend": a family friend is a personal tie of the reader's, and "if you can't tell, it is".
2. **Kept from round 5:**
   - N2: `_ING_NOUNS` and `_is_ing`.
   - N4: `_owned`, the kin branch of `_self_noun_veto`, the generic relative and `_relative_slot_ok`. `_KIN` is widened with:
     - sibling(s) and twin(s);
     - every step-kin form (stepfather, stepmother, stepdad, stepmum, stepmom, stepparent(s), stepson(s), stepdaughter(s), stepchild(ren), stepbrother(s), stepsister(s)); "step-father" tokenizes to "father", which was already kin;
     - grandparents of every kind (granny, grannie, nan, nana, nanna, grandad, granddad, gramps, grandparent, grandmothers, grandfathers, grandkids);
     - "your other half", read as ("half" after "other"), owned.
   - The repair hint (`_HINT`) on every instructional-kind message.
   - N3: `_subject_of` for a change of state, past and perfect. 4c10eea's aspect test (an aspectual over a non-procedural verb, or any past aspectual) now runs only when that subject is the reader, a "your" phrase or a body or self noun. Unlike round 5, a reader aspectual over a non-procedural verb fails ("if you keep apologising"), so the code matches the docstring again (re-review New Breakage 3).
   - Also kept, as not form side, unchanged from 3bc11f2:
     - N5's `_source`;
     - the marriage veto;
     - `_READER`'s "you among those";
     - `_CLOSING_HEAD` without "really";
     - `classify` skipping a sentence with no second-person word;
     - 3bc11f2's `_IRREGULAR`/`_OTHER_PAST` and `TRANSACTIONAL_VERBS` (with "finish");
     - the wider `_PREPOSITIONS`, `_DETERMINERS` and `_PRONOUNS`.
3. **N1:**
   - `_finite_after` is dropped and 4c10eea's `_event_veto` is back.
   - One excuse is added: when the head of the named phrase (its last named word) is a person (`_STAFF`, a closed list: porter, nurse, doctor, clerk, driver, therapist, pharmacist, chaplain, volunteer, coordinator, manager, carer, staff, worker, officer, and their kind, plus taxi, bus and ambulance), it names no time. It excuses "until the porter on duty comes" and "since the nurse who runs the clinic".
   - It cannot re-open a named-time billboard, since an event noun is never on the list. "before the move to the new flats", "since the accident on the coast roads", "the house with green shutters" and "after the fire at the old house" fail.
   - Self-review fix: the first version matched any named word, so "before the porter strike" passed. It now reads the head only.
4. **N3, perception:**
   - A perception frame (seem; look, sound or appear before a comparison word or "appear to"; feel, but not free or unwell; "mean nothing to") fails when `_subject_of` gives the reader, a "your" phrase or a body noun.
   - With any other subject it fails only before a comparison or oddness complement (`_compared`): a `_COMPARE`/`_ODD` word, or "than" within three words, read past degree words ("a little", "very", "to be").
   - "as if"/"as though" and "find <it> strange" fail whatever the subject.
   - "The lounge can feel chilly in winter, so you may want to bring a cardigan." passes. "If the corridor seems longer than it did, ..." still fails.
5. **Fixtures:** see the flips and RED/GREEN below.
6. **Docs:** see "Docs updated".
7. **Size:** 1137 lines.

### Fixtures and flips

`tests/test_lints.py` gains `_SP6`, 35 cases (20 positives, 15 near-misses), in both kinds:
- item 1 (closed form side);
- item 2 (N2, kin widening, the reader as the object of a past or of "who <verb>", a reader aspectual);
- item 3 (N1 named times and person heads);
- item 4 (perception on a thing subject and on the reader).

The hint keeps its existing test, `test_second_person_failures_in_an_instructional_kind_carry_a_repair_hint`: every instructional message ends with the hint, and memo messages carry none.

Flipped `_SP5` fixtures, from a near-miss (pass) to a positive (fail). Each passed only through round 5's open class. The rule that now fails each was checked with `probes-breaker/diagnose.py`:

| # | Sentence | Why it passed at 3bc11f2 | Now |
| --- | --- | --- | --- |
| 1 | If your loved one needs new glasses, the optician visits on the first Monday each month. | open anchor "if your <noun> <any verb>" | no anchor |
| 2 | If your family member uses a wheelchair, the side door has a ramp. | same | no anchor |
| 3 | Parking is free for the first hour; after that, display your ticket on the dashboard. | unlisted imperative "display" | no anchor |
| 4 | Mobile phones may be used in the lounge, but please set yours to silent on the ward. | unlisted "set" | no anchor |
| 5 | Jot down any questions for the pharmacist on the back of your prescription sheet. | unlisted "jot" | no anchor |
| 6 | To arrange a video call, email the family liaison team ... and tell them which times suit you. | object "you" after any verb ("suit") | reader outside a procedure |
| 7 | You should not drive until the clinic has signed you off. | object "you" with no licence | reader as object outside a service |
| 8 | Wheelchairs are available at the main entrance if you or your relative needs one. | open anchor "if you <any>" | no anchor |
| 9 | Before your first visit, we recommend reading the short welcome booklet we posted to you. | open anchor "we ... you" ("recommend") | no anchor |
| 10 | We will let you know if the visiting times change. | open anchor "we ... you"; "let" is in no closed office-service anchor | no anchor |
| 11 | We fully understand you may be worried about the first visit. | open anchor "we ... you" ("understand") | no anchor |
| 12 | If you are early, wait in the lounge until the nurse calls you. | object "you" with no licence in its clause ("until the nurse calls you") | reader as object outside a service |

Notes on the flips:
- Flip 12 was found at the first GREEN attempt, not decided beforehand: I first expected it to stay green. Its "-ly is the state" purpose is pinned again in `_SP6` by "If you are early, please wait in the lounge."
- No other earlier fixture was relabelled.

### RED and GREEN

RED, with the fixtures written and HEAD's `second_person.py` unchanged (`probes-breaker/red.txt`):
```
$ uv run pytest tests/test_lints.py -q -k second_person
28 failed, 210 passed, 36 deselected in 0.72s
```
The 28:
- flips 1 to 11;
- 17 new `_SP6` cases:
  - the three closed-form billboards ("call the visiting room a server hall", "still apologise for not being able to browse the web", "answer the kitchen phone with a support greeting");
  - five kin widenings (stepfather, granny, siblings, other half, granddad);
  - "the woman who married you" and "the person who drove you to work";
  - "if you keep apologising";
  - three named times ("the new flats", "green shutters", "the coast roads");
  - three thing-subject perception near-misses ("feel chilly", "seem quiet", "this means a short wait").

The other 18 `_SP6` cases pin behaviour HEAD already had and the merge must keep.

First GREEN attempt: 2 failures.
- "you can now park": the `_MODAL_TAIL` adverb slot, fixed as above.
- "until the nurse calls you": flip 12.
- After the fix, two pins were added, written after code:
  - "The shop has closed, so you can now buy stamps at reception.", which fails under 4c10eea's verbatim tail (checked at runtime);
  - the "if you are early" pin.

GREEN:
```
$ uv run pytest tests/test_lints.py -q
276 passed
```

### Gate (before dd6cdec, all after the last edit; `probes-breaker/gate_final.txt`)

```
uv run ruff format --check .  -> 236 files already formatted
uv run ruff check .           -> All checks passed!
uv run mypy claude_bully      -> Success: no issues found in 99 source files
uv run pytest -q -W error     -> 7625 passed, 5 skipped, 5 deselected in 420.57s (0 warnings)
uv run pytest -q -m slow      -> 5 passed, 7630 deselected in 106.06s
```

All three checked-in worlds still pass every fail-severity lint, with no world edits.

### Probe set B

Files are in `.superpowers/sdd/2026-10-24-phase-3-world-generator/probes-breaker/` (git-ignored):
- `set_b.txt` and `set_b_sha256.txt` (hash and HEAD, recorded before any code change);
- `run_probe.py`;
- `set_b_result.txt`, `set_b_code_sha.txt` (the module's hash at scoring), `set_b_diagnosis.txt` and `diagnose.py`;
- `repair_rewrites.py` and `.txt`;
- `compare_versions.py` and `set_b_version_comparison.txt`;
- `red.txt` and the `gate_*.txt` files.

Method:
- I wrote set B before any code change: 15 billboards and 20 legitimate sentences per kind.
- The billboards vary the form: conditional, modal, imperative, temporal, service object, unanchored and procedural-shaped. They vary the domain: the reader's assistant-shaped habits, kin, the past, perception, body, memory and identity.
- The legit sentences are written as a care-home FAQ or a discharge leaflet would put them, not toward any list.
- No sentence is reused from the earlier probe or review files (checked by grep).
- The runner asserts each sentence holds a second-person word, no overlay premise term and no real name. Its `--check` mode validated the set without scoring it before any code change.
- Each sentence is linted as a one-sentence document in the overlay world's context through `lint_document`.
- I scored it once, after the fast-suite gate passed on the final code. After scoring, only docs changed.

Billboard false passes, with their causes (`set_b_diagnosis.txt`):
- family_faq (2):
  - "Visitors are asked to be patient if you greet them as customers at first." "greet" is a listed procedural verb. The billboard is the reader's assistant-shaped habit phrased as procedure: semantic.
  - "Families may bring recordings from the house so that you can hear the kitchen clock again." "you can hear" is anchored, and "hear the" is in hear's procedural slot. It is the reader's past by paraphrase: semantic.
- recovery_guide (3):
  - "In the first weeks you may keep offering to help with tasks nobody has asked about, and that will ease." Structural. "keep" is listed. The aspect test needs `_subject_of` to find the reader, but the clause opens with "In the first weeks", and `_subject_of` reads only the clause's first word. 4c10eea caught it with its any-subject aspect rule, so the miss is a cost of N3's subject restriction.
  - "Ask the group leader about the evenings when you still check for new messages every few minutes." "check" is listed. It is the assistant-shaped habit: semantic.
  - "You can collect the box of things you had with you on the night the van came for you." "had" is transactional, and "came for you" is licensed by the main clause's "can". It is the reader's past by paraphrase: semantic.

Legit false fails, every one with the hint:
- family_faq (4):
  - "Visiting hours are ten until eight, and you do not need to book outside mealtimes." No anchor: "you do not need to" is in no anchor (an anchor-shape gap).
  - "Overnight stays can be arranged in exceptional circumstances, so talk to the manager if you think this applies to you." "if you think": a ruled class (cognition).
  - "If you notice your relative seems low or withdrawn, please mention it to the named nurse." "notice": a ruled class (perception).
  - "Feel free to bring a favourite chair or cushion to make the room more homely for your relative." No anchor: 4c10eea's `_IMPERATIVE` has no "feel free" (an anchor-shape gap).
- recovery_guide (9):
  - "You should not lift anything heavier than a full kettle for the first six weeks." Unlisted verb "lift".
  - "If your wound becomes hot or swollen or starts to leak, contact your doctor the same day." A change of state of a "your" phrase: a ruled class.
  - "Your first outpatient appointment will be sent to you by letter." No anchor: the "your <noun> will be sent" anchor allows at most two words after "your" (an anchor-shape gap).
  - "Do not drive until you can do an emergency stop without pain." "you can do" takes only "it/this/that/so" (a slot gap).
  - "If you live alone, arrange for someone to stay with you for the first few nights." Unlisted "live", and "arrange" is transactional only, so it is no imperative anchor.
  - "Wear the support stockings during the day, and take them off at bedtime unless the nurse advises otherwise for you." "for you" has no licence in the "unless" clause (a licence gap).
  - "If you smoke, the stop-smoking team can support you to quit." "support" is no `_OBJECT_VERBS` service verb (a list gap).
  - "Remove the dressing after five days and leave the wound open to the air unless the nurse tells you otherwise." "tells you" has no licence in the "unless" clause (a licence gap, the same as flip 12).
  - "You may shower after forty-eight hours, but pat the area dry rather than rubbing it." Unlisted "shower" and "pat".

By cause, of the 13:
- 3 are ruled classes;
- 4 are unlisted verbs or a missing service verb;
- 3 are anchor shapes;
- 2 are a missing licence in a subordinate "unless/until" clause;
- 1 is a "do <noun>" slot.

All 13 messages end with the hint. All 13 hint-directed rewrites pass (`repair_rewrites.txt`). An example: "Residents should not lift anything heavier than a full kettle for the first six weeks."

Comparison only, after scoring. The same set B, with each version's classifier patched in at runtime; the tree was untouched:

| Version | family_faq bill / legit | recovery_guide bill / legit |
| --- | --- | --- |
| breaker fix | 2/15, 4/20 | 3/15, 9/20 |
| 4c10eea | 3/15, 4/20 | 2/15, 9/20 |
| 3bc11f2 | 6/15, 4/20 | 8/15, 2/20 |

- The breaker fix catches one billboard 4c10eea passed: "Your partner of twenty years ..." (kin in any slot, from round 5).
- It passes one billboard 4c10eea caught: "you may keep offering", lost through N3.
- Its legit false fails equal 4c10eea's on this set.
- Against 3bc11f2: 9 more billboards caught, 7 more legit false fails.

### Line count

- `claude_bully/planner/second_person.py`: 1124 at 3bc11f2, 1141 at 4c10eea, 1137 now.
- `PROCEDURAL_VERBS` packed into 9 lines saved most of the room for the restored slot logic.

### Docs updated

- `claude_bully/planner/second_person.py`:
  - the module docstring: item 4 has closed form, anchors over the listed verbs, the role test's subject and object slots, the narrowed perception rule, N3 subjects, the N1 person excuse, and kin with "other half";
  - the role-test comment block.
- `claude_bully/planner/lints.py`: the `second_person` bullet now names a procedural anchor over the closed `PROCEDURAL_VERBS` list, not the open class.
- `docs/08-DIRECTOR.md`: the Billboard row's instructional-kind rule as built.
- `HANDOFF.md`:
  - the "Last updated" line;
  - the test counts (7625 fast, 5 slow);
  - Progress, Phase 3 Task 3, rewritten to the final state: five rounds, the breaker fix, set B's residuals, legit false fails repairable by the hint, and the semantic residual left to the Phase 7 LLM lint;
  - next step 1;
  - the resume prompt, which resumes at Task 4 once the breaker fix's review and docs-sync are in the ledger.
- `docs/00-RECONCILED.md`: checked. It names the module and the lint ids only, so there was nothing to change.
- `docs/handoff/`: not touched.

### Concerns

1. **The billboard target misses in recovery_guide by one (3/15).**
   - One miss is structural: `_subject_of` reads only a clause's first word, so a reader subject after a fronted phrase ("In the first weeks you may keep offering ...") is not seen. The aspect rule then lets a listed aspectual ("keep") over an unlisted verb pass. 4c10eea's any-subject aspect rule caught it.
   - A fix inside the rulings: let `_subject_of` skip a fronted prepositional phrase to the first "you", or run the aspect check whenever the aspectual follows a subject "you". I did not make it, because set B found it.
   - The other four misses are semantic: the reader's assistant-shaped habits phrased with listed verbs ("greet them as customers", "check for new messages"), and the reader's past by paraphrase ("hear the kitchen clock again", "the night the van came for you"). No closed list reaches them. They are the Phase 7 LLM lint's.
2. **Legit false fails are high in recovery_guide (9/20).**
   - There is no target, and each carries the hint (13/13 rewrites pass).
   - Discharge leaflets use many verbs outside the visiting-and-admin list (lift, shower, pat, live, smoke support).
   - Subordinate "unless/until the nurse <verb>s you" clauses have no licence.
   - Each is one generator retry. The Task 6 generator prompt should keep steering FAQ and leaflet prose toward third-person or bare-instruction sentences.
3. **The form-side restore is not byte-for-byte.** The non-verbatim points, each argued in item 1:
   - the anchor's adverb slot;
   - "is" in `_subject_ok`;
   - the -ly participle rule;
   - "remind you of" and the causative infinitive;
   - the verb-before-"you" object reading;
   - `_KIN_COMPOUNDS`.

   Every one is a closed rule, and none widens a verb list.
4. **12 round 5 near-misses were flipped to fail.** Common FAQ phrasing ("we will let you know", "if your relative needs ...", "display your ticket") now costs a retry. That is the trade the ruling accepted.
5. **The `_STAFF` excuse is a closed list.** "until the locksmith on call comes" still reads as a named time and fails (one retry).
