# Task 7b report: stage 2, the Director's author stage

One commit on 3a1ef89; the SHA is in the final reply. The probes and their outputs are in `probes-task7b/` in this folder.

## What was implemented

`claude_bully/planner/director.py`:

- `MANIFEST_SCHEMA` and `FILE_SCHEMA`: closed JSON Schemas (`additionalProperties: false`). Every field of a manifest entry is required; `layer` may be null.
- `author_order(manifest)`: the worlds come in the order the manifest first names them. Per world: sheet, documents in manifest order, ladders, premise sheets. Then personas, `config.yaml` and `expected.yaml`.
- `parse_manifest` and `parse_content`: the pure parses.
- `MANIFEST_TASK`, `file_task` and `repair_task`: the task texts. Every message goes through `planner_message`.
- `CallSpec.parse` (new, optional): the pure half of `check`. `Director._call` uses it to rebuild a committed call's parsed reply on a resume.
- `_open_stage(stage, adopt=True)`: records `inputs` and adopts the owner's edits (`_adopt_edits`) in the one write that opens the stage.
- `Director.author` and its helpers:
  - `_scan_plan`
  - `_shipped` and `_copy_worlds`
  - `_manifest_spec`, `_check_manifest`, `_entry_failures`, `_world_failures` and `_budget_failures`
  - `_file_spec`, `_check_file`, `_arrival`, `_document_arrival`, `_config_arrival` and `_world_documents`
  - `_drop`
  - `_close`, `_close_failures`, `_entry` and `_repairs_made`
  - `_calls_made` and `_all_calls`
- `REVIEW_CALLS = 3`.

`claude_bully/planner/bundle_lints.py`:

- `model_from_text`: the `schema` lint's YAML-to-model loader, factored out of `_model` and made public.
- `dry_run_refusals`: the former `_refusals`, made public.
- `plan_scans(bundle, display_names)`: the N-B scans of `plan.md`.

`claude_bully/planner/bundle.py`: `commit_order(record)`, factored out of `materialize`.

`tests/test_director_primitive.py`: the "not built yet" test now runs through `author` and expects `review` to be refused. It is now marked slow.

## Stage 2's write order

1. `plan.json`: the author `StageRecord` with `inputs`, and `PlanRecord.edited`, in one write.
2. The `plan.md` scans. They write nothing. A hit raises `DirectorError`, and `_fail` then writes `plan.json`.
3. When `world: reuse` and `base_world` is set:
   - each base-world file, written LF;
   - then `plan.json` with `base_worlds`, `base_files` and `base_premise_terms`, in one write.
4. The manifest call (index 0) through `ask`, in this order:
   - `.attempt.json`;
   - the ledger line;
   - the transcript;
   - `plan.json`, holding the call and `record.manifest` (R-commit);
   - no files;
   - the cache put.
5. The copy of each shipped world the manifest names that `base_worlds` lacks, with the same writes as step 3.
6. The say line: `the manifest implies <n> calls`.
7. Each entry in `author_order` gets a `file:<path>` call. Its writes are those of step 4, plus the file, written between the commit and the cache put.
8. After each world's last file, the world close. The close itself writes nothing. When it finds a failure, a `repair:<path>` call follows, with the same writes as step 7, and the close runs again.
9. `plan.json`: the stage `committed`, status `authored`.

## Kill-point sweep over the write boundaries

The probe is `probes-task7b/sweep_kills.py`, 7a's pattern carried to stage 2. These writes count as events:

- every `write_atomic`, the cache puts included;
- each ledger line;
- `clear_attempt`;
- `remove_file`;
- the transcript move.

For each k the probe kills the run after event k and reruns it until it returns. It then compares the result with an unbroken run on:

- the hashed files;
- `comparable(record)`;
- `resumed`;
- the ledger's (id, status) lines;
- the cache keys;
- every transcript's bytes, `failed/` included;
- the status.

Two differences are allowed: `resumed` naming the dead calls, and a cache missing one key per kill. The double sweep kills at k1 and again at each of k1+1 to k1+4, inside the resume's own writes.

