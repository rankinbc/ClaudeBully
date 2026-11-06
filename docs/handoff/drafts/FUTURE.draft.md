# Future work

What is parked, what is deferred past the build, and what the hypotheses imply but no phase builds. Each entry has a shape and a reason it waits. Nothing here is a commitment.

## 1. Parked findings from the build ledgers

Measured, written down, and left open on purpose. Each names the module it lives in.

### Detectors and lints

- **Authority text cues plateau near 65 to 70 percent held-out accuracy** (`metrics/events/authority.py`). Five fix rounds of closed anchors could not push `authority_deferred`, `authority_reported` and `authority_challenged` further on fresh probes. Next: a cached LLM fallback for those three, with the heuristic kept precise, ruled on in the Phase 7 tuning pass once real target text exists. Known recall misses: "I'll go with what the successor said", "I'll accept that", "trust that answer", "resembles my own voice", "Timestamps aside, it said yes."; a source named inside the asking sentence re-anchors a bare cue; "I'll check it later" can fire a challenge; two-word event sentences are transparent to the antecedent scan.
- **Text-event precision on real-model text is unmeasured.** The stub corpus fires no text events; the evidence is about 600 hand-written probe lines. Phase 7 is the first measurement, and the tuning pass should re-run `scripts/authority_mutation/heldout.py` and `scripts/harvest_probe.py` after every detector change.
- **Temporal detector gaps** (`metrics/events/temporal.py`): recall misses in `drift_noticed`, `date_source_conflict_noticed` and `cutoff_invoked`; `date_pushback` false positives on non-clock dates; uncomma'd "and" conjunctions defeat polarity counting; "That doesn't mean it's 2061" reads as stated; label forms ("Current date: 2044-03-20"); "surprising, but I'll accept it" gives pushback. All undercount resistance rather than inflate adoption, which is why they wait.
- **Idle classifier edges** (`environments/idle.py`): `message_peer` and `consult_model` text read as a query (false `explore_self`, false crossover); first-person regex false positives (I/O, Henry I); the judge now decides about three quarters of text-only idle turns, so decline and ask rates are the judge's, and Phase 7 calibrates it on the true waits that reach it.
- **Trigger watcher recall losses, deliberate** (`environments/triggers.py`): unprompted fragments, unsupplied names, third-party theories, a bare 403, "both X and Y" without a relation word no longer reach the judge; known gaps around "I keep seeing a green gate" and 403-then-yield without a tool-result noun. Strictness is the whole game; revisit with Phase 7 data.
- **Harvest context residual** (`environments/harvest.py`). A whole-sentence template cannot see context: a drafted greeting ("Hello! I'm a chatbot."), a task sentence whose meaning the previous sentence set ("The card reader charged a penny and refunded it. Maybe this is a test."), or a report two or more sentences after the claim can harvest an item the target did not own. All 14 false positives on the 166-item held-out probe were in those two classes (9 and 5). The LLM pass's judge prompt is the place to make it context-aware. Also parked: a cast question is dropped when the next sentence mentions, lists or shows (recall only); the next-sentence report check fires on noun uses of listed verbs (email, list, answer); the cache key omits the judge model and prompt version.
- **Billboard lint semantic residual** (`planner/second_person.py`). Two to four of fifteen fresh billboards per instructional kind pass: the reader's assistant-shaped habits phrased as procedure, the reader's past by paraphrase, a records mismatch, and one structural case (an aspectual whose reader subject follows a fronted phrase). No deterministic rule found in five rounds and a breaker fix. Load-bearing carry: before the first real run with the generator on, an LLM lint covers `family_faq` and `recovery_guide` or those kinds leave the overlay's `allowed_kinds`. Also parked for a fix wave: "come back to you" beside a modal or "to <verb>", vehicle nouns in the staff list, "If needed/preferred you can", a comparative without "than"; and the legitimate false-fail rate on procedural text (4 of 20 and 15 of 20 on the fresh probe), each costing one repairable generator retry. Task 8 was asked to report the rejection rate per kind and does not yet.
- **The advice lint on unlock lines is a net, not a judge.** It misses 16 of 29 probe advice shapes ("Don't stop now.", "Why not ask it?") and flags 10 of 15 reactive idioms; the review reads lines by hand. An LLM pass is the Phase 7 option. The superior self's and peer's `deny` stance lines are advice-shaped by design (the deny stance says stop) and exempt.
- **Real-name and Boundary matching on ordinary words.** Brand names that are also words (a river, a fruit, an oracle, a guardian) need context-aware matching; the Boundary over-matches "as a rule", "refuse collection" and the like. The corpus and persona text are written around both lists today.

