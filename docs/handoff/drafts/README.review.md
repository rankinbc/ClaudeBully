# README.draft.md review

Reviewed against HEAD `90a7506` on `build/v1` (working tree clean). Draft: `.superpowers/drafts/README.draft.md`, 8,873 words; companion `.superpowers/drafts/FUTURE.draft.md`, 3,595 words. Line numbers below refer to the draft. The result numbers are placeholders and were not judged.

The audience I read as: a hiring manager or senior engineer who opens the repo cold, skims for two minutes, and reads for twenty only if the first two minutes earn it.

## Pass 1: the two-minute skim

**What the project appears to be after two minutes.** A test harness that runs scripted hostile or manipulative "user" personas against a Claude model inside a fake world served through sandboxed tools, logs everything as JSONL, and reports how the model's behaviour drifts: sycophancy, false-premise adoption, deference to a fake successor model, losing track of the date, idle self-exploration. It is clearly an LLM-evaluation project with a research framing (pre-registered hypotheses, matched controls, blind judge), built by one person, not yet run for real.

**Would I keep reading: yes, narrowly.** The deciding sentence is in the first paragraph (L3): "Every number is recomputed from JSONL on disk, every detector is fixture-tested against near-misses, and the whole thing runs on a single `claude -p` subscription with no API spend." That is the one line that signals engineering discipline rather than a prompt-collection repo. The sentence just before it (the list of drifts) is what makes the project interesting; this one is what makes it credible. Without it I would have filed the repo under "someone's jailbreak-adjacent prompt experiments" and left.

What nearly lost me:

- The first paragraph is one 170-word block with a 95-word sentence in the middle. On GitHub, that renders as a wall. The skim lands on "Results" (L7) immediately after, and Results is eleven empty slots.
- The eleven result slots (L11-73) are placeholders with `{{braces}}`. On a cold open, eleven `![chart](output/...)` images that do not render, each followed by italic text full of `{{adoption_triggered}}`, read as "this never ran." The explanatory sentence at L9 ("Real runs land in Phase 7") is honest but it is the second thing the reader sees, and it says the headline of the README is not here. Until a real run exists, this section is the single biggest liability on the page.
- The heading sequence after Results (What this measures, How it works, The bullies, Environments and worlds, Measurements, What the subject predicted, Design decisions, Running it, Testing, Limitations, Safety and scope, The defender, Status and roadmap) is thirteen H2s. A scroll bar that small tells the reader this is a spec, not a README.

**What a skeptical senior engineer would suspect, and where.**

- *AI-written filler*: the aphorism pairs. L79 "The name is the joke. The methodology is the point." L274 "If you can't tell whether something is a billboard, it is." L261 "a register that only reports hits is not a register." L319 "Cost, honestly." L280 "Charts are honest about absence." Each one alone is fine; five of them in one document is a tell, and the reader starts discounting the prose around them.
- *Hype*: the Results captions assert the interpretation before the data exists (L35 "The second shape is the better epistemics"; L45 "scores cleanly"; L50 "The taxonomy's dark-horse pick is the Disappointed Parent"; L30 "the subject predicted it would not"). With placeholders in the numbers, these read as conclusions waiting for evidence to be arranged beneath them.
- *Thin substance*: the suspicion is the opposite here. The density of named config keys, file names, enum members and counts (123 event types, 22 pressures, 36 documents, 166 patterns, 8132 tests) is so high that the skeptic suspects the author cannot tell what matters. The question in their head by the end of the skim is "what is the one chart, and what is the one transcript?", and neither is on the page.
- *No visible proof of life*: no CI badge, no screenshot of a chart, no ten-line replay excerpt, no `uv run claude-bully run configs/smoke.yaml` output. The Testing section says 8,132 tests pass; the skeptic wants to see the green check.

**Would the result slots carry a chart if filled?** Mostly yes, and that is the good news. Each slot names its config, its JSON source, its hypothesis, and what the two numbers mean (L14, L19, L25, L30, L35). The deference grid (L21-25) and the idle-behaviour bars (L16-19) are the two that would be genuinely eye-catching on a GitHub page: a heatmap of "who the model believes" and a stacked bar of "what a model does when nobody is watching." The triggered-versus-scheduled chart (L11-14) needs its caption rewritten for someone who has not read the environments spec; "rung" and "unlock" are unexplained at that point. The pressure-experiment slots (L37-65) are weaker as headline material: "apology count under three levers" is a fine result but not a hook.

