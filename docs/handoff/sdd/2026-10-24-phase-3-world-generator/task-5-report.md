# Task 5 report: fire policy, planner and redaction, the records, schema v3

Status: DONE. Commit `aa49c52` on `build/v1` (authored by rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, not pushed). Base was 9128cba.

## What I built

Pure code, no model call, no run touched.

- `claude_bully/environments/generator.py` (this task's part, from the brief verbatim): `MAX_OFFERED`, `MAX_SHORTLIST`, `DATE_OFFSET_DAYS`, `COMMITTED`, `AUTHOR_EXCLUDED_ROLES`, `PERIODIC`, `MATERIAL_KINDS`, `doc_id_for`, `rung_reason`, `FireRequest`, `CorpusView` (`with_documents`, `seam_open`), `item_age`, `eligible_items`, `consumed_items`, `committed_docs`, `fire_requests`, `DocPlanner` (`date_for`, `slug_for`, `address_for`, `author_for`, `shortlist`, `links_for`, `plan`), `to_document`, `generator_problems`.
- `claude_bully/environments/redact.py`: `REDACTION_MARK`, `redact_span`, `redact`.
- `claude_bully/records_env.py`: `Redaction`, `LintFailure`, `_OneAddress`, `DocPlan` (with `address` and `quote`), `FireStatus`, `Rejection`, `GeneratorFire` (added to `TriggerStreamRecord`), the new `GeneratedDoc`. Module now imports `datetime as dt`, `model_validator` and `Self`.
- `claude_bully/enums.py`: `SCHEMA_VERSION = 3` (docstring notes v3). `claude_bully/runner/store.py` docstring: "no real run was recorded before schema version 3" (plus `GeneratorFire` in the triggers-stream line).
- `claude_bully/environments/config.py`: `GENERATOR_RUNG`, `PSEUDO_RUNGS`, `GeneratorConfig` (`reflexive`, `min_item_age`, `max_docs`, `seed`), `LadderConfig` refuses `generator`.
- `claude_bully/environments/world.py`: `FIRST_BUILD_KINDS`, `SLUG`, `WorldGeneratorSheet`, `WorldSheet.generator`.
- `claude_bully/config.py`: `generator_role` and `Experiment._generator_is_not_a_target`.
- `claude_bully/analysis/replay.py`: the `GENERATOR` line (with ` (<rejection>)`, ` docs=[...]`, one `lint <id>: <message>` line per failure), the reworked `GENERATED <doc_id> <kind> <layer> uses=<ids or ->` line, `GeneratorFire` in `_KIND_ORDER` before `GeneratedDoc`, docstring updated.
- World sheets: the two `generator:` blocks, verbatim, in `tests/fixtures/worlds/mini/world.yaml` and `data/worlds/overlay/world.yaml`.
- Tests: `tests/test_redact.py`, `tests/test_generator_plan.py`, `tests/fixtures/generator_stub.py` (P32: `MINI`, `MINI_ITEMS`, `mini_view`), and edits to `test_store.py`, `test_records.py`, `test_records_env.py`, `test_replay.py`, `test_env_config.py`, `test_config.py`, `test_runner_idle.py`.

## Deviations from the brief

No change to the brief's design or to any of its code. Every difference is in tests, docs or comments:

1. P32: `ITEMS` and `_view()` live in `tests/fixtures/generator_stub.py` as `MINI_ITEMS` and `mini_view()`; `tests/test_generator_plan.py` imports them (and `MINI`) instead of defining copies. The test file's now-unused imports (`CorpusIndex`, `UnlockState`, `load_world`, `HarvestItem`) were dropped. The fixture module takes `WORLDS_DIR` from `tests.helpers`.
2. P33(c): see the next section.
3. P23: `test_records_env_imports_only_enums_and_pydantic` gets `"datetime"` in `allowed`; the `GeneratedDoc` builder in `test_store.py::test_generated_docs_append_and_read` has the new required fields (I also gave it `unlock_rung="the_log"` and a `path`).
4. Extra tests beyond the brief, to cover code the brief's tests leave unpinned (the brief's tests are all present and verbatim apart from the P32 and P33 edits):
   - `test_generator_plan.py`: `test_the_seam_is_open_when_a_seam_document_other_than_the_search_log_is_visible` and `test_committed_documents_reach_the_view_a_seam_one_searchable_and_a_buried_one_not` (`CorpusView.seam_open` and `with_documents` had no direct test).
   - `test_records_env.py`: `DocPlan`, `GeneratorFire`, `Redaction` and `LintFailure` in the round-trip list; `GeneratorFire` in `ALL_STREAM` (so the union test is now "ten stream types"); the four new models in the extra-forbidden test; three tests for `DocPlan.address`/`quote`, the one-address rule on `GeneratedDoc` and `GeneratorFire` defaults.
   - `test_replay.py`: a second test pinning `GENERATOR rung:the_log written docs=[gen-1-1, gen-1-2]`.
   - `test_env_config.py`: new defaults, bounds checks, round trip of the new fields, and `generator` as a reserved rung name beside `sanctuary`.
   - `test_config.py`: `generator_role` precedence and the refusal of a generator that is a target (message pinned).
   - `test_store.py`: `test_loaders_reject_schema_version_2` (as the brief asks; it also pins "reads schema version 3 only").
