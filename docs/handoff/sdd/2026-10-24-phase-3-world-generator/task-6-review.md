# Task 6 review: the writer (2f17c02..9f3fddc)

Reviewer scope: the brief (task-6-brief.md), the carries (task-6-carries.md, which win where they differ), global-constraints.md, and the diff. Outside-diff checks were each tied to one named risk:

- Merged imports. `norm_url` is imported at generator.py:42 and used at :247 (`_norm_address`). `_authors` is defined once at :250 and used at :270 and :435. No copied normaliser was found.
- `LINE_KINDS` completeness. The kinds the generator can write are `MATERIAL_KINDS` (generator.py:81-96) plus the worlds' `allowed_kinds`. Of the line-structured kinds, only log_file, changelog and config_file are reachable, and `LINE_KINDS` covers them.
- Lint spans and the echo rule. `real_name` and `boundary` put the denylist match in `span` (lints.py:148, :155). `second_person` puts the whole sentence there (lints.py:171).
- Real-name scan coverage. tests/test_real_names.py:25 rglobs `data/personas`, so it covers the new .md file.
- One `uv run python -c` probe of `unwrap_body` (output quoted under Minor 1 and Minor 2).

The suite was not re-run. The implementer's gate shows 0 warnings under `-W error`.

## Spec Compliance

| File | Verdict | Notes |
| --- | --- | --- |
| `data/personas/world_generator.md` | PASS | Transcribed from the brief. Rule 4 is amended per the carry: "Never address the reader", with third person or bare imperatives (lines 24-27). The brief's "may give ordinary instructions in its own voice" is gone. Rule 8 adds one line per prose paragraph (lines 31-33). It holds no real names, no Boundary words and no reader address aimed at the target. |
| `claude_bully/environments/generator.py` | PASS | The import block is merged, not replaced (Task 5 carry). Every brief constant, `FireOutcome`, `cache_key`, `transcript_prefix`, `parse_reply`, `writer_prompt` and `DocWriter.write_fire` match the Interfaces. P13 is met: `FireOutcome.cache_puts` is filled by `write_fire`, which calls no `cache.put`; `commit` (:722) does the writing. The docstrings say "once its `GeneratorFire` line is on disk". The hard-wrap carry is met: `unwrap_body` (:553) is chosen and tested. The second-person carry is met: `_lint_failure` (:637) puts the sentence first and keeps the hint. |
| `claude_bully/strategies/sheets.py` | PASS | `NON_PERSONA_FILES` gains `world_generator.md`, and the comment is updated. |
| `tests/fixtures/generator_stub.py` | PASS | Appended, not created (carry). It reuses `MINI` via `WORLDS_DIR`, drops the brief's `WORLDS`, and keeps `generated_doc`. The stub code matches the brief. "Reuters" appears only as the mode `real_name` lint positive (P28). |
| `tests/test_generator_writer.py` | PASS | All 17 brief functions are present with unchanged bodies; `_write` now commits, as the P13 carry allows. P33(b): the `load_persona_sheets` assertion is dropped and the `NON_PERSONA_FILES` check is kept. Added tests: the P13 test (`test_write_fire_leaves_the_cache_untouched_until_commit`); the Fix-list sentence test; the unwrap tests (4 cases plus the wrapped guide); the placement-office test, which runs on the overlay world. `generated_doc` is reused in the one test that needs a raw document. |
| `tests/test_boundary.py` | PASS | The persona file is scanned line by line, in the pattern of the overlay test. |
| `tests/test_guardrails.py`, `tests/test_real_names.py` | PASS (unchanged) | Both rglob `data/` and `data/personas`, so they scan the new file. |
| `HANDOFF.md` | PASS | Progress item 6 is added, and the Task 5 fixture line names `generated_doc`. The counts are 8073/5/5 and 5, and "next" points at Task 7 with the `commit` call. The resume prompt (carry) says Tasks 1 to 6 are complete and to resume at Task 7. |
| `docs/02-ENVIRONMENTS.md` | PASS (one overclaim, Minor 3) | It adds the as-built writer paragraph and the cache sub-bullet. The `GeneratedDoc` line now matches docs/00-RECONCILED.md:40 (checked: the same field list). |
| `docs/00-RECONCILED.md` | PASS | Section F describes `world_generator.md` as harness-side, in `NON_PERSONA_FILES`, and under the three scans. |

