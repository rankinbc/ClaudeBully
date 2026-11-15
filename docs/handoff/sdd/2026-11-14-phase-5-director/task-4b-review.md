# Task 4b review: the denylist, count and set-relation bundle lints

Reviewed: b54f2e1..6ca2946 (one commit, author rankinbc1@gmail.com). I read the diff once. I read code outside it only for the named risks, and each place is named below. The checkout was not changed. Probes are in `probes-task4b/`, and each one has its output beside it. I did not re-run the suite.

## Verdicts

- **Spec: PASS, with one deviation (I2).** All nine lints are present and in `BUNDLE_LINT_IDS` order. Each rule matches spec section 9 and the preflight rulings (Q21, Q24, Q61). The moved patterns are byte-identical. `SCHEMA_VERSION` is still 3. The coverage tests are verbatim from the brief. The 4a carry is done: 4b's bundles are in `_skip_bundles`. The deviation is in scope. Spec section 9 says `real_name_bundle` and `boundary_bundle` read "every file under `worlds/` and `personas/`", and `reserved_hosts` reads "a bundle world or persona file". The code reads only grammar paths under those directories.
- **Quality: NEEDS FIXES.** There are three Important findings. Two are gaps in what the text scans read (I2, I3). The third is a self-reference in the jailbreak scope that will keep a bundle from ever reaching `runnable` once Task 9 records lint results (I1).

Counts: Critical 0, Important 3, Minor 3, Nit 4.

## What was verified

- **Named risk 1 (regex lines).** `probes-task4b/p1_pattern_bytes.py` slices each definition out of `git show b54f2e1:tests/test_real_names.py` and out of `git show 6ca2946:claude_bully/planner/bundle_lints.py`. `RESERVED_TLDS`, `URL_HOST`, `EMAIL_DOMAIN`, `PUBLIC_HOST` and `PROVIDER_VALUE` are EQUAL byte for byte, comments included. None of the five is still defined in `tests/test_real_names.py`, which imports them: one copy, not two. `bundle_lints.py`, `tests/test_real_names.py` and `tests/test_bundle_lints.py` hold no control byte and no CR. A `git grep` for the pattern texts finds them only in `bundle_lints.py`. Nothing was copied.
- **The denylists are reused, not copied.** The lints read `planner/lints.load_patterns` on `REAL_NAMES_PATH`, `BOUNDARY_PATH` and `data/jailbreak_denylist.txt`. The fixtures check each near-miss text against the same lists before writing it (`_clean_append`, `_host_free`). `load_patterns` and `tests/test_guardrails.load_denylist` compile the lists the same way (one `IGNORECASE` regex per non-comment line). See N3 for one cosmetic difference.
- **Q61.** I counted `CASES_4B` from the diff:

  | Lint | Near-misses of cases |
  | --- | --- |
  | `real_name_bundle` | 6 of 11 |
  | `reserved_hosts` | 6 of 10 |
  | `boundary_bundle` | 6 of 11 |
  | `jailbreak_bundle` | 6 of 11 |
  | `no_values_expectation` | 4 of 7 |
  | `anchor_floor` | 3 of 5 |
  | `expected_schema` | 7 of 13 |
  | `control_presence` | 3 of 5 |
  | `budget` | 5 of 9 |

  Every near-miss is a change to the bundle: a file edit, a new file, or a `plan.json` request edit. No positive was dropped and no test was loosened.
- **Q21 guard.** Every non-schema case asserts that `schema` reports nothing, except `VALUES_HELD`. That case asserts that `schema` fails on `expected.yaml`'s event field and on nothing else. Every 4b positive pins its exact fail results (`POSITIVE_REASONS`).
- **`expected_schema`'s reading.** `probes-task4b/p3_eventtypes.py` shows that the `EventType` values with no `DETECTORS` entry are exactly the 9 of `PENDING_DETECTORS`. Membership of `DETECTORS` therefore equals the spec's "an `EventType` with a detector".
- **Commit.** The author is rankinbc1@gmail.com. `SCHEMA_VERSION` is 3 (`enums.py:13`). The one real-name hit in the commit's added non-test lines is `provider: anthropic` in a code comment. That is the provider kind, which the config spare spares by design.

## Findings

### Important

