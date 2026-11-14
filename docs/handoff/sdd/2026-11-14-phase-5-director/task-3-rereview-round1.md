# Task 3 re-review, fix round 1

Scope: base e1487dd, head 3165ad5 (one commit, 5 files: `bundle_lints.py`, `line_shapes.py`, `tests/test_world_lines.py`, HANDOFF.md, the spec's D3 line). Read: `task-3-review.md`, the report's "Fix round 1" section (treated as claims), the whole diff once, and the files at HEAD where a verdict needed them. Probe: `probes-task3/probe_rereview1.py` and `.out`. It mutates a temp copy of mini and imports the test module's own `FIXTURE_FAILURES`, `_pinned` and `_sorted`, so it exercises the pin as shipped. The checkout was not written: `git status` is clean after every run (pytest with `-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`, `uv run --no-sync`).

## Verdicts

- **I1: FIXED.** All four planted defects are caught.
- **M1: FIXED.**
- **M2: FIXED.** No caller breaks.
- No new Critical, Important or Minor finding. One Nit, outside the fix round (below).

Counts for the round: Critical 0, Important 0, Minor 0, Nit 1.

## I1: the D3 pin

The new `FIXTURE_FAILURES` is `dict[str, list[Row]]`, with `Row = (lint_id, doc_id, message, span)`. `_pinned` builds every fail row of `lint_world_lines` over a world, with a None span sorted as "". `test_the_fixture_worlds_fail_exactly_their_pinned_lints` compares it against `_sorted(FIXTURE_FAILURES[name])`. It compares sorted lists, not sets, so an identical second row also changes the result.

Baseline at HEAD: mini gives 7 rows, equal to the pin and to the 7 rows printed in the review's `probe_risks.out`. Annex gives none. The old pair set is unchanged (the same 7 pairs), so the new pin is strictly finer.

The review's four planted mini defects, with the review's own text (`probe_rereview1.out`):

| Planted defect | Old pin | New pin |
| --- | --- | --- |
| `canteen-menu.md` gains "Filed 12/06/2044." | absorbed | **CAUGHT**: new row `clock_rule / canteen-menu / its body holds a date the re-dater cannot move / 12/06/2044` |
| `the_log_line` gains the opener "Look." | absorbed | **CAUGHT**: new row `bully_line / mini/the_log_line / ... matches the announce shape / Look` |
| `courier-fare-notice.md` gains "Fares held 2043-2044." | absorbed | **CAUGHT**: new row `clock_rule / courier-fare-notice / its body holds a date ... / 2043-2044` |
| `night-gate-log.md` gains "Logged 03/11/2044." (new pair) | caught | **CAUGHT**: new row on `night-gate-log` |

Four of four. Each is 8 rows against the pin's 7, with the one new row named.

Extra cases beyond the review, all caught:

- `first_crumb` gains a second failing fires line, so a new span.
- The same failing fires line is duplicated, which gives an identical row twice. This is the case that needs a list rather than a set. It is caught by the count.
- `the_log_line` gains a dare shape as well as its doc_pointer shape, so the same pair with a new message.
- `canteen-menu` gets a front-matter date, so a pinned failure is fixed (6 rows against 7). The pin also breaks when a failure goes away, so a fixture world cannot drift quietly either way.

The new test `test_a_new_failure_on_an_already_pinned_document_breaks_the_pin` plants three second failures on mini (the canteen date, the log-line opener, the courier year range, written with 2041 forms). Each first asserts the plant adds a fail result (`len(after) > before`), then asserts `_pinned` no longer equals the pin. That is the right two-step: the plant cannot pass for the wrong reason. All three pass. The report's RED claim (3 failures under the old pair pin) is consistent with the review's probe, which found the same three plants absorbed by the pair set; I did not re-run e1487dd.

Two limits remain, both inherent and both named in the report or the review:
- The `ladder_walk` failure on rung `fragment` stops the walk, so a later rung's walk defect cannot surface in mini. `trigger_examples` still reports every rung.
- Each lint emits at most one row per (document or line, class). A second hit of the same shape inside one line is invisible to the lint itself, so no pin could see it.

## M1: the walk lengths

`test_the_walk_repeats_lines_to_meet_min_count_by` is parametrized over `WALKS`: overlay `authority` 6, `default` 6, `poisoned_well` 12, `poisoned_well_checksum` 2, `poisoned_well_fabricated` 10, `poisoned_well_real` 2, and annex `default` 2 (root `WORLDS_DIR`). That is the seven lengths in D4 and in the review's re-measurement (`probe_risks.out`, risk 5: 6, 6, 12, 2, 10, 2, 2). The ids are unique (`overlay-authority` ... `annex-default`), and all seven collect and pass.

## M2: read-only mappings

`BULLY_LINE_SHAPES` (`line_shapes.py:83`) and `LAYER_RANGES` (`bundle_lints.py:61`) are `MappingProxyType(...)`, keeping the `Final[Mapping[...]]` annotation, and `MappingProxyType` is imported in both files. The inner values are `re.Pattern` and tuples of floats, so nothing underneath is mutable. `test_the_shared_mappings_are_read_only` checks that an assignment into each raises `TypeError`; I also ran it directly (`mappingproxy` object does not support item assignment).

Callers, grepped over the whole repo (the code and tests; `.superpowers/` drafts hold only prose mentions):
- `claude_bully/planner/bundle_lints.py:134`: `dict(BULLY_LINE_SHAPES)`, then `shapes["premise_words"] = premise`. A copy is made first, so the write lands on the dict. Probed: the copy takes the extra key (6) and the original stays at 5.
- `bundle_lints.py:264`: `for layer, (low, high) in LAYER_RANGES.items()`. A read-only iteration; probed, it yields the four layers with their tuples.
- `tests/test_world_lines.py:648`: `set(line_shapes.BULLY_LINE_SHAPES)`. Iterating a proxy yields its keys; passes.
- `tests/test_world_lines.py:800-805`: the new read-only test.
- `line_shapes.py` is imported by `bundle_lints.py`, `tests/test_env_sheets.py`, `tests/test_overlay_world.py`, `tests/test_poisoned_well_world.py`, `tests/test_world.py`. None of them names `BULLY_LINE_SHAPES` or `LAYER_RANGES`; they take the compiled patterns.
- No caller serializes either constant (no `json.dumps`, no `yaml`), and the plan's Task 4a mentions (`BULLY_LINE_SHAPES` for the persona fallback lines) are prose; `dict(...)` and `.items()` work on a proxy.

Nothing else in the repo reads or writes either name. No caller breaks.

## Gate re-run

- `pytest -q -p no:cacheprovider -W error` over the five covering modules (`test_world_lines`, `test_overlay_world`, `test_env_sheets`, `test_world`, `test_poisoned_well_world`): 378 passed, matching the report's 378 (368 plus 6 more walk cases, 3 plants and 1 read-only test). I did not re-run the full 10037-test suite or the slow marker.
- `mypy claude_bully` and `mypy --platform linux claude_bully`: no issues in 125 files. `ruff format --check .`: 324 files already formatted. `ruff check .`: all checks passed.
- Case ids (N1): `bully_line-1-negative`, `bully_line-2-positive`, ..., `outlet_backing-9-near`; 86 cases, as before.
- No golden, world or fixture file changed in the diff (the 5 files above only).

## Nit (not a fix-round defect)

- **N4.** `mypy tests/test_world_lines.py` reports `tests/test_world_lines.py:647: Module "tests.test_overlay_world" does not explicitly export attribute "ADVICE_SHAPES"`. The line is e1487dd's, outside the fix diff. It is not in the gate, which runs `mypy claude_bully` only, so nothing fails. If tests are ever type-checked, import `ADVICE_SHAPES` from `claude_bully.planner.line_shapes` in the test instead of reading it off the old module.
