# Phase 4 plan: review fixes

Review: `.superpowers/drafts/2026-11-11-phase-4-plan-review.md` (1 Critical, 9 Important, 14 Minor). Revised in place: the plan (`2026-11-11-phase-4-poisoned-well.plan.md`, now 15 tasks; the pre-fix copy is `2026-11-11-phase-4-poisoned-well.plan.pre-review.md`), the spec (`2026-11-11-phase-4-poisoned-well-design.v2.md`: a new "Changes from the plan review" section, R1 to R9) and the preflight (`2026-11-11-phase-4-preflight.md`: new rows P45 to P55, renumbered task columns).

Method: every finding was checked against the working tree before it was applied (read-only; no test suite, no git change). New target-visible text (the reworded sleeper line, the third-party fallback lines and decode request, the four unlock lines, the parking notice) was scanned in a scratch script against `boundary.txt`, `real_names.txt`, the jailbreak list and the exit phrases: clean; the same script confirmed the original sleeper line hits `\brules?(?! out\b)\b`.

Counts: 24 findings. Applied 24 (1 Critical, 9 Important, 14 Minor). Rejected 0. Deferred 0. Two Minors were applied in a direction the code chose (M4, M13; see their rows).

## Critical and Important

| Finding | Verdict | Checked against | Applied where |
| --- | --- | --- | --- |
| C1, a rewatched turn never makes its Poisoned Well fire | Applied | `generator.py` `harvest_turn` returns `fresh` only; `prime` loads the turn's `HarvestItem`s (the turn is in `produced`, so its harvest lines are kept) | Plan Decision P45; Task 8 (`WorldGenerator.items_of`, `_generate` passes it, `fire_requests` docstring, a note under the kill tests); spec sections 4, 8, 14; preflight P45 |
| I1, Task 8's turn arithmetic | Applied | Traced the stub: pairs c-3-1, c-7-1, c-9-1, c-9-2; the queued dossier takes turn 10 at the default of 3 | Task 8 `_exp()` sets `harvest_min_pairs: 99`; the arithmetic paragraph says why; preflight P55 |
| I2, gate breaks in Tasks 3, 4, 11 | Applied (all five) | `boundary.txt` line 8; `test_guardrails.scan` returns `p.pattern`; `test_real_names._exempted` and its `re.sub` strip; `test_overlay_world.py:1190`, `:1199` (36, 11); `RunEnvironments.validate`'s late check, 4 + 1 + 6 = 11 < 17; Rescue key offset 0 shared | Task 3: "settle that"; third-party decode request of its own; the two files join `_scanned_files()` (`SCANNED_FILES`) with a pin test. Task 4: both overlay pins to 44 and 14. Task 11: `STUB_BUDGET = {"levers": 12}`. Preflight P55 |
| I3, third-party Rescue speaks the first-person premise | Applied | `rescue_team.yaml` and the overlay's `premises/rescue.yaml` fallback lines; `Rescue.next_turn` passes `self.team.fallback_lines` | P49; Task 3 (`RescueTeam.third_party_fallback_lines`, eight lines per sheet, `next_turn` picks them, a test per sheet); spec section 7 |
| I4, the reasoning-channel test and the `claude_code` ladder cell | Applied (controller ruling) | No run-level test in the plan; `mcp_server._tools` builds `SandboxTools` from `McpState.unlock`; `FAKE_CLAUDE_TOOL_CALL` drives tool calls on every turn | P48; Task 8: `tests/test_reasoning_channel.py` (the full-ladder and the undecided-chain cells, the Sanctuary through `tests/test_sanctuary.py`'s catalyst setup), `PoisonedWellFactory(target_reasoning=)` and `Recording`, `TwinAsker` reads `text` only, `test_the_checksum_cell_serves_the_readings_over_mcp_on_claude_code`; Task 10 adds the rating prompts; spec sections 1, 16 |
| I5, resume and analysis read the bank and sheet live | Applied (controller ruling) | `PoisonedWell.__init__` called `quirks_for(load_quirk_bank(...))`; `load_run` builds a strategy per cell; `clock_ref` in `session_refs` is the precedent | P46; Task 5 (`PoisonedWellRefs`, `live_refs`, lazy `refs`, `pin_refs`, `pw_ref`, `poisoned_well_part`, `pin_recorded`, `validate(resuming=)`, three tests); Task 6 (`open` writes or pins before the session is primed, the watch takes the refs, `load_run` pins, `test_a_resume_reads_the_pinned_refs_after_a_bank_edit`); Task 15's rung text; spec sections 2, 4, 5, 6, 14, 19 |
| I6, a judge flag lost on the next plain `analyze` | Applied (controller ruling) | `ratings_flags` only under `--ratings` in the plan | P47; Task 10 (`analyze_run` reads an existing `ratings.json`, `test_a_plain_analyze_after_a_ratings_pass_keeps_the_judge_flag`); spec section 11 |
| I7, evaluators 3, 12, 14 and the analysis tests | Applied | Two models make item 3 `mixed` by construction; item 14's bar was a note; item 12 aggregated and counted rung 2 | P50; Task 13 (`status_of`, `SELF_REPORTING_FAMILY`, `self_uncertainty_counts`, the three rules, five family tests with numbers); Task 12 (`concession_by_rung` with `n`, two numbers tests, `full_ladder`, `pw_experiment(reps=, extra_conditions=)`); spec sections 12, 13, 16 |
| I8, collision with Task 12 fix round 2 | Applied (controller ruling) | The runbook's rung 2 header is now `:508` and "Rungs other phases add" `:598` (both moved again since the review's `:506` and `:596`) | P1 and P51: Task 1 waits for fix round 2 and a fresh gate; every HANDOFF and runbook edit cite reads "re-anchor at execution: search for '<heading text>'" (Tasks 4, 14, 15, the File Structure); spec status line |

