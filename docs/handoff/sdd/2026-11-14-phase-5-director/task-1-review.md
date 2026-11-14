# Phase 5 Task 1 review (97102a0..262b8a2)

Reviewer: task-scoped gate. I read the diff once, did not re-run the suite, and did not trust the report. Every claim below comes from the diff, from one focused read per named risk, or from a probe in `probes-task1/` (each probe's `.out` file sits beside it).

## Verdicts

- **Spec verdict: Compliant.** Every name, type and default in the brief's Interfaces block is present and matches (probe 4). The preflight rows that name Task 1 are met: Q4 (every `X | None` defaults None), and Q2, Q3, Q5 to Q9 and Q57 hold. `SCHEMA_VERSION` stays 3. `RunRecord.plan` is additive and defaults None. The diff touches no golden. All three world hashes equal the Plan Decisions values at 38dcc70 (probe 3). Docs-sync is done: docs/00 sections A, B and H, the spec's "As planned" and HANDOFF. Every changed file is LF in the index and in the work tree. The commit author matches the earlier commits.
- **Quality verdict: Approved.** I found no Critical and no Important issue. The write path is fail-closed against every adversarial path I tried (probe 1) and every junction placement (probe 2). There are 6 Minor findings and 5 Nits. None of them blocks Task 2. M1 and M2 are worth fixing before Tasks 7a and 9 build on `write_manual` and `index()`.

Counts: Critical 0, Important 0, Minor 6, Nit 5.

## Findings

### Minor

**M1. `write_manual` can overwrite an earlier call's transcript.** `claude_bully/planner/bundle.py:282-283`
- Scenario: a stage named `author` has been committed (or failed). A later `write_manual(..., stage="author")` then opens a second `author` stage. It takes `index = len(last.calls)`, which is 0, and writes `transcripts/author-planner-0.json` over the first stage's call 0. Probe 4 shows the result: the first call's `committed_outputs` now returns `personas/a.yaml: "name: b\n"`. That is the second file's content under the first file's path. Nothing raises. `materialize` (Task 7a) would rebuild the wrong bytes, or would fail only if it checks the sha itself.
- Exposure: no planned caller reopens a stage under the same name. `good_bundle`, `config_bundle` and the example script each write a stage once. So this is latent. Still, `transcript_rel(stage, role, index)` is unique only within one `StageRecord`, and Task 9's rounds and D-failed-stage both rely on archived names staying distinct.
- Fix (either one):
  - Take the index past every call already recorded under that stage name: `sum(len(s.calls) for s in record.stages if s.stage == stage)`.
  - Or refuse in `write_manual` when the transcript file already exists and no call in the current open stage names it.

**M2. `index()` and `bundle_hash` read through junctions that every write and read refuses.** `bundle.py:225-229`, `claude_bully/environments/world.py:379`
- Scenario: put a junction at `worlds/mini` that points outside the bundle. `write_file`, `read_file` and `remove_file` all refuse it with "the path runs through a link", which is correct. But `index()` lists `worlds/mini/world.yaml` and `worlds/mini/corpus/a.md` from the outside folder. `bundle_hash` also changes when a file outside the bundle changes (probe 2). On Python 3.12, `Path.rglob` does not follow symlinked directories but does follow junctions. It also yields a symlinked file, which `is_file()` then follows, on any OS.
- Consequences: Task 7a's `StageRecord.inputs` and its edit adoption would record shas of outside files. The run's `plan_hash` would then cover content outside `plans/<slug>/`. This fails closed only later, at the first re-materialize.
- Exposure: only a person with filesystem access can plant a junction. A model-supplied string cannot, so non-negotiable 1 holds.
- Fix:
  - `index()` keeps a path only when `_confined(rel)` also passes. Wrap it in try/except `BundlePathError`.
  - `bundle_hash` refuses a bundle that holds a link: walk once, raise `BundlePathError`. Do this in `bundle_hash`, not in `hash_tree`, so the world hashes stay byte-identical.

**M3. `committed_outputs` raises raw `AttributeError` or `TypeError` on a malformed reply.** `bundle.py:160`, `bundle.py:168`
- Scenario: a transcript whose reply is `{"content": 1}` raises `AttributeError: 'int' object has no attribute 'removeprefix'`. A reply of `[1]` raises `TypeError` (probe 4). A caller that catches `ValueError`, which is the function's documented error, misses both. The implementer flagged this and left it, reasoning that only the harness writes transcripts. But `materialize` reads transcripts from disk, and an owner can edit them.
- Fix: parse the reply, then check `isinstance(obj, dict) and isinstance(obj.get("content"), str)`. Otherwise raise `ValueError(f"{call.transcript}: reply has no string content")`.

**M4. `Bundle.create` does not validate its slug.** `bundle.py:178-181`
- Scenario: `Bundle.create(plans, "../x")` makes `plans/../x` and returns a bundle rooted outside `plans_root` (probe 4). `create(plans, "_cache")` would make the Director's cache folder a bundle. Every planned caller passes a validated `PlanRequest.slug` or `slug_for`'s output, so nothing reaches this today. The report records the choice as an ASSUMED.
- Why it matters: the task's binding point is "no traversal", and this is the one entry into `plans/` that takes a string.
- Fix: one line in `create` that refuses a slug failing `_SLUG.fullmatch` or found in `WINDOWS_DEVICE_STEMS`, raising `BundlePathError`. Move `_SLUG` to a public name in `request.py`, which `bundle.py` already imports.

**M5. The longest grammar path is over MAX_PATH under the repo's own `plans/`.** This comes from the grammar's 64-character names (`bundle.py` `NAME`) together with `SLUG_MAX = 48`.
- Measurements (probe 2):
  - `REPO_ROOT/plans/<48>/worlds/<64>/corpus/<64>.md` is 261 characters.
  - `write_atomic`'s temp file beside it is 275.
- This machine has `LongPathsEnabled = 1`, so the write works here. On a Windows checkout without it, a grammar-valid path fails with a raw `OSError` from `mkstemp`, not a `BundlePathError`. The planner would see a provider-style failure, not a refusal it can retry.
- Fix (one of):
  - In `check_path`, refuse a path whose absolute length, plus about 20 characters for the temp suffix, passes 259 when `sys.platform == "win32"`, and name the limit in the message.
  - Or narrow `<name>` to 40 characters.

**M6. `normalize_text` holds a literal U+FEFF.** `bundle.py:79`
- `text.removeprefix("<invisible BOM>")` reads as `removeprefix("")`, a no-op, in every diff and most editors. The diff file shows it that way. A maintainer could "simplify" it away, and only `test_write_file_writes_lf_without_a_bom...` would catch that.
- Fix: write `"﻿"`, as the tests do.

### Nits

- **N1.** `hash_tree(exclude="state")` type-checks, because a `str` is a `Collection[str]`. It then drops every first segment that is a substring of the string, for example `a/`. Probe 3 shows the hash moving. `world.py:383`. Fix: accept `frozenset[str]`, or refuse a bare `str`.
- **N2.** `read_plan_record` lets `schema_version` `"0"` and `0.0` through to validation, and pydantic coerces them to 0. A newer version such as 2 is also read as if it were version 1 (probe 4). `records.py:194`. This mirrors `runner/store.py: _checked`, the shape the brief asked for, so it is a note. Fix: check `record.schema_version` after validation as well.
- **N3.** `parse_budget` accepts `"1_8,3,12"` and non-ASCII digits (`"١٨,3,12"`), because `int()` is lenient. `request.py:128`. Fix: fullmatch `\d+` with `re.ASCII` before `int`.
- **N4.** A `write_atomic` temp left by a hard process kill (`.plan.md.<x>.tmp`) changes `bundle_hash`, though `index()` ignores it (probe 3). Only a hard kill leaves one. An exception cleans up. The result fails closed as "bundle edited" in Task 10. No fix needed now. Task 9's K-point docs could mention it.
- **N5.** `committed_outputs` does not check the content it returns against `call.outputs[rel]`. M1's corruption therefore passes through it silently. If Task 7a's `materialize` does not compare the shas, add the check here, so a mismatch raises `ValueError`.

## Named risks checked

### 1. The path grammar (probe 1, probe 2, probe 8, probe 9)
- Read: `_GRAMMAR`, `_match`, `_confined`, `check_path`, and `atomic.write_atomic` (a focused read, to see how the write replaces the file and what temp it leaves).
- Refused: everything I tried in each category.
  - `..`, `.`, empty and double segments.
  - Absolute paths, drive-relative paths (`C:plan.md`), drive letters, UNC paths, `\\?\` and `\\.\`.
  - Backslashes and mixed separators.
  - Trailing dots and spaces in any segment, and a leading space.
  - Device names in every variable segment (world, doc, ladder, premise, persona), in either case. `conin$`, `conout$` and `clock$` fall to the character class.
  - Fullwidth and zero-width look-alikes, and the dotless i.
  - NUL, CR, LF and tab.
  - NTFS streams (`:`), 8.3 short names (`~`) and wildcards.
  - Every capital variant, a 65-character name, unlisted folders, nested corpus folders, and every harness file (`plan.json`, `.attempt.json`, `transcripts/...`, `dryrun*`, `state/`, `_cache/`).
- Case-variant duplicates: none are possible, since the grammar is lowercase-only.
- What gets through, all of it harmless:
  - `com0` and `lpt0`. Probe 8: on this Windows 11 both create regular files, and Python 3.13's `ntpath.isreserved` agrees they are not reserved.
  - `con-1` and `con_`, which are not devices.
  - A trailing `-` or `_`, and a single digit.
  - The longest path, which is M5.
- Links:
  - A junction at `worlds`, `worlds/mini`, `worlds/mini/corpus` or `personas` is refused for write, read and remove. So is a junction that points back inside the bundle. Nothing reached the outside folder.
  - A hard link to an outside file is replaced, not written through: `os.replace` breaks the link and the outside file stays unchanged.
  - The symlink case skips here (WinError 1314, no privilege). The implementer's added junction test covers the `isjunction` branch, and probe 2 confirms it.
  - Gaps: `index()` and `bundle_hash` (M2). Also check-then-write TOCTOU, which is out of the threat model (no concurrent attacker).
- Probe 9: every file of `data/worlds/overlay`, `mini` and `annex`, placed under `worlds/<name>/`, fits the grammar. So Task 7b's base copy and `index()` will agree.

### 2. hash_tree (probe 3)
- Read: `hash_tree` and `world_hash`. It is the legacy body moved over unchanged, plus the first-segment skip.
- Deterministic across creation order, mtime and CRLF in `.md`, `.yaml`, `.yml`, `.txt` and `.json`. The sort is by posix relative path, the same on every OS.
- Lone CR and BOM are not folded. This is correct: the legacy scheme must hold, and `write_file` normalizes before anything is hashed.
- The repo's `.gitattributes` is `* text=auto eol=lf`, and the three worlds are `i/lf w/lf`.
- Exclusion: exactly the spec's seven names, first segment only. A nested `state/` still counts, as the brief's test pins. `review.md` is covered.
- Gaps:
  - A case-variant `State/` at the root counts. Nothing writes one, so it is not a finding.
  - A bare-string exclude (N1).
  - A leftover temp (N4).
  - Junctions (M2).
- The three world hashes equal the plan's values (e9ca0811..., 6e9f02a7..., e72358fb...).

### 3. The records against the brief (probe 4)
- Every name in the Produces list is present, and `WINDOWS_DEVICE_STEMS` in `bundle.py` is the same object as the one in `request.py`.
- `Scope` and `Stage` have the same members as `SCOPES` and `STAGES`, in order.
- Constants and signatures match the brief, `Bundle.slug` is a property, and every model has `extra="forbid"`.
- Q4 holds: every `X | None` defaults None. `DirectorCall.attempts` is `Literal[1, 2]`.
- `PlanRecord`'s field order is spec section 4's, with `base_files` and `base_premise_terms` after `base_worlds` and `rounds` after `stages`.
- `DEFAULT_ROLES` is a read-only `MappingProxyType`. Every `PlanRequest` default is a deep copy, and mutating one leaks into neither the other nor `DEFAULT_ROLES`.
- `display_name` is left at its default.
- `RunRecord.plan` is `PlanStamp | None = None`, and `PlanStamp` forbids extra fields.
- `request.py` imports nothing from `records.py` or `bundle.py`, so review I7 holds.
- Spec section 4 (one read): every field and literal agrees.

### 4. The ASSUMED decisions (see the next section)
- Downstream naming: I grepped the plan for the archive paths of D-rounds and D-failed-stage, and for every downstream use of `kind_of`, `world_of` and `write_manual`.

## Judgment on each ASSUMED

- **Transcript paths get their own grammar: sound, keep it.** `transcripts/[round-<n>/|failed/]<stage>-<planner|reviewer>-<index>.json` accepts exactly the forms that D-rounds (`transcripts/round-<n>/<same name>`) and D-failed-stage (`transcripts/failed/<stage>-<role>-<index>.json`) name. It refuses `round-0`, leading zeros, other roles, `failed/round-1/` and every traversal, and it runs the same link check (probe 1).
  - One downstream note: D-rounds also archives `review.md` to `transcripts/review-<n>.md`. That is not a JSON transcript, and this grammar refuses it, correctly. Task 9 needs its own confined writer for it, and the Task 9 reviewer should check that it has one.
- **`committed_outputs` normalizes CRLF: sound, and required.** `write_file` records the sha of the normalized text, so a re-materialize must give the normalized bytes. Probe 4 checks this: a manual `plan.md` with a BOM and CRLF gives `committed_outputs` text whose sha equals `index()` and `call.outputs`, and the disk holds LF bytes. Normalizing is idempotent, so a caller that also goes through `write_file` gets the same bytes. Keep it. See M3 and N5 for its error handling.
- **Device names are refused in the slug: sound.** It matches `slug_for`'s device fallback and D-write_file's reasoning (`plans/con/` opens a device on Windows). The cost is nil, since the error message names the rule. The same check belongs in `Bundle.create` (M4).
- The others, briefly:
  - `kind_of` and `world_of` raising for a path outside the grammar is fail-closed, and no downstream task calls them on a path outside the grammar (plan grep): accept.
  - `Transcript` fields with no defaults, as the brief's signature shows: accept.
  - `read_file` with no newline translation, so its sha equals `index()`: accept.
  - `remove_file` treating a missing file as no error, which keeps resume idempotent: accept.
  - `Bundle.create` not validating the slug: reject as stated, see M4.
  - docs/08 unchanged: accept. The brief's Step 5 does not name it.

## Probes (`probes-task1/`)

| Probe | What it checks | Result |
| --- | --- | --- |
| `p1_grammar.py` / `.out` | about 90 adversarial paths through `check_path`, plus 13 through the transcript grammar | only harmless names get through (listed under risk 1) |
| `p2_links.py` / `.out` | a symlink (skipped, no privilege); a junction at four levels and one pointing inside the bundle; a hard link; a junction as the bundle root; `index()` and `bundle_hash` through a junction; the longest path under `REPO_ROOT/plans` | writes, reads and removes are refused through every junction; `index()` and `bundle_hash` follow them (M2); 261 and 275 characters (M5) |
| `p3_hash_tree.py` / `.out` | creation order, mtime, CRLF, lone CR, BOM, an upper-case suffix, a bare-string exclude, a case-variant exclude, a leftover temp, `review.md`, the three world hashes, git eol | deterministic; the hashes match; N1, N4 |
| `p4_records.py` / `.out` | every interface name, type, default and signature; the slug and budget edges; `read_plan_record` version shapes; `committed_outputs`; `write_manual` reopening a stage; `Bundle.create("../x")` | everything matches the brief; M1, M3, M4, N2, N3 |
| `p8_devices.py` / `.out` | whether `com0` and `lpt0` are devices on this Windows 11, and Python 3.13's `isreserved` | both are regular files; Python agrees; `LongPathsEnabled = 1` |
| `p9_shipped_worlds.py` / `.out` | every shipped and fixture world file against the grammar | 54, 13 and 9 files, none outside |

The probes wrote only to temporary directories and to `probes-task1/dev/`. The checkout is unchanged.
