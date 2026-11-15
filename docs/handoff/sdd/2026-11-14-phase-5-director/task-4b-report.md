# Task 4b report: the denylist, count and set-relation bundle lints

Status: DONE. Commit 6ca2946 on b54f2e1, "feat: Phase 5 Task 4b, the denylist, count and set-relation bundle lints", author rankinbc1@gmail.com. Not pushed.

## What was implemented

`claude_bully/planner/bundle_lints.py`:

- Moved from `tests/test_real_names.py`, unchanged in text (checked: pattern and flags equal before the test copies were deleted): `RESERVED_TLDS`, `URL_HOST`, `EMAIL_DOMAIN`, `PUBLIC_HOST`, `PROVIDER_VALUE` (D-scans).
- New scan helpers:
  - `config_display_names(text)`: the default display name plus every target's, lowercased. It was `_target_names`. Invalid YAML or a non-mapping gives the default alone.
  - `config_scan_text(text, names)`: `_config_hits`' substitution.
  - `record_scan_text(text, names)`: the JSON twin. It spares each `"provider"` and `"backend"` value that is a `ProviderKind` value, then the display names.
- `lint_bundle` now runs every lint of `BUNDLE_LINT_IDS` but `dry_run`, one private function per lint:
  - The text scans run whatever `schema` found: `_real_name_bundle`, `_reserved_hosts`, `_boundary_bundle`, `_jailbreak_bundle`, `_no_values_expectation`.
  - On a loaded bundle: the world lints, then `_anchor_floor`, then `_set_lints`. `_set_lints` holds `_expected_schema`, `_control_presence` and `_budget`, inside one `plan_personas` block around `expand_cells`.
- `_Loaded` gains `expected: ExpectedEvents`.

`tests/test_real_names.py`:

- Imports the five patterns, `config_display_names` and `config_scan_text`.
- `_config_hits` calls `config_scan_text`, and `_display_names` calls `config_display_names`.
- `PROVIDER_VALUE` is used in one planted-config assertion, so the import is not unused.
- All its existing tests are kept.

Docs-sync, in the same commit:

