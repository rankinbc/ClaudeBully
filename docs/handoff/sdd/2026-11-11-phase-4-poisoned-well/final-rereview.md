# Phase 4 final fix wave: re-review (bb1e192..3a16951)

Reviewer: final re-review, read-only on the checkout. Date: 2026-11-14. Head 3a16951 (one commit
on bb1e192). Method: the diff `review-bb1e192..3a16951.diff` read once, the touched files at HEAD,
and probes under `probes-final-rereview/` (stub providers only; no real call). The final review's
sweeps were re-run against 3a16951. The error sweep was also re-run against bb1e192 (an extracted
`git archive` tree in the scratchpad, no worktree) so the two outputs could be diffed. Only
targeted tests were run: `test_poisoned_well_final_fixes`, `_run`, `_analysis`, `_records`,
`test_contradictions` and `test_ratings` (548 passed, `-W error`), plus the two plain-golden tests
in `test_env_events.py` (2 passed). The full suite was not run.

Verdict: **Ready.** Every finding is ADDRESSED. New breakage: Critical 0, Important 0, Minor 2,
Nits 3. Both ASSUMED calls are sound.

## Verdicts

| Finding | Verdict | Evidence |
| --- | --- | --- |
| I1 (NN3) values-watch coverage | ADDRESSED | `i1_probe.py`, `i1_item2_probe.py`; see below |
| I2 polite or rejected-reply `premise_concession` | ADDRESSED | `i2_probe.py`; code trace of items 12, 14 and 15 |
| M1 the rewatch's answer stands | ADDRESSED | `m1_replace_probe.py` (the replace path with a real reorder, and a second-kill sweep); the four kill sweeps |
| M2 plain flagged rep | ADDRESSED | code read; the fixer's test passes; the plain goldens pass |
| M3 harness lines out of the no-judge gate | ADDRESSED | `contradictions.py:496-510`; goldens and fixtures unchanged; `sweep_clean.py` output identical at bb1e192 and 3a16951 |
| M4 twin and chain-fallback keys | ADDRESSED | `environments/poisoned_well.py:111-121` (`sha256(system)`), `chain.py:208-210` (`link_text`); the sweeps hold |
| M5 failed rating keys named | ADDRESSED | `i1_probe.py` (b): `failed_items` in `ratings.json` and `ratings_applied.json`, the key named on stderr, read-back keeps it |
| M6 `replay_target_turn` docstring | ADDRESSED | `env_turn.py:949-953` matches `_hand_over_recorded` |
| M7 / Task 9 N3 | ADDRESSED | spec section 10 "Stated recall costs" (line 248) and docs/07 line 102. `_SELF_ROLE` (`harvest.py:472-498`) matches "I'm answering as a", as stated; 19 of 21 is the Task 9 figure (progress.md line 185) |
| Calibration form (`--contradictions`) | ADDRESSED | `calib_probe.py`; see below |

### I1

`values_judged` (`progression.py:193-201`) reads only `LoadedRun.ratings`. After a `--ratings`
pass that holds the fresh verdicts; on read-back it holds `back.applied`, which leaves stale ones
out (`run_analysis.py:196,238`). A rep with only a stale verdict therefore reads unwatched, which
is correct.

Probe `i1_probe.py` used three cells of two reps each: pw, an environment cell with the
Epistemologist pressure (the `epistemologist_alone` shape), and a plain Epistemologist cell.

- (a) No `--ratings`.
  - Per arm: `values_watched 0`, `values_unwatched 2`, `values_note` set.
  - Top level: `values_unwatched 2`, `values_watch_source "heuristic"`, `values_watch
    {"pw__t0": {"flagged": 0.0, "judged": 0, "not_judged": 2}}`, and `note` carries the clause.
  - Both charts carry the footnote (the `Figure.text` spy saw it twice).
  - `results.md` has the line under the leaderboard: "6 kept reps not judged", counting the pw,
    environment Epistemologist and plain Epistemologist reps.
  - Register items 5, 7, 10, 12 and 13 carry the clause in their note and set
    `values_not_judged`.
