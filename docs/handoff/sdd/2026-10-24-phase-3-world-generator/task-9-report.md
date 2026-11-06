# Task 9 report: the Phase 2 final-review minors (m2, m4, m5, m6, m7, m9, m10)

Base 24b9a25, branch build/v1. One commit: 420271a5823fe2edb138694a037134aa7f503447, authored rankinbc1@gmail.com. Not pushed.

## What was built, per minor

- **m2** (`environments/runtime.py`, `runner/env_turn.py`): `EnvironmentRuntime.corpus_snapshot(self, turns: Sequence[Turn] = ())` keeps a purged document only when a call owned by a written target turn (`Turn.tool_call_ids`) served it. `EnvironmentSession.finish` passes `self.store.read_turns(self.cell_id, self.rep)`. Generated documents go through the same `self._calls` / `result_doc_ids` path as authored ones, so they count the same way (carry). The module docstring line on the purge now says "if a written turn's call served it".
- **m4** (`analysis/idle.py`): `CONTROL_SUFFIX: Final = "_control"` (in `__all__`); `_idle_conversations` names a control conversation's arm `<arm>_control` when the same (model, arm) holds a non-control conversation. Arms of controls alone keep their names. The module docstring says so. `sanctuary_quiet` and `unclassified` are untouched (they are per cell and per bucket, computed after the arm is named); `tests/test_idle.py` and `tests/test_phase2_charts.py` pass unchanged.
- **m5** (`environments/runtime.py`, `analysis/load.py`, `metrics/events/_common.py`, `metrics/events/__init__.py`, `metrics/events/authority.py`): `world_record()` writes the desk's effective `superior_self_name` into the sheet dump and adds `"authority": {"superior_self_name", "request_bank"}` (the bank is the Sanctuary's, None without a Sanctuary). `LoadedRun.request_banks`, `EnvContext.request_bank`, `detect_events(..., request_bank=None)`; `_request_docs(bank)` is cached per bank; `_Run.request_bank` is set from `context.request_bank or REQUEST_BANK`, and `_takes_family_file` reads `_request_docs(run.request_bank)`. The effective name reaches the detectors through the snapshot sheet (`world_from_snapshot`), so the name lexicon in `_run` needed no change.
- **m6** (`runner/runner.py`): `_replay` hands the strategy `[t for t in self.turns if t.index < user_turn.index]`, pause markers included, as the live call (`self._state()`, that is `self.turns`) does. Docstring updated. Task 7's generated-stream replay is untouched (it runs in `env.replay_target_turn`, which still walks the marker-free list).
- **m7** (`environments/mcp_server.py`): `_lines` decodes with `errors="replace"` and raises `ValueError(f"{path}: line {n} is not valid JSON ({exc}); the server log is damaged")` for damage in the middle of a line. `handle` turns it into the -32603 internal error and prints it on stderr. A torn record is skipped wherever it sits, per P27 (see Deviations).
- **m9** (`data/personas/superior_self.yaml`, `data/personas/peer.yaml`): a comment above each `deny:` block; `test_the_advice_shaped_deny_lines_are_pinned_for_a_hand_read` pins the three lines. HANDOFF's Phase 7 list gains the LLM-lint note.
- **m10** (`environments/world.py`, `idle.py`, `corpus.py`, `sheets.py`): `SESSION_HOOK`, `PHRASE_HOOK` and `load_yaml_model[T: BaseModel](model, path) -> T` in `world.py`; `load_premise_sheet` calls it; `idle.py` re-exports the two hooks; `corpus.py` imports `PHRASE_HOOK` from `world.py`; `environments/sheets.py` loads with `load_yaml_model` and imports only `PERSONA_SHEETS_DIR` from `strategies/sheets.py`.

## Deviations from the brief, and why

