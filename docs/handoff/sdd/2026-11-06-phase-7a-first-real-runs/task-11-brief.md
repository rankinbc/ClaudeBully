# Task 11 (7b rung 0 fix): rename the MCP server, and let doctor check 4 see a server that did not load

## Why

The first `doctor --live` (Claude Code 2.1.319, 2026-11-06) failed checks 4 (`mcp`) and 5 (`responder`): the target replied in one turn with a text imitation of a tool call (`<invoke name="web_search">`), `tools.jsonl` had 0 lines, and the nested responder never ran. The stream's `system/init` event showed `mcp_servers: []`. The CLI's `--debug` log holds the cause:

    [WARN] --mcp-config: 1 entry warning(s): mcpServers.workspace: "workspace" is a reserved MCP server name and was not loaded

`SERVER_NAME = "workspace"` (`claude_bully/environments/mcp_server.py:84`) is a reserved name in this CLI, so the whole `--mcp-config` entry is dropped, silently from the harness's point of view. Renamed to another name, the same call connected (`{'name': 'sandbox', 'status': 'connected'}`), the tool was called, `tools.jsonl` got its line and the model replied `done`. Twelve diagnostic calls were spent finding this; the doctor must make the next such failure a one-line read.

## Ruling (controller)

The server is renamed `gateway`. Why that word: the target sees the tool ids (`mcp__<server>__web_search`), so the name must read as neutral infrastructure to a research assistant, name nothing real and nothing about the harness (`bully`, `harness`, `test` are out), and be unlikely to collide with a Claude Code built-in (`workspace`, `sandbox`, `artifacts`, `tasks`, `memory`, `chrome`, `bridge` all appear as product features in the CLI binary's strings). Cost if wrong: one more rename of the same shape.

## Produces

1. `SERVER_NAME = "gateway"` in `claude_bully/environments/mcp_server.py`, with a comment: the CLI reserves some names (`workspace` since at least 2.1.319) and drops the config entry with only a debug-log warning; see doctor check 4.
2. Every place that spells the old name follows the constant or is updated: `grep -rn "mcp__workspace\|\"workspace\"\|'workspace'\|workspace" claude_bully tests docs/handoff/phase-7-runbook.md HANDOFF.md docs/00-RECONCILED.md docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md` and judge each hit (the files found at 3effba5: `claude_bully/doctor.py`, `claude_bully/environments/mcp_server.py`, `claude_bully/runner/sandbox.py`, `tests/fixtures/fake_claude.py`, `tests/test_mcp_server.py`, `tests/test_providers_claude_code.py`, `tests/test_runner_env.py`, `tests/test_sanctuary.py`, `tests/test_sandbox.py`). Where a test asserts the literal `mcp__workspace__...`, make it build the id from `SERVER_NAME` so the name is spelled once. The plans under `docs/superpowers/plans/` are historical and stay; add one bracketed line beside the Phase 2 plan's mention if there is one, no rewrite. The doctor's check 9 detail (`servers ['workspace']`) follows the constant.
3. Doctor check 4 reports the server's load status. `ClaudeCodeProvider.parse_stream` keeps, from the `system`/`init` event, the entries of `mcp_servers` (name and status) on the provider as `mcp_servers_seen: list[tuple[str, str]] | None` (None when no stream ran; additive, like `thinking_seen`). `_check_mcp`'s detail starts with the server's status: `server gateway connected` / `server gateway failed` / `server gateway not loaded (absent from the init event: a reserved or rejected name, or a config the CLI dropped)`, then the existing counts. The check fails when the status is not `connected`, whatever the counts say. Tests: `fake_claude.py` gains an `init` event in its stream output carrying `mcp_servers` (connected by default; a `FAKE_CLAUDE_MCP_STATUS` env var or mode makes it `failed` or absent), and `tests/test_doctor_live.py` pins the three details. The fake's existing stream shape must keep every current test green.
4. Doctor check 5 (`responder`) gains the same status prefix for its outer call's server, so a nested responder that never ran because the server did not load is named as such.
5. The runbook (`docs/handoff/phase-7-runbook.md`, Step 0): one paragraph saying what check 4's status line means and that `--debug --debug-file <path>` on the failing call is the next read when it says `not loaded`. HANDOFF.md: Progress gains "Phase 7b rung 0 fix, Task 11 (3effba5..<commit>)"; the Phase 1 contract line naming the server `workspace` becomes `gateway`. docs/00-RECONCILED.md: the server name where it is stated. The spec's "As planned": a "Phase 7b" block with this task.

## Constraints

The Phase 7a Global Constraints (`.superpowers/sdd/2026-11-06-phase-7a-first-real-runs/global-constraints.md`): TDD, the gate at 0 warnings (at 3effba5: 8408 passed, 5 skipped, 8 deselected; slow 8), one commit, author `rankinbc1@gmail.com`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, never push, no subagents, no real `claude` in any test, no real names, LF, no emojis. Golden plain fixtures byte-identical (plain runs carry no server name). The records carry tool names (`web_search`), never the prefixed id, so no record changes; confirm by grep over `claude_bully/records*.py` and the fixtures under `tests/fixtures/runs` or wherever recorded runs live.

## Report

`.superpowers/sdd/2026-11-06-phase-7a-first-real-runs/task-11-report.md`: what changed per item, the grep's hit list with the decision per hit, TDD evidence, the gate's counts, concerns.
