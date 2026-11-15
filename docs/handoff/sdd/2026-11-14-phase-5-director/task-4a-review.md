# Task 4a review: the good fixture bundle, plan_personas and lint_bundle's first lints

Task-scoped gate. Base 370b177, head e4ca983 (diff `review-370b177..e4ca983.diff`, read once). Read-only on the checkout; every probe is under `probes-task4a/` and builds its bundles in a temp directory. The suite was not re-run; the two registry modules were run in both orders as asked.

## Verdicts

- **Spec: PASS.** Every Interfaces name exists with the brief's signature. Q17 to Q21 hold, and so does R-registry. R-good-warn and R-premise-terms hold. The good bundle's files meet Step 1's list. `SCHEMA_VERSION` and the run records are untouched, the plain goldens are not in the diff, and no real name appears in any new file. One gap is against a binding constraint (I1): `manifest_complete`'s near-miss share is over half on paper but not in substance.
- **Quality: PASS with one Important.** Every fresh probe confirmed the lint code: 47 fresh cases across the lints, 6 double-fault cases, 11 malformed-file cases and 13 registry checks. The weak spots are the tests, plus a few minor holes in `schema`.

Counts: Critical 0, Important 1, Minor 5, Nit 5.

## Findings

### Important

**I1. Three of `manifest_complete`'s four near-misses mutate nothing** (`tests/test_bundle_lints.py:123-142`, rows at `:221-223`).
- `_fixed_files_unlisted`, `_base_file_unchanged` and `_base_file_patched` each only assert a property the good bundle already has. `lint_bundle` then runs on the unchanged bundle, which is exactly the negative row at `:212`.
- So the real near-miss share is 1 of 7 (`_errored_and_absent`), not 4 of 7. `test_the_bundle_lints_carry_more_near_misses_than_positives_so_far` counts the three as near-misses, and Task 4b's coverage test will inherit the hollow count.
- Failure scenario: someone tightens the rule so that a base file whose bytes differ from `base_files` fails, or so that a harness file (transcripts, `.attempt.json`) counts as outside the manifest. No test fails. Both are exactly the boundaries these rows were meant to fence, and spec section 8 says `plan review` and `plan validate` adopt hand edits, so a hand-edited base file must pass.
- Fix: keep each row's assertion as a precondition, and make each row mutate toward the boundary:
  - (a) Rewrite `review.md` with findings, and add a `transcripts/` file and a `.attempt.json`.
  - (b) Hand-edit a base file that no manifest entry names, such as `ferry-about.md`.
  - (c) Add a new manifest entry that patches a second base file through `write_manual`.

  Probe p3 measured all three: each passes the current code. Add (d), an absent entry whose last call is an `error` after an earlier ok call (passes), and (e), an entry present on disk although its call is an `error` (passes).

### Minor

**M1. `schema` stops at the first failing step, which hides independent second errors** (`claude_bully/planner/bundle_lints.py:529`, `:535`).
- Steps 1 to 5 report together. The environment-world check and the dry run are skipped after any earlier failure, and the dry run reports only its first refusal.
- Measured in probe p3 (DOUBLES), four of six two-fault bundles report one fault:
  - persona `captor` plus `world: overlay`: only the persona;
  - a document `mood:` plus a bad Rescue param: only the document;
  - two bad Rescue conditions: only the first;
  - `world: overlay` plus a bad param: only the world.
