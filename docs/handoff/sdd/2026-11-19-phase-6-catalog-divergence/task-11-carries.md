# Carries into Task 11 (from earlier tasks' reviews)

1. `cli.analyze` catches only `DamagedRecordError` and `RateLimitExit`. An `ArmConfigError` (from `claude_bully/analysis/arms.py`, a `ValueError`) would print a traceback, not an `error:` line. Your test over `configs/` reaches the arm code: make `analyze` (and any other command of this phase that reaches `arm_of`) report an `ArmConfigError` as `error: <message>` with exit 1, with a test.
