# Task 11 carries

From the ledger. These bind this task.

- **Preflight rows.** P22, P27 and P55 name Task 11; read each in `preflight.md` in full.
- **The replay parser contract (7a Task 7).** `analysis/replay.parse_replay_line` is the one sanctioned parser of replay text, with a fixture per shape in `tests/test_replay_parser.py`, and a test pins that no other module under `claude_bully/` holds an `UNLOCK` or `HOOK` line literal. Every new shape (`quirk`, `chain`, `contradiction`, `generated`'s `origin`, the bully line's `[<move>]` flag) gets its renderer, its parser case and its fixture; a quote mark or a newline inside an LLM span must not break the layout (Phase 3 Task 4 M8 is the known instance: escape or quote spans the same way for the new shapes).
- **Task 6's strict xfail.** `tests/test_poisoned_well_run.py` holds a strict xfail (`raises=AssertionError`) for the replay move flag; this task drops the mark, and the test must pass.
- **The dossier layout (Task 5 re-review N2).** No internal turn index is ever shown to the target; the replay is for the owner and may name turns.
- **The configs.** Every config dry-runs through `check_condition` and `RunEnvironments.validate()` (Task 5's composition rules; a Poisoned Well with no environment or with a `pressure` is refused). No real names anywhere (non-negotiable 2; the denylist test runs over `configs/`). The target model strings are the project's existing ones. The contradiction judge runs on the experiment's judge (Task 7: a stub judge means templates only). `tests/test_configs.py`'s rglob test must equal the known sets (I45 pattern).
- **The 7b runbook (Task 9 ruling, Task 10).** Every environment-cell Phase 4 rung runs `analyze --ratings`. If this task adds the seven configs to the runbook's "Rungs other phases add", keep that line true and give each its call estimate; no real run is made (owner ruling 2026-11-11).
- **Quote every new target-visible or bully-spoken line in the report** (a config that sets persona text or a twin question counts).
- **Every pytest run uses the pyproject `faulthandler_timeout` (120 s).** A hang is a finding.
