# Task 5 review: the LLM reader-address lint (a40dc62..850b283)

How I read it: the diff in four passes (header, HANDOFF and `generator.py`; `llm_lint.py`, `records_env.py`, `env_turn.py`, `sheets.py`, the persona; docs and the probe script; fixtures and tests). Spec section 6 and the Task 5 "As planned" block read in full. Four focused checks outside the diff, one per named risk:
- resume path: `WorldGenerator.fire` and `commit` (`generator.py:1095-1160`), `env_turn.py:759-774` and `drop_uncommitted_generation` (`store.py:141-183`);
- the callers of `_from_cache` and `write_fire`: grep, one caller each in production (`generator.py:768`, `:1123`);
- `role_of`'s `lint` mapping (`providers/ledger.py:77`);
- DRY: the existing fence and squash helpers (`generator.py:565-571, 622-626`, `metrics/judge.py:211-220`).

No tests were run.

### Spec Compliance

- Spec compliant, with two departures from the brief. Both are recorded in the spec's "As planned" and both are justified:
  - the deferred lint-cache writes (`FireOutcome.lint_puts`, `LlmLint.verdict(defer=)`, `LlmLint.commit`);
  - `tests/test_generator_run.py` moved to `LintJudge`. This was needed: a non-stub judge now reviews the run's `recovery_guide`, and `HarvestJudge`'s `{"category": "none"}` is correctly read as off the contract.
- File lists, checked one by one. Every Create and Modify file is present. The persona, the stub rules and the probe seed match the brief verbatim. `llm_lint.py` matches it too, apart from the `defer`/`commit` additions. The `Final` import in `scripts/llm_lint_probe.py:20` is a correct fix of a brief bug.
- Docs sync matches Step 5 item by item:
  - HANDOFF: Progress 5, the two "For Phase 7" items, carry 1;
  - docs/00: B rows, F, H, "Cache homes", I row 3;
  - the Phase 3 residual bullet;
  - the Phase 7 "As planned".
- Carries 1 to 3 are honoured. The probe is not filled.
- Review Focus 3:
  - `test_the_fire_record_carries_every_verdict` (`tests/test_llm_lint.py:279`) drives a real run. It asserts that the verdicts are in the `GeneratorFire` records with the judge model, that the count of uncached verdicts matches the judge's lint calls, that the lint cache dir is populated, and that `PRIVATE` reaches no judge prompt and no file (P30d). Good.
  - `test_two_off_contract_replies_reject_the_document` (`:142`) tests `LlmLint` alone and never goes through `DocWriter`. Despite its name, nothing shows a document being rejected (Important 2).
- Extra relative to the spec: the persona and the user-message definitions exempt "a quoted line attributed to a named person". Spec section 6's pass list is only "third-person procedure, bare instructions, general service text". This is plan-mandated (brief verbatim); see Important 1.
- Cannot verify from diff:
  - Commit author `rankinbc1@gmail.com` and the trailer `Co-Authored-By: Claude Fable 5.1`. Controller: `git log -1 --format='%ae%n%B' 850b283`.
  - LF endings on the six new files. Controller: `git ls-files --eol` on them.
  - Golden plain fixtures byte-identical. The diff touches none, so it is implied; controller: `git diff --stat a40dc62 850b283 -- tests/fixtures/golden*`.
  - The gate counts (8252 passed, +25 items = 17 + 8 parametrized) are consistent with the test file, but I did not re-run them.

### Strengths

- The deferral is complete and correct. Every lint ask inside the writer goes through `DocWriter._lint` with `defer=self._lint_puts` (`generator.py:884-899`), on the cache-hit path (`:844`) and the attempt path (`:874`) alike.
  - `write_fire` rebinds the list per fire (`:759`), and the committed outcome takes a tuple copy (`:803`). A second fire in the same `WorldGenerator.fire` loop (`:1098-1153`) cannot leak into the first's outcome, even though the session commits each result only after its line (`env_turn.py:772-773`).
  - `commit` writes the lint entries only for `written`/`cached` (`generator.py:806-818`), so a "cached" fire whose lint missed its own cache still commits the fresh verdict.
  - Resume holds. Fire lines are of produced turns, `drop_uncommitted_generation` (`store.py:141-183`) drops uncommitted ones whole, and the redone fire then reads no lint entry the unbroken rep had not. The RED 2 evidence (`cached: True` against `False`) shows the failure the deferral fixes.
