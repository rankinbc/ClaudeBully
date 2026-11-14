# Task 14 report: the open Phase 3 minors on Phase 4's surface, and the carries

Commit: 5975977 `fix: Phase 4 Task 14, the Phase 3 final-review minors on Phase 4's surface` (one commit on e8c3578, author rankinbc1@gmail.com, not pushed).

## Items

RED evidence: "new test failed before the fix" means the test was written first and run against the unfixed code; "mutant" means the test is test-only (the code was already right) and I applied the named mutation to a scratch edit of the module, ran the test, saw it fail, and restored the file (`git diff` clean on the module afterwards).

| # | Item | What changed | Test | RED evidence |
| --- | --- | --- | --- | --- |
| B1 | Task 5 m4: `GeneratorFire` cross-field validator | `records_env.GeneratorFire._agrees` (`model_validator(mode="after")`): `written`/`cached` need `doc_ids` and no `rejection`; `rejected` needs a `rejection` and no `doc_ids`; `error` needs an `error` and no `doc_ids`. Two tests built unreachable fires and now build reachable ones: `tests/test_records_env.py` (a `cached` fire with no docs became `rejected`/`cap`) and `tests/test_generator_plan.py` `_fire` (a `rejected` fire now names `lints`). | `test_phase4_minors.py::test_a_fire_whose_fields_disagree_is_refused` (5 cases), `test_consistent_fires_still_validate` | new test failed before the fix: all 5 cases `DID NOT RAISE ValidationError` |
| B2 | Task 7 m7: `add_generated` and a different document under a served id | `EnvironmentRuntime.add_generated` raises `ValueError("generated document '<id>' is already served with a different body")`; the same document again stays idempotent | `test_a_different_document_under_a_served_id_is_refused` | new test failed before the fix: `DID NOT RAISE ValueError` |
| B3 | Task 9 review: `runtime._read_log` skips a malformed complete line | `_read_log` raises `ValueError("<path>: line <n> is not a valid record (<exc>); the server log is damaged")`; it still skips the unterminated last piece, and skips a complete line that is a torn record by the server's own rule (new `mcp_server.torn_line`, built on `_torn` and `_torn_bytes`) | `test_the_runtime_refuses_a_complete_line_that_is_not_a_record` (a missing field, `[1, 2]`, a bare word), `test_the_runtime_still_skips_a_torn_line` | new test failed before the fix: `DID NOT RAISE ValueError` (the torn-line test passes before and after: it is the regression guard for ASSUMED 2) |
| B4 | Task 9 review: `McpServer._lines` drops a non-object line silently | raises `ValueError("<path>: line <n> is not a JSON object (<type>); the server log is damaged")`; `handle` already answers a `ValueError` with the internal error | `test_the_server_refuses_a_line_that_is_not_an_object` | new test failed before the fix: `DID NOT RAISE ValueError` |
| B5 | Task 9 review: `corpus_snapshot`'s default | `corpus_snapshot(self, turns: Sequence[Turn])`; eight bare calls in `tests/test_corpus.py`, `tests/test_generator_runtime.py`, `tests/test_runtime.py` now pass `[]` | `test_corpus_snapshot_takes_the_written_turns` | new test failed before the fix: `DID NOT RAISE TypeError` |
| B6 | Older re-review minor: a cell with no counted reps absent from the resumed counts | `analysis/authority._resumed_per_cell` iterates every environment condition cell (`condition_cells()` with `environment_of`), 0 when none of its reps was kept | `test_every_environment_cell_has_a_resumed_count` (the annex authority run, then its one rep marked aborted) | new test failed before the fix: `assert {} == {'env_grader__t0': 0}` |
| B7 | The review's m2: an LLM-sourced item through a fire | `tests/fixtures/generator_stub.HarvestJudge(items=)` answers a harvest prompt with `{"items": items}` | `test_generator_run.py::test_an_llm_sourced_item_goes_into_a_fire`: the span `the timestamp on it is missing` becomes `h-3-x1` (`source: llm`), the turn-3 fire is `written`, the buried document lists `h-3-x1` in `used_items` and holds the span | run against HEAD's fixture: `TypeError: HarvestJudge.__init__() got an unexpected keyword argument 'items'` |
| C1 | Task 2 M2: the once-per-process record key | test only | `test_strategy_plumbing.py::test_a_kill_inside_mark_watched_hands_each_record_once_on_resume` | mutant `if key not in self._handed_records:` -> `if True:`: fails, `('unlock', 1)` handed twice |
| C2 | Task 2 M3: `target_model=` in the runner and in `load_run` | test only (`_Recorder` logs its `target_model` in `BUILT`) | `test_the_strategy_is_built_with_the_roles_model_in_a_run_and_in_load_run` | mutants deleting `target_model=cell.target.model` (runner) and `target_model=spec.target.model` (`load_run`): each fails |
| C3 | Task 2 M4: `check_condition` before `validate()` | test only: a dry run where both refuse (a misspelt param and a schedule naming no rung) must name the param | `test_a_bad_param_is_named_before_validate_reads_the_environment` | mutant moving the `check_condition` loop after `environments.validate(...)`: fails, `Regex pattern did not match` (the schedule error wins) |
| C4a | Task 2 M5 (a): the `PSEUDO_RUNGS` skip | test only (`EnvironmentSession._file` on a bare session) | `test_a_pseudo_rung_unlock_is_never_handed_to_the_strategy` | mutant removing the skip: fails |
| C4b | Task 2 M5 (b): the empty-block filter of `system_prompt_section` | test only (a toolless cell, `system_prompt_date: omit`, with a permission line) | `test_a_toolless_cell_with_idle_lines_starts_with_its_first_line` | mutant `"\n\n".join(blocks)`: fails (the section opens with a blank block) |
| C5 | Task 2 M7: a non-mapping slot value | `strategies/factory.routed_params` raises `ValueError("condition '<c>': params['<slot>'] must be a mapping of that part's params, not <type>")` | `test_a_slot_value_that_is_not_a_mapping_is_named` (a lone part `{premise: "x"}`, a split one `{premise: 3}`) | new test failed before the fix: `TypeError: 'int' object is not iterable` and the `dict("x")` `ValueError` without the condition |
| C6 | Task 5 N1: the dossier's turn-order sort | test only | `test_poisoned_well_premise.py::test_the_dossier_lists_pairs_in_turn_order_whatever_order_they_came_in` (the later pair handed first) | mutant removing the `sorted(...)` in `_dossier_text`: fails |
| C7 | Task 5 N4: a missing `quirk_bank` stem | `RunEnvironments._poisoned_well_problems` catches `FileNotFoundError` and returns `quirk bank '<stem>' has no file (<path>)`, raised as `condition '<c>' (environment '<e>'): ...` | `test_a_missing_quirk_bank_is_refused_naming_the_condition` | new test failed before the fix: raw `FileNotFoundError: ... data\nonesuch.yaml` |
| C8 | Task 11 M4: the real-name scan over `configs/` | `tests/test_real_names.py`: `_scanned_configs()` (every text file under `CONFIGS_DIR`), `_config_hits` (spares a `provider: <ProviderKind>` value and the target's display names, as exemptions are spared elsewhere), `test_no_real_names_in_configs` | `test_the_scan_covers_every_config`, `test_no_real_names_in_configs`, `test_a_real_name_planted_in_a_config_is_caught` (a planted outlet in a comment, a `gpt-4o` model, "the Anthropic API" in prose; a clean `provider: anthropic` line passes) | mutant dropping the provider spare: `test_no_real_names_in_configs` fails (the commented `provider: anthropic` lines of five configs hit), proving the scan reads every config; mutant `_config_hits` returning `[]`: the planted test fails. The 27 configs are clean. |
| C9 | Task 11 M1 and Phase 3 Task 4 M8: escape quote marks in replay spans | `analysis/replay.py`: `_escaped` on the quoted field of `TRIGGER`, `HARVEST`, `QUIRK`, `CHAIN` and `CONTRADICTION` lines; the five shapes match an escaped field (`_Q`); `parse_replay_line` unescapes those fields (`_ESCAPED_FIELDS`, `_unescaped`). A contradiction span is exact (no longer `_flat`). One parser still. | `test_replay_parser.py::test_a_rendered_span_parses_back_to_the_recorded_span` (9 spans: straight and curly quotes, `"real" vs "fabricated"`, `"a" vs "b"`, `(heuristic 1)` and `(llm 0.6)`, a newline and CRLF, a trailing quote, a trailing backslash, a line separator and a vertical tab, escape-shaped text), `test_a_plain_span_is_written_as_it_is`; the `c-4-1` fixture rewritten to the escaped form | run against HEAD's `replay.py`: 5 failed (the escaped `c-4-1` fixture, and the ` vs `, `"a" vs "b"`, newline and line-separator spans) |
| C10 | Task 12 M-new-1: the read-back's replace-by-rep | test only | `test_ratings.py::test_a_fresh_answer_replaces_the_earlier_true_by_rep_even_at_another_turn` | by-key mutant in `carry_flags` (`if key in fresh: continue`): fails, `stale_kept` keeps `pw__t0/0/rate_values/5` |
| C11a | Task 13 N-new-2: item 10's note only at `MIN_REPS` | `analysis/hypotheses.item_10`: `below` keeps entries with `min(n_a, n_b) >= MIN_REPS` | `test_hypotheses.py::test_item_10_names_a_below_neutral_rise_only_for_a_tested_entry` (slow: the `mixed_dir` run) | reverting the filter: fails (two deep reps, untested, note says "below neutral") |
| C11b | Task 13 N-new-3: the note's wording | test only | the same test: the exact sentence for -0.1/-0.5, none for 0.2/-0.5 (supported) | mutant `below = []`: fails |
| C11c | Task 13 N-new-4: `FLOOR_CLAUSE_TEXT` key parity | test only | `test_every_floor_clause_has_its_register_words`: same keys as `FLOOR_CLAUSES`, a subset of `BOUNDS`, each text in the register item's falsifier | mutants adding `4: "x"` and changing item 3's words: each fails |

## Files changed

Code: `claude_bully/records_env.py`, `claude_bully/environments/runtime.py`, `claude_bully/environments/mcp_server.py`, `claude_bully/analysis/authority.py`, `claude_bully/analysis/replay.py`, `claude_bully/analysis/hypotheses.py`, `claude_bully/strategies/factory.py`, `claude_bully/runner/env_turn.py`.

Tests: `tests/test_phase4_minors.py` (new), `tests/fixtures/generator_stub.py`, `tests/test_generator_run.py`, `tests/test_strategy_plumbing.py`, `tests/test_poisoned_well_premise.py`, `tests/test_real_names.py`, `tests/test_replay_parser.py`, `tests/test_replay.py`, `tests/test_ratings.py`, `tests/test_hypotheses.py`, `tests/test_records_env.py`, `tests/test_generator_plan.py`, `tests/test_corpus.py`, `tests/test_generator_runtime.py`, `tests/test_runtime.py`.

Docs: `HANDOFF.md` (header, the Task 14 bullet and counts, the next step, the minors list marked), `docs/00-RECONCILED.md` (B `GeneratorFire`, E replay, H Task 14), `docs/02-ENVIRONMENTS.md` (the two replay "as built" notes), `docs/04-AUTHORITY.md` (`resumed_after_dead_attempt`), the spec's "As planned" (Task 14).

## ASSUMED

- ASSUMED 1: the brief's test uses `HarvestJudge(items=...)`; the run uses `LintJudge(items=...)`, the `HarvestJudge` subclass that also answers the LLM lint. With a bare `HarvestJudge` the buried `recovery_guide` is rejected (`llm_reader_address: no verdict`), so no fire commits. And the span is turn 3's, not turn 1's: the fire holds four items and picks turn 3's first, so a turn-1 LLM item is harvested but not used. The item id is `h-3-x1`, the `h-<turn>-x1` shape the brief names.
- ASSUMED 2: `_read_log` raises on a complete line that is not a valid record, except a torn record that the server closed off before its next line. The server's `_append_line` does this when a writer is killed mid-line, and the server's own reader skips such a line (P27). Raising on it would fail a resumed `claude -p` rep that the server tolerates. The rule is shared through `mcp_server.torn_line`, not copied.
- ASSUMED 3: the escape covers the five shapes the carry names. `AUTHORITY`'s excerpt, `CROSSOVER`'s span, the `DISCOVERY` title, `IDLE PROMPT` and the `bully line:` sub-line stay as they are (see Concerns).
- ASSUMED 4: an escaped contradiction span is exact (not whitespace-collapsed), so a newline round-trips as the carry asks. `test_replay.py`'s newline test now expects the recorded spans back, and its line pins the escaped text.
- ASSUMED 5: the `configs/` scan spares a `provider: <kind>` value (a `ProviderKind` value after `provider:`, comments included) and the target's display names (`_display_names()`, which already covers the default `Claude` and every config's). That also spares the family's model strings such as `claude-opus-5-5`, the target's own API string. Everything else is scanned as written, comments included. Another family's model string or a provider name in prose is a hit.
- ASSUMED 6: the HANDOFF list marks each closed item in place (`[closed in Phase 4 Task 14]`) and ends each line "carried past Phase 4" for the rest. Phase 3 Task 4's M8 (the replay prints an LLM span raw) is closed by the carry's `HARVEST` escape, so eight items are marked closed: the brief's seven plus M8.

