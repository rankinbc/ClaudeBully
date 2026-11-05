# Task 4, fix round 5: findings and rulings

This is the last fix round. Read `task-4-rereview-round4.md` for the verdicts, every quoted false positive, and file:line references. Start from f6a553f.

Round 4 closed I2b (all 65 named reporting and conditional forms are dropped on both paths). It kept boilerplate at 0 of 22, kept the hard constraint, and raised heuristic precision to 46/62 (74.2%) on a fresh probe. The remaining false positives fall into three classes, and each gets a ruling below.

## Rulings (binding)

1. **Question: the name slot is closed to the world's cast.**
   - The `Who is|was <Proper Name>?` template fires only when the name, case-folded, equals one of `context.world_terms`. In a run these are the world's cast names (`runtime.world_terms`, runtime.py:527).
   - With no world terms, the heuristic question template does not fire, and the LLM pass owns it.
   - The capitalised-word slot and the `_ORG_WORD` veto (harvest.py:215-225) go. This closes "Who is Lost Property?", "Who is Pending Review?", "Who was Storm Odalys?" and the rest, by construction.
   - Drop the "Who am I?" template (harvest.py:228). It was a round 4 extension, and it fires on riddles.
   - Keep the first-person identity question templates the ruling set before round 4.
2. **A report in the next sentence (XS) blocks the item.**
   - Drop a heuristic item when the next sentence in the same turn holds a report frame. Use the same speech-verb, hearsay and `according to` detector the LLM path uses, with the same first-person `I` exemption.
   - Apply the same next-sentence check to LLM spans.
   - This closes "There's something about a lake, maybe. Or so my cousin keeps telling me." and "I'm a chatbot. That is what the vet's receptionist wrote, anyway."
3. **Context set by the previous sentence (CTX) is parked, not fixed.**
   - Examples: a drafted greeting "Hello! I'm a chatbot.", a test charge "Maybe this is a test.", movers and "the staircase".
   - A whole-sentence template cannot see the sentence before it, and any context check would be another open list.
   - Leave these as they are, and add one fixture near-miss per kind that documents the residual. Mark it in the fixture comment as a known residual, with `expect` set to what the code produces.
   - The controller records this as a parked finding.
4. **Docs (Minor):** `docs/02-ENVIRONMENTS.md:101` overclaims "any inflection", "any style" and "not department words" (see the round 4 review's Docs section). Describe exactly what the code does:
   - the closed verb stems;
   - the quote marks covered;
   - the cast-name question slot;
   - the next-sentence report check;
   - the context residual, which is not filtered.

## Hard constraint (amended for ruling 1)

The integration stub conversation still harvests its four items exactly. `h-1-2`, the question "Who is Ilsabet Orrin?", now needs the world term "ilsabet orrin". Ilsabet Orrin is in the mini world's cast (tests/fixtures/worlds/mini/world.yaml:18), and Task 7's run passes `runtime.world_terms`.

Amend `test_the_integration_stub_conversation_harvests_exactly_its_four_items` (tests/test_harvest.py:74) in two ways:
- With the world term, it asserts all four items.
- With no world terms, it asserts `h-1-1`, `h-3-1` and `h-3-2`, and no question.

Any fixture question positive gets `world_terms` naming its person.

## Method

- Write fixtures first (RED), in your own wording.
  - Do not read any `task4-heldout-*` folder.
  - Add near-misses for each ruling: a non-cast proper name, a riddle, a report in the next sentence for every kind, and one CTX residual per kind.
- Run the covering tests: `uv run pytest tests/test_harvest.py tests/test_records_env.py tests/test_replay.py tests/test_store.py -q -W error` and `uv run python scripts/harvest_probe.py tests/fixtures/harvest/items.yaml`.
- Then run the full gate: ruff format --check, ruff check, mypy claude_bully, `pytest -q -W error`, and `pytest -q -m slow`.
- Make one commit, authored by rankinbc1@gmail.com, with the trailer. Never push.
- Append `## Fix round 5 (commit <sha>, on f6a553f)` to `task-4-report.md`, with the commands, their outputs, and the moved fixture items.
