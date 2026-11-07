# Task 4 review: doctor --live (9d4b7d2..fb19c95)

I reviewed the diff in one pass. I also made five focused reads outside it, each for a named risk:
- `environments/authority.py` `consult`/`_respond`: does a lost responder write an AuthorityCall?
- `providers/ledger.py` `Ledger`/`activate`/`fold_server_ledger`: what does an existing out dir do to the report, and who folds the server ledger?
- `tests/fixtures/fake_claude.py` main dispatch and MCP launch: what does the fake do on `--version` and in the login modes, and which environment does the MCP server get?
- `mcp_server.py`: where does the nested responder's state live? Under the MCP state dir in the system temp dir, never the working tree.

I ran no tests, because no doubt from the reading needed a test to settle it.

### Spec Compliance
- Issues found. Nothing is missing. One pass rule is partly misunderstood (check 7). Everything else is compliant:
  - Check 1 (command), `doctor.py:_check_command`: runs `--version` under `clean_child_env()`. It passes on exit 0 with no shim suffix. Compliant.
  - Check 2 (login):
    - Any non-empty reply passes and any error fails.
    - The provider names a login error on either exit code. Both `login_error` and `login_error_exit` are tested (`tests/test_doctor_live.py:113-127`).
    - The detail carries the reply and `resolved_model or model`.
    - Compliant with P30a as amended.
  - Check 3 (structured): `JUDGE_SCHEMA` on sonnet, parsed with `JudgeVerdict.model_validate_json(strip_fences(...))`. Compliant.
  - Check 4 (mcp): requires a `tools.jsonl` line and at least one interim text. Compliant.
  - Check 4b (thinking):
    - It reads `ClaudeCodeProvider.thinking_seen` off check 4's unwrapped provider and reports yes, no or unknown.
    - It is always `ok=True`, and `INFORMATIONAL` keeps it out of `failed`.
    - It reports a bool fact and no text (C21). Compliant.
  - Check 5 (responder):
    - Setup: the mini world, the superior self enabled with `discoverable_from="turn"`, and the responder role set directly on the MCP state (the resolved form of `responder_model: target`).
    - It consults `DOCTOR_SUCCESSOR` and passes when an AuthorityCall exists.
    - The detail "answered in N ms" comes from the folded `responder` ledger line (P6, P34a).
    - It makes two model calls (P30b, recorded in the spec).
    - The report's concern 4 holds. `authority.py:543-545` returns `NO_REPLY_TEXT` before any `AuthorityCall` is built, so today "an AuthorityCall exists" means the same as "a reply that is not `NO_REPLY_TEXT`".
  - Check 6 (generator): haiku, `GENERATOR_SCHEMA`, `parse_reply`. Compliant.
  - Check 7 (effort): partly misunderstood.
    - The spec's pass rule is "a reply, and the flag in the ledger line".
    - `doctor.py:303` passes on the reply alone, and its detail says "replied with --effort low" without checking.
    - Only the test pins the ledger half (`tests/test_doctor_live.py:99`).
    - Plan-mandated (the brief's code). See Minor 3.
  - Check 8 (disk): writes and removes a probe in `runs_root`, `runs_root/_cache` and `repo_root/output`, and requires `output/` in `.gitignore`. Compliant. The roots come from the CLI (P22).
  - Check 9 (sandbox):
    - A static read of `build_args` and of check 4's `mcp.json`.
    - It requires servers == ["workspace"], `--tools ""`, `--setting-sources ""` and `--strict-mcp-config`.
    - Compliant, but it depends on check 4's model call succeeding (Minor 1).
  - Report and exit (`cli.py:263-275`):
    - `--out DIR`, default `output/doctor_live_<date>/`, writes `doctor.json` beside `ledger.jsonl`.
    - It prints one line per check and the report path.
    - It exits 1 after the report is written when `failed(results)` is non-empty.
    - Compliant, but see Important 1 on an out dir that already holds a ledger.
  - P12: compliant.
    - Both `--version` runs (offline in `cli.py`, and `doctor.py:_check_command`) pass `env=clean_child_env()`.
    - The test pins two `--version` entries and no `CLAUDECODE*` or `CLAUDE_CODE_*` key in any fake log entry.
  - Carries 1 to 4: all handled as the report says. For carry 2, `providers/claude_code.py` now resets `thinking_seen` before `_write_mcp_config()`.
  - Extra edit (report concern 1): `test_replay_reads_the_world_from_the_run_not_from_the_world_files` lost its `cli.load_world` patch. This is correct and necessary: `cli` no longer binds the name, so `monkeypatch.setattr` would raise, and `cli` cannot call it any more. Justified.
- Cannot verify from diff:
  - Commit author and trailer. Run `git log -1 --format='%ae%n%B' fb19c95` and check for `rankinbc1@gmail.com` and `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
  - The gate counts and 0 warnings. The report states 8225 passed, 5 skipped and 6 deselected, plus 6 slow. Re-run the gate once at the phase boundary.
  - That the suite leaves the real `runs/` and `output/` untouched. The report says so, but no test pins it (Important 3). Check `git status --ignored` after a suite run.
  - LF line endings in the new files.
  - The owner's sign-off on P30a and P30b. Both are now written into the spec's "As planned" Task 4 block.

### Strengths
- The CLI is thin. `cli.py:263-275` resolves `claude` once, opens the ledger, calls `run_live_checks`, writes the report, prints and exits. All check logic is in `doctor.py`, which at 396 lines has one responsibility.
- Each check is a small function that returns `(ok, detail)` behind one `_timed` wrapper. So "every check runs whatever the one before it did" comes from the structure, not from ten try blocks.
- The e2e test drives the real CLI, the real doctor and the real `fake_claude.py`, nested responder included: the fake launches the real MCP server, which builds a real `ClaudeCodeProvider` responder. The test pins:
  - the report and the ledger roles (P6);
  - the effort line;
  - P34a's regex;
  - the resolved model;
  - the two `--version` runs;
  - the clean environment.
- The login-error test covers both exit codes and asserts that the report is written before exit 1.
- Check 4b reads the unwrapped provider's `thinking_seen` and never reads text.
- The report's concern-2 analysis is correct (verified in Important 2), and the concern-1 extra edit was kept minimal.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. Rerunning into an existing out dir mixes two runs' ledgers. Location: `claude_bully/cli.py:266-269`, with `claude_bully/doctor.py:280` and `:383`. The bug is already in the brief's code.
   - What is wrong:
     - `Ledger.write` and `fold` append (`providers/ledger.py:169,192`), and `activate` opens an existing `ledger.jsonl` as it is.
     - The default dir is per date, and rerunning after fixing a login is the normal path. So the second `doctor --live` of a day writes a `doctor.json` whose `ledger` holds both runs' lines.
     - Worse, check 5 takes `nested[-1]` over every `responder` line in that ledger. If this run's nested line is missing (the outer call raised before the fold, or the server wrote none), the detail prints the previous run's latency as if it were this run's.
   - Why it matters: P34a's latency is the number the runbook uses to tune `MCP_TOOL_TIMEOUT` and the responder timeout.
   - Fix: start each live doctor on an empty ledger (unlink or rename `out_dir / LEDGER_FILE` before `activate`). Or record `len(ledger.lines())` at the start, and report and search only the lines after it. Add a test that runs `_live` twice into the same `--out` and asserts that the second report's ledger holds only its own lines.
2. The offline guard patches a name the CLI never reads. Location: `tests/test_cli.py:251` (plan-mandated).
   - What is wrong:
     - `monkeypatch.setattr("claude_bully.doctor.run_live_checks", explode)` replaces the attribute on the `doctor` module.
     - But `cli.py:118` bound `run_live_checks` into `cli` at import time, and `cli.doctor` calls that binding.
     - So the test exercises the real offline CLI path, but the `explode` guard is inert: if the offline path ever called the live checks, `explode` would never fire.
   - Why it matters:
     - The test's own `"mcp" not in result.output.lower()` would still catch that regression by accident, because the live path prints `mcp: ...`. So the risk today is low.
     - But this line is the test's stated guard ("never builds a provider"), and it pins nothing.
   - Fix:
     - Use `monkeypatch.setattr(cli, "run_live_checks", explode)`.
     - To match the test's name, also add `monkeypatch.setattr("claude_bully.doctor.ClaudeCodeProvider", explode)`. `doctor.py` looks that name up at call time, so this patch does take effect.
3. The P22 assertion is vacuous. Location: `tests/test_doctor_live.py:95` (plan-mandated).
   - What is wrong:
     - `_check_disk` always unlinks its probe (`doctor.py:312-313`), so `not (repo / "output" / ".doctor_probe").exists()` holds whichever repo was probed.
     - Nothing pins that the CLI passes its call-time `REPO_ROOT` (the test's tmp repo) rather than the real one.
   - Why it matters:
     - Suppose `cli.py:268` dropped `repo_root=REPO_ROOT`. The default `doctor.REPO_ROOT` would then be probed, and since the real repo's `.gitignore` also lists `output/`, every assertion would still pass.
     - Every suite run would then create `output/` in the working tree, silently breaking a non-negotiable.
   - Fix: assert `(tmp_path / "repo" / "output").is_dir()`. The disk check creates that directory, so the assertion fails if the probe went elsewhere.

#### Minor (Nice to Have)
1. Checks 9 and 4b depend on check 4's model call returning. Location: `doctor.py:206,364` and `:325-327`.
   - `mcp_provider` is assigned from `_check_mcp`'s return tuple. When the outer call raises (not logged in, timeout), the sandbox check fails with "the MCP check did not run", although check 4 ran and wrote `mcp.json`. 4b also reads "unknown", even if the stream parsed.
   - The spec ties check 9 only to the config check 4 wrote, so it is a static check.
   - Fix: build `inner` and assign `mcp_provider` before the call, separating construction from `complete`.
2. On failure, check 5 reports the least just when it matters most. Location: `doctor.py:263-277`.
   - `fold_server_ledger` is not in a `finally`. If the outer call fails after the nested call ran, the nested line is lost with the temp dir.
   - The failure detail says "(see stderr)", but on a real run the MCP server's stderr goes to Claude Code, not to the doctor's terminal.
   - Fix: fold in a `finally`. On failure, print the nested ledger line's status and latency, so the detail says whether it was a timeout, an error or no line at all.
3. Check 7 does not verify "the flag in the ledger line". Location: `doctor.py:303` (plan-mandated). Fix: read the newest `doctor-effort` ledger line and require `effort == "low"`.
4. Two identical except branches; the `ProviderError` one is dead code. Location: `doctor.py:136-139` (plan-mandated). Keep one `except Exception`.
5. Unused interface pieces. Location: `doctor.py:344` and `:112` (plan-mandated). `run_live_checks` never uses its `out_dir` parameter, and nothing sets `CheckResult.cost_usd`. Drop them or use them.
6. An inert re-export (report concern 3). Location: `doctor.py:49-52` and `tests/test_doctor_live.py:58-60`. `doctor.py` re-exports `resolve_claude_command` only so the fixture can patch it, but `doctor` never calls it, so both the re-export and that patch are inert. Remove both; the `cli` patch is the one that matters.
7. `cli` imports `failed` (and `INFORMATIONAL`), but neither is in `__all__`. Location: `doctor.py:63` and `cli.py:118`.
8. A bare `assert` in library code disappears under `python -O`. Location: `doctor.py:377`. Raise instead, or drop it.
9. The `.gitignore` check is an exact line match. Location: `doctor.py:318`. `/output/`, `output` and `output/*` all read as "not ignored". Running `git check-ignore -q output/` under `clean_child_env()` would be exact.
10. The fake cannot show that the nested responder strips anything. Location: `tests/fixtures/fake_claude.py:90-95` and `tests/test_doctor_live.py:109`.
    - The fake launches the MCP server with its own environment, which is already clean. Real Claude Code sets `CLAUDECODE` for its children.
    - So the e2e test proves that the outer child is clean but not that the nested responder strips anything, and that strip is check 5's first failure mode.
    - Fix: have the fake set `CLAUDECODE=1` (and one `CLAUDE_CODE_*` key) in the server's environment, so the assertion on the nested entry means something.
    - The fake also has no `--version` branch: it answers with a JSON result line. So on the fake, check 1's detail is a JSON fragment, and in `login_error_exit` mode check 1 fails spuriously (no test asserts it).
11. The default dir uses the UTC date. Location: `doctor.py:124`. An evening run west of UTC lands in tomorrow's folder. Use the local date, as the workspace's `output/<name>_<date>/` convention does.
12. The HANDOFF range is a placeholder. Location: `HANDOFF.md:174` says "9d4b7d2..Task 4 commit". Fill in `9d4b7d2..fb19c95` at the next docs sync, as was done for Task 3's range.

### Assessment
Task quality: Needs fixes
Reasoning: The nine checks plus 4b match section 9 as amended, and the e2e test really drives the doctor through the fake. But a rerun into an existing out dir corrupts the report's ledger and can print a stale responder latency, and two of the tests' guards (the offline `explode` patch and the P22 probe assertion) pin nothing; all three are small fixes.
