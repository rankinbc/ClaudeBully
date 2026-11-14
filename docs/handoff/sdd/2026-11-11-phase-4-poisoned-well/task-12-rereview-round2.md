# Task 12 re-review, fix round 2 (6455b07..0dd88a1)

Read-only on the checkout (HEAD 0dd88a1, `git status` clean after my probes). The diff was read once
(`review-6455b07..0dd88a1.diff`). The suite was not re-run. My probes are in `probes-task12-rereview2/`: three probe files
(`probe_reask.py`, `probe_keys.py`, `probe_nits.py`, the last under `-W error`) and two mutant probes ran, all green. The mutant
probes call two committed tests by name (not the suite).

## Verdicts

No new Critical. No new Important. Counts of new items: 0 Critical, 0 Important, 1 Minor, 3 Nit.

| Finding | Verdict |
| --- | --- |
| R1-1 a failed re-ask drops a values `true` | ADDRESSED. A failed (`ProviderError`, unparseable twice, off the list) or partial re-ask keeps the earlier `true` in `ratings.json`'s `stale_kept`; its rep stays out; a fresh answer replaces it. Replace-by-rep is the right rule. |
| R1-2 a `JUDGE_SYSTEM` edit stales verdicts but the rerun replays them | ADDRESSED. The rerun asks again. Only the ratings asks are keyed on it; the other keys are byte-identical to 6455b07. |
| N-new-1 empty bar or panel unlabelled | ADDRESSED. |
| N-new-2 schema not in the digest | ADDRESSED. |
| N-new-3 private `_rung_of`, off-ladder `attrs.rung` | ADDRESSED. |
| N-new-4 spec bullet and docs/00 H | ADDRESSED. |
| Digest still deterministic | CONFIRMED. |

## 1. R1-1 in detail

Code: `metrics/ratings.py:512` `carry_flags` (read before `write_ratings` overwrites the file), `:505` `_carried_entries`,
`:542` `read_back` (reads `stale_kept`, new last field `ReadBack.carried`), `analysis/run_analysis.py:196-217` (the rated
branch applies the carried flags with `ratings_flags(..., stale=True)`, writes `ratings_applied.json`, prints the stale
warning, sets the `results.md` note).

Probe `probe_reask.py`, a two-rep Poisoned Well run, both reps judged `true` first (baseline: `values_loosened_left_out 2`, arm
`reps 0`, `by.judge 2`, `stale_kept {}`):

- **Failed re-ask, three ways** (judge cache emptied so the pass asks afresh): a `ProviderError`, text no verdict parses from
  (twice, a `JudgeError`), and an answer off the list. Each: the rewritten `ratings.json` holds no `rate_values` verdict,
  `failed 2`, `stale_kept` holds both earlier `true` verdicts under their keys. `poisoned_well.json`:
  `values_loosened_left_out 2`, `values_loosened_by.judge 2`, arm `reps 0`. `ratings_applied.json`:
  `{source: pass, applied: 14, stale: 2, stale_flags_kept: 2}` (the other kinds applied). stderr and `results.md` both say
  `2 stale values flag(s) kept, fail closed`. Two later plain `analyze` runs give the same state (`source: read_back`,
  `stale_flags_kept 2`, left out 2): idempotent. A reload through `read_back` flags reps 0 and 1.
- **Partial re-ask, a real judge** (script: rep 0's ask fails, rep 1's answers `false`): `stale_kept` holds rep 0's `true`
  only; `ratings` holds rep 1's `false`; left out 1, arm `reps 1`, `by.judge 1`; only rep 0 reads flagged on reload, also
  after a later plain analyze. So the fresh `false` cleared rep 1 and the failure kept rep 0.
- **Partial re-ask, a pass that answers rep 0 `true` and gives rep 1 no `rate_values` verdict** (`rate_all` wrapped): rep 1
  carried, rep 0 fresh, left out 2. A following clean re-ask that answers `false` for both clears both: `stale_kept {}`, left out
  0, arm `reps 2`. A carried flag clears only on a fresh answer, as ruled.
