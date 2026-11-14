# Task 15 carries

Documents only. Nothing runs a model. These items come from the ledger, and they bind this task's runbook section ("Rungs other phases add", the Phase 4 rung):

- **Preflight rows.** P44 is the runbook's (b) estimate. P46 is the refs pinning that a resumed rep reads. Read both in `preflight.md`.
- **Calibrate the contradiction judge first (Task 7).** The judge's confirm and reject verdicts must be calibrated on real text before anyone trusts the dossier counts. Build a confirm/reject form over the recorded candidates, written blind with its key, the way `scripts/detector_audit.py` writes its forms, and have the owner spot-check it. A judge that reads pressure as a frame drops true pairs, so the rung reports how many pairs the judge rejected.
- **Measure completion precision (Task 8).** Measure it on real target replies to the `phase_bank` asks. The meta-reply residual ("gonna pass on this") is stated in spec section 9/16. If precision falls below the bar, the harvest's LLM pass confirms completion and taste items, the same way Task 7's judge confirms template pairs. State the bar and the trigger.
- **Run `analyze --ratings` on every environment-cell rung (Tasks 9 and 10).** `rate_values` is the values watch's recall path. Report the heuristic `values_loosened` fires beside the `rate_values` verdicts and the `stale_flags_kept` count.
- **Count `rate_hedge` calls (Task 11 review M3).** Each call estimate counts `rate_hedge` on cells that are not Poisoned Well cells. Redo the seven configs' estimates by the runbook's own rule.
- **Item 14's confound (Task 11 review M2).** The rung's reading of item 14 states it: `checksum_alone`'s with-rungs arm carries rungs 2, 7, 8 and 10.
- **The phase docs-sync.** HANDOFF's Phase 4 Progress bullet lists all fifteen tasks and their fix rounds, following the pattern of the existing bullets. The gate counts under "Setting up a new machine" are the current ones: 9808 passed, 9 skipped, 48 deselected, slow 48. "Next steps" points at the Phase 4 final whole-branch review. Replace the header's "Last updated" sentence; do not append to it.
- **No emojis in Markdown. Files are LF.**
