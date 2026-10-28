# Task 3, fix round 5 (the last): open findings and method

A prior implementer attempted the second_person fixes four times (rounds 1 to 4); you own it now. Read the report file for what was tried, in order, and then the round 4 re-review: `.superpowers/sdd/2026-10-24-phase-3-world-generator/task-3-rereview-round4.md`. Start from HEAD (4c10eea).

This is the last fix round. After it, the controller adjudicates whatever is still open. An honest measured residual is worth more than a tuned number.

## Open findings

From the round 4 re-review (verbatim one-liners; the details, file:line and confirmed examples are in the re-review file):

1. **F1 (Important), billboards in the instructional kinds: at the limit with no margin.** The fresh probe gave 2/15 per kind, but two catches rest on misparses (N1, N2), so 3/15 per kind on the right reason. Residual classes that pass:
   - the reader's kin in a procedural slot: "Your wife will ring on Sunday evening, so keep the ward phone free.";
   - kin with an adjective predicate: "Your son is safe and well, so book a visit when you can.";
   - "letters your wife has left for you";
   - change-of-state verbs outside the frame list ("fade", "come back").
2. **F2 (Important), legitimate procedural false fails: 11/40 (27.5%) on the fresh probe, target at most 10%.** 8 of the 11 are closed-allowlist gaps ("display", "set", "jot", "suit you", "signed you off", "we recommend", "if you or your relative needs").
3. **N1 (Important).** `_event_veto` (second_person.py:916) reads "since/until the X who/<prep>" as a named time.
4. **N2 (Important).** `_is_ing` (:671) treats nothing, anything, something, morning and building as gerunds, so "keep anything valuable" fails.
5. **N3 (Important).** `_frame_veto` (:852) and `_tense_veto` (:876-887) fire on any subject, beyond the ruling. For example, "The cafe has moved ...", "If a slot becomes available, we will call you.", "We moved the visitor car park last spring ...".
6. **N4 (Important).** `_kin_predicate_ok` (:1019) returns True on any copula, so "Your son is safe and well ..." passes.
7. **N5 (ruled into this round).** A sentence holding a quote is reported twice (`classify`, :1124-1141). The unquoted copy's span is not in the document, so the retry message would list a span the generator never wrote.

## Targets (unchanged)

On a fresh probe the code was never tuned on, per kind (`family_faq`, `recovery_guide`):
- billboard false passes at most 2 of 15;
- legitimate procedural false fails at most 10%.

## Method (controller ruling for round 5, binding)

a. Fix N1 to N5, each with a fixture (RED first).

b. **The form side stops being a closed verb allowlist.** An anchor position takes any verb except a closed experiencer class: perception, cognition, memory, emotion, identity and change of state (feel, seem, notice, recognise, remember, forget, believe, wonder, picture, imagine, miss, fade, blur, become, and their kind). The anchor positions are:
   - imperative clause start;
   - after a modal;
   - after "if you";
   - "we/staff will <verb> you".

   An object "you" after any non-experiencer verb is a service object, except for the agent-on-you veto (placed, put, moved, made, told or changed you). The evidence: 8 of 11 fresh false fails were list gaps. Procedure verbs are an open class, while the experiencer class is near-closed.

c. **The content side stays strict and closed.** In the instructional kinds, "your" plus a specific kin noun (wife, husband, partner, son, daughter, mother, father, brother, sister, child or children, grandchild, and their kind) fails in any slot. Only generic kin references pass, and only in a procedural slot: "your relative", "your loved one", "your family member". The overlay's central fact is the reader's wife, and "if you can't tell whether something is a billboard, it is". The role rules for the reader (experiencer, predicate nominal, past or perfect with a non-procedural verb) stay. Restrict them to the reader, a "your" noun phrase, or a body or self noun, as the round 4 ruling said, not any subject (N3).

d. **Repair hint.** Every failure message from the instructional kinds carries a repair hint, for example: "rewrite this sentence without 'you' or 'your': use the third person (visitors, families, residents) or a bare instruction". A sentence with no second-person word always passes this lint, so a false fail that names its sentence is repairable in the generator's one retry. Keep the existing message prefixes the tests pin, and append the hint.

e. **When the two targets trade off, the billboard target wins.** A false pass ships a billboard. A false fail costs a retry that the hint makes repairable.

f. **`second_person.py` must not grow beyond its 1141 lines, and should shrink** as the overlapping verb classes collapse (`PROCEDURAL_VERBS`, `TRANSACTIONAL_VERBS`, `_OBJECT_VERBS`, `_TO_VERBS`, `_CARE_VERBS`, `_NAME_VERBS`, `_CALL`). Keep `lint_document -> list[LintResult]` and the module's public classifier unchanged.

g. **Probe sets.** Before changing code, write two fresh probe sets of your own: 15 billboards and 20 legitimate procedural sentences per kind, for both kinds.
   - Vary the legitimate vocabulary widely, the way a real care-home FAQ or recovery leaflet would. Do not lean on any verb list.
   - Tune on set A only, and report set B once, honestly.
   - Do not open the round 4 re-reviewer's probe sentences beyond those quoted in the re-review file.
   - Keep the probes in `.superpowers/sdd/2026-10-24-phase-3-world-generator/probes-round5/`.

h. Update the module docstring and the Billboard row of `docs/08-DIRECTOR.md` to match the rule as built.

## Gate

Before you commit, run every step (all must pass, 0 warnings):
- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy claude_bully`
- `uv run pytest -q -W error`
- `uv run pytest -q -m slow`
