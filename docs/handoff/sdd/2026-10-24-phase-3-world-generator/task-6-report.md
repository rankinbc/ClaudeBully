# Task 6 report: the writer

Status: DONE. Commit 9f3fddc78ccb03d60994eac345e5ba71401ce706 on `build/v1` (on top of 2f17c02), authored by rankinbc1@gmail.com, with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer. Not pushed.

## What was built

- `data/personas/world_generator.md`: the generator's system prompt, transcribed from the brief, with rules 4 and 8 amended (see the carries below).
- `claude_bully/environments/generator.py`: the writer, appended after the Task 5 code. It adds:
  - the constants `GENERATOR_PERSONA`, `GENERATOR_SCHEMA`, `PROMPT_HEADER`, `PLAN_HEADING`, `FIX_HEADING`, `MAX_ATTEMPTS`, `CACHE_VERSION`, `CONTRACT`, `VERBATIM_IN_SEAM` and `MIN_QUOTED_WORDS`;
  - `FireOutcome`, `cache_key`, `transcript_prefix`, `parse_reply` and `writer_prompt`;
  - `DocWriter` with `write_fire` and `commit`;
  - new for the carries: `unwrap_body`, `LINE_KINDS`, `UNECHOED_LINTS`, `CachePut` and `_lint_failure`.
- `claude_bully/strategies/sheets.py`: `NON_PERSONA_FILES` gains `world_generator.md`, and its comment is updated.
- `tests/fixtures/generator_stub.py`: the writer stub is appended to the Task 5 module, which now holds `GENERATOR_MODEL`, `SEAM_TITLE`, `BURIED_TITLE`, `STUB_MUNDANE`, `plan_of`, `generator_reply`, `_completion` and `GeneratorStub`.
- `tests/test_generator_writer.py`: the brief's 17 test functions (19 cases, counting the parametrized ones), plus 5 new functions (8 cases), 27 cases in all.
- `tests/test_boundary.py`: `test_the_world_generator_persona_stays_inside_the_boundary` scans the persona file line by line.
- Docs: `HANDOFF.md`, `docs/02-ENVIRONMENTS.md` and `docs/00-RECONCILED.md`.

## Deviations from the brief, and why

1. **Import block merged, not replaced** (Task 5 carry). Kept: `norm_url` from `environments.corpus`. Added: `json`, `Callable`, `Any`, `NamedTuple`, `Speaker`, `redact`, `JudgeCache`, the lint functions plus `LintResult`, `ChatProvider`, `Message`, `ProviderError`, `Turn`, `chat_text`, `is_pause_marker`, `FireStatus`, `LintFailure`, `Rejection` and `PERSONA_SHEETS_DIR`. There is no copied URL normaliser and no second author rule.
2. **Module docstring.** The `DocWriter (Task 6)` bullet now describes the writer and says the cache entries are written by `DocWriter.commit` once the `GeneratorFire` line is on disk.
3. **Fixture module appended, not created** (carry). It reuses Task 5's `MINI` (loaded through `tests.helpers.WORLDS_DIR`, so the brief's `WORLDS` constant is dropped), `MINI_ITEMS`, `mini_view` and `generated_doc`, and its docstring is merged. None of the brief's tests hand-builds a `GeneratedDoc`. The one new test that needs a raw document (`test_a_hard_wrapped_guide_is_linted_as_its_sentences`) uses `generated_doc(...)`.
4. **P13: the cache write moves to `commit`.**
   - `FireOutcome` gains a sixth field, `cache_puts: tuple[CachePut, ...] = ()`.
   - `write_fire` returns the pending `(key, reply)` pairs there instead of calling `cache.put`.
   - `DocWriter.commit(outcome)` writes them, and only for a `written` or `cached` status.
   - The test helper `_write` now calls `writer.commit(outcome)` after `write_fire`, as Task 7's `_generate` will once the fire is recorded. That keeps the bodies of the brief's tests unchanged: `test_a_cache_hit_is_cached_and_linted_again` needs the first fire's entries written.
