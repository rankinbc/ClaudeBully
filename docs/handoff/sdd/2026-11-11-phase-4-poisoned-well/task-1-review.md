# Phase 4 Task 1 review: records, roles and resume plumbing

Commit a270855 on base 9cf1dd2. Reviewer read the brief, the report, the preflight rows the brief cites, the diff, the surrounding code (`runner/store.py`, `runner/env_turn.py`, `environments/runtime.py`, `providers/ledger.py`, `analysis/replay.py`) and the plan tasks that consume these interfaces (4, 6, 7, 8).

## Verdicts

- Spec compliance: every brief item met; the two out-of-brief edits are deviated-acceptably (correct, and forced).
- Quality: Approved with minors.
- Findings: Critical 0, Important 0, Minor 5.

## Spec compliance, item by item

| Brief item | Verdict | Evidence |
|---|---|---|
| `HarvestKind` eight kinds; `HARVEST_KINDS` six; `PW_HARVEST_KINDS`; `ALL_HARVEST_KINDS` | met | `records_env.py:224-238`; LLM schema (`harvest.py:80`) and `_parse_items` (`harvest.py:681`) still read the six |
| `QuirkAttempt.prompt_turn`, `family` (None) | met | `records_env.py:298-308` |
| `ChainOpenedBy`; `ChainLink.classifier/confidence/fallback_failed/pressed/opened_by` with the brief's defaults | met | `records_env.py:311-330` |
| `ContradictionPair`, `type: "contradiction"`, validator `turn_a < turn_b == turn`, in the union after `ChainLink` | met | `records_env.py:333-355`, union at `:381`; the validator is `not (a < b) or turn != b`, correct precedence |
| `GeneratedDoc.origin` after `unlock_rung` | met | `records_env.py:180` |
| `GeneratorConfig.periodic` after `max_docs`, with the comment | met | `config.py:161-163` |
| `UnlockState.checksum_open_turn`, `contradictions_degraded` after `harvest_degraded` | met | `corpus.py:112-116` |
| `AttemptRole`, `AFTER_TURN_ROLES` gain the three roles | met | `runtime.py:223-229`; `written` and `redo_turn` need no change (any role not target/bully is `watched_through >= turn`; `redo_turn` keys on `AFTER_TURN_ROLES`) |
| Ledger `ROLES` before `responder`; `_ROLE_WORDS` | met | `ledger.py:63-65`, `:81-83` |
| `WATCH_TYPES` beside `GENERATION_TYPES`; `keep_record` drops watch lines of an unwritten turn; docstrings | met | `store.py:56`, `:172` |
| `MATERIAL_KINDS`, `eligible_items`, `fire_requests` (`periodic`), docstrings | met | `generator.py:126-128`, `:210`, `:255` |
| `prime` runs the drop for every session; `generator.prime` guard stays; docstring | met | `env_turn.py:376-377`, guard at `:397` |
| `tests/test_records_env.py` eleven types | met | `ALL_STREAM` entry after `chain`, count 11 |
| `tests/test_poisoned_well_records.py` | met | 13 collected items (11 functions, one with 3 params) equal the brief's tests, imports merged (Deviation 3, harmless) |
| Docs-sync (docs/00 A, B, H; spec "As planned" V5, V6, V7, V24; HANDOFF) | met, one gap | see Minor 2 |
| Gate counts | met | +15 = 13 in the new file + 2 `contradiction` params in `test_records_env.py` (two `ALL_STREAM`-parametrized tests); reproduced below |

Out-of-brief edits:

- `analysis/replay.py` `_other` gains `ContradictionPair`: deviated-acceptably. Required by mypy (the fallthrough takes `TriggerStreamRecord` members); `_turn_of` reads `record.turn`, which for a pair is `turn_b`, so the record sorts under its later turn; `_other` prints `CONTRADICTION {...}`, `parse_replay_line` returns None for it as for `QUIRK`/`CHAIN` today. Nothing else matches exhaustively on record types (every analysis consumer filters with `isinstance`).
- `tests/test_sanctuary.py` classification: deviated-acceptably (required by the test; correct class, see "Downstream consistency").

## Probes and checks run (probes under `probes-task1/`)

