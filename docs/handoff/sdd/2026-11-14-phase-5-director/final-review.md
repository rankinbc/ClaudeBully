# Phase 5 (the Director): final whole-branch review

Range 97102a0..32df6ea (52 commits), branch build/v1. Read-only on the checkout; `git status` is
empty after the probes. Stub providers only; no real call was made.

**Verdict: Ready with fixes.** Critical 0, Important 3, Minor 9.

How the review was done: the core (`claude_bully/`, 32 files) was read as code at HEAD, the run
side and the bundle in full, `director.py` for the call primitive, the resume path and stages 3
to 5, the rest by the functions the probes led to. Tests and docs were read selectively. Four
probe scripts ran about 150 CLI invocations on the Director's doubles (see "Probes"). The full
suite was not re-run (last gate 10766 passed, 11 skipped, 215 deselected, slow 215).

## Strengths

- **The end-to-end path holds.** `plan new --no-confirm` through the CLI, `plan validate`,
  `run` on the bundle, `analyze`: every interface agrees. `run.json` stays schema version 3 with
  `plan_hash` equal to the bundle's and a `plan` stamp of `slug`, `personas`, `expected`;
  `expected.json` and the `results.md` line are written from the run directory alone.
- **Resume parity survives a change of command.** Six kills at stage boundaries, each resumed by
  a command other than `plan continue` (`plan validate` or `plan review`), all end with hashed
  files and `bundle_hash` byte-equal to the unbroken plan's, no extra round, no false dead
  attempt.
- **The record-before-file commit order** (`director.py:1022-1031`) does what spec section 8
  says it does, and `_call` replaying a committed call through a pure `parse` keeps stateful
  checks off the resume path.
- **Harness records fail closed and clean.** Eight kinds of damage to `plan.json`, across five
  commands: every one prints `error: <file>: <line or field>` and exits 1, `run` included.
- **The run side is tight.** A resume on a restamped bundle is refused with the way out named
  (`--run-id`); a foreign `--worlds-dir` is refused naming both; an unchanged revalidate resumes.
- **Lint and CI agree on a Director-built bundle.** The four `plans/` scans pass a stub-built
  runnable bundle with its ledger, transcripts and `dryrun.jsonl`.
- **Retry prompts carry no path.** Five retry messages across five file kinds: none holds the
  home path, the login or an owner-pattern hit.
- `SCHEMA_VERSION` is 3; the golden fixtures have a zero-line diff across the range.

## Issues

### Critical

None.

### Important

**I1. A denylist hit in a stage 4 revision is a dead end: the owner's fix is written over on
every resume.**
- Where: `claude_bully/planner/director.py:1860-1867` (`_scanned_call`), `:1928-1956`
  (`_check_revision`), `claude_bully/planner/bundle.py:514-532` (`rematerialize_open_stage`).
- What: a `revise:<path>` reply is checked on arrival for its schema and, for a document, the
  document lints. The real-name, owner, Boundary and jailbreak scans are not part of that check,
  so a revision that holds a hit commits. The scan before the next stage 4 call then fails the
  stage. The owner removes the line and runs `plan continue`; stage 4 is the open stage, so the
  committed call's text is written back from its transcript and the stage fails again.
  `plan review` does not help: the round is in progress, so it resumes the same way.
- Scenario: rung D, a real planner revises a persona and writes one Boundary word. The plan has
  spent 50 to 100 calls and cannot be finished by any command; the owner sees an edit vanish
  with no message.
- Evidence: `probes-final/stage4_overwrite_at_head.out` (Task 8's probe re-run at HEAD): after
  the owner's fix and a continue, `planted line back in the file: True`, stage `revise` failed
  again.
- History: Task 8's N7, carried three times as a design choice.
- Fix: run the four denylist scans over a reply's content inside the arrival check, in
  `_check_revision` and `_check_file`. A hit is then a check failure: one retry naming the lint
  id (the owner clause naming no name), then an `error` call that commits nothing and leaves the
  file as it was (D-revise-error keeps the block open). This also closes Task 8's N10 (a
  planner-written hit reaching later stage 2 prompts). A kill test: a hit in a revision, then
  the owner's edit, then continue.

