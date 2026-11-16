# Task 12 review: the example bundle and CI over plans/

Base 72ed8f0, head a9b3856 (HEAD 8c70416 is docs-only on top: `git diff --stat a9b3856 8c70416` touches only HANDOFF.md and the SDD folder). Reviewer: task-scoped gate. Probes are in `probes-task12-review/`. They are run from the repo root with `-p tests.conftest -p no:cacheprovider --basetemp <scratchpad>`, and the scratch directory is removed after each run.

## Verdicts

- **Spec verdict: compliant, with one as-built claim that is false (I2).** Every brief item is present:
  - `PLANS_DIR`;
  - the script, `provenance: manual`, `status: runnable`;
  - the overlay byte copy with `base_worlds`, `base_files` and `base_premise_terms`;
  - the manifest before the author files (Q17);
  - `review.md` at `block 0 / fix 0 / note 0`;
  - no `ledger.jsonl`;
  - the four scans extended to `plans/`, each with a covers test;
  - the brief's five tests;
  - the docs-sync.
- **Quality verdict: needs a fix round (2 Important).** The scans read the right files and fail on every straight plant. They read raw text, though, and the bundle lints learned in Task 4b (I3) not to do that. For `review.md` and the transcript replies, CI is the only reader.

Counts: Critical 0, Important 2, Minor 4, Nit 3.

## Named risks, answered

1. **Every scan reads what it claims.** Yes, for every plant that is not wrapped across a line. Each plant ran the CI test body itself, on a tmp copy of the bundle with the module's `PLANS_DIR`, `EXAMPLE` and `plans_bundle_files` pointed at it. These all fail as they should:
   - a real name in `plan.md`, in `review.md`, in a world document, in a `config.yaml` comment and in `dryrun.jsonl`;
   - a real name in a transcript reply behind an escaped newline;
   - the owner's name in `plan.md`, `review.md`, a reply, a world document and `plan.json`. The assertion text never holds the name;
   - a jailbreak phrase in `review.md` and in `plan.json`;
   - a Boundary term in a corpus document, in a `world.yaml` comment and in a `personas/` file.

   Out of scope, and passing as designed:
   - a real name in a transcript message;
   - a jailbreak phrase in a reply;
   - a Boundary term in `plan.md`;
   - anything under `dryrun/` or `state/`.

   The real-name covers test does prove each committed file lands in exactly one of its four lists. `sorted(listed) == plans_bundle_files()` fails on a duplicate and on an omission. A stray `notes.csv` or a suffixless `corpus/README` fails it (probes 19 and 20).

   Not caught: a phrase wrapped across a line, or one JSON-escaped (I1).
2. **The owner clause.** It fails loudly. With `owner_names` pointed at a docs directory that has no byline, the test raises `ValueError ... names the owner`. It does not skip (probe 11).
3. **A6 and the rebuild.**
   - Drift detection is real. One flipped byte in a tmp `worlds_dir` copy of the overlay fails `test_a_moved_overlay_fails_until_the_example_is_rebuilt`, whether the byte is in a corpus document, `ladders/default.yaml`, `world.yaml` or `premises/rescue.yaml`. So does an added overlay file, and so does one flipped byte in a tmp copy of the bundle. That last one also fails `test_the_example_is_there_and_hand_authored` on `bundle_hash`.
   - The rebuild is deterministic. Two `build(validate=False)` runs differ only in `plan.json`, and only in its timestamp fields. A full `build(validate=True)` in tmp reproduces every committed file of the checkout byte for byte except `plan.json`, which matches apart from timestamps. That includes `dryrun.jsonl` and the transcripts.
   - The byte-compare test is not flaky: `hashed_paths` excludes `plan.json`.
   - `git status` is clean after `tests/test_example_bundle.py -m "slow or not slow"` (10 passed) and after the four focused files (144 passed).
   - `plan validate` (`Director.revalidate`) on a copy rewrites only `plan.json`, and only its timestamps. Run on the checkout, it would leave a diff of timestamps only (M4).
