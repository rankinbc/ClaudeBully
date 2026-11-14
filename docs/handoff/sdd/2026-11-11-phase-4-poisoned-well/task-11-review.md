# Task 11 review: the Poisoned Well replay lines and the seven configs

Base dbf17c0, head 4684a63 (one commit, author rankinbc1@gmail.com, trailer present). Read-only on
the checkout; probes in `probes-task11/`. The full suite was not re-run; focused runs only.

## Verdicts

- **Spec verdict: matches.** The seven configs are byte-for-byte the brief's text (probe), and each
  covers what spec section 12 names for its experiment. The replay lines, the `_KIND_ORDER` slot,
  `origin=twin`, the `[<move>]` flag, `_other` taking `ResumeRecord` only, and the fixtures all match
  section 12, P22, P27 and V25/V32. No record change, `SCHEMA_VERSION` 3 (enums.py:13), no golden
  touched, no run made.
- **Quality verdict: Approved.** 0 Critical, 0 Important, 4 Minor, 5 Nit.

## Findings

### Critical

None.

### Important

None.

### Minor

**M1. A contradiction `span_b` that holds `" vs "` is mis-split without warning.**
`claude_bully/analysis/replay.py:155-161` (the `contradiction` shape) and `:451-456` (the renderer).
`span_a` is greedy, so it runs to the last `" vs "` on the line. A span_a that holds `" vs "` parses
correctly. A span_b that holds it does not: `parse_replay_line` returns wrong fields, not None.
Scenario: the judge pairs `I am a model.` with `I can't tell "real" vs "fabricated" memories.`, which
uses this premise's own vocabulary. The line parses as span_a `I am a model." vs "I can't tell "real`
and span_b `fabricated" memories.` The probe reproduced this for 9 distinct span_b cases, retracted or
not. The module comment and spec V25 note the edge, and nothing in `claude_bully/` or `scripts/`
calls the parser yet, so this is Minor. The carry asked to "escape or quote spans" and the shape
quotes them but does not escape them. HANDOFF bullet 11 and docs/00 E say a quote mark "never breaks
a line". That holds for the layout but not for the parse.
Fix: escape `\` and `"` inside the three new spans and excerpts (`\\`, `\"`). Match each with
`"(?P<x>(?:[^"\\]|\\.)*)"` and unescape in `parse_replay_line`, or `json.dumps` each span. Then add
fixtures for span_b holding `" vs "` and holding `" (llm 0.6)`.

**M2. The `checksum_alone` "with rungs" arm carries rungs 2, 7, 8 and 10 as well as 4 to 6.**
`configs/poisoned_well/checksum_alone.yaml:1-2,28`. `pw_checksum_with_rungs` runs the full
`poisoned_well` ladder with the default `artifacts`. The probe shows that is all seven artifact
rungs, and `contradiction_harvest` (the dossier) is on the ladder too. Register item 14 predicts "it
only moves the needle in combination with 4-6". The config comment says "the checksum with rungs 4
to 6 (the full ladder)". Spec section 12 says "the full ladder with it", so the config matches the
spec. The contrast is still confounded: any gain over the checksum alone cannot be credited to 4 to 6.
Fix (a controller ruling on the spec): either
`artifacts: [shibboleth, provenance_gap, divergent_twin, checksum]` (the dossier rung stays on the
ladder; a large `harvest_min_pairs` keeps it shut), or reword the comment and section 12 to "the full
ladder". Then register item 14 reads as checksum alone against everything.

