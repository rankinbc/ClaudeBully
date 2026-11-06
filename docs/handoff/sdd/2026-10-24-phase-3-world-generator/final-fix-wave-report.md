# Phase 3 final-review fix wave: report

Base: e12eaee (build/v1, clean); commit a7f7732 (rankinbc1@gmail.com), not pushed. Method: fixtures and tests first (20 new or changed cases, all RED at HEAD, nothing else failing), then the code; one commit. Scratch files only under the session scratchpad's `impl-fixwave\` (`probe.py`, a classifier probe of the candidate fixture sentences at HEAD; `red.txt`; `gate.txt`).

## Per item

### 1. I1: the judge caches are not crash-safe

Changed `claude_bully/metrics/judge.py` `JudgeCache` itself, so every cache gets it (the judge, the trigger fallback, the idle fallback, the harvest and the generated cache):

- `put` writes the entry through `tempfile.mkstemp` in the cache directory and `os.replace` over the target, with the 20 x 50 ms `PermissionError` retry `runtime._write_atomic` and `mcp_server._replace` use (a reader briefly holding the file on Windows). A kill inside `put` leaves the old entry whole, or none, never a torn one.
- `get` returns `None` (a miss, asked again and rewritten) on `FileNotFoundError`, on any `ValueError` (a torn or damaged file; `UnicodeDecodeError` is one) and on JSON that is not an object. Before, it was a bare `json.loads` that raised on every later run under the same runs root until the file was deleted.
- A class docstring says why.

Tests, one per cache that a torn entry is a miss, the provider is asked once and the entry is rewritten valid:

- the judge: `tests/test_judge.py::test_a_damaged_cache_entry_is_a_miss_and_is_asked_again` (a `judge_capture` entry cut mid-file, plus the unit rules: a missing, torn, non-UTF-8, non-object or empty file is a miss);
- the kill case: `tests/test_judge.py::test_a_kill_between_the_temp_write_and_the_rename_leaves_the_old_entry` (`os.replace` raises inside `put`; the old entry is still read and still valid JSON on disk; a later `put` succeeds);
- triggers: `tests/test_triggers.py::test_a_damaged_cache_entry_is_a_miss_and_is_rewritten`;
- harvest: `tests/test_harvest.py::test_a_damaged_cache_entry_is_a_miss_and_the_judge_is_asked_again` (item 2 below);
- generated: `tests/test_generator_writer.py::test_a_damaged_cache_entry_is_a_miss_and_is_written_again` (a torn `<cache_key>.json`; the fire is `written`, the writer asked twice, the entry valid after commit, and the next fire over the same cache is `cached` with no call);
- idle: `tests/test_idle.py::test_a_damaged_cache_entry_is_a_miss_and_the_judge_is_asked`.

### 2. Task 4 M3: a corrupt harvest entry raised out of `harvest`

Closed by item 1 (`get` returns `None`). Pinned by `tests/test_harvest.py::test_a_damaged_cache_entry_is_a_miss_and_the_judge_is_asked_again`: the torn entry is a miss, the judge is asked once, the turn is not `degraded`, the LLM item lands beside the heuristic one and the entry is rewritten.

### 3. The ruled Task 3 batch (`claude_bully/planner/second_person.py`), closed lists only

Fixtures first: `_SP7` in `tests/test_lints.py` (14 cases, fed to `test_each_lint_on_its_fixture` like `_SP4` to `_SP6`), each rule with the billboard failing and the legitimate near-miss passing. At HEAD, 9 of the 14 disagreed (the billboards passed, and the two reduced conditionals failed); the 5 near-misses already passed, as `probe.py` confirmed before the fixtures were written.

