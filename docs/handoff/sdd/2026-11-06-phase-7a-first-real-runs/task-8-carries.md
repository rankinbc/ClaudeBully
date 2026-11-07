# Carries into Task 8 (from earlier tasks)

1. HANDOFF.md: fill the Task 7 range placeholder "e48783f..Task 7 commit" with `e48783f..7c22de9`; your own entry may use the placeholder shape "7c22de9..Task 8 commit".
2. (Task 7 re-review, minor) Task 7 refactored `build_pair_prompt` in `claude_bully/metrics/judge.py` to build from constants; its text is byte-identical but no test pins the full text, so the judge cache key's stability rests on a one-off check. Add one test in tests/test_judge.py that pins `hashlib.sha256(build_pair_prompt(<fixed inputs>).encode()).hexdigest()` to the value you compute now, with a comment that a change here invalidates every cached pair judgement and needs a deliberate version bump.
3. Facts from Tasks 1 to 7 the brief (written before them) cannot know:
   - Task 1: the ledger writes a `rate_limit` line for a rate-limited call; `RateLimitError` carries `retry_after_s` where the provider reports it (check `claude_bully/providers/base.py`). Your `wait_on_rate_limit` reads that; `DEFAULT_WAIT_S` otherwise.
   - Task 3: the timeout exception is `ProviderTimeoutError(ProviderError)`; it is not a rate limit and must not be waited on.
   - Task 6: `analyze_run` lets a `RateLimitError` from the authority fallback propagate into its existing pause handling (`RateLimitExit`, exit code 3), the same path `_judge_all` uses; `--wait-on-rate-limit` on `analyze` wraps that whole call, so a fallback rate limit is waited on too. One test covers the fallback case if cheap; otherwise say so.
   - Task 2: `promote` copies `COPIED_FILES` (with `ledger.jsonl`) after `scan_run(...)`; your real-name policy sits between the scan and the copy loop (P10). `COPIED_FILES` and `COPIED_DIRS` are `Final`.
   - Task 4: `doctor --live` writes to `output/doctor_live_<date>/` and `output/` is in `.gitignore` already (Task 1 added it); do not add it again.
   - The `readme_results` command in `cli.py` and `write_results_md` in `claude_bully/analysis/report.py` are as Phase 3 left them, plus Task 2's Calls line; the `_CHART_LINK` rewrite must leave the Calls line untouched.