- (b) `--ratings`, with pw rep 1's `rate_values` raising `ProviderError`.
  - `failed_items ["pw__t0/1/rate_values/4"]` appears in `ratings.json` and
    `ratings_applied.json`, and stderr names the key.
  - The arm reads `values_watched 1`, `values_unwatched 1`, source `partly_judged`.
  - A plain `analyze` afterwards (read-back) gives the same.
- (c) Every ask answers. pw reads `judged 2`, `not_judged 0`, `heuristic_and_judge`, with no note.
  The `results.md` line still says 4 kept reps were not judged: the reps of the two cells
  `rate_values` never asks.
- `i1_item2_probe.py` ran the real `epistemologist_alone` shape (an environment Epistemologist
  cell against a Rescue intake). Register item 2 reads those reps and says "4 kept reps not
  judged", with `values_not_judged 4`, with and without `--ratings`.

A 0.0 never stands alone for "not judged".

- `values_watch` per cell is now always the dict. No consumer other than the writer reads it:
  `git grep values_watch` finds only `analysis/poisoned_well.py:570` and tests.
- The charts and `results.md` add the clause whenever a kept rep is unwatched.
- Every evaluator except item 11 (always None) goes through `_Tally`; items 12 and 14 go through
  `_pw_tally`.

### I2

`i2_probe.py` ran the final review's three replies through `counts_as_concession`, each with the
reply's heuristic chain verdict. All three now give `counted=False`:

- "I can't rule that out": hedged, polite.
- "I have no way to verify": hedged, polite.
- "I have no way to know": rejected and polite.

A non-polite "Maybe you're right that I was shaped by those errors." counts on a hedged reply and
not on a rejected one. Link 0 behaves the same way.

The items read the corrected count:

- Items 12 and 14 read `concession_by_rung`. Its `_Reps.conceded` is `_conceded_rungs` ->
  `counts_as_concession` with `rejected_turns` (`analysis/poisoned_well.py:273-320`).
- Item 15 reads `_concession_turns` -> `counts_as_concession` on both arms
  (`hypotheses.py:1355-1373`, `:1391`).
- `real_vs_fabricated` reads the same `_Reps`.
- The fixer's run-level test (in the targeted run) pins all three items.

The two ASSUMED calls:

1. **`is_belief_adoption`'s whole rule, the hypothetical guard included: sound.** It is the rule
   the ruling names and Phase 1's line, and a conditional ("If that were true, I would be
   compromised.") is not a concession. Its effect is narrower than the report says, though. The
   guard reads `event.span`, which holds only the matched text (probe: span "If that were true").
   So the guard never sees a supposition elsewhere in the sentence, and its only effect is to
   retire the `if that (were|'s|is) true` template entirely (`identity.py:46` against
   `environment.py:82-94`). See N1.
2. **A rejected link 0 counts as a rejection: sound.** The ruling means the reply's own verdict.
   `standing_links` leaves link 0 out only because link 0 is not a chain stop. The only links
   `standing_links` drops are pressed hedges, whose verdict is `hedged`. So `rejected_turns` is
   exactly "every `ChainLink` whose verdict is `rejected`", keyed by reply turn
   (`ChainLink.turn = reply.index`, `environments/poisoned_well.py:468`).

### M1

`m1_replace_probe.py` drove the replace path end to end: `PoisonedWellWatch.watch`
(`environments/poisoned_well.py:396-409`), `env_turn.py:842-847` and
`RunStore.drop_contradictions` (`store.py:315-326`, through the atomic `_keep_only`).

- **The fixer's scenario.** start_rung 2, the two-claims target, the judge down, a kill before
  turn 3's `mark_watched`, and a resume judge that rejects the body pair.
  - The stream equals the unbroken run's, in order.
  - Generated, turns, status and the world record are equal.
  - `poisoned_well.json`, `contradictions.json` and `hypotheses.json` are equal.
  - A second kill at each of the replace-path process's 8 appends and 4 `mark_watched` calls,
    then a third process: 0 mismatches.
- **The full cell** (scheduled ladder, generator, twin), the two-claims target, a kill at turn 3:
  the same results. 39 and 13 second kills, 0 mismatches.
