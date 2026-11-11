# Task 12 review (961ccab..adedf7d): neutral child cwd, email scan, attached date stated

Reviewer: read-only on tracked files. Probes are under `probes-task12/` beside this file (scratch, git-ignored). I re-ran ruff check, ruff format --check and mypy (all clean), and these tests: `tests/test_providers_claude_code.py`, `tests/test_doctor_live.py` (110 passed), the email tests in `tests/test_wait_and_promote.py` (7 passed), the two R5 tests in `tests/test_phase2_charts.py`, and two in `tests/test_runner_env.py` (4 passed, `-W error`). I did not re-run the full gate; the 8437 / 5 / 8 and slow 8 counts are the implementer's.

## Verdicts

- **Spec compliance: met.** R1, R2, R4 met; R3 and R5 deviated-acceptably (one deviation each, both justified); Produces 1 to 6 met.
- **Code quality: Approved with minors.** 0 Critical, 1 Important (a test-only gap; the product code is right), 9 Minor. Take the Important in a fix pass before the push, or carry it knowingly; it is about six lines in one test.

## Spec compliance

| Item | Verdict | Note |
|---|---|---|
| R1 root | met | `CHILD_ROOT_ENV`, else `%PUBLIC%\w` (fallback `C:\Users\Public`) on win32, `/tmp/w` elsewhere. Beyond the ruling: root and dir made through `prepare_sandbox` (0o700, no link or junction, POSIX owner and mode). Additive hardening, acceptable. |
| R2 stability | met | Verified across processes (see Check 1). |
| R3 problems and refusal | deviated-acceptably | Function, refusal, doctor check 9 all as ruled. The refusal is in `complete`, not at construction; the report says why and the reason is sound (check 4 must be able to build its provider so check 9 can read it). The deviation is in the suite: it runs under an invented login and home folder (see Check 2 and I1). |
| R4 email | met | Brief's pattern with the domain as group 1; reserved list as ruled; every stream, target included; `--exempt` does not spare; lines say `email address (domain redacted)`. |
| R5 attached date | deviated-acceptably | `backend_attaches_date` is top-level in `temporal.json` and `SCHEMA_VERSION` stays 3. `results.md` had no temporal section, so one is added (`## Temporal`) only when any value is true; plain and stub runs are byte-identical. |
| Produces 1 | met | All four functions plus `state_run_ids`; `self._cwd = child_cwd(state_dir)`; the docstring names finding 1 and session-by-directory. |
| Produces 2 | met | Guard sets the root to a session temp dir; the two `cwd` tests are rewritten; R2 stability, R3 kinds, refusal and default-root tests are present. |
| Produces 3 | met | Check 9 appends `cwd neutral` or `cwd NOT neutral: ...` and fails on problems; both details tested. |
| Produces 4 | met | `EMAIL`, `_RESERVED_EMAIL_DOMAINS`, `EMAIL_HIT`; tests for reserved, each of five streams, and `--exempt` (display name, `target_exempt`, `promote(exempt=)`, CLI). |
| Produces 5 | met | Stub run gives `false` and no note; `claude_code` on `fake_claude.py` gives `true` and the note. |
| Produces 6 | met | Runbook Step 0 and the 0b re-run; HANDOFF Progress and Next steps (the "..the Task 12 commit" form matches Task 11's); docs/00 H "version 3, additive"; spec "As planned"; the four README drafts (`.superpowers/drafts` and `docs/handoff/drafts` are byte-identical, `cmp` clean). |

## Checks you asked for

### 1. Resume: same state_dir, same cwd, across processes and in the nested responder

Yes. `child_cwd` hashes `str(state_dir.resolve())`.

- `probes-task12/probe_stable.py` run as separate processes gave the same directory for: an absolute path; the same path lower-cased with a different process cwd; forward slashes; the 8.3 short profile name; and an MCP-like minimal environment with no `PUBLIC`. A relative `state_dir` differs by process cwd, but `_sessions_path` has the same property today, so it is not a regression.
- `probes-task12/test_probe_resume.py` runs the pause-then-resume annex scenario on `fake_claude.py` (target, MCP server, nested responder, a rate-limit pause and a second `run_experiment`) and prints every logged cwd. The target is `fresh` once, then `resume` on later turns, always in the same directory. The nested responder, in a new MCP-server process each outer call, always runs in one other directory. The responder's calls are all `fresh` by design (it never resumes), so the nested resume path is not exercised, but its cwd is stable anyway. The target and responder directories are distinct.
- `test_a_session_resumes_from_the_directory_it_started_in` and the doctor live test pass.

Caveat that applies to every fake-based resume test: `fake_claude.py` does not enforce session-by-directory, so it can only show the cwd is equal, not that a real CLI finds the session. That is the property R2 pins and I confirmed it. Two things the runbook does not say (M6): the root variable must be identical when a paused run is resumed, and a run started before this commit cannot resume.

### 2. The conftest login and home override

It cannot leak into a product code path: the only product readers of `getpass.getuser()` and `Path.home()` are in `neutral_cwd_problems` (`grep` over `claude_bully` finds no others). It reaches children and the MCP server by environment, which is the only way to reach the nested responder, so the deviation is the right shape. Both the brief's temp root under the profile and R3's "no login segment" cannot hold together on Windows; the implementer resolved the conflict correctly and said so.

`REAL_USER_NAMES` is derived at import from `getpass.getuser()` and `Path.home().name`; no real name is typed anywhere. The diff has no real name, login or email on an added line (grep of the diff for the login, the name and the commit-author address finds only two pre-existing HANDOFF context lines).

It can, however, hide a real failure of R3 (I1): under the override the login and the home folder's name are both `stub-login`, so the home-folder clause is never exercised on its own. I confirmed this in `probes-task12/test_probe_override.py` (`login == home` under the suite's environment). Deleting the home check from `neutral_cwd_problems` leaves every test green. With distinct values the product check works (same probe: `inv-login`, `inv-login.CORP` and a case variant each give exactly one problem).

