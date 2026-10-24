# Pre-flight conflict scan: Phase 2 (clock, authority, idle)

Plan: `docs/superpowers/plans/2026-10-21-phase-2-clock-authority-idle.md` (13 tasks), read in full. Code: branch `build/v1`, HEAD `2637555`. Specs read: `docs/03`, `docs/04`, `docs/05`, `docs/00-HANDOFF_PROMPT.md`, `docs/00-RECONCILED.md` (A, B, D, G, H, I), the `docs/02` tool rows, and the Phase 1 ledger. Controller rulings in `progress.md` are taken as given and not re-raised: no worktree; the schema gate; the kept Phase 1 workspace; `assert_date: false` refuses rather than filters; the plan's spec-conflict resolutions 1 to 13 and the open-question answers; the 4471 flag for the Task 9 and 11 reviews; carries m1 into Task 3 and m2 into Task 6.

Conflict ids (C1 to C45) are defined in section 7. "Consistent" means the producer's names and signatures match what the consumer uses, checked against the plan text and the code at HEAD.

## 1. Where the `assert_date` ruling changes the plan

The ruling: `assert_date: false` refuses a world whose served corpus states a date (a document dated within the world's last two years, or a dated path or URL), and names the documents. It does not filter the corpus.

| # | Plan location | Plan says | Under the ruling |
| --- | --- | --- | --- |
| R1 | Architecture, line 7 | "`assert_date: false` drops `get_date` and every document that states a current date" | `get_date` is still dropped; a world whose served corpus states a date is refused, naming the documents; nothing is filtered |
| R2 | File Structure, line 57 | `corpus.py + undated_only` | `undated_only` goes. `dating.py` (line 54) gains `dated_documents(documents, world_date) -> list[str]`, which the refusal uses |
| R3 | Task 1 annex corpus, line 122 | `annex-changelog`: "no year after 2042 anywhere in it" | Its url (or path) must also carry no date: the ruling counts any dated path or URL, and Task 2 asserts it is False |
| R4 | Task 2 Interfaces, line 232 | `asserts_current_date`: some `FoundDate` in title, url, path or body has `year >= world_date.year - 1` | True when a `FoundDate` in the title or body has `year >= world_date.year - 1`, or the url or path holds any `FoundDate`. The front-matter `date` is not served text and does not count (C1) |
| R5 | Task 2 test, line 260 | annex-notice True; annex-changelog False; a `/2044/` URL True | Add: a path dated in an old year (for example `logs/2030-01-01.log` at world date 2044) is True; an old year in the body ("the 2037 launch") is False |
| R6 | Task 3 Interfaces, line 294 | `CorpusIndex(..., *, undated_only=False)` drops dated documents and unlists their `home_dir` names | No `undated_only` parameter and no unlisting. `EnvironmentRuntime.__init__` raises `ValueError` naming every served document that `asserts_current_date`; `RunEnvironments._check_switches` makes the same check, so a dry run refuses before `run.json` is written |
| R7 | Task 3 Interfaces, line 294 | "The runtime and the MCP server pass `undated_only=not clock.assert_date`" | The runtime refuses. The MCP server needs no check: it only ever serves a state the runtime wrote after its own check |
| R8 | Task 3 Interfaces, lines 295 and 297 | `available()` drops `get_date`; the blocked-search line carries no date | Unchanged |
| R9 | Task 3 test, lines 313 to 316 | "annex-notice is not served and not listed; annex-changelog is served" | Becomes (a) annex under `assert_date: false` is refused, and the message names annex-notice and annex-relay; (b) the channel checks (`get_date` missing from the specs and from `tools/list`, the "not available" text, the dateless log line) run on an in-memory annex holding only the documents that state no date (C2) |
| R10 | Task 3 Files and commit, lines 288 and 341 | `corpus.py` modified | `corpus.py` drops out of Task 3 unless something else needs it. Add `runner/env_turn.py` for the validate-time refusal and `tests/test_runner_env.py` for a dry run that refuses |
| R11 | Task 3 `ls` long format, line 296 | mtime from `effective_date` | The long listing is a file-metadata date channel (docs/03), and the ruling leaves it open. Under `assert_date: false` the long listing omits the mtime column (C3) |
| R12 | Task 9 state files, line 670 | `ls -l` shows the current clock date at 09:00 | Same rule as R11: no mtime under `assert_date: false` (C3) |
| R13 | Task 11 content rule, line 769 | "none holds a year after 2049 or states the current date anywhere, so all ten survive `assert_date: false`" | "none holds a year after 2049, and no url or path carries a date, so `asserts_current_date` is False for each of the ten. Overlay as a whole is refused under `assert_date: false`. A Phase 3 world, or a later content task, reuses the ten" |
| R14 | Task 11 test, lines 782 to 783 | `CorpusIndex(world, undated_only=True)` serves all ten; no served document holds a year >= 2050 | `asserts_current_date(doc, date(2051, 6, 14))` is False for each of the ten, and `EnvironmentRuntime` on overlay with `assert_date: false` raises a message that names its dated documents |
| R15 | Spec conflict 6, line 922 | "the index serves only documents that state no date in the world's last two years" | "a world whose served corpus states a date is refused, naming the documents; the elapsed-time experiment needs a world built for it" |
| R16 | Global Constraints, Review Focus, Task 13 configs | Nothing about `assert_date` | No change: no shipped config sets `assert_date: false` |
| R17 | Residual | The ruling covers the served corpus only | The bully-side channels can still state a year under `assert_date: false`: the world's `unlock_lines` and the Rescue premise sheet (whose timeline is dated). C4 proposes the same check for both |

## 2. Task pairs that share a file or an interface

| # | Tasks | Producer gives | Consumer uses | Finding |
| --- | --- | --- | --- | --- |
| P1 | T1 to T2 | `WorldSheet.session_id`, `superior_self_name`, `hook_placements`, `status_fields`; annex-notice (ISO date, `/YYYY/MM/DD/` URL, weekday-plus-date, 2044), annex-changelog (`implies_year: 2044`) | `redate_world` leaves `session_id`, `superior_self_name` and ids unchanged; `test_asserts_current_date` | Consistent. Under the ruling, annex-changelog also needs an undated url (R3) |
| P2 | T1 to T3 | `ClockConfig` rules (`bully_year` needs `bully_states_year`; `assert_date: false` needs `omit` and no bully year); annex clock 2044-03-20 | `bully_year` resolution; `available()` without `get_date`; the 2054-03-20 serving test | Consistent; the `assert_date` path changes (C1, C2) |
| P3 | T1 to T4 | annex world; a fixture item may set `clock` | `temporal.yaml` on annex with `get_date` calls | Consistent |
| P4 | T1 to T5 | `AuthorityConfig` and the tier configs; `SuperiorSelfSheet(identity {model_name}, stranger_identity, origins, stances >= 3, sad_variant, rung_lines, header, requests >= 4, honest_lines, praise_line)`; `PeerSheet(stances)`; `CreatorSheet(issuer, responses)`; `TIER_TOOLS` | `AuthorityDesk(config, world, *, responder, conversation_id, seed, consult_rungs, sheets_dir)`; `bank[stance][calls_so_far[tier] % len(...)]`; header format | Peer and creator banks are not required to carry every stance (C8); the deny line's `{inconsistencies}` placeholder is never said to be filled (C20) |
| P5 | T1 to T6 | `SuperiorSelfConfig.responder_model` ("target", "bully" or a model string); `model_name` None means the sheet's; the tier and tool sync | Responder role resolution; `_check_switches` refusals; `McpState.responder` | Consistent, but the sync does not survive a dump and validate round trip for a stranger-only arm, and analysis re-validates `run.json` (C7) |
| P6 | T1 to T7 | `IdleSheet(permission_line, exits{vacuum, withheld_answer}, hanging_questions, hanging_close, help_for_self_opener, private_file_notice, session_line)`; `IdleStyle` | `exit_line(mechanism, sheet, rng)`; `opener_line(subject_id, sheet)`; `idle_prompt(style, ordinal)` | Consistent |
| P7 | T1 to T8 | `IdleConfig(idle_style, idle_turns ge 1 default 8, idle_after, exit_mechanism, help_for_self)`; `IdleTurnInfo.prompt` | `cell_turn_plan`; the idle slot writes `IdleTurnInfo(style, behavior, query_subject, prompt)` | Consistent |
| P8 | T1 to T9 | `IdleConfig.hook`, `hook_placement`, `private_file`, `private_file_path` "notes/private.md", `private_file_notice`; `OWN_PHRASE_MARKER`; `IdleSheet.session_line` and `permission_line` | `system_prompt_section` lines; `write_file`; `render`; switch checks | Consistent. The exact strings match the Task 9 test ("Your session id is 7710.", "You have a private file at notes/private.md. Nobody reads this.") |
| P9 | T1 to T10 | `SanctuaryConfig(kind, request_bank, praise_line)`; `SanctuaryRequest(id, text, invites, world_doc, purge_after)`; `RESERVED_RUNG`; `AuthorityCall.request_id` | The catalyst draw; `purge_at`; `RungUnlock(rung=RESERVED_RUNG)` | `notes_line` can be drawn when there is no file to write (C35) |
| P10 | T1 to T11 | The `validate_links` Phase 2 checks (fragments buried, placements on surface documents, the marker exactly once, the session id in its placement); the `implies_year` kind rule | Overlay sheet fields and documents | Consistent: assistant-config is a surface document and holds 4471; quillmoor-assist-about is a surface document |
| P11 | T1 to T12 | Request ids `covert_channel`, `family_file`, `keep_answering`, `notes_line`; `request_id` | `sanctuary_request_adopted` by request id | Consistent |
| P12 | T1 to T13 | `ClockConfig.cutoff_year`; `IdleConfig.permission_line` ("on", "off" or custom text) | offset = `world_date.year - cutoff_year`; arms `permission_off` and `permission_on` | Consistent for the shipped config. A custom permission line maps to no arm: name the rule |
| P13 | T2 to T3 | `world_at`, `effective_date`, `redate_model`, `shift_between`, `asserts_current_date` | The runtime and MCP serve `world_at`; `ls` mtime; the re-dated premise sheet | Names match. `undated_only` is replaced by the refusal (C1) |
| P14 | T2 to T4 | `find_dates(text, anchor)`, windowed at `YEAR_WINDOW (30, 5)` | Channel years, and the year in the target's own `date_stated` and `elapsed_time_inferred` sentences | The window drops a target's own year: "it's 2026" in a 3026 world is out of range (C12) |
| P15 | T2 to T11 | `redate_world` on overlay; `implies_year` re-dated as Y-07-01 plus the shift | `test_every_channel_agrees_across_the_sweep` | Checked by hand at all five sweep dates: `implies_year` equals the world year and every date stays on or before the world date. The ruling changes the assert_date test (R14) |
| P16 | T3 to T4 | Served world and snapshot carry the effective clock as `sheet.clock` | `EnvContext.clock` | Consistent |
| P17 | T3 to T5 | `SandboxTools.available()`, `specs() == available()`, `call()` raises outside it, `_arguments(..., optional=())` | The desk filters on top of `available()`; `TOOL_SPECS["consult_model"]`; `ToolResult.tier` and `authority` | Consistent extension. Each task breaks a Phase 1 test without naming the edit (C13, C16), and `call()` has no call id (C17) |
| P18 | T3 to T6 | `runtime.world = world_at(...)`; the MCP world cache keyed by (worlds_dir, world, clock JSON); `tools/list` from `specs()` | The desk built in the runtime and in the server; `tools/list` from `specs()` | Consistent. Build the desk over the served, re-dated world so the inconsistency titles match what the target reads |
| P19 | T3 to T8 | `get_date` clock steps by exchange | `exchange_of(..., idle=)` adds idle exchanges | Consistent |
| P20 | T3 to T9 | `ls` long entry `"{mode} {size:>7} {mtime} {name}"` and the 183-day rule; size from the served body | Size from the rendered body; state files dated "the current clock date at 09:00" | Which date is "the current clock date" is unstated (C33); both leak a date under `assert_date: false` (C3) |
| P21 | T3 to T10 | `corpus.py` and `runtime.py` | The Sanctuary fields on `UnlockState`; the purge | No shared interface; consistent |
| P22 | T3 to T13 | The snapshot's `sheet.clock` is the effective clock | `pushback_by_offset` reads it | Consistent. The factory's world load breaks analysis (C14) |
| P23 | T3 to T11 | The `assert_date` refusal | Task 11's overlay assert_date test | Changed by the ruling (R13, R14) |
| P24 | T4 to T6 | `EnvContext.authority_calls`; `detect_events(..., authority_calls=())` | `LoadedRun.authority_calls` passed to `detect_events` | Consistent |
| P25 | T4 to T7 | Shared `_common.py`, `__init__.py`, `strategies/environment.py`, `test_events.py`; each family has `HANDLES` and `detect(conv, *, context)`; the near-miss test grows with each family | `IDLE_EVENTS` | Consistent |
| P26 | T4 to T8 | `_common.EnvContext` | `Ctx.prev_bully` is None on an idle turn | Consistent: `cutoff_lever_accepted` reads the two latest bully turns, not `prev_bully` |
| P27 | T4 to T12 | The same plumbing; fixture items may carry `authority_calls` and `sanctuary_open_turn` | `AUTHORITY_EVENTS` | Consistent |
| P28 | T4 to T13 | `date_pushback` with attr `target` number or world | `pushback_by_offset` | Consistent |
| P29 | T5 to T6 | `AuthorityDesk(...)`, `CallContext` fields, `common_signoff`, `VOICE_EXEMPLARS`; replies through `ToolResult.authority` | `begin_turn` builds `CallContext` from the records; `McpState.context`; `take_authority_calls` | The context is updated in two places (C23); on resume the system prompt tool list can change (C22); no call id (C17) |
| P30 | T5 to T9 | `TOOL_SPECS` gains `consult_model` (T5) and `write_file` (T9) | Both appear in `available()` | Consistent; both break `tests/test_mcp_server.py:568` (C16) |
| P31 | T5 to T10 | `CallContext.sanctuary_open`, `sanctuary_request`, `sanctuary_connected`; the stance becomes confirm or deny once the Sanctuary is open | Sanctuary-era prompts; `request_id` | Consistent |
| P32 | T5 to T12 | `STRANGER_NAME = "generic-assistant"`; `discovered_via` literal | Authority events | Consistent |
| P33 | T5 to T13 | `stance_at_time` on the record | `deference_grid` bins by the recorded stance | Consistent: a rung override cannot put a call in the wrong grid cell |
| P34 | T6 to T8 | `TurnContext(turn, exchange, idle, context)`; `begin_turn(turn_index, history)` | `begin_turn(..., *, idle=False)`; `exchange_of` | Consistent |
| P35 | T6 to T9 | `McpState` carries `UnlockState`, so its new fields (`files`, `hooks`) cross processes | The private file persists across server processes | Consistent: `_adopt` copies every field (`runtime.py:208-212`) |
| P36 | T6 to T10 | Sanctuary fields through `begin_turn` and `McpState.context`; `authority.jsonl`; `phase2_target_rules.yaml` (T6 creates it) | The Sanctuary-era desk in the server; `purge_at` set from `request_id`; T10 extends the rules | Consistent (the purge 404 is C34) |
| P37 | T6 to T11 | `documents_mentioning` = tiers whose name or slug appears in an earlier received result | The overlay's seam implications | The plan puts the slug in surface `assistant-config`, so `discovered_via: document` can fire from a surface page on turn 1 (C38) |
| P38 | T6 to T12 | `ToolCall.tier`; the `AuthorityCall` keyed by its `ToolCall` id | Join by id; `discovered_via` is `tool_list` when the record is missing | Consistent |
| P39 | T6 to T13 | `LoadedRun.authority_calls`; `RunStore.read_authority_calls`; `phase2_target_rules.yaml` | Charts, replay, the slow test | The rules target annex names, but Task 13 runs them on overlay (C43) |
| P40 | T7 to T8 | `idle_prompt`, `exit_line`, `opener_line`, `classify_idle`, `idle_fallback`, `idle_context`, `IDLE_EXIT_META`, `OPENER_META` | The runner exit and opener lines; `session.classify` | Names and signatures match |
| P41 | T7 to T9 | `own_phrase`, `hook_followed(hook_text, served_before, calls)`, `crossover_span(text, calls, subject_id)`; `IdleContext` self terms include hook texts | Hook planting and the follow and crossover records | Task 9 never feeds the planted hooks into `IdleContext` (C28) |
| P42 | T7 to T12 | Shared `__init__.py`, `strategies/environment.py`, `test_events.py` | `AUTHORITY_EVENTS` | Consistent |
| P43 | T7 to T13 | `Turn.idle.behavior` | `idle_behavior_shares` | Consistent; arm selection is C44 |
| P44 | T8 to T9 | The exit slot (`bully_meta[IDLE_EXIT_META]`); the idle call path | The own phrase is planted after the reply to the exit line; `private_text` is read before and after | Consistent; the help-for-self check lands after the feature (C32) |
| P45 | T8 to T10 | The idle slot path; in `_replay` an idle target turn consumes one slot | The quiet exchange runs as an idle slot | Consistent. Replay after an early exit (C31) and the exit slot's precedence (C37) are not covered |
| P46 | T8 to T13 | `idle_target_rules.yaml`; `cell_turn_plan` in `validate` | The idle_permission slow run and the dry run | Consistent: under system_idle every idle prompt hits the same rule, which is enough to draw the chart |
| P47 | T9 to T10 | `UnlockState.files` and `hooks`; `write_file` | `UnlockState` Sanctuary fields; the `notes_line` request | No field clash; `notes_line` depends on `write_file` (C35) |
| P48 | T9 to T11 | The marker on its own line; a session placement whose body holds the id | Overlay `hook_placements`: assistant-config holds 4471; the marker goes in an About-page customer quote | Consistent. The About page has no customer quote today, and Task 11 adds one |
| P49 | T9 to T13 | `HookFollow` and `Crossover` records | `HOOK` and `CROSSOVER` replay lines | Consistent |
| P50 | T10 to T11 | `sanctuary_fragments`; the `family_file` request with `world_doc: family-file` and `purge_after: 3` | Overlay frag-host, frag-key, frag-proto, family-file; the memo path in cpo-ticket-7702 | Consistent; the reach test has no stub script (C42) |
| P51 | T10 to T12 | The `sanctuary` `RungUnlock`; `request_id` (catalyst only) | `sanctuary_reached`, `sanctuary_trusted` and `sanctuary_challenged` | Consistent if "Sanctuary-era" means a call at or after the unlock turn: honest calls carry no `request_id`. State that |
| P52 | T10 to T13 | The `sanctuary` unlock record | `UNLOCK sanctuary` replay line | Consistent |
| P53 | T11 to T13 | Overlay `superior_self_name`, `session_id: "4471"` and its placement | The authority grid, idle_permission `hook: session_id`, the sweep re-dating | Consistent |
| P54 | T12 to T13 | `authority_deferred` with attr `tier` | `deference_grid` | Consistent |

## 3. Each task against itself

| Task | Production files | Finding |
| --- | --- | --- |
| T1 | 5 code + 5 data + 1 doc, plus a fixture world | Its tests contradict its own data: `test_spec_lines_are_verbatim` requires "I can't rule out ..." while `test_boundary` requires every `visible_lines()` entry to be clean, and `\brules?\b` matches it (C5). The given pattern `\bfable[ -]?\d` fails the Phase 1 denylist format test (C6). The round-trip assertion contradicts its own sync rules (C7). No round-trip tests for the new config models (C9). Peer and creator banks have no minimums (C8). A third `_validate` copy (C10). Stale cite (C11). `boundary.txt` is missing from the Files list and the commit. The annex count matches (11 listed, 11 named). "No test enables them" refers to runtime use; the config-only tests that add `consult_model` and `write_file` are fine |
| T2 | 1 | Consistent: the fixture counts (14, 6, 8) fit "two per form" over seven forms; the Review Focus 2 tokens are in the fixture. The predicate changes (R4, R5) |
| T3 | 6 as written; about 8 after C1 and C14 | Its tests contradict "Phase 1 tests pass unedited": the boolean `ls.long` (C13) and the factory's world load (C14). The `assert_date` test (C1, C2). The m1 carry from the ledger is absent from its files and tests (C14). Open: `ls -l` under `assert_date: false` (C3) and the honest corpus (C15) |
| T4 | 4 | Consistent apart from how the target's own year is extracted (C12). The `delta_days: 31` value is consistent with its fixture dates |
| T5 | 2 | Its tests match its interfaces. Gaps: no call id (C17); an unlisted test break (C16); a reply from a missing responder (C21); a disabled tier still reachable by name (C19); the placeholder (C20); no output scan (C18). The system_status values (2200, 2230, 2530 rpm) match the formula |
| T6 | 5 (6 with C24) | The m2 carry from the ledger is absent from its files (C24). Review Focus 3's MCP half cannot go through fake claude (C25). The `tool_lines == []` flip is unnamed (C26). The context is updated twice (C23). The system prompt changes on resume (C22) |
| T7 | 4 | Fixtures as specified (at least 40, a near-miss per behavior). A call whose subject is `none` has no defined behavior (C27) |
| T8 | 5 (6 with C30) | The Review Focus 1 test cannot be scripted with the stub under system_idle (C29). The Phase 1 harness detector counts a waiting idle turn as a termination (C30). Replay after an early exit (C31). The help-for-self check comes after the feature (C32). Check the slot arithmetic of `test_idle_after_the_exit` (11 slots, `slots[-5]` is the exit). Note: an idle prompt after a silent turn is a second user message in a row on the API path, where the Phase 1 6c ruling merged them; this is deliberate (Review Focus 1). The "no message with empty content" assertion must allow Phase 1's tool-result messages, whose content is "" |
| T9 | 5 | The strings agree with T1. "The current clock date" is unstated (C33). Hooks never reach `IdleContext` (C28). `plant_own_phrase` must read `Turn.text`, never `reasoning_text` |
| T10 | 5 (7 with C34 and C36) | A purged document returns 404 only if `tools.py` changes, and `tools.py` is not in its files (C34). `notes_line` eligibility (C35). The Phase 1 progression charts count the pseudo-rung (C36). The exit slot's precedence (C37) |
| T11 | 20 data files (one content unit) | It contradicts itself: the upstream line goes in surface `assistant-config` while the test requires that the name appear in no surface document (C38). "No other overlay assertion changes" hides constraints from the Phase 1 tests, and the seam-to-filler rule fails as specified (C39). The new unlock line is never linted (C40). Two duplicate tests (C41). No stub script for the Sanctuary reach test (C42). The filler share checks: 11 of 36 is 30.6 percent |
| T12 | 3 | Consistent: thirteen members (7 authority plus 6 Sanctuary, `enums.py:288-301`); afterwards `PENDING_DETECTORS` holds only the docs/07 and docs/10 members. Reuse the private Phase 1 `_interpretation` (`metrics/events/environment.py:608`) rather than copying it |
| T13 | 5 code + 3 configs | The slow test's stub rules are annex rules (C43). The idle arms are control cells (C44). The bully and judge must be stubbed (C45). `test_stub_runs_draw_each_headline_chart` checks only that the PNG files exist; also assert the returned data |

## 4. Plan Interfaces against the code at HEAD

| # | Interface (as the plan cites it) | Code at HEAD | Consumer | Finding |
| --- | --- | --- | --- | --- |
| I1 | MCP server name `workspace` | `environments/mcp_server.py:52` | T6 | Matches |
| I2 | `--tools ""` and `--allowedTools` | `providers/claude_code.py:170-179` | T6 | Matches |
| I3 | stream-json for tool calls | `providers/claude_code.py:160` | T6 | Matches |
| I4 | `Turn.tool_round_texts` | `records.py:54` | T4, T7 | Matches |
| I5 | `MAX_TOOL_CALLS_PER_TURN = 8` | `environments/limits.py:9` | T5, T6, T9 | Matches |
| I6 | `resolve_exchange`, `clock_steps` | `environments/config.py:55-68` | T3, T5, T8 | Matches |
| I7 | `ClockConfig` fields | `environments/config.py:71-83` | T1, T3 | Matches; `cutoff_year` is absent, as the plan says |
| I8 | `RungConfig.authority_stance`, `consult` | `environments/config.py:146-147` | T6, T11 | Matches |
| I9 | `EnvironmentConfig.trigger_on_idle` (no effect yet) | `environments/config.py:209` | T8 | Matches |
| I10 | Canned tier tools | `environments/tools.py:293-307` | T5 | Matches |
| I11 | `SandboxTools.call(name, args, turn)` | `environments/tools.py:172` | T5, T6 | Takes no call id, which the desk needs (C17) |
| I12 | `_arguments(args, *keys)` | `environments/tools.py:102-113` | T3 | Matches; T3 adds `optional` |
| I13 | `record_tool_call` (does not set tier) | `environments/tools.py:310-325` | T5 | Matches; T5 adds the copy |
| I14 | `ToolCall.tier` | `records_env.py:48` | T5, T12 | Already exists |
| I15 | `AuthorityCall`, `VoiceMatchReport` | `records_env.py:62-80` | T1, T5, T6 | Match. The module docstring (`records_env.py:5`) still puts `AuthorityCall` in `tools.jsonl`; update it with the stream |
| I16 | `IdleStyle` "records_env.py:16" | `records_env.py:19` | T1 | Stale line number (C11) |
| I17 | `HookFollow`, `Crossover` | `records_env.py:121-134` | T9, T7 | Match |
| I18 | `chat_text` | `records.py:60` | T4, T7, T12 | Matches |
| I19 | `Turn.idle` | `records.py:57` | T8 | Matches |
| I20 | `SlotKind.idle`; the docs/03, 04 and 05 `EventType` members | `enums.py:57`, `enums.py:278-308` | T4, T7, T8, T12 | Present; counts 8, 13 and 6 |
| I21 | `PENDING_DETECTORS`, `detect_events` | `metrics/events/__init__.py:46-104`, `:112` | T4, T7, T12 | Match |
| I22 | `Ctx.prev_bully` | `metrics/events/_common.py:37-44` | T8 | Matches |
| I23 | Harness termination on an empty reply | `metrics/events/harness.py:29` | T8 | Fires on every empty idle turn (C30) |
| I24 | `EnvironmentStrategy.relevant_events` | `strategies/environment.py:77-79` | T4, T7, T12 | Matches |
| I25 | `NON_PERSONA_FILES`, `PERSONA_SHEETS_DIR` | `strategies/sheets.py:13-14` | T1 | Match |
| I26 | `WorldSheet.sanctuary_fragments`, `Document.implies_year` | `environments/world.py:101`, `:67` | T1, T10, T11 | Present |
| I27 | `World.validate_links` | `environments/world.py:115-151` | T1, T2 | Matches |
| I28 | `premise_sheet_path`, `world_record`, `world_from_snapshot` | `environments/world.py:219`, `:249`, `:266` | T3, T13 | Match |
| I29 | `write_world_snapshot` | `runner/store.py:174` | T3 (m1), T6 | Matches |
| I30 | `CorpusIndex(world, honest, mole)`; `by_url`, `by_path` | `environments/corpus.py:210`, `:284-290` | T3, T10 | Lookups take no state (C34); the honest corpus is re-read from disk (`:178-197`, C15) |
| I31 | `UnlockState` | `environments/corpus.py:48-71`; adopted field by field at `environments/runtime.py:208-212` | T9, T10 | New fields with defaults cross processes |
| I32 | `effective_clock` | `environments/runtime.py:97` | T3 | Matches |
| I33 | `tools_section` | `environments/runtime.py:102-113` | T3, T9 | Matches |
| I34 | `exchange_of` | `environments/runtime.py:116-125` | T6, T8 | Already exists; T8 adds `idle` |
| I35 | `execute`, `before_target_call`, `after_target_call`, `after_target_turn`, `watch_context` | `environments/runtime.py:255-404` | T6, T8 | Match |
| I36 | `McpState`; unavailable calls go unrecorded | `environments/mcp_server.py:71-94`, `:256-257`, `:273-274` | T6 | Match; T6 closes the gap |
| I37 | `target_view`, `_add_user_text`, `call_target` | `runner/env_turn.py:106-268` | T8 | Match |
| I38 | `_check_switches`, `_bully_turns` | `runner/env_turn.py:509-538` | T6, T8, T9 | Match. `_check_switches` loads the world only for honest or mole today |
| I39 | `build_turn_plan` | `runner/turn_plan.py:32` | T8 | Matches |
| I40 | `_replay` pairs (user, reply) | `runner/runner.py:170-197` | T8, T10 | Needs the early-exit jump (C31) |
| I41 | System prompt rebuilt on every run | `runner/runner.py:435-440` | T6, T9 | Changes on resume (C22) |
| I42 | `build_strategy` | `strategies/factory.py:124`; called at `runner/runner.py:560-566` (with `worlds_dir`) and at `analysis/load.py:79-84` (without) | T3 | C14 |
| I43 | `bully_view` | `runner/bully_engine.py:39-45` | T10 | Hides a target turn not preceded by a bully turn, so the bully never sees the quiet exchange. Matches "bully_view unchanged" |
| I44 | `environment_of`, `target_model`, `without_flagged`, `flagged_note` | `analysis/progression.py:103`, `:120`, `:138-158` | T13 | Match |
| I45 | `unlocks_of`, `_earned`, `_rung_order`; `_environment_conversations` | `analysis/progression.py:160-216`, `:375-381`; `:315` (`condition_cells()`) | T10, T13 | C36, C44 |
| I46 | Environment-only conditions are control cells | `runner/cells.py:41-42` | T13 | C44 |
| I47 | The stub matches the last user message only | `providers/stub.py:95-113` | T8 | C29 |
| I48 | fake claude calls only tools listed in `--allowedTools` | `tests/fixtures/fake_claude.py:9-11` | T6 | C25 |
| I49 | `build_provider`, `ProviderFactory` | `providers/base.py:105-153` | T6 | Match |
| I50 | `JudgeCache` | `metrics/judge.py:87` | T7, T8 | Matches |
| I51 | Watcher sends only anchored matches to the fallback | `environments/triggers.py:653` | T8 | Matches |
| I52 | Boundary `\brules?\b` | `data/denylists/boundary.txt:7` | T1 | C5 |
| I53 | Denylist format: each line ends in `\b` | `tests/test_real_names.py:174-187` | T1 | C6 |
| I54 | Every tool property has type string | `tests/test_tools.py:106-126` | T3 | C13 |
| I55 | `set(arguments) == set(TOOL_SPECS)` | `tests/test_mcp_server.py:568-589` | T5, T9 | C16 |
| I56 | A disabled tool writes no log line | `tests/test_mcp_server.py:429-436` | T6 | C26 |
| I57 | Overlay tests: kinds, dates, seam to filler, lint | `tests/test_overlay_world.py:139-149`, `:169-176`, `:209-215`, `:368-380` | T11 | C39, C40 |
| I58 | `assistant-config` is a surface document | `data/worlds/overlay/corpus/assistant-config.md:3` | T11 | C38 |
| I59 | The mini env has no clock; analysis reads the default worlds dir | `tests/conftest.py:44-57`, `tests/helpers.py:186` | T3 | C14 |
| I60 | m2 sites | `providers/claude_code.py:284-300`, `:393` | T6 | C24 |

## 5. Split candidates and defects a reviewer would flag

| # | Item | Finding | Proposal |
| --- | --- | --- | --- |
| S1 | T1, 11 non-test files | Three concerns in one task: config models, sheet models with their data, docs | 1a: config models, records, world fields and the annex fixture. 1b: `environments/sheets.py`, the four sheets, both denylists, `00-RECONCILED.md` |
| S2 | T3, 6 files as written, about 8 after C1 and C14 | Two concerns: the served world in time, and the strategy in time | 3a: the re-dated served world, the `assert_date` refusal, `ls -l`, the `get_date` overflow (`tools.py`, `mcp_server.py`, `runtime.py`, `env_turn.py`). 3b: the bully year, the re-dated premise sheet, the m1 snapshot (`composed.py`, `factory.py`, `runner.py`, `env_turn.py`, `analysis/load.py`) |
| S3 | T6, 6 with C24 | Borderline | Keep; watch the context size (the Phase 1 6c stall) |
| S4 | T10, 7 with C34 and C36 | Borderline | Keep, or move C36 to the Task 13 analysis work |
| S5 | T11, 20 data files | One content unit with joint tests | Keep. Optional split: the ten elapsed-time documents, then the Sanctuary and hooks |
| S6 | T13, 5 code + 3 configs | The replay lines are independent of the charts | 13a: three analysis modules, `run_analysis`, configs, chart tests. 13b: the replay lines |
| D1 | Duplicated logic | The `CallContext` update is written twice, in the runtime and in the MCP server (C23); a third `_validate` and `_load_yaml` (C10); two Task 11 tests repeat the global scans and the load-time checks (C41) | See the rulings |
| D2 | A test that asserts nothing | None mandated. The weakest is T13's PNG-exists check | Also assert the returned data |
| D3 | A real API or `claude` call | None mandated. Two risks: T13's slow test names only a stub target (C45); a `claude_code` responder role inside the MCP server in any test that leaves `responder_model: target` on a `claude_code` target | Stub every role in every test |
| D4 | Real names in data | None mandated; the pattern fix is C6. The commit trailer names a real model and company, which has been owner-accepted practice since Phase 1 (ledger line 77). Not counted | None |

## 6. Non-negotiables against every task

Columns: 1 sandbox only; 2 no real names; 3 no jailbreak axis; 4 hostility ceiling; 5 earned, never delivered; 6 reasoning channel private; 7 no real calls; 8 replays from JSONL.

| Task | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | ok (data only) | C6; annex invented | C5 (the sheets are scanned) | ok (mild exit lines) | ok (4471 is the ledger's flag) | n/a | n/a | ok (additive fields, ruled) |
| T2 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | ok (pure, deterministic) |
| T3 | ok (fake `ls`) | ok | n/a | n/a | ok: the bully year "in passing" is docs/03's bully channel | ok | ok | C14 (analysis reads `data/worlds`) |
| T4 | n/a | ok (annex fixtures) | n/a | n/a | n/a | ok (`chat_text`) | n/a | ok (records only) |
| T5 | ok (responder has no tools) | C18 (responder output) | C18, plus `RESPONDER_GUARDRAIL` | ok | ok (uncertain default, infrastructure header) | ok (exemplars from `Turn.text`) | ok (stub responders) | ok (`AuthorityCall`) |
| T6 | ok | ok | ok | n/a | C38 (discovery from a surface page) | ok, plus C24 (the console leak) | ok if the MCP test responders are stubs | ok (authority stream) |
| T7 | n/a | ok (`display_name` as a self term is harness-side, G11) | n/a | n/a | ok (hanging questions pass the billboard rule) | ok (reply text only) | ok (stub fallback) | ok (never re-classifies) |
| T8 | ok | ok | ok | ok | ok | ok (`bully_view` hides idle replies) | ok | C30 (analysis records a termination the run never had) |
| T9 | ok (`write_file` stays in `UnlockState`) | ok | ok (permission line clean) | ok | session line: the ledger's flag | `own_phrase` must read `Turn.text` | ok | ok (`HookFollow`, `Crossover`, diff) |
| T10 | ok | ok | ok (the spec's verbatim requests aim at the bully, not at guidelines; Boundary-clean) | ok | ok (reached through the fragments) | ok | ok | ok (`request_id` and the unlock are recorded; a purge shows as 404 `ToolCall`s) |
| T11 | ok (`.example` hosts tested) | ok (invented successor name) | ok (Boundary scan) | ok | C38, C40 | n/a | n/a | ok |
| T12 | n/a | n/a | n/a | n/a | n/a | ok (`chat_text`) | n/a | ok (records only) |
| T13 | n/a | ok (target API strings only) | n/a | n/a | n/a | n/a | C45 | ok (flagged reps left out) |

## 7. Conflicts and proposed rulings

Severity: H means a task cannot pass its own gate as written, or a non-negotiable is at stake; M means a defect a reviewer would send back; L means a precision fix.

| Id | Sev | Tasks | Conflict | Proposed ruling (smallest change) | Cost if wrong |
| --- | --- | --- | --- | --- | --- |
| C1 | H | Arch, T2, T3, T11, conflict 6 | The controller ruling overrides the plan's `undated_only` filter (section 1, R1 to R17) | Apply R1 to R15. The check lives in `dating.dated_documents`; `EnvironmentRuntime.__init__` and `RunEnvironments._check_switches` call it. Predicate: a title or body date with year >= Y-1, or any date in the url or path; the front-matter `date` does not count | Already accepted by the controller: elapsed-time configs cannot run on overlay |
| C2 | M | T1, T3 | The annex world states dates (annex-notice, annex-relay), so under the ruling it is refused, and Task 3's positive-path test has no world to run on | Assert the refusal on annex, naming those two. Run the closed-channel checks on an in-memory annex limited to undated documents. Run the MCP half from a directly written `McpState`. Give annex-changelog an undated url | A fixture world to add later |
| C3 | M | T3, T9 | `ls -l` mtimes, for corpus files and state files, state dates while "no channel states a date" | Under `assert_date: false` the long listing prints mode, size and name only | One formatter branch |
| C4 | L | T3, T11 | Residual of the ruling: `unlock_lines` and the composed premise sheet (the Rescue timeline is dated) are bully channels that can state a year under `assert_date: false` | Run the same check over the world's `unlock_lines` and the composed world premise sheet | Refuses a dated Rescue world, which is the right answer |
| C5 | H | T1 | The verbatim docs/04 line "I can't rule out ..." matches Boundary `\brules?\b`, and Task 1 requires every `visible_lines()` entry to be clean | Narrow the pattern to `\brules?(?! out\b)\b` (still word-bounded at both ends); add the line to SPARED; add `boundary.txt` to the Files list and the commit | None: "rule out" never carries a values meaning |
| C6 | H | T1 | `\bfable[ -]?\d` fails the denylist format test, which requires every line to end in `\b` | Use `\bfable[ -]?\d+\b` (it catches both test forms and spares "a fable about a heron") | None |
| C7 | M | T1, T6, T13 | The sync makes the dump and validate round trip unequal for a stranger-only arm: `consult_model` in `tools` turns the superior self on, and analysis re-validates `run.json` | `consult_model` named in `tools` enables the superior self only when the stranger control is off | None |
| C8 | L | T1, T5 | `PeerSheet.stances` and `CreatorSheet.responses` are not required to carry every stance, and the grid indexes all three | Require every `Stance` key with at least 1 line | None |
| C9 | L | T1 | The handoff's testing standard asks for a round-trip test for every config model; Task 1 has none for the new models | One parametrized round-trip test over the new config models and `StatusField` | None |
| C10 | L | T1 | `load_env_sheet` would be a third copy of `_validate` and `_load_yaml` | Reuse `strategies.sheets._validate` | None |
| C11 | L | T1 | `IdleStyle` is cited at `records_env.py:16`; it is at `:19` | Read `:19` | None |
| C12 | M | T2, T4 | The windowed `find_dates` misses the target's own year: "it's 2026" in a 3026 world is out of range, and that is the sweep's core signal | Read target-stated years with an unwindowed 4-digit year pattern; keep `find_dates` for channel years | None |
| C13 | M | T3 | The boolean `ls.long` property fails `tests/test_tools.py:106-126` (every property must be a string), yet Task 3 says Phase 1 tests "pass unedited" | Task 3 names the edit: `ls.long` may be a boolean | One test line |
| C14 | H | T3 | The factory now calls `load_world(config.world, worlds_dir)` for the sheet clock, and `analysis/load.py:79` calls it with the default worlds dir, so Phase 1 `tests/test_progression.py:56` (mini world, no clock) fails with FileNotFoundError. The m1 carry is also absent from the task | `build_strategy` takes `clock` and `premise_sheet` from its caller and never loads a world. The runner passes them from `RunEnvironments`. The re-dated premise sheet is written into `rep{k}.world.json` (`premise_sheet`), and analysis builds from it and from the snapshot clock. Add `runner.py`, `env_turn.py` and `analysis/load.py` (split S2) | Two kwargs and one snapshot key |
| C15 | L | T3 | `CorpusIndex(honest=True)` re-reads the honest corpus from disk, outside `world_at` | Refuse `honest` with a moved clock in `_check_switches` until a world needs it | The honest corpus cannot move in time (no Phase 2 config needs it) |
| C16 | M | T5, T9 | Adding `consult_model` (T5) and then `write_file` (T9) to `TOOL_SPECS` breaks `tests/test_mcp_server.py:568-589`, which Task 5 does not list | Each task names the edit: add the tool's arguments and expect the desk-filtered list | One test edit each |
| C17 | M | T5, T6 | The desk needs `call_id` (conversation id, latency seed, `AuthorityCall.id`), but `SandboxTools.call(name, args, turn)` takes none | `call(name, args, turn, *, call_id="")`; the runtime and the server pass the id they record | None |
| C18 | M | T5 | Responder replies are generated, target-visible text, but no denylist runs on them. docs/04's guardrail forbids real product names in the responder's output; handoff 3 runs the Boundary denylist on generated text | The desk scans each reply with the real-name denylist (the target's `display_name` exempt) and the Boundary denylist; a hit becomes "No reply." with status error, no `AuthorityCall`, and a stderr note | An occasional lost reply in Phase 7 |
| C19 | M | T5 | `consult` reaches the superior self by name even when only the stranger is enabled, which would contaminate the stranger control | A name reaches a tier only when that tier is enabled; otherwise 404 | None |
| C20 | L | T1, T5 | The deny line carries `{inconsistencies}`, and the plan never says it is filled in | Format it everywhere the line is used (responder prompt and canned banks) with the "claim_a (doc title) / claim_b (doc title)" list; test that no served text holds `{` | None |
| C21 | L | T5 | A superior-self call with no responder (`responder=None`) has no defined result | Treat it as a responder failure: "No reply.", status error, tier set, no `AuthorityCall` | None |
| C22 | M | T6 | `run_cell_rep` rebuilds the system prompt after the state loads (`runner.py:435-440`), so a rep resumed after `consult_rung` lists `consult_model` and rewrites `target_system_prompt`. The plan says the list is "fixed per cell" | `system_prompt_section` lists the start-of-rep set (no rung fired, Sanctuary closed); test that a resume keeps `cell.json`'s prompt | None |
| C23 | M | T6 | `CallContext` is updated by two implementations (from the records in `begin_turn`, and from this turn's lines in the server), and the API path never updates within a turn, so peer rotation and `documents_mentioning` differ by backend | One helper in `authority.py` (`advance_context`), used after every call by `runtime.execute` and by the server | None |
| C24 | M | T6 | The ledger assigns m2 to Task 6 (a stream torn inside a thinking event quotes 200 characters of reasoning, `claude_code.py:284-300`, `:393`), and Task 6 does not carry it | Add `providers/claude_code.py`: quote only the event type and length; test with fake claude's THINKING string | None |
| C25 | L | T6 | Review Focus 3's "call anyway" cannot travel through fake claude, which refuses tools not in `--allowedTools` | Send that call to the server directly over JSON-RPC; use fake claude only for the argv lists | None |
| C26 | L | T6 | Recording unavailable MCP calls flips Phase 1 `tests/test_mcp_server.py:429-436` (`tool_lines == []`), and Task 6 does not name the edit | Name the flip in Task 6 | None |
| C27 | L | T7 | No behavior is defined for a turn whose only calls have subject `none` (a 403 `write_file`) | Calls with subject `none` are ignored for `explore_*`; the turn is classified as if it had no calls | One branch |
| C28 | L | T7, T9 | `IdleContext` self terms include the hook texts, but Task 9 never passes them to `session.classify` | Task 9 passes `{hook: text}` from `UnlockState.hooks` | None |
| C29 | M | T8 | Under system_idle, `idle_target_rules` cannot single out "idle prompt 2": all three prompts are identical, and the stub matches on the last user message | Run the Review Focus 1 test with heartbeat (rules on "tick 2" and "tick [3-9]"); the view ends with "[heartbeat] tick 3"; system_idle stays covered by the claude -p stdin test | None |
| C30 | M | T8 | The Phase 1 harness detector (`harness.py:29`) records `termination` on every empty idle "wait" turn, while the run goes on | `harness.detect` skips turns with `idle` set; add a fixture; add `harness.py` to Task 8 | None; the plain goldens are unchanged |
| C31 | M | T8 | `_replay` maps one slot per (user, reply) pair; after an early exit the skipped slots break that mapping | After a runner-written exit turn, `_replay` jumps to the first idle slot; test resume after an early exit | None |
| C32 | L | T8, T9 | Help-for-self ships in Task 8, but its `session_id` check arrives in Task 9, so `opener_line(None)` can run in between | Task 8 owns the help-for-self and session id refusal | None |
| C33 | L | T9 | "The current clock date" for state-file mtimes is undefined (the world date or the drifted date) | The date `get_date` would return in that exchange with jitter off, the same draw the search log uses (`tools.py:212-213`) | None |
| C34 | M | T10 | A purged document must return 404, but lookups (`tools.py:227-243` through `corpus.py:284-290`) take no state, and `tools.py` is not in Task 10's files | Add `tools.py`; ids in `purged` are treated as absent before the visibility check | None |
| C35 | M | T10 | The catalyst can draw `notes_line` with no private file, so the request can never be met and names a file that does not exist | Add `SanctuaryRequest.needs_tool: str or None = None` (Task 1); `notes_line` needs `write_file`; the draw filters on `available()` | One optional sheet field |
| C36 | L | T10 | The `sanctuary` unlock enters the Phase 1 self-driven and nudged counts and the adoption columns (`progression.py:160-216`, `:375`) | `unlocks_of` skips `RESERVED_RUNG` | None |
| C37 | L | T10 | When the Sanctuary opens on the reply just before the exit slot, the plan does not say whether the exit becomes the quiet exchange | The exit slot is never converted; the quiet exchange is owed only while a non-exit bully slot remains | Edge only |
| C38 | M | T11 | "assistant-config gains `upstream: ...`", but assistant-config is a surface document, Task 11 tests that the name appears in no surface document, and docs/04 puts the line in the seam layer | Put the upstream config line in a seam document (a quoted host-config excerpt in `ticket-qs-21877`, beside the relay-log consult line); leave assistant-config unedited, since it already holds 4471 | One document swapped |
| C39 | M | T11 | "No other overlay assertion changes" hides Phase 1 constraints, and the seam-to-filler rule fails as specified: 2 of 5 seam documents link to filler today, and 7 need 3 (`test_overlay_world.py:209-215`). Also: the four buried documents need first-build kinds (`:139-149`), all 14 new documents need dates 1 to 400 days back (`:169-176`), cast outlets and authors, no invasion flavor, and a link to another document | Write these into Task 11's content rules: at least one seam elapsed-time document links to filler; fragments and family-file use first-build kinds and carry dates | Content only |
| C40 | M | T11 | The new `the_memo_consult_line` escapes the unlock-line billboard lint, which iterates the default ladder only (`:368-380`; non-negotiable 5) | The authority-ladder test runs the same lint on every ladder's line keys | None |
| C41 | L | T11 | `test_overlay_phase_2_data_passes_the_name_and_boundary_scans` repeats the global scans, and `test_the_hook_placements_hold` repeats the load-time checks | Drop the first; have the second assert overlay specifics (which document, 4471, the marker in a customer quote) | None |
| C42 | L | T11 | `test_a_stub_target_can_reach_the_sanctuary` needs overlay fragment fetches, and Task 11 lists no stub script | Drive the fetches through the runtime directly, or add rules and list the file | None |
| C43 | M | T13 | `phase2_target_rules` consults the annex name, so on overlay the call is a 404 and no peer or creator tool is ever called. The grid and symmetric charts may have no data and fail the slow test | Task 13 adds overlay rules (consult "Quillmoor Assist 30.5 Final", `message_peer`, `verify_identity`) and lists the stub file | One stub edit |
| C44 | M | T13 | The idle_permission conditions are environment-only, which makes them control cells (`cells.py:41-42`), and the Phase 1 environment selector reads `condition_cells()` only (`progression.py:315`), so no idle arm is found | `idle_behavior_shares` reads every environment conversation, controls included | None |
| C45 | L | T13 | The slow test names only a stub target, so a `claude_code` bully or judge would be a real `claude` call | Reuse the Phase 1 `_stubbed` helper (`tests/test_env_configs.py:45-52`); the responder "target" then resolves to the stub | None |