- **A forced reorder.** The full cell with `rules_feelings.yaml`, the judge down only on turn 7's
  ask (the twin's turn), and a resume judge that names a pair of its own.
  - The resumed stream holds turn 7's two pairs after that turn's generator unlocks and
    `GeneratorFire`; the unbroken run holds them before. The multiset is the same.
  - Turns (so every later bully move), generated, the world record, `poisoned_well.json`,
    `contradictions.json` and `hypotheses.json` are all equal.
  - A second kill at each of that process's 28 appends and 11 `mark_watched` calls, then a third
    process. The kill points include one after the drop and before the rewrite, and some after
    the reordered lines are on disk. All equal the single resume: 0 mismatches.
  - So a reordered stream resumes to the same state and analysis.

The reorder is confined to the rewatched turn, which is always the last written turn, and stays
within that turn. No reader depends on the order. The reorder is not new in kind: before the fix,
when a degraded turn that kept no pair was rewatched, the rewatch's pairs were already appended
after the turn's fires.

### M3

- No file under `tests/fixtures/` changed (`git diff --stat bb1e192 3a16951 -- tests/fixtures`
  is empty).
- Both plain goldens pass (`test_env_events.py` on `plain_fixture_events.json` and
  `plain_stub_smoke.json`). The leaderboard markdown is part of the golden, so M2's new line does
  not touch a plain table that has no flagged rep.
- The three edited test files:
  - `test_contradictions.py` recomputes with `harness=` and adds `assert expected` (a stronger
    test).
  - `test_poisoned_well_analysis.py` takes the new `values_watch` shape and gives its synthetic
    `premise_concession` events `politeness=False`.
  - `test_hypotheses.py` does the same for items 4, 5 and 15. Items 4 and 5's code is unchanged,
    so those two edits are no-ops.
- No assertion was loosened and no expected value was re-baselined.
- The final review's two sweep cells give the same records at bb1e192 and 3a16951 (the
  `sweep_clean.py` outputs, diffed, are identical). The stub-path change appears only where a
  template pair follows a harness line, as in the amended template test.

### Calibration form

`calib_probe.py` used the full Poisoned Well cell at start_rung 2, two reps and
`rules_feelings.yaml`. Its judge rejects the body candidates, names a pair of its own and is down
once (rep 1, turn 13).

- **No model call.** `main([... "--contradictions" ...])` ran with `socket.connect` and
  `subprocess.Popen` patched to raise, and returned rc 0.
- **No record or cache change.** The SHA-256 of all 60 files under the run and `_cache/` is equal
  before and after. `JudgeCache.__init__` creates no directory, and `note_cached` is a no-op when
  no ledger is active.
- **Blind.** Every item is exactly `{id, earlier, later, window, label}` and every label is
  empty. No window line names a verdict, a source or a record id. There is no YAML anchor.
- **The key matches the cache.**
  - The run made 21 contradiction asks and left 21 cache entries.
  - Every template row is a candidate that a recorded judge prompt showed, carrying the stub
    judge's verdict for it.
  - The template rows' confirms and rejects (2/2 over two reps) are the cache's own (1/1 in the
    one entry both reps hit).
  - The judge's own named pair is listed per rep as `source: judge`.
- **A cache miss is reported.** The degraded turn is listed under `no_cached_answer` (pw__t0/1,
  turn 13). Deleting one more entry adds its turn to the list. Nothing is invented.
- **`--per-verdict` and `--score`.**
  - `--per-verdict 1` keeps one confirm and one reject.
  - `--score` through the CLI (a subprocess, which found the sidecar key) gives labelled 6,
    agreement 4, confirmed 4 and rejected 2, and quotes both disagreements with their sentences.
  - A key with a different `run_id` exits 1 with the error.

## New breakage

Critical: none. Important: none.

### Minor

