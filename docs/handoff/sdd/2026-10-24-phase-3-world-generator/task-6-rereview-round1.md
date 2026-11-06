# Task 6 re-review, fix round 1 (9f3fddc..e5ce59a)

Scope: Minors 1 to 3 of task-6-review.md (1 and 2 regraded to Important) and the fix diff. Evidence: the diff file, the files at e5ce59a, one scratch probe of `unwrap_body` (scratchpad `probe.py`), and a focused run of `tests/test_generator_writer.py` (34 passed, `-W error`). The full suite was not re-run.

## Finding Verdicts

### 1. Important: a quoted span holding a line break (unwrap vs quote rules and redact): ADDRESSED

The implementer took the "never join inside a double-quoted run" option from the review, and also added whitespace normalisation to the seam check.

- Unwrap (generator.py:557-590). `quoted = straight % 2 == 1 or curly > 0` (:575) is the quote state at the start of `line`, which is the state at the break being considered. `and not quoted` (:578) blocks the join. The counters update from the raw line after each decision (:588-589). Straight and curly double quotes are both tracked; the curly counter is clamped at 0. A span that sits inside a double-quoted run therefore reaches the quote rule and `redact` exactly as the target wrote it, and both are unchanged exact-match code (:830 `span not in body`, redact.py:36).
- Seam check (generator.py:593-597, :839). `_squash(item.span) in _squash(body)` collapses every whitespace run on both sides. This makes the seam guard independent of the unwrap: a verbatim span escapes it only by differing in non-whitespace characters. The previous exact-match gap (span with a space where the target had a newline) is closed as well. Verified by the probe: an unquoted multi-line span that the unwrap joins is not `in` the unwrapped body, but `_squash(span) in _squash(body)` is True.
- Required near-miss tests exist and pass at head:
  - Seam doc with a verbatim multi-line span fails `verbatim_in_seam`: tests/test_generator_writer.py:430 (`test_a_seam_document_quoting_a_multi_line_span_is_refused`, gaps `"\n"`, `" "`, `"\n  "`, asserts `rejected`/`contract` and `[VERBATIM_IN_SEAM]` after two attempts).
  - Buried doc with one passes the quote rule: tests/test_generator_writer.py:388, scripted (not the stub), asserts `written`, two prompts (no retry), the span present in the served body, and the second span redacted with its break kept.
  - Unwrap cases for straight and curly runs added to `test_unwrap_joins_hard_wrapped_prose_only` (:379).
- The "\n" seam gap is pinned by the unwrap change alone; the `" "` and `"\n  "` gaps are pinned by `_squash`. The two fixes are each covered.

### 2. Important: lowercase header fields joined: ADDRESSED

- `_FIELD` is now `^[a-z][\w /&-]{0,30}:(?:\s|$)` with `re.IGNORECASE` (generator.py:478).
- The join is refused when either line matches: `_FIELD.match(before.lstrip()) is None` (:582) and `_FIELD.match(line) is None` (:583). `line` needs no `lstrip` because the gate before it is `line[:1].islower()` (:579).
- The case `requester: Dag Quenby\nstatus: open\npriority: low` is in `test_unwrap_joins_hard_wrapped_prose_only` (tests/test_generator_writer.py:363-365), and it passes.
- Both options the review offered (case-insensitive pattern, current-line check) were applied.

### 3. Minor: "never echoed" overclaim: ADDRESSED

- generator.py:472-474 comment now reads "the real_name and boundary results are not echoed" and adds that a sentence another lint's result echoes may still hold such a match. generator.py:661 already says "a denylist match (`UNECHOED_LINTS`) is not echoed", which is accurate.
- docs/02-ENVIRONMENTS.md:107 and HANDOFF.md:129 carry the required wording. docs/02 also states the caveat.
- A repo grep (excluding `.superpowers`) finds no remaining "never echoed" or "never echo" claim. Nothing in the design spec makes the claim.
- Prose nit only: the unwrap sentence in docs/02:107 now reads "joins a line before it that ends in no sentence or clause mark, is no `>` line, when neither line is a header field in any case ..." The comma-"when" run-on is awkward but not wrong.

