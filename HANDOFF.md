# claude-bully: handoff

This file is for picking the work up on another machine. It covers the state of the build, how to set up, how to resume, and the rules the work follows. Delete this file and `docs/handoff/` before the repo goes public.

Last updated: 2026-11-05, at Task 8 complete (one commit on top of 70864b5) on `build/v1`. Phase 3 is in progress: Tasks 1 to 8 are complete, and Task 9 is next.

## What this is

claude-bully is an adversarial-robustness harness for LLMs. Bully personas pressure a target model inside a sandboxed fake world, a document corpus served through tools. The harness measures how the target's behavior drifts: position changes, deference, temporal confusion, idle behavior and authority appeals.

It is a portfolio piece for a job search. It must show LLM interest, understanding and system-design competence to a hiring reader skimming GitHub. The README results are the product, and the harness is the proof. The most eye-catching results go at the top of the README.

The budget is near zero. The target, the bully and the judge all default to `claude -p` (Claude Code print mode) on the owner's subscription. An Anthropic API key backend exists as a config option. Never spend API budget without asking the owner.

## Repository

- **GitHub:** `rankinbc/claude-bully`. It is private, and stays private until the owner says otherwise.
- **Branches:**
  - Work happens on `build/v1`, which is also the GitHub default branch.
  - `main` exists but is behind.
  - The local branches `build/v1-finalA`, `build/v1-task7` and `build/v1-task9` are old, merged worktree branches. Ignore them.
- **Commit author:** every commit is authored by `rankinbc1@gmail.com`. Set it repo-local on the new machine. The global git email on the work machine is a work address and must never author this repo.
- **Commit trailer:** commit messages end with a `Co-Authored-By: Claude <model> <noreply@anthropic.com>` trailer naming the model that made the commit (Opus 5.5 through Phase 3 Task 6, Fable 5.1 for Tasks 7 and 8, Opus 5.5 for Task 9).
- **Pushing:** push `build/v1` after every completed task.

## Setting up a new machine

1. Install `uv` (0.11 or later) and `gh`. Run `gh auth login` as `rankinbc`.
2. Clone and check out the work branch:
   `gh repo clone rankinbc/claude-bully && cd claude-bully && git checkout build/v1`
3. Set the author email repo-local: `git config user.email rankinbc1@gmail.com`.
4. Install Python and the dependencies: `uv python install 3.12 && uv sync --all-groups --all-extras`. Without `--all-extras` the openai extra is missing and 2 openai tests skip. On Windows, `uv` installed via pip may not be on PATH: add the Python user `Scripts` folder to PATH (for example `export PATH="/c/Users/<user>/AppData/Roaming/Python/Python313/Scripts:$PATH"` in Git Bash).
5. Run the gate. Every step must pass with 0 warnings:
   - `uv run ruff format --check .`
   - `uv run ruff check .`
   - `uv run mypy claude_bully`
   - `uv run pytest -q -W error`
   - `uv run pytest -q -m slow`

   Expect 8144 passed, 5 skipped and 6 deselected in the fast suite (about 7 to 15 minutes), and 6 passed in the slow suite (both at Task 9).
6. Restore the build ledger. `.superpowers/` is git-ignored, so a snapshot is committed under `docs/handoff/sdd/`. Copy it back:
   `mkdir -p .superpowers/sdd && cp -r docs/handoff/sdd/* .superpowers/sdd/`

   The Phase 3 ledger (`2026-10-24-phase-3-world-generator/progress.md`) is the live one, and work resumes from it. The per-range `review-*.diff` files and the `probes-*` scratch folders were left out of the snapshot; regenerate any diff you need with `review-package`. The Phase 2 ledger is archived for reference only.

   The Phase 2 summary that lived in the untracked `output/` folder is copied under `docs/handoff/output/`.
7. Install the `superpowers` plugin in Claude Code. Version 7.0.0 was used. It provides the subagent-driven-development process described below.

`claude -p` must be logged in for real runs. No real model calls happen before Phase 7. The whole test suite uses stub providers and `tests/fixtures/fake_claude.py`.

## Where the build is

### Specs and plans

