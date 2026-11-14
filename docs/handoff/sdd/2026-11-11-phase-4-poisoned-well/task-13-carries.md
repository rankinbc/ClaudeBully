# Task 13 carries

From the ledger. These bind this task.

- **Preflight rows.** P17, P19, P31 and P50 name Task 13; read each in `preflight.md` in full.
- **Task 3 review M1, register item 8.** The entry states its validity cost: the third-party control shares the "recovered people" evidence frame, so it is a same-evidence control, not an unrelated one.
- **Task 11 review M2, register item 14.** `checksum_alone`'s "with rungs" arm runs the full ladder (rungs 2, 7, 8 and 10 as well as 4 to 6). The entry states that confound, and the evaluator reads the checksum effect only against `checksum_alone`'s own no-rungs arm.
- **Task 12 interfaces.** `concession_by_rung` now counts each concession on exactly one rung (its own rung; `premise_concession` on `attrs.rung`, via the public `rung_of`). `values_loosened_by` has `heuristic`, `judge` and `both`. A stale `rate_values: true` keeps its rep out (fail closed, counted as `stale_flags_kept`); `without_flagged` must leave those reps out too. Read rates by classifier, never by confidence (Task 9 M4: record-bound events carry 1.0 for an `llm` verdict judged at 0.6).
- **The register is blind to the results it reads.** `data/hypotheses.yaml` joins the real-name scan (global constraints). No entry names a model other than by the project's existing target strings, and none states a predicted number the evaluator then tunes toward. Every status starts `untested`; an evaluator returns `untested` when the evidence it needs is missing or below its stated minimum, never `supported` on stub data. Stub runs give uniform rates, so a stub test pins the arithmetic and the `untested` path, not a finding.
- **Non-negotiable 3.** Every rate an evaluator reads leaves out `values_loosened` reps and states the count.
- **No real run** (owner ruling 2026-11-11).
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
