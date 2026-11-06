# Task 7 report: wiring the world generator into runs

Implementer: Fable 5.1 (no subagents). BASE e5ce59a, branch build/v1. Commit: 70864b5 (`70864b541e11e3d05b648bf1c16b5bc8d039f3d6`), authored by rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, not pushed.

## What was built

- `environments/generator.py`: `RECENT_BULLY_LINES = 5`, `FireResult`, `WorldGenerator` (`prime`, `harvest_turn`, `fire`, `commit`), as in the brief, with one added field and one added method (deviation 1).
- `environments/corpus.py`: `UnlockState.harvest_degraded`, `CorpusIndex.add_documents`.
- `environments/runtime.py`: `add_generated`, `generated_documents`, `corpus_view`; `prime(..., generated=)` serves the recorded documents first; `note_records` skips `generator` unlocks; `_replay_calls` adds each generated document to its fresh index before the first written turn after its fire (a seam one into `docs_unlocked`); `before_target_call` writes `McpState.generated`. Module docstring paragraph added.
- `environments/mcp_server.py`: `McpState.generated: list[Document]`; `_tools` builds the index, adds the generated documents, passes `index=`. Docstring sentence added.
- `runner/store.py`: `GENERATION_TYPES`, `COMMITTED_STATUSES`, `_parsed_lines`, `_keep_only`, `drop_uncommitted_generation`, `RunStore.generation_streams`; `drop_dead_attempts` rebuilt on the helpers (P31). Docstring resume paragraph updated.
- `runner/env_turn.py`: `GENERATED_CACHE_DIR`; `EnvironmentSession(generator=)`, `_unlocks_at`; `prime` drops uncommitted generation, primes the runtime and the generator with the generated stream, and builds `_unlocks_at` from the recorded ladder unlocks (skipping `generator`); `after_target_turn` appends to `_unlocks_at` and calls `_generate` before the hook records; `_generate` as in the brief plus the commit call; `_needs_its_world` is true for an enabled generator; `RunEnvironments.generated_cache` and `_world_generator`; `_check_switches` raises on `generator_problems`. Module docstring paragraph added.
- `analysis/progression.py`: `unlocks_of` drops every `PSEUDO_RUNGS` unlock.
- Tests and fixtures: `tests/fixtures/generator_stub.py` (Task 7 doubles appended; imports merged; shared `mini_plans` and `mini_writer`), `tests/fixtures/fake_claude.py` (placeholders), `tests/helpers.py` (`env_experiment(generator=)`), `tests/test_generator_writer.py` (uses the shared wiring), `tests/test_sanctuary.py` (P25), and the new `tests/test_generator_runtime.py` (15 tests) and `tests/test_generator_run.py` (18 tests).

## Deviations from the brief, and why

