# Task 14 review (e8c3578..5975977)

Scope: Phase 4 Task 14, the seven Phase 3 minors on Phase 4's surface (brief), the Task 2, 5, 11, 12 and 13 carries (task-14-carries.md), and preflight P30. Task-scoped gate. I read the diff once and checked code outside it only for the named risks. The checkout stayed read-only. Every mutant and probe ran in a `git archive HEAD` copy under `probes-task14/tree`, using the repo's venv. I did not re-run the suite.

## Verdicts

- **Spec: Approved.** Every brief item and every carry item is implemented and has a test. 37 of the 40 mutants I applied fail their test. The three that pass are sub-rules of B1, and the brief's own test parametrization leaves them out (Minor 1). P30 holds: every fire `WorldGenerator.fire` and `DocWriter.write_fire` can build agrees with the validator, and the two tests that built unreachable fires now build reachable ones. Plain-run goldens are untouched. `SCHEMA_VERSION` is untouched. `parse_replay_line` is still the only parser. The commit author is `rankinbc1@gmail.com`.
- **Quality: Changes required.** There is one Important finding: the new `configs/` real-name scan lets a config exempt itself from the scan. Its fix is small and test-only. The Minors can be fixed now or carried.

Counts: 0 Critical, 1 Important, 6 Minor.

## Findings

### Important

**I1. The `configs/` real-name scan exempts any name that a config writes as a `display_name:`.** Location: `tests/test_real_names.py:299-303` (`_config_hits`) and `:159-167` (`_display_names`).
- How it fails: `_config_hits` deletes every name `_display_names()` returns. `_display_names()` collects every block-style `display_name:` value from every YAML under `configs/`, whatever role it belongs to. So a config that writes `display_name: Reuters` under its `bully:` role, plus `# lines from the Reuters wire`, passes the scan. The same goes for `display_name: Gemini` under a target, which also hides `Gemini` in every other config.
- Evidence: probe in `probes-task14`. I planted that config in the tree copy and both `test_no_real_names_in_configs` and `test_no_real_names_in_worlds_or_personas` passed. The flow-style form `{..., display_name: Gemini}` is caught, but only because the harvesting regex is anchored at line start, which is luck.
- Why it matters: non-negotiable 2 says the only name that may be exempted is the target's own display name. Here the allowlist is built from the very files being scanned, for every role.
- Fix:
  - Spare only the `RoleConfig` default (`Claude`) plus the display names of `targets[*]`, read with `yaml.safe_load`.
  - Spare each target's name only inside its own file.
  - Add a planted case to `test_a_real_name_planted_in_a_config_is_caught`: a block-style `bully:` with `display_name: Reuters` and a comment naming Reuters must hit.

### Minor

**M1. Three sub-rules of `GeneratorFire._agrees` are not pinned.** Location: `tests/test_phase4_minors.py:12-21`, against `claude_bully/records_env.py:163-166`.
- How it fails: these three mutants pass `test_a_fire_whose_fields_disagree_is_refused`:
  - `written` that ignores `rejection`;
  - `cached` that ignores empty `doc_ids`;
  - `error` that ignores `doc_ids`.
- The five cases are exactly the brief's.
- Fix: add three cases:
  - `{"status": "written", "doc_ids": ["gen-1-1"], "rejection": "lints"}`
  - `{"status": "cached", "doc_ids": []}`
  - `{"status": "error", "error": "E", "doc_ids": ["gen-1-1"]}`

**M2. `CROSSOVER` prints its span raw, and a newline splits the line.** Location: `claude_bully/analysis/replay.py:476`.
- How it fails: `crossover_span` can fall back to a query's argument text, which is target-written and can hold a newline (`environments/idle.py:883-891`).
- Evidence: my probe rendered `CROSSOVER "one` and `two"` as two lines, and `parse_replay_line` returned None for the first.
- See Named risk 2 for the per-shape recommendation.
- Fix: write `_escaped(record.span)`, add `crossover: ("span",)` to `_ESCAPED_FIELDS`, use `{_Q}` in its shape, and add a round-trip case.

