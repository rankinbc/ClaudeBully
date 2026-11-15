# Task 5 report: the dry run

Status: DONE. One commit on 40d87e4 (the SHA and subject are in the reply to the controller).

## What was implemented

- `claude_bully/environments/generator.py`: `plan_from_prompt(prompt)`, which is `plan_of`'s body and docstring, placed beside `writer_prompt`. `tests/fixtures/generator_stub.py` now imports it as `plan_of`.
- `claude_bully/planner/dryrun.py`, this task's half:
  - The constants: `DRYRUN_BULLY_LINE` (A9), `DRYRUN_CLOSING`, and `DRYRUN_SENTENCES` (60 mundane sentences of 4 to 7 words).
  - The walk: `walked_state` (every rung through `Ladder.apply`), `named_by_id`, `searched_document` (R-buried) and `fetched_document`.
  - The scripts: `dry_run_script`, `cell_script` and `top_rung_state`.
  - The generator double: `dryrun_document` and `DryRunGenerator(seed)` (R-dryrun-pure).
  - The run: `load_bundle_experiment`, `dryrun_provider_factory(bundle, exp)` (Q26, D-twin, R-registry), `dry_run_id` and `dry_run`.
- What `dry_run` does:
  - It runs inside `plan_personas`.
  - It removes `dryrun/_cache` before a run whose directory does not exist yet.
  - Before a resume, it drops the lines of a dead attempt from its own ledger (D-K12; see the concerns).
  - It calls `run_experiment` on the doubles against the bundle's worlds, then `analyze_run(judge=False)`.
  - It builds one `DryRunCell` per cell.
  - It removes every older `dryrun-*` directory and `dryrun/_cache`.
  - It rewrites `dryrun.jsonl` whole and leaves `plan.json` to its caller.
- `claude_bully/planner/bundle_lints.py`:
  - The `dry_run` lint. `lint_bundle` runs it only when it is given the cells. It fails on any of these:
    - a dry run with no cell (the `dry_run=[]` half of the budget carry)
    - a cell that `expand_cells` gives but the cells do not hold
    - a cell that is not complete
    - a buried search hit
    - a generated fire's lint failure
    - no laddered cell at its top rung
    - per laddered cell, a script longer than the cell's target turns: "the dry-run script is n target turns; the cell has m turns"
  - `budget`'s `max_calls` clause from Task 4b is unchanged; it was extended in tests, not added again.
  - NEW-2: `_YAML_REFUSED` at the three `safe_load` sites.
  - NEW-3: `_holds_itself`, a cycle refusal in `_model` ("a YAML anchor holds its own alias").
- `claude_bully/environments/world.py`: `YAML_BUILD_ERRORS` and `yaml_error_text`. `_load_yaml` now turns a malformed core tag (a `KeyError`, `AttributeError` or `IndexError` inside `safe_load`) and nesting past the stack (a `RecursionError`) into a `ValueError` that names the file. This is NEW-2's `world.py` site, which `parse_document` and `load_world` read through.
- `tests/fixtures/bundle_fixtures.py`: `config_bundle`, `REPS_1` and `OVERLAY`.
- Docs-sync:
  - docs/08: the Dry run row and its paragraph. They now say `turns` mode, not "scripted"; give the fixed bully line and why; give the run id; and say what a buried search hit is.
  - docs/00 section H: Task 5 changes no record.
  - The spec:
    - M-1 scoped in sections 9 and 14.
    - "As planned": the Task 2 `fnmatchcase` line, and Task 5's lines for D-A9, R-buried, R-dryrun-pure, D-K12, Q26, the per-cell aggregation, the `dry_run` lint, NEW-2 and NEW-3.
  - HANDOFF: Phase 5 item 6.

## Tests

`tests/test_dryrun.py` has 21 test functions (30 tests, 16 slow).

The brief's 16 functions, with two edits (both under ASSUMED):
- The later-fire test counts writer calls without `cached` lines.
- The later-fire test asserts that every clean fire commits.

