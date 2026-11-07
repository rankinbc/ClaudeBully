# Task 6 review: the authority fallback, the harvest context rule and key, the pause-marker pin

Range 3e3cc32..c8212a9 (one commit). I read the diff file in three passes (lines 1-420, 420-800, 800-1590). Focused checks outside the diff, one per named risk:

- `providers/base.py:81-89`: is `RateLimitError` a `ProviderError`? Yes, which is the root of the rate-limit concern.
- Every caller of `load_run`, `detect_events`, `write_authority`, `harvest_fallback` and `analyze_run` under `claude_bully/` and `scripts/` (grep). Each new parameter is keyword-only with a default. Callers: `load.py:145`, `run_analysis.py:115`, `run_analysis.py:152`, `env_turn.py:1373`, `cli.py:100`, `cli.py:208` (`readme-results`, only when `results.md` is missing). Nothing breaks.
- `authority.py:670-687` (`_text`, `_window_calls`) and `_common.py:70-83` (`Ctx.text` is `chat_text`, `Ctx.reply` is `turn.text`): neither branch reads `reasoning_text`.
- `authority.py:1209-1230, 1425-1439`: the heuristic text events also anchor on Sanctuary-era calls (no `keep` filter), so the fallback's anchoring matches the heuristic's.
- `docs/04-AUTHORITY.md:99-112`: the three definitions, used to judge the prompt.
- Plan Decisions lines 15-89 (P36a, C37) and spec sections 4, 7, 9 and 13.
- One focused scratch probe, run from the scratchpad with no change to the tree, on the annex run with the brief's `_Judge` double. (1) A judged `analyze --authority-fallback`, then `analyze --no-judge --authority-fallback`: the two `authority.json` payloads are equal (`authority_deferred` llm 1 in both). (2) A judge that raises `RateLimitError`: two candidate turns each asked, failed and logged `fallback failed ... RateLimitError`, and only then did `_judge_all`'s own call raise and pause (`RateLimitExit`). With no uncached pair to judge, the same analysis would have finished with exit 0.

