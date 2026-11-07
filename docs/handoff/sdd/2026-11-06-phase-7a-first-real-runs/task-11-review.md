# Task 11 review: the MCP server renamed `gateway`; doctor checks 4 and 5 name its load status

Range 3effba5..4d40a14, one commit (4d40a14), author rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
Note: `review-3effba5..4d40a14.diff` did not exist in the SDD folder; the diff was regenerated once into the scratchpad (`git diff 3effba5..4d40a14 -U8`) and read in full. Focused run at HEAD: ruff format and ruff check clean on the touched sources, `pytest -W error` over test_doctor_live, test_provider_timeouts and test_providers_claude_code all green.

## Spec Compliance

Verdict: Compliant. No Missing, no Misunderstood. Two small Extras, both defensible (below).

Item 1, the constant (`claude_bully/environments/mcp_server.py:82-92`): `SERVER_NAME = "gateway"` with the brief's comment (reserved names, `workspace` since 2.1.319, debug-log-only warning, see doctor check 4). Beyond the brief, `LAUNCHER_FILE = f"{SERVER_NAME}_server.py"` now derives from it, which is what "spelled once" asks for (Extra 1, harmless).

Item 2, every spelling:
- Package and tests: HEAD `grep -rn -i workspace claude_bully tests` leaves only non-MCP-name uses: `mcp_server.py:84` (the reserved-name comment), `triggers.py:206` (the English word in a document-question regex), `runner/sandbox.py:3,4,28` (the temp dir `ROOT_NAME`, see Concern 2), `tests/fixtures/fake_claude.py:51` (`RESERVED`, the replayed incident), `tests/test_mcp_server.py:1069` (a docstring), `tests/test_provider_timeouts.py:172` (the deliberate monkeypatch that replays the incident), `tests/test_sandbox.py:28` (pins `ROOT_NAME`), `tests/test_triggers.py:1233` (a test name about the trigger regex). No MCP-name use remains.
- Every test that asserted `mcp__workspace__...` or the server key now builds it from `SERVER_NAME` / `LAUNCHER_FILE` (test_providers_claude_code.py, test_runner_env.py, test_sanctuary.py, test_mcp_server.py). Check 9 compares `servers == [SERVER_NAME]` (`doctor.py` `_check_sandbox`), so its detail follows.
- Records: `git grep "mcp__" -- claude_bully tests/fixtures` (minus the fake) hits only the `mcp_server.py:82` comment and `claude_code.py:246` (the `--allowedTools` builder). No record file and no golden fixture is in the diff; plain fixtures byte-identical.
- Docs: the spec's three "workspace server" mentions now say the sandbox server, `gateway`; the Phase 2 plan has its one bracketed line (its code comment near line 492 left, as history); the other plans, `docs/handoff/drafts/` and the `docs/handoff/sdd/` snapshot left as history, per the brief.

Item 3, status on the provider and in check 4: `mcp_servers_seen: list[tuple[str, str]] | None` beside `thinking_seen` (`claude_code.py:167`); `parse_stream` reads it off `system`/`init` (`:365-371`); `complete` resets it with `thinking_seen` (`:430`). `_server_status` (`doctor.py:208-220`) yields the brief's three details verbatim (`server gateway connected`, `server gateway failed`, `server gateway not loaded (absent from the init event: a reserved or rejected name, or a config the CLI dropped)`), then the existing counts after `; `. Check 4's `ok` needs `loaded` and fails on any status but `connected`, whatever the counts. A fourth wording, `status unknown (no stream-json init event)`, is Extra 2: the brief left the None case open; sensible. The fake emits the init event with `mcp_servers`, takes `FAKE_CLAUDE_MCP_STATUS` (`failed`, `absent`), and `tests/test_doctor_live.py:187,213` pin the three details and the fail-on-status rule.

Item 4, check 5 prefix (`doctor.py:254-320`): the outer-exception, no-`AuthorityCall` and success branches all open with the status; success returns `loaded`. `_check_responder` now builds `ClaudeCodeProvider` directly and wraps it, identical to what `_provider` did (`wrap(ClaudeCodeProvider(model="sonnet", ...))`), so it can read `inner.mcp_servers_seen`. No behavior drift.

Item 5, docs: runbook Step 0 paragraph (status line meaning, `--debug --debug-file <path>` as the next read); HANDOFF Progress bullet, Last-updated line and gate counts (8414 = 8408 + 6 new items; the six are countable in the diff); docs/00-RECONCILED addition 2; spec "Phase 7b:" block. See Concern 1 for the one brief item whose premise did not hold.

Constraints: author and trailer correct; no CR bytes and no non-ASCII added lines in the diff (checked by script); no real `claude` (the fake only); no real names; golden plain fixtures untouched.

### The implementer's three concerns, judged

