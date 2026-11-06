# Task 6 carries (rulings and notes the brief cannot know)

- **Task 5 state (ruling from the Task 5 review).** Task 5's fix round refactored `claude_bully/environments/generator.py` after the plan was written:
  - DocPlanner and `generator_problems` share one `_authors(world)` helper;
  - address keys use the corpus's public `norm_url` (`claude_bully/environments/corpus.py`) and a single `_is_url` helper.

  The brief says to replace generator.py's import block. Merge it instead: keep every import the Task 5 code now needs, among them the `norm_url` import, and add the writer's. Do not reintroduce a copied url normaliser or a second author rule. The brief's import block is a minimum, not the whole list.
- **Task 5 fixture module.** `tests/fixtures/generator_stub.py` already exists, from Task 5 (P32). It holds `MINI`, `MINI_ITEMS`, `mini_view` and `generated_doc(**overrides)`. The brief says "Create" it: append the writer stub to the existing module instead, and reuse `generated_doc` wherever a test hand-builds a `GeneratedDoc`.
- **P13 (preflight ruling; the spec wins).** The cache write happens after the `GeneratorFire` line is on disk.
  - `write_fire` returns the pending `(key, reply)` puts on `FireOutcome` instead of writing them.
  - A `DocWriter.commit(outcome)` writes them. Task 7 calls it from `_generate` after `self._record(result.fire)`, through `WorldGenerator`.
  - Reword any docstring or doc line that says the cache is written during the fire, to "once its `GeneratorFire` line is on disk".
  - The brief's tests stay as they are. Add one test proving that `write_fire` leaves the cache untouched until `commit` runs.
- **P28 (preflight ruling).** "Reuters" stays in the test code as the `real_name` lint positive. Lint and denylist positives inside test code and test doubles are exempt from the no-real-names rule, so keep them out of data files, world fixtures and the persona file. `tests/test_real_names.py` must still pass.
- **P33(b) (preflight ruling).** `assert "world_generator" not in load_persona_sheets()` cannot fail, because the loader globs `*.yaml` only (strategies/sheets.py). Drop that assertion, and keep the `NON_PERSONA_FILES` membership check.
- **Second-person lint and the writer prompt (Task 3 carries, binding).** Task 3's `second_person` lint fails any descriptive "you" aimed at the reader. Instructional kinds (`family_faq`, `recovery_guide`) fail often, and every failure carries a repair hint. The brief's persona file, rule 4, says "A FAQ or a guide may give ordinary instructions in its own voice". Amend rule 4 so that it steers the writer:
  - write FAQs and guides in the third person ("visitors", "families", "residents"), or as bare imperatives with no "you";
  - never address the reader.

  The retry's "## Fix these" section must list each failing sentence with its lint message, which carries the repair hint.
- **Hard-wrapped bodies (Task 3 carry).** `sentences()` splits on newlines (claude_bully/metrics/turn.py:11). A hard-wrapped sentence's continuation is therefore linted alone, and it can fail with no anchor. Unwrap paragraph bodies before the lints run: join lines inside a paragraph, and keep blank-line paragraph breaks and line-structured kinds (log lines, ticket header fields). Alternatively, tell the writer not to hard-wrap prose. Pick one, test it, and report the choice.
- **A premise term inside a cast name (Task 3 carry).** The premise pairing fails any instructional "you" sentence that names the overlay cast's "Continuity Placement Office", because "placement" is a premise term. A third-person or bare-imperative FAQ avoids it. Add one writer test over that name, so the steering is pinned.
- **Generator on for real runs (Phase 7 carry, for awareness).** The deterministic `second_person` lint lets 2 to 4 of 15 fresh billboards through per instructional kind. Do not change the lint in this task.
- **Environment.**
  - If `uv` is not on PATH in Git Bash, run `export PATH="/c/Users/Brian.Rankin/AppData/Roaming/Python/Python313/Scripts:$PATH"`, and skip any `export PATH=/c/Users/badmin/...` line in the plan.
  - Put scratch files in `C:\Users\BRIAN~1.RAN\AppData\Local\Temp\claude\b3f956596010799d\7d309c2e-1430-4cb8-9c70-de3f61a002fe\scratchpad\impl-task6\`, and read no other folder there.
- **Docs sync.** Make the `HANDOFF.md`, `docs/02-ENVIRONMENTS.md` and `docs/00-RECONCILED.md` edits the brief names. In `HANDOFF.md`, add "Phase 3 Task 6" to Progress, and update the test counts to your gate's numbers.
- **Gate counts at BASE.** The fast suite is about 8045 passed, 5 skipped and 5 deselected. The slow suite is 5 passed.
- **Commit.** Make one commit, authored by rankinbc1@gmail.com (check the repo-local `user.email`). End the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
- **Docs-sync carries from Task 5.** The HANDOFF.md resume prompt (near line 251) still says to resume at Task 5; make it name the next task after yours. The `GeneratedDoc` line in docs/02-ENVIRONMENTS.md (near line 146) lacks the schema v3 fields (title, url or path, date, author, links_to, used_items, reflexive, redactions, unlock_rung); bring it in line with docs/00-RECONCILED.md:40.
