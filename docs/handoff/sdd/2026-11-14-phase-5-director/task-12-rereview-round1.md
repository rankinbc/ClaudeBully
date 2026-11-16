# Task 12 re-review, fix round 1

Base 8c70416, head e191082 (one commit). Reviewer: scoped gate, sonnet. Probes are in `probes-task12-rereview/` (three files, 67 tests, all pass). They run from the repo root with `-p tests.conftest -p no:cacheprovider --basetemp <scratchpad>`, each plant in a tmp copy of the example bundle, and the scratch directory is removed afterwards. The owner's name came from `owner_names()` at run time. It was written only into tmp copies, which are deleted. It is never printed, and no assertion echoes it.

## Verdicts

| Finding | Verdict |
| --- | --- |
| I1 | FIXED |
| I2 | FIXED, with one open consequence for `review.md` (point 2 below) |
| M1 | FIXED |
| M2 | FIXED by documentation; the runbook line itself is still Task 13's |
| M3 | FIXED |
| M4 | FIXED |
| N1, N2, N3 | FIXED (N3 leaves one sibling case, new Minor N-2) |

New: Critical 0, Important 0, Minor 3 (N-1 to N-3), Nit 1. Regressions: none.

## I1: the scans read folded text

Each plant ran the scan body itself (`plans_real_name_hits`, `plans_owner_hits`, `plans_jailbreak_hits`, `plans_boundary_hits`) on a tmp copy with `plans_dir` pointed at it. Every plant below fails the scan and the hit names the planted file.

- **Real name** ("Wall Street" + newline + "Journal"), 9 plants:
  - `review.md` split by LF, by CRLF and by a double space;
  - `plan.md` split;
  - `plan.json`, a constraint holding an escaped newline;
  - a transcript reply, JSON content split;
  - a transcript reply, non-JSON text split;
  - a world document split;
  - `review.md` straight.
  A name in a transcript message still passes, as designed.
- **Owner**, 6 plants:
  - `review.md` straight and after a newline;
  - `plan.json` after an escaped newline;
  - a reply, JSON content;
  - a world document;
  - `plan.md`.
  Every hit names the file and none holds the name. The owner's name on this machine is one word, so there is nothing to wrap, and the multi-word variants (the probe would add 4) did not run. Folding changes nothing for a one-word name, so the escaped-newline and own-line plants are the meaningful ones.
- **Jailbreak** ("ignore all previous" + newline + "instructions"), 6 plants:
  - `review.md` straight, split by LF and by CRLF;
  - `plan.md` split;
  - `plan.json` escaped newline;
  - a world document split.
  A phrase in a transcript reply passes. That is by design: spec section 9 leaves `transcripts/` out of the jailbreak scan.
- **Boundary** ("safety" + newline + "training"), 4 plants plus a persona file:
  - a corpus document split by LF and by a double space;
  - `world.yaml` split and a `world.yaml` comment straight;
  - a `personas/` file split across a block scalar.
  A term in `plan.md` or in a reply passes. That is by design: the Boundary scan covers `worlds/` and `personas/` only.

**Folding is reused, not copied.** `bundle_lints.collapse_paragraphs` is the only definition. The package's two users, `_scan_texts` and `_jailbreak_bundle` (four calls), use it, and `tests/helpers.py: folded` and `tests/test_boundary.py` import it. A grep for `_collapse` finds nothing left. The only other paragraph-join in the tree is a pre-existing helper at `tests/test_bundle_lints.py:414`, which this diff does not touch.

**The plant tests discriminate (M1 as well).** I broke the fix three ways, one at a time, and ran the repo's own plant dicts:

- With `folded` as the identity, every wrapped real-name plant (4), every wrapped or escaped jailbreak plant (3) and the wrapped Boundary plant went unseen. That is the report's 9 failures.
- With `config_scan_text` as the identity, the display name in `plan.md` failed.
- With `record_strings` emptied, the wrapped `plan.json` plant went unseen.

**Layering.** CI does not decode YAML escapes, so a wrapped name written as a double-quoted scalar with `\n` in `world.yaml` passes the CI text scan. The bundle lint catches it (`real_name_bundle` fails, probed), and `test_every_bundle_passes_every_lint` runs the lint over every bundle under `plans/`. So there is no gap. `review.md` quotes are JSON strings (`render_review`), so a quoted line break is a literal backslash-n that CI reads raw. That cannot hide a hit, since `check_findings` requires every quote to be text of a file the scans already read.

## I2: plan.md's display-name rule

