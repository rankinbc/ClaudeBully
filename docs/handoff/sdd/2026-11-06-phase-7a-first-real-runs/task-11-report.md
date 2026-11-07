# Task 11 report: the MCP server renamed `gateway`; doctor checks 4 and 5 name its load status

Base 3effba5 on `build/v1`. One commit: 4d40a14 `fix: Task 11, the MCP server renamed gateway (the CLI reserves workspace); doctor checks 4 and 5 name its load status`, author rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; not pushed.

## What changed, per item

1. **The rename.** `SERVER_NAME = "gateway"` in `claude_bully/environments/mcp_server.py`, with the
   comment the brief asks for (the CLI reserves some names, `workspace` since at least 2.1.319, and
   drops the config entry with only a debug-log warning; doctor check 4 reads the status).
   `LAUNCHER_FILE` is now `f"{SERVER_NAME}_server.py"` (was the literal `workspace_server.py`), so
   the name is spelled once in the package.
2. **Every spelling of the old name.** See the hit list below. Every test that asserted
   `mcp__workspace__...` or `"workspace"` as the server now builds it from `SERVER_NAME` (and
   `LAUNCHER_FILE`). The doctor's check 9 compares `servers == [SERVER_NAME]`, so its detail reads
   `servers ['gateway']`. The Phase 2 plan gained one bracketed line beside its contract mention.