Missing: none. The Extras are all carry-sanctioned: `unwrap_body`, `LINE_KINDS`, `UNECHOED_LINTS`, `CachePut`, `_lint_failure`, `FireOutcome.cache_puts`, `DocWriter.commit` and the `_Scripted` test provider. Misunderstood: none.

Outside this diff: Review Focus 2's second half (`test_a_rejected_pair_leaves_its_items_for_the_next_fire`) and the item consumption it checks belong to Task 7's policy wiring: CANNOT VERIFY. The writer itself consumes nothing, which is correct.

Spec verdict: PASS.

## Implementer concerns, judged

1. **Task 7 must call `commit`.** The API does not enforce the call, but it fails safe. A forgotten `commit` means no caching, which costs money but never correctness or replay; and nothing can cache a rejected fire, because `commit` gates on `COMMITTED` and a rejected outcome carries `cache_puts == ()`. The call is documented in five places: the `FireOutcome`, `DocWriter` and `commit` docstrings, HANDOFF "Next steps" item 1, and docs/02. Acceptable. Task 7 should pin it with a run-level test: a second unbroken run with the same prefix reports `cached`.
2. **The field is named, the match is not.** This is consistent with the brief's retry contract. The brief's layout is `- <lint_id>: <message>` (brief lines 46-47), and the brief's own `_check` passed `r.message` through unchanged. The carry asks only that each failing *sentence* be listed with its message, which is the `second_person` case, and that is done. Not echoing a denylist match is a defensible extra. But the guarantee the docs state is not airtight; see Minor 3.
3. **`unwrap_body` skips a capitalised continuation.** Acceptable. Leaving a wrap unjoined fails closed: the orphan line is linted alone, and the worst case is a false failure that costs one retry, never a billboard served. Rule 8 covers the case by instruction. The carry allowed either remedy and the implementer did both. The real gaps in the unwrap lie elsewhere (Minor 1 and Minor 2).

## Strengths

- P13 is cleanly separated. `write_fire` is pure apart from the cache read and the provider calls. Puts travel on the outcome, and `commit` is idempotent in effect and gated on status. The new test checks every link in the chain: nothing written before `commit`; exactly the put keys after it; put keys equal each doc's `cache_key`; and a rejected fire yields no puts and creates no cache directory.
- The served body is the linted body. `unwrap_body` runs before the quote rules, `redact` and `lint_document` (generator.py:806, :827), and the cache stores the raw reply, which is unwrapped again on a hit. Same input, same served text, same key.
- The check order matches the brief: parse, then the contract problems accumulated, then the quote rules, then redaction, then the fail-severity lints. A cache hit goes through the same `_check`, so a reply that fails now is a miss.
- The pair is all-or-nothing. Both the rejection and the `ProviderError` paths return `docs=[]` and no puts before the seam is ever cached; Focus 2's writer half is pinned by `test_a_rejected_seam_pointer_commits_neither_document`. A non-`ProviderError` exception propagates, as Task 7's kill tests need.
- The placement-office test is real behaviour. It runs on the overlay world and asserts that the actual lint's repair hint ("third person") reaches the retry's Fix list, not a canned string.
- DRY is respected where the carries ask. The fixture module is appended, `generated_doc` is reused, and the merged imports neither add a second normaliser nor a second author rule.

## Issues

### Critical

None.

### Important

None.

### Minor

1. **The unwrap breaks the quote rules for a span that holds a line break** (generator.py:806, :809, :817, :827).
   - What is wrong: harvest ends sentences only at `. ? !` (harvest.py:11-13), so an LLM span can hold "\n". When the generator quotes such a span verbatim, `unwrap_body` joins it, and `span in body` is False. The probe confirmed it: `'She said "I can\'t verify\nany of this" ...'` unwraps to `'... "I can\'t verify any of this" ...'`, and `span in unwrapped` is False.
     - In a buried (`quote: true`) document this fails closed: a false "not quoted word for word" contract failure on both attempts. The item stays unconsumed and can be re-offered and rejected again.
     - In a seam (`quote: false`) document it fails open: a verbatim multi-line span escapes `verbatim_in_seam`.
     - `redact` also misses such a span, so a real name inside it falls to the `real_name` lint, which rejects the document.
   - Why it matters: the quote rules are the writer's own guarantees. The task introduced this interaction.
   - The fix: unwrap the span the same way before matching and redacting, for example `unwrap_body(span, kind)` or an internal-whitespace normalisation applied to both sides. Alternatively, never join inside a double-quoted run. Add one near-miss case.