**M3. `torn_line` is shared by the live readers but not by the resume reader.** This is pre-existing and outside the diff. Location: `claude_bully/runner/store.py:109-129` (`_parsed_lines`, used by `drop_dead_attempts` on `mcp/tools.jsonl` and `mcp/authority.jsonl`).
- How it fails: suppose the server logs a record cut short and closes it off with its next line (P27). The live path now skips that line: both `McpServer._lines` and `_read_log` use `torn_line`, so ASSUMED 2 holds. But if that rep is later killed and resumed, `drop_dead_attempts` raises on it ("not a torn last line"). The rep cannot resume without a manual edit.
- Evidence: probe in `probes-task14`, cases 1 and 2.
- Fix (carry, one line): in `_parsed_lines`, accept a closed torn line through `mcp_server.torn_line` for the MCP logs, or for all logs.

**M4. Inside `_complete`'s `except BaseException`, a damaged MCP log now masks the provider's exception.** Location: `claude_bully/runner/env_turn.py:672-675`.
- How it fails: `_recover` calls `after_target_call` → `_read_log`, which now raises `ValueError`. If the completion failed with `RateLimitError` and the log holds a damaged complete line, the `ValueError` replaces the `RateLimitError`. The rep dies instead of pausing.
- Impact is small:
  - The log was damaged anyway, and the next successful call would raise too.
  - On resume, `drop_dead_attempts` drops a damaged line that has no produced `turn` (my probe, cases 3 and 4), so in that case the rep comes back.
- Fix (optional): in that branch, wrap `_recover` in `try/except ValueError as exc: raise exc from original`, or log it and re-raise the original.

**M5. `add_generated`'s error message says "a different body", but the check compares the whole record.** Location: `claude_bully/environments/runtime.py:802`.
- The wording comes from the brief, and it is accurate for the case that matters.
- I checked that the whole-record comparison is not too strict on resume:
  - A `GeneratedDoc` written by `RunStore.append_generated` and read back by `read_generated` compares equal to the live one. `model_fields_set` differs, but pydantic 2.14's `__eq__` ignores it.
  - `prime(read_back)`, then `add_generated(live)`, then `prime(read_back)` does not raise.
  - Docs from a dead attempt are dropped by `drop_uncommitted_generation` before `prime`, so a redone fire never meets its stale doc.
- Fix (optional): "is already served as a different record".

**M6. The sibling `resumed_after_dead_attempt` maps in `generator.json` and `poisoned_well.json` still omit a cell with no counted reps.** Location: `claude_bully/analysis/generator.py:177-188`, `claude_bully/analysis/poisoned_well.py:483-500`.
- Only `authority.json` was named in the brief, so this is a consistency note.
- Fix: carry it with the other "carried past Phase 4" minors.

## Item-by-item binding check

"Killed" means I applied the mutant in the tree copy, ran the named test, and saw it fail. Each file was restored after its run (`out-mutants-1.txt`, `out-mutants-2.txt`).

