# Task 7b review: stage 2, the author stage

Review of 3a1ef89..32d9acd (one commit, authored `rankinbc1@gmail.com`, trailer present). Read-only on the checkout; probes in `probes-task7b-review/` (under 100 KB). Disk 2.4 GB free before, 2.7 GB after.

## Verdicts

- **Spec verdict: meets the requirements but one.** Every brief test is present as written; the carries are built and their tests bite (probed in memory, below). The gap: resume parity fails at one stage-2 kill point the spec names (section 8, "every temp file `write_atomic` left beside a target when the process was killed outright"). A hard kill inside the write that opens stage 2 leaves a temp file that the resume never removes (I1).
- **Quality verdict: good, with fixes.** The parse split, the replay rule in `_close` and the D-copy keying are sound. I found no prompt text built outside `planner/context.py`, and no odd reply escapes the arrival check as an exception. Three record or check gaps are Minor.

Counts: Critical 0, Important 1, Minor 5, Notes 8.

## Findings

### Important

**I1. A hard kill inside stage 2's opening record write leaves `.plan.json.<8>.tmp` in the bundle for good.** `claude_bully/planner/director.py:732`: `run()` calls `rematerialize_open_stage`, and with it `remove_leftovers`, only when the stage already has a record (`if existing is not None:`). A kill inside the write that would create the author `StageRecord` (the write that now carries `inputs` and `edited`) leaves no record. The resume therefore skips the cleanup, and the temp file survives in the bundle root. `bundle_hash` covers it, since `HASH_EXCLUDES` names `plan.json` and not its temp. Probe `hard_kill_sweep.py clean 10`: `MISMATCH ['files', 'leftovers'] files-only-one-side=['.plan.json.4ogd1ikn.tmp']`. No later step of that run removes it. A later `plan continue` or `plan review` that does re-materialize removes it, after stage 5 has stamped `bundle_hash` over it. The implementer's sweep cannot see this case: it raises after each write completes, never inside one.
Fix: call `remove_leftovers(self.bundle)` at the top of each loop pass in `run()`, before `if existing is not None:` (or once at `run()` entry). Add a test that plants `.plan.json.abcdefgh.tmp` beside a planned bundle and asserts it is gone after `run(through="author")`. The same gap exists at `Director.new`'s first write (7a's K1), and this fix closes both.

### Minor

**M1. A torn plan-ledger line wedges every resume.** `claude_bully/planner/director.py:696` (`_drop_dead_lines`) validates every line after the marker's offset, so a half-written last line raises `ValidationError` out of `run()`. Every `plan continue` raises the same way. Probe `hard_kill_sweep.py clean 22` and `timeout_config 93`: `RESUME RAISED ... ValidationError: 1 validation error for LedgerLine ... EOF while parsing`. Stage 2's calls write these lines, but the code is 7a's primitive. A torn append needs a death inside one short `write`, or a full disk (the implementer's first sweep filled this disk).
Fix: in `_ledger_raw`, treat a final line with no trailing newline that does not parse as torn, and drop it. That is the Phase 4 rule (`mcp_server.torn_line`). Add a resume test over a ledger with a torn tail.

**M2. `inputs` and `edited` are recorded once, when stage 2 first opens, so the record can misstate which plan the stage read** (`director.py:602`, `_open_stage(adopt=True)` on a new record only). Probe `probe_inputs.py`:
- A, the designed recovery path: plan.md fails the scan, the owner puts the planner's bytes back, the plan continues. The record ends with `edited ['plan.md']` although plan.md now matches its committing call. `inputs[plan.md]` is the sha of the rejected text (`4b0365b70e2c`), which no call saw. The scan worked: no call saw the bad line.
- B: the owner edits plan.md during a rate-limit pause. On the resume, the manifest and the world sheet had seen the old plan and the 12 later calls see the edited one. The record says `edited []`, and `inputs` holds the pre-pause sha.

So, to the named question: a continue after a scan failure shows the fixed plan, as designed. A resume after a pause or a provider error shows an owner's mid-stage edit to the remaining file calls, which an unbroken run never does, and the record does not say so. Nothing reads `inputs` or `edited` yet (Task 9's `plan diff` and `plan review` will).
Fix: at each `author()` entry, compare plan.md's sha with `stage.inputs["plan.md"]`. With no call committed, re-record `inputs` and recompute `edited` in one write. With calls committed, refuse with `DirectorError` ("plan.md changed while stage 2 was open"), or at least add it to `edited`. Pin both cases with a test.

**M3. A document's front-matter `layer` is never checked against its manifest entry's** (`director.py:1064`, `_document_arrival` takes no entry). The manifest's floor and its `MIN_FILLER_SHARE` clause read the planner's labels. On content, stage 5 has only `layer_counts`, which warns, and `anchor_floor`, which counts documents. A fresh world can therefore reach `runnable` with any actual filler share.
Fix: pass the entry, and fail arrival when `doc.layer != entry.layer`. That is a closed set relation, so it meets the "closed by construction" constraint, and the retry names it.

