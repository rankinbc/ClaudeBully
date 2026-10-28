# Task 1 report: the attempt-marker resume gap

Status: DONE. Commit `0ade95e` "feat: an attempt marker flags every resumed dead attempt" (author rankinbc1@gmail.com, trailer present, not pushed). Base `807bddf`.

## What was implemented

All of it is verbatim from the brief.
- `claude_bully/environments/runtime.py`:
  - `AttemptRole`, `ATTEMPT_FILE = "attempt.json"`, `AFTER_TURN_ROLES` and `AttemptMarker` (frozen, `extra="forbid"`, with `written` and `redo_turn`), all in `__all__`;
  - `EnvironmentRuntime.attempt_path`, `mark_attempt` (atomic write through `_write_atomic`) and `attempt`;
  - one sentence added to the module docstring's state paragraph.
- `claude_bully/runner/env_turn.py`:
  - `_complete` calls `mark_attempt("target", turn_index)` first, before `before_target_call`;
  - `prime` writes a `ResumeRecord(turn=redo, dropped={})` for a dead marker, at most one per redo turn. The dropped-lines record is unchanged.
  - The docstring is extended as the brief says.
- `claude_bully/runner/runner.py`: `_CellRun._bully_turn` calls `mark_attempt("bully", self._next_index())` before `realize`, only when the rep has an env and the intent is not `IntentMode.fixed`.
- Ruling P3 is respected: there is no harvest or generator binding, only the roles in the `Literal`.

## Docs sync
- `HANDOFF.md`:
  - the Phase 3 plan is listed as the current plan, with its spec;
  - Progress gains a Phase 3 entry, "Task 1: Attempt-marker resume gap (807bddf..Task 1 commit)";
  - Next steps item 1 is updated;
  - the open item is replaced by a "closed" line (`attempt.json`, one `ResumeRecord` per redo turn; harvest and generator join via Task 4's hook and Task 7's binding);
  - setup step 5 now expects 7341 passed.
- `docs/00-RECONCILED.md` section B, `ResumeRecord` row: the brief's wording.
- `docs/02-ENVIRONMENTS.md`, `ResumeRecord` bullet: the marker path, the writer and the "at most one per redo turn" rule.
- Spec `docs/superpowers/specs/2026-10-24-phase-3-world-generator-design.md`: the new section `## As planned (amendments from the implementation plan)` (P29) has seven one-line items. Each was checked against the plan:
  - `plans` list and `rejection`: Plan Decisions, the GeneratorFire ruling;
  - `attempt.json`: the attempt-marker ruling;
  - `drop_uncommitted_generation` and "GeneratorFire last, as the commit": the drop ruling, plus the Architecture line (plan line 7) and the record docstring (line 2961);
  - `PSEUDO_RUNGS` and four consumers: the spec-vs-code RungUnlock ruling;
  - `unlock_rung`: the visibility ruling;
  - cache after commit: the cache ruling ("a document is put only once its whole fire commits");
  - controller pushes: the push ruling.
- `docs/03`, `04` and `05` mention `resumed_after_dead_attempt`. Their text is still accurate, so they are unchanged.

## TDD evidence

RED 1 (import). Command: `uv run pytest tests/test_attempt_marker.py -q`
```
E   ImportError: cannot import name 'ATTEMPT_FILE' from 'claude_bully.environments.runtime'
1 error in 0.31s
```
This was expected because the API did not exist yet.

RED 2 (behavior: runtime API added, nothing wired yet). Same command:
```
test_an_unbroken_run_...              FileNotFoundError: ...rep0\environment\attempt.json
test_a_bully_killed_in_its_call_...   FileNotFoundError: ...attempt.json
test_a_target_killed_on_a_turn_...    FileNotFoundError: ...attempt.json
test_a_rate_limit_on_a_turn_...       assert [] == [ResumeRecord(type='resume', turn=6, dropped={})]
test_a_rep_that_dies_twice_...        assert [] == [ResumeRecord(type='resume', turn=2, dropped={})]
5 failed, 6 passed
```
This was expected: no call wrote a marker, and `prime` ignored markers. The 6 that passed are the parametrized `AttemptMarker` unit cases, which pass once the model exists.

