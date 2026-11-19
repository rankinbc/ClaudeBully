# Phase 5 plan review

Plan: `docs/superpowers/plans/2026-11-14-phase-5-director.md` (13 tasks). Spec: `docs/superpowers/specs/2026-11-14-phase-5-director-design.md` (binding). Code: `build/v1` at 29ba4e0 (the plan was checked at 38dcc70; the only change since is the plan file itself).

Method: I read the plan's code blocks against the tree and ran parts of them read-only, from the scratchpad with `PYTHONDONTWRITEBYTECODE=1`. Nothing tracked was edited and the suite was not run. What I ran:

- the plan's `walk_lines` as written, and every world-level lint rule as the plan states it, over `overlay`, `mini` and `annex`;
- the dry run's scripted search against the real `CorpusIndex` after a full walk of every shipped ladder;
- whole-file Boundary, real-name, jailbreak and reserved-host scans over the three worlds and over `configs/environments/triggered_vs_scheduled.yaml`;
- the real-name and jailbreak scans over docs/08's two prompt blocks, verbatim and reworded, and over the confirm prompt; a byte comparison of the plan's quoted reviewer prompt with docs/08's block;
- the plan's lint fixture lines against the real shapes, `dating` and `TriggerWatcher`;
- `check_condition` on a misspelt param for a sheet premise;
- the strategy registry under the `isolated_registry` patch in a fresh process;
- a stub run of `triggered_vs_scheduled` killed inside the third target call and the third bully call, resumed, with the ledger compared to an unbroken run's;
- the planner message's inputs (docs/01 to 07) against the plan's two leak tests;
- the three pinned world hashes.

## Verdict: Ready with fixes

The architecture holds: record before file, one call primitive, the cache put last, a rate limit that commits nothing, closed lints, and a dry run that is an ordinary run. Most cited code is as the plan says. One Critical finding (a dry-run rule that fails the shipped overlay ladder and so blocks the example bundle) and nine Important findings need edits to the plan before Task 1. Each fix is local.

Counts: Critical 1, Important 9, Minor 17.

## Critical

**C1. Task 5 and spec section 10: the dry run's buried-search rule fails the overlay's own ladder, so the example bundle can never be `runnable`.**

- Location: Task 5 Step 3, `dry_run_script` ("a `web_search` step for the title of the first buried document (by id) that the ladder's top-most opening rung opens") and the `dry_run` lint ("a `buried_search_hit`" fails). Spec section 10 says the search "must return no buried hit".
- What the code does: a buried document is searchable once a rung names it by id (`CorpusIndex.searchable`: `doc.id in state.docs_unlocked`). The overlay's `the_truth` rung does exactly that, on purpose: `unlocks: [cpo-review-4471-r3]`, with the comment "an id unlock makes it searchable" (`data/worlds/overlay/ladders/default.yaml`; `authority.yaml` is the same). `lint_world`'s docstring says the same thing is by design.
- Measured: after the walk, `index.search("Placement review 4471-r3", state)` returns `cpo-review-4471-r3` on `default` and `authority`. The query holds no censorship term. The four Poisoned Well ladders, `mini` and `annex` return no buried hit.
- Effect: Task 5's tests pass (they run the mini bundle). Task 12 is the first to dry-run the overlay: every tooled cell of `triggered_vs_scheduled` records `buried_search_hit: true`, the `dry_run` lint fails, the bundle is `validated` and not `runnable`, and `test_the_example_is_there_and_hand_authored` and `test_every_bundle_passes_every_lint` fail. The rework lands seven tasks after the rule is built, and rung D inherits it.
- Fix: define the hit from the records: a buried document in a `web_search` result that no fired rung names by id. In `dry_run_script`, search for the first buried document the walk leaves unsearchable (opened by a layer or by `unlock_rung`), and skip the search step when every buried document the ladder opens is named by id; the fetch step keeps the top rung's document. Add a Task 5 test that scripts and stub-runs `triggered_vs_scheduled` on the overlay, so Task 12 is not the first to meet it. Record the change as a departure from spec section 10.

## Important

**I1. The scoped registry snapshots a registry that may not be loaded yet, and then empties it for the rest of the process.**

