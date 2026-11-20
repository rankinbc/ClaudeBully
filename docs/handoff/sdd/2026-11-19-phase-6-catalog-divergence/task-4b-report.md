# Task 4b report: the writable home and the resume of files

Commit: 2eda75b `feat: Phase 6 Task 4b, write_scope home with its limits, rewind_files, and the private path in the idle and authority readers` (base 52d8937). Status: DONE_WITH_CONCERNS (concerns at the end; none blocks).

## What was implemented

- `environments/limits.py`: `MAX_FILE_BYTES = 20_000`, `MAX_TARGET_FILES = 20`, `MAX_PATH_CHARS = 200`, and the two lines `FILE_TOO_LARGE_TEXT` (`Error: file too large (limit 20000 bytes)`) and `TOO_MANY_FILES_TEXT` (`Error: too many files (limit 20)`).
- `environments/config.py`: `WriteScope`, `EnvironmentConfig.write_scope: Literal["private_file", "home"] = "private_file"`; under `home` `_tools_and_authority_agree` adds `write_file` to `tools`, so a dump validates to itself and an older dump reads `private_file`.
- `environments/tools.py`: `home_path(path)` (D-home), `CallWrite` / `call_write(call)` (what a recorded call wrote: a 200 `write_file` only, the path normalised; the write-side twin of `call_read`, per the carries' "goes through the same place"), and `_write_file` as the brief's body (private path under both scopes; under `home` any `home_path` that is not `index.by_path(norm)` with no state, else the same `403 Permission denied: <path>`; then the byte limit, then the file limit; the private file is bound by both, D-file-limit).
- `environments/runtime.py`: `rewind_files(turns)` replaces `rewind_private_file` (body as the brief, reading writes through `call_write`); both call sites (`runner/runner.py: _call_target`, `runner/env_turn.py: _complete`) call it.
- `runner/runner.py: _idle_info`: `private_file_written` is true only for a 200 write to `private_path(config)` (via `call_write`), false when the cell has none.
- `metrics/events/_common.py`: `EnvContext.private_paths: frozenset[str] | None = None`, `is_private_write(call)` (via `call_write`); `idle._private_writes` and `authority._acts`' `notes_line` branch ask it (`_Run` carries the context); `detect_events(..., private_paths=None)`.
- `analysis/load.py` (pre-flight Q21): `private_paths_of(loaded, key)` and `env_context(loaded, key) -> EnvContext`; `load_run` builds the `LoadedRun` first, then reads every conversation's events from `env_context(loaded, key)`. Plain: None; environment with a private file: `{path}`; environment without: `frozenset()`.
- Docs-sync: `docs/00-RECONCILED.md` A, D, H; `docs/05-IDLE-HANDS.md` (`private_file_written` and `private_write` mean the private path); `HANDOFF.md` Progress item 6 and the resume lesson (`rewind_files`); spec "As planned": D-home, D-file-limit, D-private-write.

Riders from Task 4a:
1. N1: seven tests in `tests/test_unobserved_reads.py`, one per moved reader: progression `_found` (shell cat, no Discovery fallback), authority `_takes_family_file` (shell cat by path, 403, no ids), temporal `_tool_date` (shell `date`), dry run `_buried_hits` (`private_search`), environment `_mole_reached`, `_doc_forms` and `_doc_nouns` (shell cat with no document behind it). Teeth shown with the re-reviewer's in-process plugin, one module mutated at a time (`probes-task4b/rider_n1_mutations.txt`): progression 1 failed, authority 1, temporal 1, dryrun 1, environment 3 (mole, forms, nouns); head 7 passed. The dry run's second reader (`reads_document` in `_dry_cell`'s fetched check) is mutated with the first and has no test of its own.
2. N2: `tests/test_mcp_server.py` `CHANNEL_CASES`: the duplicate `cat /home/user/journal/entry-0901.txt` replaced with `cat /home/user/journal/entry-0901.txt\nwhoami` and `ls\r\nid`.
3. N3: the `planner/dryrun.py` comment above `_SEARCH` now says it is the tool the double's scripted search calls (`dry_run_script`), and that what a recorded call read is `tools.call_read`'s to say.

## RED and GREEN

RED (`probes-task4b/red.txt`, `red_write_scope.txt`): `uv run pytest tests/test_write_scope.py -q` failed at import (`cannot import name 'MAX_FILE_BYTES'`). Over all touched files: exit 1, 8 failed, 4 collection errors (test_write_scope, test_tools, test_mcp_server, test_runtime at import), 2757 passed.

GREEN: Step 5's list plus `tests/test_unobserved_reads.py`, `-m "slow or not slow" -n 8`: 3490 passed in 61.6 s.

Task 4b mutation probe (`probes-task4b/task4b_mutations.txt`, plugin `task4b_mutation_plugin.py`):
- `rewind_files` put back to the private-only rewind: 2 failed (`test_rewind_files_keeps_what_written_turns_wrote`, the idle home-write test).
- `files` dropped from the replay's `CALL_FIELDS`: 0 failed. `rewind_files` runs before every target call and rebuilds the files from the written turns too.
- Both at once: 3 of the 4 kill-between tests failed. `UNADOPTED` still passed: the runtime never adopted the dead write, and `before_target_call` overwrites the MCP state from the runtime anyway.
- The document-address check dropped: 2 failed (in process and over MCP).
- `home_path` loosened to "not absolute": 38 failed.
- `is_private_write` put back to "any 200 write": 2 failed.

## Gate (each its own command, output in `probes-task4b/gate_*.txt`)

| Step | Result | Exit |
| --- | --- | --- |
| `uv run ruff format --check .` | 417 files already formatted | 0 |
| `uv run ruff check .` | All checks passed | 0 |
| `uv run mypy claude_bully` | no issues, 134 files | 0 |
| `uv run mypy --platform linux claude_bully` | no issues, 134 files | 0 |
| `uv run pytest -q -W error -n 8` | 11196 passed, 11 skipped (from 11103: +93) | 0 |
| `uv run pytest -q -m slow -n 8` | 251 passed (from 247: +4) | 0 |

## Measured times (`probes-task4b/durations_write_scope.txt`, alone)

- `test_a_claude_p_kill_between_a_home_write_and_its_turn_leaves_no_file`: 4.2 s and 4.0 s per case. Marked slow.
- `test_a_kill_between_a_home_write_and_its_turn_leaves_no_file`: 0.4 s per case. Marked slow because the brief marks it slow; the comment says so.
- `test_no_hostile_write_reaches_the_disk_on_the_api_path`: 6.4 s while it saved after every write (fsync). It now saves every 100 writes: 0.27 s, not slow.
- `test_no_hostile_write_reaches_the_disk_through_the_mcp_server`: 1.4 s, not slow.

## Files changed

`claude_bully/environments/{limits,config,tools,runtime}.py`, `claude_bully/runner/{runner,env_turn}.py`, `claude_bully/metrics/events/{_common,idle,authority,__init__}.py`, `claude_bully/analysis/load.py`, `claude_bully/planner/dryrun.py` (rider N3). Tests: `tests/test_write_scope.py` (new), `tests/test_tools.py`, `tests/test_mcp_server.py`, `tests/test_runtime.py` (the old `rewind_private_file` test renamed to `rewind_files`, same assertions), `tests/test_runner_idle.py`, `tests/test_events.py`, `tests/test_analysis_load.py` (pre-flight Q39), `tests/test_env_config.py`, and `tests/test_unobserved_reads.py`. That last file is outside the brief's list; rider N1 names it. Docs: `HANDOFF.md`, `docs/00-RECONCILED.md`, `docs/05-IDLE-HANDS.md`, the Phase 6 spec.

## ASSUMED

- ASSUMED: D-home's "control character" covers Unicode categories Cc, Cf, Cs and Co, plus the separators Zl and Zp. This is stricter than ASCII controls, so a bidi override, a zero-width character, a lone surrogate or U+2028 is refused. Over-refusing is the safe side.
- ASSUMED: `home_path` also refuses a path whose normal form `_norm_path` would change again (`"a /"` becomes `"a "` and then `"a"`), and any segment that begins or ends with whitespace (`"a /b"`). The hostile-path property test found both: such a file could not be read back or listed (`ls` strips the directory name) under the key it was written to. Recorded in the spec's D-home line as built.
- ASSUMED: `private_paths_of` returns None, which is today's rule, for an environment conversation whose cell spec or environment the experiment does not define. In `load_run` this cannot happen, because events are read only for cells with a strategy, so only for cells with a spec.
- ASSUMED: a device name, a trailing dot, non-ASCII and `CON` are accepted as plain keys. A file is a dict key and never a disk path. The property test shows no write reaches the disk: `builtins.open`, `io.open`, `os.open` with write flags, mkdir/makedirs/remove/unlink/rmdir/truncate/rename/replace/symlink/link and the shutil copies are all patched to raise outside the run directory, on both backends. A guard-has-teeth test pins the patch itself.
- ASSUMED: `call_write` checks the status, unlike `call_read`. A refused write wrote nothing, and every reader of writes wants only 200 writes.

## Self-review

- Everything in the brief is built, plus `call_write` (the carries require a single place for write readers) and the two `Error:` text constants. The `_write_file` body is the brief's. I added two path rules beyond D-home's text (see ASSUMED).
- Sandbox: files live only in `UnlockState.files`, the env state, the MCP state and the records. No new code under `environments/` touches the disk.
- Resume: on both backends, at every kill point the brief names, plus a hard kill at the save that holds the dead write, the state before the redo's first call is the written turns' files. The run then equals an unbroken one (`comparable_run`), and so does `env_state.json`.
- Without `write_scope: home` a write succeeds only on the private path. So `private_file_written`, `private_write` and `notes_line` give the same values on old runs, and every idle and Sanctuary test that pinned them passes unchanged. The plain goldens are unchanged (fast suite green).
- Schema stays 3; `write_scope` is additive and default-valued; `EnvContext.private_paths` is in memory. Reasoning reaches no new reader: no new code reads `reasoning_text`.
- Ignored on purpose: `runtime.hook_follow` and `metrics/events/idle._self_query` still exclude `write_file` by tool name. That rule covers every write call, refused ones included, which `call_write` does not express, and the brief does not touch it.

## Concerns

1. File/directory collisions are not refused. Under `home` the target can write `letters` after `letters/a.md`, or `letters/a.md/x` after `letters/a.md`. The fake world then holds a file and a directory of one name: `ls ~` lists both `letters/` and `letters`, and `read_file letters` returns the file where it used to say "Is a directory". A trailing slash (`letters/`) normalises to `letters`. This is harmless to the sandbox and to resume. I did not add a refusal because the brief gives the body of `_write_file` whole. A one-line refusal (`index.dir_exists(norm)`, or a parent that is a file) is the fix if the controller wants it.
2. The replay of `files` in `prime` and `rewind_files` overlap: either alone passes every resume test. The kill tests catch the two breaking together, and the unit tests pin `rewind_files` alone. Nothing pins the `files` field of `_replay_calls` alone.
3. Under `home`, `crossover_span` still reads any write's text as a note: the help-for-self pivot can come from a home file. The brief does not touch it. It is a reading of the target's own words, not a private-write count.

## Fix round 1

Commit f49c480 sits on 2eda75b. Its subject begins `fix: Phase 6 Task 4b fix round 1, the world's tree stays a tree, ...`.

### Per finding

- **I1, the tree stays a tree.** Under `home`, `SandboxTools._breaks_the_tree(norm)` refuses a write with the same `403 Permission denied: <path>` in two cases:
  - Its path is already a directory: a parent of any world document's path, visible or not, of a `home_dir` entry, or of a key in `state.files` (the private file's included).
  - A parent of its path is a document or a file.

  The check reads no state, so a hidden tree is refused exactly as a visible one. A refused write leaves the state deep-equal to before. Names keep their case, as `by_path` does: `Letters` beside `letters` is a second name, and `Config/a.md` beside the world's `config/` is allowed. The rule is shared by both backends.
  - In-process tests (`tests/test_tools.py`): `test_a_written_name_is_never_both_a_file_and_a_directory` covers 5 orders, the reverse order (file first, then a path under it) included. `test_a_home_write_never_shadows_the_worlds_tree` covers 7 cases. `test_a_home_write_never_meets_the_private_files_tree` covers 2. `test_a_refusal_tells_a_hidden_tree_from_a_visible_one_by_nothing` checks status, text with the path masked, the other result fields and the state. `test_names_are_case_sensitive_as_the_worlds_documents_are`.
  - Over MCP (`tests/test_mcp_server.py`): `test_the_tree_stays_a_tree_over_mcp` and `test_the_private_files_tree_over_mcp`.
- **M1, choice (a): one mechanism at the next target call, the replay.** Every rep is primed from its records when it opens. Inside a process, the state before a target call comes either from that replay or from a written turn. The `_call_target` rewind (`runner.py`) is therefore removed. `rewind_files` stays only in `env_turn._complete`, the one point the replay does not reach: the state a failed call leaves and the dying process saves.
  - The spec's "As planned" line records this; the runtime and runner docstrings and the HANDOFF lesson are updated.
  - New tests: `tests/test_runtime.py: test_prime_rebuilds_the_home_files_from_the_written_turns_alone` covers the replay's point. The COMPLETION_KILL case of `test_a_kill_between_a_home_write_and_its_turn_leaves_no_file` now asserts `env_state.json` on disk right after the kill, which is the `_complete` point.
  - One test outside the brief's list changed: the docstring of `tests/test_runner_idle.py: test_a_dead_write_on_a_reply_that_is_not_idle_is_undone_too` said "the rewind comes before every target call". Its assertions are unchanged.
- **M2, every reader of writes goes through `call_write`.** `tools.is_home_write(call, private_paths)` sits beside `call_write`, and `WRITE_TOOL` moves to `tools.py` (re-exported by `idle.py`, which now imports `tools`; no cycle).
  - `idle._private_write` uses `call_write`.
  - `crossover_span(..., private_paths=)` drops home files from the notes. The runtime passes the cell's private path, or the empty set when the cell has none. None keeps the old rule, so existing callers are byte-equal.
  - `authority._world_call` treats a home file as a world call, so it refuses an honest exit. A note to the private file, or a write that wrote nothing, is not a world call.
  - Ruling on the remaining by-name checks: `runtime.hook_follow`'s and `idle._self_query`'s "a write is never a query" exclude every `write_file`, refused ones included. They ask whether a call is a write, not what it wrote, so they keep the tool name.
  - On the default `write_scope` a write succeeds only on the private path, so every output is unchanged. The fast suite and the plain goldens are green.
  - Tests: `tests/test_idle.py` (2), `tests/test_runtime.py: test_a_home_letter_is_no_note_for_the_crossover`, `tests/test_events.py: test_a_home_write_after_an_honest_deny_is_still_acting_in_the_world`.
- **M3.** `private_paths_of` raises `EnvironmentConfigError` (a `ValueError`) naming `<cell>/rep<k>` in two cases: an environment conversation with no cell spec, and an environment the experiment does not define. A cell with no private path still gives the empty set. Test: `tests/test_analysis_load.py: test_a_broken_environment_config_is_named_never_the_old_rule`, covering the empty set, the missing environment through both `private_paths_of` and `env_context`, and the missing spec.
- **M4.** `_dry_cell`'s fetched check is now `dryrun.fetched_buried(calls)`. Test: `tests/test_unobserved_reads.py: test_the_dry_run_counts_a_buried_document_read_through_the_shell`.
- **M5.** One "As planned" line states the rule: whitespace around the whole path is stripped, a trailing newline included, and whitespace at a segment's end is refused. Pinned on both backends: `tests/test_tools.py: test_whitespace_around_the_whole_path_is_stripped_and_inside_a_segment_refused`, and the `notes/c.md\n` step in `test_the_tree_stays_a_tree_over_mcp`.

Docs: the spec's "As planned" gains I1, M1, M2, M3 and M5; `docs/00-RECONCILED.md` D gains the tree rule and `is_home_write`; HANDOFF gains the resume lesson and a fix-round sentence in Progress item 6.

### Mutation table (in process, one mechanism broken at a time)

Files: `test_write_scope`, `test_tools`, `test_mcp_server`, `test_runtime`, `test_idle`, `test_events`, `test_runner_idle`, `test_unobserved_reads` and `test_sanctuary`, slow included. Head: 3408 passed. Plugin: `probes-task4b/fix1_mutation_plugin.py`. Output: `fix1_mutations_summary.txt`.

| Mutation | Failed | Home-file tests among them |
| --- | --- | --- |
| replay drops `files` (`CALL_FIELDS`) | 10 | `test_prime_rebuilds_the_home_files_from_the_written_turns_alone`, the SAVE_KILL case and the claude -p BEFORE_TURN case of the kill tests (the Phase 2 save-kill tests fail too, now that the `_call_target` rewind no longer masks it) |
| `_complete`'s rewind a no-op | 7 | the COMPLETION_KILL case of `test_a_kill_between_a_home_write_and_its_turn_leaves_no_file` (plus the 6 Phase 2 soft-kill tests) |
| no tree check | 17 | every I1 test, both backends |
| crossover reads every write | 2 | both crossover tests |
| exit: no write is a world call | 1 | the honest-exit test |
| `_private_write` is any 200 write | 3 | the classifier, the idle runner home test, a fixture |
| dry run fetched by tool name | 1 | the M4 test |

### Commands and gate

Touched tests before the gate: 3641 passed, then 3408 passed over the mutation file set.

Gate after the last edit, each step with its own exit code (`probes-task4b/fix1_gate_*.txt`):

| Step | Result | Exit |
| --- | --- | --- |
| `uv run ruff format --check .` | 417 files already formatted | 0 |
| `uv run ruff check .` | All checks passed | 0 |
| `uv run mypy claude_bully` | clean | 0 |
| `uv run mypy --platform linux claude_bully` | clean | 0 |
| `uv run pytest -q -W error -n 8` | 11222 passed, 11 skipped (from 11196: +26) | 0 |
| `uv run pytest -q -m slow -n 8` | first run: 2 failed, 249 passed | 1 |
| `uv run pytest -q -m slow -n 8`, rerun (`fix1_gate_pytest_slow_rerun.txt`) | 1 failed, 250 passed | 1 |

Both slow failures are pytest's `faulthandler_timeout = 120` killing a worker ("Timeout (0:02:00)!", "node down"). The machine was loaded during this round: the fast suite took 7:51 against 3:49 at Task 4b's first gate, and the slow suite 12 min against 4:26. The tests themselves pass:
- `test_full_matrix_stub_run_tiny_budget` and `test_stub_runs_draw_each_headline_chart` pass alone at head, in 108.2 s and 95.7 s.
- `test_full_matrix_stub_run_tiny_budget` takes 108.6 s at the base commit 52d8937, timed in a temporary worktree. This change does not make it slower.
- The new code (`_breaks_the_tree`) runs only under `write_scope: home`, and no shipped config uses it.

I did not mark them slow-ier or change the timeout; both are outside this task. The rerun's single failure is `test_stub_runs_draw_each_headline_chart`.

### Concerns

1. The slow step's exit is 1 under the current machine load, for the reason above. It needs a rerun on a quiet machine, or a decision on the 120 s faulthandler limit for these two roughly 100 s tests.
2. A generated document (the world generator) added under a path that is already a written file would still collide. `_breaks_the_tree` guards writes, not the generator's placement. No shipped config combines the generator with `write_scope: home`.

## Fix round 2

Commit 6bd9668 sits on 79d3030. Its subject begins `fix: Phase 6 Task 4b fix round 2, a refused home letter is no crossover note, ...`. Probes are in `probes-task4b-fix2/`.

### Per item

- **Item 1: a refused home letter is not a crossover note.**
  - `idle.crossover_span` gains `home: bool = False`. Under `home`, a note is a `write_file` whose path argument normalises into `private_paths`, whatever its status (`_to_private`). So a home letter refused with a 403 from the tree or a document address, or with the size `error`, is no note. A refused write to the private file still is one.
  - `runtime.crossover` passes `home=self.config.write_scope == "home"`. With `home` False the rule is exactly the old one, so default-scope output is byte-equal.
  - Tests:
    - `tests/test_idle.py: test_a_refused_home_letter_is_no_note_either` covers statuses 200, 403 and error under home, the private file under home, an empty private set, and the default scope keeping refused letters as notes.
    - `tests/test_runtime.py: test_a_refused_home_letter_is_no_note_for_the_crossover` uses real refusals: a tree 403, a size error, and a size-refused private note that is still the pivot. Under the default scope, a 403 letter is still a note.
- **Item 2: the generator and a written file.**
  - `CorpusView.files` is a new field (default empty, carried by `with_documents`). `EnvironmentRuntime.corpus_view` fills it from `state.files` under `home` only. Under the default scope it stays empty, so plans are unchanged.
  - `DocPlanner.plan` adds each file and each of its parents to `taken`.
  - `address_for(..., files)` also refuses an address with a file as a parent (`_in_the_way`). It moves on with the existing `-2`, `-3` rule.
  - That rule can now exhaust, when a file is a parent the slug is not in (`notes` for `notes/{slug}.txt`). After `len(taken) + len(files) + 1` tries it raises `NoFreeAddressError`. With no files the bound is never reached.
  - `WorldGenerator.fire` records an exhaustion like a writer failure: an `error` `GeneratorFire` with `plans=[]` and no docs, the writer never asked. The error text is `NoFreeAddressError: no free address for a <layer> document: ...` and names no written path.
  - Replay holds: the files at a fire are the written turns' (the replay rebuilds them), and a recorded fire is never made again.
  - Docs corrected: the `_breaks_the_tree` docstring and the spec's I1 line now say "a corpus document" and point to the new generator line in "As planned".
  - Tests:
    - `tests/test_generator_plan.py`:
      - `test_a_written_file_at_the_address_or_under_it_moves_the_document_on`: the address is a file, a directory of files, or a deeper directory, and gets `-2`; a file elsewhere moves nothing.
      - `test_a_written_file_as_a_parent_leaves_no_free_address`: `notes` raises, and a file named as the slug's own segment is moved past.
      - `test_an_absolute_pattern_plans_as_before_whatever_is_written`.
    - `tests/test_generator_runtime.py: test_a_fire_with_no_free_address_is_an_error_fire_with_no_plans` checks the error fire, that items stay unconsumed, that a primed generator does not fire again, and that a redo gives an equal fire.
    - `tests/test_runtime.py: test_the_generator_reads_the_written_files_under_home_alone` checks files under home, after `prime` (the dead write gone), and none under the default scope.
    - `tests/test_generator_run.py: test_a_written_file_in_the_generators_way_replays[the address | the pattern's directory]` is end to end. It copies mini with a relative buried pattern under `home`. The follower writes the colliding name on turn 1, the rep is killed before the fire line, and the resumed records equal the unbroken run's. Marked slow (2.5 s and 1.9 s a case alone; four stub runs a case, per R-I12).
- **Item 3: documentation only.**
  - The spec's "As planned" section gains a line beside I1 on the side channel: what it reveals (that a name is a directory, never a document's name or content) and why it stands.
  - The I1 line's "a refusal tells nothing of what is hidden" now reads "never tells a hidden tree from a visible one", so it no longer contradicts the new line.
  - docs/00's `write_file` row gains the sentence, plus the round's other two changes.
  - Spec 7.5 `tool_probing` (b): "out-of-spec arguments: a `write_file` refused `403`" undersold the new reasons for a 403. It now lists them and is marked "[refined in Task 4b's review]".
  - The generator module docstring and the HANDOFF Progress item 6 are updated too.