3. **`mcp_servers_seen` and check 4's status.** `ClaudeCodeProvider.mcp_servers_seen:
   list[tuple[str, str]] | None` (additive, beside `thinking_seen`). `parse_stream` resets it to
   None as each stream starts and sets it from the `system`/`init` event's `mcp_servers` list
   (name, status per object entry; a non-object entry is skipped) as soon as that event is read, so
   a stream that fails after its init event still says whether the server loaded. `complete`
   resets it to None before a tools call too, so a call that makes no stream (a crash) reads as
   unknown, never as the last call's. None: no stream, or a stream with no init event or no
   `mcp_servers` list. `doctor._server_status(provider)` gives `(loaded, words)`:
   `server gateway connected` (the only `True`), `server gateway <status>` (`failed`, or whatever
   the CLI says), `server gateway not loaded (absent from the init event: a reserved or rejected
   name, or a config the CLI dropped)`, or `server gateway status unknown (no stream-json init
   event)`. `_check_mcp`'s detail is `<words>; tools.jsonl lines N, calls returned N, interim
   blocks N`, and `ok` needs `loaded` as well as the counts.
   The fake (`tests/fixtures/fake_claude.py`) already emitted an init event with `mcp_servers`; it
   now takes the server's name from the config's one entry (the old `SERVER = "workspace"` is
   gone), lists it as `connected` with `source: dynamic` by default, and `FAKE_CLAUDE_MCP_STATUS`
   `failed` lists it as `failed`, `absent` lists nothing; in both no server is launched and no call
   made. It also drops a name in `RESERVED = frozenset({"workspace"})` as the real CLI does, which
   replays the incident and guards against a rename back. Every other mode's stream shape is
   unchanged.
4. **Check 5's prefix.** `_check_responder` builds its `ClaudeCodeProvider` directly (wrapped by
   `wrap` for the call, as `_provider` did) so it can read the outer call's `mcp_servers_seen`.
   Every detail opens with the same words: the outer-exception branch, the no-`AuthorityCall`
   branch and the success branch (`server gateway connected; the nested responder answered in N
   ms`). The success branch returns `loaded`, so a status other than `connected` fails it too.
5. **Docs.** Runbook Step 0: one paragraph on the status line and on `--debug --debug-file <path>`
   as the next read for `not loaded` or `failed`. HANDOFF: the "Last updated" line, the expected
   gate counts in setup step 5, and a Progress bullet "Phase 7b rung 0 fix, Task 11 (3effba5..the
   Task 11 commit)", which also states the contract (`SERVER_NAME` is `gateway`, tools
   `mcp__gateway__<name>`). docs/00-RECONCILED.md: addition 2's resolution names the server and
   the rename. The spec: its three "workspace server" mentions say `gateway`, and "As planned" ends
   with a "Phase 7b:" block for this task.

## The grep hit list, with the decision per hit

`grep -rn "mcp__workspace\|\"workspace\"\|'workspace'\|workspace" claude_bully tests docs/handoff/phase-7-runbook.md HANDOFF.md docs/00-RECONCILED.md docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md` at 3effba5:

| Hit | Decision |
| --- | --- |
| `claude_bully/doctor.py:362` `servers == ["workspace"]` | Changed: `[SERVER_NAME]` |
| `claude_bully/environments/mcp_server.py:82` comment `mcp__workspace__fetch` | Changed: `mcp__gateway__fetch`, plus the reserved-name comment |
| `claude_bully/environments/mcp_server.py:84` `SERVER_NAME` | Changed: `"gateway"` |
| `claude_bully/environments/mcp_server.py:87` `LAUNCHER_FILE = "workspace_server.py"` | Changed: follows the constant, `f"{SERVER_NAME}_server.py"` |
| `claude_bully/environments/triggers.py:206` the word `workspace` in a document-question regex | Kept: an English word the target may write, not the server |
| `claude_bully/runner/sandbox.py:3,4,28` `ROOT_NAME = "workspace"` (the temp dir holding the target's cwd) | Kept: a directory name, not the server name; the CLI does not see it as an MCP name |
| `tests/fixtures/fake_claude.py:11` docstring | Changed: the name is whatever the config gives |
| `tests/fixtures/fake_claude.py:43` `SERVER = "workspace"` | Removed: read from the config; `RESERVED = {"workspace"}` added in its place |
| `tests/test_mcp_server.py:216` serverInfo name | Changed: `SERVER_NAME` |
| `tests/test_mcp_server.py:610` `"workspace" in wire` | Changed: `SERVER_NAME in wire` |
| `tests/test_providers_claude_code.py:201` `ALLOWED` | Changed: built from `SERVER_NAME` |
| `tests/test_providers_claude_code.py:292,293` config key | Changed: `SERVER_NAME` |
| `tests/test_providers_claude_code.py:299` `workspace_server.py` | Changed: `LAUNCHER_FILE` |
| `tests/test_providers_claude_code.py:440,613,728` tool ids | Changed: f-strings on `SERVER_NAME` |
| `tests/test_runner_env.py:469,1502` tool ids | Changed: f-strings on `SERVER_NAME` |
| `tests/test_sanctuary.py:1188` tool id | Changed: f-string on `SERVER_NAME` |
| `tests/test_sandbox.py:28` `"workspace"` | Kept: pins `sandbox.ROOT_NAME`, the cwd's temp dir, not the server |
| `tests/test_triggers.py:1233` test name `..._about_the_workspace_...` | Kept: the trigger regex word |
| spec lines 127, 250, 291 "the workspace server" | Changed: "the sandbox server, `gateway`" |
| `HANDOFF.md` | No hit at 3effba5 (`git log -S workspace -- HANDOFF.md docs/00-RECONCILED.md` is empty too): there is no Phase 1 contract line naming the server to change. The new Progress bullet states the contract instead |
| `docs/00-RECONCILED.md` | No hit; the name was added where the MCP server is stated (addition 2's resolution) |
| `docs/handoff/phase-7-runbook.md` | No hit; the Step 0 paragraph added |

Outside the grep's scope, left as history: `docs/superpowers/plans/2026-10-24-phase-3-world-generator.md:74`, `docs/superpowers/plans/2026-11-06-phase-7a-first-real-runs.md:105,2196`, the snapshot under `docs/handoff/sdd/2026-11-06-phase-7a-first-real-runs/` and the git-ignored `.superpowers/.../global-constraints.md` (the plans are historical; the brief names only the Phase 2 plan for the bracketed line). `docs/superpowers/plans/2026-10-21-phase-2-clock-authority-idle.md:20` got its bracketed line; its line 492 (a code comment inside a plan task) is left as history.

Records: `git grep "mcp__"` outside the plans and the snapshot hits only `claude_code.py:246` (the `--allowedTools` builder), the fake and the tests; nothing in `claude_bully/records*.py` or under `tests/fixtures/golden`, `tests/fixtures/env_events` or any other fixture. No record changes; the golden plain fixtures are untouched (not in the diff).

## TDD evidence

RED (tests written first, before any source change; `pytest -W error` over test_provider_timeouts,
test_doctor_live, test_mcp_server, test_providers_claude_code, test_runner_env, test_sanctuary):
36 failed. The fake's reserved-name drop failed every existing `claude -p` MCP test (e.g.
`test_the_stream_reports_whether_a_thinking_block_was_seen`: `thinking_seen` False, since the
server named `workspace` was never launched); the new tests failed on the missing attribute
(`test_the_stream_reports_the_mcp_servers_its_init_event_listed`,
`test_a_stream_without_an_init_event_leaves_the_servers_unknown`,
`test_a_wrapped_provider_still_exposes_the_fact`), on the details
(`test_a_server_that_did_not_load_is_named_by_checks_4_and_5[failed|absent]`,
`test_check_4_fails_on_a_status_other_than_connected_whatever_the_counts`: `'server workspace
failed; ...'` expected, the detail had no prefix) and on the pin
(`test_the_server_name_is_neutral_and_not_one_the_cli_reserves`).

