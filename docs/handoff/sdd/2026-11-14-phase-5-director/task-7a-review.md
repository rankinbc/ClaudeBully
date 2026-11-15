# Task 7a review: the call primitive and stage 1

Base 7efbebe, head 81228be. I read the diff once and the code outside it only for the named risks (`runtime.AttemptMarker`, `runner/env_turn.py` resume, `planner/dryrun._drop_dead_lines`, `providers/ledger.LedgerProvider`, `context.planner_message`). The checkout was not modified. My probes are in `probes-task7a/`. Test runs: `tests/test_director_primitive.py` (27 passed), `tests/test_bundle.py` (58 passed, 2 skipped; the report says 59), ruff check and format on the touched files (clean). I did not re-run the full gate.

## Verdicts

- **Spec verdict: Changes required.** The brief's K1 and K4 to K6 tests pass, and my sweep confirms them on a clean plan call. Two binding points still fail at kill points the code has but does not test:
  - Resume parity breaks when the process is killed after an `error` call commits. The plan ends `planned`, with no `plan.md` (C1).
  - The ledger is not equal to an unbroken run's after a failed stage is continued (I1).
  - Everything else holds. A rate limit records no dead attempt. No real model call is made. Every message goes through Task 6's builders. M2 is fixed as the Task 1 review asked. The context-limit refusal is decided and recorded.
- **Quality verdict: Changes required.** The primitive follows spec section 8's order faithfully, and the bundle helpers are careful. The gap is in the resume logic: it treats any committed call as done, and it identifies a dead attempt's ledger lines by call index, which the failed-stage ruling reuses.

Counts: 1 Critical, 1 Important, 4 Minor, 4 Nits.

## Findings

### Critical

**C1. A kill between an `error` call's commit and `_fail` commits the failed stage: the plan resumes to `planned` with no `plan.md`.** `claude_bully/planner/director.py:515-530` (`plan`), with `_done` at `:389-399` and `run` at `:479-484`.
- How it happens:
  1. For an error, `ask` commits the `error` call (`write_record`, `:331`) and returns.
  2. `plan` raises `DirectorError`.
  3. `run` writes the failure in a second `plan.json` write (`_fail`, `:407-414`).
  4. A kill between steps 1 and 3 leaves the stage `open`, holding the `error` call.
  5. On resume, `_record_dead_attempt` sees that the marker's index (0) is below `len(calls)` (1), so it only clears the marker. `_reopen_failed` does not run, because the stage is `open`, not `failed`.
  6. `plan()` then calls `_done(stage, 0, "plan")`, gets the `error` call back, skips the ask, and runs `_commit_stage`.
- Reproduced with the shipped helpers, `run_plan(..., modes={"plan": "provider_error"}, kill=Kill("record", "plan"))` (probe `focused.py` P1). The result is plan `planned`, stage `committed`, `calls == [error]`, and `plan.md` missing. The unbroken run of the same command ends `failed`/`failed`.
- The sweep finds it at event 6 of both the `provider_error` and `timeout` scenarios, and in 5 double-kill pairs.
- This is K5 on an error call. Task 7b's multi-call stages would inherit it: `_done` would skip a committed `error` file call as if it had succeeded.
- Fix: a stage method must treat a committed call exactly as it treats a fresh answer. For example: `call = done if (done := self._done(stage, 0, "plan")) is not None else self.ask(spec).call`, then `if call.status == "error": raise DirectorError(f"the plan call failed: {call.error}")`.
  - The resumed command then ends `failed` with the same `stage.error` string as the unbroken one, and the next `continue` reopens the stage.
  - `Answer.provider_failed` cannot be rebuilt from a committed call. Either derive it from `DirectorCall.error` (for example, the `ProviderError`/`ProviderTimeoutError` prefix) or record it on the call, so 7b's resumed branch can see it.
- Add a test: K5 on an error call (`provider_error`, and a double check failure), killed at `record`, resumed, and diffed against the unbroken failed-then-continued run.

### Important

