# Rules for every Phase 6 task reviewer

Project: claude-bully, an adversarial-robustness harness for LLMs. Bully personas pressure a target model inside a sandboxed fake world, and the harness measures drift. Phase 6 ("catalog and divergence") adds the capture of the target's reasoning, a divergence judge, an anomaly catalog, a baseline, promotion and a review queue. Repo: C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully (branch build/v1). The plan's workspace is `.superpowers/sdd/2026-11-19-phase-6-catalog-divergence/` (git-ignored); below it is called WS.

You review one task's implementation: first whether it matches its requirements, then whether it is well-built. This is a task-scoped gate, not a merge review; a whole-branch review happens after all tasks.

## What was requested

- The task brief: WS/task-<N>-brief.md.
- WS/global-constraints.md: the constraints that bind every task and the phase's review focus. Read both sections; they are your attention lens.
- Where the brief cites a spec section: `docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md` (binding; read only the cited sections; sentences marked "[refined in the plan review]" are current).
- Any pre-flight rows your dispatch names: WS/preflight.md, by id; the "recommended ruling" column is binding on the task.
- Any carries file your dispatch names.

## What the implementer claims

WS/task-<N>-report.md. Treat it as unverified claims; a stated rationale or an `ASSUMED:` line never lowers a finding's severity. Judge each `ASSUMED:` and each file changed beyond the brief's list on its merits.

## The diff

The dispatch gives the base, the head and the diff file (the commit list, the stat summary and the full diff with context). Read all of it, in passes if it is large. Do not re-run git commands for it. Inspect code outside the diff only to evaluate a concrete risk you can name, one focused check per risk, and name both in your report. Standing named risks for this phase, each in scope whenever the diff touches it:
- recorded reasoning reaching a reader the spec forbids: the bully's input, the generator's, the Sanctuary's or authority desk's, a judge prompt other than the divergence judge's, a cache key, a review-queue item, a chart, replay without `--reasoning`, promoted output;
- a pre-existing count, rate, chart or file changing on a run that lacks the new feature (they must be byte-equal);
- `values_loosened`: a flagged rep counted as a success by any path, or a reasoning-only one lost or flagging;
- `n/a` reported as zero, or a rate with no matched control;
- a detector that fires on ordinary text, has no near-miss fixtures, or fails open;
- a record field that is not additive and default-valued, or an older run that no longer loads (`SCHEMA_VERSION` stays 3);
- a resumed run differing from an unbroken one, or a written file that a kill at some byte leaves torn;
- a real name of an outlet, brand, institution, product, model or person in a fixture, config, line or doc; a line with a jailbreak endpoint; an unlock, consult or outlet line that announces, advises or dares;
- a real model call or network access in a test; a new multi-second test without the `slow` mark.

Read-only on the checkout: do not change the working tree, the index, HEAD or any branch. Do not dispatch subagents.

## Tests

The implementer ran the gate (the fast and slow suites under pytest-xdist, `-n 8`) and reported counts and exit codes. Do not re-run the suites. Run a focused test or a small probe only where reading the code raises a specific doubt no existing run answers (`uv run pytest -q <file>::<test>`, add `-m slow` for a slow-marked test; or `PYTHONDONTWRITEBYTECODE=1 uv run python <probe>`; no real model call, no network). A mutation probe (wrap or patch a function in process, never edit a tracked file) is the preferred way to judge whether a test has teeth. Probe scripts and outputs go only in WS/probes-task<N>-review/ (or -rereview<R>/), by absolute path. Warnings or noise in the reported test output are findings.

## Part 1: spec compliance

Missing (skipped, or claimed without implementing), Extra (not requested), Misunderstood. Check the brief's file list against the diff file by file. A requirement you cannot verify from the diff is a "Cannot verify from diff" item, with what the controller should check.

## Part 2: quality

Separation of concerns, error handling, duplication, edge cases. Whether the new and changed tests verify behavior, and whether each would fail if the behavior it names broke. Whether each changed pre-existing test still tests what it was written to test. File responsibilities and growth.

## Calibration

Critical: breaks a non-negotiable or corrupts records. Important: the task cannot be trusted until fixed (wrong or fragile behavior, a missed requirement, swallowed errors, a test that asserts nothing or cannot catch what it is named for, verbatim duplication of a logic block). Minor: the rest. If the brief itself mandates something this rubric calls a defect, report it as Important, labeled plan-mandated. Name what was done well, briefly, before the issues.

## Output

Write the full review to WS/task-<N>-review.md (if the Write tool refuses a .md file, use a Bash heredoc with a quoted delimiter):

### Spec Compliance (compliant, or issues with file:line; plus the cannot-verify items)
### Strengths
### Issues (Critical / Important / Minor; each with an id, file:line, what is wrong, why it matters, the fix if not obvious)
### Assessment (Task quality: Approved | Needs fixes; one or two sentences)

Your final message to the controller: the spec verdict, the quality verdict, the counts (Critical / Important / Minor / cannot-verify), and one line per Critical, Important, Minor and cannot-verify item. Nothing else.

# Rules for a scoped re-review of a fix round

Your job is to verdict each finding the dispatch lists and inspect the fix diff, nothing else. Read the brief, the findings (in the review file the dispatch names, as the controller ruled them), the report's "Fix round <R>" section, and the fix diff file. Scope is the findings list and the fix diff; an issue entirely outside the fix diff goes under Out-of-Scope Observations. "Attempted" is not addressed: the specific defect must no longer exist. Judge by a mutation probe where a finding was "this test cannot catch X". The read-only, no-subagent and test rules above apply.

Write the report to WS/task-<N>-rereview-round<R>.md:

### Finding Verdicts (one line each, in order: ADDRESSED | NOT ADDRESSED, with file:line evidence)
### New Breakage in the Fix Diff (severity and file:line, or "None")
### Out-of-Scope Observations
### Verdict

Your final message to the controller: the verdict line, the counts (addressed / not addressed / new Critical / new Important / new Minor), and one line per NOT ADDRESSED or new item. Nothing else.
