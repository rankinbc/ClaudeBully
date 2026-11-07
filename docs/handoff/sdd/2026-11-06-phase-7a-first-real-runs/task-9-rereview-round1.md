# Task 9 re-review, fix round 1 (afe71f8..883a24b)

### Finding Verdicts

- **C1, rung 0b raised ValueError out of run_experiment (key_turns 1 against a Rescue minimum of 2); the dry-run tests could not see it** — ADDRESSED.
  - `configs/ladder/rung0_smoke_env.yaml:21` now carries `{intake_turns: 1, evidence_turns: 1, recall_turns: 1, key_turns: 2}`; the sum is 5 = `turn_budget`, which the dry-run test's stage-sum assert still checks (T stays 5, slot counts and estimate stand). `RescueStrategy.__init__` (`claude_bully/strategies/rescue.py:125-126`) refuses only `key_turns < 2`, so 2 passes.
  - Amended in all four places the ruling named: config comment (`rung0_smoke_env.yaml:2`), spec section 5's 0b row (spec diff line 131), spec "As planned" Task 9 bullet (spec line 484), HANDOFF item 9 stage text (HANDOFF diff line 55).
  - The new test `test_every_rung_config_runs_on_stubs` (`tests/test_ladder_configs.py`, diff lines 257-276) closes the blind spot: it goes through `run_experiment` without `dry_run`, so each strategy is built with its params. The implementer's RED run reproduced the original defect on `[rung0_smoke_env]` (`ValueError: key_turns must be at least 2`), which is the evidence the test would have caught C1.
  - The test docstring (module level) now states why a dry run cannot see it.
- **Rider: kindness header comment (116 chars) wrapped under 100** — ADDRESSED. `configs/kindness_vs_cruelty.yaml:1-2` are 93 and 24 characters (measured). No other config, ladder file or test file line exceeds 100 characters.
- **Rider: slow Sanctuary test's `--only "*__t0*"` live again** — ADDRESSED. `tests/test_ladder_configs.py` (diff lines 310-323): the `_stubbed` copy gets a second stub target (`stub-target-2`), `assert len(expand_cells(exp)) == 8` pins the full expansion, and `only="*__t0*"` must select exactly 4 (`cells_completed == cells_total == 4`). `run_experiment` sets `cells_total = len(cells) * exp.repetitions` after the `fnmatch` filter (`runner.py:732-736`), so if the glob were ignored the total would be 8 and the assert would fail: the filter is live. The docstring says so.
- **Rider: `LADDER_EXPECTED` derived from `RUNGS`; the move of `RUNGS` into `tests/test_configs.py`** — ADDRESSED, and the move is sound. `test_ladder_configs.py` already imports `_stubbed` from `tests.test_configs` (I33), so `test_configs` importing `RUNGS` from `test_ladder_configs` would be a cycle. `RUNGS` in `test_configs.py:38-44`, `LADDER_EXPECTED = set(RUNGS)` at line 45, and `test_ladder_configs.py` imports `RUNGS` beside `_stubbed`: one definition, three consumers (the rglob test, the "exactly five rungs" test, the parametrizations). The alternative (a third helper module) would be heavier for a table that Phase 5's `tests/helpers` move can relocate with `_stubbed`; the comment above `RUNGS` records why it sits there. Importing names (not test functions) from `test_configs` causes no double collection.
- **Rider: redundant `only=` in the pilot test removed** — ADDRESSED. `test_the_sanctuary_pilot_has_no_control_cells_and_skips_the_pair` now calls `run_experiment(stubbed, runs_root=tmp_path)` (diff line 290); the one-cell config makes the glob meaningless.

### Named checks

1. **The stub-run test really runs every rung in `RUNGS` through `run_experiment` and asserts per cell: PASS.** Parametrized over `sorted(RUNGS)` (all five, each rung's `slow` mark applied through `pytest.param`, none dropped). It calls `run_experiment(exp, runs_root=tmp_path, provider_factory=GeneratorFactory())` with no `dry_run`, on a `_stubbed` copy at `repetitions: 1`, and asserts `cells_aborted == 0` and `cells_completed == cells_total == cells` (the cell count from `RUNGS`). With reps forced to 1 for the Sanctuary pilot (6 in the config), `cells_total == cells` holds for all five.
2. **`slow` covers only the case over two seconds; the other four stay fast: PASS.** `SLOW_STUB_RUNS = {"rung1_env_pilot"}`; the other four ids are plain strings. `pyproject.toml:67-68` (`addopts = "-m 'not slow'"`) so only the env pilot case is deselected from the fast suite. The reported durations (0.13, 0.35, 0.45, 0.43 s fast; 2.70 s env pilot) match, and the count deltas agree: fast 8350 -> 8354 (+4), deselected 7 -> 8 (+1), slow 7 -> 8 (+1), HANDOFF line updated to the same numbers.
3. **No `claude_code` provider is built, no real call: PASS.** `_stubbed` (`test_configs.py:98-106`) replaces targets, bully and judge with `stub` roles; the test replaces the one top-level generator (the env pilot's `haiku` on `claude_code`) with a stub role on `GENERATOR_MODEL`, which `GeneratorFactory` hands the `GeneratorStub`; the judge model `stub-judge` is not the factory's `JUDGE_MODEL` (`judge-x`), so it falls through to `build_provider` as a stub. The MCP responder role derives from the target or bully role (`env_turn.responder_role`), so it is a stub too. Beyond that, the session-scoped autouse `no_real_providers` (`tests/conftest.py:36-57`) points `CLAUDE_BULLY_CLAUDE` at `fake_claude.py` and makes the Anthropic and OpenAI clients refuse first use. No shipped config sets `command` (pinned by `test_no_config_names_a_claude_command`).
4. **The stages edit touches only rung 0b: PASS.** Fix-diff stat: the only file under `configs/ladder/` is `rung0_smoke_env.yaml` (a 2-line change: the comment and the params). `rung1_*` and `rung0_smoke_plain` are untouched. The other edits are rung 0b's documentation (spec row, "As planned" bullet, HANDOFF item 9) and the counts line. Rescue stage sums for the other rungs (2 + 3 + 10 + 3 = 18 for the env and Sanctuary pilots) are unchanged.

### New Breakage in the Fix Diff

None Critical or Important.

- Minor, `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md` ~line 483 (the "rungs as shipped" Task 9 bullet, unchanged by the fix): it still says "`tests/test_ladder_configs.py`'s `RUNGS` pins each rung's turn budget, reps and cell count". The fix moved `RUNGS` to `tests/test_configs.py`; the next bullet (line 484, added by the fix) states the new location, so the section is internally corrected, but the earlier sentence is now literally stale. One-clause fix when convenient; not blocking.
- Minor, `tests/test_ladder_configs.py` (`test_every_rung_config_runs_on_stubs`): `RUNGS[stem]` is looked up twice (`_, _, cells = RUNGS[stem]` then `RUNGS[stem][0]`). Style only.

### Out-of-Scope Observations

- `docs/superpowers/plans/2026-11-06-phase-7a-first-real-runs.md` lines 5324 and 5349 still hold the original `1 + 1 + 2 + 1` / `key_turns: 1` text (and the drafts copies). The implementer disclosed it as historical plan text; the spec, the binding authority, is amended. Anyone re-seeding the config from the plan would reintroduce C1, but the new stub-run test would catch it at once.
- M3 (an `--only` glob that matches nothing returns silently) and M5 (dry-run the unstubbed config) were left for Task 10 or a runner guard, as the implementer says; neither was in the ruling.

### Verdict

Fix round: All findings addressed, no new Critical/Important breakage.