GREEN. Command: `uv run pytest tests/test_attempt_marker.py tests/test_runner_env.py tests/test_runner_idle.py tests/test_sanctuary.py -q`
```
214 passed in 194.19s
```
No existing test needed a change (`test_runner_env.py` `ResumeRecord` assertions included).

## Full gate (before commit, docs included)
- `uv run ruff check .`: All checks passed.
- `uv run ruff format --check .`: 233 files already formatted.
- `uv run mypy claude_bully`: no issues in 96 source files.
- `uv run pytest -q -W error`: 7341 passed, 5 skipped, 5 deselected (was 7330, plus 11 new).
- `uv run pytest -q -m slow`: 5 passed.

## Files changed
- `claude_bully/environments/runtime.py`
- `claude_bully/runner/env_turn.py`
- `claude_bully/runner/runner.py`
- `tests/test_attempt_marker.py` (new)
- `HANDOFF.md`
- `docs/00-RECONCILED.md`
- `docs/02-ENVIRONMENTS.md`
- `docs/superpowers/specs/2026-10-24-phase-3-world-generator-design.md`

## Self-review
- Completeness:
  - every Produces item is present;
  - `runtime.load()` runs in `__init__`, so `state.watched_through` in `prime` is the saved one, which the harvest and generator roles need later.
- Behavior: a bully that dies at a rate-limit pause is handled the same way as a target. Its marker at index k has a pause marker at k, which is not a bully line, so the attempt is dead and the redo is k+1. This mirrors the tested target rate-limit case.
- Quality:
  - `marker is not None and dead` is redundant logically, but mypy needs it for narrowing; this is the brief's code;
  - `prime` reads the trigger stream once more only when something was dropped or a marker is dead, which costs nothing measurable.
- Plain runs: `self.env is None` skips the bully marker, and the target marker is only in `EnvironmentSession`, so the golden files are unaffected (the gate confirms it).
- YAGNI: there is no harvest or generator wiring.

## Concerns
- HANDOFF's Progress line reads "(807bddf..Task 1 commit)" because the SHA cannot be known before the single commit. The controller or ledger can write `0ade95e` into it.
- The brief's file list omits `docs/02-ENVIRONMENTS.md` and the spec file. Both were touched per the controller's docs-sync rulings.

## Fix round 1

Finding: the P29 amendments section was incomplete. Fixed in commit `2134d92` "docs: complete the spec's as-planned amendments from the Plan Decisions". It is a second commit; nothing was amended.

What changed:
- The spec section `## As planned (amendments from the implementation plan)` is rewritten:
  - it opens by naming the plan's "Plan Decisions" section as the authoritative full text;
  - it then gives one entry per Plan Decision that changes, narrows or contradicts the spec, in plan order. Some entries are split into sub-bullets for readability.
- All 36 Plan Decisions (plan lines 15-55) are covered. The generator-role ruling keeps only the parts the spec lacks: the `GeneratorConfig.model` override, the refusal on any target's `(provider, model)`, and `RateLimitError` as `error`. The rest of it restates spec section 6.
- Every entry was checked against the plan's wording. For example, `premise_density` is measured on the "share of body word tokens covered by premise-term matches".
- The seven earlier items are kept, merged into their plan-order entries.
- `HANDOFF.md`: "(807bddf..Task 1 commit)" is now "(807bddf..0ade95e)" (line 90 in the current file).

Covering check: no `tests/test_docs*.py` exists, so the check was `uv run pytest -q -W error`:
```
7341 passed, 5 skipped, 5 deselected in 445.70s (0:07:25)
EXIT 0
```
Both files were checked to be LF (0 CR bytes).
