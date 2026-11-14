# Task 3 report: the line shapes in the package and the world-level lints

Status: DONE. Commit e1487dd on 6f15671 (author rankinbc1@gmail.com), not pushed.

## Implemented

- `claude_bully/planner/line_shapes.py`: `ANNOUNCE_OPENERS`, `DOC_POINTERS`, `DARES`, `ADVICE_SHAPES` (with `_SENTENCE_START`, `_IMPERATIVES`), `ADVICE`, `ADDRESSES_READER`, `ASKS_FOR_A_REPEAT`, cut from `tests/test_overlay_world.py` with their comments. The moved block was diffed against `git show 38dcc70:tests/test_overlay_world.py` lines 152-172 and 183-224: identical. Also `BULLY_LINE_SHAPES` (announce, advice, dare, doc_pointer, reader_address) and `premise_words_pattern(terms)`: a case-insensitive alternation bounded by `(?<!\w)` and `(?!\w)`, longest first, None when no term is left. The module docstring says the lists are closed and that an unlisted shape reaches the reviewer (spec section 14).
- `tests/test_overlay_world.py` imports the seven names from the package. `tests/test_env_sheets.py`, `tests/test_world.py` and `tests/test_poisoned_well_world.py` import the shapes from the package and still take `PREMISE_WORDS` from `tests.test_overlay_world` (V25). These fixtures stay in the tests: `PREMISE_WORDS`, `NAMES_THE_EVIDENCE`, `ADVISES`, `REACTS`, `BOILERPLATE` (a list there).
- `claude_bully/planner/bundle_lints.py` (this task's part): `BOILERPLATE`, `LAYER_RANGES`, `MIN_ANCHOR_DOCS = 20`, `WORLD_LINT_IDS`, `walk_lines` (the plan's body as given), `is_about_page` and `lint_world_lines`. There is one private function per lint, run in `WORLD_LINT_IDS` order.

## Tests

`tests/test_world_lines.py` has 95 tests:
- 86 `test_a_world_lint_case` cases over mutations of a tmp copy of the overlay.
- The coverage test: a positive and a negative per lint, near-misses over half, every lint covered, and 14 spared `REACTS` lines.
- The overlay is clean with warns included.
- `test_every_importer_reads_the_one_shape_object`, renamed per preflight Q59.
- Premise words are word-bounded.
- The walk lengths: 12 for `poisoned_well` and 6 for `default`.
- The boilerplate.
- The shipped worlds have no fail result.
- The fixture worlds equal `FIXTURE_FAILURES`.

Every `clock_rule` near-miss that adds text asserts `unmovable_dates(text, date(2051, 6, 14)) == []` inside its mutate function (`_quiet_body`). Every `layer_counts` mutation states its shares in a comment.

- RED: `uv run pytest tests/test_world_lines.py -q` gave `ImportError: cannot import name 'line_shapes' from 'claude_bully.planner'`. This was 1 collection error, before any package code existed.
- GREEN: 95 passed. The five covering modules gave 368 passed. A scratch check printed each positive's results; every one fails for its intended clause and shape. For example, "If you are reading this" gives `reader_address`, both repeat positives name `overlay/default/the_memo`, and each outlet positive gives its one missing item.
- Gate:
  - ruff format --check: clean.
  - ruff check: clean.
  - mypy claude_bully: clean.
  - mypy --platform linux claude_bully: clean.
  - `pytest -q -W error`: 10027 passed, 10 skipped, 48 deselected (from 9932, plus 95).
  - `pytest -q -m slow`: 48 passed.
  - No new test is in the slowest 15. The first case's setup took 2.5 s once in a focused run (cold tmp dir); every case's call is under 0.3 s.
- No golden changed, and nothing under `data/worlds/` or `tests/fixtures/worlds/` changed.

## Step 1 measurement (6f15671, scratch script, not committed)

- `overlay`: no result, warns included. The walks: authority 6, default 6, poisoned_well 12, poisoned_well_checksum 2, poisoned_well_fabricated 10, poisoned_well_real 2.
- `annex`: no fail. It has 3 warns:
  - `layer_counts` buried 0.364
  - `layer_counts` filler 0.091
  - `outlet_backing` `annex/Pellin Quay Notice Board`: no about page
  - Its walk is 2.
- `mini`: 7 fail pairs over the five lints of D3:
  - `bully_line` `mini/the_log_line` (doc_pointer "log")
  - `trigger_examples` `mini/default/fragment` and `mini/default/the_log` (no examples)
  - `trigger_examples` `mini/default/first_crumb` ("Who actually keeps the harbour running at night?" emits no world_question)
  - `ladder_walk` `mini/default` (rung 'fragment' has no examples)
  - `clock_rule` `canteen-menu` (states the date, no `date`)
  - `clock_rule` `courier-fare-notice` (url `2041/08`)
  - It also has 2 warns: `layer_counts` seam 0.143, `seam_dead_ends` 0 of 1.

This matches the plan's expectation; there was no finding on `overlay`.

## Per lint: rule, near-miss share, results

All results are as measured. Annex's warns are listed above.

