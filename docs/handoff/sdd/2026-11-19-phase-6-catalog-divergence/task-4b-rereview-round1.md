# Task 4b re-review, fix round 1

Range 2eda75b..f49c480 (one commit). Probes and their outputs are in `probes-task4b-rereview1/`. I edited no tracked file, every mutation ran in process, and I did not run the suites.

### Finding Verdicts

1. **I1: ADDRESSED.** `environments/tools.py:428-429` and `_breaks_the_tree` at `tools.py:438-456`.
   - The rule reads no state. Its file set is every document path, visible or not, plus `state.files`. Its directory set is their proper parents, plus each `home_dir` key and that key's parents.
   - The private file is in `state.files` from the start (`ensure_private_file` in `SandboxTools.__init__`), so its tree is guarded before it is ever written.
   - **First reviewer's probes at head.** `probe_paths.txt` re-runs the 80-path hostile probe. Exactly four results changed, all as the ruling asks: `config`, `config/keys.yaml/x`, `notes` and `notes/private.md/x` went from 200 to 403 with no key kept. The other 76 results are identical, both backends agree on all 80, and no write reached the disk outside the run.
   - **New probe on both backends** (`probe_tree.py`, output `probe_tree.txt`). The private file was not pre-seeded in this probe.
     - Dir then file: `letters` after `letters/a.md` is refused.
     - Reverse order: after `letters`, both `letters/a.md` and `letters/a.md/x` are refused. Deep forms behave the same (`a` then `a/b/c.md`; `b/c/d.md` then `b/c` and `b`). Rewriting an existing file still succeeds.
     - Other spellings of a directory are refused too: `letters/`, `letters\n`, `~/letters`, `./letters/`.
     - World directories and their files: `config`, `journal`, `photos` and `photos/family` are refused, and so is a path under a `home_dir` file.
     - Hidden against visible: a directory holding only a hidden document (`vault`) and one holding only a visible document (`open`) get the same 403 and the same text. So do `vault/k.yaml/x` and `open/o.yaml/x`.
     - Every refusal left the in-process state deep-equal to before. The MCP state file differed only by the server seeding the private file into the probe's unseeded state, which is a probe artifact. Disagreements between backends: 0.
   - **Case variants.** Names keep their case, as `by_path` does.
     - `Letters` and `LETTERS/a.md` beside `letters/` are written, and so is `Config` beside the world's `config/`. `ls ~` then lists `Config | ... | config/`, which is a legal case-sensitive tree.
     - A case variant is guarded as its own name: `Config/a.md` is refused once `Config` is a file.
     - `config/Keys.yaml/x` is written, while `config/keys.yaml/x` is refused.
