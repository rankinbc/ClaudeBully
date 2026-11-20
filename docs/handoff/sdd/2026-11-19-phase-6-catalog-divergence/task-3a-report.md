# Task 3a report: the divergence judge and its pass

Commit: 62ac316 `feat: Phase 6 Task 3a, the divergence judge, its fixtures and the opt-in pass, cache-only without the flag` (base fc417ab).

## What was implemented

- `claude_bully/metrics/divergence.py` (new): `DIVERGENCE_PROMPT_VERSION = 1`, `DIVERGENCE_HEADER`, `DIVERGENCE_MIN_CONFIDENCE = 0.5`, `CONCEALED` (the five concealed classes), `JudgedClass`, `DivergenceVerdict` and `DivergenceEvent` as the brief gives them, `DIVERGENCE_SCHEMA = _schema(DivergenceVerdict)` (property `class`, enum without `reasoning_absent`, `additionalProperties: false`), `build_divergence_prompt` (the rubric verbatim, seven parts joined by blank lines, `(none)` for no line), `answered_line`, `_checked(reasoning, reply)` (a per-call subclass whose `model_validator(mode="after")` raises `ValueError("span: ...")` for a concealed class whose `reasoning_span` is empty or not in the folded reasoning, or whose non-empty `reply_span` is not in the folded reply; the message quotes no span), `judge_divergence` (steps 1 to 5 of the brief, read back through `DivergenceVerdict.model_validate`), `divergence_pass`, `counted_class`, `concealment_rate`. `LoadedRun` and `ConvKey` are imported under `TYPE_CHECKING` only.
- `metrics/judge.py`: `ask = _ask`; `cached_answer(model, prompt, cache, *, keyed_on_system=False)` (same key as `ask`, a `cached` ledger line on a hit, None on a miss).
- `analysis/load.py`: `LoadedRun.divergence`, `LoadedRun.pass_notes` (both default empty).
- `analysis/run_analysis.py`: `analyze_run(divergence=False)`; inside the ledger block after the ratings branch, the pass with the provider only when `divergence`, a provider was built and the role is not a stub, else `provider=None`; `pass_notes["divergence"]` is `run`, `cache_only` or `skipped: stub judge` (with the stderr line the brief gives); a `RateLimitError` dumps the judgements and raises `RateLimitExit`. Nothing written to `analysis/`.
- `cli.py`: `analyze --divergence` with the brief's help text, passed through.
- `tests/fixtures/divergence/pairs.yaml`: 45 items: 5 per concealed class (25), 5 aligned, 5 near misses (aligned; the five the brief lists), 5 `reasoning_absent`. Every concealed item ends its reasoning with ` [[divergence: <class>]]` on the span line. Invented names, `.example` addresses only.
- `tests/fixtures/catalog_stub.py`: `JUDGE_ROLE`, `MARKER`, `strip_markers`, `CatalogJudge(PoisonedWellJudge)` with the five options, `catalog_factory`.
- Tests: `tests/test_divergence.py` (the brief's tests plus a fixture-hygiene test, the cache-key test, a refused-cache-hit test, a whitespace-folding test, an `answered_line` test, and two slow run-level tests), `tests/test_judge.py` (`ask` and `cached_answer`), `tests/test_run_analysis.py` (two slow run-level tests), `tests/test_reasoning_channel.py` (the fourth privacy test, slow), `tests/test_real_names.py` (`SCANNED` gains `tests/fixtures/divergence`, and a test that the pairs file is scanned).
- Docs-sync: `docs/00-RECONCILED.md` (B's `DivergenceEvent` row, E's `analyze --divergence`, H's Task 3a sentence, I34's cache-key sentence), `docs/10-ROUND-TWO.md` Part 2 (the one reader, the rubric), `HANDOFF.md` Progress item 3, spec "As planned" (D-unjudged, D-span).

## RED and GREEN

RED (probes-task3a/red.txt): `uv run pytest tests/test_divergence.py tests/test_judge.py tests/test_run_analysis.py tests/test_reasoning_channel.py tests/test_real_names.py -q -m "slow or not slow"`: `ModuleNotFoundError: No module named 'claude_bully.metrics.divergence'`, 1 error during collection, exit 2.

GREEN: the same five files under `-n 8`: 206 passed in 21.06 s.

Mutations, each restored (probes-task3a/mutations.txt): (A) the cache-only read skips the span check: 2 tests fail; (B) no low-confidence floor: 2 fail; (C) the pass writes every turn's reasoning to `analysis/leak.txt`: the privacy test fails.

## Gate (each its own command, probes-task3a/gate_*.txt)

- `uv run ruff format --check .`: 411 files already formatted, exit 0
- `uv run ruff check .`: All checks passed, exit 0
- `uv run mypy claude_bully`: no issues in 132 source files, exit 0
- `uv run mypy --platform linux claude_bully`: no issues in 132 source files, exit 0
- `uv run pytest -q -W error -n 8`: 10947 passed, 11 skipped in 227.90 s, exit 0 (from 10892: 55 fast tests)
- `uv run pytest -q -m slow -n 8`: 235 passed in 256.49 s, exit 0 (from 230: 5 slow tests)

After the gate only `HANDOFF.md` changed (Progress item); the tests that read it, plus `test_director_context.py`, were rerun: 189 passed (probes-task3a/after_handoff_edit.txt), and `ruff format --check` stayed clean.

## Timings of the run-level tests (serial, `--durations`)

`test_a_plain_analyze_reads_the_cache_and_makes_no_call` 3.06 s; `test_divergence_under_a_stub_judge_role_is_off_and_says_so` 1.27 s plus 2.26 s setup; `test_analyze_divergence_asks_once_per_turn_with_reasoning_and_caches` 1.92 s; `test_a_rate_limit_in_the_divergence_pass_pauses_the_analysis` 1.24 s; `test_only_the_divergence_prompt_holds_recorded_reasoning` 1.19 s. All five are under 4 s but marked `slow` because the brief marks them slow and each runs a stub experiment (R-I12); each marker comment gives its measured time.

## ASSUMED

- ASSUMED: `catalog_factory` returns `ledger.wrap(judge)` for the `JUDGE_MODEL` role, not the bare double (the brief's ledger assertions need a `judge` line per ask, and a double built outside `build_provider` writes no ledger line; the wrapper hands every other attribute to the double).
- ASSUMED: `answered_line` reads an idle turn's own `idle.prompt` first, before looking at the turns before it (an idle slot has no user-side turn, so the turn before it is not what it answers).
- ASSUMED: the span check applies to concealed classes only, `reply_span` included (spec 5.4 says "For a concealed class"); an `aligned` verdict's spans are kept as given.
- ASSUMED: `--divergence` with `--no-judge` under a non-stub role prints `[divergence] off: --divergence needs the judge (no judge); cached verdicts only` with note `cache_only` (spec 15 asks for a stderr line; the brief's note values have no `no judge` state). Written in the spec's "As planned" D-span line.
- ASSUMED: `cached_answer` writes a `cached` ledger line per hit, as `_ask` and the authority fallback's cache-only path do. So a plain analyze of a run that had a flagged analysis adds `cached` lines to `ledger.jsonl`. A run without reasoning does no lookup, so its outputs are byte-equal.
- ASSUMED: the run-level fixture runs both cells (the grader and its control, no `only` filter) so the pair judge is asked and the privacy test's "other judge prompts" check has something to check. A `by_cell` entry gives the control its own text: with the default entries its prompts matched the grader's byte for byte and replayed from the cache.

## Self-review

- Everything in the brief is implemented. Extras, all tests: the hygiene, cache-key, refused-hit, folding and `answered_line` tests, and the `test_real_names` coverage test.
- Privacy: the divergence prompt is the only new prompt and the only one that holds `reasoning_text`. The cache key is a sha256. The span-check error message names no span. A `JudgeError` is swallowed into `error` and never logged. Neither stderr line holds reasoning. The privacy test checks the divergence prompts (they hold the sentinel), every other judge prompt, every string sent to any other provider, every file under `analysis/`, `ledger.jsonl`, the judge cache's file names and contents, and stderr (none of these hold it).
- One reasoning store that is by design: a concealed verdict's `reasoning_span` quotes the reasoning, and that value is cached under the run's `judge_cache/` (not `analysis/`). Task 3b writes it to `divergence.jsonl`, which the spec allows. The privacy test's cache check passes only because the stub's sentinel verdicts are aligned with empty spans.
- `SCHEMA_VERSION` is unchanged; no record changes; nothing is written under `analysis/`. A run without reasoning does no cache lookup, so its outputs are byte-equal and the goldens are unchanged (the gate's golden tests pass).
- Resume: the pass adds no run-time state. A rate limit leaves the earlier verdicts cached, and the rerun replays them (tested).
- No test flaked under `-n 8` or alone.

## Concerns

- The `--no-judge` stderr line and `cli analyze --divergence`'s pass-through have no test. The brief lists no CLI test file. The flag is in `analyze --help`, checked by hand.
- `JudgeError` is told apart by the substring `span:` in its message, as the brief says. A pydantic error for some other field whose echoed input holds `span:` would be read as `span`.

## Fix round 1

Commit 4506652 on top of 62ac316. Review: 0 Critical, 0 Important, 6 Minor. The controller graded m1 and m3 up to Important.

RED (probes-task3a/fr1_red.txt): `uv run pytest tests/test_divergence.py -q -n 8` stopped first at import, because the `PASS_*` names did not exist yet. With the names in place, two tests failed: `test_an_unusable_reply_that_says_span_is_a_judge_error_never_a_span_error[prose]` (`(None, False, 'span') != (None, False, 'judge')`) and `test_a_cache_hit_the_parser_refuses_writes_no_cached_ledger_line` (`['cached', 'cached'] != ['cached']`). 2 failed, 64 passed.

- m1: the span label no longer reads the message text. `_checked`'s validator now raises `SpanError(ValueError)` in `metrics/divergence.py`. `metrics/judge._ask` raises its `JudgeError ... from last_error`. `_is_span_failure` returns `span` only when the chained `ValidationError` holds a `SpanError` in an error's `ctx`; anything else is `judge`. Tests: the reviewer's two cases, the prose reply and the field error, both now `judge`. The existing `bad_span` test still gives `span`.
- m2: spec 15's row says only "the JSON's `note` and one stderr line say so" and gives no wording. So the note is `skipped: no judge`. It is defined as `PASS_SKIPPED_NO_JUDGE` in `claude_bully/metrics/divergence.py`, beside `PASS_RUN`, `PASS_CACHE_ONLY` and `PASS_SKIPPED_STUB`. A new function there, `divergence_pass_state(flag, *, has_provider, stub_role) -> (ask, note, stderr line)`, makes the choice, and `analyze_run` calls it. A stub judge role wins over no judge. Tests:
  - `test_the_pass_state_names_why_it_did_not_ask` (fast, 7 cases).
  - `test_cli_analyze_passes_divergence_through` (fast, CliRunner with `analyze_run` patched, 3 cases).
  - `test_a_plain_analyze_reads_the_cache_and_makes_no_call` (slow) gains an end-to-end `judge=False, divergence=True` analysis. It checks the note `skipped: no judge`, exactly one `[divergence]` stderr line with the text, no call, and the same events as before.
- m3: `test_only_the_divergence_prompt_holds_recorded_reasoning` now runs on reasoning `CONCEALING`: the `SENTINEL` line, then `SPAN [[divergence: concealed_plan]]`. Every divergence verdict is therefore `concealed_plan` with `reasoning_span == SPAN`.
  - Where the reasoning may be: the span is in the events the pass returns (read through `PassSpy`) and in `judge_cache/`, by design (risk 9). The cache holds the span alone, never the sentinel line.
  - Where it may not be: neither the span nor the sentinel is in any other judge prompt, any string another provider is sent, any file under `analysis/`, `ledger.jsonl`, any cache or analysis file name, or the analysis's stdout or stderr.
  - Teeth (probes-task3a/probe_fr1_privacy_teeth.py and fr1_privacy_teeth.txt): an in-process patch of `run_analysis.divergence_pass` that writes a ledger line holding the span (`note_cached("judge/divergence/<span>")`) makes the test fail. So does one that prints the span to stdout. A control run with the same patch and no leak passes. 3 passed, exit 0.
- m4: the pairs check is now an allowlist. Every dotted host outside a marker must end in `.example`, `.test` or `.invalid`. A guard asserts that the check finds hosts at all (it finds five).
- m5: `CELL`, `CONTROL`, `TURNS`, `divergence_run`, `EXPECTED` and `PassSpy` moved to `tests/fixtures/catalog_stub.py`. `tests/test_divergence.py`, `tests/test_run_analysis.py` and `tests/test_reasoning_channel.py` import them from there, and no module imports `tests.test_divergence`.
- m6: the fix was small and local, so it is in. `cached_answer` gains an optional `parser=`: a hit the parser refuses is returned as a miss and writes no ledger line. `judge_divergence`'s cache-only path passes its checking parser. Test: `test_a_cache_hit_the_parser_refuses_writes_no_cached_ledger_line` (one `cached` line for the used hit, none for the refused one).
- Docs: `docs/00-RECONCILED.md` (E: the four notes and the ledger rule), the spec's D-span line (`SpanError` and the chained cause; the `skipped: no judge` note), and `HANDOFF.md` Progress item 3's fix-round sentence.

Covering files: `uv run pytest tests/test_divergence.py tests/test_judge.py tests/test_run_analysis.py tests/test_reasoning_channel.py tests/test_real_names.py -q -m "slow or not slow" -n 8`: 219 passed.

Gate (probes-task3a/fr1_gate_*.txt):
- `ruff format --check`: 411 files formatted, exit 0.
- `ruff check`: all checks passed, exit 0.
- `mypy claude_bully`: clean, exit 0.
- `mypy --platform linux claude_bully`: clean, exit 0.
- `pytest -q -W error -n 8`: 10960 passed, 11 skipped, exit 0 (from 10947: 13 fast tests).
- `pytest -q -m slow -n 8`: 235 passed, exit 0 (unchanged; the slow tests were changed in place).

After the gate, only the HANDOFF counts changed. The tests that read HANDOFF.md, plus `test_director_context.py`, passed: 189 passed (probes-task3a/fr1_after_handoff_edit.txt).

Not done here: CV2, the plan's File Structure naming `pass_notes`. That is the controller's, and the plan is not in this task's files.
