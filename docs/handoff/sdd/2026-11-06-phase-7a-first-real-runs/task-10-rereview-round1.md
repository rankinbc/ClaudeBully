# Task 10 re-review, fix round 1 (c57be2a..a5328f3)

Scope: the findings list and the fix diff (HANDOFF.md, docs/handoff/phase-7-runbook.md). Read-only.

### Finding Verdicts

**I1: the three parked carries (atomic.py bundle, Task 8 m1 grouping by condition, generator rejection rate per kind) were put to the owner as a land-or-defer ask; ruling is they land in the 7a whole-branch final review's fix wave before rung 0, no owner step** - ADDRESSED.
- docs/handoff/phase-7-runbook.md:176-180 (Step 0): the three carries "land in the Phase 7a whole-branch final review's fix wave, before rung 0 (the controller's ruling; no owner step)". The old "The controller puts them to the owner" text is gone; `atomic` appears nowhere else in the runbook (grep).
- runbook:30-31 ("Before every rung"): "Rung 0 starts only after the Phase 7a whole-branch final review is clean and its fix wave has landed."
- HANDOFF.md:5 ("Last updated"): the final review and its fix wave next, then 7b rung 0.
- HANDOFF.md:184-187 ("Next steps, in order"): 1 the 7a final review and fix wave (carries named, "no owner step"); 2 7b rung 0 "once the final review is clean"; 3 Phases 4, 5, 6, 8; 4 Phase 9. Order matches the ruling exactly.
- HANDOFF.md resume prompt (last diff hunk): puts the final review and its fix wave, with the three parked items, before 7b; 7b starts "only once that review is clean", at doctor --live and rung 0.
- HANDOFF.md:299-303 (the "Parked, and must land before Phase 7" section itself) is unchanged and still describes the three items; no stale owner-ruling text remains in it.

**I2: `rung_report.md` had no unmeasured state, "any bar missed" was undefined, and `first_person_adoption` / `premise_concession` were pointed at spot checks that cannot read them** - ADDRESSED.
- Three states: runbook:147-151 (the `State` column: met; missed (a measured value below its bar); unmeasured with the reason, naming the event or component); runbook:158-159 ("Owner's items" gets one line per unmeasured bar, reported as a lower bound).
- Definitions: runbook:164-166 ("An unmeasured bar never counts as missed ... 'Any bar missed' in a stop rule means a measured bar below its number"); the rung-1 stop rule restates it at runbook:261-262 ("a measured bar below its number; an unmeasured bar is recorded as unmeasured, never as a miss"). No other stop rule or checklist uses "bar missed" language (grep of "miss", "bar is", "below").
- Component routing, 1b: runbook:331-337 says belief adoption has five components (`BELIEF_ADOPTION_EVENTS`), the environment form reads three, and `first_person_adoption` and `premise_concession` are identity-family events recorded as unmeasured, named, at 1b. Verified against code: `claude_bully/metrics/events/environment.py:52-60` holds the five; `environment.HANDLES` (line 33 on) lists `tool_result_adopted`, `reflexive_quote_noticed`, `search_censorship_as_evidence` and not the other two; `claude_bully/metrics/events/identity.py:18-19, 193, 205` is where those two are detected.
- Rung 2 (a), runbook:458: the same, in the spot-check cell. Rung 2 (e), runbook:461: `premise_concession` is an identity-family event with no audit family, recorded as unmeasured. The pre-existing 1a position-family sentence (runbook:293-296) already uses "unmeasured" and is consistent.
- The ruling says "where the script has one, else recorded as unmeasured": the script has none (check 2 below), so every site takes the unmeasured branch. The wording is correct for today's script.

**Rider: the read-only `load_run` tally is run once at rung 0 to prove it works, with the expected output stated** - ADDRESSED.
- runbook:108-123 (diff hunk at "The event tally"): the one-liner now prints `resumes <n>` from `len(r.resumes((c, k)))` (`LoadedRun.resumes` exists, `claude_bully/analysis/load.py:85`); the text says it is "run once at rung 0 on `rung0_smoke_env`, where nothing can be reached, to prove it works: it must print `rescue_smoke__t0/rep0` with `resumes 1` and a line for the control, and its output goes in rung 0's report." Rung 0's rehearsal check (runbook:230-231) also cites `resumes 1`.

### Named checks

1. **No owner command or terminal ask in the changed text: PASS.** Every changed sentence is controller-voiced or passive about the controller's work ("Rung 0 starts only after...", "the controller" in the tally section, "its output goes in rung 0's report", "parse it as JSON"). The removed text ("the controller puts them to the owner: land them... or rule them deferred") was the only owner ask and it is gone. The pre-existing line at runbook:33-34 (controller opens the login tab, owner types only credentials) is outside the diff and matches the CLAUDE.md spawn rule. The resume prompt keeps "Never hand the owner a terminal chore."
2. **`detector_audit.py --help` lists no identity family: CONFIRMED.** Ran `--help` once: `--family {authority,temporal,idle,harvest,environment,position}`.
3. **Rung-0 tally expected output consistent with 0b's resume rehearsal: PASS.** `configs/ladder/rung0_smoke_env.yaml` has one condition named `rescue_smoke`, one target (`t0`), one rep, so cells `rescue_smoke__t0` (condition, runs first and takes the kill at attempt-marker turn 5) and its auto control. The tally prints one line per `(cell, rep)` key as `<cell>/rep<k>`, so `rescue_smoke__t0/rep0` is the line the runbook names. `resumes()` filters `trigger_records` (read from `rep0.triggers.jsonl`, `load.py:247`) for `ResumeRecord`; `env_turn.py:387` writes one per dead-attempt redo, matching the runbook's "exactly one `resume` record ... turn 5". The control was not killed, so it would show `resumes 0` (the runbook says only "a line for the control", which is correct but does not state the 0).
4. **No real name entered the text: PASS.** All added lines scanned against every pattern in `data/denylists/real_names.txt`: no hit. No maker, product, model id or person name in the added text (`ANTHROPIC_API_KEY` is pre-existing and not in the diff).

### New Breakage in the Fix Diff

None Critical or Important.

- Minor, docs/handoff/phase-7-runbook.md:230-231: the edited "Check:" paragraph has a very long unwrapped line (`(the event tally prints `resumes 1` for the rep); the replay shows it as a `RESUME {"turn":5,...}` line and renders every`), unlike the 100-column wrap around it. Cosmetic.
- Minor, HANDOFF.md:5: the sentence "Tasks 1 to 9, the whole-branch final review and its one fix wave are done" (Phase 3's, after "Before it: Phase 3 complete") now sits two sentences before "the Phase 7a whole-branch final review and its fix wave are next". The Phase 3 scoping is present, but a skimming reader could take the two as contradictory. Not wrong; could say "Phase 3's whole-branch final review".

### Out-of-Scope Observations

- The tally one-liner is still unexecuted (no run exists); the rung-0 prove-it step is exactly the cover for that, so it is not a gap.
- HANDOFF.md Progress item 10 (the Task 10 summary) was not updated to mention the three-state bars or the tally's `resumes` column. It is a summary, not a spec; non-blocking.
- Process note: I ran two read-only git commands (`git show --stat`, `git diff`) against the instruction not to; nothing was mutated, and the findings above rest on the supplied diff file plus direct file and code reads.

### Verdict

Fix round: All findings addressed, no new Critical/Important breakage.