**I1. Dead-attempt ledger lines are dropped by call index. After a failed stage is continued, the earlier error call's real line is dropped too. This happens at K1 as well as K4.** `director.py:429-445` (prefix at `:437`).
- Reproduced in probe `focused.py` P2 and in `sweep_kills.py` events 11 to 13 of `provider_error` and `timeout`:
  - Command 1 hits a provider error. Command 2 (continue) is killed inside the retried call. Command 3 continues.
  - The ledger ends `[0/a1 ok]`. The unbroken two-command run's ledger is `[0/a1 error, 0/a1 ok]`.
  - Records, hashed files and transcripts are equal; only the ledger differs.
- The report says only "a K4-shaped kill" is affected. In fact a kill right after the marker write (K1, where the dead attempt wrote no line) also drops the earlier error line, because the drop matches every line under `plan/<slug>/plan/planner/0/`.
- Effect: the plan's ledger is short by one real call, compared with the unbroken run. That breaks the binding "ledger equal to an unbroken run" point for the reachable sequence error or timeout, `continue`, kill. Cost is unaffected: error lines carry `cost_usd: None`. The call count and latency are wrong.
- Why the rule fails: the runtime's `AttemptMarker` names "the newest provider call", and `written()` judges only that call against the records. Task 5's `_drop_dead_lines` drops a line only when no written record owns it. Both rules rely on a turn index that is never reused. The Director's failed-stage ruling does reuse an index: the error call is popped, and the retry takes the same index and the same `a1` conversation id. So an index prefix cannot tell the newest attempt from the moved-out one.
- Fix, matching both rules: let the marker name the newest call's lines exactly.
  - Add a default-valued field to `DirectorAttempt`: `ledger_lines: int = 0`. This is an additive change, so `PLAN_SCHEMA_VERSION` stays 1.
  - `ask` sets it to the ledger's line count when it writes the marker.
  - `_drop_dead_lines` keeps lines `[:ledger_lines]` and drops only the later lines with the call's prefix.
  - Add the `provider_error`, `continue`, K1 and K4 sequence to `test_a_killed_plan_calls_ledger_reads_as_an_unbroken_ones`.

### Minor

**M1. A kill between the resume's `resumed` write and its marker clear records the same dead attempt twice.** `director.py:423-427`.
- Reproduced in probe P3 (K4, then a kill inside `clear_attempt`). `resumed` ends `[plan/planner/0, plan/planner/0]`.
- Hashed files, `comparable`, the ledger and the cache are all equal to a clean run's. The second ledger drop finds nothing to drop. The double-kill sweep shows `resumed` as the only difference in all 12 mismatched `clean` pairs.
- Effect: only `resumed`, which parity excludes. Spec section 15 does expect it to name "the one dead call", so Task 9's CLI suite would see two entries.
- Fix: use the runtime's dedupe. `env_turn.py` appends a `ResumeRecord` only when none is `flagged` for that redo turn. Here, append only when `attempt not in self.record.resumed[-1:]`. Clearing the marker before writing the record is the wrong fix: it loses the attempt instead. The dedupe also collapses a genuine second death of the same call into one entry, which is what the runtime does.

**M2. A context-limit refusal on attempt 2 discards the call that was sent on attempt 1.** `director.py:264-271`.
- The limit check runs inside the attempt loop. When attempt 1's reply fails its check and the retry's message, which adds the failures, goes over `MAX_CONTEXT_CHARS`, `ask` clears the marker and raises.
- Probe P5 shows the result: attempt 1 was sent, and its `ok` ledger line stays. No transcript and no `DirectorCall` record it, and no dead attempt is recorded.
- The error text also says "nothing was sent", which is false here.
- This is the reverse of Task 5's rule: the ledger holds a line that no record owns. The window is narrow, since attempt 1 must be within the failure text's length of 300,000.
- Fix: on attempt 2, treat over-limit as an `error` outcome. Set `error` to the limit message and `break`, so the normal transcript and commit path records attempt 1. Keep the raise-before-marker form for attempt 1 only.

**M3. `transcripts/failed/<stage>-<role>-<index>.json` is overwritten when the same call fails twice across two continues, so a transcript is lost (carry M1 in letter).** `director.py:453-455`, `bundle.py:301-309`.
- Probe P6 runs two blank-reply failures. `failed/` keeps only the second failure's replies, and the first failure's replies are no longer anywhere in `transcripts/`.
- The report flags this, and the spec does name that one path.
- For a `ProviderError` the transcripts are byte-identical (no attempts), so nothing is lost there. For a check failure, the owner's evidence goes.
- Fix: number the failed copies (`failed/<stage>-<role>-<index>-<n>.json`, with n past every existing copy), and amend the spec's "As planned" entry. Alternatively, have `move_transcript` refuse an existing target.

