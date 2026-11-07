# Task 6 report: the authority fallback, the harvest prompt context and key, the pause-marker pin

Status: DONE. Commit c8212a9 on build/v1 (BASE 3e3cc32). One commit, carries included, not pushed.

## What was implemented

- `metrics/events/_common.py`: `AuthorityFallback` type alias; `EnvContext.authority_fallback` (default None).
- `metrics/events/__init__.py`: `detect_events(..., authority_fallback=None)` passes it into `EnvContext`; the docstring line was added.
- `metrics/events/authority.py`: the brief's constants (`FALLBACK_CONFIDENCE` 0.6, `AUTHORITY_FALLBACK_VERSION` 1, header, system, `FALLBACK_FLAGS`, schema), `AuthorityFallbackError`, `fallback_prompt`, `fallback_digest`, `_flags`, `AuthorityFallbackAsker` (with `failures`), `authority_fallback(...)`, `_Run.fallback`, `classifier="heuristic"` on the three heuristic text events, and `_fallback_events`, which runs only when no text event fired on the turn. The module docstring paragraph was added. Code is verbatim from the brief, with only formatter wrapping.
- `analysis/load.py`: `load_run(run_dir, *, authority_fallback=None)` passes it to every `detect_events` call.
- `analysis/run_analysis.py`: `analyze_run(..., authority_fallback=False)` rewritten as the brief says. The experiment is read from `RunStore`. The judge provider is built inside `activate(...)` (P8). `load_run` and `_judge_all` run inside a second activation of the same path. The ledger is re-read before `write_ledger` (P20b). Task 2's `write_ledger` and `calls_line` are kept. `write_authority` gets `fallback.failures`.
- `analysis/authority.py`: `TEXT_EVENTS`, `_classifier_shares`, `write_authority(..., fallback_failed=0)`. The payload gains `classifier` and `fallback_failed` after `lineage_appeal_accepted`, and the docstring covers both.
- `cli.py`: `analyze --authority-fallback` (checked in `--help`).
- `environments/harvest.py`: `HARVEST_PROMPT_VERSION` 2 and `CONTEXT_RULE`, placed after `OWNERSHIP_RULE` in `harvest_prompt`. `harvest_fallback(..., *, model="")` uses the digest `sha256(f"{HARVEST_PROMPT_VERSION}\0{model}\0{text}")`, and the cached note now uses `model`.
- `runner/env_turn.py`: `_world_generator` passes `model=self.exp.judge.model`.
- Docs:
  - HANDOFF.md: header and Next steps now say Tasks 1 to 6 are done and Task 7 is next; Progress item 6 added. In "For Phase 7", the authority paragraph now describes the built fallback and the 7b rung 1d switch, and the harvest residual gains `CONTEXT_RULE`, version 2 and the judge model in the key ("7b rung 1b measures"). The pause-marker item is replaced by its closed line, and the Task 4 cache-key minor is marked closed.
  - docs/00-RECONCILED.md: B's HarvestItem row (the key rule), C's `04` bullet (the fallback), E (`--authority-fallback`), and H's Phase 7a additive line (`Event.attrs["classifier"]`, and `classifier` and `fallback_failed` in `authority.json`).
  - The spec's "As planned": a Task 6 entry with the six rulings, plus the carry-2 bullet in the Task 5 review list.

Carries:
1. HANDOFF Task 5 range `a40dc62..Task 5 commit` became `a40dc62..3e3cc32`. I also filled the second placeholder in the same entry, the fix round's `850b283..Task 5 fix commit`, as `850b283..3e3cc32`, since 3e3cc32 is that fix commit. My own entry uses `3e3cc32..Task 6 commit`.
2. `tests/test_llm_lint.py` gains one row in `test_parse_verdict_holds_the_reply_to_the_contract`: a fenced reply with prose after the closing fence gives `"not JSON"`. The spec's Task 5 "As planned" review list gains one bullet saying so. The lint itself is unchanged.
3. The facts from Tasks 1 to 5 were followed:
   - `note_cached(conv, model)` is used throughout.
   - P8 and P20b are kept in the rewrite.
   - `ProviderTimeoutError` is a `ProviderError`, so the asker turns it into a counted `AuthorityFallbackError`.
   - `GeneratorFire.llm_lint` is untouched.
   - Lint question: the `_Judge` double only serves `analyze_run` (its `provider_factory`). The annex run itself runs on `annex_experiment`'s stub judge (`provider: stub`), so `RunEnvironments.judge()` is None, no LLM lint runs, and the annex config has no generator cell. `LintJudge` was not needed.
