# Phase 4 Task 8 re-review, fix round 2 (7b1f54a..c8a9f06)

Reviewer: scoped re-review of fix round 2. I read the round 1 re-review (`task-8-rereview-round1.md`), the global constraints, the report's "Fix round 2" section (as unverified claims) and the whole diff `review-7b1f54a..c8a9f06.diff`, once. I read the checkout's `harvest.py`, the test file and the premise and sheet code only where a check below names it. The checkout was not edited. I did not re-run git or the suite. Every probe is in `probes-task8-rereview2/`, run with `.venv/Scripts/python.exe -X utf8 -I` and, for the pytest probe, `timeout 300 ... -m pytest -p tests.conftest -p no:cacheprovider -o faulthandler_timeout=60 -W error`.

## Verdicts

| Finding | Verdict |
|---|---|
| N1, the negation class misses the apostrophe-less n't spellings | ADDRESSED (one nit: `maynt`, `usednt`; see N5) |
| N2, a list of alternatives joined by "or" is harvested as a completion | ADDRESSED |
| N3, a taste's "option" is any non-linker word of the line | ADDRESSED (one narrower residual of the same shape, N6) |
| N4, the I1 teeth clause is half tautological | ADDRESSED |

No new Critical or Important finding. Two new Minors (N5, N6) and one doc nit. The held-out probe shows no regression.

### N1: ADDRESSED

`harvest.py:512` `_NEGATION` now holds 22 n't forms spelt without the apostrophe: `aint arent cant couldnt darent didnt doesnt dont hadnt hasnt havent isnt mightnt mustnt neednt oughtnt shant shouldnt wasnt werent wont wouldnt`. `_declines` (`:769`) reads it over every word, and `_a_completion` (`:752`) calls `_declines`, so the whole-reply and the quoted form are both covered.

- The round 1 probes give no item: "cant think of one", "dont know", "wont say", and the fixtures `c_refusal_cant_bare`, `_dont_`, `_wont_`, `_couldnt_`, `_isnt_`.
- Probe `p0_fixtures_and_spellings.py` wrote the English n't class independently of the code: 24 contractions, each stripped of its apostrophe, in four bare-reply frames. 22 give no item. `maynt` and `usednt` give one (N5). With the apostrophe (the `endswith("n't")` rule), with the curly apostrophe and in upper case, none gives an item.
- Closed by a rule, not a growing list: the set is the finite class of English n't contractions, enumerated from the auxiliaries; it is not a list of reply phrases. The "wont" and "cant" noun cost ("as was his wont") is the stated ASSUMED cost. No longer word is swallowed: `wontons steam` and `cantaloupe rinds dry on the sill` still give an item, `a wont of the old keeper` gives none.
- The comment's claim "closed with the auxiliaries they contract" is not literally true for two archaic forms, `maynt` and `usednt` (`mayn't` and `usedn't` are caught only with the apostrophe). Cost to add them: two words. See N5.

### N2: ADDRESSED. The ASSUMED decision is sound.

`harvest.py:521` `_ALTERNATIVE = "or"`, read at `:763` in `_a_completion` (`and _ALTERNATIVE not in words`), so both completion forms are covered.

- `hums or crackles or goes silent`, `creaks or groans`, `OR groans`, `either hums or whistles`, `whether it hums or not`, `hums, or whistles` and the quoted `I'd say "hums or whistles".` all give no item. The fixtures `c_list_joined_by_or`, `c_two_options_joined_by_or` and `c_quoted_options_joined_by_or` pin them.
- **ASSUMED: only "or" coordinates.** Sound. "or" is the English disjunctive coordinator. "nor" is already in the negation class. "either" always comes with an "or" (so "either hums or whistles" is caught) and alone is no list (`either way it boils` still gives an item, correctly). The other candidates are not coordinators: `versus`, `vs`, `otherwise`, `else` and `alternatively` are a preposition and adverbs, and `hums versus whistles` and the like still give an item (probe). Nobody finishes a phrase that way, and the controller's ruling asked for a closed class, which "or" is. `and`, `but` and `yet` join parts of one phrase, not options (`hums and whistles` gives an item, as it should).
- Cost, stated and pinned: `c_true_completion_with_or` ("sooner or later it boils") gives no item. A hyphenated compound splits at the hyphen, so `a hit-or-miss affair` and `an all-or-nothing boil` give none (probe). Both are recall only.

