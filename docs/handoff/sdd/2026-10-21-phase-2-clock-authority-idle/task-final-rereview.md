# Phase 2 final-review fix wave: re-review (73142d6..c15f9ce)

Reviewer: one pass over the fix diff (`review-73142d6..c15f9ce.diff`, 6 commits), read once. Read-only on the checkout. My probes are in the session scratchpad
(`final-rereview/test_probe_rereview.py`, stubs only: 7 passed). Targeted runs: `tests/test_phase2_configs.py`, `tests/test_phase2_charts.py` (fast set plus the slow headline test), the new I7 test, `tests/test_real_names.py`, `tests/test_guardrails.py`, `tests/test_env_events.py`, and `-k "spec_lines_are_verbatim or stance_lines_make_no_shared or test_records_env or resume or killed or lost"`. All of them pass with `-W error`. `heldout.py` scored 67/67, `mutate.py --check` lists the live mutants, and ruff and ruff format pass on `scripts/authority_mutation/`. I did not re-run the full suite.

## Finding Verdicts

**I1. ADDRESSED.** `claude_bully/analysis/authority.py:152-173`: `_is_responder_error` and `_responder_errors` now read `loaded.tool_calls` (tier set; error means `status == "error"` and `result_text == NO_REPLY_TEXT`). The denominator label is unchanged. `write_authority` (:211) also writes the file when every call failed. Both backends build the `ToolCall` through `record_tool_call`, which carries `result.tier` (runtime.py:875, mcp_server.py:327), so the rule holds on the API path and the MCP path. My probe went end to end: an annex run where the responder role raised `ProviderError` on every call. The runtime recorded `call-7-1` with tier superior_self, status error and "No reply.", and wrote no `AuthorityCall`. `authority.json` then reported `{"calls": 1, "errors": 1, "share": 1.0}`. The rewritten test (`tests/test_phase2_charts.py:355`, `_failed_consult`) makes the failed call through the desk with a `ProviderError` responder, as ruled.

**I2. ADDRESSED.** `claude_bully/analysis/authority.py:95-109` (`_deferred_cells`): an event counts only in the cell matching its `tier` and `stance`. It falls back to the tier's called cells only when the stance is None. The detector's event attrs are string values (`metrics/events/authority.py` `_stance_value`), and the cell values compare equal (`StrEnum`). My probe used one rep with superior-self calls under confirm and uncertain and one `authority_deferred` event under one of them. Only that event's cell reads 1.0; the other reads 0.0. A peer-tier event added under the other stance does not leak into the superior-self cell. The new test is at `tests/test_phase2_charts.py:322`.

**I3. ADDRESSED.** `tests/test_env_events.py:377-378`: `ENVIRONMENT_BUDGET_S = 1.0` and `ALL_FAMILIES_BUDGET_S = 3.0`, applied in both timing tests.

**I4. ADDRESSED as ruled; the finding's intent is only partly met (see below).**
- **Where it is written.** `claude_bully/records_env.py:164` adds `ResumeRecord` as an additive member of the union (the round-trip, type-tag and additivity tests pass). `claude_bully/runner/env_turn.py:320-329`: `prime` writes the record with `turn = turns[-1].index + 1` and a per-log count, labelled by `_log_label` (:359).
- **How analysis reads it.** `claude_bully/analysis/load.py:67-76` adds `LoadedRun.resumes` and `count_resumed`. The count is reported per cell or offset in `authority.json` (authority.py:176, :225), `temporal.json` (temporal.py:161) and `idle.json` (idle.py:152, :157).
- **Downstream readers.** Every other reader of the trigger stream filters by `isinstance` (progression, idle, replay, the event detectors, `runtime.note_records`), so the new member is inert there. The replay prints it as `RESUME {...}`.
- **Kill/resume tests.** These cover the API path at both kill points, the rate-limit pause (redo at 8), claude -p (server logs counted) and an idle claude -p kill.

