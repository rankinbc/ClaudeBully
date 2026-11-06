# Task 7 review: wiring the world generator into runs (e5ce59a..70864b5)

Reviewer scope: the brief (task-7-brief.md), as amended by task-7-carries.md (including the controller's correction of the P13 "re-asks the writer" sentence), and global-constraints.md. I read the diff in full. I did not re-run the suite or any git command. I made five focused checks outside the diff, each for a named risk:

1. Risk: `docs_unlocked` is wiped on resume, so `prime`'s `add_generated` would be undone. Check: `CALL_FIELDS` (runtime.py:214). It is `retry_counts`, `search_log` and `files` only, so the seam ids `add_generated` puts in `docs_unlocked` survive `_replay_calls`.
2. Risk: search statistics are frozen at index build, so documents added later never rank. Check: `CorpusIndex.search` (corpus.py:303-335). BM25 is built per query over the searchable documents, so documents added by `add_documents` are ranked.
3. Risk: `runtime.world` is the authored world, so the planner would date from the sheet. Check: runtime.py:482. `self.world = served = served_world(...)`, so the planner gets the served world.
4. Risk: a duplicate in `_unlocks_at` makes two fires with one reason. Check: the session's unlock loop (env_turn.py:705-717). `_recorded_rungs` skips an already-recorded rung before the append, and `prime` builds `_unlocks_at` from the recorded unlocks, so no rung is listed twice.
5. Risk: the replay test passes vacuously. Check: `SandboxTools` fetch (tools.py:455-461). A retry is counted only for a document the index holds and shows, so a document missing from the replay index counts nothing (see Minor 2).

## Spec Compliance

Spec verdict: PASS. Every file the brief lists is changed as the brief says, or departs from it in a way a carry requires. Every carry is met. The three Task 5 CANNOT VERIFY items are each pinned by a test that would fail under the wrong wiring.

### File by file

| File | Verdict | Notes |
| --- | --- | --- |
| `claude_bully/environments/corpus.py` | PASS | `UnlockState.harvest_degraded`, and `CorpusIndex.add_documents` as briefed (keeps the same document, refuses a different one under a taken id, reindexes). |
| `claude_bully/environments/mcp_server.py` | PASS | `McpState.generated`. `_tools` builds the index, then `add_documents(state.generated)` (mcp_server.py:361), then passes `index=`. The docstring sentence is added. |
| `claude_bully/environments/runtime.py` | PASS | `_generated`, `add_generated`, `generated_documents` and `corpus_view` are as briefed (runtime.py:787-810). `prime(generated=)` calls `add_generated` first. `note_records` skips `generator` unlocks (runtime.py:778). `_replay_calls` serves each document from the turn after its fire (runtime.py:711-722). `before_target_call` passes `generated=`. The docstring paragraph is added. |
| `claude_bully/environments/generator.py` | PASS (Extra, justified) | `RECENT_BULLY_LINES`, `FireResult` and `WorldGenerator` are as briefed. Extra: `FireResult.outcome` and `WorldGenerator.commit` (generator.py:918, 1068). P13 requires the commit to go through `WorldGenerator`, and the brief's three-field `FireResult` could not carry the outcome. |
| `claude_bully/runner/store.py` | PASS | `GENERATION_TYPES`, `COMMITTED_STATUSES`, `_parsed_lines`, `_keep_only`, `drop_uncommitted_generation` and `generation_streams`. `drop_dead_attempts` is rebuilt on the helpers (P31; store.py:78-139). Its behaviour is unchanged: a torn last line is dropped, a damaged middle line raises before any write, and blank lines are skipped. The `_turn_in` extraction shares one predicate between the two droppers. |
| `claude_bully/runner/env_turn.py` | PASS | `GENERATED_CACHE_DIR`, `generator=` and `_unlocks_at` are added. `prime` drops, primes and skips `generator` unlocks before `_recorded_rungs`. `after_target_turn` appends to `_unlocks_at` and calls `_generate` before the hooks. `_generate` makes the commit call after the fire line (env_turn.py:725-759). `_needs_its_world` is updated. `_check_switches` raises on `generator_problems` (env_turn.py:1124). `_world_generator` passes the seed with fallback plus the rep (1331), the served world, and `runtime.world_terms` only (1355). |
| `claude_bully/analysis/progression.py` | PASS | `unlocks_of` filters `PSEUDO_RUNGS`. |
| `tests/fixtures/generator_stub.py` | PASS | The imports are merged, not replaced (carry P32). Task 6's `_plans`/`_writer` moved here as `mini_plans`/`mini_writer` with unchanged bodies, so `_pair()` reuses them. The Task 7 doubles are verbatim. |
| `tests/fixtures/fake_claude.py` | PASS | `_FILL`, `_filled`, the loop preamble and the docstring paragraph are added. |
| `tests/helpers.py` | PASS | `env_experiment(generator=)`. |
| `tests/test_generator_runtime.py` | PASS | The brief's tests are present. `test_generator_unlocks_are_no_ladder_unlocks` is rewritten through behaviour, as P34 allows. Seven tests are added. |
| `tests/test_generator_run.py` | PASS | The brief's tests are present, with stronger asserts (the cache file count, and the writer asked twice on redo). Six tests are added and pin the carries. |
| `tests/test_generator_writer.py` | PASS | It now uses the shared wiring (P32), with no change of behaviour. |
| `tests/test_sanctuary.py` | PASS | P25: `harvest_degraded` is added to `with_its_turn`. |
| `HANDOFF.md`, `docs/00-RECONCILED.md`, `docs/02-ENVIRONMENTS.md` | PASS | Every sync item the brief and the carries list is present: Progress 7, both Phase 3 carries closed, the `world_terms` open item removed, counts 8113/5/5 and 5, the resume prompt naming Task 8, and the trailer line. The 02 "Reproducibility" edits went into "Replay, caching and determinism", which is that section. |
| Commit author and trailer | CANNOT VERIFY | The diff package shows only the commit subject. The report states the author `rankinbc1@gmail.com` and the Fable 5.1 trailer. |
| `test_runner_env.py`, `test_mcp_server.py`, `test_runtime.py`, `test_progression.py`, `test_replay.py` unchanged and passing | PASS (unchanged) / CANNOT VERIFY (passing) | None of them is in the diff. The reported gate (8113 passed, 0 warnings, slow 5) is not re-run. |

### The points the controller asked me to judge

1. **The Task 5 CANNOT VERIFY items.** PASS on all three.
   - `fire_requests` gets only the turn's newly opened `generate` rungs. The session passes `self._unlocks_at.get(turn, [])` (env_turn.py:747), and `fire` filters on `self.rungs[r].generate`. A cumulative list would make a second `rung:the_log` fire at turn 5, since the dedup is per `(turn, reason)`. `test_a_generated_buried_document_is_found_through_its_seam_pointer` asserts exactly one fire, so it would fail. The unit test `test_only_the_turns_newly_opened_generate_rungs_fire` (test_generator_runtime.py:350) pins the filter itself.
   - Seed and plan index. `test_the_generator_seed_and_the_plan_index` (test_generator_run.py:207), for seeds None and 7, checks the date and slug of plans 0, 1 and 2 against `DocPlanner(seed)`. A plan index counted per fire, or over committed fires only, would put the periodic plan at index 0 and fail the test. A seed that ignored `generator.seed` would fail the seed-7 case. The `+ rep` term is exercised at rep 0 only (Minor 5).
   - Served world. `test_the_planner_dates_from_the_served_world` (test_generator_run.py:196) moves the clock to 2042-03-01, which the authored 2041 world cannot satisfy. Check 3 confirms the wiring.
2. **The commit after the fire line (P13).** PASS. `_generate` writes the documents, then the unlocks, then `self._record(result.fire)`, then `generator.commit(result)`, then `add_generated` (env_turn.py:752-759). The pins:
   - The kill test asserts an empty cache after each of the four kills, and that the writer is asked twice on redo.
   - `test_a_fire_whose_line_is_written_is_never_made_again` kills inside `DocWriter.commit`: the writer is asked nothing on resume, and the records are equal to the unbroken run's.
   - The cache-hit test shows a committed fire's replies are hits.
   The controller's corrected reading of the carry is the one pinned.
3. **The cast names only as `world_terms`.** PASS. `_world_generator` passes `runtime.world_terms` and nothing else (env_turn.py:1355). `test_the_harvest_gets_the_cast_names_only` spies the constructor in a real run, and the `h-1-2` question item depends on a cast-name match.
4. **Resume.** PASS.
   - The four kill points resume to equal records, each with one `ResumeRecord(turn=3, dropped=...)`, and the drop counts are right per kill point.
   - `drop_dead_attempts` is rebuilt on `_parsed_lines`/`_keep_only` (P31).
   - `drop_uncommitted_generation` parses both files before rewriting either. It drops the harvest and fire lines of unwritten turns, and every document and `generator` unlock no committed fire lists.
   - A redone turn records nothing twice: `harvest_turn` and `fire` return only what is new, and `_recorded_rungs` and `_unlocks_at` are rebuilt from the records.
5. **P29.** I agree none of the three needs naming in the spec amendment.
   - `McpState.generated` is the concrete field behind the spec's section 8 sentence, "Committed generated documents go into the env state file that the MCP server already reloads". The spec already states the behaviour. The field is a sandbox-internal hand-off file, not a run record that analysis replays, and `docs/00-RECONCILED.md` now names it, which is the right home.
   - `FireResult.outcome` and `WorldGenerator.commit` are the in-process mechanics of P13. The spec states only the order: cache after the fire line.
   - `_unlocks_at` is private and implements the amendment line "A rung fire reads the turn's recorded ladder unlocks".
   The one place the departure should be visible is the plan, not the spec: the plan's interface line and its type-consistency list give `FireResult` three fields. Task 8 does not consume `FireResult` (I grepped the Task 8 and 9 plan text), so nothing downstream breaks. The ledger should record the deviation.

## Strengths

- Resume is correct by construction. The `GeneratorFire` is the commit line, the dropper keys on it, and `WorldGenerator.fire` reads `earlier` (fires before this turn) for the policy but all recorded fires for the plan index and the dedup. A turn resumed after one of its fires is committed therefore plans the rest exactly as an unbroken run did.
- `_unlocks_at` reads the recorded unlocks rather than the ladder's return value. That makes the "harvest call" kill work: the `the_log` unlock is already on disk and skipped by `_recorded_rungs`, yet the redo still fires.
- The tests verify through records: the trigger and generated streams, the turn texts, the cache directory and the writer stub's prompt count. The kill tests use separate runs roots for the clean and killed runs, so a shared cache cannot mask a redo.
- P13 is shown both ways: no cache entry exists without a fire line, and a fire line with no cache entry is never redone.
- DRY: the shared `mini_plans`/`mini_writer`, `_turn_in` shared by both droppers, and `_parsed_lines`/`_keep_only` reused.
- The documentation is accurate and specific: the commit order, the redo turn of after-turn markers, and the cache directory.

## Issues

### Critical

None.

### Important

None.

### Minor

1. **No run-level test of the cap, the writer's provider error or a degraded harvest.**
   - Where: generator.py:1007 (`late`), generator.py:1034 (the over-cap `FireOutcome`), env_turn.py:741-743 (`harvest_degraded.append`).
   - What: `grep` over `test_generator_run.py` and `test_generator_runtime.py` finds no `max_docs`, `cap`, `ProviderError`, `error` mode or `harvest_degraded`. Three paths new in this task are therefore untested here: the session appending a degraded turn and the next fire's plans listing it (`late`), the over-cap branch that records a `rejected`/`cap` fire without calling the writer, and a writer `error` fire in a run. The plan's traceability table (plan line 6944, "10 Error handling table") credits Task 7, beside Tasks 4 and 5, with "cap" and "harvest LLM error, `harvest_degraded`". Tasks 5 and 6 test the pure pieces, but nothing tests their wiring.
   - Why it matters: a broken `late` window or a misplaced `degraded.append` would pass the gate, and the spec's error-handling row would be unverified at the integration level.
   - Fix: add three run tests:
     - `HarvestJudge(crash_at=1, crash=HarvestFallbackError(...))` and turn budget 5: the turn-1 harvest is degraded, and the turn-3 fire's plans have `harvest_degraded == [1]`;
     - `max_docs: 1`: the turn-3 fire is `rejected`/`cap`, the writer is asked nothing, and two plans are recorded;
     - `GeneratorStub(["error"])`: the fire is `error`, no document or cache entry exists, and the items stay unconsumed.
   This is coverage, so it is Minor; the final review should know the plan row is not yet backed.
2. **The replay test does not pin that the replay index gets the generated documents.**
   - Where: test_generator_runtime.py:117-165.
   - What: `retry_counts == {}` holds whether or not `_replay_calls` adds the documents to its fresh index. A document missing from the index is a 404, and a 404 counts no retry (check 5). The implementer's mutation check removed the `docs_unlocked.add` line, which the test does catch. Removing `index.add_documents(...)` at runtime.py:717 would survive.
   - Why it matters: `_replay_calls` is the named resume risk. The index half is near-inert for today's `CALL_FIELDS`, because a seam document is unlocked by name and a buried one has `unlock_rung`, so neither counts retries. The test's docstring still claims more than it proves.
   - Fix: either assert the replayed `fetch` reaches the document (for example, run the replayed index's lookup, or check that a `read_file` replay of the buried path changes a field), or narrow the docstring to "a seam document in the replay index is unlocked by name".
3. **`test_generator_unlocks_are_no_ladder_unlocks` does not fail without the `note_records` skip.**
   - Where: test_generator_runtime.py:179-198; runtime.py:778.
   - What: the report says its RED came from `unlocks_of` only. A `generator` entry in `_unlocks` is filtered by `_rungs` in `_replay_calls` and touches no consult rung, so the state and context equalities hold either way. The test pins `unlocks_of` and behavioural inertness, not the skip itself. P34 accepted this form.
   - Fix (optional): assert `GENERATOR_RUNG not in` the rungs `_replay_calls` applies, through `_takes_family_file` as P34 suggests. Or accept it as a defensive skip and say so in the test docstring.
4. **`fire()` makes every request's writer calls before the session writes any line.**
   - Where: generator.py:1012-1065 and env_turn.py:752-759. Plan-mandated shape.
   - What: when two generate rungs open on one turn and the rep dies inside the second fire's writer call, the first fire's finished replies are neither recorded nor cached, so its writer calls are made again. The records are still equal to an unbroken run's.
   - Why it matters: wasted generator calls on the subscription in Phase 7, and with a nondeterministic model the redone first fire may differ from what the dead attempt saw. Nothing records the lost version, so this is not a records defect.
   - Fix (later): have `fire` yield one `FireResult` at a time, or let the session commit after each, so each fire's lines and cache land before the next fire's writer call.
5. **The `+ rep` seed term is untested.**
   - Where: env_turn.py:1331; test_generator_run.py:207.
   - What: the test runs rep 0 only, so a dropped `+ rep` passes. Two reps sharing a seed would plan the same dates and slugs.
   - Fix: run with `repetitions: 2` and assert that rep 1's plan 0 matches `DocPlanner(seed + 1).date_for(0)`.
6. **The fill patterns are written out twice.**
   - Where: tests/fixtures/fake_claude.py:36 and tests/fixtures/generator_stub.py:268-269. Plan-mandated.
   - What: the `{{last_url}}`/`{{last_path}}` regexes and the fill loop appear in both files. `fake_claude.py` runs as a standalone subprocess script, so it cannot import the fixture module.
   - Fix (optional): a comment in each file naming its twin, so they are changed together.
7. **`add_generated` ignores a different document under a recorded id.**
   - Where: runtime.py:787-797 (brief code).
   - What: `fresh` filters by `doc_id`, so a different document under an id `_generated` already holds is skipped without a word, while `CorpusIndex.add_documents` refuses that case. No current path produces one.
   - Fix (optional): compare against `self._generated[doc.doc_id]` and raise, as the index does.

## Assessment

Task quality: Approved

The wiring meets the brief and every carry. The resume design is sound: the fire line is the commit, `earlier` is separated from all recorded fires, and the recorded unlocks drive the rung fires. The tests show it through records at all four kill points and both P13 cases. The findings are coverage gaps, chiefly the untested cap, writer-error and degraded-harvest paths that the plan's traceability table credits to this task, and none of them makes the task untrustworthy.
