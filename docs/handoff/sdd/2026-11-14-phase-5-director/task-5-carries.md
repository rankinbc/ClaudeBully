# Task 5 carries

These come from the ledger. They bind this task in addition to the brief and the preflight rows that name Task 5 (Q20 among them: dry_run cases run through 4b's CASES test, and the lint needs more than half near-misses).

- **Task 2 (stub reasoning).** Ship a test that the stub's reserved `reasoning` key reaches no Completion chat field, no run record, and no bully, generator or judge prompt. Use the sentinel-on-watched-Turns pattern of tests/test_reasoning_channel.py.
- **Task 2 (stub rules).** Add tests for the two stub rules the implementer assumed: a turns script needs a non-empty `default`, and a non-string `reasoning` value is refused. Add the `fnmatchcase` line to the spec's "As planned".
- **Task 3 review (R-buried).** Test the stray-search-hit case. A buried document that no fired rung names by id, but that the scripted search hits, fails. Plant one in a temporary copy of the overlay and assert the failure. Also assert that the shipped overlay passes.
- **Task 4b (budget).** The `max_calls` clause of `budget` already exists from Task 4b. Extend it; do not add it again. The `dry_run=[]` half of `budget` is this task's.
- **Task 4b re-review round 3 (NEW-3).** A self-referencing YAML anchor in an `Any` field (condition `params`, persona `intent_meta`) passes lint_bundle, but `model_dump(mode="json")` raises on it. The dry run model-dumps the experiment, so a cyclic value must fail `schema` before the dry run, as a fail and not an exception.
- **Task 4b re-review round 3 (NEW-2).** Catch `RecursionError` and every `yaml.constructor` error (explicit tags such as `!!bool maybe`, `!!timestamp abc`, `!!int ''`) at each `safe_load` site that lint_bundle reaches. Each one becomes a schema fail that names the file. Reuse the probes in `.superpowers/sdd/2026-11-14-phase-5-director/probes-task4b-rereview3/`.
- **Task 4b M-1.** Scope the spec's split-phrase residual sentence: the gap is open only in markdown files and in YAML `|` literal blocks. A split phrase in folded, plain or quoted scalars is caught.
- **Phase 4 lessons.**
  - Test resume parity at each kill point the brief names.
  - A rate limit pauses the dry run; it never degrades it.
  - The dry run makes no real model call: stub providers only.
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
- **Write regex lines with the Edit tool only.** A Bash heredoc turns `\b` into a control character.
