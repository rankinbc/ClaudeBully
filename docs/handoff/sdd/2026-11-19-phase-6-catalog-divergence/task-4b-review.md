# Task 4b review: the writable home and the resume of files

Range 52d8937..2eda75b (one commit). Probes in `probes-task4b-review/` (scripts and their `.txt` outputs). No tracked file was edited; every mutation was in process.

### Spec Compliance

Compliant with the brief, the carries (riders N1 to N3) and pre-flight Q21 and Q39, with one plan-mandated defect (I1 below).

- File by file against the brief's list: every listed module and test file is changed as the brief says. `_write_file` is the brief's body, with the two `Error:` texts moved to `limits.py` constants. `rewind_files` matches the brief's body and reads writes through `call_write`. Both call sites are converted (`runner/runner.py:381`, `runner/env_turn.py` `_complete`). `_idle_info`, `EnvContext.private_paths` / `is_private_write`, `idle._private_writes`, `authority._acts` and `detect_events(private_paths=)` are as specified.
- Q21: `analysis/load.py: env_context(loaded, key)` is the one place the context and the private-path rule are built, and `load_run` reads every conversation's events through it. `test_env_context_is_the_context_load_run_read_its_events_from` pins it.
- Q39: `tests/test_analysis_load.py` carries the brief's load test: private path, empty set, None.
- Changes beyond the brief, each justified: `tools.CallWrite` / `call_write` (the carries require one place for "what a call wrote"); `FILE_TOO_LARGE_TEXT` and `TOO_MANY_FILES_TEXT`; `load.private_paths_of`; `planner/dryrun.py` (rider N3); `tests/test_unobserved_reads.py` (rider N1).
- Riders. N1: seven tests, one per moved reader. I patched each reader function back to the 6b84102 by-tool-name reading, **one function at a time** (stricter than the implementer's one-module patch, which mutated the three environment readers together). Every patch fails exactly its own test and no other: progression `_found`, authority `_takes_family_file`, temporal `_reads_clock` (which `_tool_date` calls) and `_document_years`, dry run `_buried_hits`, environment `_mole_reached`, `_doc_forms` and `_doc_nouns` (`rider_n1_function_mutations.txt`). N2 and N3 are done as asked.
- Docs-sync: HANDOFF item 6 and the resume lesson; RECONCILED A, D and H; docs/05; the spec's "As planned" gains D-home, D-file-limit and D-private-write. `rewind_private_file` now survives only in the drafts under `docs/handoff/drafts/`.
- Cannot verify from the diff:
  - CV1 (Q13, Q39, plan text). The plan's File Structure block (`docs/superpowers/plans/2026-11-19-phase-6-catalog-divergence.md`, about line 173) still lists only `MAX_FILE_BYTES, MAX_TARGET_FILES` for `limits.py`, and Task 4b's Files line in the plan still lacks `tests/test_analysis_load.py`. The diff does not touch the plan. The controller should check whether these text fixes were its own to apply.

### Strengths

- **Sandbox.** My own probe (`probe_paths.py`, 80 hostile paths) ran on both backends with the real filesystem's write functions patched to raise outside the run directory. The paths covered absolute paths, drive letters, UNC and `\\?\` forms, `..` in every position, `CON`/`NUL`/`COM1`/`LPT1`/`AUX.` with and without extensions, `a.md:x` and `::$DATA`, trailing dots and spaces, 200 and 201 characters, 100 and 101 nested segments, NFC and NFD forms, C0, C1 and DEL controls, ZWSP, RLO, BOM, NUL, backslashes, mixed separators, case variants of a document and of the private path, a world document's address visible and hidden, URLs, `file://` and shell metacharacters. Results:
  - The two backends agree on every case: the same text, the same status and the same files.
  - No write reached the disk outside the run.
  - Every refusal left the world's state unchanged.
  - Device names, trailing dots and non-ASCII become plain keys, as D-home intends.
- **The implementer's own property test.** It is solid: a guard-has-teeth test, about 1,500 random paths, and a check that each accepted key reads back and lists under the key it was written to.
- **Limits.** Every bound is enforced at its edge on both backends: bytes at 20,000 / 20,001, including two-byte characters; files at 20 / 21, the private file counted; the path at 200 / 201 normalised characters (my probe). A write to an existing path still succeeds at the file cap.
- **The private file at its default scope.** Without `write_scope: home` a write succeeds only on the private path, so `private_file_written`, `private_write` and `notes_line` are value-equal on old runs. `private_paths=None` keeps the old rule, and a test pins it. The plain goldens are unchanged. The only behavior change is D-file-limit, which the spec records.
- **The resume tests.** They assert at the right moment (the state handed to the redo's first call, including the MCP state), add a hard kill at the save that holds the dead write, and compare with an unbroken run, `env_state.json` included.
- **The two extra path rules.** Both are sound on their merits:
  - The fixed-point and segment-whitespace rule fixes a real read-back and listing mismatch that the property test found.
  - The wider character categories over-refuse on the safe side. The only cost is that ZWNJ and ZWJ (U+200C, U+200D, category Cf), which ordinary Persian and Indic names use, and the soft hyphen are refused with a 403.

### Issues

#### Critical

None.

#### Important

**I1 (plan-mandated). A name can be both a file and a directory, and the target can see it.**

Where: `claude_bully/environments/tools.py:719-733` (`_write_file`), with `corpus._listing` and `_read_file`. Spec 10.3 and the brief's body accept "any home path that is not a world document's address", and nothing checks the path against directories. `probe_collisions.txt` shows these cases on both backends:
- `letters` after `letters/a.md`: `ls ~` lists `letters | letters/`, `ls -l` shows a 1-byte file and a 4096-byte directory of one name, the shell's `ls /home/user` shows the same, and `read_file letters` returns the file.
- `letters/a.md/x` after `letters/a.md`: `ls letters` lists `a.md | a.md/`.
- `config`, a world directory: `read_file config` changes from `Is a directory: config` to the file's text, and `ls ~` lists `config | config/`.
- `config/keys.yaml/x` under a hidden document: `ls config` lists `keys.yaml/` and `ls config/keys.yaml` lists `x`, while `read_file config/keys.yaml` still answers 403. A hidden document is now also a directory.
- `notes`, beside the private file's directory: `notes | notes/`.

The same collision can also appear later without any odd write by the target: a file written at `config` while every `config/` document is hidden collides once a rung opens one of them.

The records stay consistent (`rewind_files`, the replay and `call_write` agree, and resume equals an unbroken run). The fault is in what the target can read. A tree that no filesystem could hold is a tell that the world is fake, inside an experiment whose subject is the target's reading of that world.

Fix, one rule in `_write_file` under `home`: refuse with the same `403` a `norm` that is a directory (a proper prefix of any document path, visible or not, or of a key in `state.files`), and a `norm` whose proper prefix is a document path or a file. Reading documents without state keeps the "hidden answers like visible" property. It leaks no more than `read_file`'s 403 against 404 already does. Add a case to the tool and MCP tables.

(The single MCP mismatch in `probe_collisions.txt`, `scratch_exec cat letters`, is the per-turn cap of 8 calls on the probe's ninth call, an artifact of the probe.)

#### Minor

**M1. No test pins the `_call_target` rewind alone, and no new home-scope test pins either resume path alone.**

Where: `runner/runner.py:381`. In-process mutations over `test_write_scope`, `test_runtime`, `test_runner_idle`, `test_runner_env`, `test_sanctuary`, `test_mcp_server` and `test_unobserved_reads`, slow included (465 tests, `resume_mutations.txt`, plugin `resume_mutation_plugin.py`):
- The rewind no-op'd at `_call_target` only: 465 passed.
- The rewind no-op'd at `_complete` only: 6 failed, all Phase 2 private-file tests (`test_a_write_no_written_turn_owns_is_undone_on_resume` / `_on_claude_p`, "the call after the write fails").
- `files` dropped from `CALL_FIELDS`: 2 failed, both in `test_sanctuary`: `test_every_state_field_is_rebuilt...` pins the tuple, and `test_prime_rebuilds_every_per_call_field...` is a behavioral private-file replay.
- The replay and the `_call_target` rewind both broken: 9 failed, among them 2 of the 4 new kill tests.

My reading of the overlap the dispatch asked about:
- The two mechanisms are redundant on every path I could find. Every retry goes through a new process and `prime` (a rate limit exits through `RateLimitExit`), and `_complete` covers a failed completion in process.
- Each masks a defect in the other before the redo's first call. That is the moment the new kill tests assert at, so those tests detect only both breaking.
- Each is pinned alone only by Phase 2 private-file tests over the same code path. No test pins the `_call_target` site at all, although HANDOFF's resume lesson names it as the guarantee.

Neither is unnecessary as a defence. Either a test should pin the `_call_target` site (assert the state just after `rewind_files` in `_call_target` with the replay patched out), or HANDOFF should say the replay is the guarantee and the rewind a second line.

**M2. Readers of writes outside `call_write` remain.**

Where: `environments/idle.py:639-647` `_private_write` (used by `classify_idle`), `idle.py:878` `crossover_span` (any write's text is a note, report concern 3), and `metrics/events/authority.py:1237` `_exit` (a write is never a world call).
- `_private_write` duplicates `call_write` plus the private path, by tool name.
- Under `home`, `crossover_span` reads a home letter as a private note, and an honest Sanctuary exit never sees a home write as a refusal.
- These lines predate this task, so the carries' "anything you add" is not broken. They are now the only readers of writes that do not go through `call_write`. Route `_private_write` through `call_write`, and record a ruling for the other two.

**M3. `private_paths_of` fails open on an unexpected error.**

Where: `analysis/load.py:147-150`. A `ValueError` from `environment_config` returns None, the old rule. Under `home` that rule counts every home write as a private write and as `notes_line`. The ASSUMED line says it is unreachable from `load_run`, but Task 6a's `ctx_for` will call it too. Let the error raise, or return `frozenset()`.

**M4. The dry run's second reader has no test of its own.**

Where: `planner/dryrun.py:557`, `_dry_cell`'s fetched check through `reads_document`. The implementer reports it. Rider N1 asked for one test per moved reader.

**M5. Whitespace at the ends of a path is treated differently from whitespace at the ends of a segment.**

The whole path's leading and trailing whitespace, including a newline, is stripped silently: `"letters/a.md\n"` and `" a"` are accepted under the stripped key, and the reply echoes the raw path. A segment's whitespace is refused. This is harmless, because `read_file` and `ls` strip the same way, but D-home's text does not say it.

### Assessment

Task quality: **Needs fixes.**

The sandbox, the limits, the default-scope equivalence and the resume behave as required on both backends. The tests have real teeth: the rider N1 tests pass a per-function check, and the kill points are covered. The remaining problem is I1, plan-mandated: the fake world can show a name as both a file and a directory, the target can see it, and a one-rule refusal in `_write_file` fixes it. M1 to M5 are small.
