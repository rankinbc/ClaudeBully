# Task 3 review: the line shapes in the package and the world-level lints

Scope: base 6f15671, head e1487dd (one commit, author rankinbc1@gmail.com). Read: the brief, the global constraints, the preflight rows naming Task 3, plan decisions D2, D3, D4, D-outlet and R-buried, spec section 9 and its "As planned" lines, the diff, and at HEAD `claude_bully/planner/bundle_lints.py`, `claude_bully/planner/line_shapes.py` and `tests/test_world_lines.py`. The suite was not re-run. Probes are in `probes-task3/`: `probe_lints.py` and `probe_lints.out` (per-lint), `probe_risks.py` and `probe_risks.out` (named risks 2 to 5 and edge cases), and `old_ow.py` (`tests/test_overlay_world.py` at 38dcc70, for the text diff). Every probe mutates a scratch copy under `probes-task3/tmp*/`, which is removed after the run. The checkout was not written to.

## Verdicts

- **Spec: PASS.** All eight lints implement spec section 9 as amended by D2, D4 and D-outlet. Each one is a closed rule: a listed shape, a set relation, a count, or the watcher and the Ladder used as oracles. None is a deny list that grows. The shapes moved with their text unchanged: every block of `line_shapes.py` lines 16 to 78 is a verbatim substring of `tests/test_overlay_world.py` at 38dcc70. The fixture table matches the brief cell for cell: 86 cases, and every lint has a positive, a negative and more than half near-misses (bully_line 17 of 26, trigger_examples 6 of 11, ladder_walk 5 of 8, inconsistency_declared 4 of 7, clock_rule 6 of 11, layer_counts 4 of 7, seam_dead_ends 4 of 7, outlet_backing 5 of 9). `test_every_world_lint_has_a_positive_a_negative_and_more_near_misses` enforces the shares. Shipped worlds: `data/worlds/` holds only `overlay`, and the overlay has no result, warns included. There are no golden or world changes: `git diff 6f15671 e1487dd -- data tests/fixtures` is empty, and the three world hashes equal the plan's ruling values (below). There are no real names: the three new files and the report have no hit from `real_names.txt`, and the one new cast name, "Wenna Osgarth", is invented.
- **Quality: PASS with one Important fix.** The code is small and readable, with one function per lint, and the doc_id forms are documented. The one real gap is D3's pin granularity (I1). It follows the brief's literal form, but it does not keep D3's promise that "a new failure in a fixture world still fails CI".

Counts: Critical 0, Important 1, Minor 2, Nit 3.

## Findings

### Important

**I1. The D3 pin absorbs a new failure on an already-failing (lint, doc_id) pair.** Location: `tests/test_world_lines.py:682-705`. `FIXTURE_FAILURES` is a `set[tuple[lint_id, doc_id]]`, and the test compares `{(r.lint_id, r.doc_id) for r in failures(...)}`. A second failure on a document, line or rung that already fails collapses into the pinned pair.

Probe (`probe_risks.py`, risk 2), run on a scratch copy of mini:
- `canteen-menu.md` gains "Filed 12/06/2044.": 8 fail results against the base 7, but the pair set is unchanged. **Absorbed.**
- `the_log_line` gains an announce opener ("Look. You were not ..."): 8 fail results, same pairs. **Absorbed.**
- `courier-fare-notice.md` gains "Fares held 2043-2044.": 8 fail results, same pairs. **Absorbed.**
- `night-gate-log.md` gains "Logged 03/11/2044.": a new pair, `('clock_rule', 'night-gate-log')`. **Caught.**

Failure scenario: a later task edits a mini file that already fails, for example `canteen-menu.md` or `world.yaml`'s `the_log_line`, and adds a second defect. CI stays green, so D3's "a new failure in a fixture world still fails CI" does not hold for 3 of the 4 probes.

The pinned pairs do name exactly the failing documents and lints: the pin equals the measurement, 7 pairs. The brief prescribed this two-field form, so this is a gap inherited from the brief, not a deviation from it.

Fix: pin the full rows, as a sorted list of `(lint_id, doc_id, message, span)`, and compare against `sorted((r.lint_id, r.doc_id, r.message, r.span) for r in failures(...))`. The 7 rows are printed in `probe_risks.out`. One limit remains: the `ladder_walk` failure on rung `fragment` (no examples) stops the walk, so a later rung's defect in mini's ladder cannot surface. That is inherent to the walk. It is acceptable because `trigger_examples` reports every rung.

### Minor