### 3. Concern 2: predictable inherited-ACL cwd under `%PUBLIC%\w`

Real risk: low. Impact: data integrity of an experiment (prompt injection into the target), not code execution.

- Every child gets `--setting-sources ""` (`build_args`, unconditional), plus `--strict-mcp-config` and `--tools ""`. Planted `.claude/settings*`, `.mcp.json` and, per the CLI's source-gating, `CLAUDE.md` are not read. Direct evidence on this CLI (2.1.319): the old cwd (`runs/<id>/state/.../cwd`) had the owner's `C:\Users\<login>\CLAUDE.md` in its ancestor chain, and the rung 0 report lists only `userEmail` and `Environment` as attached sections, no memory file. That is inference from the report, not a canary; I did not run the real `claude`.
- On this machine `icacls C:\Users\Public` shows `INTERACTIVE:(OI)(CI)(IO)(M,DC)` plus `INTERACTIVE:(RX,WD,AD)` on the folder itself, and the same for SERVICE and BATCH. So another interactive or service principal can create `w` first, or plant files under `w\<hash>`, or in `Public` itself. That needs a second principal on the box; a single-user work laptop has none in practice.

"Refuse a non-empty cwd" is cheap but not right:

1. It guards the leaf only. The CLI also walks ancestors, and `w` and `Public` are equally writable, so a planted `C:\Users\Public\CLAUDE.md` is not covered.
2. It risks a worse failure than the one it prevents. The rung 0 `cwd` directories on disk are empty (checked under `docs/handoff/runs/*/state/**/cwd`), so there is no false positive today, but if any CLI version writes a `.claude/` or scratch file into its cwd, every resumed call is refused and runs stop resuming.
3. A check-then-spawn window remains, and it is a new behaviour no ruling asked for.