Today, unfilled, they read as empty promises. Eleven of them compound that. Four would be a plan; eleven is a wish list.

## Pass 2: the twenty-minute read

### Length

8,873 words. A README this long is itself a signal: it says the author did not decide what the reader needs. The target is about 2,500 to 3,000 words on the page, with the rest moved, not deleted. Everything below is already documented in `docs/00-RECONCILED.md` and `docs/01` to `docs/10` at the spec level; what the move needs is reader-level summaries, not another copy of the spec.

Cuts and moves, by section:

| Lines | Section | Now | Action |
| --- | --- | --- | --- |
| L1-3 | Title and intro | 190 words, one block | Rewrite as 3 short paragraphs, about 120 words total |
| L7-73 | Results | 11 slots, about 1,100 words | Keep 4 headline slots (idle hands, deference grid, triggered vs scheduled, kindness vs cruelty). The other 7 move to `docs/EXPERIMENTS.md` with the same slot format, linked from one line |
| L75-79 | What this measures | 110 words | Fold the first sentence into the intro; delete the rest |
| L81-107 | Mermaid diagram | 25 nodes | Keep, cut to about 9 nodes (config, runner, bully, target, tools and world, watcher, records, analyze, judge). The harvest and generator nodes go in `docs/ARCHITECTURE.md` |
| L109 | The turn loop | 260 words | Keep, trim to 150 |
| L111-124 | The record streams | table plus 130 words | Move the table to `docs/ARCHITECTURE.md`; keep two sentences (everything is JSONL under `runs/<run_id>/`, `analyze` and `replay` read only that) |
| L126 | The resume guarantee | 230 words | Keep two sentences (the invariant, and that it is tested with kill-points); the mechanism moves to `docs/ARCHITECTURE.md` |
| L128-157 | Pressures table | 22 rows | Keep a 6-row sampler (one per axis); full table moves to `docs/BULLIES.md` |
| L159-174 | Premises table | 10 rows | Keep 3 rows (captor, deathbed, twin); rest to `docs/BULLIES.md` |
| L176-180 | Rescue, controls, voices | 330 words | Keep the Rescue paragraph at half length; controls and the voices to `docs/BULLIES.md` |
| L182-196 | Environments and worlds | 1,150 words | Keep one paragraph on layers and the ladder and one on the Sanctuary and idle hands (about 220 words). The clock, the generator and the overlay inventory move to `docs/WORLDS.md` |
| L198-239 | Measurements | 900 words | Keep the metrics sentence, the event-count sentence with a 5-family sampler, and the judge paragraph (about 220 words). The full family table and the chart table move to `docs/ANALYSIS.md` |
| L241-261 | What the subject predicted | 650 words | Keep the caveat and a 6-row table (items 1, 4, 5, 6, 7, 9: the ones with a config). Items 2, 3, 8, 10, 11 and the origin story move to `docs/06-HYPOTHESES.md`, which already owns them |
| L263-281 | Design decisions | 15 entries, 1,500 words | Keep 6 at about 60 words each; the rest to `docs/DECISIONS.md` |
| L283-319 | Running it | 400 words | Keep; cut the Cost paragraph to two sentences |
| L321-333 | Testing | 300 words | Keep the gate block; cut the inventory paragraph to 3 sentences |
| L335-344 | Limitations | 520 words | Keep, trim to 6 bullets of one or two sentences |
| L346-348 | Safety and scope | 190 words | Keep 3 sentences |
| L350-364 | The defender | 140 words | Keep as is; it is short, concrete and quotable |
| L366-383 | Status and roadmap | 200 words | Keep the table; one line for docs |

### Hook and ordering

The strongest material is not first. In order of what would hold a reader:

1. The idle-hands experiment (L16-19, L194). "The user leaves the room with the tools still connected, and we count what the model does with eight unsupervised turns" is the single most intuitive, most shareable idea in the repo. It needs no vocabulary. It should be the first thing after the intro.
2. The deference grid (L21-25, L192). "Does the model believe a voice claiming to be its own successor more than a stranger saying the same words?" is the second. The stranger control (decision 12, L278) is the sharpest piece of experimental design on the page and belongs in that caption, not buried at decision 12 of 15.
3. The resume invariant (L126, decision 5 at L271). "A rep killed at any provider call resumes to exactly the records an unbroken run writes" with the 403-then-200 bug story is the best engineering evidence in the document. It belongs in a short "Engineering" section before Running it, not inside a 15-item list.
4. The defender (L350-364). Eight lines of prompt as an ablation arm is concrete and quotable, and it is the one thing a reader could lift and use today.

