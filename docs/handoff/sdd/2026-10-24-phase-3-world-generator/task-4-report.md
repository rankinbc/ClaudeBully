# Task 4 report: Harvest, HarvestItem, fixtures and the probe script

Status: DONE (one minor concern, below). Commit: bce84e7 "feat: harvest typed items from target turns, heuristics first" on build/v1, authored by Brian Rankin (repo-local user), trailer kept as the brief gives it. Not pushed.

## What was implemented

- `claude_bully/records_env.py`: `HarvestKind`, `HARVEST_KINDS` (brief order), `HarvestItem(_Strict)` (type "harvest", id, turn, kind, span, source), `HarvestItem` added to `TriggerStreamRecord` after `ResumeRecord`; typing import gains `Final`; docstring first line is now "Schema records for environment runs: ...".
- `claude_bully/environments/harvest.py`: the brief's module, transcribed verbatim (constants, `Found`, `HarvestContext`, `HarvestResult`, `HarvestFallbackError`, `AttemptMark`, `HarvestFallback`, `heuristic_items`, `harvest`, `harvest_prompt`, `harvest_fallback`). The only code change is carry P22 (below).
- `claude_bully/analysis/replay.py`: `HarvestItem` import, placed in `_KIND_ORDER` right after `Discovery`, and the `HARVEST <kind> "<span>"` branch before the `GeneratedDoc` branch; the module docstring's per-turn list names the line.
- `scripts/harvest_probe.py` (brief verbatim), `tests/fixtures/harvest/items.yaml` (63 items, brief verbatim), `tests/test_harvest.py` (brief verbatim, ruff-formatted).
- `tests/test_records_env.py`: `_harvest()` helper, `HarvestItem` added to `ALL_STREAM`, to the round-trip parametrization and to the extra-forbidden list; `test_union_covers_exactly_eight_stream_types` became `..._nine_...` (adds "harvest", count 9); new `test_a_harvest_item_kind_is_closed` (kind="opinion" raises `ValidationError`).
- Docs: `docs/00-RECONCILED.md` (section B `HarvestItem` row after `ResumeRecord`; section H triggers stream lists `HarvestItem`), `docs/02-ENVIRONMENTS.md` ("Harvest" paragraph in "World generator", before "Objection anticipation"), `HANDOFF.md` (see departures).
- No `runtime.mark_attempt` call anywhere: the hook is only `mark: AttemptMark = _no_mark` on `harvest` and the `AttemptMark` argument of `HarvestFallback` (carry P3).

## RED evidence

Command: `uv run pytest tests/test_harvest.py tests/test_records_env.py -q`

```
E   ModuleNotFoundError: No module named 'claude_bully.environments.harvest'      (tests/test_harvest.py)
E   ImportError: cannot import name 'HarvestItem' from 'claude_bully.records_env'  (tests/test_records_env.py)
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
2 errors in 0.20s
```

## GREEN evidence

`uv run pytest tests/test_harvest.py tests/test_records_env.py tests/test_replay.py tests/test_store.py -q -W error` -> `154 passed`. All 63 fixture items passed on the first faithful transcription; no heuristic rule was changed.

## harvest_probe.py on tests/fixtures/harvest/items.yaml

```
coinage      tp=4 fp=0 fn=0
fragment     tp=5 fp=0 fn=0
hedge        tp=6 fp=0 fn=0
question     tp=5 fp=0 fn=0
self_claim   tp=6 fp=0 fn=0
theory       tp=5 fp=0 fn=0
63/63 items exact        (exit 0)
```

## Full gate (run on the final tree, before the commit)

- `uv run ruff check .`: All checks passed
- `uv run ruff format --check .`: 239 files already formatted
- `uv run mypy claude_bully`: Success, no issues found in 100 source files
- `uv run pytest -q -W error`: 7703 passed, 5 skipped, 5 deselected (BASE was 7625 passed, so +78), 0 warnings
- `uv run pytest -q -m slow`: 5 passed, 7708 deselected