- `probe_old_files.py`: the committed v3 smoke run (`docs/handoff/runs/rung0_smoke_env`, written before this commit): its trigger line round-trips byte-identically through `TriggerStreamRecord`; both `env_state.json` files load with `checksum_open_turn None`, `contradictions_degraded []`; both `attempt.json` files load. `probe_replay_old_run.py`: `replay_cell` and `load_run` on that run succeed.
- `SCHEMA_VERSION` is 3 (`enums.py:13`, file untouched). No file under `tests/fixtures`, `data` or `configs` is in the diff, so the golden plain fixtures are untouched; `tests/test_env_events.py` (the golden reader) passes. Plain runs never reach `EnvironmentSession.prime` or `GeneratorConfig`.
- `probe_resume_watch_records.py`: killed an env rep after its second target write, planted a `quirk` on the last written turn, a `chain` and a `contradiction` on a turn never written and a torn `contradiction` line; the resume kept the first, dropped the other three, and wrote one `ResumeRecord(turn=4, dropped={'rep0.triggers.jsonl': 3})`.
- `probe_marker_roles.py`: with `attempt.json` naming each of `harvest`, `generator`, `chain`, `contradictions`, `twin` on the written-but-unwatched last target turn, the resume writes exactly one `ResumeRecord(turn=<that turn>, dropped={})`; the three new roles behave as the two old ones; a `target` marker on a written turn writes none.
- Targeted runs: `tests/test_poisoned_well_records.py tests/test_records_env.py tests/test_sanctuary.py` (pass); `test_env_events, test_store, test_ledger, test_ledger_analysis, test_replay, test_replay_parser, test_harvest, test_generator_plan, test_generator_run, test_generator_runtime` (576 passed). `ruff check`, `ruff format --check` on the touched files and `mypy claude_bully` (110 files) clean. No CR in the diff.

## Review of the asked-about points

Additivity. Every new field has a default (`None`, `1.0`, `False`, `[]`, `"heuristic"`, `"generator"`, `True`); `QuirkAttempt`/`ChainLink`/`GeneratedDoc`/`UnlockState`/`GeneratorConfig` still read lines and files written before the commit (probe). The one non-additive element is the new union member, which a pre-commit reader would reject; no pre-commit code reads post-commit files and the phase rules say so. Old v3 `env_state.json`s adopt the new fields at their defaults through `_adopt`. A new `GeneratedDoc` line now carries `origin`; no golden compares generated lines.

Resume. Exactly as the brief rules and as Phase 3 does for `harvest`/`generator_fire`:

- dead attempt (a watch record of a turn no written target turn has): dropped and counted under `rep{k}.triggers.jsonl` in the `ResumeRecord`;
- torn last line: dropped for every environment session now (`_parsed_lines` yields None, `keep_record(None)` is False), counted; this also fixes what was a `JSONDecodeError` at `read_trigger_records` for a session with no generator (the report's RED 2);
- a watch record whose turn IS written but not yet watched (the kill-inside-the-watch case) is kept, as a `harvest` item is. That is correct for Task 1 and it is where "nothing written twice" now depends on Task 6: `PoisonedWellWatch.prime(records)` and `record_key` must skip the kept records (plan lines ~4030-4036 do: `("quirk", turn)`, `("chain", turn, k)` keys, and pair ids). Nothing writes these records yet, so nothing can be written twice by this commit; the unit test and my probe pin the drop, and Task 6/7's kill-in-the-fallback tests pin the dedupe.
- the drop is idempotent (`_keep_only` rewrites only when it drops), so a second resume drops nothing and writes no second `ResumeRecord`.
- `ContradictionPair.turn == turn_b` holds on construction and on read (`model_validate_json` runs the validator, so a hand-edited line raises loudly rather than being misfiled); the store and replay both read JSON `turn`, which is `turn_b`.

Roles. `role_of` reads the fourth segment of `<run>/<cell>/rep<k>/<word>`; the shapes in use today are `target`, `bully`, `trigger`, `idle`, `harvest`, `generator/<doc>/...`, `lint/<doc>/...`, `authority/<call>` (grep of every `conversation_id` constructor), plus `judge/<key>` and `doctor...` which are decided by prefix after the cell shape fails. None of `chain`, `contradictions`, `twin` is used by any of them, and a cell id cannot collide because the regex anchors the `rep<k>` segment third. The attempt roles use the same words as the ledger roles. `analysis/ledger.py` orders by `ROLES` and puts unknown roles last, so the insertion point before `responder` changes no existing output.

Downstream consistency (plan Tasks 4, 6, 7).

- `contradictions_degraded` as "saved with the turn" is right, and in fact the only possible class: a degraded turn leaves no record (spec failure table: heuristic pairs only, the turn joins the list; P54: a rewatch asks the judge again). Task 6's `_poisoned_well` appends after `watch.watch` returns and before `mark_watched`, and nothing saves the state in between (`runtime.save()` runs only in the tool rounds, `mark_watched` and `finish`), so a dead attempt cannot leak a value into `env_state.json`. See Minor 1 for the controller's carry, which asks for something that cannot be done for this field.
- `checksum_open_turn` as "saved with the turn" is accurate for the setter (set after the unlock record, before `mark_watched`, `turn not in` guard), and Task 6's `prime` additionally derives it from the recorded `checksum` unlock, which makes it behave as the Sanctuary class on resume. Either label passes the sanctuary test (it only checks membership), and no stale-value path exists: the unlock record is written before the setter, and `RungUnlock` lines are never dropped (`drop_uncommitted_generation` drops only `generator`-rung unlocks).

## Findings

### Critical
None.

### Important
None.

### Minor

1. Carry in `.superpowers/sdd/2026-11-11-phase-4-poisoned-well/progress.md:11` is unachievable for `contradictions_degraded` and imprecise for `checksum_open_turn`. It says each value must be "rebuilt on resume from the turn's written records". A degraded turn has no record, so Task 7 cannot rebuild it; the invariant to test is: value present after a kill following `mark_watched` (loaded by `_adopt`), absent after a kill before it (the rewatch recomputes it, asking the judge again per P54). For `checksum_open_turn`, Task 6's `prime` (plan line 4082) sets it from the recorded unlock but never clears a saved value; that is safe today (a saved value always has its unlock record) but Task 6 should state it, or derive in the sanctuary style (set or None). Failure scenario if left: the Task 7 implementer writes a derive-from-records test that cannot pass, or "fixes" it by inventing a marker record, which is a schema addition nobody ruled.
2. Docs-sync gap. `docs/02-ENVIRONMENTS.md:111` ("Resume (as built, Phase 3 Task 7)": roles `harvest` and `generator`, "the generator's lines of any turn never written") and the `ResumeRecord` row at `docs/00-RECONCILED.md:53` ("a `harvest` or `generator` marker") still describe the generator-only drop and two after-turn roles; `environments/runtime.py:11` ("Before a target, bully, harvest or generator call the runtime names it") likewise. The global constraint asks for any docs file naming the touched events. Scenario: a Phase 4 reader trusts the doc and expects a session with no generator to keep a torn trigger line.
3. Test depth. `test_a_generated_doc_defaults_to_the_generator_origin` (`tests/test_poisoned_well_records.py:119`) reads `model_fields[...]`, so it passes even if a line without `origin` failed to load or `"twin"` were rejected; a one-line `GeneratedDoc.model_validate` of an old-shaped dict and a `origin="twin"` round trip would pin it. The watch-record drop is covered at unit level and by the torn-line session test only; a session-level case (my `probe_resume_watch_records.py`) is not in the suite, but Task 6's kill tests are the natural home.
4. `GENERATION_TYPES | WATCH_TYPES` (`runner/store.py:172`) rebuilds a frozenset per record; a module constant (`DROPPED_WITH_THEIR_TURN`) reads better and costs nothing. Cosmetic.
5. `HANDOFF.md` progress bullet cites "9cf1dd2..the Task 1 commit" instead of the SHA (same style as earlier bullets, so consistent; fill in a270855 when the controller next edits it). Cosmetic.

## Notes for the controller

- The brief's ordering and wording were followed closely; the report's deviations list is complete and accurate (I found no unreported edit: the diff touches exactly the brief's files plus `replay.py` and `test_sanctuary.py`).
- Task 6 must make the watch skip already-recorded records on a rewatch (keys above) and Task 7's pair numbering (`c-<turn>-<n>`, heuristic first) must be stable under a rewatch whose judge now succeeds (heuristic ids unchanged, the judge's appended), or a kept `c-7-1` and a fresh `c-7-1` would both be written. The plan's P54 text implies this; its test is `test_a_rep_killed_in_the_contradiction_pass_resumes_to_the_unbroken_records`.