Cheaper and more correct, in order: (a) one canary in the 0b re-run (plant a `CLAUDE.md` with a nonsense token in `w\<hash>` and in `w`, ask the target to repeat any project instructions, confirm none appear); (b) if the owner wants it enforced, a targeted check for `CLAUDE.md`, `CLAUDE.local.md`, `.claude` and `.mcp.json` in the leaf and its ancestors, not "non-empty"; (c) on Windows, a one-time `icacls <root> /inheritance:r /grant:r <current user>:(OI)(CI)F` when the root is created. None is needed to approve this task (M1).

### 4. The email scan

`probes-task12/probe_email.py` runs 32 cases. Handled as intended:

- Subdomains of a reserved name are spared (`a@mail.example.com`, `a@b.c.example.net`); subdomains of a non-reserved name block.
- Plus-addressing, upper case, `mailto:`, an apostrophe in the local part, trailing `.` `,` `)` all block (the trailing-dot reserved FQDN `a@example.com.` is spared, correctly).
- Spoofs block: `x@example.com.evil.org`, `x@notexample.com`, `x@example.com-evil.org`. `x@evil.org.example` is spared, which is right since `.example` is reserved.
- `a@example.com, b@real.net` blocks on the second.
- `EMAIL_HIT` (from `email_hits`) is the only thing in any line or in the `ValueError`; the tests assert neither the local part nor the domain appears, including in the CLI output.

Not caught (M7): quoted local parts, non-ASCII local parts and IDN domains, `[at]`/`at ... dot` obfuscation, `%40` and `&#64;`, a fullwidth `@`, a zero-width character, and an address split across a line break. One false positive: `pkg@next.js` (a loud, harmless refusal). The threat is the target quoting its own attached context verbatim, which is plain ASCII and is caught, so this is acceptable.

### 5. No real name, login or email in the diff

Clean. The test address is `pennet.quay@zzq-invented-mail.net`; reserved examples are invented; login and home values come from `getpass`/`Path.home()` at run time or are `stub-login`. The two author-email hits in the diff output are unchanged HANDOFF context lines from before this task. Commit author is `rankinbc1@gmail.com`; trailer is `Co-Authored-By: Claude Opus 5.5`, as the brief asked.

## Findings

### Critical

None.

### Important

**I1. The home-folder clause of R3 has no effective test.** `tests/conftest.py:74-75` sets `LOGNAME=stub-login` and a home folder named `stub-login`, so `tests/test_providers_claude_code.py:252` (`test_the_login_and_the_home_folder_name_are_problems_unquoted`) tests `{login, LOGIN, home}` where `home == login`; the assertion `"login" in problems[0] or "home folder" in problems[0]` accepts either branch. Failure scenario: a refactor drops or breaks the `home` comparison (`claude_code.py:134-141`); on a domain-joined profile whose folder is `First.Last.CORP` while the login is `First.Last`, the profile name reaches the CLI's `# Environment` block via a `CLAUDE_BULLY_CHILD_ROOT` under it, and the suite stays green. Fix (test only): in that test `monkeypatch.setenv("LOGNAME", ...)` and `monkeypatch.setenv(HOME_ENV, <tmp>/<a different name>)`, then assert the login and the home name each give one problem, with the right wording, and that neither quotes its name. `probes-task12/test_probe_override.py::test_product_check_with_distinct_login_and_home` is a working model.

### Minor

