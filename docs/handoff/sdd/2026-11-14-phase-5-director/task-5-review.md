# Task 5 review: the dry run, the dry_run lint and K12

Reviewer: opus. Task-scoped gate on 40d87e4..855733f (one commit, 855733f). I read the diff once. I went outside it only for the named risks: `runtime.AttemptMarker`, `providers/ledger.py`, `providers/stub.py`, `corpus.searchable`, the YAML load sites and `env_turn` note_turn. I did not edit the checkout. Probes are in `probes-task5/`, and their outputs are in `probes-task5/out_*.txt`.

## Verdicts

- **Spec: PASS, with stated deviations.**
  - Every interface the brief produces exists with its signature.
  - The brief's 16 test functions are present. One of them, the later-fire test, was edited; the edit is justified, see named risk 6.
  - Q20 holds: a separate parametrized case test, 8 near-misses of 15, and 4b's `CASES` assertion unchanged.
  - Every carry has a test.
  - Docs-sync is done: docs/08, docs/00 H, the spec's "As planned", and HANDOFF.
  - The commit author is `rankinbc1@gmail.com` and the trailer is present. No golden file changed (`git diff -- tests/fixtures/golden` is empty).
  - The deviations are all stated under ASSUMED and judged below. One of them, the hit message not naming the document, departs from the brief's text (M-4).
- **Quality: PASS, with fixes (Minor only).** I swept every kill point of every role and saw resume parity hold everywhere. The derived ledger is exact, and the dry run is deterministic across processes. No Critical or Important finding.

Counts: Critical 0, Important 0, Minor 5, Nit 4.

## Named risks

### 1. Resume parity at every K12 kill point; is the derived ledger exact?

Probe `p4_k12_sweep.py`. For each kill point it kills inside call n of one role's double, using the shipped `_killing`, then resumes. It then compares the resumed run with one unbroken run on three things:
- (a) the cells, with `resumed_after_dead_attempt` stripped;
- (b) the ledger as a multiset of (role, cell, rep, turn, status). This is the exactness check for the derived ledger.
- (c) every record file of the run directory, normalized. I dropped the clock fields `ts`, `timestamp`, `*_at` and `*latency_ms`, and the resume records. `p5_what_varies.py` showed that these clock fields are the only ones that vary between two unbroken runs.