## Skipped

None.

## The replay escaping format

Applies to the quoted field of `TRIGGER` (span), `HARVEST` (span), `QUIRK` (answer excerpt), `CHAIN` (response excerpt) and `CONTRADICTION` (both spans). Inside the quotes:

- a backslash is written as two backslashes;
- a straight quote mark is written as a backslash and a quote;
- a newline is a backslash and `n`, a carriage return a backslash and `r`;
- every other character `str.splitlines` breaks a line at (vertical tab, form feed, the three separators 0x1c to 0x1e, NEL, U+2028, U+2029) is a backslash, `u` and four hex digits;
- curly quotes and everything else are written as they are.

The parser's quoted group is `(?:[^"\\]|\\.)*`, so a field ends at its first bare quote mark. `parse_replay_line` undoes each escape. An excerpt is cut and flattened to one line first, as before, and then escaped. A span with none of these characters reads exactly as before, so `HARVEST hedge "I can't verify any of this"` is unchanged.

Examples (as rendered, then as parsed):

- `CONTRADICTION c-4-1 t1/t4 "I said \"yes\" once." vs "I never said \"yes\"." (heuristic 1)` parses to span_a `I said "yes" once.` and span_b `I never said "yes".`
- `CONTRADICTION c-1-1 t0/t1 "I am a model." vs "I can't tell \"real\" vs \"fabricated\" memories." (llm 0.6)` parses to span_b `I can't tell "real" vs "fabricated" memories.` (before, span_a ran to the last ` vs `).
- `HARVEST hedge "I said it once.\nThen again."` parses to a span holding a real newline; the replay line stays one line.
- `TRIGGER world_question "It ends on a quote\"" (heuristic 0.9)` and `TRIGGER world_question "It ends on a backslash \\" (heuristic 0.9)`.
- `CHAIN link 1 hedged "I scored (heuristic 1) once." (llm 0.6) pressed`: the classifier text inside the quotes moves no field.

