# Phase 5 Task 2 review: the stub's turns mode, the reserved reasoning key, stubbed_experiment, tests.helpers.stubbed

Range d68aa3f..049101d (one commit). Read-only on the checkout; probes are in `probes-task2/`, run with `PYTHONDONTWRITEBYTECODE=1`, with run output under the session scratchpad. The suite was not re-run. I ran `ruff check` and `ruff format --check` on the touched files and `mypy` on `dryrun.py` and `stub.py` only (cache outside the checkout): all clean.

## Verdicts

- Spec (does it match its requirements): MET. Every interface in the brief is present with the stated signature, the four binding points hold (probed, below), and Q10 and Q11 are built and tested.
- Quality (is it well-built): GOOD. The turns rule is a pure function of the messages, parse errors name the entry, the two old `_stubbed` helpers are one shared helper with no call-site drift, and nothing outside the task's files moved. Findings are Minor and Nit only.

Counts: Critical 0, Important 0, Minor 4, Nit 3.

## What was checked, by named risk

### 1. Behaviour equivalence (probe1_equivalence.py)

Method: the two old `_stubbed` bodies and their `TARGET_RULES` / `JUDGE_RULES` constants were extracted from git at d68aa3f (`git show`, then `exec`) and compared with `tests.helpers.stubbed` by `model_dump()` and `==`.

- Constants: the old `tests/test_configs.py` TARGET_RULES and JUDGE_RULES and the old `tests/test_env_configs.py` JUDGE_RULES resolve to the same two paths as `tests/helpers.py`.
- 66 caller/input pairs are equal, covering every caller shape. `test_configs` (`_stubbed(exp, turn_budget=n)`, and the positional `_stubbed(exp, n)` that `test_ladder_configs` and `test_poisoned_well_configs` used) was run over every top-level config and every `ladder/` and `poisoned_well/` config. The env helper (`_stubbed(exp, script, **updates)`, script None, `overlay_target_rules`, `phase2_target_rules`, with and without `turn_budget`, `name`, `repetitions`) was run over every `environments/` config.
- Call-site audit: `git grep _stubbed d68aa3f -- tests` lists 21 lines; each maps to a `stubbed(...)` call at 049101d with the same arguments (positional `turn_budget` became `turn_budget=`). `git grep -nw _stubbed 049101d -- tests` exits 1. The two local `stubbed` bindings are renamed `stubbed_exp` (`tests/test_ladder_configs.py:90`, `tests/test_phase2_charts.py:110`). `tests/test_generator_analysis.py:63` has an unrelated local `stubbed` and does not import the helper.
- `tests/test_hypotheses.py:1147` still imports `OVERLAY_RULES, _config, _short` from `tests.test_env_configs`; all three remain.
- No file under `tests/fixtures/golden/` changed (`git diff --stat` is empty).
- `StubProvider` for list scripts and plain responders: the dispatch changed from `isinstance(.., ScriptedResponder)` to the union; the `_parse_rule` messages are unchanged (`tests/test_providers_stub.py:245` matches `stub rule`).

### 2. Q11 (probe2_q11.py)

- Each of the 17 shipped configs with environments (45 environments) was dirtied with `generator.model = "opus"` and `superior_self.responder_model = "sonnet-x"` on every environment. After `stubbed_experiment` every `generator.model` is None and every `responder_model` is `bully`. `generator_role(...)` gives `stub-generator` where the generator is enabled, and `responder_role(...)` gives a stub role whose model is one of the four doubles. Cell ids are unchanged, the input is not edited, and `Experiment.model_validate(stubbed.model_dump())` passes (`model_copy` skips validators, so this shows the copy is also valid).
- `target` and `bully` are kept; the shipped `authority_grid` values (`target`) are untouched. `"Target"`, `"BULLY"` and `""` are not role words, so they map to `bully`, the same reading `responder_role` gives them.
- A disabled-generator environment that names a model is cleared, and the experiment generator stays None. A stubbed experiment stubs again to itself.
- Every role the runner builds a provider for (`env_turn.py:1179`, `1531`, `1539`, `1663`, `1714`, `runner.py:853`, `858`) is covered: judge, target, twin (the target role), responder, generator, bully. I found no other environment field naming a model (`environments/config.py` holds only `generator.model` and `responder_model`).