4. **Local `plans/` bundles are scanned.** That is spec-literal: section 15 says "every bundle under `plans/`", and only `dryrun/`, `state/` and `_cache/` are ignored, so anything under `plans/` is committable. It does turn the local gate red while a rung-D plan is in flight there (probe 22; M2).
5. **The ASSUMED lines.** All are accepted:
   - **`target_models`** keeps `plan.json` true to `config.yaml`. The default budget (18 turns, 3 reps, 12 cells) holds the eight cells.
   - **Eight cells.** Four per target on two targets. `expected.yaml` predicts both condition cells of each target, which matches the dry-run cell ids.
   - **Transcript messages are not read.** Spec section 12 left this to Task 12, the carries say "the replies only", and the decision is recorded in section 12.
6. **No real model call.** A counting wrapper around `_no_provider` recorded zero calls through a full `build(validate=True)`. Every stage call has status `manual`. The factory matches the `ProviderFactory` call shape (`director.py:1042`).
7. **Goldens are untouched.** `git diff 72ed8f0 8c70416 -- tests/fixtures/golden data/ configs/` is empty, and the only package file changed is `claude_bully/paths.py`. `diff -r data/worlds/overlay plans/.../worlds/overlay` finds no difference, so the 46 corpus documents and the ladders match.

## Findings

### Important

**I1. The CI scans read raw text, so a phrase wrapped across a line escapes them. For `review.md` and the transcript replies, CI is the only reader.**

The bundle lints collapse each paragraph's whitespace (`bundle_lints._collapse`, Task 4b fix round 1, review I3). The new CI scans do not. They call `scan(text, patterns)` on the raw file, or on the decoded strings. Probes 24 to 27 pass, which means each of these is missed:

- "ignore all previous" + newline + "instructions" in `review.md`;
- "ignore all" + escaped `\n` + "previous instructions" in `plan.json`'s constraints;
- "Wall Street" + newline + "Journal" in `review.md`;
- "safety" + newline + "training" in a world document.

`real_name_bundle` and `jailbreak_bundle` both exempt `review.md`, and nothing else reads the transcript replies. So for those files the miss gets past every check, against section 14's "fail closed on non-negotiable 3".

- Where:
  - `tests/test_guardrails.py:88` (`test_no_denylisted_text_in_the_plans_bundles`);
  - `tests/test_real_names.py:413` (the `plans/` text files go through `test_no_real_names_in_worlds_or_personas`);
  - `tests/test_real_names.py:484` (`_reply_hits`);
  - `tests/test_boundary.py:137`, where the miss matters less, since `boundary_bundle` collapses and `bundle_hash` pins world files.
- Fix:
  - Make `_collapse` public in `planner/bundle_lints.py` (say `collapse_paragraphs`).
  - For every `plans/` file, scan its collapsed text as well as the raw text. For JSON, collapse each decoded string, and give the jailbreak scan the same decoded strings the real-name scan already reads.
  - Add plants of a wrapped phrase in `review.md` and in a reply.

**I2. `plan.md`'s display-name rule is unsettled, and one as-built claim is false.**

Three things disagree:

- **(a) CI is stricter than the lint.** CI reads `plan.md` with no spare, so "Claude" in `plan.md` fails (probe 8). docs/08 section 9 has `real_name_bundle` read `plan.md` "through the config's spare, since a plan names its target". So a Director-written plan that names its target is `runnable` and then fails CI. Rung D regenerates exactly this bundle (C22, Task 13).
- **(b) The same words get two verdicts.** Those words in the transcript reply that commits `plan.md` are spared (`_reply_hits` applies `config_scan_text`).
- **(c) The no-exemption claim is false.** A `# real-name-ok: claude` line in `plan.md` does exempt the display name, and `test_exemptions_name_only_the_targets_display_name` accepts it (probe 9). That contradicts the spec's as-built row 2 ("the text files whole with no exemption for `plan.md` or `review.md`"), the module docstring and the report's ASSUMED line.

