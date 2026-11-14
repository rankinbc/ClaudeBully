# Phase 5 Task 1 report: records and the bundle

Status: DONE. Commit 262b8a2 on 97102a0: "feat: Phase 5 Task 1, the plan's records, hash_tree and the bundle's path grammar (schema v3, additive)".

## What was implemented

- `claude_bully/environments/world.py`: `hash_tree(root, exclude=())`, which holds the old `world_hash` body over `root`. It skips a file whose root-relative posix path has its first segment in `exclude`. `world_hash(world)` is now `hash_tree(world.root)`.
- `claude_bully/records.py`: `PlanStamp(slug, personas={}, expected=None)` (strict), and `RunRecord.plan: PlanStamp | None = None` after `world_hashes`, with the comment the brief gives.
- `claude_bully/planner/request.py` contains:
  - `Scope`, `SCOPES` (seven, in order), and `DEFAULT_ROLES`, a read-only mapping. `target`, `bully`, `judge` and `reviewer` are `claude_code` `sonnet`; `planner` is `claude_code` `opus`; `display_name` keeps its default.
  - `PlanBudget` (18/3/12/None, each `ge=1`).
  - `PlanRequest`: spec section 4's table, `extra="forbid"`. Each role default is a deep copy of `DEFAULT_ROLES`. `question` is stripped and refused when blank. `slug`, when given, must fullmatch `[a-z0-9][a-z0-9-]{0,47}`.
  - `parse_budget`, `load_plan_request` (through `load_yaml_model`), `SLUG_MAX`, `WINDOWS_DEVICE_STEMS`, and `slug_for`, the brief's body verbatim.
  - It imports nothing from `records.py` or `bundle.py` (review I7).
- `claude_bully/planner/records.py` contains:
  - `PLAN_SCHEMA_VERSION = 1`, `Stage`, `STAGES`, `PlanStatus` and `ManifestKind`.
  - `ManifestEntry`, `DirectorCall` (`attempts: Literal[1, 2]`), `StageRecord`, `DirectorAttempt`, `LintRecord` (classmethod `of`), `DryRunCell`, `Expectation` (`event: EventType`), `CellExpectation`, `ExpectedEvents`, `ReviewFinding` and `PlanRecord`. `PlanRecord` adds `base_files` and `base_premise_terms` beside `base_worlds`, and `rounds` after `stages`.
  - Every model is `extra="forbid"`. Every list and dict defaults empty. Every `X | None` field defaults None (preflight Q4). `open_blocks` defaults 0 and `status` defaults `"planned"`.
  - `read_plan_record` refuses an integer `schema_version` below 1 with the brief's message, then validates.
- `claude_bully/planner/bundle.py` contains:
  - The constants, `HASH_EXCLUDES`, `FIXED_FILES`, `NAME` and `_GRAMMAR` (verbatim). `WINDOWS_DEVICE_STEMS` is imported from `request.py`.
  - `BundlePathError(ValueError)`, `normalize_text` (drops a leading BOM, turns CRLF and lone CR into LF), `kind_of` and `world_of`.
  - `Transcript` and `TranscriptAttempt`, both strict.
  - `committed_outputs`: `plan` maps to `plan.md`; `file:`, `repair:` and `revise:` map to `json.loads(reply)["content"]`; the result is normalized. A call with no outputs gives `{}`. A purpose that does not give `call.outputs`' paths raises `ValueError`.
  - `Bundle`, a frozen dataclass with the full interface the brief lists, and `bundle_hash`.
  - `check_path` does three things in order. It fullmatches the grammar and refuses any named group that is a device stem. It then walks each component from the root down to the file and refuses `is_symlink()` or `os.path.isjunction` with "the path runs through a link". Last, it refuses a path that resolves outside `root.resolve()`.
  - `write_file` normalizes, calls `write_atomic`, and returns the sha256 of the text as written.
  - `index()` lists only grammar paths, sorted, each with the sha256 of its bytes.
  - `write_manual` checks the path first. It appends to the last stage when that stage is `stage` and open, or opens a new one. It then writes the transcript (one attempt, an empty message, reply `{"content": text}`), appends the call, writes the record, and writes the file last.
- `.gitignore`: the three lines, under the brief's comment.

## Tests and results

- `tests/test_plan_records.py` and `tests/test_bundle.py` are verbatim from the brief, then run through `ruff format`. I added one test, `test_a_path_through_a_junction_is_refused`, which runs only on win32 and creates a junction with `_winapi.CreateJunction`. The symlink test skips on this machine because it has no privilege, so without the new test nothing would cover the `os.path.isjunction` branch. A scratch check confirmed that on 3.12 a junction gives `is_symlink() False` and `isjunction True`, so the junction test fails whenever that branch is missing.
- Focused run: 87 passed, 1 skipped. The skip is the symlink test (no privilege).
- World hashes printed by the brief's command: overlay `e9ca0811...7a36`, mini `6e9f02a7...5a17`, annex `e72358fb...372d`. All three equal the Plan Decisions' hashes at 38dcc70.
- Gate:
  - `ruff format --check .`: clean (319 files).
  - `ruff check .`: clean.
  - `mypy claude_bully` and `mypy --platform linux claude_bully`: both clean (122 files).
  - `pytest -q -W error`: 9912 passed, 10 skipped, 48 deselected in 12:04. That is +87 passed and +1 skipped against 9825/9.
  - `pytest -q -m slow`: 48 passed.