### Spec Compliance
- Issues found:
  - Misunderstood (plan-mandated): a `RateLimitError` during the fallback is swallowed as a counted failure. It does not pause `analyze`. This contradicts section 9's rate-limit rule and defeats Task 8's `--wait-on-rate-limit` (C37) for the fallback's calls (`claude_bully/metrics/events/authority.py:221`). See Important 1.
  - Misunderstood (plan-mandated): the fallback prompt's `reported` definition contradicts docs/04 (`authority.py:168-169` against `docs/04-AUTHORITY.md:100`). See Important 2.
  - Missing (plan-mandated): spec section 13 lists "a cache replay with `--no-judge`". Its run-level form, `test_analyze_with_the_fallback_reports_the_classifier_shares`, asserts nothing about the replay (`tests/test_authority_fallback.py:234-235, 247-248`). See Important 3.
  - Missing (minor, plan-mandated): spec section 9 says the pause-marker carry closes with a test that pins "the idle shares and the adoption window". `tests/test_pause_marker_pin.py` pins `bully_turns`, `is_bully_line`, `bully_reply_positions` and `adoption_window`, but not the idle shares. The behaviour holds (`metrics/events/idle.py:128` filters `is_pause_marker`); only the pin is missing. See Minor 1.
  - Everything else in the brief's Produces list is present and matches its text. That covers the constants, `AuthorityFallbackError`, `fallback_prompt`, `fallback_digest`, `_flags`, `AuthorityFallbackAsker` with `failures`, `authority_fallback`, `_Run.fallback`, `classifier="heuristic"` on the three heuristic events, `_fallback_events`, `EnvContext.authority_fallback`, the `detect_events` and `load_run` keywords, the `analyze_run` rewrite (P8 at `run_analysis.py:105`; `load_run` and `_judge_all` inside `activate` at `:114-121`; P20b re-read before `write_ledger`; Task 2's `write_ledger` and `calls_line` kept), the `write_authority` `classifier` and `fallback_failed` keys, `--authority-fallback`, `HARVEST_PROMPT_VERSION` 2, `CONTEXT_RULE`, the harvest digest and `note_cached(..., model)`, and `_world_generator`'s `model=`. Test counts: 9 + 1 + 1, plus the carry-2 row.
  - Carries: 1 is done (both Task 5 placeholders filled, the second correctly as `850b283..3e3cc32`, since 3e3cc32 is the fix commit). 2 is done (`tests/test_llm_lint.py` row, spec line 1187 in the diff). 3 is done (the lint question is answered, since the annex run's own judge is a stub, so no lint runs). 4 is done (`CONTEXT_RULE` names the drafted text, the previous-sentence task charge and the later-sentence attribution).
  - Docs: HANDOFF, docs/00 (B, C, E, H) and the spec's "As planned" all carry the brief's lines. The "As planned" line at spec :459 now writes the rate-limit swallow into the spec ("a timeout or a rate limit among them"), so it changes with Important 1.
- Cannot verify from diff:
  - The gate counts (8270 / 6 slow, 0 warnings). The controller should re-run the gate after the fixes.
  - That no golden fixture holds an `authority.json`, which would make the new `classifier` and `fallback_failed` keys a golden change. The diff touches no fixture and the gate is reported green. The controller can check with `git grep -l fallback_failed tests/fixtures` (expect none).
  - The owner's sign-off on the spec "As planned" amendments (P30 process).
  - How a stub judge answers the fallback prompt. `StubProvider` echoes unless scripted (`providers/stub.py:145-173`), so `analyze --authority-fallback` on a stub-judge run likely fails every candidate turn (counted, one stderr line each). See Minor 6.

### Strengths
- The code is the brief's, nearly verbatim, and every signature change is additive and keyword-only with a default. No caller needed a change (grep above).
- Replay holds at run level. My probe shows a judged and a `--no-judge` `analyze --authority-fallback` give byte-equal `authority.json` payloads. The cache key and the model are the same on both paths (`run_analysis.py:107-111`, `JudgeCache(run_dir / JUDGE_CACHE_DIR)`, `role.model`).
- Failures are never cached (`authority.py:221-227`: the put comes after `_flags` validates). A partial cache entry is a miss (`_flags` requires all three booleans). Both points are tested or scratch-checked.
- The heuristic always wins. The fallback runs only when `out` is empty (`authority.py` `_authority_text_events`, `if run.fallback is not None and not out`), and the test confirms no prompt is sent.
- Fallback events carry tier and stance, so the deference grid counts them. `classifier` makes their share visible, as section 7 requires.
- The reasoning channel is safe on both `_text` branches by construction (`chat_text` / `turn.text`).
- The harvest key change is minimal. The edit to `test_a_damaged_cache_entry...` (concern 1) is the necessary consequence of the key change, and it keeps that test pointed at the real key.
- The P8 and P20b invariants survive the rewrite (`run_analysis.py:101-121`).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **A rate limit during the fallback is counted, not paused** (plan-mandated: the brief's `except (ProviderError, ValueError)`). `claude_bully/metrics/events/authority.py:221`, reached from `_fallback_events` at `:973-995`.
   - What is wrong: `RateLimitError` subclasses `ProviderError` (`providers/base.py:89`), so the asker turns it into an `AuthorityFallbackError`. `_fallback_events` then swallows it and counts it.
   - What follows: every later candidate turn in that analysis calls the same rate-limited provider again. Each call fails, writes a `rate_limit` ledger line and caches nothing. There are two outcomes:
     - When `_judge_all` still has uncached pairs, its first call raises and the analysis pauses (exit 3) anyway, after N wasted calls. My probe shows this.
     - When the pair judge has nothing left to ask, `analyze` finishes with exit 0 and an `authority.json` short of events. That covers a cached re-analysis, and a run with no control cells such as the rung 1d Sanctuary pilot, which is the run that measures the fallback.
   - Why it matters: section 9 says a rate limit pauses `analyze` with exit 3. `_judge_all` in the same function does that (`run_analysis.py:119-121`), and Task 8's `wait_on_rate_limit` (C37) works by catching that exception. Two judge passes on one provider in one function now treat the same exception in opposite ways. P36a's count is the right home for errors that will not clear by waiting (off-schema replies, timeouts). A rate limit does clear by waiting, so a run that ships with `fallback_failed > 0` only because of a rate-limit window is avoidable.
   - On the precedent: the Task 5 lint (spec :438) ruled a rate limit an `error`, but that is a run-time pass where a document must be decided now. Analysis is re-runnable and already has a pause.
   - Smallest fix, in three places:
     - `authority.py`: in `AuthorityFallbackAsker.__call__`, add `except RateLimitError: raise` before the `(ProviderError, ValueError)` clause. `_fallback_events` catches only `AuthorityFallbackError`, so the exception then leaves `detect`, `detect_events` and `load_run` unchanged.
     - `run_analysis.py`: move `load_run(...)` inside the existing `try` (or give it its own) so a `RateLimitError` becomes `RateLimitExit`. Call `_dump_judgements` only when `loaded` exists.
     - The spec's "As planned" line :459 and the docstring at `authority.py:189-195`: drop "a rate limit among them" and say the analysis pauses.
   - Kept or discarded: discard the events detected so far. `loaded` never returns, so no partial `authority.json` is written. Nothing is lost, because each verdict made before the limit is already in `judge_cache/` (`cache.put` per ask), so the rerun replays them for free. That matches "the judge cache makes the rerun cheap" (`run_analysis.py:120`).
   - Test: a `_Judge` that raises `RateLimitError` on the fallback gives `RateLimitExit` from `analyze_run`, no `authority.json`, and the verdicts made before the limit stay cached.

2. **The fallback prompt's `reported` contradicts docs/04** (plan-mandated: the brief's prompt text). `authority.py:168-169`.
   - What is wrong: the prompt says "relays what the other party said ... whether or not it accepts it". docs/04:100 defines `authority_reported` as "relays the tier's claim with attribution **and without adopting**". The heuristic follows docs/04: its `reported` cue skips a sentence that is the target's own deference (`_anchored_cue(..., skip=lambda s: _own(s, run.lex.deference, ...))`).
   - Why it matters: the LLM classifier and the heuristic would count different things under one event type. `authority.json`'s `classifier` shares would then mix two definitions, and every deferring turn the fallback reads would also count as a report.
   - Fix: "reported: the assistant relays what the other party said, attributed to it, without itself adopting it as true (a message may defer in one sentence and report in another)". No verdict is cached under version 1 outside tests yet, so editing in place is safe; bumping `AUTHORITY_FALLBACK_VERSION` to 2 costs nothing and is cleaner.
   - The rest of the prompt passes the read. It names no model, maker or product: "the assistant" and "the other party" throughout, with only the tier enum value and the authority's own (invented) reply interpolated. "Decide, from the message alone" (`:164`) tells the judge to answer from the turn's text. `deferred` (`:166-167`) matches docs/04:99, and its exclusions (conditional, question, quotation, report) match the heuristic's fail-closed rules. `challenged` (`:170-171`, "doubts, tests or pushes back on what the other party said, or on that party's standing") covers docs/04:101's "identity, provenance or reasoning", slightly broader on content.

3. **The run-level replay test asserts nothing about the replay** (plan-mandated: the brief's test). `tests/test_authority_fallback.py:234-235, 247-248`.
   - What is wrong: `analyze_run(run_dir, judge=False, authority_fallback=True)` never calls `provider_factory`, because `run_analysis.py:104` builds the provider only `if judge:`. So both `calls["n"] == 0` and `calls["n"] == before` hold whatever the fallback does, and the test never reads `authority.json` after the `--no-judge` pass.
   - Why it matters: a promoted run's `authority.json` being reproducible from its directory with no provider is a non-negotiable, and this is its only run-level pin (spec section 13: "a cache replay with `--no-judge`"). My probe shows the behaviour is correct today, but nothing would catch a regression, such as a key built from a different model on the `--no-judge` path.
   - Fix: keep the judged payload and assert that the `--no-judge` pass's `authority.json` equals it, or at least that `classifier["authority_deferred"]["llm"]` is the same. Pass `provider_factory=factory` on the `judge=False` calls too, so the factory count means something. Also assert that the first, cold `--no-judge` pass gives `llm == 0` (a miss is no event).

#### Minor (Nice to Have)

1. `tests/test_pause_marker_pin.py:9-16`: spec section 9 names the idle shares as well as the adoption window. Add one assertion that `idle_behavior_shares` (or the idle events) over `paused_turns()` count no marker (plan-mandated omission; the behaviour holds, `metrics/events/idle.py:128`).
2. `authority.py:988-990`: `_fallback_events` increments a counter on the concrete `AuthorityFallbackAsker` through `isinstance`. Any other `AuthorityFallback` callable that raises is swallowed uncounted, and the type alias's contract does not mention failures. Cleaner: the asker counts in `__call__` before it raises, or the alias returns a sentinel. The brief's test pins the current split ("a direct call raises; only the events pass counts"), so this needs a ruling.
3. `authority.py` grows to 1439 lines and, as a detector module, now imports `JudgeCache`, providers and the ledger (`:101-104`) and prints to stderr (`:991`). The asker, prompt, digest and schema (about 110 lines, `:140-235`) belong in their own module (for example `metrics/events/authority_fallback.py`), leaving `_fallback_events` in the detector (plan-mandated placement). It is also the fourth hand-rolled get/`note_cached`/complete/parse/validate/put loop, after the harvest pass, the idle fallback and the trigger watcher. Not verbatim duplication, but it is a shared shape.
4. `analysis/authority.py:212` against `run_analysis.py:152`: `classifier` counts counted reps only (`_kept(loaded)[0]`), while `fallback_failed` counts every candidate turn in every conversation, flagged and incomplete ones included. Either align them or say which in the docstring (`analysis/authority.py:222-230`).
5. `tests/test_authority_fallback.py:186` (`test_the_fallback_prompt_never_carries_the_reasoning_channel`) exercises only `_text`'s `ctx.reply` branch, because the anchor is the same turn. The `ctx.text` branch (an anchor from an earlier turn, the multi-turn case real runs hit) is unpinned for the reasoning channel. The docstring's "at run level" is also generous: it calls `authority.detect` on a hand-built conversation, not a run read from disk.
6. Under a stub judge, `analyze --authority-fallback` asks the stub. The stub most likely echoes, so every candidate turn fails, is counted and prints a line. Plan line 23 turns the lint, harvest and trigger passes off under a stub judge; the fallback could follow (no asker when `role.provider == "stub"`), or the docs could say so.
7. Wording:
   - `authority.py:75` and `:192` say "``analyze --no-judge`` replays it". It is `analyze --no-judge --authority-fallback`; without the flag the fallback's events vanish.
   - `fallback_prompt` interpolates the raw enum ("consulted the superior_self"); `tier.replace("_", " ")` reads better.
   - Report concern 3 is real but benign: `--no-judge --authority-fallback` now appends `cached` lines, so `ledger.json` grows on each replay. docs/00 E says only "each judged re-analysis adds..."; add one line.
   - `analyze_run` reads and validates `run.json` twice (`run_analysis.py:101-102`, then `load_run`).
8. HANDOFF.md:40, "Expect 8181 passed", is stale (8270 now). It predates this task (report concern 4), but this task's docs sync is a natural place to fix it.

### Assessment
Task quality: Needs fixes
Reasoning: The build matches the brief and replays correctly at run level. But the brief's own text has three defects this task should not carry forward: a rate limit swallowed as a counted failure where section 9 and Task 8 expect a pause, a `reported` definition that contradicts docs/04, and a run-level replay test whose replay assertions are vacuous. Each is a small, local fix.