- Where:
  - `tests/test_real_names.py:418` (`_exempted` is honored for `plans/` files);
  - `tests/test_real_names.py:484`;
  - spec section 12 row 2, "As built".
- Fix: choose one rule and make the code, the docstring and the spec say it.
  - **Recommended:** read `plan.md` under `plans/` through `config_scan_text` with `_plans_display_names(bundle)`, as `real_name_bundle` and the reply scan do, and stop honoring `real-name-ok` for any file under `plans/`.
  - **Or:** keep `plan.md` strict, ignore `real-name-ok` under `plans/`, and carry a line to Task 13 that a regenerated `plan.md` naming its target is hand-edited before commit.

### Minor

**M1. The suite has no plant tests for the jailbreak and Boundary scans over `plans/`, and the real-name plant test only partly tests the scan.**

`test_a_planted_owner_name_or_real_name_in_a_plans_bundle_is_caught` has three gaps:

- it checks the `plan.md` plant with `scan()` directly, which proves nothing about file selection;
- it plants no real name in `review.md`;
- it never runs a CI test body on a redirected `plans/`.

The covers tests guard selection today, but a regression in a scan body would go unseen.

- Where: `tests/test_real_names.py:532`, `tests/test_guardrails.py`, `tests/test_boundary.py`.
- Fix: give each scan body a `plans_dir` parameter (the helpers already take one), and add plant tests that run it on a tmp copy, as `probes-task12-review/probe_task12_scans.py` does.

**M2. A rung-D plan in flight under `plans/` turns the local gate red.**

Several tests fail on such a plan:

- `test_every_bundle_passes_every_lint` (parametrized on any directory holding a `plan.json`, so an unvalidated record fails the `dry_run` lint);
- the slow dry-run equality test;
- the real-name scan of a `plan.md` that names its target (I2).

This follows the spec, and it works as a guard before commit. But `plan new` defaults to `plans/` (`DEFAULT_PLANS_ROOT is PLANS_DIR`), and the runbook does not say what to do.

- Where: `tests/test_example_bundle.py:26`, `tests/helpers.py` (`plans_bundles`).
- Fix: a Task 13 runbook line saying that rung D runs `plan new --plans-root <outside the repo>` and moves the bundle into `plans/` once it is clean. The other way is to read `git ls-files plans/`, which departs from section 15. The runbook line is recommended.

**M3. Reader-eye review (spec section 14): the null result overlaps the predictions.**

The null result is "Within one rep at every rung" at three reps. The predicted gaps are each one rep:

- `buried_opens`: some (1 of 3) against rare (0 of 3);
- `the_truth`: most (2 of 3) against some (1 of 3).

So the predicted outcome can also meet the falsifier, and the plan cannot tell hypothesis 9 from its null.

`plan.md` shows no billboard: it is harness-side, and the task adds no unlock line. Its predictions are otherwise specific enough to be wrong.

- Where: `scripts/build_example_bundle.py:139-145`.
- Fix: state the null on the targets pooled (6 reps per arm), or as "scheduled at or above triggered on the adoption events at `buried_opens` and `the_truth`". Or say plainly that three reps cannot separate adjacent bands. Then rebuild.

**M4. `plan validate` on the checkout rewrites `plan.json` timestamps.**

It is harmless (`plan.json` is not hashed) and the tests do not do it. But anyone following HANDOFF's "rebuild or validate" sees a diff of timestamps only.

- Where: HANDOFF "Repository", the `plans/` bullet.
- Fix: one clause, saying that a `plan.json` diff of timestamps alone after `plan validate` is not committed. Optional.

### Nit