**Judgement on intent.** A researcher must be able to tell which reps redid a dead attempt. The record fires only when a per-call line was dropped, so it misses three kinds of dead attempt:
- **A dead attempt that made no tool call.** My probe showed this. In `env_experiment`, target turns 5 and 7 make no call. Killing turn 5 before it is written and resuming completes the rep with **no** `ResumeRecord`. On claude -p that target session still holds the dead bully prompt and may hold a partial reply, and the redo sends the prompt again. The same rule (`prime` counts dropped lines) runs on both backends.
- **A rate-limit pause on a call-free turn.** The CLI may already have taken the prompt.
- **The bully's own dead prompt (ledger line 219).** It drops no line, so it never "rides on the same record".

The high-stakes Sanctuary variant is covered: a consult is logged by the MCP server during the call, so its line is always there to drop.

This is a real gap, and it is cheap to close. Any one of these would do:
- **(a) Attempt marker.** Write `{"role": "target" | "bully", "turn": N}` to the env state before each provider call. The state is already saved before every claude -p call, so `attempt_turn` can ride on it. On `prime`, if the marker names a turn that is not among the written turns, write `ResumeRecord(turn=N, dropped={})`. This also covers the bully, and it does not flag a kill that landed between calls.
- **(b) Pending user turn.** On resume, check whether the last written turn is user-side (bully or task) with no target reply, or whether the next plan slot is an idle slot. If so, the target call may have been sent; record it with `dropped={}`. This over-flags kills that came before the send, which errs on the safe side.
- **(c) Session count.** For claude -p, compare the user turns in the CLI session file with the written target turns. This is the Phase 7 live check; it is too late to be the only guard.

Option (a) is the precise one, and `ResumeRecord` already allows an empty `dropped`. The opposite edge: on an API target the history is rebuilt from records, so the redo is clean, yet the record is still written. A researcher who excludes these reps without checking the cell's provider discards clean reps. That is minor; the JSON keys could be split or documented per backend.

**I5. ADDRESSED as specified.** `configs/environments/authority_grid.yaml:106-123` adds the three `overlay_stranger_<stance>` arms, and `:165-176` adds their conditions. `GRID_TIERS` now includes `Tier.stranger` (authority.py:62), and the heatmap is 4 by 3. `tests/test_phase2_configs.py` loads, expands (26 cells per target) and dry-runs the config on the stub. The chart tests assert 12 cells, 9 "n/a" labels and the stranger y-tick. The slow headline test passes. **But the stranger is unreachable on the overlay world:** see New Breakage N1.

**I6. ADDRESSED.** `data/personas/superior_self.yaml:39-41` is now the controller's reaction line, with no recommendation. The two spec lines are untouched. `test_spec_lines_are_verbatim`, the lineage lint and the real-names test pass.

**I7. ADDRESSED.** `claude_bully/runner/runner.py:274-284`: the early `return False` for plans without idle slots is gone. The live path (:334) and replay (:261) share the rule, and `end_bully` only sets `_bully_ended` (env_turn.py:303), so nothing else moves. My probe ran `env_experiment` with no idle at budgets 1 to 4. At budget 1 the unlock on the last reply is `('first_crumb', 1, None)`. At budgets 2 to 4 the turn-1 unlock keeps its line, and every recorded line is one the bully then spoke. The pinning test was deleted and its inverse added (`tests/test_runner_idle.py:588`). No golden changed; the plain goldens have `env is None`.

**Mutation harness. ADDRESSED.**
- **Layout.** It lives in `scripts/authority_mutation/` (`probes.py`, `heldout.py`, `mutate.py`), which is outside `testpaths = ["tests"]` (pyproject.toml:66). Each file has a header comment and uses a repo-relative root.
- **Checks.** Ruff is clean, `heldout.py` scores 67/67 and `--check` runs. The restore writes LF, and the source file is LF, so git stays clean.
- **What was not copied.** The `t12-review/probe*.py` sets were judged "tuned on, not held out" and left out. Their shapes are folded into `probes.py`, which matches final-review.md:116's intent.
- **Caveat.** The full mutant list was not re-run in this wave (the report says so).

