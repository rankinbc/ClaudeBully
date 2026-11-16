# Task 9 re-review, fix round 2 (9639ab8..6e90524)

Scoped to N1 (Important), N2 and R1 of task-9-rereview-round1.md and the fix diff. The checkout was left read-only (git status clean, HEAD 6e90524): bundles were built on the doubles under the session scratchpad and deleted; mutations are applied at import by a pytest plugin. Probes and outputs are in `probes-task9-rereview2/`. The full gate was not re-run.

## Verdicts

| Finding | Verdict |
| --- | --- |
| N1 `plan new` on a plan past stage 1 | FIXED. All seven statuses print and exit as claimed; the assumed exit 1 for an in-progress plan is coherent with the spec |
| N2 missing-path test and a long temp folder | FIXED |
| R1 damaged transcript, attempt marker, schema-invalid ledger line | FIXED for all three, as real processes, no traceback |
| Unfixed: missing transcript, empty-attempts transcript | Not reachable without a hand edit; each graded Note |

New findings: Critical 0, Important 0, Minor 0, Notes 5 (N-a to N-e below). No new breakage: the fix tests pass (19 selected, and 172 across `test_bundle`, `test_plan_records`, `test_store`, `test_director_primitive`, `test_plan_cli`).

## N1

`plan new` without `--no-confirm` on an existing slug, each status, `probes-task9-rereview2/test_n1_probes.py` (outputs `n1_probes.out`, `n1_probes_first.out`; CliRunner on the doubles; every case also asserts the record unchanged and 0 planner and 0 reviewer calls added):