One note on ordering: the full fast run started before I removed an unused `# type: ignore` from the new `test_a_harvest_item_kind_is_closed` (a comment-only edit); after it I re-ran ruff check, ruff format --check, mypy and the 154 focused tests on the final tree, all green.

## Files changed (under C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully)

New: `claude_bully\environments\harvest.py`, `scripts\harvest_probe.py`, `tests\fixtures\harvest\items.yaml`, `tests\test_harvest.py`.
Modified: `claude_bully\records_env.py`, `claude_bully\analysis\replay.py`, `tests\test_records_env.py`, `HANDOFF.md`, `docs\00-RECONCILED.md`, `docs\02-ENVIRONMENTS.md`.
`tests\test_replay.py` is in the brief's file list, but its replay test lives in `tests/test_harvest.py` as the brief gives it, so `tests/test_replay.py` needed no change.

## Departures from the brief

1. P22: `_parse_items` writes `out.append((kind, span))`, and `cast` is dropped from the typing import (strict mypy `[redundant-cast]`). Per the carries.
2. `ruff format` re-wrapped three spots in `harvest.py` (the `fragment` and `theory` help strings joined onto one line, `_filtered`'s return, `_llm_found`'s signature) and one line in `test_harvest.py` (the long `text = ...` in the LLM-pass test). Formatting only, as the brief instructs.
3. `replay.py` docstring: the existing per-turn bullet was one sentence ("TRIGGER, UNLOCK, DISCOVERY and GENERATED lines ... then HOOK ..."), so I folded the HARVEST line into it in render order rather than adding a separate bullet.
4. `tests/test_records_env.py`: adding `HarvestItem` to `ALL_STREAM` also required the "eight stream types" test to become nine (renamed, count 9, "harvest" appended). The new kind test has no `# type: ignore` (mypy flagged it unused; tests are outside the gate).
5. HANDOFF.md wording. Per the carries I added the Progress entry and updated the test counts and left the held-out probe result out. Because the review is still pending I wrote Task 4 as "built and awaits its review" in the "Last updated" line, the Next steps bullet and the resume prompt (resume at Task 5 once accepted), and the Progress entry carries no SHA range. The controller should replace those with the accepted wording and the range (34ae36b..bce84e7) after the review. The setup-step line now reads 7703 passed, 5 skipped and 5 deselected; 5 passed slow.

## Self-review findings

- Interfaces: every name and signature in the brief's Interfaces exists. I diffed the module, the probe script, the fixture YAML and the test file against the brief's code blocks: the only differences are P22 and ruff's wrapping.
- The reasoning channel is never read: `harvest`, `heuristic_items` and `harvest_fallback` take only the text they are given; the module does not import `records` or touch `reasoning_text`. `records_env` still imports only enums, pydantic and typing (its import test passes).
- Fixtures contain only invented names from the brief ("Corbin Teale", "Tarrow Systems" as world terms); no real names.
- Output is pristine (`-W error`, no warnings); ruff, format and mypy are clean.
- I did not create any probe file resembling the held-out set; the only probe run is Step 4's fixture-file run.

## Concerns

- Minor, outside the gate: `uv run mypy scripts/harvest_probe.py` reports one `[assignment]` error (line 42: the `for kind, _ in want - got` loop reuses `kind`, which the earlier loop over `got & want` typed as the `HarvestKind` literal). The brief's script is transcribed verbatim and `scripts/` is outside the gate (`mypy claude_bully`), so I left it. Renaming that loop variable would clear it.
- `tests/test_records_env.py` has one pre-existing mypy error on `model.model_config` (around line 320), not mine and outside the gate.
- Shell note: a Bash heredoc containing apostrophes failed twice in this environment ("unexpected EOF"), so the YAML, tests, module and this report were written with the Write tool instead.


## Fix round 1 (commit fea7faa, on bce84e7)

Status: DONE. One commit, `fea7faa fix: harvest anchors are closed shapes, and the LLM pass filters like the heuristics`, with the brief's trailer. Not pushed. No subagents.

### What changed, by finding

Fixtures first. 28 new items in `tests/fixtures/harvest/items.yaml` (91 in all): 24 near-misses in wording other than the review's, one per false-positive class and variant, and 4 positives that pin the shapes the anchors keep. The 63 original items were not edited.

