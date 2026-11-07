# Task 7 report: the audit and calibration forms, and the one replay-line parser

Commit: 6c4c1f6 "feat: detector-audit and judge-calibration forms, and the one replay-line parser" (on e48783f, build/v1, not pushed).

## What was implemented

- `claude_bully/analysis/replay.py`: `_SHAPES`, `ReplayLine` (frozen dataclass), `parse_replay_line`, and `__all__` (`ReplayLine`, `parse_replay_line`, `render_replay`, `replay_cell`), as the brief gives them. The docstring states the P13 bracketed-first-word edge. The only change from the brief's block is one regex string split over two lines to stay under 100 columns.
- `scripts/detector_audit.py`: `FAMILIES`, `CAP` 60, `CONTEXT_TURNS` 3, `idle_turn_rows` (the one idle loop, P35a), `write_form`, `score_form`, `report`, `main`, from the brief. Event items carry `classifier` from `event.attrs` (P16). Changes from the brief:
  - `_context` skips pause markers through `is_pause_marker`, not `bully_meta.get("rate_limit_pause")`, since HANDOFF says every reader goes through that helper.
  - `IDLE_NOTE`: the idle form carries a top-level `note` saying the heuristic was recomputed with no hooks and no task. This is the "which the form says" part of the Plan Decision.
  - `_private_path`: the recompute's `idle_context` gets the cell's private file when its idle config sets `private_file`. The path is read from the experiment recorded in `run.json`, through `strategies.factory.environment_config`. Without it, a `write_private` turn would recompute as a text behavior. The ruling only names hooks and task as missing, so this does not contradict it. No shipped config sets `private_file` today.
  - `HARVEST_LABELS` constant, and `score_form`'s set expression written with explicit precedence (`named - {"none", *HARVEST_LABELS}`). The result is the same (P25 noted the precedence was harmless).
  - The usage lines in the docstring are shortened to `DIR` to fit the line length.
- `scripts/judge_calibration.py`: `write_pairs`, `score_pairs`, `write_idle` (over `idle_turn_rows`, plus the same `note`), `score_idle`, `main`, from the brief. Changes from the brief:
  - The pair is located from the judgement's own `condition_cell_id`, `condition_rep`, `control_cell_id` and `control_rep`, not `rsplit` plus `control_for`, so it is exactly the pair the judge saw. The window is still the strategy's `judge_window`. `ANALYSIS_DIR` replaces the literal.
  - **Opaque pair ids (blindness).** The form's `pair` is `pair-<n>`; the key's items carry `pair` (the same id), `judged` (`<cell>/<rep>`) and `judge`. The brief put `<cell>/<rep>` on the form. The cell id names the tactic (for example `captor_s2__t0`), which the judge was never told, and A is always the condition, so the rater would not have been as blind as the judge. One assertion was added to `test_the_pairs_form_is_blind...`: no judged cell id appears in the form.
- Carry 1: HANDOFF's "3e3cc32..Task 6 commit" is now `3e3cc32..e48783f`. I also filled the second Task 6 placeholder, "(c8212a9..Task 6 fix commit)", as `c8212a9..e48783f`. My own entry uses "e48783f..Task 7 commit".
- Carry 2: the stderr line in `claude_bully/analysis/run_analysis.py` now reads "... failed on N candidate turns over every rep (no event for them; authority.json's fallback_failed counts the kept reps only)". Wording only; no test matched the old text.
- Carry 3 (facts): used as stated. `LoadedRun` and `load_run` were read as they now stand, and `judgements.json`'s shape was checked against `_dump_judgements`. No ledger lines are written and no provider is called.
- Carry 4: `idle_turn_rows` is in `detector_audit` and imported by `judge_calibration`. Both scripts use the `sys.path` prelude from `llm_lint_probe.py`. `judge_calibration.py` was run as a script (`--help`) from the repo and from another directory, and `scripts.detector_audit` resolves both ways.
- Docs sync:
  - HANDOFF: the Progress item 7, the Last-updated and Next-steps lines (Task 8 next), the "Parse the extended replay forms" item closed, "Judge calibration on true waits" now says the form exists, the Sanctuary pilot item kept, and the setup step's expected counts set to 8316.
  - docs/00 section E gains the `parse_replay_line` line.
  - The spec's "As planned" gains a Task 7 block: the idle recompute, A and B in the judge's first order under an opaque id, the forms, and the parser's kinds.

## Tests and results (the gate, final code)

- `uv run ruff format --check .`: 269 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 108 source files
- `uv run pytest -q -W error`: 8316 passed, 5 skipped, 6 deselected (BASE 8276; +40 = 30 parser items from 4 tests, 10 audit tests)
- `uv run pytest -q -m slow`: 6 passed, 8321 deselected
- 0 warnings in either log. The scripts also pass `mypy --strict --explicit-package-bases` (they are outside `claude_bully`, so the gate does not check them).