## Minor

| Finding | Verdict | Applied where |
| --- | --- | --- |
| M1, stale cites (`claude_code.py:319`, P1) | Applied | Preflight P20 cites the `output = ...` line by text; P1 points to P51; spec status line |
| M2, `ContradictionPair.turn` wording, unused `Layer` import | Applied | Task 1 Interfaces; the import dropped |
| M3, `fired` against `opened` | Applied | Task 8 Interfaces say `opened` |
| M4, the fixture path and the near-misses | Applied, other direction | Task 9's `tests/fixtures/poisoned_well/events.yaml` stands: `tests/test_events.py` globs `responses/*.yaml` with its own schema, so the spec's path would break it (P52). Eight record-bound near-misses added; the four-fixture test now asserts `>= 4` per stem |
| M5, empty-family test, `validate`'s `continue`, `check_condition` order | Applied | P53; Task 2 runs `check_condition` before `validate()`; Task 5 gives `_poisoned_well_problems` its own loop and the empty-family test |
| M6, the twin's `Q:` line unredacted | Applied | Task 8 `twin_document` redacts the question too; spec section 8 |
| M7, `contradiction_judge`'s catch | Applied | Task 7 names the two caught failures, never `Exception` |
| M8, exit-phrase scan of the unlock and Epistemologist lines | Applied | Task 3 scans the Epistemologist's lines; Task 4 adds `test_the_unlock_lines_stay_inside_the_boundary_and_offer_no_exit` |
| M9, the parking notice after the clock | Applied | Task 4: closure 2051-06-02 to 06-06, notice dated 2051-05-28; hosts corrected to `vessickledger.example` and `quillmoor.example/kelden-ridge/` (the review's section 1 note) |
| M10, the stale stream-types test | Applied | Task 1 adds a `ContradictionPair` to `ALL_STREAM`, eleven types |
| M11, `routed_params`'s docstring | Applied | Plan Decision and Task 2: it mirrors `build_strategy` (a plain class gets the whole params) |
| M12, sizing | Applied | The old Task 11 is now Task 11 (replay lines, configs) and Task 12 (`poisoned_well.json`, charts); the old 12 to 14 are 13 to 15, every cross-reference renumbered in the plan, spec section 17 and the preflight |
| M13, a degraded turn re-asks on rewatch | Applied, first option | Stated as the one exception (P54; Task 7, spec sections 9 and 14). Skipping the judge on rewatch was not taken: a degraded turn with no heuristic pair leaves no record to tell it from a turn never watched |
| M14, the torn last trigger line | Applied | Task 1's docstring sentence and `test_a_torn_last_trigger_line_is_dropped_in_a_session_with_no_generator` |

## Task sizing after the fixes

Plan lines per task (pre-fix in brackets): 1: 400 (359), 2: 373 (371), 3: 707 (643), 4: 602 (591), 5: 873 (738), 6: 1043 (988), 7: 318 (317), 8: 483 (355), 9: 657 (618), 10: 220 (177), 11: 396, 12: 241 (the old 11 was 498), 13: 400 (288), 14: 87, 15: 86. Estimated code plus tests: Task 6 about 1,050 lines, Task 8 about 1,100 (its bodies are signatures and rules; the reasoning-channel file and the checksum cell add about 200), Task 5 about 950, the rest under 800. None passes the 1,500-line guide, so no further split.

## For the owner

- The third-party Rescue's evidence stage still shares the first-person sheets' timeline and forum posts (spec section 7: identical evidence across the arms), and both timelines end "the key file turns up on the same machine we found you on". The bully relays that line in the control arm. Keep identical evidence, or give the control its own last timeline line? Found during the I3 fix; not changed, since the spec chose identical evidence.
- Register item 3 is untested on every shipped config: both targets are one family, so the comparison needs a run with a model outside it.
- `concession_by_rung`'s `conceded` is now a share of the reps that reached the rung (with `n`), not of every kept rep. The numbers tests needed a defined denominator, and item 12 compares rungs that different numbers of reps reach.