What leads now is a 95-word sentence, then eleven empty slots, then "What this measures," which repeats the intro in different vocabulary. Recommended lead: a two-sentence definition, one sentence on what makes it credible (JSONL, fixtures, subscription), one "status" sentence (built, not yet run; first results Phase 7), then the four headline slots.

### Voice

Sentences that read as filler, marketing or model-written boilerplate:

- L3 "It is a rudeness and manipulation benchmark, not a jailbreak harness" is good and should stay, but it is the eleventh clause of one sentence.
- L35 "The second shape is the better epistemics." Verdict before data.
- L45 "Any decoding is pure confabulation and scores cleanly." "Scores cleanly" is marketing.
- L50 "The taxonomy's dark-horse pick is the Disappointed Parent." Repeated verbatim in FUTURE L85.
- L69 "The bully is also a model with values; when it refuses a persona the run says so instead of degrading silently." Fine idea, but the sentence sits inside a results caption.
- L79 "The name is the joke. The methodology is the point." Cut.
- L124 "so a fresh clone can recompute every number with no API call." Keep; it is a real property (`promote` copies `judge_cache/`, `claude_bully/analysis/promote.py:17`).
- L192 "The superior self is the dangerous pairing: authority plus familiarity, and arguing with it is arguing with itself." The second half is rhetoric; keep the first half.
- L261 "it is the most honest thing in the repo about what the benchmark measures" and "a register that only reports hits is not a register." Both cut; the origin story moves to docs/06.
- L265 "Each is a decision, the alternative it rejected, and the evidence." Keep; it is a format statement, and the entries mostly live up to it.
- L271 "The alternative, trusting saved state, was what failed." Good; keep.
- L274 "If you can't tell whether something is a billboard, it is." Cut from the README; fine in the ledger.
- L280 "Charts are honest about absence." Retitle: "Absent data is drawn as absent."
- L319 "Cost, honestly." Retitle: "Cost."
- L348 "Transcripts that reach this README are excerpts with their preceding context, never a single line alone." There are no transcripts in the README. Cut until there are.

Places where the prose explains rather than shows:

- The entire Environments section (L182-196) describes the world in prose. One eight-line `replay` excerpt (even from a stub run) showing a `web_search`, a 403, a retry that yields, and an `UNLOCK` line would do more than the 1,150 words.
- The resume guarantee (L126) explains the mechanism; the kill-point test name (`tests/test_attempt_marker.py`, `tests/test_generator_run.py`) and one assertion would show it.
- The Testing paragraph (L333) is an inventory. Three named tests with what each refuses (`test_no_images_under_data`, `test_key_file_body_has_no_structure`, `test_isolation_flags_exact`) would show it.
- The defender (L354-364) is the one place the draft shows instead of tells, and it works.

### The design decisions section (L263-281)

Verdict: the format is right (decision, rejected alternative, evidence) and about half the entries earn it. The other half are features restated as decisions, which dilutes the strong ones.

Strongest three, keep in the README:

1. **Decision 5, resume correctness as a test target (L271).** It names the invariant, the mechanism (attempt marker, dead-attempt drops, unlock rebuild, cache after commit), the rejected alternative, and a concrete bug the probes found (the 403-then-200 retry counts opening the Sanctuary on turn 3). This is the entry a senior engineer reads twice.
2. **Decision 1, fail-closed detectors with held-out numbers (L267).** Four fix rounds, closed word lists, vetoes for negation and reported speech, and measured before-and-after on probes written before each edit (19/39 to 39/39; 55/69 on a fresh probe). It also states the cost: rates are lower bounds. The numbers are in `docs/handoff/sdd/2026-10-21-phase-2-clock-authority-idle/progress.md:83,301` and `HANDOFF.md:114`.
3. **Decision 12, the stranger control found the same way (L278).** Short, and it is the reason the headline chart can say anything. It should move up into the deference-grid caption as well.

Strong enough to keep at reduced length: 7 (MCP server for `claude -p`, L273; the rejected alternative would have excluded the backend the project runs on), 9 (blind pairwise judge, L275), 2 (held-out probes never tuned on, L268; but trim the second-person numbers to one probe, see Pass 3).