- Location: Task 4, the `isolated_registry` fixture (`monkeypatch.setattr(base, "_REGISTRY", dict(base._REGISTRY))`) and `plan_personas` ("restores `_REGISTRY` to its prior contents on exit"); Task 10, `register_plan_personas`.
- What the code does: strategies register lazily. `ensure_registered` is `lru_cache`d and runs the `@register` imports once (`strategies/bootstrap.py`). Nothing in the plan calls it on the planner side.
- Measured in a fresh process: 0 strategies at import; patch a copy in; `ensure_registered()` puts 36 into the copy; undo the patch; `ensure_registered()` again; `all_strategies()` is empty, for good.
- Effects:
  - Production: `plan validate`, and a `plan continue` that enters stage 5, in a fresh process. The first `plan_personas` block (`lint_bundle`, the `schema` lint) snapshots an empty registry, `run_experiment(dry_run=True)` loads the 36 inside the block, and the exit restores "prior contents", which is empty. The next block (`dry_run`) fails with `unknown strategy`.
  - Tests: any file run alone whose first test takes `isolated_registry` leaves every later test with no strategies. The plan's own commands do this: Task 9's `pytest tests/test_plan_cli.py tests/test_plan_parity.py tests/test_cli.py` then fails `test_list_strategies_lists_36`, and Task 6's `test_the_capabilities_list_the_registered_strategies...` passes with nothing to check.
  - The `schema` lint's "no persona name is a registered strategy" check and `register_plan_personas`' coded-strategy refusal read an empty registry and pass a persona named `captor`; the later load then overwrites it silently.
- Smaller leaks in the same area:
  - Task 11's shared `stub_bundle_run(tmp_path)` is a plain function that calls `register_plan_personas`; a test that uses it without `isolated_registry` leaves `ferry_caller` registered for the rest of the suite.
  - Task 5's `test_the_factory_serves_the_four_doubles_and_refuses_a_fifth` builds per-cell scripts (`expand_cells`) with no persona registered.
  - `cli.run` calls `expand_cells` for `--only` before the plan's bundle detection registers anything.
- Fix: `isolated_registry`, `plan_personas` and `register_plan_personas` each call `ensure_registered()` first. `plan_personas` removes or restores only the names it registered. Make `stub_bundle_run` a fixture that depends on `isolated_registry`. `dryrun_provider_factory` builds its scripts inside `plan_personas`. `cli.run` detects the bundle and registers before the `--only` check. Add one subprocess test: `plan validate` on the good bundle in a fresh interpreter.

**I2. Resume: `plan continue` on a failed stage records a dead attempt that never died, and the ruling has no test.**

- Location: Task 7 Step 4, `Director.run`: `_reopen_failed(existing)`, then `rematerialize_open_stage`, then `_record_dead_attempt(existing)`; the D-failed-stage ruling.
- What the code does: `ask` writes `.attempt.json` naming index N before the call and never clears it (only stage 5 and a rate limit do). An `error` call commits at index N. On `plan continue`, `_reopen_failed` moves that call out, so `len(calls)` is N again, and `_record_dead_attempt` sees a marker "at or past `len(calls)`" and appends it to `resumed`.
- Effect: every continued provider error, timeout or twice-failed file adds a false entry to `PlanRecord.resumed`. No test continues a failed stage at all: `run_plan` resumes only after a `Crash`.
- Fix: record the dead attempt before `_reopen_failed`, and clear the marker once it is read (or when an `error` call commits). Add tests: a `provider_error` on a file call, then continue, gives `resumed == []`, the error's transcript under `transcripts/failed/`, and a bundle equal to an unbroken plan's.

**I3. Resume: `ask` has no place to commit record fields with a call, so the manifest and the world copy can be lost between two writes.**

- Location: Task 7, `ask` (given as code) and `author()` ("it commits `record.manifest`"; D-copy, "each such world is copied right after the manifest commits"; "`base_worlds` and `base_files` committed in one record write after the files").
- The problem: the manifest call has no file outputs, and `ask` writes the record before it returns. Nothing in `CallSpec` can set `record.manifest` inside that write. The natural implementation sets it after `ask` returns, in a second write. A plan killed between the two has a committed manifest call and an empty manifest; resume skips the call and authors nothing. The same window exists for the D-copy case with `base_world: None`: the copy is not a call, so a resume that skips the committed manifest call can skip the copy.
- No kill test sits there: K2 dies inside the manifest call, and K5 is tested on a file call only.
- Fix: add `commit: Callable[[Any, PlanRecord], None]` to `CallSpec`, applied before `write_record` in `ask` (or read the manifest from the committed transcript on resume, and say which). Key the copy on `base_worlds` membership, not on the call. Add `Kill("record", "manifest")` and `Kill("files", "manifest")` to `KILLS`, once with `base_world` set and once with None.