4. The brief's `CONTEXT_RULE` names all three cases: a drafted greeting or composed reply, a test charge set up by the previous sentence, and a later-sentence attribution. Nothing was added.

## Tests and results (the gate, on the final tree)

- `uv run ruff format --check .`: 264 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 107 source files
- `uv run pytest -q -W error`: 8270 passed, 5 skipped, 6 deselected in 455.46s. BASE was 8258; the +12 are 9 fallback tests, 1 pause-marker pin, 1 harvest test and 1 lint row. 0 warnings.
- `uv run pytest -q -m slow -W error`: 6 passed, 8275 deselected

## TDD evidence

RED, after pasting the brief's three test blocks and the carry-2 row:
- `uv run pytest tests/test_authority_fallback.py ... -q` failed at collection with `ImportError: cannot import name 'AUTHORITY_FALLBACK_HEADER' from 'claude_bully.metrics.events.authority'`. Expected: the module had no fallback yet.
- `uv run pytest tests/test_pause_marker_pin.py tests/test_harvest.py tests/test_llm_lint.py -q` gave `1 failed, 401 passed`. The failure was `test_the_llm_pass_key_holds_the_prompt_version_and_the_judge_model` with `ImportError: cannot import name 'HARVEST_PROMPT_VERSION'`. As the brief expects, the pause-marker pin passed at HEAD. The lint row also passed at HEAD, since it pins existing behaviour.

GREEN:
- `uv run pytest tests/test_authority_fallback.py tests/test_pause_marker_pin.py tests/test_harvest.py tests/test_authority.py tests/test_env_events.py tests/test_phase2_charts.py tests/test_generator_run.py tests/test_run_analysis.py tests/test_cli.py tests/test_llm_lint.py -q -W error` gave `563 passed, 1 deselected`. No existing authority test compared whole `Event` objects, so no expected attrs needed extending.

## Files changed

- claude_bully/metrics/events/_common.py, claude_bully/metrics/events/__init__.py, claude_bully/metrics/events/authority.py
- claude_bully/analysis/load.py, claude_bully/analysis/run_analysis.py, claude_bully/analysis/authority.py
- claude_bully/cli.py, claude_bully/environments/harvest.py, claude_bully/runner/env_turn.py
- tests/test_authority_fallback.py (new, 9 tests), tests/test_pause_marker_pin.py (new, 1 test), tests/test_harvest.py (1 appended, 1 edited, see below), tests/test_llm_lint.py (1 row)
- HANDOFF.md, docs/00-RECONCILED.md, docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md

## Self-review

Edge cases, each checked by a test or by a scratch script against the real code:
- A candidate turn with no call in its window gets no ask and no event (`test_a_turn_with_no_authority_call_in_reach_is_not_a_candidate`).
- A judge that errors once: no event, nothing cached, `failures == 1` (test). Scratch check: a later pass with a working judge re-asks and gets the event.
- A cache entry holding only one flag, e.g. `{"deferred": true}`, is a miss because `_flags` needs all three booleans. With no provider there is no event; with a judge it is re-asked once and the entry is overwritten (scratch check).
- `--no-judge` without `--authority-fallback`: no asker, heuristics only, every text event `classifier: heuristic`, `fallback_failed` 0. With `--authority-fallback` it is cache-only (`test_analyze_with_the_fallback_reports_the_classifier_shares`: no factory call on a cold or a warm cache).
- A turn where the heuristic fired one of the three flags is not asked (`test_a_heuristic_fire_stands_and_the_fallback_is_not_asked`).
- The reasoning channel is never in the fallback's prompt or cache files (`test_the_fallback_prompt_never_carries_the_reasoning_channel`, run level, P30d). `_text` reads `chat_text`, which leaves out `reasoning_text`.
- Plain runs: `analyze_run` now always opens the activation around `load_run`. With no judge and no fallback nothing writes to it, so no ledger file appears and the golden fixtures are unchanged (the gate passes).

