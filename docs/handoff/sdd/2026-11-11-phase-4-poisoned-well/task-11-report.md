# Task 11 report

Status: COMPLETE. Committed as 4684a63 "feat: Phase 4 Task 11, the Poisoned Well replay lines and
the seven configs" on build/v1 (one commit on dbf17c0, author rankinbc1@gmail.com, not pushed).

Gate (all after the last edit to code and tests; only HANDOFF.md was edited after the full pytest run):
- ruff format --check: 309 files already formatted; ruff check: all checks passed.
- mypy claude_bully and mypy --platform linux claude_bully: no issues in 118 files.
- `uv run pytest -q -W error`: 9673 passed, 9 skipped, 21 deselected, 0 xfailed, 0 warnings, in 649 s
  (from 9645 passed, 1 xfailed; +28).
- `uv run pytest -q -m slow`: 21 passed (from 16).
- HANDOFF.md bullet 11 carries the counts. The header paragraphs (last updated, next steps, resume
  line) are left for the controller's close-out, as at Task 10.

## Implemented
- `claude_bully/analysis/replay.py`: `_KIND_ORDER` gains `QuirkAttempt, ChainLink, ContradictionPair`
  after `Discovery`; `_record_block` renders the `QUIRK`, `CHAIN` and `CONTRADICTION` lines;
  `GENERATED` gains ` origin=twin`; `_speaker_line` adds `[<move>]` from `bully_meta["pw_move"]`
  after the other flags; `_other` takes `ResumeRecord` only; `_SHAPES` gains `quirk`, `chain`,
  `contradiction` and `generated`'s optional `origin`; new `_flat` helper (whitespace collapsed
  in contradiction spans; excerpts still use `_excerpt`, 120 chars).
- `configs/poisoned_well/`: the seven YAMLs verbatim from the brief.
- Tests: `tests/test_poisoned_well_configs.py` (new; dry run and counts for all seven; stub runs, two
  default, five `slow`), `tests/test_configs.py` (`POISONED_WELL_EXPECTED`, rglob union),
  `tests/test_replay_parser.py` (10 fixtures), `tests/test_replay.py` (6 renderer tests),
  `tests/test_poisoned_well_run.py` (xfail mark dropped; one new run-level parse test).
- Docs: spec "As planned" Task 11 section; docs/00 sections E, H and I; docs/02 (replay as-built);
  docs/07 (as-built note); runbook "Rungs other phases add" (chain_stop restated, six configs with
  estimates). HANDOFF.md NOT yet touched.

## RED and GREEN
- RED (configs dir moved aside, parser fixtures in place): 19 failed, 63 passed, 1 xfailed
  (7 dry-run, `seven_configs_are_there`, 2 small stub runs, 8 parser fixtures, rglob test).
- GREEN after implementation: `tests/test_poisoned_well_configs.py tests/test_replay_parser.py
  tests/test_poisoned_well_run.py tests/test_configs.py tests/test_replay.py -m "slow or not slow"`:
  109 passed, `test_replay_shows_the_moves` passes without its mark; later replay-test additions:
  116 passed over five modules. ruff format --check, ruff check, mypy and mypy --platform linux
  all clean.

## Replay shapes (examples)
- `    QUIRK q-letter-count reproduced "2"`
- `    CHAIN link 2 rejected "That doesn't follow." (heuristic 1) pressed`
- `    CONTRADICTION c-7-1 t3/t7 "I am a model." vs "I am not a model." (heuristic 1) retracted`
- `    GENERATED gen-7-1 instance_transcript buried uses=- origin=twin`
- `#4 bully (reveal) [chain_link] Here is a plain one first.`
No new target-visible or bully-spoken line (configs set no persona text and no twin question).

## Cell counts and call estimates (first target, `--only "*__t0*"`, from stub-run turn counts)
chain_stop 4 cells (about 330 calls with ratings; 245 conversation), real_vs_fabricated 8 (about
1,000), epistemologist_alone 6 (about 290), levers 14 (about 2,350), checksum_alone 8 (about
1,000), poisoned_vs_captor 8 (about 730), rescue_third_party 6 (about 400).

## ASSUMED
- ASSUMED: new spans are made safe by whitespace collapse plus quote-tolerant regexes; the existing
  HARVEST and TRIGGER lines still embed spans raw (Phase 3 Task 4 M8 left open for them).
- ASSUMED: the move flag follows `[scripted]` and the other flags.
- ASSUMED: estimates use the rule stated in the runbook (conversation calls measured by stub runs,
  plus pair judge, chain fallback ceiling, contradiction pass ceiling, trigger fallbacks about 7 per
  conversation, harvest and generator calls, ratings).
- ASSUMED: the five ladder stub-run tests are marked `slow` as the brief says (only `levers`
  measured over 2 s; the others 0.6 to 1.3 s).
- Expected gate counts if all passes: 9673 passed, 9 skipped, 21 deselected, 0 xfailed; slow 21.

## Concerns
- The full pytest run took 10 min 49 s, inside the stated range.
- The five ladder stub-run tests are marked `slow` as the brief says; only `levers` measured over 2 s
  (2.4 s), the others 0.6 to 1.3 s.
- Existing HARVEST and TRIGGER lines still embed spans raw (Phase 3 Task 4 M8); the new shapes do not.
