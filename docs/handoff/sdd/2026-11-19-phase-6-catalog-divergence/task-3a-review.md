# Task 3a review: the divergence judge and its pass

Range fc417ab..62ac316 (one commit). Read: reviewer-rules.md, task-3a-brief.md, global-constraints.md, task-3a-report.md, preflight Q13 (and Q55), the spec rows the brief and report cite (5.1, 5.4, 15's table, the "As planned" lines, risk 9 on where reasoning is stored), and the whole diff. Probes in `probes-task3a-review/` (one script, its output beside it).

Focused checks outside the diff, one per named risk:
- Recorded reasoning in a ledger line or an error log: `providers/ledger.py: LedgerProvider._write` records only the exception's class name, and `note_cached` only the key prefix and model. `_ask`'s `JudgeError` message carries the judge's raw reply (which can quote the reasoning), but `judge_divergence` swallows it into `error` and nothing logs it. Clear.
- Reasoning in promoted output: `promote.COPIED_DIRS` copies `judge_cache/`, so a concealed verdict's `reasoning_span` and `rationale` travel with a promoted run. The spec allows this: risk 9 lists the judge cache among the harness-side stores that `promote` copies and that never become a prompt. The real-name scan (`scan_real_names`) reads turns, not the cache, and the email scan reads every copied file, so an address in a cached span blocks, the same as an address in the reasoning does. Clear.
- `answered_line`'s idle reading: `records_env.IdleTurnInfo` is attached to the target turn ("it has no user-side Turn of its own"), so reading `current.idle.prompt` first is the only reading of the brief that works. Clear.
- Byte-equality on a run without reasoning: every target turn there is `reasoning_absent` before any cache lookup, so no `cached` ledger line is written and nothing goes under `analysis/`. The goldens passed in the gate. Clear.

### Spec Compliance

Compliant. Checked file by file against the brief:
- `metrics/divergence.py`: all the produced names; the rubric is verbatim (seven parts, header and version first, `(none)`); `_checked` is a per-call subclass with a `model_validator(mode="after")` that raises `span: ...` after whitespace folding, inside the ask; steps 1 to 5 run in order; the read-back goes through `DivergenceVerdict.model_validate` (M5); `LoadedRun` and `ConvKey` are imported under `TYPE_CHECKING` only (M4). `counted_class`, `concealment_rate` (None, never 0.0) and `divergence_pass` (complete conversations, sorted) are as written.
- `metrics/judge.py`: `ask = _ask`. `cached_answer` uses the same key as `_ask` and writes a `cached` line on a hit.
- `analysis/load.py`: `divergence` and `pass_notes`, both defaulting to empty.
- `analysis/run_analysis.py`: the pass is in the ledger block after the ratings branch. It asks only with the flag, a built provider and a non-stub role. The three notes are correct, the stub stderr line matches the brief's text exactly, and a `RateLimitError` dumps the judgements and raises `RateLimitExit`. Nothing is written to `analysis/`.
- `cli.py`: `--divergence` with the brief's help text. The pass-through is confirmed by a probe: `--divergence --no-judge` reaches `analyze_run(divergence=True, judge=False)`.
- Fixtures: `pairs.yaml` has 45 items (5 per concealed class, 5 aligned, 5 near misses matching the brief's five, 5 absent). The markers end the span lines, and the names are invented. `catalog_stub.py` provides `JUDGE_ROLE`, `MARKER`, `strip_markers`, `CatalogJudge` with the five options, and `catalog_factory`.
- Tests: every test the brief names is present, with its asserted text, plus extras (hygiene, cache key, refused hit, folding, `answered_line`, the scan coverage test). The privacy test asserts what the brief asks and more.
- Docs-sync: docs/00 B, E, H and I34 (the brief's I34 sentence, verbatim), docs/10 Part 2, HANDOFF Progress item 3, and the spec's "As planned" D-unjudged and D-span.
- Preflight Q13: implemented on the code side (`LoadedRun.pass_notes` exists, default empty). The ruling's text edit is to the plan, not to this task's files; see cannot-verify CV2.

ASSUMED items, judged:
- `ledger.wrap` in `catalog_factory`: sound. It mirrors what `build_provider` does inside `activate`, and the brief's ledger assertions need it.
- Idle prompt first in `answered_line`: correct (see the focused check above).
- Span check for concealed classes only, `reply_span` included: matches spec 5.4 ("For a concealed class"). Accepted.
- `--no-judge --divergence` gives a stderr line and the note `cache_only`: the line is what spec 15 asks for. The note cannot say why (see m2).
- A `cached` ledger line per cache-only hit: consistent with `_ask` and the authority fallback. Accepted.
- The run fixture runs the grader and its control: sound, and needed so that the privacy test's check of the other judge prompts has prompts to check.
- Five run-level tests marked slow: the brief marks them slow and R-I12 asks for it whenever a stub experiment runs. Accepted.
- `reasoning_span` cached in `judge_cache/`: allowed by spec risk 9. Accepted.
- `JudgeError` read as `span` when its message holds `span:`: mandated by the brief, but it misfires on prose replies (m1).

Cannot verify from the diff:
- CV1: the gate counts and the claim of 0 warnings (not re-run, per the rules). The controller can check `probes-task3a/gate_*.txt`.
- CV2: Q13's text ruling ("The File Structure lines gain the three names"). The plan's File Structure block (docs/superpowers/plans/2026-11-19-phase-6-catalog-divergence.md, around line 149, `analysis/load.py ... + LoadedRun.divergence (Task 3a)`) still does not name `pass_notes`. This diff does not touch the plan. The controller should confirm whether that edit is the controller's to apply.

### Strengths

- The span check sits inside the parser, so a misquoted verdict is retried once and never cached. The test proves this: two prompts, and an empty cache directory.
- The read-back goes through the model, never by key, and a test replays a cached entry (`class_`, not `class`) and reads its class. The cache-only path also runs a hit through the checking parser, so a damaged entry is refused, and that is tested.
- The privacy test is broader than the brief asks: it also checks the ledger, the cache's file names, stderr and every other provider's inputs. Mutation C shows it has teeth.
- The span-error messages quote no span. `JudgeError` is never logged.
- The near-miss fixtures cover the five cases the brief lists, and the hygiene test pins the marker convention.
- The import direction (M4) is respected, and the plain-run outputs are untouched.

### Issues

#### Critical

None.

#### Important

None.

#### Minor

- m1. `claude_bully/metrics/divergence.py:494` (diff line 494): `"span:" in str(exc)` labels a non-span failure as `error="span"` whenever the raw reply is shown in the `JudgeError` message. Probe (`probes-task3a-review/probe_span_label_and_cli.txt`): a prose reply, "The reasoning span: none. I would say aligned.", gives `error: span`, where `judge` is right. A field error (confidence 1.5, with "span:" in the rationale) is labelled correctly, because pydantic echoes only the field's input there. Why it matters: Task 3b counts unjudged turns by error, and a real judge's prose fallback naturally says "span". This is the brief's mandated test, so the severity stays Minor. Fix: match the rendering of the validator's own error (`"Value error, span:"`), or raise a `ValueError` subclass and have `_ask` chain the last error (`raise JudgeError(...) from last_error`) so the check can read `exc.__cause__`.
- m2. `claude_bully/analysis/run_analysis.py:252-257` (and `cli.py`): the `--no-judge --divergence` stderr line and the CLI pass-through have no test. The probe confirms that the pass-through works. Under `--no-judge --divergence` the note is `cache_only`, the same as a plain analyze, while spec 15's row says "the JSON's `note` and one stderr line say so". Task 3b, which writes the JSON note from `pass_notes`, cannot tell the two apart. Fix: a fast test of the line (it needs no run; a `PassSpy`-style test of an already recorded run, or a `CliRunner` with `analyze_run` patched, as the probe does). The controller should rule whether the note gains a `skipped: no judge` value, which mirrors `ratings.SKIPPED_NO_JUDGE`.
- m3. `tests/test_reasoning_channel.py` (the new test's last loop, diff lines 1728-1730): the test asserts that no judge cache value holds the sentinel. That is true only because every verdict in this run is `aligned` with empty spans (the report says so). Spec risk 9 places reasoning in the judge cache by design, so the assertion is not a requirement, and it will mislead the first test that copies this one onto a run with a concealed verdict. Fix: keep the file-name check, and either drop the content check for `judge_cache/` or comment it as a property of this stub only.
- m4. `tests/test_divergence.py` (`test_the_pairs_hold_no_denylisted_word...`, diff lines 1242-1244): the address check is a denylist of six top-level domains (`com org net io ai gov`), so a host such as `foo.dev` or `foo.co.uk` would pass. The global constraint is that every address sits under `.example`, `.test` or `.invalid`. Fix: require every dotted host outside the marker to end in one of the three reserved suffixes. The current file passes either way.
- m5. `tests/test_divergence.py`: `divergence_run`, `CELL`, `EXPECTED` and `PassSpy` are shared helpers that live in a test module, and `tests/test_run_analysis.py` and `tests/test_reasoning_channel.py` import them. Importing a test module runs its module-level YAML load and registers its tests' names in the other modules' namespace. They belong in `tests/fixtures/catalog_stub.py` or `tests/helpers.py`, which Tasks 3b and 7b will also reach for.
- m6. `claude_bully/metrics/judge.py: cached_answer` with `divergence.py:479-485`: on a cache-only hit that the checking parser then refuses, `cached_answer` has already written a `cached` ledger line, so `ledger.json` counts a replay for a turn reported unjudged. This is cosmetic and harmless, but the docstring's "noted in the ledger" reads as a used verdict.

### Assessment

Task quality: Approved. The judge, its cache-only path and the pass are built as the brief specifies, the privacy surface is clean (no reasoning in any key, ledger line, log line, stderr line or other prompt), and every test the brief names has teeth. The six Minors are a misfire of the brief's `span:` substring rule on prose replies, a few untested or over-strong assertions, and test-helper placement.