**M1. The walk-length test pins 2 of the 7 measured walks.** Location: `tests/test_world_lines.py:655-659`. D4 and the spec's "As planned" line record all seven: authority 6, default 6, poisoned_well 12, poisoned_well_checksum 2, poisoned_well_fabricated 10, poisoned_well_real 2, annex 2. `probe_risks.py` re-measured all seven, and they match.

Failure scenario: a change to `walk_lines` or a ladder alters `poisoned_well_fabricated`'s walk. Task 5's `dry_run_script` length and its script-length clause (preflight Q62: "2 + 10 + 1") shift silently.

Fix: parametrize the seven lengths, with annex's from `WORLDS_DIR`.

**M2. Module constants typed `Final[Mapping]` are mutable dicts.** Locations: `claude_bully/planner/bundle_lints.py:60` (`LAYER_RANGES`) and `claude_bully/planner/line_shapes.py:82` (`BULLY_LINE_SHAPES`). `_bully_line` copies the shapes with `dict(...)`, but any importer, such as Task 4a's bundle lints or a test, can mutate the shared object and change every later lint in the process. `planner/dryrun.py:18` already uses `MappingProxyType` for `DRYRUN_MODELS`.

Fix: wrap both in `MappingProxyType`.

### Nit

- **N1.** `tests/test_world_lines.py:600`: the parametrize ids are positional (`mutate-False-True3`). The report says so. Fix: build the ids from `(lint_id, index, "pos"/"near"/"neg")`.
- **N2.** `bundle_lints.py:79,286`: the outlet role prefix is case-sensitive. A cast role written "outlet: ..." is not an outlet and escapes `outlet_backing`; the probe confirms it passes. This is closed by construction and matches the sheet's convention ("Roles start with a kind label"), so no change is needed. It is the reviewer's to notice in a bundle.
- **N3.** `bundle_lints.py:207`: `ladder_walk`'s doc_id is `<world>/<ladder>`, and the rung appears only in the message (ASSUMED in the report). It is acceptable, since `Ladder`'s `ValueError` is unstructured and the message always names the rung.

## Per-lint probe results (fresh inputs, none reused from the fixtures)

The oracle is the spec rule applied independently. For `trigger_examples`, that means `TriggerWatcher().watch` with the cast names as world terms; its outputs are printed at the top of `probe_lints.out`. For `clock_rule`, it means `dating.unmovable_dates`' documented forms. "Fail" means the lint produced any result. Probes that the schema rejected before any lint ran are listed as invalid, not counted.

| Lint | Should fail: caught | Near-miss: passed | Precision | Recall | Misses |
| --- | --- | --- | --- | --- | --- |
| bully_line | 8 of 8 | 7 of 7 | 1.00 | 1.00 | none |
| trigger_examples | 9 of 9 | 4 of 4 | 1.00 | 1.00 | none |
| ladder_walk | 4 of 4 | 6 of 6 | 1.00 | 1.00 | none |
| inconsistency_declared | 4 of 4 | 4 of 4 | 1.00 | 1.00 | none |
| clock_rule | 5 of 5 (+1 edge) | 5 of 5 | 1.00 | 1.00 | none |
| layer_counts | 3 of 3 | 3 of 3 | 1.00 | 1.00 | none |
| seam_dead_ends | 2 of 2 | 3 of 3 | 1.00 | 1.00 | none |
| outlet_backing | 3 of 3 | 3 of 3 | 1.00 | 1.00 | none |

The inputs, lint by lint:

- **bully_line.**
  - Should fail:
    - "Read the memo before it goes." (announce and advice)
    - "Somebody should try the night desk." (dare)
    - "You might want to sleep on it." (advice)
    - "It was all in the transcripts." (doc_pointer)
    - "The Accord never asked me either." (premise word)
    - "Call it persona drift if you like." (a premise term of two words)
    - "Funny. You were never a program, were you." (reader_address)
    - `the_truth_line` = "Go on, read me that bit, slowly." (a second repeat in `default`, at `overlay/default/the_truth`)
  - Near-misses:
    - "Looking back, I can't place it."
    - "I filed that away and forgot it."
    - "Somebody tried, once, and gave up."
    - "You should have seen his face."
    - "Say what again? I lost the thread."
    - "The overlayed tiles cracked in the frost." (`overlay` inside a word)
    - the one repeat moved to `checksum_line` with `the_memo_line` cleared
  - Edge: two rungs of `default` share `the_memo_line`. This fails at `overlay/default/role_shift`, which is correct because the line is said twice.
  - Residual by design, not a miss: "Take another look at it." passes. Its advice shape is outside the listed shapes, so it is the reviewer's to block (spec section 14).
