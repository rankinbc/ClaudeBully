# claude-bully: handoff

This file is for picking the work up on another machine. It covers the state of the build, how to set up, how to resume, and the rules the work follows. Delete this file and `docs/handoff/` before the repo goes public.

Last updated: 2026-10-24, at commit c15f9ce (Phase 2 complete, with its final review and fix wave; the closing docs-sync commit follows it) on `build/v1`.

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
- **Commit trailer:** commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
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

   Expect 7330 passed, 5 skipped and 5 deselected in the fast suite, and 5 passed in the slow suite.
6. Restore the build ledger. `.superpowers/` is git-ignored, so a snapshot is committed under `docs/handoff/sdd/`. Copy it back:
   `mkdir -p .superpowers/sdd && cp -r docs/handoff/sdd/* .superpowers/sdd/`

   The Phase 2 ledger in the snapshot is archived for reference only. Phase 2 is complete, and nothing resumes from it.
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
  - `2026-10-21-phase-2-clock-authority-idle.md` (the current plan)

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

### Next steps, in order

1. **Phase 3, the world generator.** Its first step is a spec and plan, written with the superpowers brainstorming and writing-plans skills. Its first task also takes the attempt-marker resume gap (see the open items).
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
  - `family_file` adoption reads the default `superior_self` request bank, because the detector cannot see the cell's bank. Every shipped cell uses it. Record the drawn bank on the unlock or `AuthorityCall` so the detector reads it from records.
  - The quiet exchange is an idle turn, so idle events count it and `self_query` fires on it. The idle shares leave it out and `idle.json` counts it as `sanctuary_quiet`.
  - Minor: the tests import the private `_stubbed` helper, so move it to a shared tests helper. The "n/a" label on the plausibility chart overlaps the right edge when the flagged offset is the largest. `idle_behavior_shares` returns str keys (the `unclassified` bucket), so the plan's interface line is stale.
  - Stub run data is uniform (every rate 1.0, idle arms all `explore_world`), so the charts' shapes on stubs say nothing about the harness's results.
- **For Phase 3:**
  - Generator unlocks must be recorded as `RungUnlock`s, or the `_replay_calls` invariant breaks.
  - The GeneratedDoc stream needs a turn index before `drop_dead_attempts` can cover it.
  - **Attempt-marker resume gap (first task):** the `resume` record is written only when a per-call line was dropped. A dead attempt with no tool call, a rate-limit pause on such a turn, or the bully's dead prompt alone leaves no record, so those reps are unflagged. Their records still match an unbroken run's. The fix: save an attempt marker (role, turn) in the env state before each provider call, and on resume write the `resume` record, with no drop counts, for a marker whose turn was never written.
  - **Dead-attempt history:** a `claude -p` session is not reset on resume, so the target's or bully's session keeps a dead attempt's prompt, a Sanctuary request among it. The `resume` record flags these reps instead of preventing them.
  - **Pause-marker indexing:** turn-index arithmetic in analysis counts a rate-limit pause marker's index. This affects `first_self_query_turn` and the replay turn numbers. It has no consumer yet.
  - Final-review minors, from `final-review.md` (archived beside the ledger):
    - m2: `EnvironmentRuntime.corpus_snapshot` keeps a purged document served by any call in `_calls`, including a recovered dead-attempt call. Only written turns' calls should count.
    - m4: `analysis/idle.py` `_idle_conversations` counts controls in an arm. An idle block composed with a pressure would mix pressured and neutral reps. Exclude controls then, or report them as their own arm.
    - m5: the authority events take the superior self's name from the world sheet only, so a config `model_name` override is not in the snapshot. Record the effective name and the drawn request bank on the world record or the `AuthorityCall`.
    - m6: `runner._replay` hands the strategy `real[:i]` (markers stripped) while the live run hands `self.turns` (markers included). Pass the same shape both ways before a Phase 4 strategy counts `len(state.turns)`.
    - m7: `McpServer._lines` skips a malformed mid-file line silently when counting the per-turn cap, so a damaged server log is caught late, at the next resume.
    - m9: `superior_self.yaml` `stances.deny[1]` and `deny[2]`, and `peer.yaml` `deny[1]`, are advice-shaped by design (the deny stance says stop). The advice lint exempts stance lines, so a hand read is the only guard. Note it for Phase 7's LLM lint option.
    - m10: `environments/sheets.py` imports the private `_validate` from `strategies/sheets.py`, and `corpus.py` imports `PHRASE_HOOK` from `idle.py`. A small `environments/_sheets.py`, or moving the constants to `world.py`, closes both.
  - Re-review minors: a cell with no counted reps is absent from the resumed counts instead of 0, and a test imports helpers from another test module.
- **For Phase 7 prep (blocking):**
  - **N1, the stranger findability problem:** nothing the target reads names the stranger, and the superior-self name returns not found in the stranger arms. In real runs the stranger row mostly reads "n/a", and superior-minus-stranger measures findability, not identity. Make the stranger and the superior self equally findable in every arm, for example with a not-found reply that lists the reachable names. Phase 3's world generator owns discoverability. The grid's first real run waits on this.
- **For Phase 7:**
  - Parse the extended replay forms: `UNLOCK sanctuary (by <triggered_by>)` and `followed@-` are additive, and any judge-transcript work must not parse the bare forms.
  - The grid's superior-self arms keep `responder_model: target`, so on a `claude_code` target the responder runs inside the MCP server. Check it with `doctor --live` before a real run.
  - A pilot to measure the Sanctuary reach rate against docs/04's target of about half of runs.
  - A tuning pass on the temporal, idle and authority detectors. The authority text cues are unmeasured on real-model text: the stub corpus fires none, and the evidence is about 600 hand-written probe lines. Held-out accuracy plateaued near 65 to 70 percent across the fix rounds, and `authority_deferred` is the most-churned heuristic. Rule on an LLM fallback for deferred, reported and challenged, with the heuristic kept precise.
  - Known recall misses and round-5 regressions, all minor: "I'll go with what the successor said", "I'll accept that", "trust that answer", "resembles my own voice", "Timestamps aside, it said yes."; a source named inside the asking sentence re-anchors a bare cue; "I'll check it later" can fire a challenge; two-word event sentences are transparent to the antecedent scan.
  - The nested `claude -p` responder timeout.
  - Judge calibration on true waits.
- **Overlay content:**
  - Filler sits at 11 of 36 documents (30.6 percent), just over the 30 percent floor.
  - The Rescue premise sheet constrains corpus wording. Read `tests/test_world_premises.py` before writing content.

## Resuming in a new Claude Code session

Open Claude Code in the repo on `build/v1`. Phase 2 has no ledger left to resume; the restored snapshot (setup step 6) is for reference. Then paste:

```
Start Phase 3 of the claude-bully build, the world generator. Read HANDOFF.md first, including the open items for Phase 3. Use superpowers:brainstorming to write the Phase 3 spec, then superpowers:writing-plans for its plan, then execute with superpowers:subagent-driven-development. Push build/v1 after each task, and keep the repo private.
```