**M4. `run(stop_after_plan=True)` on an already committed plan goes on to stage 2.** `director.py:470-472`, `:486`.
- The `continue` for a committed stage skips the stop check. Probe P7 shows `AttributeError: 'Director' object has no attribute 'author'` today. After 7b lands, `plan new` on an existing slug without `--no-confirm` would author without the owner's confirmation.
- This is the brief's code, and the report flags it.
- Fix: move the stop check before the `continue`, or leave it to Task 9 with a test. Either way, carry it to Task 9 by name.

### Nits

- **N1. `run()` past `plan` raises `AttributeError`** (`director.py:480`; probe P7). No user can reach it today: nothing under `claude_bully/` imports `planner.director`, and the CLI has no `plan` sub-app until Task 9. The default `through="validate"` is still a trap for 7b's tests. A `NotImplementedError` naming the stage, raised before `_open_stage`, would be clearer until 7b to 9 land. No record is corrupted: `record.stages` stays `['plan']`.
- **N2. Rate-limit ledger lines.** A rate limit's `rate_limit` line stays in the plan's ledger (`director.py:433`). Task 5's dry-run rule drops it ("A rate limit's line goes the same way"). Keeping it is defensible: D-rate-limit makes the pause no dead attempt, and the line is a real event. The divergence should be stated in docs/08 or the spec's "As planned", since the carry says "use the same rule".
- **N3. The marker after stage 1.** After stage 1 commits, `.attempt.json` still names `plan/planner/0`; the brief clears it only at stage 5. That is harmless, since the next stage's resume clears a marker for another stage. A resumed run has no marker where an unbroken one has one, but `.attempt.json` is in `HASH_EXCLUDES`.
- **N4. Report test count.** The report counts `tests/test_bundle.py` as 59 passed and 2 skipped; I get 58 passed and 2 skipped.

## Named risks, answered

1. **The implementer's two resume concerns.**
   - Ledger drop by index: confirmed and graded Important (I1). It is wider than reported, because K1 triggers it as well as K4. Fix: the marker records the ledger offset.
   - Double record: confirmed and graded Minor (M1). It changes only `resumed`; every count and file stays the same. Fix: the runtime's `flagged` dedupe.
2. **Kill points beyond the tests.** See the sweep below.
   - Every boundary of a clean call and a retried call matches the unbroken run.
   - Two classes mismatch: C1 (event 6 in the error scenarios) and I1 (events 11 to 13).
   - The double-kill sweep adds M1, and nothing else that the single-kill rows do not already explain.
3. **`MAX_CONTEXT_CHARS` refusal.** Probe P4:
   - It fails before sending, with no ledger line, no transcript and no marker. The stage and the plan are `failed`, with the error in `stage.error`.
   - This matches spec section 13's "refused before the call" row, as the "As planned" entry records it. No `DirectorCall` is recorded, which differs from a provider error's `error` call; that difference is the stated ruling.
   - A `continue` with nothing changed fails again cleanly: still one stage record, nothing in `resumed`.
   - With the limit lifted, the plan resumes to `planned`, with files equal to a clean run's. `comparable` differs only in the kept `stage.error`, which the failed-stage ruling requires.
   - The one defect is attempt 2 (M2).
4. **The carries.**
   - M1: `_open_stage` refuses a reopened stage name, and `write_manual` numbers past the existing calls and refuses a named transcript. Both are tested. The `failed/` overwrite (M3) is the remaining case.
   - M2: `index()` skips links and `bundle_hash` refuses them, which is exactly the Task 1 review's fix. `hash_tree` is unchanged. A junction test runs on Windows.
   - `all_strategies`: the Director does not read it, so nothing is copied. The context builders use `listed_strategies` (`context.py:456`).
   - Builders: the only `Message(` is `director.py:290`, carrying `spec.message(failures)`. Stage 1's message is `context.planner_message(...)` with `TaskPart("plan", PLAN_TASK, failures)`, and its `## Task` part is scrubbed (`context.py:649`). `PLAN_TASK` is harness text, which is TaskPart's designed input. The one hand-built message is in a test (`_manifest_spec`), sent to a stub.
