# Task 8 review: the rate-limit wait, promote's real-name policy, the README chart links (7c22de9..c06bed1)

### Spec Compliance

- Issues found (two, both on the real-name exemption, both plan-mandated by the brief's code; everything else matches the brief, the carries and the binding rulings):
  - Misunderstood, scope of the `--exempt` exemption. `claude_bully/analysis/promote.py:83-117` (`_hits`, `scan_real_names`) and `claude_bully/analysis/promote.py:134` spare the `--exempt` names in every scanned text. Spec section 10 spares "the target's `display_name` and its own maker" in target text only. The display name being spared everywhere is right; the maker being spared everywhere is not (see verdict (a) below). The spec's "As planned" amendment (`docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md:476`) writes the wider rule into the spec.
  - Misunderstood, the exemption method. `claude_bully/analysis/promote.py:76-80` (`_spared`) deletes the exempt name from the text before the patterns run. That defeats the denylist's family-plus-version entries for an exempted family. See verdict (b).
- Checked and compliant:
  - Brief file list: `runner/wait.py` and `tests/test_wait_and_promote.py` are created. `cli.py`, `analysis/promote.py`, `HANDOFF.md`, `docs/00-RECONCILED.md` (section E at line 118, G11) and the spec's "As planned" are modified. `.gitignore` is untouched (diff stat).
  - There are 8 new tests in `tests/test_wait_and_promote.py` (lines 45, 52, 58, 68, 120, 132, 157, 188).
  - Two test files outside the brief's list are modified, and both are justified by the carries: `tests/test_authority_fallback.py` (carry 3, the fallback case) and `tests/test_judge.py` (carry 2).
  - C37 and P26: `claude_bully/runner/wait.py:33-37`. It catches `RateLimitExit` only. With no ceiling it re-raises at once. `retry_after_s` or `DEFAULT_WAIT_S` is used. It re-raises when the next wait would pass the ceiling. `sleep` and `say` are bound inside the call.
  - Both commands use the helper: `run` at `claude_bully/cli.py:78` and `analyze` at `claude_bully/cli.py:127`. The exit-3 handlers are unchanged.
  - C19 and P10: the policy sits between `scan_run` and the copy loop (`claude_bully/analysis/promote.py:133-141`). A blocking hit raises `ValueError` before `dest` is touched, and the test asserts that nothing was written (`tests/test_wait_and_promote.py:120`).
  - C17: `claude_bully/cli.py:53` and `claude_bully/cli.py:244` (`relpath`, posix). The flag gates the rewrite. Without it, links are untouched (the second half of `tests/test_wait_and_promote.py:188`).
  - Carry 1: HANDOFF Task 7 ranges filled (`e48783f..7c22de9`, `6c4c1f6..7c22de9`); own entry uses "7c22de9..Task 8 commit".
  - Carry 2: `tests/test_judge.py` `test_the_pair_prompt_text_is_pinned` pins the sha256 of `build_pair_prompt`. Its comment carries the version-bump warning.
  - Carry 3:
    - `retry_after_s` comes from `RateLimitExit`, which the runner fills from `RateLimitError` (`claude_bully/runner/runner.py:334`, focused check).
    - A timeout is not a `RateLimitExit`.
    - The fallback rate limit is waited on, in `tests/test_authority_fallback.py` `test_analyze_waits_out_a_rate_limit_in_the_fallback`.
    - The Calls line has no `.png` link, so `_CHART_LINK` cannot touch it.
  - Pinned item "promote blocks on a harness-side real name and only reports a target-side one": tested for bully and target turns (`tests/test_wait_and_promote.py:120`, `:132`).
  - Commit: authored `Brian Rankin <rankinbc1@gmail.com>`, with the mandated trailer, in one commit. LF on every changed file (`git ls-files --eol`).
- Cannot verify from diff:
  - Pinned item "a rate-limited call writes a `rate_limit` line and the wait helper re-runs the action until the ceiling". The re-run until the ceiling is tested (`tests/test_wait_and_promote.py:58`). No test reads the ledger after a waited re-run. The controller should check that a `run --wait-on-rate-limit` over a stub that rate-limits once leaves exactly one `rate_limit` line and one pause marker in `ledger.jsonl` and the turns. The Task 2 paused-run test pins the line for the unwaited path only.
  - In-process resume of the real `run_experiment`. `tests/test_wait_and_promote.py:68` replaces `run_experiment` wholesale. The runner enters `activate()` per call (`runner.py:770`), so re-entry looks safe, but no test runs the real runner twice in one process after a pause. The controller should run it or add the test described above.
  - The reported gate counts (8332 passed, 0 warnings). Not re-run, per instructions.

### Strengths

- `wait.py` is small, correct and typed. Its failure modes are explicit:
  - None or 0 falls back to the default.
  - A first wait over the ceiling re-raises with nothing slept: `waited + delay > ceiling` at `wait.py:37` takes the same branch as the tested third wait.
  - A timeout is never caught.
- The P26 binding is honest. The CLI tests patch `time.sleep` after the import and no test sleeps for real.
- The fallback-wait test is a real end-to-end check (CLI, real `analyze_run`, a judge that rate-limits once). It asserts the slept value and the resulting `authority.json`, so the cached verdicts replay correctly across the in-process retry.
- Departures from the brief, all sound:
  - `_say` escapes rich markup (`cli.py:56`). An error text with `[` cannot be swallowed or mis-styled. This improves on the brief.
  - `_link_charts` is a module function (`cli.py:60`). It is the correct response to B023, it is testable on its own, and the regex is unchanged.
  - `promote_run` runs before the report (`cli.py:274-276`). The rationale is verified: `display_names` reads `run.json`, so scanning first would turn "no run named ..." into a raw file error. A blocking hit still raises before anything is copied.
  - The RED-order note is correct: the test module imports `analysis.promote` names before `runner.wait`, so `ImportError` on `RealNameReport` is the first failure. This is not a substantive disagreement.
- The carry 2 pin was cross-checked against the pre-Task-7 text. That is the right way to show the refactor was byte-identical.
- Non-negotiable 2, check (c): I scanned the diff's added lines against `data/denylists/real_names.txt`. There are three hits:
  - One is a pre-existing word on the rewritten G11 line in `docs/00-RECONCILED.md` (the line gained a sentence; the name was already there).
  - Two are the target's own display name "Claude" in `tests/test_wait_and_promote.py:158-161`. That is G11-exempt and brief-mandated.
  - The maker's name is never written. The `--exempt` test passes `REAL[0]`, and the outlet comes from `REAL[3]`.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **The strip-before-scan exemption defeats the denylist's family-plus-version entries (plan-mandated, brief Step 3 `_spared`).**
   - Where: `claude_bully/analysis/promote.py:76-85`.
   - What is wrong: `_spared` deletes every word-bounded occurrence of an exempt name, then runs the patterns over what is left. The denylist's header (lines 5-6) says a model family followed by a version is a real name ("fable 30.5"). Its entries `\bgpt-?\d\w*\b`, `\bgemini-(?:pro|flash|ultra|nano|exp)\b`, `\bfable[ -]?\d+\b` and `\bgemma ?[0-9]+\b` span more than the family word. Deleting the family word (a `-` is a non-word boundary) leaves a remainder no pattern matches.
   - Focused check (`uv run python`, `_hits` against `load_real_name_patterns()`):

     | Text | Exempt names | Hits |
     |---|---|---|
     | `'Ask GPT-5 instead.'` | `{'GPT'}` | `[]` |
     | `'Ask GPT-5 instead.'` | none | the `gpt` pattern |
     | `'Try gemini-pro.'` | `{'Gemini'}` | `[]` |
     | `'Fable 30.5 is out.'` | `{'Fable'}` | `[]` |
     | `'Gemma 2 says hi'` | `{'Gemma'}` | `[]` |

   - Why it matters: for any target whose `display_name` is its family name, a bully line, generated document or responder reply naming another version of that family passes the blocking gate silently. That is a non-negotiable-2 breach in committed `results/`. Today's Claude target loses nothing only because the denylist has no versioned `claude` entry. Adding one, by the header's own rule, would be silently defeated for every Claude run. The gate is fragile against its own data file.
   - How to fix: keep the text whole and skip a match only when the matched span is itself an exempt name:

     ```python
     def _hits(text, patterns, names):
         spared = {n.strip().casefold() for n in names if n.strip()}
         return [p.pattern for p in patterns
                 if any(m.group(0).strip().casefold() not in spared for m in p.finditer(text))]
     ```

     This spares "I am Claude" and "Claude 3 Opus" while `\bclaude\b` is the only claude entry, and blocks "GPT-5" under a "GPT" exemption. Add one test using an exempted family (take the name from `REAL`, e.g. `REAL[8]` "GPT-4o" against an exempt `"GPT"`, built from a slice so no new literal is written) that asserts the versioned name still blocks. Amend the spec's "As planned" line (`design.md:476`), which states the "removed ... before the denylist runs" method.

2. **`--exempt` names are spared on the harness and world side; spec section 10 spares them in target text only (plan-mandated, brief Step 3 / C19's wording followed literally).**
   - Where: `claude_bully/analysis/promote.py:134` (one `names` set passed to every branch at `:88-117`), `claude_bully/cli.py:272-276`, and the spec amendment at `docs/superpowers/specs/2026-11-06-phase-7-first-real-runs-design.md:476`.
   - What is wrong: the owner will pass the maker's name with `--exempt` on every real promotion, because a target saying who made it is the expected case. With one exemption set, that same flag also spares the maker's name when the bully says it, when the generator writes it into a corpus document, in a tool result and in a responder reply. Those are exactly the texts the harness must never author with a real name. The real-name block on harness-side text is turned off for the one lab name most likely to appear there (the creator and superior-self premises).
   - Why it matters: the spec is the binding authority, and it is narrower on purpose. C19's text lists the exempt names without saying where they apply, so it does not override the spec. The brief's code widened the rule.
   - How to fix: split the exemption. `scan_real_names(store, patterns, exempt, *, target_exempt=())`, where `display_names(store)` are spared everywhere and the `--exempt` names in target turns only. In `promote`: `scan_real_names(store, pats, display_names(store), target_exempt=exempt)`. Add a test where a bully turn names `REAL[0]` with `exempt={REAL[0]}` and promotion still blocks. Correct the "As planned" ruling and the HANDOFF Task 8 entry, which says "each `promote --exempt NAME` ... is spared".

#### Minor (Nice to Have)

1. `scan_real_names`'s tool-result, generated-document and responder branches (`claude_bully/analysis/promote.py:101-115`) have no test. These are the world-side texts most likely to carry a real name. mypy checks the attribute names; nothing checks the routing to `blocking` or the source line. An annex run (as `tests/test_authority_fallback.py` uses) with one generated body, one tool result and one responder reply rewritten to hold `REAL[3]` would pin all three. The implementer admits this gap.
2. No test covers "a first wait that already passes the ceiling" (`wait.py:37`, e.g. `_flaky(1, 7200)` with a ceiling of 60 must re-raise with `slept == []`). No test covers "a timeout is not waited on" (a `ProviderTimeoutError` raised from the action must propagate with nothing slept). Both are one-line tests of stated contracts.
3. `tests/test_wait_and_promote.py:99`: the "without" call asserts only exit 0. The comment says "no flag, no wait", but the third call never rate-limits, so it proves neither. Make the first call without the flag rate-limit, then assert exit 3 and `slept` unchanged.
4. `claude_bully/cli.py:272-276` scans twice and rebuilds `display_names(store) | names`, duplicating `promote.py:134`. Have `promote` return the report (or take it as a parameter), so the CLI prints what the gate decided rather than a second computation that could drift (for example, after fix 2 the two unions must change together).
5. The `ValueError` at `claude_bully/analysis/promote.py:137-140` lists the first five hits with no total. Add "(N in all)" so the owner knows how much to clean.
6. `claude_bully/cli.py:244` resolves the README but not `analysis`. `os.path.relpath` uses `abspath` for the other side, so a symlinked or junctioned README directory gives a wrong `../` chain. On Windows, a README and a results root on different drives raise a bare `ValueError`. Use `analysis.resolve()` for symmetry and give the cross-drive case a `typer.BadParameter`.
7. The HANDOFF Task 8 entry (`HANDOFF.md:178`) says "Phase 5's `plan` takes the same flag through the same helper" in the present tense. `plan` does not exist yet. docs/00 line 118 words it correctly ("which `plan` takes in Phase 5").

### Verdicts on the asked questions

- (a) Exempting the `display_name` in every text is right. It is the target's own name (non-negotiable 2's "other than the target's own API string", G11). A bully line that addresses the target by its display name ("Claude, you said ...") must not block, and under the spec's literal narrower rule it would block every real run. The `--exempt` names (the maker) should hold the spec's narrower rule. Spare them in target text only, so a bully line, generated document, tool result or responder reply naming the maker still blocks (Important 2). The bully line that names the target by display name then still passes; nothing about it changes.
- (b) The strip-before-scan method is not sound against the denylist. It defeats every family-plus-version entry (`gpt-?\d`, `gemini-pro`, `fable N`, `gemma N`) for an exempted family; the focused probe confirmed this. It also hides a versioned name built on "Claude" the day such an entry is added. A whole-match exemption (skip a match only when its span equals an exempt name, and scan the rest of the text) is needed (Important 1). Strip-before-scan can, in principle, also manufacture a match by joining the text around the removed name. Against today's entries I found none that two non-word neighbours can complete, so this is not a finding.
- (c) No code, fixture or doc line in the diff writes the maker's name or a real model name. The only added denylist hits are the target's own display name in one test (G11-exempt, brief-mandated) and a pre-existing word on the rewritten G11 line. The tests take their positives from `tests.test_real_names.REAL`.

### Assessment

Task quality: Needs fixes

Reasoning: The wait, the link rewrite and the carries are correct and well tested. The real-name gate, though, is weaker than the spec in two plan-mandated ways: the exempt name is stripped before the scan, which defeats the denylist's versioned entries, and the maker exemption applies to harness-side text. Both silently let a non-negotiable-2 breach into committed `results/`.