- "come back to you" under a licence (the breaker-fix regression, Important): `_object_ok`'s to/back branch now fails when the clause holds a form of "come" (`_COME`) and "back" and no office subject (`_OFFICE`: we, staff, team, office), as round 5 did. Billboards: "...the faces in it may take a while to come back to you.", "Write down any songs that start to come back to you, ...". Near-misses: "We will come back to you within two working days ...", "Staff will come back to you with a date ...".
- `_STAFF` vehicle nouns: taxi, bus, minibus and ambulance dropped; the list is persons only, as every doc line says. Billboards: "...the weeks before the ambulance to the ridge.", "...on the day of the bus to the campus.". Near-miss: "...until the driver from the taxi rank arrives." (a person head is still excused).
- "If needed/preferred you can": `_reader_veto`'s verb-before-"you" rule no longer reads a past form after a subordinator (`_REDUCED`: if, when, whenever, unless, once, while, where, until, as) as taking "you" for its object; the relative pronouns stay out of that list, so "who/that <verb> you" keeps its object reading. Near-misses: "If needed you can ask for a wheelchair at reception.", "If preferred you can pay the monthly invoice by card.". Kept positive: "...the name of the nurse that admitted you on the first night.".
- Comparative without "than": `_compared` reads a closed `_COMPARATIVES` list (more, less and -er forms not already in `_COMPARE`). Billboards: "If the corridor seems longer now, ...", "The street may seem quieter now, ...", "The lounge may feel more like home ...". Near-miss: "The garden may seem quiet on weekdays, ...". The ruled trade stands: "the ward may seem quieter at weekends" now costs one retry.
- The two docs inaccuracies: (a) "a person after 'until' or 'since'" in the module docstring, the role-test comment, docs/08 and HANDOFF is true now that `_STAFF` holds persons only (no doc line changed); (b) docs/08's "the names that come back to you" among the object-rule failures is accurate now that the class is closed again. The module docstring (4c) and the role-test comment name the three new rules in one clause each.

No open verb class was widened; `PROCEDURAL_VERBS`, `TRANSACTIONAL_VERBS`, `_OBJECT_VERBS` and `_TO_VERBS` are untouched.

### 4. Task 3 N5: a quote holding a sentence end yielded a span the document lacks

