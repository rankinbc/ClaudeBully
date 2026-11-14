### Task 14: The open Phase 3 minors on Phase 4's surface

C20 gives this phase the Phase 3 final-review minors still open (HANDOFF; re-anchor at execution: search for '**Final-review minors still open**'). This task closes the seven that touch code Phase 4 builds on; every other one stays in that HANDOFF list, marked "carried past Phase 4".

**Files:**
- Modify: `claude_bully/records_env.py` (`GeneratorFire`: a cross-field validator; Task 5 m4)
- Modify: `claude_bully/environments/runtime.py` (`add_generated`: a different document under a recorded id raises, Task 7 m7; `_read_log`: a malformed complete line raises, Task 9 review; `corpus_snapshot(turns)` takes `turns` with no default, Task 9 review)
- Modify: `claude_bully/environments/mcp_server.py` (`McpServer._lines`: a valid JSON line that is not an object raises, Task 9 review)
- Modify: `claude_bully/analysis/authority.py` (`_resumed_per_cell`: every environment condition cell, 0 when none of its reps counted; older re-review minor)
- Modify: `tests/fixtures/generator_stub.py` (`HarvestJudge(items=)`), `tests/test_generator_run.py` (+ one test; the review's m2)
- Test: `tests/test_phase4_minors.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_phase4_minors.py
"""Phase 4 Task 14: the Phase 3 final-review minors on Phase 4's surface (C20)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_bully.records_env import GeneratorFire


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "written", "doc_ids": []},
        {"status": "cached", "doc_ids": ["gen-1-1"], "rejection": "cap"},
        {"status": "rejected", "doc_ids": []},
        {"status": "rejected", "doc_ids": ["gen-1-1"], "rejection": "lints"},
        {"status": "error", "doc_ids": []},
    ],
)
def test_a_fire_whose_fields_disagree_is_refused(fields: dict[str, object]) -> None:  # T5 m4
    with pytest.raises(ValidationError):
        GeneratorFire(turn=1, reason="periodic", plans=[], **fields)  # type: ignore[arg-type]


def test_consistent_fires_still_validate() -> None:
    GeneratorFire(turn=1, reason="periodic", plans=[], status="written", doc_ids=["gen-1-1"])
    GeneratorFire(turn=1, reason="periodic", plans=[], status="rejected", rejection="cap")
    GeneratorFire(turn=1, reason="periodic", plans=[], status="error", error="ProviderError: down")
```

and, in the same file, tests that:

- `EnvironmentRuntime.add_generated` raises `ValueError` naming the id when handed a document whose id is recorded with a different body, and stays idempotent for the same document (build the runtime as `tests/test_generator_runtime.py` does);
- `EnvironmentRuntime._read_log` on a file holding a complete line that is not a valid record raises a `ValueError` naming the file and the line number, and still skips an unterminated last line;
- `McpServer._lines` on a log holding the complete line `[1, 2]` raises a `ValueError` naming the file and the line (build the server as `tests/test_mcp_server.py` does);
- `EnvironmentRuntime.corpus_snapshot()` with no argument is a `TypeError`;
- `write_authority`'s `resumed_after_dead_attempt` lists every environment condition cell of a run with authority calls, `0` for a cell none of whose reps were counted (an aborted rep), using the run `tests/test_runner_env.py`'s annex authority test makes.

In `tests/test_generator_run.py`, `test_an_llm_sourced_item_goes_into_a_fire`: `HarvestJudge(items=[{"kind": "self_claim", "span": "<a sentence the follower's reply holds verbatim>"}])` makes the LLM pass return that span, and the run's buried document lists the item `h-<turn>-x1` in its `used_items`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_phase4_minors.py "tests/test_generator_run.py::test_an_llm_sourced_item_goes_into_a_fire" -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`GeneratorFire._agrees` (a `model_validator(mode="after")`): `written` and `cached` have `doc_ids` and no `rejection`; `rejected` has a `rejection` and no `doc_ids`; `error` has an `error` and no `doc_ids`. Fix any test that builds a fire the validator refuses (the fire's fields are what a test asserts on, so a test that built an inconsistent one was not testing a reachable record). `add_generated` compares a recorded id's `GeneratedDoc` with the one handed and raises `ValueError(f"generated document {doc_id!r} is already served with a different body")`. `_read_log` raises `ValueError(f"{path}: line {number} is not a valid record ({exc}); the server log is damaged")` where it printed. `McpServer._lines` raises the same shape for a non-object line. `corpus_snapshot(self, turns: Sequence[Turn])`. `_resumed_per_cell` iterates every environment condition cell (`_grid_conversations`'s cells, all reps) and counts the kept ones. `HarvestJudge.__init__(..., items: list[dict[str, str]] | None = None)` answers a harvest prompt with `{"items": items or []}`.

- [ ] **Step 4: Run the tests and the gate**

Run: `uv run pytest tests/test_phase4_minors.py tests/test_generator_run.py tests/test_runtime.py tests/test_mcp_server.py tests/test_phase2_charts.py -q`, then the gate.
Expected: PASS.

- [ ] **Step 5: Docs-sync and commit**

HANDOFF (re-anchor at execution: search for '**Final-review minors still open**'): the seven closed ones move to "closed in Phase 4 Task 14"; every other line gains "(carried past Phase 4)". docs/00 B `GeneratorFire`: the cross-field rule.

```bash
git add claude_bully/records_env.py claude_bully/environments/runtime.py claude_bully/environments/mcp_server.py \
  claude_bully/analysis/authority.py tests/fixtures/generator_stub.py tests/test_generator_run.py \
  tests/test_phase4_minors.py docs/00-RECONCILED.md HANDOFF.md
git commit -m "fix: Phase 4 Task 14, the Phase 3 final-review minors on Phase 4's surface

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