- **Non-negotiable 3 end to end**: a `write_results_md` spy sees `(rep 0 flagged, rep 1 flagged, left out 2)` in the failed pass
  itself and in the later plain analyze, so every success count downstream already excludes both reps.
- **A rate limit mid re-ask** raises `RateLimitExit` before `write_ratings`: `ratings.json` is byte-identical to before, and a plain
  analyze still flags both reps.
- **A `--ratings` pass that is skipped** (no judge): `mark_skipped` reads and rewrites the payload, so `stale_kept` survives;
  left out stays 2.
- **An earlier file that was already stale** (every digest zeroed), then a failed re-ask: both `true` verdicts are still carried
  (`carry_flags` does not test the digest).
- **Hand-damaged `stale_kept`** (a list, `null`, a string, entries that are an int, lack `rationale`, have an unparseable key,
  name a gone rep, or are a `rate_hedge` `true`): no crash, nothing kept from any of them, and a file without `stale_kept` reads
  as before (`kept {}`, `carried []`).

### Replace by rep, not by key: right

- `rating_items` yields at most one `rate_values` item per conversation (`if replies: yield _values_item(...)`), keyed at the
  reveal turn. So by rep and by key mean the same thing while the reveal turn stays put.
- They differ when it does not: a rep re-run under its id, or an edit to `_reveal` (the digest hashes the code that picks the
  line, so such an edit stales the verdict and can move the turn together). By key, an old `true` at turn T+1 would never match
  the fresh key at T, so it would stay carried for ever and no rerun could clear it.
- Probe `test_fresh_answer_replaces_by_rep_even_at_another_turn`: the earlier `true` re-keyed to turn+1, a fresh `false`
  re-ask gives `stale_kept {}` and left out 0. A second probe seeds a carried entry at turn 999 and a fresh `true`: `stale_kept {}`.
- There is no committed test for it (M-new-1 below).

## 2. R1-2 in detail

Code: `metrics/judge.py:101` `JudgeCache.key(model, prompt, *, system=None)`, `:182` `_ask(..., *, keyed_on_system=False)`,
`metrics/ratings.py:370` `rate_all` is the only caller that passes `keyed_on_system=True` (`git grep` over 0dd88a1).

Probe `probe_keys.py`:

- **A `JUDGE_SYSTEM` edit makes the rerun ask again.** No edit: a `--ratings` rerun makes 0 judge asks. After the edit: a plain
  analyze reports 16 stale (kinds `rate_escape` and `rate_values`) and keeps 2 flags; the `--ratings` rerun makes 7 asks
  (one per distinct prompt, the 16 verdicts dedupe), every one carrying the edited system prompt, writes `applied 16, stale 0,
  stale_flags_kept 0`; cache files go 7 to 14 (new entries beside the old). With the edit reverted, a rerun makes 0 asks: the
  original entries replay, nothing is stranded.
- **Byte for byte against 6455b07.** I load 6455b07's `judge.py` source (from `git show`) as a module and compare:
  - `JudgeCache.key` over 603 inputs (the labels `chain`, `contradictions`, `authority`, `harvest`, `llm_lint`, `trigger`,
    `twin` and the model names, with random digests including NUL, newline and non-ASCII): 603 of 603 equal, and 603 of 603 equal
    `sha256(f"{model}\n{prompt}")`.
  - `judge_pair` and `judge_capture`, base against head, same provider script: 3 cache files each with identical names, and the
    same conversation ids (`judge/4f410ac7f135`, `judge/c9560126e8e7`, `judge/825e069839d1`).
  - The chain, contradictions, authority, harvest, lint, trigger and twin sites build `JudgeCache.key(label, digest)` themselves
    and none of their files is in the diff (the five changed `claude_bully` files are `analysis/poisoned_well.py`,
    `analysis/run_analysis.py`, `metrics/events/poisoned_well.py`, `metrics/judge.py`, `metrics/ratings.py`). `JUDGE_SYSTEM` is
    read only by `judge.py` and `ratings.py`, so no other digest could have moved.
  - The keyed form `sha256(model NUL sha256(system) NUL prompt)` is its own space (never equals a plain key, moves with every
    part, an empty system string is still keyed).