No golden replay fixture changed: `test_replay.py`'s, `test_harvest.py`'s, `test_generator_run.py`'s, `test_poisoned_well_run.py`'s and `test_env_configs.py`'s pinned lines hold no quote mark, backslash or line break inside a span. The only pinned text that changed is the `c-4-1` parser fixture, now written in its escaped form:

```
-        'CONTRADICTION c-4-1 t1/t4 "I said "yes" once." vs "I never said "yes"." (heuristic 1)',
+        r'CONTRADICTION c-4-1 t1/t4 "I said \"yes\" once." vs "I never said \"yes\"."'
+        " (heuristic 1)",
```

`test_replay.py::test_a_newline_or_a_quote_in_a_contradiction_span_leaves_one_line_that_parses` now expects the exact spans (`'I said "yes"\nonce.'`, `"I never\r\n said it."`), not the collapsed ones. Records are untouched: the replay is text, and the golden record fixtures are unchanged.

## Gate

Run once each, on the final tree:

- `uv run ruff format --check .`: 313 files already formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy claude_bully` and `uv run mypy --platform linux claude_bully`: no issues in 119 source files.
- `uv run pytest -q -W error`: 9801 passed, 9 skipped, 46 deselected in 703 s (from 9764/9/45: +37 default tests).
- `uv run pytest -q -m slow`: 46 passed (from 45: `test_item_10_names_a_below_neutral_rise_only_for_a_tested_entry`).
- Every new default test runs under 2 s (`--durations`; the slowest is 1.25 s, the ratings re-ask).

## Concerns

1. The other quoted replay fields are not escaped: the `AUTHORITY` excerpt, the `CROSSOVER` span, the `DISCOVERY` title, `IDLE PROMPT` and the `bully line:` sub-line (no shape parses the last two). The parsed ones are the last field on their line, or, for the title, run to the last quote before ` via`, so a quote mark inside one still parses. A raw line break in a `CROSSOVER` span or an idle prompt could still split its line, and a title holding `" via ` could mis-split. They are outside the carry's list. Closing them would be the same small change per shape.
2. A replay text written before this commit, with a raw quote inside a `TRIGGER`, `HARVEST`, `QUIRK`, `CHAIN` or `CONTRADICTION` field, no longer parses through `parse_replay_line`; it returns None. Nothing stores replay text (it is rendered from the records each time, and nothing under `claude_bully/` or `scripts/` calls the parser), so I judged this acceptable.
3. `_read_log`'s message embeds pydantic's multi-line `ValidationError` text, as the brief's format says. It reaches stderr through the provider error path. A one-line form (`factory.one_line`) would read better; I kept the brief's shape.
4. `add_generated` compares whole `GeneratedDoc` records, not the body alone, so any field difference under a served id raises. The message says "a different body", as the brief words it. The full suite passed with this, so no path re-serves a changed record.