| Status | How reached | Exit | Output |
| --- | --- | --- | --- |
| planned | fresh slug, and the same request again | 0 | `plan.md`, `stopped after stage 1: review <bundle>/plan.md, then run plan continue <bundle>`, `status planned` |
| authored | `run_plan(through="author")`; also a rate limit in stage 3 after a failed-then-fixed stage 2 | 1 | `plan new without --no-confirm runs stage 1 only; this plan stands at authored, so run plan continue <bundle>`, `status authored` |
| reviewed | `through="review"` | 1 | same line with `reviewed`, `status reviewed` |
| revised | `through="revise"` | 1 | same line with `revised`, `status revised` |
| validated, failing lints | good bundle, ladder line mutated, `plan validate` | 1 | the three `fail <lint_id> <doc_id>: <message>` lines (identical to `plan validate`'s own output), `status validated`; no stop message |
| runnable | good bundle, `plan validate` | 0 | the four cell lines, `status runnable` |
| failed (stage 2) | `file:config.yaml` off contract twice | 1 | `failed: stage author: the file:config.yaml call failed: ...`, `status failed` |
| failed (stage 5) | owner's name planted in a persona | 1 | `failed: stage validate: ... real_name_bundle: holds the owner's name`, `status failed` |

The fix's four tests pass; two mutations bite (`_finish` exits 0 for a mid-plan status: the authored test fails; `fail` lines dropped from the report: the validated test fails).

### The ASSUMED: an in-progress plan exits 1 with a "run plan continue" line

Coherent. The spec says it twice:

- Section 11: "Every subcommand prints one line per dry-run cell (...) and the plan's status. Exit code 1 when the plan is not runnable."
- D-exit (section 15): "`new`, `continue`, `review` and `validate` print one line per dry-run cell and `status <status>`, and exit 0 when the plan is `runnable` or when `new` stopped after stage 1 as asked; 1 for every other outcome; 3 for a rate limit the wait did not cover."

An authored, reviewed or revised plan is not runnable, and `new` ran no stage and stopped nothing "as asked" (the asked stop is stage 1's). So 1 is the literal reading, and it matches the `new` docstring (`Exit 0 runnable or stopped after stage 1 as asked, 1 not runnable, 3 rate limited`). Section 11's "on an existing slug with the same request it continues" is the `--no-confirm` path; without the flag the command is "stage 1 only", and the new line says so and names the way on. The old rule is gone from every doc (`git grep` for round 1's "whatever stage it stands at" and "neither runnable nor failed" finds nothing outside the ledger).

### Notes on N1

- **N-a (Note): a `planned` plan with stage 2 open still prints the stop and exits 0.** Killed or rate-limited inside stage 2, the status stays `planned` (a status is the last committed stage's), so `plan new` again prints `stopped after stage 1 ...`, `status planned`, exit 0 (probe `test_n1_open_stage2.py`: stages `plan committed`, `author open (3 calls)`, calls added 0). The status line is true and the message's caution about editing a stage in progress covers it; no state changes. Left as is it is defensible; a stricter rule would key on "stage 2 not opened".
- **N-b (Note): the tests pin `authored` only.** `reviewed` and `revised` are in `_MID_PLAN` and behave (above), but dropping either from the set would pass the suite (exit stays 1; only the continue line goes). One parametrized case would pin them.

## N2

FIXED.

- The new test, real `--basetemp` of 130 and of 172 characters (`pytest tests/test_plan_cli.py -k missing_path`): 3 passed each. The temp folders' resolved lengths were 149 and 191 for `<tmp>/nowhere` with a short test name, about 22 more with the real test's folder name.
- A sweep in one process (`test_probe_n2.py`, `n2_sweep.out`): pad lengths 0 to 158 in steps of 2 over the three cases (the `<missing>` path 8 to about 190 characters). Round 1's assertion (`named in result.output and "nowhere" in result.output`) fails 18 times, first at a 140-character path (`request`) and at 152 (`BUNDLE`, `OTHER`); the new one (`re.sub(r"[\s│|]+", "", output)`) fails 0 times.

## R1

Real processes, `probes-task9-rereview2/case2.py` (the doubles as the provider factory, then `cli.app()` with no CliRunner), `plan continue` on a plan killed inside stage 2. Outputs `r1_cases*.out`.

| Damage | Result |
| --- | --- |
| `.attempt.json` not JSON | `error: <bundle>\.attempt.json: line 1: not valid JSON (...)`; exit 1; 0 tracebacks |
| `.attempt.json` wrong shape | `error: ...\.attempt.json: field stage: Field required (and 3 more)`; exit 1 |
| `.attempt.json` not UTF-8, and empty | `error: ...: line 1: a byte that is not UTF-8 (...)`, `... not valid JSON (Expecting value)`; exit 1 |
| committed call's transcript cut, wrong shape, not UTF-8 | `error: <bundle>/transcripts\author-planner-1.json: line 6: not valid JSON (...)`, `: field system_sha256: Field required (and 3 more)`, `: line 1: a byte that is not UTF-8`; exit 1 |
| same, a stage-3 review transcript cut | `error: ...review-reviewer-0.json: line 6: not valid JSON`; exit 1 |
| transcript reply that is no `{"content": ...}`, a text of another sha256, no attempt | `error: transcripts/author-planner-1.json: the file:... reply is not a JSON object with a content` / `... a text whose sha256 is not the one the call recorded` / `no attempt to read the committed files from`; exit 1 |
| plan ledger line (in the dead attempt's window) valid JSON, not a `LedgerLine` | `error: <bundle>\ledger.jsonl: line 4: field ts: Field required (and 5 more)`; exit 1 |
| same, a JSON array | `error: ...ledger.jsonl: line 4: field (the record): Input should be an object`; exit 1 |
| ledger line mid-file with a byte that is not UTF-8 | `error: ...ledger.jsonl: line 3 is not valid JSON (...); it is not a torn last line ...`; exit 1 (round 1's rule, unchanged) |
| undamaged control (both bases) | exit 0, `status runnable` |

Each of the four new readers bites: with `Bundle.read_transcript`, `Bundle.read_attempt`, `Director._drop_dead_lines` or `committed_outputs` put back as in 9639ab8 (plugin `rr2_mut.py`), the CLI test fails (3, 3, 1 cases) and the unit test fails (1 each; the bare `committed_outputs` read fails its test). The dry run's ledger test passes; not mutated (the fixer's RED run covers it). The planted-bug test of round 1 still passes (`_plan_errors` catches `DirectorError` and `DamagedRecordError` only).

### Notes on R1

- **N-c (Note): a non-string `content` still raises a bare error.** A committed file call whose reply is `{"content": 5}` or `{"content": null}` gives `AttributeError: 'int' object has no attribute 'removeprefix'` out of `normalize_text` (`probe_content_type.py`); a list or a JSON string gives the named error. Hand edit only; the claim "a reply that is no JSON object with a content" covers a missing key and a non-object, not a wrong type.
- **N-d (Note): a schema-invalid ledger line before the marker's offset is not read.** `_drop_dead_lines` validates only lines after `attempt.ledger_lines`; a bad line 1 passes silently (`ledger_first_shape`: exit 0, runnable). It is no traceback and it is outside what the ruling named ("after the marker's offset", round 1's wording). A `null` line parses as the torn-tail marker and is dropped (pre-existing `parsed_lines` rule).

## Unfixed paths, graded by effect

Both reproduced by hand edit in a real process (`killed_review` base, a committed stage-3 review call killed after its record write; `r1_cases4.out`):

| Path | Hand edit | Result |
| --- | --- | --- |
| Missing transcript (`FileNotFoundError`) | delete `transcripts/review-reviewer-0.json` | `plan continue` exits 1 with a Rich traceback ending `FileNotFoundError: [Errno 2] ... transcripts\review-reviewer-0.json`, which does name the file; nothing written but the idempotent clear of `.attempt.json`; `plan.json` and the ledger unchanged (`cmp.py`); restoring the file lets the plan finish |
| Empty-attempts transcript (`IndexError`) | set `attempts` to `[]` in that transcript | exit 1, traceback ending `IndexError: list index out of range` at `Director._call`; no file named; same state afterwards |

Reachability without a hand edit:

- **Empty attempts.** The Director does write such a transcript: a provider error or timeout on the first attempt (`ask`, `attempts` still `[]`). But that call is an `error` call, and every `attempts[-1]` reader skips `error` calls (`_call`, `review_findings`, `findings_of`, `committed_outputs` returns early with no outputs). Probe: a stub timeout on the first file call leaves status `failed` and an empty transcript, and `plan continue` moves it to `transcripts/failed/`, resumes and ends `runnable`, exit 0 (`timeout_plans`). A non-error call with an empty transcript would need a hand edit. The fixer's concern 3 ("not reachable from a transcript the Director wrote") is right in effect, though the Director does write empty-attempts transcripts for failed calls.
- **Missing transcript.** A transcript is written before the record that names it, `_archive_round` copies before it rewrites and deletes last, and `_reopen_failed` moves a failed call's transcript then pops the call (a kill between them is redone as a no-op by `archive_failed_transcript`). By reading, no kill point leaves a committed call without its file; the hard-kill sweeps of Tasks 7b to 9 cover those writes. Deleting a harness file is a hand edit.

Grade: **N-e (Note)**, both. Effect is exit 1 and a traceback, nothing lost, on a state no run produces. They do not block Task 10; fold them into the same wrapper (`read_transcript` for a missing file, a check in `_call`) if the final review wants every harness read to print `error:`.

## Checks run

- `uv run pytest -q -m "slow or not slow" tests/test_plan_cli.py tests/test_bundle.py tests/test_dryrun.py -k "again_on or damaged_attempt or damaged_transcript or schema_invalid_ledger or cannot_give or planted_bug or missing_path"`: 19 passed. `tests/test_bundle.py tests/test_plan_records.py tests/test_store.py tests/test_director_primitive.py tests/test_plan_cli.py`: 172 passed, 2 skipped.
- Mutations (plugin, checkout untouched): `mid_exit0` (RED 1), `no_fail_lines` (RED 1), `transcript_raw` (RED 4), `attempt_raw` (RED 4), `ledger_raw` (RED 1), `content_raw` (RED 1).
- Real-process cases: 24 (`r1_cases.out`, `r1_cases2.out`, `r1_cases3.out`, `r1_cases4.out`). N1: 11 cases (CliRunner on the doubles). No real model was reachable (`PlanProviders` was the stub factory throughout).

## Files

All under `.superpowers/sdd/2026-11-14-phase-5-director/probes-task9-rereview2/`: `test_n1_probes.py`, `test_n1_open_stage2.py`, `test_probe_n2.py`, `test_probe_len.py`, `probe_content_type.py`, `prep2.py`, `prep3.py`, `case2.py`, `cmp.py`, `show.py`, `rr2_mut.py`, and the outputs `n1_probes.out`, `n1_probes_first.out`, `n2_sweep.out`, `r1_cases*.out`, `mutations.out`, `mutations_r1.out`, `fix_tests.out`. The `.out` files hold local paths from the machine (probe logs, not committed material).

## Disk

2.1 GB free at the start; 2.8 GB at the end. Every base bundle, work copy and basetemp was removed.