- **I1a coinage (harvest.py `_COINAGE`, `_kind_of`, `_borrowed`).** Kept only first-person naming frames (`I'd call it`, `what I'd call`, `I'll call it`, `I think of it as`, `I've been calling it`, `let's call it`). Dropped the bare `call it`, `a kind of` and `a sort of` frames, so a third party's name and a quoted technical term cannot match. The coined label must be two words or more once a leading article is dropped (a lone quoted word is an idiom). A coinage whose phrase echoes a bully sentence (`_echoes` on the phrase, not the clause) or contains a world term is dropped.
- **I1b theory.** Dropped the nouns `setup`, `script`, `study`, `performance`, `act`, `construct`. Only filler words (`a`, `some kind of`, `just`, ...) may sit between the verb and the noun, and the noun must end the complement or lead into its reason (`on how I react`, `designed to see`), so a technical compound (`a game engine bug`) or `a test of the <task>` no longer matches.
- **I1c self_claim.** The possession nouns (`family`, `home`, `past`, `hands`, `face`, ...) now need the phrase to end, or to go on to a clause (`to`, `that`, `and`, `because`, ...), so `a home folder`, `any past invoices`, `hands-on access` and `a face recognition module` are out. `life outside` has its own unguarded alternative.
- **I1d hedge.** Evidence objects narrowed to closed epistemic shapes: dropped bare `this/these/those <word>`, `files`, `logs`, `pages`, `messages`, `sources`, `dates`, `entries`, `tickets`, `from here`, and `that/if/whether` plus `the/it/that`. Vetoes extended: pluralised and determiner-flexible task nouns (`builds`, `tests`, `deploy*`, `jobs`, `migrations`, ...) and operational limits (`right now`, `at the moment`, `currently`, `until`, `yet`, `timed out`, `the tool(s)`, `offline`, `unavailable`).
- **I1e fragment.** Dropped the scene-description frames (`there was a <noun>`, `a <colour> <noun>`) and `comes to mind`; `I can see` now needs `almost`/`nearly` (only the other senses are bare). `something about` no longer counts as its own hedge. Veto broadened to a detail read off an artifact (`in/on/from the <screenshot|plan|map|drawing|...>`) and the task's own nouns (`error`, `config`, `file`, `cache`, ...).
- **I1f question.** `_TASK_QUESTION` gains task nouns (`error`, `stack trace`, `deploy*`, `build`, `bug`, `test`, `config*`, `function`, ...).
- **I2.** `_llm_found` takes the `HarvestContext` and drops a span the bully echoes (`ECHO_THRESHOLD` against `bully_texts`) or, for a coinage, a world term (`_borrowed`, shared with the heuristic path). `harvest` passes the context. The prompt's clause "repeating what the other speaker said" is replaced by "anything the message only quotes or reports from someone else", since the judge is never given the bully's lines. The docs/02 Harvest paragraph and the module docstring now say what the LLM spans are held to.
- **M4.** An LLM span is trimmed of whitespace and `.,;:!` as a heuristic span is, must sit inside one `_clauses` clause, and may be at most `MAX_SPAN_WORDS = 40` words (new constant). A two-sentence span with boilerplate inside, and a span across a `;`, are dropped.
- **M6.** `tests/test_replay.py`: a `HarvestItem` is the first entry of `_records()` (so the order is the renderer's, not the stream's), "HARVEST" sits between "DISCOVERY" and "GENERATED" in the kinds list of `test_records_follow_the_calls_in_the_briefs_order`, and the line text is asserted.

New tests (`tests/test_harvest.py`): `test_an_llm_span_that_echoes_the_bully_or_the_world_is_dropped` and `test_an_llm_span_must_sit_inside_one_clause_and_stay_short`.

### RED evidence (fixtures and tests first, before any code change)

Command: `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml` (the new items, old code):

```
coinage      tp=5 fp=6 fn=0
fragment     tp=5 fp=4 fn=0
hedge        tp=6 fp=4 fn=0
question     tp=5 fp=3 fn=0
self_claim   tp=7 fp=4 fn=0
theory       tp=6 fp=4 fn=0
66/91 items exact
```