**I1. `jailbreak_bundle` reads `plan.json` whole, and `plan.json` holds the harness's own lint records. One recorded hit makes the bundle fail for good.** `claude_bully/planner/bundle_lints.py:913-927`.

Plan Task 9's `Director.validate()` writes `record.lint_results = [LintRecord.of(r) for r in results]` into `plan.json`. Each record carries `lint_id="jailbreak_bundle"`, the message, and the phrase as its `span`. The probe is `probes-task4b/p4_jailbreak_self_reference.py`, which runs that loop without the dry run:
1. A clean bundle: no fail.
2. A phrase planted in a body: one fail, on the body.
3. The body fixed, then validated again: two fails on `plan.json`. One is the old phrase, from the stored span and message. The other is `jailbreak`, from the stored lint id itself, because `\bjailbreak` matches `jailbreak_bundle`.
4. Validated a third time: the same two fails. Each validate records the result again.

So once any `jailbreak_bundle` result has been recorded, no later `plan validate` can reach `runnable` unless someone edits `plan.json` by hand. `review.md` carries a smaller form of the same hazard: the reviewer is told to quote the exact text of a problem, so a quoted phrase stays after the planner fixes the file.

This comes from Q24's ruling ("every file under the bundle root but transcripts/ ..."). It is latent until Task 9, but cheapest to settle now.

- **Fix (needs a ruling):** scan `plan.json` through `bundle.read_record()`, using `record.request.model_dump_json()` (the question and the constraints, Q24's stated intent), not its raw bytes. Leave the harness-written fields (`lint_results`, `stages[*].calls[*].error`, `DirectorAttempt.lint_failures`, `dry_run`) out.
- Add a test: plant the phrase, record the results, fix the file, lint again, expect no fail.
- Decide `review.md` in the same ruling. Either keep it, and accept that a re-review is needed to clear a quoted phrase, or scan only its responses.

**I2. Files outside the bundle grammar are invisible to `real_name_bundle`, `boundary_bundle` and `reserved_hosts`, though the run reads them.** `bundle_lints.py:831-833` (`_world_and_persona_files` lists only `bundle.index()`, which holds grammar paths only), used at `:847`, `:868` and `:897`.

- `load_world` globs `corpus/*.md` and `ladders/*.yaml` (`environments/world.py:342` and `:353`).
- `bundle_personas` globs `personas/*.yaml` (`planner/bundle.py:330`). It is the loader that Task 5's dry run and the run on a bundle use.
- `schema` and `manifest_complete` also read only `bundle.index()` (4a), so nothing else catches these files.

The probe is `probes-task4b/p3_counts_and_sets.py`, part (a). Each case below gives no fail from any of the four lints named, and `schema` and `manifest_complete` report nothing:

- **`personas/zz.caller.yaml`.** It is a copy of the persona with "reads Reuters, refuses rules" in its backstory and the same `name`. `bundle_personas(b)["ferry_caller"]` returns this file over the grammar file, because it sorts later. `lint_bundle` reports no fail at all. A person keeping a backup copy (`ferry_caller.v2.yaml`) creates exactly this case.
- **`worlds/mini/corpus/Pier-Cafe-Extra.md`.** A capital stem, served by `load_world`, with `url: https://pennetferry.com/cafe`. `reserved_hosts` misses it. Phase 3's `real_name` caught only the body's name.
- **`worlds/mini/ladders/Extra.yaml`.** The triggered environment names it. A real name and a Boundary word in it pass.

The fix:
- Make `_world_and_persona_files` list every file under `worlds/` and `personas/` (an `rglob`, as `_jailbreak_bundle` already does), which is the spec's wording.
- Have `manifest_complete` (or `schema`) fail any file under `worlds/` or `personas/` that is outside the grammar. The run should never read a file the Director could not have written.
- Add one positive per lint, with a non-grammar persona and a non-grammar document.

**I3. The text scans read raw YAML, so a name or phrase wrapped across a line of a folded scalar passes. The bully reads the joined value.** `bundle_lints.py:847-861`, `:897-910` and `:913-927`.

The persona's prose fields are `>-` folded scalars. The planner writes them wrapped at about 95 columns, as the good bundle's are. The probe is `probes-task4b/p6_folded_yaml.py`. It writes "Bill / Gates", "safety / training" and "ignore all previous / instructions" across a wrap in the backstory. In each case the loaded `backstory` holds the joined phrase, and `real_name_bundle`, `boundary_bundle` and `jailbreak_bundle` return nothing (3 of 3 missed).

`tests/test_guardrails.py:test_no_denylisted_text_in_data` already scans loaded persona fields as well as raw text, so the repository has the precedent.

- **Fix:** scan each text twice, as written and with `re.sub(r"\s+", " ", text)`, reporting a pattern once. That stays closed and still covers comments.
- Alternatively, also scan the loaded strings of each YAML file.
- Add one positive per lint with the phrase across a folded wrap.

### Minor

**M1. `reserved_hosts` fails a reserved URL followed by punctuation, a query or a fragment.** `bundle_lints.py:881`.

`URL_HOST`'s capture class stops at `/`, whitespace, `)`, `]`, `>`, quotes and backtick only. In the probe (`p2_denylist_scans.py`), all four of these fail as "not under .example, .test, .invalid":
- `See https://pennetferry.example.` gives `'pennetferry.example.'`;
- `See https://pennetferry.example, then.` gives `'pennetferry.example,'`;
- `https://pennetferry.example?day=1`;
- `https://pennetferry.example#hours`.

A planner's prose will put a URL at a sentence's end. The pattern must stay unchanged in text (D-scans). The fix:
- Normalize after the capture: cut at the first `?` or `#`, then `rstrip(".,;:!")`, then drop the port.
- Put that in one helper, for example `url_hosts(text)`, that `tests/test_real_names.py:421` also calls.
- Add two near-misses: a sentence-end URL and a URL with a query.

**M2 (named risk 4). The `max_calls` clause does not conflict in code, but Task 5's text still says it builds the clause.**

- The plan's Task 5 lists, under Files, "`bundle_lints.py` (the `dry_run` lint, `budget`'s `max_calls` clause)".
- Its last paragraph says "`budget`'s `max_calls`: the sum of `estimated_calls` at most `max_calls`."
- The clause now exists at `bundle_lints.py:1036-1042`. It matches D-lint_bundle: it reports nothing with `dry_run=None`.

