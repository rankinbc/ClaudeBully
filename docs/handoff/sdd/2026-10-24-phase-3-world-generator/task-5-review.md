# Task 5 review: fire policy, planner, redaction, records, schema v3

Range: 9128cba..aa49c52 (one commit, authored by rankinbc1@gmail.com, trailer present).
Inputs: task-5-brief.md, task-5-carries.md, global-constraints.md, task-5-report.md, review-9128cba..aa49c52.diff.

## Spec Compliance: PASS

The production code is the brief's code. A whitespace-insensitive comparison of the brief's code blocks against
the committed files shows `claude_bully/environments/redact.py` is identical. `claude_bully/environments/generator.py`
differs only where `ruff format` re-wrapped two expressions (generator.py:270-272 and the joined string at :398).
The full fast gate in the implementer's log shows 8043 passed, 5 skipped and 5 deselected; the slow suite shows 5 passed; there are 0 warnings in `scratchpad/impl-task5/gate.log`.

File by file against the brief and the carries:

| File | Verdict | Notes |
| --- | --- | --- |
| `claude_bully/environments/generator.py` | PASS | Every constant, `FireRequest`, `CorpusView`, `item_age`, `eligible_items`, `consumed_items`, `committed_docs`, `fire_requests`, `DocPlanner`, `to_document` and `generator_problems` are present and match the brief verbatim. |
| `claude_bully/environments/redact.py` | PASS | Verbatim. |
| `claude_bully/records_env.py` | PASS | `Redaction`, `LintFailure`, `_OneAddress`, `DocPlan` (`address`, `quote`), `FireStatus`, `Rejection`, `GeneratorFire` and the new `GeneratedDoc` are present. `GeneratorFire` is in `TriggerStreamRecord` (diff 1111-1124). The module docstring now lists `datetime`. |
| `claude_bully/enums.py` | PASS | `SCHEMA_VERSION = 3`; the docstring notes v3. |
| `claude_bully/environments/config.py` | PASS | `GENERATOR_RUNG`, `PSEUDO_RUNGS`, the new `GeneratorConfig` fields and bounds, and the `LadderConfig` refusal are present. |
| `claude_bully/environments/world.py` | PASS | `FIRST_BUILD_KINDS`, `SLUG`, `WorldGeneratorSheet` and `WorldSheet.generator` are present. |
| `claude_bully/config.py` | PASS | `generator_role` and `_generator_is_not_a_target` are present. |
| `claude_bully/runner/store.py` | PASS | The docstring says v3 and the triggers line names `GeneratorFire`. |
| `claude_bully/analysis/replay.py` | PASS | The `GENERATOR` line, the reworked `GENERATED` line, `_KIND_ORDER` and the docstring are done. |
| `tests/fixtures/worlds/mini/world.yaml`, `data/worlds/overlay/world.yaml` | PASS | The two blocks are verbatim and placed after `premise_terms`. |
| `tests/test_generator_plan.py` | PASS with one deviation | The brief's tests are present. P32 imports are applied. P33(c) took a third path; see Minor 1. Two extra `CorpusView` tests were added. |
| `tests/test_redact.py` | PASS | Verbatim. |
| `tests/fixtures/generator_stub.py` (P32) | PASS | It holds `MINI`, `MINI_ITEMS` and `mini_view`, takes `WORLDS_DIR` from `tests.helpers` (the same path the brief used), and `test_generator_plan.py` defines no copies. |
| `tests/test_store.py` | PASS | The P23 builder gets the new fields, and `test_loaders_reject_schema_version_2` is added beside the v1 test. |
| `tests/test_records.py` | PASS | Both `== 2` assertions are now `== 3`. |
| `tests/test_records_env.py` | PASS | The P23 `datetime` allowance is in, the builder has the new fields, and the new records are added to the round-trip, union and extra-forbid lists. |
| `tests/test_replay.py` | PASS | The `GENERATED` expectation is reworked and the brief's `GENERATOR` test is verbatim; one extra `docs=[...]` test is added. |
| `tests/test_env_config.py`, `tests/test_config.py` | PASS | The tests cover new defaults, bounds, round trip, the reserved name, role precedence and the target refusal message. |
| `tests/test_runner_idle.py` | PASS | The docstring no longer says the version stays 2. |
| `HANDOFF.md` | PASS | It has Progress item 5 and the 8043/5 counts. Both carries are kept until Task 7. |
| `docs/00-RECONCILED.md` | PASS | Sections A, B and H are updated as the brief names. The line 7 intro edit is an extra, and it is justified because otherwise the intro would contradict the new heading for section H. |

