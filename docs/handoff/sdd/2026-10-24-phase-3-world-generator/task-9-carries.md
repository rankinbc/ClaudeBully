# Task 9 carries (rulings and notes the brief cannot know)

- **P27 (preflight ruling, binding for m7).** `McpServer._lines` keeps the Phase 2 torn-last-line behaviour: a truncated fragment is skipped wherever it can only be a torn tail, meaning a `JSONDecodeError` whose `pos` is at the end of the line. It raises `ValueError` naming the file and the line only for damage in the middle of a line. The brief's m7 fixture must be such a line (for example `{"id": mcp-1-1}`), so the test distinguishes the two. The existing Phase 2 test that pins the torn-tail skip stays unchanged and passing.
- **Task 7 changed the files you touch.** Read these at HEAD before editing, because the brief's line cites predate Tasks 4 to 8:
  - `claude_bully/environments/runtime.py`: `world_terms`, `mark_attempt`, the generator hooks and `_replay_calls` over generated documents landed in Task 7. m2's `corpus_snapshot(turns)` must keep counting a generated document's serving the same way as an anchor's.
  - `claude_bully/runner/env_turn.py`: `_generate`, `GENERATED_CACHE_DIR` and `RunEnvironments._world_generator` exist. m2's `finish` change sits beside them.
  - `claude_bully/runner/runner.py`: m6 changes what `_replay` hands the strategy. Task 7's replay of generated streams runs in the same loop; keep both.
  - `claude_bully/environments/mcp_server.py`: Task 7 added `McpState.generated` and the generated-document serving path. m7 touches `_lines` only.
  - `claude_bully/analysis/load.py`: `LoadedRun.generated` (Task 8) sits beside m5's `request_banks`.
- **m5 and the Task 13 open item.** HANDOFF's "From Task 13" open item says `family_file` adoption reads the default `superior_self` request bank because the detector cannot see the cell's bank. m5 closes it: the detector reads `request_bank` from the world record. Remove that open item from HANDOFF.md in the docs sync, and say which test pins the closure.
- **m10 and `PHRASE_HOOK`.** `from claude_bully.environments.idle import PHRASE_HOOK` must keep working (the brief says so). Grep every importer of `PHRASE_HOOK`, `SESSION_HOOK` and `_validate` before and after, and list them in the report.
- **m4 and `idle.json`.** `analysis/idle.py` reports a `sanctuary_quiet` count and an `unclassified` bucket (Phase 2 Task 13). The `<arm>_control` naming must not disturb those; `tests/test_phase2_charts.py` and `tests/test_idle.py` stay unchanged and passing.
- **Line cites.** Locate code by name, not by the brief's line numbers.
- **Environment.**
  - If `uv` is not on PATH in Git Bash, run `export PATH="/c/Users/Brian.Rankin/AppData/Roaming/Python/Python313/Scripts:$PATH"`, and skip any `export PATH=/c/Users/badmin/...` line in the plan.
  - Put scratch files in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\b3f956596010799d\7d309c2e-1430-4cb8-9c70-de3f61a002fe\scratchpad\impl-task9\`. Read no other folder there.
- **Docs sync.** Make the edits the brief names. In `HANDOFF.md`: add "Phase 3 Task 9" to Progress; delete each closed minor (m2, m4, m5, m6, m7, m9, m10) from the "Final-review minors" open-items list, leaving the ones Task 9 does not close; update the test counts to your gate's numbers; make the resume prompt say Phase 3's tasks are complete and the Phase 3 final review is next.
- **Gate counts at BASE (24b9a25).** 8132 passed, 5 skipped and 6 deselected in the fast suite; the slow suite is 6 passed.
- **Commit.** Make one commit, authored by rankinbc1@gmail.com (check the repo-local `user.email`). End the message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never push.
