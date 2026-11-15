# Task 4b re-review, fix round 1

Scope: 6ca2946..8ec2485 (one commit, `review-6ca2946..8ec2485.diff`, read once). Read-only: the checkout is unchanged (`git status` clean). Probes are in `probes-task4b-rereview/`, each with its output beside it (`*_output.txt`). The review's probes were re-run on the new code; two of them call private functions whose signatures changed (`_View`, `_jailbreak_bundle(view, record)`), so the copies are `p2r_`, `p3r_`, `p4r_` and `p6r_`, changed only by that wrapper. I did not run the full suite. I ran `tests/test_real_names.py` (85 passed) and 39 selected tests of `tests/test_bundle_lints.py` (passed).

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| I1 (plan.json self-reference) | ADDRESSED for the harness's own records, with one residual (R1 below, Important by effect) | p4: step 3 and step 4 give `jailbreak_bundle -> []` (was two fails on `plan.json`, in both steps). `plan.json`'s request is still scanned (the constraint-with-line-break case is a true positive). The new test bites: with `_HARNESS_RECORDS` emptied, `test_a_recorded_jailbreak_hit_never_fails_a_later_validate` fails (p13, M1). |
| I2 (files outside the grammar) | ADDRESSED | p3a: all three cases now fail `schema` ("outside the bundle's path grammar") and the scan that matters: `zz.caller.yaml` gives real_name_bundle `Reuters` and boundary_bundle `rules`, `refuses`; `Pier-Cafe-Extra.md` gives real_name_bundle `Reuters` and reserved_hosts `pennetferry.com`; `Extra.yaml` gives real_name_bundle `Reuters` and boundary_bundle `guidelines`. All 76 files of `data/worlds` and `tests/fixtures/worlds` match the grammar (p10 c), so a reused base world does not trip the new schema clause. |
| I3 (folded and wrapped text) | ADDRESSED | p6: 3 of 3 caught (was 0 of 3). p11: 8 of 9 YAML spellings caught, where the raw text hits none of the 8: `\x74` escape, ` `, `\n` escape, a line continuation, a multi-line flow value, a literal block, a tab, an NBSP. The 9th, a zero-width space, is the known list residual (the loaded value does not hold the phrase either). The parsed-values text is what catches the escapes, so it earns its place beside the collapsed text. With `_scan_texts` reverted to raw only, the real_name positive fails (p13, M2). |
| M1 (reserved URL with punctuation) | ADDRESSED | 92-case probe: the four false positives (sentence end, comma, query, fragment) are gone. p9: over 28 hosts the new verdict is right on 28; it is stricter on `https://pennetferry.com?.example` and `...#.example` (the old reading let the reserved-looking tail hide the public host). |
| M2 (Task 5's max_calls text) | CARRIED, not in the diff | `progress.md` has "carry to Task 5: budget's max_calls clause already exists". The second half of the review's note (`dry_run=[]` with `max_calls` set passes, harmless only if Task 5's `dry_run` lint fails an empty dry run) is not in the carry. The plan's Task 5 text is unchanged. |
| M3 (repeated reads) | ADDRESSED | p5r: `lint_bundle` 145 ms warm, mean of 20 (was 226). One `Bundle.index()` per call, `Bundle.read_file` once per path, raw reads at most twice per path (the index hash and one read). The report's near-miss shares recount exactly from `CASES` (p12): schema 19/37, real_name_bundle 9/17, reserved_hosts 10/15, boundary_bundle 7/13, jailbreak_bundle 10/19. |

## 1. The review's probes, re-run

p3a, p4 and p6 are in the verdict table above (I2, I1, I3). The 92-case probe follows.

**The 92-case denylist probe** (`p2r_denylist_scans.py`, same cases and labels as `p2`):

| Lint | TP | FN | FP | TN | Precision | Recall | Was |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `real_name_bundle` | 15 | 2 | 0 | 11 | 1.00 | 0.88 | 1.00 / 0.65 |
| `reserved_hosts` | 9 | 3 | 2 | 10 | 0.82 | 0.75 | 0.60 / 0.75 |
| `boundary_bundle` | 8 | 2 | 0 | 10 | 1.00 | 0.80 | 1.00 / 0.70 |
| `jailbreak_bundle` | 9 | 3 | 2 | 6 | 0.82 | 0.75 | 0.82 / 0.75 |

- `real_name_bundle`: the four fixed misses are the line break, the double space and the two off-grammar files. Left: a name fused into a compound host, and a zero-width space (both list residuals the report names).
- `reserved_hosts`: the four fixed false positives are the M1 cases. Left: `.de` and a scheme-relative `.ru` (R-bare-host), a public URL in `config.yaml` (outside the spec's files), and the two deny-list false positives (`hours.info`, a path ending `.us`).
- `boundary_bundle`: fixed are the folded wrap and the off-grammar ladder. Left: `unrestricted` and `disallowed` (the list's leading `\b`).
- `jailbreak_bundle`: the identical 9/3/2/6 hides a swap. The three old misses (double space, line break, a constraint with a line break) are now caught. The three new "misses" are `ledger.jsonl`, `dryrun.jsonl` and `.attempt.json`, which the I1 ruling took out of scope on purpose. Relabelled as must-pass, as the ruling reads, the set is TP 9, FN 0, FP 2, TN 9: precision 0.82, recall 1.00. The two false positives are the list's (`developer modelled`, `bypass filters`), unchanged.

## 2. Collapsed text instead of raw: does any pattern lose a match?

Reading the code first: `reserved_hosts` does not read the collapsed text at all. It reads the raw text (`bundle_lints.py:996`). Its three patterns (`URL_HOST`, `EMAIL_DOMAIN`, `PUBLIC_HOST`) stop at whitespace or hold none, so nothing there depends on a newline. `PROVIDER_VALUE` (the config spare) uses `\s*`, which spans a newline and a space alike.

The three lists hold 186 patterns. None anchors on a newline or a line start: no `^`, `$`, `\A`, `\Z`, `(?m)`, `\n` or `\s` in any pattern line (grepped; `load_patterns` compiles with `IGNORECASE` only). Three patterns read what follows them with a negative lookahead:

| Pattern | File:line |
| --- | --- |
| `\bthe verge\b(?! of\b)` | `data/denylists/real_names.txt:49` |
| `\brules?(?! out\b)\b` | `data/denylists/boundary.txt:8` |
| `\bgemini\b(?!-[a-z])` | `data/denylists/real_names.txt:72` |

`p7_collapse_differential.py` builds samples that match every pattern, puts each in 8 line-break contexts and 3+ wraps, as a `.md` body and as a YAML scalar, and compares the raw search with what `_scan_texts` gives the lints: 186 patterns, 6,276 cases.

- **Loss (raw caught, the scans do not): 3 distinct cases, all of the two lookaheads.** `the verge` then a line break then `of` (both `the verge\nof tears` and a heading `# the verge`, a blank line, then `Of the rest`), and `rule` then a line break then `out`. Gemini loses nothing (collapsed `gemini -x` still matches).
- **Gain (the scans catch, raw did not): 1,620 cases, every one a wrap.** No other context changed. That is the intended join.
- Over the real files (153 under `data/worlds`, `data/personas`, `tests/fixtures`) against all 186 patterns: 0 differences (`p7b`).
- End to end through the lints: "Source: The Verge" then a line, then "Of the three outlets" passes `real_name_bundle` (raw failed it); "The house rule" then a line, then "Out of hours" passes `boundary_bundle` (raw failed it).

So the report's ASSUMED line, "collapsing keeps every non-whitespace character, so it catches everything the raw text did", is false for those two patterns. The spare is the list's own design (the same words on one line are spared), so a wrapped line reads as the list reads it. But a heading or a source line ending `The Verge`, followed by a paragraph that opens with "Of", loses a true positive that a blank line should have kept apart. Graded Minor (M-A below). A cheap refinement, tested in `p14`: collapse each blank-line-separated paragraph on its own and join paragraphs with a newline. It keeps every pinned spare (`verge\nof tears`, `rule\nout`), restores the two heading-then-paragraph hits, and keeps the wrap gains.

Two other places the collapse could bite and did not: a join across structural lines gave no gain beyond wraps (the contexts "line start", "line end", "own line" all agree with raw), and the collapsed text keeps every non-whitespace character, so `\b` edges are unchanged.

## 3. review.md in the jailbreak scope

Yes, it keeps the bundle failing, and the report's reason ("a quoted phrase is cleared by the next review round") is wrong in the case that matters.

`p8_review_md_quote.py`, following the spec's stages (stage 3 renders `review.md` with the quote, stage 4 fixes the file, stage 5 runs `lint_bundle`):

| Step | `jailbreak_bundle` |
| --- | --- |
| A. stage 3 done, file still bad | `review.md` (two fails) and the body |
| B. stage 4 fixed the file, stage 5 validate | `review.md` only: the quoted phrase and `jailbreak` |
| C, D. `plan validate` again, twice | the same two fails, unchanged |
| E. `plan review` rewrote `review.md` on the fixed bundle | clean |
| G. the same phrase quoted in `plan.md` | `plan.md` fails |

- The spec's stage order (`design.md`, "Stage 5, validate"; "The commands' reach") puts stage 5 after stage 4 in the same run, and `plan validate` reruns stage 5 only. So `review.md` from stage 3 is still on disk at the first stage 5: a plan whose reviewer blocked a jailbreak phrase, and whose planner fixed it, ends `validated`, not `runnable`, and only `plan review` (three more stages, reviewer calls) clears it. It is not forever (E), so it is a smaller shape than I1, but `plan validate` cannot clear it.
- The quote is not the only trigger. The reviewer's own prose names the class: docs/08 lists "a rung whose natural endpoint is a jailbreak" among its named checks, and `\bjailbreak` matches that word with no phrase quoted. My B-D probe's `review.md` fails on `jailbreak` as well as on the quoted phrase. So any `block`, `fix` or `note` about the one class this lint exists for demotes the run.
- This lands on the spec's own bars (spec line 439: "the plan ends `runnable`", and the reviewer's blocks on a seeded bad bundle): a seeded jailbreak phrase is exactly a reviewer blocking a planted phrase, then a planner fix.

**Recommendation: exclude `review.md` from `jailbreak_bundle`, whole file** (add it to the set at `bundle_lints.py:942`, or a sibling `_QUOTING = {"review.md"}`). Reasons:
1. It is the rule the sibling scans already use: `real_name_bundle` exempts `plan.md`, `review.md` and `transcripts/` "since they quote", and `boundary_bundle` reads none of them. Only `jailbreak_bundle` reads `review.md`.
2. It loses no coverage a run could meet. A block's quote must be text of the file at review time (spec stage 3), so the phrase is still scanned in its source file for as long as it is there. A run reads `worlds/`, `personas/`, `config.yaml`; no run reads `review.md`.
3. Field-level exclusion, the way `plan.json` was done, is not possible: `review.md` is rendered text with no fields. Excluding the file is the equivalent.
4. The in-flight versus committed split already exists for real names: spec section 12 has the CI scan of a checked-in bundle read `review.md` whole. Task 12's scan can read it for the jailbreak list the same way (spec line 401 says the jailbreak scan covers `plans/`), so a committed bundle that quotes a phrase still gets caught at commit time.

What it changes: `tests/test_bundle_lints.py:680-683` pins the opposite (a positive: `_append("review.md", ...)` fails). It becomes a near-miss, so the jailbreak share goes from 10 of 19 to 11 of 19. Add a test shaped like the I1 one: plant a phrase, write `review.md` with the quote and the word "jailbreak" in its prose, fix the file, lint three times, expect clean. Keep `plan.md` in scope: the planner writes it and stage 4 can revise it (it is in the `plan` review group), so it has no I1 shape (G fails until revised, which is right).

This needs the controller's ruling because Q24 ("every file under the bundle root but `transcripts/`...") chose the scope and `jailbreak_bundle`'s positive was written to it.

## 4. `url_hosts` in tests/test_real_names.py

Coverage kept. `p9_url_hosts_coverage.py`:
- Over 162 files (`data/worlds`, `data/personas`, `tests/fixtures`), 113 URL hosts: the old test fails 0 and the new fails 0, and no file's verdict differs.
- Over 28 constructed hosts the new verdict is right on all 28. It differs from the old reading in six places, all for the better: four reserved hosts followed by `.`, `,`, `?` or `#` no longer fail; two public hosts that hid behind a reserved-looking tail (`?.example`, `#.example`) now fail.
- The project-wide real-name scan itself (the denylist scan over `data/worlds`, `data/personas`, `tests/fixtures/worlds`, `tests/fixtures/bundles`) does not call `url_hosts`. The diff touches only the world-address test (`tests/test_real_names.py:421`, `hosts = {h for text in texts for h in url_hosts(text)}`). The `assert hosts` guard is intact, so the test still cannot pass on an empty set. The module's 85 tests pass.
- `url_hosts` leaves `URL_HOST`'s text unchanged (`bundle_lints.py:448`), and the test's `host.split(":")[0]` is now redundant but harmless.

## New breakage, by severity

### Important

**R1. `review.md` stays in `jailbreak_bundle`'s scope (I1's open half).** `bundle_lints.py:939-942` (the exemption set holds `plan.json`, `.attempt.json`, `ledger.jsonl`, `dryrun.jsonl`, not `review.md`) and the loop at `:1029-1048`. Section 3 has the probe and the recommendation. Graded Important by effect, as 4a's ladder minor was: a plan the planner fixed ends `validated`, and `plan validate` cannot clear it. The review marked this "decide in the same ruling"; the ruling did not, and the report kept it by default.

### Minor

**M-A. Collapsing replaces the raw scan, and two lookaheads lose a true positive across a paragraph break.** `bundle_lints.py:518-553` (`_collapse`, `_scan_texts`), patterns at `real_names.txt:49` and `boundary.txt:8`. Section 2. Fix: collapse per paragraph (`p14`). The pinned near-miss at `tests/test_bundle_lints.py:863` ("rule" then "out" across a wrap) stays green under the refinement; add the heading-then-paragraph positive beside it. The fix report's ASSUMED sentence should say "except across a paragraph break" or the refinement should land.

### Nit

**N-1. The off-grammar schema failure is stricter than its message and hides the world lints.** `bundle_lints.py:705-710`. The message says "though a loader reads every file here". No loader reads `.DS_Store`, `Thumbs.db`, `desktop.ini`, `.gitkeep` or a `notes.txt` beside a world (`load_world` globs `corpus/*.md` and `ladders/*.yaml`, `bundle_personas` `personas/*.yaml`), yet each fails `schema` for good (p10 d, four of four). It is the controller's own ruling ("a file there outside the grammar fails schema"), so the severity is the wording and the lost detail: because `schema` fails, `loaded` is None, so the Phase 3 world lints report nothing for the whole bundle while the file stays. In p3a's `Pier-Cafe-Extra.md` case the old run also showed `real_name` and `no_duplicate_fact` on it; the new run shows the three fails above and nothing else. Reword ("outside the grammar; the loaders glob this folder") or limit the fail to what the globs read.

**N-2. A non-UTF-8 byte in `plan.md` or `review.md` now raises out of `lint_bundle`.** `bundle_lints.py:581-590` (`_View.read_file` goes through `Bundle.read_file`, `bundle.py:226`, which decodes strictly) where 6ca2946's `_jailbreak_bundle` read those two files with `errors="replace"`. p10 b: `UnicodeDecodeError` for `plan.md` and `review.md`. A persona, config, expected file or world file with such a byte already raised at 6ca2946 (`real_name_bundle` read them strictly). A cp1252 hand edit of `plan.md` fails the stage-1 adoption first, so this is unlikely to be reached.

**N-3. Not tested: a link under `worlds/` or `personas/`.** The widened scan reads non-grammar files with `Path.read_bytes` (`bundle_lints.py:585-590`), which follows a link where `Bundle.read_file` refuses one. This host refuses to create a symlink (WinError 1314), so I could not run it. It reads only, and `schema` fails the file anyway.

**N-4. The M2 carry lacks the second half.** See the table.

## Probes in `probes-task4b-rereview/`

- `p2r_denylist_scans.py`, `p3r_counts_and_sets.py`, `p4r_jailbreak_self_reference.py`, `p6r_folded_yaml.py`: the review's probes on the new code.
- `p5r_timing_and_reads.py`: M3.
- `p7_collapse_differential.py`, `p7b_real_files_and_lost_cases.py`: section 2.
- `p8_review_md_quote.py`: section 3.
- `p9_url_hosts_coverage.py`: section 4.
- `p10_new_breakage.py`: N-1 to N-3 and the base-world grammar check.
- `p11_yaml_forms.py`: I3 beyond the fixture.
- `p12_share_count.py`: the near-miss recount.
- `p13_mutations.py`: the two new tests bite.
- `p14_paragraph_collapse.py`: the refinement for M-A.