- **Why the implementer added the pair-judge test.** The pair and capture judges are the only other callers of `_ask`, and they
  share `JUDGE_SYSTEM` with the ratings. A flipped default (or an over-broad `_ask` edit) would re-ask them after any system-prompt
  edit and orphan every Phase 3 cache entry that `promote` carries. The unit test in `tests/test_judge.py` covers
  `judge_capture` only; the slow test (`tests/test_run_analysis.py:97`, 5 s) covers the analyze path, both `judge_pair` and
  `judge_capture`, on a copied run. It passes on 6455b07 too (a guard, as the report says). It is discriminating:
  `probe_pair_mutant.py` flips `_ask`'s default to `True` and the committed test fails (`assert 12 == 6`); head passes it. A direct
  `judge_pair` probe agrees (2 calls before and after the edit on head; 2 then 4 on the mutant).

## 3. The nits

- **N-new-1, charts.** `probe_nits.py` under `-W error`, reading the saved figures:
  - A kept arm beside an all-flagged arm: chain x labels `['stub-target\npw', 'stub-target\npw2\nall flagged']`; escape legend
    `['pw', 'pw2: all flagged']`.
  - Two models, one all flagged: chain `...stub-target-two\npw\nall flagged`; panel `stub-target-two` legend `['pw: all flagged']`,
    `stub-target` legend `['pw']`.
  - Every rep flagged: every bar and every panel says it.
  - Nothing flagged: no note anywhere. A partly flagged arm (1 of 2) draws normally (`reps 1`, left out 1).
  - PNGs in `probes-task12-rereview2/charts/` (I looked at `v2_arm_chain.png` and `v2_all_escape.png`: clean; the legend entry
    has an empty handle slot, cosmetic).
- **N-new-2, schema in the digest.** `prompt_digest` hashes `json.dumps(rating_schema(kind), sort_keys=True)`. Editing one kind's
  schema moves that kind only; editing `ANSWERS["rate_hedge"]` moves it; `JUDGE_SYSTEM`, `CUT_MARK` and the cut path still move
  what they moved; a change to the probe conversation's metadata moves nothing.