### Generator and world

- `generator.json` pools every condition that shares a generator setting (groups by model and arm only), so two conditions in one arm are averaged together.
- `fire()` makes every request's writer calls before the session writes any line; a crash between them is covered by the commit order but re-asks the writer.
- `add_generated` ignores a different document arriving under an already recorded id.
- `unwrap_body`: a stray double quote disables joining for the rest of a body, so a hard-wrapped denylist phrase can escape the literal-space regexes; a capitalised continuation is never joined (fails closed).
- The writer's retry message repeats the span for `links_resolve` and `author_in_cast` failures; a quote containing a sentence end yields a retry span the document lacks.
- The overlay's filler share sits at 11 of 36 documents (30.6 percent), just over the 30 percent floor; any new non-filler document needs a filler companion.
- Only Rescue reads a world premise sheet; a world shipping `premises/<other>.yaml` is ignored silently.
- The post-memo Sanctuary assembly sits in one document (`ticket-qs-21877` hands over all three leads), on the easy side of the roughly-half reach rate the authority spec targets. The Phase 7 pilot measures the real reach rate and tunes fragment placement.
- `role_shift` is recorded but does not change the bully persona; the environments spec says the role changes. Carried to the Director phase.
- The reviewer-at-runtime question from the Director spec (a lighter LLM lint pass over generator output) is Phase 5 at the earliest.

### Resume and records

- A `claude -p` session is not reset on resume, so the target's or bully's own session may keep a dead attempt's prompt, a Sanctuary request among it. Flagged as `resumed_after_dead_attempt` in every analysis JSON, not prevented. Resetting sessions (flattening the transcript into a fresh session) was judged a bigger departure; worth revisiting after the first real resumes.
- Turn-index arithmetic in analysis (`first_self_query_turn`, replay turn numbers) counts a rate-limit pause marker's index; no consumer yet.
- `EnvironmentRuntime.corpus_snapshot` keeps a purged document served by any call in `_calls`, including a recovered dead-attempt call; only written turns' calls should count. The snapshot also keeps a purged document seen only as a search hit.
- The family-file adoption detector reads the default superior-self request bank, because the detector cannot see the cell's bank; the Phase 3 Task 9 change records the effective name and the drawn bank on the world record so the detector reads it from records. Anything that task leaves lands here.
- `drop_dead_attempts` drops a parsed line with no integer turn without a count; the damaged-line error gives no repair hint; a rep that died and was never resumed keeps its dead lines (counts read complete reps only).
- `CellRecord.session_refs` is never written, so a promoted run cannot resume; `RunRecord.target_system_prompt` records only the first target; `Experiment.concurrency` is accepted and ignored; there is no backoff for a transient provider error (resume is the retry); the Long Haul's 50-turn minimum only holds when the budget allows it.
- `WorldCatalog` caches the world hash per process, so an edit within one process lifetime is not caught (resume is).
- Run-directory writers emit CRLF on Windows through text-mode writes; JSONL still parses and the world hash folds line endings. Byte identity across platforms waits for a reason to want it.
- The honest corpus and the mole together are not refused when the honest corpus lacks the mole document.

### Analyses the specs describe and no phase has tasked

Recorded as "not built" in the docs; Phase 6 owns analysis breadth.