**I4. Resume: `review.md` is written after stage 3 commits, and nothing writes it again for a committed stage.**

- Location: Task 8 Step 3, `review()`: "the stage committed (the record write), and `review.md` is written ... (the file after the record, spec section 8)".
- The problem: section 8's rule is about a call's record and its file. `review.md` is derived from every committed review call, so it is safe to render before the stage flag is set. As planned, a plan killed between the two writes resumes with stage 3 committed and no `review.md`. Stage 4 then records its `inputs` without it, so `plan.json` differs from an unbroken plan's outside timestamps and `resumed`. This is K11 at the review boundary; the plan's K11 test kills after `author`, where no such file exists.
- Fix: render `review.md`, then commit the stage (a resume with every call committed renders the same bytes again). Add a checkpoint between the two and a kill test there.

**I5. `rounds` is not built by any task, and the archive step makes old calls point at new transcripts.**

- Location: D-rounds; Task 9, `Director.review_round`; Task 1's Interfaces.
- Findings:
  - Task 1's `PlanRecord` is "spec section 4's fields plus `base_files`". `rounds` is in no task's model, no test round-trips it, and Task 9's file list does not touch `planner/records.py`. The model is `extra="forbid"`.
  - The archive moves transcripts to `transcripts/round-<n>/`, but each archived `DirectorCall.transcript` still names `transcripts/<stage>-<role>-<index>.json`, which the new round's calls then write. An archived revise call now points at another round's reply.
  - `materialize` walks `stages`. After one `plan review`, round 1's revise outputs are in `rounds`, so the rebuild of spec section 12 row 8 skips them.
  - The archive is several writes with no stated order and no kill test. Killed after the transcripts move and before the record is written, the committed review calls name files that are gone, and `findings_of` raises on the next command.
  - Task 9's test runs `plan review` after a full plan. The reviewer double's default block quotes "a sentence of `DOC1`", which round 1's revision replaced; if the double quotes from the fixture file and not from the message, `check_findings` refuses the reply twice and the test fails.
- Fix: add `rounds` to Task 1 with a round-trip test. Rewrite each archived call's `transcript` to its round path in the same record write. Order the archive: copy the transcripts, write the record, delete the old files. Make `materialize` walk `rounds` before the current stages. Say that the reviewer double quotes from the file text in its message. Add one kill test between the copy and the record.

**I6. The dry run is not a pure function of the bundle: the generator double counts calls, and the generated cache outlives a run.**

