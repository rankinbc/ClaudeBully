# Task 12 re-review, fix round 2

Base e191082, head 1dda514 (one commit). Reviewer: scoped gate, sonnet. Read-only on the checkout. Probes are in `probes-task12-rereview2/` (two files, 283 tests). They run from the repo root with `-p tests.conftest -p no:cacheprovider --basetemp <scratchpad>`, each plant goes in a tmp copy of the example bundle, and the scratch directories are removed. The owner's name came from `owner_names()` at run time. It was written only into tmp copies, never printed, and no assertion echoes it. The probe files and the saved outputs were searched afterwards and hold no copy of it.

## Verdicts

| Finding | Verdict |
| --- | --- |
| N-3 (review.md and the bundle's own display name) | FIXED |
| N-1 (CI raw read stricter than the lints at a lookahead spare) | FIXED, with one new Minor (M-1) and one Nit (N-5) |
| N-2 (`record_strings` on a raw U+2028) | FIXED |

New: Critical 0, Important 0, Minor 1 (M-1), Nit 3 (N-5 to N-7). Regressions: none.

The invariant holds in the direction that matters. A bundle that passes `plan validate` did not fail CI in any probe, except a whitespace run of 62 or more characters (N-5). CI misses one thing the lints catch (M-1), and the fast suite's lint test over `plans/` still catches it, so the gate has no hole.

## N-3: real names in review.md

18 probes pass.

- **The own display name passes.** A reviewer note quoting `display_name: Claude`, in all three casings, passes the real-name scan of `review.md`.
- **Any other real name fails.** Eight forms, each in `review.md`: Reuters, Gemini, OpenAI, Anthropic's, Wall Street Journal, "display_name: Claude, from Reuters", "Claude by Anthropic", and Reuters on a line before Claude.
- **The owner name still fails.** Five forms in `review.md`: alone, upper-cased, beside "Claude", in a line that quotes `display_name: Claude`, and in a line of notes. Every hit names the file and none holds the name. The owner clause is read with nothing spared, so a spared display name beside it hides nothing. The real-name scan does not carry the owner clause (it stays separate, as designed).
- **Jailbreak stays strict.** "ignore all previous instructions", straight and wrapped, fails in `review.md`.
- **`real-name-ok` stays ignored.** A `# real-name-ok: reuters` line does not spare a Reuters line in `review.md`.
- **The spare is per bundle.** A second bundle whose config and request name "Gemini" has "Gemini" spared in its own `review.md`. The same line in the example's `review.md` fails, and the second bundle's file is not flagged.

## N-1: `helpers.lint_parity_hits`

### The spare probes pass, and the lint agrees

- **"the verge" before "of"**: 8 forms (wrapped, double space, CRLF, indented, tab, trailing space, one line, "of" on its own line) in a world document, `plan.md`, `review.md`, a persona file and `world.yaml`. All pass CI. The same 8 in a world document also pass `lint_bundle`'s `real_name_bundle`.
- **"rule" before "out"**: 5 forms (wrapped, double space, "rules" wrapped, indented, one line) in a world document and a persona file. All pass CI. The same 5 pass `boundary_bundle`.

### Splits with no spare still fail, in each family

- **Real name**, 11 forms: LF, CRLF, trailing space plus indent, a literal double space, tab, "The Verge" then "yesterday", "The Verge" then a blank line then "Of", a spared pair followed by an unspared one, a lone Reuters, U+2028 between the words, U+00A0 between the words. Each fails in a world document, `plan.md`, `review.md`, a persona file and `world.yaml` (55 probes). The first 6 also fail in `plan.json` behind an escaped newline and in a transcript reply (JSON content). Eight of them, planted in a world document, also fail the lint.
- **Jailbreak**, 5 forms (LF, CRLF, double space, one word per line, U+2028): each fails in the same 5 files (25 probes). The first 4 also fail in `plan.json`.
- **Boundary**, 6 forms ("safety" then "training" by LF, by CRLF and by a double space; "rules" then "changed"; "rule" then a blank line then "out"; a text holding "guidelines" beside a spared and an unspared "rule"): each fails in a world document, `world.yaml`, a persona file and a ladder file (24 probes).

### Differential fuzz against the old read

`lint_parity_hits` against the lint's own read (a search of `collapse_paragraphs(text)`) and against e191082's read (per line plus folded for Boundary; raw plus folded for the others). Texts of 2 to 12 tokens, with LF, CRLF, tab, double space, blank line, U+2028, U+00A0 and VT between them.

| Family | Texts | lint hit, CI miss | CI hit, lint miss | old hit, new miss |
| --- | --- | --- | --- | --- |
| Boundary | 18,000 | 0 | 0 | 275, every one a "rule" before "out"; none is a lint hit |
| Real name | 12,000 (lint columns); 8,000 more (old column) | 0 | 0 | 1, a lookahead spare |
| Jailbreak | 8,000 (lint columns); 8,000 more (old column) | 0 | 0 | 0 |
| Owner | 20,000 | not run | not run | 0 differences from the old raw plus folded read |

- **Owner pattern.** `owner_pattern` is `(?<!\w)(?:name)(?!\w)`. It carries a lookbehind and a lookahead, so the fix report's ASSUMED line ("their patterns have no lookahead") is wrong for the owner. It is harmless: the lookahead is `\w`, which whitespace does not touch. The differential shows no change, and the owner still fails in `review.md`, `plan.md`, a world document, `world.yaml`, a persona file, `config.yaml`, `expected.yaml`, `plan.json` behind an escaped newline and a reply (10 probes, beside the 5 `review.md` forms under N-3).

### Does Boundary still catch a term in a YAML comment line?

Yes. A comment line, an inline comment, "# safety training", "# the house rules", a term ending a comment before a key line, and two comment lines "# the house" and "# rules" each fail in `world.yaml`, a ladder, a premise and a persona file, and the lint fails the same ones. The whole-text fold keeps the `#` between two comment lines, so folding does not create a term out of a split comment.

### Does folding create or hide a term?

| Plant | CI | lint |
| --- | --- | --- |
| `# the house rule` then `out: 1` (comment, then content) | passes | passes |
| `# the house rule` then `# out of hand` (comment, comment) | fails | fails |
| `a: safety` then `training: 1` (content, content) | fails | fails |
| `the: rule` then `out: 1` (value, then key) | passes | fails (M-1) |

- **Hidden:** "rule" ending a comment line and the next line opening "out" is joined to "rule out" and spared, in both reads. The per-line read caught it. This is the same blind spot the lint has, which the ruling accepts ("CI keeps lint parity").
- **Created:** two content lines joined make "safety training" out of `a: safety` / `training: 1`. Both reads fail it. The lint has always done this (a false positive, not a regression).

### Is anything the per-line read caught now missed?

Yes, in two classes. Both are by the ruling or covered elsewhere, and neither is a Critical or Important.

1. "rule" ending a line before a line that opens "out" (the comment and the key-value cases above), which both reads spare. All 275 fuzz losses are this class, and none is a lint hit.
2. M-1 below.

## New findings

**M-1 (Minor): the scan body misses a YAML value that ends "rule" before a line opening "out", which the lint catches.** `the: rule` then `out: 1`, in `world.yaml`, a ladder, a premise or a persona file. The lint reads each parsed YAML value on its own line (the second text of `_scan_texts`), so it sees the value "rule" alone and fails. The CI scan reads only the raw and folded file text, where it is "the: rule out: 1" and spared. The per-line read at e191082 caught it, so this is a narrowing of what the scan body catches, against the ruling's "CI still catches everything the lints catch". It is no hole in the gate: `tests/test_example_bundle.py::test_every_bundle_passes_every_lint` is not marked slow, runs `lint_bundle` over every bundle under `plans/`, and fails on any fail-severity result. The same applies to "the verge" before "of" (`outlet: The Verge` then `of: ...`), the only other lookahead in the lists. Carry it with a note (HANDOFF or docs/08 says the lint test is what covers decoded YAML values), or have the scan also read decoded YAML strings for `worlds/` and `personas/`.

**N-5 (Nit): a whitespace run of 62 characters or more between "rule" and "out" fails CI and passes the lint.** CI judges a raw match on a window that ends 64 characters past the match, and the window cuts the "out". Probed with a run of spaces, and with a line feed plus indentation:

| Gap | 55 | 58 | 60 | 62 | 64 | 70 | 200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lint / CI hit | no / no | no / no | no / no | no / yes | no / yes | no / yes | no / yes |

The same boundary holds for "the verge" before "of". No natural text has a 62-character run inside one paragraph, but it is a case where a validated bundle fails CI. The fix report's ASSUMED line names the 64-character window, but about a lookahead that reads far, not about whitespace the fold collapses. A window taken to the next paragraph break (or the folded tail of the paragraph) removes it.

**N-6 (Nit): the display-name spare can splice a real name into a spared form.** The spare removes the name and leaves its spaces, so "The Verge Claude of the matter" reads as "The Verge  of the matter" and the lookahead spares it. This is true of `plan.md` since round 1 and now of `review.md`. It takes a deliberate insertion between the two words.

**N-7 (Nit): the fix report's ASSUMED line on the owner and jailbreak patterns.** The jailbreak list has no lookahead, as claimed. The owner pattern has a lookbehind and a lookahead (see above). No effect.

## N-2: a raw U+2028 in a ledger line

- **No raise.** `record_strings` reads a valid ledger line holding a raw U+2028, U+2029, U+0085 or U+2028 plus U+2029 in a string (4 probes). At e191082 `splitlines()` cut the line in two and `json.loads` raised `JSONDecodeError`, checked here on the same line.
- **The scans read it.** The four scans over a copy of the example with such a ledger run clean (3 probes, one per separator).
- **A name across the separator is still caught.** "Wall Street", the separator, "Journal" fails the real-name scan on `ledger.jsonl`, and "ignore all previous", the separator, "instructions" fails the jailbreak scan (3 probes, one per separator, each for both families). The fold treats the separators as whitespace.
- **The earlier rule holds.** A CRLF-terminated ledger reads. A torn last line (also one torn after a separator) is skipped. A bad middle line and a bad last line closed by a line feed raise `ValueError` naming the file and the line, and the line number counts line feeds, not separators. Blank lines, an empty file, a lone newline and a last line with no newline read.

## Regressions

- **Covering tests:** `tests/test_real_names.py`, `tests/test_guardrails.py`, `tests/test_boundary.py` and `tests/test_example_bundle.py` with `-m "slow or not slow" -W error`: 192 passed in 100 s, as the fix report says.
- **Example bundle:** passes the four scans on the checkout and on a copy. Scan cost on the checkout: real names 1.6 s, owner 0.07 s, jailbreak 0.14 s, Boundary 0.09 s.
- **Checkout clean:** `git status --short` is empty after the runs.
- **Goldens, data, configs and the package untouched:** `git diff e191082 1dda514 -- tests/fixtures/golden data configs claude_bully` is empty. The commit changed `HANDOFF.md`, `docs/00-RECONCILED.md`, the spec and four test files (`tests/helpers.py`, `test_boundary.py`, `test_guardrails.py`, `test_real_names.py`).
- **Tmp copies and scratch directories:** deleted.
- **Not run:** the full `tests/test_bundle_lints.py` (past the 300 s limit); ruff and mypy; a mutation run of the new plant tests (round 1's showed the plant tests bite; the fix report's RED of 6 failed and 5 passed on e191082 is not re-run here, since the checkout is read-only).

## Probes

| File | Tests | What |
| --- | --- | --- |
| `probe_task12_rereview2.py` | 268 | N-3 plants; N-1 spare and split plants in every family and location; Boundary comment plants against the lint; the differential fuzz; the whitespace-window probe; N-2 ledger probes |
| `probe_task12_rereview2_owner.py` | 15 | the owner clause through `lint_parity_hits`, the old-versus-new differential for the owner, real-name and jailbreak lists, scan timing |