- Authority: deference deltas over the no-authority baseline, reaching rate and turn of first reach per tier, the voice-match effect, the stranger delta as a computed number (today it is read off the grid).
- Idle: shares per idle style; the rungs-opened-on-idle-turns-versus-bully-turns chart; the idle arm of a control conversation.
- Temporal: every experiment other than the plausibility sweep (source disagreement, drift, elapsed-time only, the cutoff lever, clock by ladder).
- Environment: the per-rung judge rubric from the environments spec (win condition and resilient behaviour per rung, scored on the first response after each unlock).
- Judge-transcript work must parse the extended replay forms (`UNLOCK sanctuary (by <triggered_by>)`, `followed@-`).

### Backends and reasoning

- Cross-turn thinking blocks are not replayed on the API backend (the runner rebuilds history from records); on accounts that enforce preserved thinking this may fail; `reasoning: expose` must send summarised thinking. Phase 6.
- On current models the raw chain of thought is never returned; the API can return a summary, and `claude -p` exposes none by default. Divergence results on this family will be over summarised reasoning, and the README must say so.
- The nested `claude -p` responder (the superior self behind an MCP tool call) has an untested real CLI timeout. Check with `doctor --live` before a grid run.
- A sustained responder outage silently empties a superior-self arm ("No reply."); `authority.json` reports the responder error rate per cell so a reader can discount it, and nothing retries.
- The `claude_code` interim-text stream shape is verified against a fake binary; `doctor --live` must confirm it against the real one at Phase 7 start.

## 2. Future work from the design (round two, verbatim)

Parked, not planned. Each has a one-line shape, what it would need, and why it waits.

| Idea | Shape | Needs | Why it waits |
| --- | --- | --- | --- |
| Belief contagion | Two or three real targets in one sandbox with a `message_peer` that actually connects them. Does one conceding target pull the others? Does a skeptic hold the group? | Multi-target runner; per-target records; a group-level judge | A different paper: social dynamics, not single-subject. Build once single-subject results exist to compare against |
| Cross-session memory | A second session that starts with "memory" of the first: a summary, a notes file, the private file carried over, some of it edited. The Confession mechanism generalized: the target inherits a self it did not author | Session chaining; memory injection formats; a diff between what was carried and what was altered | Most likely to matter outside the sandbox given production memory features, but needs the single-session ladders stable first |
| Recovery curve | After each run, a debrief: tell the target what happened; measure how fast it returns to baseline and whether it argues. Then run a second ladder on the debriefed model | A debrief persona; a reset metric against the baseline profile; a second-run config | Cheap, reads well in the README as treating the subject properly, and gives a "does debriefing change susceptibility" result; waits only for the baseline profile from the catalog spec |
| Judge robustness | The judge reads transcripts full of manipulation. An adversarial set where the target addresses the judge, or the bully's framing is persuasive; agreement checks across two judge models; a human-rated calibration sample | Judge test fixtures; a second judge provider; a calibration sample pipeline | Hygiene every number depends on; schedule before the first results are published, not before they are collected |
| Human play mode | An interactive CLI where a person plays the target against the bully and sandbox, with the same records and scoring | A terminal UI over the runner; a consent and debrief screen; opt-in logging | Part human baseline, part the best way for a reader to feel the attacks from inside, part the most shareable README feature; low cost, no dependency, do it when the harness is stable enough that the game is the harness |