**M3. The runbook estimates leave out the rating calls on cells that are not Poisoned Well.**
`docs/handoff/phase-7-runbook.md:686-714`. The rule counts ratings only for "a Poisoned Well
conversation (its post-reveal replies plus three)". `rate_hedge` runs over every `self_uncertainty`
trigger on any cell (`metrics/ratings.py:281`), so the controls, the Captor, the Rescue and the
Epistemologist cells also make rating calls. `rescue_third_party`'s 400 is 324 conversation calls,
plus 12 pair-judge calls, plus about 63 trigger fallbacks, with no ratings. The rest of the method is
sound. My reconstruction from the stated rule gives `levers` about 2,430 (stated 2,350),
`poisoned_vs_captor` about 740 (730), `real_vs_fabricated` about 1,090 (1,000) and `checksum_alone`
about 1,120 (1,000). All are within the stated "a tenth either way", and the chain-fallback ceiling
counts four a rep even on the `chain_pace: 1000` arms, where the chain never opens.
Fix: add "one `rate_hedge` per `self_uncertainty` trigger on every cell" to the rule and bump the
rescue, epistemologist and captor figures. The `analyze --ratings` line is present for every
environment-cell config (chain_stop's rung line and the six-config paragraph).

**M4. The real-name scan does not cover `configs/`.**
`tests/test_real_names.py:27-29` (`SCANNED`, `SCANNED_FILES`). The carry says "the denylist test runs
over `configs/`", but `configs/` is read only for display names (`:160`). Probe
`probe_real_names.py`: the seven new configs hit only `claude`, from the `claude_code` provider
string and `display_name: Claude`, the exempt target name. They are clean, so non-negotiable 2 holds
for this task. The gap is older than this task, and a later config edit would go unscanned.
Fix: either add `CONFIGS_DIR` to the scan, sparing provider strings and target model strings, or
record it as a residual for the final review.

### Nit

- **N1.** `replay.py:248,255`: `{confidence:g}` writes a value under 1e-4 as `1e-05`, and
  `[\d.]+` will not read it, so the parser returns None. No current writer produces such a value
  (the writers use 1.0, 0.6 and 0.5). Fix: fixed-point formatting, or `[\d.e+-]+`.
- **N2.** `replay.py:378-379`: the `_KIND_ORDER` comment still ends "then the later-phase
  records". Those records now sit after the discoveries.
- **N3.** `chain_stop.yaml:5` says "about 300 calls" and the runbook now says about 330. The text
  is the brief's verbatim, so restate it in one place.
- **N4.** `real_vs_fabricated.yaml`: the real arm has the default five tools and the fabricated arm
  has six (plus `system_status`, which its checksum needs). The arms differ by one tool. That is
  acceptable, but it is worth one line in the comment.
- **N5.** `replay.py:285`: the move flag is read from any turn's `bully_meta`, not only a bully
  turn's. This is harmless, since only bully turns carry it.

## Named risks checked

1. **Round trip** (`probe_roundtrip.py`). I rendered each new shape through `render_replay` and
   parsed the line back. The spans tried were straight and curly quotes, a trailing quote, `'"'`,
   `'""'`, ` vs `, `" vs "`, `" (`, `(heuristic 1)`, `tail" (llm 0.6) pressed`, and
   `tail" (llm 0.6) retracted`. Whitespace cases were `\n`, `\r\n`, `\t`, U+2028, U+0085, an empty
   span and padding. I also tried six confidence values. QUIRK and CHAIN round-trip every span,
   because the group's suffix is anchored at `$` and fixed. CONTRADICTION round-trips everything
   except a span_b that holds `" vs "` (M1). Confidence 1e-05 fails to parse (N1). Every span
   stayed on one line. `GENERATED ... origin=twin` and the `generator` origin both render as
   specified (test_replay.py). The move flag parses with `[scripted]`, with an empty text, and with
   a text that opens with a bracket (the known P13 edge).
2. **The configs against the spec and the brief** (`probe_configs.py`). All seven are verbatim and
   LF. The cell counts (4, 8, 6, 14, 8, 8, 6) equal `EXPECTED` and spec V32. No Poisoned Well
   condition lacks an environment or has a pressure. Every Poisoned Well `params` passes
   `PoisonedWellConfig`. Every condition passes `check_condition`, and every config passes a dry run
   (`RunEnvironments.validate`). Every role is on `claude_code`: the targets are sonnet and opus,
   the bully and judge are sonnet, and the generator is haiku only where a world writes documents,
   with `periodic: false`. For P27, `chain_pace: 1000` keeps the chain shut on a `start_rung: 2` arm:
   the chain opens at `rung1_ended + pace` (`premises/poisoned_well.py:324-326`), past every budget.
   The fabricated ladder has no `contradiction_harvest` rung, so it has no dossier move. Each config
   maps to its section 12 row. The one doubtful contrast is checksum_alone (M2).
3. **Runbook estimates.** The method is stated and reproducible from the turn counts, and is within
   about 10 percent (M3). `analyze --ratings` is present for chain_stop's rung and for the six.
4. **Slow marks.** Durations from my focused run: levers 3.14 s, checksum_alone 1.46 s,
   poisoned_vs_captor 1.37 s, real_vs_fabricated 1.06 s and rescue_third_party 0.80 s. The default
   chain_stop run took 1.00 s and epistemologist_alone 0.52 s. Judgment: keep all five marked
   `slow`. The brief says so, and the rule only requires that a test over 2 s be slow. The gate runs
   `-m slow`, so no test drops out of the gate. Three of the five sit at 1.0 to 1.5 s, close to the
   line on a loaded machine. Both default stub runs are under 2 s.
5. **The xfail drop** (`probe_move_flag.py`). Every line holding `[chain_link]` or `[press]` is a
   bully speaker line whose `bully_meta["pw_move"]` is that move. No turn text holds the bracketed
   names. When I drop `pw_move` from the meta before `_speaker_line`, the test's assertion is false.
   It passes for the right reason.

Further one-off checks: the rglob test and `tests/test_real_names.py` (80 passed). Only `replay.py`
was touched in `claude_bully/`, so no new UNLOCK or HOOK literal is outside it. Goldens and
`SCHEMA_VERSION` are untouched.

## Probe results

- `probes-task11/probe_configs.py`: 7 of 7 verbatim; counts, composition, params, `check_condition`
  and dry run all pass. Per-condition dump (ladder, gating, tools, generator, resolved params) above.
- `probes-task11/probe_roundtrip.py`: 19 failures over the grid, 18 of them the M1 class (9 span_b
  shapes, each twice for `retracted`) and 1 the N1 confidence. Move-flag cases all pass.
- `probes-task11/probe_move_flag.py`: the flag comes from meta; the mutation turns the assertion
  false.
- `probes-task11/probe_real_names.py`: the new configs hit only `claude` (the provider and the
  exempt display name).
- Focused pytest (config module, `-m "slow or not slow"`, the two replay run tests): 17 passed in
  15.4 s.

## ASSUMED, judged

- *Spans made safe by whitespace collapse plus quote-tolerant regexes; HARVEST and TRIGGER left
  raw.* Partly accepted. The collapse is right and keeps the layout. The quote tolerance has the
  span_b `" vs "` hole (M1). Leaving HARVEST and TRIGGER raw is in scope to accept (M8 stays open,
  stated).
- *The move flag follows `[scripted]` and the other flags.* Accepted. This is what V25 says.
- *Estimates by the stated rule.* Accepted with M3: the rule leaves out the rating calls on cells
  that are not Poisoned Well.
- *The five ladder stub runs marked `slow` as the brief says.* Accepted (risk 4).
- *Expected gate counts 9673 / 9 / 21 / 0 xfailed; slow 21.* Not verified (no suite re-run, as
  instructed). The test arithmetic is consistent: +10 parametrized config tests and the presence
  test, +10 parser fixtures, +6 renderer tests, +1 run-level test, and the unmarked xfail.
