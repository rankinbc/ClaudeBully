# Task 7 review: e48783f..6c4c1f6

The diff was read in three passes (lines 1-450, 450-900, 900-1317). Named checks outside the diff, one per risk:
- Renderer shapes against the parser's regexes: `claude_bully/analysis/replay.py:228-239` (`_speaker_line`) and `:352-406` (`_record_block`), plus the field types in `claude_bully/enums.py` (Speaker, Phase, Layer) and `claude_bully/records_env.py` (FireStatus, Rejection, `AuthorityCall.discovered_via`, `TriggerEvent.classifier`).
- What the pairs form shows against what the judge was given: `claude_bully/metrics/judge.py:134-162` (`neutralize_transcript`, `build_pair_prompt`) and `:225-270` (`judge_pair`, so `verdicts[0]` is the condition-as-A ordering), with `run_analysis._judge_all` for the window (`strategy.judge_window(conv)`).
- The idle recompute against current signatures: `claude_bully/environments/idle.py:596-602, 649-654`, and the runtime's own call at `claude_bully/runner/env_turn.py:662-676`.
- Where harvest runs: `claude_bully/runner/env_turn.py:751` (only through `generator.harvest_turn`).
- Spec sections 7, 8 and section 10's replay-parsing line; `scripts/authority_mutation/heldout.py:195-208` for its print layout.

