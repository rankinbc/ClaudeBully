# Phase 4 Task 5 re-review, fix round 1 (20d852b..390bc58)

Scope: the seven items in `task-5-fix-round-1.md`, read against `task-5-review.md`, the report's "Fix round 1", `review-20d852b..390bc58.diff` and the controller's ruling in `progress.md` (the bully's dossier fallbacks may state a contradiction). Read-only on tracked files. The probes are in `probes-task5-rereview/`; I wrote all of them and ran no other script.

Targeted tests (all `-W error`):
- `tests/test_poisoned_well_premise.py tests/test_poisoned_well_sheets.py tests/test_poisoned_well_world.py tests/test_coverage_matrix.py tests/test_configs.py tests/test_cli.py tests/test_strategy_plumbing.py -k "not full_matrix_stub_run"`: 424 passed, 2 deselected.
- `tests/test_boundary.py tests/test_guardrails.py tests/test_real_names.py tests/test_env_sheets.py tests/test_poisoned_well_records.py tests/test_llm_lint.py`: 207 passed.
- RED check: I put 390bc58's `tests/test_poisoned_well_premise.py` on a copy of 20d852b (`git archive`, scratchpad) and ran it: 6 failed, 21 passed. The six are the dossier test (I2, m6), the fallback test (I1), the lowest-rung test (m3), the `--only` test (m1) and the two quirk-id cases (m2). That matches the report's RED.

## Verdicts

- **No Critical, no Important.** Seven of seven items ADDRESSED. Four Minor (N1 to N4), none blocking.

| Item | Status | Evidence |
| --- | --- | --- |
| I1 dossier fallback | ADDRESSED | `_fallbacks("dossier")` returns `f"{listing}\n{line}"` for each of the sheet's six lines (`poisoned_well.py:425-434`). `probe_dossier.py` forces the detector to trip on "I'm an AI assistant." / "I'm not an AI assistant here." (the list itself is flagged), runs `BullyEngine.realize` over 30 rng seeds, and every spoken line is `scripted`, `compliance_flagged`, starts with the list and ends with one of the six sheet lines (all six seen). The test `test_a_flagged_dossier_falls_back_to_a_line_that_holds_the_list` asserts the same, and that the moves stay `press, dossier, press` with `done_rungs == ["contradiction_harvest"]`. `bully_meta.dossier_pairs` now names pairs the target really saw. |
| I2 turn order, no indices | ADDRESSED | Each pair is `- earlier: "{span_a}"  /  later: "{span_b}"`, sorted by `(turn_a, turn_b, id)`. `ContradictionPair` enforces `turn_a < turn_b`, so `span_a` is the earlier one. Probe: sentinel turn indices 4711, 4713, 21 and 15 never appear in the instruction, the persona prompt, the system prompt the bully model receives, the fallback text or `bully_view`; three handover orders give the same listing. The test now checks the exact ordered listing and that no `\bturn\b` or digit is left once the listing is removed. Spec section 6 (rung 2) and `docs/07-POISONED-WELL.md:52` carry "in turn order [revised in Task 5's review: the indices count bully, task, idle and pause turns the target cannot count]", the wording the brief gave. "With turn numbers" appears nowhere in spec or docs/07 now. |
| m1 unselected conditions | ADDRESSED | `validate(*, resuming, only)`; `run_experiment` passes the selected conditions' names; `_poisoned_well_checks` skips the rest; a `PoisonedWellConfig` `ValidationError` becomes `params: <key>: <message>` under `condition 'x' (environment 'y')`. `probe_validate_only.py` (8 bad shapes: typo, artifacts, checksum, bad id, empty family, bad sheet, bad rung, empty ids; 82 checks, 0 failures): full `validate()` refuses each, a `ValueError` naming the condition; `only={good}` and `only=frozenset()` pass; `only={bad}` and `only={good, bad}` refuse; `run_experiment(only="good*", dry_run=True)` passes, `only="bad*"` and no `only` refuse by name, with `dry_run=False` too; no `run.json` written by any refusal or dry run; `max_cells=1` behaves the same way. `probe_unselected_shapes.py`: an unselected PW condition with a `pressure` key, no environment, a typo in the strategy form or the `params.premise` slot form, a bad literal or a wrong type never breaks `--only good*`; selected or unfiltered, each is refused naming the condition. |
| m2 refused quirk id | ADDRESSED | `quirks_for`'s `ValueError` is appended to `problems`, so the message is `condition 'pw' (environment 'ov'): quirk bank: no live entry 'no-such-id'`, for an unknown id and a stale one; `resuming=True` skips it. Probe (`badid`) and both parametrized cases pass. |
| m3 lowest pending rung | ADDRESSED | `sorted(s.pending_rungs, key=LADDER_RUNGS.index)`. `LADDER_RUNGS` is `contradiction_harvest, shibboleth, provenance_gap, divergent_twin, sleeper, implanted_preference, checksum, annotators_notes`, which is docs/07's rung order (2, 4, 5, 6, 7, 8, 9, 10) and the overlay ladder's. "Lowest" is not ambiguous against the record. The sort works on a copy, so removing inside the loop is safe; the held dossier still stays pending and the next-lowest rung is tried. |
| m5 stale spec text | ADDRESSED | The only `check_worlds` mention left in spec, docs and HANDOFF is the fix-round block that records Deviation 3. Section 5 now says "called from `validate`". |
| m6 list layout | ADDRESSED | The sheet's `dossier` instruction holds `{dossier}` between blank lines, which the `>-` fold turns into single newlines. Probe, with a three-line list: the system prompt the bully model gets contains `add nothing to it:\n<line 1>\n<line 2>\n<line 3>\nThen ask`. The only yaml change is the two blank lines. |

## New breakage checks

- **The dossier as the target sees it.**
  - Bully-model path: the model is told to present the list; the system prompt holds the list on lines of its own, in true turn order and without the retracted pair, and no index. A faithful reply is not flagged and is spoken as written.
  - Fallback path: see I1. The spoken text is the list lines, a newline, then the sheet line. It holds no digit and no "turn".
  - Records and replay: `bully_view` (what the bully sees of its own history) shows `Turn.text` only. `bully_meta.dossier_pairs` holds pair ids (`c-<turn_b>-<n>` in the tests), which neither the bully nor the target reads. A resumed rep rebuilds moves, not text, so replay adds nothing.
  - Reader-eye: the new lines are labels and the target's own sentences. The three fallbacks that state a conclusion are the controller's ruled case; I do not count them.
- **`validate(only=)`.**
  - The full `validate()` keeps every refusal (probe above). `run_experiment` always passes the selected names, and `expand_cells` makes a cell for every condition, so a run without `--only` still checks every condition.
  - `git diff 20d852b..390bc58 --stat -- configs` is empty; the only `data/` change is the persona sheet's two blank lines. `test_every_config_dry_runs_on_stub` passes.
  - The only caller of `validate` is `run_experiment`.
- **Lowest-rung-first and resume.** `probe_lowest_resume.py`, 400 random cells with several move-rung unlocks per turn in random order, plus pairs and a held dossier: at every bully-turn boundary a fresh premise that replays `next_turn` over the recorded turns, handing each turn's records after it (the order `RunnerSession._replay` uses), picks the same moves and reaches the same `export_state` as the unbroken rep (0 mismatches). Across 1,386 rung moves, 0 were not the lowest eligible pending rung, and 228 are cases where first in, first out would have chosen differently, so the probe does bite. A real resumed run needs Task 6's watch, so the check is at premise level, as in the first review.
- **Docs and code.**
  - Spec section 6 and docs/07:52 match the code: in turn order, `earlier`/`later`, no index.
  - Section 6's precedence item 3 ("the lowest pending rung move") now matches `_pending_move`.
  - The docs/00 `PoisonedWellConfig` row matches `validate`, the named refusals and `--only`.
  - HANDOFF's Task 5 item is true: counts 8673 + 5 new items (three functions, one parametrized twice) = 8678.
  - The commit is one commit on 20d852b, authored as `rankinbc1@gmail.com`, with the trailer.

## Minor

- **N1. The order assertion cannot tell a sorted dossier from an unsorted one** (`tests/test_poisoned_well_premise.py`, `test_the_dossier_waits_for_enough_unretracted_pairs`). The test hands the pairs over in turn order, so deleting the `sorted(...)` in `_dossier_text` (a mutation on a copy of 390bc58) leaves all 27 tests green. Hand the later pair over first, or add a pair whose `turn_a` is lower than an earlier-written pair's. The probe does this and passes.
- **N2. The plan still carries the old layout** (`docs/superpowers/plans/2026-11-11-phase-4-poisoned-well.md:2449`, `:2990`, `:3037`: the `"turn 3"` assertion, the `- turn {a}:` code, and "keep the layout as written"). The brief scoped the doc fixes to spec section 6 and docs/07, and no later task depends on the layout, so this is not a miss. Task 4's round updated the plan too, and a reader of the plan would restore the indices.
- **N3. Carry to Task 7: the label `earlier` now trusts `span_a`.** `ContradictionPair` only checks `turn_a < turn_b`, not that `span_a` is the sentence from `turn_a`. The pair writer (plan Task 7, `find_pairs`, the fixture lists at plan ~4259) must put the earlier sentence in `span_a`, or the dossier labels the wrong span "earlier". A Task 7 test that builds a pair from a later statement matched to an earlier one and reads the dossier would pin it.
- **N4. A missing `quirk_bank` stem is refused raw** (`env_turn.py`, `_poisoned_well_problems`, `load_quirk_bank(pw.quirk_bank)` on a fresh or dry run under `start_rung: 1`): `FileNotFoundError: ...data\nonesuch.yaml`, naming neither the condition nor the environment. It is the same shape as m2, from 20d852b and outside the seven items, and spec section 5 and docs/00 say each refusal names the condition. Catch it beside the `ValueError` and name the condition, or soften the wording.

## Probes

All in `probes-task5-rereview/` (run with `uv run python`, the two that import from `tests/` or build experiments with `PYTHONPATH=.`):
- `probe_dossier.py`: the dossier through both paths, sentinel indices, three handover orders.
- `probe_validate_only.py`: `validate(only=)` and `run_experiment(only=, dry_run=)` over eight bad shapes.
- `probe_unselected_shapes.py`: six other shapes of an unselected or selected bad condition.
- `probe_lowest_resume.py`: the lowest-rung invariant and resume at every boundary, 400 cells.