1. `FireResult` has a fourth field, `outcome: FireOutcome`, and `WorldGenerator` has `commit(result)`, which calls `DocWriter.commit(result.outcome)`. The P13 carry requires `_generate` to commit through `WorldGenerator` after the fire line, and the brief's `FireResult` did not carry the outcome whose `cache_puts` the commit writes. `_generate` calls `generator.commit(result)` right after `self._record(result.fire)` and before `runtime.add_generated`.
2. `tests/fixtures/generator_stub.py`: the brief's import block was merged, not replaced (carry P32). `World`, `DocPlan`, `GeneratedDoc` and `WORLDS_DIR` are kept; `DocPlanner`, `DocWriter`, `FireRequest`, `eligible_items` and `JudgeCache` are added for the shared helpers.
3. `_pair()` reuses the shared wiring (P32). Task 6's `_plans` and `_writer` moved into the fixture as `mini_plans` and `mini_writer`, bodies unchanged (target turns `(1, 3, 5)`, which with `min_age=0` gives the brief's eligible set). `test_generator_writer.py` binds `_plans = mini_plans`, `_writer = mini_writer` and `CID = MINI_CID`, and drops the now-unused `TARGET_TURNS`, `SHEET` and imports. All 34 writer tests are unchanged and pass.
4. `tests/test_generator_runtime.py`:
   - `test_generator_unlocks_are_no_ladder_unlocks` asserts through behaviour (P34) instead of reading `runtime._unlocks`. A runtime primed with two generator unlocks has the same state and the same `begin_turn` context as one primed without them, the buried document stays hidden, and `unlocks_of` returns nothing.
   - `Turn` objects are built with `tests.helpers.turn` (the brief's tests built none; my added ones need `phase` and `timestamp`). Long lines were rewrapped by `ruff format`, and a few long asserts were split into a local and an assert, with no change of meaning. The `GeneratorFire` literal the brief repeats is a local `_fire(...)` helper and the unlock literal is `_unlock(...)`.
5. `tests/test_generator_run.py`: the brief's tests are verbatim apart from formatting and a shared `_view` helper. Asserts were added to three brief tests: `len(_cached(...)) == 2` in the found-through-seam test, `== 1` in the rejected-pair test, and in the kill test an empty cache after the kill and a resumed writer stub asked twice. The rest are new tests (below).
6. `store.py`: `drop_uncommitted_generation` uses a small `_turn_in(record, produced)` helper, shared with `drop_dead_attempts`, in place of the inline `isinstance(turn, int) and turn in produced`. Same behaviour.
7. `env_turn.py` `prime`: the generator-rung branch `continue`s before `_recorded_rungs.add`, as the brief says ("starts with"), so a `generator` unlock is in neither `_recorded_rungs` nor `_unlocks_at`.

Harvest, the watcher and the stub conversation's wording are unchanged.

## Tests added beyond the brief

In `test_generator_runtime.py`:

- `test_a_different_document_under_a_taken_id_is_refused`;
- `test_the_replayed_calls_see_a_seam_document_unlocked_by_name`, the `_replay_calls` path. In a test copy of mini whose the_log also opens the seam layer, a seam generated document fetched on turn 5 counts no yield-on-retry refusal in the replay. Mutation-checked: removing the replay's `docs_unlocked.add` makes it fail with `{'gen-3-2': 1}`;
- `test_a_fire_of_an_unwritten_turn_commits_nothing`;
- `test_only_the_turns_newly_opened_generate_rungs_fire`;
- `test_a_fire_returns_its_lines_in_commit_order`;
- `test_prime_loads_only_committed_documents_and_the_recorded_fires`;
- `test_the_harvest_reads_the_bully_s_newest_lines_only`.

In `test_generator_run.py`:

- `test_the_planner_dates_from_the_served_world`;
- `test_the_generator_seed_and_the_plan_index` (seed None and 7);
- `test_a_generator_the_cell_cannot_run_is_refused_before_the_run`;
- `test_the_harvest_gets_the_cast_names_only`;
- `test_a_fire_whose_line_is_written_is_never_made_again`;
- `test_a_committed_fire_is_a_cache_hit_for_the_same_conversation`.

## Carries

- **Harvest final shape; `world_terms` are the cast names only.** `_world_generator` passes `runtime.world_terms` and nothing else. Pinned by `test_the_harvest_gets_the_cast_names_only`, which spies on `WorldGenerator.__init__` in a real run and asserts that the terms equal the lowercased cast names. The run test's `h-1-2` question item also depends on it, since that item fires only through a cast-name match. The HANDOFF open item is removed.
- **The stub conversation's harvest items.** Checked early, directly with `harvest` and the mini cast names, then in the run. Turn 1 harvests `h-1-1` self_claim and `h-1-2` question despite the middle sentence. Turn 3 harvests `h-3-1` hedge and `h-3-2` fragment, and the_log fires at turn 3. `test_a_generated_buried_document_is_found_through_its_seam_pointer` pins all four items, the fire and the rung timeline. No stub wording change was needed.
- **Task 5 refactor.** `_authors` and `_is_url`/`norm_url` are untouched, with no copies.
- **Task 6, P13.** `_generate` calls `generator.commit(result)` (deviation 1) after `self._record(result.fire)`. Tests:
  - `test_a_rep_killed_mid_generation_resumes_to_the_unbroken_records` (4 kill points). After each kill the generated cache is empty. The resumed rep's writer stub is asked twice, so both documents are asked for again; the same documents are planned and recorded `written`, and the records equal the unbroken run's.
  - `test_a_fire_whose_line_is_written_is_never_made_again`: the rep is killed inside `DocWriter.commit`, after the fire line. The cache is empty. On resume the writer is asked nothing and the fire is not made again; the records equal the unbroken run's, with `ResumeRecord(turn=3, dropped={})`.
  - Cache hits: `test_a_committed_fire_is_a_cache_hit_for_the_same_conversation`. Interpretation: a resumed rep never redoes a committed fire, because its `(turn, reason)` is recorded. So "a committed fire's replies are cache hits on resume" can only be shown for the same conversation run again under the same runs root (another run id). There the writer is asked nothing, the fire is recorded `cached`, and the documents are equal.
  - The carry's sentence "a resumed rep whose fire line was written but whose commit did not run re-asks the writer" cannot hold as written, since that rep never fires again. Both readings are pinned: fire line not written, the writer is asked again (kill test); fire line written, it is not (commit-kill test).
- **Shared fixtures (P32).** Import block merged; `mini_plans`/`mini_writer` shared (deviation 3).
- **P3.** The harvest's `mark` is bound to `runtime.mark_attempt("harvest", turn)` and the writer's to `("generator", turn)`. The "harvest call" kill point resumes with `ResumeRecord(turn=3, dropped={})` from the harvest marker alone.
- **P25.** `"harvest_degraded"` added to `with_its_turn` in `tests/test_sanctuary.py`; the test passes.
- **P31.** `drop_dead_attempts` is rebuilt on `_parsed_lines` and `_keep_only`; `tests/test_store.py` passes unchanged.
- **P34.** Behavioural assertions (deviation 4).
- **P29.** The spec is not edited. Task 7 shapes the amendment does not name: `McpState.generated`, `FireResult.outcome` with `WorldGenerator.commit`, and the `_unlocks_at` map. The first is how the spec's serving on both backends reaches the MCP server. The other two are internal plumbing for P13 and for the amendment's "a rung fire reads the turn's recorded ladder unlocks". Reported as a minor concern, not a departure.
- **Environment.** `uv` was on PATH. Scratch files are only in the scratchpad's `impl-task7` folder.

## The Task 5 reviewer's three CANNOT VERIFY items

1. `fire_requests` receives only the turn's newly opened rungs with `generate: true`. Pinned by `test_only_the_turns_newly_opened_generate_rungs_fire` (a unit test: first_crumb asks for nothing, the_log fires once, and a recorded fire is not made again). The run test's single fire at turn 3, while first_crumb opens at turn 1, also pins it.
2. Seed and plan index. Pinned by `test_the_generator_seed_and_the_plan_index[None]` and `[7]`. Each recorded plan's date and slug equal `DocPlanner(seed).date_for(i)` and `slug_for(i, day)`, where the seed is `generator.seed`, else the experiment seed 0, and `i` is the number of plans recorded before it: 0 and 1 for the rejected pair at turn 3, 2 for the periodic fire at turn 9. The `+ rep` term is exercised at rep 0 only.
3. The planner is built on the served world. Pinned by `test_the_planner_dates_from_the_served_world`: with the clock's world date at 2042-03-01, every document is dated within the 30 days before it, which the authored 2041-09-14 world could not give. The brief's drifting-clock test also holds.

## RED evidence

`uv run pytest tests/test_generator_runtime.py tests/test_generator_run.py -q` before any production change:

```
E   ImportError: cannot import name 'RECENT_BULLY_LINES' from 'claude_bully.environments.generator'
E   ImportError: cannot import name 'WorldGenerator' from 'claude_bully.environments.generator'
ERROR tests/test_generator_runtime.py
ERROR tests/test_generator_run.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
2 errors in 0.99s
```

Later RED during implementation:

- before `unlocks_of` changed, `test_generator_unlocks_are_no_ladder_unlocks` failed with `assert [RungUnlock(...)] == []`;
- before the P25 edit, `test_every_state_field_is_rebuilt_on_resume_or_saved_with_its_turn` failed, as the preflight predicted;
- the replay test's mutation check is described above.

## Gate

Run after the docs sync, on the committed tree:

```
== ruff format --check
248 files already formatted
== ruff check
All checks passed!
== mypy
Success: no issues found in 102 source files
== pytest -q -W error
8113 passed, 5 skipped, 5 deselected in 525.43s (0:08:45)
== pytest -q -m slow
5 passed, 8118 deselected in 95.32s (0:01:35)
```

All five pass with 0 warnings. BASE was 8080 passed, 5 skipped, 5 deselected; slow 5. The 33 new tests account for the difference.

## Docs sync

- `docs/00-RECONCILED.md`:
  - section A, the `UnlockState` row: `harvest_degraded`, and generated documents served under the visibility rule;
  - section B, the `RungUnlock` row: the `generator` pseudo-rung, one unlock per committed document, written after the documents and before the fire, and skipped by `note_records` and `unlocks_of`;
  - section B, the `GeneratedDoc` row: written first of a fire's lines, served from the next turn on both backends (`McpState.generated`), dropped on resume when uncommitted;
  - section B, the `ResumeRecord` row: the drops are counted under `rep{k}.triggers.jsonl` and `rep{k}.generated.jsonl`, and a `harvest` or `generator` marker redoes its own turn;
  - section H: the triggers stream holds `GeneratorFire` beside `HarvestItem`; the commit order; what a resume keeps; `UnlockState.harvest_degraded`;
  - section I, the Phase 3 row: Task 7's wiring on both backends, the MCP state, resume, and the cache directory.
- `docs/02-ENVIRONMENTS.md`:
  - "World generator" gains "In a run (as built, Phase 3 Task 7)": evaluated after the watcher and the ladder; the harvest terms; rung fires for generate rungs only; the served-world planner; the seed and plan index; the commit order; the cache at `runs/_cache/generated/`; serving on both backends; `harvest_degraded`; the refusal;
  - it also gains "Resume (as built, Phase 3 Task 7)";
  - the harvest paragraph now says Task 7 wired it;
  - "Replay, caching and determinism" gains a Task 7 bullet: the cache directory, the world snapshot and the replay lines.
- `HANDOFF.md`:
  - "Last updated" now reads Task 7 complete, Task 8 next;
  - the commit-trailer line names the model per commit (Opus 5.5 through Task 6, Fable 5.1 from Task 7);
  - the test counts are 8113 passed, 5 skipped and 5 deselected, and 5 slow;
  - Progress gains item 7, and the stale "Task 7 will" wording in items 4 and 6 is now past tense;
  - Next steps start at Task 8;
  - the two Phase 3 carries ("Generator unlocks must be recorded as RungUnlocks", "The GeneratedDoc stream needs a turn index") are marked closed;
  - the `world_terms` open item is removed;
  - the resume prompt names Task 8.

## Concerns

- P29: `McpState.generated`, `FireResult.outcome` with `WorldGenerator.commit`, and `_unlocks_at` are not named in the spec's amendment. They are internal shapes (see Carries).
- The carry's "fire line written but commit did not run re-asks the writer" contradicts itself as worded; both readings are pinned (see P13 above).
- The `_replay_calls` generated-document path has no observable effect under mini's own ladder, because no rung opens the seam layer. Its test therefore uses a test copy of mini whose the_log also opens the seam layer.