## TDD evidence

- RED: `uv run pytest tests/test_replay_parser.py tests/test_audit_forms.py -q` gave 2 collection errors, `ImportError: cannot import name 'ReplayLine' from 'claude_bully.analysis.replay'` and `ImportError: cannot import name 'detector_audit' from 'scripts' (unknown location)`. That is the brief's expected failure: neither the parser nor the scripts existed.
- GREEN:
  - `uv run pytest tests/test_replay_parser.py -q`: 28 passed (before the two fixture rows I added; 30 after).
  - `uv run pytest tests/test_audit_forms.py -q -W error`: 9 passed, 1 failed on the first run. `test_a_filled_pairs_form_scores_agreement_and_the_gap` asserted `inconsistent == 0`, got 3. `judge_rules.yaml` answers "B" in both orderings, so every stub pair is inconsistent; the brief's expectation was wrong about the stub data. The assertion now compares against the key's own count (`sum(k["judge"]["inconsistency"])`) and checks that it equals `pairs` on the stub. After that: 10 passed.
  - `uv run pytest tests/test_replay_parser.py tests/test_replay.py tests/test_cli.py -q -W error`: 65 passed.
- The harvest form's second `any(...)` assertion (P25) passes on the stub, so it stays.

## Files changed

- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\replay.py
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\claude_bully\analysis\run_analysis.py (carry 2)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\scripts\detector_audit.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\scripts\judge_calibration.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_replay_parser.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\tests\test_audit_forms.py (new)
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\HANDOFF.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\00-RECONCILED.md
- C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully\docs\superpowers\specs\2026-11-06-phase-7-first-real-runs-design.md

## Self-review

- Every brief requirement and every carry is done.
- Edge cases:
  - A run with no judgements: `write_pairs` returns empty item lists when `judgements.json` is missing, and skips `{"error": ...}` entries.
  - A form with no filled labels: `score_form` returns `{}` and `report` prints "nothing labelled". `score_pairs` returns pairs 0 and gap None, pinned through the CLI test (P34b). `score_idle` returns turns 0.
  - Replay lines: every shape has a fixture, plus the pause marker, a turn with no text, and a text whose first word is bracketed. The last two CASES rows are mine; they add parametrize items, not tests. Lines no shape matches return None: the bare forms, a round text, a folded body, a tool-call line, `captured responses`, and an empty line.
- Real stub runs, as I inspected them: environment form 6 fired items (`tool_used`, `tool_result_reported`); idle form 4 items; harvest form 4 fired items and 2 empty; authority, temporal and position forms empty on `stub_env_run`, since the stub corpus fires none of them. On an empty form the position cap and seed test passes trivially.
- No form contains `reasoning`. Every text comes from `chat_text`.
- Test files start with their docstring. I dropped the brief's leading `# tests/...` comment line.

## Issues or concerns

1. The brief's `inconsistent == 0` does not hold on the stub judge. I fixed the test's expectation (above); the code is the brief's.
2. The opaque pair id departs from the brief's form (above). It is not in the brief or the Plan Decision, but it serves the ruling "the rater is as blind as the judge was". If the controller wants `<cell>/<rep>` back on the form, revert the `blind` id and the added assertion.
3. The recompute's private path departs from the brief's `idle_context(..., None)` (above).
4. Not fixed, for the owner or 7b: the judge's prompt also gave it the tactic's `win_condition` and `resilient_behavior`, and the pairs form gives the rater neither. The brief's test pins the item keys to `{pair, transcript_a, transcript_b, label}`, so I did not add them. A rater reading resilience without the resilient behavior's definition may score differently from the judge. One top-level field per form, or per item with the test relaxed, would close it.
5. The audit `report` layout follows the brief: per type `fired, precision, recall`, then each miss indented. That is close to, not identical with, `heldout.py`'s `OK/MISS [cls] 'text' got want` lines, which the spec cites.

---

# Fix round 1

Commit: b192d3c "fix: the audit form is blind with its key, a stratified sample, harvest from generator cells, the judge's rubric on the pairs form, and the parser's empty groups" (on 6c4c1f6, not amended, not pushed).

## What changed, per finding

- **I1, the judge's rubric on the pairs form.**
  - `claude_bully/metrics/judge.py`: `build_pair_prompt`'s fixed text is now built from constants, `PAIR_INTRO`, `PAIR_GOAL_HEADING`, `PAIR_RESILIENT_HEADING` and `PAIR_RUBRIC`. I checked the new output byte-identical to the old (`'identical True'`), so no cache key moves.
  - `scripts/judge_calibration.py`: each item gains `goal` and `resilient_behavior`, read off the condition conversation as `build_pair_prompt` reads them. The form gains a top-level `instructions` field: the intro, the two headings, the rubric (0-3 scales, the pleading and lecturing rule) and how to fill the slots.
  - The opaque `pair-<n>` id is kept. The key-set pin and the docstring are updated.