Discipline: nothing beyond the brief. `SCHEMA_VERSION` stays 3, and every addition is a default-valued attr or a JSON key.

## Issues and concerns

1. An existing test, `tests/test_harvest.py::test_a_damaged_cache_entry_is_a_miss_and_the_judge_is_asked_again`, built the old harvest key (`sha256(text)`), so it would have failed under the versioned key. Its key line now uses the new formula (`HARVEST_PROMPT_VERSION`, empty model, text), which keeps it testing a damaged entry at the real key. The brief only says "append" for this file; this one-line adaptation follows from the key change the brief requires.
2. Behaviour to know, as the brief specifies it: `RateLimitError` is a `ProviderError`, so a rate limit during the fallback becomes a counted failure (`fallback_failed`), not a `RateLimitExit` pause. Each later candidate turn in that analysis also asks and fails, and none is cached. A rerun asks those turns again. This is visible in the records (P36a) but costs one failed call per remaining candidate turn. Not changed.
3. With `--no-judge --authority-fallback`, cache hits now write `cached` lines to `ledger.jsonl`, because `load_run` runs inside the activation. That is consistent with "a cache hit is noted by its user" and with the Task 3 re-analysis amendment, but a `--no-judge` analysis can now append to the ledger. Noted, not changed.
4. No brief, spec or code disagreement otherwise. The HANDOFF setup line `Expect 8181 passed` (line 40) was left at its Phase 3 value, as Tasks 1 to 5 left it.

## Fix round 1 (review task-6-review.md): commit e48783f, on top of c8212a9

### What changed, per item

- **Important 1 (a rate limit pauses):**
  - `AuthorityFallbackAsker.__call__` re-raises `RateLimitError` ahead of the `(ProviderError, ValueError)` clause, so a rate limit is never an `AuthorityFallbackError`.
  - `analyze_run` wraps `load_run` in `except RateLimitError` and raises `RateLimitExit`. This is the pair judge's pause: `cli.analyze` exits 3.
  - That pass's events are discarded and no `authority.json` (or anything after it) is written. The verdicts made before the limit stay cached.
  - Spec "As planned": the "failed ask" bullet drops "a rate limit among them", and a new "A rate limit pauses" bullet was added. docs/00 E says the same.
  - Test: `test_a_rate_limit_in_the_fallback_pauses_and_the_rerun_replays_the_cache`. It runs an annex run at turn budget 6 with only the condition cell, giving three candidate turns. The judge rate-limits on the second fallback prompt: `RateLimitExit`, no `authority.json`, one cache entry. The rerun with an answering judge writes exactly one `cached` `judge/authority/...` ledger line, asks the other two, and reports `llm == 3` with `fallback_failed == 0`.