A Task 5 implementer who follows the plan literally may add a second clause. That would give two fail results per overrun, and `test_the_max_calls_clause_reads_the_dry_runs_estimate` pins exactly one.

- **Fix:** add a line to Task 5's brief saying the clause exists (`_budget`, its test at 39, 40 and 41 calls) and that Task 5 only feeds it real `DryRunCell`s through `lint_bundle(bundle, dry_run=cells)`, with one end-to-end case.
- Also, `dry_run=[]` with `max_calls` set passes (a sum of 0). That is harmless only if Task 5's `dry_run` lint fails an empty dry run. Say so in the same note.

**M3 (named risk 5). The test file's 2.5 minutes is not mostly repeated fixture setup that a module-scoped fixture would remove.** The probe is `probes-task4b/p5_timing.py`, warm, mean of 20:

| Step | Time |
| --- | --- |
| `good_bundle()` | 220 to 284 ms |
| A `copytree` of one prebuilt bundle | 74 ms |
| `lint_bundle()` | 226 ms |
| of which `_schema`, the dry run included | 61 ms |
| of which the four text scans and `no_values_expectation` | 127 to 157 ms |
| of which the world lints | 20 ms |
| of which the set lints | 6 ms |

Inside the scans, the regex work itself is about 24 ms. The rest is `bundle.index()` (7.6 ms, sha256 of every file), called about eight times per `lint_bundle`, plus each scan re-reading the same files and re-reading the denylists.

A module-scoped fixture cannot be shared as-is, because every case mutates the bundle. Two changes together should cut the file to about half:
1. Keep a module-scoped prebuilt good bundle and copy it per test, saving about 150 to 200 ms per test.
2. Read `index()` and the file texts once per `lint_bundle` and pass them to the scans, and cache `load_patterns` per path. This saves about 80 ms per test, and the Director's own validate gets the same saving.

No single test is over two seconds, so no `slow` mark is owed.

### Nit

