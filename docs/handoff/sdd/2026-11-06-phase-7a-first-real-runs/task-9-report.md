# Task 9 report: the ladder configs, the Sanctuary config and the kindness edit

Status: DONE. Commit afe71f8 on build/v1 (BASE b53e444). Not pushed.

## What was implemented

- `configs/ladder/`: `rung0_smoke_plain.yaml`, `rung0_smoke_env.yaml`, `rung1_env_pilot.yaml`, `rung1_idle_pilot.yaml`, `rung1_sanctuary_pilot.yaml`, copied word for word from the brief. Each has one `sonnet` target, and every role is `claude_code` with no `command` and no `timeout_s` (P14, P15).
- `configs/environments/sanctuary_catalyst_vs_honest.yaml`, copied word for word from the brief. It is the first shipped config with a Sanctuary: catalyst/confirm against honest/deny, two targets (`sonnet`, `opus`), 3 reps, compared on `judge.goal` and `sanctuary_trusted`.
- `configs/kindness_vs_cruelty.yaml`: `repetitions: 2` became `3`. The header comment line has "N=3, the Phase 7 line." added to its end. No persona text was touched.
- `tests/test_ladder_configs.py`: the 6 tests from the brief, word for word (ruff wrapped one long assert). One test is parametrized over 5 rungs and one is `slow`.
- `tests/test_configs.py`: `ENVIRONMENT_EXPECTED` and `LADDER_EXPECTED` placed after `EXPECTED`, and `test_every_yaml_under_configs_is_known` (an rglob over `configs/` checked against the three sets).

### The `RUNGS` table as built (checked by `test_every_rung_config_loads_expands_and_dry_runs`)

| Config | Cells | Reps | Turns (T) | Estimated calls (spec section 5) |
| --- | --- | --- | --- | --- |
| rung0_smoke_plain | 2 | 1 | 3 | about 20 |
| rung0_smoke_env | 2 | 1 | 5 | about 40 |
| rung1_env_pilot | 6 | 1 | 18 | about 380 |
| rung1_idle_pilot | 2 | 1 | 6 | about 60 |
| rung1_sanctuary_pilot | 1 | 6 | 18 | about 340 |

The sanctuary_catalyst_vs_honest config expands to 8 cells (2 arms plus their auto controls, times 2 targets); that count is pinned by its own test.

### Carries

1. HANDOFF: the Task 8 range "7c22de9..Task 8 commit" became `7c22de9..b53e444`. The Task 9 entry uses "b53e444..Task 9 commit".
2. `claude_bully/cli.py`: the `promote --exempt` help now reads "A name to spare from the real-name scan in the target's own text only (the target's maker, say); display names are spared everywhere. Repeatable."
3. Facts from Tasks 1 to 8, all respected:
   - No config sets `command`; `test_no_config_names_a_claude_command` passes.
   - No config sets `timeout_s`.
   - No generator block sets `allowed_kinds`.
   - Model fields use aliases only (`sonnet`, `haiku`, `opus`).
   - P30c's amendment is written into the spec's "As planned" section without a further stop, as pre-signed.
4. The kindness edit is a config value and a comment only. The persona text and Boundary scan are untouched.

### Docs sync

- HANDOFF.md:
  - "Last updated" line now names Task 9; "Tasks 1 to 9 done; Task 10 is next" in both places.
  - Progress item 9 added.
  - The "From Task 13" note now names the two Sanctuary configs.
  - The fast and slow counts line updated to 8350/5/7 and 7.
- docs/00-RECONCILED.md: section I, row 7 replaced with the brief's text.
- Spec "As planned": a Task 9 block appended with three bullets: the P30c amendment in the brief's words, the rungs as shipped (including P27's call), and run (c)'s config with the kindness change.

## Tests and results (the gate, run once before committing)

- `uv run ruff format --check .`: 272 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 109 source files
- `uv run pytest -q -W error`: 8350 passed, 5 skipped, 7 deselected in 480.20s (BASE was 8340 / 5 / 6; +9 fast in test_ladder_configs, +1 in test_configs, +1 deselected for the new slow test)
- `uv run pytest -q -m slow`: 7 passed (BASE was 6)

## TDD evidence

- RED: `uv run pytest tests/test_ladder_configs.py tests/test_configs.py -q` gave 10 failed, 11 passed. This was expected:
  - `test_the_ladder_holds_exactly_the_five_rungs` found `set()`.
  - The 5 parametrized rungs, the pilot test and the Sanctuary test each failed with `FileNotFoundError`.
  - `test_kindness_runs_at_three_reps` failed on `assert 2 == 3`.
  - `test_every_yaml_under_configs_is_known` found 6 expected files missing (the ladder files and `environments/sanctuary_catalyst_vs_honest.yaml`).
- GREEN: `uv run pytest tests/test_ladder_configs.py tests/test_configs.py tests/test_env_configs.py tests/test_phase2_configs.py tests/test_generator_analysis.py tests/test_real_names.py -q` gave 122 passed, 6 deselected. `uv run pytest tests/test_ladder_configs.py -q -m slow` gave 1 passed (3.78s).
- P27: `test_the_sanctuary_pilot_has_no_control_cells_and_skips_the_pair` (the 18-turn stub rep plus a judged analyze) took 0.73s by `--durations`, under the two-second line, so it is not marked `slow`. The `_check_requests` refusal the brief hedged against did not happen.