| Item | Mutant | Test | Result |
| --- | --- | --- | --- |
| B1 `GeneratorFire._agrees` | `if problem:` -> `if False:` | `test_a_fire_whose_fields_disagree_is_refused` | killed (5 failed) |
| B1 sub-rule rejected+docs | drop `or bool(self.doc_ids)` | same | killed |
| B1 sub-rules written+rejection, cached+no docs, error+docs | each dropped | same | **survived** (M1) |
| B2 `add_generated` refusal | `if False:` | `test_a_different_document_under_a_served_id_is_refused` | killed |
| B2 idempotence | refuse any served id | same | killed |
| B3 `_read_log` raises | skip again | `test_the_runtime_refuses_a_complete_line_that_is_not_a_record` | killed |
| B3 torn line still skipped | drop the `torn_line` skip | `test_the_runtime_still_skips_a_torn_line` | killed |
| B4 `McpServer._lines` non-object | skip again | `test_the_server_refuses_a_line_that_is_not_an_object` | killed |
| B5 `corpus_snapshot` no default | restore `= ()` | `test_corpus_snapshot_takes_the_written_turns` | killed |
| B6 `_resumed_per_cell` | restore kept-cells-only | `test_every_environment_cell_has_a_resumed_count` | killed |
| B7 `HarvestJudge(items=)` | always `{"items": []}` | `test_an_llm_sourced_item_goes_into_a_fire` | killed |
| C1 record key (T2 M2) | `if True:` | `test_a_kill_inside_mark_watched_hands_each_record_once_on_resume` | killed |
| C2 `target_model=` in the runner | removed | `test_the_strategy_is_built_with_the_roles_model_in_a_run_and_in_load_run` | killed |
| C2 `target_model=` in `load_run` | removed | same | killed |
| C3 `check_condition` before `validate()` | loop removed (so `validate` refuses first) | `test_a_bad_param_is_named_before_validate_reads_the_environment` | killed |
| C4a `PSEUDO_RUNGS` skip | removed | `test_a_pseudo_rung_unlock_is_never_handed_to_the_strategy` | killed |
| C4b empty-block filter | `"\n\n".join(blocks)` | `test_a_toolless_cell_with_idle_lines_starts_with_its_first_line` | killed |
| C5 non-mapping slot | check off | `test_a_slot_value_that_is_not_a_mapping_is_named` | killed (2) |
| C6 dossier sort (T5 N1) | `sorted` -> `list` | `test_the_dossier_lists_pairs_in_turn_order_whatever_order_they_came_in` | killed |
| C7 missing `quirk_bank` (T5 N4) | catch the wrong exception | `test_a_missing_quirk_bank_is_refused_naming_the_condition` | killed |
| C8 configs scan (T11 M4) | `_config_hits` -> `[]` | `test_a_real_name_planted_in_a_config_is_caught` | killed (but see I1) |
| C8 coverage | `rglob` -> `glob` | `test_the_scan_covers_every_config` | killed |
| C9 escape (T11 M1, T4 M8) | `_escaped` identity | `tests/test_replay_parser.py` | killed (8) |
| C9 | parser does not unescape | same | killed (9) |
| C9 | no escape for: quote, backslash, CR, the other line breaks | the round-trip test | each killed |
| C9 | per shape, no escape for: HARVEST, TRIGGER, QUIRK, CHAIN, CONTRADICTION span_b | the round-trip test | each killed |
| C10 replace-by-rep (T12 M-new-1) | by-key `if key in fresh` | `test_a_fresh_answer_replaces_the_earlier_true_by_rep_even_at_another_turn` | killed |
| C11a item 10 `MIN_REPS` gate | filter removed | `test_item_10_names_a_below_neutral_rise_only_for_a_tested_entry` (slow) | killed |
| C11b the note's wording | wording changed | same | killed |
| C11c `FLOOR_CLAUSE_TEXT` parity | not mutated by me | `test_every_floor_clause_has_its_register_words` | read: it asserts equal keys, a subset of `BOUNDS`, and each text inside the falsifier; adding a key or changing item 3's text fails it as written |

Round-trip fixtures that carry M1 asks for in `tests/test_replay_parser.py`:
- straight and curly quotes: present;
- `" vs "`: present twice;
- `(heuristic 1)`: present;
- a newline: present, plus CRLF;
- a trailing quote: present.

## Named risks checked

**1. Item coverage.** See the table. Every item binds except the three B1 sub-rules (M1).

**2. Replay escaping round trip.** Probe in `probes-task14`, output `out-replay-roundtrip.txt`.
- I rendered and re-parsed 18 adversarial spans through all five escaped shapes. None failed, and every render stayed one line. The spans covered:
  - straight quotes, a lone backslash, `"x" vs "y"`, and a span that holds `" (heuristic 1)`;
  - newline, CRLF, a lone CR, U+2028, NEL, and tab plus NUL;
  - a backslash before a quote, a backslash at the end, a quote at the end, a lone quote, a lone backslash;
  - the empty span, escape-shaped text, and leading and trailing spaces.
- For QUIRK and CHAIN, the parsed excerpt equals the flattened excerpt, as before.

Recommendation on the fields left raw:
- **AUTHORITY can stay.** Its excerpt goes through `_excerpt`, which flattens it to one line, so a newline cannot split it. It is the last field on its line and greedy, so a quote inside it parses.
- **CROSSOVER should be escaped.** Its span can be target-written query text, and my probe split it (M2). This is the same three-line change as the other five shapes. Do it now, or carry it with a named owner.
- **DISCOVERY title and IDLE PROMPT can be carried.** Their text is authored by the world sheet, the idle sheet or the generator. A newline there would split the line too, so list them in HANDOFF as carried. Escaping them later is cheap.