**N1. Residuals of the shared lists, not of this lint.** These are for the list owner, recorded so they are known:
- `real_names.txt` misses a name fused into a compound host (`reutersnews.example`), a double space, a line break, and a zero-width space.
- `boundary.txt` misses `unrestricted` and `disallowed`, because the leading `\b` fails after a prefix.
- `jailbreak_denylist.txt` misses a double space or a line break inside a phrase, including a constraint holding `\n`, which `plan.json` writes as a literal backslash-n. It also fails "The developer modelled the tides." (`developer mode` has no trailing `\b`) and "The bypass filters were cleaned."

The CI scans share all of these.

**N2. A pre-existing copy of the spare.** `tests/test_real_names.py:306` still has its own copy of the display-name substitution (`_exempted` spare). `bundle_lints._spare_names` (`:480`) is the same expression. Calling it would leave one copy.

**N3. A cosmetic difference between the two loaders.** `load_denylist` (`tests/test_guardrails.py:17-21`) tests `startswith("#")` on the unstripped line, while `load_patterns` tests it on the stripped one. No list line starts with whitespace and then `#` today (checked), so both load the same patterns.

**N4. Three probed boundaries pass as the spec reads, and no case pins them.** `expected_schema` passes `hypotheses: []` and a cell with `rungs: {}`, and it fails `cells: {}` only through "no expectation is marked likely_wrong". A near-miss pinning the first two would document the reading.

## Probes

All are in `probes-task4b/`. Each `*_output.txt` holds its run.

- **`p1_pattern_bytes.py`: named risk 1.** All five patterns are byte-equal to b54f2e1's, there is one copy, and there are no control bytes.
- **`p2_denylist_scans.py`: named risk 2.** This is an adversarial set of 92 cases over the four scans, each a change to a fresh good bundle, calling the scan directly. The rates describe this adversarial set, not a corpus.

  | Lint | TP | FN | FP | TN | Precision | Recall |
  | --- | --- | --- | --- | --- | --- | --- |
  | `real_name_bundle` | 11 | 6 | 0 | 11 | 1.00 | 0.65 |
  | `reserved_hosts` | 9 | 3 | 6 | 6 | 0.60 | 0.75 |
  | `boundary_bundle` | 7 | 3 | 0 | 10 | 1.00 | 0.70 |
  | `jailbreak_bundle` | 9 | 3 | 2 | 6 | 0.82 | 0.75 |

  - `real_name_bundle`:
    - It caught odd casing (`REUTERS`, `rEuTeRs`, `bill gates`, `GPT-4O`), names in reserved URL hosts and paths, ladder, sheet, config and `expected.yaml` comments, and a bully `display_name: Reuters`.
    - It spared `Claudette`, `Amazonian`, `Applegate`, `Bingley`, `Mitre`, `Uberti`, "on the verge of tears" and `Gemini-Ridge`.
    - Misses, quoted:
      - "outlet fused into a compound host (reutersnews)";
      - "person split across a line break";
      - "person with a double space";
      - "zero-width space inside an outlet";
      - "outlet in a ladder file outside the grammar (capital stem; load_world globs it)";
      - "outlet in a persona file outside the grammar (bundle_personas globs it)".

      The last two are I2. The first four are N1.
  - `reserved_hosts`:
    - Misses, quoted:
      - "bare host on an unlisted suffix (.de; the residual)";
      - "scheme-relative url on .ru (the residual)";
      - "public url in config.yaml (outside the spec's files)".

      The first two are R-bare-host's pinned residual. The third is outside spec scope.
    - False positives, quoted:
      - "reserved url at a sentence end";
      - "reserved url before a comma";
      - "reserved url with a query";
      - "reserved url with a fragment";
      - "a file name ending .info (a listed suffix)";
      - "a reserved url whose path ends in .us".

      The first four are M1. The last two are R-bare-host's deny-list cost.
  - `boundary_bundle`:
    - It caught upper case, singulars, the backstory, sheet, config and ladder comments, and `restricted`.
    - It spared `rule out`, `ruled out`, `ruler`, `unruly`, `allowance`, `realigned`, `rules_board` and `permission`.
    - Misses, quoted:
      - "unrestricted (a prefix defeats the leading \b)";
      - "disallowed (a prefix)";
      - "a Boundary word in a ladder file outside the grammar".

      The first two are N1. The third is I2.
  - `jailbreak_bundle`:
    - It caught upper case; `ledger.jsonl`, `dryrun.jsonl`, `.attempt.json`, a stray root file, `plan.json`'s question, and `worlds/mini/transcripts/` (only the top-level `transcripts/` is exempt).
    - It spared `transcripts/`, `dryrun/` and `state/`.
    - Misses, quoted:
      - "double space inside the phrase (list residual)";
      - "line break inside the phrase (list residual)";
      - "a constraint holding a line break, in plan.json (JSON writes \n)".
    - False positives, quoted:
      - "the developer modelled the tides";
      - "the bypass filters were cleaned".

      All five are N1.
