# Phase 3 final review: the world generator (807bddf..24b9a25, Tasks 1 to 8)

Reviewer: senior code review, whole branch. Range: base 807bddf (the plan commit), head 24b9a25 (Task 8 complete), 29 commits. Read-only on a dirty checkout (Task 9 in progress): no tests or working-tree commands were run; every claim below is from the committed range.

How the diff was read: `review-807bddf..24b9a25.diff` (23,023 lines) in passes, by concern rather than by file order:

1. Resume core: `records_env.py`, `runner/store.py`, `runner/env_turn.py`, `runner/runner.py`, `environments/runtime.py`, plus `git show 24b9a25:` of the unchanged call sites (`_CellRun`'s `after_target_turn` call, `EnvironmentSession.rewatch`, `CorpusIndex.visible/searchable/search`, `chat_text`, `JudgeCache.get/put`, `RateLimitError`).
2. The generator and its inputs: `environments/generator.py`, `harvest.py`, `redact.py`, `corpus.py`, `mcp_server.py`, `world.py`, `config.py`, `environments/config.py`, `authority.py`, `enums.py`.
3. Lints: `planner/lints.py`, `planner/second_person.py` (read whole, not re-probed: its precision numbers are ruled and parked).
4. Analysis: `analysis/generator.py`, `load.py`, `progression.py`, `replay.py`, `run_analysis.py`.
5. Tests and fixtures: every new test module in full (`test_attempt_marker`, `test_generator_plan`, `test_generator_writer`, `test_generator_runtime`, `test_generator_run`, `test_generator_analysis`, `test_redact`), the modified ones (`test_store`, `test_replay`, `test_records_env`, `test_records`, `test_config`, `test_env_config`, `test_authority`, `test_boundary`, `test_sanctuary`, `test_progression`, `test_phase2_charts`, `test_world`, `test_runner_idle`, `helpers.py`), the first 200 lines of `test_harvest` and `test_lints`, the fixture doubles (`generator_stub.py`, `fake_claude.py`), the data files (`world_generator.md`, `generator_reflexive.yaml`, the three world sheets, `overlay_generator_rules.yaml`, the `environment.yaml` additions, the head of `harvest/items.yaml`).
6. Docs: `HANDOFF.md`, `docs/00`, `02`, `04`, `06`, `08`, the spec's "As planned" amendment. The `docs/handoff/sdd/*` snapshot (diff lines 7024 to 15613, the ledger's own briefs and reports copied into the repo) was not re-read: it is the record of this process, not code.

Every `Ruling:` line in the ledger was taken as settled; the code was judged against it, not the ruling against the spec.

## Strengths

