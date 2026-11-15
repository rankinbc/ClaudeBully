# Task 7a report: the call primitive and stage 1

Status: DONE. Commit 81228be on 7efbebe (build/v1), authored rankinbc1@gmail.com. Not pushed.

Gate: 10596 passed, 11 skipped, 69 deselected (from 10567 and 10: the 27 tests of `tests/test_director_primitive.py` and 3 of `tests/test_bundle.py`, the new symlink test skipping without the privilege); slow 69 passed; both mypy runs clean. ruff format --check and ruff check clean; 0 warnings under `-W error`.

## What I implemented

- `claude_bully/planner/director.py` (new).
  - The brief's constants: `DIRECTOR_CACHE_VERSION`, `MAX_PLAN_CHARS`, `MIN_FILLER_SHARE`, `MAX_REPAIR_CALLS`, `ROLE_KEY_EXCLUDES`, `DOCS_DIR`. Also `DIRECTOR_CACHE` (`"director"`), `FAILED_TRANSCRIPTS` and `PLAN_TASK` (stage 1's task text).
  - `director_cache_key` (R-cache-key) and `conversation_id`.
  - `CallSpec`, `Answer`, `DirectorError`, `Checkpoint`.
  - `Director`, with `new`, `open`, `ask`, `run` and `plan`.
  - `ask` is the brief's code, with two additions (see the write order below): the context-limit refusal, and a grammar check of each output path before the commit.
  - `run` is the brief's code as given.
  - `_record_dead_attempt` follows R-marker: a marker is read once, and a dead attempt's ledger lines are dropped.
  - `_reopen_failed` follows the failed-stage ruling.
  - `_open_stage` refuses a stage name the record already holds (M1).
  - `_check_ceiling` counts every non-manual call in the stages and the rounds.
- `claude_bully/planner/bundle.py`.
  - `materialize` and `rematerialize_open_stage`, as the brief gives them. Both go through `_committed_texts`, which checks each text against the sha the call recorded (Task 1 review N5).
  - `remove_leftovers` (R-tmp).
  - `named_transcripts`.
  - `Bundle.move_transcript`, for the failed-stage move. It is idempotent after a kill.
  - M1: `write_manual` numbers a reopened stage's calls past every call recorded under that name, and refuses a transcript path that a call of the record already names.
  - M2: `index()` and `bundle_hash` walk the tree without following links (`_tree`). `index()` lists no file reached through a link. `bundle_hash` refuses a bundle that holds a link outside `HASH_EXCLUDES`. `hash_tree` is unchanged.
