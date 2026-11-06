# Phase 3 final-review fix wave

One fix dispatch for everything the whole-branch review (`final-review.md`, over 807bddf..24b9a25) said to fix now, plus the parked batch the ledger ruled into this wave. Read `final-review.md` for file:line references and the reasoning behind each item. The review was over Tasks 1 to 8; Task 9 (seven Phase 2 minors) landed after it, so read the touched files at HEAD, not at the review's lines.

## Important

1. **I1: the judge caches are not crash-safe.** `JudgeCache.put` is a non-atomic `write_text` and `get` a raw `json.loads` (`claude_bully/metrics/judge.py`, near :98-107). Phase 3 puts the generated-cache write right after the fire line (`env_turn.py` `_generate`, P13), so a kill inside `commit` leaves a torn `runs/_cache/generated/<key>.json`, and every later run under that root dies in `_from_cache` (`generator.py`, near :773-790) on every resume until the file is deleted. Fix in `JudgeCache` itself so every cache (triggers, harvest, generated) gets it: write to a temp file in the same directory and rename over the target; return `None` from `get` on a parse failure (a cache miss, re-asked). Add one test per cache that a torn file is a miss, and one that a kill between temp write and rename leaves the old entry readable.
2. **Task 4 M3** rides with I1: a corrupt harvest JudgeCache entry raised `JSONDecodeError` out of `harvest` (`harvest.py`, near :687-691); with `get` returning `None` it degrades as the house pattern (judge.py) does. Keep or add the test.

## The ruled Task 3 batch (second_person lint)

3. "come back to you" with a modal or "to <verb>" (the breaker-fix regression, Important), `_STAFF` vehicle nouns (`second_person.py`, near :559-565), "If needed/preferred you can", comparative without "than", and the two docs inaccuracies the Task 3 breaker re-review named. See `task-3-rereview-breaker.md` beside this file for the quoted lines. Each gets a fixture pair (the billboard fails, the legitimate near-miss passes) before the code changes. Do not widen any open verb class; this module's rule is closed lists.
4. **Task 3 N5:** a quote containing a sentence end yields a span the document lacks (`second_person.py` `_source`, near :1060-1066). The retry message must never name text the generator did not write. Fix the span to the document's own text, with a test.
5. **Task 3 staff-addressed memos fail:** record it in `docs/08-DIRECTOR.md`'s lint section as one line (as ruled).
6. **`lints.py` `_WORD` lacks `Final`:** add it.

## Docstrings and docs (one sentence each)

7. **m7:** `claude_bully/environments/runtime.py:12-13` overclaims: "Before every provider call the runtime names it in attempt.json". The trigger fallback, the idle fallback and the responder are provider calls and are not marked. Say which calls are marked (target, bully, harvest, generator).
8. **m8:** `harvest.py`'s module docstring names only the context residual; `docs/02-ENVIRONMENTS.md` and the spec amendment name two (context, and a report two or more sentences later). Make the docstring name both.
9. **m6:** the plan's Decisions list says a heuristic harvest span "is its clause, trimmed of `.,;:!`"; the code and spec amendment say the whole sentence trimmed of a trailing `.` or `!`. Correct the plan line (`docs/superpowers/plans/2026-10-24-phase-3-world-generator.md`).
10. **m4:** duplicate stem line in `_SPEECH_STEMS` (`harvest.py` "figures figured" twice); drop one.

## Cheap minors worth riding the wave

11. **m1:** `GeneratorFactory` (`tests/fixtures/generator_stub.py`, near :432-441) falls through to a real provider for the judge role when `judge` is None. Make it raise instead, so no test can reach a real provider by omission.
12. **m5:** `EnvironmentSession.prime` reads the trigger stream twice (`env_turn.py`, near :377 and :382). Read once, reuse.
13. **m3:** the writer prompt lists the pair's own buried document under "Documents the reader can already reach" (`generator.py`, near :669-671, via `with_documents` marking it visible). Exclude the pair's own documents from that list; add a test on the prompt text.

## Left parked (do not touch)

Everything else in `final-review.md`'s triage stays parked with its ruling, including Task 4 M7 (cache key omits judge model and prompt version) and Task 8 m1, both flagged must-land before Phase 7, and m2 (no run-level test with an LLM-sourced item through a fire).

## Method

- Fixtures and tests first (RED), then the code.
- Run the covering tests for each area, then the full gate (ruff format --check, ruff check, mypy claude_bully, `pytest -q -W error`, `pytest -q -m slow`). Every step passes with 0 warnings.
- One commit, authored by rankinbc1@gmail.com, ending `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never push.
- Write the report to `final-fix-wave-report.md` beside this file: per item, what changed, the test that pins it, and the gate output.
- Scratch files go in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\b3f956596010799d\7d309c2e-1430-4cb8-9c70-de3f61a002fe\scratchpad\impl-fixwave\` only.