**M4. `config.yaml`'s arrival passes an environment whose ladder the world lacks, under `triggered` gating** (`director.py:1088`). I confirmed the implementer's concern with `probe_missing_ladder.py`. With `ladder: nope` on the triggered environment the arrival check passes, and stage 5 `schema` fails `environment 'mini_triggered': world 'mini' has no ladder 'nope'`. On the scheduled environment `run --dry-run` itself refuses it. This conforms to spec section 7 step 5 (the arrival check is "the refusal `run --dry-run` would give"), but the plan then spends its review and revise calls before stage 5 fails it.
Fix: at arrival, run `bundle_lints._environments`' ladder-membership check (a set relation) beside `dry_run_refusals`.

**M5. The manifest's call budget is a lower bound** (`director.py:152` `REVIEW_CALLS = 3`, `director.py:985` `_budget_failures`). It leaves out corpus chunks past `REVIEW_CHUNK_DOCS` (25), repairs, revise calls and confirm calls. Grading the concern by effect: an undercount never refuses a valid plan. It can admit an over-budget one, which `_check_ceiling` then stops in stage 3 or 4 with the count. Spec section 13's "refused before the call" holds per call, though not per plan. The brief asks for "the three review calls", so the code follows the brief.
Fix: Task 8 replaces the constant with a count built from `review_groups`' chunking. For a fresh world that is `ceil(docs / REVIEW_CHUNK_DOCS)` corpus calls plus `lines` and `plan`. Record in "As planned" that repairs, revise and confirm calls are not counted.

### Notes

- **N1.** A hard kill inside a cache put leaves `_cache/director/.<key>.json.<8>.tmp`, and nothing removes it (`hard_kill_sweep.py clean 25`, `31`). `cache_keys` globs `*.json`, so the keys and parity are untouched; the file is litter in a git-ignored folder. Optional: sweep the cache folder's leftovers once per `run()`.
- **N2.** The close dead end (implementer concern 2): spec section 7 step 4 and section 13 say only that the stage fails with the failures listed, and promise no recovery. `plan continue` replays every committed call and fails identically at no call cost (`hard_kill_sweep.py still_fails`, unbroken `['cmd0:failed', 'cmd1:failed']`). Section 8 says an owner's hand fix to a file of the open stage is overwritten. Task 9's CLI should say this when it prints the failure: start a new plan, or a later `plan review` path.
- **N3.** A real-name hit in the plan.md scan copies the name into `plan.json` (`director.py:840` joins `r.message`, which is `holds a real name: '<match>'`). The owner clause carries no name. `plan.json` is not target-readable, and Task 12's `plans/` scan reads only checked-in bundles. For symmetry with the owner clause, consider leaving the span out of the stage error.
- **N4.** K7a's dead-attempt assertion checks only `attempt.stage == "author"` (`tests/test_director_author.py:345`). Pin `(stage, role, index)` to the repair's index, as the other points do.
- **N5.** `_field_errors` is duplicated (`director.py:305`, `bundle_lints.py:701`). Import one.
- **N6.** A dropped document's entry stays in `record.manifest`, although spec section 7 says it is "dropped from the manifest". The deviation is recorded in "As planned" and `manifest_complete` excuses it. Fine.
- **N7.** `_NAMED_DOCUMENT` maps `buried document 'x' is unreachable` to the buried document itself, which can fix that only by changing its layer, since a seam document's link is the fix. One repair, then the close fails the stage. Acceptable under "each failure names a file". A mapping to the world's seam documents would serve better.
- **N8.** A reused world the manifest lists no file of is never closed in stage 2, because `last` in `author()` spans manifest entries only. It is a shipped world, and stage 5 lints it. Fine.

## Named risks

### 1. The carries and their tests

| Carry | Test | Bites? (probe `mutplugin.py`, mutated in memory, checkout untouched) |
| --- | --- | --- |
| A resumed `parsed` and `provider_failed` equal the unbroken run's | `test_a_resumed_calls_parsed_reply_and_provider_failed_equal_an_unbroken_runs` [None, provider_error] | `MUT=parse_off` (`parse_manifest` None, so the resume reruns the check): 2 failed. Baseline 2 passed. |
| The frozen budget | the same test, at an exact budget of 18; `test_the_budget_counts_...` | `MUT=budget_lazy` (the budget read at check time) survives, 2 passed. That is expected: it is equivalent while the check never runs after its call commits. `MUT=budget_lazy_parse_off`: 2 failed. The freeze is pinned through the parse split. |
| The plan.md scan before any stage-2 call | `test_plan_md_with_a_denylist_hit_fails_stage_2_before_any_call_shows_it` | `MUT=scan_off`: 1 failed. Baseline 1 passed. |
| ... with the owner clause | the same test, owner case | `MUT=owner_off` (owner pattern never matches): 1 failed. The test also asserts that the owner's name is not in `plan.json`. |
| The `repair:` calls wired | `test_the_world_close_asks_one_repair_and_closes`, `test_a_close_that_still_fails_after_its_repair_fails_the_stage`, K7a, K7b | Read. The replay rule in `_close` (`director.py:1143`) is right: a committed `repair:` of the world is replayed, and any other committed call ends the close. |
| Replay from the committed call list | `_call` by index; `_close` replay | The sweep below: no mismatch from the replay in 20 kills. |