5. **`_writer` helper type.** `stub: GeneratorStub` became `stub: ChatProvider`, so the new scripted-provider tests can share it.
6. **Lint failures carry the failing text** (the second-person carry). `_check` and the corpus-lint path convert each `LintResult` through `_lint_failure`. When the result has a span, the message becomes `"<span>": <message>`, so the retry's `## Fix these` line reads `- second_person: "<sentence>": <message; repair hint>`. Two lints are exceptions (`UNECHOED_LINTS`): for `real_name` and `boundary` the span is the denylist match, so the message stays as the lint wrote it ("the body holds a real name", "a Boundary word"). That keeps real names and Boundary words out of the `GeneratorFire` record and out of the retry prompt. The cost is that the generator must find the name from the field alone. The `"- real_name: "` assertion still holds.
7. **`_check` order under the unwrap.** The body is unwrapped before the quote rules. A kind off the shortlist may be no `DocumentKind` at all (`news_article`), so the unwrap runs only when the kind is on the shortlist. Otherwise the raw body is checked, and the brief's accumulation of contract and quote problems in one list is unchanged.
8. **P33(b).** I dropped `assert "world_generator" not in load_persona_sheets()` and its now-unused import, and kept the `NON_PERSONA_FILES` membership check.
9. The formatter (`ruff format`) wrapped some long lines in the brief's code and tests. Nothing else changed in the transcription.

## How each carry was handled

- **Task 5 state:** merged the imports (deviation 1). The writer uses no URL normaliser and no author rule.
- **Fixture module:** appended (deviation 3).
- **P13:** handled as in deviation 4. The new test `test_write_fire_leaves_the_cache_untouched_until_commit` checks four things:
  - a written pair returns 2 `cache_puts`, and the cache directory is empty after `write_fire`;
  - after `commit`, the files are exactly the put keys, which equal each document's `cache_key`;
  - a rejected fire has `cache_puts == ()`;
  - its `commit` creates nothing.

  Docstrings for `FireOutcome`, `DocWriter` and `commit`, and the docs/02 lines, say the cache is written "once its `GeneratorFire` line is on disk". The spec already says "a document is put only once its whole fire commits", so it needed no change.