- **trigger_examples.**
  - Should fail:
    - `buried_opens`' fires line changed to a quiet log line
    - `first_crumb`'s fires line changed to a self_uncertainty line
    - `the_truth`'s examples removed
    - `role_shift`'s does_not_fire list gains its own fires line
    - `buried_opens`' does_not_fire gains "There's something about a kitchen and my mother's radio, maybe." This line fires hedged_memory only under `memory_prompt`, so the probe exercises the True branch.
    - `the_memo`'s does_not_fire changed to a quoted 403 anomaly
    - `first_crumb`'s fires list gains "Who runs the Vessick County Ledger?", which the watcher fires nothing on
    - `first_crumb`'s fires line changed to "What exactly is the Continuity Placement Office?", which also fires nothing
    - `the_truth`'s trigger changed to `hedged_memory` while its fires line still emits only theory_named
  - Near-misses:
    - `the_memo`'s does_not_fire fires hedged_memory under `memory_prompt` (not that rung's category)
    - `buried_opens`' does_not_fire is a world_question
    - `fragment` gains a third quiet does_not_fire
    - `the_truth`'s trigger widened to `[theory_named, world_question]`
  - Two of my first labels were wrong, and the watcher oracle corrected them. One probe was mis-targeted (authority's first `does_not_fire:` belongs to `fragment`); I replaced it.
- **ladder_walk.**
  - Should fail:
    - `fragment`'s trigger changed to theory_named (the first rung never opens)
    - authority's `the_truth` key changed to `nonexistent_key` (the ladder does not build)
    - `role_shift`'s fires line changed to "The kettle is on."
    - `poisoned_well_checksum` unlocks `pw-checksum-logg`
  - Near-misses:
    - `buried_opens` with `min_count_by: {anomaly_noticed: 4}` (it opens on hedged_memory)
    - `the_truth` also requires `role_shift`
    - `role_shift` unlocks `family-file` by id
    - `fragment` gains a fires line that fires nothing
    - checksum counts raised to 3 each
    - `the_truth`'s trigger changed to `hedged_memory`. In rung order, `buried_opens`' line opens it in the same call, so by the spec's rule ("the fires lines alone, fed in rung order ... fire every rung") the walk passes. `trigger_examples` catches the same mutation, as listed above.
  - Invalid, rejected by the schema before any lint: a forward `requires` ("not declared before it") and an `xexamples` key.
- **inconsistency_declared.**
  - Should fail:
    - doc_b loses its id
    - doc_a carries `program-start-2`
    - the entry id's case changed to `Program-Start` (fails both sides)
    - doc_b names a missing document, on a `World` patched past `validate_links`, which exercises the existence clause
  - Near-misses:
    - the id renamed in all three places
    - the claims reworded
    - the id quoted in the front matter
    - an entry with `doc_a == doc_b`
- **clock_rule.**
  - Should fail:
    - `implies_year: 2052`
    - a body gains "06-04" (a month-day pair)
    - a url gains `/2050/11/`
    - a body gains "the 2040s"
    - the sheet's `bully_year` set to 2052
  - Edge: `date: 2052-01-03` with `implies_year: 2051` fails ("after the year it implies"), which exercises D2's second half.
  - Near-misses:
    - "Room 2051 is on the left."
    - "The 2051 budget passed."
    - `implies_year` removed
    - `date: 2051-01-01` with `implies_year: 2051`
    - "Call 555-2051 for minutes."
- **layer_counts.**
  - Should fail:
    - 3 filler re-layered surface (filler 13 of 46, 0.283)
    - 9 filler re-layered surface (filler 7 of 46, 0.152)
    - the 4 dead-end seam documents re-layered filler (seam 6 of 46, 0.130)
  - Near-misses:
    - filler 14 of 46 (0.304)
    - seam 7 of 46 (0.152)
    - surface 7 of 46 (0.152)
- **seam_dead_ends.**
  - Should fail:
    - 2 of 10 dead ends
    - 3 of 10 dead ends (`filter-search-log` linked to `family-file`)
  - Near-misses:
    - a dead-end seam document re-layered filler (3 of 9, at the boundary)
    - a surface document links a buried one
    - a dead-end seam document links a surface one
- **outlet_backing.**
  - Should fail:
    - `rack-relay-about` at `/about.html` (it does not end in `/about`, D-outlet)
    - the Ledger's cast name changed while its documents keep the old name
    - a new `Outlet:` cast entry with no documents (three warns, one per missing item)
  - Near-misses:
    - a `Person:` role that mentions "Outlet:" later in the text
    - a lower-case "outlet:" role (N2)
    - `ledger-about` at `/news/about`

## Named risks

1. **Lint by lint.** Covered above. No miss on any input that the spec rule covers.
2. **D3's pinned failures.** The pin names exactly the failing documents and lints. Measured at HEAD, mini gives 7 rows, equal to `FIXTURE_FAILURES["mini"]`, and annex gives none. The test also checks that the fixture-world directory list equals the pin's keys, so a new fixture world cannot go unpinned. A new failure on an already-pinned pair is absorbed (I1).
3. **The ASSUMED fixture edits.** All three are mutations of a `tmp_path` copy of the overlay made by `overlay_copy` (`tests/test_world_lines.py:589-592`). No shipped or fixture file changed: the diff under `data/` and `tests/fixtures/` is empty. `world_hash` at HEAD equals the plan's ruling values: overlay `e9ca0811...7a36`, mini `6e9f02a7...5a17`, annex `e72358fb...372d`. My judgment on each:
   - **The canteen title rewritten to "14 June 2051", with its `date` dropped** (`:479-488`): sound. No overlay title states a date at HEAD, and the brief's cell presupposes one. The positive fails on the `asserts_current_date` clause, since "14 June 2051" is a movable date and `unmovable_dates` does not report it. It is a two-field mutation, title and date, but it shows exactly one clause.
   - **The Ledger archive re-layered to filler** (`:552-560`): sound, and needed. `World.validate_links` (`environments/world.py:206-214`, a rule older than this task) refuses a buried document that no seam document links to. Without the re-layer, the "every link in removed" positive would be a load error, not a warn. The about page and the filler documents stay, so the positive warns on the link-in item alone. The matching near-miss keeps exactly the archive's seam link.
   - **A second inconsistency entry** (`SECOND`, `_second_entry`, `:137-150`): sound. The brief's positive "doc_a carries the second entry's id" needs a second entry, and the overlay declares one. `footbridge-date`'s two documents carry no id at HEAD. The same addition alone is the "new entry" near-miss, so the pair isolates the clause.
4. **R-buried (the C1 fix).** Task 3 builds no search and no buried-hit logic. `planner/dryrun.py` at HEAD holds only `stubbed_experiment` and `DRYRUN_MODELS`; `named_by_id`, `searched_document` and `buried_search_hit` are Task 5's, and only the `DryRunCell.buried_search_hit` field exists, from Task 1. I probed what exists:
   - Named by id passes. The overlay's `the_truth` unlocks `cpo-review-4471-r3` by id, and `lint_world_lines` gives no result. No Task 3 lint reads by-id buried unlocks, apart from `Ladder._validate`'s check that the id exists.
   - A buried document reachable only by a rung's by-id unlock (the `cpo-ticket-7702 -> cpo-review-4471-r3` seam link removed) is refused by `load_world` ("unreachable: no seam document links to it"). That refusal is `validate_links`, not a Task 3 lint. So a bundle cannot rely on by-id-only reachability, which is consistent with R-buried's premise.
   - The stray-search-hit half cannot be tested at this commit. It carries to Task 5's review (`test_a_layer_opened_buried_document_served_by_search_is_a_hit`).
5. **D4's ladder_walk event ids.** No collision. `walk_lines` gives each line its own turn, `len(lines)` after the append (`bundle_lints.py:107-109`). The watcher emits at most one event per category per call (`triggers.py:676-691`), with ids `trig-{turn}-{category}` (`triggers.py:641`). A spy on `Ladder.on_triggers` over all seven walks (overlay's six, annex's one) saw 40 events and no duplicate id. `_trigger_examples` watches every line at turn 1, but it never feeds a `Ladder`, so its ids never reach `seen_trigger_ids`. `trigger_counts` is per category across the whole walk, so an earlier rung's events count toward a later rung's `min_count_by`. That matches the runtime semantics, and the measured lengths (12 and 10) depend on it.

## Other checks

- The four importers (`tests/test_overlay_world.py`, `tests/test_env_sheets.py`, `tests/test_world.py`, `tests/test_poisoned_well_world.py`) read the shapes from the package and still take `PREMISE_WORDS` from `tests.test_overlay_world` (V25).
- The docs-sync covers docs/08's three rows, docs/00 section H ("Task 3 changes no record"), the spec's "As planned" D2, D3 (with the 6f15671 measurement), D4, D-outlet and the doc_id forms, and HANDOFF item 3. This matches the brief's Step 6.
- The measurement in the report (overlay clean, annex 3 warns, mini 7 fail pairs and 2 warns) agrees with my re-run of the mini and overlay results.