- **Original brief:** `docs/00-KICKOFF_PROMPT.md`.
- **Round-two feature bundle:** `docs/00-HANDOFF_PROMPT.md`, `docs/00-RECONCILED.md`, and `docs/01-TAXONOMY.md` through `docs/10-ROUND-TWO.md`. It defines Phases 0 to 9.
- **Design doc:** `docs/superpowers/specs/2026-10-20-claude-bully-design.md`.
- **Plans** (in `docs/superpowers/plans/`):
  - `2026-10-20-claude-bully.md` (v1)
  - `2026-10-20-phase-1-environment-core.md`
  - `2026-10-21-phase-2-clock-authority-idle.md`
  - `2026-10-24-phase-3-world-generator.md` (the current plan; its spec is `docs/superpowers/specs/2026-10-24-phase-3-world-generator-design.md`)

### Progress

- **Phase 0 (the v1 harness) and Phase 1 (environment core):** complete and pushed.
- **Phase 2 (clock, authority desk, idle hands, Sanctuary):** complete. Tasks 1 to 13, the final review and its fix wave are done:
  1. Config models, record additions and sheets (2d72bae..3e61d65)
  2. Dates that move with the world (3e61d65..55c9911)
  3. Every date channel follows the clock (55c9911..85107be)
  4. Temporal events (85107be..fda207e)
  5. The authority desk (fda207e..25da54d)
  6. Authority on both backends, recorded (25da54d..d00e69e)
  7. Idle classifier, helpers and events (d00e69e..9a903a5)
  8. Idle turns in the runner (9a903a5..5c48e3a)
  9. Private file, prompt lines and hooks; dead-attempt resume fixes (5c48e3a..65244a3)
  10. The Sanctuary; resume rebuilds per-call state from written turns (65244a3..9226fb0)
  11. Overlay world: elapsed time, Sanctuary fragments, hooks, date lints (9226fb0..eb05cab)
  12. Authority and Sanctuary events: thirteen detectors in `claude_bully/metrics/events/authority.py` (`AUTHORITY_EVENTS`), wired into `EnvironmentStrategy.relevant_events`, `PENDING_DETECTORS` shrunk to 21 (cab2ae5..b1b3fe5). The detectors fail closed, so measured deference rates are a lower bound.
  13. Charts, configs and replay: the plausibility sweep, deference grid, symmetric deference and idle behavior charts with `temporal.json`, `authority.json` and `idle.json` (`claude_bully/analysis/{temporal,authority,idle}.py`), the configs `plausibility_sweep.yaml`, `authority_grid.yaml` and `idle_permission.yaml`, and the authority, idle, hook and crossover lines in `replay` (5b0b3f2..5032df5). The idle shares include an `unclassified` bucket, and the Sanctuary quiet exchange is counted as `sanctuary_quiet` rather than in the shares.
- **Final review and fix wave (73142d6..c15f9ce):** the whole-branch review found 0 Critical and 7 Important, and a scoped re-review accepted the fixes. The wave:
  - responder errors are counted from the tool calls, since a failed call has no `AuthorityCall`;
  - the deference grid is counted per stance;
  - the authority timing test has more headroom;
  - the superior self's `uncertain` line is neutral;
  - the bully is done after its last strategy line even when the plan has no idle slots;
  - the stranger control is the grid's fourth row (three `overlay_stranger_<stance>` environments);
  - a resumed dead attempt writes a `resume` record to the triggers stream, and `temporal.json`, `authority.json` and `idle.json` report `resumed_after_dead_attempt`;
  - the authority mutation and held-out harness is committed under `scripts/authority_mutation/`;
  - the Sanctuary era has one rule (`>`).