Five functions of mine:
1. The generator double is a function of the plan's address. A rebuilt double gives the same reply, another address gives another body, and the real `DocWriter` commits the pair.
2. No line a double says or writes holds a premise term, cast name, real name or Boundary phrase of any checked-in world, and no spoken line fires a trigger.
3. A rate limit pauses the dry run and the same call resumes it (target and generator, slow).
4. The stub's `reasoning` key reaches no chat field, no record and no prompt (slow).
5. A planted stray buried hit fails and the shipped overlay passes (slow).

`tests/test_bundle_lints.py` adds these:
- `test_a_dry_run_lint_case`: 15 cases (6 positives, 1 negative, 8 near-misses; Q20). Three of them are real dry runs and are marked slow.
- Its coverage test.
- The empty dry run beside `max_calls`.
- NEW-2: 7 carriers, plus a document's front matter.
- NEW-3: `params` and `intent_meta`, plus a shared anchor that is no cycle.

`tests/test_stub_turns.py` adds the two Task 2 rules: a non-empty `default`, and a `reasoning` value that is no string.

RED evidence:
- Collection failed at import (`ImportError: DRYRUN_BULLY_LINE`). Saved in scratchpad `red_import.txt`.
- With the code in place, before the lint and the fixes, each of these failed for its own reason:
  - The budget-script case failed because there was no `dry_run` lint yet.
  - The leaky-search case failed because no hit was recorded: the script's search step disappeared under the patched `searchable`.
  - The two later-fire K12 cases failed twice over. The estimate was 48 against 47, and `no_duplicate_fact` rejected the second fire.
  - The stray-hit case failed.

The mutation RED runs (scratchpad `red_mutations.txt`) each restored the source after the run, and each restore was verified with `cmp`:

| Mutation | Result |
| --- | --- |
| M1: no dead-line drop | 4 failed: later-fire second and last; rate limit target and generator |
| M2: echoing bully (A9) | the Poisoned Well top-rung test failed |
| M3: `searched_document` through `CorpusIndex.searchable` | the leaky-search test failed |
| M4: link line by title and address | the later-fire test failed on its clean-fire assertion |
| M5: the NEW-2 catches narrowed back to `(YAMLError, ValueError)` | 8 failed |
| M6: no cycle check | 2 failed |
| M7: the Task 2 stub rules removed | 5 failed |

GREEN, focused run: `tests/test_dryrun.py tests/test_bundle_lints.py tests/test_generator_writer.py tests/test_stub_turns.py tests/test_world_lines.py -m "slow or not slow" -W error` gave 605 passed.

Gate (one run each, 0 warnings):
- `ruff format --check`: 336 files formatted
- `ruff check`: clean
- both mypy runs: clean
- `pytest -q -W error`: 10463 passed, 10 skipped, 68 deselected (before: 10419, 10, 49)
- `pytest -q -m slow`: 68 passed (before: 49; the 19 new are 16 in `tests/test_dryrun.py` and 3 in `tests/test_bundle_lints.py`)

Goldens: `git diff --stat -- tests/fixtures/golden` is empty. Only `dryrun_provider_factory` builds the dry-run bully, and no existing test's stub changed.

## Files changed

- claude_bully/environments/generator.py
- claude_bully/environments/world.py
- claude_bully/planner/bundle_lints.py
- claude_bully/planner/dryrun.py
- tests/fixtures/bundle_fixtures.py
- tests/fixtures/generator_stub.py
- tests/test_dryrun.py (new)
- tests/test_bundle_lints.py
- tests/test_stub_turns.py
- docs/00-RECONCILED.md
- docs/08-DIRECTOR.md
- docs/superpowers/specs/2026-11-14-phase-5-director-design.md
- HANDOFF.md

`world.py` and `test_stub_turns.py` are outside the brief's Files list. The NEW-2 carry and the Task 2 carries need them.

