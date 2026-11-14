# Task 14 re-review, round 1 (5975977..a8a5578)

Scope: the fix round's seven findings (I1, M4 re-graded Important, M1, M2, M3, M5, M6) and the fix diff `review-5975977..a8a5578.diff`, read once. Read-only on the repo: `git status` is clean at a8a5578. Every probe and mutant ran in a `git archive HEAD` copy under `probes-task14-rereview/tree` (with its own `.venv`; each mutated file was restored after its run). The suite was not re-run; I ran only the named tests, the two golden tests, and `test_replay*.py`, `test_phase4_minors.py`, `test_real_names.py` (178 passed) to check what a mutant or a probe touched.

## Verdicts

| Finding | Verdict | One line |
| --- | --- | --- |
| I1 configs scan exempts any `display_name:` | ADDRESSED | The review's plant now fails the scan; no shipped exemption changed (old and new `_display_names()` are both `{claude}`). |
| M4 damaged log hides the rate limit | ADDRESSED | The rate limit wins; a kill at the swallow point and every damaged run probed (31) resume to exactly the twin's records and state. One Minor side effect (N1, the ledger fold). |
| M1 three `_agrees` sub-rules unbound | ADDRESSED | All eight conjunct mutants now die, including the review's three survivors. |
| M2 CROSSOVER prints its span raw | ADDRESSED | 20 adversarial spans and a span-less line round-trip; each stays one line. |
| M3 resume raises on a closed-off torn line | ADDRESSED (scoped as ruled) | Right to leave the store's generated stream raising. Two Minor test gaps on the scoping (N2). |
| M5 "a different body" | ADDRESSED | Message and test say "a different record". |
| M6 sibling maps omit empty cells | ADDRESSED | `generator.json` and `poisoned_well.json` list every cell of their kind, 0 when none counted. Goldens unchanged. |

New breakage: 0 Critical, 0 Important, 2 Minor, 4 Nit. Counts below.

## The four named checks

### 1. I1: the planted-name probe, and the world-file exemptions

- The review's plant (a `bully:` block with `display_name: Reuters`, plus `# lines from the Reuters wire`) now fails `test_no_real_names_in_configs`; `_config_hits` returns `['\\breuters\\b']` (`out-i1-hits.txt`). Planted at HEAD, the failing set (`out-i1-planted.txt`):
  - A block-style bully `display_name: Reuters` plus a comment: FAILS.
  - B flow-style bully `{..., display_name: Reuters}` plus a comment: FAILS.
  - C judge `display_name: Gemini` plus a comment: FAILS.
  - D the plant A, with `Reuters` also named in a second file: FAILS.
  - F no `display_name` at all, a comment naming Reuters: FAILS.
  - E a TARGET role with `display_name: Reuters` plus a comment: passes in its own file, by the review's own recommended rule (N3 below).
  - After cleanup the baseline passes again.
- `test_a_display_name_off_a_target_exempts_nothing` binds the fix: three mutants die (`_config_hits` spares the global `_display_names()`; `_target_names` also reads the bully role; `_display_names()` back to the regex harvest of every `display_name:`).
- World files, `out-i1-shipped.txt`:
  - Old `_display_names()` (every `display_name:` value in `configs/`) is `{claude}`. New is `{claude}`. Nothing in either direction.
  - 27 configs scanned, equal to the `*.yaml` count, no non-YAML file under `configs/`.
  - Two files carry a `# real-name-ok:` line in the whole tree (data, tests/fixtures, configs, claude_bully): `data/hypotheses.yaml` (`Claude`) and `data/personas/captor.yaml` (`claude`). Both are covered by the new set. The raw grep agrees.
  - So no shipped world or persona file fails, and no exemption ever covered a non-target name: the narrowing is prophylactic, as ASSUMED 9 says.

### 2. M4: does the resume rebuild the state exactly?

What the swallow path skips: `_recover` raises inside `after_target_call` (after `_adopt`, before `_remember`), so it never reaches `fold_server_ledger`, `_record_call`, `_record_authority` or its own `runtime.save()` (env_turn.py:691-700). The rewind then saves only if the private file changed.

Probes, `probe_m4_kill.py` (claude -p annex rep, 3 turns, fake claude through the real MCP server; the third target call fails; the run is then resumed in a fresh process-equivalent; compared with an undamaged twin):