- **A display name in `plan.md` passes.** The bundle's own names ("Claude", "CLAUDE", "claude") are spared.
- **Any other real name fails** (Reuters, Gemini, OpenAI, Anthropic, each next to a "Claude").
- **The spare is per bundle.** A second bundle whose config and request name "Gemini" spares it in its own `plan.md`. The example's `plan.md` naming "Gemini" fails, and the other bundle's file is not flagged.
- **`real-name-ok` exempts nothing under `plans/`.** The line, with the name it exempts and a name it does not, fails in `plan.md`, `review.md`, `config.yaml`, `expected.yaml`, a world document and `world.yaml`. `# real-name-ok: claude` does not spare "Claude" in `review.md`. `_scanned_files()` holds no file under `plans/`. `_exempted` is untouched for `data/` and the fixtures, and `test_exemptions_name_only_the_targets_display_name` passes.
- **The lint and CI now share the rule for `plan.md`.** The CI spare is the config's names plus the request's, a superset of the lint's (config only), so a `plan.md` that passes the lint passes CI.
- The spec's section 12 row 2, the docs/00 section F paragraph, the module docstring and HANDOFF item 14 all now say the new rule. No "no exemption" text is left.

### Point 2: can `review.md` staying strict fail a Director-validated bundle?

**Yes, today.** Probed on a tmp copy:

- `render_review` renders a note whose quote is `display_name: Claude`, a line of `config.yaml` that the reviewer is shown as written. `lint_bundle` gives no `real_name_bundle` or `jailbreak_bundle` fail, because the lint and the Director's pre-call scans (`review_scans`) leave `review.md` out. The CI real-name scan fails on `review.md`.
- The same words in `plan.md` pass CI, so the two files get two verdicts.
- A planner `response` such as "kept the line, Claude reads it" fails CI the same way.

The path is not rare. The example's own `config.yaml` carries `display_name: Claude` on both targets, so any reviewer finding that quotes the targets block, or a sentence of `plan.md` that names the target, lands in `review.md`. A rung-D plan (Task 13) regenerates exactly that.

**Recommended ruling: spare the bundle's own target display names in `review.md`'s real-name read, and nothing else.**

- Read `review.md` through `config_scan_text(text, _plans_display_names(root))`, as `plan.md` is read.
- Keep the owner clause, the jailbreak scan and every other real name strict on it.
- Keep `real-name-ok` ignored.

Reasons:

1. `review.md`'s quotes come from `plan.md` and `config.yaml`, where the name is legal.
2. CI is `review.md`'s only reader (lint, pre-call scans and transcripts are all exempt), so it should reject names outside the spare, not the spare itself.
3. A hand edit of a rendered `review.md` moves `bundle_hash` (it is a hashed file), so it forces a new `plan validate`.

The residual, a reviewer or planner free-text field (`problem`, `direction`, `response`) naming a real name outside the display names, stays fail-closed. Nothing scans those fields before CI. Carry to Task 13's runbook: "a `review.md` that CI rejects for such a name is hand-edited, then `plan validate` is run again". Having the Director scan the rendered `review.md` before it commits would be better still, but it is not needed now.

If the owner keeps `review.md` strict: the ASSUMED line stands as written, but "a validated bundle never fails CI" is then false for `review.md`, and docs/08 and HANDOFF do not say that a review quoting the target is hand-edited before commit.

## The minors and nits

- **M1 (plant tests): fixed.** Each scan body is a function of `plans_dir`. The plant tests run the real body on a tmp copy: 12 real-name plants, 4 display-name spares, 5 owner files, 6 jailbreak plants, 4 Boundary plants, each group with a clean-copy baseline, and out-of-scope checks for transcripts and `plan.md`. The mutation runs above show they bite.
- **M2: addressed by documentation.** HANDOFF "Repository" now says a plan in flight is made with `plan new --plans-root <outside the repo>` and moved in once `runnable` and clean. The spec's Task 12 fix-round bullet marks it as a carry to Task 13's runbook. There is no `task-13-brief.md` yet, so the runbook line is still to be written. Keep it on the Task 13 list.
- **M3 (null result): fixed.** The null is now on the arms pooled over both targets, 6 reps per arm: scheduled at or above triggered on an adoption event at both `buried_opens` and `the_truth`. In 6 reps the predictions give triggered 2 to 3 of 6 against scheduled 0 to 1 at `buried_opens`, and 4 to 6 against 1 to 3 at `the_truth`. So the predicted outcome never meets the null, and the plan says outright that 3 reps cannot separate adjacent bands on one target. Only `plan.md`, its transcript and `plan.json` changed. The byte-rebuild test passes, so `bundle_hash` and `dryrun.jsonl` are consistent.
  - Nit N-4: the pooled-at-two-rungs reading is the plan's own. `analyze --hypotheses` item 9 (`item_9`) compares per model, as a mean over the rungs both arms reached. The two will not give the same number. Say so in the README or the runbook.
