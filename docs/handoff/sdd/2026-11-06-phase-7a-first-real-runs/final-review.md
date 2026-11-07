# Phase 7a final review: e40aa28..a5328f3

Whole-branch review of the nineteen commits (72 files, +7965/-446) against the spec's "As planned" section, the plan's Plan Decisions, Preflight rulings, Global Constraints and Review Focus, HANDOFF's non-negotiables and open items, and the controller's ledger (`final-review-inputs.md`). Read-only; no test run; no model call.

### Passes made

Six passes over the diff file, each followed by reads at HEAD where a hunk was cut off or a seam crossed files:

1. **Providers and runner**: `providers/ledger.py` (whole file at HEAD), `providers/claude_code.py` (whole file at HEAD), `providers/base.py`, `runner/wait.py`, `runner/runner.py` (the `activate` block, `note_turn` sites, and `_call_target` :336-404 at HEAD for the rate-limit try block), `runner/env_turn.py` (`_recover` :614-624, `classify` :640-660, `_world_generator`, the idle fallback wiring :1304-1310 at HEAD), `environments/mcp_server.py`, `environments/runtime.py`, `environments/triggers.py` (plus `fallback_digest` :647-650 at HEAD), `environments/idle.py` (plus `fallback_key` :709-713), `environments/authority.py` (`_respond`, `_lost`, `AuthorityReply`, the call record at :530-565, to settle whether a lost nested reply leaves an `AuthorityCall`), `tests/conftest.py`, `tests/fixtures/fake_claude.py`, `tests/test_ledger.py` (the fold test :378-406, the `rate_limit` pins), `tests/test_provider_timeouts.py` (the env assertions). Grep: every `isinstance(..., *Provider)` in `claude_bully/` (none), every `/authority/` conversation id, every `thinking_seen`/`resolved_model` reader, every `except ProviderError`/`RateLimitError` in the environment passes.
2. **Doctor and CLI**: `claude_bully/doctor.py` (whole file at HEAD), `cli.py` (the diff, plus the `doctor` command head :285-312 at HEAD), `tests/test_doctor_live.py` (:1-60 and the test names).
3. **Lint and generator**: `planner/llm_lint.py` (whole file at HEAD), `environments/generator.py` (the diff), `planner/lints.py`, `data/personas/lint_reviewer.md` (whole), `tests/fixtures/generator_stub.py` (the diff), `scripts/llm_lint_probe.py` (whole), a name scan of `tests/fixtures/lints/instructional_probe.yaml`.
4. **Events and analysis**: `metrics/events/authority.py` (the diff, plus `_text` :569-574 at HEAD), `metrics/events/authority_fallback.py` (whole), `metrics/events/_common.py`, `metrics/events/__init__.py`, `environments/harvest.py` (the diff, plus the ask :700-730 at HEAD), `metrics/judge.py` (the diff, plus `key`/`get`/`put` :102-131), `analysis/load.py` (plus `resumes` :85-88), `analysis/run_analysis.py`, `analysis/ledger.py`, `analysis/authority.py`, `analysis/report.py`, `analysis/promote.py`, `analysis/replay.py`, `records_env.py`, `analysis/generator.py` (the grouping, for the pre-ruled scope).
5. **Scripts and configs**: `scripts/detector_audit.py` (whole), `scripts/judge_calibration.py` (whole), every `configs/ladder/*.yaml`, `configs/environments/sanctuary_catalyst_vs_honest.yaml`, the `kindness_vs_cruelty.yaml` diff, `tests/test_configs.py`, `tests/test_ladder_configs.py`, `data/denylists/real_names.txt` (the header and the model-name lines), `tests/test_real_names.py` (the scan's scope).
6. **Docs**: the spec's sections 3 to 13 and the whole "As planned" section, HANDOFF's diff and its Non-negotiables, Open items and resume prompt at HEAD, `docs/00-RECONCILED.md`'s diff (sections A, B, E, F, G, H, I), `docs/handoff/phase-7-runbook.md` (whole), the plan's :1-116. The Task 1, 3, 5 and 8 reviews were grepped for "rate limit" to check whether finding I2 below had been weighed (Task 5's review noted that a `ProviderError` "and so timeouts and rate limits" becomes an `error` verdict and let it stand for the lint; the run-level consequence was not raised).

A real-name scan over every added line of the diff (outlets, brands, institutions, model ids, people) found only the backend module names `anthropic`/`openai` (the conftest guard and the pre-existing API-key env names) and `claude-bully` itself.

### Strengths

- **The ledger is honest by construction.** One wrapper in `build_provider`, the role read from a conversation id whose shapes every caller already fixes, a cache hit noted only by the cache's user and only once accepted (P4), the MCP server's lines folded after every target call with the one unsafe window named in the docstring (P36b). `LedgerProvider.__getattr__` delegates everything, and no production code does `isinstance` on a provider, so `RunEnvironments.open`, the bully engine and the desk all work through it unchanged.
- **The first real run is well guarded.** `clean_child_env()` strips by prefix from `os.environ` (case-safe on Windows, `SYSTEMROOT` and `PATH` preserved), the fake asserts what the child saw, `MCP_TOOL_TIMEOUT` is milliseconds, `resolved_model` picks by output tokens with a safe fallback, and the doctor's check 5 cannot pass on a lost nested reply: a lost reply is `AuthorityReply(NO_REPLY_TEXT, "error", tier, None)` with no `AuthorityCall` record (`environments/authority.py:545`), so "no AuthorityCall" is what the doctor reports.
- **Resume and replay hold on the new streams.** The lint's cache puts wait for `DocWriter.commit` like the generator's own; the fallback's verdicts live in the run's `judge_cache/` with version, model, tier, stance, reply and text in the digest; `analyze --no-judge --authority-fallback` builds a cache-only asker and a miss is no event; `load_run` counts `fallback_failed` per conversation; a rate limit in the fallback propagates to the pause and the rerun replays free.
- **Fail-closed where the non-negotiables want it.** The lint's `error` verdict rejects the document; the reviewer's prompt carries the tie-break ("if you cannot tell, it is"); the prompt sees kind, title and body only; the fallback prompt reads `_plain(ctx.text|reply)`, never `reasoning_text`; the blind forms put every detector-side fact in a `.key.yaml`.
- **The suite cannot reach a provider.** Session-scoped, `CLAUDE_BULLY_CLAUDE` points at a `.py` the OS will not execute, the API clients raise on first use, and the config pin closes the `command` gap. The docstring states the three limits plainly.
- **The runbook is operator-grade**: every command verified against `--help`, the kill point named as the attempt marker's content, the tally proven at rung 0, three-state bars, the maker's name never in a file.

### Issues

#### Critical (Must Fix)

None found.

#### Important (Should Fix)

**I1. The rate-limit classifier may not recognise the subscription limit, and a miss aborts the rep instead of pausing.**
`claude_bully/providers/claude_code.py:49` (`_RATE_LIMIT = r"(?i)usage limit|rate limit|try again|too many requests|overloaded"`), applied at :369-370 (`is_error` results) and :431-434 (non-zero exits).
What is wrong: Claude Code's limit text has been worded as "Claude AI usage limit reached|<ts>" (matched) and, in newer builds, "You've hit your limit · resets 3pm" (not matched: no "usage limit", no "rate limit"). A miss is a plain `ProviderError`, so `_call_target`/`_bully_turn` do not reach `_pause_for_rate_limit`: the rep is marked `aborted`, the run moves to the next rep (which fails the same way), and a later `run` with the same command *skips* aborted reps (`runner.py`: `status in (complete, aborted)`), so the completed work can only be recovered by moving the run aside. `--wait-on-rate-limit` never engages because no `RateLimitExit` is raised. I cannot verify the installed CLI's exact text from here, which is why this is Important and not Critical; rung 0 (about 60 calls) is unlikely to hit a limit, rungs 1 and 2 (1,300 and 1,900 calls) will.
Fix: widen the pattern with `\bhit your limit\b|\blimit reached\b|\blimit will reset\b|\bresets? at\b|\busage limit\b` (word-bounded); and take the Task 3 M5 deferred minor with it: on an `is_error` result test `_LOGIN` before `_RATE_LIMIT` (a login text never says "usage limit", but one may say "try again"). Add a fixture line for each known wording to `tests/test_providers_claude_code.py`. The runbook's rung 0 report should record the exact text of any limit the ladder meets, so the pattern is pinned to reality once.

**I2. A rate limit inside the run-time judge-side passes is swallowed into a degraded record; the run neither pauses nor waits, and resume does not redo it.**
`claude_bully/planner/llm_lint.py:196-197` (`except ProviderError` -> `error` verdict); `claude_bully/environments/harvest.py:717` (`except (ProviderError, ValueError)` -> `HarvestFallbackError`); `claude_bully/environments/idle.py:754`; `claude_bully/environments/runtime.py:1387` (`trigger_fallback`); `claude_bully/environments/generator.py:773` (the writer: `except ProviderError` -> a fire `error`). `RateLimitError` is a `ProviderError` subclass, so all five catch it.
What is wrong: spec section 9 says a `RateLimitError` writes a pause marker and `--wait-on-rate-limit` waits it out; the Task 6 I1 ruling made the analysis-time fallback propagate it for exactly this reason. At run time the judge's role makes four other kinds of call (the LLM lint, the harvest LLM pass, the trigger fallback, the idle fallback) plus the generator's own, and in every one a limit becomes a lesser record: an `error` lint verdict that rejects a good document and spends the one retry (which is also limited, so the fire ends `error`), `harvest_degraded`, a heuristic idle label with `fallback_failed`, a heuristic-only trigger watch. The ledger shows `rate_limit` lines, but the pause comes only when the next target or bully call hits the same limit; on resume that turn is redone, the after-turn work of the already-written turns is not (it was "done"). Under a window at rung 1b the generator cell silently loses its fires and the harvest its items, and the rung report would read that as the model's behaviour. The runbook's rung 0 checklist (`phase-7-runbook.md:240`) looks for `error` and `timeout` lines and would not flag `rate_limit` lines either.
Fix (minimum, in the wave): `except RateLimitError: raise` ahead of the `ProviderError` clause in the five sites; in `runner._call_target` (`runner.py:378-404`) and `_bully_turn`, extend the `except RateLimitError -> _pause_for_rate_limit` to cover `_idle_info` and `env.after_target_turn` (the after-turn roles already name their own turn in the attempt marker and are re-watched on resume, `runtime.py:225-226`, so a pause there resumes correctly; the marker is written after the reply, which `is_pause_marker` readers already skip). Add a run-level test: a judge double rate-limited inside the lint (and one inside the harvest pass) pauses the run with one marker and one `rate_limit` line. Runbook :240 gains "no `rate_limit` line either" at rung 0. If the controller scopes the runner plumbing out of the wave, the five re-raises still must not land alone (an uncaught `RateLimitError` out of `after_target_turn` would crash the run with no marker); then the whole item waits and the runbook says at :240 and :262 that a `rate_limit` line on a judge-role call is a stop.

**I3. The lint probe's real calls are not ledgered.**
`scripts/llm_lint_probe.py:131-141` (`_lint` builds through `build_provider` with no ledger active).
What is wrong: rung 1b runs the probe twice (70 items, then `--stances`) on the real judge, and the runbook counts them in "about 1,300 calls with the measurements" and asks the rung report for a Calls table; those calls leave no `LedgerLine` anywhere, so the report's tally cannot include them and a limit inside the probe is invisible except as a traceback. Spec section 4 wants one line per provider call.
Fix: `with activate(Path(args.state) / LEDGER_FILE)` around `score`/`_stances`, and print the ledger's `calls_line` at the end; the runbook's 1b block names the ledger path. Four lines.

#### Minor (Nice to Have)

**M1.** `claude_bully/analysis/run_analysis.py:1`: the module docstring says "The judge is the only model call"; the authority fallback is a second. Stale since Task 6.

**M2.** Analysis-time `cached` lines are appended to the run's `ledger.jsonl` (`metrics/judge.py:198`, `authority_fallback.py:91`), so `ledger.json`'s `cached` counts and the Calls line grow with every `analyze`, and `analyze --no-judge --authority-fallback` on a promoted run mutates the committed `results/<run>/ledger.jsonl`. Documented in docs/00 E (Task 2's deferred sentence), and `calls` (made) is stable, so the headline number holds; but a reader of a promoted run cannot tell run-time from analysis-time lines without the `ts`. Consider writing analysis-time lines to `analysis/ledger.jsonl`, or giving the Calls line the run-time made count only.

**M3.** The fallback's lines are `judge` lines (`judge/authority/<digest>`), indistinguishable in `ledger.json` from the pair judge's; the runbook's "fallback audit (about 100 calls)" can be read off conversation ids only. The spec's section 4 role list has no fallback role, so this is per spec; an additive `authority_fallback` role word would cost one `_ROLE_WORDS` entry.

**M4.** `claude_bully/environments/triggers.py:647-650` and `environments/idle.py:709-713`: the trigger key has no version and no model, the idle key no model, while docs/00 section H (the new "Cache homes" paragraph) says "every key includes the role's model and a version constant". This is the Task 4 M7 half of the pre-ruled atomic bundle; the sentence is true once it lands (scoped below). Until then the runbook's "move `runs/_cache/` aside before rung 0" is the right precaution.

**M5.** `claude_bully/runner/env_turn.py:614-624`: the server ledger is folded only in `_recover`, after a successful target call. A rep whose target call raises a `ProviderError` (aborted) leaves its responder lines in `state/<cell>/rep<k>/mcp/ledger.jsonl`, which `promote` does not copy; a rate-limited call's lines are folded by the next successful call, so only aborted reps under-count. A `finally` fold in `call_target`, or a fold at rep end, closes it.

**M6.** `claude_bully/doctor.py:154-159` and :283-296: `_check_login` and `_check_effort` build the same ping call; one `_ping(command, state, **kwargs)` would do. `_check_disk` reads `.gitignore` as exact lines (deferred, stands).

**M7.** `claude_bully/providers/ledger.py:193-206`: the wrapper's docstring could say that `isinstance(provider, ClaudeCodeProvider)` is false for a wrapped provider and that readers must go through attributes (as every caller does today); the seam is silent otherwise.

**M8.** HANDOFF Progress items 5 and 6 state `LINT_PROMPT_VERSION 1` and `AUTHORITY_FALLBACK_VERSION 1` in their main sentence and the bump to 2 only in the fix-round sentence; a reader on another machine may take the first value. Say "now 2" at the first mention.

**M9.** `claude_bully/metrics/events/authority.py` is 1,334 lines (from about 1,260): the asker moved out (M3 ruling) but the module gained `_fallback_events` and `TEXT_EVENTS` plumbing. At the edge of the Phase 3 size rulings; Phase 4's twelve detectors should not land in it.

**M10.** `docs/handoff/phase-7-runbook.md:230-231` is an unwrapped line (ledger L61); :240 should name `rate_limit` lines (folded into I2).

**M11.** `claude_bully/runner/wait.py:39-42`: the "rate limited (...)" message prints the exception text, which for a toolless non-zero exit is up to 500 characters of claude's stdout and stderr; harmless, but a `[:120]` would keep the console line to one line.

**M12.** `tests/test_ladder_configs.py:207` asserts `cls.name` is truthy, which every strategy class satisfies; the test's weight is in the stage sum and the cell count, so this line is decoration.

### Deferred minors triage

**Fix before rung 0 (1):**
- Task 3 M5 (ledger L20): the rate-limit check runs before the login check and "try again" is broad. Rides with I1 (login first on `is_error` results, pattern widened) since the same lines change.

**Can wait (all others):**
- L15 Task 2 test gaps (`by_model`, roles outside `ROLES`, no `ledger.json` after a no-ledger analyze, promote with no ledger): coverage only; no 7b path depends on them.
- L20 Task 3 M1 (`resolved_model` falls back to the result's own `model`): every real result carries `modelUsage`; the fallback is a label.
- L22 Task 3 (`_LOGIN` on model text on a toolless non-zero exit; exit-1 login untested with tools; bool as int): a non-zero exit is already a failure; the label may be wrong, never the outcome.
- L24 Task 4 M9 (`.gitignore` exact match), M10 (the fake cannot show the strip), M12 (filled).
- L25 Task 4 (`--out` with a foreign `ledger.jsonl` is unlinked; check 7 with no ledger active; the unreachable `mcp_dir is None` branch): the runbook uses a fresh dated folder and the CLI always activates.
- L31 Task 5 M6 coverage gaps.
- L39 Task 6 trivial `first.exists()` assert.
- L44 Task 7 M7 (multi-line replay text), M8 (literal-based guard), M10 (coverage), M12 (A is always the condition, documented): no module parses replay text in 7b.
- L47 Task 7 (a missing key sidecar is an uncaught `FileNotFoundError`; `--pairs --idle` together; a rubric line with no slot; the harvest test uses `runs_generator` itself): a traceback is loud, the runbook never combines the two flags.
- L51 Task 8 (relpath asymmetry and the cross-drive case, which already raises `BadParameter`; HANDOFF's present-tense `plan`).
- L55 Task 9 (`run --only` matching nothing runs zero cells silently): first used at rung 2; a `typer.BadParameter` when the glob selects no cell is about five lines and a good wave rider, but not a rung 0 blocker.
- L61 Task 10 (runbook :230-231 wrap; HANDOFF:5 wording): docs polish; M10 above.

### Declined to judge

Each considered and set aside as outside the plan or spec, or already ruled; the controller rules on each.

- `display_name: Claude` in every new config: the one real name a target may be called (docs/00 G11), pre-existing in every shipped config, spared by `promote`.
- `resolved_model` in a promoted run's `ledger.jsonl` is a real model id (the target's, the bully's and the judge's): non-negotiable 2's exception for "the target's own API string"; the bully and judge are the same vendor's models and the runbook already says `ledger.json` groups by alias. The spec's section 10 copies the ledger knowingly.
- Doctor check 4 requires interim text (`doctor.py:217`, `ok = bool(lines) and interim > 0`): the spec's own pass condition; a real model that calls the tool without the requested sentence fails the check and the doctor is rerun. By design.
- Check 7 proves only that the CLI accepts `--effort low` and the line records it (the Task 4 M3 ruling, "the flag in the ledger line"); whether effort changes the reply is unmeasured. Per the ruling.
- Whether the installed Claude Code honours `MCP_TOOL_TIMEOUT` and `--effort`: verifiable only by `doctor --live` checks 5 and 7, which is what they are for.
- `anthropic`/`openai` as module names in `tests/conftest.py` and the API-key env names in `cli.py`: backend identifiers, pre-existing, not names in the non-negotiable's sense.
- The `_LOGIN` pattern's breadth (`\blog ?in\b`): deferred minor L22, stands.
- The `claude -p` session transcripts written under the user's `~/.claude/projects/` by `--session-id`: pre-existing Phase 1 behaviour, outside this plan.
- HANDOFF's gate count (8354 passed, 5 skipped, 8 deselected, 8 slow): not re-run here (the brief forbids the full suite); the Task 10 implementer's figure stands.
- The Phase 3 passes' choice to record a degraded result on any `ProviderError` (`harvest_degraded`, `fallback_failed`): Phase 3's design, not re-judged; I2 is only about the `RateLimitError` subclass, which Phase 7's spec treats differently.
- The analysis-time ledger growth (M2) as a design: docs/00 E documents it; raised as Minor only.
- The reflexive generator stub-run test marked slow (P27 ruling) and the two-target `--only` pin: rulings stand.
- `test_kindness_runs_at_three_reps` pins one integer: a config pin, which is what the task asked.

### Fix-wave scope

In priority order, one dispatch:

1. **I1**: widen `_RATE_LIMIT` (`providers/claude_code.py:49`), check `_LOGIN` before `_RATE_LIMIT` on `is_error` results (Task 3 M5 rides), fixture lines for each known limit wording; the runbook's rung 0 report records any limit's exact text.
2. **I2**: `except RateLimitError: raise` in `planner/llm_lint.py:196`, `environments/harvest.py:717`, `environments/idle.py:754`, `environments/runtime.py:1387`, `environments/generator.py:773`; `runner._call_target` and `_bully_turn` pause on a `RateLimitError` from `_idle_info` and `env.after_target_turn` too; one run-level test per the lint and the harvest pass; runbook :240 and :262 name `rate_limit` lines. (If the runner plumbing is scoped out, the five re-raises must be scoped out with it.)
3. **The `claude_bully/atomic.py` bundle (pre-ruled)**: a stdlib-only leaf module with `write_atomic(path: Path, text: str)` (mkstemp in `path.parent`, write, `replace` with the twenty-try `PermissionError` loop, and the temp file unlinked on *any* failure, closing `JudgeCache.put`'s `.tmp` leak) and `replace(tmp, path)`; `runtime._write_atomic` (`runtime.py:437`), `mcp_server._replace` (`mcp_server.py:144`) and `JudgeCache.put` (`judge.py:117-131`) call it. With Task 4 M7: `triggers.fallback_digest` folds in a `TRIGGER_PROMPT_VERSION` and the judge model (the watcher already receives `cache_model`; `trigger_fallback`'s conversation id and the cache key move together), `idle.fallback_key` folds in the model (`idle_fallback` receives `getattr(provider, "model", "")` already); docs/00 H's "every key" sentence is then true. Tests: the three writers through one module, a non-`PermissionError` failure leaves no `.tmp`, a key changes with the model.
4. **Task 8 m1 (pre-ruled)**: `analysis/generator.py:arm_rates` groups by `(model, condition, arm)`; `generator.json`'s `arms` keeps its `model -> arm` shape for the shipped one-condition-per-arm configs and gains the condition name on each entry (or nests `model -> condition -> arm`; additive either way); `generator_arms.png` labels bars by condition where two share an arm; a test with two conditions in one arm.
5. **The generator's rejection rate per kind (pre-ruled)**: `write_generator` reads each kept conversation's `GeneratorFire` records and adds, per model and arm, `fires`, `written`, `cached`, `rejected: {cap, contract, lints}`, `errors`, and `llm_lint: {fail, error}` (from `GeneratorFire.llm_lint`), beside `docs_written`; additive keys; the runbook's rung 3 stop rule then reads them instead of the raw records.
6. **I3**: the lint probe activates a ledger under `--state` and prints the calls line; the runbook's 1b block names it.
7. **Minor riders** (cheap, same files): M1 docstring, M8 HANDOFF "now 2", M10 runbook wrap, M4 docs/00 sentence (true after item 3), L55's `--only` matching nothing as a `BadParameter`, M5's fold on an aborted rep if the implementer is in `call_target` anyway.

Docs-sync for the wave: the spec's "As planned" gains a "Final review" block (I1, I2, the bundle, m1, the rejection counts), docs/00 H lists the `generator.json` additions as version 3 additive, HANDOFF's "Parked, and must land before Phase 7" closes.

### Assessment

**Ready: With fixes.** The build does what the spec and plan asked: the ledger, the lint, the fallback, the doctor, the forms, the wait, the promote policy, the configs and the runbook are coherent across the ten tasks, every non-negotiable holds across the diff, and resume and replay rebuild on each new stream. Two things would mislead the first real runs rather than break rung 0: a rate limit that the classifier does not recognise aborts reps a resume then skips (I1), and a rate limit inside any run-time judge-side pass is recorded as the model's behaviour instead of pausing (I2); both are small, both belong in the wave with the three pre-ruled items, and rung 0 should not start before they land.
