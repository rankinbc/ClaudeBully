# Task 7a re-review, round 1: fix round 1 (81228be..be05ee5)

I read the fix diff once (`review-81228be..be05ee5.diff`), then the code it changes at head be05ee5 and the review's probes. The checkout was not modified. Probes are in `probes-task7a-rereview/` (the review's three, copied and re-run, plus five of mine). Test runs: `tests/test_director_primitive.py`, `tests/test_bundle.py` and `tests/test_plan_records.py` give 125 passed, 2 skipped (`-o faulthandler_timeout=60`, `timeout 300`); ruff check, ruff format --check and mypy on `planner/{director,bundle,records}.py` are clean. I did not re-run the full gate (10605).

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| C1 (kill between an error call's commit and `_fail`) | **Fixed** | `focused.py` P1 and `c1_exact.py`: the resumed plan ends `failed`, no `plan.md`, with the unbroken run's `stage.error`, record, files, ledger and `failed/`. After a continue on both, the two are equal again. Held for a provider error, a timeout and two failed checks. |
| I1 (dead lines dropped by call index) | **Fixed** | `focused.py` P2, K4 and K1: the ledger ends `[error, ok]`, equal to the unbroken `[error, ok]`; files, record and transcripts equal. The offset also holds under persistent failures (below). |
| M1 (one dead attempt recorded twice) | **Fixed** | P3: `resumed` is one entry; files, record and ledger equal. See the counting caveat in N-1. |
| M2 (retry over `MAX_CONTEXT_CHARS`) | **Fixed** | P5: an `error` call with `attempts=1`, its transcript written, its `ok` line owned by the committed call; the error names the failures, the limit and "the retry was not sent". |
| M3 (`failed/` overwritten) | **Fixed** | `failed/plan-planner-0.json`, then `-2`, `-3`; the grammar admits the suffix under `failed/` only; a source already gone moves nothing. Two failures across two continues keep both, under every single and double kill of the persistent sweeps. |
| M4 (`stop_after_plan` on a committed plan) | **Fixed** | `run` returns at a committed stage 1 before the stage-not-built check. |
| N1 (`AttributeError` past `plan`) | **Fixed** | P7: `NotImplementedError: stage author is not built yet (Tasks 7b to 9)`, record untouched. |
| N2 (rate-limit line) | **Accepted** | stated in the spec's "As planned" (docs only). |
| N3 (marker after stage 1) | **Accepted** | no change, as the review said. |
| N4 (report test count) | **Accepted** | corrected in the report. |

Counts: Critical 0, Important 0, Minor 1 (a carry to 7b), Nit 1.

### The new tests bite

I applied each mutation to a scratch copy of be05ee5 (`git archive`, outside the repo) and ran `tests/test_director_primitive.py` (36 tests):

| Mutation | Result |
| --- | --- |
| a resumed `error` call returns as `fresh` (C1) | both C1 cases fail |
| `_drop_dead_lines` by index prefix only (I1) | K1 and K4 fail |
| no `attempt not in resumed[-1:]` dedupe (M1) | the M1 test fails |
| a retry over the limit raises (M2) | the M2 test fails |
| `archive_failed_transcript` overwrites (M3) | the M3 test fails |
| `stop_after_plan` skipped on a committed stage (M4) | the M4 test fails |
| no `NotImplementedError` (N1) | the N1 test fails |
| resumed `Answer.provider_failed` forced to False | **36 passed: nothing pins it** |
| resumed `Answer.parsed` forced to None | **36 passed: nothing pins it** |

The last two do not matter for stage 1, which ignores both. They matter to 7b (item 4 below).

## Kill sweeps, re-run on the fixed tree

**The review's sweeps** (`sweep_kills.py`, `sweep_double_kills.py`):
- Single kills: 64 write boundaries over 5 scenarios (clean 9, retry 9, provider_error 17, timeout 17, rate_limit 12). **0 mismatches.** Events 6 (C1) and 11 to 13 (I1) now read `== unbroken`.
- Double kills: clean 51 pairs, 0 flagged; provider_error 149 pairs, **3 flagged, the same three the fixer named**: (3, 14), (3, 15), (3, 16).
- The three pairs (`pair_3_14.py`): event 3 is command 0's marker (K1), so the call is redone and fails, as the unbroken command 0 does. Command 1 continues, and the kill is in its retry (marker, ledger line or transcript). `resumed` is `[(index 0, ledger_lines 0), (index 0, ledger_lines 1)]`. Files, record, ledger, transcripts and status all equal the unbroken run's; only `resumed` differs.

**Is a two-entry `resumed` correct for two real deaths? Yes.** The call at index 0 died twice, once in each command, at different ledger positions, and each entry names one of them. Parity excludes `resumed`, and the spec's "names the one dead call" describes the single-kill case.

**Persistent failures (my sweep, `sweep_persistent.py`).** The review's error doubles fire once, so a call killed after its error and then redone succeeded ("== clean"). I added doubles whose failure persists over two commands and ends in a third that succeeds (a provider error every time, `perr3`; a plan over `MAX_PLAN_CHARS` on both attempts, `check3`, which puts `a1` and `a2` lines in the ledger). A redone call reproduces its error here, so the offset, the `failed/` numbering and the C1 re-raise are all exercised after kills.

| Sweep | Kill sets | Mismatches (files, record, ledger, transcripts incl. `failed/`, cache, status) |
| --- | --- | --- |
| perr3, single (25 events) | 25 | 0 |
| check3, single (27 events) | 27 | 0 |
| perr3, double | 343 | 0 |
| check3, double | 408 | 0 |

- `resumed` held more than one entry in 27 perr3 and 40 check3 double sets, always for deaths at different ledger offsets.
- The probe first reported 2 "mismatches" per single sweep, both at the write that fails a plan. That was the probe's model: after a kill on that write, re-running the command is a further `continue`, and with a persistent failure a further error is the correct result. The probe now treats a kill inside `_fail` as the command's end. Not a code defect.

## Item 3 in full: the dedupe's granularity

- The dedupe compares the whole marker with the last `resumed` entry, so it counts distinct (index, ledger offset) points of death, not deaths.
- `collapse.py`, clean scenario: kills (3, 4) are one real death plus the resume's own kill, so one entry, which is right. Kills (3, 6) and (3, 7) are two real deaths of call 0 at the same offset (the redo dies at its marker, or after its ledger line), so also one entry.
- This matches the runtime, whose `flagged` rule is coarser still (one record per redo turn). It has no parity effect, but the fix report's "two real deaths of the same call remain two entries" is true only for different offsets.

## Item 4: `spec.check` on resume

- **It cannot hide a failure that an unbroken run would raise.** A committed non-error call passed its check once, at call time, and the unbroken path never checks it again. So a resumed `_call` cannot soften or lose a failure.
- **What it can change is `parsed`.** `check_and_field.py`: a manifest-shaped check that counts the calls made so far and returns `(None, failures)` when over budget. Fresh, `parsed` is the manifest (made = 0 when it runs). Resumed, the manifest call is committed (made = 1), the check fails, and `_call` returns `parsed = None`: `parsed equal: False`. A check that returns `(data, failures)` regardless gives equal values. 7a's `plan()` ignores `parsed`, so 7a is correct.
- A check that raises on the changed state would also crash a resume rather than fail it.

**What Task 7b must do** (carry to the 7b brief):
1. **Make the resumed path state-free.** Add a pure `CallSpec.parse(reply) -> parsed`, used alone by `_call` on a committed call. State-dependent validation stays on the fresh path. If the split is too heavy, the contract is that `check` returns the same `parsed` whether or not a state failure arises, and `_call` refuses a non-error call whose rebuilt `parsed` is None.
2. **Manifest call budget: freeze the state as of the call.** Compute "calls made before this call" from the record prefix (earlier stages plus `stage.calls[:index]`), never from `len(stage.calls)`, `_check_ceiling()` or a counter inside `check`. Also re-assert once in the stage method, after the manifest `_call`, that calls made plus calls still owed (manifest entries with no committed call) is at most `max_director_calls`. Both paths run that line, a failure is a `DirectorError`, and the sum does not change as calls commit, so a replay gets the same answer.
3. **Do not re-decide from live state while replaying.** The world close and its repair calls depend on the documents present, and `rematerialize_open_stage` writes every committed file first. A replayed close sees more documents than the original did and can skip a repair the original issued. Then `_call`'s purpose guard fails the resume with "call j is 'repair:x', not 'file:y'". That fails loudly, which is right, but it is a failure the unbroken run did not have. Drive the replay from the committed call list, or run each close over the documents committed before that call's index.
4. **Pin it with tests.** At every committed-call boundary of a 7b stage, assert that the resumed `Answer` equals the fresh one in `parsed` and `provider_failed`, plus a mutation whose check reads `len(stage.calls)`. Both mutations above survive today.
5. **`provider_failed` is for 7b's branch.** A file call that fails twice drops its document and one that hits a provider error fails the stage; both must read `answer.provider_failed` from `_call`, so a resume branches as the fresh run did.

## Item 5: `provider_failed`

`check_and_field.py`: `DirectorCall.provider_failed` defaults to False; a dumped call carries the key; a call without the key (an older plan.json) loads as False; True round-trips; a real provider error and a timeout write True to `plan.json`, and a reopened record equals the one on disk. `DirectorAttempt.ledger_lines` behaves the same (default 0, an older marker loads as 0, which reproduces the earlier index-only drop; 3 round-trips). `PLAN_SCHEMA_VERSION` is still 1. The change is additive for reading older files only: `_Strict` is `extra="forbid"`, so code from before the fix refuses a plan.json that holds the new key. No shipped consumer exists yet.

## New breakage

None found. Checked: the new `_TRANSCRIPT` grammar (`failed/<stem>-<n>.json`, n from 2) against every `transcripts` user in `planner/`; the `NotImplementedError` check placed after the committed-stage skip, so `stop_after_plan` and a committed stage 1 still return first; the M2 error call's key and attempts; the sweeps above, which include every kill the fix can reach.

Findings:
- **R-1 (Minor, a carry to 7b).** Item 4: no test pins a resumed `Answer`'s `parsed` or `provider_failed`, and a state-dependent `check` can change `parsed` on resume. 7a is correct for stage 1; the 7b recommendations above close it.
- **N-1 (Nit).** The `resumed` count is of distinct (index, ledger offset) points; two deaths at the same offset read as one. The fix report's wording should say so; no parity effect.

## Probes (`probes-task7a-rereview/`, run from the repo root with `uv run python <file>`; each writes only under a TemporaryDirectory)

| Probe | What it does | Output |
| --- | --- | --- |
| `sweep_kills.py`, `sweep_double_kills.py`, `focused.py` | the review's probes, copied and re-run on be05ee5 | `sweep_kills.out`, `sweep_double_kills.out`, `focused.out` |
| `c1_exact.py` | C1 reproduction compared with the unbroken run, then both continued (provider error, timeout, two failed checks) | `c1_exact.out` |
| `sweep_persistent.py single\|double perr3\|check3 [lo hi]` | kill sweeps with failures that do not fire once | `persistent_single_*.out`, `pd_perr3_*.out`, `pd_check3_*.out` |
| `pair_3_14.py` | the three flagged double-kill pairs, event by event | `pair_3_14.out` |
| `collapse.py` | two deaths at the same ledger offset read as one `resumed` entry | `collapse.out` |
| `check_and_field.py` | items 4 and 5: `parsed` rebuilt under a state-dependent check; `provider_failed` and `ledger_lines` defaults and round trips | `check_and_field.out` |

The mutation runs used a scratch copy of be05ee5 outside the repo; no script for them is kept here.