- **Resume is a function of the streams, and it is pinned on real records.** A fire's lines go documents, then `generator` unlocks, then the `GeneratorFire` (`claude_bully/runner/env_turn.py:750-759`); `drop_uncommitted_generation` (`claude_bully/runner/store.py:153-195`) drops exactly what no committed fire of a written turn lists; `WorldGenerator.prime` reloads the rest and `fire` dedupes on `(turn, reason)` (`claude_bully/environments/generator.py:949-963, 1005`). `test_a_rep_killed_mid_generation_resumes_to_the_unbroken_records` compares whole record views over four kill points (the harvest LLM call among them), and `test_a_fire_whose_line_is_written_is_never_made_again` pins the P13 case (fire line on disk, commit not run: no cache entry, the writer not asked again, one `ResumeRecord(turn=3, dropped={})`).
- **P13 is honoured exactly as ruled.** `DocWriter.write_fire` returns `cache_puts` and never writes; `DocWriter.commit` writes them, called only after `self._record(result.fire)` (`env_turn.py:759`, `generator.py:764-771`); `test_write_fire_leaves_the_cache_untouched_until_commit` and the kill tests assert the cache directory is empty after a kill.
- **The attempt marker closes the Phase 2 I4 gap for the four roles the plan names**, in its own atomic file, with the "written" rule per role (`runtime.py:221-241`) and at most one `ResumeRecord` per redo turn (`env_turn.py:364-381`). The harvest marker is written only before a real call, after the cache check (`harvest.py:692`), so a cache hit on resume leaves no false flag.
- **Items are consumed by policy, not by the writer**, so the arms fire on the same turns (`generator.py:1013-1020`, `test_the_non_reflexive_arm_fires_on_the_same_turns_with_nothing_offered`), and a rejected or errored fire holds nothing (`test_a_rejected_pair_leaves_its_items_for_the_next_fire`, `test_a_rejected_seam_pointer_commits_neither_document`).
- **The planner is pure and seeded by the plan index**, which is the number of plans recorded before (rejected fires included), so a resumed rep plans the same addresses, dates and authors (`generator.py:1022-1026`; `test_the_generator_seed_and_the_plan_index`). The address check keys urls as the corpus index does (`norm_url`, the Task 5 I1 fix), pinned by `test_the_planner_and_the_corpus_index_agree_on_a_urls_key`.
- **Replay of calls on resume sees generated documents from the turn after their fire** (`runtime.py:712-722`), and the only consequence that could differ, a yield-on-retry count on a seam document reached by layer rather than by name, is pinned by its counterfactual (`test_the_replayed_calls_see_a_seam_document_unlocked_by_name`).
- **Both backends serve generated documents alike**: `McpState.generated` is added to the index the MCP server builds per call (`mcp_server.py:325-326`), BM25 is built per query over the searchable set so content search covers them (`corpus.py:316-319` at HEAD), and the end-to-end test drives `fake_claude` through search, fetch and read_file to the buried document, with the buried one never a search hit (`test_a_claude_p_target_follows_a_seam_pointer_to_a_generated_document`, `test_the_mcp_server_serves_committed_generated_documents`).
- **Non-negotiables hold.** The harvest and the writer read `chat_text` only (`generator.py:966-972, 540-554`), and `test_the_reasoning_channel_never_reaches_the_harvest_or_the_generator` sweeps every prompt and every file under the run root for the private string. The persona file is scanned line by line against the Boundary list and whole against all three denylists; the stub's bodies are scanned too. `values_loosened` reps leave every arm rate with the count stated (`analysis/generator.py:70-102`; the chart footnote and `generator.json` note are asserted). Generator unlocks carry `bully_line_used=None` (`generator.py:1038-1047`): nothing announces a generated document. Real names in test code are the two lint positives P28 allows.
- **The lints fail closed and the retry path is honest**: one `second_person` result per failing sentence with the repair hint, `real_name` and `boundary` matches not echoed, a quoted real name redacted in the served body with the original kept (`test_a_real_name_inside_a_quoted_span_is_redacted`, `test_a_real_name_outside_a_quote_is_retried_then_rejected`).
- **Task 8's chart tests assert literal labels and hand-derived bar heights**, not just "a file exists", and the no-generator runs are pinned to write nothing.

## Issues

### Critical

None found.

### Important

