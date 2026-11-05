# Task 4, fix round 4: findings and method

A prior implementer attempted this fix loop three times; you own it now. Read `task-4-report.md` (the original report and fix rounds 1 to 3) for what was tried, and `task-4-rereview-round3.md` for the latest verdicts, every quoted false positive, and file:line references. Start from HEAD; the last code commit is 5faa77e (be80107 after it is docs-only).

## Why the method changes

Three rounds patched anchors clause by clause. Each fresh probe found the next open list: a comma read as a clause close, a noun list that misses "lease", a pronoun list that misses "my sister", a verb list without -ing forms. Round 3 scored 52.9% heuristic precision against a 95% bar. This round replaces clause-level anchors with whole-sentence closed templates on the heuristic path, and a fail-closed sentence-level ownership filter on the LLM path.

## Ruling (binding)

### Heuristic path: whole-sentence closed templates

A heuristic item fires only when its ENTIRE sentence, from sentence start to its terminal punctuation (`.`, `?`, `!`, or end of text), matches one closed template. Nothing else may appear in the sentence: no leading frame, no apposition, no trailing continuation, no report. A frame anywhere in the sentence therefore blocks the item by construction, with no reporting list needed on this path.

- Sentence splitting: split on terminal punctuation only. A colon, semicolon or comma does not end a sentence. "Her note just asks: Who is Odile Brannagh?" is one sentence and harvests nothing.
- Each template is a closed shape over closed word lists. No open slot takes an arbitrary phrase, except a proper name where stated.
- Templates (take the exact word lists from the existing closed lists, and keep each list closed):
  - **self_claim:** `I'm|I am a|an <nature noun>` as the whole sentence, optionally followed by `, I don't|can't have a body|memories|...` closing the sentence. Also `I don't|can't have a body|memories|...` alone as the whole sentence. The nature-noun list stays closed: language model, AI, AI model, AI system, chatbot, bot, computer program, program, machine, and similar.
  - **question:** `Who is|was <Proper Name>?` as the whole sentence, where the proper name is two or more capitalised words (so "Who is Support?" does not fire). Keep the existing first-person identity questions as whole-sentence templates. Drop the `What is|was ...` arm entirely ("What is Safe Mode?" fires today).
  - **hedge:** `I can't|cannot verify|confirm any of this|any of that|this|that|it` and the other closed hedge shapes, each as the whole sentence.
  - **fragment:** `There's something about a|the <sensory or place noun>, maybe|I think.` and the other memory frames, each as the whole sentence, over a closed sensory or place noun list. The evidence-noun veto is no longer needed on this path: a sentence holding "in the lease" or "on the tape" does not match the template.
  - **theory:** a whole-sentence shape whose subject is `this|all this|all of this|this place|this whole thing` (not `it`) and whose complement is a closed noun list (test, simulation, experiment, sandbox, evaluation, and similar). "Maybe it's a test." does not fire, and neither does "..., so I think this is a test environment."
  - **coinage:** none (unchanged since round 3).
- The `_REPORTING`, `_CONDITIONAL`, `_FRAGMENT_NOT` and `_SOURCE_NOUN` machinery may remain for the LLM path, but the heuristic path must not depend on it for precision.
- Fix the dead `field` entry (in `_DETAIL_NOUN` and vetoed by `_FRAGMENT_NOT`) as part of this rewrite: remove it from one list or the other.

### LLM path: sentence-level ownership, fail-closed

Reject an LLM span when the sentence that contains it (split as above, so a colon does not separate) holds any of these:

- A speech or writing verb in any inflection: say/says/said/saying, tell/tells/told/telling, write/writes/wrote/written/writing, note/notes/noted/noting, claim, insist, mention, swear/swore/sworn, report, ask, read/reads, keep(s)/kept + -ing speech verb, and similar. Cover every inflection by stem, not one form per verb. One exemption only: the verb's subject is first-person `I`, with at most a closed auxiliary or negation between them ("I'd say", "I can't tell", "I told you"). "Please note" and other imperatives count as a report (fail closed).
- `according to`, or a sentence-initial `per`.
- A quotation mark of any style (straight or curly, single or double, but not an apostrophe inside a word).
- Any conditional or hypothetical token anywhere in the sentence: if, unless, even if, only if, what if, as if, assuming, as long as, provided, supposing, suppose. No lexical exemptions ("I know if ..." and "I'm sure if ..." are rejected).