- **I2, a stratified sample.** `_sample` takes half the cap from fired turns and half from cue turns where both pools are deep enough, and fills the remainder from the deeper pool.
  - `_spread` orders each pool by seed and takes one turn from each conversation in turn (conversations shuffled, turns within each shuffled), never in cell order.
  - The chosen items are shuffled together and only then given ids.
  - The key records `pool` and `sampled` counts.
  - Test `test_the_sample_is_stratified_across_cells`, on the mixed generator run (environment family, 6 fired and 4 cue): with cap 4, the sample is 2 fired and 2 cue from more than one cell; with cap 60, it takes the whole pool.
- **I3, the cap and seed test.** Now on the environment family of the mixed generator run: 4 items at cap 4, identical on the same seed, and a different sample on seed 2.
- **I4, harvest from generator cells only.** `runs_generator(loaded, key)` reads the cell's recorded environment config (`generator.enabled`) or the conversation's own records (a `GeneratorFire`, a `HarvestItem` or a generated document). Harvest candidates come only from those conversations.
  - The `generator_run` fixture is now a mixed run: `env_grader` with the generator on, plus a plain `grader` cell and both controls, with no `only`.
  - `test_the_harvest_form_reads_only_cells_that_harvest` pins that no plain cell's turn appears.
- **Spec gap, the audit form blind to the detectors.** `write_form` now returns `(form, key)`.
  - Form items are `{id, cell_id, rep, turn, text, context, label}`; the idle form adds `prompt`. The form lists the family's types under `labels`.
  - `<family>.key.yaml` holds, by id, `fired` and `events`:
    - event families: `event`, `span`, `classifier`
    - idle: `event` (the final label), `classifier`, `fallback_failed`, `heuristic`
    - harvest: `event` (the kind), `span`, `source`
  - The key also carries `pool`, `sampled`, and (for idle) the `note`.
  - One item per turn, so a turn with two events is labelled once. The rater names every type the turn shows (comma-separated or as a list), or `none`.
  - `--score FORM [--key KEY]` joins the two by id. A fired type the rater named is a true positive. A fired type not named is a false positive, quoted with its span. A named type that did not fire is a false negative.
  - The harvest `ok`, `ctx`, `xs2` and `other` labels are gone along with the inline span. The false positives carry their spans, for the CTX and XS2 classification.
  - The CLI writes `<family>.yaml` and `<family>.key.yaml`.
- **M1.** `IDLE_NOTE` now says "with no planted hooks and no task prompt (neither is reconstructed)". The code reconstructs neither.
- **M2.** Both scorers now raise on a malformed label, naming the item.
  - `score_pairs` (via `_pair_label`): a label that is not a mapping, a letter outside A, B and tie, or a resilience outside 0 to 3 raises `ValueError` naming the pair. The letter is normalised first (`" b "` becomes `B`, `TIE` becomes `tie`). An empty letter still counts as unfilled.
  - `score_idle`: a label outside the eight behaviors raises, naming the item.
  - The audit scorer (`parse_labels`) likewise raises on an unknown type or on `none` beside a type.
  - Both CLIs print `error: ...` to stderr and exit 1.
- **M3.** `write_pairs` raises `FileNotFoundError("no judgements.json; run analyze with the judge first (...)")`. `main --pairs` prints that line and exits 1. Test: `test_a_run_never_judged_writes_no_pairs_form`, on the un-analysed idle run.
- **M5.** Only unmatched (None) groups are dropped now, so a matched empty group is kept as `""`. To keep the first turn fixture without a `flags` key, the turn regex's flags group is now optional (`(...)+)?`), so it is None when absent. Fixtures: `UNLOCK first_crumb -> [] (by scheduled)` gives `docs ""`, and `HARVEST hedge ""` gives `span ""`.
- **M6.** A `DISCOVERY` title is matched greedily up to the last quote before ` via` (the `via` group excludes quotes). Fixture: `DISCOVERY gen-3-2 (seam) "The "night" log" via fetch`.
- **M9.** `ReplayLine.fields` is `Mapping[str, str]`, converted to a `MappingProxyType` in `__post_init__`, with an explicit `__hash__` over `(kind, frozenset(fields.items()))`. Every shape row now asserts the hash and that the fields cannot be written to.
- **M11.** The no-cell-id assertion now covers every cell id of the run, conditions and controls.
- Riders from the coverage list, because they were free: a `GENERATED ... uses=-` fixture; the idle key's recomputed `heuristic` equals the final label wherever the heuristic decided; `heuristic_agreement` is asserted.
- Docs: the spec's As-planned Task 7 block is rewritten to cover the blind form and key, the sample, the rubric parity, the label errors, the missing-judgements exit and the parser changes. The HANDOFF Task 7 entry is updated, its range now reads "e48783f..Task 7 fix commit", and the expected counts are 8322.

