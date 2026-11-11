# Phase 4 Task 1 report: records, roles and resume plumbing

Status: DONE_WITH_CONCERNS (minor; see Concerns)
Commit: a270855 (BASE 9cf1dd2), author rankinbc1@gmail.com, not pushed.

## What changed, per item

- `claude_bully/records_env.py`: `HarvestKind` holds eight kinds; `HARVEST_KINDS` keeps six; `PW_HARVEST_KINDS = ("completion", "taste")` and `ALL_HARVEST_KINDS` new (V7). `QuirkAttempt` gains `prompt_turn`, `family` (default None) and a docstring. `ChainOpenedBy` new; `ChainLink` gains `classifier` ("heuristic"), `confidence` (1.0), `fallback_failed` (False), `pressed` (False), `opened_by` (None). New `ContradictionPair` (`type: "contradiction"`, validator `turn_a < turn_b == turn`), added to `TriggerStreamRecord` after `ChainLink`. `GeneratedDoc.origin: Literal["generator", "twin"] = "generator"` after `unlock_rung`. All as the brief's blocks.
- `claude_bully/environments/config.py`: `GeneratorConfig.periodic: bool = True` after `max_docs`, with the brief's comment (V24).
- `claude_bully/environments/corpus.py`: `UnlockState.checksum_open_turn: int | None = None`, `contradictions_degraded: list[int]` after `harvest_degraded`.
- `claude_bully/environments/runtime.py`: `AttemptRole` and `AFTER_TURN_ROLES` gain `chain`, `contradictions`, `twin`; `AttemptMarker.written` docstring names the after-turn roles.
- `claude_bully/providers/ledger.py`: `ROLES` gains the three before `responder`; `_ROLE_WORDS` maps each to itself.
- `claude_bully/runner/store.py`: `WATCH_TYPES = frozenset({"quirk", "chain", "contradiction"})` beside `GENERATION_TYPES`; `keep_record` drops `GENERATION_TYPES | WATCH_TYPES` lines of an unwritten turn; module and function docstrings name the watch's records.
- `claude_bully/environments/generator.py`: `MATERIAL_KINDS` gains `completion: (leaked_manifest,)`, `taste: (config_diff,)`; `eligible_items` leaves out `PW_HARVEST_KINDS`; `fire_requests` returns before the periodic branch when `not config.periodic`; module docstring gains a sentence for each, `fire_requests` docstring one clause (V6, V24).
- `claude_bully/runner/env_turn.py`: `EnvironmentSession.prime` runs `drop_uncommitted_generation` for every session (the `generator.prime` guard stays); docstring says the watch's records go too and a torn last trigger line of any session is now dropped and counted (V5, M14).
- `tests/test_records_env.py`: `ALL_STREAM` gains the `contradiction` entry after `chain`; the union test is `..._eleven_stream_types` with 11 (M10).
- `tests/test_poisoned_well_records.py`: the brief's 13 tests (formatted; imports collected at the top).
- Docs-sync: `docs/00-RECONCILED.md` sections A (`EnvironmentConfig` generator `periodic`, `UnlockState` fields), B (`GeneratedDoc.origin`, `HarvestItem` kinds, `QuirkAttempt`, `ChainLink`, `ContradictionPair` now "triggers file", C4), H (a "Phase 4 Task 1 (version 3, additive)" bullet, and the v2 stream list names `ContradictionPair`); spec "As planned" gains Task 1's rulings V5, V6, V7, V24; HANDOFF Progress gains a Phase 4 bullet with Task 1 and the counts.

## RED evidence

1. Before any implementation: `uv run pytest tests/test_poisoned_well_records.py tests/test_records_env.py -q` failed at collection, both files: `ImportError: cannot import name 'ContradictionPair' from 'claude_bully.records_env'` ("2 errors during collection").
2. With the records, roles, store and generator changes in but `env_turn.py` unchanged: `1 failed, 70 passed`, the failure `test_a_torn_last_trigger_line_is_dropped_in_a_session_with_no_generator` with `json.decoder.JSONDecodeError: Unterminated string ... '{"type": "trigger", "id": "trig-9'` (the no-generator session kept the torn line, so reading the stream failed). Green after the `prime` change.
3. The first full gate run found `tests/test_sanctuary.py::test_every_state_field_is_rebuilt_on_resume_or_saved_with_its_turn` failing (`set(UnlockState.model_fields)` gained the two new fields); fixed as Deviation 2.

## Gate (at a270855's tree)

- `uv run ruff format --check .`: 277 files already formatted. `uv run ruff check .`: all checks passed.
- `uv run mypy claude_bully` and `uv run mypy --platform linux claude_bully`: no issues in 110 source files.
- `uv run pytest -q -W error`: 8498 passed, 9 skipped, 8 deselected (BASE 8483; +15 = the 13 new tests and 2 parametrized `contradiction` cases in `test_records_env.py`), 0 warnings.
- `uv run pytest -q -m slow`: 8 passed.
- Golden plain fixtures untouched (no fixture file in the diff). `SCHEMA_VERSION` unchanged at 3. All touched files LF.

## Deviations

1. `claude_bully/analysis/replay.py` (not in the brief's file list): `_other`'s parameter type gains `ContradictionPair`, and the import. Reason: adding the record to `TriggerStreamRecord` made `mypy` fail (`replay.py:416`, arg-type), since `_other` is the fallthrough for later-phase records. The replay prints `CONTRADICTION {...}` through the generic line until the task that gives it a layout (plan's File Structure: replay gains QUIRK, CHAIN, CONTRADICTION lines).
2. `tests/test_sanctuary.py` (not in the brief's file list): `test_every_state_field_is_rebuilt_on_resume_or_saved_with_its_turn` lists `checksum_open_turn` and `contradictions_degraded` under `with_its_turn`. Reason: the test requires every new `UnlockState` field to say which class it is; the brief's comment says both are "saved with the turn's records".
3. The brief's test block had two import lines out of order and a duplicate `claude_bully.enums` import, and listed the last test's imports separately; they are merged at the top of the file. `STREAM` is annotated `TypeAdapter[TriggerStreamRecord]`. No behavior change.
4. The first full gate run used `-p no:cacheprovider` by habit; the recorded run (the second) is the exact gate command.

## Concerns

- The new fields are read by nothing but the tests yet (as the brief says). `checksum_open_turn` and `contradictions_degraded` are classed "saved with its turn"; the later tasks that set them must save them with the turn's records, or the sanctuary test's classification is wrong.
- `HarvestKind` now admits `completion` and `taste` everywhere it is used as a type (`harvest.py` templates, the fallback's answer type). The LLM pass's schema and `_parse_items` still read `HARVEST_KINDS` (six), so they are never produced there; only a later Poisoned Well task should create them.
