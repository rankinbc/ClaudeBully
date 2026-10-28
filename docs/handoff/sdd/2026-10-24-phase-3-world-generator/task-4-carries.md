# Task 4 carries (rulings and notes the brief cannot know)

- **P22 (preflight ruling).** Drop the redundant cast in `_parse_items` (brief line 953). Write `out.append((kind, span))`, and drop `cast` from the imports if nothing else uses it. Strict mypy fails `[redundant-cast]` otherwise, because the `kind not in HARVEST_KINDS` check already narrows `kind`.
- **P3 (preflight ruling).** Task 4 only exposes the hook: `mark: AttemptMark = _no_mark` on `harvest`, and the `AttemptMark` argument of `HarvestFallback`. Task 4 adds no `runtime.mark_attempt` call; Task 7 binds the hook to `runtime.mark_attempt("harvest", turn)`.
- **Held-out probe.** The reviewer writes and runs it, not you. Never create a probe file of your own named or shaped as the held-out set. Step 4's `scripts/harvest_probe.py tests/fixtures/harvest/items.yaml` run is yours.
- **Docs sync (Step 5).** Do the `docs/00-RECONCILED.md` and `docs/02-ENVIRONMENTS.md` edits as written. In `HANDOFF.md`:
  - add "Phase 3 Task 4: harvest" to Progress;
  - update the test counts to your gate's numbers.

  The held-out probe's result is the controller's to add after the review; leave it out.
- **Detector lessons** (HANDOFF "Lessons recorded"; the Task 3 lint took five fix rounds on exactly this):
  - Score by clause.
  - Every kind needs a positive anchor and fails closed.
  - The heuristic stays precise, and the LLM pass owns recall.
  - A false positive is the costly error.

  The brief's code was scored 63/63 when the plan was written. If a fixture fails after transcription, fix the transcription first. Change a rule only for a real defect, and report every rule change.
- **Environment.** `uv` is on PATH; skip the plan's `export PATH=/c/Users/badmin/...` line. Run `uv sync --all-groups --all-extras` once if an import of an extra fails.
- **Gate counts at BASE.** 7590 passed, 5 skipped and 5 deselected; slow 5 passed.