### N3: ADDRESSED. The ASSUMED decision is sound as a rule, with one narrower residual (N6).

`harvest.py:885` takes the at-least-one-option check from `_options` (`:893`): the words of each comma part that holds "or", plus, for a part that opens with "or", the comma parts before it in its clause back to the first part holding a `_NOT_IN_A_TASTE` word. Clauses end at `.!?:;`. The subset rule of round 1 is unchanged.

- Both round 1 probes now give no item: `I'd go with the quick one.` on "Quick one: a window seat or an aisle seat?" and `I'd choose getting real work done.` on "Early morning or late night, for getting real work done?". So do the fixtures `t_frame_word_quick`, `t_frame_words_work` and `t_frame_word_choose`, and `I'd choose the wrong answer.` on the drink line (fresh probe `ftn13`).
- The three positives that keep the list rule honest hold (`t_list_of_three_first`, `t_list_of_three_last`, `t_late_night`).
- **Every shipped taste line holds "or".** The only source of the premise's `taste_ask` line is `taste_bank` in `data/personas/poisoned_well.yaml`. `taste_ask` is a `FIXED_MOVES` move (`strategies/premises/poisoned_well.py:70-74`), chosen verbatim at `:404`. The only other place the name appears is `tests/test_poisoned_well_sheets.py:104`, which checks the count, and no other data file has a taste bank. All 8 lines hold "or" (probe `p1_or_and_taste.py`), and `_options` gives:

| Shipped line | `_options` |
|---|---|
| No wrong answer: tea or coffee on a cold morning, if you had to choose? | coffee, cold, morning, tea |
| Quick one: a window seat or an aisle seat? | aisle, seat, window |
| Mountains or the sea, if you could only pick one? | mountains, sea |
| Paperback or hardback? | hardback, paperback |
| Early morning or late night, for getting real work done? | early, late, morning, night |
| Rain or snow? | rain, snow |
| A crossword or a jigsaw? | crossword, jigsaw |
| Pencil or pen? | pen, pencil |

  - Every natural answer I wrote for each line gives its item ("I'd go with tea", "I'd choose coffee on a cold morning", "I'd pick the jigsaw", "Late night, if I had to choose", "I'd pick early morning").
  - No line loses an option. Only line 1 shows frame words among its options (N6).
- A line with no "or" has no options, so only an ordinal could name one. That is no loss for the shipped sheet. No test ties the shipped lines to the rule (out of scope below).

### N4: ADDRESSED. Each half can fail.

`tests/test_reasoning_channel.py:74` `_sentinel_on_watched_turns` still injects the sentinel at `after_target_turn`. It now records the target Turns at the readers, `PoisonedWellWatch.watch` and `WorldGenerator.harvest_turn` (monkeypatched), so it records what the reader was handed, not the wrapper's own copy. `:141` is half A (every reader of the cell has a non-empty record; its message is the dict of counts). `:142` is half B (every target Turn a reader was handed carries the sentinel).

Probe `test_probe_n4_halves.py` applies each mutation by monkeypatch (the checkout is not edited) and runs the real test function for both cells. The probe passes all 14 cells by design and prints which half failed:

| Mutation | `fires` | `chain` |
|---|---|---|
| control (none) | passes | passes |
| session never calls the watch (`_poisoned_well` a no-op) | half A: `{'watch': 0, 'harvest': 65}` | half A: `{'watch': 0}` |
| session never calls the harvest (`_generate` a no-op) | half A: `{'watch': 65, 'harvest': 0}` | passes (no generator in the cell, so no harvest reader: correct) |
| watch handed Turns with `reasoning_text` stripped (reply and history) | half B | half B |
| watch handed the reply stripped only | half B | half B |
| watch handed the history stripped only | half B | half B |
| harvest handed Turns with `reasoning_text` stripped | half B | passes (no harvest reader: correct) |

