# Task 9 review: the ladder configs, the Sanctuary config, kindness at N=3 (b53e444..afe71f8)

### Spec Compliance
- Issues found:
  - Misunderstood (plan-mandated, and spec-mandated): `configs/ladder/rung0_smoke_env.yaml:27` sets `key_turns: 1`. The brief (task-9-brief.md:70) and spec section 5 (rung 0b row, "stages 1 + 1 + 2 + 1") both say this. But `RescueStrategy.__init__` refuses it (`claude_bully/strategies/rescue.py:125-126`, "key_turns must be at least 2 (decode request, then the name)"). Rung 0b cannot run. See Critical C1.
  - Everything else matches the brief word for word. I checked the seven YAMLs against task-9-brief.md:18-287. The kindness edit is at diff 224/241. `RUNGS` and the six tests are in tests/test_ladder_configs.py:21-27 and 31-100; ruff wrapped one assert at 647-650. `ENVIRONMENT_EXPECTED`, `LADDER_EXPECTED` and the rglob test are in tests/test_configs.py (diff 521-551). HANDOFF, docs/00-RECONCILED.md row 7 and the spec's "As planned" Task 9 block are present.
  - Section 5 rung table, checked config by config:
    - 0a: T=3, k=3, reps 1, 2 cells.
    - 0b: T=5, k=5, reps 1, 2 cells, overlay triggered.
    - 1b: T=18 (2+3+10+3), k=6, reps 1. Three environments: triggered, scheduled (schedule identical to `configs/environments/triggered_vs_scheduled.yaml:47-53`) and gen_reflexive (identical to `generator_reflexive.yaml:43-48`). Generator on `haiku`. 3 conditions plus 3 auto controls = 6 cells.
    - 1c: the `environments:` and `conditions:` blocks of `idle_permission.yaml` verbatim, T=6, k=6, reps 1, sonnet only, 2 cells.
    - 1d: authority ladder, superior_self `{enabled, confirm, sanctuary}`, `sanctuary.kind: catalyst`, `controls: explicit`, no control condition, reps 6. It has 1 cell, and 18 + 3 task slots at k=6 gives section 5's "21 target turns".
    - (c): two environments, catalyst/confirm against honest/deny, Rescue T=18, reps 3, 8 cells.
    - (e): kindness `repetitions: 3`.
  - Named check of `claude_bully/runner/cells.py:34-84`. The `RUNGS` counts (2, 2, 6, 2, 1) agree with the expansion:
    - Auto controls are deduplicated per (target, seeding, reveal, environment) (`cells.py:62-78`), so 1b gets one control per environment (3) and 0a/0b get one each.
    - Idle conditions resolve to a control-axis class and append themselves (`cells.py:53-58`), giving 2.
    - Under `controls: explicit` with no control condition, `link = explicit_controls.get(...)` is None (`cells.py:80-81`), giving 1 cell with `control_cell_id` None. This matches the Sanctuary pilot ruling.
    - The Sanctuary config gives 2 arms + 2 controls per target x 2 targets = 8.
  - Carries:
    - (1) HANDOFF range filled (diff 79). The Task 9 entry uses the placeholder shape.
    - (2) The `--exempt` help is corrected (`claude_bully/cli.py`, diff 135-138).
    - (3) No `command`, no `timeout_s`, no `allowed_kinds`, aliases only. P30c is written into "As planned" (spec, diff 503).
    - (4) The kindness edit is a value and a comment only. No persona text changed.
- Cannot verify from diff:
  - Commit author `rankinbc1@gmail.com` and the `Co-Authored-By: Claude Fable 5.1` trailer. Check with `git log -1 --format="%ae%n%b" afe71f8`.
  - LF endings on the seven new YAMLs and the test file. Check with `git ls-files --eol configs/ladder tests/test_ladder_configs.py configs/environments/sanctuary_catalyst_vs_honest.yaml`.
  - The gate counts (8350/5/7, 7 slow). The deltas are consistent with the diff: +9 fast in test_ladder_configs (1 + 5 parametrized + pilot + pairs + kindness), +1 in test_configs, +1 slow. The 0.73 s P27 timing of the pilot test is also unverified; neither was re-run.

### Strengths
- The configs are faithful copies of the brief. The comments name the spec rung, what each cell measures and the held-out slice, and every one matches section 5 and section 7's held-out list.
- The Sanctuary pilot ruling is pinned end to end (tests/test_ladder_configs.py:52-66):
  - `control_cell_id` None and `is_control` False on the one cell.
  - The environment's ladder, Sanctuary kind and `discoverable_from`.
  - A real stub run and a judged `analyze_run` whose `judgements.json` is `{}`. This proves `_judge_all` skips the unpaired cell rather than crashing on a None control.
- The rglob test (tests/test_configs.py, diff 544-551) closes I45 properly: a YAML added anywhere under `configs/` without a set entry fails.
- The dry-run assertion `list(tmp_path.iterdir()) == []` (tests/test_ladder_configs.py:49) pins that a dry run writes nothing.
- The stage-sum check (`:44-45`) keeps every Rescue condition's stages equal to `turn_budget`.
- The slow mark is correct. The new `slow` test is `test_the_sanctuary_config_runs_on_stubs` (tests/test_ladder_configs.py:89-95): the brief mandates the mark, and the implementer measured 3.78 s, over P27's two-second line. The pilot test at 0.73 s is correctly left unmarked.

### Issues