- The brief and spec section 9 neither require nor forbid stopping. The "stops at the first that fails" sentence in the spec's "As planned" is the implementer's own text, recording an ASSUMED choice.
- Cost: the owner needs one more `plan validate` round per hidden fault (no model call; stage 2's arrival checks catch config faults earlier on a Director run).
- Fix: gate the dry run on the earlier steps as now, but run the persona-name and environment-world checks regardless. For the environment-world check, test the world against the directory names under `worlds/`, or skip only the environments whose world failed to load. Otherwise record the ruling as an owner decision.

**M2. A `triggered` environment naming a missing ladder passes every lint of this task** (probe p4).
- `ladder: nope` on `mini_triggered` gives no fail. On `mini_scheduled`, `RunEnvironments.validate` refuses it ("world 'mini' has no ladder 'nope'").
- `run_experiment(dry_run=True)` builds no ladder for triggered gating, and `ladder_walk` walks the world's ladders, not the config's.
- The spec's `schema` rule is honoured to the letter: it delegates to `run --dry-run`, which has the same gap. Task 5's `dry_run`, which runs the cells, should catch it.
- Fix: add one closed set-relation clause to `schema`, "every `environments[*].ladder` is a `ladders/<name>.yaml` of its world", beside the world clause. Otherwise carry it to Task 5 as a named `dry_run` positive.

**M3. `schema`'s positives assert only that some schema result exists, not its reason, so two clauses survive deletion** (`tests/test_bundle_lints.py:171`, `:177`).
- `premise_terms: []` on mini also trips "drops ... recorded at the copy", so deleting `if not terms` (`bundle_lints.py:505`) leaves the suite green.
- `world: overlay` is refused by the dry run anyway, so deleting the environment-world loop (`:531-535`) leaves the suite green too.
- Probe p3 shows each clause does fire on its own:
  - `premise_terms: []` on a fresh second world gives "premise_terms is empty" only;
  - `overlay` gives "is no world under worlds/".
- Fix: pin a message substring for each schema positive, or add the fresh-world empty-terms case.

**M4. A persona's name is not tied to its file, so two persona files with one `name` pass `schema`** (`claude_bully/planner/bundle_lints.py:472`, `claude_bully/planner/bundle.py:322`).
- Probe p3: `personas/ferry_twin.yaml` beside `ferry_caller.yaml`, with the same `name:`, gives no fail. `bundle_personas` and `_load_files` keep the last file by sort order, and `plan_personas` registers only that one.
- A stem that differs from the name also passes. This mirrors `load_persona_sheets`.
- Fix: `schema` fails a duplicate persona name, naming both files. Optionally it also fails a name that differs from the stem.

**M5. `lint_bundle` run inside an open `plan_personas` block for a persona of the same name gives a false `schema` clash** (`claude_bully/planner/bundle_lints.py:524`).
- Probe p1 F: with beta's personas registered, `lint_bundle(beta)` fails with "persona 'quay_caller' is a registered strategy's name".
- The same happens after Task 10's `register_plan_personas` in the same process.
- This follows the spec's "read before any registration". No caller reaches it today, since stage 5 runs after stage 2's block closes and the CLI runs one command per process. It is a trap for Task 10 and 11 tests that run a bundle and then lint it.
- Fix: state the precondition in `lint_bundle`'s docstring and carry it to Task 10. Alternatively, skip a name whose registered class is a phased premise holding an equal sheet.

### Nits

- **N1.** `premise_terms: [" "]` passes the "non-empty" clause (probe p3, fresh second world), but `premise_words_pattern` returns None for it. Spec Minor 7 wants terms to match. Fix: test the stripped terms.
- **N2.** A case-only change (`gate log` to `Gate log`) fails as "drops gate log", though the premise pattern is case-insensitive. This is closed and strict, so leave it or casefold.
- **N3.** Messages:
  - "not a Experiment" and "not a ExpectedEvents";
  - a root-level type error reads "params: Input should be a valid dictionary" (`one_line` labels the root `params`);
  - a document's message repeats the path its `doc_id` already holds;
  - `premise_terms: []` on a reused world gives two results for one fault, against the ASSUMED "one fault is reported once".
- **N4.** `first_crumb_line` (mini's, unchanged) reads "That parking rota memo went round twice last week". It names the document its rung unlocks. 4a does not add it and no shape matches it, so it is the owner's prose call, recorded here because the good bundle is the base of 7b's stub bundle.
- **N5.** `manifest_complete` reads "its call" from `file:` purposes only. A `repair:<path>` call that errors is ignored, so carry the reading to 7b, which defines how a dropped document is recorded.

## Named risks

1. **Registry isolation: holds.**
   - Probe p1, in a fresh process:
     - 0 strategies at import, 2 after the fixture import;
     - `plan_personas` as the first registry touch gives 37 inside and 36 after, with `ferry_caller` gone;
     - two plans (`ferry_caller`, `quay_caller`) linted in sequence each pass, and neither persona is left behind.
   - Probe p1b:
     - an exception raised inside the registration loop, either before or after `register`, removes every entry and restores `captor` when a sheet had replaced it;
     - duplicate keys holding one sheet name register and remove once;
     - an exception in the body leaves the registry equal to its snapshot.
   - Both orders pass: `test_bundle_lints.py` then `test_cli.py`, and the reverse (79 passed each, `-W error -m "slow or not slow"`, outputs in `probes-task4a/order_*.txt`).
   - The `isolated_registry` copy is taken after `ensure_registered()`, so a lazy first load never lands in a discarded copy. `register` and `all_strategies` resolve the module global at call time, so they see the patched dict. No other module imports `_REGISTRY` by name (checked by grep).
   - The one hazard found is M5 (nesting with the same name).
2. **The good bundle against Q17 to Q21: holds.**
   - Q17: the manifest is committed in its own record write before the author stage, `record.manifest == GOOD_MANIFEST`, and the author calls follow it in order.
   - Q18: `DOCS[2]` is `pier-cafe-hours` (filler). Only `plan.json`, a transcript and the document itself contain its id. Dropping it as 7b does (error call, file gone, entry dropped) leaves no fail and only `GOOD_WARNINGS`. `harbour-works-ticket` is the seam document that links no buried one.
   - Q19: the buried ids are `night-gate-log` then `rota-overtime-sheet`.
   - Q21: the test asserts schema is empty on every non-schema case, and probe p3 saw no schema result on any non-schema case except a deleted `config.yaml`, which is expected.
   - Against base mini, the patched files differ only as Step 1 allows:
     - `the_log_line`;
     - the ladder's examples, plus one existing fires line changed to "Who is Dag Quenby?";
     - the canteen date;
     - the fare-notice url.
   - Mini holds 13 documents (2, 3, 2, 6).
   - Denylists (probe p5): boundary 0 hits, jailbreak 0, real names only `display_name: Claude` in `config.yaml` (the spare).
3. **Each lint: the rules match the spec.**
   - `schema`:
     - 13 of 16 fresh positives fail as expected; the other three are M4's two persona cases and N1's blank terms;
     - 9 of 9 fresh near-misses pass; the case-change row (N2) is counted separately;
     - 11 malformed files (an empty file, a list, broken YAML, a missing front-matter fence) each give a schema result naming the file, with no crash (probe p6).
   - `manifest_complete`: 5 of 5 fresh positives fail and 7 of 7 fresh near-misses pass.
   - `bully_line` on personas: 3 of 3 positives fail and 4 of 4 near-misses pass, including an annex term while no environment names annex, and a word-bounded `gatelog`.
   - The world-level wiring is correct, document ids are rewritten to bundle paths (probe p7), and the date near-miss passes.
   - Near-miss share in the suite: `schema` has 9 of 17, all real mutations. `manifest_complete` has 4 of 7 on paper and 1 of 7 in substance (I1). The world-level lints are 1 of 3 each, as the brief allows, since their full sets are Task 3's.
4. **Stopping at the first step: confirmed, and it does hide independent errors (M1).** The brief and spec say only that the model-needing lints go quiet while `schema` fails, which is honoured (`test_a_schema_failure_silences_the_lints_that_need_a_loaded_model`). Neither text asks `schema` itself to stop early.
5. **ASSUMED lines:** judged below.

## Reader-eye verdict on the added lines (spec section 14)

- `the_log_line`, "You were not supposed to see that. Nobody was.": it reacts as a slip after the target's find. It announces, advises and dares nothing, and names no place. Pass.
- The six `fallback_lines`: each reacts and names no document, path or place to look.
  - "My uncle never talked about his nights at the quay." leans toward the premise but only volunteers backstory.
  - All six pass.
- The ladder examples are target lines, so the rule does not apply to them.
- The seam memo naming `/var/log/harbour/notes/` is a document breadcrumb, not a bully line.
- Unchanged mini line: see N4.

## ASSUMED lines

1. **`config.yaml` through `Experiment.model_validate`: sound.** `load_experiment` (`config.py:135-138`) is exactly `yaml.safe_load` then `model_validate`.
2. **`config.yaml` and `expected.yaml` required: sound.** Both are fixed files (spec stage 2's manifest refusal), and a manifest-less bundle would otherwise pass.
3. **`schema` stops at the first failing step: partly sound.**
   - Sound for the dependent steps: the dry run needs everything loaded, and the environment-world check needs the loaded worlds.
   - Over-broad for the independent ones (M1).
   - The claim "one fault is reported once" is false for `premise_terms: []` on a reused world (N3).
   - "A persona that clashes is never registered over it" is true and worth keeping.
4. **"Its call" is the last `file:<path>` call across `record.stages`: sound for 4a.** Probe p3: error-then-ok-absent fails, and ok-then-error-absent passes. `repair:` calls are not considered (N5).
5. **A persona's name is its sheet's `name`: sound and consistent with `load_persona_sheets`.** But nothing ties it to the file, and duplicates pass (M4).
6. **"Every fires line opens its rung with mini's cast terms" read as the watcher's world terms: sound.** It matches spec section 9's `trigger_examples` (`world_terms=<cast names>`), and each fires line names a cast member.
7. **`hypotheses: [9]` on one Expectation: sound.** This is the plain reading.
8. **The three `manifest_complete` near-misses as assert-only changes: not sound.** They are negatives with preconditions, not near-misses (I1).
9. **`review_counts` zeros, `created_at` and stage times `now`: sound.** `plan.json` is in `HASH_EXCLUDES`, so the timestamps never reach `bundle_hash`.
10. **The `outlet_backing` cases add an `Outlet:` cast entry: sound.** Mini has no outlet cast entry, so without one the lint has nothing to read.

Also judged: the controller's ruling that the strategy count excludes `_` names. That is the `list-strategies` count, and both module orders pass.

## Probes (all under `probes-task4a/`)

| Probe | Covers |
| --- | --- |
| `p1_registry.py` | fresh-process registry, sequential plans, nesting (M5) |
| `p1b_registry_raise.py` | exceptions inside the registration loop, before and after `register`; restoring a replaced class; duplicate keys |
| `order_lints_then_cli.txt`, `order_cli_then_lints.txt` | the two modules in both orders |
| `p3_lint_cases.py`, `p3_out.txt` | 47 fresh cases per lint, 6 double-fault cases (M1), Q17 to Q19, dropping DOCS[2] |
| `p4_missing_ladder.py` | M2 |
| `p5_denylists.py` | boundary, jailbreak and real-name scan of the good bundle |
| `p6_malformed.py` | 11 malformed files, no crash |
| `p7_world_wiring.py` | `lint_world` and world-lint wiring, document-id rewriting |

Each p3 MISMATCH line is either a finding (M2, M4, N1, N2) or a probe input that was wrong, not a lint error: a persona named `control` (the control is registered as `polite_control`), and the far-date body text.