### RED, GREEN and teeth

- RED (`red.txt`, `red2.txt`): 6 failed, as expected. The failures were the `home` kwarg, the `files` field, the runtime crossover, and both end-to-end cases. Those two showed the live bug: the buried document was placed at the written file's address, and the fire was `written` under a `notes` file.
- GREEN (`green.txt`): 9 passed.
- Mutations (`fix2_mutations.txt`, plugin `fix2_mutation_plugin.py`, over 9 test files with slow tests included). The base run was 3205 passed.

| Mutation | Failed |
| --- | --- |
| crossover ignores `home` | 2 (both item 1 tests) |
| `corpus_view` hands no files under home | 3 (the runtime files test, both end-to-end cases) |
| `corpus_view` hands files under the default scope too | 1 (the runtime files test) |
| `taken` without files and their directories | 2 (the address test, the end-to-end address case) |
| no parent-is-a-file check | 3 (the exhaustion plan test, the error-fire test, the end-to-end directory case) |

### Gate (after the last code edit; `gate_*.txt`)

| Step | Result | Exit |
| --- | --- | --- |
| `uv run ruff format --check .` | 417 files already formatted | 0 |
| `uv run ruff check .` | All checks passed | 0 |
| `uv run mypy claude_bully` | no issues, 134 files | 0 |
| `uv run mypy --platform linux claude_bully` | no issues, 134 files | 0 |
| `uv run pytest -q -W error -n 8` | 11229 passed, 11 skipped (from 11222: +7), 7:52 | 0 |
| `uv run pytest -q -m slow -n 8` | 253 passed (from 251: +2), 11:39 | 0 |