- Some tests read `docs/` and `HANDOFF.md`, and I edited docs while the full run was going. After the edits I re-ran those modules (`test_hypotheses`, `test_replay_parser`, `test_corpus`, `test_progression`, `test_sanctuary`, `test_pause_marker_pin`, `test_phase3_minors`, `test_store`, `test_records`, `test_real_names`) together with the two new modules.

## RED, then GREEN

- RED: `uv run pytest tests/test_plan_records.py tests/test_bundle.py -q` failed at collection:
  - `ImportError: cannot import name 'hash_tree' from 'claude_bully.environments.world'`
  - `ModuleNotFoundError: No module named 'claude_bully.planner.records'`
- GREEN: after the implementation, 86 passed and 1 skipped; then 87 passed and 1 skipped once the junction test was added.

## Files changed

- `claude_bully/environments/world.py`
- `claude_bully/records.py`
- `claude_bully/planner/request.py` (new)
- `claude_bully/planner/records.py` (new)
- `claude_bully/planner/bundle.py` (new)
- `.gitignore`
- `tests/test_plan_records.py` (new)
- `tests/test_bundle.py` (new)
- `docs/00-RECONCILED.md`:
  - section A: the `PlanRequest` row extended, a `PlanBudget` row added;
  - section B: `RunRecord.plan` and a "plan.json (plan schema 1, apart from the run schema)" heading with the plan records and the bundle;
  - section H: "Phase 5 (version 3, additive): `RunRecord.plan` (`PlanStamp`)".
- `docs/superpowers/specs/2026-11-14-phase-5-director-design.md`: "As planned" gains Task 1's three lines (D-base_files with D-rounds and Q4, D-write_file, the slug ruling).
- `HANDOFF.md`: a Phase 5 bullet under Progress, with Task 1 and the gate counts.

## ASSUMED

- ASSUMED: The preflight's "Controller rulings" section is empty, so I applied each recommended ruling of a row that names Task 1. Q4: every `X | None` field of `planner/records.py` defaults None. Q57 needed nothing beyond Q4. Q10 (TurnEntry) belongs to Task 2 and has no counterpart here.
- ASSUMED: `PlanRequest.slug` also refuses a Windows device stem, besides the brief's regex. A `--slug con` would otherwise make `plans/con/`, which Windows opens as a device. This follows the D-write_file reasoning.
- ASSUMED: `kind_of` and `world_of` raise `BundlePathError` for a path outside the grammar instead of returning None. None stays reserved for `plan.md` and `review.md` (and for `world_of` outside `worlds/`), which is fail-closed.
- ASSUMED: transcript paths have their own closed grammar, `transcripts/[round-<n>/|failed/]<stage>-<role>-<index>.json`, and the same link and escape check. The round and failed forms are the ones D-rounds and D-failed-stage name, so Tasks 7a and 9 can read archived transcripts without changing Task 1's code.
- ASSUMED: `Transcript`'s fields have no defaults, exactly as the brief's signature shows. Q4 covers `planner/records.py` only.
- ASSUMED: `committed_outputs` normalizes the text it returns, so a CRLF reply re-materializes to the bytes `write_file` hashed (Review Focus 2). The manual transcript keeps the text as given.
- ASSUMED: `read_file` decodes the bytes on disk with no newline translation, so `sha256(read_file(rel))` equals `index()[rel]` even for a CRLF file an owner edited.
- ASSUMED: `remove_file` treats a missing file as no error, so resume stays idempotent.
- ASSUMED: `Bundle.create` makes the directory and does not validate the slug. Slugs come from `slug_for` or a validated `PlanRequest`.
- ASSUMED: `docs/08-DIRECTOR.md` is left unchanged. Its Inputs list is the original design text, and neither the brief's Step 5 nor the dispatch names it for this task.

## Concerns

- The symlink test skips on this machine, as the brief allows. The new junction test covers the Windows link branch. The `is_symlink` branch runs only where symlinks can be made, such as Linux CI.
- `committed_outputs` trusts that a transcript's `content` is a string. A non-string raises a raw `AttributeError`, not a named error. Transcripts are written only by the harness after its checks, so I left it alone.
- The suite's first test spends about 2.3 s in setup. That is the session fixtures, not the test itself, so I did not mark anything slow.