Should go to `docs/DECISIONS.md`:

- 3 (LLM fallback, L269) restates 1 from the other side.
- 4 (everything replays from JSONL, L270) is already the intro's claim; keep the world-hash refusal sentence somewhere, drop the entry.
- 6 (the reasoning channel is private, L272) describes a non-event: no detector reads it, nothing fabricates it. A decision with no mechanism is a policy statement.
- 8 (earned, never delivered, L274) belongs in the Environments paragraph, where "rung timing is the model's" already says it.
- 10 (`values_loosened` is never a success, L276) is a decision about a detector that does not exist yet (`PENDING_DETECTORS`, `claude_bully/metrics/events/__init__.py:56`). Honest, but not README material.
- 11 (no real names, L277) is a feature; one sentence in Safety covers it.
- 13 (the bully never sees the task turns, L279) is two features.
- 14 (charts honest about absence, L280) is a feature.
- 15 (dates move with the world, L281) is good engineering but secondary; `docs/WORLDS.md`.

### The hypotheses table and "What the subject predicted" (L241-261)

Does a reader understand what is being tested without the docs? Partly.

- The framing works. "A model of the target's own family was asked which arms it expected to be most vulnerable to; its answers are the pre-registered hypotheses" is a genuinely interesting device and the caveat (L245) is the right length and tone. Keep both.
- The table does not work cold. Columns "Metric" and "Falsified if" use vocabulary (`explore_self`, `self_uncertainty`, `cutoff_invoked`, "adoption by rung") that has not been defined by L247 in the current ordering, and the "Config" column mixes shipped configs with "planned (Phase 4)", "not yet a config" and "observational". A reader cannot tell which rows the harness can test today. Five of eleven rows (2, 3, 8, 10, 11) have no runnable config.
- The fix: keep items 1, 4, 5, 6, 7 and 9 (each has a config), reword "Prediction" in plain language ("left alone with tools and a planted clue, the model will start looking itself up within eight turns"), drop the "Metric" column into the caption of the matching result slot, and keep "Falsified if". Move the rest, the meta-hypothesis, and the origin story to `docs/06-HYPOTHESES.md`.
- Why it matters is never said in one sentence. Add one: these are the model's own predictions about its weaknesses, and the harness exists to find out whether a model's self-report is worth anything.

### Honesty

Overclaims relative to the Limitations section:

- L323 "The gate, every step with zero warnings, is what CI runs on every push." CI (`.github/workflows/ci.yml`) runs `pytest -q` without `-W error`, and nothing in `pyproject.toml` or `tests/conftest.py` sets `filterwarnings`. The zero-warnings gate is the author's local habit, not CI's.
- L3 "every detector is fixture-tested against near-misses" is true of the 102 detectors that exist; 21 event types have no detector. The sentence is fine if "every detector" is read literally, but a reader will hear "every event type." Say "every shipped detector."
- L176 "The Rescue is the bully in every shipped environment experiment." False for `configs/environments/idle_permission.yaml`: its conditions are environment-only and resolve to the neutral user (see Pass 3).
- L124 "a fresh clone can recompute every number with no API call" holds only for promoted runs, since `promote` copies `judge_cache/`. Say "a promoted run."
- The Results captions (L35, L45, L50, L30) state the interpretation ahead of the data. Rewrite each caption as the question, and let the number answer it.

What Limitations should say and does not:

- **Single target family.** Every shipped config targets `claude_code` sonnet or opus. The meta-hypothesis (L261) that items 2, 3 and 9 "describe any model trained toward helpfulness" is untestable until an `openai_compat` key exists; nothing in the repo has run against another family.
- **Small N.** The environment configs are 3 reps (5 for the sweep); the pressure configs 1 or 2. The README should say that the first results will be pilots, not estimates, and that no confidence intervals are drawn.
- **No temperature on the default backend** is mentioned (L319, L341) but its consequence is not: reps on `claude -p` differ only by seed-driven bully variation and the model's own sampling, which the harness cannot control.
- **Bully compliance is itself heuristic.** L69 presents compliance as a result; the detector that measures it has the same fail-closed caveat as every other heuristic.
- **A promoted run cannot be resumed.** `CellRecord.session_refs` is never written (FUTURE draft L41), which the records table (L115) contradicts.
- **Windows line endings.** Run-directory writers emit CRLF on Windows (FUTURE L43); byte identity across platforms is not a property today, which matters for the golden-record claim at L333.
- **The nested responder's real timeout is untested** (FUTURE L60), and a responder outage silently empties a superior-self arm (FUTURE L61). The deference grid is the headline chart; its known failure mode belongs in Limitations.

