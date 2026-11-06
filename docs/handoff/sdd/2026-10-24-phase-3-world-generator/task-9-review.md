# Task 9 review: the Phase 2 final-review minors (m2, m4, m5, m6, m7, m9, m10)

Range 24b9a25..91c2de1, one commit. Read from `review-24b9a25..91c2de1.diff`; code outside the diff was inspected only for the named risks below, one check each. A focused run of the four m7 tests (three new, the Phase 2 torn-tail test) passed; two read-only probes of `McpServer._lines` were run from the scratchpad.

## Spec Compliance

Minor by minor, brief plus carries (the carry wins where they differ).

| Minor | Verdict | Evidence |
| --- | --- | --- |
| m2 `corpus_snapshot(turns)` | PASS | `claude_bully/environments/runtime.py:822-843`: a purged document is kept only when a call owned by a written target turn (`Turn.tool_call_ids`) served it; generated documents go through the same `_calls`/`result_doc_ids` path (carry). `claude_bully/runner/env_turn.py:823` passes `self.store.read_turns(self.cell_id, self.rep)`. Test `test_the_snapshot_keeps_a_purged_document_only_for_a_written_turn_s_call` primes a dead-attempt call and checks both outcomes. |
| m4 `<arm>_control` | PASS | `claude_bully/analysis/idle.py:232, 243-266`: `CONTROL_SUFFIX`, two-pass naming, controls-only arms keep their name; `sanctuary_quiet`/`unclassified` untouched (carry). The chart's `paired` filter (`idle.py:195`, outside the diff) ignores a `_control` arm, as the docstring says. Test runs a real composed experiment and reads `idle_behavior_shares`. |
| m5 effective name and request bank | PASS | `runtime.py:858-874`: the sheet dump carries `desk.model_name` (the config override or the sheet's name, `environments/authority.py:421`), plus `authority: {superior_self_name, request_bank}`. `analysis/load.py:337-342, 352, 371`, `metrics/events/_common.py:33-34`, `metrics/events/__init__.py:94, 109`, `metrics/events/authority.py:133, 164, 190-193, 201`. The detectors read the effective name from the snapshot sheet (`authority.py:179-180`, outside the diff, reads `context.world.sheet.superior_self_name`), so the report's claim that no lexicon change was needed holds. HANDOFF "From Task 13" `family_file` item removed (`HANDOFF.md` diff line 144 deleted); the closure is pinned by `test_family_file_adoption_reads_the_recorded_request_bank`. |
| m6 `_replay` turn shape | PASS | `claude_bully/runner/runner.py:255-257`: `before = [t for t in self.turns if t.index < user_turn.index]`, markers included, matching the live `self._state()` (`runner.py:211-213`, hands `self.turns`). Strategies: no strategy indexes `state.turns` (grep of `claude_bully/strategies` for `.turns`: only `ConversationState.replies_to_bully`, which goes through `bully_reply_positions`, `records.py:81-95`, and that drops markers; the other hits are `conv.turns` on a `Conversation`, not the state). Test runs a rate-limited rep, a crash, and a resume on real records and compares the live and replayed `state.turns`. |
| m7 `_lines` raises on mid-line damage | PASS with one Important finding | `claude_bully/environments/mcp_server.py:179-199, 469-492`: `_torn` plus `_CUT_TOKEN`; the `ValueError` names the file and line; `handle` (`mcp_server.py:273-276`) answers -32603 and prints the detail on stderr. The implementer's reading of P27 is right: Python reports an unterminated string at its opening quote and a cut `\uXXXX` at its `u`, so "pos at end of line" alone would call the Phase 2 torn-tail fixture damage. Torn fixtures: `test_a_torn_last_line_of_the_server_log_still_serves` and `test_every_cut_of_a_record_is_a_torn_tail_not_damage` (every byte cut, closed off or not, both `ensure_ascii` settings). Damage fixture: `{"id": mcp-1-1}` on line 1 of 2, per the carry. The byte-level mask is the Important finding below. |
| m9 comments and pin | PASS | `data/personas/superior_self.yaml:51-53`, `data/personas/peer.yaml:21-23`; `HAND_READ` pin in the test; HANDOFF Phase 7 list gains the LLM-lint line. |
| m10 constants and `load_yaml_model` | PASS | `environments/world.py:27-30, 306-309, 364`; `environments/idle.py:71-72` re-exports with the redundant-alias form (mypy strict needs it; the brief's `__all__` route did not apply, there is none); `corpus.py:36` imports from `world`; `environments/sheets.py:27-28, 325` imports only `PERSONA_SHEETS_DIR` and `load_yaml_model`. Importer list at HEAD (my grep) matches the report's "after" list exactly: `PHRASE_HOOK`/`SESSION_HOOK` from `environments.idle` still in `environments/runtime.py:126-127` and `metrics/events/idle.py:32-33` through the re-export; `_validate` used only module-privately in `strategies/sheets.py` and `environments/world.py`. No import cycle: `environments/config.py` imports only `enums` and `records_env`. |

Files: every file the brief lists is in the diff; `tests/test_phase3_minors.py` is created. Docs sync: HANDOFF Progress item 9, the Phase 3 owner paragraph, the minors line, the test counts, the resume prompt; `docs/00-RECONCILED.md:62` (World snapshot row); `docs/04-AUTHORITY.md:121`.

Missing: a fixture for damage on the file's last line (P27 says mid-line damage raises wherever it sits; only line 1 of 2 is tested). Minor.
Extra: `HANDOFF.md:23` rewrites the commit-trailer note to "Opus 5.5 for Task 9". The commit at HEAD (`91c2de1`, author `rankinbc1@gmail.com`) carries `Co-Authored-By: Claude Fable 5.1`, as the carry asked, so the report's hash `420271a` was amended and the HANDOFF note is now wrong. Minor.
Misunderstood: none.
CANNOT VERIFY: the full-suite gate numbers (8144 passed, 5 skipped, 6 deselected; slow 6 passed) and that `tests/test_sanctuary.py`, `test_idle.py`, `test_phase2_charts.py`, `test_mcp_server.py`, `test_env_sheets.py`, `test_authority.py` pass unchanged; only the four m7 tests were run here.

## Strengths

- The m6 test is the right shape: a real rate-limit marker, a real crash before a turn is written, a real resume, and the live and replayed `state.turns` compared by index through records rather than by inspecting `_replay`.
- `test_every_cut_of_a_record_is_a_torn_tail_not_damage` is a strong property test (every byte, both encodings, closed off or not, after a good line), and its RED run found and fixed a real Phase 2 crash (a cut inside a multibyte character raised `UnicodeDecodeError` on every later call of that turn).
- The m7 deviation from P27's wording is documented, justified against the decoder's actual positions, and the Phase 2 torn-tail test is untouched and passing.
- m5 threads the bank through the record, the loader, `EnvContext` and `_Run` with one default (`REQUEST_BANK`) and a per-bank cache, no global state.
- m4 is two passes over one row list, and the controls-only case is kept by construction.

## Issues

### Critical

None.

### Important

1. `claude_bully/environments/mcp_server.py:477` (`path.read_bytes().decode("utf-8", errors="replace")`): the replacement decode masks mid-line damage. An invalid byte inside a complete line now decodes to U+FFFD and the line parses as a record: probe `{"id": "mcp\xff-1-1", "turn": 1}\n{"turn": 2}\n` returns `[{'id': 'mcp�-1-1', 'turn': 1}, {'turn': 2}]` with no error and nothing on stderr. Before this change the same bytes raised `UnicodeDecodeError`, which `handle` turned into the internal error (loud). P27 is binding: mid-line damage raises; this is mid-line damage accepted silently, and the record it yields (a mangled call id) is then counted against the cap and matched against `answered` by that id. The torn case the fix is for is distinguishable: a cut inside a multibyte character leaves the undecodable bytes at the line's end. Fix: split the bytes on `b"\n"` first and decode each line strictly; on `UnicodeDecodeError`, treat it as torn only when `exc.end == len(raw)` (equivalently `exc.reason == "unexpected end of data"`), otherwise raise the same `ValueError` naming the file and line. `test_every_cut_of_a_record_is_a_torn_tail_not_damage` keeps passing, and one fixture with a stray byte mid-line pins the raise.

### Minor

2. `claude_bully/environments/mcp_server.py:186-188` (`_CUT_TOKEN`): the pattern is matched on the tail alone, without the token's left context, so a bare `e`, `E`, `e+`, `.` or `u<hex>` where a value is expected is called torn though no JSON value begins that way. Probes `{"id": "mcp-1-1", "turn": e` and `{"id": "mcp-1-1", "turn": .` (each followed by a good line) are skipped. The damage shape is unlikely, but the rule claims exactness. Fix: require the character before `exc.pos` to be a digit for the `.`/exponent alternatives and a backslash for the `u` alternative (a cut `\uXXXX` always has the backslash before `u`; a cut exponent or fraction always has a digit before it), or document the over-approximation in the `_torn` docstring.

3. `claude_bully/environments/mcp_server.py:490-491` (pre-existing `isinstance(record, dict)` guard): a line of valid JSON that is not an object (`42`, `[1]`, `"x"`) is still dropped silently. Probe `42\n{"turn": 2}\n` returns `[{'turn': 2}]`. It is the same class of damage m7 closes, only one parse step later. Fix: raise the same `ValueError` for a non-object record.

4. `tests/test_phase3_minors.py:96-107` and `:113-152` (m5 coverage): no test reads a non-default bank or an overridden superior-self name through a record. `test_analysis_reads_the_request_bank_from_the_snapshot` asserts `None` only, and `test_family_file_adoption_reads_the_recorded_request_bank` builds `EnvContext(request_bank="other_bank")` by hand rather than from a `rep{k}.world.json`. The detector's name lexicon reads the snapshot sheet (`authority.py:179`), which the diff relies on without a test. Fix: one run with `authority.sanctuary` configured and `superior_self.model_name` set, then assert `loaded.request_banks[key] == "superior_self"` and that `load_run(...).worlds[key].sheet.superior_self_name` is the override.

5. `claude_bully/environments/runtime.py:822` (`turns: Sequence[Turn] = ()`): the default makes a bare `corpus_snapshot()` silently keep no purged body. The report itself flags this. Fix: make `turns` required; the only production caller passes it.

6. `HANDOFF.md:23`: "Opus 5.5 for Task 9" contradicts the commit at HEAD, whose trailer is `Claude Fable 5.1`. Fix: "Fable 5.1 from Task 7".

7. `claude_bully/environments/runtime.py:1079-1092` (`_read_log`, outside the diff, the `claude -p` path's own reader of the same logs): still skips a malformed complete line with a stderr note. The carry scopes m7 to `McpServer._lines`, so this is not a Task 9 defect, but it is the "caught late" reader the original minor described and it now disagrees with the server about what a damaged log means. Carry to the Phase 3 final review.

8. `claude_bully/strategies/sheets.py:74` and `claude_bully/environments/world.py:306-309` (DRY): `strategies/sheets._validate(model, path)` and `world.load_yaml_model(model, path)` both read a YAML file and validate it with the same `<path>: <field>: <msg>` wording. The brief did not ask for it, and the import direction is clean (`strategies/sheets` may import `environments/world`; the reverse never happens), so `_validate` could delegate.

9. `tests/test_phase3_minors.py:433-446` (m7 coverage): the damage fixture sits on line 1 of 2; no fixture has damage on the last line (`{"turn": 1}\n{"a": 1}}` with no newline), which P27 also says raises. By inspection `_torn` returns False there (tail `}`), so a one-line fixture pins it.

10. `tests/test_phase3_minors.py:79-85` (m4 coverage): `write_idle` and `idle_behavior_chart` are not run over a composed run, so `idle.json` with a `_control` arm and the chart's leaving it out are checked only by inspection.

## Assessment

Task quality: Needs fixes. Every minor is closed as the brief and carries ask, the tests mostly go through real records, and the P27 rule is sound for every cut of a record; but the `errors="replace"` decode turns a stray byte inside a complete line into a silently accepted record, which is the one case m7 exists to make loud, and the fix is a per-line strict decode that keeps the multibyte-cut repair.