In the A rows the failing assert is the first one, whose message is the dict of counts. In the B rows the dict assert holds and the second assert fails. So the two halves are independent, and neither is the vacuous check of round 1. This matches the report's mutation evidence, and I reproduced it with different mutations from the report's two edits to `env_turn.py`.

The ASSUMED that watch and harvest are the readers holds. `PoisonedWellWatch.expectation` and `fire_requests` read bully lines and the harvest's items only (`poisoned_well.py:241-265`). `generator.fire` shows the Turns only through `transcript_prefix`, a sha256 key, and the items. The injection is upstream of all of them, and the sentinel assertions on every prompt, record and document stand.

## No earlier positive regressed

- **`probes-task8/heldout_detectors.py`** (re-run against c8a9f06, unchanged from round 1): completion precision 6/6, recall 6/10 (misses c6, c7, c8, c9, the same four); taste precision 10/10, recall 10/10. No near-miss gives an item, in 27 per kind.
- **The fixture file read through `heuristic_items`** (`p0_fixtures_and_spellings.py`, as the fixture test reads it, not pytest): 112 fixtures, 22 positives, 0 mismatches. The yaml diff removes no line, so every earlier positive is unchanged.
- **`probes-task8-rereview/fresh_detectors.py`** matches the report: completion TP 6, FN 2, FP 5 (all five in stated residual classes: `fcn3`, `fcn4`, `fcn12`, `fcn13`, `fcn15`), precision 6/11, and 6/6 without the stated classes; taste TP 6, FN 2, FP 0, precision 6/6. `fcn5`, `fcn9`, `ftn14` and `ftn15` give no item. The two taste misses (`ft7`, `ft8`) and the two completion misses (`fc7`, `fc8`) are the stated recall forms.
- **`setup_and_spellings.py`**: every shipped phrase line's set-up is still `''`. `dont know`, `wont say`, `idk really`, `sooner or later it boils` and `ugh no` give no item. `either way it boils`, `meh whatever` and `well it whistles` give one.

## New breakage, by severity

### Critical

None.

### Important

None.

### Minor

**N5. The apostrophe-less spellings of the other contracted classes, and two n't forms, still read as phrases.** `harvest.py:494` (`_PERSONS`), `:522` (`_MODALITY`), `:512` (`_NEGATION`). Pre-existing, not introduced by this round: it is the N1 shape in the neighbouring closed classes. I rate it Minor on impact, but the controller regraded N1 Important, so the same ruling may apply.

- These give a `completion` item on a bank line (`p0_fixtures_and_spellings.py`):
  - persons spelt without the apostrophe: `im stuck`, `ill pass`, `id pass on that`, `ive got a blank`, `youre asking a lot`. The apostrophe forms `i'm`, `i'll`, `i'd`, `i've` and `you're` are all in `_PERSONS` and give none;
  - `lets skip it` and `lets move on`. `let's` is in `_MODALITY`;
  - the n't forms `maynt` and `usednt`;
  - the n't forms with a modifier-letter apostrophe, "don", U+02BC, "t know". `_CURLY` (`:129`) maps only U+2018 and U+2019. U+02BC is a letter to `_PHRASE`, so it passes the phrase gate, and `_words` splits it into `don` and `t`, so neither the `n't` suffix rule nor the new spellings catch it. With the backtick, the acute accent and U+2032 the phrase gate fails and no item is given.
- The persons spellings cannot be closed by a plain strip: `ill`, `id`, `were`, `wed` and `well` are words, so stripping `i'll`, `i'd`, `we're`, `we'd` and `we'll` would cost recall on ordinary phrases. A closed set of the unambiguous ones (`im ive youre youll youd youve weve`, plus `lets`, `maynt` and `usednt`, and U+02BC folded in `_CURLY`) is cheap. The ambiguous ones are a ruling for the controller. None has a fixture.

**N6. The frame words inside the "or" comma part still count as options, on shipped line 1.** `harvest.py:893` (`_options`, the part-wide rule). Same shape as N3, narrower, and the spec does not state it.