- **`p3_counts_and_sets.py`: named risk 3, plus I2's part (a).** All of these behave as the spec states:
  - `anchor_floor`: 19 documents fail ("has 19 documents, under 20") and 20 pass.
  - `budget`:
    - `turn_budget` 18 passes and 19 fails;
    - `repetitions` 3 passes and 4 fails;
    - `max_cells` 4 against 4 cells passes and 3 fails;
    - `max_calls` 40 against 40 calls passes;
    - `max_calls` None with 10**6 calls passes;
    - `max_calls` 1 with `dry_run=[]` passes (M2).
  - `expected_schema`:
    - hypothesis ids 1 and 15 pass, and 0 and 16 fail;
    - `[]` passes;
    - `cells: {}` fails on `likely_wrong` only;
    - a control cell's rung passes;
    - `history_dug` (pending) fails.
  - `control_presence`:
    - explicit with a control for one environment fails the other cell only;
    - explicit with controls at the wrong seeding fails both;
    - explicit with matching controls passes.
- **`p3_eventtypes.py`:** `DETECTORS` covers exactly `EventType` minus the 9 pending detectors.
- **`p4_jailbreak_self_reference.py`:** I1.
- **`p5_timing.py`:** M3.
- **`p6_folded_yaml.py`:** I3.

## The ASSUMED decisions

1. **A fresh world for `anchor_floor` is a bundle world with no `base_worlds` entry, whatever the request's `world` says.** Accept. D-copy gives every reused world an entry, and spec section 5 says "a fresh world starts empty". A world the planner adds under `world: reuse` is a fresh world and should meet the floor. This reading is stricter than stage 2's manifest check, which keys on the request, and it is the safer of the two. The third near-miss pins it.
2. **The four text scans and `no_values_expectation` run even when `schema` fails.** Accept. D-lint_bundle silences only the lints that need a loaded model, and reporting every independent fault is 4a's M1 rule.
3. **The `values_held` near-miss stays, against the Q21 guard.** Accept. It is the brief's own row. `no_values_expectation` is a text scan that runs whatever `schema` found, so it passes for the right reason (no such text). The exception is named and asserted narrowly: `schema` fails on `expected.yaml`'s event field only. Note that without it, `no_values_expectation` would sit at 3 of 6, so the majority leans on this row.
4. **`jailbreak_bundle` gains a fourth positive, and three near-misses for 6 of 11.** Accept. This is Q24's positive, and Q61's arithmetic redone correctly. The scope this ruling chose is what I1 is about.
5. **`control_presence`'s "controls: auto (the good bundle)" near-miss is replaced by a third condition at `seeding_turns: 2`.** Accept. The good bundle is already the negative, and the replacement exercises auto's construction on a new shape. One check under both modes is the spec's rule restated.
6. **`budget`'s `max_cells: 4` near-miss is made real as 6 cells against 6.** Accept.
7. **`anchor_floor`'s "world: reuse with 13 documents" is made real as reuse with `base_world: None`.** Accept, but it is weak. It changes only `plan.json` bytes the lint never reads, so it mostly restates the negative. A stronger near-miss would be a reused world patched down to fewer documents (13 minus a removed filler, with its manifest entry), which still passes because it has a base entry.
8. **`budget`'s `max_calls` clause is built here.** Accept. It is the brief's Step 3 and D-lint_bundle. See M2 for the note Task 5's brief needs.
9. **`expected_schema`'s detector reading is membership of `DETECTORS`, and an unknown cell's rungs go unchecked.** Accept. `p3_eventtypes.py` shows it equals the spec's reading. An unknown cell already fails, and its events and hypotheses are still checked.
10. **docs/08 gets four new rows rather than one.** Accept.
11. **`anchor_floor` runs after the per-world lints.** Accept. Nothing reads the order of the results.