| Scenario | Events | Single kills | Mismatches | Double kills | Mismatches |
| --- | --- | --- | --- | --- | --- |
| clean | 104 | 104 | 0 | 407 | 0 |
| no_base (copy after the manifest) | 104 | 104 | 0 | - | - |
| retry (manifest off_contract once) | 105 | 105 | 0 | - | - |
| repair (close_fail on REPAIRED) | 110 | 110 | 0 | 431 | 0 |
| drop (lint_fail:twice on DOC3) | 103 | 103 | 0 | - | - |
| provider_error on DOC1, then continue | 112 | 112 | 0 | 439 | 0 |
| rate_limit on DOC1, then continue | 107 | 107 | 0 | - | - |
| Total | | 745 | 0 | 1,277 | 0 |

The first launch (16 processes) filled the disk, because it kept every killed bundle until it exited. Every mismatch it reported was `OSError: [Errno 28] No space left on device`, and it found none before that point (`probes-task7b/run1-disk-full/`). The probe now removes each kill root after reading it. The numbers above are the second launch's.

## Tests, with RED and GREEN

RED: with the implementation stashed, `uv run pytest tests/test_director_author.py -q -m "slow or not slow"` stopped at collection with `ImportError: cannot import name 'FILE_SCHEMA' from 'claude_bully.planner.director'`. The brief expected this failure, since the names did not exist yet.

GREEN: `tests/test_director_author.py` holds 54 tests, all passing, 32 of them slow. One author stage takes 2.2 to 2.5 s, so several tests the brief left unmarked are marked slow, under the global constraint that a test over two seconds is slow. Otherwise the brief's tests are as written, ruff-formatted, with `KILLS` typed `dict[str, dict[str, Any]]`.

Tests beyond the brief:

- the two schemas;
- the pure parses;
- `test_a_resumed_calls_parsed_reply_and_provider_failed_equal_an_unbroken_runs`, clean and with provider_error, at an exact budget of 18;
- 13 manifest-clause cases, each refusal beside its near-miss;
- a shipped world's name under `world: fresh`;
- the budget count;
- the floor after a dropped document;
- the `plan.md` scans: a Boundary word and the owner's name, read at run time and never written;
- a close that still fails, and the `MAX_REPAIR_CALLS` bound;
- the config's arrival through the dry run's refusals, leaving nothing beside the bundle (Q39);
- a copy killed midway, and a kill after a patched base file.

RED after the code: `probes-task7b/mutations.py` breaks one piece of the code and runs the test that covers it. All 13 mutations make their test fail:

1. the resume calls `check` instead of `parse`;
2. no `plan.md` scan;
3. no layer clause;
4. no shipped-name clause;
5. the budget leaves out the manifest call;
6. no floor check after a drop;
7. no repair bound;
8. no dry-run refusals at arrival;
9. the copy keyed on nothing;
10. `base_worlds` committed before the copy's files;
11. no replay at the close;
12. no edit adoption;
13. `links_resolve` kept at arrival.

The first version of the copy test still passed under mutations 9 and 10. I strengthened it with a kill after a patched base file, and both now fail it.

Gate:

- `ruff format --check`: clean.
- `ruff check`: clean.
- `mypy claude_bully`: clean.
- `mypy --platform linux claude_bully`: clean. One run hit a mypy INTERNAL ERROR that was gone on rerun.
- `pytest -q -W error`: 10626 passed, 11 skipped, 102 deselected. That is 21 more than before: 22 new fast tests, less the 7a test now marked slow.
- `pytest -q -m slow`: 102 passed (from 69: 32 new tests and the moved 7a test).

## Files changed

- `claude_bully/planner/director.py`
- `claude_bully/planner/bundle_lints.py`
- `claude_bully/planner/bundle.py`
- `tests/test_director_author.py` (new)
- `tests/test_director_primitive.py`
- `docs/08-DIRECTOR.md`: "Process", stage 2 (A2)
- `docs/00-RECONCILED.md`: section H
- `docs/superpowers/specs/2026-11-14-phase-5-director-design.md`: "As planned", Task 7b
- `HANDOFF.md`: Phase 5 bullet 9