### 3. The turns mode (probe3_turns.py, probe4_reasoning.py)

- Empty default: `default: []`, `default: null`, `default` a mapping, `default` absent (with and without `by_cell`), and an empty list under a `by_cell` pattern are all refused with `ValueError` naming the place. `by_cell` absent or null is accepted.
- `by_cell` matching: the first listed pattern wins (not the most specific); matching is case-sensitive (`RESCUE_*` does not match `rescue_...`, and `Exact__t0` and `exact__t0` differ); `[0-9]` and `?` work; an id with no cell (`judge/abc`, `doctor/x`, `""`, `not-a-cell-id`) takes the default; YAML order is kept through `load_stub_script`.
- Non-string `reasoning` (5, a list, a mapping, True, None) is refused on all four shapes (rule, tool rule, entry, tool entry); `""` is accepted.
- Tool step: the call id is `turn-0-0`, a second provider built mid-conversation issues an equal call, `args` are deep-copied per call (mutating a returned call does not change the next), and the follow-up answers `reply_after_tool`.
- End to end through the real runner: a stub run of two `smoke` conditions with a turns script on the target (`by_cell: grader__*` plus a default) completed 4 of 4 cells. The grader cell answered the by-cell entries (first, then the repeating last) and the captor cell the default, so the cell id the runner builds does reach `parse_conversation_id` as the rule needs.

### 4. The reserved reasoning key (probe4_reasoning.py)

- Direct: 16 completions over both shapes, with and without tools offered, over four history shapes. `reasoning_text` is None on every one and the sentinel is in no field of `Completion.model_dump_json()`. By construction the key is read only into `_Rule.reasoning` and `TurnEntry.reasoning` (`stub.py:57-63`, `90-98`, `162-188`); nothing reads it back.
- End to end: sentinels were placed in the target's turns script, the bully's rules script and every rule of the judge's script. A stub run plus `analyze_run(judge=True)` wrote 43 files (ledger, transcripts, `judge_cache/` with 4 files, analysis). The canned reply texts are present in them (so the scan is live) and no sentinel appears in any file. No prompt to a bully, generator or judge can hold it.
- Caveat: the shipped test for this (`test_the_reasoning_key_is_accepted_on_both_shapes`) asserts only `reasoning_text is None` and the turns entry's value. The no-leak property rests on construction and on this probe, not on a shipped test (M4).

## Findings

### Critical

None.

### Important

None.

### Minor

M1. The two ASSUMED strictness rulings have no test. `claude_bully/providers/stub.py:57-63` (`reasoning` must be a string, on both shapes) and `stub.py:258-259` (`default` required, with or without `by_cell`) are never exercised by `tests/test_stub_turns.py:143-157`: its seven bad scripts hold no non-string `reasoning` and no script with a `by_cell` and no `default`. Both work (probe3), but a later loosening would pass the suite. Add `{"mode": "turns", "by_cell": {"a*": [{"reply": "x"}]}}` and a `reasoning: 5` case on each shape.

M2. `load_stub_script` changed on degenerate files. `stub.py:283-287` reads `[] if raw is None else raw`; the old body was `yaml.safe_load(fh) or []`. A file holding `{}`, `0`, `''` or `false` loaded as an empty rule list before and now raises `ValueError`. No shipped or test script is affected (`test_every_shipped_rules_script_still_loads`), so the binding point holds for every real caller, but it is a quiet behaviour change the report does not name. The opposite slack is at `stub.py:251` (`raw.get("by_cell") or {}`), which silently accepts a falsy wrong-typed `by_cell` (`[]`, `''`, `0`) where a truthy one (`["a*"]`) is refused. One rule, "None is empty, any other non-mapping is refused", would fix both.

