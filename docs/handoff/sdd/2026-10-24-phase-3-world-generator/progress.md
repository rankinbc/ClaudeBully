# SDD ledger — plan: docs/superpowers/plans/2026-10-24-phase-3-world-generator.md

Spec: docs/superpowers/specs/2026-10-24-phase-3-world-generator-design.md (approved by owner 2026-10-24/25: "continue", plan "go").
Branch: build/v1. Start HEAD: 807bddf. Execution: subagent-driven (owner choice).
Standing rules: docs-sync after every task (owner); push build/v1 after each task; commits as rankinbc1@gmail.com; no real API calls.
Preflight: see preflight.md in this folder.

## Preflight rulings (table: preflight.md, P1-P35; 12 non-agree)
- P3 Ruling: Task 1's mention of `mark_attempt` for harvest is wording only; Task 4 exposes the `mark` hook, Task 7 binds it — carried as a note to Tasks 1/4/7 — cost if wrong: an implementer adds an unused binding, caught in review.
- P13 Ruling: the cache write moves after the GeneratorFire line (pending writes returned on FireOutcome, written after commit); Plan Decision line 45 reads accordingly — the spec's resume-equals-unbroken requirement is binding — cost if wrong: an extra field on FireOutcome. Carry to Task 6 and Task 7.
- P22 Ruling: drop the redundant cast in `_parse_items` (plan line 2240) — mypy strict fails otherwise — cost: none. Carry to Task 4.
- P23 Ruling: Task 5 also edits `test_records_env_imports_only_enums_and_pydantic` (allow `datetime`) and the GeneratedDoc builder at tests/test_store.py:245 — existing tests break otherwise — cost: none. Carry to Task 5.
- P25 Ruling: Task 7 adds `harvest_degraded` to `with_its_turn` in tests/test_sanctuary.py (~line 1602) and lists that file — cost: none. Carry to Task 7.
- P27 Ruling: m7 keeps the Phase 2 torn-last-line behavior (a truncated fragment is skipped anywhere it can only be a torn tail; damage mid-line raises); m7's fixture is rewritten to be distinguishable — the existing Phase 2 test encodes a resume invariant — cost if wrong: damaged mid-file lines of the torn shape stay silent. Carry to Task 9.
- P28 Ruling: "Reuters" stays in tests/fixtures/generator_stub.py as the real_name lint positive; the constraint is narrowed to exempt lint/denylist positives inside test code (the real-name scan does not cover that path) — a lint needs a positive — cost if wrong: one real name in test code of a public repo; replaceable by any denylist entry later. Carry to Task 6.
- P29 Ruling: the plan's departures from the spec (GeneratorFire `plans` list + `rejection`, attempt.json, drop_uncommitted_generation, pseudo-rung routing, GeneratedDoc.unlock_rung, controller push) are written into the spec as an "As planned" amendment during Task 1's docs sync, and listed to the owner at phase end — the plan's rulings refine, not change, the owner-approved design — cost if wrong: owner rework of a named, listed set.
- P31 Ruling: rebuild `drop_dead_attempts` on the `_parsed_lines`/`_keep_only` helpers instead of duplicating — cost: none. Carry to Task 7.
- P32 Ruling: Task 5 creates the shared fixture (mini_view / MINI_ITEMS) in a tests helper module; Tasks 5-7 import it — cost: none. Carry to Tasks 5, 6, 7.
- P33 Ruling: tighten each weak assertion — Task 2 pin asserts the reply text names the reachable names, not only 404; Task 6 persona-loader check asserts the loader's actual skip set (NON_PERSONA_FILES) contains world_generator.md or drop it; Task 5 drifting-clock check uses a drift that moves the served date — cost: none. Carry to Tasks 2, 5, 6.
- P34 Ruling: tests assert through behavior where a public path exists; where none does, reading a private field is accepted and noted — cost: brittle tests on refactor. Carry to Tasks 7, 9.
- Note: off-by-one cite at tests/test_runner_idle.py:1277 — implementers locate by name.
Task 1: dispatched (BASE 807bddf, implementer opus, agent ae091b630851e8ffb)
Task 1: review (opus) — spec code OK, 1 Important (P29 amendments section incomplete), Needs fixes.
Task 1: minor (deferred): runtime.py:133-134 docstring says every provider call is marked; only target+bully until Tasks 4/7.
Task 1: minor (deferred): tests/test_attempt_marker.py _view compares (type,id,turn) only; reuse test_runner_env _records_view.
Task 1: minor (deferred): untested — bully rate-limited at own call; fixed-mode intent writes no marker; dropped lines + dead marker in one resume.
Task 1: fix round 1 dispatched (resume implementer; FIX_BASE 0ade95e).
Task 1: fix round 1/5 (1 addressed, 0 open — P29 amendments completed, 36 rulings; commits 0ade95e..2134d92)
Task 1: complete (commits 807bddf..2134d92, review clean)
Task 2: dispatched (BASE 2134d92, implementer sonnet)
Task 2: implementer DONE (09fa85c, c9bf062; gate 7348/5/5, slow 5); review dispatched (sonnet)
Task 2: review (sonnet) — spec OK, Approved, minors only.
Task 2: minor (deferred): authority.py reachable_names duplicates _reached's conditions; build both from one helper.
Task 2: minor (deferred): untested — no-reachable-names bare reply branch; blank model_name.
Task 2: minor (deferred): test_authority imports helpers from tests.test_guardrails (brief-prescribed; known handoff minor).
Task 2: minor (deferred): no MCP end-to-end test of the new not-found text.
Task 2: complete (commits 2134d92..c9bf062, review clean)
Task 3: dispatched (BASE c9bf062, implementer opus)
Task 3: implementer DONE_WITH_CONCERNS (b37a554, 52b19eb; gate 7403/5/5, slow 5); concerns: 'thank you for your <word>' exemption broad; staff-addressed memos rejected; single-quoted you passes by regex accident
Task 3: review (opus) — spec OK; held-out probe real_name 10/10, boundary 8/8, second_person 26/45 (58%); 4 Important + 1 plan-mandated Important; Needs fixes.
Task 3: Ruling (issue 5, plan-mandated order): the reader-address check runs on the unstripped text (quotes and > lines included); quote stripping applies only to the generic "you" check — spec 5 says "never address the reader", and a quoted found note that addresses the reader is the most natural billboard smuggle — cost if wrong: a legit quoted line with a reader phrase costs one generator retry.
Task 3: Ruling (method): fixes are structural, not per-sentence — (a) quote stripping covers single and curly quotes opening after whitespace/line start, one newline allowed in a span; (b) politeness as a structural closing pattern; (c) identity nouns only at clause end; (d) in the instructional kinds a sentence pairing "you" with a world premise term fails; (e) reader patterns for the probe's billboard families. Asymmetry: a false fail costs one retry, a false pass ships a billboard, so ambiguous cases fail. Re-review measures on a fresh probe set the implementer has not seen — cost if wrong: more rounds, as Phase 2 Task 12.
Task 3: minor (deferred): staff-addressed memos fail by the plan's fail-closed rule — record as a known cost in docs/08.
Task 3: minor (deferred): docs/08 Billboard row omits curly-apostrophe mapping and narrowed reader patterns.
Task 3: minor (deferred): lints.py:76 _WORD lacks Final.
Task 3: minor (deferred): "thank you for your service as a program" passes (exotic).
Task 3: fix round 1 implementer DONE (df7de3d; 7434/5/5, slow 5)
Task 3: fix round 1/5 (2 addressed, 3 open — closings still a phrase list (3/6 fresh false-fail, `see you` false pass); instructional billboards 9/13 fresh false-pass; quoted/> billboards 4/6 false-pass + Important _END closing-quote regression; old probe 45/45, fresh probe 37/54; commits 52b19eb..df7de3d)
Task 3: Ruling (method, round 2): switch second_person to positive anchors that fail closed (the Phase 2 Task 12 lesson). In the instructional kinds a sentence with "you"/"your" passes only if it matches a procedural anchor (imperative/conditional procedure: if you need|want|have|would like|are unable; you can|may|should|will need to + a procedural verb such as call, bring, ask, book, visit, contact, request, collect, park, fill, use, send, wait); everything else fails. Inside quoted spans and > lines, a span with a second-person be-predicate (you are|were|'re|aren't|weren't), "you (really|actually|still)", or an agent acting on you (placed|put|moved|made|told|changed you) fails. Closings are spared only as a line-final structural closing (a short line ending in a comma, or "see you <time>" at a sign-off). Lexical reader lists stay only as an extra fail path — reader lists overfit; a fail-closed allowlist bounds false passes — cost if wrong: FAQ/guide generation pays more retries; measured on a fresh probe each re-review.
Task 3: fix round 2 implementer DONE_WITH_CONCERNS (386801c; 7467/5/5, slow 5); new file planner/second_person.py (293 lines); 5 near-miss fixtures re-labeled to fail under fail-closed.
carry to Task 6: the generator prompt steers family_faq/recovery_guide toward procedural "you" (descriptive FAQ "you" now fails the second_person lint and costs a retry).
Task 3: fix round 2/5 (2 addressed, 1 open + 1 new Important — closings and quoted/> billboards generalize; finding 4 open: anchored clause approves identity billboards, 11/17 fresh false-pass; new: ~24% false-fail on legit procedural FAQ (coordination split, negative imperatives, verb list), FAQ infeasible in 2 attempts; probe3 73/91; commits df7de3d..386801c)
Task 3: Ruling (round 3 structure): in the instructional kinds a "you" sentence passes iff it has a procedural anchor AND no identity-domain veto anywhere in the sentence (veto: who/what you are|were|used to be, who are you, your own, remember/recall/memory/memories (except "remember to <verb>"), real/really/true/truth, voice/sounds like you, the family/name/life you had, why you / why nobody, proof/doubts, premise terms). Anchors are sentence-scoped (coordination and comma lists covered), negative imperatives (do not/don't/never + verb) anchor, the imperative verb list widens to common procedure verbs. Closings accept "!" and "appreciate" but still run the veto and B. The lint returns one LintResult per failing sentence so a retry repairs all at once. Target on a fresh probe: instructional billboard false-pass <= 2/15, legit procedural false-fail <= 10% — the anchor decides form, the veto decides content; identity talk is the billboard's whole vocabulary — cost if wrong: Task 3 escalates to rounds 4-5 on a fresh implementer.
Owner: 'wrap up the subagent' — Task 3 round 3 implementer told to finish (commit if complete+green, else stash task3-round3-wip) and report; no further dispatch until owner says.
Task 3: round 3 wrapped up at owner request — not complete; WIP in stash `task3-round3-wip` (lint tests 154 pass; full gate not run); implementer's own fresh probe: billboards 7/15 pass (target <=2), legit false-fail 2/20. Committed head 386801c (unpushed: b37a554..386801c). Docs for round 3 not updated. Resume point: Task 3 fix round 3 (or round 4 on a fresh implementer, a tier up, starting from the stash).
Task 3: round 3 WIP committed at owner request (commit 158746b); stash dropped by pop.
Pushed build/v1 at 158746b (owner request; Task 3 incomplete).
Gate at 158746b: pytest -q -W error 7503 passed / 5 skipped / 5 deselected (slow not run).