## ASSUMED

- ASSUMED: the generator double's link line names each linked document by its title alone. The brief says "by title and address"; the spec says only "one line naming the linked documents".
  - Measured on the overlay: two buried documents from its two fires both link `cpo-ticket-7702`.
  - With title and address, the second document repeated 9 of its 39 word 8-grams, so `no_duplicate_fact` rejected that fire.
  - The later-fire test now pins that every clean fire commits.
- ASSUMED: before a resume, `dry_run` drops from its own `ledger.jsonl` every line of an unfinished rep that no written turn owns.
  - The rule is the runtime's own (`AttemptMarker.written`):
    - a target or responder call is owned by its target turn
    - a bully call is owned by its bully line
    - an after-turn call is owned when `watched_through` reaches its turn
  - Without the drop, a kill after an earlier call of the same attempt had returned counted that call twice. The case: the pair's buried document wrote its ledger line, then the seam document's call died. The estimate was 48 against 47. D-K12's reasoning covers only a kill at a call's start.
  - A rate limit's line is dropped by the same rule.
  - Only the dry run's stub ledger is rewritten; a real run's ledger is never touched.
- ASSUMED: the later-fire test counts writer calls as generator ledger lines whose status is not `cached`.
  - The brief's count included the cache's `cached` lines. The two targets are one stub, so the t1 cells replay the t0 fires from the cache.
  - With the brief's count, the `last` case aimed its kill at line 16 of 8 real calls and never fired.
- ASSUMED: `searched_document` reads the buried rule directly: visible after the walk, and not in `docs_unlocked`. It does not call `CorpusIndex.searchable`.
  - The brief's leaky-search test patches `searchable`. Calling it would also have removed the script's search step, so no hit could ever be recorded.
  - On the shipped corpus both readings give the same answer; the SEARCHED table holds.
- ASSUMED: a buried hit counts only the rungs fired strictly before the call's turn. A rung, triggered or scheduled, fires in `after_target_turn`, after that turn's calls.
- ASSUMED: one `DryRunCell` per cell, aggregated over its reps:
  - A rung counts as fired, the top as reached and a buried document as read only when every rep did it.
  - A hit, a lint failure or a resume counts when any rep had one.
  - The generator's status counts are summed.
  - The estimate is the cell's ledger lines plus 2 pair-judge calls per condition rep.
  - The status is aborted when any rep aborted, complete when every rep is, and otherwise the first status that is not complete.
- ASSUMED: the hit's lint message names the cell and says that a web_search served a buried document that no rung fired before the search names by id. `DryRunCell` holds a flag, not the document id, and the lint reads only the cells. The id stays in the run's tool calls for the reviewer.
- ASSUMED: the read step uses `fetch` for a url and `read_file` for a path. When the cell lacks the matching tool, there is no read step.
- ASSUMED: the script-length clause skips a ladder that `walk_lines` cannot walk (`ladder_walk` already fails it), so `lint_bundle` never raises there.

## Carries