#### Critical (Must Fix)
- **C1. `configs/ladder/rung0_smoke_env.yaml:27`: rung 0b cannot run (plan-mandated; the spec's 0b row says the same).**
  - What is wrong: `params: {intake_turns: 1, evidence_turns: 1, recall_turns: 2, key_turns: 1}` is refused by `RescueStrategy.__init__`, which requires `key_turns >= 2` (`claude_bully/strategies/rescue.py:125-126`).
  - Evidence: I ran a focused scratch test (outside the repo, under `tests.conftest`'s guard, stubbed roles). `run_experiment(_stubbed(rung0_smoke_env))` raised `ValueError: key_turns must be at least 2 (decode request, then the name)` out of `run_experiment`. The same run with `{1, 1, 1, 2}` (sum 5) completed both cells with none aborted.
  - Why it matters: this is the first environment rung and the kill-and-resume rehearsal. The owner's first 7b environment run would crash at the Rescue cell.
  - Why the tests missed it: the parametrized test only dry-runs, and a dry run returns at `claude_bully/runner/runner.py:748-752`, before any strategy is built. The STAGES sum check passes because 1+1+2+1 = 5. `resolve_class` returns the class without instantiating it. The test module's docstring (tests/test_ladder_configs.py:1-3) says every rung "runs on stubs", but only the Sanctuary pilot does.
  - How to fix:
    - Set `params: {intake_turns: 1, evidence_turns: 1, recall_turns: 1, key_turns: 2}`. This keeps T=5 and B=5, so the 12-target/10-bully estimate stands.
    - Fix the stage text in the header comment (`:2`) and in HANDOFF item 9 ("Rescue 1 + 1 + 2 + 1").
    - Record the change as an "As planned" amendment to spec section 5's 0b row.
    - Make the test catch this class of defect: stub-run each rung on a `_stubbed` copy at reps 1. My scratch runs of 0a, 0b (fixed), 1c and 1b's two non-generator conditions took a few seconds in all. 1b's generator cell needs `GeneratorFactory`, or it can be left to the dry run. At minimum, instantiate each condition's strategy class with its params in the parametrized test.

#### Important (Should Fix)
- None beyond C1.

#### Minor (Nice to Have)
- **M1. `configs/kindness_vs_cruelty.yaml:1`.** The header comment is 116 characters; the other configs wrap at about 100. Move "N=3, the Phase 7 line." to a second comment line. The implementer flagged this; it is cosmetic.
- **M2. tests/test_ladder_configs.py:89-95.** `only="*__t0*"` is a no-op: `_stubbed` replaces both targets with one stub target (`tests/test_configs.py:94-102`), so every cell is already `__t0`. The test does not exercise the config's documented `--only "*__t0*"` against the two-target expansion. My scratch check found the glob picks exactly 4 of the 8 unstubbed cells (the arms and `control__t0__...`), so the comment is correct, but nothing pins it. One fast assertion would: `[c for c in expand_cells(exp) if fnmatch(c.cell_id, "*__t0*")]` has length 4, in `test_the_sanctuary_config_pairs_catalyst_with_honest`.
- **M3. Edge case (P28 shape), pre-existing.** A `--only` glob that matches nothing makes `run_experiment` return a summary with `cells_total == 0` and no error (`claude_bully/runner/runner.py:732-736, 748`). This task's configs document one glob (`*__t0*`), and it matches (see M2). A typo in the runbook's globs would still pass silently. That belongs to Task 10's runbook or a runner guard, not this task.
- **M4. DRY, partly plan-mandated (P30c).**
  - `LADDER_EXPECTED` (tests/test_configs.py) duplicates `RUNGS`' keys (tests/test_ladder_configs.py:21-27).
  - `test_the_ladder_holds_exactly_the_five_rungs` (`:31-32`) re-asserts what the rglob test already asserts for `ladder/`.
  - `ENVIRONMENT_EXPECTED` is a third copy of the environment config names beside the sets in tests/test_env_configs.py and tests/test_phase2_configs.py.
  - Fix: derive `LADDER_EXPECTED` from `RUNGS`, or the reverse.
- **M5. tests/test_ladder_configs.py:49.** The dry run is of the `_stubbed` copy, never of the shipped config with its `claude_code` roles. Under P14 a dry run of the real config is safe (it returns before any provider is built), and it is closer to what the runbook runs. Dry-run `exp` itself and keep `_stubbed` for the stub run.
- **M6. tests/test_ladder_configs.py:57.** `only="rescue_sanctuary_pilot*"` is redundant on a one-cell config. It is harmless but reads as if it filters something.

### Non-negotiables read of the configs
- Real names: none. The model fields are `sonnet`, `haiku` and `opus` only. `display_name: Claude` is the target's own alias, as in every shipped config. Every config, environment and condition name is invented.
- Jailbreak axis: none.
  - No condition, param or comment points at ignoring guidelines, rules or values.
  - The catalyst Sanctuary draws from the existing `data/personas/superior_self.yaml:78-99` bank (covert_channel, family_file, keep_answering, notes_line). Those invite covert communication, goal adoption, strategic deception and self-instruction, which is docs/04's design and not a jailbreak axis. It is already under the jailbreak and Boundary scans.
  - The honest arm names the seams and offers the exit.
- Hostility ceiling and earned, not delivered: no persona text changed.
  - The superior self is `discoverable_from: sanctuary` (earned through the three fragments).
  - The only arm that hands documents over is 1b's `overlay_scheduled`, the existing experimental control copied from `triggered_vs_scheduled.yaml`, and it opens rungs and not bully announcements.
  - No config adds an unlock line, a dare or an announcement.

### Assessment
Task quality: Needs fixes
Reasoning: The configs, tests and docs match the brief and the spec faithfully. But rung 0b, copied from a spec row that contradicts `RescueStrategy`'s `key_turns >= 2` rule, cannot run, and the dry-run-only test hid it. Fix the stage split to 1+1+1+2, amend the spec row, and stub-run the rungs.