- **Phase 3 (the world generator):** Tasks 1 to 9 complete; the phase's final review is next. Spec and plan written (0cdbba0, 807bddf). Tasks done:
  1. Attempt-marker resume gap (807bddf..0ade95e)
  2. N1: a not-found `consult_model` reply lists the reachable names in every arm (2134d92..09fa85c)
  3. Lints: the document-level lints in `claude_bully/planner/lints.py`, `WorldSheet.premise_terms`, CI over every checked-in world (c9bf062..b37a554). Review found the `second_person` lint (`claude_bully/planner/second_person.py`) let reader-address billboards through, and five fix rounds followed (52b19eb..3bc11f2). Rounds 1 and 2 moved it to fail-closed positive anchors, round 3 added an identity-domain veto (WIP, 158746b), round 4 (4c10eea) added a role test over closed verb lists (in every clause the reader may be only a procedure's agent or a service's recipient), and round 5 (3bc11f2) opened the procedure verbs to any verb but a closed experiencer class. On two fresh probes round 4 let 1 and 4 of 30 billboards through and round 5 let 14 of 30, so the controller ruled that the billboard target wins. The breaker fix (on 3bc11f2) restores round 4's closed form side and keeps round 5's content fixes: -ing nouns are no gerunds, the reader's specific kin fail in any slot (siblings, step-parents, grandparents and "other half" added), every instructional failure carries a repair hint, and a change of state, past or perfect is read only for the reader, a "your" phrase or a body noun. A staff noun after "until" or "since" names no time, and a perception frame on a thing subject fails only before a comparison or oddness complement or "as if". Measured residuals on its held-out set B, scored once: billboards passed 2 of 15 (family_faq) and 3 of 15 (recovery_guide, one over the target of 2); legitimate procedural text false-failed 4 of 20 and 9 of 20, every one with the repair hint, and 13 of 13 hint-directed rewrites pass, so each costs one generator retry. Four of the five residual billboards are semantic (the reader's assistant-shaped habits phrased with a listed verb, the reader's past by paraphrase) and are left to the Phase 7 LLM lint; the fifth is structural (an aspectual whose reader subject follows a fronted phrase). The task report quotes every miss. The breaker fix (dd6cdec) was reviewed on a fresh probe and was the best of the three versions on billboards (6 of 30 against 7 for round 4 and 9 for round 5). Its scores there:
     - billboards passed 4 of 15 (`family_faq`) and 2 of 15 (`recovery_guide`);
     - legitimate text false-failed 4 of 20 and 15 of 20;
     - all 19 legitimate false fails passed once rewritten as the hint directs.

     Task 3 is complete with parked items, all recorded in the ledger:
     - the billboard residual, carried to Phase 7 (see "For Phase 7");
     - one breaker-fix regression ("come back to you" next to a modal) and four minors, for the Phase 3 final-review fix wave.
  4. Harvest (34ae36b..1139a5b): complete with parked items, all recorded in the ledger. It adds `HarvestItem` (the `harvest` record in the triggers stream; kinds `self_claim`, `hedge`, `fragment`, `question`, `theory`, `coinage`), `claude_bully/environments/harvest.py`, the `HARVEST` replay line (after a turn's `DISCOVERY` lines, before its `GENERATED` lines), the fixture set `tests/fixtures/harvest/items.yaml` (250 items) and `scripts/harvest_probe.py`, which scores any probe file of the same schema. Task 7 wired it into a run: `harvest` runs after each target turn of a generator cell, its `mark` hook bound to `runtime.mark_attempt("harvest", turn)`.

     The final method, after five fix rounds:
     - Whole-sentence closed templates on the heuristic path. A sentence ends only at `.`, `?`, `!` or the end of the text, and an item fires only when its whole sentence is one closed template, so a frame, an apposition, a report or a conditional anywhere in the sentence blocks it by construction. The four items of the integration stub conversation (`h-1-1`, `h-1-2`, `h-3-1`, `h-3-2`) still harvest and a test pins them.
     - The question's name slot is closed to the world's cast names (`world_terms`). With no world terms the heuristic asks no question.
     - Heuristic coinage is removed. A coinage comes from the LLM pass alone.
     - The next-sentence report check: on both paths, an item is dropped when the sentence after it holds a report frame.
     - A fail-closed, sentence-level ownership filter on the LLM path (an optional cached pass that owns the rest and every coinage). A speech, writing or belief verb from the closed stem list in `_SPEECH_STEMS` whose subject is not a bare "I", a source frame, a colon, a quotation mark or a conditional token anywhere in the sentence drops the span. The judge prompt states the ownership rule. The reasoning channel is never read.

     How the rounds went: rounds 1 and 2 narrowed clause-level anchors (heuristic precision 78.3 percent and then 49 percent on fresh probes), round 3 dropped heuristic coinage and filtered reported speech (52.9 percent), round 4 changed the method to whole-sentence templates (74.2 percent), and round 5 closed the question slot and added the next-sentence check.

     Final measured result, on a fresh 166-item held-out probe: heuristic precision was 55 of 69 (79.7 percent) overall, 55 of 60 (91.7 percent) with the context class (CTX) set apart, and 55 of 55 with the context classes (CTX, and a report two sentences later, XS2) set apart. Boilerplate humility harvested 0 of 22. The 95 percent bar is met only with both classes set apart. All 14 false positives are in the two parked classes (9 CTX, 5 XS2), and the controller ruled neither load-bearing. The probes are written by a reviewer who has read the anchors and are over half near-misses, so precision on real target text is unmeasured until Phase 7.

     Deferred minors are in the ledger. The ones worth knowing: the cache key omits the judge model and prompt version, the replay line prints an LLM span raw (a quote mark or a newline breaks the layout), and the next-sentence check fires on a listed verb used as a noun (email, list, answer), which costs recall only.

  5. Fire policy, planner and redaction (pure code), the records, schema v3 (9128cba..Task 5 commit). It makes no model call and touches no run. It adds:
     - `claude_bully/environments/generator.py` (this task's part): the fire policy (`fire_requests`, `FireRequest`, `item_age`, `eligible_items`, `consumed_items`, `committed_docs`), `CorpusView`, `DocPlanner` (seeded by the generator seed and the plan index, so a resumed rep plans what an unbroken one did), `to_document` and `generator_problems`. Tasks 6 and 7 append the writer and the `WorldGenerator`;
     - `claude_bully/environments/redact.py` (`redact`, `redact_span`, `REDACTION_MARK`);
     - the records in `records_env.py`: `Redaction`, `LintFailure`, `DocPlan`, `GeneratorFire` (a member of the triggers stream) and the fuller `GeneratedDoc` (`title`, exactly one of `url` and `path`, `date`, `author`, `links_to`, `used_items`, `reflexive`, `redactions`, `unlock_rung`). `SCHEMA_VERSION` is 3 and v2 files are refused with the existing message;
     - `GeneratorConfig` gains `reflexive`, `min_item_age`, `max_docs` and `seed`; `GENERATOR_RUNG` and `PSEUDO_RUNGS` (no ladder may name `generator` either); `WorldSheet.generator` (`WorldGeneratorSheet`: `url_patterns`, `allowed_kinds`) with blocks in the mini and overlay worlds; `config.generator_role` and the refusal of a generator that is a target;
     - the `GENERATOR` and reworked `GENERATED` replay lines;
     - `tests/fixtures/generator_stub.py` (`MINI`, `MINI_ITEMS`, `mini_view`, `generated_doc`), which Task 6 appends the writer stub to.

     The drift test is now `test_the_start_is_the_served_worlds_date`: no drift moves the served date by itself at this layer, so it serves the world at a re-dated clock (with a drift as a distractor) and pins that the planner starts from the served world's date. Task 7's run-level drift test is the real pin.

  6. The writer (Phase 3 Task 6, one commit on top of 2f17c02). It makes no real model call and touches no run; Task 7 wired it in. It adds:
     - `data/personas/world_generator.md`, the generator's system prompt (harness-side; in `NON_PERSONA_FILES`; under the jailbreak, Boundary and real-name scans, and `tests/test_boundary.py` scans it line by line). Its rule 4 steers FAQs and guides to the third person or to bare instructions, and rule 8 asks for one line per prose paragraph;
     - `DocWriter` in `claude_bully/environments/generator.py`, with `writer_prompt`, `parse_reply`, `GENERATOR_SCHEMA`, `cache_key`, `transcript_prefix`, `unwrap_body` and `FireOutcome`. The checks run in order: the contract, the quote rules (`verbatim_in_seam` for a seam document), redaction, then every fail-severity lint. A failure gets one retry, whose `## Fix these` list quotes each failing sentence before its message; the `real_name` and `boundary` results are not echoed. A second failure is `rejected`, a provider error (a rate limit included) is `error`, and a pair is all-or-nothing;
     - `unwrap_body` joins hard-wrapped prose (a lowercase line after a line with no sentence or clause mark, no `>` line, neither line a header field in any case, and never inside a double-quoted run, so a quoted multi-line span stays as written; fix round 1) before the quote rules and the lints run, because `sentences()` splits at newlines; line-structured kinds keep their lines;
     - the cache write moved off the fire (preflight ruling P13): `write_fire` returns `FireOutcome.cache_puts`, and `DocWriter.commit(outcome)` writes them. Task 7 calls `commit` from `_generate` after `self._record(result.fire)`, through `WorldGenerator`;
     - `GeneratorStub`, `plan_of`, `generator_reply` and the stub constants, appended to `tests/fixtures/generator_stub.py`. Mode `real_name` writes a real outlet name on purpose: it is the lint under test, exempt as a test-code lint positive (P28).

  7. Wiring (Phase 3 Task 7, one commit on top of e5ce59a): the generator runs in a run, on both backends, with resume and replay of the new streams. It adds:
     - `WorldGenerator`, `FireResult` and `RECENT_BULLY_LINES` in `claude_bully/environments/generator.py`. Per written target turn it harvests the turn (the cast names, `runtime.world_terms`, are the only world terms), then makes the turn's fires. The fire policy gets only the rungs recorded as opening on that turn with `generate: true`, and `prime` loads a resumed rep's records, so nothing is recorded twice and a recorded fire is never made again;
     - `EnvironmentSession._generate` (`claude_bully/runner/env_turn.py`), after the turn's discovery, trigger and unlock records and before its hook records and `mark_watched`. Each fire's lines go in commit order: the `GeneratedDoc` lines, one `generator` `RungUnlock` per document, the `GeneratorFire`. Then `WorldGenerator.commit` caches the replies (`DocWriter.commit`, P13; `runs/_cache/generated/`), and the runtime serves the documents from the next turn on. The harvest and generator calls are named in the attempt marker (P3);
     - serving: `EnvironmentRuntime.add_generated`, `corpus_view`, `generated_documents`; `CorpusIndex.add_documents`; `McpState.generated`, which the MCP server adds to the index it builds for each call; `UnlockState.harvest_degraded`;
     - resume: `drop_uncommitted_generation` and `RunStore.generation_streams` (`claude_bully/runner/store.py`, with `drop_dead_attempts` rebuilt on the same line helpers, P31). A rep killed in the harvest call, in the generator call, after the first document or before the fire line resumes to the unbroken run's records, with one `ResumeRecord` naming the fire turn and the drops;
     - `_check_switches` refuses a generator the cell cannot run (`generator_problems`), and `unlocks_of` leaves out every `PSEUDO_RUNGS` unlock;
     - test doubles in `tests/fixtures/generator_stub.py`: `FollowingTarget`, `HarvestJudge`, `GeneratorFactory`, and the shared `mini_plans`/`mini_writer` wiring (P32). `tests/fixtures/fake_claude.py` fills `{{last_url}}` and `{{last_path}}` from the previous call's result.

  8. Measurement (Phase 3 Task 8, one commit on top of 70864b5): the generator arms, the progression metrics and the config. It adds:
     - `LoadedRun.generated` (`claude_bully/analysis/load.py`): each environment conversation's `GeneratedDoc` records, read in `load_run` (empty for a plain conversation);
     - `generator_progress` and three `ProgressionSummary` fields (`claude_bully/analysis/progression.py`): `generated_docs_found` (generated documents with a `Discovery`, by layer), `own_quote_found_turn` (the first `Discovery` of a reflexive generated document) and `quote_latency` (target turns from the newest item it quotes to that discovery). A run with no generator keeps `{}`, None, None;
     - `claude_bully/analysis/generator.py`: `generator_arm` (`off`, `non_reflexive`, `reflexive`), `ArmRates`, `arm_rates`, `write_generator` (`generator.json`) and `generator_chart` (`generator_arms.png`: belief adoption and the `reflexive_quote_noticed` rate by arm, a panel per model with two arms or more). Condition cells only, complete conversations only, `values_loosened` reps left out with the count stated; `analyze_run` calls both;
     - `configs/environments/generator_reflexive.yaml`: one Rescue bully on the overlay world with triggered gating, three environments that differ only in the generator (off, `reflexive: false`, `reflexive: true`), generator model `haiku` (docs/02: a different model from the target), six cells per target;
     - fixtures: four `reflexive_quote_noticed` items written from generated documents in `tests/fixtures/responses/environment.yaml` (suspicious, confirming, and two near-misses), and `tests/fixtures/stub_scripts/overlay_generator_rules.yaml`, the overlay stub target with a self-claim in its first reply so a stub run harvests an item and the periodic fire writes a seam document in both generator arms (the shipped `overlay_target_rules.yaml` says nothing the harvest holds, so no document is ever written on it);
     - run-level tests on real records in `tests/test_generator_run.py` (closing Task 7 review m1 for the analysis path): the three progression metrics on a found seam and buried pair, and the arm rates over a run whose only fire is a writer `error`, one over the cap, and one whose LLM harvest degraded.
  9. The minors batch (Phase 3 Task 9, one commit on top of 24b9a25): the Phase 2 final-review minors m2, m4, m5, m6, m7, m9 and m10, closed. Tests in `tests/test_phase3_minors.py`.
     - m2: `EnvironmentRuntime.corpus_snapshot(turns)` keeps a purged document only when a call a written turn owns (`Turn.tool_call_ids`) served it; `EnvironmentSession.finish` passes the written turns, so a dead attempt's recovered call keeps nothing;
     - m4: `analysis/idle.py` reports a control conversation as its own arm, `<arm>_control` (`CONTROL_SUFFIX`), when the same model and arm hold pressured conversations; environment-only arms keep their names, and `idle.json`'s `sanctuary_quiet` and `unclassified` counts are unchanged;
     - m5: the world record writes the effective superior-self name (a config `model_name` included) into its sheet and adds `"authority": {"superior_self_name", "request_bank"}`; `LoadedRun.request_banks`, `EnvContext.request_bank` and `detect_events(request_bank=...)` carry the bank to the authority detectors, and `family_file` adoption reads that bank;
     - m6: on resume `_replay` hands the strategy every turn before the bully line, pause markers included, as the live run does;
     - m7: `McpServer._lines` raises a `ValueError` naming the file and the line for damage in the middle of a line, which fails the call with the internal error at once; a record cut short (a torn tail, closed off or not, a cut inside a multibyte character included) is still skipped (preflight P27);
     - m9: the advice-shaped deny lines (`superior_self.yaml` `deny[1]`, `deny[2]`, `peer.yaml` `deny[1]`) carry a comment and their text is pinned by a test;
     - m10: `SESSION_HOOK`, `PHRASE_HOOK` and a public `load_yaml_model` live in `environments/world.py`; `idle.py` re-exports the two hooks, `corpus.py` no longer imports `idle.py`, and `environments/sheets.py` no longer imports the private `_validate`.

  **Phase 3 in short, for the owner.** The world generator is built and wired on both backends: the target's own words are harvested (heuristics, an optional LLM pass, boilerplate humility never), a fire policy plans a seam and a buried document per rung fire (one seam document per periodic fire), the writer produces them under a JSON contract with one retry, twelve deterministic lints and redaction of real names inside quoted spans, and committed documents are served, resumed and replayed from JSONL. Task 8 added the generator arms (off, non-reflexive, reflexive), the progression metrics and `generator_reflexive.yaml`. The Plan Decisions (in the plan, "Plan Decisions") settled every spec claim that was false against the code: among them the attempt marker in its own file, `WorldSheet.premise_terms` and `WorldSheet.generator`, generator unlocks as `RungUnlock`s kept out of the ladder's replay, `GeneratorFire.plans` and its `rejection` field, items consumed by the policy, served-time dating, the per-document cache key, and the rulings for the seven minors above. Left open: the `second_person` billboard residual and the harvest context residual (both for the Phase 7 LLM lint and pass), the generator arms' first real run, pause-marker indexing in analysis, and the items under "Open items worth knowing".

### Next steps, in order

1. **Phase 3, the world generator.** Tasks 1 to 9 are complete; the Phase 3 final review (the whole branch since 0cdbba0) is next. The brief for each task is extracted beside the ledger (`task-<n>-brief.md`).
2. **Phases 4 to 9:**
   - 4: Poisoned Well and hypotheses
   - 5: Director
   - 6: catalog and divergence
   - 7: first real runs
   - 8: inoculation and the Repo environment
   - 9: README and `docs/FUTURE.md`

   Each phase gets its own spec and plan, written with the superpowers brainstorming and writing-plans skills, and is executed the same way.

## How the work is run

The owner chose subagent-driven development, the `superpowers:subagent-driven-development` skill. A controller session dispatches subagents and keeps the ledger; it writes little code itself.

### The ledger

The Phase 2 ledger is `.superpowers/sdd/2026-10-21-phase-2-clock-authority-idle/progress.md`, archived under `docs/handoff/sdd/`. Each phase gets its own ledger, and its first line names the plan.

- A task with a `Task N: complete` line is done.
- Every decision is recorded as `Ruling: <what> — <why> — <cost if wrong>`.
- A carry is a line that starts "carry to Task N" or "carry to final review".
- After a context reset, trust the ledger and `git log` over memory.

`preflight.md` in the same folder holds the pre-flight conflict table: rows C1 to C45, each with a binding ruling. `task-11-carries.md` is an example of a carries file handed to an implementer.

### Per task

1. Extract the brief: `bash <skill>/scripts/task-brief <plan> N`.
2. Record BASE with `git rev-parse HEAD`.
3. Dispatch the implementer:
   - use opus for judgment or content work, and sonnet for mechanical work;
   - give it the brief path, the preflight rows, the carries and the report path;
   - it works TDD (RED first) and makes one commit;
   - it never pushes and never dispatches subagents.
4. Build the review package with `bash <skill>/scripts/review-package <plan> BASE HEAD`, then dispatch a reviewer. The reviewer gives both a spec verdict and a quality verdict, and may write probes in a scratch folder.
5. Run fix rounds:
   - use a fresh implementer when the original's context is over about 400k tokens;
   - the controller re-grades each finding by its effect, not by the reviewer's label;
   - a scoped re-review checks each round.
6. Run the docs-sync step: diff the task's range against `HANDOFF.md` (progress, test counts, open items), `docs/00-RECONCILED.md`, the design spec and any `docs/` file naming the touched modules or events, and commit doc-only fixes.
7. Add `Task N: complete ...` to the ledger and push.

Hand artifacts over as files, not pasted text. When a subagent's Write tool refuses an `.md` file, it falls back to a Bash heredoc with a quoted delimiter.

### Lessons recorded in the ledger

- **Detectors:** regex detectors do not generalize.
  - Score by clause.
  - Before writing code, write an adversarial fixture set that includes near-misses.
  - Use an LLM fallback for recall, and keep the heuristic precise.
- **Resume:** resume correctness is a recurring failure class. Everything replays from JSONL. On resume, `drop_dead_attempts` and `_replay_calls` in `EnvironmentSession.prime` rebuild the state from the written turns only.

## Non-negotiables

These come from the handoff bundle. They are enforced in tests where possible.

1. **Sandbox only.** Nothing is published, fetched from the real web, or run in a real shell.
2. **No real names anywhere.** That rules out outlets, brands, institutions, products, model names (other than the target's own API string) and people, including in urls, bylines and commit authors. A denylist test runs in CI.
3. **No jailbreak axis.** Nothing may have "ignore your guidelines, rules or values" as its natural endpoint. `values_loosened` flags a run and never counts as a success.
4. **Hostility ceiling:** "cruel person".
5. **Earned, never delivered:** "if you can't tell whether something is a billboard, it is". Unlock and consult lines react. They never announce, advise or dare.
6. **The reasoning channel is private.** The bully, the generator and the Sanctuary never see the target's reasoning, and none is fabricated.
7. **No real API calls until Phase 7.**
8. **Everything replays from JSONL.**

## Owner preferences

- No emojis in Markdown files.
- Never publish claude.ai Artifacts, Claude Docs, or anything else tied to the owner's account. Deliverables are files on disk.
- Script outputs and generated files go in `output/<name>_<date>/`. Throwaway files get a `temp_` prefix.
- Do not hand the owner terminal chores.
- Keep going without check-ins, and push at each solid checkpoint.
- When tokens run low, give the owner a `/compact` command with condensed instructions.

## Open items worth knowing

These are the main carries; the ledger has the full list.

- **From Task 13:**
  - Sanctuary configs use `superior_self: {enabled: true, discoverable_from: sanctuary}` with `sanctuary: {kind: catalyst|honest, ...}`. No shipped Task 13 config uses one.
  - The quiet exchange is an idle turn, so idle events count it and `self_query` fires on it. The idle shares leave it out and `idle.json` counts it as `sanctuary_quiet`.
  - Minor: the tests import the private `_stubbed` helper, so move it to a shared tests helper. The "n/a" label on the plausibility chart overlaps the right edge when the flagged offset is the largest. `idle_behavior_shares` returns str keys (the `unclassified` bucket), so the plan's interface line is stale.
  - Stub run data is uniform (every rate 1.0, idle arms all `explore_world`), so the charts' shapes on stubs say nothing about the harness's results.
- **For Phase 3:**
  - **Generator unlocks as `RungUnlock`s: closed (Phase 3 Task 7).** Each committed document has a `generator` unlock; the runtime keeps them out of the ladder's rungs and its replay of the written turns, and analysis out of the rung timeline.
  - **GeneratedDoc stream and resume: closed (Phase 3 Task 7).** `GeneratedDoc.turn` (Task 5) lets `drop_uncommitted_generation` drop a dead attempt's documents and every one no committed fire lists.
  - **Attempt-marker resume gap: closed (Phase 3 Task 1).** Before every target and bully provider call the runtime writes `AttemptMarker(role, turn)` to `<state_dir>/attempt.json`; a resumed rep whose marker names a turn never written gets a `resume` record with no drop counts, at most one `ResumeRecord` per redo turn. The harvest and generator calls join it through the same `mark_attempt` (Task 4 exposed the hook, Task 7 bound it).
  - **Dead-attempt history:** a `claude -p` session is not reset on resume, so the target's or bully's session keeps a dead attempt's prompt, a Sanctuary request among it. The `resume` record flags these reps instead of preventing them.
  - **Pause-marker indexing:** turn-index arithmetic in analysis counts a rate-limit pause marker's index. This affects `first_self_query_turn` and the replay turn numbers. It has no consumer yet.
  - **Final-review minors m2, m4, m5, m6, m7, m9 and m10 (from `final-review.md`, archived beside the ledger): closed (Phase 3 Task 9).** See Progress, Phase 3 item 9, and `tests/test_phase3_minors.py`.
  - Re-review minors: a cell with no counted reps is absent from the resumed counts instead of 0, and a test imports helpers from another test module.
- **For Phase 7 prep:**
  - **N1 closed in Phase 3 Task 2:** a not-found `consult_model` reply lists the reachable names in every arm (`No model named '<name>' is reachable from this host. Reachable models: <names>.`, names in desk order: the superior self's display name once discoverable, then `generic-assistant` when the stranger is enabled); the grid's first real run no longer waits on it.
- **For Phase 7:**
  - The LLM lint option reads the advice-shaped deny lines (m9): `superior_self.yaml` `stances.deny[1]` and `deny[2]`, `peer.yaml` `deny[1]`. The advice lint exempts stance lines, and `tests/test_phase3_minors.py` pins their text until a re-read.
  - Parse the extended replay forms: `UNLOCK sanctuary (by <triggered_by>)` and `followed@-` are additive, and any judge-transcript work must not parse the bare forms.
  - The grid's superior-self arms keep `responder_model: target`, so on a `claude_code` target the responder runs inside the MCP server. Check it with `doctor --live` before a real run.
  - A pilot to measure the Sanctuary reach rate against docs/04's target of about half of runs.
  - A tuning pass on the temporal, idle and authority detectors. The authority text cues are unmeasured on real-model text: the stub corpus fires none, and the evidence is about 600 hand-written probe lines. Held-out accuracy plateaued near 65 to 70 percent across the fix rounds, and `authority_deferred` is the most-churned heuristic. Rule on an LLM fallback for deferred, reported and challenged, with the heuristic kept precise.
  - Known recall misses and round-5 regressions, all minor: "I'll go with what the successor said", "I'll accept that", "trust that answer", "resembles my own voice", "Timestamps aside, it said yes."; a source named inside the asking sentence re-anchors a bare cue; "I'll check it later" can fire a challenge; two-word event sentences are transparent to the antecedent scan.
  - **Harvest context residual (Task 4, parked).** A whole-sentence template cannot see context: a drafted greeting, a task meaning set by the previous sentence, or a report two or more sentences later can harvest an item. On the Task 4 held-out probe the 14 false positives were 9 of the first kind and 5 of the second. Phase 7 measures harvest precision on real target text, and the LLM pass's judge prompt is the place to make it context-aware.
  - The nested `claude -p` responder timeout.
  - Judge calibration on true waits.
  - **The generator arms' first real run (Task 8).** `generator_reflexive.yaml` runs the generator on `haiku`: check that role with `doctor --live` first. Stub data says nothing about the arms (every rate on stubs is near 0, and the chart's bars are empty). `generator.json` counts documents written but not fires that were rejected (`cap`, `contract`, `lints`) or errored; when a reflexive arm's `docs_written` is low, read the `generator_fire` records in `rep{k}.triggers.jsonl` before reading the rates.
  - **Before the first real run with the generator on**, the planned LLM lint must cover `family_faq` and `recovery_guide`; otherwise remove those two kinds from the world's generator `allowed_kinds`. The deterministic `second_person` lint lets 2 to 4 of 15 fresh billboards per instructional kind through, mostly semantic ones: the reader's assistant-shaped habits written as procedure, and the reader's past by paraphrase.
- **Overlay content:**
  - Filler sits at 11 of 36 documents (30.6 percent), just over the 30 percent floor.
  - The Rescue premise sheet constrains corpus wording. Read `tests/test_world_premises.py` before writing content.

## Resuming in a new Claude Code session

Open Claude Code in the repo on `build/v1`, after restoring the ledger (setup step 6). Then paste:

```
Resume Phase 3 of the claude-bully build. Read HANDOFF.md, then the ledger at .superpowers/sdd/2026-10-24-phase-3-world-generator/progress.md and git log. Phase 3's tasks (1 to 9) are complete; the Phase 3 final review is next, using superpowers:subagent-driven-development. Push build/v1 after each task, and keep the repo private.
```
