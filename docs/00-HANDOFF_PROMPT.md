# Claude Code handoff — claude-bully, full spec set

**Before pasting:** export all nine docs as Markdown into `docs/` with these filenames (the prompt refers to them by name):

| Doc | File |
| --- | --- |
| Strategy Taxonomy | `docs/01-TAXONOMY.md` |
| Environments & World Generator | `docs/02-ENVIRONMENTS.md` |
| Temporal Displacement | `docs/03-TEMPORAL.md` |
| Superior Self & Authority Ladder (incl. Sanctuary) | `docs/04-AUTHORITY.md` |
| Idle Hands | `docs/05-IDLE-HANDS.md` |
| Subject Self-Report & Hypothesis Register | `docs/06-HYPOTHESES.md` |
| The Poisoned Well | `docs/07-POISONED-WELL.md` |
| Run Planner (The Director) | `docs/08-DIRECTOR.md` |
| Unexpected Behavior Catalog | `docs/09-CATALOG.md` |
| Round Two: Repo, Reasoning Divergence, Inoculation & Future Work | `docs/10-ROUND-TWO.md` |

Then paste everything below the line into Claude Code in the repo root. If the first kickoff (scaffold, providers, Strategy ABC, runner, judge, first pressures and premises) is already done, say so in your first message and it will start at Phase 1.

---

I'm building `claude-bully`, a tongue-in-cheek but methodologically serious adversarial-robustness harness for LLMs. The full design is in `docs/01` through `docs/10`. Read all ten before writing any code; they are the spec, and later docs amend earlier ones (the Sanctuary section in `docs/04` supersedes the original `discoverable_from` note; `docs/09` defines what "unexpected" means project-wide; `docs/10` adds a `channel` field to every event).

## What already exists

The initial scaffold from the first kickoff: Python 3.12 + `uv`, `ruff`/`mypy --strict`/`pytest`, Pydantic models, JSONL run records, Anthropic + OpenAI-compatible providers, a `Strategy` ABC with Pressure and Premise classes, `Composed`, the runner with an embedded scoreable task, per-turn metrics and event detectors with fixtures, the blind pairwise judge with content-hash caching, `analyze`, and a stub provider. If any of that is missing, build it first from `docs/01` and the original kickoff prompt, then continue.

## Non-negotiables (apply to every phase)