- Matrix, `out-m4-kill.txt`: three failure families (rate limit before the call, rate limit after the server ran the turn's calls, hard kill after) times three damage lines (`[1, 2]`; a valid JSON object that is not a record; a closed-off torn fragment) times two logs (tools, authority). 18 damaged runs. Every one differs from its twin in nothing: per-turn calls, tool-call stream, authority stream, trigger records without the `resume` record, `env_state.json`, `attempt.json`, the server logs' ids. Only the `resume` record's drop counts differ (they include the damaged line, as they should). The kill family also equals the unbroken run.
- A kill at the swallow point, `out-m4-kill-in-recovery.txt`: damage plus a rate limit, then the process dies right after the `ValueError` is swallowed and before the rewind and its save (patched `rewind_private_file` raises once, only for the failed call). Both the pre-call and the post-call variants resume to exactly the unbroken run (differs in nothing against the kill control and against the unbroken run).
- The state fields the dead attempt changes, `out-m4-state-fields.txt`: turns whose calls write the `search_log` and `retry_counts` (blocked search, two reads of a 403 doc, a consult). In the kill-in-recovery case the state on disk at the kill holds 2 search lines, and after the resume the final state holds the unbroken run's 3. So `prime`'s rebuild from the written turns (`_replay_calls`) is what restores it, and it does so exactly. Not probed: the private-file (`write_file`) path of an idle cell; it rests on the same rebuild (`files` is a `CALL_FIELDS` field) and on `rewind_private_file`, which is unchanged.
- Non-vacuity: `out-m4-vacuity.txt` shows the first matrix compares real state (`watched_through`, layers) and logs; the second run adds the search log.
- The new slow test binds the fix: removing the swallow (`except ValueError` to `except OSError`) fails `test_a_damaged_log_never_hides_the_rate_limit_of_the_call` (`out-mutants-slow.txt`). The bare `raise` after the inner `try` re-raises the call's own error (the run exits with `RateLimitExit`), as the test shows.

Side effect (N1): the ledger fold is skipped too. See New findings.

### 3. M3: the store's generated stream stays raising. Right.

- The scoping is `closed_torn=log.parent == mcp_dir` (env_turn.py:421): only `mcp_dir/tools.jsonl` and `mcp_dir/authority.jsonl`.
- Why the MCP logs differ: a separate process, the server (a new one per `claude -p` call), appends with `_append_line` (mcp_server.py:156), which deliberately closes off a killed predecessor's fragment (P27). A mid-file fragment is therefore an expected artifact there. `torn_line` is the precise P27 rule (cut inside a string or token), not "any unparsable line".
- Why the store's streams differ: `RunStore._append` (store.py:249) is a single plain `write` that never closes off anything. "Atomic" is loose (a kill mid-write leaves a tail fragment), but what matters is that it never appends after one: a fragment can only be the last line, and `prime` runs `drop_dead_attempts` and `drop_uncommitted_generation` before any append of a resumed rep, which drop a torn last line. A mid-file fragment in a store stream can only be real damage (disk, hand edit), and tolerating it would silently lose a committed generated document from the served corpus. Raising is right, and `drop_uncommitted_generation` does not take `closed_torn` at all.
- `probe_m3_drop.py` (`out-m3-drop.txt`): with `closed_torn=True`, a fragment between two produced-turn lines is dropped with the dead turn's line and the produced lines stay (a); a fragment cut inside a multibyte character is dropped (d); a bare-word line (c) and garbage after a closed record (h) still raise and leave the file untouched. Without it (the store's own streams), the same fragment raises (b); a torn last line is dropped either way (e); the generated stream raises on a mid-file fragment (f).
- End to end, the matrix's `closed_torn` rows (live `_read_log` skips it by `torn_line`, then the resume drops it) complete for rate-limit and kill, pre and post.
- Test gap on the scoping: N2.

### 4. M1, M2, M5, M6