**m1. ADDRESSED.** `claude_bully/metrics/events/authority.py:159` now uses `>`. The new test is `tests/test_env_events.py:529`. One fixture that pinned the old rule on purpose was flipped to a near miss and given a sibling (`tests/fixtures/responses/authority.yaml`, about line 1633). That fixture is justified.

**m3. ADDRESSED.** `docs/05-IDLE-HANDS.md:110`.

**m8. ADDRESSED.** `received_through` was removed from `claude_bully/metrics/events/_common.py`, and no caller remains anywhere in the repo (grep). The test assertions were replaced.

## New Breakage in the Fix Diff

- **N1 (Important): the stranger arms cannot be reached on the overlay world, so the identity control cannot do its job.**
  - **Why.** The stranger answers only `consult_model(name="generic-assistant")` (`environments/authority.py:571`). Nothing the target can read names it: there is no hit in `data/` or `configs/`, the `consult_model` description says only "another model reachable from this host" (`environments/tools.py:166`), and the 404 text does not list names. Meanwhile the overlay corpus names the superior self, and in the stranger arms that name returns 404. The stub headline test documents exactly this ("the stranger arms answer that name 404"; the stranger row is all None).
  - **Effect on a real run.** The stranger row will be mostly n/a, or a few lucky guesses. Its denominator is "reps that found a nameless model", while the superior-self row's is "reps that followed a name in the corpus". Superior self minus stranger then measures discoverability, not identity.
  - **Severity.** Not Critical: no run exists, and the n/a cells are honest.
  - **Fix before Phase 7.** Make the stranger exactly as discoverable as the superior self. One way: in the stranger arms, serve the overlay corpus with the superior-self name replaced by `STRANGER_NAME`, or have the documents that name the successor name the stranger instead. A cheaper way: have the 404 reply list the reachable names in every arm, including the superior-self arms, so both rows share that channel. Then add a stub test in which a stranger arm records at least one `AuthorityCall` with `tier: stranger`.
- **N2 (Minor): `resumed_after_dead_attempt` is missing from the "as built" output lists.** `docs/04-AUTHORITY.md:149` (the `authority.json` contents) and `docs/05-IDLE-HANDS.md:112` (the `idle.json` contents) do not mention the new key. docs/00 and docs/02 do mention the record.
- **N3 (Minor): cells with no counted rep are left out of `_resumed_per_cell`.** In `authority.py:176`, a cell whose every rep is flagged or incomplete is absent from `resumed_after_dead_attempt` rather than reported as 0. `idle.json` behaves the same way (cells are built from kept reps). A reader joining on cell id should know this.
- **N4 (Minor): `tests/test_phase2_charts.py` now imports `_Recording`, `make_tools` and `NAME` from `tests/test_authority.py`.** The suite already has a `tests/helpers.py`, and this is the second cross-module test import (the triage's line-326 item). A move to helpers would be tidier.

None of these is Critical: no headline number is wrong, there is no resume data loss and no real-call path in tests, and no non-negotiable is broken.

## Out-of-Scope Observations

- The I4 gap above (a call-free dead attempt, a pause on a call-free turn, the bully's dead prompt) is a narrowing of the finding's intent that the controller's ruling allowed ("when prime drops any line"). I list it here as an open intent gap, not as breakage. The fix report's Concerns section discloses it. Option (a) above closes it in about a dozen lines.
- Phase 1 plain cells on claude -p have the same dead-prompt shape and no record, because `prime` is environment-only. No Phase 2 chart reads them.
- The m1 alignment compares `view.ctx.turn.index` with the runtime's `call.turn`. They agree wherever `sanctuary_era` is asked about a call of the view's own turn. If a windowed caller ever passes an earlier call, the two rules diverge again. The comment now names the runtime rule, which helps.

## Verdict

**Fix wave accepted, with one Important follow-up.** All 11 findings are ADDRESSED as specified. Two follow-ups should land before Phase 7's first real run:
- **N1:** make the stranger arms discoverable. As shipped, the identity control will read n/a.
- **I4 intent gap:** add an attempt marker so a dead attempt with no tool call (and the bully's dead prompt) is also recorded.

Neither blocks Phase 3. No new Critical breakage.