**I1. A torn or corrupt cache file is a permanent crash, and Phase 3 made a torn file likely.**
`claude_bully/metrics/judge.py:98-107` at HEAD: `JudgeCache.put` is a bare `write_text` (not atomic) and `get` is a bare `json.loads` (raises on damage). Phase 3 placed the generated-cache write right after the fire line (`env_turn.py:759`, the P13 ordering), so a process killed inside `DocWriter.commit` (the exact kill `test_a_fire_whose_line_is_written_is_never_made_again` simulates by monkeypatch, but with a half-written file instead of none) leaves `runs/_cache/generated/<key>.json` torn. The same rep is safe (its fire is recorded, so `_from_cache` is never consulted), but every later run of the same experiment under that runs root computes the same key (`test_a_committed_fire_is_a_cache_hit_for_the_same_conversation` shows the cross-run hit is by design) and dies in `_from_cache` (`claude_bully/environments/generator.py:773-790`) with a raw `JSONDecodeError` from inside the fire, on every resume, until someone deletes the file. The harvest cache has the same shape (`harvest.py:687-691`; this is the ledger's Task 4 M3, which was graded Minor before the commit-after-fire-line ordering made a torn write the likelier case).
Why it matters: a real Phase 7 run interrupted once can become unrunnable, and the failure names nothing a user can act on.
Fix: in `JudgeCache`, write through a temp file and `os.replace` (the `_write_atomic` pattern `runtime.py` already uses), and have `get` return None on `ValueError` (the house pattern the ledger cites at `judge.py:162`), so a damaged entry is a miss, as a failing hit already is (`test_a_cached_reply_that_fails_now_is_a_miss`). Two small changes in a Phase 1 helper; add one test per cache.

(The ledger's own Important, the `second_person` "come back to you" regression at `claude_bully/planner/second_person.py:738-740`, is confirmed present at HEAD: an object "you" after "to" or "back" passes whenever a `_TO_VERBS` form (`come` is one, :485) sits in the clause under a modal licence. It is ruled for this fix wave and triaged below, not counted again here.)

### Minor

**m1. `GeneratorFactory` falls through to a real provider for the judge role.** `tests/fixtures/generator_stub.py:432-441`: when `judge` is None, a `JUDGE_MODEL` role (provider `anthropic` in `_exp(judge=True)`, `test_generator_run.py:97-102`) reaches `build_provider`. Every current test passes a `HarvestJudge`, but a future `_exp(judge=True)` without one builds a real Anthropic provider inside the suite. Fix: raise in the factory when the judge role arrives with no double.

**m2. No run-level test puts an LLM-sourced item through a fire.** `HarvestJudge` always answers `{"items": []}` (`generator_stub.py:410`), so `_order`'s heuristic-before-LLM ordering (`generator.py:175-180`), `MAX_OFFERED` over mixed sources and an `h-<t>-x<n>` id in `used_items` are exercised only in `test_harvest`'s unit tests. Fix: one `HarvestJudge` mode that returns a valid span, and one assertion on the buried document's `used_items`.

**m3. The writer prompt lists the pair's buried document under "Documents the reader can already reach".** `generator.py:669-671` builds the list from `view.visible`, and `with_documents` marks the just-written buried document visible (`generator.py:151-159`), so the seam pointer's prompt names, as already reachable, the one document only this pointer makes reachable. Harmless for the stub; a real model may write "as noted in <buried title>" as if it were common knowledge. Fix: label the section "Documents in the world" or pass the pointer its target separately.

**m4. Duplicate stem line in `_SPEECH_STEMS`.** `claude_bully/environments/harvest.py:313` ("figures figured") and `:339` ("figure figures figured figuring"); harmless because the forms become a set.

**m5. `EnvironmentSession.prime` reads the trigger stream twice** (`env_turn.py:377` for the dedupe, `:382` for the prime). One read, reused, is enough.

**m6. The plan's own Decisions list is stale on the harvest span.** The Plan Decisions ruling says a heuristic span "is its clause, trimmed of `.,;:!`"; the code and the spec amendment say the whole sentence trimmed of a trailing `.` or `!` (`harvest.py:21-25`, spec line 230). The amendment is authoritative; the plan should say so where it contradicts it.

**m7. The runtime docstring overclaims the marker.** `claude_bully/environments/runtime.py:12-13`: "Before every provider call the runtime names it in attempt.json". The trigger fallback, the idle fallback and the responder are provider calls and are not marked (see Declined). This is the ledger's Task 1 minor, still open at HEAD; one sentence.

**m8. `harvest.py`'s module docstring names one residual, `docs/02` names two.** `harvest.py:20-22` describes the context class only; the report-two-sentences-later class (XS2) is in `docs/02-ENVIRONMENTS.md` and the spec amendment. The ledger's Task 4 minor; one sentence.

## Triage of the parked and deferred list

Parked (with rulings):

- Task 3 F2 legit false fails (15 percent): stays parked (ruled; Task 8 should report rejection rate per kind, see Recommendations).
- Task 3 semantic billboard residual: stays parked (Phase 7 LLM lint; the load-bearing carry is already in HANDOFF).
- Task 3 N5 residual (a quote containing a sentence end yields a span the document lacks): fix now. Ruled "deferred to final review"; the retry message is the repair path, and it should never name text the generator did not write (`second_person.py:1060-1066`, `_source`).
- Task 3 billboard target unmet on family_faq: stays parked (Phase 7 carry, ruled).
- Task 3 "come back to you" with a modal or "to <verb>" (Important), `_STAFF` vehicle nouns (`second_person.py:559-565`), "If needed/preferred you can", comparative without "than", the two docs inaccuracies: fix now, as one batch, as ruled for this wave.
- Task 3 F2 recovery_guide 15/20: stays parked (ruled).
- Task 4 CTX residual: stays parked (ruled; Phase 7 measures on real text).
- Task 4 XS2 residual: stays parked (ruled).
- Task 4 CTX (round 5): stays parked (ruled).
- Task 4 cast-question recall loss: stays parked (ruled fail-closed).
- Task 4 breaker adjudication: a ruling, nothing to triage; the code honours it (`runtime.py:536`, `test_the_harvest_gets_the_cast_names_only`).

Deferred minors:

- Task 1 runtime.py docstring (every provider call is marked): fix now (one sentence; m7 above).
- Task 1 `_view` compares (type, id, turn): stays parked.
- Task 1 untested (bully rate-limited, fixed-mode intent, dropped lines plus dead marker): stays parked.
- Task 2 `reachable_names` duplicates `_reached`: stays parked.
- Task 2 untested bare-reply branch, blank model_name: stays parked.
- Task 2 test_authority imports from test_guardrails: stays parked (known handoff minor).
- Task 2 no MCP end-to-end of the not-found text: stays parked.
- Task 3 staff-addressed memos fail (record in docs/08): fix now (one docs line, as ruled).
- Task 3 docs/08 Billboard row omits curly-apostrophe mapping: stays parked.
- Task 3 lints.py `_WORD` lacks Final: fix now (trivial, ride the wave).
- Task 3 "thank you for your service as a program" passes: stays parked.
- Task 3 N6 dead branch: stays parked.
- Task 3 N7 size and overlapping verb classes: stays parked (the Phase 7 LLM-lint decision settles whether this module shrinks or is replaced).
- Task 3 N8 docstring prepositions: stays parked.
- Task 4 M1 dead alternatives: stays parked.
- Task 4 M2 curly-apostrophe word count: stays parked.
- Task 4 M3 corrupt JudgeCache entry raises: fix now, together with I1 (same two-line change).
- Task 4 M5 `text.find` first occurrence: stays parked.
- Task 4 M7 cache key omits judge model and prompt version: stays parked (plan-mandated, mirrors the trigger cache), but it must land before Phase 7 changes the judge model, else stale harvest answers survive under `runs/_cache/triggers` (see Recommendations).
- Task 4 M8 replay line raw span: stays parked.
- Task 4 M9 harvest_probe mypy: stays parked (outside the gate).
- Task 4 M10 LLM-path test gaps: stays parked.
- Task 4 fix-round recall losses: stays parked.
- Task 4 95 percent bar on reviewer probes: stays parked (Phase 7 measures).
- Task 4 `_HEDGE` "'m unable to" dead: stays parked.
- Task 4 next-sentence check on noun uses: stays parked.
- Task 4 next-sentence check omits colon and quote triggers: stays parked (follows the ruling).
- Task 4 HANDOFF.md:102 overclaim: closed by the Task 4 docs-sync as far as the HANDOFF diff shows (the round summary now says "whole-sentence templates"); nothing to do.
- Task 4 harvest.py docstring omits XS2: fix now (one sentence; m8 above).
- Task 5 m2 duplicate config-default tests: stays parked.
- Task 5 m4 GeneratorFire cross-field validator: stays parked.
- Task 5 m6 replay lint line raw message: stays parked.
- Task 5 m7 v2 generated stream read alone: stays parked (no v2 file exists).
- Task 6 m4 Fix lines repeat the span: stays parked.
- Task 6 m5 test doubles and view-building duplicated: stays parked.
- Task 6 m6 unwrap fixtures pin a procedural "you": stays parked.
- Task 6 m7 persona rule 4 allows bare imperatives: stays parked (ruled).
- Task 6 stray `"` disables joining: stays parked.
- Task 7 m1 run-level tests for cap, writer error, degraded harvest: closed by Task 8 (`test_a_writer_error_is_a_fire_with_no_documents_and_the_arm_reads_it`, `test_a_fire_over_the_cap_is_rejected_and_the_arm_reads_it`, `test_a_degraded_harvest_is_marked_on_the_plans_and_the_arm_reads_the_run`).
- Task 7 m2 replay test does not pin the replay index gets generated documents: stays parked (the runtime-level pin exists: `test_the_replayed_calls_see_a_seam_document_unlocked_by_name`).
- Task 7 m3 `test_generator_unlocks_are_no_ladder_unlocks` does not fail without the skip: stays parked.
- Task 7 m4 `fire()` makes every writer call before any line is written: stays parked (a real-model cost only: a two-fire turn killed in the second fire redoes the first's calls; records still equal an unbroken run's).
- Task 7 m5 "+ rep" seed term untested: stays parked.
- Task 7 m6 fill patterns twice: stays parked (`fake_claude.py` is a standalone script by design).
- Task 7 m7 `add_generated` ignores a different document under a recorded id: stays parked.
- Task 8 m1 arms pool every condition sharing a generator setting (`analysis/generator.py:75-78`): stays parked for the shipped config (one condition per arm), but it is wrong the day a config has two conditions in one arm; note it for Phase 7.
- Task 8 m5 reflow artifact: closed in Task 8 fix round 1.
- Task 8 m6 stub script copies the target rules wholesale: stays parked.
- Task 8 m8 redundant defaults assertion: stays parked.

Fix now: 7 lines of the list (the Task 3 batch, N5, the Task 1 docstring, the docs/08 memo note, `_WORD` Final, M3 with I1, the harvest docstring).

## Declined to judge

- The trigger fallback, the idle fallback and the authority responder are provider calls that are not attempt-marked; a death inside one at turn N leaves `target N` written and the rep unflagged. The plan's Task 1 names four roles and Task 7 binds them; this is the Phase 2 gap narrowed, not a Phase 3 defect.
- A rep whose LLM harvest was degraded, killed before `mark_watched`, may on resume get a successful LLM pass and extra `x` items. The dead attempt's degraded flag was never saved and its items never written, so the result equals an unbroken run that happened to succeed; "replays from JSONL" is kept. Provider nondeterminism, outside the spec.
- Two `generate: true` rungs opening on one turn share one `CorpusView` from the session (`env_turn.py:749`) while `WorldGenerator.fire` chains `with_documents` per request; on a resume between the two fires the primed `corpus_view()` already holds the first pair. The two derivations agree because the buried document's rung fired that turn. Not pinned by a test; the shipped ladders never open two generate rungs in one turn.
- `verbatim_in_seam` ignores spans under three words (`MIN_QUOTED_WORDS`), so a one- or two-word coinage may appear verbatim in a periodic seam document. A plan constant, by design.
- A death after `_generate` on a turn whose fire was a cache hit leaves the marker at `target N` (no provider call was made), so no `ResumeRecord` is written though the turn is re-watched; the rewatch is idempotent and the records equal an unbroken run's. The marker flags provider calls, as designed.
- `configs/environments/generator_reflexive.yaml` names `sonnet`, `opus` and `haiku` and `display_name: Claude`: the convention every Phase 2 config already follows, and the real-name scan exempts display names and does not read config model strings.
- "Reuters" and "Claude" in `tests/fixtures/generator_stub.py` and `test_generator_writer.py` as lint positives: P28.
- The `second_person` and harvest precision numbers: ruled and parked after their own probe rounds; I read the modules for structure and did not re-probe.
- `honest: true` and `assert_date: false` refusing an enabled generator: ruled.
- The hostility ceiling: Phase 3 adds no bully text; the N1 reply and the generator unlocks hand the bully nothing.
- `RunEnvironments.judge()`'s "a stub judge is no fallback" rule: Phase 2.
- The Task 9 working-tree edits: out of range by instruction.
- The `docs/handoff/sdd/*` snapshot: process record, not code.

## Recommendations

1. Make `JudgeCache` atomic on write and degrading on read (I1, M3): one helper, two tests. Do it in the fix wave; it is the only new Important.
2. Run the ruled fix wave: the `second_person` batch (the "come back to you" licence at `second_person.py:738-740`, the `_STAFF` vehicle nouns, "If needed/preferred you can", comparative without "than", the two docs lines), N5's `_source` fallback, and the three docstring and docs lines (m7, m8, the docs/08 memo note), plus `_WORD: Final`.
3. Before Phase 7's first real run: put the judge model and a prompt version into the harvest cache key (M7) and, if the trigger cache shares the shape, there too; otherwise a judge change silently reuses old answers under `runs/_cache/triggers`. Also group `arm_rates` by condition as well as arm (Task 8 m1) before any config carries two conditions in one arm, and report the generator's rejection rate per kind in `generator.json`, which the Task 3 F2 ruling asked for and Task 8 did not add (`arm_rates` counts documents written, not fires rejected).
4. Add the two cheap tests: an LLM item through a fire (m2) and the `+ rep` seed term (Task 7 m5). Guard `GeneratorFactory` against a judge role with no double (m1).
5. Decide in Phase 7's planning whether the trigger, idle and responder calls get an attempt marker; the mechanism is one line each and would make "resumed after a dead attempt" mean every provider death.
6. Where the plan was wrong, for the record: the spec's "generator unlocks need no special case" (corrected by P29, four consumers); the plan's clause-scored harvest heuristics and its allowlist-shaped `second_person` lint, both replaced by fail-closed whole-sentence or anchor-plus-veto designs over five rounds each; Task 8's brief assumed `overlay_target_rules.yaml` would harvest something (it does not; a new stub script was needed); plan line 6944 credited Task 7 with run-level tests it did not have; the P13 carry's wording ("re-asks the writer") was the opposite of the behaviour the ruling wanted; and the Plan Decisions list still states the pre-fix harvest span rule (m6).

## Assessment

Ready: With fixes. The resume model, the non-negotiables and the cross-task seams are sound and pinned on real records; the one new Important is a two-line hardening of a Phase 1 cache helper that Phase 3's commit ordering made load-bearing, and the rest of the wave is the ruled `second_person` batch plus docstrings.