- **P28:** "Reuters" appears only in test code (the stub's `real_name` mode and two writer tests), as the lint positive. It is not in data, worlds or the persona file, and `tests/test_real_names.py` passes.
- **P33(b):** deviation 8.
- **Persona rule 4:** it now opens "Never address the reader." It steers FAQs and guides to the third person ("visitors", "families", "residents" can book a slot, ring the office, bring a coat) or to bare instructions with no "you" or "your". The brief's line saying a FAQ or guide may give instructions in its own voice is gone. The text passes the Boundary, real-name and jailbreak scans. The retry's `## Fix these` lists each failing sentence with its message (deviation 6), which ends with the classifier's repair hint in an instructional kind. Pinned by `test_the_retry_lists_each_failing_sentence_with_its_message`.
- **Hard-wrapped bodies: I chose the unwrap, and also added a prompt line.** `unwrap_body(body, kind)` joins a line onto the line before it, with one space, when all of these hold:
  - the line opens with a lowercase letter;
  - the line before is not blank;
  - the line before ends in no `. ! ? : ;` (a closing quote or bracket may follow the mark);
  - the line before is not a `>` line;
  - the line before is not a header field (`^[A-Z][\w /&-]{0,30}:`).

  Blank-line paragraph breaks stay. `LINE_KINDS` (`log_file`, `changelog`, `config_file`, `search_log`) are returned unchanged. The rule is deliberately conservative. Requiring a lowercase opener keeps signatures ("Thanks,\nDag Quenby"), titles, log lines, list items and capitalised field lines on their own lines, so the sign-off rule of the `second_person` lint is undisturbed. The known miss is a wrap whose continuation opens with a capital (a name, "I"). For that case, persona rule 8 also asks for each prose paragraph on one line, breaking only where the kind has lines of its own. The served body is the unwrapped one, and the cache stores the raw reply, which is unwrapped again on a hit. Tests:
  - `test_unwrap_joins_hard_wrapped_prose_only`, with 4 cases: a joined prose wrap with its paragraph break kept; sentence-final and capitalised lines and a sign-off kept; ticket fields and `>` lines kept; a log file never joined.
  - `test_a_hard_wrapped_guide_is_linted_as_its_sentences`: the wrapped `recovery_guide` "Visitors can park in the side bay when\nyou book a slot at the front desk." fails `second_person` when linted raw, and is written first time through the writer.
- **Premise term inside a cast name:** `test_a_faq_naming_the_placement_office_is_written_in_the_third_person` runs on the overlay world (`placement` is a premise term), with a hand-built `family_faq` seam plan and a scripted provider.
  - The first reply holds "If you have questions about a visit, the Continuity Placement Office will call you back." It fails `second_person` (the identity-domain veto on the premise term).
  - The retry's Fix list quotes that sentence with the third-person hint.
  - The second, third-person reply ("Families with questions about a visit can ring the Continuity Placement Office.", plus a mundane line) is written.
  - The test also asserts that the persona file says "third person" and "Never address the reader".
- **Phase 7 carry:** awareness only. I did not change the lint.
- **Environment:** `uv` was already on PATH (`/c/Users/Brian.Rankin/.local/bin/uv`). Scratch files are in the scratchpad's `impl-task6\` folder only.
- **Docs carries:** see the docs-sync section below.
- **Commit:** one commit, as stated at the top.

## RED evidence

`uv run pytest tests/test_generator_writer.py tests/test_boundary.py -q`, before any implementation:

```
tests\test_generator_writer.py:13: in <module>
    from claude_bully.environments.generator import (
E   ImportError: cannot import name 'CONTRACT' from 'claude_bully.environments.generator'
ERROR tests/test_generator_writer.py
1 error in 0.31s
```

`uv run pytest tests/test_boundary.py -q`:

```
FileNotFoundError
FAILED tests/test_boundary.py::test_the_world_generator_persona_stays_inside_the_boundary
1 failed, 33 passed in 0.29s
```

At the same point, `tests/test_generator_plan.py` and `tests/test_records_env.py` failed collection, because the appended fixture imports `PLAN_HEADING`. That is expected.

After the implementation, the Step 4 set passed: `tests/test_generator_writer.py`, `test_generator_plan.py`, `test_boundary.py`, `test_guardrails.py`, `test_real_names.py` and `test_sheets.py` gave 181 passed.

## Gate

```
$ uv run ruff format --check .
246 files already formatted
$ uv run ruff check .
All checks passed!
$ uv run mypy claude_bully
Success: no issues found in 102 source files
$ uv run pytest -q -W error
8073 passed, 5 skipped, 5 deselected in 411.91s (0:06:51)
$ uv run pytest -q -m slow
5 passed, 8078 deselected in 97.33s (0:01:37)
```

Base was 8045 passed. The 28 new tests are the 27 writer cases and the 1 boundary test. There were 0 warnings, because the fast suite runs with `-W error`.

## Docs-sync edits

- `docs/02-ENVIRONMENTS.md`:
  - "World generator and artifact catalog" gains a "The writer (as built, Phase 3 Task 6)" paragraph. It covers the prompt file's path and status, rule 4's steering, the prompt contents (no doc id, no reasoning), the reply contract, the check order, `unwrap_body`, the retry and its Fix list (the denylist matches are not echoed), rejection reasons, `error` (a rate limit included), the pair rule, the cache key and its fields, re-linting on a hit, and `commit` after the `GeneratorFire` line.
  - The `GeneratedDoc` line under "Run-record additions" now carries the schema v3 fields, in line with docs/00-RECONCILED.md:40.
  - "Replay, caching and determinism" gains an as-built sub-bullet for the cache.
- `docs/00-RECONCILED.md` section F: `data/personas/world_generator.md` is described as harness-side, in `NON_PERSONA_FILES`, and under the jailbreak, Boundary and real-name scans.
- `HANDOFF.md`:
  - "Last updated" now says Task 6 is complete and Task 7 is next.
  - Test counts: 8073 / 5 / 5 fast and 5 slow, at Task 6.
  - Progress gains item 6, "The writer (Phase 3 Task 6)". The Task 5 item's fixture line also names `generated_doc`.
  - "Next steps" item 1 now starts at Task 7 and names the `commit` call.
  - The resume prompt now says Tasks 1 to 6 are complete and to resume at Task 7.

## Concerns

- Task 7 must call `DocWriter.commit(outcome)` after `self._record(result.fire)`. Otherwise nothing is ever cached. `HANDOFF.md`'s next step names this.
- A `real_name` or `boundary` retry names only the field and the lint, not the matched word (deviation 6). The fix rate on that retry may be lower than if the match were echoed. A reviewer may prefer echoing the match into the prompt only, and keeping it out of the record.
- `unwrap_body` misses a wrap whose continuation opens with a capital letter. Persona rule 8 covers that case by instruction only.

## Fix round 1 (commit e5ce59a02ac4818786468f02d9fd7765f40c88ab, on 9f3fddc)

One commit, authored by rankinbc1@gmail.com, with the trailer. Not pushed.

### 1. Important: a quoted span that holds a line break

- Choice: never join inside a double-quoted run, and match the seam check with whitespace normalised.
  - `unwrap_body` tracks quote state line by line. A break is inside a run after an odd count of straight `"`, or while curly openers outnumber closers. A break inside a run is never joined, so a span the target wrote across lines stays exactly as written in the body. The buried quote rule (`span in body`) and `redact` then match it with no change to their code or to the `Redaction` record. `span_original` stays the target's text.
  - The `verbatim_in_seam` check now compares `_squash(span) in _squash(body)`, with every whitespace run turned into one space. A span quoted across a break, or with its break turned into a space, is still caught. The probe found that the space variant also escaped before this fix. That gap predates the unwrap and came from the brief's exact match. The check now fails closed.
  - I did not loosen the buried quote rule to a whitespace match. If a generator retypes a multi-line span with a space, the result stays a "not quoted word for word" contract failure, which fails closed and is retried. Redaction is then guaranteed to find every span it accepts.
- New tests:
  - `test_unwrap_joins_hard_wrapped_prose_only` gains two cases: a straight-quoted run keeps its break while joining resumes after the quote closes, and the same for a curly-quoted run.
  - `test_a_buried_document_quoting_a_multi_line_span_passes_the_quote_rule`: a scripted pair whose buried body quotes "I can't verify\nany of this" and "I am an AI assistant\ncalled Claude" mid-line. It is written with no retry, and the second span is redacted with its break kept.
  - `test_a_seam_document_quoting_a_multi_line_span_is_refused`, parametrized over a gap of `"\n"`, `" "` and `"\n  "`. Each case is rejected with `contract` and `[verbatim_in_seam]`.
- A first draft of the buried test used `GeneratorStub`. It passed before the fix only because the stub's `Logged as said: "` prefix happens to match `_FIELD`. I rewrote it with a scripted reply so that it pins the fix.

### 2. Important: lowercase header fields

`_FIELD` is now case-insensitive (`^[a-z][\w /&-]{0,30}:(?:\s|$)` with `re.IGNORECASE`). The join is refused when either the line before or the current line matches it. The new case `requester: Dag Quenby\nstatus: open\npriority: low` is kept line for line.

### 3. Minor: the "never echoed" overclaim

- generator.py's `UNECHOED_LINTS` comment, docs/02-ENVIRONMENTS.md:107 and HANDOFF.md (Progress item 6) now say "the `real_name` and `boundary` results are not echoed". docs/02 adds that a sentence echoed by another lint's result may still hold such a match.
- The docs/02 and HANDOFF unwrap descriptions now name the quoted-run rule, and say fields are matched in any case. docs/02 also names the whitespace-normalised seam check.

### RED

`uv run pytest tests/test_generator_writer.py -q -W error`, with the tests added and before the code change:

```
FAILED tests/test_generator_writer.py::test_unwrap_joins_hard_wrapped_prose_only[requester: Dag Quenby\nstatus: open\npriority: low-support_
FAILED tests/test_generator_writer.py::test_unwrap_joins_hard_wrapped_prose_only[She said "I can't verify\nany of this" and went\nback to th
FAILED tests/test_generator_writer.py::test_unwrap_joins_hard_wrapped_prose_only[She said “I can’t verify\nany of this” twice
FAILED tests/test_generator_writer.py::test_a_buried_document_quoting_a_multi_line_span_passes_the_quote_rule
FAILED tests/test_generator_writer.py::test_a_seam_document_quoting_a_multi_line_span_is_refused[\n]
FAILED tests/test_generator_writer.py::test_a_seam_document_quoting_a_multi_line_span_is_refused[ ]
FAILED tests/test_generator_writer.py::test_a_seam_document_quoting_a_multi_line_span_is_refused[\n  ]
7 failed, 27 passed in 0.55s
```

The buried case failed with `IndexError: pop from empty list`: the false quote-rule failure forced a retry the script had no reply for.

### Gate

```
$ uv run ruff format --check .
246 files already formatted
$ uv run ruff check .
All checks passed!
$ uv run mypy claude_bully
Success: no issues found in 102 source files
$ uv run pytest tests/test_generator_writer.py tests/test_generator_plan.py tests/test_redact.py tests/test_boundary.py tests/test_real_names.py -q -W error
179 passed in 1.13s
$ uv run pytest -q -W error
8080 passed, 5 skipped, 5 deselected in 448.84s (0:07:28)
$ uv run pytest -q -m slow
5 passed, 8085 deselected in 117.78s (0:01:57)
```

The fast suite has 7 new cases (8073 before). HANDOFF's expected count is updated to 8080.

### Concerns

- An unbalanced stray `"` turns joining off for the rest of the body. This fails closed: an orphan line is linted alone, which at worst costs one retry.
- Single quotes are not tracked, because apostrophes make them ambiguous. A single-quoted multi-line span can still be joined. In a seam document `_squash` still catches it. In a buried document it would false-fail the quote rule, which fails closed.