**3. New raises on real runs.**
- `_read_log`:
  - It skips a torn line through `torn_line`, the same `_torn` and `_torn_bytes` rules the server's `_lines` uses. The server's `_lines` calls those helpers inline rather than calling `torn_line`, but the rule is the same. A live killed-writer line therefore does not kill the rep.
  - A wrong-record line, or `[1, 2]`, does raise. On resume, `drop_dead_attempts` drops such a line when it has no produced `turn`, so the rep comes back.
  - The resume reader does not share `torn_line` (M3, pre-existing). The new raise can also mask a `RateLimitError` in `_complete` (M4).
- `McpServer._lines`: the server never writes a non-object line, and `handle` answers the `ValueError` with the internal error. There is no new dead-rep path.
- `add_generated`: whole-record equality survives the JSONL round trip (M5 evidence). The only production callers are `prime`, which runs on a fresh runtime after `drop_uncommitted_generation`, and the post-fire call at `env_turn.py:898`, which hands new ids. I found no resume path where a field set at commit time differs.
- `corpus_snapshot`: its one production caller (`env_turn.py:986`) passes the turns, and the eight test calls were updated. No runtime effect.

**4. The `configs/` real-name scan.**
- Coverage: `_scanned_configs` reads every `.yaml`, `.yml`, `.md` and `.txt` file under `configs/`, recursively. That is 27 YAML files today and nothing else. `test_the_scan_covers_every_config` pins the count against `rglob("*.yaml")`.
- The `provider:` spare is narrow: it covers only `ProviderKind` values after `provider:`.
- The display-name spare has a gap (I1).
- Sparing `claude` everywhere also spares any Claude-family model string for a non-target role. The configs use the aliases `sonnet`, `opus` and `haiku`, which are not on the denylist, so this does not matter today.

**5. `_resumed_per_cell` reports 0 for a cell with no counted reps.**
- `condition_cells()` is sorted, so key order in the JSON output is unchanged.
- No golden holds `authority.json`. Both files under `tests/fixtures/golden` are unchanged in the diff.
- Nothing under `claude_bully/` reads that map back.
- The only output change: `authority.json` now also lists environment cells with no authority calls and cells whose reps were all aborted or flagged, each as 0. That is what the brief asks for.
- The sibling maps still omit such cells (M6).

## ASSUMED judgments

1. **`LintJudge(items=)` rather than a bare `HarvestJudge`, and turn 3's span:** accepted. `LintJudge` subclasses `HarvestJudge`, and the `HarvestJudge` mutant kills the test. The id follows the brief's `h-<turn>-x1` shape. The test asserts `source: llm`, a `written` fire, `used_items`, and that the span is in the body.
2. **`_read_log` skips a closed torn line:** accepted, and needed. Without it, a live killed-writer line would kill a rep that the server tolerates. The rule is shared through `torn_line`, not copied. But the resume reader does not share it (M3).
3. **Escaping only the five named shapes:** accepted for this task, since they are the ones the carry names. CROSSOVER should follow, and the rest can be carried (Named risk 2, M2).
4. **The contradiction span is exact, not collapsed:** accepted. It is the only way a newline round-trips. The replay text changes only for spans that hold a run of whitespace or a line break, and no pinned fixture holds one. The one changed pinned line is the parser fixture `c-4-1`, which the report shows.
5. **The configs scan spares provider values and the target's display names:** the provider spare is accepted. The display-name spare is rejected as built, because it takes every config's `display_name:` from every role (I1).
6. **HANDOFF marks closed items in place, marks the rest "(Carried past Phase 4.)", and counts M8 as closed:** accepted. The `HARVEST` escape does close M8, and the list reads correctly.

## Probes

Everything is in `probes-task14\`:
- `tree\`: a `git archive` copy of HEAD.
- `mutants.py`: the mutation table above. Output in `out-mutants-1.txt` and `out-mutants-2.txt`.
- `probe_replay_roundtrip.py`: Named risk 2. Output in `out-replay-roundtrip.txt`.
- `probe_add_generated_resume.py`: Named risk 3 and M5. Output in `out-add-generated.txt`.
- `probe_torn_sharing.py`: Named risk 3, M3 and M4. Output in `out-torn-sharing.txt`.
- The I1 plant was a temporary `configs/zz_probe_planted.yaml` in the tree copy, removed after the run.