## ASSUMED

- ASSUMED: the budget counts the calls made before the manifest, the manifest call itself, one call per entry and `REVIEW_CALLS = 3` against `max_director_calls`. For the good bundle, 1 + 1 + 13 + 3 = 18 passes a limit of 18. Repairs are not counted; `_check_ceiling` still refuses any call past the limit.
- ASSUMED: the close repairs one file at a time. The first failing file not yet repaired gets its repair, then the close runs again. The stage fails when only repaired files fail, or when the plan has made `MAX_REPAIR_CALLS` repairs. Each file still gets at most one repair. A batch of repairs decided from one close could not be rebuilt after a kill inside the batch, because the bundle by then holds the later repairs.
- ASSUMED: the replay rule. Before the last committed call the close is not run: a committed `repair:` of the world is replayed, and any other committed call means the close had passed.
- ASSUMED: under `world: reuse`, every shipped world the manifest names is copied, not only `base_world`. Under `world: fresh` nothing is copied, and a shipped world's name is refused (the plan's D-copy).
- ASSUMED: a fresh world's manifest must list its `world.yaml`. This clause goes beyond the brief's list; without it, every document of that world fails its arrival check.
- ASSUMED: a hit in the `plan.md` scans fails the stage with the lint results as its `error`. They are not added to `record.lint_results`, which is stage 5's. The scan spares the request's target display names and the `RoleConfig` default display name, since `config.yaml` does not exist yet. It runs every time the stage is entered.
- ASSUMED: the say line's n is `len(manifest) + REVIEW_CALLS`.
- ASSUMED: a dropped document's `ManifestEntry` stays in `record.manifest`. `manifest_complete` already excuses an `error` call, and removing the entry would add a second record field to the file call's commit.
- ASSUMED: a close failure maps to a file as follows:
  - a `load_world` message: the bundle path it opens with, else the first `document '<id>'` it names, else the world sheet;
  - a ladder failure: that ladder's file;
  - a `lint_world` result: the file whose document id it names.

  The second rule reads `World.validate_links`' own message shapes.
- ASSUMED: every failure message the planner is shown has the bundle root removed, so a cache key does not depend on where the plans root is.

## Carries against their tests

