# Task 14 carries

The brief closes seven Phase 3 minors. The Phase 4 ledger also carried these items to Task 14; they bind this task too. Each is small; each gets a test that fails without its fix (RED first), and most are test-only.

**Preflight.** P30 names Task 14; read it in `preflight.md`.

**From Task 2 (review M2-M5, M7).** Tests that fail when you:
- remove the once-per-process record key (`records_env.record_key` use in `EnvironmentSession._hand_over_records`);
- drop `target_model=` in the runner or in `load_run`;
- move `factory.check_condition` after `RunEnvironments.validate()`;
- drop the `PSEUDO_RUNGS` skip, or the empty-block filter in `system_prompt_section`.

Also: a non-mapping slot value is refused naming its condition.

**From Task 5 (re-review N1, N4).**
- A test that fails when the sort in `_dossier_text` is removed.
- A missing `quirk_bank` stem is refused naming the condition, not raised as a raw `FileNotFoundError`.

**From Task 11 (review M1, M4).**
- **M4, the real-name scan over `configs/`** (non-negotiable 2). Extend the real-name scan to every YAML under `configs/`, with a test that fails on a planted real name.
- **M1, escape quote marks in replay spans.** Cover the new `QUIRK`, `CHAIN` and `CONTRADICTION` lines and the older `HARVEST` and `TRIGGER` lines (Phase 3 Task 4 M8). The renderer escapes a quote mark and a newline inside a span, and `parse_replay_line` unescapes them.
- Add round-trip fixtures in `tests/test_replay_parser.py` for spans that hold:
  - straight and curly quotes;
  - `" vs "`;
  - `(heuristic 1)`;
  - a newline;
  - a trailing quote.
- `parse_replay_line` stays the one parser.
- Plain-run records stay byte-identical (the replay is text, not a record). If a golden replay fixture changes, say so and show the diff.

**From Task 12 (re-review M-new-1).** A test that pins the ratings read-back's replace-by-rep and kills the by-key mutant (`metrics/ratings.py` near line 512).

**From Task 13 (re-review round 4).**
- The item 10 note fires only at or above `MIN_REPS` (`analysis/hypotheses.py` near line 1126).
- A test of the note's wording.
- A key-parity test for `FLOOR_CLAUSE_TEXT` against the items the floor rule covers.

**Not this task's.** These belong to Task 15, the runbook rung; leave them:
- the contradiction judge's calibration form;
- the completion-precision measure;
- `analyze --ratings` on every environment-cell rung.

**HANDOFF.** Mark every Phase 3 minor this task does not close as "carried past Phase 4", as the brief says.

**Pytest.** Every run uses the pyproject `faulthandler_timeout` (120 s). A hang is a finding.