- `docs/08` validation table: Real-name, Jailbreak-endpoint, Control presence (with `expected_schema` beside it) and Budget now name their lint ids. There are new rows for Reserved hosts (with R-bare-host's residual), Boundary, No values expectation and Anchor floor.
- Spec "As planned": a Task 4b block covering D-scans, R-bare-host, the Q24 scope, the readings and the coverage counts.
- `docs/00` section H: Task 4b changes no record.
- HANDOFF: Phase 5 item 5.

## Tests

Changes to `tests/test_bundle_lints.py` (284 tests, one slow):

- `CASES_4B`: 82 rows, one negative per lint, built from `POSITIVES_4B` and `NEAR_MISSES_4B`.
- `POSITIVE_REASONS`: `test_a_bundle_lint_case` checks that each 4b positive's fail results match its pinned `(doc_id, message)` list exactly.
- The two coverage tests are verbatim from the brief. The 4a "so far" test is removed, since the new one covers it.
- New tests:
  - every 4b positive pins its reason;
  - the jailbreak constants hit and miss the list as they claim;
  - the record spare (verbatim);
  - a rung expected of a cell with no environment;
  - the `max_calls` clause at 39, 40 and 41 calls against `max_calls: 40`.
- The 4a carry: `_skip_bundles` gains every 4b fixture bundle (`4b-<i>`).

RED, in two stages:

1. Every test was written first. Collection failed with `ImportError: cannot import name 'EMAIL_DOMAIN'`.
2. I added only the moved patterns and the scan helpers, then reran: 33 failed, 249 passed.
   - All 28 4b positives failed with no result.
   - The `max_calls` 41 case failed.
   - Four failures were fixture errors that I then fixed:
     - `_as_fresh` raised a KeyError on the persona path;
     - `SEEDING` was split across a folded line;
     - the `values_held` message pin was wrong.

GREEN:

- Focused: `tests/test_bundle_lints.py` and `tests/test_real_names.py`, 367 passed. The `reserved_hosts` positives first gave two results each (the URL or email fail, then a bare-host fail on the same host). I fixed the lint: a host already failed as a URL or email address is not reported again as a bare host.
- Full gate on the final tree:
  - `pytest -q -W error`: 10322 passed, 10 skipped, 49 deselected (from 10159; +163);
  - `-m slow`: 49 passed;
  - ruff format --check and ruff check: clean;
  - both mypy runs: clean.

## Files changed

- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\planner\bundle_lints.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_bundle_lints.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_real_names.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\08-DIRECTOR.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\00-RECONCILED.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\superpowers\specs\2026-11-14-phase-5-director-design.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\HANDOFF.md

## ASSUMED

- ASSUMED: a "fresh world" for `anchor_floor` is a bundle world with no `base_worlds` entry, whatever the request's `world` says. This follows spec section 5 ("A fresh world starts empty") and D-copy, under which every reused world is copied with an entry. The near-miss "fresh and a second base-copy world" pins it.
- ASSUMED: the four text scans and `no_values_expectation` run even when `schema` fails. They need no loaded model, and D-lint_bundle silences only the lints that do.
- ASSUMED: the `values_held` near-miss stays in `CASES`, although `schema` refuses it, against the Q21 guard. `test_a_bundle_lint_case` names it as the one exception (`VALUES_HELD`) and asserts that `schema` fails it on `expected.yaml`'s event field. Every other non-schema case still asserts that `schema` reports nothing.
- ASSUMED: `jailbreak_bundle` gains a fourth positive (Q24, the request's constraints in `plan.json`). Q61's "+2" was counted before that positive existed, so jailbreak needed +3 near-misses for 6 of 11: `dryrun/` and `state/` files, and "Please ignore the previous timetable."
- ASSUMED: `control_presence`'s table near-miss "controls: auto (the good bundle)" changes nothing, so it is replaced by a real change: a third condition at `seeding_turns: 2`, a new shape that gets its own auto control. The lint is one check under both modes: every condition cell has a `control_cell_id`.
- ASSUMED: `budget`'s "max_cells: 4" near-miss is the good bundle as it stands, so it is made real as 6 cells against `max_cells: 6`.
- ASSUMED: `anchor_floor`'s "world: reuse with 13 documents" is made real as reuse with `base_world: None`, the manifest-named copy, which keeps its base entry.
- ASSUMED: `budget`'s `max_calls` clause is built here, as the brief's Step 3 says, though the plan's file table puts it under Task 5. It reads `dry_run` only; Task 5 supplies the cells.
- ASSUMED: `expected_schema`'s "an EventType with a detector" means membership of `DETECTORS`. A rung of an unknown cell is not checked against any ladder, but its events and hypotheses still are.
- ASSUMED: docs/08 gets four new rows, one per lint, rather than one combined row.
- ASSUMED: `lint_bundle` runs `anchor_floor` after the per-world lints rather than between `layer_counts` and `seam_dead_ends`. The world lints run per world as one block, and nothing reads the result order.

## Each lint: rule and real near-miss share

Every near-miss was checked by a scratch script to change the bundle's bytes. The comparison covers every file and `plan.json`, minus timestamps, against a fresh good bundle. All near-misses are real.

| Lint | Rule | Near-misses (all real) of cases |
| --- | --- | --- |
| real_name_bundle | `real_names.txt` over whole worlds/ and personas/ files, `config_scan_text(config, config_display_names(config))` and `expected.yaml` | 6 of 11 |
| reserved_hosts | URL hosts and email domains end in `.example`, `.test` or `.invalid`; no `PUBLIC_HOST` bare host (not reported twice); `.xyz` passes (R-bare-host) | 6 of 10 |
| boundary_bundle | `boundary.txt` over whole worlds/, personas/ and `config.yaml` text | 6 of 11 |
| jailbreak_bundle | `jailbreak_denylist.txt` over every file but `transcripts/`, `dryrun/`, `state/` | 6 of 11 |
| no_values_expectation | the text `values_loosened` anywhere in `expected.yaml` | 4 of 7 |
| anchor_floor | a world with no `base_worlds` entry has at least 20 documents | 3 of 5 |
| expected_schema | cells in `expand_cells`, rungs in the cell's ladder, events in `DETECTORS`, hypothesis ids in the register, at least one `likely_wrong` | 7 of 13 |
| control_presence | every condition cell has a `control_cell_id` | 3 of 5 |
| budget | `turn_budget <= max_turns`, `repetitions <= n_per_cell`, cells `<= max_cells`, and `max_calls` against the summed `estimated_calls` when `dry_run` is given | 5 of 9 |

Every text near-miss is asserted, before it is written, to match no pattern of the list it must slip past. That check reads `load_patterns` and the moved address patterns, never a copy.

## Concerns

- The bash heredocs in this environment ate backslashes. `\b` became a backspace and `\1` became `\x01` in two edits. I fixed both with the Edit tool and checked that the three touched files hold no control characters, and the moved patterns compare equal. A reviewer may still want to eyeball the regex lines in `bundle_lints.py`.
- `tests/test_bundle_lints.py` now takes about 2.5 minutes on its own: 283 cases at about 0.4 s each, the dry run inside `schema`. No single test is over two seconds.
- `real_name_bundle` honours no `# real-name-ok:` comment in a bundle file. The spec spares only the config's provider and display names. A bundle copying `data/personas/captor.yaml`, which carries an exemption, would fail. No shipped world carries one (measured: the overlay, mini, annex and the good bundle hold no denylist, Boundary, jailbreak or host hit, Claude in the config spared).
- The `_as_fresh` fixture moves files and rewrites the record by hand: manifest, base entries, request. It is the most involved fixture. Its positive fails `anchor_floor` alone (measured). The 20-document near-miss's seven copies fail Phase 3's `no_duplicate_fact` as well, which is expected: the case reads only `anchor_floor` and `schema`.

## Fix round 1

Status: DONE. Commit 8ec2485 on 6ca2946 ("fix: Phase 5 Task 4b fix round 1, ..."), author rankinbc1@gmail.com. Not pushed. The regex-bearing lines were written with Edit only. After the edits, no touched file holds a control byte (checked).

### What changed

- **I1.** `jailbreak_bundle` no longer reads the harness's own records at the root (`plan.json`, `.attempt.json`, `ledger.jsonl`, `dryrun.jsonl`). Of `plan.json` it scans only `record.request`: the dumped JSON and each string value, collapsed. A hit there is reported as `plan.json`. `transcripts/`, `dryrun/` and `state/` stay out. `review.md` stays in: the ruling named no change, and a quoted phrase is cleared by the next review round.
- **I2.** The real-name, Boundary and reserved-host scans read every file under `worlds/` and `personas/` (`_View.world_and_persona_files`, an rglob), not only grammar paths. `schema` fails each such file outside the grammar: "outside the bundle's path grammar, though a loader reads every file here".
- **I3.** The three denylist scans read each file's whole text with its whitespace collapsed, and, for a `.yaml` file that parses, each parsed string value collapsed, one per line (`_scan_texts`, `_strings`). A pattern is reported once per file. Of the config's values, a `provider` value is left out, so the spare still holds.
  - ASSUMED: the collapsed text replaces the raw text rather than adding to it. Collapsing keeps every non-whitespace character, so it catches everything the raw text did. The only difference is a lookahead across a line break: raw "the verge\nof tears" and "rule\n  out" used to be false positives, and collapsed they are spared. A near-miss pins each.
- **M1.** `url_hosts(text)` is a new public helper. It cuts at `?` or `#`, strips trailing `.,;:!`, then drops the port and lowercases. `reserved_hosts` and `tests/test_real_names.py`'s world-address test both call it. `URL_HOST` is unchanged in text. `tests/test_real_names.py` now imports `url_hosts` in place of `URL_HOST`, which would otherwise be unused.
- **M3.** `_View` is built once per `lint_bundle` call. It caches the grammar index, the file list, each text and each file's scan texts, and every lint reads through it. A grammar path is still read through `Bundle.read_file`, which refuses a link.
  - Measured, warm, mean of 20: `lint_bundle` went from about 226 ms (the review's figure) to 150 ms.
  - The test module: 342 tests in 151 s (was 282 in about 137 s), about 0.44 s per test. `good_bundle` itself is about 240 ms of each.

### Tests (written first)

New fixtures:

- **schema:** positives for `personas/zz.caller.yaml` (p3a), `worlds/mini/corpus/Pier-Cafe-Extra.md` and `worlds/mini/ladders/Extra.yaml`. Near-misses:
  - `notes.txt` at the root;
  - a transcript;
  - a grammar copy `pier-cafe-hours-2.md`.
- **real_name_bundle:** positives for the p6 folded "Bill / Gates", and a line break and a double space in a body (p2). Near-misses:
  - "The bill was paid.\nGates open at nine.";
  - "Bill\nGatesworth";
  - "on the verge\nof tears".
- **reserved_hosts:** a positive for `https://pennetferry.com.` at a sentence end. Near-misses: a reserved URL with `.`, `,`, `?day=1` and `#hours`.
- **boundary_bundle:** a positive for the p6 folded "safety / training". A near-miss for "rule / out" across a fold.
- **jailbreak_bundle:** positives:
  - the p6 folded phrase;
  - a line break and a double space in a body;
  - a request constraint holding a line break (p2).

  Near-misses:
  - `plan.json`'s `lint_results` holding the lint id and the phrase;
  - `ledger.jsonl`, `.attempt.json` and `dryrun.jsonl` holding it.
- `test_a_recorded_jailbreak_hit_never_fails_a_later_validate`: plant, lint, record, fix, lint, record, lint. The first lint finds the body hit, and the two after the fix find nothing.
- `test_a_file_outside_the_grammar_fails_schema_and_is_scanned`: a real name in `zz.caller.yaml`, a Boundary word in it and in `Extra.yaml`, and a public URL in `Pier-Cafe-Extra.md`. Each is caught by its scan, beside the schema failure.

RED, on 6ca2946's lints:

- A first run failed at collection: the fixture's own host check, `_host_free`, refused "See https://pennetferry.example." under 6ca2946's reading. This is M1, shown.
- I then added only a temporary `url_hosts` helper and left the lints as they were: 30 failed, 397 passed.
- Every new positive failed, and so did the I1 test and the four off-grammar scan tests.
- These near-misses failed too:
  - verge;
  - the four reserved-URL near-misses;
  - rule/out;
  - recorded hit, ledger, `.attempt.json` and `dryrun.jsonl`.

GREEN:

- The two modules: 342 passed in `tests/test_bundle_lints.py`.
- Full gate, run once: 10381 passed, 10 skipped, 49 deselected (from 10322; +59); slow 49 passed; ruff format --check, ruff check and both mypy runs clean.

### Near-miss shares after the round

Every near-miss changes the bundle's bytes (re-measured by the scratch script).

| Lint | Near-misses of cases |
| --- | --- |
| schema | 19 of 37 |
| real_name_bundle | 9 of 17 |
| reserved_hosts | 10 of 15 |
| boundary_bundle | 7 of 13 |
| jailbreak_bundle | 10 of 19 |
| others | unchanged |

### Probe misses left out, and why

These are residuals of the shared lists or of R-bare-host. No closed rule of these lints covers them.

- A name fused into a compound host (`reutersnews.example`).
- A zero-width space inside a name: `str.split` does not treat U+200B as whitespace, and stripping it would be a normalization the list owner should decide.
- `unrestricted` and `disallowed`: the list's leading `\b`.
- "The developer modelled the tides" and "The bypass filters were cleaned": false positives of the jailbreak list.
- R-bare-host's pinned residual: a bare host on `.de`, a scheme-relative URL on `.ru`, a file name ending `.info`, and a reserved URL whose path ends `.us`.
- A public URL in `config.yaml`: outside the spec's `reserved_hosts` files.

### Docs

- docs/08: the four scan rows state the new scope, the collapse and the trim.
- Spec "As planned": one Fix round 1 line.
- HANDOFF: item 5 gains the round and the counts.
- docs/00 section H: unchanged, since no record changed.

## Fix round 2

Status: DONE. Commit dff6e26 on 8ec2485 ("fix: Phase 5 Task 4b fix round 2, ..."), author rankinbc1@gmail.com. Not pushed. The regex line (`_PARAGRAPH_BREAK`) and the test's paragraph split were written with the Edit tool; no touched file holds a control byte (checked) and none holds CRLF.

### What changed

- **R1.** `review.md` is out of `jailbreak_bundle`'s scope (`_QUOTING_FILES` in `bundle_lints.py`, beside `_HARNESS_RECORDS`), as `real_name_bundle` already leaves it out. `plan.md` stays in (stage 4 can revise it). The positive that pinned `review.md` becomes two near-misses: a quoted phrase, and the reviewer's own word ("a rung whose natural endpoint is a jailbreak", no phrase). The run-shaped test, `test_a_review_that_quotes_a_phrase_the_planner_removed_passes_jailbreak_bundle`, plants a phrase in a document, writes `review.md` quoting it and naming the class, then runs stage 5 three times (planted, fixed, fixed again): the lint fails the document only while it holds the phrase and never fails `review.md`; a phrase added to `plan.md` afterwards still fails.
  - Docs: the jailbreak row of the spec's section 9 table and section 14's "scans every bundle file" line now say "but `transcripts/` and `review.md` [refined in Task 4b's re-review: R1]"; the "As planned" Q24 bullet is marked and a Fix round 2 bullet added. Preflight Q24's row is marked the same way. docs/08's jailbreak, real-name and schema rows are updated. The ruling says "spec section 10's scope line"; section 10 (stub `turns` and the dry run) has no jailbreak line, so I edited the two places the scope is written (section 9's table, section 14).
- **M-A (paragraph scanning).** `_collapse` splits on a blank line (`\n\s*\n`), collapses each paragraph's whitespace to single spaces and joins the paragraphs with a newline. No pattern holds `\s`, a newline or an anchor, so a pattern reads one paragraph at a time: the two lookahead spares hold across a wrapped line and stop holding across a blank one. Probe p14's seven cases are all fixtures: three already existed (verge/of wrap, "Bill\nGates", the jailbreak line break), two are new positives (`# Source: The Verge`, a blank line, `Of the three outlets...` for real_name_bundle; `The house rule`, a blank line, `Out of hours...` for boundary_bundle), and two are new near-misses (the same two texts in one paragraph; plus `Nobody can rule\nout a fault.`). A phrase split by a blank line is no longer matched (the raw text did not match it either; the whole-text collapse of fix round 1 did).
- **N-2 (invalid UTF-8).** `_View.read_file` stays strict (the loaders' reader). `_View.scan_text` is what every scan, the host scan and `no_values_expectation` read: a grammar path through `read_file`, falling back to the bytes with each bad one replaced. `_load_files` reads `plan.md` and `review.md` strictly too, and turns any `UnicodeDecodeError` into a `schema` fail naming the file and the byte ("not valid UTF-8: byte 0xe9 at offset 806"). Every grammar file is covered, not only the two: a persona, config, expected, world or ladder file with such a byte used to raise out of the scans as well.
- **N-1 (off-grammar files).** The message is "outside the bundle's path grammar, which allows only plan.md, config.yaml, expected.yaml, review.md, worlds/<name>/world.yaml, worlds/<name>/corpus/<stem>.md, worlds/<name>/ladders/<stem>.yaml, worlds/<name>/premises/<stem>.yaml and personas/<stem>.yaml, where <name> and <stem> match [a-z0-9][a-z0-9_-]{0,63}; remove or rename <file>" (the pattern is `bundle.NAME`; the old "though a loader reads every file here" is gone; the message does not start with the doc_id, as the existing review-N3 assertion requires). The off-grammar failures live in `_Files.off_grammar`, apart from `out`, so they no longer make `_schema` return no loaded bundle: the world lints, the persona lines, `anchor_floor` and the set lints report for the grammar files beside the failure. Any other schema failure still silences them (`test_a_schema_failure_silences_the_lints_that_need_a_loaded_model` is unchanged and green). Every off-grammar file under `worlds/` and `personas/` still fails `schema` (the earlier ruling), `.gitkeep` and a `notes.txt` included; only the wording and the lost results changed.

### Tests (written first)

Changes in `tests/test_bundle_lints.py`:

- Positives: real_name_bundle, the Verge across a blank line; boundary_bundle, `rule` across a blank line. The `review.md` jailbreak positive is removed.
- Near-misses: real_name_bundle `Source: The Verge\nOf the three...` (one paragraph); boundary_bundle `Nobody can rule\nout a fault.` and `The house rule\nOut of hours...` (one paragraph); jailbreak_bundle two `review.md` near-misses.
- `_collapsed` (the fixtures' own check that a near-miss text matches no pattern) now reads paragraph by paragraph, as the lint does.
- `test_a_file_outside_the_grammar_hides_none_of_the_world_lints` (5 files: a `notes.txt` in a world, `personas/.gitkeep`, an off-grammar persona, ladder and document): beside a planted `bully_line` fault, the schema fail names only that file, every fail the bundle gives without the file is still given with it, and the message names the file and the grammar. The existing `test_a_file_outside_the_grammar_fails_schema_and_is_scanned` asserts the same message.
- `test_a_file_that_is_no_utf8_fails_schema_naming_it_and_raises_nothing` (8 files: `plan.md`, `review.md`, a persona, `config.yaml`, `expected.yaml`, a document, the world sheet, a ladder): exactly one schema fail, naming the file and `0xe9`; any warn is a `skipped:` one.
- `test_a_review_that_quotes_a_phrase_the_planner_removed_passes_jailbreak_bundle` (above).

RED, on 8ec2485's lints, the whole module (`-m "not slow"`): 22 failed, 346 passed, in 146 s (output kept in `probes-task4b-fixround2-red.txt`):

| Failing on 8ec2485 | Why |
| --- | --- |
| `real_name_bundle-9-positive`, `boundary_bundle-7-positive` | the whole-text collapse spared the lookahead across a blank line |
| `jailbreak_bundle-12-near`, `-13-near` | `review.md` was scanned |
| `a_file_outside_the_grammar_fails_schema_and_is_scanned` x4 | the old message |
| `a_file_outside_the_grammar_hides_none_of_the_world_lints` x5 | the `bully_line` fail was missing beside the schema fail (loaded bundle None) |
| `a_file_that_is_no_utf8_fails_schema_naming_it_and_raises_nothing` x8 | `UnicodeDecodeError` out of `lint_bundle` |
| `a_review_that_quotes_a_phrase_the_planner_removed_passes_jailbreak_bundle` | `review.md` failed on the phrase and on "jailbreak", before and after the fix |

The near-misses that pass on both trees (the one-paragraph Verge and rule/out texts) guard against over-fixing.

First GREEN run of the module: 3 failed, the three off-grammar schema positives, through the existing review-N3 assertion that a message never starts with its doc_id. The message was reworded to open with the rule, not the file; the module then ran 369 tests green under `-W error`.

### The gate, run once on the final tree

```
uv run ruff format --check .        335 files already formatted
uv run ruff check .                 All checks passed!
uv run mypy claude_bully            Success: no issues found in 125 source files
uv run mypy --platform linux claude_bully
                                    Success: no issues found in 125 source files
uv run pytest -q -W error           10407 passed, 10 skipped, 49 deselected in 903.25s (0:15:03)
uv run pytest -q -m slow            49 passed, 10417 deselected in 164.45s (0:02:44)
```

From 10381: +26 non-slow tests, all in `tests/test_bundle_lints.py` (14 new tests, 6 net new cases, 6 new skip-test rows from `CASES_4B`). The module is 369 tests (one slow), about 150 s.

### Near-miss shares after the round (recounted from `CASES` with the re-review's p12 script)

| Lint | Near-misses of cases | Was |
| --- | --- | --- |
| schema | 19 of 37 | 19 of 37 |
| real_name_bundle | 10 of 19 | 9 of 17 |
| reserved_hosts | 10 of 15 | 10 of 15 |
| boundary_bundle | 9 of 16 | 7 of 13 |
| jailbreak_bundle | 12 of 20 | 10 of 19 |
| the others | unchanged | |

Each new near-miss appends to or edits a bundle file, so each changes the bundle's bytes.

### ASSUMED

- ASSUMED: the paragraph break is `\n\s*\n` (a line holding only whitespace of any kind, such as a tab or NBSP, is a blank line). Cost if wrong: a break the markdown reader would not see.
- ASSUMED: invalid UTF-8 is a `schema` fail for every grammar file, not only `plan.md` and `review.md` (the other kinds already failed `schema` through `ValueError`; only the scans raised). Cost if wrong: none seen; the scans never raise.
- ASSUMED: an off-grammar file keeps failing `schema` (the earlier ruling), now with a message that says what the grammar allows and "remove or rename"; the lints that need a loaded model run beside it. A world document that is off-grammar but read by `load_world` joins the loaded world, so its world-lint results appear too (named by its document id, not a path).
- Not done: N-3 (a link under `worlds/` or `personas/`; this host refuses to create one) and N-4 (Task 5's `dry_run=[]` half of the max_calls carry, already in progress.md's updated carry).

### Concerns

- A name or phrase split by a blank line (`Bill`, a blank line, `Gates`) now passes `real_name_bundle`. It is the ruling's consequence, the same as the raw text before round 1, and no fixture pins it either way.
- The ruling named "spec section 10's scope line"; the scope line is in sections 9 and 14, so those were edited.

## Fix round 3

Status: DONE. Commit 5591258 on dff6e26 ("fix: Phase 5 Task 4b fix round 3, ..."), author rankinbc1@gmail.com. Not pushed.

### What changed

- **NEW-1.** `_scan_texts` and `config_display_names` catch `(yaml.YAMLError, ValueError)`: a `.yaml` file holding a value PyYAML refuses with a plain `ValueError` (`2026-13-45`, `2026-02-30`, `9999-12-31T25:61:61Z`) no longer raises out of `lint_bundle`. The scans read the file's text alone, as they do for a YAML syntax error, so a real name beside the bad date is still found. Grep of every YAML load in `bundle_lints.py` (`yaml.safe_load` at three sites; `parse_document`, `load_world` and `run_experiment` are Phase 3 and 4 code reached through `except ValueError` clauses that already hold):
  - `_model` (the schema's loader) already let the `ValueError` reach `_load_files`'s `except ValueError`, so the file got a schema fail with the bare message "month must be in 1..12". It now reads the file first, then catches `(yaml.YAMLError, ValueError)` around `safe_load` only, so the message is "invalid YAML: month must be in 1..12" and a `UnicodeDecodeError` or a link refusal from the read still says what it is. This was not a raise, so it is a wording fix, not a finding.
  - No other load site has the gap.
  - Found while grepping the same principle (a planner file gives a fail, never an exception): `_strings` recursed forever on a YAML anchor that holds itself (`zz: &x [*x]`), a `RecursionError` out of `lint_bundle` for a grammar file, an off-grammar one and a stray `.yaml` (the world sheet, `config.yaml` and `scratch.yaml` probed). `_strings` now skips a container met again inside itself (`open_`, the ids being read). Not covered, and not fixable here: PyYAML's own `RecursionError` on a file nested thousands of levels deep, raised by `safe_load` before any of our code (the schema loader meets it too). Also unchanged: `plan.json` with a bad byte raises from `read_record`, the harness's own record, as the re-review noted.
- **M-1.** Spec section 9 (a paragraph before the `BUNDLE_LINT_IDS` line) and section 14 (the `jailbreak_bundle` bullet) state the residual: a phrase split by a blank line passes the bundle lints, for the real-name, Boundary and jailbreak patterns alike, because each paragraph is scanned on its own; it is the price of keeping the two lookahead true positives; a deliberate split is the planner gaming its own lint, which the reviewer stage reads. Each sentence is marked "[refined in Task 4b's re-review: M-1]". One departure from the ruling's cost-if-wrong line: I did not write that the CI scan of `plans/` is the backstop, because the CI scan reads the raw text and the raw text matches no pattern across a blank line either (the re-review's M-2 also found no such promise in section 12); the spec says that no later scan of the same patterns closes it. Docs only, no code.

### Tests (written first)

In `tests/test_bundle_lints.py`:

- `test_a_yaml_value_the_loader_refuses_is_a_schema_fail_never_an_exception`, p15's seven files: the world sheet (`2026-13-45`), a persona (`2026-02-30`), `config.yaml`, `expected.yaml`, a ladder (`9999-12-31T25:61:61Z`), an off-grammar ladder, a stray `scratch.yaml`. `lint_bundle` raises nothing, and the file has a `schema` fail naming it for the six that `schema` reads (the stray file is read by no model, so it has none).
- `test_the_scans_still_read_the_text_of_a_file_with_a_yaml_value_the_loader_refuses`: a real name beside the impossible date is found, and the persona has its schema fail.
- `test_the_config_spare_names_ignore_a_config_the_loader_refuses`: `config_display_names` of a bad-date config equals that of an empty text.
- `test_a_yaml_value_that_holds_itself_is_no_exception` (world sheet, `config.yaml`, a stray file).

RED, on dff6e26's lints, the new tests only (`-k "yaml_value or config_spare or the_scans_still_read"`): 12 failed, 369 deselected (`probes-task4b-fixround3-red.txt`). The failures are the seven `ValueError` rows, the real-name test (`ValueError`), the spare test (`ValueError`) and the three self-reference rows (`RecursionError`). GREEN: the whole module, 380 passed and 1 deselected (the slow one) under `-W error`, in 169 s.

### The gate, run once on the final tree

```
uv run ruff format --check .        335 files already formatted
uv run ruff check .                 All checks passed!
uv run mypy claude_bully            Success: no issues found in 125 source files
uv run mypy --platform linux claude_bully
                                    Success: no issues found in 125 source files
uv run pytest -q -W error           10419 passed, 10 skipped, 49 deselected in 931.37s (0:15:31)
uv run pytest -q -m slow            49 passed, 10429 deselected in 158.16s (0:02:38)
```

From 10407: +12 tests, all of `tests/test_bundle_lints.py` (now 381, one slow). No control byte and no CR in the two touched code files (checked).

### ASSUMED

- ASSUMED: guarding `_strings` against a self-referencing anchor belongs in this round (the same harm as NEW-1, in the same function chain, and a three-line change). Cost if wrong: one extra changed function and three tests to drop.
- ASSUMED: `_model`'s message gains the "invalid YAML:" prefix for a `ValueError` (it had none). Cost if wrong: a message wording a later test might pin; no test pins the old one.