Missing: none.
Extra: the section-H intro line in `docs/00-RECONCILED.md` (justified), and the extra tests (judged below; sound, not scope creep).
Misunderstood: none. P33(c) is a deliberate departure from the carry's literal "else drop" branch. It was reported, and it is judged under Minor 1.

### Cross-cutting checks (named risk, then the one focused check made)

- Risk: the schema bump to 3 breaks committed fixtures or goldens that carry `"schema_version": 2`. Check: grep for `schema_version` under `tests/fixtures` and `data`. Result: no fixture carries a version. Only `tests/test_store.py` writes a v2 line, and it does so on purpose. The goldens are unaffected. PASS.
- Risk: non-test code constructs `GeneratedDoc` with the old fields. Check: grep `GeneratedDoc(` across the repo. Result: only the three test builders, all updated. PASS.
- Risk: a consumer of `TriggerStreamRecord` breaks on the new member. Check: read each consumer named by grep. `runtime.note_records` (runtime.py:743) narrows by `isinstance` and ignores others. `replay._turn_of` (replay.py:228) reads `.turn`, which `GeneratorFire` has. `replay._record_block` gets the new branch before the `_other` fallback, and mypy strict passed. `store._TRIGGER_RECORD` uses the union adapter. PASS.
- Risk: the new `Experiment` validator refuses a shipped config. Check: grep `configs`, `data` and `tests/fixtures` yaml for an enabled generator. Result: none. PASS.
- Risk: the P33(c) claim that no drift moves the served date is false. Check: read `dating.world_at` (dating.py:739-751) and `ClockConfig.date_at` (config.py:130). `world_at` re-dates only to `clock.world_date` and sets `sheet.clock = clock`; `date_at` feeds the tool date only. The claim holds.

### CANNOT VERIFY

- That Task 7 passes `fire_requests` only `generate: true` rungs. The plan's Task 7 code does filter (plan line 5680), but that code is not in this diff.
- That Task 7 seeds `DocPlanner` with `GeneratorConfig.seed or experiment seed` and passes the plan index as "the number of plans recorded before". Resume-equivalence of a whole rep depends on it. This task only provides pure inputs.
- That Task 7 builds the planner on the served world (`world_at`), which `DocPlanner.start` relies on.

## Strengths

- Pure, seeded planning. Every draw is `Random(f"{seed}:gen:{index}:<facet>")` or a sha256 of the same key (generator.py `date_for`, `slug_for`, `address_for`, `author_for`). String seeding in `random.Random` is hashed with sha512, so it does not depend on PYTHONHASHSEED. Ties in `links_for` break on `d.id`. Given the same recorded inputs, a resumed process plans the same documents.
- The one-address rule lives once, in `_OneAddress` (records_env.py:69), and `DocPlan` and `GeneratedDoc` share it.
- P32 is done cleanly. The fixture module is small, documented, and import-only for the tests.
- The P33(c) analysis is correct, and it was reported plainly instead of being papered over.
- The extra tests pin code the brief's tests left unpinned:
  - `CorpusView.seam_open`, including the search-log-only case and a non-vacuity guard (`seam_ids and seam_ids <= view.visible`);
  - `with_documents`, where a buried document never becomes searchable;
  - the exact `DocPlan.quote` and `address` behavior;
  - both directions of the one-address rule on `GeneratedDoc`;
  - the `GeneratorFire` defaults and the closed `status` literal;
  - env-model-over-experiment-generator precedence;
  - the pinned refusal message;
  - "off is not asked";
  - `test_loaders_reject_schema_version_2` also pins "reads schema version 3 only".

  They are sound and stay inside this task's surface.

## Issues

### Critical

None.

### Important

1. Verbatim duplication of two rules (plan-mandated).
   - Where: `claude_bully/environments/generator.py:231-235` against `:400`, and `generator.py:214-217` against `claude_bully/environments/corpus.py:190-192`.
   - What is wrong, case 1: the authoring rule `not member.role.startswith(AUTHOR_EXCLUDED_ROLES)` is written twice. `DocPlanner.__init__` uses it to build `authors`, and `generator_problems` uses it to decide "no cast member can author a document".
   - What is wrong, case 2: the url branch of `_norm_address` (`address.strip().rstrip("/")`) re-implements `corpus._norm_url`, which keys `CorpusIndex._url_ids` (corpus.py:263).
   - Why it matters: `generator_problems` is the pre-run check that promises the planner will not raise. If the two copies of the authoring rule drift, a cell passes validation and then `DocPlanner` raises mid-run. The planner's `taken` set exists so that a generated url never shadows an anchor in the index's url map. If `_norm_url` ever changes (for example, by lowercasing the host), the collision check silently disagrees with the index, and one url maps to two documents (the dict keeps the later one).
   - Fix: add one module-level `_authors(world) -> list[str]`. Have `DocPlanner.__init__` and `generator_problems` use it (`if not _authors(world)`). In `_norm_address`, call the corpus normalizer (make it public, for example `corpus.norm_url`) instead of copying it. Also route the `http://`/`https://` test (generator.py:215 and :345) through one `_is_url` helper.