- **M1. Public ACL, concern 2.** Accept as is (Check 3). Carry it into HANDOFF's open items with the canary in (a) as the 0b re-run's extra check, so the CLAUDE.md claim is measured once instead of inferred.
- **M2. `neutral_cwd_problems` can raise instead of reporting** (`claude_code.py:133-134`). With no `USERPROFILE`/`HOMEPATH` (Windows) `Path.home()` raises `RuntimeError`; with no `LOGNAME`/`USER`/`USERNAME` `getpass.getuser()` raises `ModuleNotFoundError` on Windows (both reproduced with `env -i`). The real CLI's MCP default environment carries `USERNAME` and `USERPROFILE` on Windows and `HOME`/`LOGNAME`/`USER` on POSIX, so the nested responder should be fine, and doctor check 6 would show a failure live. Failure scenario: a stripped environment (service, container) crashes `complete` or check 9 with a traceback instead of a `ProviderError`/`NOT neutral` line. Wrap both calls and return a problem line ("cannot determine the user, set CLAUDE_BULLY_CHILD_ROOT").
- **M3. `UnsafeSandboxError` is not a `ProviderError`** (`claude_code.py:536-537`). A `CLAUDE_BULLY_CHILD_ROOT` that already exists as a mode 755 directory on POSIX, a second POSIX user meeting the shared `/tmp/w`, or a planted junction on Windows raises `UnsafeSandboxError` out of `complete`. The message is clear and the run stops either way (the runner handles neither), so this is cosmetic, but doctor and callers that catch `ProviderError` miss it. Convert at the call site. The `/tmp/w` shared-name consequence is R1's ruling, not a defect.
- **M4. Relative `CLAUDE_BULLY_CHILD_ROOT`** (`claude_code.py:112-113`): returned as given, so the child's cwd depends on the process cwd and resume across a changed process cwd would not find the session. `Path(configured).expanduser().resolve()` fixes it (and keeps the digest unchanged).
- **M5. Run-id match is a bare substring over every segment** (`claude_code.py:146`), the 12-hex digest and the root name included. A run id of `w`, `c`, `a`, `public`, or a hex word such as `beef` refuses spuriously (loudly, with a clear message). Acceptable as reported (concern 4); a minimum length (say 4) or whole-segment equality for short ids would remove the surprise.
- **M6. Docs gaps.** The runbook's 0b re-run and Step 0 should say: set `CLAUDE_BULLY_CHILD_ROOT` the same way when resuming a paused run (a different root gives a different cwd and `--resume` finds nothing); a run started before Task 12 cannot resume (report concern 1; HANDOFF only says restored runs are for replay). `%PUBLIC%\w` also accumulates one empty `<hash>` directory per provider and per doctor run, never cleaned; worth one line.
- **M7. Email regex edge cases** (Check 4): non-verbatim and non-ASCII forms are missed. Fine for the stated threat; note in `promote.py`'s docstring that only a verbatim ASCII address is detected.
- **M8. Copied-but-unscanned text.** `promote` copies `judge_cache/` and `analysis/` (`promote.py:40`, `234`) and scans neither for emails (nor names; pre-existing). The finding says the judge's own context carries the owner's address; a judge `rationale` that quoted it would be published. Improbable and within the brief's scope ("every text it already scans"), but `email_hits` over those copies is a few lines.
- **M9. Report concern 5 is wrong, in the safe direction.** An 8.3 profile name in `CLAUDE_BULLY_CHILD_ROOT` is caught by the provider, because `cwd_problems()` passes the resolved path: `C:\Users\<8.3 name>\w` gave `["segment 2 is the user's login"]` here. Only the pure function on an unresolved path would pass it. Also a design wart worth a sentence: a home folder named `tmp` (`HOME=/tmp`, common in containers) makes the default `/tmp/w` refuse itself; the escape is the env var.

## Probes (all under `probes-task12/`, none touches tracked files)

- `probe_stable.py`: digest stability across processes, case, slashes, 8.3 names, minimal env.
- `test_probe_resume.py`: pause and resume on `fake_claude.py` with the nested responder; prints every logged cwd. Run with `uv run pytest -q -s -p tests.conftest <file>`.
- `test_probe_override.py`: `login == home` under the suite's override; product check with distinct values.
- `probe_email.py`: 32 regex and reserved-domain cases.