**I2. A resumed stage 3, 4 or 5 deletes an owner-added file the manifest names, a rate-limit
pause included.**
- Where: `claude_bully/planner/bundle.py:527-531`.
- What: `rematerialize_open_stage` removes every grammar file owned by neither `base_files` nor a
  committed call. A file the owner added, with its manifest entry in `plan.json`, is neither.
- Scenario: the owner adds a corpus document and its manifest entry, then runs `plan review`
  (docs/08's route after an edit). A rate limit pauses stage 3. The same command resumes, the
  file is removed without a line, and the plan ends `validated` on `manifest_complete: in the
  manifest but not on disk`. The unbroken twin keeps the file. The in-process wait
  (`--wait-on-rate-limit`) takes the same path, since it re-runs the action.
- Why it matters: it breaks two project rules at once (resume parity; a rate limit pauses and
  never degrades) and it deletes owner-authored text that may be untracked.
- Evidence: `probes-final/probe_cross_DE.out`, part E: the file exists after the pause, is gone
  after the resume, exists in the unbroken twin.
- History: Task 7b deferred it as a minor; Task 13's runbook routes rung D around it ("a new
  file would vanish").
- Fix: remove unowned files only when the open stage is `author` (the one stage where the
  harness itself can leave one, a base copy killed midway). In stages 3 to 5 leave them to
  `manifest_complete`, which names them. Print one `say` line per file removed. Amend spec
  section 8 and the runbook's rung D paragraph. A test: the probe's part E.

**I3. Three traceback paths remain on the owner's documented workflow, and the commonest names
no file.**
- Where: `claude_bully/planner/bundle.py:276-279` (`read_file`), `:316-320` (`read_transcript`),
  `claude_bully/planner/director.py:1177` and `:726` (`attempts[-1]`), `:937-953` (the marker
  written before the message is built).
- What:
  - An owner-edited bundle file that is not UTF-8 (cp1252 or UTF-16 from a Windows editor), then
    `plan review`: `UnicodeDecodeError` with a traceback and no file name, for all six file kinds
    tried. The pre-call scans pass the file; `reviewer_message` then reads it. `plan validate`
    on the same bundle prints `fail schema <file>: not valid UTF-8: byte ... at offset ...`.
  - A transcript missing from disk: `FileNotFoundError` on `plan review` of a runnable plan and
    on `plan continue` of a plan killed in stage 3.
  - A transcript with no attempts: `IndexError` on `plan continue`.
- Side effects of the first: the round was archived before the crash, so the plan is no longer
  `runnable`; and the marker of a call never sent is recorded in `resumed` as a dead attempt on
  the next run.
- Scope: spec section 13 promises the clean message for harness records only, and nothing wrong
  proceeds (fail closed holds). It is graded Important for the first path alone, which needs no
  damage, only an editor's default encoding. The other two need a hand edit or a deleted file.
- Evidence: `probes-final/probe_cross_C.out` (14 cases), `probe_errors_part1.out`,
  `probe_errors_part2.out`.
- Fix, one small wave:
  - `_scan_bundle` first checks that every grammar file decodes, and raises `DirectorError`
    naming the file and the byte offset (the stage fails with a named file; a continue after the
    owner's fix goes on).
  - `read_transcript` raises `DamagedRecordError` for a missing file.
  - `_call` and `_last_reply` raise `DamagedRecordError` for an empty `attempts`.
  - `committed_outputs` refuses a `content` that is not a string (Task 1's M3, Task 9's N-c).

### Minor

**M1. Absolute paths under the home folder are printed, and the owner pattern matches the home
folder's name.**
- `claude_bully/cli.py:54-55`: the `--runs-root` and `--results-root` help of seven commands
  prints the absolute default (Task 9's m4; the ledger's ruling already sends it to this wave).
- `claude_bully/planner/cli.py:433` and `:464`: `plan diff` labels every file with its absolute
  path, the shipped side from `WORLDS_DIR`.
- Probe: `the owner pattern matches the home folder's name: True` (`probe_cross_AB.out`). A
  pasted help text or diff carries the name.
- Fix: one shared help-default helper (as `PLANS_ROOT_SHOWN`); `plan diff` labels relative to the
  bundle root and to the worlds directory.

**M2. A failed stage's error text puts the absolute checkout path into `plan.json`.**
- `claude_bully/planner/director.py:1189-1196` (`_fail`).
- `plan new ... --base-world <a typo>` fails stage 2 with `world '<name>' not found: no
  <home>\...\data\worlds\<name>\world.yaml`, recorded in `StageRecord.error`. The default plans
  root is `plans/`, which the CI owner clause reads, so the local gate goes red on a failed
  plan. It fails closed, and the text reaches no model.
- Evidence: `probes-final/probe_paths.out`.
- Fix: `_fail` replaces the repository root and the home folder in the message before it is
  recorded and printed.

**M3. "A validated bundle never fails CI" holds for the files the lints read, not for the
harness's own.**
- A ledger line whose `error` holds a provider's text (`api.anthropic.com` in the probe) fails
  the CI real-name scan; so can a `StageRecord.error` kept after a successful retry
  (`director.py:1289-1301` keeps it by design).
- The runbook's move-in paragraph names `review.md`, `plan.md` and transcript replies, not
  `ledger.jsonl` or `plan.json`'s error text.
- Fix: one sentence in the runbook's rung D and in spec section 12. No code.

**M4. A `plan.json` of a newer plan schema is read as schema 1.**
`claude_bully/planner/records.py:242` refuses only an older version; version 2 ran every command
to `runnable` in the probe. It mirrors `runner/store.py:74`. Task 1's N2.

**M5. A `runnable` bundle can lack `plan.md` and `review.md`.**
`claude_bully/planner/bundle_lints.py:1004-1024`: `manifest_complete` exempts both and `schema`
requires neither. With either deleted, `plan validate` ends `runnable` (`probe_cross_DE.out`,
part D). docs/08 lists both as the bundle's contents. Fix: `schema` fails a bundle with no
`plan.md`.

**M6. `plan new` without `--no-confirm` on a plan killed inside stage 2 prints the stage 1 stop
and exits 0.** Task 9's N-a. The status line is true; the "plan.md is yours to edit" line is
loose once stage 2 has made its manifest call.

**M7. `analysis/expected.py:40` imports `planner/records.py`.** The analysis now depends on the
planner package for two models. No cycle. Task 10's layering nit covers the test's regex.

**M8. The runbook says a new file vanishes "after a kill, or after a rate limit past the
wait".** A rate limit within the wait takes the same path (I2's probe). Rewritten with I2's fix.

**M9. A hand-damaged `run.json` stamp shows a traceback at `analyze`.** A persona recorded under
another name raises `ValueError` from `register_plan_personas` (`runner/plan_stamp.py:73-74`).
An invalid `expected` is handled cleanly. Hand edit only.

## Passes

1. **Spec coverage (section 1's success lines, section 18).**
   - Line 1 (a stub plan loads, lints clean, dry-runs to the top rung, rebuilds from the record
     and transcripts): built; probed end to end; `test_materialize_rebuilds_...` in
     `tests/test_plan_cli.py:135` and `tests/test_director_primitive.py:378`.
   - Line 2 (kill parity, the dead call named, no cache entry): built;
     `tests/test_plan_parity.py:47` over K1 to K13; I2 is the one case found where a resume
     differs, and it needs an owner-added file.
   - Line 3 (`run` on a bundle, the stamp, the refusals, analysis from the run directory):
     built; probed; `tests/test_bundle_run.py`.
   - Line 4 (every rule a lint or a block that fails closed): built. I1 is a fail-closed rule
     with no way back, not a hole.
   - Line 5 (no real call): the dry run's factory refuses any non-stub role
     (`dryrun.py:469-478`); every test and probe ran on doubles.
   - Section 18: the runbook's rung D holds the command, estimate, bars, stop rules and both
     measurements; nothing runs it.
2. **Cross-task data flow.** Stages 1 to 5, `plan.json`, the bundle, `run`, `analyze`: the
   interfaces agree (`probe_e2e.out`). `PlanStamp.expected` is carried unvalidated and validated
   at analysis, where an invalid one writes a named line and no file.
3. **Error contract and fail-closed.** Harness records: clean. Owner-edited files and missing
   transcripts: I3. No swallowed error was found: `run()` catches `DirectorError` alone and
   records it; `_plan_errors` catches two types.
4. **Resume and kill parity across stages.** Six cross-command cases equal (`probe_cross_F.out`).
   I1 and I2 are the two places where the open-stage rule meets an owner's edit.
5. **Real-name and denylist invariants.** The lint and CI rules agree on a Director-built
   bundle; the owner clause's results name no name; no retry prompt carries a path. M1, M2 and M3
   are where the home path or a provider's text gets out or gets in.
6. **Docs truth.** HANDOFF's counts match the last gate. docs/08's five commands and the
   `transcripts/round-<n>/` and `review-<n>.md` archive match the code. docs/00's section H row
   for Phase 5 matches `records.py`. Spec section 8's resume rule matches `bundle.py:514-532`
   (and is what I2 asks to change). The runbook's rung D matches the live commands; M8 is its
   one inexact clause.

## Triage of the deferred items

Fix before close:

| Item | Disposition |
| --- | --- |
| Task 8 N7, stage 4's confirm-scan overwrite dead end | I1 |
| Task 8 N10, a planner-written hit reaching later stage 2 prompts | closed by I1's fix |
| Task 7b, an owner-added file removed by a resume | I2 |
| Task 9, the hand-edit-only traceback paths (missing transcript, empty attempts) | I3 |
| Task 1 M3 and Task 9 N-c, a non-string `content` raises `AttributeError` | I3's wave, one check |
| Task 9 m4, the seven commands' `--runs-root` and `--results-root` help | M1, as ruled |
| Task 11, the note's fourth reason `stale` | fix: "never asked" tells the reader a rerun changes nothing when a rerun is the fix |
| Task 11's three notes (the untested parenthetical, a stale `expected.json` beside the "not read" line, "asks it") | fix the stale file (delete `expected.json` when the stamp is unreadable); the two wordings ride along |
| Task 13's three nits (the 54 index lines, entry kinds, a 109-column line) | fix with I2's runbook rewrite |
| Task 1 M6, the literal BOM in `normalize_text` (`bundle.py:106`) | fix: write the escape, one line |

Leave parked:

| Item | Why |
| --- | --- |
| Phase 4 N2, the "not judged" note | closed in Task 11 |
| Task 1 M4, `Bundle.create` takes an unvalidated slug | every caller passes a validated slug |
| Task 1 M5, the longest grammar path passes MAX_PATH | this machine has long paths on; note in HANDOFF |
| Task 1 nits N1, N3, N4, N5 | N5 is closed (`_committed_texts` compares the sha); the rest latent |
| Task 1 N2, a newer plan schema read as 1 | M4 above; mirrors the run store |
| Task 2, `load_stub_script` refuses empty-falsy files | checked: 15 shipped scripts, none empty |
| Task 2 nits | no effect |
| Task 4a N-7, N-8, N-9 | an unused environment failing `schema` is the strict side |
| Task 4b, a bad byte in `plan.json` raises from `read_record` | closed in Task 9 (`DamagedRecordError`; probed) |
| Task 5 M-2, M-3 and nits | a stated residual and test strength; no behavior |
| Task 6 N-A, N-C, N-D | N-C eases under I1's fix (the retry names the lint id); the others latent |
| Task 6 M4, the confirm prompt defines one outcome of three | the lean keeps blocks open; rung D's seeded check measures it |
| Task 7b, the `cache_key` spec wording | one clause, any docs-sync |
| Task 7b, `Ledger.lines()` and `fold()` use `splitlines` | pre-existing; the plan ledger's own readers split on LF |
| Task 8 N9, `besides` relies on the re-materialization running first | true by `run()`'s order; a comment |
| Task 9 round-2 notes N-a, N-b, N-d, N-e | M6 above; the rest test strength |
| Task 10's three nits | a composition left registered is harmless; "failed: None" needs a hand edit |
| Task 12 M-1 and nits | the fast lint test still fails on the missed case; no gate hole |
| Task 12 N-4, M2 | closed in Task 13 |

## Rulings

No ruling reads as wrong on its merits. Four notes:

- **Line 154 and line 137 (two carries graded minor).** Both are graded up here by effect (I1,
  I2): each ends a plan or deletes owner text on a path a real rung will take.
- **Line 74's cost line** names the CI scan of `plans/` as the backstop for a phrase split by a
  blank line. It is not one: the denylist patterns use literal spaces, so the raw read misses
  the split too, and rulings 209 and 213 made CI read as the lint reads. Spec section 9 already
  says so ("no later scan of the same patterns closes it"); only the ledger line is stale. The
  reviewer stage is the one backstop.
- **Lines 68 and 74** ("invalid UTF-8 is a schema fail, never an exception") hold for
  `lint_bundle` only. Stages 3 and 4 read the same files through `Bundle.read_file` (I3).
- **Lines 209 and 213** ("a validated bundle never fails CI") hold for the files the lints
  read. The harness's own records are outside it (M2, M3).

## Declined to judge

- A config moved out of its bundle, or a bundle whose `plan.json` is deleted, runs as a plain
  config on `data/worlds` with no hash check and no stamp. Spec section 11 keys detection on
  `plan.json` beside the config; by design.
- `plan validate` restamps a hand-edited bundle with no reviewer call. Spec section 13 says so;
  the owner is trusted.
- `promote` does not scan `run.json`'s `plan` stamp. The personas there come from a bundle
  `run` refused unless validated, and their text reaches the bully turns `promote` scans.
- A committed stage's transcript deleted by hand goes unnoticed until `materialize` or
  `plan review` reads it. The rebuild promise is then silently false for that bundle.
- Whether the real planner and reviewer behave as the doubles do. Rung D measures it; nothing
  here ran a model.
- The suite's 82-minute run time. HANDOFF states it.

## Probes

All in `probes-final/`. Every probe ran on the Director's doubles and the dry run's doubles;
the work directory was deleted; the outputs hold `<home>` and `<login>` in place of the path.

| File | What it ran | Result |
| --- | --- | --- |
| `probe_e2e.py`, `.out` | `plan new` through the CLI, `plan validate`, `continue`, `new` again, `diff`, `run --dry-run`, a foreign `--worlds-dir`, a stub run, `analyze` | all as specified; schema 3; the stamp and `expected.json` written |
| `probe_errors.py`, `probe_errors_part1.out` | 22 kinds of damage to a runnable bundle, each on up to five commands | harness records clean; I3's tracebacks; M4 |
| `probe_errors_part2.py`, `.out` | 10 kinds of damage to a plan killed in stage 3 | I3's `FileNotFoundError` and `IndexError`; a torn ledger tail and a bad marker clean |
| `probe_cross.py`, `probe_cross_AB.out`, `_B.out` | the four CI scans over a Director-built bundle; real-shaped ledger lines; retry prompts under five failing file kinds | scans pass; M3; no path in any retry |
| `probe_cross_C.out` | a non-UTF-8 edit of six file kinds, on `plan review` and `plan validate` | I3 |
| `probe_cross_DE.out` | a deleted `plan.md`, `review.md`, `expected.yaml`; an owner-added file through a rate-limit pause | M5; I2 |
| `probe_cross_F.out` | six stage-boundary kills resumed by another command | all byte-equal to the unbroken plan |
| `probe_cross_G.out` | a run, a revalidate, an edit, a restamp, a resume; a damaged stamp at `analyze` | refusals as specified; M9 |
| `probe_paths.py`, `.out` | a failed stage's error text in `plan.json` | M2 |
| `stage4_overwrite_at_head.out` | Task 8's stage 4 probe at HEAD | I1 |

## Assessment

**Ready to merge: with fixes.**

The phase meets its spec: the five stages, the bundle, `run` on a bundle and the analysis agree
end to end, and parity holds at and across stage boundaries. The three Important findings are
all the same seam, the open-stage resume rule meeting an owner's edit, and each has a small,
local fix with a test the probes already describe. One fix wave (I1 to I3, M1, M2, the
fix-before-close rows), then close.