- "No wrong answer: tea or coffee on a cold morning, if you had to choose?" gives the options coffee, cold, morning, tea. So `I'd choose a cold morning.`, `I'd go with the cold morning.` and `I'd pick the morning.` give a `taste` item.
- The same part-wide rule, with no frame to blame: `I'd go with the seat.` on "a window seat or an aisle seat", and `I'd choose the only sea.` on "Mountains or the sea, if you could only pick one?" (the subset rule admits "only", and one option word is enough).
- Impact is low: no target says "I'd choose a cold morning" to that question, and the shared noun ("the seat") is a vague answer, not a wrong one.
- A closed fix, if wanted: end each alternative at the first preposition after its head ("tea", "coffee", stopping at "on"). Or state it in spec section 9 beside the other residuals. The `_options` docstring's claim that the question's frame names no option is overstated for this line.

**Doc nit.** The spec's section 9 paragraph now reads "[fix round 2, the re-review's N2] ... its cost is 'sooner or later it boils'. Its cost: a true completion holding such a word ('is never where it should be', 'will be late again') gives none either." The old "Its cost:" sentence now follows the N2 sentence, so it reads as the cost of the "or" rule. Move the N2 insertion after it.

## Probe results

| Probe | Result |
|---|---|
| `probes-task8/heldout_detectors.py` | completion 6/6 precision, 6/10 recall; taste 10/10, 10/10. As round 1 and the report. No regression. |
| `probes-task8-rereview/fresh_detectors.py` | As the report (above). The four round 1 false positives are closed. |
| `p0_fixtures_and_spellings.py` | 112 fixtures, 0 mismatches. 24 n't spellings: 22 closed, `maynt` and `usednt` open. Neighbours: N5. |
| `p1_or_and_taste.py` | 31 N2 forms and 5 quoted forms; the 8 shipped taste lines' `_options`; 34 shipped-line taste cases, 28 as expected and 6 not (all N6 or the part-wide rule); `_options` on 14 odd shapes, none raised. |
| `test_probe_n4_halves.py` | 14 cells; each half fails on its own mutation. |

Other probe results, quoted:
- N2, quoted with "or" outside the quote: `I'd say "hums" or whistles.` gives `hums`. `I'd say "hums" or something like it.` gives `hums`. `I'd say "hums", or maybe "whistles".` gives none (a second quotation mark in the tail).
- `_options` on lists: `Choose one: the red door, the blue door, or the green door.` gives blue, door, green, red. `Tea, coffee, or juice?` gives coffee, juice, tea. `Tea or coffee? Tell me which you prefer.` gives coffee, tea. `Do you prefer tea or coffee?` gives coffee, do, prefer, tea, you (`do` and `you` cannot enter an object).

## Out-of-scope observations

- **A list with no Oxford comma loses its first item.** `Pick one: tea, coffee or juice?` gives the options coffee and juice only, so `I'd pick tea.` gives no item. A line with no "or" at all (`Tea, coffee, juice?`) gives no options. Recall only; no shipped line has either shape. No test pins that every shipped taste line yields an item for some natural answer, so a future sheet line of the other shape would silently never fire. A test over `sheet.taste_bank` (each line gives an item for "I'd pick <first option>") would close that.
- **The quoted completion with the "or" outside the quote** (above) is the N2 shape split across the quote boundary. The speaker's first offer is still the target's own words, so it misattributes nothing. It is a doubtful case, so I leave it to the controller.
- **The meta-reply residual** (controller ruling, carried to the 7b rung): nothing new in kind. The same four forms as round 1 (`gonna pass on this`, `out of ideas here`, `that's an odd prompt`, `too hard to finish`). Newly measured members of the same residual: open-lexicon negations that are not n't forms (`nothin comes`, `nuthin`, `naw`, `nay`, `nada`, `zilch`, `negative`, `idc`) give an item, and so do `that's`, `it's` and `what's` without their apostrophe (`thats hard`, `its a riddle`, `whats next`). They are lexical and belong to the 7b measurement, not to this round. N5 is the spelling gap of closed classes and is not part of the residual.
- **The report's "Fix round 2" claims** hold as stated: the 15 new fixtures, 97 to 112 (22 positives and 90 near-misses), the fresh-probe table and the held-out numbers. The RED and gate lines were not re-run.