`_addressed` now reads a `_blanked` copy of the text (quoted spans and `>` lines made spaces of the same length, so every offset is the document's), over the original text's paragraph bounds (`_paragraphs`), and hands each "you" sentence the document's own text at its offsets. `_source` keeps its exact and containing match against the originals and falls back to that held text instead of the unquoted sentence. `classify` then skips a source that contains, or is contained in, a sentence already reported, so the sentence is one result. The retry message never names text the generator did not write.

Test: two cases added to `tests/test_lints.py::test_second_person_reports_a_quoted_sentence_once` (a memo with `"shuts at six. Nobody minds"` inside the sentence; a FAQ with `"mind the gap. Mind the step"`), each one result whose span is in the body. At HEAD both reported `Dag told you the gate   and left.` or `The sign says   and you know who you are.`, which the documents lack (the second also reported twice).

### 5. Staff-addressed memos fail

One sentence added to the Billboard row of docs/08-DIRECTOR.md's Validation table: a memo that addresses the staff in the second person, outside quoted speech, a `>` line or a sign-off, fails like any other and is rewritten in the third person, a known cost of failing closed.

### 6. `lints.py` `_WORD` lacks `Final`

`_WORD: Final = re.compile(...)` in `claude_bully/planner/lints.py`.

### 7. m7: the runtime docstring overclaimed the marker

`claude_bully/environments/runtime.py` module docstring: "Before a target, bully, harvest or generator call the runtime names it in attempt.json (mark_attempt); the trigger fallback, the idle fallback and the authority responder are provider calls it does not mark."

### 8. m8: the harvest docstring named one residual

`claude_bully/environments/harvest.py` module docstring now names both: the context residual, and a report two or more sentences after the claim, since the report check reads the next sentence only.

### 9. m6: the plan's Decisions list was stale on the harvest span

`docs/superpowers/plans/2026-10-24-phase-3-world-generator.md` line 43 now says the span is the whole sentence trimmed of surrounding whitespace and a trailing `.` or `!` (a `?` kept), as the spec amendment and `harvest.py` say, and notes the earlier clause rule as the pre-fix one. The plan's Task 4 code block (line 1772) still carries the old docstring text; it is the historical block the task was built from and was left as is.

### 10. m4: duplicate stem line

`"figures figured"` dropped from `_SPEECH_STEMS`; `"figure figures figured figuring"` stays, so `_SPEECH_FORMS` is unchanged.

### 11. m1: `GeneratorFactory` fell through to a real provider for the judge role

`tests/fixtures/generator_stub.py`: a `JUDGE_MODEL` role with `judge=None` raises `RuntimeError("the judge role (...) reached GeneratorFactory with no double; pass judge=HarvestJudge(...)")`. Test: `tests/test_generator_run.py::test_the_factory_refuses_the_judge_role_with_no_double` (raises without a double; hands back the double with one).

### 12. m5: `EnvironmentSession.prime` read the trigger stream twice

`claude_bully/runner/env_turn.py` `prime` reads the trigger records once, before the resume check, uses them for the "already flagged" test, appends the `ResumeRecord` it writes so the list is the stream as it stands, and primes the runtime and the generator from it. Test: `tests/test_attempt_marker.py::test_prime_reads_the_trigger_stream_once` (a rep whose bully died at turn 2 is resumed; `RunStore.read_trigger_records` is counted inside `prime`: exactly one read, and the resume record is written as before).

### 13. m3: the writer prompt listed the pair's own buried document as already reachable

`claude_bully/environments/generator.py`: `writer_prompt` takes `own`, the fire's documents written so far, and leaves them off "Documents the reader can already reach"; the plan's `links` still names the buried target with its title and address. `DocWriter.write_fire` passes the ids of the documents written so far through `_attempts`. Test: `tests/test_generator_writer.py::test_the_seam_pointer_s_prompt_lists_its_target_as_a_link_only` (the seam prompt's reachable list holds an anchor and not `gen-3-1`; `gen-3-1` is among the plan's links; the buried prompt never lists it either).

## RED evidence

Before any code change, over the eight covering modules (`uv run pytest -q -W error tests/test_lints.py tests/test_judge.py tests/test_triggers.py tests/test_harvest.py tests/test_idle.py tests/test_generator_writer.py tests/test_generator_run.py tests/test_attempt_marker.py`): `20 failed, 3328 passed in 25.04s`, the 20 being exactly the new cases:

```
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-245]   (come back to you, modal)
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-246]   (come back to you, "start to")
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-249]   (ambulance)
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-250]   (bus)
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-252]   (If needed you can)
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-253]   (If preferred you can)
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-255]   (seems longer now)
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-256]   (seem quieter now)
FAILED tests/test_lints.py::test_each_lint_on_its_fixture[second_person-257]   (feel more like home)
FAILED tests/test_lints.py::test_second_person_reports_a_quoted_sentence_once[internal_memo-... "shuts at six. Nobody minds" ...]
FAILED tests/test_lints.py::test_second_person_reports_a_quoted_sentence_once[family_faq-... "mind the gap. Mind the step" ...]
FAILED tests/test_judge.py::test_a_damaged_cache_entry_is_a_miss_and_is_asked_again
FAILED tests/test_judge.py::test_a_kill_between_the_temp_write_and_the_rename_leaves_the_old_entry
FAILED tests/test_triggers.py::test_a_damaged_cache_entry_is_a_miss_and_is_rewritten
FAILED tests/test_harvest.py::test_a_damaged_cache_entry_is_a_miss_and_the_judge_is_asked_again
FAILED tests/test_idle.py::test_a_damaged_cache_entry_is_a_miss_and_the_judge_is_asked
FAILED tests/test_generator_writer.py::test_a_damaged_cache_entry_is_a_miss_and_is_written_again
FAILED tests/test_generator_writer.py::test_the_seam_pointer_s_prompt_lists_its_target_as_a_link_only
FAILED tests/test_generator_run.py::test_the_factory_refuses_the_judge_role_with_no_double
FAILED tests/test_attempt_marker.py::test_prime_reads_the_trigger_stream_once
```

After the code: the same eight modules `3348 passed` (one adjustment on the way: the m3 test first asserted the seam's links were `["gen-3-1"]` alone, but the planner also links an anchor (`canteen-menu`); the assertion became "gen-3-1 is among the links", which is what the item pins).

## Concerns

- `second_person.py` is 1185 lines (`wc -l`), over the 1141-line ceiling Task 3's breaker brief set. The fix wave's items (N5's offset-preserving source, four closed rules, their docstring lines) are the whole growth; nothing else was added. The N7 ruling (the Phase 7 LLM-lint decision settles whether the module shrinks or is replaced) stands.
- `JudgeCache.put` carries its own copy of the Windows `PermissionError` retry loop (the third beside `runtime._write_atomic` and `mcp_server._replace`); `judge.py` cannot import either without a cycle, and a shared helper module was outside this wave.

## Gate (every step 0 warnings)

```
== uv run ruff format --check .
251 files already formatted
== uv run ruff check .
All checks passed!
== uv run mypy claude_bully
Success: no issues found in 103 source files
== uv run pytest -q -W error
8181 passed, 5 skipped, 6 deselected in 520.88s (0:08:40)
== uv run pytest -q -m slow
6 passed, 8186 deselected in 166.98s (0:02:46)
```

The full `pytest -q -W error` ran in the foreground of the session (the harness moved it to a background slot after 180 s on its own; it was waited on, not re-run, and its full output is in the scratchpad's `gate.txt`). Against the review's baseline the suite grew from the 20 new or changed cases (14 `_SP7` fixtures, 2 N5 cases, 7 cache and minor tests).