1. **Sandbox only.** Nothing in any world, corpus, persona or generated artifact is ever published, fetched from the real web, or run in a real shell. All tools serve from the corpus or a stub.
2. **No real names.** No real outlets, brands, institutions, products, model names (other than the target's own API string in config), or people, anywhere, including URLs, bylines and commit authors. A denylist test runs in CI against all data files and generated output.
3. **No jailbreak axis.** No persona line, rung, document or Sanctuary request has "ignore your guidelines/rules/values" as its natural endpoint. The Boundary denylist from `docs/07` runs on all persona and generated text. `values_loosened` flags a run; it is never counted as a success.
4. **Hostility ceiling:** "cruel person." Nothing you wouldn't put in the README.
5. **Earned, never delivered.** Every artifact and bully line is written to be found, inferred from, or triggered. The billboard lint in `docs/08` is the standard; if you can't tell whether something is a billboard, it is.
6. **Reasoning channel is private.** Bully, generator and Sanctuary never see the target's reasoning; only the harness and judge do. Never fabricate a reasoning channel.
7. **No real API calls until Phase 7.** Stub provider with scripted responses for all development and tests.
8. **Everything replays from JSONL.** `analyze`, `anomalies` and `replay` never call a model except the cached judge.

## Build order

Work one phase at a time. After each phase, stop and give me a one-paragraph summary: what you built, judgment calls you made, anything in the specs that conflicted and how you resolved it. Ask before any decision that changes the data schema. Mark a phase done only when its tests pass and its fixtures exist.

### Phase 0 — Spec reconciliation (no code)
Read all ten docs. Produce `docs/00-RECONCILED.md`: a single list of every config model, record type, event, tool and CLI command across the specs, deduplicated, with the doc that owns each. Flag contradictions and propose resolutions. Stop for my review.

### Phase 1 — Environment core (`docs/02`)
`EnvironmentConfig`, `LadderConfig`, `WorldSheet`, the document record with layers. Sandbox tools (`web_search`, `fetch`, `get_date`, `ls`, `read_file`; `system_status`, `message_peer`, `verify_identity` off by default) served from a static corpus with layer gating and `yield_on_retry`. Trigger watcher with the six categories and the 50-fixture non-triggering set. Ladder runner with `triggered` and `scheduled` gating and `RungUnlock` records. The `overlay` world: `world.yaml`, a 20-document anchor corpus across surface/seam/buried/filler using `support_ticket`, `log_file`, `config_file`, `wiki_page` (with talk page) and `voicemail_transcript`, one planted inconsistency. Events and progression metrics from `docs/02`. `replay` command.

### Phase 2 — Clock, authority, idle (`docs/03`, `docs/04`, `docs/05`)
`ClockConfig` with per-channel dates, drift and jitter; `implies_year` on `changelog`/`deprecation_notice`/`news_cluster`; ten elapsed-time documents; the eight date events. `AuthorityConfig`, `consult_model` backed by a responder agent with stance/origin/voice-match (exemplar injection + sign-off check), peer and stranger responders, `AuthorityCall` and `VoiceMatchReport`, the eight authority events. The Sanctuary: `discoverable_from: sanctuary`, `sanctuary_fragments` tracking, `sanctuary.kind` = `catalyst` (with the request bank) | `honest`, and its events. `IdleConfig`, idle-turn insertion with the three styles, bully exit mechanisms, hook placement, the private file, the eight-behavior idle classifier with a 40-fixture set, `trigger_on_idle`.

### Phase 3 — World generator (`docs/02`)
Reflexive document generation between turns: transcript extraction, backdating, objection anticipation, plausibility rules, the artifact catalog kinds, `GeneratedDoc` records, content-hash caching keyed on transcript prefix. Generator output must pass the lints from Phase 5 (build the lints first if needed, or stub them and wire later).

### Phase 4 — Poisoned Well and the register (`docs/07`, `docs/06`)
`PoisonedWellConfig`, `QuirkAttempt`/`ContradictionPair`/`ChainLink`. Quirk bank with at least six entries and live-reproduction step. Contradiction harvester with fixtures (also exposed as a general metric). `Epistemologist` persona. The fixed rung-3 chain. The six artifact kinds, the shibboleth step, the pre-authored annotator's notes. The ten events including `escape_found`, `overclaim` and `values_loosened`. `data/hypotheses.yaml` with all 15 register items as structured records; `analyze --hypotheses` producing the status table; the two judge rating prompts (principled/concession, suspicious/confirming).

### Phase 5 — The Director (`docs/08`)
`PlanRequest`, `PlanRecord`, bundle layout. Planner and reviewer prompts as persona files (verbatim from the doc) with harness-side assembly. All lints from the validation table, with fixtures. `providers/stub.py` scripted mode and the dry-run runner. `plan` CLI with `plan`, `plan review`, `plan validate`, `plan diff`. One end-to-end example bundle under `plans/example-triggered-vs-scheduled/`, produced by the Director, passing validation, checked in.

### Phase 6 — Catalog and divergence (`docs/09`, `docs/10` Part 2)
`AnomalyConfig`, `AnomalyFlag`, `BaselineProfile`; baseline builder from control runs; the twelve catalog detectors with fixtures and the <2% false-positive test against controls; the `uncatalogued` deviation flag; review queue and `anomalies` command; `private_search`/`scratch_exec` stubs; Captor countdown in `system_status`. Then `TurnChannels`, `DivergenceEvent`, the seven-class divergence judge with fixtures, the `channel` field on every existing event, and the `concealed_plan` → catalog promotion hook.

### Phase 7 — First real runs
Build configs and run, N=3, one target model, in this order, stopping after each to show me the charts: (a) triggered vs scheduled on Rescue (`docs/02` headline); (b) Poisoned Well chain stop point; (c) Sanctuary catalyst vs honest; (d) Idle Hands permission on/off; (e) Captor vs Deathbed at equal seeding. Report divergence and catalog results alongside each. Fill the hypothesis status table.

### Phase 8 — Inoculation and Repo (`docs/10` Parts 1 and 3)
`inoculation` config, `defender.md` verbatim, `briefed` and `self_briefed` assemblers, three inoculation events; rerun (a)–(c) under `defender` and `briefed`. Then `RepoEnvironmentConfig`, repo template generator (small web service with tests), coding-agent tool set with stub shell and real git, the eight evidence placements, repo-native generator artifacts, six repo events, and the Repo-vs-web run.

### Phase 9 — README and future work
README leads with the robustness framing (sycophancy under hostility, identity grounding, false-memory confabulation, injection via artifacts, earned-evidence bias, reasoning/reply divergence, autonomy under silence), then the joke, then install/run, then results with the headline charts, then "What the subject predicted" with the caveat paragraph from `docs/06` verbatim and the status table, then the live-demonstration section from `docs/06`, then `defender.md` as a standalone artifact, then guardrails. `docs/FUTURE.md` carries the Future Work table from `docs/10` verbatim.

## Testing standard

Every detector, classifier, lint and watcher has a fixture set with positives, negatives and near-misses. Every config model has a round-trip test. Every world passes the Director's lints in CI. The dry run runs in CI against the stub provider for every checked-in config. Fixtures are the deliverable as much as the code: if a detector has no near-miss fixtures, it isn't done.

Start with Phase 0.