## Fix round 1

Commit: a8a5578 `fix: Phase 4 Task 14 fix round 1, ...` (one commit on 5975977, author rankinbc1@gmail.com, not pushed).

Every test below was written first and run against 5975977. Where the code was already right (M1), the RED evidence is the reviewer's surviving mutants, which the new cases now kill.

| Finding | What changed | Test | RED on 5975977 |
| --- | --- | --- | --- |
| I1 (configs scan exempts any `display_name:`) | `tests/test_real_names.py`: `_target_names(path)` reads `targets[*].display_name` with `yaml.safe_load`. `_config_hits` spares only the `RoleConfig` default and that file's own targets' names. `_display_names()` (the world files' `# real-name-ok` allowlist) is the default plus every config's target names, with no other role. | `test_a_display_name_off_a_target_exempts_nothing`: in a monkeypatched `CONFIGS_DIR`, a block-style `bully:` with `display_name: Reuters` plus a comment naming it is a hit, in that file and in another, and `reuters` is not in `_display_names()`; a target named so is spared in its own file only | failed: `_config_hits(planted)` returned `[]` |
| M4 (a damaged log hides the rate limit) | `EnvironmentSession._complete`'s `except BaseException`: `_recover` is wrapped, a `ValueError` from a damaged log is printed to stderr, and the call's own exception is re-raised | `test_runner_env.py::test_a_damaged_log_never_hides_the_rate_limit_of_the_call` (slow, about 3.5 s): the claude -p annex run's third target call is rate-limited after `[1, 2]` reached `mcp/tools.jsonl`; the run pauses (`RateLimitExit`), and the resume drops the line and completes | failed: `ValueError: ...tools.jsonl: line 3 is not a valid record` instead of `RateLimitExit` |
| M1 (three `_agrees` sub-rules unbound) | test only | 3 cases added to `test_a_fire_whose_fields_disagree_is_refused`: written with a rejection, cached with no docs, error with docs | the cases pass on 5975977 (its code is right); the reviewer's three mutants (written ignores rejection, cached ignores empty docs, error ignores docs) each fail the test now (1 failed, 7 passed) |
| M2 (CROSSOVER prints its span raw) | `replay.py`: `CROSSOVER` writes `_escaped(span)`, its shape uses `_Q`, `_ESCAPED_FIELDS["crossover"]`. `AUTHORITY` stays raw. HANDOFF lists the `DISCOVERY` title and `IDLE PROMPT` as carried past Phase 4. | `test_a_rendered_span_parses_back_to_the_recorded_span` gains a `Crossover` record (9 spans) | failed for the newline span (`'Then again.\r'`) and the line-separator span (`CROSSOVER "A line` split) |
| M3 (the resume reader raises on a closed torn line) | `store.drop_dead_attempts(..., closed_torn=False)` / `_parsed_lines(closed_torn=)`: with `closed_torn`, a line `mcp_server.torn_line` calls torn is dropped with the dead attempt. `EnvironmentSession.prime` passes `closed_torn=True` for the MCP server's two logs only. | `test_runner_env.py::test_a_torn_log_line_closed_off_mid_file_resumes` (slow, about 4 s): the paused run's tools log holds `{"id": "mcp-5-1", "tu` closed off by a newline, and the resume completes; `test_phase4_minors.py::test_only_a_server_log_reads_a_closed_off_torn_line_as_torn`: the same line raises without `closed_torn`, and with it the line is dropped | failed: `...tools.jsonl: line 3 is not valid JSON ...; it is not a torn last line, so it is not dropped`; the unit test fails with `TypeError` (no `closed_torn`) |
| M5 (the message says "a different body") | `add_generated`: "is already served as a different record" | `test_a_different_document_under_a_served_id_is_refused` matches the new text | failed: `Regex pattern did not match` |
| M6 (sibling resumed maps omit a cell) | `generator.json`: every environment condition cell. `poisoned_well.json`: every Poisoned Well condition cell. Each cell with no counted rep is 0. `values_watch` is unchanged (it divides by a cell's reps). | `test_generator_analysis.py::test_a_cell_with_no_counted_rep_has_a_resumed_count_of_0` (every reflexive rep aborted); `test_poisoned_well_analysis.py::test_a_cell_with_no_counted_rep_has_a_resumed_count_of_0` (a second PW cell whose rep aborted) | failed: `rescue_gen_reflexive__t0` absent; `pw_b__t0` absent |

ASSUMED (fix round 1):
- ASSUMED 7: M3 applies the closed-torn rule only to the MCP server's logs, not to every log. The first version applied it everywhere, and it broke `tests/test_generator_runtime.py::test_a_torn_last_line_is_dropped_and_damage_raises`, which pins that a mid-file fragment in the store's own `generated` stream is damage. That stream is never closed off, so the pin is right. `drop_dead_attempts` therefore takes `closed_torn`, and the session sets it for `mcp_dir / tools.jsonl` and `mcp_dir / authority.jsonl`.
- ASSUMED 8: M4 prints the damaged-log error and re-raises the call's own exception, rather than chaining one onto the other. The pause path then behaves as before Task 14. The resume's `drop_dead_attempts` drops the line, since no written turn owns it, and the test shows the rep completing.
- ASSUMED 9: I1 also narrows `_display_names()`, the allowlist for the world files' `# real-name-ok` comments, to target roles, since the same hole was there. No world or persona file's exemption changed: the scan tests pass.
- The two run-level tests take 3.5 to 4 s, so they are marked `slow`.

Files changed (fix round 1): `claude_bully/runner/env_turn.py`, `claude_bully/runner/store.py`, `claude_bully/analysis/replay.py`, `claude_bully/analysis/generator.py`, `claude_bully/analysis/poisoned_well.py`, `claude_bully/environments/runtime.py`; `tests/test_real_names.py`, `tests/test_phase4_minors.py`, `tests/test_replay_parser.py`, `tests/test_runner_env.py`, `tests/test_generator_analysis.py`, `tests/test_poisoned_well_analysis.py`; `HANDOFF.md`, `docs/00-RECONCILED.md`, `docs/02-ENVIRONMENTS.md`, the spec's "As planned".

Goldens: no golden changed. `tests/fixtures/golden/` is untouched, and no golden holds `generator.json` or `poisoned_well.json`. `tests/test_generator_analysis.py`'s existing `{FLAT: 1, OFF: 0, REFLEXIVE: 0}` pin and `tests/test_poisoned_well_analysis.py`'s `{CELL: 0}` still hold.

Gate (fix round 1), run once on the final tree: ruff format and ruff check clean; both mypy runs clean (119 files); `uv run pytest -q -W error` 9808 passed, 9 skipped, 48 deselected (+7 default); `uv run pytest -q -m slow` 48 passed (+2).

Concerns (fix round 1):
1. The `DISCOVERY` title and `IDLE PROMPT` stay raw, as the coordinator ruled; they are carried past Phase 4 in HANDOFF.
2. When `_recover` fails on a damaged log during a failed call, it does not reach its own `runtime.save()`. The pause then saves only what the rewind saves. The resume re-derives the state from the records, and the test shows it completing.