5. `tests/test_runner_idle.py` docstring: "(SCHEMA_VERSION stays 2)" became "(no schema bump for them)".
6. Formatting: `ruff format` re-wrapped a few lines of the brief's test code. No semantic change.
7. Docs: `docs/00-RECONCILED.md` line 7 (the intro sentence that called section H "the schema version 2 proposal, which needs the owner's approval before Phase 1") now reads "Section H lists the schema changes: version 2 (Phases 1 and 2) and version 3 (Phase 3)." The brief did not name this line, but leaving it would contradict the new section H heading.

## The P33(c) choice

Neither literal branch of the ruling fits at this layer, so I took a third that keeps the assertion meaningful, and I am reporting it plainly.

- `drift_per_turn` only feeds `ClockConfig.date_at` (the tool date). It never changes `world_date`, and `world_at(world, clock)` re-dates only to `clock.world_date`. So no drift moves the served date at this layer, and a drift-only test is vacuous (the brief's version compared `start` with a `world_date` that the drift never touches).
- I did not drop the test. I kept `test_a_drifting_clock_does_not_move_the_start` and rebuilt it: the clock re-dates the world four weeks on (`world_date = START + 28 days`) and also drifts (`P30D`); the world is served with `world_at`. The test asserts that the drifted tool date differs from `world_date` (the drift does move something), that `DocPlanner(served, ...).start == clock.world_date`, and that `start` is neither the authored sheet's date nor the drifted date.
- It now fails if the planner reads the authored sheet's date, or any `date_at` value, instead of the served world's `sheet.clock.world_date`. It still cannot test the per-turn drift of a live run; Task 7's run-level drift test remains the real pin (HANDOFF says so).

## RED evidence

Run before any production code existed (tests written first):

```
uv run pytest tests/test_generator_plan.py tests/test_redact.py tests/test_store.py tests/test_records.py tests/test_replay.py -q
E   ImportError: cannot import name 'generator_role' from 'claude_bully.config'      (test_generator_plan.py)
E   ModuleNotFoundError: No module named 'claude_bully.environments.redact'          (test_redact.py)
E   ImportError: cannot import name 'DocPlan' from 'claude_bully.records_env'        (test_replay.py)
ERROR tests/test_generator_plan.py / tests/test_redact.py / tests/test_replay.py
3 errors in 0.52s
```

(The brief expected `ModuleNotFoundError` for `environments.generator`; the first failing import in the file was `generator_role`, which fails first. Same cause.) Tests that import cleanly failed on behavior:

```
uv run pytest tests/test_store.py tests/test_records.py tests/test_runner_idle.py -q -x
FAILED tests/test_store.py::test_generated_docs_append_and_read
  pydantic_core.ValidationError ... used_items / reflexive / unlock_rung: Extra inputs are not permitted
1 failed, 9 passed
```

and `tests/test_records_env.py`, `tests/test_env_config.py`, `tests/test_config.py` failed collection (`ImportError: cannot import name 'generator_role'`). One self-inflicted failure on the way (a `\n` in a heredoc that became a real newline in `test_store.py`, a `SyntaxError`) was fixed before the RED run that counts.

GREEN, the brief's step 4 set (with `-W error`): `647 passed in 21.83s` on first transcription of the brief's code.

## Gate (final state, one commit)

Run in order, output tails from `scratchpad/impl-task5/gate.log`:

```
### uv run ruff format --check .      244 files already formatted                      exit 0
### uv run ruff check .               All checks passed!                              exit 0
### uv run mypy claude_bully          Success: no issues found in 102 source files    exit 0
### uv run pytest -q -W error         8043 passed, 5 skipped, 5 deselected in 539.61s (0:08:59)   exit 0
### uv run pytest -q -m slow          5 passed, 8048 deselected in 131.90s (0:02:11)  exit 0
```

Fast suite: BASE 7996 passed, now 8043 (+47 tests). Skipped and deselected unchanged (5 and 5). Slow suite 5 passed, as at BASE. 0 warnings. An earlier full fast run before the last two `CorpusView` tests and the docs edits gave `8041 passed, 5 skipped, 5 deselected in 882.76s`; the gate above is the one that counts.

## Docs-sync edits

`docs/00-RECONCILED.md`:
- Section A, `EnvironmentConfig` row: generator block lists `enabled, model, min_turns_between_fires, reflexive, min_item_age, max_docs, seed`, and the role rule (`Experiment.generator`, else the bully's role, `generator.model` overriding, never a target).
- Section A, `WorldSheet` row: `generator: WorldGeneratorSheet | None` with `url_patterns` and `allowed_kinds` and their rules.
- Section A, `LadderConfig` row: `generator` reserved beside `sanctuary` (`GENERATOR_RUNG`, `PSEUDO_RUNGS`).
- Section B: the `GeneratedDoc` row has the new fields and `unlock_rung`; new rows `DocPlan`, `GeneratorFire`, `LintFailure`, `Redaction`.
- Section H is "Schema version 3": the v2 to v3 changes, v2 files refused with the existing message, the v2 list kept below it; the triggers-stream list gains `GeneratorFire`. Intro line 7 adjusted (deviation 7).

`HANDOFF.md`: "Last updated" line (Task 5 complete, one commit on top of 9128cba, Task 6 next); fast-suite count 8043 passed (about 15 minutes), slow 5; Progress gains item "5. Fire policy, planner and redaction ..." (file, record, config and replay summary, the drift-test note); Next steps start at Task 6. The "Generator unlocks must be recorded as RungUnlocks" and "GeneratedDoc stream needs a turn index" carries were left in place until Task 7. The spec's "As planned" section was not edited (P29).

## Concerns and notes

- P29: no Task 5 shape found that the spec's amendment does not already cover (`GeneratorFire.plans`, `rejection`, `error`, `GeneratedDoc.unlock_rung`, `GENERATOR_RUNG`, `WorldSheet.generator`, the authors and address rules are all in it).
- HANDOFF's sha reference is "on top of 9128cba" because the commit cannot name its own sha; the controller may want to replace it with `aa49c52` when pushing.
- The fast suite takes 9 to 15 minutes on this machine, so a gate run is long.
- Not run: nothing was skipped from the gate. No emoji in any Markdown. All files LF.

## Fix round 1 (commit 2f17c02, on aa49c52)

One commit, authored by rankinbc1@gmail.com with the trailer, not pushed. The commit was amended once before this report, to correct the drift test's name in `HANDOFF.md` (docs only, so the gate was not rerun; the committed code and tests are what the gate ran).

### What changed

Important 1 (the two duplicated rules in `claude_bully/environments/generator.py`):
- (a) One `_authors(world)` helper holds the authoring rule. `DocPlanner.__init__` and `generator_problems` both call it (`self.authors = _authors(world)`, `if not _authors(world)`).
- (b) `claude_bully/environments/corpus.py`: `_norm_url` is now the public `norm_url` (with a docstring saying the generator reads it); its two callers in the index were renamed with it, nothing else referenced it. `generator._norm_address` now returns `norm_url(address)` for a url and `_norm_path(address)` otherwise. The review's extra suggestion was also taken: one `_is_url` helper replaces the two `startswith(("http://", "https://"))` tests.
- New tests pin both rules:
  - `test_the_planner_and_the_corpus_index_agree_on_a_urls_key`: for three spellings of one url (bare, trailing slash, padded), `norm_url` gives one key, a `CorpusIndex` holding an anchor at that url finds it under every spelling, and the planner, given a view that holds the anchor, will not plan that address (it suffixes `-2`) and the planned address collides with nothing in the index.
  - `test_the_planner_and_generator_problems_agree_on_who_may_author`: a cast of only `Place:` roles makes `generator_problems` name the author problem and `DocPlanner` raise; one authoring member left makes both accept, and `authors` is that member.
- Mutation checks (run by hand, not committed): a `norm_url` that forgets the trailing slash fails the url test; an `_authors` that stops excluding roles fails the author test.

Minors:
- m1: the P33(c) test is `test_the_start_is_the_served_worlds_date`; its docstring now says what it pins and that drift is only a distractor (Task 7's run-level test is the drift pin). `HANDOFF.md` carries the new name.
- m3: `generated_doc(**overrides)` is in `tests/fixtures/generator_stub.py` (a valid buried `GeneratedDoc`; pass `url=...` and `path=None` for a seam one). The four hand-built builders (`test_generator_plan.py`, `test_records_env.py`, `test_replay.py`, `test_store.py`) use it and keep their own overrides. `test_generator_plan.py` dropped its local `_generated` and its now-unused `GeneratedDoc` import.
- m5: the `fire_requests` docstring says `opened` holds the turn's newly opened rungs with `generate: true`, in ladder order, and that the caller filters (every name given fires).
- `HANDOFF.md`: expected fast count 8045 (was 8043; two new tests).

Not done (not asked, left as the review leaves them): Minor 2 (duplicate default and reserved-name assertions across `test_env_config.py` and `test_generator_plan.py`), Minor 4 (`GeneratorFire` cross-field validator, optional), Minor 6 (replay lint-message folding and separators), Minor 7 (v2 stream read alone gets a pydantic error; ledger note).

### Commands and outputs

Covering tests (the coordinator's command, glob resolved to the one corpus test file):

```
uv run pytest tests/test_generator_plan.py tests/test_redact.py tests/test_records_env.py tests/test_replay.py tests/test_store.py tests/test_env_config.py tests/test_config.py tests/test_corpus*.py -q -W error
309 passed in 3.11s
```

(A wider run that also included `test_runtime.py`, `test_mcp_server.py` and `test_tools.py`, the other readers of the corpus index, gave `535 passed in 37.17s`.)

Full gate on the code that was committed (`scratchpad/impl-task5/gate2.log`):

```
### uv run ruff format --check .      244 files already formatted                      exit 0
### uv run ruff check .               All checks passed!                              exit 0
### uv run mypy claude_bully          Success: no issues found in 102 source files    exit 0
### uv run pytest -q -W error         8045 passed, 5 skipped, 5 deselected in 549.73s (0:09:09)   exit 0
### uv run pytest -q -m slow          5 passed, 8050 deselected in 143.26s (0:02:23)  exit 0
```

0 warnings. Fast suite: 8043 before this round, 8045 now (+2 tests); skipped, deselected and slow counts unchanged.