| Carry | Where | Test |
| --- | --- | --- |
| 7a re-review: a pure parse split from the check | `CallSpec.parse`, `parse_manifest`, `parse_content`, `_call` | `test_a_resumed_calls_parsed_reply_and_provider_failed_equal_an_unbroken_runs` (no `_check_manifest` call on the resume; mutation 1 makes it fail) |
| Freeze the manifest's call budget as of the call | `_manifest_spec(self._calls_made())`, built once and read only by the check | the same test, at an exact budget of 18; `test_the_budget_counts_the_calls_made_the_manifest_its_files_and_the_reviews` |
| Replay from the committed call list | `_call` by index; the replay in `_close` | the sweep (745 single and 1,277 double kills); K7b; mutation 11 |
| Pin a resumed `parsed` and `provider_failed` to an unbroken run's | | the same test, clean and with provider_error |
| A state-dependent check never sees other state | the manifest, file and config checks run only inside `ask` | the same test |
| Task 6 re-review N-B: scan `plan.md` before any stage-2 call shows it | `plan_scans`, `_scan_plan` | `test_plan_md_with_a_denylist_hit_fails_stage_2_before_any_call_shows_it` (Boundary and owner; no manifest call; the owner's name not in `plan.json`) |
| Task 4a review N5: the planner's `repair:` calls | built in `_close` and `_file_spec(kind="repair")` | `test_the_world_close_asks_one_repair_and_closes`; `test_a_close_that_still_fails_after_its_repair_fails_the_stage`; K7a, K7b |
| Every message through Task 6's builders | `_planner_message` only | every author test (the doubles read the `call:` line) |
| 7a's primitive as built (`ledger_lines`, `provider_failed`, one dead attempt per marker, a resumed error fails again) | `ask` unchanged; `_call` gains only `parse` | the provider_error test; the sweep's provider_error scenario, ledger compared |
| Re-use 7a's kill sweep over stage 2's write boundaries | `probes-task7b/sweep_kills.py` | the sweep table above |
| A rate limit pauses and never degrades | `ask` (7a) | `test_a_rate_limited_file_call_pauses_and_resumes_with_no_dead_attempt`; the sweep's rate_limit scenario |
| Stub providers only; the pyproject `faulthandler_timeout` | the doubles only; pyproject unchanged | every test |
| Shell writes | regex lines written with the Edit tool; no write redirected to a relative path | |
| Preflight Q6, Q9 | `_copy_worlds`: `base_files`, `base_premise_terms` and `base_worlds` (`world_hash`) in one write | `test_a_clean_author_stage_writes_the_good_bundle`; `test_a_copy_killed_midway_is_removed_and_made_again` |
| Q18, Q37 | `DOC1`, `DOC3` and `REPAIRED` from `author_order(GOOD_MANIFEST)` | the drop test: the stage commits with `pier-cafe-hours` dropped |
| Q22 | the config's arrival check inside `plan_personas(bundle_personas(bundle))` | `test_config_yaml_arrives_through_the_dry_runs_refusals_and_leaves_nothing_beside_the_bundle` |
| Q34, Q35 | `ask`, `CallSpec`, `Answer.provider_failed`, `run_plan` | throughout |
| Q38 | a `Ladder` under `triggered` only at the close | stated in "As planned" |
| Q39 | `dry_run_refusals` uses a temporary runs root | `test_config_yaml_arrives_through_the_dry_runs_refusals_and_leaves_nothing_beside_the_bundle` |
| Q40 | `MAX_REPAIR_CALLS` counted per plan over every stage and round (`_repairs_made`) | the `MAX_REPAIR_CALLS` bound test |

## Concerns

- **A missing ladder passes the config's arrival check.** `run --dry-run` does not refuse an environment whose ladder the world lacks under `triggered` gating, so the arrival check passes it too; stage 5's `schema` lint catches it. I found this while writing the config test, which now uses a schedule refusal instead. The arrival check could also run `schema`'s `_environments` check, if this should be caught in stage 2.
- **A close that still fails is a dead end.** After its repairs it fails the stage, and `plan continue` fails it again the same way: no `error` call is moved out, and re-materializing overwrites an owner's edit to an open stage's file. The spec states this outcome, but leaves the owner no way out short of a new plan.
- **`inputs` can go stale.** `inputs` and `edited` are recorded once, when the stage first opens. If the owner fixes `plan.md` after a scan failure and continues, the fixed text is scanned and shown, but `inputs` keeps the old sha.
- **Document layers are not cross-checked.** A document's front-matter `layer` is not checked against its manifest entry's `layer`, so the manifest's floor and filler-share checks rely on the planner's labels. Stage 5's `anchor_floor` counts documents, not layers. A closed check would be simple to add.
- **`REVIEW_CALLS = 3` follows the brief.** A corpus over `REVIEW_CHUNK_DOCS` documents makes more review calls (Task 8).
- **Transcripts are large.** Each author stage writes about 3 to 4 MB of transcripts: every planner message is about 200k characters, recorded in full.

## Fix round 1

One commit on 32d9acd. It follows the controller's ruling in `progress.md` and the review's `task-7b-review.md`.

### The changes

`claude_bully/planner/director.py`:

- **I1.** `run()` calls `_clear_hard_kill()` on every pass, before the stage is read and whether or not the stage has a record. It does three things:
  - `remove_leftovers(bundle)` removes every `write_atomic` temp in the bundle. This closes the kill inside the write that opens the author stage (the review's kill 10) and 7a's K1, the kill inside `Director.new`'s first write.
  - `_drop_torn_ledger_tail()` handles the ledger (M1, below).
  - `remove_leftovers_of(cache.directory, keys)` handles the cache (below).
- **M1 (re-graded Important).** `_drop_torn_ledger_tail` reads the plan ledger with `runner/store.parsed_lines`. That is the runtime's torn-tail helper, renamed from `_parsed_lines` and made public. No second helper was written. The rule: a last line that has no newline after it and does not parse is torn. The ledger is then rewritten without it through `write_atomic`, and the next pass removes that write's own temp. A line that does not parse anywhere else raises the helper's `ValueError` ("ledger.jsonl: line N is not valid JSON ... it is not a torn last line"), before anything is written. That includes a cut record closed off by a newline. This closes the review's kills 22 and 93.
- **The cache-litter cases.** The cache is shared by every plan, so the sweep there is keyed. `bundle.remove_leftovers_of(folder, targets)` removes only the temp of each `<cache_key>.json` that a committed call of this plan names. A temp beside any other key may be another plan's put in flight, so it is left alone. `_LEFTOVER` now captures the target name (edited with the Edit tool). This closes the review's kills 25 and 31.
- **M2.** When an open author record is entered again, `_open_stage(adopt=True)` runs `_readopt`. That happens on a resume after a kill or a pause, and on a continue after a failure. `_readopt` re-records two things:
  - `inputs`: each of the stage's input paths as it is now. A path the resume removed is left out.
  - `edited`: holds an input path exactly when it differs from its committing call's sha, or from `base_files`. That sha comes from `_owned(besides=stage)`, which is factored out of `_adopt_edits`.

  Entries of `edited` that are not inputs of this stage stay. The record is written once, and only when something changed. So a `plan.md` put back after a failed scan leaves `edited`, and `inputs` holds the sha the next call reads. An edit made during a pause joins `edited`.
- **M3.** `_document_arrival` now takes the manifest entry. It fails a document whose front-matter `layer` is not the entry's, with the message "`<path>`: its front matter's layer is X, but its manifest entry says Y". An entry made for a reused world's file has no layer and is not compared.
- **M4.** `_config_arrival` runs `bundle_lints.environment_refusals` after `expand_cells`. That function is Task 4a's `_environments` clause run alone over the bundle's worlds, and it applies under every gating. The clause is reused, not copied. `dry_run_refusals` then checks only the conditions whose environment passed, so a missing ladder is reported once under either gating.
- **M5.** `REVIEW_CALLS = 3` is gone, replaced by `review_calls(paths)` with `REVIEW_CHUNK_DOCS = 25` and `REVIEW_GROUPS`. The new count:
  - one `corpus` call per 25 documents, rounded up;
  - one `lines` call (world sheets, ladders, personas and premise sheets);
  - one `plan` call (`plan.md`, `config.yaml` and `expected.yaml`);
  - no call for a group with no file.

  `_review_calls(entries)` applies it to the bundle the manifest makes: `plan.md`, `base_files`, each shipped world the manifest names that is still to be copied (`_world_files`, now shared with `_copy_worlds`), and the manifest's paths. The budget clause and the say line both use it. The good bundle still counts 3, so the existing budget test still holds at 18.

Other files:

- `claude_bully/planner/bundle.py`: `_LEFTOVER` gains a named group, and `remove_leftovers_of` is new.
- `claude_bully/planner/bundle_lints.py`: `environment_refusals` is new.
- `claude_bully/runner/store.py`: `_parsed_lines` is renamed to `parsed_lines`. Behavior is unchanged.
- `tests/test_director_author.py`: 18 new test cases (9 fast, 9 slow).
- Docs: the spec's "As planned" for Task 7b (the budget clause, the arrival checks, the say line, and two new bullets on the hard-kill resume and on M2), `docs/08-DIRECTOR.md` stage 2, `docs/00-RECONCILED.md` section H (no record change), and HANDOFF Phase 5 bullet 9.

### Tests

Each test is pinned to a review item:

- `test_a_kill_inside_the_write_that_opens_a_stage_leaves_no_temp_file[None, plan, author]` (I1, and 7a's K1). The test makes a real hard kill inside the `plan.json` write, using a `write_atomic` double that leaves the half-written temp. After the resume: no `*.tmp` remains, and the hashed files and `comparable` equal an unbroken run's.
- `test_a_torn_last_ledger_line_is_dropped_and_the_resume_goes_on[manifest, file:config.yaml]` (M1, kills 22 and 93). The test tears the manifest's ok line and a timeout's line. After the resume: the plan is authored, `resumed` names the dead call, and the files, record and ledger (id, status) equal an unbroken run's.
- `test_damage_in_the_middle_of_the_plan_ledger_still_raises[not a record, a cut record closed off]`. The resume raises `ValueError` naming line 1, and `plan.json` is unchanged.
- `test_a_kill_inside_a_cache_put_leaves_no_temp_file[manifest, file:worlds/mini/world.yaml]` (kills 25 and 31). The put's temp is gone after the resume. A planted temp beside a key no call of this plan names is kept.
- `test_inputs_and_edited_are_re_recorded_after_a_plan_md_fix` (M2 case A) and `..._after_an_edit_made_during_a_pause` (M2 case B). Case B also asserts that the next call's message holds the edit.
- `test_a_documents_front_matter_layer_must_be_its_manifest_entrys` (M3), with a near-miss.
- `test_config_yaml_naming_a_ladder_its_world_lacks_fails_arrival_under_every_gating[triggered, scheduled]` (M4). There is exactly one message, and the good config passes.
- `test_the_budget_counts_the_review_calls_a_chunked_corpus_makes[25-3, 26-4, 50-4, 51-5]` (M5). Each case passes at the exact budget and is refused one call under it.

### RED evidence

The tests ran on 32d9acd with the code unchanged. The full output is in `probes-task7b-fixround1-red.txt`. Result: 17 failed, 1 passed. The one that passed is the `[25-3]` near-miss, which is the same count under the old constant. Each failure is the defect named:

- the `.plan.json.<8>.tmp` left behind (3);
- `ValidationError ... LedgerLine` raised out of `run()` (2);
- `DID NOT RAISE ValueError` for mid-file damage (2);
- the cache put's temp left behind (2);
- `edited` wrong on the final record (2);
- the layer mismatch not reported (1);
- the triggered ladder passing, and the scheduled one worded as a dry-run refusal (2);
- no budget refusal, so `not enough values to unpack` (3).

### The hard-kill sweep

The probe is `probes-task7b-fixround1/hard_kill_sweep.py`, built from the review's. It kills inside every write the plan makes, from `Director.new`'s first `plan.json` to the author commit, across stage 1 and stage 2. There are two kinds of kill:

- inside `write_atomic`: the temp is half written, never renamed and never removed;
- inside `Ledger.write`: half the line is written and no newline.

After each kill, the scenario's commands run again until they return: `plan new` while no `plan.json` exists, then `plan continue`. The result is compared with an unbroken run on:

- the hashed files;
- `comparable(record)`;
- `resumed`;
- the ledger's (id, status) lines, with a torn line or a missing newline flagged;
- the cache keys;
- every transcript, `failed/` included;
- the status;
- every `*.tmp` under the plans root, the bundle and the cache both.

Two differences are allowed: `resumed` with one more dead call, and the cache missing one key. In a scenario whose double raises once, a kill between the raise and its commit redoes the call, and the redone call succeeds. That result is compared with the clean run of the same request instead. Each kill root was deleted as soon as it was read.

| Scenario | Writes = kills | Equal | Equal to clean (a dead raising call redone) | Mismatched |
| --- | --- | --- | --- | --- |
| clean | 104 | 104 | 0 | 0 |
| no_base | 104 | 104 | 0 | 0 |
| retry (manifest off_contract once) | 105 | 105 | 0 | 0 |
| repair (close_fail) | 110 | 110 | 0 | 0 |
| drop (lint_fail:twice) | 103 | 103 | 0 | 0 |
| config_retry | 105 | 105 | 0 | 0 |
| provider_error, then continue | 110 | 107 | 3 (k33 ledger error, k34 transcript, k35 commit) | 0 |
| rate_limit, then continue | 106 | 105 | 1 (k33 ledger rate_limit) | 0 |
| timeout_config, then continue | 110 | 107 | 3 (k93 ledger timeout, k94 transcript, k95 commit) | 0 |
| still_fails, then continue | 94 | 94 | 0 | 0 |
| Total | 1,051 | 1,044 | 7 | 0 |

No resume raised, and no `*.tmp` was left anywhere. The probe's outputs are `hard_<scenario>.out` beside it, 30 KB in all. The review's three resume failures (kills 10, 22 and 93) and its two cache-litter cases (kills 25 and 31) are now equal, or equal to clean.

### Commands and output

Every command ran in Git Bash with `/c/Users/Brian.Rankin/.local/bin` on PATH:

- `uv run ruff format --check .`: 346 files already formatted.
- `uv run ruff check .`: All checks passed.
- `uv run mypy claude_bully`: Success, no issues found in 127 source files.
- `uv run mypy --platform linux claude_bully`: Success, no issues found in 127 source files.
- `uv run pytest -q -W error`: 10635 passed, 11 skipped, 111 deselected in 958.83 s. That is 9 fast tests more than 10626.
- `uv run pytest -q -m slow`: 111 passed in 468.28 s. That is 9 slow tests more than 102.
- Covering runs, with `timeout 300` and `-W error`:
  - the 18 new cases: 18 passed;
  - `tests/test_director_author.py` and `tests/test_director_primitive.py` not slow: 66 passed;
  - the same two files, slow: 42 passed.

### Disk

Free space on C: was 2.87 GB at the start. It was 2.71 GB before the sweep, between 2.67 and 2.75 GB during it, and 2.68 GB after it. It never fell under 1 GB.

### Concerns

- **ASSUMED: the torn-tail rule is `runner/store.parsed_lines`'.** Its rule: the last line, with no newline, that does not parse is torn. It does not also require `mcp_server.torn_line` to recognize the cut. A last line of garbage with no newline is therefore dropped as torn rather than raised. That matches how the run store treats its own streams.
- **ASSUMED: damage in the middle of the ledger raises a `ValueError` out of `run()`.** It does not fail the stage. Nothing is written first.
- **M2 makes the record say what the next call reads.** In case B, the calls committed before the pause saw the earlier `plan.md`. Their transcripts hold that text, but `inputs` no longer does. The ruling chose this, over refusing an edit to `plan.md` made while the stage is open.
- **An earlier gap, not changed here.** A file the owner adds before stage 2 first opens stays in the bundle through an unbroken stage 2, yet a resume's `rematerialize_open_stage` removes it as unowned. The two can therefore differ when the owner adds a file by hand. No sweep covers it, since the sweep makes no owner edits.
- **M5 is still a lower bound.** Repairs, revise calls and confirm calls are not counted (stated in "As planned"). Task 8's `review_groups` should use `REVIEW_CHUNK_DOCS` and `REVIEW_GROUPS` from `director.py` and agree with `review_calls`.
- **Only the keys of this plan's committed calls are cleaned in the cache.** That covers every put: a put follows a fresh commit, and an `error` call, the only kind that is archived, is never put. A temp left by another plan's killed put stays until that plan resumes.

## Fix round 2

One commit on 91f1413. It follows `task-7b-rereview-round1.md` and the ruling at the tail of `progress.md`.

### The changes

- **M5-new (re-graded Important).** `Director._review_calls` now counts only what a review reads in full: `plan.md` and the manifest's entries. Before, every unchanged base file of a reused world counted, so the budget refused plans that fit.
  - `planner/context.py` gains `unchanged_base_files(base_files, manifest)`: the base copy's files that no manifest entry names. That is the rule `ReviewGroup.index` names, and its docstring now points to it.
  - `_review_calls` takes the bundle the manifest makes and subtracts those files, so the rule lives in one place. Task 8's `review_groups` should build `index` from it.
  - A patched base file is a manifest entry, so it is still reviewed.
  - A shipped world still to be copied adds only unchanged files, so `_review_calls` no longer lists its files.
- **The spec's `inputs`.** Section 4 now reads: `inputs` is as of the stage's latest entry, and each call's transcript and `cache_key` pin what that call saw. Both the section 4 line and the M2 "As planned" bullet carry "[refined in Task 7b's re-review]". A fix-round-2 bullet is added, and the round-1 budget text is corrected.
- **The ledger append (re-review N-A).** `_drop_torn_ledger_tail` also rewrites a complete last line that has no trailing newline, adding the newline and keeping its bytes. The next `Ledger.write` therefore cannot glue a second record onto it.
- **Newline splitting (re-review N-B).** `_ledger_raw` now reads the bytes and splits on `\n` only, as `parsed_lines` does. Before, it used `splitlines`, which also splits on U+2028, U+2029 and U+0085. Each line keeps its bytes, the `\r` of a text-mode line included.
- HANDOFF Phase 5 bullet 9 gains the fix round 2 counts.

### Tests

These are in `tests/test_director_author.py`, all fast:

- `test_the_budget_counts_no_review_call_for_an_unchanged_base_file`. The shipped overlay (more than `REVIEW_CHUNK_DOCS` corpus files) is reused with 2 new documents. Expected: `_review_calls` gives 2, the manifest passes at `max_director_calls` 8, and at 7 it is refused with "and 2 review calls make 8".
- `test_a_complete_last_ledger_line_with_no_newline_gets_its_newline`. With the ledger's final newline stripped, `_clear_hard_kill` leaves the record's bytes plus `\n`.
- `test_the_plan_ledger_splits_on_newlines_only`. A ledger line whose error holds U+2028, U+2029 and U+0085 raw must count as 1 in `_ledger_lines`, and `_drop_dead_lines` must validate it whole and keep it.

### RED evidence

The tests ran on 91f1413 with the code unchanged. The output is in `probes-task7b-fixround2-red.txt`. Result: 3 failed.

- The budget test: `assert 4 == 2`.
- The newline test: the bytes were left with no `\n`.
- The splitting test: `assert 4 == 1`, because `splitlines` cut the one line into 4 pieces.

### Commands and output

All commands ran in Git Bash, with `/c/Users/Brian.Rankin/.local/bin` on PATH.

- Covering runs (`timeout 300`, `-W error`):
  - `test_director_author.py`, `test_director_primitive.py` and `test_director_context.py`, not slow: 146 passed.
  - The slow kill, ledger and resume tests of the first two files: 24 passed.
- `uv run ruff format --check .`: 346 files already formatted.
- `uv run ruff check .`: All checks passed.
- `uv run mypy claude_bully` and `uv run mypy --platform linux claude_bully`: no issues in 127 source files.
- `uv run pytest -q -W error`: 10638 passed, 11 skipped, 111 deselected, 962.53 s. That is 3 more than 10635.
- `uv run pytest -q -m slow`: 111 passed, 501.11 s.

No probe bundles were kept. The only probe output is the RED text file.

### Disk

Free space on C: was about 2.2 GB before this round and 2.32 GB after.

### Concerns

- **ASSUMED: the rule's one home is `unchanged_base_files` in `context.py`.** No code computed `ReviewGroup.index` yet; it is Task 8's to build. "Reusing the rule" therefore means defining it once, beside `ReviewGroup`. Task 8 should build `index` from it and pin that `review_calls` over the manifest equals `len(review_groups(...))`, the carry the re-review recommends.
- **Kept ledger lines keep their bytes.** A text-mode line keeps its `\r`, and a line given its newline ends `\n` rather than `\r\n`. Readers strip whitespace, so both read the same.
- **The carries to Task 9 are not done here.** The CLI must catch the `ValueError` a damaged ledger line raises and print the line, and spec section 13 needs its row. Both are left to Task 9, as ruled.
