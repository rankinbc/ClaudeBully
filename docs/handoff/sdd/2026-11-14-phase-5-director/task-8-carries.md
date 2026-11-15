# Task 8 carries

These come from the ledger. They bind this task alongside the brief and the preflight rows that name Task 8. Those rows include Q42 to Q45:
- Q42: the stub's dull replacement sentence makes a second review round fail.
- Q43: a provider error on a confirm call fails stage 4, per spec section 13.
- Q44: the confirm check must not refuse a missing number.
- Q45: the `no_response` mode is never defined.

## The binding carries

- **Task 6 re-review R1, and Task 7b.** Before each reviewer call and each confirm call, run the denylist scans on the bundle:
  - `real_name_bundle`, with the owner clause;
  - Boundary;
  - jailbreak (review.md stays exempt).

  A hit blocks the call as a lint failure, and the scans never raise. Stage 2 already scans plan.md, so reuse that path rather than writing a second one.
- **Task 7b round 2.** `review_groups` uses `context.unchanged_base_files`; it is the rule's one home. Add a test that pins `review_calls == len(review_groups)` for the good bundle and for the overlay plus two new documents.
- **Task 7b's budget.** It is a lower bound: repairs, revise and confirm calls are not counted. Count the review stage's calls by the same rule, so the manifest's call budget stays honest.
- **Task 7a and 7b primitive rules.** Use them all:
  - a pure parse;
  - a frozen budget;
  - replay from the committed call list;
  - one dead attempt per marker;
  - `ledger_lines`.

  Test resume parity at every kill point the spec names for stages 3 and 4, including hard kills inside each write. Use Task 7b's sweep probe: `.superpowers/sdd/2026-11-14-phase-5-director/probes-task7b-fixround1/`.
- **Task 6.** Every message goes through Task 6's context builders.
  - The reviewer and confirm calls never see review.md.
  - The confirm prompt carries no revision cue (D-confirm).
  - Each judge prompt is neutral and blind.
  - No message holds `reasoning_text`.
- **Phase 4 lessons.**
  - A rate limit pauses the run and never degrades it.
  - Stub providers only.
  - Every pytest run uses the pyproject `faulthandler_timeout` (120 s).

## Environment cautions

- **Disk:** the machine has about 2 GB free. Delete every killed bundle and temporary run as soon as you have compared it. Keep probe output under 200 MB. Check free space before and after with PowerShell `Get-PSDrive C`, and stop and report if it drops under 1 GB.
- **Regex lines:** write them with the Edit tool only.
- **Shell writes:** never redirect one to a bare relative path.