M3. The `fnmatchcase` deviation from spec section 10 and the brief (`fnmatch`) is right and is pinned by `tests/test_stub_turns.py:75`. On Windows `fnmatch` folds case, so one script would pick different entries here and on Linux CI (RED 3 in the report shows it). It is recorded only in docs/00 section F and HANDOFF item 2. The spec's "As planned" block for Task 2 (`docs/superpowers/specs/2026-11-14-phase-5-director-design.md:538-544`) lists the tool-id ruling, Q10 and Q11 but not this, nor the refusal of a non-string `reasoning`; that block is the spec's list of every plan decision that changes, narrows or contradicts it. Add one line each.

M4. The "reasoning stays private" binding point has no shipped test of its own. `tests/test_stub_turns.py:129-141` checks that the turns entry keeps the value and that `reasoning_text is None`, but not that the rules shape keeps it (`_Rule.reasoning` is never read by a test) and not that the value is absent from `Completion.text`. The behaviour is correct (probe4). A sentinel assertion on `completion.text` and `model_dump_json()` for both shapes would pin it before Phase 6 changes `Completion`.

### Nit

N1. `ScriptedTurns.respond` counts `done` again (`stub.py:241`) after `entry_for` already did (`stub.py:226`). A private `_done(messages)` used by both keeps the id rule and the index rule from drifting.

N2. `claude_bully/planner/dryrun.py:27` (`_ROLE_RESPONDERS = {"target", "bully"}`) restates the role words of `env_turn.responder_role` (`env_turn.py:231-244`). If that function gains a third role word, the dry run would silently map it to `bully`. `test_a_stubbed_experiment_maps_a_named_responder_model_to_the_bully` catches the drift only for the cases it names.

N3. `_parse_entry` (`stub.py:162-188`) and `_parse_rule` (`stub.py:76-98`) repeat the same reply / tool / reply_after_tool cross-checks with different message prefixes; only the tool step and `reasoning` were shared. Acceptable here (the rule messages are pinned by an existing test), but a third shape would want one validator that takes the prefix.

Also noted, not findings:
- The report says "13 functions"; `tests/test_stub_turns.py` has 14 (20 collected), which agrees with its own total of 20.
- The report's concern that two stub targets share the model `stub-target` is real but benign for this task. A stubbed `sanctuary_catalyst_vs_honest` (two targets) ran 8 of 8 cells, and `analyze_run(judge=False)` wrote a `results.md` naming both `__t0` and `__t1` (probe5). How analysis groups two targets of one model is Task 5's to see.
- The working-tree copies of the new files are CRLF while the committed blobs are LF (`.gitattributes` has `eol=lf`; `git show 049101d:<file>` holds no CR), so the commit is correct.

## Probes

All in `.superpowers/sdd/2026-11-14-phase-5-director/probes-task2/`.

| File | Risk | Result |
|---|---|---|
| `probe1_equivalence.py` | 1 | the old `_stubbed` (from git d68aa3f) equals `tests.helpers.stubbed` on 66 caller/input pairs; the constants resolve to the same paths |
| `probe2_q11.py` | 2 | 17 env configs / 45 envs dirtied and cleaned; target and bully kept; cell ids, validators and idempotence hold |
| `probe3_turns.py` | 3 | empty or missing default, by_cell first-wins and case rules, non-string reasoning refused on four shapes, tool ids and statelessness; also records the M2 behaviour |
| `probe4_reasoning.py` | 4 | no sentinel in any Completion field (16 cases) nor in any file of a stub run with a turns target, a scripted bully and a scripted judge (43 files) |
| `probe5_two_targets.py` | the report's concern | a stubbed two-target config runs 8 of 8 cells and analyses |

Probes 4 and 5 read `PROBE_SCRATCH` (a scratchpad directory) for their run output; nothing was written inside the checkout.