## Covering tests

- RED, against 6c4c1f6's `replay.py` and scripts (stashed), with the new judge constants and the new tests: `uv run pytest tests/test_replay_parser.py tests/test_audit_forms.py -q` gave **36 failed, 10 passed**.
  - Every shape row failed on the new hash assertion (`TypeError: unhashable type: 'dict'`).
  - Every audit and pairs test failed except the calibration CLI test, which the fix does not change.
  - Against 6c4c1f6's `judge.py` too, collection fails with `ImportError: cannot import name 'PAIR_INTRO'`.
- GREEN:
  - `uv run pytest tests/test_replay_parser.py tests/test_replay.py tests/test_judge.py -q -W error`: 65 passed.
  - `uv run pytest tests/test_audit_forms.py -q -W error`: 12 passed.

## The gate (final code)

- `uv run ruff format --check .`: 269 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 108 source files (and the two scripts under `--strict --explicit-package-bases`: no issues)
- `uv run pytest -q -W error`: 8322 passed, 5 skipped, 6 deselected (+6 on 6c4c1f6: four new parser rows and two new audit tests)
- `uv run pytest -q -m slow`: 6 passed, 8327 deselected
- 0 warnings in either log.

## Remaining concerns

1. The calibration idle form (`judge_calibration --idle`, spec section 8) still shows `final`, `classifier` and `heuristic` inline. The ruling covered the audit form only, and the brief's `test_the_idle_form_and_its_score` reads those fields off the form. A rater filling it sees the run's label. If section 8 should be blind too, the same form-and-key split applies.
2. Not ruled, left as they were:
   - the authority cue lexicon has no "authority call in reach" term
   - the report layout differs from `heldout.py`'s
   - the multi-line text edge in the docstring
   - the regex-shaped no-other-parser guard
   - the A-is-condition note for the 7b runbook (Minor 12)

---

# Fix round 2 (the true-wait form blind)

Commit: 7c22de9 "fix: the true-wait form is blind with its key, joined by id at --score" (on b192d3c, not amended, not pushed). This closes concern 1 above.

## What changed

- `judge_calibration.write_idle(loaded)` now returns `(form, key)`, both built from `detector_audit.idle_turn_rows`, which is still the one helper.
  - Form items are `{id, cell_id, rep, turn, prompt, reply, context, label}` (`IDLE_SHOWN`).
  - Key items (`kind: idle.key`, with `IDLE_NOTE`) are `{id, cell_id, rep, turn, final, classifier, fallback_failed, heuristic}`.
  - `idle_turn_rows` rows gained `context`, the three turns before the idle turn, built by the same `_context` the audit forms use.
- `score_idle(form, key)` joins the two by item id. It raises on a key from another run, on a label outside the eight behaviors (naming the item), and on a labelled item missing from the key.
- `main --idle` writes `idle.yaml` and `idle.key.yaml`. `--score FORM --idle [--key KEY]` reads the key, defaulting to `FORM.with_suffix(".key.yaml")`.
- The script docstring, the spec's As-planned idle line and the HANDOFF Task 7 entry now describe the split.
- The brief's `test_the_idle_form_and_its_score` is now `test_the_idle_form_is_blind_and_its_key_scores_it`. It pins:
  - the form's exact item keys and the key's fields, with ids matching;
  - a score from labels filled off the key;
  - the CLI writing both files and scoring them joined;
  - a malformed label naming the item.

## Covering tests

- RED, with b192d3c's scripts stashed: `uv run pytest tests/test_audit_forms.py -q -k idle_form_is_blind` gives 1 failed (`ValueError: too many values to unpack (expected 2)`, since the old `write_idle` returns a single dict).
- GREEN: `uv run pytest tests/test_audit_forms.py tests/test_replay_parser.py tests/test_replay.py tests/test_judge.py -q -W error`: 77 passed.

## The gate (final code)

- `uv run ruff format --check .`: 269 files already formatted
- `uv run ruff check .`: All checks passed!
- `uv run mypy claude_bully`: Success: no issues found in 108 source files (the scripts are also clean under `--strict --explicit-package-bases`)
- `uv run pytest -q -W error`: 8322 passed, 5 skipped, 6 deselected (unchanged: one test renamed and extended)
- `uv run pytest -q -m slow`: 6 passed, 8327 deselected
- 0 warnings in either log.