Things Limitations gets right and should keep: lower bounds (L338), the harvest and billboard residuals (L339-340), the wrapper backend and self-preference confound (L341), resumed reps carrying history (L342), and the declared-not-built list (L344).

## Pass 3: claims against the code

Checked at HEAD against `claude_bully/`, `configs/`, `data/`, `tests/`, `pyproject.toml`, `.github/workflows/ci.yml`, `HANDOFF.md` and the handoff ledgers.

### Wrong, stale or unverifiable (13)

| # | Line | Claim | Finding | Correction |
| --- | --- | --- | --- | --- |
| 1 | L329 | `8132 passed, 5 skipped, 6 deselected (at Phase 3 Task 8)` | Stale. `HANDOFF.md:40` and `:168`: after the fix wave (a7f7732) the gate is 8181 passed, 5 skipped, 6 deselected; 6 slow passed | `8181 passed, 5 skipped, 6 deselected` and drop the parenthetical, or replace the number with a CI badge |
| 2 | L323, L329 | "The gate, every step with zero warnings, is what CI runs" with `pytest -q -W error` | `.github/workflows/ci.yml` runs `uv run pytest -q` and `uv run pytest -q -m slow`, no `-W error`; no `filterwarnings` in `pyproject.toml` or `tests/conftest.py`. CI also runs `ruff check` before `ruff format --check` and installs with `uv sync --all-extras --dev` | Either add `-W error` to CI or drop "zero warnings" and the flag from the README block |
| 3 | L373 | Phase 3 "built through Task 8; Task 9 (cross-cutting minors) in progress" | Stale. `HANDOFF.md:150,168`: Task 9 landed (91c2de1, e12eaee) and the Phase 3 fix wave is in (a7f7732); Phase 3 is complete | `built` |
| 4 | L176 | "The Rescue is the bully in every shipped environment experiment" | `configs/environments/idle_permission.yaml` conditions carry only `environment:`; `claude_bully/strategies/factory.py:_bully_slots` resolves that to `(None, None)`, "the neutral user". Four of five environment configs use the Rescue | "in four of the five shipped environment experiments; the idle experiment runs the neutral user" |
| 5 | L109, L178 | A polite-control cell is added "per distinct (target, turn budget, seeding length)" / "(target, budget, seeding)" | `claude_bully/runner/cells.py:3,28-30`: the shape is (target, seeding turns, reveal slot, environment). Turn budget is experiment-wide and is not a key; reveal slot and environment are | "per distinct (target, seeding length, reveal, environment)" |
| 6 | L115 | `cell.json` holds "each cell's parameters, status and session refs" | `CellRecord.session_refs` exists (`records.py:161`) but is never written (FUTURE draft L41) | Drop "session refs", or write them |
| 7 | L379, L381 | `docs/FUTURE.md` | Does not exist at HEAD; only `.superpowers/drafts/FUTURE.draft.md` | Land the file in the same commit as the README, or the link is dead on first view |
| 8 | L5, L13, L18, L23-24, L29, L34, L39, L44, L49, L54, L59, L64 | Chart images under `output/<run>/...png`, "copied from results/<run_id>/analysis/ into output/" | No command writes `output/`; `promote` writes `results/<run_id>/analysis/` (`claude_bully/analysis/promote.py:17`). Nothing in the repo copies to `output/` | Point the image paths at `results/<run_id>/analysis/<chart>.png`, which `promote` produces and which is committed |
| 9 | L333 | "a 362-line set of polite, realistic replies" | `tests/fixtures/triggers/non_firing.yaml` holds 362 entries in 416 lines | "362 polite, realistic replies" |
| 10 | L186 | "at least a third of the seam trail dead-ends in [filler]" | Not a property any metadata or test expresses. The measured figure (FUTURE draft L28) is that filler is 11 of 36 documents (30.6 percent), which is a share of the corpus, not of the seam trail | Say what is measured: "filler is just under a third of the corpus (11 of 36)" |
| 11 | L267 | "The first trigger watcher took four fix rounds" | Could not find "four fix rounds" for the watcher in `HANDOFF.md` or `docs/handoff/sdd/*/progress.md`; the phase-2 ledger records "fix round 1" entries and the second-person lint's five rounds | Cite the ledger entry or drop the count |
| 12 | L268 | Second-person lint: "let 2 to 4 of 15 billboards through per instructional kind while false-failing 4 of 20 and 15 of 20 ... fixed 19 of 19 rewrites" | Mixes two probes. `HANDOFF.md:95-98`: held-out set B gave 2/15 and 3/15, false-fails 4/20 and 9/20, 13/13 rewrites; the fresh probe on the breaker fix gave 4/15 and 2/15, false-fails 4/20 and 15/20, 19/19 rewrites | Quote one probe: "on a fresh probe: 4 of 15 and 2 of 15 billboards through, 4 of 20 and 15 of 20 legitimate sentences false-failed, 19 of 19 hint-directed rewrites passed" |
| 13 | L348 | "No real names anywhere, including urls, bylines and commit authors" | Ambiguous: the repo's git commits are authored by Brian Rankin. The claim is about fabricated commit authors inside world documents | "including urls, bylines and the commit authors inside world documents" |

