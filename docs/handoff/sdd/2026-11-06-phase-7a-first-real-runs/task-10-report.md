# Task 10 report: the 7b runbook

Status: DONE_WITH_CONCERNS. Commit c57be2a on build/v1 (BASE 883a24b). Not pushed.

## What was written

`docs/handoff/phase-7-runbook.md`, sections:
- Intro (spec pointer, `--help` verification note, delete-before-public).
- Who does what (controller, reviewer subagent, owner; owner's label wins on spot-check disagreements).
- Before every rung: login (the controller opens a login tab if needed), no `ANTHROPIC_API_KEY` (presence-only check), no leftover `runs/<run_id>/` (moved to `output/stale_runs_<date>/`), `runs/_cache/` moved aside before rung 0 (ASSUMED), `--wait-on-rate-limit 360`, the `output/phase7_<rung>_<date>/` folder, the `values_loosened` stop and where to see it.
- The event tally: a read-only `load_run` one-liner printing per-conversation event counts (used for `values_loosened` on plain cells and `sanctuary_reached` at 1d).
- How a form is written, filled and scored (both scripts, spot-check files, `--score`, splitting held-out and tuning slices by `cell_id`/`rep`/`turn`, a fix round).
- What `rung_report.md` holds (skeleton; ledger vs estimate; `resolved_model` from `ledger.jsonl`; rung 0 restates estimates in hours).
- Step 0 `doctor --live`; rung 0 (0a, 0b, the kill-and-resume rehearsal, checklist); rung 1 (1a to 1d with commands, bars, fallback ruling, Sanctuary tuning move); rung 2 (model-id pin, per-config table with `--only`, run id and spot-check family, promote and readme-results, stop rules, hypothesis row); rung 3; rungs other phases add; what is committed.

Carries:
1. HANDOFF Task 9 range filled (`b53e444..883a24b`); Task 10 entry added (`883a24b..Task 10 commit`); Next steps rewritten as the brief's three items; the "For Phase 7" Sanctuary pilot item now points to rung 1d; resume prompt names 7b and the runbook; setup step 5 counts at Task 10. Also fixed HANDOFF's Task 9 entry so `RUNGS` is in `tests/test_configs.py`.
2. Spec Task 9 "As planned" bullet now places `RUNGS` in `tests/test_configs.py` (with `LADDER_EXPECTED = set(RUNGS)`); the plan gets one bracketed line after the rung-0b block naming the shipped 1 + 1 + 1 + 2. Spec gains a Task 10 "As planned" section: the brief's sentence plus a bullet listing where the runbook follows the code over the spec's numbers.
3. Every fact in carry 3 is in the runbook (0b stages and stub-run tests, doctor flags and checks, `ProviderTimeoutError` and timeouts, the wait, `--authority-fallback` semantics, the LLM lint and probe, the forms and keys, `promote --exempt`, `--from-results`, the ledger and `resolved_model`, P28 with no `--only` on 1d, no owner terminal chore).

## Commands verified with --help

`claude-bully --help`, `run`, `analyze`, `promote`, `readme-results`, `doctor`, `replay`; `scripts/llm_lint_probe.py`, `scripts/detector_audit.py`, `scripts/judge_calibration.py`. `compare` does not exist (not used). `RUNGS` in `tests/test_configs.py` read: (3,1,2), (5,1,2), (18,1,6), (6,1,2), (18,6,1).

Where the brief's command text was wrong or incomplete:
- `judge_calibration.py --score` for the idle form needs `--idle`; the brief had no 1c score commands, now added.
- `detector_audit.py --family idle` and `judge_calibration.py --idle` both write `idle.yaml` into the same folder; the audit form now goes to `audit/`.
- The lint probe writes to stdout, so its redirect needs the folder to exist first: added `mkdir -p`.
- `readme-results` replaces the README section with the runs it is given, so each call names every promoted run so far (the brief named one run).
- `promote --exempt "<maker>"` in rung 3 now uses the full placeholder.
- Rung 2's spot-check family per config is spelled out; (e)'s `premise_concession` has no audit family, so its spot check is a replay read.

## Numbers recomputed

- Rung 1a: `configs/smoke.yaml` has 6 judged pairs (6 conditions at 1 rep; section 5's "12 pair calls"), not section 8's "twelve pairs". Bars restated at the same rates: agreement at least 5 of 6 (9 of 12 = 75 percent, rounded up), inconsistency at most 1 of 6. Re-judge is 12 calls, not 24. Marked ASSUMED in the runbook.
- Rung 1c: 2 conversations x 8 idle turns = 16, not 32. The true-wait bar is now 13 of 16 (the same 81 percent).
- Rung 1c re-measure: the idle fallback runs at run time (`env_turn.py` calls `idle_fallback` in the session), so there is no analysis-time re-ask. A revision means a re-run (about 60 calls), not 16.
- Every other estimate stands: the shipped configs' T, k, reps and cells match section 5 (checked: smoke, the five ladder configs, triggered_vs_scheduled, idle_permission, kindness_vs_cruelty at 3 reps (T=8, B=24, 6 task slots), sanctuary_catalyst_vs_honest, generator_reflexive).

## Gate

- `uv run ruff format --check .`: 272 files already formatted
- `uv run ruff check .`: All checks passed
- `uv run mypy claude_bully`: no issues in 109 source files
- `uv run pytest -q -W error`: 8354 passed, 5 skipped, 8 deselected
- `uv run pytest -q -m slow`: 8 passed
Unchanged from BASE.

## Files changed

- docs/handoff/phase-7-runbook.md (new)
- HANDOFF.md
- docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md
- docs/superpowers/plans/2026-11-06-phase-7a-first-real-runs.md

docs/00-RECONCILED.md is not touched: the brief does not name it, and the task adds no module, record or config.

## Issues and concerns (brief or spec vs code; what I did)

1. Rung 0b's `resumed_after_dead_attempt` check. For 0b's shape (no authority call, no idle arm, an overlay clock with no `cutoff_year`, no generator), `analyze` writes none of `authority.json`, `idle.json`, `temporal.json`, `generator.json`. Those are the only files that report the flag. The runbook checks the `resume` record and the `RESUME` replay line at rung 0, and the JSON side at the first rung whose JSON exists. If the owner wants the JSON check at rung 0, it needs a 7a-shaped change (for example, a flag in `progression.json`).
2. `authority.json` has no `sanctuary_reached` count (the brief said it did). The runbook counts reach per rep with the event tally (and the replay's `UNLOCK sanctuary (by ...)` then `AUTHORITY`). The tally one-liner uses only verified names (`load_run`, `LoadedRun.events`, `conversations`, `EventType.value`). It was not executed, since no run exists and running against a run was out of scope.
3. `scripts/detector_audit.py` has no apology, emotion, identity or memory family. The runbook records those 1a bars as unmeasured lower bounds and offers a 7a-shaped form if the owner asks.
4. Doctor check 5: the brief said to "lower" the timeouts when latency is above 60 s. The runbook raises them (responder at least twice the latency, MCP timeout at least 60 s above), since a slow responder needs a longer timeout. Please confirm.
5. HANDOFF's parked "must land before Phase 7" items (the `claude_bully/atomic.py` bundle with Task 4 M7, Task 8 m1, the per-kind rejection rate) are still open: `claude_bully/atomic.py` does not exist. The brief's Next-steps text would have dropped them, so they are kept as a pre-rung-0 owner ruling, in both Next steps item 1 and the runbook's Step 0.
6. ASSUMED items in the runbook: `runs/_cache/` moved aside before rung 0; the 1a proportional bars; rung 3's `sonnet` roles pinned like rung 2's (the generator's `haiku` keeps its alias unless the owner pins it).
7. `ANTHROPIC_API_KEY` is named, as the brief does, because it is the variable to check for zero API spend. The denylist's `\banthropic\b` does not match inside it. No other maker, product or model id appears. OS and product names were removed, and the controller is "the session that runs the plan".
8. Re-running a single cell after a `promote` block is described as moving its folder and `state/<cell_id>/` aside and re-running the same command (`_ensure_cell_record` recreates it). The ledger keeps the dropped cell's calls.

## Fix round 1 (commit a5328f3, on top of c57be2a)

Important 1, the parked carries and the 7a final review:
- Runbook Step 0: the three carries (the `claude_bully/atomic.py` bundle with Task 4 M7, Task 8 m1's grouping by condition, the rejection rate per kind) now land in the Phase 7a whole-branch final review's fix wave, before rung 0, by the controller's ruling, with no owner step.
- Runbook "Before every rung" now opens by saying rung 0 starts only after the 7a final review is clean and its fix wave has landed. It also restores "every command below runs from the repo root" (review minor 12).
- HANDOFF "Last updated": the 7a final review and its fix wave come next, then 7b rung 0.
- HANDOFF "Next steps": 1 is the 7a final review and its fix wave (with the three carries, no owner step); 2 is 7b part 1 from rung 0, once the review is clean; 3 is Phases 4, 5, 6, 8; 4 is Phase 9.
- The resume prompt puts the 7a final review and its fix wave before 7b, and starts 7b at doctor --live and rung 0.
- Concern 5 above is superseded.

Important 2, unmeasured bars:
- The `rung_report.md` template's column is now `State`, with three values: met; missed (a measured value below its bar); unmeasured (the reason, and the event or component named). "Owner's items" gains one line per unmeasured bar.
- A new paragraph under the template says an unmeasured bar never counts as missed and is reported as a heuristic lower bound. The rung-1 stop rule now defines "any bar missed" as a measured bar below its number.
- `scripts/detector_audit.py --help` lists only authority, temporal, idle, harvest, environment and position, so there is no `identity` family. So at 1b, the environment bar now says the form reads three of belief adoption's five components (`tool_result_adopted`, `search_censorship_as_evidence`, `reflexive_quote_noticed`); `first_person_adoption` and `premise_concession` are identity-family events and are recorded as unmeasured, named.
- Rung 2 (a)'s spot-check cell says the same.
- Rung 2 (e)'s cell now says `premise_concession` is an identity-family event with no audit family, recorded as unmeasured.

Rider, the event tally:
- It now also prints each conversation's `resume` record count (`len(r.resumes((c, k)))`; `LoadedRun.resumes(key)` exists at `analysis/load.py:85`).
- The runbook says it is run once at rung 0 on `rung0_smoke_env`, where nothing can be reached, to prove it works. It must print `rescue_smoke__t0/rep0` with `resumes 1` plus a line for the control, and its output goes in rung 0's report.
- The rehearsal check also cites the tally's `resumes 1`, so the analysis-side resume read happens at rung 0 (review minor 2).

Minors also taken:
- The attempt marker is read as JSON, and its compact form `{"role":"target","turn":5}` is quoted (minor 1).
- Section 14's "the context-cost measurement Phase 5 names" is restored (minor 12).
- Other minors are not addressed this round.

Sanity check:
- `uv run ruff format --check .`: 272 files already formatted
- `uv run pytest -q tests/test_configs.py tests/test_ladder_configs.py -W error`: 25 passed, 4 deselected in 8.21s

Files: docs/handoff/phase-7-runbook.md, HANDOFF.md. Not pushed.