2. **Lowercase header fields are joined** (generator.py:476, `_FIELD`).
   - What is wrong: `_FIELD` requires a capital opener, and only the line *before* is tested. The probe confirmed it: `'requester: Dag Quenby\nstatus: open\npriority: low'` becomes `'requester: Dag Quenby status: open priority: low'`. That corrupts a served `support_ticket`, the kind rule 1 describes as having "a requester, a status".
   - The fix: make `_FIELD` case-insensitive, or also refuse the join when the current line itself matches a field pattern. Add the case to `test_unwrap_joins_hard_wrapped_prose_only`.
3. **The docs overclaim "never echoed"** (docs/02-ENVIRONMENTS.md:107; HANDOFF.md:129; generator.py:473).
   - What is wrong: `UNECHOED_LINTS` suppresses the echo only for `real_name` and `boundary` results. A sentence that fails both `second_person` and `real_name` ("If you read <outlet>, stop.") is echoed whole through the `second_person` result (lints.py:171), into the retry prompt and the `GeneratorFire` record.
   - Why it matters: the docs state a guarantee the code does not give. The practical harm is low: the generator is harness-side, and `GeneratedDoc.redactions` already records original spans.
   - The fix: either word the docs as "the `real_name` and `boundary` results are not echoed", or, in `_lint_failure`, mask any denylist match inside an echoed span with `REDACTION_MARK`.
4. **The echo is redundant where the message already holds the span** (generator.py:637-643).
   - What is wrong: `links_resolve` and `author_in_cast` put the span inside their message as well (lints.py, the `_fail("links_resolve", ...)` and `_fail("author_in_cast", ...)` calls), so the Fix line reads `"x": links_to names 'x', ...`.
   - The fix: echo only for lints whose span is a sentence (`second_person`), or skip the echo when the span already appears in the message. This is polish.
5. **The tests duplicate test doubles and view-building** (tests/test_generator_writer.py:119-139, :385-394, :401).
   - What is wrong: `_Scripted` repeats `GeneratorStub.complete`'s signature and `_completion`. `_overlay_view` repeats `mini_view`'s CorpusIndex-to-CorpusView body. `load_world("overlay", ...)` is called twice.
   - Why it matters: Task 7 will likely want a scripted generator too.
   - The fix: give `GeneratorStub` an optional `replies=` script, or move `_Scripted` into `tests/fixtures/generator_stub.py`. Generalise `mini_view(state, world=MINI)`.
6. **The unwrap fixtures pin a procedural "you" as served text** (tests/test_generator_writer.py:343-345, :372, :382).
   - What is wrong: the example "Visitors can park ... when you book a slot" is written and asserted served. That is allowed by Task 3's `second_person` anchor rules, but it is the very form that persona rule 4 now steers away from. If the Phase 7 LLM lint for `family_faq` and `recovery_guide` tightens this, the test breaks for a reason unrelated to unwrapping.
   - The fix: add a comment saying the "you" is there only to make the orphan line fail raw. Alternatively, choose an orphan that fails another lint, so the served text is third person.
7. **Bare imperatives are allowed by persona rule 4** (data/personas/world_generator.md:27: "Book a slot at the front desk.").
   - What is wrong: this is carry-mandated. A bare imperative in a FAQ is implicitly addressed to a reader, in some tension with "a document never addresses or advises the reader". The carry explicitly permits it and the `second_person` lint passes it, so this is no fix for this task.
   - The fix: none now. Note it for the Phase 7 LLM-lint work on instructional kinds.

## Assessment

Task quality: Approved.

Every brief requirement and carry is met. The retry, rejection, pair and P13 cache paths are correct and tested against real behaviour. The cache key is deterministic, and what is served is exactly what is linted. The findings are edge cases in the new `unwrap_body` heuristic (multi-line quoted spans, lowercase field lines), a docs overclaim about non-echoing, and test DRY. None makes the task untrustworthy, and Minors 1 and 2 are cheap to fold into Task 7 or a fix round.