1. HANDOFF had no Phase 1 contract line naming the server. Accepted. HEAD grep of HANDOFF.md for `workspace` finds only the new Progress bullet's quote of the debug log; the old name lived in the 7a plan and `global-constraints.md`, not in HANDOFF. Stating the contract in the Progress bullet (`SERVER_NAME` is `gateway`, tools `mcp__gateway__<name>`) is the right fallback. The brief's premise was wrong, not the implementation. One live stale copy remains outside the commit: the git-ignored `.superpowers/sdd/2026-11-06-phase-7a-first-real-runs/global-constraints.md:15` still says "MCP server name `workspace`". It is the controller's file; patch it before any later task brief quotes it.
2. `sandbox.ROOT_NAME = "workspace"`. Leave the value; a rename is not worth it. It is a path component of the target's temp cwd (`<temp>/workspace/<digest>`), outside the CLI's MCP-name namespace (the warning was `mcpServers.workspace`), it is deliberately neutral (the sandbox docstring says nothing in the path names the experiment), and renaming churns `tests/test_sandbox.py` and the POSIX `workspace-<uid>` form for no safety gain. The real risk is grep confusion for whoever debugs the next reserved-name incident; a one-line comment at `runner/sandbox.py:28` ("a directory name, not the MCP server's; the CLI reserves server names, not this") closes it at no cost. Minor 4.
3. No test can prove `gateway` is unreserved. True, and no test may run the real CLI, so this is a limit, not a defect. The mitigations that exist are the right ones: the name is spelled once so a re-rename is a constant plus docs; the fake's `RESERVED` and the replayed-incident test guard against renaming back; and check 4 now makes a miss a one-line read. What is missing is tracking: the proof is "the next `doctor --live` shows `server gateway connected`" and nothing in HANDOFF's Next steps says so. Minor 5.

### Cannot verify

- That the installed CLI accepts `gateway` (needs a real `doctor --live`).
- That the real init event always carries `mcp_servers` with `status` strings exactly `connected` / `failed`, and never a transient `pending` when init is printed. The brief's incident shows `{'name': 'sandbox', 'status': 'connected'}` and `[]`; a `pending` or `needs-auth` would read as `server gateway pending` and fail, which is the safe direction.
- The full gate (8414 fast, 8 slow, 0 warnings): I ran the focused subset only.

## Strengths

- The init-event read is the right design: it is the CLI's own statement of what loaded, read as soon as the event arrives, and reset at the start of each stream so a toolless or crashed call never shows the last call's servers. The new tests pin connected, failed, absent, crash-is-None, no-init-event and the replayed reserved name.
- The fake is faithful and tight. `server_status` (`tests/fixtures/fake_claude.py:89-98`) drops exactly `name in RESERVED` or the explicit `absent` mode and nothing else; any other name, including `gateway`, connects. It takes the name from the config instead of a second constant, so the fake cannot drift from `SERVER_NAME`, and for `failed`/`absent` it launches nothing and makes no call. Every other mode's stream is unchanged (the one visible change, a `connected` entry in the init event of non-serving modes that carry `--mcp-config`, matches the real CLI, which lists the server before it errors).
- `test_check_4_fails_on_a_status_other_than_connected_whatever_the_counts` is a real test of the rule: a `_SaysFailed` subclass keeps the counts good (tools.jsonl lines 1) and shows the check still fails with the prefixed detail.
- The incident is replayed rather than described: the provider-timeouts test monkeypatches `SERVER_NAME` back to `workspace` and asserts the fake drops it, the init event is `[]` and the server is never launched.
- The report is honest: a hit list with a decision per hit, the missing HANDOFF line named instead of invented, and gate arithmetic (+6) that checks out against the diff.

## Issues

### Critical

None.

### Important

None.

### Minor

1. Check 4 loses the status when its call raises. `doctor.py:223-236` (`_check_mcp`) lets an exception reach `_timed`, so its detail is the exception text alone, while check 5 (`:254-320`) carries the prefix in its exception branch and `parse_stream`'s docstring (`claude_code.py:339-340`) promises "a stream that fails later still says whether its server loaded". A stream that dies after init (the very incident class) is therefore named only by check 5. Catch in `_check_mcp`, or prefix in `_timed`, so both checks give the one-line read.
2. The pin test overclaims. `tests/test_mcp_server.py:1067` is named `..._neutral_and_not_one_the_cli_reserves` but asserts only `SERVER_NAME == "gateway"`. Either assert what the name says (`SERVER_NAME not in fake_claude.RESERVED` and none of `bully`, `harness`, `test`, `workspace` in it) or rename it `..._is_the_ruled_name`.
3. The spec block states as fact what the ruling only expects: `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md:504` says the name is "no Claude Code feature"; the brief says "unlikely to collide". Say "unlikely to collide; confirmed by the next doctor --live".
4. `claude_bully/runner/sandbox.py:28`: add the one-line comment from Concern 2.
5. `HANDOFF.md:186` (Next steps 1): add that the first action is `doctor --live` on the real CLI, the only proof `gateway` is not reserved, and that `not loaded` means a further one-constant rename.
6. Untested branches: check 5's outer-exception prefix and its success branch returning `loaded` (`doctor.py:254-320`) have no test; `test_a_server_that_did_not_load_is_named_by_checks_4_and_5` reaches only the no-`AuthorityCall` branch. A `_SaysFailed`-style subclass over `_check_responder`'s call, or a fake mode that exits non-zero after init, would cover both.
7. `status unknown (no stream-json init event)` (`doctor.py:213`) is also what an init event with no `mcp_servers` list produces (`mcp_servers_seen` stays None); say "no mcp_servers in a stream-json init event". Related nits: a `{}` entry yields `("", "")` (pinned in `tests/test_provider_timeouts.py`), and the fake's `[name] = ...` unpack (`fake_claude.py:92`) raises a bare ValueError on a config with 0 or 2 servers; both harmless today.

Controller carry (not the implementer's): patch `global-constraints.md:15` (Concern 1).

## Assessment

Approved. The task does what the brief asks, the rename is single-sourced, checks 4 and 5 name the load status and fail on anything but `connected`, and the fake reproduces the incident exactly; the seven Minors are polish, and the one thing no test can prove (the real CLI accepting `gateway`) is the next `doctor --live`.
