# Task 4b re-review, fix round 2

Scope: 8ec2485..dff6e26 (one commit, `review-8ec2485..dff6e26.diff`, read once). Read-only: the checkout is unchanged (`git status` clean before and after). Probes are in `probes-task4b-rereview2/`, each with its output beside it (`*_output.txt`). The round-1 probes were re-run unchanged (`_View(bundle)` and `_jailbreak_bundle(view, record)` keep their signatures); new ones are p15 to p18 and `mut_plugin.py`. I ran `tests/test_bundle_lints.py` and `tests/test_real_names.py` together with `-m "not slow" -W error`: 453 passed, 1 deselected, 151 s. I did not run the full gate.

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| R1 (`review.md` leaves the jailbreak scope) | ADDRESSED | p8 (the spec's stage order): after stage 4 fixes the file, `jailbreak_bundle` is `[]` on the first validate, the second and the third (it was two fails on `review.md`); a file that keeps the phrase still fails on the file (F); `plan.md` quoting the phrase still fails (G). p17: `review.md` quoting the phrase, quoting it across a line wrap, and holding only the word "jailbreak" all pass; `plan.md` with the phrase or the word fails; a `transcripts/` copy is exempt. `review.md` is also not read by `real_name_bundle`, `reserved_hosts` or `boundary_bundle`. The exemption is the exact root path (`rel in _QUOTING_FILES`), so a nested `worlds/x/review.md` is still scanned. Mutants: `_QUOTING_FILES` emptied fails the two near-misses and the run-shaped test; `plan.md` added to it fails the run-shaped test (its last step). |
| M-A (lookahead true positives across a paragraph break) | ADDRESSED | p7b and p14: `# Source: The Verge`, a blank line, `Of the three outlets...` gives `real_name_bundle` 'The Verge'; `The house rule`, a blank line, `Out of hours...` gives `boundary_bundle` 'rule'. A blank line holding spaces counts as a break (p17). The spares across a wrap in one paragraph hold: `verge\nof tears`, `Source: The Verge\nOf the three...`, `rule\nout a fault`, `The house rule\nOut of hours` all pass. p7 (186 patterns, 6,276 cases): the heading-then-paragraph loss is gone, the remaining losses are the two same-paragraph wraps (the intended spare), and the gain is 1,620 cases, every one a wrap (round 1: 1,620). p7b: 0 differences over the 153 real files. Mutant: the paragraph split neutralised fails `real_name_bundle-9-positive`. |
| N-2 (invalid UTF-8 raises) | ADDRESSED for bytes; a sibling raise remains (NEW-1) | p15 (A): all 20 grammar files of the good bundle (config, expected, persona, plan.md, review.md, 13 documents, ladder, world sheet), each with bad bytes appended: no raise, exactly one `schema` fail naming the file and the byte ("not valid UTF-8: byte 0xe9 at offset 806"), no other fail. 5 byte shapes (cp1252, lone continuation, overlong, truncated 3-byte at EOF, UTF-16) over 5 file kinds: 25 of 25 a schema fail naming the file. All 20 bad at once: 20 schema fails. Valid-UTF-8 oddities (a NUL, a BOM) are YAML fails or nothing, never a raise. (B) Files outside the grammar with bad bytes (a note, a png, `.DS_Store`, a root stray file, `ledger.jsonl`, `.attempt.json`, `dryrun.jsonl`, `scratch.yaml`, and the exempt `transcripts/`, `dryrun/`, `state/`): none raises. A bad-byte `corpus/Extra.md` or `ladders/Extra.yaml` gives the off-grammar fail plus "world 'mini' does not load" (load_world's decode, caught as a ValueError). Mutant: `scan_text` made strict fails all 8 UTF-8 tests. Aside: a bad byte in `plan.json` still raises from `read_record` (`bundle.read_record()` at the top of `lint_bundle`); that is the harness's own record, not a grammar file, and not in the finding. |
| N-1 (off-grammar message hides the world lints) | ADDRESSED | The message now opens with the rule and ends "remove or rename <file>", listing the whole grammar and `bundle.NAME`; checked against `bundle._GRAMMAR`, it is complete (only the Windows device stems are not mentioned). p18: beside the test's own `bully_line` fault, a `notes.txt` in a world, a `personas/.gitkeep` and a binary `.DS_Store` each add only their own schema fail and lose nothing; a capital `Extra.md` document beside them gets its world lints (`no_duplicate_fact`, `layer_counts`, `premise_density`). Beside a real schema failure (a bad `config.yaml`) the world lints stay silent, as ruled, and the off-grammar fail is still listed (the early-return paths carry `files.off_grammar`). Mutant: any schema fail returning `loaded=None` fails all 5 `hides_none_of_the_world_lints` cases. |

## The 92-case probe, re-run (p2, same cases and labels as round 1)

| Lint | TP | FN | FP | TN | Precision | Recall | Round 1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `real_name_bundle` | 15 | 2 | 0 | 11 | 1.00 | 0.88 | 1.00 / 0.88 |
| `reserved_hosts` | 9 | 3 | 2 | 10 | 0.82 | 0.75 | 0.82 / 0.75 |
| `boundary_bundle` | 8 | 2 | 0 | 10 | 1.00 | 0.80 | 1.00 / 0.80 |
| `jailbreak_bundle` | 9 | 3 | 2 | 6 | 0.82 | 0.75 | 0.82 / 0.75 |

Nothing regressed; every verdict, miss and false positive is the same case as in round 1. The leftovers are the named residuals: a name fused into a compound host and a zero-width space; `.de`, a scheme-relative `.ru`, a public URL in `config.yaml`, `hours.info` and a path ending `.us`; `unrestricted` and `disallowed`; for the jailbreak list `developer modelled` and `bypass filters`. The jailbreak list's three misses are `ledger.jsonl`, `dryrun.jsonl` and `.attempt.json`, which the I1 ruling took out of scope; relabelled must-pass, it is TP 9, FN 0, FP 2, TN 9: precision 0.82, recall 1.00.

Round-2 supplement (p17, 25 cases, one change each; the seven residual cases are labelled must-fail on purpose): `real_name_bundle` TP 3, FN 2, FP 0, TN 3 (1.00 / 0.60); `boundary_bundle` TP 2, FN 1, FP 0, TN 3 (1.00 / 0.67); `jailbreak_bundle` TP 4, FN 1, FP 0, TN 4 (1.00 / 0.80); `reserved_hosts` 1.00 / 1.00. Every FN is a phrase split by a blank line. Near-miss shares recounted (p12): schema 19 of 37, real_name_bundle 10 of 19, reserved_hosts 10 of 15, boundary_bundle 9 of 16, jailbreak_bundle 12 of 20, all still a majority. The round-1 probes p3r (counts and sets, with the off-grammar cases), p4r (the plan.json self-reference), p6r (3 of 3 folded cases) and p11 (8 of 9 YAML spellings; the 9th is the known zero-width residual) are unchanged.

## New breakage, by severity

### Important

**NEW-1. A `.yaml` file with a YAML value that raises `ValueError` raises out of `lint_bundle`.** `_scan_texts` (`bundle_lints.py:557-561`) and `config_display_names` (`:486-489`) catch only `yaml.YAMLError`. PyYAML raises a plain `ValueError` for a timestamp that is not a date (`zz: 2026-13-45`, `2026-02-30`, `9999-12-31T25:61:61Z`; also `!!int abc`). p15 (E): 7 of 7 files raise `ValueError` out of `lint_bundle` (the world sheet, a persona, `config.yaml`, `expected.yaml`, a ladder, an off-grammar ladder, a stray `.yaml`), at `construct_yaml_timestamp`. `schema` itself handles the same text (its `_model` lets the `ValueError` reach the `except ValueError` in `_load_files`), so before the scans ran the result was a schema fail that says "month must be in 1..12"; now the exception ends the pass and the finding is lost. Origin: round 1's `_scan_texts` (8ec2485) for every `.yaml` but `config.yaml`; `config.yaml` has raised since 6ca2946 through `config_display_names`. It is outside the four round-1 findings, and the fix report's "so a scan never raises" holds for bytes only. Graded Important by the ruling's own principle (planner-authored file text must give a fail, never an exception out of `lint_bundle`), with the caveat that the input is an unquoted impossible calendar date in a `.yaml` file, which is rare. Fix: catch `(yaml.YAMLError, ValueError)` at both sites (the scan then reads the text alone, as it does for a YAML syntax error), plus a case beside `test_a_file_that_is_no_utf8_fails_schema_naming_it_and_raises_nothing`. Carry it instead if the controller reads the rarity as Minor.

### Minor

**M-1. The accepted blank-line residual is wider than the ruling's wording.** The ruling and the fix report name `real_name_bundle` ("a name split by a blank line passes"). p16 counts what the round-1 whole-text collapse caught and the paragraph scan does not: 65 of 166 real-name patterns, 1 of 9 boundary patterns (`safety training`) and 10 of 11 jailbreak patterns (`ignore all previous instructions` and the others of two or more words). It applies to a markdown body and a YAML literal block (`|`) only: folded (`>`), quoted and plain multi-line scalars still resolve a blank line to one newline in the parsed value, so the parsed-values text catches them. The raw text caught none of these either, so nothing falls below the 6ca2946 baseline; the extension to the jailbreak list is the one a reader of the ruling may not expect (a phrase an injection reads the same across a blank line). State it in the residual line, or accept it as is.

**M-2. The docs cite section 12 for a CI promise section 12 does not make for the jailbreak list.** Spec section 9's jailbreak row and docs/08's row say "a bundle checked into the repository is scanned whole by CI, `review.md` included (section 12)". Section 12 row 2 says it for the real-name scan (the list of files `tests/test_real_names.py` reads); row 3 (no jailbreak axis) points to section 14, which now says the scan leaves `review.md` out, and plan line 102 gives Task 12 a `plans/` jailbreak scan without naming `review.md`. Carry to Task 12's brief: the CI jailbreak scan of `plans/` reads `review.md` whole, and a committed bundle whose `review.md` quotes a phrase is "not committed as it stands" (spec line 439's real-name rule, extended).

### Nit

None new beyond M-2's wording. N-3 (a link under `worlds/`; this host cannot create a symlink, WinError 1314) and N-4 (the Task 5 carry) are carried as before; the Task 5 carry now holds both halves in `progress.md`.

## What the new tests do

Each new test bites on its mutant (`mut_plugin.py`, in-process monkeypatches, 22 selected tests green on the real tree): `_QUOTING_FILES` emptied fails `jailbreak_bundle-12-near`; the paragraph split neutralised fails `real_name_bundle-9-positive`; a strict `scan_text` fails `no_utf8...[plan.md]` and the rest of that test; any schema failure hiding the loaded bundle fails `hides_none_of_the_world_lints[notes]`; `plan.md` exempted fails the run-shaped R1 test. No test covers NEW-1.

## Probes in `probes-task4b-rereview2/`

- `p2_denylist_scans.py`: the 92-case probe (round 1's `p2r`, unchanged).
- `p3r`, `p4r`, `p6r`, `p11`, `p12`: round 1's, re-run on dff6e26.
- `p7_collapse_differential.py`, `p7b_real_files_and_lost_cases.py`, `p14_paragraph_collapse.py`: M-A.
- `p8_review_md_quote.py`: R1.
- `p10_new_breakage.py`: UTF-8, the base-world grammar check (76 of 76 files inside it), droppings.
- `p15_invalid_utf8_everywhere.py`: N-2 over 95 runs (8 raised: `plan.json` and the 7 YAML-timestamp cases of NEW-1).
- `p16_blank_line_split.py`: M-1.
- `p17_round2_delta.py`: the 25-case supplement and the off-grammar-beside-fault cases.
- `p18_off_grammar_beside_fault.py`: N-1 with the test's own fault.
- `mut_plugin.py`: the mutants.