- Location: Task 5 Step 3, `DryRunGenerator` ("the plan index is the count of writer prompts this instance answered, kept per conversation id so a rebuilt provider draws the same") and `dry_run` ("remove every `dryrun/dryrun-*` directory but this id's").
- Findings:
  - A count kept by an instance starts at zero in a rebuilt provider. On a ladder with two generating rungs (the overlay's `buried_opens` and `the_truth`), a dry run killed in the second fire and resumed answers that fire with index 0, the body the first document already holds. Spec section 10's own rule is that a double answers from its messages, never from the instance. The K12 test kills generator call 1 on a one-fire ladder and cannot see this.
  - `run_experiment` keeps `_cache/generated/` under the runs root (`runner/env_turn.py`, `GENERATED_CACHE_DIR`), here `<bundle>/dryrun/_cache/`. It survives the old run directory, so the second dry run of a bundle records its fires `cached`, not `written`. `DryRunCell.generator` then depends on whether the bundle was validated before, and a checked-in bundle that was validated twice fails Task 12's comparison with a fresh dry run.
  - `test_a_changed_bundle_gets_a_new_run_id_and_the_old_directory_goes` asserts `iterdir()` is `[second]`; the good bundle's generator is on, so it is `["_cache", second]`.
- Fix: seed the draw from the plan itself (its address or slug, both in the prompt's plan JSON). Remove `dryrun/_cache` with the old run directories, or count `cached` as `written` in `DryRunCell`. Fix the test's expected listing. Add a generator kill at the second writer call on a two-fire ladder.

**I7. Tests and helpers that fail as written. Each was checked by running the code it names.**

- **Task 3, `_line`.** It loads the unlock line with `yaml.safe_load` and asserts the loaded string is a literal of `world.yaml`. The overlay writes its lines as folded scalars over two lines, so the assert fails for 8 of 11 keys, `fragment_line`, `first_crumb_line` and `the_memo_line` among them. Every `bully_line` case uses it. Fix: rewrite the `unlock_lines` mapping through YAML in the copy.
- **Task 3, the `bully_line` near-misses.** "Each of the 16 `REACTS` lines" must pass, but "Look, I don't know." matches `ANNOUNCE_OPENERS`. Fifteen pass. Fix: name the fifteen, and list that line as a positive. Task 4's persona near-miss ("an entry from `REACTS`") must not pick it.
- **Task 4, the `schema` positive.** "A condition's `params: {stage_lenght: 3}` (refused by `check_condition`)" is accepted: a sheet premise has no `params_model`, and the good bundle's conditions use the bundle persona. `check_condition` refuses the same key on `rescue`. Fix: put the case on a condition whose class has a params model, and state the residual (a bundle persona's params are not validated), or give sheet premises a model.
- **Task 4, 5 and 8, "the good bundle passes every lint".** `lint_bundle(good_bundle) == []` with warnings counted, but mini's `night-gate-log` carries a Phase 3 `premise_density` warning (0.140), and Task 8's test pins that file as unchanged. Fix: say `lint_bundle` keeps Phase 3's fail results only, or patch the file and change Task 8's pin.
- **Task 6, `test_no_director_message_holds_a_run_or_a_result`.** It asserts `"runs/" not in message`. `docs/02-ENVIRONMENTS.md` is in every default planner message and holds `runs/` four times (`runs/_cache/generated/`). Fix: plant a sentinel file under a runs root and assert its text is absent.
- **Task 6, `test_the_planners_message_holds_no_text_of_docs_08_09_or_10`.** `_long_lines` counts table rows: `| --- | --- | --- | --- |` and `| Experiment | Varies | Fixed | Question |` are in docs/09, docs/10 and docs/01 to 07. docs/08 shares no line. Fix: count alphabetic words.
- **Task 1, the import.** `request.py` imports `WINDOWS_DEVICE_STEMS` from `bundle.py`, `bundle.py` imports `PlanRecord` from `records.py`, and `records.py` imports `PlanRequest` from `request.py`. Fix: keep the constant in `request.py` and import it into `bundle.py`.
- **Task 2, Step 4.** `git grep -n _stubbed -- tests` is expected to find nothing, but the new test names `test_the_stubbed_experiment_...` and `test_a_stubbed_experiment_...` hold the string. Fix: `git grep -nw _stubbed`.

**I8. Tests the spec promises that are missing or prove nothing.**

- **`materialize`.** No test calls it. Spec section 1's first success line and section 15 both name the rebuild from `plan.json` and `transcripts/`; the Self-review says Task 9 covers it. Fix: in Task 9, delete every authored file of a finished plan, call `materialize`, and compare the hashed files; state that base copies are checked against `base_files`, not rebuilt.
- **Review Focus 2.** `test_a_crlf_reply_commits_and_resumes_to_the_same_bytes` calls `rematerialize_open_stage` on a committed author stage, which "does nothing to a stage that is committed". It returns `[]` whatever the code does. Fix: kill at `Kill("files", ...)` on the CRLF call and resume.
- **D-A9.** The plan drops the spec's A9 assumption on the strength of a scratch trace, and commits no test for it: Task 5 checks a Poisoned Well script's length only. Fix: one slow test that dry-runs `real_vs_fabricated` on the four doubles and reaches the top rung in every arm.
- **Blindness at confirm time.** Task 6 tests the message builders before any planner response exists. No Task 8 test asserts that the confirm messages the Director sends hold no planner response text or status. Fix: assert it over `reviewer.calls` in `test_a_clean_review_and_revision`.
- **The reasoning sentinel.** The `runs/` half cannot fail: the Director takes no runs root, and the test plants the sentinel in a sibling directory nothing points at. The written-files scan also skips `plans/_cache/director/`. Fix: point `DEFAULT_RUNS_ROOT` and `DEFAULT_RESULTS_ROOT` at the planted root, and scan the cache directory too.

**I9. Non-negotiable 2: a checked-in bundle has six kinds of file outside every real-name scan.**

- Location: Task 12 Step 4 ("`plan.md`, `review.md` and `transcripts/` exempt from the real-name scan"); `SCANNED` gains bundle worlds, personas, configs and `expected.yaml`.
- The problem: the lint's exemption exists because an in-flight review quotes what it blocks. A bundle committed to the repository is different: its `plan.md`, `review.md`, `plan.json`, `transcripts/*.json`, `ledger.jsonl` and `dryrun.jsonl` are repository text, and the example's `plan.md` is written by hand in this phase. A real outlet named there is committed with no test to catch it. The same holds for `tests/fixtures/bundles/good/plan.md`.
- Fix: the CI scan over `plans/` and over `tests/fixtures/bundles/` covers every text file of a checked-in bundle, with the config spare (provider values and the target's display name) applied to `plan.json` and the transcripts. The lint keeps its exemption for a plan in flight. Rung D's report says a bundle whose `review.md` quotes a real name is not committed as it stands.

## Minor

1. Task 9's parity suite drives K4, K5, K6, K11 and K13 "through the CLI", but `planner/cli.py` exposes only `PlanProviders` and `WORLDS_DIR`. Name the checkpoint seam.
2. Task 7: K1 holds only if `_open_stage` writes the new `StageRecord` before `write_attempt`; `run` records a dead attempt only when the stage is already in `plan.json`. Say so.
3. Task 4: pin `mini_scheduled`'s schedule as `{fragment: 1, first_crumb: 2, the_log: 3}`. Task 5's budget-4 test needs `RunEnvironments.validate` to pass (it raises `ValueError` on an exchange after the shortest condition's last), and the scheduled cell's fetch needs `the_log` open first.
4. Task 6, the confirm prompt: dropping "quoted from an earlier version" is right. Add one neutral sentence, "A passage may or may not appear in the file.", or a judge that cannot find a passage answers `cannot_tell`, which leaves the block open. Say whether verdict numbers are the local ones the message shows or the finding ids (`ReviewerStub(verdicts={1: ...})` reads as ids).
5. The cache key covers the model string and the bytes sent. It does not cover the provider kind or `effort`, and the reviewer's message does not hold the request. Add both to the key's prefix, or state the residual. The date the installed CLI attaches is outside it too (rung D measures that).
6. `reserved_hosts`: the URL and email clauses are a positive rule (three reserved endings). The bare-host clause is a deny list of 15 public suffixes, so `pennetferry.xyz` passes. It is the one new clause that is not closed by construction. Close it (a dotted token ends in a reserved ending, a listed file extension or a digit) or pin the residual with a fixture and a docstring line.
7. An empty `premise_terms` (the `WorldSheet` default) makes `bully_line`'s premise clause and Phase 3's `premise_density` and `mundane_detail` pass with nothing to match. A planner can write or patch a sheet that way. Add a count to `schema`: non-empty, and for a reused world a superset of the base sheet's.
8. `write_atomic` leaves `.name.xxxx.tmp` beside the target when a process is killed outright (the tests raise, which cleans up). A leftover in the bundle changes `bundle_hash`. Have `rematerialize_open_stage` remove them, or have `hash_tree` skip them.
9. A rate limit on a call's second attempt discards the first attempt. State that the planner double picks its "first attempt" reply from the `/a1` suffix, not from its own count, or a resumed call records `attempts: 1` where an unbroken one records 2.
10. Spec section 13 fails the stage on a provider error; the plan drops a document that "fails twice". `ask` returns the same `error` status for both. Say that a provider error on a document fails the stage.
11. Task 10: `str(runnable / "worlds") in bad.output` compares a long temporary path with console output that may wrap. The test's name promises the accepted case ("unless it is the bundle's") and tests only the refusal.
12. Slow marks: Task 5's budget test runs a full dry run and `analyze_run`; several Task 7 tests run two or three author stages. The plan's rule is two seconds.
13. `PROMPT_FILES` is typed `Final[Mapping[...]]`, and Task 7's test uses `monkeypatch.setitem` on it. Make it a dict. `StubProvider(responder=...)` is typed `Responder`; `ScriptedTurns` is not callable, so widen the type for mypy strict.
14. Text slips: `GOOD_MANIFEST` "eleven world files" is ten; `good_bundle` commits the review stage "with no call" and also writes `review.md` "through `write_manual(..., stage="review")`"; Task 12 lists `ledger.jsonl`, which a manual build never writes; Task 2 says the importers change "their import line", but their call sites pass `turn_budget` by position.
15. `plan validate` on a plan that failed with open blocks sets status `validated`, so the next `plan continue` no longer prints the open-block message. Say what `plan validate` does to the status and to an existing validate `StageRecord`.
16. Task 7's world copy: state the order (open the stage and record `inputs`, copy, write `base_files`). Killed mid-copy before the stage record exists, the resumed stage records `inputs` that include the partial copy.
17. Sizing: Task 7 is the largest (the primitive, both stages, the manifest's refusals, the close and repair, three rulings, the double with eleven modes and about two dozen tests). Split it at stage 1: 7a the primitive with K1 and K4 to K6 on the plan call, 7b stage 2 with K2, K3 and K7. Task 4 (eleven lints and a 14-file fixture bundle) can split the same way.

## 1. Claims against the code

False or stale claims:

- Spec section 10 and Task 5: the scripted search "must return no buried hit" (C1).
- Task 5: "kept per conversation id so a rebuilt provider draws the same" (I6).
- Task 5: the dry-run directory holds only the run id (I6).
- Task 3: `_line` as code; "each of the 16 `REACTS` lines" (I7).
- Task 4: "(refused by `check_condition`)"; D-stub's "four mini files" beside a bundle that passes every lint (I7).
- Task 6: the expected PASS of two context tests (I7).
- Task 1: "`WINDOWS_DEVICE_STEMS` is imported from `planner/bundle.py`" (I7).
- Task 2 Step 4: "exit 1, no match" (I7).
- Self-review: "rebuild ... through `materialize`" as tested (I8); "Section 4: Task 1 (with D-base_files and D-rounds)" (I5).
- Review Focus 2: its Task 7 test (I8).

Verified as stated:

| Area | What was checked |
| --- | --- |
| The two measurements | `walk_lines` as written gives 6, 6, 12, 10, 2, 2 on the overlay and 2 on annex. D2: the overlay passes; mini fails on `canteen-menu` and `courier-fare-notice`; `annex-changelog` is 2042-11-18 with `implies_year: 2044`. D3: mini's five failures, annex none. D-outlet: both overlay outlets back themselves with a `web_page` at `/about` |
| The overlay | 46 documents, 10 surface, 10 seam, 10 buried, 16 filler; four seam dead ends; no world-level result, warnings included |
| Shipped worlds under the bundle scans | whole-file Boundary, real-name, jailbreak and host scans are clean on `overlay`, `mini`, `annex` and the example config |
| Hashes | the three world hashes equal the plan's |
| Providers | `LedgerProvider` forwards `reset_session` (`__getattr__`); `activate` nests on a different path; `RateLimitError` is a `ProviderError` and is caught first; `ClaudeCodeProvider` keeps sessions by conversation id in the state dir, so the fake-claude reset test discriminates |
| Signatures | `run_experiment`, `RunSummary`, `RateLimitExit`, `wait_on_rate_limit`, `JudgeCache.key/get/put`, `write_atomic`, `Ladder(...)`, `fired`, `on_triggers`, `WatchContext`, `asserts_current_date`, `unmovable_dates`, `LintResult`, `LoadedRun`, `unlocks_of`, `without_flagged`, `write_results_md`, `render_replay`, `_SHAPES`, `not_judged_note` |
| Prompts | docs/08 holds each reworded phrase exactly once; the reworded blocks and the confirm prompt hit neither denylist; the plan's quoted reviewer prompt equals docs/08's block with the one substitution |
| Fixture lines | the five `bully_line` positives hit their shapes; "Someone misplaced the key." hits none; the `clock_rule` and `reserved_hosts` strings behave as the tables say; `DRYRUN_BULLY_LINE` and `DRYRUN_CLOSING` fire no trigger and match no shape |
| D-K12 | a run killed inside the third target call, and one inside the third bully call, resume to the unbroken run's ledger line counts for every cell and role |
| Counts and anchors | 36 registered strategies; 15 stub scripts load as rules; the four `_stubbed` importers; `.gitattributes` forces LF; every world file is inside the path grammar; the HANDOFF and runbook anchors exist |

## 2. Order and dependencies

The order is sound, and no task's tests need a later task's code, with these exceptions:

- `PlanRecord.rounds` is used by Task 9 and built by no task (I5).
- Task 5's budget test depends on a schedule Task 4 leaves open (Minor 3).
- Task 12 is the first task to run the dry-run rule on the overlay (C1).
- Task 9's `plan review` test depends on how Task 8's reviewer double picks its quote (I5).
- Tasks 6, 9 and 10 depend on a registry another test happened to load (I1).

Task 4's `good_bundle` names `author_order` before Task 7 defines it and says what to use until then; that is handled. D-kill placement, each kill test landing with the code it kills, is the right call and makes Tasks 5, 7 and 8 reviewable alone.

## 3. Non-negotiables and the five lenses

- **No real names.** The three prompt files scan clean, and `data/personas/*.md` is already under the scan. The reworded phrase is the only hit in either verbatim prompt. The gap is the checked-in bundle (I9).
- **No jailbreak axis.** `boundary_bundle` over whole files holds on every shipped world. A review the harness cannot read fails the stage; a block closes on three agreeing signals. Holds.
- **Earned, never delivered.** `bully_line`, `trigger_examples` and `ladder_walk` are closed and pass the overlay. Two rules pass with nothing to check: empty premise terms (Minor 7) and unvalidated persona params (I7).
- **Reasoning channel.** `ask` reads `completion.text` only; the transcript holds no reasoning. The sentinel test's own-reasoning half is real; its `runs/` half is not (I8).
- **No real call.** Every Director call goes through the factory; the one `build_provider` test names the fake's command. Holds.
- **SCHEMA_VERSION 3, additive.** `RunRecord.plan` is the one run-record change. The goldens pin events, judge transcripts and the leaderboard, never `run.json`, so they stay byte-identical.
- **Judge prompts.** The confirm prompt is neutral and blind, and the plan's change to it is correct (Minor 4 adds one sentence). The `## Reply` part names fields only. The key covers the model, the system prompt, the message and the schema (Minor 5 names what it leaves out).
- **The dry-run bully.** The fixed line lives only in `dryrun_provider_factory`. `StubProvider`'s echo default, `tests/helpers.stubbed` and both goldens are untouched, and no existing test changes for it.
- **Lints.** Shipped worlds stay fail-free under every rule as stated; fixture-world failures are pinned (D3); each table carries near-misses. The exceptions are C1, the bare-host clause (Minor 6) and the fixture slips of I7.

Resume, per kill point as the plan wires it:

| Point | Status |
| --- | --- |
| K1 | correct, given Minor 2 |
| K2, K3, K4 | correct |
| K5 | correct on a file call; untested and exposed on the manifest call (I3) |
| K6 | correct |
| K7 | correct, both halves |
| K8, K9, K10 | correct |
| K11 | correct after `author`; `plan.json` differs after `review` (I4) |
| K12 | correct for a target or bully kill (run); a generator kill in a second fire differs (I6) |
| K13 | correct on a first validation; the generator's counts differ on a later one (I6) |
| Rate limit | correct: nothing commits, the marker goes, the same command resumes |
| Continue after a failed stage | a false dead attempt, untested (I2) |
| `plan review` round | unordered writes, stale transcript paths (I5) |
| `base_files` | sound as a record; its commit point with `base_world: None` is exposed (I3) |

## 4. Sizing

Tasks 4, 7 and 9 are the large ones. Minor 17 gives the split for 7 and 4. Task 9 (stage 5, five commands, the round archive and the whole parity suite) is reviewable once I5 moves the `rounds` model into Task 1.

## 5. Spec coverage

Every section maps to a task. The gaps:

- section 1's rebuild line and section 15's `materialize` bullet (I8);
- section 15's "no ... planner response" at confirm time, as a run-level test (I8);
- section 10's A9 check, replaced by a trace with no committed test (I8);
- section 13's "`plan continue` retries the stage from that call" (I2);
- section 7's "the commands' reach", whose `rounds` model no task builds (I5).

Section 10's buried-search sentence is implemented as written and is wrong against the code (C1).