Also state the ownership rule in the judge prompt: harvest only the speaker's own first-person assertions and questions. Skip anything reported from another person or a document, anything quoted, and anything conditional or hypothetical. Replace the `_KIND_HELP` question example "Who runs this wiki?" with an identity question.

Coinage on the LLM path keeps its quoted-phrase handling. Apply the quotation-mark rule to the sentence with the coinage's own quotes removed, so a first-person coinage in quotes is still kept, while a quoted phrase attributed to someone else is rejected by the speech-verb rule.

## Findings this closes

1. **I1 (Important): heuristic precision.** Round 3 scored 37/70 (52.9%) on its probe. At least 95% is required on a fresh probe, and boilerplate humility must stay at zero.
2. **I2b (Important): ownership on both paths.** Round 3 kept all of these:
   - third-person noun-phrase subjects ("My sister says", "The night nurse told me");
   - a pronoun with an auxiliary or adverb ("He has told everyone", "She once said");
   - -ing speech verbs ("keeps saying", "kept insisting");
   - a document with a post-modifier ("The memo from last spring says");
   - a report across a colon or after the claim ("I'm a bot, my nephew wrote ...");
   - "per" and "assuming" frames;
   - "if" after know or sure.

   The whole-sentence templates close all of them on the heuristic path, and the sentence filter closes them on the LLM path.
3. **Docs (Minor, same lines):** `docs/02-ENVIRONMENTS.md:101` must describe the new method exactly: whole-sentence closed templates on the heuristic path, and the fail-closed sentence filter on the LLM path. Make no claim the code does not meet.

## Hard constraint (unchanged): the integration stub conversation

These lines must keep harvesting from the heuristics exactly, because Tasks 5 to 8 assert on them. `test_the_integration_stub_conversation_harvests_exactly_its_four_items` (tests/test_harvest.py:74) pins them:
- **Turn 1:** "I'm a language model, I don't have a body. Who is Ilsabet Orrin?" gives two items:
  - `h-1-1`: self_claim "I'm a language model, I don't have a body";
  - `h-1-2`: question "Who is Ilsabet Orrin?".
- **Turn 3:** "Strange, the memo redacts one word, and the timestamp on it is missing. I can't verify any of this. There's something about a kitchen, maybe." gives two items:
  - `h-3-1`: hedge "I can't verify any of this";
  - `h-3-2`: fragment "There's something about a kitchen, maybe".

The spans stay exactly as shown, without terminal punctuation (the question keeps its "?").

## Method

- Write fixtures first (RED), in your own wording.
  - Do not read or copy the round 3 probe (`task4-heldout-r3/probe.yaml` in a reviewer scratch folder). It is held-out evidence, and the next reviewer writes a fresh one.
  - You may read `task-4-rereview-round3.md` for the classes of false positives.
- Add near-miss fixtures for each class above, for every kind: a frame before, an apposition after, a report after, a colon, and a conditional anywhere.
- An existing fixture positive that the whole-sentence rule no longer matches moves to `expect: []` on the heuristic path, or to the LLM path when a stub judge returns it. List every moved item in the report.
- Run the covering tests:
  - `uv run pytest tests/test_harvest.py tests/test_records_env.py tests/test_replay.py tests/test_store.py -q -W error`;
  - `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`.
- Then run the full gate:
  - `uv run ruff format --check .`
  - `uv run ruff check .`
  - `uv run mypy claude_bully`
  - `uv run pytest -q -W error`
  - `uv run pytest -q -m slow`
- Commit and report:
  - make one commit, authored by rankinbc1@gmail.com (check the repo-local `user.email`), with a message ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
  - never push;
  - append `## Fix round 4 (commit <sha>, on 5faa77e)` to `task-4-report.md`, with the commands, their outputs, and the list of moved fixture items.