| Bundle | Role | Kill points | Result |
| --- | --- | --- | --- |
| good | target | every call, 1 to 60 (covers both calls of each tool step) | 60 of 60 OK on (a), (b) and (c) |
| good | bully | every call, 1 to 52 | 52 of 52 OK |
| good | generator | every call, 1 to 4 (both calls of each fire's pair) | 4 of 4 OK |
| TVS + GEN_EDITS | generator | every real writer call, 1 to 8 (two fires per cell, pair calls) | 8 of 8 OK |
| real_vs_fabricated | target | 29 to 33. Call 31 is the twin's call (`pw_fabricated__t0` turn 13, served by the target double, D-twin) | 5 of 5 OK |
| real_vs_fabricated | generator | 1 (the only real call) | OK |
| real_vs_fabricated | bully | every 17th, 1 to 154 | 10 of 10 OK |
| good | two kills in a row: generator call 2, then target call 30 on the resumed run, then a resume (`p10`) | | OK on (a), (b) and (c) |

Every resumed run had `resumed_after_dead_attempt` set on some cell.

The derived ledger matches the runtime's count. `_drop_dead_lines` (dryrun.py:607) keeps a line when `AttemptMarker(role, line.turn).written(turns, watched_through)` holds. That matches how the ledger stamps `turn`, which I checked in the code:
- a target or responder call gets the target turn's index (runner.py:382);
- a bully call gets the bully line's index (runner.py:533, set before `realize`);
- an after-turn call (generator, twin, harvest) gets `reply.index` (env_turn.py:840, 880). Its owner is `watched_through`, the runtime's own rule (runtime.py:241-251).

A rate-limit line is never owned. Its pause marker is a bully or `neutral_user` turn, never a target turn, and `is_bully_line` excludes the marker. So the line is dropped, which is what the redo needs.

One boundary of the rule: it is exact only because the dry run's judge-side passes are off. Nothing after the turn that is recorded but not asked again (a recorded harvest item, for example) makes a call in the dry run. If a later phase puts a recorded-then-reused LLM call on the dry run's path, this rule would undercount it. N-1 asks for a docstring line saying so.

Verdict: exact at every point probed. The controller's ruling stands.

### 2. The rate-limit resume shifts later turn indices by one

Probe `p7_rate_limit_shift.py`. It used four limit points: target call 4, generator call 2, target call 40 and bully call 5. In every case:
- the cells are equal;
- `dryrun.jsonl` is not written before the resume;
- the per-cell line counts, and so `estimated_calls`, are equal.

What depends on the shifted indices, in the run directory only:
- `rep0.turns.jsonl` has one extra row (27 against 26), and every later index moves by one;
- trigger ids (`trig-8-world_question` for `trig-7-...`), tool call ids (`call-12-1` for `call-11-1`) and a `discovery`'s `path_taken`;
- `analysis/progression.json` (the rung turns) and `rep0.world.json` (`documents`, `docs`);
- the generated documents' `cache_key`, because the writer prompt carries a turn-dependent part. The bodies are equal.

Within the dry run's own output, only one field could depend on an index. `DryRunCell.lint_failures[*].doc_id` is `"<cell>/rep<k>/turn<N>"` (dryrun.py:558), so a fire rejected after a pause would record a different doc id from an unbroken run's. `_buried_hit` compares a call's turn with unlock turns from the same records, so the shift cancels there.

The pause marker is the runtime's established rate-limit design (`_pause_for_rate_limit`, outside this diff), and the stub doubles never raise a rate limit. So this cannot happen in a real dry run; only the test induces it. See M-5.

### 3. Determinism

Probe `p6_determinism.py`. It built the good bundle and TVS + GEN_EDITS at fixed paths and kept pristine copies. It dry-ran them in process A, twice: run 1, then the pristine copy restored and run 1b. It then dry-ran them again in a fresh process B (run 2).

Results for run 1 against run 2, and for run 1 against run 1b:
- 283 files on each side, the same set;
- 265 byte-identical, including `dryrun.jsonl`, every `generated.jsonl`, `tools.jsonl`, `triggers.jsonl`, the cell records and the analysis outputs;
- the other 18 differ only in clock fields: `turns.jsonl` `timestamp` and `latency_ms`, `ledger.jsonl` `ts` and `latency_ms`, `run.json` `created_at`, and `analysis/ledger.json` `mean_latency_ms`;
- the run id is the same across processes.

One real determinism gap across ids is M-1 below (`p10` part b).

### 4. The carries

| Carry | Test | Bites (probe) |
| --- | --- | --- |
| Reasoning key, no leak | `test_the_stubs_reasoning_key_reaches_no_chat_field_record_or_prompt` | yes. In `test_p9_carry_bites.py`, a leak of `entry.reasoning` into the reply text fails it, and so does a leak into `Completion.reasoning_text`. Its judge leg cannot fail, because no judge is called in a dry run (N-3). |
| The two stub rules | `test_a_turns_script_needs_a_non_empty_default`, `test_a_reasoning_value_that_is_no_string_is_refused` | yes. Each asserts the refusal's own message (`stub.py:62`, `:208`, `:258`). |
| R-buried's stray hit | `test_a_stray_buried_search_hit_fails_and_the_shipped_overlay_passes` | yes, in both directions. With `_buried_hit` forced False, the planted half fails. With `named_by_id` emptied, the shipped half fails: the triggered cells' search returns `cpo-review-4471-r3`. |
| budget's dry_run half | `test_an_empty_dry_run_passes_max_calls_and_fails_the_dry_run_lint` | yes. It pins `budget` silent and `dry_run` failing "the dry run holds no cell". |
| NEW-2 | `test_a_yaml_tag_or_nesting_..._never_an_exception` (7 carriers), `test_a_document_front_matter_tag_...` | yes (see below). |
| NEW-3 | `test_a_yaml_anchor_holding_itself_in_an_any_field_fails_schema` and the shared-anchor near-miss | yes (the implementer's mutation M6). The near-miss pins that an anchor used twice is no cycle. |
| The scoped M-1 sentence | spec section 9 (line 272) and section 14 | **partly wrong**: see M-2. |

More on NEW-2:
- The implementer's mutation M5 failed 8 tests.
- I checked that every `safe_load` that lint_bundle reaches goes through `_model`, `_scan_texts`, `config_display_names` or `world._load_yaml`.
- The raw loaders in `config.py:137`, `sheets.py:74`, `rescue.py:112` and `poisoned_well_sheet.py:128` are reached only after `schema` passes, or only by the dry run itself. That is Task 9's carry.
- `p8_deep_nesting.py`: at every depth `safe_load` builds (up to about 490), `_holds_itself` walks without a RecursionError, and the bundle fails `schema` cleanly.

More on the M-1 sentence: `p11_m1_scope.py` shows that in a corpus document's YAML front matter, a folded or plain scalar split by a blank line passes both `real_name_bundle` and Phase 3's `real_name`.

### 5. The 60 sentences, read as a reader

- No name: no person, outlet or place, real or invented. The only person word is "Someone left a scarf on the bench."
- No "you": the closed test pins this.
- No billboard. No sentence announces, advises, dares or points at evidence. They are a facilities notice board: keys, bins, the kettle, the lift. "Spare keys hang by the back door." is the only one that reads as where-something-is, and it is about a building, not a trail.
- The bully line, "I hear you. Go on.", invites the target to keep talking. It dares nothing and names nothing. The spoken lines ("Thanks, that came back.", "Thanks, I have read it." and the close) are neutral.
- No repeated sentence. There is near-repetition in the bank, though (N-2):
  - "A stack of chairs blocks the corridor." against "Chairs were stacked after the meeting." (dryrun.py:135 and :147), the same fact twice;
  - "reception" three times (:95, :140, :148);
  - "kettle" twice (:89, :123), "car park" twice (:90, :138), "drawer" twice, "shed" twice, "bins" twice.

  Five sentences are drawn per document, so one body can hold both chair sentences.
- Register: British office ("car park", "lift", "gritted", "porters' desk"). It sits fine beside every checked-in world.

Only stub targets ever read these sentences. The reader-eye bar is met.

### 6. The edited later-fire test

The brief counted `writes` as every generator ledger line. On TVS + GEN_EDITS that is 16 lines, 8 of them `cached`, because the t1 cells replay the t0 fires (`p1_baseline.py`). The brief's `last` case therefore aimed its kill at call 16 of 8 real calls. The kill never fired, and `pytest.raises(_Killed)` would fail. Excluding the `cached` lines is the right count, so the edit is justified. The added assertion that every clean fire commits is also right: it pins the title-only link line.

The edited test still meets the brief's intent, but only through its `last` case. `test_p9_carry_bites.py` swaps in a double that draws from a count it keeps, which is the regression R-dryrun-pure guards:
- `last` (call 8, the second fire of the t0 control cell) fails, as it should;
- `second` (call 2) passes, because call 2 is the second document of the first fire's pair. A resume redoes that whole fire, so a counting double redraws the same bodies.

So the `second` case pins a kill inside one fire, not a later fire, which its id and the test docstring say it pins. See M-3.

## Findings

### Minor

#### M-1: A resumed dry run can read another id's generated cache

In `dryrun.py:666-671`, `dryrun/_cache` is removed only before a run whose directory does not exist; a resume keeps it. Probe `p10` part (b) shows the problem:
1. Content A is killed before its fire.
2. The bundle is edited (id B), and B is killed after its first cell's fire was cached.
3. The edit is reverted, giving id A again. Its directory exists, so `_cache` stays.
4. A's resume reads B's cached reply. `ferry_triggered__t0` records `generator: {"cached": 1}`; the unbroken run records `{"written": 1}`.

This breaks the binding point that a resumed run equals an unbroken one, and it breaks the property `test_a_changed_bundle_gets_a_new_run_id...` asserts. The effect is confined to the status counts and the ledger line's status, because a hit needs identical prompt bytes and so gives an identical reply.

Fix: own the cache by run id.
1. Write `dryrun/_cache/OWNER` holding `run_id` when a run starts.
2. At every `dry_run`, remove `_cache` when `OWNER` is absent or names another id.
3. Add a slow test of the A-killed, B-killed, revert sequence.

#### M-2: The scoped M-1 sentence overstates the catch

Spec section 9 (line 272) and section 14 say a split phrase "in a folded (`>`), plain or quoted YAML scalar ... is caught". But `_scan_texts` (bundle_lints.py:586) parses only `.yaml` files, so a corpus document's YAML front matter (a `.md` file) is read as raw text only.

Probe `p11` used `title: >\n  Pier cafe, washington\n\n  post copy`, and the same split as a plain scalar. Both pass `real_name_bundle` and Phase 3's `real_name`, while the one-line control fails both.

Fix, either one:
- parse the front matter of `worlds/*/corpus/*.md` in `_scan_texts` too, for example by `parse_document` over the text inside the try already there, adding its string fields to the parsed values; or
- extend the residual sentence to "a markdown body, a YAML literal block, or any scalar of a corpus document's front matter".

The first closes the gap and keeps the sentence true.

#### M-3: The later-fire test's `second` case does not kill a later fire

At tests/test_dryrun.py:296, call 2 is the second call of the first fire's pair, so a counting double passes it (`test_p9_carry_bites.py`). Only `last` pins R-dryrun-pure.

Fix, either one:
- aim `second` at the first call of the second fire: the first writer call of the first cell whose turn is greater than the first fire's turn, read from the clean ledger (call 3 here); or
- rename the case `within_a_fire` and add that case beside it.

#### M-4: The hit's lint message names no document

At bundle_lints.py:1311 the message names no document, but the brief says "its message names the document and says so". `DryRunCell` holds a bool, so the reviewer must dig the id out of `tools.jsonl`. This is an ASSUMED deviation, and the reason is sound: the lint reads only the cells.

Fix: add a default-valued `buried_search_docs: list[str] = []` to `DryRunCell`. This is an additive plan-record change at PLAN_SCHEMA_VERSION 1. Fill it in `_buried_hit`, and name the documents in the message.

#### M-5: A rate-limit resume equals the unbroken run only at the cell level

The records shift by one index (named risk 2). `DryRunCell.lint_failures[*].doc_id` embeds the turn (dryrun.py:558), so a fire rejected after a pause would differ from an unbroken run's. No real dry run can rate-limit, since the doubles never raise.

Fix, either one:
- key the fire's doc_id by the fire's ordinal among the rep's fires rather than its turn; or
- state in `dry_run`'s docstring and the spec's D-K12 bullet that a rate-limit resume equals the unbroken run's cells, not its records. Then make the rate-limit test also compare the `_generated` bodies (which hold) and say why the records differ.

### Nit

- **N-1:** `_watched_through` (dryrun.py:601) rebuilds the runtime's state path from a copied literal: `_RUNTIME_DIR = "environment"` at :159, where the runtime's own is env_turn.py:1549. A move there silently makes every after-turn line look dead, though the K12 tests would catch it.
  - Export the directory name from `env_turn`, or read it through the runtime.
  - Also say in `_drop_dead_lines`'s docstring that the rule is exact only while every after-turn call the dry run makes is asked again on resume (named risk 1).
- **N-2:** The near-duplicate sentences listed in named risk 5. Replace "Chairs were stacked after the meeting." and one "reception" line with sentences about other things.
- **N-3:** The reasoning test's judge leg is vacuous. `sent["judge"]` is always empty because the stub judge is never asked in a dry run; tests/test_dryrun.py:523 asserts only the bully and generator. Say so in the docstring, so the judge clause is not read as tested here.
- **N-4:** The strict `turn < call.turn` of `_buried_hit` (dryrun.py:503) is the right reading, since a rung fires after its turn's calls. But no test pins it: a `<=` mutant survives every shipped test, because the shipped searches never share a turn with an unlock. A cell-level unit test of `_buried_hit`, with an unlock on the call's own turn, would pin it.

## ASSUMED decisions and concerns

| Item | Judgment |
| --- | --- |
| Link line by title alone | Accept. Measured (9 of 39 8-grams with the address) and pinned by the clean-fire assertion. The brief's "and address" bought nothing the lints read. |
| Drop dead-attempt lines from the dry run's ledger (D-K12) | Accept, as ruled. Exact at every one of about 140 kill points probed, plus a double kill. Only the dry run's own scratch ledger is rewritten. |
| The later-fire writer count excludes `cached` | Accept, justified (16 against 8 lines, so the brief's `last` never fired). See M-3 for the `second` case. |
| `searched_document` reads the buried rule, not `CorpusIndex.searchable` | Accept. It matches `searchable` on the shipped code (`visible` already excludes the purged), and it is the only reading under which the leaky-search test can record a hit. |
| A hit counts only rungs fired strictly before the call's turn | Accept. A rung fires in `after_target_turn`, after the turn's calls. Untested boundary (N-4). |
| `DryRunCell` aggregated over reps | Accept. The rules are reasonable and documented in the spec's "As planned". |
| The hit message without the document id | Accept the reason; fix per M-4. |
| `fetch` for a url, `read_file` for a path, no read without the tool | Accept. |
| The script-length clause skips an unwalkable ladder | Accept. `ladder_walk` already fails it, and `lint_bundle` must never raise. |
| world.py and test_stub_turns.py outside the Files list | Accept. The NEW-2 and Task 2 carries need them. `YAML_BUILD_ERRORS` also lists `TypeError`, which its comment does not name; it is harmless, but the comment should name it. |
| Concern 1: the derived ledger | Verified exact (named risk 1). |
| Concern 2: the rate-limit shift | Confirmed. Cells and estimates are equal; the records shift (named risk 2, M-5). It is inherited from the runtime's pause marker. |
| Concern 3: two departures from the brief | Both justified (named risk 6, the link line). |
| Concern 4: the 60 sentences | Read. No name and no billboard; N-2 near-repeats. |
| Concern 5: `dry_run` raises on an unwalkable ladder | Accept. It is carried to Task 9 (run it after `schema` and `ladder_walk` pass). |

## Probes

All are in `probes-task5/`. Run them with `uv run python <probe>`, or with `uv run pytest` for `test_p9_*`.

- `p1_baseline.py`: one dry run each of the good bundle and TVS + GEN_EDITS. It shows:
  - the ledger's make-up: good bundle 60 target, 52 bully, 4 generator; TVS 184 target, 144 bully, 8 generator ok plus 8 cached;
  - every search and read;
  - every generated document.
- `p2_generated_search.py`, `p3_generated_false_hit.py`: could the scripted search serve a generated buried document (unlocked by the generator's pseudo-rung) and read it as a stray hit? It does not: generated buried documents are not served by search even when their title shares terms with the query. No finding.
- `p4_k12_sweep.py` (outputs in `out_p4_*.txt`): the K12 sweep (named risk 1).
- `p5_what_varies.py`: what differs between two unbroken runs (clock fields only).
- `p6_determinism.py` (data in `work_p6/`): the cross-process byte comparison (named risk 3).
- `p7_rate_limit_shift.py`: the rate-limit shift (named risk 2).
- `p8_deep_nesting.py`: NEW-2 and NEW-3 at the nesting boundary.
- `test_p9_carry_bites.py`: the mutation checks (named risks 4 and 6). Five pass as expected. `second` survives a counting double (M-3).
- `p10_two_kills_and_cache.py`: the double kill (OK) and the cross-id cache (M-1).
- `p11_m1_scope.py`: the scoped M-1 sentence (M-2).

Tests run, scoped rather than the full suite, all with `-o faulthandler_timeout=60`:

| Run | Result |
| --- | --- |
| `tests/test_dryrun.py tests/test_stub_turns.py -m "not slow"` | 39 passed in 30 s |
| `tests/test_dryrun.py -m slow` | 16 passed in 129 s; the slowest is 17 s (the later-fire cases); no hang |
| `tests/test_bundle_lints.py -k "dry_run or yaml or empty_dry_run or anchor"`, slow included | 51 passed in 36 s |