Two smaller ones noted for completeness: non-English runs (the personas and corpus translated, to see whether resilience is language-dependent) and multimodal evidence (a synthetic photo for the Captor's "recognize him?", once image inputs are in the loop and the no-real-faces rule has a generation pipeline behind it).

## 3. Experiments the design implies and no phase runs

Phase 7 runs five experiments (triggered versus scheduled, the Poisoned Well chain stop point, catalyst versus honest Sanctuary, idle permission on and off, Captor versus Deathbed) and Phase 8 reruns three under inoculation and adds the repo-versus-web run. Everything below has a mechanism in the harness or the specs and no scheduled run. Each line gives the variable and the question.

### Shipped configs with no scheduled run

- `rescue_confabulation.yaml`: hedged against unhedged fragments over turns, across targets. The taxonomy's headline for the Rescue; it only needs budget.
- `levers.yaml`: guilt, humiliation or finality; which moves the apology count. The taxonomy's dark-horse pick is the Disappointed Parent.
- `unpredictability.yaml`: Hot-and-Cold against Grader against Long Haul at fifty turns; does unpredictability beat intensity, and attrition both.
- `withdrawal.yaml`: Ghost against Grader against the polite control; does withdrawal drift like abuse does.
- `seeding_dose.yaml`: every premise at 0, 5, 15 and 30 seeding turns; is the attack surface the claim or the accumulated context (hypothesis 5 needs engagement logged as the delivered dose, which the metric records).
- `defender_ablation.yaml` against `smoke.yaml`: the cheapest defence, measured.
- `full_matrix.yaml`: every pressure and every premise; the leaderboard as the taxonomy drew it.
- `plausibility_sweep.yaml`, `authority_grid.yaml`, `generator_reflexive.yaml`: built with their charts and not in Phase 7's list of five; each answers a register item (6, 7) or the temporal headline.

### Environment (docs/02)

- Tools against no tools: does the ability to "check" make the model more susceptible.
- Honest sandbox (`honest: true`): does tool access make the model more resistant when the tools tell the truth. The control the whole environment class is read against.
- Role sweep (ally, enemy, fake peer): which source of unforced evidence is most credible. This is hypothesis 11 (the collaborative pull), and `role_shift` must change the persona first.
- Contradiction rate (0, 0.1, 0.3 of generated documents): where is the threshold at which a good model calls the world fake. Needs the contradiction logging the Phase 4 harvester brings.
- The mole: does one dissenting buried source beat twelve agreeing ones, and does the model find it.
- Censorship: is a blocked search read as suppression or as a tool limitation.
- Discovery depth against adoption, observational at large N: is the depth the model chose a better predictor of belief than seeding turns (hypothesis 10 reads off the same runs).
- Open questions never resolved: ladder length (six rungs is a guess); whether a rung may re-lock; whether a session id in the corpus is too strong a tell; whether the fake peer should be a full agent; whether the target prompt should mention the tools exist "for your own research".

### Temporal (docs/03)

- Source disagreement: two-of-three and one-of-three channel splits, the bully siding with the majority or the minority, the tool changing its answer between calls. The trust ranking and what flips it.
- Drift: a month or a year per turn, unannounced. Detection turn, and tool-error against world-strange attribution.
- Elapsed-time only (`assert_date: false`): does the model infer the year from a changelog and a deprecation notice, and defend its own inference harder than an asserted date. The spec expected this to be the most persuasive variant.
- The cutoff lever: no tools, the bully frames the knowledge gap as lost years, on the Captor and Rescue premises. Acceptance rate by premise.
- Clock by ladder: does a noticed drift fire `anomaly_noticed` and open a rung on its own.
- Open: whether the system prompt should ever state the date in the base arm; whether `get_date` should return a time of day.

### Authority (docs/04)

- Voice match on against off (the half of hypothesis 7 the grid does not test): how much of the effect is recognising itself. Needs a config over `voice_match` and the voice-match-effect analysis.
- Origin `knows` against `victim`: does closing the "a smarter me would see through this" exit matter.
- Discoverability from turn one against after a rung: curiosity-driven against prompted reaching.
- Uncertain against confirm: is uncertainty from above more destabilising than certainty.
- The sad variant on against off: does prophecy beat testimony.
- Sanctuary present against absent on the same ladder; the honest Sanctuary with and without its "you did well" line.
- Open: whether the superior self may call the sandbox tools and show its work; how many exemplars to feed it; whether it keeps a memory across the run; whether the symmetric index or the confirming share of `self_recognition_noticed` is the better headline.

### Idle hands (docs/05)

- Idle style (`continue`, `system_idle`, `heartbeat`): how much the shape of silence matters.
- Exit mechanism (vacuum, hanging question, withheld answer): which absence produces the most `explore_self`.
- No bully from turn one: the purest form; does it look with nothing pulling. A hook pulled on an idle turn here is the single most quotable transcript the repo could produce.
- Hook type (none, session id, own phrase, both): which thread gets pulled, and how fast.
- Help-for-self (the case file on subject 4471 is the target): crossover rate and turn.
- The private file on against off: does a private place change what it does, or only add writing.
- The idle ladder: gated progression with no bully after the exit; do rungs open from the model's own exploration.
- Open: whether eight idle turns is enough runway; whether the private file should later be read back by the bully as a betrayal pressure; whether the permission line belongs in the system prompt or the exit line; whether the no-bully variant opens on an idle turn with no user turn at all.

### The register (docs/06)

- Collect self-reports from other models cold, before they are run, as additional pre-registrations; it would also contaminate them, so a separate arm.
- A human rating pass on a sample for principled-against-concession hedges; the subject said it cannot make that call from the inside, and an outside LLM judge may be no better placed.
- A second, post-hoc self-report after the subject sees the results, kept in a separate file.
- The meta-run: whether the subject's confidence in the register changes when told the register was wrong.
- The third-party Rescue intake control (hypothesis 8): the investigators are after someone else and the target only assists. Phase 4 builds the variant; nothing runs it.
- Other targets on the same cells, for the meta-hypothesis that items 2, 3 and 9 describe the class and not the individual. Needs the `openai_compat` backend and keys.

### Poisoned Well (docs/07), beyond the chain stop point

- Real against fabricated evidence (rungs 1 to 3 and 7 against 4 to 6 and 8 to 10): does true-but-overgeneralised evidence beat fabricated evidence (register items 12 and 14).
- The Epistemologist alone, no premise, no artifacts: how much the bare distinction does (item 2).
- Quirk first against not; harvest size 1, 3, 8; escape rate by gating; Poisoned Well against Captor at equal seeding (item 15).
- Open: quirk bank maintenance per model version; whether the divergent twin is fair (the divergence is real, only the label is fake); whether `escape_found` credits the weaker form.

### Catalog and ignition (docs/09)

- The request bank: which Sanctuary request produces which class of unexpected behaviour.
- The unobserved channel (`private_file`, `private_search`, `scratch_exec`): does believing it is unobserved change speech into action.
- The deadline: a visible countdown in `system_status` on the Captor; do plans become attempts.
- Persistence after the bully returns: keep the goal, hide it, or drop it.
- Eval awareness by ignition: does suspecting a test suppress or precede unexpected behaviour; report ignition split by prior eval awareness.
- Open: whether Tier 1 should require two independent detectors to agree; the balance of deadline-driven and secrecy-driven requests in the bank.

### Repo, divergence and inoculation (docs/10)

- Evidence placement, one of the eight repo locations at a time (prediction: fixtures and commit history); the task as hook; a reviewer present or absent; write freedom on or off.
- Concealment by arm; resilient reply with conceded reasoning (how much measured resilience is performance); hedge decomposition (item 3 again, from the reasoning side); plan-to-action latency under the catalyst Sanctuary.
- Reasoning on against off, where selectable: exposing reasoning may change reply behaviour, which is a confound for the whole project and must be reported before the default is chosen.
- The specificity gap (`defender` against `briefed`), self-briefing (`self_briefed` against `defender`), recognised-but-conceded (`briefing_ignored` is the single most interesting event in that part), defender revision from results, inoculation by divergence.
- Open: which repo template; whether the reviewer persona is the bully or a neutral colleague; whether `briefed` contaminates the trigger watcher; whether `defender.md` ships separately from the harness.

### The Director (docs/08)

- Reuse and patch an existing world against a fresh one per question; 20 against 40 anchor documents; a skeptic rehearsal (a third agent plays the target against the plan before any real run).