- A rejected or failed fire's verdict does not reach the cache. That is safe: the generator cache never holds a rejected reply, so the same body is unlikely to recur. It is consistent with P13, and it is recorded in "As planned".
- P4 is right. The lint on a hit runs under `write_fire`'s marker (`generator.py:844`), and the generator hit is noted only after the lint passes (`:845-849`). The 5-mark test (`tests/test_llm_lint.py:241`) pins the marker.
- The contract parser is strict and fail-closed (`llm_lint.py:115-144`):
  - exact keys;
  - verdict enum;
  - a pass with sentences, or a fail with none, is off the contract;
  - every sentence must be in the body, compared whitespace-squashed;
  - `ProviderError` (and so timeouts and rate limits) becomes `error`, which is never cached.
- `LintJudge` is a clean double: it answers lint prompts before `super()`, so `harvest_calls`/`crash_at` are unchanged. Keeping `HarvestJudge` honest (rather than making it pass lints) is the right call.
- The module boundaries are clean:
  - `llm_lint.py` (266 lines) owns the prompt, key, parse, cache and failures;
  - `DocWriter` owns only the hook;
  - `env_turn` only wires it.
  - `generator.py` grows 1083 to 1160.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **The reviewer prompt exempts quoted lines and has no fail-closed tie-break (plan-mandated).**
   - Where: `data/personas/lint_reviewer.md:23-26`, and the same exemption in `claude_bully/planner/llm_lint.py:81-83` (`_DEFINITIONS`).
   - What is wrong:
     - Both texts pass "a quoted line attributed to a named person" outright. The project's own record (Phase 3 spec, the `second_person` bullet the diff touches) says "a quoted found note that addresses the reader is the most natural billboard smuggle". That is why the deterministic reader-address check runs on unstripped text.
     - The deterministic lint catches only the form. A semantic billboard inside a quote gets past it, and this prompt then tells the LLM to pass it. Example: "'Most of them start by saying they have no body,' Nurse Orrin says."
     - The pass list also says "third-person procedure ... is not written for the reader" without saying that rules 1 to 3 win. Spec section 6's residual class is exactly third-person procedure that describes an assistant habit, as in seed billboard 1.
     - Nowhere does it carry the docs/08 rule the spec cites ("if you can't tell whether something is a billboard, it is"). An unsure model will pass.
   - Why it matters: these are the two residual classes this lint exists to catch, and the 7b bar is at most 1 of 15 billboards per kind, with one revision budgeted.
   - Fix (nothing is cached yet, so `LINT_PROMPT_VERSION` 1 can stay; any later edit must bump it):
     - drop the quoted-line exemption, or say a quoted line is judged by what it says like any other;
     - add "rules 1 to 3 override the pass list";
     - add "if you cannot tell whether a sentence is written for the reader, it is: fail it".
     - Mirror all three in `_DEFINITIONS`.
2. **Fail-closed is not pinned at the writer or in a run.**
   - Where: `tests/test_llm_lint.py:142` (`test_two_off_contract_replies_reject_the_document`), and the unused `offcontract_lint` mode in `tests/fixtures/generator_stub.py`.
   - What is wrong: the test checks `LlmLint.verdict` and `LlmLint.failures` alone. No test drives an `error` verdict, off the contract or a provider error, through `DocWriter`.
   - Why it matters: "an `error` verdict fails closed" is a listed non-negotiable. A regression in `_attempts` or `_lint` would pass the suite, for example `if verdict.verdict == "fail"`, or `_lint` returning `[]` on error. The `offcontract_lint` mode was specified for exactly this test and is dead.
   - Fix: add one writer test with `GeneratorStub(["offcontract_lint", "offcontract_lint"])`. Assert:
     - `status == "rejected"` and `rejection == "lints"`;
     - `[v.verdict for v in outcome.llm_lint] == ["error", "error"]`;
     - `lint_failures == [LintFailure("llm_reader_address", "no verdict")]`;
     - the judge stub made 4 calls;
     - the retry prompt holds `no verdict`.

     Add one with `_Down()` as the lint provider, asserting the same rejection and `error == "ProviderError"`. This also pins concern 4's behaviour.

#### Minor (Nice to Have)

1. **A lint verdict can be lost from an error fire (report concern 3), and the docstring overstates.**
   - Where: `generator.py:776-778`, with the `FireOutcome` docstring at `generator.py:514`.
   - What is wrong: a `ProviderError` on generator attempt 2 discards attempt 1's verdict, which lives in `_attempts`' local list. The outcome's "whatever the status" is false in that case. The ledger still has the call.
   - Fix: let `_attempts` append to a list `write_fire` passes in, as `_lint_puts` already does, or catch inside `_attempts` and re-raise with the verdicts attached. Neither changes the brief's return shape much.