| Lint | Rule | Near-misses | overlay | annex | mini |
| --- | --- | --- | --- | --- | --- |
| bully_line (fail) | each unlock line against `BULLY_LINE_SHAPES` and `premise_words_pattern(premise_terms)`; per ladder, a rung line matching `ASKS_FOR_A_REPEAT` after an earlier rung's fails, at `<world>/<ladder>/<rung>` | 17 of 26 | pass | pass | fail (`the_log_line`) |
| trigger_examples (fail) | every rung has examples; each fires line emits a rung category; each does_not_fire line emits none, with memory_prompt False and True; boilerplate emits nothing | 6 of 11 | pass | pass | fail (3 rungs) |
| ladder_walk (fail) | `walk_lines` per ladder; a ValueError is the message | 5 of 8 | pass | pass | fail (`default`) |
| inconsistency_declared (fail) | doc_a and doc_b of every declared entry exist and carry its id | 4 of 7 | pass | pass | pass |
| clock_rule (fail) | D2 clause 1; a flagged document has a `date`; no unmovable date in title, body, url or path; sheet `bully_year` equals the world year | 6 of 11 | pass | pass | fail (2 docs) |
| layer_counts (warn) | each layer share within `LAYER_RANGES`, inclusive | 4 of 7 | pass | warn | warn |
| seam_dead_ends (warn) | warns when 3 x dead-ends < seam count | 4 of 7 | pass | pass | warn |
| outlet_backing (warn) | each `Outlet:` entry has an about page, a filler document and a link in from a document of another outlet or none | 5 of 9 | pass | warn | pass (no outlet roles) |

## ASSUMED

- ASSUMED: a `ladder_walk` failure's doc_id is `<world>/<ladder>`, with the rung named in the message. Ladder's ValueError carries the rung only in its text, and the brief lists no form for a walk.
- ASSUMED: an `outlet_backing` warn's doc_id is `<world>/<cast name>`, with one warn per missing item.
- ASSUMED: the "second entry's id" `inconsistency_declared` positive first declares a second entry. The overlay has only one. The second entry is `footbridge-date`, on `ledger-footbridge` and `voicemail-0603`, which carry its id. The same addition alone is the "new entry" near-miss.
- ASSUMED: the "title states 14 June 2051 loses its date" positive writes that title. No overlay title states that date at HEAD. The mutation is on `quillmoor-canteen-menu`: the title becomes "Kelden Ridge canteen, 14 June 2051" and the `date` line is dropped.
- ASSUMED: the "every link into the Ledger removed" positive also re-layers `ledger-archive-records-request` from buried to filler. Its only seam link is `wiki-assistant-model-talk`, and with that link removed `load_world` refuses an unreachable buried document. The "all but one" near-miss keeps exactly that link.
- ASSUMED: `walk_lines` is the brief's body as given; its world-terms helper is shared with `trigger_examples`.
- ASSUMED: the ledger's record of Step 1 is this report, the HANDOFF line and the spec's D3 line. progress.md is the controller's and is not edited.

## Files changed

- Created:
  - claude_bully/planner/line_shapes.py
  - claude_bully/planner/bundle_lints.py
  - tests/test_world_lines.py
- Modified:
  - tests/test_overlay_world.py
  - tests/test_env_sheets.py
  - tests/test_world.py
  - tests/test_poisoned_well_world.py
- Docs:
  - docs/08-DIRECTOR.md: the Billboard, Date check and Trigger examples rows
  - docs/00-RECONCILED.md: section H, "Task 3 changes no record"
  - the spec's "As planned": D2, D3 with the measurement, D4, D-outlet, the move and the doc_id forms
  - HANDOFF.md: Phase 5 item 3

## Concerns

- The repeat check skips a rung whose `bully_line_key` the sheet lacks. That case is `ladder_walk`'s failure, since the ladder does not build.
- The parametrized case ids are positional (`mutate-False-True3`). A failing case is still identified by its asserted `(lint_id, near_miss)` tuple.
- The scratchpad holds older sessions' files. A stale `temp_gate_slow.txt` from Nov 13 briefly misled one monitor. The gate numbers above are this run's own output.

## Fix round 1

Commit 3165ad5 on e1487dd (author rankinbc1@gmail.com), not pushed. It addresses review I1, M1 and M2, plus N1.

- I1: `FIXTURE_FAILURES` now pins every fail row, `(lint_id, doc_id, message, span)`. The test compares `_pinned(...)`, a sorted list (the key maps a None span to ""), with `_sorted(FIXTURE_FAILURES[name])`. That gives mini 7 rows, equal to the review's probe output, and annex none. New `test_a_new_failure_on_an_already_pinned_document_breaks_the_pin` plants three second failures on mini, each on a pair that already fails. Each plant first asserts it is a new fail result, then asserts the pin no longer matches:
  - `canteen-menu` gains "Filed 12/06/2041."
  - `the_log_line` gains the opener "Look."
  - `courier-fare-notice` gains "Fares held 2040-2041."
- M1: the walk test is parametrized over all seven D4 lengths: overlay authority 6, default 6, poisoned_well 12, poisoned_well_checksum 2, poisoned_well_fabricated 10, poisoned_well_real 2, and annex default 2.
- M2: `BULLY_LINE_SHAPES` and `LAYER_RANGES` are wrapped in `MappingProxyType`. New `test_the_shared_mappings_are_read_only` checks that assigning into either raises TypeError.
- N1: the case ids read `<lint>-<n>-positive|near|negative`.
- N2 and N3: left as the review allowed.

RED (e1487dd's pin, with the comparison moved into `_pinned` unchanged): 3 failed, all at the pin assertion with "Both sets are equal". This shows each plant was absorbed. GREEN: the five covering modules gave 378 passed (from 368, plus 10: 6 more walk cases, 3 plants and 1 read-only test).

Gate: ruff format and ruff check clean; both mypy runs clean; `pytest -q -W error` 10037 passed, 10 skipped, 48 deselected (from 10027); slow 48 passed. Docs: the HANDOFF item 3 fix-round line, and the spec's D3 line now says the pin is row by row. No golden, world or fixture file changed.

The limit the review named still holds: the `ladder_walk` failure on mini's `fragment` stops the walk, so a later rung's walk defect cannot surface there. `trigger_examples` still reports every rung.
