# Phase 7a final fix wave: scoped re-review 2 (987f8d4..6978fe1)

Read-only. Evidence: the diff file, runner.py as it stands, env_turn.py, mcp_server.py, analysis/generator.py,
the providers, the shipped configs. Ran `tests/test_after_work_pause.py` (with each half of the fix disabled
by a scratch pytest plugin in the scratchpad, nothing in the tree touched), plus `tests/test_env_events.py`
(the two plain golden tests), `tests/test_runner.py`, `tests/test_ledger.py`, `tests/test_wait_and_promote.py`
under `-W error`: 97 passed. (Two read-only git queries were run for the fixture check; the tree is clean.)

### Finding Verdicts

- N1: ADDRESSED. `claude_bully/runner/runner.py:262` calls the new `_recapture` (277-285) for every written
  (bully line, reply) pair in `_replay`; `run()` 597-599 ends the rep through `_finish_terminated` after
  `rewatch` when `_ended_unchecked` (287-297) finds the last written non-idle reply terminating. Disabling
  `_recapture` fails the test at its `captured_responses` assertion (line 100); disabling `_ended_unchecked`
  fails it at `terminated_by_target` (line 99, `False != True`). Each half is load-bearing.
- N2: ADDRESSED. `docs/handoff/phase-7-runbook.md:246-249` (rung 0 checklist) and `:272-276` (rung 1 stop rule)
  say a responder's `rate_limit` line is a lost reply (`No reply.`), no pause, and a judge-side role's pauses.
  True to the code: `mcp_server.py:35` and `:436-439` (a failed responder costs one reply), the responder is
  wrapped in `LedgerProvider` (`mcp_server.py:447`) which writes the `rate_limit` line (`providers/ledger.py:227`).
  No other runbook line contradicts it (grep of every `rate_limit` mention).
- N3: ADDRESSED. HANDOFF.md (the Task 8 bullet, now about line 315) names the per-entry counts (`fires`, `written`,
  `cached`, `rejected` by kind, `errors`, the LLM lint's `fail` and `error`). `docs/00-RECONCILED.md` section H
  says they are totals over the entry's kept reps while `docs_written` is a per-rep mean; this matches
  `analysis/generator.py:100-122` (counts summed over the kept conversations' fires) and `:150`
  (`docs_written` divided by `len(keys)`).

### Named checks

1. PASS. `_recapture` reads `capture_as` and `intent_phase == reveal` from the bully line's `bully_meta`, which
   `_bully_turn` writes from the same intent (runner.py:537-539) that the live path reads for `captures`
   (555-559); same keys (`capture_as` name, `POST_REVEAL`), same `_capture` (turn_index and text of the same reply
   turn, first capture wins). No strategy puts either key in `intent.meta` (grep), and runner-written lines
   (opener, exit) carry neither, so no spurious capture; task turns never reach it. The test asserts
   `resumed.captured_responses == clean.captured_responses`.
2. PASS. Resume-side termination is a subset of live termination: same `_terminates` on the same stored text and
   `tool_cap_cutoff`, but `_last_completion` is None on resume, so the refusal branch can only under-terminate,
   never over-terminate. An idle reply returns None (`last.idle is not None`, line 295; live never terminates an
   idle turn); a pending bully line returns None (292); pause markers are skipped when picking the last turn
   (294), and a pause in `rewatch` raises first (594-596), so a marker never leads to a finish. A task reply
   terminates on both paths (live 611/665). A fresh rep (no turns) returns None.
3. PASS. `tests/test_after_work_pause.py` drives `run_experiment` on real records and the real `_replay` and
   `rewatch`; it patches only `build_strategy` (to put `capture_as`/reveal on the second line) and
   `EnvironmentRuntime.after_target_turn` (the injected rate limit), never `_replay`. It asserts the pause marker
   and empty captures after the pause (the precondition), then after resume `complete`, `terminated_by_target` at
   turn 3, equal captures, and the real (speaker, text) turns equal to the unbroken run's, which excludes any
   further bully turn after the `[END]`.
4. PASS. The fix diff touches six files, none under `tests/fixtures/`; the tree is clean; both plain golden tests
   (`plain_stub_smoke.json`, `plain_fixture_events.json`) pass.

Refusal limit: ACCEPTABLE, not a gap. Termination is the runner's (`is_termination`, runner.py:116-119), not a
strategy's. `stop_reason == "refusal"` can only come from `AnthropicProvider` (`anthropic_api.py:135`): the
`claude_code` provider sets `stop_reason` to the result subtype (`claude_code.py:399`, "success" or an error
subtype), the stub sets `tool_use`/`end_turn`, OpenAI's `finish_reason` is never "refusal", and every shipped config
(and every 7b ladder rung) targets `claude_code` (the `anthropic` target is commented out in all of them). A refusal
with empty text is caught by the text test anyway. The gap needs an API target, an environment cell, a rate limit in
exactly that reply's after-work, and a non-empty refusal text. The docstring (runner.py:287-291) and the spec bullet
disclose it. Closing it would mean keeping `stop_reason` on `Turn` (a schema change); not worth it now.

### New Breakage in the Fix Diff

None. `_ended_unchecked` runs on every `run()` but returns None on a fresh rep and on any rep whose last real turn
is a bully line, an idle turn or a non-terminating reply, so the ordinary resume and the unbroken paths are
unchanged (97 related tests plus the new one pass under `-W error`). A rep killed after writing a terminating reply
(not only paused) now ends instead of getting more bully turns, which is the live behavior.

### Out-of-Scope Observations

- The test's injected limit raises at the head of `EnvironmentRuntime.after_target_turn`, before any discovery or
  trigger record is written; a real judge-side pass raises partway through the session's after-work. N1's capture
  and termination logic does not depend on where it raised, and `rewatch`'s idempotence was covered by the fix
  wave's I2 tests, so this narrows nothing here.
- `_ended_unchecked` calls `_terminates`, which passes `self._last_completion` (always None on a fresh `_CellRun`);
  harmless and disclosed, but the refusal branch there is dead code on resume.
- Carried from the implementer's report, unchanged and pre-existing: `runner/store.py: _keep_only` does a bare
  `os.replace` with no Windows `PermissionError` retry.

### Verdict

Repair: All findings addressed, no new Critical/Important breakage.