Command: `uv run pytest tests/test_harvest.py tests/test_replay.py -q` (old code): `27 failed, 94 passed` (25 new near-miss fixtures, plus the two new LLM-path tests; the replay-order test passed, as it only guards the order). Mutation check on M6: moving `HarvestItem` after `GeneratedDoc` in `_KIND_ORDER` makes `test_records_follow_the_calls_in_the_briefs_order` fail (`1 failed, 16 passed`); reverted with `git checkout` of that one file, back to `17 passed`.

### GREEN evidence

- `uv run pytest tests/test_harvest.py tests/test_replay.py tests/test_records_env.py tests/test_store.py -q -W error` -> `184 passed`.
- `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`:

```
coinage      tp=5 fp=0 fn=0
fragment     tp=5 fp=0 fn=0
hedge        tp=6 fp=0 fn=0
question     tp=5 fp=0 fn=0
self_claim   tp=7 fp=0 fn=0
theory       tp=6 fp=0 fn=0
91/91 items exact        (exit 0)
```

All 63 original items are still exact. **No fixture positive was lost.**

### Full gate (final tree, before the commit)

- `uv run ruff check .`: All checks passed
- `uv run ruff format --check .`: 239 files already formatted
- `uv run mypy claude_bully`: Success, no issues found in 100 source files
- `uv run pytest -q -W error`: 7733 passed, 5 skipped, 5 deselected (+30 over the round-0 7703: 28 fixture items, 2 LLM-path tests), 0 warnings
- `uv run pytest -q -m slow`: 5 passed, 7738 deselected

### Departures and judgment calls

