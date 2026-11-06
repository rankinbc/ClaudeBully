# Task 5 re-review, fix round 1 (aa49c52..2f17c02)

Scope: the four findings of task-5-review.md and the fix diff only. Reviewed the diff file once, plus the current
files. Focused checks run (not the full suite): `ruff format --check` and `ruff check` on the touched tests and
`claude_bully/environments/`, and `pytest -W error` on test_generator_plan, test_records_env, test_replay,
test_store and tests/test_corpus*.py: 189 passed, ruff clean. Working tree, index and HEAD untouched.

## Finding Verdicts

### 1(a) Author-eligibility rule duplicated: ADDRESSED
- `claude_bully/environments/generator.py:226-232` defines `_authors(world)` (the single place that reads
  `AUTHOR_EXCLUDED_ROLES`, line 54; no other `AUTHOR_EXCLUDED_ROLES` use remains).
- `DocPlanner.__init__` calls it at :246 (`self.authors = _authors(world)`); `generator_problems` calls it at :411
  (`if not _authors(world)`). Same order and same predicate as before, so behaviour is unchanged.
- New test `tests/test_generator_plan.py:291-302` (`test_the_planner_and_generator_problems_agree_on_who_may_author`)
  builds a cast of only `Place:` roles and asserts `generator_problems` names an "author" problem and `DocPlanner`
  raises "no cast member can author"; then restores one authoring member and asserts both accept and `authors` is
  that member. It would fail if either call site reverted to its own predicate that diverged.

### 1(b) Url branch copies the corpus normaliser: ADDRESSED
- `claude_bully/environments/corpus.py:190` is now the public `norm_url` (docstring says the generator reads it);
  the two index callers were renamed with it (:265 `_reindex`, :349 `by_url`).
- `generator.py:33` imports it; `generator.py:220-223` `_norm_address` returns `norm_url(address)` for a url and
  `_norm_path(address)` otherwise. No copied `.strip().rstrip("/")` remains. The optional `_is_url` helper
  (:215-217) replaces both `startswith(("http://","https://"))` tests (:223 via `_norm_address`, :356 `web`).
- Pinning test `tests/test_generator_plan.py:257-288` (`test_the_planner_and_the_corpus_index_agree_on_a_urls_key`):
  for three spellings of one url (bare, trailing slash, padded) it asserts `norm_url(spelling) == free`, that a real
  `CorpusIndex` holding an anchor at that spelling finds it via `by_url(free)`, that the planner given a view holding
  the anchor refuses the taken address (plan url differs and ends `-2`), and that `index.by_url(plan.url)` is None.
  A generator that failed to strip the trailing slash would plan `free` and fail. It pins behaviour on the three
  spellings, not structure; delegating to `norm_url` is what keeps the two from drifting beyond them. Adequate for
  the finding.
- No import cycle: corpus.py imports only enums, `idle` and `world`; nothing in corpus imports generator.

### 2 (m1) Rename the P33(c) test: ADDRESSED
- `tests/test_generator_plan.py:241` is `test_the_start_is_the_served_worlds_date`; its docstring states what it
  pins and that drift is only a distractor, with Task 7's run-level test as the drift pin. Body unchanged.
- The old name survives only in historical ledger material (docs/handoff/sdd preflight, brief, carries, and the
  plan), which record the original text and are not live code. `HANDOFF.md:125` carries the new name.

### 3 (m3) Shared `generated_doc(**overrides)` builder: ADDRESSED
- `tests/fixtures/generator_stub.py` adds `generated_doc(**overrides)` (a valid buried doc, validated through
  `GeneratedDoc.model_validate`). No `GeneratedDoc(` constructor call remains anywhere in `tests/`.
- Per-file override check against the pre-fix builders (every originally supplied field is either overridden or
  equal to the builder default):
  - test_generator_plan.py: local `_generated` deleted, same defaults moved into the builder; the call sites
    (`doc_id`, `layer`, `kind`, `path`, `url`, `unlock_rung` overrides) pass through; unused `GeneratedDoc` import dropped.
  - test_records_env.py `_generated`: seam doc. Overrides `layer=seam`, `path=None`, `url`, `author`, `links_to`,
    `used_items`, `title`, `cache_key`, `body`, `turn`, `trigger_turn`, `source_spans`, `kind`, `doc_id`, and
    `unlock_rung=None` (the original never set it, default None). `date` and `reflexive=True` equal the builder
    defaults. `:357-358` still asserts `unlock_rung is None`, and it holds because of that explicit override.
  - test_replay.py `_generated`: buried; `layer`, `path`, `date`, `author`, `links_to`, `reflexive`, `cache_key`
    equal the defaults; `unlock_rung=None` re-asserted; `used_items`, `body`, `turn`, `kind`, `trigger_turn`,
    `source_spans` overridden. The one value that changed is `title` ("Night notes" becomes "Night office notes");
    nothing reads it (the replay `GENERATED` line takes the title from the world document at replay.py:339-341, and
    the render calls here pass `world=None`), and no test mentions "Night notes".
  - test_store.py: `doc_id`, `turn`, `kind`, `trigger_turn`, `source_spans`, `cache_key`, `body`, `title`,
    `used_items` overridden; `layer`, `path`, `date`, `author`, `links_to`, `reflexive` and `unlock_rung="the_log"`
    equal the defaults. The now-unused `date` and `GeneratedDoc` imports were dropped; ruff is clean.
- Import side effect: test_records_env, test_replay and test_store now import `tests.fixtures.generator_stub`, which
  loads the mini world at import time. test_replay and test_store already loaded worlds, so this is harmless.

### 4 (m5) `fire_requests` docstring: ADDRESSED
- `generator.py:183-187`: the docstring now says `opened` holds the turn's newly opened rungs with `generate: true`,
  in ladder order, that the caller filters, and that every name given fires.

## New Breakage in the Fix Diff

None.

- `norm_url` public rename: grepped every caller across `claude_bully/`, `tests/` and top-level docs. The old name
  `_norm_url` has zero remaining references (only corpus.py:265 and :349 used it, both updated). No `__all__` in
  corpus.py or `environments/__init__.py` to update. Importers of `norm_url` are generator.py:33 and
  tests/test_generator_plan.py:21 only.
- Shared builder dropped no test's own override (see the per-file table in finding 3).
- Ruff format and check clean; the 189 focused tests pass under `-W error`.

## Out-of-Scope Observations

- `claude_bully/metrics/events/authority.py:1177` has its own, differently-behaved `_norm_address` (lstrip `~`,
  strip `/`, lowercase) for a metrics event. Pre-existing, not in this diff, and a different purpose (matching a
  tool's args to a doc address, not index keying). Same name as the generator's helper; no clash since both are
  module-private.
- Historical ledger files under `docs/handoff/sdd/...` and the plan still quote the old test name
  `test_a_drifting_clock_does_not_move_the_start`; they are records of the original text, so leaving them is right.
- The report's deferred minors (2, 4, 6, 7) are untouched by this diff, as stated.

## Verdict

All findings addressed, no new Critical/Important breakage