### Minor

1. P33(c): the test pins a real behavior, but its name and its drift half claim something it does not test.
   - Where: `tests/test_generator_plan.py:240-252`.
   - What it pins: `start == clock.world_date` on a world re-dated four weeks on, and `start != START`. This is real: it fails if `world_at` stops carrying the effective clock into `sheet.clock`, or if `DocPlanner` reads anything but the served sheet's date. It is a genuine improvement on the brief's version, which could not fail.
   - What it does not pin: drift. `start != drifted` can fail only if the planner called `date_at(3, ...)`, and the planner has no turn to call it with. `drifted != clock.world_date` checks the test's own setup, not the code. The name ("a drifting clock does not move the start") therefore describes a property this layer cannot exercise.
   - On the carry: its literal ruling for "no such drift" was to drop the test. Keeping it is defensible because it now pins something, but the name should say what that is.
   - Fix: rename it to `test_the_start_is_the_served_worlds_date` (the drift may stay as a harmless distractor) and leave the drift pin to Task 7's run-level test, as HANDOFF already says.
2. Duplicate tests across files.
   - Where: `tests/test_env_config.py:192` (`test_generator_defaults`, now extended) repeats `tests/test_generator_plan.py:315` (`test_generator_config_defaults`, brief-mandated). `tests/test_env_config.py:339` overlaps `tests/test_generator_plan.py:334`.
   - Why it matters: it is harmless, but two places must change when a default changes.
   - Fix: keep the near-name check in `test_env_config.py` and drop the repeated default and reserved assertions there.
3. Four hand-built `GeneratedDoc` builders (plan-mandated).
   - Where: `tests/test_generator_plan.py:381`, `tests/test_records_env.py:179`, `tests/test_replay.py:253` and `tests/test_store.py:245`.
   - Why it matters: each new required field means four edits, as this task just showed.
   - Fix: a `generated_doc(**overrides)` in `tests/fixtures/generator_stub.py`, which Tasks 6 and 7 will need anyway.
4. `GeneratorFire` has no cross-field validation.
   - Where: `claude_bully/records_env.py:113`.
   - What is wrong: nothing ties `rejection` to `status == "rejected"`, `error` to `status == "error"`, or a non-empty `doc_ids` to a committed status. `committed_docs` and `consumed_items` trust `status` alone.
   - Why it matters: a malformed fire written by Task 7 would be accepted and would skew the cap and consumption on replay.
   - Fix: add a small `model_validator`. It is not in the brief, so this is optional.
5. The `fire_requests` docstring reads as if it filters (plan-mandated).
   - Where: `claude_bully/environments/generator.py:182`.
   - What is wrong: "a pair for each `generate: true` rung in `opened` (the turn's recorded unlocks ...)" suggests the function filters, but it fires for every name it is given, including `sanctuary` or `generator` pseudo-rung unlocks.
   - Why it matters: the plan's Task 7 caller does filter. This is a contract-clarity issue, not a bug.
   - Fix: say "`opened`: the turn's newly opened rungs with `generate: true`".
6. Replay layout (plan-mandated).
   - Where: `claude_bully/analysis/replay.py:306` and `:308`.
   - What is wrong: lint messages are printed raw, so a newline in a message breaks the layout (the same class as the deferred harvest-span minor). `uses=a,b` and `docs=[a, b]` use different separators.
   - Fix: fold or escape the message, and pick one separator.
7. A v2 generated or triggers stream read on its own gets a pydantic error, not the friendly message (pre-existing design).
   - Where: `claude_bully/runner/store.py:47-55`.
   - What is wrong: `_checked` keys on a `schema_version` field that the records_env records do not carry. A v2 `rep{k}.generated.jsonl` read alone fails as "field required", not "schema version 2; re-run".
   - Why it matters: in practice the turns or run loader refuses first, so the global constraint holds at the run level.
   - Fix: none needed now. It is worth a line in the ledger.

## Assessment

Task quality: Needs fixes

The task matches the brief and carries, and the planner is deterministic and resume-safe given recorded inputs. The one Important finding is plan-mandated duplication of the authoring rule and the url normalizer. Either copy can silently drift away from the check that is meant to guard it, and the fix is a few lines.