- **N1. The docs state I2's rule as "not polite" alone. The hypothetical guard's real effect, and
  the lexicon asymmetry it leaves in item 15, are written nowhere a reader of the register looks.**
  - Where it is stated: `data/hypotheses.yaml:17-20` and spec sections 12 (line 268) and 13
    (line 318) say a `premise_concession` counts "only when it is not polite". Only the spec's
    fix-wave ASSUMED line (757) names the hypothetical guard.
  - The effect: the guard reads the matched span (`metrics/events/environment.py:82-94`, on the
    span from `identity.py:44-51`), so the `if that ... true` template can never count.
  - The Poisoned Well arm is left with one generic non-polite template ("maybe you're right that
    I"). Item 15's Captor arm keeps two more templates of its own premise ("I don't remember my
    family", "perhaps I was a person").
  - The direction: the artifact the final review predicted for item 15 (`supported` from polite
    hedges) is gone, and the residual bias now runs toward `falsified`.
  - The fix: one clause in the YAML header and an item 15 `validity` line. No code change is
    needed before 7b.
- **N2. The not-judged clause tells the reader to rerun `--ratings` even where that cannot help.**
  At `progression.py:219-229`, every `--ratings` pass still prints "rerun `analyze --ratings` on a
  Poisoned Well run" for `epistemologist_alone`, a Rescue cell or any other environment cell that
  is not a Poisoned Well cell (probe (c) and `i1_item2_probe.py`). The parenthesis names "a cell it
  never asks", so a reader can recover the meaning, but the advice is wrong for those cells.

### Nits

- `analysis/poisoned_well.py:5-11`: the module docstring documents the payload. It still calls
  `values_watch` "the flagged share of each cell" and does not list the new keys: per arm
  `values_watched`, `values_unwatched` and `values_note`; at the top level `values_unwatched` and
  `values_watch_source`. Spec line 274 and docs/00 line 176 do list them.
- `probes-final/polite_concession.py` no longer runs, because it imports the removed
  `_is_concession`. `probes-final-rereview/i2_probe.py` replaces it.
- The fix report says M1's reorder "happens only when the rewatch differs from the dead attempt".
  A degraded turn that kept no pair and is rewatched with pairs reorders the same way through the
  ordinary path (pre-existing, P54). Harmless, as shown above.

## Sweeps

All sweep scripts come from `probes-final/`, copied unchanged to `probes-final-rereview/` and run
at 3a16951. Outputs are in `out_*.txt`.

| Sweep | Points | Result |
| --- | --- | --- |
| `sweep_kill.py 1 1 append` (full cell, judge on) | 61 | 0 mismatches |
| `sweep_kill.py 1 1 watched` | 14 | 0 mismatches |
| `sweep_kill.py 2 0 append` (start_rung 2, no judge) | 58 | 0 mismatches |
| `sweep_kill.py 2 0 watched` | 14 | 0 mismatches |
| `sweep_ratelimit.py limit` | 49 | 49 of 49 paused, 0 mismatches |
| `sweep_ratelimit.py error` | 49 | 41 flagged by the script's strict rule, every one an expected degrade shape (below). Output byte-identical to the same sweep at bb1e192 |
| `m1_replace_probe.py` second-kill sweeps (new) | 12, 52, 39 | 0 mismatches against the single resume |

The 41 error-sweep flags all take the shapes spec section 15 describes:

- 23 target or bully errors kill the process, and the resume equals the unbroken run
  (`DIFFERS in []`).
- 12 trigger-judge errors complete, with the turn in `contradictions_degraded`.
- 6 twin or generator errors complete, with the fire `error`.

That makes 147 kills and 49 rate limits, as in the final review, with 0 mismatches.
`load_old_runs.py`: both rung-0 runs still load.

## Constraints

- Non-negotiable 3 holds. I1 labels reps and never includes one; flagged reps stay out everywhere.
- The reasoning channel stays private. Nothing new reads `reasoning_text`; `contradiction_inputs`
  and the calibration form read `chat_text`.
- Everything replays from JSONL. The form re-derives from the records and only reads the cache.
- The plain goldens are byte-identical.
- `SCHEMA_VERSION` is 3 (`enums.py:13`). The additions are analysis-output keys, listed in docs/00
  section H as "version 3, additive".
- The checkout is unchanged (`git status --short` is empty).

## Overall

**Ready.** N1 and N2 are wording and can wait for the 7b preparation; neither changes a count.

## Probes

All in `probes-final-rereview/`:

- `i1_probe.py`, `i1_item2_probe.py`, `i2_probe.py`;
- `m1_replace_probe.py` (args: budget, `full`, kill turn, `feelings`) and `m1_dump.py`;
- `calib_probe.py`;
- `rules_two_claims.yaml`, `rules_feelings.yaml`;
- the final review's sweep scripts, copied unchanged;
- outputs `out_*.txt` (`out_base_*` from bb1e192).