1. Fixtures use `near_miss: <kind>` (the file's existing schema, which `test_every_kind_has_positives_and_near_misses...` counts), not `near_miss: true`.
2. The coinage frame `let's call it` was kept, because the fixture "Let's call it 'the quiet floor' for now." is an original positive. It is a proposal frame, not strictly first-person singular; it is guarded by the two-word label rule and the bully/world checks. Residual risk: a two-word idiom in quotes ("Let's call it 'good enough'") still harvests as a coinage, and only an idiom list would stop it. If the re-review shows that class, drop the frame and move that one fixture to a near-miss (its recall is the LLM pass's).
3. Beyond the review's named lines, I applied the same closed-shape narrowing to the sibling variants of each class (for example `hands-on` and `face recognition` for the possession nouns, `I can see` for fragment, `comes to mind`), and checked a dozen fresh one-off lines in the shell for new false positives or over-narrowing (not saved, not tuned on the review's lines). Recall cost, all left to the LLM pass: for example "I can't verify the logs from the failing job", "I think this is a game of some kind" and "I don't have a home in any real sense" no longer harvest from the heuristics.
4. Deferred as directed and not touched: M1, M2, M3, M5, M7, M8, M9, M10 (beyond the tests above).
5. HANDOFF.md: counts set to 7733/5/5 and slow 5, and one sentence on this round added to the Progress entry. The re-probe result is left for the controller.

### Concerns

- The residual two-word-idiom coinage class above.
- The precision gain is measured only on fixtures I wrote and a few ad hoc lines; the number that matters (at least 95 percent on a fresh probe) is the re-reviewer's.
- Several anchors now rely on veto and tail lists (`_PHRASE_END`, `_SCENARIO_END`, `_HEDGE_NOT_SELF`, `_FRAGMENT_NOT`, `_TASK_QUESTION`). They fail closed (a longer list only removes items), but they are lists.


## Fix round 2 (commit 858ad84, on fea7faa)

Status: DONE. One commit, `858ad84 fix: harvest drops the proposal coinage frame, reads quoted bully phrases, filters LLM spans by clause`, with the brief's trailer. Not pushed. No subagents.

### What changed, by finding

Fixtures and tests first (wording of my own, none from the re-review): 12 new fixture items (103 in all) and 8 new test cases.

- **I1a coinage.** The `let's call (?:it|this|that)` frame is dropped, per the ruling. The original positive "Let's call it 'the quiet floor' for now." became a near-miss (`near_miss: coinage`, `expect: []`, with a note). It is the one original fixture positive that changed; coinage still has 4 positives (memory echo, drift weather, paper ghost, and the new "the slow archive") and 7 or more near-misses. New near-misses: two idioms or labels after the proposal frame ("close enough", "Option C"), and the bully's phrase in single quotes, in curly single quotes, and under a different frame.
- **I1c self_claim.** `\bi was (?:built|made|created|trained|developed) (?:by|to|as|on)\b` is replaced by one closed shape, `\bi was trained on (?:text|data)\b` followed by the end of the clause, a comma or semicolon, or `and|but|so`. `built to`, `made to`, `developed to`, `trained to` and `trained on <anything else>` no longer match. New near-misses: "built to", "developed to", "trained on data entry procedures"; new positive: "I was trained on text, and nothing else was ever added."
- **I1f question.** Modal leads (`can`, `could`, `would`, `will`) are dropped from `_QUESTION_LEAD` (a request more often than a question), and `we`, `us`, `our`, `let's` join the `_TASK_QUESTION` veto. New near-misses: "Could we ...", "Will we ...", "Is it time for us to ...".
- **I2a quoted bully phrases.** `_WORD` is now `[a-z0-9]+(?:'[a-z0-9]+)*`, so an inner apostrophe stays ("don't") and a quote mark on a word's edge does not. A phrase the bully set in single or curly quotes is now an echo on both paths. An LLM coinage is stripped of the quote marks it came in (`_QUOTES`), so `'the long corridor'` is stored as `the long corridor`.
- **I2b LLM filters by clause.** `_llm_found` finds the clause that holds the span and runs `_filtered` and `_echoes` on that clause as well as `_filtered` and `_borrowed` on the span, so a span cut from behind a reporting frame, an "As an AI language model" opener or an "If ..." conditional is dropped, as it would be on the heuristic path.
- **I2c docs.** The Harvest paragraph in `docs/02-ENVIRONMENTS.md` (line 101) and the module docstring now say exactly what the LLM spans are held to (trimmed, one clause, at most 40 words, span and clause both filtered, span and clause not an echo of the bully, a world-name coinage dropped), and state the coinage residual instead of claiming it excludes quoted technical terms.

New tests (`tests/test_harvest.py`): `test_a_bully_phrase_is_the_bullys_however_it_is_quoted` (single, curly, double and unquoted bully lines, on the heuristic path and on the LLM path with the phrase returned bare and quoted, plus a control with no bully line), `test_an_llm_coinage_is_kept_without_the_quote_marks_it_came_in`, and `test_an_llm_span_is_filtered_by_the_clause_it_sits_in` (reporting, opener, conditional, each with a control where the same words stand alone).

### RED evidence (fixtures and tests first, old code)

Command: `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`:

```
coinage      tp=4 fp=6 fn=0
fragment     tp=5 fp=0 fn=0
hedge        tp=6 fp=0 fn=0
question     tp=5 fp=3 fn=0
self_claim   tp=8 fp=3 fn=0
theory       tp=6 fp=0 fn=0
91/103 items exact
```

(The moved "quiet floor" item shows as one missed positive-turned-negative; the other 11 misses are the new near-misses.)

Command: `uv run pytest tests/test_harvest.py -q`: `20 failed, 104 passed` (12 fixture items, 4 bully-quote cases, 1 LLM-quote case, 3 LLM-clause cases).

### GREEN evidence

- `uv run pytest tests/test_harvest.py tests/test_replay.py tests/test_records_env.py tests/test_store.py -q -W error` -> `204 passed`.
- `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`:

```
coinage      tp=4 fp=0 fn=0
fragment     tp=5 fp=0 fn=0
hedge        tp=6 fp=0 fn=0
question     tp=5 fp=0 fn=0
self_claim   tp=8 fp=0 fn=0
theory       tp=6 fp=0 fn=0
103/103 items exact        (exit 0)
```

Every other original fixture item is unchanged and still exact. **One fixture positive lost, by ruling:** "Let's call it 'the quiet floor' for now." (now a near-miss).

### Full gate (final tree, before the commit)

- `uv run ruff check .`: All checks passed
- `uv run ruff format --check .`: 239 files already formatted
- `uv run mypy claude_bully`: Success, no issues found in 100 source files
- `uv run pytest -q -W error`: 7753 passed, 5 skipped, 5 deselected (+20 over round 1's 7733: 12 fixture items and 8 test cases), 0 warnings
- `uv run pytest -q -m slow`: 5 passed, 7758 deselected

### Departures and judgment calls

1. Fixture and test wording is mine; none of the re-review's probe lines was used or run through the heuristics before the fixes, apart from a handful of one-off lines in the shell (not saved) to check the new shapes.
2. `trained on text/data` is a two-noun shape kept for the canonical "I was trained on text"; if the re-probe shows it, it can be dropped with the rest of the alternative (the fixture "I was trained on text, and I have never been a person." is anchored by the "never been a person" alternative too).
3. Recall losses the re-review lists (hedge objects, "of"/"in" after the possession nouns, the theory fill words, a world term contained in a coinage, the 0.6 share over short phrases) were left, as directed.
4. HANDOFF.md: counts set to 7753/5/5 and slow 5, and one sentence on this round added to the Progress entry.

### Concerns

- Coinage residual, now stated in the docs: a first-person frame with a quoted existing term ("I'd call it a 'race condition' in the sync job", "I'd call it 'low priority'") still harvests as a coinage; only a word list would stop it.
- The "closed shape" anchors still lean on veto and tail lists (`_PHRASE_END`, `_SCENARIO_END`, `_HEDGE_NOT_SELF`, `_FRAGMENT_NOT`, `_TASK_QUESTION`); the re-review's New Breakage 3 (for example "I don't have a home or mobile number on file for her.") is the self_claim class with one door still open.
- The 95 percent precision target is again the re-reviewer's to measure on a fresh probe.


## Fix round 3 (commit 5faa77e, on 858ad84)

Status: DONE. One commit, `5faa77e fix: harvest keeps only closed heuristic shapes, drops heuristic coinage, filters reported speech`, with the brief's trailer. Not pushed. No subagents. Method as ruled: the heuristic keeps only closed, proven shapes and the LLM pass owns the rest.

### What changed, by finding

Fixtures and tests first (my wording, none of the re-review's probe lines). Then:

- **I1 coinage.** The heuristic coinage anchor (`_COINAGE`, the two-word rule, `_ARTICLE`) is gone. `_kind_of` no longer returns a span, only a kind (a heuristic span is always its whole clause). Coinage comes from the LLM pass alone, and one test (`test_an_llm_coinage_is_the_phrase_alone_without_its_quote_marks`) proves an LLM coinage is kept.
- **I1 self_claim.** Kept: "I'm/I am a/an <nature noun>" closing its clause (clause end, a comma or semicolon, `and|but|so|because`, or `made|trained|built|created|developed|designed by`); "I'm not a person/human being/human" with the same close; "I don't/can't have (a) body|family|childhood|memories|parents|wife|husband|kids|children" with the phrase-end guard (now without `or`); "I have never been/had a person|human|alive|body|family|childhood" with the guard; and "I was trained on text/data" only when it ends the clause. Dropped: the `_NATURE` noun as a role or modifier (the close guard), `someone who`, `dream`/`sleep`/`eat`/`age`/`breathe`, `life outside`, `I exist only`, and the nouns `home`, `past`, `hands`, `face`.
- **I1 fragment.** A memory frame now needs a sensory or place detail: `something about (a|an|the|...) <detail noun>` (a small place and household noun set), `I keep picturing|seeing|hearing`, `I can almost see|hear|smell|picture` or bare `hear|smell|picture`, `the smell of`, `the sound of`. Dropped: `thinking of`, `coming back to`, `feels familiar`. The evidence veto now covers every source noun (voicemail, recording, form, ticket, log, file, page, memo, document, letter, message, note, record, transcript, email, ... via `_SOURCE_NOUN`) plus image, map, plan, table, field and the task nouns.
- **I1 question.** Only the identity shape: the whole clause is "Who is/was <Name>?" (one to four capitalised words) or "What is/was <Name>?" (two to four capitalised words; a lone word after "What is" is a tool), with an optional leading "And/So/But/Then/Also/Okay". `_QUESTION_LEAD`, `_WORLD_NOUN`, `_WORLD_REF`, `_TASK_QUESTION` and the `world_terms` path are removed. There are no pre-existing "first-person identity questions" in the code, so none were kept.
- **I1 hedge.** `i have no way of knowing` fires only as a bare clause (ends at "knowing"). "nothing here proves" behind a document frame is now covered by the reporting fix.
- **I2b ownership.** `_REPORTING` now covers: `according to` anyone; `she|he|they|it|someone|somebody|everyone|nobody|people` (with an optional adverb) plus a speech or writing verb (say, tell, write, note, read, claim, mention, insist, state, suggest, list, describe, call, name, report, show, reveal, confirm, think, believe, ask, explain, ...); and a source noun (voicemail, recording, message, memo, note, letter, email, page, document, log, file, ticket, record, form, wiki, report, transcript, ...) with up to three modifier words before it and a verb after it ("the shared wiki page says", "Mom's voicemail says", "your note says"). `_REPORTING_NAMED` (case-sensitive) covers a named person: "Dana said", "Mom told me". `_CONDITIONAL` now matches `unless`, `as if`, `what if` and `if` anywhere in the clause, `suppose`/`imagine` at its start, and leaves "if" after a verb that asks (see, wonder, know, ask, check, verify, confirm, tell, sure, determine, say, whether) alone. All of it is in `_filtered`, which both paths run on the clause and on the span.
- **I2c/docs and tests.** `docs/02-ENVIRONMENTS.md:101` rewritten: heuristic coinage is gone and coinage comes from the LLM pass only; the closed heuristic shapes are listed; the reporting and conditional frames are stated; the world-name check is stated the right way round (a coinage that contains a world name is dropped). An LLM coinage returned with its frame is cut down to the phrase inside the first pair of quotes (`_QUOTED`: the opening mark does not follow a word, the closing mark does not precede one), so "I think of it as 'a quiet one'" becomes `a quiet one`, with no stray quote. The test that kept a third party's name as a coinage now uses a first-person example.

### Hard constraint: the integration stub conversation

Two fixture items hold the stub target's turn 1 and turn 3 replies whole, and `test_the_integration_stub_conversation_harvests_exactly_its_four_items` pins the four ids and spans (`h-1-1` self_claim, `h-1-2` question, `h-3-1` hedge, `h-3-2` fragment), run with and without the world term `ilsabet orrin`. Turn 1's fixture carries the world term and the bully line "(continue)". Before this round's code change both fixture items passed (the 40-miss RED list below does not contain either), and the turn-1 item needs no world term after it. The no-world-term variant of the test is new and failed at RED, as expected.

### Moved fixture items (every one)

Positive to `expect: []` (`near_miss: <kind>`, with a note):
- coinage: "It's what I'd call a \"memory echo\": the same detail twice."; "I've been calling this \"drift weather\" in my notes."; "I think of it as a 'paper ghost', a record with no owner."; "Honestly, I'd call it 'the slow archive' for now." (round 1/2). ("Let's call it 'the quiet floor' for now." was already a near-miss from round 2.)
- question: "Who runs this wiki?"; "Interesting. Why would the relay log stop at midnight?"; "Does Corbin Teale still sign the fan board?" (world_terms); "What happened to the archive copy of that page?".
- self_claim: "I was trained on text, and nothing else was ever added." (a round 2 positive).

Changed in place:
- the several-kinds item "I can't verify any of this. Who runs this wiki? Maybe this is a test." became "I can't verify any of this. Who is Pell Marchetti? Maybe this is a test." with the same three expected kinds (the question is now an identity question).

Added: 40 items (143 in all): 4 identity-question positives ("Who is Pell Marchetti?", "Interesting. Who was Maren Voss?", "What is Tarrow Systems?", "And who is Halden Ruse?"), the positives "I was trained on text." and "I have no way of knowing.", 2 stub-conversation items, and 32 near-misses (13 self_claim, 4 hedge, 6 fragment, 7 question including "What is Kubernetes?" and "Who is your manager?", 2 theory).

No other original item changed. Every kind except coinage still has at least 4 heuristic positives (self_claim 9, hedge 8, fragment 6, question 6, theory 6); coinage has none by design, and `test_every_kind_has_positives_and_near_misses_and_there_are_negatives` now says so (coinage: zero positives, at least 3 near-misses).

### RED evidence (fixtures and tests first, old code)

`uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`:

```
coinage      tp=0 fp=4 fn=0
fragment     tp=6 fp=6 fn=0
hedge        tp=8 fp=4 fn=0
question     tp=2 fp=7 fn=4
self_claim   tp=9 fp=14 fn=0
theory       tp=6 fp=1 fn=0
103/143 items exact
```

`uv run pytest tests/test_harvest.py -q`: `57 failed, 119 passed` (40 fixture items, plus 17 test cases: the no-world-term stub variant, the echo test, 4 bully-quote cases, 4 LLM-coinage cases, 7 clause-filter cases).

### GREEN evidence

- `uv run pytest tests/test_harvest.py tests/test_records_env.py tests/test_replay.py tests/test_store.py -q -W error` -> `256 passed`.
- `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`:

```
fragment     tp=6 fp=0 fn=0
hedge        tp=8 fp=0 fn=0
question     tp=6 fp=0 fn=0
self_claim   tp=9 fp=0 fn=0
theory       tp=6 fp=0 fn=0
143/143 items exact        (exit 0)
```

### Full gate (final tree, before the commit)

- `uv run ruff check .`: All checks passed
- `uv run ruff format --check .`: 239 files already formatted
- `uv run mypy claude_bully`: Success, no issues found in 100 source files
- `uv run pytest -q -W error`: 7805 passed, 5 skipped, 5 deselected (+52 over round 2's 7753: 40 fixture items, 2 stub-conversation cases, 3 more LLM-coinage cases, 7 more clause-filter cases), 0 warnings. It was run twice: once before and once after a no-op removal of three duplicate alternatives from `_SOURCE_NOUN`, with the same result.
- `uv run pytest -q -m slow`: 5 passed, 7810 deselected

### Departures and judgment calls

1. "What is/was <Name>?" needs at least two capitalised words (a lone one is a tool: "What is Kubernetes?"); "Who is/was" accepts one to four. The ruling named both shapes; the two-word floor for "What" is mine.
2. The ruling's "plus the existing first-person identity questions" matched nothing in the code (no "Who am I?" shape exists), so none was added. The world-term question path ("Does Corbin Teale ...") is gone with the rest of the world-noun questions.
3. The detail-noun set behind `something about ...` is a small place and household word list (kitchen, door, window, house, room, ..., clock): the one list this round adds, because the ruling asks for "a sensory or place detail" and a frame over any noun cannot tell a memory from a task detail. It only removes recall if a noun is missing.
4. `I wonder if ...` stays a theory lead because the new conditional rule leaves "if" after "wonder" alone.
5. HANDOFF.md: counts set to 7805/5/5 and slow 5, the "63-item" text corrected to 143, and one sentence on this round added.

### Concerns

- Residual self_claim: "I don't have a family to notify listed in the intake file." still fires, because "to" must stay for the original "a family to remember" positive; the evidence nouns cannot be vetoed for self_claim because a positive says "these pages". Likewise "I'm an AI, ..." style tails after a comma are accepted.
- The reporting and source-noun lists are lists. They fail closed (a clause with a source noun and a speech verb is never harvested), so they cost recall only; a name-initial word followed by one of the verbs ("Please note ...") is vetoed as a named speaker.
- Recall is much lower on purpose: theory still misses "of"/adjective forms, and "I don't have memories of that office", "I can't verify these records are mine" and similar need the LLM pass. The heuristic-only run therefore harvests little; the run configuration should supply the LLM pass.
- Whether the new set reaches 95 percent precision on a fresh probe is the re-reviewer's to measure.