| Carry | Test |
| --- | --- |
| Task 2, stub reasoning | `test_the_stubs_reasoning_key_reaches_no_chat_field_record_or_prompt`. The sentinel is on every entry and on every watched target Turn, using the pattern from tests/test_reasoning_channel.py. Its teeth: the harvest read Turns carrying it, and the bully and generator were asked. |
| Task 2, stub rules, and the fnmatchcase line | `test_a_turns_script_needs_a_non_empty_default`, `test_a_reasoning_value_that_is_no_string_is_refused`, and the spec's "Task 2, a line owed" |
| Task 3 review, R-buried stray hit | `test_a_stray_buried_search_hit_fails_and_the_shipped_overlay_passes`, plus `test_a_layer_opened_buried_document_served_by_search_is_a_hit` |
| Task 4b, budget (extend, not re-add; the dry_run=[] half) | `test_an_empty_dry_run_passes_max_calls_and_fails_the_dry_run_lint`. The existing max_calls test is unchanged and still passes. |
| Task 4b, NEW-3 | `test_a_yaml_anchor_holding_itself_in_an_any_field_fails_schema` (params, intent_meta) and `test_a_shared_yaml_anchor_that_holds_no_cycle_still_loads` |
| Task 4b, NEW-2 | `test_a_yaml_tag_or_nesting_the_loader_cannot_build_is_a_schema_fail_never_an_exception` (p19's four classes across 7 carriers) and `test_a_document_front_matter_tag_the_loader_cannot_build_is_a_schema_fail` |
| Task 4b, M-1 | spec sections 9 and 14, scoped to a markdown body and a YAML literal block |
| Phase 4, resume parity at each kill point | `test_k12_a_dry_run_killed_in_a_call_resumes_to_the_unbroken_cells` (3 cases) and `test_k12_a_generator_killed_in_a_later_fire_resumes_to_the_same_documents` (2 cases) |
| Phase 4, a rate limit pauses and never degrades | `test_a_rate_limit_pauses_the_dry_run_and_the_same_call_resumes_it`, target and generator: it raises `RateLimitExit`, writes no `dryrun.jsonl`, and the resume equals the clean run |
| Phase 4, stub providers only | `test_the_factory_serves_the_four_doubles_and_refuses_a_fifth` (a non-stub provider and a fifth model are refused) |
| Q20 | `test_a_dry_run_lint_case` (8 near-misses of 15) and the coverage test. 4b's `CASES` assertion is unchanged. |
| Q19 | the SEARCHED table (night-gate-log) and the n4 near-miss (`the_log` naming `rota-overtime-sheet` by id) |
| faulthandler, 120 s | every run used the pyproject setting, with no hang |
| regex lines with the Edit tool | no regex was written through a heredoc. There are no control characters in planner/*.py or the new tests. |

## Dry run results on the shipped configs

One rep each; the raw output is in scratchpad `dryrun_results.txt`.

- TVS:
  - All 8 cells are complete and `reached`, with 6 of 6 rungs and no buried search hit.
  - The triggered cells read `cpo-review-4471-r3`. The scheduled cells do not, because `the_truth` opens at exchange 12, after the read.
  - Estimates: 43 for the conditions, 41 for the controls.
  - Every web_search query is the family file's title.
- TVS with the generator (GEN_EDITS):
  - The same climb, with no lint failure.
  - The triggered t0 cells write 2 fires; the t1 cells take 2 from the cache.
- real_vs_fabricated (Poisoned Well):
  - `poisoned_well_real`: 2 of 2 in all 4 of its cells, condition and control.
  - `poisoned_well_fabricated`: 6 of 6 in all 4 cells. The t0 condition writes its fire; the t1 condition caches it.
  - No hit anywhere.
- checksum_alone (Poisoned Well):
  - `poisoned_well_checksum`: 1 of 1 in all its cells.
  - `poisoned_well`: 8 of 8, with its fire written.
  - No hit.
- The good bundle: all 4 cells reached 3 of 3, and the triggered cells wrote their fire.

These match D-A9's trace: 2/2, 6/6, 1/1 and 8/8.

## Concerns

1. D-K12 as written was false for a kill after a call had returned. The fix rewrites the dry run's own ledger at resume. Review should decide whether a ledger that is derived, in the dry run only, is acceptable.
2. A rate-limit resume is not shape-identical to an unbroken run. The pause marker takes a turn index, so later turn indices shift by one. On the good bundle the cells and estimates are still equal.
3. Two departures from the brief's text: the later-fire writer count, and the title-only link line.
4. The 60 sentences need the reviewer's reader-eye pass (spec section 14). The closed parts are tested.
5. `dry_run` raises `ValueError` from the factory for a ladder that `walk_lines` cannot walk. Task 9 should dry-run only after `schema` and `ladder_walk` pass.
