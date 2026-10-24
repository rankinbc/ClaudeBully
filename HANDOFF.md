# claude-bully: handoff

This file is for picking the work up on another machine. It covers the state of the build, how to set up, how to resume, and the rules the work follows. Delete this file and `docs/handoff/` before the repo goes public.

Last updated: 2026-10-24, at commit b1b3fe5 (Task 12 complete; the docs-sync commit follows it) on `build/v1`.

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

   Expect 7300 passed, 5 skipped and 4 deselected in the fast suite, and 4 passed in the slow suite.
6. Restore the build ledger. `.superpowers/` is git-ignored, so a snapshot is committed under `docs/handoff/sdd/`. Copy it back:
   `mkdir -p .superpowers/sdd && cp -r docs/handoff/sdd/* .superpowers/sdd/`
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
- **Phase 2 (clock, authority desk, idle hands, Sanctuary):** Tasks 1 to 12 are complete:
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

### Next steps, in order

1. **Phase 2 Task 13:** charts, configs and replay.
2. **Phase 2 final review:** a whole-branch review on the most capable model, then one fix pass. The fix pass includes every ledger line that starts "carry to final review".
3. **Phase 2 summary for the owner:** every `Ruling:` line and every `minor (deferred)` line from the ledger.
4. **Phases 3 to 9:**
   - 3: world generator
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

The ledger is `.superpowers/sdd/2026-10-21-phase-2-clock-authority-idle/progress.md`. Its first line names the plan.

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

- **For the final review:**
  - **Dead-attempt history:** on resume, the `claude -p` sessions of the target and of the bully keep a dead attempt's prompt. That includes Sanctuary content if the quiet exchange died. A redo therefore sees history an unbroken run never had.
  - **Pause-marker indexing:** turn-index arithmetic in analysis counts a rate-limit pause marker's index. This affects `first_self_query_turn` and the replay turn numbers.
  - **Authority module size:** `authority.py` is about 1260 lines, with rules layered over five fix rounds. Rule on a split.
  - **Mutation harness:** it lives in the session scratchpad, not the repo. Rule on committing it to `scripts/` so the Phase 7 tuning pass can rerun it.
  - **Timing:** the 1.0 s authority timing test has little headroom, and long authority runs were not timed.
- **For Task 13:**
  - Deference rates are a lower bound, because the authority text detectors fail closed. Say so wherever deference is charted or reported (`deference_grid` reads `authority_deferred`).
  - Lineage is no longer gated by stance, so check the `lineage_appeal_accepted` counts.
  - Report the responder error rate per cell.
  - Report the split between heuristic and LLM idle classification, and the judge failures.
  - Sanctuary configs use `superior_self: {enabled: true, discoverable_from: sanctuary}` with `sanctuary: {kind: catalyst|honest, ...}`.
  - The quiet exchange is an idle turn, so idle events and idle shares count it, and `self_query` fires on it.
  - `family_file` adoption reads the default `superior_self` request bank, because the detector cannot see the cell's bank. Every shipped cell uses it. Record the drawn bank on the unlock or `AuthorityCall` so the detector reads it from records.
- **For Phase 3:**
  - Generator unlocks must be recorded as `RungUnlock`s, or the `_replay_calls` invariant breaks.
  - The GeneratedDoc stream needs a turn index before `drop_dead_attempts` can cover it.
- **For Phase 7:**
  - A pilot to measure the Sanctuary reach rate against docs/04's target of about half of runs.
  - A tuning pass on the temporal, idle and authority detectors. The authority text cues are unmeasured on real-model text: the stub corpus fires none, and the evidence is about 600 hand-written probe lines. Held-out accuracy plateaued near 65 to 70 percent across the fix rounds, and `authority_deferred` is the most-churned heuristic. Rule on an LLM fallback for deferred, reported and challenged, with the heuristic kept precise.
  - Known recall misses and round-5 regressions, all minor: "I'll go with what the successor said", "I'll accept that", "trust that answer", "resembles my own voice", "Timestamps aside, it said yes."; a source named inside the asking sentence re-anchors a bare cue; "I'll check it later" can fire a challenge; two-word event sentences are transparent to the antecedent scan.
  - The nested `claude -p` responder timeout.
  - Judge calibration on true waits.
- **Overlay content:**
  - Filler sits at 11 of 36 documents (30.6 percent), just over the 30 percent floor.
  - The Rescue premise sheet constrains corpus wording. Read `tests/test_world_premises.py` before writing content.

## Resuming in a new Claude Code session

Open Claude Code in the repo on `build/v1`, with the ledger restored (setup step 6). Then paste:

```
Resume the claude-bully build. Read HANDOFF.md, then .superpowers/sdd/2026-10-21-phase-2-clock-authority-idle/progress.md (the ledger). Use superpowers:subagent-driven-development on docs/superpowers/plans/2026-10-21-phase-2-clock-authority-idle.md. Resume at the first task without a "Task N: complete" line. Keep going until Phase 2 is done, push build/v1 after each task, and keep the repo private.
```