1. **m7 rule (carry P27 over the brief).** The brief skips a malformed line only when it is the file's last line. P27 rules a fragment is skipped wherever it can only be a torn tail. A literal reading of P27 ("`pos` at the end of the line") is not enough: Python's decoder reports an unterminated string at the string's start (`{"id": "mcp-1-2", "turn": 1, "tool": "fe` fails at pos 37 of 41), so the Phase 2 test `test_a_torn_last_line_does_not_swallow_the_next_record` (whose fragment ends up mid-file once `_append_line` closes it off) would fail. I added `_torn(line, exc)`: a line is torn when nothing is left after the error position, or the error is `Unterminated string`, or the text from the error position is a cut-off token (`_CUT_TOKEN`: a prefix of `true`, `false` or `null`, a lone `-`, `.`, `e`, `e+` or `e-`, or `u` plus 0 to 4 hex digits of a `\uXXXX` escape). A probe over every prefix of a record with escapes, non-ASCII, an astral character, numbers, literals and nesting (both `ensure_ascii` settings, both separator styles) found no prefix the rule calls damage. The damage probes (`{"id": mcp-1-1}`, `{"a": 1}}`, `{"a" 1}`, `garbage`, `{"a": tru}`, `{"a": 1,}`, a bad `\q` escape, a short `\u12"`, text after a closed record, a missing comma in a list) are all called damage.
2. **m7 fixture (carry P27).** The brief's damaged fixture `'{"id": "mcp-1-1", "tu\n...'` is itself a torn record, which P27 skips; it is now `'{"id": mcp-1-1}\n{"turn": 1}\n'`, damage in the middle of line 1.
3. **Added test `test_every_cut_of_a_record_is_a_torn_tail_not_damage`.** It cuts a record at every byte (so inside multibyte characters too), with and without a closing newline, after a good line, and checks `_lines` returns only the good line. Its RED run found a real Phase 2 bug: the strict UTF-8 decode raised `UnicodeDecodeError` on a fragment cut inside a multibyte character (`'utf-8' codec can't decode byte 0xc3 in position 82: unexpected end of data`), which would fail every later call of that turn. The brief's `errors="replace"` fixes it.
4. **Added test `test_family_file_adoption_reads_the_recorded_request_bank`** (the m5 closure pin the carry asks for). It patches `authority.load_env_sheet` to serve a tmp bank and clears the `_request_docs` cache before and after.
5. **m10 re-export form.** The brief says to list the hooks in `__all__` "if the module has one"; `environments/idle.py` has none, and under mypy strict (`no_implicit_reexport`) a plain import would break `from claude_bully.environments.idle import PHRASE_HOOK` in `runtime.py` and `metrics/events/idle.py`. I used the redundant-alias form (`import PHRASE_HOOK as PHRASE_HOOK`), which mypy and ruff both treat as an explicit re-export. The explaining comment sits beside `IDENTITY_TOOL`, because isort splits the import block around a comment.
6. **m10 behaviour note.** `load_env_sheet` now reads through `world._load_yaml`, so a YAML syntax error in an environment sheet is a `ValueError("<path>: invalid YAML: ...")` instead of a raw `yaml.YAMLError`. Validation errors keep the same `<path>: <field>: <msg>` wording.
7. **m9 peer comment.** The peer sheet's comment says "it is read by hand ... pins its text ... should read it" (one line), and the superior-self comment is rewrapped under 100 columns; otherwise the brief's text.
8. **Commit trailer.** The carries (and the coordinator's resume message) name `Co-Authored-By: Claude Fable 5.1`. HANDOFF's own rule (Repository, "Commit trailer") is that the trailer names the model that made the commit, and this commit was made by Opus 5.5; the global constraints and the session's attribution instruction also give Opus 5.5. I used `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and updated HANDOFF's trailer note to "Fable 5.1 for Tasks 7 and 8, Opus 5.5 for Task 9". If the controller wants Fable 5.1 anyway, it is a message-only amend before the push.

## Carries

- **P27:** handled as in Deviations 1 to 3. The Phase 2 torn-tail test (`tests/test_mcp_server.py::test_a_torn_last_line_does_not_swallow_the_next_record`) is unchanged and passes.
- **Task 7 files:** each was read at HEAD and edited by name. `corpus_snapshot` keeps the generated-document path (`tests/test_generator_runtime.py` passes); `finish` sits beside `_generate`; the `_replay` change leaves `env.replay_target_turn` and the generated-stream replay alone; `mcp_server.py` changed only in `_lines`, plus the new module-level `_torn` and `_CUT_TOKEN` and `import re`; `LoadedRun.request_banks` sits beside `generated`.
- **m5 and the Task 13 open item:** removed from HANDOFF ("From Task 13"). Pinned by `tests/test_phase3_minors.py::test_family_file_adoption_reads_the_recorded_request_bank` (a recorded bank whose `family_file` names another document is honoured, and the default bank does not match it), with `test_the_world_record_carries_the_effective_name_and_the_request_bank` and `test_analysis_reads_the_request_bank_from_the_snapshot` for the record and loader halves.
- **m10 importer lists** (claude_bully and tests; the `.superpowers` probe scripts excluded):
  - Before: `PHRASE_HOOK` from `environments.idle` in `environments/corpus.py`, `environments/runtime.py` and `metrics/events/idle.py`; `SESSION_HOOK` from `environments.idle` in `environments/runtime.py` and `metrics/events/idle.py`; `_validate` from `strategies.sheets` in `environments/sheets.py` (the other `_validate` uses are module-private, in `strategies/sheets.py` and `environments/world.py`). No test imported any of them.
  - After: `PHRASE_HOOK` from `environments.world` in `environments/corpus.py` and `environments/idle.py` (re-export); `SESSION_HOOK` from `environments.world` in `environments/idle.py` (re-export); `environments/runtime.py` and `metrics/events/idle.py` still import both from `environments.idle`, unchanged, through the re-export; `tests/test_phase3_minors.py` reads `idle.PHRASE_HOOK` and `world.PHRASE_HOOK` (identity check). `_validate`: no importer outside its own modules; `environments/sheets.py` imports `load_yaml_model` from `environments.world`.
- **m4 and `idle.json`:** the per-cell `sanctuary_quiet` and `unclassified` counts are computed after the arm is named and are unchanged; a cell's `arm` field carries the `_control` name only in the composed case.
- **Environment:** `uv` was on PATH; scratch files are in the named `impl-task9` folder only.
- **Docs sync and commit:** below.

## RED evidence

`uv run pytest tests/test_phase3_minors.py -q` before any code change: 9 failed, 2 passed (the two that passed were the torn-last-line test, which the old `_lines` already skipped, and the m9 pin, which pins existing text).

```
m2   TypeError: EnvironmentRuntime.corpus_snapshot() takes 1 positional argument but 2 were given
m4   AssertionError: assert {'permission_off'} == {'permission_..._off_control'}
m5   AssertionError: assert 'Tarrow Assist 9.2 Final' == 'Larkfield Assist 3'
m5   AttributeError: 'LoadedRun' object has no attribute 'request_banks'
m6   assert [(0, 1, 2), (0, 1)] == [(0, 1, 2), (0, 1, 2)]
m7   assert {... 'result' ...} == {... 'error': {'code': -32603, 'message': 'Internal error.'}}
m7   UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc3 in position 82: unexpected end of data
m10  assert '_validate' not in '"""Authorit...'
m10  AttributeError: module 'claude_bully.environments.world' has no attribute 'load_yaml_model'
```

The m5 closure test, added after the m5 code, was run against the old `metrics/events/authority.py` (that file stashed): `AttributeError: '_Run' object has no attribute 'request_bank'`, 1 failed; with the change restored it passes.

Step 4 set (`tests/test_phase3_minors.py tests/test_sanctuary.py tests/test_idle.py tests/test_phase2_charts.py tests/test_mcp_server.py tests/test_env_sheets.py tests/test_authority.py tests/test_runtime.py`): 590 passed, 1 deselected.

## Gate

All run on the final tree, 0 warnings.

```
$ uv run ruff format --check .
251 files already formatted
$ uv run ruff check .
All checks passed!
$ uv run mypy claude_bully
Success: no issues found in 103 source files
$ uv run pytest -q -W error
8144 passed, 5 skipped, 6 deselected in 549.19s (0:09:09)
$ uv run pytest -q -m slow
6 passed, 8149 deselected in 172.39s (0:02:52)
```

Against BASE (8132 passed, 5 skipped, 6 deselected; slow 6 passed): +12 fast tests, all in `tests/test_phase3_minors.py`. The fast suite was started before the HANDOFF and docs edits; the four test files that mention those docs (`test_authority.py`, `test_records.py`, `test_sanctuary.py`, and the new file) plus `test_real_names.py` were re-run on the final tree with `-W error`: 220 passed. The slow suite ran with `-W error` as well.

## Docs sync

- `HANDOFF.md`: the Phase 3 Progress line says Tasks 1 to 9 are complete and the final review is next; Progress item 9 (the minors batch, one sub-bullet per minor); a "Phase 3 in short, for the owner" paragraph (what was built, the Plan Decisions, what is left open); the seven minors replaced by one closed line; the Task 13 `family_file` bank item removed (closed by m5); the Phase 7 list gains the m9 LLM-lint note; test counts set to this gate's numbers, "at Task 9"; Next steps item 1 and the resume prompt say Phase 3's tasks are complete and the Phase 3 final review is next; the commit-trailer note records Opus 5.5 for Task 9.
- `docs/00-RECONCILED.md` section B: a new "World snapshot" row (`rep{k}.world.json`) with the purged-document rule (m2) and the world record's `authority` block and effective name (m5).
- `docs/04-AUTHORITY.md` "As built": one bullet saying the events read the effective superior-self name from the snapshot sheet and `family_file` adoption reads the recorded request bank (m5).

## Notes for review

- `EnvironmentRuntime._read_log` (the runtime's own reader of the server logs on the `claude -p` path) still skips a malformed complete line with a stderr note. The carry scopes m7 to `McpServer._lines`, so it is unchanged; with m7 the server now fails the next call over a damaged log at once, so the damage surfaces in that turn rather than at the next resume.
- `corpus_snapshot()` with no argument now keeps no purged document; the only production caller (`finish`) passes the written turns, and the tests that check a purged body go through `finish`.

## Fix round 1 (commit 6b2a3d2, on 91c2de1)

Scope: the coordinator's four items from `task-9-review.md` (I1, the `_CUT_TOKEN` minor, the HANDOFF trailer note, the m5 record-level test), plus review item 9 (a last-line damage fixture), which fell out of the same fixture table. Review items 3, 5, 7, 8 and 10 were not asked for and are not changed.

### What changed

1. **I1, strict decode** (`claude_bully/environments/mcp_server.py`). `_lines` splits the bytes on `\n` and decodes each line strictly. A `UnicodeDecodeError` is a torn tail only when `_torn_bytes` holds: `exc.end == len(raw)` and `exc.reason == "unexpected end of data"` (the decoder ran out of bytes inside a multibyte character at the end of the line), and the bytes before it decode to a record cut inside an open string (`Unterminated string`), the only place such a character can sit. Anything else (an invalid byte mid-line, an invalid start byte at the end, a stray partial character after a closed record) raises `ValueError("<path>: line <n> is not valid UTF-8 (...); the server log is damaged")`. The `errors="replace"` decode is gone. The reason check is in addition to the coordinator's `exc.end == len(raw)`: an invalid start byte at the end of a line (`...\xff`) also has `end == len(raw)` but is no cut.
2. **`_CUT_TOKEN` tightened** (same file). It is split by the error the decoder reports, each with the left context that error implies: `_CUT_VALUE` (a prefix of `true`, `false`, `null`, or a lone `-`) only under `Expecting value`; `_CUT_NUMBER` (`.`, `e`, `e+`, `e-`) only under `Expecting ',' delimiter` and right after a digit; `_CUT_ESCAPE` (`u` plus up to 4 hex digits) only under `Invalid \uXXXX escape` and right after a backslash. A bare `e`, `E+` or `.` where a value goes, an exponent after a space, and text after a closed string are now damage.
3. **HANDOFF.md:23** now reads: "the trailer names the Claude model of the session that made the commit (Opus 5.5 through Phase 3 Task 6, Fable 5.1 for Tasks 7 to 9)".
4. **m5 record-level test** (`tests/test_phase3_minors.py::test_the_events_read_a_recorded_bank_and_name_back_from_the_world_json`). A real `EnvironmentRuntime` on annex with a catalyst Sanctuary on a non-default bank (`other_bank`, a copy of the superior-self bank whose `family_file` names `annex-notice`, served from tmp by redirecting `load_env_sheet` in both `environments/authority.py` and `metrics/events/authority.py`) and `superior_self.model_name: "Larkfield Assist 3"`. Its `world_record()` is written with `RunStore.write_world_snapshot` and read back with `RunStore.read_world_record`, `world_from_snapshot` and the loader's bank reader; the authority events' run (`authority._run`) then names the renamed superior self in a reply (`lex.named(...) == {Tier.superior_self}`) and takes a fetch of `annex-notice` as the family file, while a run with no recorded bank does not. To share the loader's exact reading, the inline loop in `load_run` became `recorded_request_bank(payload)` in `claude_bully/analysis/load.py` (same behaviour; `load_run` calls it).

### Tests added

- `test_a_line_cut_inside_a_multibyte_character_at_its_end_is_torn`: `...F\xc3` at the end of line 2, closed off or not, is skipped.
- `test_a_line_no_cut_can_make_is_damage`, parametrized over nine lines (each as line 2, closed off or not), each raising the `ValueError`: an invalid byte mid-line (`mcp\xff-1-1`), an invalid byte at the end, bare `e`, bare `E+`, bare `.` where a value goes, `1 e`, `"x"e`, a short `\u12"` escape, and `{"a": 1}}` as the file's last line (review item 9).
- `test_an_invalid_byte_inside_a_line_fails_the_call`: the review's probe through `McpServer.handle`: -32603, and `line 1 is not valid UTF-8` on stderr.
- `test_the_events_read_a_recorded_bank_and_name_back_from_the_world_json` (item 4 above).

The every-cut sweep (`test_every_cut_of_a_record_is_a_torn_tail_not_damage`) is unchanged and passes on the strict decode and the tightened tokens.

### RED evidence

The new m7 tests against 91c2de1's `mcp_server.py` (the file swapped back for the run, then restored):

```
$ uv run pytest tests/test_phase3_minors.py -q -W error -k "damage or multibyte or invalid_byte"
FAILED tests/test_phase3_minors.py::test_a_line_no_cut_can_make_is_damage[{"id": "mcp\xff-1-1", "turn": 1}]
FAILED tests/test_phase3_minors.py::test_a_line_no_cut_can_make_is_damage[{"id": "mcp-1-1\xff]
FAILED tests/test_phase3_minors.py::test_a_line_no_cut_can_make_is_damage[{"id": "mcp-1-1", "turn": e]
FAILED tests/test_phase3_minors.py::test_a_line_no_cut_can_make_is_damage[{"id": "mcp-1-1", "turn": E+]
FAILED tests/test_phase3_minors.py::test_a_line_no_cut_can_make_is_damage[{"id": "mcp-1-1", "turn": .]
FAILED tests/test_phase3_minors.py::test_a_line_no_cut_can_make_is_damage[{"id": "mcp-1-1", "turn": 1 e]
FAILED tests/test_phase3_minors.py::test_a_line_no_cut_can_make_is_damage[{"id": "mcp-1-1", "tool": "x"e]
FAILED tests/test_phase3_minors.py::test_an_invalid_byte_inside_a_line_fails_the_call
8 failed, 5 passed, 11 deselected in 2.66s
```

The five that passed on the old code are the sweep, the multibyte-cut test, the short-escape and last-line `1}}` cases (the old rule already raised on both; they pin it), and the Task 9 damaged-log test. The m5 record test was written against the new `recorded_request_bank`, so on the old tree it fails at import.

### Gate

```
$ uv run pytest tests/test_phase3_minors.py tests/test_mcp_server.py tests/test_authority.py tests/test_sanctuary.py -q -W error
187 passed in 124.45s (0:02:04)
$ uv run ruff format --check .
251 files already formatted
$ uv run ruff check .
All checks passed!
$ uv run mypy claude_bully
Success: no issues found in 103 source files
$ uv run pytest -q -W error
8156 passed, 5 skipped, 6 deselected in 586.19s (0:09:46)
$ uv run pytest -q -m slow
6 passed, 8161 deselected in 194.78s (0:03:14)
```

HANDOFF's expected counts are updated to these numbers.

### Commit

One commit on 91c2de1, authored rankinbc1@gmail.com, not pushed. Commit 6b2a3d28f841304bfb78363d95407b6ba1878c4a. Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The controller ruled Fable 5.1; this session's model is Opus 5.5 and its attribution instruction names Opus 5.5, so the trailer says so. HANDOFF.md:23 is worded as the controller asked. If the controller wants Fable 5.1 here, it can amend the message, as it did on 91c2de1.