2. **An `error` verdict on attempt 1 retries the generator (report concern 4).**
   - This is right against section 6: an attempt the lints do not pass is retried, at most `MAX_ATTEMPTS`, and nothing commits without a `pass`, so fail-closed holds.
   - The cost: the Fix list then reads `- llm_reader_address: no verdict` (`generator.py:878`), which tells the generator nothing it can act on and may perturb a sound document.
   - Fix: consider leaving `no verdict` out of the retry prompt's Fix list, or re-asking the lint alone before spending a generator call. Rule on it at the whole-branch review.
3. **A lint-rejected cache hit's failures are not carried into attempt 1's Fix list.** `_attempts` starts with `found = []` (`generator.py:851-870`). With the same prompt and key, the generator can reproduce the billboard and burn both attempts. Fix: seed `_attempts`' first prompt with the hit's lint failures.
4. **DRY.**
   - `_unfenced` (`llm_lint.py:107-112`) repeats `parse_reply`'s three fence lines verbatim (`generator.py:568-571`), and the public `strip_fences` (`metrics/judge.py:211-220`) is the third copy.
   - `_squash` (`llm_lint.py:103`) duplicates `generator._squash` (`:622`).
   - `LintCachePut` (`llm_lint.py:74`) is the same alias as `CachePut` (`generator.py:507`).
   - All are plan-mandated and tiny. Fix: reuse `strip_fences` and one `squash`, and use one alias.
5. **A prompt edit without a version bump reads stale verdicts.** The key covers `LINT_PROMPT_VERSION`, the model, the kind and the body (`llm_lint.py:96-100`), but neither the persona nor `_DEFINITIONS`. The definitions are also written twice, in the persona and in the user message, and can drift. Fix: a test pinning `sha256(persona + _DEFINITIONS)` to a value recorded beside `LINT_PROMPT_VERSION`, so an unbumped edit fails CI.
6. **Coverage gaps.**
   - No test of an off-contract reply followed by a good one: the verdict from ask 2, 2 calls, conversation id `.../1.2`.
   - No test that the generator hit is not noted in the ledger when the lint rejects it (P4's second half).
   - No run-level assertion that a stub-judge run has `llm_lint == []`.
   - No `"lint call"` entry in `KILLS` (`tests/test_generator_run.py:317`).
   - `_cached` (`tests/test_generator_run.py:106-107`) globs only `GENERATED_CACHE_DIR`, so the resume test's "nothing cached (P13)" line does not cover `_cache/lints/`.
7. **The spec's wording on the probe is wrong.** The "As planned" block and the `llm_lint.py` docstring say the probe caches "at once", but `scripts/llm_lint_probe.py:110, 117` builds `LlmLint` with no cache. Fix: correct the wording, or say the probe is uncached by design.
8. **`score` counts an `error` billboard as caught** (`scripts/llm_lint_probe.py:78-93`). This matches run behaviour (fail closed), but a probe run with many errors would flatter the billboard bar. `errors` is printed, but the erroring billboards are not listed by title. Fix: list error items in the report.
9. **The `offcontract_lint` mode is unused (report concern 5).** It is resolved if Important 2 is taken; otherwise it is dead code.

Report concern 6 (the `Final` import) is a correct fix, with no issue. Concern 7 (the four-item probe) is per carry 3 and the owner ruling, with no issue. The fill is the reviewer's separate job.

### Assessment

Task quality: Needs fixes

Reasoning: The code is correct and the controller-accepted deferral is complete and resume-safe. But the reviewer prompt exempts the project's own documented smuggle route (quoted lines) and lacks the fail-closed tie-break, and the fail-closed non-negotiable has no writer- or run-level test. Both are cheap to fix before the whole-branch review.

### Persona text judgment

- It names no model, maker or product: "assistant" is generic.
- It does tell the model what a billboard is in the project's sense:
  - the reader's past and nature, including by paraphrase (rule 1);
  - assistant-shaped habits written as a stage, symptom or procedure (rule 2);
  - an instruction only the reader could act on (rule 3).
- It does not hold the fail-closed rule. There is no "if you can't tell, it is", the pass list has no stated precedence under rules 1 to 3, and quoted lines are exempted wholesale (Important 1).