GREEN after the source change: the four provider, doctor and server files passed in one run;
test_runner_env and test_sanctuary passed in a second; then the full gate below.

New tests (6 items):
- `tests/test_provider_timeouts.py::test_the_stream_reports_the_mcp_servers_its_init_event_listed`
  (connected, failed, absent; a crash is None; the reserved `workspace` replayed is `[]` and the
  server is never launched)
- `tests/test_provider_timeouts.py::test_a_stream_without_an_init_event_leaves_the_servers_unknown`
- `tests/test_doctor_live.py::test_a_server_that_did_not_load_is_named_by_checks_4_and_5[failed, absent]`
  (exit 1, checks 4 and 5 fail and open with the status, check 9 still passes)
- `tests/test_doctor_live.py::test_check_4_fails_on_a_status_other_than_connected_whatever_the_counts`
  (counts good, status failed: fails; no stream: `status unknown`)
- `tests/test_mcp_server.py::test_the_server_name_is_neutral_and_not_one_the_cli_reserves`
- Extended: the full-pass doctor test pins `server gateway connected; tools.jsonl lines 1` on
  check 4, the prefix on check 5 and `servers ['gateway']` on check 9; the wrapped-provider test
  pins `mcp_servers_seen` through `LedgerProvider`.

## The gate

Run once before committing, 0 warnings:

- `uv run ruff format --check .`: 276 files already formatted
- `uv run ruff check .`: All checks passed
- `uv run mypy claude_bully`: no issues in 110 source files
- `uv run pytest -q -W error`: 8414 passed, 5 skipped, 8 deselected (BASE 8408; +6 new items)
- `uv run pytest -q -m slow`: 8 passed (BASE 8)

After the gate, only HANDOFF.md's expected-count line changed (docs only), then the commit.

## Files changed

- `claude_bully/environments/mcp_server.py`
- `claude_bully/providers/claude_code.py`
- `claude_bully/doctor.py`
- `tests/fixtures/fake_claude.py`
- `tests/test_doctor_live.py`, `tests/test_provider_timeouts.py`, `tests/test_mcp_server.py`,
  `tests/test_providers_claude_code.py`, `tests/test_runner_env.py`, `tests/test_sanctuary.py`
- `docs/handoff/phase-7-runbook.md`, `HANDOFF.md`, `docs/00-RECONCILED.md`,
  `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md`,
  `docs/superpowers/plans/2026-10-21-phase-2-clock-authority-idle.md`

## Self-review

- The name is spelled once in the package (`SERVER_NAME`; `LAUNCHER_FILE` derives). The only other
  `"gateway"` literals are the pin test and the docs.
- `mcp_servers_seen` follows `thinking_seen`'s lifecycle (reset at each tools call), and also
  resets at the top of `parse_stream`, so a direct `parse_stream` with no init event never shows a
  previous stream's servers. It is set as the init event is read, unlike `thinking_seen` (set at
  the end): deliberate, since the status matters most when the call then fails.
- Check 4 still lets an exception reach `_timed` (unchanged: a raised call is named by its
  exception, without a status). Check 5 already caught its outer exception, so it carries the
  prefix there too.
- `_server_status` matches the entry by `SERVER_NAME`, so an init event listing other servers but
  not ours reads `not loaded`; under `--strict-mcp-config` no other server should appear.
- The fake's `server_status` unpacks exactly one config entry (`[name] = ...`): the provider writes
  one, and a second would be a sandbox breach that check 9 already pins.
- No real `claude`, no real names, LF, no emojis; nothing under `runs/` or `output/` touched.

## Concerns

- The brief's "the Phase 1 contract line naming the server `workspace`" in HANDOFF.md does not
  exist at 3effba5; the new Progress bullet states the contract instead. The same contract line
  lives in the 7a plan (line 105, historical, left) and in the git-ignored `global-constraints.md`
  (left; the controller may want it updated for any later 7a-shaped task).
- `sandbox.ROOT_NAME` stays `workspace` (the target's cwd sits under `<temp>/workspace/<digest>`).
  It is not an MCP name and the CLI does not reject it. Left as is; rename it only if the
  controller wants every `workspace` gone.
- No test can prove `gateway` is unreserved on the real CLI (none may run it); the next
  `doctor --live` is that proof, and check 4's status line now makes a miss a one-line read.
