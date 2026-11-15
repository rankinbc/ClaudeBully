# Task 6 re-review, fix round 1: the Director's prompts, the agents' context, the ledger roles

Base 734477b, head 44ff1fa (one commit). I read the diff `review-734477b..44ff1fa.diff` once and checked the fix report's claims against the code. I did not trust the report. The checkout was read-only. My probes are in `probes-task6-rereview/`. The focused tests pass: `tests/test_director_context.py`, `test_director_prompts.py`, `test_cli.py` and `test_real_names.py` with slow included, 165 passed (`focused_tests.out`). This file spells out the owner's name nowhere, and neither do the probes' outputs.

## Verdicts

| Finding | Verdict |
| --- | --- |
| I1, real names and the owner's name in the context | **ADDRESSED for the harness's own text. The ruling's test is met.** Two new findings remain open beside it (R1, R2). |
| I2, D-plan-in-context | **ADDRESSED** |
| M1, review.md shown to the reviewer | **ADDRESSED.** It matches the spec (quotes below). |
| M2, the capabilities filter | **ADDRESSED** |
| M3, the confirm key `finding` | **ADDRESSED** (the key is now `passage`) |
| M4, the confirm prompt defines one outcome of three | **NOT CHANGED, correctly.** The text is verbatim, so this is the controller's ruling to make. It is still open with the controller. |
| M5, the reviewer is primed to find | **ADDRESSED** (recorded in docs/08) |
| M6, the message size | **ADDRESSED in the spec.** The carry to Task 7a's note and the runbook is the controller's. See also N2. |
| M7, `_premise_model` was private | **ADDRESSED.** One stale reference is left in the spec (N3). |
| M8, an ambiguous confirm passage | **ADDRESSED** |
| M9, the Specs part did not say what it left out | **ADDRESSED** |

New findings: Critical 0, Important 2 (R1, R2), Minor 5 (N1 to N5).

## 1. I1 coverage

### The planner

Probe 1 (`probe_scan.py`) built 97 messages:
- the planner message for every single scope, every pair of scopes and all scopes;
- the default request with each of the seven contract kinds;
- the good bundle's own request (target display name `Claude`);
- each of these on both worlds directories, with a retry fix list;
- four reviewer groups shaped like the spec's `REVIEW_GROUPS` (corpus, a corpus chunk with an index, lines, plan);
- one confirm call per bundle file.

I scanned every message independently, with no spares, using `load_patterns(REAL_NAMES_PATH)` plus the owner's name, which I read from the docs' bylines with my own pattern.

- There were 382 raw hits. Every one of them sits on a `display_name: Claude` line, on a `provider: anthropic` line, or on the target's display-name line inside `## Request`. Those are the scan's own spares and the scrub's spare.
- The owner's name had 0 hits in all 97 messages.
- 0 hits were unspared.

### The reviewer and confirm messages

I stripped each shown file's text and path out of the reviewer and confirm messages. What remains is the harness's own text:
- the headings;
- the 32 lint ids;
- `call: review:<group>` and `files:`;
- `REVIEW_REPLY` and `CONFIRM_REPLY`.

That residue holds no real name and no owner's name. It also holds no docs/01 to 07 line: the one six-word match was a table separator, `| --- | --- | --- | --- |`, from plan.md. Neither builder takes `docs_dir`, `worlds_dir`, a template or a request. On the harness side, therefore, neither message carries any docs/ context, harness text or template that names a real name or the owner. The ruling is met for everything the harness writes.

The implementer's slow test, `test_no_built_message_holds_a_real_name_or_the_owners_name` (`tests/test_director_context.py:507`), covers the same matrix and passes. Its reviewer and confirm half is true by construction on the clean good bundle. What it really pins is the residue above, and that is the right thing to pin.

### The ordering: not confirmed (R1)

The implementer's justification is that bundle files are shown as written because they "pass `real_name_bundle`" (`claude_bully/planner/context.py:561`; the spec's "As planned" Task 6 bullet at line 596). That is not true at the time the reviewer reads them:

- `real_name_bundle` is a `lint_bundle` lint, and `lint_bundle` runs only at stage 5. That is after stage 3 (review) and after stage 4's confirm calls (spec section 7, "Stage 5, validate").
- On arrival in stage 2, only corpus documents get a real-name check (`lint_document`'s `real_name`, then `lint_world` at the world close). A world sheet, ladder, premise sheet, persona, `config.yaml` and `expected.yaml` get their schema only (section 7, stage 2 step 3).
- `plan.md` is exempt from `real_name_bundle` altogether (section 9's row) and is never real-name-checked in flight.

Probe 3 (`probe_order_plan_limit.py`) planted `Anthropic` and the owner's name in the good bundle's persona backstory, and `OpenAI` and the owner's name in `plan.md`. All of them reached the `lines` and `plan` reviewer messages and the `plan.md` confirm call. The owner's name and `OpenAI` in plan.md also reached the planner's `## Bundle so far` in a stage-2 file call. Stage 5's `lint_bundle` then failed `real_name_bundle` on the persona's `Anthropic`. It passed the owner's name in the persona, and it passed everything in plan.md.

This is model-written or owner-edited text, not harness context. But the ruling says "before any model sees it", and both plan.md (which the owner may edit before stage 2) and a planner slip reach the reviewer and confirm calls, and plan.md reaches the planner, with no check first.

## 2. The owner's name in bundles: recommendation

**Yes. Make the lints read the owner's name at run time from the docs' bylines, and keep it off `real_names.txt`.** Concretely:

1. **One helper.** Move `owner_names` to `planner/lints.py` beside `REAL_NAMES_PATH`, so `context.scrub`, `bundle_lints` and the tests read one source. Have it **raise** when no byline gives a name. Today an empty result silently turns the owner's scrub into a no-op (N4). The test `test_the_owner_is_found_by_the_spec_docs_bylines` guards only the shipped docs.
2. **`real_name_bundle` gains an owner clause.** It should run over the files the lint already scans (worlds, personas, config, expected) **and over `plan.md`**:
   - There is no reason for plan.md to quote the owner's name. Its exemption exists for quoted real names.
   - plan.md is the one file the owner edits by hand before stage 2.
   - plan.md now reaches the planner unscrubbed through `## Bundle so far` (I2).
   - `review.md` and `transcripts/` stay exempt.
3. **Run the denylist scans before review (closes R1).** Task 8 should run `real_name_bundle` (with the owner clause) over each review group's files before the reviewer call, and over the confirmed file before each confirm call. A failing file goes to the existing repair path. Stage 2's adoption of an owner edit (`edited`) should run the owner clause on plan.md before the first file call. The cost is the two scans already built, run earlier.
4. **Task 12's repository scan** of `plans/` and `tests/fixtures/bundles/` should take the same helper, so a committed bundle naming the owner fails CI.

If the controller prefers not to touch Task 8's order, the minimum is to correct the claim at `context.py:561` and the spec's line 596 to say what actually holds: documents are real-name-checked on arrival, every other file only at stage 5, and plan.md never.

## 3. Scrub fidelity

Probe 2 (`probe_fidelity.py`) diffed every changed span of docs/01 to 07, the register, the index, the capabilities and every contract example. The index, the capabilities and five of the seven contract examples are unchanged. The bends:

**R2 (Important): the persona contract example is mangled into a sheet the planner would copy.** `CONTRACT_EXAMPLES["persona"]` is `data/personas/captor.yaml` (`context.py:129`), the one shipped persona with an exemption. Its `# real-name-ok: claude` line and the target-named friend are scrubbed with no regard for the exemption. Every persona file call is shown (probe 4, `probe_persona_contract.py`):

```
# real-name-ok: a model
  - name: a model
  You are talking about an old friend named a model, an engineer you knew for twenty years.
  - "a model made bread every Sunday. Terrible bread. He made everyone eat it anyway."
```

This is the one example of the kind, and it is the shape the planner copies. The result is a cast member whose `name:` is "a model", a nonsensical exemption directive, and a sentence opening in lowercase. A persona copied from it passes every lint; the reviewer is the only catch.

The config example has the same fault in a comment: `#   model: a model-opus-5-5` (from `configs/environments/triggered_vs_scheduled.yaml:30`).

Fix: choose a persona example with no `# real-name-ok:` line, and drop or reword the config comment. Then add a test that every contract example is unchanged by `scrub`. That test closes the class.

**N1 (Minor): the prose and code spans that bend:**
- **"Deliverables for Claude Code" becomes "Deliverables for a model".** This happens in docs/02:252, 03:121, 04:174, 05:133 and 07:148. The implementer's checklist now reads as if it addressed the reader, which is the planner. Suggested closed fix-up: "Claude Code" becomes "the implementer".
- **docs/04's successor-name example `"Fable 30.5 Final"` becomes `"a model"`.** Likewise `upstream_model: fable-30.5-final` becomes `upstream_model: a model` (docs/04:22, 31, 52). The authority premise needs that shape (same lineage, higher version, invented). The planner now reads "a model in its own lineage (e.g. "a model")" and loses the pattern. Suggested fix: replace the example with an invented family and version, not with the neutral word.
- **Two distinct labs collapse into one.** "Anthropic and OpenAI-compatible targets" reads "the provider and the provider-compatible targets" (docs/02).
- **Grammar breaks.** "the real a model" (docs/01) and "not a model-specific" (docs/06).
- **Commands and module names in code spans are mangled.** `claude -p` becomes `a model -p` (docs/02, 04, 05). `claude-bully analyze --hypotheses` becomes `the harness analyze --hypotheses` (docs/06). `` `claude-defender` `` becomes `` `a model-defender` ``, which then reads "a `a model-defender` module" (docs/01). The planner runs nothing and writes no code path, so these mislead little. The ruling accepted them ("a slightly edited doc").
- **No path or config key is mangled.** `claude_bully/...`, `claude_code` and `ClaudeCodeProvider` are untouched, because an underscore or a letter is a word character. Provider values are spared.

## 4. I2

This is addressed. In a stage-2 file call (a document contract, on the good bundle), `## Bundle so far` opens with `### plan.md` and a four-backtick fence holding plan.md in full (probe 3 (c)). A stage-1 bundle has no such heading (tested). plan.md is shown unscrubbed, which is how an owner's edit naming the owner reaches the planner (see point 2).

Nit: a plan.md containing a four-backtick line would close the fence early. That is unlikely under `MAX_PLAN_CHARS = 20_000`.

## 5. MAX_CONTEXT_CHARS

**Stated in the spec: only in the "As planned" amendments** (spec line 598), not in section 6's parts list or section 13. That meets the ruling's letter. A line in section 6, part 7 or the call primitive, would make it findable.

**The test is meaningful as a regression guard on the harness side, and weak as a budget (N2).** `test_every_default_planner_message_is_under_the_context_limit` (`tests/test_director_context.py:627`) builds the default request with every contract on the good bundle. Its `## Bundle so far` is about 6k characters. The test holds the largest message under 250,000 and above 150,000, and the lower bound stops a lazily large limit, which is good.

A realistic stage-2 bundle is much closer to the limit. I measured the overlay reused (46 documents) plus plan.md at `MAX_PLAN_CHARS`: `## Bundle so far` is 47,884 characters and the message is 235,402 with the config contract (probe 3 (d)). That is 94 percent of the limit before any authored document is added.

`planner_message` does not refuse (ASSUMED, left to Task 7a). Task 7a should therefore either measure the limit against a worst-case bundle or bound `## Bundle so far` on its own. The code comment's figures (`context.py:186-188`) are 734477b's. They are correct as history, but the spec's post-fix figures are the ones to carry.

## 6. review.md

The implementer refuses it in `reviewer_message` (files and index) and in `confirm_message`, on every round. The spec agrees:

- Section 6, the closed rule (line 169): "No reviewer message holds the planner's prompt, the request's constraints, a transcript, `plan.json`, the planner's responses (at confirm time), or a lint result."
- Section 7, stage 3 (line 191): "One reviewer call per group of `REVIEW_GROUPS`: `corpus` (in chunks of at most `REVIEW_CHUNK_DOCS = 25` documents), `lines` (world sheets, ladders, personas, premise sheets), `plan` (`plan.md`, `config.yaml`, `expected.yaml`)." review.md is in no group.
- Section 7, "The commands' reach" (line 199): "`plan review` reruns stages 3, 4 and 5 on an edited bundle; the old `review.md` goes to `transcripts/review-<n>.md`." So a later round's review never has a review.md to show.
- docs/08:48: "The reviewer receives the bundle and the lint list (next sections)." At stage 3, review.md has not yet been written.

review.md holds the planner's responses only after stage 4, which is "at confirm time". No spec line shows it to the reviewer at any stage. The refusal on every round is therefore what the spec says, made structural. The spec's section 6 now states it (line 167).

## New findings

### Important

- **R1. The bundle's files reach the reviewer and confirm calls, and plan.md reaches the planner, before any real-name or owner check.** See `context.py:561`, spec line 596, and spec sections 7 and 9. The claim that they "pass `real_name_bundle`" is false at review time: that lint runs at stage 5, non-document files get no name check on arrival, and plan.md never gets one. The owner's name is caught nowhere (probe 3). Fix: see point 2 (3), as a Task 8 carry, plus correcting the two sentences now.
- **R2. The persona contract example is scrubbed into `name: a model`, `# real-name-ok: a model` and lowercase "a model made bread".** See `context.py:129` (`captor.yaml`) and the config example's `a model-opus-5-5` comment. Fix: a persona example with no exemption, the config comment reworded, and a test that every contract example is scrub-invariant.

### Minor

- **N1. Scrub bends in prose and code spans** (point 3). Fix the "Deliverables for Claude Code" fix-up and docs/04's successor-name example. Accept the rest under the ruling.
- **N2. `MAX_CONTEXT_CHARS` is pinned on a small bundle.** A realistic stage-2 bundle measures 235,402 characters (94 percent of the limit). It is stated only in "As planned". Carry to Task 7a.
- **N3. The spec has stale text.**
  - The "As planned" Task 6 bullet at line 594 still reads `bundle_lints._premise_model`.
  - Section 12, row 2 (line 337) and the plan's R-scan-bundles still say a transcript's message "is not rescanned: ... built from docs/01 to docs/07 (which name real models by design)". After the scrub, a message holds no real name but the spared target names and the bundle's files as written. Task 12 can now scan the messages with the config spare. Carry to Task 12.
- **N4. `owner_names` returns an empty set for a docs directory with no byline** (`context.py:279`). `planner_message` then scrubs no owner and says nothing. Fail closed (raise), as point 2 (1) suggests.
- **N5. The retry's fix list is scrubbed.** A `real_name` failure therefore reaches the planner as "the provider" or "a model", not as the word it wrote (the report's ASSUMED). The lint id and the file still locate it. Acceptable, but a line in the spec would say so.

## Probes (all in probes-task6-rereview/)

| File | What it shows |
| --- | --- |
| `probe_scan.py` / `.out` | 97 built messages, scanned raw with the real-name patterns and the owner's name (from the bylines, not printed). 382 hits, all spares. 0 owner hits. 0 unspared hits. The reviewer and confirm residue (the harness's own text) verbatim, with no name and no docs line. |
| `probe_fidelity.py` / `.out` | Every span the scrub changes in docs/01 to 07, the register, the index, the capabilities and the contract examples, with code spans marked. |
| `probe_order_plan_limit.py` / `.out` | (a) and (b): names planted in a persona and in plan.md reach the reviewer, the confirm call and the planner. Stage 5 catches the persona's lab name only, and never the owner. (c): plan.md opens `## Bundle so far` in a stage-2 call. (d): an overlay-sized bundle with a 20,000-character plan.md gives 235,402 characters. |
| `probe_persona_contract.py` / `.out` | The persona and config contract examples as a file call receives them. |
| `focused_tests.out` | 165 passed, slow included. |
