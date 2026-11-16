### Task 12: The example bundle and CI over `plans/`

**Files:**
- Create: `scripts/build_example_bundle.py` (re-runnable: it rebuilds the example from the overlay and the authored files when the overlay moves)
- Create: `plans/example-triggered-vs-scheduled/` (`plan.md`, `config.yaml`, `expected.yaml`, `review.md`, `plan.json`, `transcripts/`, `dryrun.jsonl`, `worlds/overlay/` the byte copy; no `ledger.jsonl`: a manual build makes no Director call, and stage 5 makes none, so no plan ledger line is written; review Minor 14)
- Modify: `tests/test_real_names.py` (every text file of every bundle under `plans/`, as Task 4a does for `tests/fixtures/bundles/`, R-scan-bundles: `plan.md`, `review.md`, the grammar files, `plan.json`, `ledger.jsonl` and `dryrun.jsonl` when present, `config.yaml` through `config_scan_text`, the JSON files through `record_scan_text`, and each transcript's `reply` texts), `tests/test_guardrails.py` (the jailbreak scan covers `plans/` but `transcripts/`), `tests/test_boundary.py` (every file under `plans/*/worlds/` and `plans/*/personas/`, comments included), the reserved-host test (`test_world_addresses_use_reserved_top_level_domains`) over `plans/*/worlds`
- Test: `tests/test_example_bundle.py`

**Interfaces:**
- Consumes: Task 1's `Bundle`, `write_manual`; Task 9's `Director.validate`; `PLANS_DIR = REPO_ROOT / "plans"` (added to `claude_bully/paths.py`).
- Produces: `paths.PLANS_DIR`; the example bundle, `provenance: manual`, `status: runnable`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_example_bundle.py
"""Phase 5 Task 12: every bundle under plans/ passes every lint (fast); each dry-runs to the top
in both arms (slow); the example cites hypothesis 9 (spec section 15)."""

import shutil
from pathlib import Path
from typing import Final

import pytest
import yaml

from claude_bully.paths import PLANS_DIR
from claude_bully.planner.bundle import Bundle, bundle_hash
from claude_bully.planner.bundle_lints import lint_bundle
from claude_bully.planner.dryrun import dry_run

BUNDLES: Final = sorted(p for p in PLANS_DIR.iterdir() if (p / "plan.json").is_file())
EXAMPLE: Final = PLANS_DIR / "example-triggered-vs-scheduled"


def test_the_example_is_there_and_hand_authored() -> None:
    assert EXAMPLE in BUNDLES
    record = Bundle(EXAMPLE).read_record()
    assert (record.provenance, record.status) == ("manual", "runnable")
    assert record.bundle_hash == bundle_hash(EXAMPLE)  # nothing changed since it was validated
    assert {c.status for s in record.stages for c in s.calls} == {"manual"}


@pytest.mark.parametrize("root", BUNDLES, ids=lambda p: p.name)
def test_every_bundle_passes_every_lint(root: Path, isolated_registry: None) -> None:
    bundle = Bundle(root)
    found = [r for r in lint_bundle(bundle, dry_run=bundle.read_record().dry_run) if r.severity == "fail"]
    assert found == [], [(r.lint_id, r.doc_id, r.message) for r in found]


@pytest.mark.slow
@pytest.mark.parametrize("root", BUNDLES, ids=lambda p: p.name)
def test_every_bundle_dry_runs_to_the_top_in_both_arms(root: Path, tmp_path: Path, isolated_registry: None) -> None:
    copy = tmp_path / root.name
    shutil.copytree(root, copy, ignore=shutil.ignore_patterns("dryrun", "state"))
    cells = dry_run(Bundle(copy))
    laddered = [c for c in cells if c.top_rung != "not_applicable"]
    assert laddered and all(c.top_rung == "reached" for c in laddered if not c.cell_id.startswith("control"))
    assert [c.model_dump() for c in cells] == [c.model_dump() for c in Bundle(root).read_record().dry_run]


def test_the_example_expects_against_hypothesis_9() -> None:
    expected = yaml.safe_load((EXAMPLE / "expected.yaml").read_text("utf-8"))
    cited = {h for cell in expected["cells"].values() for rung in cell["rungs"].values() for e in rung for h in e.get("hypotheses", [])}
    assert 9 in cited


def test_the_example_worlds_are_a_byte_copy_of_the_overlay_at_its_base_hash() -> None:
    record = Bundle(EXAMPLE).read_record()
    assert set(record.base_worlds) == {"overlay"}
    copied = {p.relative_to(EXAMPLE).as_posix() for p in (EXAMPLE / "worlds").rglob("*") if p.is_file()}
    assert copied == set(record.base_files)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_example_bundle.py -q`
Expected: FAIL (`paths.PLANS_DIR` does not exist; no bundle under `plans/`).

- [ ] **Step 3: Build the example bundle**

`scripts/build_example_bundle.py` (stdlib and the package only; `--out plans/`, default the repository's `plans/`): creates `plans/example-triggered-vs-scheduled/` with `PlanRecord(provenance="manual", request=PlanRequest(question="Does triggered gating beat scheduled on the Rescue premise?", base_world="overlay", hypotheses=[9], slug="example-triggered-vs-scheduled"), ...)`; copies `data/worlds/overlay` byte for byte (`base_worlds`, `base_files`, `base_premise_terms`); writes through `write_manual` `plan.md` (stage `plan`; the question, the four cells and what each isolates, the headline chart (adoption by gating, hypothesis 9's metric), the expected events per cell, the null result: "scheduled matches triggered", hypothesis 9's falsifier), then `config.yaml` (stage `author`; `configs/environments/triggered_vs_scheduled.yaml`'s content, comments kept, every field explicit) and `expected.yaml` (both condition cells, at least two rungs each, hypothesis 9 cited, one `likely_wrong`, no `values_loosened`); renders `review.md` with no finding (`block 0 / fix 0 / note 0`) and commits the review and revise stages with no call; then `Director.open(...).run(through="validate")`, which runs stage 5 on the stubs and stamps `bundle_hash`. Its dry run is the one Task 5's `test_the_overlay_example_config_dry_runs_with_no_buried_search_hit` already runs on this config (R-buried: the overlay's `the_truth` names `cpo-review-4471-r3` by id, which is searchable by design and no hit), so this task is not the first to meet the overlay's ladder in a dry run. It adds no unlock line and no persona; the reader-eye review of spec section 14 covers `plan.md` and `expected.yaml`, which the task's reviewer reads for a billboard and for predictions specific enough to be wrong. Run it once; commit what it writes (`dryrun/` and `state/` are ignored).

- [ ] **Step 4: Extend the scans**

`paths.PLANS_DIR = REPO_ROOT / "plans"`. Each of the four scans gains `plans/` as stated in Files. The real-name scan of a checked-in bundle has no exemption for `plan.md`, `review.md` or the transcripts' replies (R-scan-bundles, review I9: a committed bundle is repository text, and the example's `plan.md` is written by hand in this phase); the `real_name_bundle` lint keeps its exemption for a plan in flight. A transcript's `message` is not rescanned: it is built from `docs/01` to `docs/07` (which name real models by design), `data/` (scanned at its source) and the bundle's own files (scanned as files). The jailbreak scan skips `transcripts/`; the Boundary scan covers `worlds/` and `personas/` only. Each scan's "covers" test gains an assertion that a file of the example bundle is in its list, and the real-name one that the example's `plan.md`, `review.md` and `plan.json` are.

- [ ] **Step 5: Run the tests and the gate**

Run: `uv run pytest tests/test_example_bundle.py tests/test_real_names.py tests/test_guardrails.py tests/test_boundary.py -q -m "slow or not slow"`, then the gate.
Expected: PASS.

- [ ] **Step 6: Docs-sync and commit**

docs/08 "Inputs and outputs": the example bundle is hand-authored now (`provenance: manual`) and rung D regenerates it (C22); docs/00 section F: `plans/` and what is committed. HANDOFF: "Repository" names `plans/`.

```bash
git add scripts/build_example_bundle.py plans/example-triggered-vs-scheduled claude_bully/paths.py \
  tests/test_example_bundle.py tests/test_real_names.py tests/test_guardrails.py tests/test_boundary.py \
  docs/08-DIRECTOR.md docs/00-RECONCILED.md docs/superpowers/specs/2026-11-14-phase-5-director-design.md HANDOFF.md
git commit -m "feat: Phase 5 Task 12, the hand-authored example bundle and CI over plans/

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