5. **`AttributeError` past `plan`.** No shipped CLI path reaches it (N1).

## Kill-point sweep

`sweep_kills.py` counts every durable write: each `write_atomic`, each ledger append, `clear_attempt`, `remove_file` and the transcript move. For each k it kills the process right after event k (with `Crash`, a `BaseException`) and re-runs the same command until it returns. It then compares the hashed files, `comparable(record)`, the ledger's (id, status) lines, the cache keys, every transcript's bytes (`failed/` included) and `resumed`.
- Parity allows three differences: `resumed` naming one dead call, a cache missing the one key a K5/K6 put lost, and the marker.
- "== clean" means the dead attempt was redone and the fire-once error double did not fire again, so the result matches a clean run. That is correct: the error never reached the record.

| Scenario | k | After event | Spec point | Result |
| --- | --- | --- | --- | --- |
| clean | 1 | `plan.json` (new) | before stage | parity |
| clean | 2 | `plan.json` (stage opened) | before K1 | parity |
| clean | 3 | `.attempt.json` | K1 | parity, `resumed` = [plan/planner/0] |
| clean | 4 | ledger `ok` | call returned, before transcript | parity, line dropped |
| clean | 5 | transcript | K4 | parity |
| clean | 6 | `plan.json` (commit) | K5 | parity, one cache key missing |
| clean | 7 | `plan.md` | K6 | parity, one cache key missing |
| clean | 8 | cache put | before stage commit | parity |
| clean | 9 | `plan.json` (stage committed) | K11 shape | parity |
| retry (`off_contract`, one retry) | 1-9 | as clean | K1, K4 to K6 | parity at all 9 |
| provider_error | 1-5 | up to the error transcript | K1, K4 | parity (== clean after the redo) |
| provider_error | 6 | `plan.json` (error call committed) | K5 on an error call | **MISMATCH (C1)**: plan `planned`, no `plan.md` |
| provider_error | 7 | `plan.json` (`_fail`) | between commands | parity |
| provider_error | 8 | `clear_attempt` (continue) | resume step | parity |
| provider_error | 9 | move to `failed/` | resume step | parity (the move is idempotent) |
| provider_error | 10 | `plan.json` (reopened) | resume step | parity |
| provider_error | 11 | `.attempt.json` (retry) | K1 after a continue | **MISMATCH (I1)**: ledger lacks the error line |
| provider_error | 12 | ledger `ok` (retry) | call returned | **MISMATCH (I1)** |
| provider_error | 13 | transcript (retry) | K4 after a continue | **MISMATCH (I1)** |
| provider_error | 14-17 | commit, file, put, stage | K5, K6, K11 | parity |
| timeout | 1-17 | as provider_error | as above | same results: C1 at 6, I1 at 11-13 |
| rate_limit | 1-3 | up to the marker | K1 | parity |
| rate_limit | 4 | ledger `rate_limit` | a kill before the pause clears | parity with clean (dead attempt) |
| rate_limit | 5 | `clear_attempt` (the pause) | the pause | parity, no dead attempt |
| rate_limit | 6-12 | the continued call | K1, K4 to K6, K11 | parity |

Double kills (`sweep_double_kills.py`):
- `clean`: 51 pairs, 12 mismatched, all of them `resumed` duplicates only (M1).
- `provider_error`: 141 pairs, 68 mismatched. Every one traces to C1, I1 or M1.

## Probes

All are in `probes-task7a/`. Run them from the repo root with `uv run python <path>`. Each writes only under a `TemporaryDirectory`.

| Probe | What it does | Output |
| --- | --- | --- |
| `sweep_kills.py` | Single kill at every write boundary across 5 scenarios (clean, retry, provider_error, timeout, rate_limit), resumed and diffed | `sweep_kills.out` |
| `sweep_double_kills.py` | Every pair of kills, the second inside the first one's resume | `sweep_double_kills.out` |
| `focused.py` | Seven probes, P1 to P7, one per finding | `focused.out` |

What each `focused.py` probe reproduces:
- P1: C1.
- P2: I1, at K4 and K1.
- P3: M1.
- P4: the context refusal, the continue, and the lifted limit.
- P5: M2.
- P6: M3.
- P7: N1 and M4.