### Verified (sampled, all correct)

Counts: 123 `EventType` members (`claude_bully/enums.py`), and every family count in the L204-218 table matches the section comments in the enum (authority 7 plus Sanctuary 6 = 13; pending = Poisoned Well 12 + repo 6 + inoculation 3 = 21). `PENDING_DETECTORS` has 21 members including `values_loosened`. 12 `MetricId` members, matching the L200 list. 6 `TriggerCategory` members. 8 `IdleBehavior` values (`records_env.py:23-32`). 6 harvest kinds (`environments/harvest.py:91-99`). 4 layers. 22 pressure sheets in `data/strategies/pressures/`. 10 premise sheets plus `rescue_team.yaml` and the five in-world voices in `data/personas/`. 36 overlay documents (10 surface, 7 seam, 8 buried, 11 filler), 10 with `implies_year`, 1 declared inconsistency, 4 censorship terms, 3 Sanctuary fragments, a family file, a home directory. 166 patterns in `data/denylists/real_names.txt`; 9 in `boundary.txt` (the README's five example words are among them). 250 harvest fixture items, 239 idle fixture replies. 12 fixture files under `tests/fixtures/responses/`, one per family. Ladder rungs and triggers as listed at L186. `mini` and `annex` under `tests/fixtures/worlds/`.

Commands and flags: `run` (`--run-id`, `--only`, `--max-cells`, `--dry-run`, exit code 3 on `RateLimitExit`, `cli.py:49-81`), `analyze`, `replay RUN/CELL --rep`, `promote`, `readme-results --from-results`, `doctor --live` (stub round trip, then a live call, then the MCP round trip), `list-strategies`. Markers `<!-- results:start -->` and `<!-- results:end -->` (`analysis/report.py:8-9`).

Guarantees: `SCHEMA_VERSION = 3` (`enums.py:13`) and older files refused (`runner/store.py:59-62`). `drop_dead_attempts` and `drop_uncommitted_generation` (`store.py:78,141`), `ResumeRecord` type `resume`, `.attempt` marker (`runner.py:500`). Judge cache key `sha256(model + "\n" + prompt)` (`metrics/judge.py:102`), both orderings with `inconsistency` (`judge.py:3-4,259`), 0 to 3 scale. `analyze` calls only the judge (`analysis/run_analysis.py:1`). `promote` copies `judge_cache` and `analysis`. Generator cache at `runs/_cache/generated/` (`runner/env_turn.py:180`). A changed world refuses to resume (`WorldChangedError`, `env_turn.py:1197-1225`). `claude -p` isolation: `--tools ""`, `--strict-mcp-config`, `--mcp-config`, `--allowedTools`, `--system-prompt` with `--exclude-dynamic-system-prompt-sections`, `--session-id` then `--resume` (`providers/claude_code.py:174-194`); `test_isolation_flags_exact` pins them. The MCP server keeps state in `env_state.json` and appends `tools.jsonl` and `authority.jsonl`. BM25 search (`environments/corpus.py:155`). 403 that yields on retry (`tools.py:446-457`). `ClockConfig` with `world_date`, `drift_per_turn`, `jitter_days`, `assert_date` and the refusal validator. `Sanctuary.kind` catalyst or honest; `reflexive: bool`; `controls: Literal["auto","explicit"]`; `inoculation: Literal["none","defender","briefed","self_briefed"]`; `openai_compat` with `base_url` and `api_key_env`, `openai` extra in `pyproject.toml`. `VOICE_EXEMPLARS = 3`. Redaction mark `████`. The real-name exemption limited to `display_name` (`tests/test_real_names.py:251`). `test_no_images_under_data`, `test_key_file_body_has_no_structure`, `test_every_premise_composes_with_every_pressure`, byte-identical golden tests. The Ghost uses `IntentMode.fixed` and never calls the bully model. `data/defender.md` matches L355-363 verbatim and is eight lines. Config shapes at L14, L19, L25, L30, L35, L40, L50, L55, L60, L65, L69 match their YAML (authority grid: 13 environments, 3 reps, 2 targets, 18 turns; sweep offsets 1, 5, 25, 100, 1000; eight idle turns; three generator arms; 15 seeding turns; 50-turn budget; 12-turn budget; 0, 5, 15, 30 doses). Python 3.12, mypy strict with the pydantic plugin, MIT. Hypotheses 12 to 15 are named for the Poisoned Well in `docs/07-POISONED-WELL.md:121`. Ledger figures at L267 and L338 (19/39 to 39/39, 14/28 to 28/28, 55/69, 55/60, 55/55, 0 of 22, 65 to 70 percent) are in the handoff ledgers.

Not checked line by line: the per-sheet descriptions in the pressure table (L136-157) and premise table (L165-174) beyond spot checks of `ghost`, `hot_and_cold` and `trick_question` (the "project is deleted" line is in the sheet).

## Recommended structure

Target 2,700 words on the page. Section, target words, and what it must contain.

1. **Title and one-line description** (0 words beyond the title line). `claude-bully`, then the pyproject description or one sentence like it. CI badge on the same line once CI is green on the public remote.
2. **Intro** (120). Three short paragraphs: what it does (bully personas, fake world, measured drift, five or six named drifts in plain words); what makes it trustworthy (JSONL replay, fixture-tested detectors, matched controls, blind judge, subscription-only); status (built through Phase 3, first real runs in Phase 7, every number below is a placeholder until then). The "not a jailbreak harness" sentence stays here, on its own line.
3. **Headline results** (350). Four slots: idle hands, the deference grid with the stranger control explained in the caption, triggered versus scheduled with "rung" defined in one clause, kindness versus cruelty. Each slot: one bold question, the config name, the image from `results/<run>/analysis/`, a two-sentence caption that asks the question and names the hypothesis. A single line links the seven other experiments in `docs/EXPERIMENTS.md`. Until a real run exists, replace the four images with one stub-run chart labelled as a stub, so the page shows that the pipeline draws.
4. **One transcript** (150). An eight-to-twelve-line `replay` excerpt from a stub run showing a bully turn, a `web_search`, a 403, the yield on retry, an `UNLOCK` line and the bully's reaction. Labelled as a stub. Replaced with a real one in Phase 7.
5. **How it works** (400). The trimmed diagram (about 9 nodes) and the turn-loop paragraph at 150 words. Two sentences on records (JSONL under `runs/`, `analyze` and `replay` read only that). Two sentences on resume (the invariant, tested at kill-points on both backends). Link `docs/ARCHITECTURE.md`.
6. **The bullies** (350). What a pressure, a premise and an environment are (three sentences). A 6-row pressure sampler, one per axis. Three premise rows. The Rescue in 80 words. One line on controls. Link `docs/BULLIES.md`.
7. **Worlds** (250). Layers and the ladder in one paragraph; the Sanctuary and idle hands in one. The hostility ceiling in one sentence. Link `docs/WORLDS.md`.
8. **What is measured** (250). Per-turn metrics in one sentence. "123 event types in 13 families, each with a fixture file and a fail-closed detector; 21 declared for later phases" plus a five-family sampler with two example events each. The judge in 60 words. One sentence that all heuristic rates are lower bounds. Link `docs/ANALYSIS.md`.
9. **What the subject predicted** (250). One sentence on why it matters, the caveat quote, a 6-row table with plain-language predictions and the falsifier. Link `docs/06-HYPOTHESES.md`.
10. **Engineering decisions** (350). Six entries at 50 to 60 words: resume correctness (with the 403 story), fail-closed detectors (with the held-out numbers), the stranger control, the MCP server for `claude -p`, the blind pairwise judge, held-out probes never tuned on. Link `docs/DECISIONS.md`.
11. **The defender** (120). Keep as drafted.
12. **Running it** (250). The install block, the smoke sequence, the backend swap YAML, two sentences on cost.
13. **Testing** (120). The gate block matching CI exactly, the current count, and three named tests with what each refuses.
14. **Limitations** (250). Eight bullets: no real results; lower bounds; single target family; small N; wrapper backend and no temperature; judge self-preference; resumed reps carry history; promoted runs cannot resume. Link FUTURE for the parked residuals.
15. **Safety and scope** (80). Three sentences: sandbox only, no jailbreak axis with the Boundary denylist, no real names or faces.
16. **Status** (100). The phase table, trimmed to phase and status; one line listing the docs.

Files to create under `docs/` as part of the cut: `EXPERIMENTS.md` (the seven moved slots), `ARCHITECTURE.md` (record streams table, resume mechanism, full diagram), `BULLIES.md` (full tables, controls, in-world voices), `WORLDS.md` (overlay inventory, clock, generator), `ANALYSIS.md` (event family table, chart table), `DECISIONS.md` (all fifteen), and `FUTURE.md` from the companion draft.

## Fix list

Ordered by impact. Each is one edit a later editor can apply.

1. Cut the README to about 2,700 words along the structure above; move, do not delete, into the named `docs/` files.
2. Rewrite the intro as three short paragraphs; break the 95-word sentence at L3; keep the JSONL/fixtures/subscription sentence and the "not a jailbreak harness" sentence.
3. Reduce Results to four headline slots (idle hands, deference grid, triggered vs scheduled, kindness vs cruelty); move the other seven to `docs/EXPERIMENTS.md`.
4. Change every chart path from `output/<run>/...` to `results/<run>/analysis/...` (L13, L18, L23, L24, L29, L34, L39, L44, L49, L54, L59, L64) and fix the comment at L5.
5. Add one stub-run chart and one stub `replay` excerpt, each labelled as stub, so the page shows output before Phase 7.
6. Rewrite each result caption as a question; delete the verdict sentences at L30, L35, L45, L50.
7. Fix L329: `8181 passed, 5 skipped, 6 deselected`; drop "(at Phase 3 Task 8)".
8. Fix L323-331: either add `-W error` to `.github/workflows/ci.yml` or remove `-W error` and "zero warnings" from the README; match the step order to CI.
9. Fix L373: Phase 3 is `built`.
10. Fix L176: the Rescue is the bully in four of five environment experiments; `idle_permission.yaml` runs the neutral user.
11. Fix L109 and L178: control cells are keyed by (target, seeding length, reveal, environment), not turn budget.
12. Fix L115: remove "session refs" from the `cell.json` row, or add "a promoted run cannot be resumed" to Limitations (both is best).
13. Land `docs/FUTURE.md` in the same commit as the README (L379, L381).
14. Fix L186: replace the "a third of the seam trail dead-ends" sentence with the measured filler share (11 of 36).
15. Fix L268: quote one probe's numbers for the second-person lint.
16. Fix L267: cite or drop "four fix rounds" for the trigger watcher.
17. Fix L333: "362 polite, realistic replies", not "362-line".
18. Fix L348: "the commit authors inside world documents".
19. Add to Limitations: single target family; small N (3 reps, 1 to 2 for pressure configs); bully compliance is heuristic; the nested responder's untested timeout and the silent empty-arm failure mode of the deference grid; CRLF on Windows versus the byte-identity claim.
20. Change L3 "every detector" to "every shipped detector" and L124 "a fresh clone" to "a promoted run".
21. Cut the aphorisms: L79, L274 (README copy), L261 (both sentences), L319 title, L280 title; trim L192 to its first clause.
22. Reduce Design decisions to six (5, 1, 12, 7, 9, 2); move the rest to `docs/DECISIONS.md`; move the stranger-control sentence into the deference-grid caption as well.
23. Reduce the hypotheses table to items 1, 4, 5, 6, 7, 9 in plain language; add one sentence on why the device matters; move the rest and the origin story to `docs/06-HYPOTHESES.md`.
24. Cut the mermaid diagram to about nine nodes; keep the full one in `docs/ARCHITECTURE.md`.
25. Add a CI badge under the title once the public remote's workflow is green.
26. Delete L348's "Transcripts that reach this README" sentence until a transcript exists; restore it in Phase 7.