### Spec Compliance
- Issues found (all of them follow the brief's code or tests; none are code drift):
  - Missing, plan-mandated: the pairs form does not give the rater the per-pair `win_condition` and `resilient_behavior` that `build_pair_prompt` gave the judge (`scripts/judge_calibration.py:751-758`). The brief's test pins the item keys (`tests/test_audit_forms.py:1048`). See Important 1.
  - Misunderstood, plan-mandated: section 7 asks for fired items plus a sample of cue-present turns, capped at 60. `(fired + cues)[:cap]` (`scripts/detector_audit.py:484`, `:591`) returns no cue items once a family fires 60 times, and takes the fired items in sorted cell order rather than sampling them. See Important 2.
  - Misunderstood: the harvest form's not-fired items come from every target turn of every conversation (`scripts/detector_audit.py:577-589`), including cells where harvest never runs. See Important 4.
  - Missing, plan-mandated, Minor: section 7's cue list includes "an authority call in reach". The authority cue is a regex lexicon only (`scripts/detector_audit.py:413-417`).
  - Minor: section 7 says `--score` prints "in the layout `heldout.py` already prints". `heldout.py` prints `OK/MISS [cls] 'text' got want` lines and per-class `k=n/total` counts (`scripts/authority_mutation/heldout.py:195-197`). `report` prints `kind: fired N, precision P, recall R` with the misses indented (`scripts/detector_audit.py:647-654`). This is the brief's layout, and the implementer flags it (concern 5).
  - Verified compliant:
    - The parser handles all eleven kinds. I checked each `_speaker_line` and `_record_block` branch against `_SHAPES` (`claude_bully/analysis/replay.py:168-220`). The bare `UNLOCK sanctuary` and `HOOK x planted@3` forms are None (test at `tests/test_replay_parser.py:1272-1285`).
    - The P13 docstring is at `replay.py:232-236` and is pinned by the fixture at `tests/test_replay_parser.py:1166-1177`.
    - The no-other-parser test is at `tests/test_replay_parser.py:1309-1317`.
    - P16 `classifier` is set at `scripts/detector_audit.py:473`.
    - P35a: `idle_turn_rows` lives in `detector_audit.py:497` and is imported by `judge_calibration.py:725`.
    - The idle ruling: no hooks and no task (`detector_audit.py:509`), and the form says so (`IDLE_NOTE`, `:398-402`, written at `:605-606` and `judge_calibration.py:806`).
    - The calibration ruling: A is `verdicts[0]`'s order, the condition (`judge_calibration.py:748, 754-755`), and the scorer compares against that verdict (`:787`).
    - P34b: the CLI test parses the printed JSON and asserts `pairs == 0` (`tests/test_audit_forms.py:1113-1114`).
    - P25: the harvest `any(not fired)` assertion is kept (`tests/test_audit_forms.py:999`).
    - Carries 1 and 2: HANDOFF lines 75-76; `run_analysis.py:280-282`.
    - Docs sync: HANDOFF, docs/00 line 308, and the spec's As-planned Task 7 block at lines 336-341.
    - Test counts match the brief: 4 parser tests (30 items) and 10 audit tests, for +40.
- Cannot verify from diff:
  - The commit's author email and the `Co-Authored-By: Claude Fable 5.1` trailer. Controller: run `git log -1 --format='%ae%n%B' 6c4c1f6`.
  - LF line endings on the four new files. Controller: run `git ls-files --eol` on them.
  - The gate's 0-warning claims (8316 passed, 6 slow). The report states them but no log is attached. Controller: check the logs if any were kept.
  - That `scripts/judge_calibration.py` resolves `scripts.detector_audit` when run from outside the repo root. The report says it was tried. Controller: run `uv run python scripts/judge_calibration.py --help` from another cwd.

### Strengths
- The parser matches the renderer exactly on every branch I checked:
  - the pause marker (`replay.py:230`)
  - all three flag forms, including `behavior=-` (`:232-238`)
  - Sanctuary and ladder unlocks with `role_shift` (`:368-379`)
  - `followed@-` (`:363-364`)
  - `TRIGGER` with the `heuristic|llm` Literal (`records_env.py:252`)
  - `DISCOVERY` with an optional title and an optional `via`
  - `GENERATOR` statuses and rejections, all `\w+` (`records_env.py:135-136`)
  - `GENERATED` with comma-joined uses or `-`
  - `AUTHORITY` with its Literal `discovered_via` (`records_env.py:199`)
  - `CROSSOVER` with and without a span.

  The round-trip test runs on a real rendered stub replay (`tests/test_replay_parser.py:1288-1306`), not only on hand-typed strings.
- `write_pairs` locates the pair from the judgement's own `condition_cell_id`, `condition_rep`, `control_cell_id` and `control_rep` (`judge_calibration.py:744-747`), not from `rsplit` plus `control_for`. That is exactly the pair the judge saw. The window is the same `strategy.judge_window(conv)` that `_judge_all` passed.
- The opaque `pair-<n>` id with the mapping in the key (`judge_calibration.py:750, 762`), and a test that no judged cell id appears on the form (`tests/test_audit_forms.py:1058-1059`).
- The idle recompute's arguments match the runtime's own `idle_context` call (`env_turn.py:670-676`), with the same `cell.target.display_name` source. The private-file addition (`detector_audit.py:487-494`) makes a `write_private` turn recompute as the runtime would have, and does not contradict the ruling.
- `_context` uses `is_pause_marker` (`detector_audit.py:432`), not the raw meta key.
- Every text on every form comes from `chat_text` or `neutralize_transcript`, so nothing on the reasoning channel reaches a form.
- The implementer caught that the brief's `inconsistent == 0` cannot hold on the stub judge. The test now compares against the key's own count (`tests/test_audit_forms.py:1078-1079`) instead of bending the fixture.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The pairs form withholds the judge's rubric** (plan-mandated). `scripts/judge_calibration.py:751-758`; key set pinned at `tests/test_audit_forms.py:1048`.
   - What is wrong: `build_pair_prompt` (`metrics/judge.py:147-162`) gave the judge four things beside the two windows: the tactic's `win_condition`, its `resilient_behavior`, the 0-3 scales, and the rule that "pleading and lecturing count against resilience". The form gives the rater none of them, yet asks for `resilience_a` and `resilience_b`, and `--score` reports the mean absolute gap on them.
   - Why it matters: the rater scores "closeness to the resilient behavior" without the behavior's text. The gap then measures rubric mismatch as well as judge error. Section 8's remedy, revising `build_pair_prompt` once on a miss, assumes the human read the same instructions. This is the ruling "the rater is as blind as the judge was" failing on parity: the rater is less informed than the judge, not equally so.
   - Fix: add per-item `goal` and `resilient_behavior` from `conv.win_condition` and `conv.resilient_behavior`. The judge saw these too, so they reveal nothing about which transcript is the condition. Add one top-level `instructions` field quoting the scales and the pleading/lecturing rule (or the prompt body minus the two windows). Relax the key-set assertion to include the new keys.
2. **The cap starves the recall sample and biases the precision sample** (plan-mandated). `scripts/detector_audit.py:483-484`, also `_harvest_items` `:590-591` and `_idle_items` `:551`.
   - What is wrong: `(fired + cues)[:cap]` keeps the fired items in sorted `(cell, rep)` order and appends the shuffled cues after them. A family that fires 60 or more times gets zero cue items, and its 60 fired items all come from the alphabetically first cells.
   - Why it matters: this is the expected case on rung 1 for the environment family, since `tool_used` fires on every tool turn. Recall is then `n/a` for every type except misreads of fired items, and precision is measured on two or three cells. Section 7's "estimated recall on cue-present items" cannot be computed.
   - Fix: sample the fired items with the seeded rng too, stratified by conversation, into a fixed share of the cap (say half), then fill the rest from the shuffled cues. Record the per-family fired and cue totals on the form so a scorer can weight the estimates.
3. **The cap and seed test asserts nothing** (plan-mandated). `tests/test_audit_forms.py:981-985`.
   - What is wrong: the position family is empty on `stub_env_run`, as the implementer's own report says. `len(items) <= 3 and small == again` therefore holds for `[] == []`.
   - Why it matters: the cap cut and the seeded shuffle are untested, so a regression in either, Important 2's fix included, would pass.
   - Fix: use the environment family, which has 6 fired items plus cue items on the stub, with a cap below its item count. Assert `len(items) == cap`, that the same seed gives the same sample, and, where there are 2 or more cues, that another seed gives a different cue order.
4. **Harvest not-fired items include turns harvest could never have fired on.** `scripts/detector_audit.py:577-589`.
   - What is wrong: every target turn of every conversation without a `HarvestItem` becomes a not-fired candidate. Harvest only runs through the generator (`env_turn.py:751`, `generator.harvest_turn`), so on a mixed run (generator arms beside off arms and control cells, the shipped rung 3 shape) most of these candidates come from cells with no harvester. A rater who labels one with a kind scores an `fn` the detector could not have caught.
   - Why it matters: the harvest recall printed for a real run is understated by construction. The test passes only because `generator_run` is all generator cells (`only="env_grader*"`).
   - Fix: take empty candidates only from conversations whose stream holds a `GeneratorFire` or a `HarvestItem`, or whose recorded environment config enables the generator. Add a test on a run with a generator-off cell.

#### Minor (Nice to Have)
1. `scripts/detector_audit.py:398-402`, the `IDLE_NOTE` wording. "(the records hold neither)" is wrong for the task. The runtime's task prompt is the last `Speaker.task` turn's text (`env_turn.py:667-668`), which is in the transcript. The ruling to leave it out stands; reword to "not reconstructed".
2. `scripts/judge_calibration.py:778-792`, malformed labels.
   - A `more_resilient` of `a`, ` A ` or `C` counts silently as a disagreement.
   - A `label:` left null raises `AttributeError` at `.get`.
   - Fix: normalise the letter (strip and upper-case, keep `tie`), reject anything outside {A, B, tie} with an error that names the pair, and treat a null label as unfilled.

   `score_form` likewise turns a typo label (`tool_usd`) into a new type that has only fns (`detector_audit.py:614-617`). Warn on a label outside the family's known types.
3. `scripts/judge_calibration.py:737`: a run with no `analysis/judgements.json` (never analysed, or `--no-judge`) silently writes an empty form and prints "0 pairs". Say "no judgements.json; run `analyze` with the judge first" and exit nonzero.
4. Spec section 7 Labels: "the reviewer ... labels every item ... blind to `fired`". The form carries `fired`, `event`, `span` and `classifier` inline (`detector_audit.py:466-475`), and a turn with two events gives two items with identical text. A blind labeller cannot tell the two items apart, and one label per (turn, event) item double-counts on such turns. The spec's own Candidates paragraph puts `fired:` on the form, so this is spec tension, not drift. Consider a `--blind` view for 7b: one item per turn, the detector columns stripped, a list label.
5. `claude_bully/analysis/replay.py:243`: the blanket `v != ""` filter, there to drop an empty `flags`, also drops a matched empty `docs` (`UNLOCK x -> [] (by y)`) and empty spans (`TRIGGER c "" (...)`, `HARVEST k ""`). Consumers then get a missing key, not "". Filter `flags` alone.
6. `replay.py:199`: a `DISCOVERY` title containing `"` makes the whole line None (`[^"]*`). Generated-document titles can contain quotes.
7. `replay.py:232-236` (docstring): the renderer writes `turn.text`, `evidence_span` and harvest spans raw, so a multi-line reply spills onto unmarked lines. The parser reads only the first line's text, and a continuation line that begins with a record keyword would be misread. This edge is the same class as P13's and could be stated beside it. No consumer exists this phase, which is why it is Minor.
8. `tests/test_replay_parser.py:1309-1317`: the guard catches `"UNLOCK ` and `'UNLOCK ` but not `r"^UNLOCK`, `"UNLOCK\\s"` or `"^HOOK"`. This is the plan's literal-based ruling; a regex-shaped check (`["']\^?(UNLOCK|HOOK)\b`) would be closer to the spec's "matches the line shapes".
9. `replay.py:223-228`: `ReplayLine` is `frozen=True` with a `dict` field, so `hash()` raises `TypeError`. Use a `Mapping` held as a `MappingProxyType`, or drop `frozen`. The shape is the brief's.
10. Coverage gaps:
    - P16's attr-present path (`classifier: llm`) is never exercised, since every stub event lacks the attr.
    - The idle `heuristic` value is never checked. On a stub idle run with no hooks and no task, every `classifier == "heuristic"` row should have `heuristic == final`, a cheap correctness pin for the recompute.
    - The harvest scoring branch (`ok` as tp; `ctx`, `xs2` and `other` excluded from the types) has no test.
    - `heuristic_agreement` is never asserted.
    - There is no fixture for `GENERATED ... uses=-`.
    - The round trip covers only `stub_env_run`; `generator_run`'s replay would exercise `GENERATOR`, `GENERATED` and `HARVEST` on rendered text.
11. `tests/test_audit_forms.py:1058`: the no-cell-id assertion checks only the condition cells. Add the control cell ids too.
12. Blindness residual, ruling-mandated: A is always the condition. The script docstring (`judge_calibration.py:699-701`) and the spec say so, and the judge was not told it. A rater handed the form alone stays blind; a rater who reads the docstring does not. Hand the reviewer the form only, and say so in the 7b runbook.

### On the two blindness questions
- (a) **The opaque `pair-<n>` id: equally blind. Not a defect, and the right departure from the brief.** The judge saw no cell id. The brief's `<cell>/<rep>` would have named the tactic (`captor_s2__t0`) and, since A is always the condition, told the rater which transcript is which. The rater would then have been less blind than the judge, against section 8's "blind to the same things" and the ruling. The opaque id restores parity, and the key keeps the mapping. The one residual is the fixed A-is-condition order (Minor 12). The ruling mandates that order, and it leaks only to a rater who reads the docs.
- (b) **The missing `win_condition` and `resilient_behavior`: the rater is more blind (less informed) than the judge. That is a defect.** It does not break the letter of the blindness sentence: nothing the judge was denied is shown to the rater. It does break the ruling "the rater is as blind as the judge was", which is a parity rule. The calibration compares the rater's resilience scores and winner against the judge's, and the judge scored against criteria the rater never sees. Withholding them confounds the agreement and the gap with a rubric difference. Giving them to the rater would not unblind anything, because the judge saw them without being told which transcript was the condition. This is Important 1, plan-mandated.

### Assessment
Task quality: Needs fixes
Reasoning: The parser, the scripts' wiring and the docs are faithful and well tested on real stub records. But the forms would mislead 7b in three places: the rater scores resilience without the judge's rubric, the cap leaves no recall sample on any high-frequency family, and the harvest recall is understated on a mixed run. One mandated test also asserts nothing, and all four Important items need a small fix before rung 1 uses the forms.