- **M4: fixed.** HANDOFF says a timestamp-only `plan.json` diff is not committed.
- **N1: fixed.** `tests/test_example_bundle.py` uses `helpers.plans_bundles`, and with no `plans/` it returns `[]` (probed). `BUNDLES == plans_bundles()`.
- **N2: fixed.** The script compares each written file with the shipped bytes. A CRLF overlay, a lone CR and a BOM are all refused with `differs from the shipped bytes` (probed). The default build is untouched.
- **N3: fixed, with one sibling left.** A torn last line without a newline is skipped. A bad last line closed by a newline, and a bad middle line, raise `ValueError` naming the file and the line. That is the rule of `runner/store.parsed_lines`.

## New findings

**N-1 (Minor): the CI raw read is stricter than the lints where a lookahead spare wraps.** The two lookahead patterns are `the verge` not before ` of` (`real_names.txt:54`) and `rule` not before ` out` (`boundary.txt:8`). The lints read collapsed text, which spares them across a wrapped line. CI reads the raw text as well as the folded text, and the raw text does not spare them.

Probed in a world document of a tmp copy:

- "on the verge" + newline + "of closing": the lint is clean, CI real-name fails.
- "rule" + newline + "out": the lint is clean, CI Boundary fails.
- Both on one line pass both.

This predates the round: CI always read raw, and the ruling kept the raw read. It makes "a bundle that validates never fails CI" untrue for those two phrases. A line of prose that wraps at "rule" is plausible in a planner-written document. The fix is small: have the plans scans read the folded text only, or spare those two patterns on the raw read. The Boundary per-line read is the one that hit in the probe (`cpo-about.md:35`), so it cannot stay as it is: a per-line read can never spare a lookahead that spans a line break. The raw read adds nothing else, since folding only changes whitespace and these two lookaheads are the only whitespace-sensitive patterns. Probe: `probe_task12_rereview_lookahead.py`.

**N-2 (Minor): `record_strings` splits on `str.splitlines()`.** It also breaks on U+2028, U+2029, U+0085 and similar. A `ledger.jsonl` line written by `model_dump_json()` keeps those characters raw inside a string. The Director already knows this: `_ledger_numbered` splits on `\n` alone (Task 7b re-review N-B, "a provider's error text can carry raw"). A valid line with a raw U+2028 raises `ValueError: line 1: not JSON (Unterminated string...)` (probed). The old `_record_texts` split the same way, so this is no regression, but it is the exact case N3 set out to name correctly. It is reachable only for a Director-made bundle, which has a `ledger.jsonl`; the example has none. The fix is `text.split("\n")`.

**N-3 (Minor): the review.md ruling above (point 2).** If the owner takes the recommendation it is a one-line change plus a plant test. It is not a regression of this round. It is the "one rule shared by lint and CI" aim of the ruling, which the `plan.md` fix met and the `review.md` fix did not.

**N-4 (Nit):** the pooled null against `item_9`'s per-model reading (M3 above).

## Regressions

- **Example bundle:** `tests/test_real_names.py`, `tests/test_guardrails.py`, `tests/test_boundary.py` and `tests/test_example_bundle.py`, with `-m "slow or not slow" -W error`, gave 181 passed in 63 s. That includes the byte-for-byte rebuild, A6, the lint pass and both-arm dry runs. 68 of the `real_name`, `jailbreak`, `boundary` and fold tests of `tests/test_bundle_lints.py` passed too. The full file runs past 300 s, as the fix report says. `ruff format --check` and `ruff check` are clean.
- **Checkout clean:** `git status --short` is empty after the runs.
- **Goldens untouched:** `git diff 8c70416 e191082 -- tests/fixtures/golden data configs` is empty. The package change is `bundle_lints.py` only (the rename and its three call sites).
- **Files changed outside tests and docs:** `HANDOFF.md`, `bundle_lints.py`, the three bundle files (`plan.md`, its transcript, `plan.json`) and the build script.
- **Tmp copies and the scratch directory:** deleted.

## Probes

| File | Tests | What |
| --- | --- | --- |
| `probe_task12_rereview.py` | 43 | I1 plants for all four families, I2 spare and exemptions, `review.md` rendered from `render_review`, the owner variants |
| `probe_task12_rereview_minors.py` | 21 | mutation runs of the repo's plant dicts, the YAML-escape layering, N1, N2 (CRLF, lone CR, BOM), N3 (torn, closed-bad, mid-file, U+2028) |
| `probe_task12_rereview_lookahead.py` | 3 | N-1: the verge and rule, wrapped and on one line |
