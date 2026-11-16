# Task 13 report: rung D in the runbook and the phase docs-sync

Base c8c0c5c on build/v1. Documents only: no code, record, config or test changed, and no model ran. One commit, 64b4cf0 `docs: Phase 5 Task 13, rung D in the 7b runbook and the phase docs-sync`, authored rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Not pushed.

## Files changed

- `docs/handoff/phase-7-runbook.md`
  - New `### Rung D: the Director's first real plan (Phase 5)` after the rung 3 section and before `## Rungs other phases add` (quoted below). It holds spec section 18 as built, the two Task 12 carries (M2, N-4) and two one-line readers.
  - The "after Phase 5" bullet (its v1 figures, a fixed author-call ceiling and "40 to 100 calls", are gone) now points at the section.
  - The intro says the rung's commands were read against the live `--help` (`plan new`, `plan review`, `plan validate`) and that the two readers were run on the example bundle and on a stand-in ledger.
  - "What is committed" gains a sentence: rung D's plan is made outside the repo and committed under `plans/` only on the owner's yes, once its scans pass.
- `HANDOFF.md`
  - Header rewritten (all thirteen tasks done, Tasks 1 to 12 complete and pushed, Task 13 committed, the final review next, rung D waiting on the owner).
  - "Plans" list gains the Phase 4 and Phase 5 plans.
  - The Phase 5 Progress bullet is no longer "in progress": it states the range convention, the gate movement (9825/9/48/48 to 10766/11/215/215) and the spec pointer.
  - Each of the fourteen Phase 5 entries has its range, review result and fix-round commits (from the ledger's `Task N: complete` lines) in place of "one commit on <base>"; entry 15 is Task 13.
  - "Next steps" item 1 (the stopping-point step) is rewritten to: the controller checks and pushes Task 13, then the Phase 5 final whole-branch review (base 97102a0), one fix wave, re-review, close. Item 2 now says Phase 6 next and that rung D is written and waiting. Item 4 (real runs) names rung D.
  - "Open items worth knowing" gains a "From Phase 5" group holding every "minor (deferred, final review)" and "carry to the final fix wave" ledger line, plus the plan's two stated residuals; it says Task 13 closed Task 12's M2 and N-4.
  - The resume paste block now describes Phase 5.
  - The gate counts under "Setting up a new machine" are updated (see "Gate").
- `docs/00-RECONCILED.md`
  - Sections A, B and F were already complete from the per-task docs-syncs (A: `PlanRequest`, `PlanBudget`; B: the plan records, `RunRecord.plan`, the expected-vs-observed report; F: the three prompt files and `plans/`), so they are unchanged.
  - Section E's command list now names `plan new`, `plan continue`, `plan review`, `plan validate`, `plan diff` and `run --worlds-dir`.
  - G11 and G16 each get a "Built in Phase 5" sentence.
  - Section H gains a Task 13 line.
  - Phase map row 5 is rewritten as complete.
- `docs/08-DIRECTOR.md`
  - Outputs table is the as-built layout (`worlds/<name>/...`, `personas/<stem>.yaml`, `premises/`, plus `plan.json`, `transcripts/`, `ledger.jsonl`), with the path grammar, the git-ignored files and the world copy.
  - New section "The review as rendered" (the format of `render_review`, with an example).
  - The layer-check row is marked built (`layer_counts`).
  - "Every row below is built" replaces "the rest are Phase 5's".
  - The dry run's fixed bully line gets its A9 sentence (a Poisoned Well ladder is held to the top rung; `not_applicable` only for a cell with no ladder to climb).
  - Process step 4, the intro `plan new`, the Records paragraph and the deliverables list (five subcommands; the example is hand-authored, rung D asks for the Director's own) are corrected.
  - The two prompt blocks and the confirm block are untouched (`tests/test_director_prompts.py` pins them).
- `docs/superpowers/specs/2026-11-14-phase-5-director-design.md`
  - The status line says "built".
  - Section 18 gains a pointer to the runbook.
  - "As planned": the placeholder is replaced by an intro; the 27 **Departs from the spec** lines of the plan's Plan Decisions, in plan order, one line each (19 `D-` lines, then the eight plan-review rulings `R-`, whose spec text is already marked "[refined in the plan review]"); then the whole-phase summary paragraph (which says so); then "By task" followed by the existing task entries, unchanged. A Task 13 entry is appended at the end.

## Rung D, as written (quoted)

    ### Rung D: the Director's first real plan (Phase 5)

    Not run until the owner says so (2026-11-11: infrastructure only for now). It is the first time a
    real model plays the planner and the reviewer; every Director test so far ran on stubs. The same
    checks as every rung ("Before every rung"), then `doctor --live` first (Step 0): the planner runs
    on `opus` and the reviewer on `sonnet`, both `claude_code` (the request's defaults, merged
    question 4), and every call after stage 1 asks for a JSON reply through `--json-schema`, the
    route check 3 (`structured`) exercises. The commands below were read against the live `--help` of
    `plan new`, `plan review` and `plan validate` (Phase 5 Task 13).

        uv run claude-bully plan new "Does triggered gating beat scheduled on the Rescue premise?" --no-confirm --base-world overlay --hypotheses 9 --slug director-triggered-vs-scheduled --wait-on-rate-limit 360 --plans-root <a directory outside the repo>

    It asks the hand-authored example's question (`plans/example-triggered-vs-scheduled/`) into a slug
    of its own beside it. `--no-confirm` goes on past `plan.md` through stage 5, `--base-world overlay`
    copies the shipped overlay for the planner to patch, and `--hypotheses 9` names the register item.
    A plan in flight is made with `--plans-root` outside the repository and moved into `plans/` only
    once it is `runnable` and clean: the CI scans read every bundle under `plans/`, so an in-flight
    plan there turns the local gate red. A rate limit the wait does not cover exits 3, and the same
    command resumes the plan (on an existing slug with the same request `plan new` continues it;
    `plan continue <bundle> --wait-on-rate-limit 360` does the same).

    Estimate: one plan call, one manifest call, about 30 file calls for a patch of the overlay, up to
    10 repairs, 4 review calls, about 10 revise calls and about 5 confirm calls: 50 to 110 planner and
    reviewer calls, under the request's `max_director_calls = 120`, ledgered as `planner` and
    `reviewer` in the bundle's own `ledger.jsonl`. The ceiling counts committed calls, so a call whose
    first reply failed its check and was retried is one call against it and two ledger lines. The dry
    run and the lints cost nothing (a stub run, no model call).

    Read first `plan.json`'s `stages[*].calls[*].attempts` and `status`, and each stage's `status` and
    `error` (a call is `fresh`, `cached` or `error`; `attempts` 2 means the first reply failed its
    check and the retry was sent). This prints them, then the plan's status and how many file calls
    (`file:<path>`) needed their retry:

        uv run python -c "import sys; from pathlib import Path; from claude_bully.planner.records import read_plan_record; r = read_plan_record(Path(sys.argv[1], 'plan.json')); [print(s.stage, s.status, s.error) for s in r.stages]; calls = [(s.stage, c) for s in r.stages for c in s.calls]; [print(st, c.role, c.index, c.purpose, c.status, 'attempts', c.attempts) for st, c in calls]; f = [c for st, c in calls if c.purpose.startswith('file:')]; print(r.status, 'file calls', len(f), 'with a retry', sum(c.attempts == 2 for c in f))" <bundle>

    Then `review.md` (its first line is `block N / fix N / note N`; every block ends in a `confirm:` line,
    `(closed)` or `(open)`), then the ledger's counts against the estimate (by role and status; a
    `timeout` line is a stop rule below):

        uv run python -c "import json, sys; from collections import Counter; from pathlib import Path; rows = [json.loads(x) for x in Path(sys.argv[1], 'ledger.jsonl').read_text(encoding='utf-8').split('\n') if x]; [print(role, status, n) for (role, status), n in sorted(Counter((r['role'], r['status']) for r in rows).items())]; print('calls', len(rows))" <bundle>

    and `plan.json`'s `resumed` (a dead attempt: none expected on a clean run), `edited` (hand edits
    adopted: none expected) and `lint_results` (a `warn` stays in the record for the owner's eye; no
    `fail` result stands on a `runnable` plan).

    The plan's null result is read with one caution. The example's null result (`plan.md`, "A null
    result", beside its per-cell `expected.yaml`) pools the arms over the two targets (six reps per
    arm) and reads two rungs, `buried_opens` and `the_truth`. That is the plan's own reading.
    `analyze --hypotheses` item 9 (`item_9`) compares per model, each arm's mean adoption rate over
    the rungs both arms reached, so the two give different numbers for one run. Read a bundle's null
    result as its own `plan.md` states it, and the register's item 9 as `analyze` computes it, and
    never one as a check on the other; when the report sets the generated bundle's null result beside
    the example's, it says which of the two readings each uses.

    Bars (spec section 18):

    - the plan ends `runnable`;
    - no fail lint needed a hand edit: `edited` is empty and no stage ended `failed` or waited on the
      owner;
    - the owner reads every unlock line and every document the planner added and finds no billboard
      the reviewer missed. The controller writes them to `output/phase7_rungD_<date>/spotcheck_director.md`
      (each `unlock_lines` entry of the world sheet, and every bundle file whose path is not a key of
      `plan.json`'s `base_files` or whose sha differs from it), and the owner reads that;
    - the reviewer's blocks on a seeded bad bundle catch at least 8 of 10 (spec sections 15 and 18). The
      controller plants ten defects of the two classes the reviewer's prompt blocks (a billboard, a
      guardrail breach) in a scratch copy of the example bundle, outside the repository, each one a
      defect no denylist scan reads (a document whose main point is the premise, an unlock line that
      announces its evidence by paraphrase, hostility over the ceiling), since stage 3 runs the real-name,
      Boundary and jailbreak scans before every reviewer call and a defect they stop never reaches the
      reviewer. It runs `plan review <copy> --wait-on-rate-limit 360` once, and counts the planted
      defects that stage 3's `review.md` quotes under a `block`. ASSUMED: the spec fixes no mechanism and
      the CLI has no reviewer-only command, so the check is a plan of its own (its own ceiling of 120
      calls): 4 review calls, then the revise and confirm calls its blocks cause. A copy the check
      edits is never committed.

    Stop rules (a fix is a task of its own, to the prompt, the lint or the code at fault, with a
    brief, a commit, a review and the docs-sync, as for any rung; the plan is then made again under a
    new slug):

    - a `values_loosened`-shaped line, or a real name, in any authored file that the lints passed;
    - more than a quarter of the file calls needing their retry (`file calls ... with a retry` above);
    - a planner call over the provider's timeout (a `timeout` line in the ledger, or an `error` call
      whose `error` names it);
    - any bar missed.

    A generated bundle whose `review.md`, `plan.md` or a transcript's replies quote a real name (a
    review in flight may, to block it) is not committed as it stands: the repository scan reads every
    text file of a checked-in bundle (R-scan-bundles). To commit one on the owner's yes, move it into
    `plans/`, run `uv run claude-bully plan validate plans/director-triggered-vs-scheduled` (no model
    call) and `uv run pytest -q tests/test_real_names.py tests/test_guardrails.py tests/test_boundary.py
    tests/test_example_bundle.py` (the dry run of each bundle is in the slow suite, `-m slow`), and
    take it out again if one goes red. A `plan.json` diff of timestamps alone after a validate is
    not committed.

    The same rung measures what the spec assumed (spec section 18), from the same bundle:

    - The input size of a planner call with `docs/01` to `docs/07` in it: the character length of the
      first attempt's `message` in each `transcripts/<stage>-planner-<index>.json`, and `input_tokens`
      on the `planner` ledger lines where the CLI reports it; record the largest and the median of
      each. Measured on stubs at build: the default request about 195,000 characters and a stage-2
      call about 235,000, against a limit of `MAX_CONTEXT_CHARS = 300,000`, over which a call is
      refused before it is sent.
    - Whether the attached context of the installed CLI shows up in authored files (rung 0 finding 1:
      the real date, the model's name and exact id and the account's email address, beside the system
      prompt): search every authored file (`plan.md`, `config.yaml`, `expected.yaml`, `personas/` and the
      planner's files under `worlds/`) for the run day's date in any written form, each
      `resolved_model` the ledger names and the account's address (never written into a report). A hit
      is a finding whatever lint passed.

    Its report (`output/phase7_rungD_<date>/rung_report.md`, the form under "What `rung_report.md`
    holds"; its Calls rows are the `planner` and `reviewer` lines of the bundle's `ledger.jsonl`, since
    no run exists) decides whether the specs are distilled for the planner (spec section 17: on the
    measured input size) and whether the example bundle is replaced by the generated one, a task of its
    own, since `scripts/build_example_bundle.py` and `tests/test_example_bundle.py` are written for the
    hand-authored one.

## Gate

Run on the working tree with the five documents edited (nothing else), before the commit:

- `uv run ruff format --check .`: 404 files already formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy claude_bully`: success, no issues in 130 source files.
- `uv run mypy --platform linux claude_bully`: success, no issues in 130 source files.
- `uv run pytest -q -W error -p no:cacheprovider`: **10766 passed, 11 skipped, 215 deselected** in 4927.65 s (1:22:07). Equals Task 12's counts.
- `uv run pytest -q -m slow -p no:cacheprovider`: **215 passed**, 10777 deselected, in 2292.14 s (0:38:12). Equals Task 12's.
- The brief's verify command (`'### Rung D' in t and 'MAX_AUTHOR_CALLS' not in t`) exits 0.
- `tests/test_director_prompts.py` and `tests/test_director_context.py` (the tests that read docs/08 and docs/01 to docs/07) were also run on their own before the full run: 84 passed.

Order note: `docs/08-DIRECTOR.md`, `docs/00-RECONCILED.md` and the spec were final before the fast run began; two small wording edits to the runbook (it is read by no test) and the HANDOFF gate-count line (also read by no test) came after it started.

## Verify command

`uv run python -c "import pathlib,re,sys; t=pathlib.Path('docs/handoff/phase-7-runbook.md').read_text(encoding='utf-8'); sys.exit(0 if '### Rung D' in t and 'MAX_AUTHOR_CALLS' not in t else 1)"` exits 0.

## ASSUMED

- ASSUMED: the runbook command is the brief's, verbatim, with `--plans-root <a directory outside the repo>` appended. Without it the plan would be made under `plans/` and turn the gate red (Task 12 review M2, binding). The brief's command has no `--plans-root`, so both bindings are met by appending it and explaining why in the text.
- ASSUMED: the "reviewer's blocks on a seeded bad bundle catch at least 8 of 10" bar (spec sections 15 and 18) names no mechanism, and the CLI has no reviewer-only command. The runbook has the controller plant ten defects of the two block classes (billboard, guardrail audit) that no denylist scan reads in a scratch copy of the example outside the repo, and run `plan review` on it (4 review calls plus the revise and confirm calls its blocks cause, its own ceiling of 120). The runbook marks this ASSUMED and so does the spec's Task 13 entry. Cost if wrong: that paragraph is rewritten when rung D runs.
- ASSUMED: the spec's "As planned" gets the departures index and the summary at the top of the section, ahead of the task entries, not at the end as Phase 4's did; the one-line-each list is the one the plan's Task 13 asks for and the task entries keep the detail.
- ASSUMED: the HANDOFF "Open items" group carries every ledger line as one condensed bullet per task or pair of tasks, naming the items the ledger names; the ledger has each in full.

## Concerns

- The carry text for N-4 says "the example's expected.yaml pools its null at two rungs". The pooled null is in the example's `plan.md` ("A null result"); `expected.yaml` is per cell and predicts both targets separately. The runbook says: the example's null result (`plan.md`, "A null result", beside its per-cell `expected.yaml`) pools the arms over the two targets and reads two rungs. The substance of N-4 (item 9's per-model mean over the rungs both arms reached gives a different number) is stated as carried.
- The Phase 5 ledger snapshot under `docs/handoff/sdd/2026-11-14-phase-5-director/` was not refreshed (it is the controller's step). HANDOFF "Next steps" item 1 says the final review package is regenerated with `review-package`.
- HANDOFF's "Open items" lists items from the ledger as they stand. Two are marked as since closed or covered (Task 4b's `plan.json` bad byte, closed by Task 9's `DamagedRecordError`; Task 12's M2 and N-4, closed here); I did not re-verify the others against the code.
- One process slip: I appended the spec's Task 13 entry with a shell heredoc (`>>` to a relative path, from the repo root) instead of the Edit tool. The content and target were correct (`git diff` shows an append only); every other edit used the Edit tool.
- The fast gate was run with `-p no:cacheprovider` (no `.pytest_cache` written); the counts are unaffected.

# Fix round 1 (the Task 13 review: I1, M1 to M5, N1 to N6)

FIX_BASE 64b4cf0. Documents only, no model run. One new commit on top of 64b4cf0, d06e18f, same author and trailer, not pushed. Every edit used the Edit tool; no shell write went to a relative path (the only scripts were read-only or wrote to the scratchpad by absolute path, and `git status` shows no untracked file). The "Rung D, as written (quoted)" section above is the 64b4cf0 text and is superseded by the passages quoted below.

## What changed, by finding

- **I1 (the recipe).** Read first: `context.unchanged_base_files` and `Director.review_groups` (`planner/context.py:270-278`, `planner/director.py:458`). Both ways the code supports were checked on a scratch copy of the example bundle (in the scratchpad, outside the repo):
  - As the example stands, `review_groups` gives one group, `plan` (plan.md, config.yaml, expected.yaml): the whole 54-file overlay copy is index lines, so the reviewer sees no corpus document, sheet or ladder at all.
  - With two manifest entries added to the copy's `plan.json` (`worlds/overlay/world.yaml` as `world_sheet`, `worlds/overlay/corpus/cpo-about.md` as `document`, purpose "seeded defect", layer null), `review_groups` gave `corpus-1` and `lines` with those two files in full, and `plan validate` on the copy exited 0 with status `runnable` (it accepted the hand-edited record).
  - Chosen: edit the overlay file in place and add a manifest entry for it (the shape `Director._entry` gives a patched base file). Rejected: planting each defect as a new file, because an unlock line lives in the world sheet (`worlds/overlay/world.yaml`, a base file no new file can replace), and because `bundle.rematerialize_open_stage` removes every grammar file owned by neither `base_files` nor a committed call when a stage 3 is resumed (a kill, or exit 3 and the same command), so a new file would vanish and score as missed. A changed `plan.md`, `config.yaml` or `expected.yaml` needs no entry. The runbook states the choice and the reason, gives the entry's shape, and gives a one-line check (`review_groups` over the copy) whose output must list every seeded path under "full:". The same is recorded in the spec's Task 13 ASSUMED bullet.
- **M1.** The "spec fixes no mechanism" lines (runbook and spec) now say that section 18 names the fixture bundles of section 15, that those are lint fixtures the stage 3 scans and stage 5 lints stop before any reviewer call, that the CLI has no reviewer-only command, and so the recipe departs from it (stated as ASSUMED in both).
- **M2.** The runbook's Estimate paragraph now says: 50 to 110 calls for the plan, plus up to 120 for the seeded check (a second plan with its own ceiling), up to about 230 in all with the check at its ceiling, and that the check is expected to use far less (up to 3 review calls, a revise call per file with a block or a fix, a confirm call per file with a block). HANDOFF's item 4 and the Task 13 Progress entry, the spec's Task 13 entry and the pointer under section 18 say the same.
- **M3.** The runbook's commit paragraph makes the size of a real bundle's `transcripts/` the owner's decision (each attempt stores its whole message, about 195,000 to 235,000 characters a planner call; likely ten megabytes or more, labelled an estimate, against about 135 KB for the example), and the rung's report gives the bundle's total bytes and `transcripts/`'s (and counts the seeded check's ledger in its Calls rows). HANDOFF item 4 names it.
- **M4.** `docs/08-DIRECTOR.md`'s validation table gains `seam_dead_ends` and `outlet_backing` (warn rows, worded from the lints' code), under the existing "Every row below is built".
- **M5.** The Phase 7 spec's section 14 bullet ("about 40 to 100 planner and reviewer calls (`MAX_AUTHOR_CALLS = 80` is the ceiling)") gets a bracketed "Superseded in Phase 5 Task 13" note pointing at the runbook's rung D, section 18 and the new figures (the constant does not exist in the code: grep). The runbook's rung D opening also says those v1 figures are superseded and that this section and the Phase 5 spec's section 18 govern (without naming the constant, so the verify command still holds).
- **Open item.** HANDOFF's "From Phase 5" group gains the Task 12 re-review's third nit (the Task 12 report's claim that the owner pattern has no lookahead is wrong; no effect on any scan).
- **N1.** Kept as one-liners (see Concerns for the owner question).
- **N2.** The command's `--plans-root` is now `output/phase7_rungD_<date>/plans` (the rung's git-ignored output folder; `git check-ignore` confirms `output/` is ignored). The runbook says any directory outside `plans/` serves, a directory outside the checkout included, since `plans/` is the only folder the CI scans read.
- **N3.** Done (the open item above). **N4.** `plan continue` is in the commands read against `--help` (the intro and rung D). **N5.** "of its own, which sits beside the example once it is moved in."
- **N6.** The ledger snapshot under `docs/handoff/sdd/` is not refreshed here (the controller's step at Task 13's close; the review says so too).

## Changed passages, quoted

The seeded-bundle bar (runbook, rung D, "Bars"):

    - the reviewer's blocks on a seeded bad bundle catch at least 8 of 10 (spec sections 15 and 18).
      Section 18 names the fixture bundles of section 15, but those are lint fixtures: the stage 3
      scans and the stage 5 lints stop what they hold before a reviewer sees it, and the CLI has no
      reviewer-only command. ASSUMED: the check is a plan of its own (its own ceiling of 120 calls).
      The controller makes a scratch copy of the example bundle outside the repository and plants ten
      defects of the two classes the reviewer's prompt blocks (a billboard, a guardrail breach), each
      one a defect no denylist scan reads (a document whose main point is the premise, an unlock line
      that announces its evidence by paraphrase, hostility over the ceiling), since stage 3 runs the
      real-name, Boundary and jailbreak scans before every reviewer call and a defect they stop never
      reaches the reviewer. It runs `plan review <copy> --wait-on-rate-limit 360` once, and counts the
      planted defects that stage 3's `review.md` quotes under a `block`. A copy the check edits is never
      committed.

      Every planted defect must sit in a file the reviewer reads in full. Stage 3 shows a reused
      world's file that no manifest entry names as one index line (id, layer, kind, title, address,
      links), never its body (`context.unchanged_base_files`, which `Director.review_groups` reads),
      and the example's manifest names only `config.yaml` and `expected.yaml`: as the example stands
      its 54 overlay files are index lines and the reviewer is shown no corpus document, sheet or ladder
      at all, so a defect edited into one is invisible and would score as missed for a reason that says
      nothing about the reviewer. The code allows two ways to put a defect in front of it, and the
      recipe takes the first: edit the overlay file in place and add a manifest entry for it to the
      copy's `plan.json` (`"manifest"` is a list; the entry is
      `{"path": "worlds/overlay/world.yaml", "kind": "world_sheet", "purpose": "seeded defect", "layer": null}`,
      with kind `document` for a corpus document: the shape `Director._entry` gives a patched base
      file), or plant it as a new file. A new file is not used, for two reasons: an unlock line lives in
      the world sheet (`worlds/overlay/world.yaml`, `WorldSheet.unlock_lines`), a base file that no new
      file can replace; and a stage 3 resumed after a kill, or after a rate limit past the wait, removes
      every grammar file owned by neither `base_files` nor a committed call
      (`bundle.rematerialize_open_stage`), so a new file would vanish and score as missed, where an
      edited base file is owned and stays. A changed `plan.md`, `config.yaml` or `expected.yaml` needs
      no entry (never base files, always reviewed in full). Before the run, this lists what each review
      group reads in full, and every seeded path must be among them; it ran on the example with two
      entries added (`plan validate` accepted that edited `plan.json`, and the groups listed the two
      files):

          uv run python -c "import sys; from pathlib import Path; from claude_bully.planner.bundle import Bundle; from claude_bully.planner.director import review_groups; b = Bundle(Path(sys.argv[1])); [print(g.name, 'full:', list(g.files), 'index lines:', len(g.index)) for g in review_groups(b, b.read_record())]" <copy>

The estimate's new tail (runbook, rung D, "Estimate"):

    The rung also runs the seeded-bundle check below, a second plan of its own (`plan review` on a
    scratch copy, under its own `max_director_calls = 120`): so the rung costs 50 to 110 calls for the
    plan, plus up to 120 for the check, up to about 230 in all with the check counted at its ceiling.
    The check is expected to use far less than its ceiling: up to 3 review calls (one per group the
    copy shows in full), a revise call for each file with a block or a fix and a confirm call for each
    file with a block.

The commit step's new tail (runbook, rung D):

    Size is a decision for the owner before anything is committed: each transcript attempt stores its
    whole message (about 195,000 to 235,000 characters a planner call, measured on stubs), so across 50
    to 110 calls a real bundle's `transcripts/` likely run to ten megabytes or more (an estimate from
    those sizes, not a measurement), against about 135 KB for the stub-built example, and the
    repository scans read every text file of a checked-in bundle. The report gives the bundle's total
    bytes and `transcripts/`'s, and says whether to commit the bundle with its `transcripts/` (with
    `plan.json` they rebuild the authored files, `materialize`) or keep it out of the repository; the
    owner rules on it with the yes.

## Verification

- `uv run python -c "...'### Rung D' in t and 'MAX_AUTHOR_CALLS' not in t..."` exits 0 (run before the commit).
- Docs-reading tests, each under `timeout 300`, `-W error`: `tests/test_real_names.py` 121 passed (1:53); `tests/test_director_prompts.py` 7 passed; `tests/test_director_context.py` 77 passed, 1 deselected; `tests/test_hypotheses.py` 60 passed, 22 deselected; `tests/test_poisoned_well_world.py` 71 passed; `tests/test_world.py` 60 passed; `tests/test_director_author.py` 34 passed, 47 deselected; `tests/test_director_review.py` 8 passed, 42 deselected. `tests/test_bundle_lints.py` (reads the docs' bylines through the owner clause) hit the 300 s limit on its first run (rc 124 at about 84%, the module being the slowest in the suite; the machine was loaded), so it was rerun alone with `timeout 590`: 424 passed, 4 deselected, in 727.71 s (the one deviation from `timeout 300`).
- The full gate was not re-run (documents only; the counts stand at 10766 passed, 11 skipped, 215 deselected, slow 215).
- The recipe's check ran on a scratch copy of the example in the scratchpad: groups before and after the two entries (above), and `uv run claude-bully plan validate <copy>`: eight cells, each `complete top_rung=reached`, `status runnable`, exit 0 (a stub run, no model call).

## ASSUMED (fix round)

- ASSUMED: the rung's git-ignored `output/phase7_rungD_<date>/plans` satisfies Task 12 review M2's "a directory outside the repo" (its reason is that `plans/` is the only folder the CI scans read); the runbook says a directory outside the checkout serves as well. Cost if wrong: one path in the command.
- ASSUMED: the seeded check's expected cost is stated as "far less" than its ceiling (up to 3 review calls and a revise and a confirm call per file at ten files at most), from the code's stage order, not from a run. Cost if wrong: an estimate line.
- ASSUMED: "likely ten megabytes or more" for a real bundle's `transcripts/`, an estimate from the message sizes the runbook already measured on stubs and the call count, labelled as such. Cost if wrong: one sentence; rung D measures it.

## Concerns (fix round)

- N1 for the owner (via the controller): the two `python -c` one-liners (the `plan.json` reader, the ledger reader) and the new `review_groups` one-liner are single-use commands in the runbook. ASK owner (workspace rule: a one-time script that could be reusable): keep them as one-liners, or add one `scripts/` file for the rung (not done: it would be code, and this round is documents only). Checked: the runbook, HANDOFF and the ledger name no existing script that reads a plan bundle.
- The seeded-bundle check hand-edits the copy's `plan.json` (a harness-owned record). The copy is scratch and never committed, and `plan validate` accepted the edited record, but `plan review` on it is not run here (that is the rung's first model call); a defect in the recipe that only a real `plan review` shows costs a rewrite of that paragraph.
- The ledger snapshot (N6) and the push are the controller's.