### 2. The implementer's concerns, graded by effect

| Concern | Effect | Grade |
| --- | --- | --- |
| `inputs` stale after a plan.md fix | A record misstatement (`edited` names a reverted file; `inputs` holds a sha no call saw). An edit made during a pause reaches the remaining calls, unrecorded | M2 |
| A close that still fails, fails forever | Spec-conformant: no recovery path is promised. A continue costs no calls | N2 |
| Front-matter layer not checked | The filler-share floor is enforced on labels only | M3 |
| `REVIEW_CALLS = 3` | Never refuses a valid plan; can admit an over-budget one, which `_check_ceiling` stops mid-stage | M5 |
| The dry run passes a missing ladder under `triggered` | Confirmed; caught only at stage 5, after the review calls | M4 |

### 3. The kill sweep

The implementer's table kills after each completed write in 7 scenarios. Its event model (every `write_atomic`, ledger append, marker clear, `remove_file`, move) agrees with the write sites in `bundle.py` and `director.py`; I found no `write_text` or `os.replace` outside it. The kill points it does not list are the ones inside a write. I killed at 20 of them, each a hard kill:
- inside `write_atomic`: the temp written half, no rename, no cleanup;
- inside `Ledger.write`: a torn line with no newline.

The 20 points span three scenarios, two of them not in the implementer's table (`still_fails`, `timeout_config`). Each kill root was deleted after reading.

| Scenario | Kills (event index: write) | Result |
| --- | --- | --- |
| clean | 10 author open `plan.json`; 14 copy file; 20 copy record; 22 manifest ledger line; 24 manifest commit; 25 manifest cache put; 30 sheet file; 31 sheet cache put; 96 `config.yaml`; 104 stage commit | 10 and 22 fail (I1, M1); 25 and 31 leave cache litter (N1); 6 equal |
| still_fails (close fails after its repair, then a continue) | 88 repair transcript; 89 repair commit; 90 repaired file; 92 `_fail` write; 93 reopen write | 5 equal |
| timeout_config (timeout on `config.yaml`, then a continue) | 93 timeout ledger line; 94 error transcript; 95 error commit; 96 `_fail` write; 97 reopen write | 93 fails (M1). 94 and 95 equal a clean run (the dead error call is redone on a double that raises once; `--vs-clean`). 96 and 97 equal |

Totals: 20 kills. 3 resume failures (I1, M1 twice), 2 cache-litter cases, 15 byte-equal. `tests/test_director_author.py -k killed_in_stage_2`: 11 passed.

### 4. Every message through `planner/context.py`

`grep` over `claude_bully/planner/`: the Director has one `provider.complete` (`director.py:495`). Its message is always `spec.message(failures)`, and all three `CallSpec`s build it with `_planner_message`, which calls `context.planner_message`. `MANIFEST_TASK`, `file_task` and `repair_task` are the `TaskPart` text, scrubbed with the fix list by `scrub(_task(task))` (`context.py:649`). The only other `complete` is the pre-existing `llm_lint.py:208`, which is no Director call. Clean.

## Probes

All under `probes-task7b-review/`. Each probe writes only under a `TemporaryDirectory`, or mutates in memory.

| Probe | What | Output |
| --- | --- | --- |
| `hard_kill_sweep.py` | Hard kills inside a write; `--list` prints the write log | `list_*.out`, `hard_clean.out`, `hard_still_fails.out`, `hard_timeout_config.out`, `hard_timeout_config_vs_clean.out` |
| `mutplugin.py` | A pytest plugin: `MUT=<name>` breaks one carry in memory | `mutations.out` |
| `probe_arrival.py` | 17 odd contents for each of 6 kinds through `_check_file` | `probe_arrival.out`: 0 escaped, every one refused |
| `probe_inputs.py` | The stale-inputs cases A and B | `probe_inputs.out` |
| `probe_missing_ladder.py` | A missing ladder at the config's arrival and at stage 5 `schema` | `probe_missing_ladder.out` |

Tests run: `tests/test_director_author.py -m "not slow" -W error`, 22 passed; `-m slow -k killed_in_stage_2`, 11 passed. The full suite was not re-run.
