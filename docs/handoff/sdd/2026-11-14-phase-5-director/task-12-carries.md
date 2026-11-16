# Task 12 carries

These come from the ledger. They bind this task together with the brief and the preflight rows that name Task 12.

## What the CI scan of `plans/` must do

- **Read `review.md` whole (Task 4b re-review M-2).** The docs cite a CI jailbreak scan of `review.md`. State it in spec section 12 and build it. CI reads `review.md` in full, even though the bundle lint `jailbreak_bundle` exempts it.
- **Reuse the owner clause (Task 6 R1).** It comes from `planner/lints.py: owner_names`, which reads the owner's name from the docs' byline at run time. The name stays off every checked-in list. A checked-in bundle that names the owner fails CI.
- **Expect `lint_bundle` to raise when `docs/` has no byline (Task 6 round 2).** CI runs on a full checkout, so this holds there. Make the CI test fail loudly if the byline is missing; never let it skip silently.
- **Scan these files.** They are R-scan-bundles' scope:
  - every text file of every bundle under `plans/`
  - for transcripts, the replies only, because the messages quote docs/01-07, which name the CLI's maker
  - every file is real-name clean, including `plan.md`, `review.md`, `plan.json`, `dryrun.jsonl` and the grammar files

## How the example bundle is built and checked

- **Validate it end to end.** It is built by `scripts/build_example_bundle.py` and must pass `plan validate` as `runnable`, through the same `lint_bundle` and dry run the Director uses. The plan review's C1 fix is what made it runnable: a document a shipped ladder unlocks by id is reachable by design.
- **Copy the overlay's bytes (A6).** The example holds a byte copy of the overlay under `worlds/overlay/`. A test fails when the shipped overlay drifts from the copy without a rebuild.
- **Keep goldens byte-identical.** No real model call; stub providers only.

## Practical rules

- **No real names anywhere.**
- **Disk: about 2 GB free.** The example bundle is checked in, so keep it small. Delete any temporary run.
- **Timeouts.** Every pytest run uses the pyproject `faulthandler_timeout` (120 s).
- **Shell writes.** Write regex lines with the Edit tool only. Never redirect a shell write to a bare relative path.