- `tests/fixtures/director_stub.py` (new).
  - `Crash`, `Kill`, `PlannerStub`, `ReviewerStub` (its replies are Task 8's), `StubFactory`, `REQUEST`, `comparable`, `hashed_files`, `cache_keys`, `run_plan`.
  - Every planner mode in the brief's table works: `off_contract`, `outside_grammar`, `repeated_path`, `no_config`, `fresh_small` (13 documents under `worlds/fresh/`, 6 filler), `lint_fail`, `close_fail`, `crlf`, `rate_limit`, `timeout`, `provider_error`. Each was probed for 7b.
  - A mode name the double does not know is refused.
- Docs-sync:
  - docs/00 section B: a paragraph on the statuses of `DirectorCall` and the shape of the transcript.
  - docs/00 section H: the Phase 5 line gains Task 7a (no record change).
  - docs/08 "Process": the record-before-file order (A3), the cache's home (A7), its key (R-cache-key), the rate-limit, error and context-limit rules, and stage 1.
  - The spec's "As planned": a Task 7a section.
  - HANDOFF: Phase 5 item 8.

## Tests

`tests/test_director_primitive.py` has 27 tests:

- The brief's 12 tests, verbatim (ruff only rewrapped their lines).
- 15 of mine:
  - ledger parity at K1, K4, K5 and K6 (4);
  - the one retry, with the failures in the message;
  - R-commit, killed after the record, plus an error call setting no field;
  - a cache hit that fails its check is a miss;
  - the call ceiling;
  - the context limit;
  - the reasoning text is written nowhere;
  - R-tmp;
  - rematerialize on an open stage and on a committed one;
  - materialize, and its sha refusal;
  - a stage is never opened twice;
  - `new` on a slug that holds another request is refused.

`tests/test_bundle.py` has 3 new tests:

- `test_index_and_bundle_hash_refuse_a_junction`. It runs on Windows. It also checks that a junction under `state/` does not make `bundle_hash` refuse.
- `test_index_and_bundle_hash_refuse_a_symlink`. It skips when there is no privilege, like the existing symlink test.
- `test_a_reopened_stage_name_never_overwrites_an_earlier_calls_transcript`.

RED:

- The brief's tests, at import, with `director.py` moved aside: `ModuleNotFoundError: No module named 'claude_bully.planner.director'`, 1 error during collection.
- M1 and M2, behavioral, run against the old `bundle.py` (`git stash`): 2 failed.
  - The junction test: `index()` listed `worlds/mini/corpus/a.md` and `worlds/mini/world.yaml` from outside the bundle.
  - The reopened-stage test: both calls named `transcripts/author-planner-0.json`.
- The 13 director-level and bundle-level tests I wrote after the primitive: RED by mutation. One line of the code was broken at a time and the covering test run; all 13 went RED.

| Mutation | Covering test |
| --- | --- |
| no ledger drop | ledger[K4] |
| no commit hook | R-commit |
| no context check | context limit |
| reasoning in the reply | reasoning |
| a cache hit not checked | cache-hit miss |
| `>` for `>=` in the ceiling | ceiling |
| a stage opened twice | M1 director |
| no failures in the retry message | retry |
| no leftover removal | R-tmp |
| no unowned removal | rematerialize |
| no sha check | materialize |
| R-marker order swapped | the brief's failed-stage test |
| no marker clear on a rate limit | the brief's rate-limit test |

GREEN: 27 passed in `tests/test_director_primitive.py`; `tests/test_bundle.py` 59 passed and 2 skipped (the two symlink tests). Every test is under 1 s (the slowest is 0.93 s), so none is marked slow.

## Files changed

- `claude_bully/planner/director.py` (new)
- `claude_bully/planner/bundle.py`
- `tests/fixtures/director_stub.py` (new)
- `tests/test_director_primitive.py` (new)
- `tests/test_bundle.py`
- `docs/00-RECONCILED.md`
- `docs/08-DIRECTOR.md`
- `docs/superpowers/specs/2026-11-14-phase-5-director-design.md`
- `HANDOFF.md`

## ASSUMED

- ASSUMED: a message over `MAX_CONTEXT_CHARS` is refused before it is sent. `ask` raises `DirectorError` naming the purpose, the length and the limit, after clearing the marker (nothing was sent, so no call is dead). Nothing is committed, and `run` fails the stage and the plan. Spec section 6 left this to 7a. It reads like section 13's "refused before the call" for `max_director_calls`.
- ASSUMED: a dead attempt's ledger lines are dropped at the resume (the carry). The rule is the Director's form of `AttemptMarker.written`: a line whose call never reached the record, which is the one the marker names at or past `len(calls)`. A rate limit's line stays, because D-rate-limit clears its marker first. A real call's cost dies with its dead attempt. That loss is narrow: only a K4-shaped kill (the call returned, killed before the record) writes such a line; a kill inside the call writes none.
- ASSUMED: a stage is opened once. `_open_stage` refuses a name the record already holds. The brief's code opens a new record whenever the last one is not this open stage, and a second record of a stage would number its calls from 0 over the first one's transcripts (M1). A resume reopens a failed stage in place. Task 9's validate replaces its record and `plan review` archives into `rounds`, so neither needs a second record. With this guard, a transcript check inside `ask` could never fire, so there is none.
- ASSUMED: for M1, `write_manual` takes the review's first fix (the index runs past every call of that stage name) and its second (refuse a transcript path already named). The refusal alone would have broken `tests/test_bundle_lints.py: _manifest_patches_a_second_base_file`, which reopens `author` on the good bundle.
- ASSUMED: `ask` checks each output path against the grammar before the commit, so a path the Bundle refuses never sits in a committed record that no resume could write.
- ASSUMED: `Director.new` on an existing slug compares `record.request` to the request. Equal continues the plan, and anything else is a `DirectorError` (spec section 4's `slug` row). Task 9 owns the CLI's wording.
- ASSUMED: after `_reopen_failed`, the plan's status is the status its last committed stage earned (`planned` when none is committed).
- ASSUMED: `REQUEST` spells out the good bundle's request (`bundle_fixtures._REQUEST`, which is private), the generator model `haiku` included. It does not import it.
- ASSUMED: `StubFactory` wraps each double in the active ledger, as `build_provider` does, so the plan's `ledger.jsonl` is written in tests and the ledger-parity test has lines to compare.
- ASSUMED: `outside_grammar` appends one `../escape.md` document to the good manifest. `fresh_small` lists the manifest's eight documents and then mini's own five, with every world path renamed `worlds/fresh/`.

## The call primitive's write order (`Director.ask`)

1. `_open_stage`: a new open `StageRecord` is written to `plan.json` unless the last record is this open stage. A stage name the record already holds is refused.
2. `_check_ceiling`: `DirectorError` naming `max_director_calls`. No marker has been written yet.
3. `.attempt.json` names `(stage, role, index)`, written atomically.
4. For attempt 1, then 2:
   - the message is built (the context builders only);
   - over `MAX_CONTEXT_CHARS`, the marker is cleared and `DirectorError` raised;
   - the key is computed and the cache read; a hit that passes its check is `cached` (a `note_cached` ledger line), and a hit that fails is a miss;
   - `reset_session(cid)`, then `complete`;
   - `RateLimitError`: the marker is cleared and `RateLimitExit` raised, with nothing committed;
   - `ProviderError` (a timeout among them): `error`, `provider_failed`, no retry;
   - the reply is checked; it passes as `fresh`, or the failures go into the retry's message.
5. The transcript: the system prompt's sha, the model and each attempt's message and reply. Then `checkpoint("transcript")`.
6. The outputs are normalized and each path checked against the grammar.
7. The commit: the `DirectorCall` is appended and `CallSpec.commit` applied when the call is not an error, then one `plan.json` write. Then `checkpoint("record")`.
8. The files are written, each atomically and LF. Then `checkpoint("files")`.
9. The cache put, for a `fresh` reply only.

The resume (`run`, at the first stage not committed):

1. `_record_dead_attempt`: when the marker names this stage at or past `len(calls)`, its ledger lines are dropped, it is appended to `resumed` and the record is written. The marker is cleared either way.
2. A `failed` stage is reopened in place: its last `error` call moves out and its transcript goes to `transcripts/failed/`.
3. `rematerialize_open_stage`: leftovers are removed; then the open stage's committed outputs are rewritten wherever they differ, and the grammar files nothing owns are removed.
4. The stage method goes on at `len(calls)` (`_done` skips a committed call).

## Kill points

| Point | Where | Test | What is checked |
| --- | --- | --- | --- |
| K1 | inside the plan call (`crash_at="plan"`) | `test_a_plan_killed_at_its_plan_call_resumes_byte_equal[K1]`, `test_a_killed_plan_calls_ledger_reads_as_an_unbroken_ones[K1]` | hashed files byte-equal; `comparable` equal; `resumed == [plan/planner/0]`; cache keys equal; ledger equal |
| K4 | after the transcript, before the record (`Kill("transcript", "plan")`) | `...[K4]` (both) | as K1; the call's `ok` ledger line was written and is dropped at the resume |
| K5 | after the record, before the file (`Kill("record", "plan")`) | `...[K5]` (both), `test_rematerializing_rewrites_the_open_stage_and_removes_what_nothing_owns`, `test_a_resume_removes_what_a_killed_write_atomic_left` | as K1 with `resumed == []`; the cache lacks exactly the one key; `plan.md` written from the transcript; leftovers removed |
| K6 | after the file, before the cache put (`Kill("files", "plan")`) | `...[K6]` (both) | as K5 |
| rate limit | inside the plan call (`rate_limit`) | `test_a_rate_limited_call_pauses_and_resumes_with_no_dead_attempt` | no marker; stage open with no call; `resumed == []`; `comparable` equal |
| provider error, then continue | inside the plan call (`provider_error`) | `test_continuing_a_failed_stage_records_no_dead_attempt` | `resumed == []`; the error's transcript under `failed/`; hashed files equal |

## Concerns

- The ledger drop keys on the call's index prefix (`plan/<slug>/<stage>/<role>/<index>/`). If a provider error at index i is continued, and the retry at index i is then killed after its call returned (K4), the resume also drops the earlier error call's line: a real call's trace leaves the ledger. It is narrow, but if the plan's ledger is to be a cost record, Task 9 or the controller may prefer to keep a dead attempt's lines and accept a ledger that differs from an unbroken plan's.
- `_record_dead_attempt` writes the record and then clears the marker. A process killed between the two records the same dead attempt twice on the next resume. The window is two writes. Clearing first would lose the attempt instead.
- `transcripts/failed/<stage>-<role>-<index>.json` is overwritten if the same call fails twice across two continues. The spec names that one path.
- `run(through=...)` past `plan` raises `AttributeError` until 7b to 9 define `author`, `review`, `revise` and `validate`. The default `through="validate"` therefore cannot run yet. The brief's code is kept as given.
- `run(stop_after_plan=True)` on a bundle whose plan stage is already committed goes on to stage 2, because the committed stage is skipped by `continue` before the stop check. This is the brief's code; Task 9's `plan new` without `--no-confirm` should check the case.
- `Director.say` is stored and not yet used. The manifest's call-count line is 7b's.

## Fix round 1

Commit be05ee5 on 81228be. Not pushed.

Gate: 10605 passed, 11 skipped, 69 deselected, 0 warnings (`-W error`; it was 10596 before this round, and the 9 new tests account for the difference); slow 69 passed; ruff format and ruff check clean; both mypy runs clean. Correction (review N4): in the first round, `tests/test_bundle.py` had 58 passed and 2 skipped, not 59 passed.

### What changed

- **C1.** A resumed call is now handled exactly as a fresh answer.
  - `Director._done` is replaced by `Director._call(stage, index, spec) -> Answer`. It asks when the stage has not reached the index. Otherwise it rebuilds the `Answer` from the committed call, re-reading the parsed reply from the transcript.
  - So `plan()` raises `DirectorError` for a committed `error` call, and the stage fails with the same `stage.error` as an unbroken run.
  - `DirectorCall.provider_failed` (default false, plan schema 1 unchanged) records what `Answer.provider_failed` said, so 7b's resumed document calls can still tell a provider error from two failed checks.
- **I1.** `DirectorAttempt.ledger_lines` (default 0) is the plan ledger's line count when the marker is written. `_drop_dead_lines` keeps `raw[:ledger_lines]` and drops only the call's lines after that point.
- **M1.** A dead attempt is appended only when it is not already the last entry of `resumed` (the runtime's `flagged` rule, `runner/env_turn.py:436`). The comparison includes `ledger_lines`, so two real deaths of the same call at different ledger positions remain two entries.
- **M2.** A retry over `MAX_CONTEXT_CHARS` now ends the call as an `error`. The error names the failures, the limit, and the fact that the retry was not sent. Attempt 1 is recorded in the transcript and the commit. A first attempt over the limit is still refused before the marker.
- **M3.** `Bundle.archive_failed_transcript` replaces `move_transcript`.
  - The first failure goes to `failed/<stage>-<role>-<index>.json`. Later failures go to `failed/<stage>-<role>-<index>-<n>.json`, n from 2. The transcript grammar admits that suffix under `failed/` only.
  - A source that is already gone means a move made before a kill, so nothing is moved.
  - Spec "As planned" is amended.
- **M4.** `run(stop_after_plan=True)` returns at a stage 1 that was committed before the run.
- **N1.** `run` raises `NotImplementedError("stage <s> is not built yet ...")` before touching the record.
- **N2.** The rate-limit line divergence from the dry-run rule is stated in the spec's "As planned".
- **N3.** No change. The marker left after stage 1 is harmless, as the review says.
- Docs: docs/00 sections B and H (the two new plan-schema fields), docs/08 Process (the retry limit), the spec's "As planned" (fix round 1), HANDOFF.

### Tests (9 new, `tests/test_director_primitive.py`)

- `test_a_plan_killed_after_its_error_call_commits_fails_as_an_unbroken_one[provider_error, check_twice]`. This is the review's reproduction, plus a two-failed-checks variant (`MAX_PLAN_CHARS` set to 10). The test compares:
  - the killed-and-resumed state with the unbroken state (`comparable`, hashed files, the ledger, `failed/` bytes);
  - the same again after a continue on both.
- `test_a_kill_in_a_continued_call_keeps_the_earlier_error_calls_ledger_line[K1, K4]`. The sequence is a provider error, a continue killed at K1 or K4, then a continue. The ledger must equal the unbroken `[error, ok]`.
- `test_a_dead_attempt_is_recorded_once_when_its_resume_dies_before_the_marker_clears`.
- `test_a_retry_over_the_context_limit_commits_the_attempt_that_was_sent`.
- `test_a_call_that_fails_across_two_continues_keeps_both_failed_transcripts`.
- `test_stop_after_plan_on_a_committed_plan_stops`.
- `test_a_stage_not_built_yet_is_refused_before_it_opens`.

RED on 81228be: all 9 failed, as follows.

- Both C1 cases failed on the new field, so I also re-ran them on 81228be with that one assertion removed. Each then failed on its behavior: `'planned' == 'failed'`.
- The two I1 cases: the ledger was `[ok]` against `[error, ok]`.
- M1: `resumed` held two entries.
- M2: `DirectorError ... nothing was sent`.
- M3: only `plan-planner-0.json` was kept.
- M4 and N1: `AttributeError: 'Director' object has no attribute 'author'`.

GREEN: `tests/test_director_primitive.py`, `tests/test_bundle.py` and `tests/test_plan_records.py` give 125 passed and 2 skipped (`timeout 300`).

### The review's kill sweeps, re-run on the fixed tree

- `sweep_kills.py`: 0 mismatches across all 5 scenarios (clean, retry, provider_error, timeout, rate_limit). Event 6 (C1) and events 11 to 13 (I1) now match the unbroken run. The probe still sees the failed-transcript move, through `bundle.replace`.
- `sweep_double_kills.py`: 149 pairs, of which the probe flags 3. All three are `provider_error` pairs `(3, 14|15|16)`:
  - In each, the first kill is the command-0 call at its marker, and the second is command 1's retry after the provider error.
  - So the same call index really died twice, at different ledger positions, and `resumed` records both. The probe counts any `resumed` longer than one as a mismatch.
  - The ledger, files, record and transcripts all equal the unbroken run's.
  - The `clean`-scenario duplicates the review found (M1) are gone.

### ASSUMED

- ASSUMED: I record `provider_failed` on `DirectorCall` rather than deriving it from the `error` text. It is an additive plan-schema field, and the review offered either option.
- ASSUMED: the M1 dedupe compares the whole marker, including `ledger_lines`, against the last `resumed` entry only (the review's `resumed[-1:]`). A marker read twice collapses into one entry, while two different deaths stay as two.
- ASSUMED: the first failed copy keeps the unnumbered name, so the brief's test and 7b's `failed/<name>.json` assertion stand. Numbering starts at 2.

### Concerns

- `_call` re-runs `spec.check` on a committed reply only to rebuild `parsed`, and ignores its failures. A 7b check that depends on the plan's state (for example the manifest's call budget) would then see a different state on a resume. Its parsed value is unaffected, because failures are discarded.
