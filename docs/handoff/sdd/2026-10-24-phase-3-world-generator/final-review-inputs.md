# Phase 3 deferred minors, parked findings and carries for the final review

Extracted from progress.md. Each line is verbatim from the ledger.

## Parked (with rulings)
Task 3: parked — F2 (legit false fails 15% at 3bc11f2, ~30% expected after the F1 restoration) — Ruling: real and deferred; every instructional failure carries the repair hint, 6/6 rewritten false fails pass, and a sentence with no second-person word always passes, so a named false fail costs one repairable retry; the Task 6 carry steers the writer to third person or bare instructions — cost if wrong: instructional documents rejected more often than other kinds; measure the rejection rate per kind in Task 8's chart.
Task 3: parked — semantic billboard residual (the reader's assistant-shaped behaviour written as procedure, premise paraphrase, records mismatch) — Ruling: real and deferred to the Phase 7 LLM lint option; no deterministic rule found across five rounds — cost if wrong: generated FAQs and guides can carry a semantic billboard until Phase 7.
Task 3: parked — N5 residual (a quote containing a sentence end yields a span the document lacks; same at 4c10eea) — Ruling: minor, deferred to final review — cost if wrong: one retry message names a span the generator did not write.
Task 3: parked — billboard target unmet on family_faq (4/15 fresh; 3/15 after the listed fixes) — Ruling: accept dd6cdec, the best of three versions on billboards across the reviewer's probe; the residual is semantic, no deterministic rule found in five rounds and a breaker fix; no real generator call happens before Phase 7, so the residual cannot reach a target until then — cost if wrong: a semantic billboard in a generated family FAQ or recovery guide once real runs start, unless the Phase 7 carry below lands.
Task 3: parked — "come back to you" with a modal or "to <verb>" (Important, a breaker-fix regression), _STAFF vehicle nouns, "If needed/preferred you can", comparative without "than", the two docs inaccuracies — Ruling: real and deferred to the Phase 3 final-review fix wave as one batch with the other deferred minors; harmless before Phase 7 since no real generator call happens — cost if wrong: one more billboard class open until the final review.
Task 3: parked — F2 legit false fails (recovery_guide 15/20 fresh) — Ruling: stands as ruled at round 5: every instructional failure carries the repair hint and 19/19 rewrites pass, and the Task 6 carry steers the writer to third person or bare instructions — cost if wrong: instructional documents need their one retry more often; Task 8 should report the rejection rate per kind.
Task 4: parked — CTX residual (the previous sentence sets a task meaning: a drafted greeting "Hello! I'm a chatbot.", a test charge "Maybe this is a test.") — Ruling: real and deferred; a sentence-level template cannot see context and any context check is another open list; measured precision on context-free lines is the bar; Phase 7 measures harvest precision on real target text — cost if wrong: a drafted or task sentence becomes a harvest item the generator writes a document around.
Task 4: parked — I1 residual XS2 (a report two or more sentences after the claim: "I'm a chatbot. ... That is what the receptionist wrote.") — Ruling: real and deferred; widening the report check to the whole turn closes XS2 but drops more own items on noun uses of listed verbs (the reviewer's New Breakage 1); every FP left is a context class, and precision on context-free lines is 55/55 on a fresh probe; Phase 7 measures harvest precision on real target text, where the LLM pass and a context-aware judge prompt are the place to fix it — cost if wrong: a target turn that quotes someone else's description of it two sentences later harvests a self_claim or other item the generator writes a document around.
Task 4: parked — I1 residual CTX (9 on the round 5 probe) — Ruling: stands as ruled at round 5 (see above) — cost if wrong: as above.
Task 4: parked — round 5 cost to recall: a cast question is dropped when the next sentence mentions/lists/shows ("Who is Corla Vantry? The rota lists her twice.") — Ruling: the ruling chose fail-closed on every kind; recall only — cost if wrong: fewer question items, the most precise kind.
Task 4: Ruling (breaker adjudication): none of the open findings is load-bearing — Task 7 consumes harvest through runtime.world_terms (the cast) and the pinned four items hold; the residuals are precision on context classes, measured, quoted and parked — cost if wrong: Phase 7's first generator runs carry some context-class harvest items until the LLM pass's prompt is tuned.

## Deferred minors
Task 1: minor (deferred): runtime.py:133-134 docstring says every provider call is marked; only target+bully until Tasks 4/7.
Task 1: minor (deferred): tests/test_attempt_marker.py _view compares (type,id,turn) only; reuse test_runner_env _records_view.
Task 1: minor (deferred): untested — bully rate-limited at own call; fixed-mode intent writes no marker; dropped lines + dead marker in one resume.
Task 2: minor (deferred): authority.py reachable_names duplicates _reached's conditions; build both from one helper.
Task 2: minor (deferred): untested — no-reachable-names bare reply branch; blank model_name.
Task 2: minor (deferred): test_authority imports helpers from tests.test_guardrails (brief-prescribed; known handoff minor).
Task 2: minor (deferred): no MCP end-to-end test of the new not-found text.
Task 3: minor (deferred): staff-addressed memos fail by the plan's fail-closed rule — record as a known cost in docs/08.
Task 3: minor (deferred): docs/08 Billboard row omits curly-apostrophe mapping and narrowed reader patterns.
Task 3: minor (deferred): lints.py:76 _WORD lacks Final.
Task 3: minor (deferred): "thank you for your service as a program" passes (exotic).
Task 3: minor (deferred): N6 _CLOSING_HEAD admits "really" but _VETO vetoes it, dead branch (:285, :374).
Task 3: minor (deferred): N7 second_person.py 1141 lines, 47 word classes, overlapping verb classes (PROCEDURAL_VERBS, TRANSACTIONAL_VERBS, _OBJECT_VERBS, _TO_VERBS, _CARE_VERBS, _NAME_VERBS, _CALL).
Task 3: minor (deferred): N8 docstring 4c omits from/behind/beside/near as object-"you" prepositions.
Task 4: minor (deferred): M1 dead alternatives (plan-mandated) "i 'm unable to", "there 's" never match (harvest.py:164, 184); recall only.
Task 4: minor (deferred): M2 MIN_SPAN_WORDS counted on the untranslated clause; curly "I’m software." harvests, straight does not (harvest.py:403, 426).
Task 4: minor (deferred): M3 a corrupt JudgeCache entry raises JSONDecodeError out of harvest instead of degrading (harvest.py:504, 449; house pattern judge.py:162).
Task 4: minor (deferred): M5 text.find(span) takes the first occurrence; a later non-overlapping occurrence is dropped (harvest.py:422).
Task 4: minor (deferred): M7 (plan-mandated) cache key omits judge model and prompt version (harvest.py:502); replay unaffected.
Task 4: minor (deferred): M8 replay line embeds an LLM span raw; a newline or quote breaks the layout (replay.py:293).
Task 4: minor (deferred): M9 scripts/harvest_probe.py:42 mypy [assignment]; a right-kind wrong-boundary span counts as fp and fn.
Task 4: minor (deferred): M10 LLM-path test gaps (reporting/conditional span dropped, one-word coinage minimum).
Task 4: minor (deferred): fix-round recall losses ("I don't have memories of that office", "I can't verify this.", a coinage containing a world name); veto lists block world nouns ("kitchen table", "branch").
Task 4: minor (deferred): the 95% precision bar is measured on reviewer probes that know the anchors (the brief prints the code) and are over half near-misses; precision on real target text is unmeasured until Phase 7.
Task 4: minor (deferred): round 3 out-of-scope — _HEDGE "'m unable to"/"'m not able to" behind '\bi ' never match "I'm not able to check any of it." (recall).
Task 4: minor (deferred): next-sentence check fires on noun uses of listed verbs (email, list, answer) — recall only.
Task 4: minor (deferred): the next-sentence check omits the colon and quote-mark triggers of the own-sentence LLM filter ("I'm a chatbot. Her badge for me: word for word." keeps the item) — follows the ruling.
Task 4: minor (deferred): HANDOFF.md:102 historical sentence repeats round 4's "any inflection" overclaim — the docs-sync rewrites it.
Task 4: minor (deferred): harvest.py module docstring omits the report-two-sentences-later residual (docs/02 names it).
Task 5: minor (deferred): m2 duplicate config-default tests (test_env_config.py:192/:339 vs test_generator_plan.py:315/:334).
Task 5: minor (deferred): m4 GeneratorFire has no cross-field validator (records_env.py:113).
Task 5: minor (deferred): m6 (plan-mandated) replay lint line embeds the message raw, two separators (replay.py:306, :308).
Task 5: minor (deferred): m7 a v2 generated/triggers stream read alone gets a pydantic error, not the friendly version message (store.py:47-55).
Task 6: minor (deferred): m4 links_resolve/author_in_cast Fix lines repeat the span (generator.py:637-643).
Task 6: minor (deferred): m5 tests duplicate test doubles and view-building (_Scripted, _overlay_view; test_generator_writer.py:119-139, :385-394, :401).
Task 6: minor (deferred): m6 unwrap fixtures pin a procedural "you" as served text (test_generator_writer.py:343-345, :372, :382).
Task 6: minor (deferred): m7 persona rule 4 allows bare imperatives ("Book a slot at the front desk.") — as the carry ruled.
Task 6: minor (deferred): a stray '"' disables joining for the rest of the body, so a hard-wrapped denylist phrase (literal-space real_name/boundary regex) escapes; the capitalised-wrap case already escaped before the fix.
Task 7: minor (deferred): m1 no run-level test of the cap, the writer's provider error or a degraded harvest (plan 6944 credits Task 7 with them) — carry to Task 8's review scope or the final review.
Task 7: minor (deferred): m2 replay test does not pin that the replay index gets the generated documents.
Task 7: minor (deferred): m3 test_generator_unlocks_are_no_ladder_unlocks does not fail without the note_records skip.
Task 7: minor (deferred): m4 fire() makes every request's writer calls before the session writes any line.
Task 7: minor (deferred): m5 the "+ rep" seed term is untested.
Task 7: minor (deferred): m6 the fill patterns are written out twice.
Task 7: minor (deferred): m7 add_generated ignores a different document under a recorded id.
Task 8: minor (deferred): m1 arms pool every condition sharing a generator setting (generator.py:76-80 groups by (model, arm) only).
Task 8: minor (deferred): m5 reflow artifact in overlay_generator_rules.yaml:6 header.
Task 8: minor (deferred): m6 overlay_generator_rules.yaml copies overlay_target_rules.yaml wholesale for one reply (the stub format has no include).
Task 8: minor (deferred): m8 the test_progression.py defaults assertion is redundant (brief-mandated).

## Carries to the final review
Task 3: parked — "come back to you" with a modal or "to <verb>" (Important, a breaker-fix regression), _STAFF vehicle nouns, "If needed/preferred you can", comparative without "than", the two docs inaccuracies — Ruling: real and deferred to the Phase 3 final-review fix wave as one batch with the other deferred minors; harmless before Phase 7 since no real generator call happens — cost if wrong: one more billboard class open until the final review.
Task 4: complete (commits 34ae36b..9128cba, 4 parked: CTX residual, XS2 residual, next-sentence question recall loss, plus the breaker adjudication; minors deferred to the final review)
