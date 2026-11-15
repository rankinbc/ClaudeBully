# Task 6 re-review, fix round 2: the owner clause, the real-name scrub, the context limit

Base 44ff1fa, head ff6d18d (one commit). I read `review-44ff1fa..ff6d18d.diff` once, then checked the report's claims against the checkout (read-only; HEAD is ff6d18d, tree clean). Probes are in `probes-task6-rereview2/`. This file and the probe outputs spell the owner's name nowhere (`<OWNER>` stands for it); I checked the outputs for the name and for fragments of it.

Tests I ran (no `.pytest_cache`, no bytecode written): `tests/test_director_context.py`, `test_director_prompts.py` and `test_real_names.py` with slow included, 170 passed in 38 s (`focused_tests_context.out`); `tests/test_bundle_lints.py -k "real_name or owner or Reuters or plan"`, 37 passed (`focused_tests_bundle_lints.out`).

## Verdicts

| Finding | Verdict |
| --- | --- |
| R1, the owner clause and plan.md in `real_name_bundle` | **ADDRESSED.** One qualification on "no checked-in file" (section 1, check 3). One carry to widen (N-B). |
| R2, contract examples and fenced code | **ADDRESSED.** The fence rule is exercised by the contracts only (docs/01 to 07 hold no fenced block). One spare is private to the scrub and its test (N-A). |
| N1, "Deliverables for Claude Code" | **ADDRESSED.** All five read "Deliverables for the CLI". |
| N1, docs/04's successor-name example | **ADDRESSED.** "Tessel 30.5 Final" passes every pattern; the old name still hits. |
| N2, `MAX_CONTEXT_CHARS` | **ADDRESSED.** Code and spec both say 300,000. No mismatch (section 3). |
| N3, stale spec text | **ADDRESSED.** `premise_sheet_model` and section 12 row 2 updated. Row 2 now carries one false clause (N-A). |
| N4, `owner_names` silent on no byline | **ADDRESSED.** It raises. |
| N5, the retry's fix list is scrubbed | Unchanged, accepted in round 1. The owner clause adds a hint-less line (N-C). |

New findings: Critical 0, Important 0, Minor 4 (N-A to N-D), Nit 3.

## 1. R1

**Check 1, a persona or plan.md that names the owner fails `real_name_bundle`; a planted real name in plan.md fails.** Probe 1 (`probe_owner_clause.py`) on the good bundle, whose own result is empty:

- The owner in the persona's backstory (plain, upper-case, possessive, `@handle`): one fail each, `personas/ferry_caller.yaml`, message `holds the owner's name`, span `None`.
- The owner in plan.md (plain, bold, in a heading, in a code span, hyphen-joined): one fail each, `plan.md`, same message, span `None`. The result never holds the name.
- Word-bounded: `<OWNER>wick` and `<OWNER>stead` pass.
- A real name in plan.md fails with its span: `Reuters`, `OpenAI`, `Anthropic` in prose, and `New York Times` wrapped across two lines. The target's display name alone (`Claude is the target`) passes through the config spare.
- `review.md` and a transcript naming the owner and `Reuters` pass (exempt, as ruled).
- The diff's tests agree: positives 11, near-misses 14, negative 1, so near-misses are 14 of 26 (`probe_counts_and_size.py`).

**Check 2, `owner_names` raises when there is no byline.** A docs directory with no byline and one that does not exist both raise `ValueError` ("no spec document's byline ... names the owner"). Through `lint_bundle` (the helper pointed at an empty docs directory) the exception comes out of `lint_bundle`, not as a `LintResult`.

**Check 3, the owner's name in no checked-in file.** `git grep -iw` over tracked files:

- **True for every list, code, test, fixture, config, script and spec file.** 0 hits under `claude_bully/`, `tests/`, `data/`, `configs/`, `scripts/`, `plans/`, the spec, `HANDOFF.md` and `README.md`. The diff itself adds or removes 0 lines naming the owner. The tests read it at run time (`OWNER`, `OWNERS`) from the bylines.
- **False taken literally.** 44 tracked files hold it. None is under any scan's scope (`data/worlds`, `data/personas`, `tests/fixtures/worlds`, `tests/fixtures/bundles`, `configs/`, the bundle lints):
  - the byline on line 3 of docs/01 to 10, and docs/02:234's body ("`<OWNER>` can overrule", scrubbed to "the owner" in the planner's view);
  - `LICENSE:3` and `pyproject.toml:8` (copyright and author metadata, with a surname);
  - `docs/superpowers/plans/2026-10-20-claude-bully.md:101`, `docs/handoff/drafts/README.review.md:174`;
  - 28 files under `docs/handoff/sdd/` (Windows profile paths such as `C:\Users\<OWNER>.<surname>\...` in the reports' command lines, and a "commits are authored by" sentence);
  - two run records, `docs/handoff/runs/rung0_smoke_env/*/cell.json` lines 16 and 17 (`sandbox_dir`, an 8.3 temp path).
  This is pre-existing and outside the ruling's "off every checked-in list". Say so if the controller wants a stricter rule; Task 12's CI scope (`plans/`, `tests/fixtures/bundles/`) does not reach these files.

**Check 5, `lint_bundle` raises when docs/ has no byline.** Nothing current breaks:

- `lint_bundle` has no caller outside tests until Task 9. The only other reference to `owner_names` is `context.planner_message`.
- CI (`.github/workflows/ci.yml`) is a full `actions/checkout` on ubuntu, so `docs/` is there. `SPEC_DOCS_DIR` is `REPO_ROOT / "docs"`, resolved from the package file like `DATA_DIR`; a tree without `docs/` is as unsupported as one without `data/`. `.gitattributes` forces LF, and the byline regex tolerates a trailing `\r` anyway.
- No test patches `SPEC_DOCS_DIR`. `tests/test_doctor_live.py:70` patches `cli.REPO_ROOT`, a different binding.
- `owner_names` globs every `docs/*.md`, while the tests' `OWNERS` reads `0[1-7]-*.md`. Today all ten bylines give one name, and `test_the_owner_is_read_by_one_helper...` asserts the two sets are equal, so a future doc with a different byline fails that test, loudly.
- Carry to Task 9 and Task 12: the `ValueError` is an exception, not a result. Task 9's validate must let it through or report it (fail closed is right). Task 12's CI scan reads `docs/` from the same checkout, so it is safe unless CI runs the scan outside the repository; a byline reformat would raise through every `lint_bundle` test at once.

## 2. R2

Probes 2, 2b, 2c, 6 (`probe_fidelity2.py`, `probe_config_contract_names.py`, `probe_scrubbed_lines.py`, `probe_span_edges.py`).

- **Contract examples.** All seven kinds and every shipped premise sheet are fixed points of `scrub`, hold no `real-name-ok`, and pass the real-name scan (a config's through the config spare). The persona example is `twin.yaml`: every key of the Captor's sheet plus `capture_schedule`, valid as a `PersonaSheet`, no exemption (`probe_twin_example.py`).
- **Fenced blocks.** 29 fences over 15 built messages (every single scope, all scopes, each of the seven contracts), found by my own CommonMark parser: 0 are changed by the scrub, and each contract is byte-verbatim in its message. Every fence is clean under the real-name scan with the display name `Claude` and provider values spared, except one hit, the config schema's `"anthropic",` enum string (N-A).
- **docs/01 to 07 hold no fenced block and no indented code block** (0 lines of either, checked by grep). The report's "42 lines change, none inside a fence" is true and vacuous. The fence rule works on the contracts and nothing else. Changed lines: 41 (the report says 42; the register adds one, the index and capabilities none).
- **Mangle greps over the harness side outside fences, 15 messages.** 0 neutral words glued to a path, id, key or flag (`-`, `_`, `/`, `.`, `\`, or before `-x`/`--x`); 0 inside a code span except the quoted value on docs/02:124 (`query "the provider"`, pinned by the test as the one allowed place); 0 doubled articles.
- **Inline spans.** 8 spans change in docs/01 to 07:
  - five `claude -p` spans (docs/02:109, 111, 156; 04:150; 05:112) read "the CLI target's ...", "attempt's CLI session": the span goes, prose stays;
  - docs/01:135 `` `claude-defender` `` reads `` `defender` ``;
  - docs/06:68 `` `claude-bully analyze --hypotheses` `` reads `` `analyze --hypotheses` ``;
  - the quoted log value above.
  No path or config key changes. The two shortened names are no longer runnable or real identifiers; the planner runs nothing. The register changes on one prose line only; the index and the capabilities do not change.
- **Prose bends that remain** (reported, accepted in round 1): "the real a model" (docs/01:58), "an old friend named a model" (01:57), "'a model' and his kids" (06:23).

## 3. The limit

- Code: `MAX_CONTEXT_CHARS: Final = 300_000` (`claude_bully/planner/context.py:200`).
- Spec: section 6's body, line 167 ("`MAX_CONTEXT_CHARS = 300_000` characters"), and "As planned" line 611. Line 600 is the round-1 bullet, kept as history and marked "raised to 300,000 in fix round 2". `HANDOFF.md` carries both numbers in order. No other file states 250,000 as the limit.
- The report's "240k ceiling" is the stage-2 test's threshold, `0.8 * MAX_CONTEXT_CHARS` (`tests/test_director_context.py:954`), which is 240,000 only because the limit is 300,000. **No mismatch.** The default test's bounds are 0.6x and 1x (180,000 to 300,000); the largest default message is 195,633.
- Measured (`probe_counts_and_size.py`): the realistic stage-2 message is 235,364 with the config contract (235,045 with the world-sheet contract; the report says 235,402, an immaterial drift). Headroom to the limit is 64,636; the margin to the test's own ceiling is 4,636 characters, 1.9 percent. Any growth of the docs by about 4.6k characters trips the test, as the report says is the intent. That bundle holds no authored documents beyond the overlay copy; Task 7a's size handling remains open.

## 4. docs/04's invented name

- Diff: three lines changed (22, 31, 52), `Fable 30.5 Final` / `fable-30.5-final` to `Tessel 30.5 Final` / `tessel-30.5-final`; `real_names.txt` changes in its header comment only.
- Probe 5 (`probe_docs04_name.py`): every pattern over `Tessel 30.5 Final` and `tessel-30.5-final` gives no hit; the old name and id still hit (`Fable 30`, `fable-30`), so the denylist keeps its point; docs/04 scrubbed gives no hit; the three lines are unchanged by the scrub; no pattern mentions "tessel". `test_docs_04_keeps_its_successor_name_example...` passes.
- Invented: yes in the sense that matters (no model family, brand or outlet on the list). Two nits: the stem is shared with the overlay world's own invented "Tessellate fleet" (`data/worlds/overlay/world.yaml`), and, to my knowledge, "Tessel" was a small open-source hardware board, so "invented" means "not on the list", not "never used". Neither affects the scan.

## New findings

### Minor

- **N-A. The provider JSON enum spare exists only in the scrub and its test.** The config contract's schema holds `"anthropic",` (ProviderKind's enum, shown as generated). `_PROVIDER_STRING` spares it in `context.scrub` and in the test's own `_real_name_hits`, but `bundle_lints.config_scan_text` and `record_scan_text` (the repository's spares) do not. Probe 3 (`probe_message_through_repo_spare.py`): scanning each built message through `config_scan_text` with `Claude` spared gives 0 hits for the seven other contract kinds and for none, and 1 hit (`anthropic`, line 697) for the config contract. So spec section 12 row 2's new sentence, "since Task 6's context scrub it holds no real name but a target's display name and model id and a role's provider value (the scan's spares)", is false for a config-contract message. Carry to Task 12: either add the JSON enum string to the config spare, or strike the sentence's claim for the config contract.
- **N-B. plan.md reaches every model call before any scan, and stage 5 has no repair.** The ruling's Task 8 carry runs the denylist scans before each reviewer and confirm call. plan.md is written at stage 1, adopted after an owner edit, and shown to the planner in `## Bundle so far` on every stage-2 file call; the owner's name or a real name in it reaches the planner (stage 2) first, and stage 5 ("No model call", spec section 7) can only report it, after stages 2 to 4 are spent. Probe (round 1) showed the same. Widen the carry: run the plan.md clause (real name plus owner) at the stage 1 commit and at adoption of an owner edit, before the first file call.
- **N-C. The owner clause's fix line carries no span and the planner cannot find its subject.** The result is `plan.md: holds the owner's name`, as intended (a recorded result and a retry's fix list hold no copy). The planner's context says "the owner" everywhere, so it does not know the word, and a character named with the owner's given name (a common one) in a persona or world sheet passes `lint_document` on arrival and fails only at stage 5, with no repair route and no hint. Probability per world is low, the cost is the whole authoring run. Carry to Tasks 7a and 9: a fix-list sentence for this clause that says what to look for (a character's given name, in any file) without the name. Also, the pattern's `(?<!\w)...(?!\w)` lets `<OWNER>_notes` and a name with a zero-width space through (probe 1, "escapes"): the project's other `\b` patterns share this. Nit: the `ValueError` text carries the docs path, which holds the profile name on this machine; a Task 9 handler should not record it.
- **N-D. The scrub's span rule is positional, and the test cannot see one form of its damage.** Probe 6 shows what a future span would read as: `` `claude-opus-5-5` `` becomes `` `opus-5-5` ``; `` `model: claude-sonnet-4` `` becomes `` `model: model-sonnet-4` ``; `` `CLAUDE.md` `` becomes "a model"; `` `claude/config.yaml` `` becomes "a model"; `` `claude-bully/docs/x.md` `` becomes "the harness"; `` `gpt-4o-mini` `` becomes `` `mini` ``. None occurs in docs/01 to 07, the register, the index or the capabilities today. `test_no_scrubbed_message_holds_a_mangled_command_path_or_config_key` looks for the neutral words including "a model", so the article-stripped "model-sonnet-4" inside a span passes it. The implementer named part of this ("`claude-opus-5-5` would read `opus-5-5`"). A Task 12 or docs edit that adds such a span to docs/01 to 07 will not be caught by the test. Cheap fix: also match `\bmodel-\w` and a span that vanished whole.

### Nits

- The report says the stage-2 message is 235k against 240k; the test's ceiling is 0.8 of the limit, not a second limit (section 3).
- `owner_names` reads all of `docs/*.md`, the tests' `OWNERS` only `0[1-7]-*.md` (equal today and asserted).
- docs/01:57 reads "an old friend named a model" in the Captor pressure's table; the persona the planner copies from is the Twin, so this is prose only.

## Carried items

- Task 8: the denylist scans (real-name with the owner clause, Boundary, jailbreak) before each reviewer and confirm call, as ruled; widen to the stage 1 commit and the adoption of an owner edit (N-B).
- Task 9: `lint_bundle` raises `ValueError` when no byline gives the owner (check 5); a fix line for the span-less owner clause (N-C).
- Task 12: the CI scan reuses the owner clause (`plans/`, `tests/fixtures/bundles/`); the config-contract message's `"anthropic"` enum (N-A); the docs byline dependency.
- Task 7a: `planner_message` still does not refuse over the limit; the realistic message is 235k of 300k.

## Probes (all in probes-task6-rereview2/)

| File | What it shows |
| --- | --- |
| `probe_owner_clause.py` / `.out` | The owner and real names in a persona and in plan.md, near-misses, escapes, exempt files, `owner_names` and `lint_bundle` with no byline, the fix line. |
| `probe_fidelity2.py` / `.out` | Every changed line of docs/01 to 07 (whole lines, owner redacted), the register, index and capabilities, 15 built messages: fences, real-name scan, glued words, code spans. |
| `probe_config_contract_names.py` / `.out` | Every raw real-name hit in each contract (the spared ones). |
| `probe_scrubbed_lines.py` / `.out` | Each changed doc line as the planner reads it. |
| `probe_message_through_repo_spare.py` / `.out` | Each built message scanned through the repository's own config spare (N-A). |
| `probe_twin_example.py` / `.out` | `twin.yaml` against the Captor's keys and `PersonaSheet`. |
| `probe_docs04_name.py` / `.out` | The invented name against every pattern; the old name still hits. |
| `probe_span_edges.py` / `.out` | What the span rules do on inputs docs/01 to 07 do not hold (N-D). |
| `probe_counts_and_size.py` / `.out` | The real_name_bundle case counts and the message sizes against 300,000 and 240,000. |
| `focused_tests_context.out`, `focused_tests_bundle_lints.out` | 170 passed; 37 passed. |
