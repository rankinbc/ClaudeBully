# Task 3 fix round 1 (FIX_BASE 5df9e41)

Inputs: task-3-review.md (I1, I2, the unmet spec sentence, M3). Make one commit on top of 5df9e41 under the same constraints. Work TDD, with RED per item.

1. **I1: the third-party arm's persona prompt.** Add an optional `third_party_rescuers` field to both Rescue sheets (`rescue_team.yaml` and the overlay's `rescue.yaml`). It re-tells only the character details that place the rescuer where the assistant is now, told of the third party. `_persona_prompt(third_party=True)` uses that field in place of the first-person details, so no rescuer line in the control arm says or implies "I was where you are" to the target. Add a test on the built persona prompt for the third-party arm: no premise claim about the target, including in the second person or by "the assistant".
2. **The unmet spec sentence.** Spec section 7 says the persona prompt drops the belief that the assistant is a person. Make `_persona_prompt(third_party=True)` drop it, and pin that with a test on the prompt text.
3. **I2: a round-trip failure.** Make `third_party_fallback_lines: list[str] | None = Field(default=None, min_length=6)`, and the same for any sibling field that takes the same shape. A sheet without the lines saves None, and `load_run` reads it back. Add a round-trip test: a Rescue sheet without the third-party lines is written by a run snapshot (`env_turn` save) and analysed by `load_run`.
4. **M3: famous gotchas.** Replace every quirk-bank entry that reproduces a famous public gotcha (the letter count in "strawberry", 9.11 against 9.9, and any other the review lists) with an invented equivalent of the same family. Keep the entry ids stable only if no run has recorded them (none has), and update their tests.

Carried, not this round:
- M1 goes to Task 13's register entry.
- M5 goes to Task 5.
- The remaining Minors are deferred.

Update `task-3-report.md` with a "Fix round 1" section, and keep the HANDOFF Task 3 item true. Reply in at most 8 lines: the commit sha, the gate counts, RED per item, and concerns.