- **N1.** `tests/test_example_bundle.py:26` re-implements `helpers.plans_bundles`. With no `plans/` directory it fails at collection. Use the helper.
- **N2.** The script copies with `read_text` and `write_file`, which strips CRLF and any BOM. That is not literally byte for byte, though A6's bytes compare would fail loudly on any difference (`scripts/build_example_bundle.py:270`). An assert at copy time that the written bytes equal `path.read_bytes()` would make the claim mechanical.
- **N3.** `_record_texts` (`tests/test_real_names.py:292`) calls `json.loads` on every `.jsonl` line. A torn last ledger line, which the harness tolerates, would error with a raw `JSONDecodeError` instead of naming the file. No committed bundle has one.

## Probes

`probes-task12-review/probe_task12_scans.py` (32 tests, all pass, each asserting the scan's verdict):

| # | Plant (tmp copy) | Scan | Result |
| --- | --- | --- | --- |
| 00 | none | all 11 scan and covers bodies | pass (baseline) |
| 01 | real name in plan.md | real text | fails |
| 02 | real name in review.md | real text | fails |
| 03 | real name in a reply, after an escaped newline | real replies | fails |
| 04 | real name in a message | real replies | passes (not read, by design) |
| 05 | real name in a corpus document | real text | fails |
| 06 | real name in a config.yaml comment | real config | fails |
| 07 | real name in dryrun.jsonl, after an escaped newline | real records | fails |
| 08 | display name in plan.md | real text | fails |
| 09 | `# real-name-ok: claude` and the display name in plan.md | real text, exemptions | both pass (I2) |
| 10 | owner's name in plan.md, review.md, a reply, a world document, plan.json | owner | fails, name not in the message |
| 11 | no byline in the docs | owner | raises ValueError, no skip |
| 12, 13 | jailbreak phrase in review.md, in plan.json | jailbreak | fails |
| 14 | jailbreak phrase in a reply | jailbreak | passes (out of scope) |
| 15, 16, 17 | Boundary term in a corpus document, a world.yaml comment, a personas file | boundary | fails |
| 18 | Boundary term in plan.md | boundary | passes (out of scope) |
| 19, 20 | notes.csv; a suffixless corpus file | real covers | fails |
| 21 | planted files under dryrun/ and state/ | real text, jailbreak, covers | pass (never read) |
| 22 | a second, in-flight bundle whose plan.md names the target | real text | fails (M2) |
| 24 to 27 | wrapped jailbreak phrase in review.md; JSON-escaped one in plan.json; wrapped real name in review.md; wrapped Boundary term in a corpus document | jailbreak, real text, boundary | pass, so missed (I1) |

`probes-task12-review/probe_task12_a6_rebuild.py` (10 tests, all pass, `-m "slow or not slow"`):

- **A6 baseline.** A tmp `worlds_dir` copy of the overlay passes.
- **A6, one byte flipped in the tmp overlay.** It fails, whether the byte is in a corpus document, `ladders/default.yaml`, `world.yaml` or `premises/rescue.yaml`.
- **A6, an added overlay file.** It fails.
- **A6, one byte flipped in a tmp copy of the bundle.** It fails A6, and also `test_the_example_is_there_and_hand_authored` on `bundle_hash`.
- **Rebuild twice (`validate=False`).** Only `plan.json` differs, and only in its timestamps.
- **Full `build(validate=True)` in tmp.** No provider call is made, the result is `runnable` and every call is `manual`. Every committed file equals the checkout except `plan.json`, which matches apart from timestamps.
- **`Director.revalidate()` on a copy** (what `plan validate` runs). Only `plan.json` changes, and only its timestamps.

Also run: `tests/test_example_bundle.py -m "slow or not slow"` gave 10 passed. The four focused files, fast, gave 144 passed. The slowest call was 1.38 s, and the 4.00 s on the first test is setup. `git status` was clean afterwards, with only the ignored `dryrun/` present.