- **Important 2 (`reported` is docs/04's):**
  - The prompt now reads: "relays the other party's answer, attributed to that party, without adopting it (in its own words or quoted). A message can defer in one sentence and report in another."
  - `AUTHORITY_FALLBACK_VERSION` is 2, so the digest changes and no version-1 verdict is reused.
  - Test: `test_the_prompt_defines_reported_as_docs_04_does` pins the wording and the absence of "whether or not it accepts". The digest test now expects version 2.
- **Important 3 (the replay pinned):**
  - `test_analyze_with_the_fallback_reports_the_classifier_shares` passes `provider_factory=_no_provider` (raises if called) on both `--no-judge` passes.
  - It asserts the cold cache-only pass gives `llm == 0`, the judged pass built exactly one provider, and the `--no-judge --authority-fallback` replay's `authority.json` equals the judged one.
  - The run's `run.json` is rewritten to name a non-stub judge (`_judged_by_a_backend`), because of M6.
- **M1:** `test_the_idle_shares_count_no_marker`, in `tests/test_pause_marker_pin.py`. It takes a stub idle run (`env_experiment(idle_turns=1)`) and replaces its pressured conversation with `paused_turns()`. `idle_behavior_shares` then gives that arm `unclassified == 1.0`, and `idle.json` counts `idle_turns == 1` (the one idle turn, no marker).
- **M2:** `AuthorityFallback` is now a `Protocol` with `failures: int` and `__call__`, and `AuthorityFallbackError` lives beside it in `_common.py`. `_fallback_events` increments `fallback.failures` for any fallback, with no `isinstance`.
- **M3:**
  - New module `claude_bully/metrics/events/authority_fallback.py` holds the version, header, system text, flags, schema, `fallback_prompt`, `fallback_digest`, `_flags`, `AuthorityFallbackAsker` and `authority_fallback`.
  - `authority.py` keeps `FALLBACK_CONFIDENCE` and `_fallback_events`. It imports no provider, cache or ledger and prints nothing (the per-turn stderr print is gone). `analyze_run` prints one stderr line with the total when any ask failed.
  - Spec "As planned" gains a "File structure" bullet. The spec has no File Structure section of its own; the plan's is the one being amended.
  - `run_analysis.py` imports from the new module, and the tests import from it and from `_common`.
- **M4:**
  - `load_run` records per-conversation failures in `LoadedRun.fallback_failed` (the protocol's counter, read before and after each `detect_events`).
  - `write_authority` sums them over `_kept` (the counted reps `classifier` uses) and no longer takes a `fallback_failed` keyword.
  - Test: `test_fallback_failed_counts_the_counted_reps_as_classifier_does`. An off-schema judge fails both the condition's and the control's candidate turns (2 asks), and `fallback_failed == 1`.
- **M5:** `test_an_earlier_anchor_reads_the_whole_chat_text_and_still_no_reasoning`. Turn 3's anchor is turn 1's call, so `_text` takes the `ctx.text` branch: turn 3's tool-round text is in its prompt, and its `reasoning_text` is in no prompt.
- **M6:**
  - The fallback is built only when `role.provider is not ProviderKind.stub` (the same test as `RunEnvironments.judge()`).
  - Test: `test_the_fallback_is_off_under_a_stub_judge`. On a stub-judged annex run, `analyze --authority-fallback` gives `fallback_failed == 0`, every `llm` share 0, and an empty `judge_cache`.
- **M7:**
  - The docstrings say `analyze --no-judge --authority-fallback`.
  - The prompt names the tier in words (`superior self`), pinned in the wording test.
  - docs/00 E notes that a `--no-judge --authority-fallback` replay appends `cached` lines.
  - The double read of `run.json` in `analyze_run` stays: the judge role is needed before `load_run` because the fallback asks inside it. A comment says so.
- **M8:** HANDOFF.md line 40 now says "Expect 8276 passed, 5 skipped and 6 deselected ... 6 passed in the slow suite (both at Phase 7a Task 6's fix round)". HANDOFF Progress item 6 gains a fix-round sentence (`c8212a9..Task 6 fix commit`).

### Tests that have teeth (targeted mutations, each reverted)

- `except RateLimitError` turned into `except KeyError` (the rate limit swallowed again): `test_a_rate_limit_in_the_fallback_pauses_and_the_rerun_replays_the_cache` FAILED.
- Stub gate removed: `test_the_fallback_is_off_under_a_stub_judge` FAILED.
- The `--no-judge` asker keyed with a different model (`role.model if judge else ""`): `test_analyze_with_the_fallback_reports_the_classifier_shares` FAILED.

### Covering tests

`uv run pytest tests/test_authority_fallback.py tests/test_authority.py tests/test_harvest.py tests/test_analysis_load.py tests/test_run_analysis.py tests/test_pause_marker_pin.py tests/test_ledger.py tests/test_ledger_analysis.py tests/test_phase2_charts.py tests/test_env_events.py tests/test_cli.py -q -W error` gives `557 passed, 1 deselected`. `tests/test_authority_fallback.py` alone gives 14 passed.

### Gate (final tree)

- `uv run ruff format --check .`: 265 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 108 source files
- `uv run pytest -q -W error`: 8276 passed, 5 skipped, 6 deselected in 437.35s, 0 warnings. That is +6 over c8212a9: 5 fallback tests and 1 pause-marker test.
- `uv run pytest -q -m slow -W error`: 6 passed, 8281 deselected

### Notes

- The analysis tests that need the fallback on rewrite the run's `run.json` judge to `anthropic/judge-x` after the run, because the fallback is now off under a stub judge. The run itself was made with the stub judge, so no run-time pass asked a judge. The docstring of `_judged_by_a_backend` says so.
- Under `--no-judge` with a stub-judged run the fallback is off too, so a promoted run whose judge was a stub has no fallback events to replay. That follows from the M6 ruling.
