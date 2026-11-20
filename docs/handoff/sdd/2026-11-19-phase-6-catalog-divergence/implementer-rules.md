# Rules for every Phase 6 implementer

Project: claude-bully, an adversarial-robustness harness for LLMs. Bully personas pressure a target model inside a sandboxed fake world (a document corpus served through tools), and the harness measures drift. Phase 6 ("catalog and divergence") adds the capture of the target's reasoning, a divergence judge, an anomaly catalog, a baseline, promotion and a review queue. Seventeen tasks: 1, 2, 3a, 3b, 4a, 4b, 5, 6a, 6b, 7a, 7b, 8, 9, 10a, 10b, 11, 12.

Work from C:\Users\Brian.Rankin\claude-workspace\projects\ClaudeBully (branch build/v1, one working tree; you are the only one writing to it). The workspace for this plan is `.superpowers/sdd/2026-11-19-phase-6-catalog-divergence/` (git-ignored); below it is called WS.

## Read

1. Your task brief (WS/task-<N>-brief.md): your requirements, with the exact values to use verbatim.
2. WS/global-constraints.md: the constraints that bind every task and what the reviewer looks hardest at.
3. Where the brief cites a spec section: `docs/superpowers/specs/2026-11-19-phase-6-catalog-divergence-design.md` (binding; read the cited sections, not the whole file). Sentences marked "[refined in the plan review]" are current.
4. Any pre-flight rows your dispatch names: WS/preflight.md, the row by its id (Q<n>); the "recommended ruling" column is binding.
5. Any carries file your dispatch names.
Never read the whole plan file.

## How to work

- TDD: write the failing tests first, run them, save the RED output, then write the code. For a detector, write the adversarial fixtures (positives and near-misses) before the detector.
- While iterating, run only the test files you touch. Before the commit, run the whole gate once, each step as its own command with its own exit code, every step with 0 warnings:
  `uv run ruff format --check .`
  `uv run ruff check .`
  `uv run mypy claude_bully`
  `uv run mypy --platform linux claude_bully`
  `uv run pytest -q -W error -n 8`
  `uv run pytest -q -m slow -n 8`
  The two pytest steps run in parallel under pytest-xdist: about four to five minutes each. Save each command line with its output and exit code to a file in your probes folder. Do not report a count you did not see. If a test outside your change fails, find out why before you touch it; never edit or skip an unrelated test to get green; if you must change a test outside the brief's file list, say which and why in the report. A test that passes alone and fails only under `-n 8` (or the reverse) is a finding: name it.
- Mark `slow` any new test that takes more than about four seconds (measure with `--durations`), with a comment naming the measurement.
- No real model call and no network in any test: stub providers and `tests/fixtures/fake_claude.py` only.
- One commit for the task, its docs-sync step included, with the commit message the brief gives. Author email `rankinbc1@gmail.com` (check `git config user.email`). End the message with the trailer naming your own model, for example `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, whatever the brief's sample says. Never push. Never amend or rebase earlier commits. A fix round is one new commit on top.
- Do not dispatch subagents, for help or for review.
- Scratch files (probes, test outputs, backups) go in WS/probes-task<N>/ by absolute path, never in a tracked path and never by a relative path.
- No emojis and no em dashes in Markdown. No real names of outlets, brands, institutions, products, models or people in any fixture, test, config or doc.
- If the brief and the code disagree in a way the brief did not foresee, choose the reading that serves the spec, write it in the report as `ASSUMED: <what> (<why>)`, and go on. Stop with BLOCKED or NEEDS_CONTEXT only when every path forward is a guess.

## Self-review before reporting

Read your own diff. Everything in the brief implemented, nothing extra built. Tests assert behavior and would fail if the behavior broke. The target's reasoning reaches no reader the spec forbids (the bully, the generator, the Sanctuary or authority desk, a review-queue item, a chart, a cache key). Every pre-existing analysis output on a run without the new feature is byte-equal. `SCHEMA_VERSION` is 3, new fields are additive with defaults, older runs load. A run killed anywhere and resumed equals an unbroken one. Every file the task writes survives a kill at any byte.

## Report

Write the full report to WS/task-<N>-report.md (if the Write tool refuses a .md file, use a Bash heredoc with a quoted delimiter): what you implemented; the RED and GREEN evidence (commands and the relevant output); the gate's counts and exit code for each step as you saw them; measured times of any multi-second test; files changed; each `ASSUMED:`; the self-review's findings; concerns. A fix round appends a "Fix round <R>" section: per finding what changed, the covering tests, the commands, their output, the gate counts.

Then reply with only (under 15 lines): Status (DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT); the commit (short SHA and subject); the gate counts in one line; your concerns, if any; the report path. If BLOCKED or NEEDS_CONTEXT, put the specifics in the reply.