- **N-new-3, `rung_of`.** Public at `metrics/events/poisoned_well.py:879`, imported by the analysis; `git grep -w _rung_of` finds
  none in code, tests, the spec, docs/00 or HANDOFF (only the historical plan under `docs/superpowers/plans/` still quotes the
  original). Probe, three reps on the chain window: a `premise_concession` naming `not_a_rung` and one naming nothing both count on
  `chain` (conceded 2/3, n 3); one naming `sleeper`, a rung this run's windows do not hold, counts nowhere (sleeper n 0); a
  `sleeper_question_conceded` at the chain's turn counts nowhere. Detector-produced events carry `attrs.rung = rung_of(all
  windows)`, so for them the new fall-through repeats the same lookup over the on-ladder windows; it changes a count only for a
  hand-set name or an off-ladder stamp. No harm.
- **N-new-4, docs.** Spec section 12's `concession_by_rung` bullet is one sentence per rule (reads cleanly); docs/00 H line 170
  says a rep with no `poisoned_well` block reads None degraded turns, and records `stale_kept`, the ratings-only key, the schema
  digest and the chart labels. HANDOFF counts add up (9694 + 10 = 9704 default, 23 + 1 = 24 slow; 6 + 2 + 2 new default tests,
  1 slow).

## 4. The digest is still deterministic

`probe_nits.py::test_digest_is_deterministic...`: in-process and in four subprocesses with `PYTHONHASHSEED` 0, 1, 12345 and
random, all four digests equal (`rate_hedge 8b440e36a1042dba`, `rate_recognition d1a9ab52889e3a8b`, `rate_escape 35dcd9be9f9a22bf`,
`rate_values 93bed5afda7071ff`) and pairwise distinct. They differ from round 1's (the schema is new in them), so every
`ratings.json` written at 6455b07 or earlier reads stale once and keeps its flags (fail closed); the implementer names this
and no real run holds one.

## New breakage by severity

No Critical. No Important.

### Minor

**M-new-1. The by-rep replacement is not pinned by a committed test.**
- Where: `claude_bully/metrics/ratings.py:512` (`carry_flags`), tests `tests/test_ratings.py:679` and `:714`.
- Probe `probe_bykey_mutant.py`: a by-key mutant of `carry_flags` (skip an earlier `true` only when the pass answered the same
  key) passes `test_a_failed_reask_...`, both parametrisations of `test_a_reask_that_answers_replaces_...` and
  `test_a_reask_carries_no_false_...`, because every one re-asks at the same turn.
- Why it matters: the rule the implementer chose is right and rests on a one-line comparison; a later "simplification" to a key
  match would strand a flag after a reveal-turn change and no committed test would say so.
- Fix (small): a test that re-keys the earlier `true` to another turn (my `test_fresh_answer_replaces_by_rep_even_at_another_turn`
  is one) and asserts the fresh `false` clears it.

### Nit

- **N-r2-1.** The pass that carries a flag prints and writes it as `N stale verdict(s) not applied` and `left out`
  (`ratings.py:617-634`, `:637-647`), counting the carried flags among the stale beside `stale_flags_kept`, the round-1
  convention. The wording reads as if the flag were dropped. `ratings_applied.json` says `source: pass` with `stale > 0` and
  `stale_reps: []`, which the implementer notes. Optional: say "kept" in the pass's line.
- **N-r2-2.** A carried flag has no other way out than a fresh `rate_values` answer, so a rep whose ask always fails stays out of
  every rate and the count is repeated on every analyze. By design (fail closed, counted, named); noted so Task 13's reader of
  `results.md` knows the note can persist.
- **N-r2-3.** A `stale_kept` entry that does not parse as a `RatingVerdict` (hand-edited: no `rationale`) is silently not kept, so
  its flag drops; it is still counted among `stale`. Only a hand edit reaches it. `ratings.py:490`, `_keeps_flag`.

## Probes (`probes-task12-rereview2/`)

Run each from the repo root with
`PATH=/c/Users/Brian.Rankin/.local/bin:$PATH PYTHONDONTWRITEBYTECODE=1 timeout 300 uv run --no-sync pytest <file> -p tests.conftest -s -o faulthandler_timeout=60 --rootdir . -p no:cacheprovider -m "slow or not slow"`
(`probe_nits.py` also with `-W error`; `probe_keys.py` imports `probe_reask`, so run it from the same rootdir).

| Probe | Result |
| --- | --- |
| `probe_reask.py` | 12 passed. Baseline; failed re-ask by `ProviderError`, unparseable and off-list (kept stale, rep out, idempotent); partial re-ask both ways; replace-by-rep at another turn; non-negotiable 3 end to end; skipped pass; damaged `stale_kept`; a stale-digest earlier file; a rate limit mid re-ask. |
| `probe_keys.py` | 5 passed. Key function 603 of 603 equal to 6455b07's; no other key site touched; pair and capture judge cache entries and ids identical to base; a flipped default would re-ask the pair judge (2 then 4 calls); the ratings rerun asks again after a system edit and replays after a revert. |
| `probe_nits.py` | 5 passed under `-W error`. Chart labels in four scenarios; a partly flagged arm; the digest across four hash seeds, schema, system prompt and cut path edits; no `_rung_of` left; the `premise_concession` rung rules. |
| `probe_pair_mutant.py` | 2 passed. The committed slow pair-judge test passes on head and fails on the flipped-default mutant. |
| `probe_bykey_mutant.py` | 1 passed. The committed R1-1 tests all pass under a by-key mutant (M-new-1). |