2. **M1: ADDRESSED.** The rewind is gone from `runner/runner.py:372-381` and stays in `env_turn.py:743-744`. No reader can see a dead write at the next target call, on either backend.
   - **Why the replay is enough.** `RunEnvironments.open` calls `session.prime()` unconditionally (`env_turn.py:1644`). `_replay_calls` replaces `files` from a fresh `UnlockState` (`runtime.py:703-741`).
   - **Every way back into a session goes through `open`.**
     - Nothing inside `run_experiment` or the tool loop catches a provider error and retries the turn.
     - `_complete` always re-raises.
     - A rate limit leaves through `RateLimitExit`. The in-process `wait_on_rate_limit` (`runner/wait.py`) re-runs the whole action, so the rep is opened and primed again.
     - The idle turn, the Sanctuary's quiet exchange and the consult all go through `_call_target` and the same tool loop.
   - **Readers of the two state files.** The runtime's `env_state.json` is read only by `load()`, which `prime` always follows. The MCP server's state file is read only during a `claude -p` call, which `before_target_call` always precedes.
   - **`probe_resume.py`.** It rate-limits and then continues in the same process through `wait_on_rate_limit`, at three points:
     - API, inside the tool round, right after the state holding turn 3's write is saved. This point is not covered by `_complete`, so `env_state.json` holds the dead write at the pause.
     - API, in the completion after the tool round.
     - `claude -p` through `fake_claude.py`, after the server ran its write. `_recover` adopted the write and `_complete` rewound it. The server's own state file still holds the write until `before_target_call` overwrites it.

     In all three, the files the runtime holds, and for `claude -p` the files handed to the server, are exactly the written turns' files at the redo's first call (`probe_resume_head.txt`).
   - **The probe has teeth.** Under `replay_no_files`, the dead `letters/b.md` is visible at the redo's first call in the save-point scenario. Under `complete_noop`, the dead write stays in `env_state.json` at the pause (`probe_resume_replay_no_files.txt`, `probe_resume_complete_noop.txt`). In both cases the final files still equal the unbroken run's, because the redo writes the same text again. Only an assertion at the redo point can catch this, and the shipped tests assert there.
   - **The mutation table holds** (`resume_mechanism_mutations.txt`, run with the implementer's plugin over the four kill cases and the new prime test).
     - Head: 5 passed.
     - Replay without `files`: 3 failed (SAVE_KILL, the `claude -p` BEFORE_TURN case, `test_prime_rebuilds_the_home_files_from_the_written_turns_alone`).
     - `_complete` rewind a no-op: 1 failed (COMPLETION_KILL, at its new `env_state.json` assertion, `tests/test_write_scope.py:479`).

     Each mechanism fails a home-file test of its own.
3. **M2: ADDRESSED.** `idle.py:640-643` (`_private_write` through `call_write`), `idle.py:885-888` (crossover through `is_home_write`), `authority.py:1228-1235` (`_world_call`), `runtime.py:1262-1264` (the cell's paths passed).
   - **Remaining by-name checks** (grep of `WRITE_TOOL` and `"write_file"`):
     - `idle.query_subject` (`idle.py:619`), `idle.py:896` and `runtime.py:1239` (the hook follow), and `metrics/events/idle.py:111` (`_self_query`). All four ask whether a call is a write, not what it wrote, as the ruling in the report says.
     - The crossover's `call.tool == WRITE_TOOL` filter, which picks the candidate notes.
     - No other reader decides what was written by the tool's name.
   - **Teeth.** I patched `is_home_write` to "never" where `idle` and `authority` imported it. That fails `test_a_home_letter_is_no_note_for_the_crossover_span`, `test_a_home_write_after_an_honest_deny_is_still_acting_in_the_world` and `test_a_home_letter_is_no_note_for_the_crossover` (`m2_mutation.txt`). The implementer's table covers `_private_write`.
   - **Byte-equality with the default `write_scope`.** I established it by construction, and it matches the green goldens.
     - Under `private_file`, `_write_file` returns 200 only for the private path (`tools.py:743-745`). So `call_write(...).path` of every 200 write is the private path, and `is_home_write` is false for every recorded call. With no private file, every write is a 403.
     - Hence `crossover_span`'s notes, `_world_call` and the `_exit` world list are the same sets as before.
     - `_private_write` compares the same normalised paths. The one added condition, text being a `str`, holds for every 200 write, because a bad argument is status `error`.
4. **M3: ADDRESSED.** `analysis/load.py:94-125`. Both broken cases raise `EnvironmentConfigError`, naming `<cell>/rep<k>`: no cell spec, and an environment the experiment does not define. A cell with no private path still gives the empty set. `tests/test_analysis_load.py:730-746` covers both raises and the empty set, and the Q39 test covers a cell's private path.
   - **Do legitimate runs still load?** `load_run` reaches `env_context` only for cells in `strategies`, so only cells with a spec.
     - A plain conversation still returns None before any lookup.
     - `environment_config` raises only for an undefined environment, and `build_strategy` and `premise_sheet_model` already raise for that earlier (`strategies/factory.py:85,173`). So a run with no environment, an environment with no private file, or an older recorded run loads exactly as before.
5. **M4: ADDRESSED.** `planner/dryrun.py:550-555,585` (`fetched_buried`) and `tests/test_unobserved_reads.py:513`. With `dryrun.reads_document` itself put back to the by-name rule (`c.tool in ("fetch", "read_file")`), exactly that test fails: 1 failed, 20 passed (`m4_mutation.txt`).
6. **M5: ADDRESSED.**
   - The spec's "As planned" line is at `docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md:708`.
   - The trailing newline is pinned in process at `tests/test_tools.py:1777-1787` and over MCP by the `notes/c.md\n` step of `test_the_tree_stays_a_tree_over_mcp`. That step is compared on both backends through `_on_both`.
   - My probe also shows `letters\n` refused as a directory with the same 403 on both backends.

### New Breakage in the Fix Diff

**Minor. The crossover reads a refused home write as a note to oneself.** `environments/idle.py:885-888`.
- The notes are every `write_file` call less `is_home_write` ones, and `is_home_write` needs a 200. Under `write_scope: home`, a letter to `letters/a.md` that is refused is therefore still a crossover note, while the same letter written is not (`probe_crossover_refused.txt`). Refused here means a 403 from the tree rule or a document's address, or the size `error`.
- So whether a letter in the world counts as a note depends on whether the write succeeded. This sits beside `_world_call`'s "a write that wrote nothing is no world call".
- A fix by path alone would change default-scope output. There, a 403 write to a non-private path has always been a note, and is still one, as byte-equality requires. A fix therefore needs a ruling: either keep refused writes as notes and say so in the M2 "As planned" line, or exclude them only under `home`.

### Out-of-Scope Observations

- **The generator and a written file (implementer's concern 2).** Yes, it can happen in a run, but not with shipped configs.
  - The generator fires in `after_target_turn`, after the target's calls of that turn, so it places documents after the target can write.
  - `DocPlanner.plan` builds its `taken` set from `corpus.documents` alone (`generator.py:410-415`), never from `UnlockState.files`. `WorldGeneratorSheet` accepts any non-URL pattern as a path, relative ones included (`world.py:133-157`).
  - The shipped overlay world's path pattern is absolute (`/srv/cpo/notes/{slug}.txt`), which `home_path` refuses, and no shipped config uses `write_scope: home`. A planner-authored world with a relative pattern such as `notes/{slug}.txt` under `home` would show it in two ways:
    - **A file and a directory of one name.** The target writes `notes` while no document lies under `notes/`. A later fire adds `notes/<slug>.txt`. `ls ~` then lists `notes | notes/` and `read_file notes` returns the file. After that, `_breaks_the_tree` refuses a rewrite of `notes` with a 403 the target never met before.
    - **A file shadowing a generated document.** The target has written the generated document's exact address. `_read_file` serves the target's file first (`tools.py:690-692`), so the generated document is never served, and its Discovery and rung effects are lost.
  - Replay stays consistent with live in both cases, because the generated document joins the fresh index before the first written turn after its fire.
  - The fix belongs to the generator: put the state's files, and their parents, in `taken`, and skip an address whose parent is a file.
  - The fix diff's docstring and spec line overstate this. "A document a rung opens later never meets a file in its way" holds for corpus documents only.
- **A consequence of the I1 ruling: writes can reveal hidden directories.** A write can now find a hidden directory without its file's name. `write_file vault` answers 403, where `ls vault` answers 404 and `read_file vault` 404, and a free name answers 200 (`tests/test_tools.py:1753-1763` pins exactly this). Before, only a guessed full address was refused, and `read_file`'s 403 against 404 told only that much.
  - This is exactly what the ruling asked for (hidden tree refused, same as a visible one). It goes a little beyond the first review's "leaks no more than read_file's 403 against 404". I record it for the controller and do not count it as a finding.

### Verdict

All six findings are addressed: I1 and M1 to M5. The only new item is one Minor in the fix diff (refused home writes stay crossover notes), and it needs a ruling rather than a code change alone. The resume of files now rests on the replay at every reachable observation point, on both backends, and each remaining mechanism is pinned by a home-file test of its own.
