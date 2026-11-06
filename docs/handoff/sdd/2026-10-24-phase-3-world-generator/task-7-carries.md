# Task 7 carries (rulings and notes the brief cannot know)

## From Tasks 4 to 6 (the code as built differs from the plan text)

- **Harvest (Task 4, final state).** The heuristic path scores whole sentences against closed templates.
  - The question template `Who is|was <Name>?` fires only when the name, case-folded, equals one of `HarvestContext.world_terms`. With no world terms, no heuristic question fires.
  - An item is also dropped when the next sentence holds a report frame.
  - Pass `runtime.world_terms` (the cast names, lowercased; runtime.py:527) as the generator's `world_terms`, and pass nothing else. Any other term would also make the question template fire.
  - Turn 1 of the stub conversation has a middle sentence ("The crossing runs every forty minutes from first light.") that harvest's pinned test text does not have. Check early that turn 1 still harvests `h-1-1` and `h-1-2` in the run, and that turn 3 still harvests `h-3-1` and `h-3-2`. If one does not, change only that stub line's wording, the same way the brief already allows for the anomaly line. Never change harvest.
- **Task 5 refactor.** `generator.py` has `_authors(world)` and uses the corpus's public `norm_url` (corpus.py:190) through `_is_url`. Do not reintroduce copies.
- **Task 6, P13 (binding).** `DocWriter.write_fire` returns the pending cache puts on `FireOutcome.cache_puts` and writes nothing.
  - `_generate` must call `DocWriter.commit(outcome)` through `WorldGenerator`, after `self._record(result.fire)` has put the `GeneratorFire` line on disk.
  - Without that call nothing is ever cached.
  - Add a test proving that a resumed rep whose fire line was written but whose commit did not run re-asks the writer and plans the same documents. Also prove that a committed fire's replies are cache hits on resume.
- **Shared fixtures (P32).** `tests/fixtures/generator_stub.py` already holds `MINI`, `MINI_ITEMS`, `mini_view`, `generated_doc(**overrides)` and Task 6's writer stub. The brief says to replace its import block: merge it instead, keeping every import that the existing contents need. Task 7's `_pair()` must reuse Task 6's `_plans`/`_write` wiring, or a shared helper in that module, rather than repeat it.

## Preflight rulings

- **P3.** Bind harvest's `mark` hook to `runtime.mark_attempt("harvest", turn)`, and bind the generator's to its own role, as the brief says.
- **P25.** Add `"harvest_degraded"` to `with_its_turn` in `tests/test_sanctuary.py` (about line 1602). That file is part of this task.
- **P31.** Rebuild `drop_dead_attempts` on the `_parsed_lines` and `_keep_only` helpers rather than duplicating them. Behaviour is unchanged, and test_store pins it.
- **P34.** For `_unlocks`, assert through behaviour: after `note_records`, `_replay_calls` and `progression.unlocks_of` ignore the pseudo-rung unlock. Reading `_request_docs` is accepted, or test it through `_takes_family_file`.
- **P29.** The spec's "As planned" amendment (written in Task 1) covers this task's departures: `drop_uncommitted_generation`, `attempt.json` and pseudo-rung routing. Do not edit the spec's amendment section. If your docs sync finds a Task 7 shape the amendment does not cover, report it as a concern.

## The Task 5 reviewer's CANNOT VERIFY items (this task must satisfy them; the reviewer checks)

1. `fire_requests` receives only the turn's newly opened rungs with `generate: true`.
2. `DocPlanner` is seeded with `GeneratorConfig.seed`, falling back to the experiment seed. The plan index passed is the number of plans recorded before.
3. The planner is built on the served world (`world_at`), which `DocPlanner.start` relies on.

Pin each with a test, or name the existing test that pins it, in your report.

## Environment, docs, commit

- **Environment.**
  - If `uv` is not on PATH in Git Bash, run `export PATH="/c/Users/Brian.Rankin/AppData/Roaming/Python/Python313/Scripts:$PATH"`, and skip any `export PATH=/c/Users/badmin/...` line in the plan.
  - Put scratch files in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\b3f956596010799d\7d309c2e-1430-4cb8-9c70-de3f61a002fe\scratchpad\impl-task7\`. Read no other folder there.
- **Docs sync.**
  - Make the edits the brief names.
  - In `HANDOFF.md`, add "Phase 3 Task 7" to Progress and update the test counts to your gate's numbers.
  - Make the HANDOFF resume prompt name Task 8.
  - Remove the open item "Task 7 must pass cast names only as world_terms" once your code does so and a test pins it.
- **Gate counts at BASE.** The fast suite is about 8073 passed, 5 skipped and 5 deselected; the slow suite is 5 passed.
- **Commit.** Make one commit, authored by rankinbc1@gmail.com (check the repo-local `user.email`). End the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
- **Task 6 final state.** `unwrap_body` never joins inside a double-quoted run and refuses the join when either line is a header field (any case); `verbatim_in_seam` ignores whitespace differences. The gate at BASE e5ce59a: 8080 passed, 5 skipped, 5 deselected; slow 5.
- **Commit trailer (changed).** End the commit message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` (this replaces the Opus trailer named above). In HANDOFF.md:23, say that commit messages end with a `Co-Authored-By: Claude <model> <noreply@anthropic.com>` trailer naming the model that made the commit (Opus 5.5 through Task 6, Fable 5.1 from Task 7).