## The implementer's claims, judged

- Single-quoted runs untracked, "fails closed": HOLDS. Seam: `_squash` catches the span whether or not the unwrap joined it. Buried: a joined single-quoted span is not `in` the body, so the quote rule fails with a contract failure before redaction ever runs, and the retry follows. Redaction is only reached for spans the rule accepted, so no unredacted real name reaches a served body by this route.
- Unbalanced double quote "fails closed": PARTLY HOLDS, overstated. Confirmed by probe that one stray `"` (for example `5" pipe`) turns joining off for the rest of the document (`'The 5" pipe burst.\nVisitors can park ... when\nthe night crew book a slot.'` comes back unjoined; the balanced twin joins). Sentence-level lints then see orphan lines, which fails closed at worst by one retry. It is not fail-closed for the denylist lints, which are literal-space regex searches over the whole body (planner/lints.py:135-158; patterns such as `\bwall street journal\b`). A phrase hard-wrapped across the break in the unjoined region is not matched: probe, `'The 5" pipe burst.\nThe porter read the wall street\njournal on Friday.'` gives no real_name hit raw or after unwrap, while the same sentence without the stray quote is joined and hits. See New Breakage 1 for severity.

## New Breakage in the Fix Diff

1. Minor, generator.py:575-578 (with planner/lints.py:145-157): the quote-state gate widens the region where a lowercase-continued hard wrap stays unjoined (inside any double-quoted run, and for the rest of a body after an unbalanced `"`), and `real_name` / `boundary` search with literal single spaces, so a multi-word denylist phrase split across such a break is not caught. Narrow: it needs a hard wrap (persona rule 8 asks for one line per paragraph), a lowercase continuation (a capitalised outlet name such as "Wall Street\nJournal" was never joined, before or after this commit, so the dominant case is a pre-existing gap), and either a quoted run or a stray quote. Not Important. A cheap remedy for Task 7 or later: run the two denylist lints over a whitespace-normalised copy of the text. The lints are outside this diff.
2. Minor, generator.py:575: one stray straight `"` (an inch mark, an unclosed dialogue quote) disables joining to the end of the document. The risk is a lowered join rate and one extra retry, not a wrong serve (apart from item 1). No fix needed now; a per-paragraph reset of the parity at each blank line would bound it, if wanted.
3. None for the specific doubt raised on `verbatim_in_seam`. The whitespace-insensitive check only adds matches that differ from the old exact match in whitespace alone, so a seam document is newly rejected only when an offered span of 3 or more words appears word for word, same case, with its words split by a different whitespace run (a newline, a paragraph gap, a double space). A seam document that reuses a span's terms in its own voice (different words, order or case) is unaffected. A coincidental cross-line match needs the whole 3-plus-word span to straddle a line or paragraph break; probe: `"the kettle trips again"` matches `"...the kettle\ntrips again later"`. That is the intended fail-closed direction, and rare for harvest spans, which are near-whole-sentence templates.

## Out-of-Scope Observations

- Buried documents still need an exact match for a multi-line span, including its "\n" (generator.py:830). The implementer chose that deliberately so that redaction always finds the span. Persona rule 8 asks for one line per prose paragraph, and the retry message ("not quoted word for word") does not say that the span holds a line break, so a generator that retypes a multi-line span with a space fails both attempts and the item stays unconsumed. Fail-closed, but a recurring cost for any LLM-pass span with a newline. Task 7 or Phase 7 could trim internal whitespace in spans at harvest (so spans are one line), or name the line break in the retry message.
- A buried document that quotes a multi-line span with no quote marks at all is still joined by the unwrap and still false-fails the quote rule (probe: span not `in` the unwrapped body). Same fail-closed class, same remedy.
- HANDOFF.md:30 count (8080 passed) and the report's gate numbers were not re-verified here.

## Verdict

All findings addressed, no new Critical/Important breakage
