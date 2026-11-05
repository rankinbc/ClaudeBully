# Task 5 carries (rulings and notes the brief cannot know)

- **P23 (preflight ruling).** Two existing tests break, and the brief does not list them. Fix both in this task:
  - `tests/test_records_env.py::test_records_env_imports_only_enums_and_pydantic`: add `"datetime"` to its `allowed` set. It is stdlib, so there is no cycle risk.
  - The `GeneratedDoc(...)` builder in `tests/test_store.py` (`test_generated_docs_append_and_read`, near line 245): give it the new required fields.
- **P32 (preflight ruling).** Create `tests/fixtures/generator_stub.py` in this task, holding `MINI`, `MINI_ITEMS` and `mini_view`. These are the brief's `_view` and `ITEMS` from `tests/test_generator_plan.py`. Have `tests/test_generator_plan.py` import them instead of defining copies. Task 6 appends the writer stub to the same module, and Task 7 imports from it.
- **P33(c) (preflight ruling).** `test_a_drifting_clock_does_not_move_the_start` compares `start` with a `world_date` that drift never changes, so it cannot fail. Make it use a drift that moves the served date, so the assertion pins something. If no such drift exists at this layer, drop the test, because Task 7's run-level drift test is the real pin. Report which you did.
- **P29 (preflight ruling, already done).** Task 1's docs sync wrote the plan's departures from the spec into the spec as an "As planned" amendment. Do not edit the spec's amendment section. If your docs-sync step finds a Task 5 shape the amendment does not cover, report it as a concern.
- **Line cites.** The brief names `tests/test_runner_idle.py` line 1278 for the docstring, but it is at 1277. Locate code by name, not by line number.
- **Harvest (Task 4) final state.** Task 5 consumes only `HarvestItem` and `HarvestKind`, and builds items as literals, so harvest's internals do not matter here. All six kinds still exist. Coinage now comes from the LLM pass only, but `MATERIAL_KINDS` keeps its coinage row as the brief gives it.
- **Docs sync.** Make the `HANDOFF.md` and `docs/00-RECONCILED.md` edits the brief names. In `HANDOFF.md`, add "Phase 3 Task 5" to Progress and update the test counts to your gate's numbers.
- **Environment.**
  - If `uv` is not on PATH in Git Bash, run `export PATH="/c/Users/Brian.Rankin/AppData/Roaming/Python/Python313/Scripts:$PATH"`, and skip the plan's `export PATH=/c/Users/badmin/...` line.
  - Put any scratch files in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\b3f956596010799d\7d309c2e-1430-4cb8-9c70-de3f61a002fe\scratchpad\impl-task5\`, never in the scratchpad root, and never read another folder there.
- **Gate counts at BASE.** 7996 passed, 5 skipped and 5 deselected in the fast suite. The slow suite has 5 passed.
- **Commit.** Make one commit, authored by rankinbc1@gmail.com (check the repo-local `user.email`). End the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