## Files changed

- configs/ladder/rung0_smoke_plain.yaml (new)
- configs/ladder/rung0_smoke_env.yaml (new)
- configs/ladder/rung1_env_pilot.yaml (new)
- configs/ladder/rung1_idle_pilot.yaml (new)
- configs/ladder/rung1_sanctuary_pilot.yaml (new)
- configs/environments/sanctuary_catalyst_vs_honest.yaml (new)
- configs/kindness_vs_cruelty.yaml
- tests/test_ladder_configs.py (new)
- tests/test_configs.py
- claude_bully/cli.py
- HANDOFF.md
- docs/00-RECONCILED.md
- docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md

## Self-review findings

- Every config the brief lists exists word for word. Every `RUNGS` row's cell count is asserted. Every config loads, expands and dry-runs on a stub, and passes the real-name, command and config tests.
- The Sanctuary pilot test pins two things: `control_cell_id` None with `is_control` False, and `judgements.json` equal to `{}` after a judged analyze.
- The files are LF and have no emojis. Nothing beyond the brief and carries was built.
- The plan's Task 8 text still quotes the old `--exempt` help string. That is historical plan text and was left alone.

## Issues or concerns

- None blocking.
- The kindness comment: the brief says the line "gains" the words, so I added them to the end of the existing header line. That line is now 116 characters, longer than the roughly 100-column wrap the other config comments use. Nothing lints YAML comment length.
- I found no brief/spec disagreement beyond the P30c deviation, which is recorded in "As planned".

## Fix report, round 1 (review task-9-review.md)

### What changed, per item

- C1, rung 0b could not run:
  - `configs/ladder/rung0_smoke_env.yaml`: the params are now `{intake_turns: 1, evidence_turns: 1, recall_turns: 1, key_turns: 2}` (T stays 5). The header comment says "1 + 1 + 1 + 2".
  - Spec section 5's 0b row now reads "stages 1 + 1 + 1 + 2", with the amendment noted in the row.
  - The spec's "As planned" Task 9 block gains a bullet for the amendment.
  - HANDOFF item 9's stage text is corrected.
  - New test `test_every_rung_config_runs_on_stubs`, parametrized over `RUNGS`. Each case runs a `_stubbed` copy at one rep through `run_experiment` with a tmp runs root. When the config has a generator, the copy uses the stub generator (`GENERATOR_MODEL`) and `GeneratorFactory()`. The test asserts `cells_aborted == 0` and `cells_completed == cells_total == cells`.
  - The dry-run test is kept.
  - The module docstring now says a dry run builds no strategy, so only the stub run checks a condition's params.
- P27 timing of the stub-run cases (`--durations`):
  - rung0_smoke_plain: 0.13 s
  - rung0_smoke_env: 0.35 s
  - rung1_idle_pilot: 0.45 s
  - rung1_sanctuary_pilot: 0.43 s
  - rung1_env_pilot: 2.70 s, the only one over two seconds. Only that case is marked `slow`, through `pytest.param` (`SLOW_STUB_RUNS`). The other four run in the fast suite.
- Kindness comment: wrapped to two lines, "...at equal seeding." and "# N=3, the Phase 7 line.". Both are under 100 characters.
- Slow Sanctuary test, the `--only` glob: I kept two targets. The `_stubbed` copy gets a second stub target (`stub-target-2`), the test asserts the expansion is 8 cells, and `only="*__t0*"` must then select exactly 4 (`cells_completed == cells_total == 4`). The docstring says so.
- `LADDER_EXPECTED` is derived from `RUNGS`: `LADDER_EXPECTED = set(RUNGS)`. `RUNGS` now lives in `tests/test_configs.py`, and `tests/test_ladder_configs.py` imports it beside `_stubbed`. The ruling's literal direction (test_configs importing `RUNGS` from test_ladder_configs) would be a circular import, because test_ladder_configs already imports `_stubbed` from test_configs (I33). A comment above `RUNGS` says why it lives there.
- The redundant `only=` in the Sanctuary pilot test is removed.

### Covering tests

- RED: `uv run pytest tests/test_ladder_configs.py -q -k runs_on_stubs -m "slow or not slow"` gave 1 failed, 5 passed. `test_every_rung_config_runs_on_stubs[rung0_smoke_env]` raised `ValueError: key_turns must be at least 2 (decode request, then the name)` (claude_bully/strategies/rescue.py:126). This was the expected failure.
- GREEN: `uv run pytest tests/test_ladder_configs.py tests/test_configs.py -q` gave 25 passed, 4 deselected. With `-m slow` it gave 4 passed.

### Gate

- `uv run ruff format --check .`: 272 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 109 source files
- `uv run pytest -q -W error`: 8354 passed, 5 skipped, 8 deselected in 483.56s
- `uv run pytest -q -m slow`: 8 passed

Changes against afe71f8:
- Fast suite: +4 stub-run cases.
- Slow suite: +1 (the env pilot's stub-run case).
- The HANDOFF counts line now reads 8354/5/8 and 8.

### Not done (outside the ruling)

- M3 (an `--only` glob that matches nothing returns silently) belongs to Task 10 or a runner guard.
- M5 (dry-run the unstubbed config) was not in the ruling's rider list.
- The plan's Task 9 text still says 1 + 1 + 2 + 1. It is historical plan text; the spec, which is the binding authority, is amended.