- **M1.** `mutate_m1_m2.py`, `out-mutants-m1-m2.txt`: each of the eight conjuncts of `_agrees` dropped in turn dies against `test_a_fire_whose_fields_disagree_is_refused`, including the review's three (written ignores rejection, cached ignores empty docs, error ignores docs). The consistent-fire test still passes.
- **M2.** `probe_m2_crossover.py`, `out-m2-crossover.txt`: 20 spans (the review's 18, plus the five line-break characters VT FF FS GS RS and curly quotes) and a span-less `CROSSOVER` render as one line and parse back exactly; the six escaped shapes together round-trip. Mutants: raw render dies, no-unescape (`_ESCAPED_FIELDS`) dies. The third (shape `_Q` back to `.*`) survives, and it is an equivalent mutant: the span is the line's last field, so a greedy `.*` parses a rendered line the same way. `AUTHORITY` stays raw, `DISCOVERY` title and `IDLE PROMPT` are listed as carried in HANDOFF, as the review allowed.
- **M5.** Message at runtime.py:802 and the test's regex agree; the only other mention of the old wording is the plan document. Mutant to the old wording dies.
- **M6.** Both writers now iterate `loaded.condition_cells()` (controls excluded, sorted, as before) filtered by `environment_of(...) is not None` or `is_poisoned_well_cell(...)`, and read `cells.get(cell, [])`. `cells` is built from complete reps of the same cells, so no cell that had a count lost it. `values_watch` still divides by a cell's reps and keeps counted cells only (unchanged). Goldens: the diff touches no file under `tests/fixtures`; neither golden (`plain_stub_smoke.json`, `plain_fixture_events.json`) holds `resumed_after_dead_attempt`, and both golden tests pass at HEAD (`test_plain_fixture_items_detect_exactly_what_they_did_before`, `test_plain_stub_run_analysis_is_byte_identical`), along with the three pre-existing pins on these maps. The two new tests die when each writer is mutated back to counted cells only.

## New findings in the fix diff

No Critical. No Important.

### Minor

**N1. The swallow path skips `fold_server_ledger`, against the Final-review M5 contract.** Location: `claude_bully/runner/env_turn.py:696` (`_recover` folds after `after_target_call`), reached through the swallow at `:676-683`.
- `test_a_failed_target_call_still_folds_the_servers_responder_lines` (tests/test_ledger.py) pins that a failed `claude -p` call's recovery folds the server's responder lines into the run's ledger. With a damaged log, `_recover` raises before the fold.
- Evidence, `out-m4-ledger.txt` (post-call variants, with the run's ledger active): the undamaged twin holds `responder@t5` at the pause; the damaged run does not, and one line sits unfolded in `mcp/ledger.jsonl`. After the resume's first recovery the final ledgers are equal in both the rate-limit and the kill family.
- Effect: the ledger undercounts the dead attempt's responder calls from the pause until a resume, and for good if the rep is never resumed. The report's concern 2 names only the skipped `runtime.save()`.
- Fix: call `fold_server_ledger(self.runtime.mcp_dir)` in the except branch (it parses nothing), and extend the slow test to read the run ledger at the pause.

**N2. The M3 scoping is not pinned at its call site, and the torn-line rule is not pinned on the resume reader.** Locations: `claude_bully/runner/env_turn.py:421`, `claude_bully/runner/store.py:130`.
- `closed_torn=True` for every log (the store's own tools and authority streams too) survives 17 tests in `test_runner_env.py` (`out-mutants-rest.txt`). The code is right (probe b raises); nothing fails if a later edit widens it.
- `closed_torn` dropping any unparsable mid-file line (the `torn_line` rule removed) survives the 4 tests selected for it. The code is right (probes c and h raise); no committed test feeds `drop_dead_attempts(closed_torn=True)` a bare-word or garbage-after-record line.
- Fix, test only: in `test_only_a_server_log_reads_a_closed_off_torn_line_as_torn`, add a bare-word mid-file line that raises with `closed_torn=True`, and one resume-level case where a store stream (`rep0.tools.jsonl`) holds a closed-off fragment and the resume raises.

### Nit

- **N3.** `_display_names()` is still a union over every config's targets, so a target `display_name: Reuters` in any config legitimises a world file's `# real-name-ok: Reuters` and passes the config scan (plant E). This is the review's own recommended rule ("the display names of `targets[*]`"), so not a regression; a later tightening could pin target display names to the `RoleConfig` default.
- **N4.** `DEFAULT_DISPLAY_NAME` in `_config_hits` (test_real_names.py) is unbound: removing it passes, since every config that names Claude also gives its target `display_name: Claude`. Equivalent today.
- **N5.** `_target_names` runs `yaml.safe_load` on every file `_scanned_configs()` returns, `.md` and `.txt` included. A prose file under `configs/` could raise a `YAMLError` (loud, not silent). None exists; all 27 are YAML.
- **N6.** A mid-file torn fragment from a live (non-dead) turn is now counted in the `resume` record's `dropped` and makes the resume record a redo turn; harmless and arguably informative.

## Probes (all under `probes-task14-rereview\`)

- `tree\`: `git archive` copy of a8a5578, with its own `.venv`; `tree\tests\test_probe_m4_kill.py` and `test_probe_m4_vacuity.py` are copies of the probes below.
- I1: `probe_i1_planted.py` (`out-i1-planted.txt`), `probe_i1_shipped.py` (`out-i1-shipped.txt`), `probe_i1_hits.py` (`out-i1-hits.txt`).
- M4: `probe_m4_kill.py` (three tests: the matrix `out-m4-kill.txt`; `kill_in_recovery` `out-m4-kill-in-recovery.txt`; state fields `out-m4-state-fields.txt`; the ledger `out-m4-ledger.txt`), `probe_m4_vacuity.py` (`out-m4-vacuity.txt`).
- M3: `probe_m3_drop.py` (`out-m3-drop.txt`).
- M2: `probe_m2_crossover.py` (`out-m2-crossover.txt`).
- Mutants: `mutate_m1_m2.py` (`out-mutants-m1-m2.txt`), `mutate_rest.py` (`out-mutants-rest.txt`, and `out-mutants-slow.txt` for the two slow tests; two lines of `out-mutants-rest.txt` are marked INVALID because the slow tests were deselected there, and the slow run supersedes them).