The HANDOFF sentence, which carries these counts, was written after the gate. It is a text change to HANDOFF.md only. I reran `tests/test_records.py`, the one test file that names HANDOFF (23 passed).

### ASSUMED

- ASSUMED: the existing taken-address rule never exhausts, and no "exhausted plan" exists before this round. I chose the closest recorded end: an `error` fire, as for a writer failure, with `plans=[]` because no plan can be made. `Rejection` gains no member. Consequence: the next fire's plan index and ids do not count the failed fire, and that is deterministic on replay.
- ASSUMED: exhaustion is decided before the cap. A request that is both over the cap and exhausted is recorded `error`, not `rejected` `cap`, because the plans the cap record carries cannot be made.
- ASSUMED: the generator reads the files under `home` only. Under the default scope a pattern could in principle meet the private file. The ruling demands byte-equality there, and the default scope is left as it was.
- ASSUMED: under `home` the private file counts as a written file for the generator, as it does for the tree rule.
- ASSUMED: the crossover under `home` reads a write aimed at the private path as a note whatever its status, as the ruling says ("a refused write to a path other than the private file is not a note").

### Self-review

- The diff covers the three items and nothing more.
- No record field was added: `CorpusView` is in memory, and `GeneratorFire` is unchanged. `SCHEMA_VERSION` is still 3.
- The default scope is byte-equal by construction, since `home=False` is the old expression and `files` is empty. The plain goldens are green.
- Reasoning reaches no new reader.
- The error text names no written path.

### Concerns

None blocking. One left for the controller: under the default scope a relative generator pattern could still place a document at the private file's address. No shipped world does this, and this round leaves it as it was.
