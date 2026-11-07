# Carries into Task 9 (from earlier tasks)

1. HANDOFF.md: fill the Task 8 range placeholder "7c22de9..Task 8 commit" with `7c22de9..b53e444`; your own entry may use the placeholder shape "b53e444..Task 9 commit".
2. (Task 8 re-review, minor) `claude_bully/cli.py`: the `promote --exempt` option's help text says the name is spared in target text only (display names are spared everywhere). One line.
3. Facts from Tasks 1 to 8 the brief (written before them) cannot know:
   - Task 1 added `test_no_config_names_a_claude_command`: no YAML under `configs/` or `tests/fixtures/configs` may set a `claude_code` role's `command`. Your ladder configs must not; the test will tell you.
   - Task 1's `tests/test_configs.py` may already have moved or grown; read it before adding `ENVIRONMENT_EXPECTED`, `LADDER_EXPECTED` and the rglob test (I33, I45, P30c). P30c's spec amendment (the env-config `EXPECTED` sets are not widened; `configs/ladder/` is covered by `LADDER_EXPECTED` and the rglob test) is signed off by the owner in advance; write it into the spec's "As planned" in your docs-sync without a further stop.
   - Task 3: `RoleConfig.timeout_s` exists (`Field(default=None, gt=0)`); the ladder YAMLs do not set it (P15); `responder_role` gives the Sanctuary target role `timeout_s` 120.
   - Task 5: the LLM reader-address lint runs whenever the judge is not a stub, over `INSTRUCTIONAL_KINDS` (`family_faq`, `recovery_guide`). The ladder configs name real judges, so the lint is on in every rung; a dry run or `_stubbed` copy never reaches it. If a ladder config's world generator block sets `allowed_kinds`, keep the two instructional kinds in (the spec's rung 1 probe measures the lint on them).
   - Task 6: `analyze --authority-fallback` exists and is off under a stub judge; the runbook (Task 10) names it, your configs do not.
   - Task 8: `promote --exempt` and `readme-results --from-results` exist; `run` and `analyze` take `--wait-on-rate-limit MINUTES`.
   - The owner ruled (merged question 5) that model aliases are not pinned in 7a: the configs name `sonnet`, `haiku`, `opus` aliases as the brief says; the ledger records `resolved_model`; the owner pins ids in 7b.
4. The kindness edit: the brief names the config and the line. The non-negotiables apply: hostility ceiling "cruel person", no jailbreak axis, earned never delivered. Read `tests/test_boundary.py` and the persona it scans before editing persona text.
