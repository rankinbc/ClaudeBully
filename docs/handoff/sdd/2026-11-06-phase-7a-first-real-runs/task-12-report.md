# Task 12 report: a neutral working directory for every claude -p child, email addresses in promote's scan, the attached date stated

Status: DONE_WITH_CONCERNS. Commit: adedf7d (BASE 961ccab), author rankinbc1@gmail.com, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Not pushed. No subagents were used.

## What changed, per Produces item

1. `claude_bully/providers/claude_code.py`
   - `CHILD_ROOT_ENV = "CLAUDE_BULLY_CHILD_ROOT"`, `child_cwd_root()`, `child_cwd(state_dir)`, `neutral_cwd_problems(path, *, run_ids=())`, and also `FORBIDDEN_CWD_WORDS` and `state_run_ids(state_dir)`.
   - `self._cwd = child_cwd(state_dir)`, plus `self.run_ids = state_run_ids(state_dir)`, a `cwd` property and `cwd_problems()`.
   - The refusal is in `complete`, not at construction. It runs after `_write_mcp_config()` and before the working directory is made or any child starts. Construction-time refusal would have stopped doctor check 4 from building its provider, so check 9 would have had nothing to inspect. Refusing after the MCP config is written lets check 9 read `mcp.json` and report the cwd line.
   - The directory is made with `runner/sandbox.py: prepare_sandbox(cwd, fresh=False)`. Both the root and the directory are made 0o700, and an existing one is reused only if it is a real directory (never a link or junction) and, on POSIX, owned by this user and mode 700. This is the house pattern for a shared `/tmp` (CWE-377). It goes beyond R1; the reason is under Concerns.
   - The module docstring names finding 1, the attached sections, and the CLI's session-by-directory behaviour.
2. `tests/conftest.py`
   - The session guard sets `CLAUDE_BULLY_CHILD_ROOT` to `tmp_path_factory.mktemp("child_root")`.
   - It also sets an invented login (`LOGNAME=stub-login`) and an invented home folder (`USERPROFILE` on Windows, `HOME` elsewhere, under a session temp dir). This is a deviation; see R3 below.
   - `REAL_USER_NAMES` holds the real login and home folder name, read at import before the patch. They are compared at run time and written nowhere.
   - `tests/fixtures/fake_claude.py` now logs its `cwd`.
   - Updated tests: `test_providers_claude_code.py` (the old `test_cwd_is_clean_dir_under_state` became `test_the_child_runs_in_an_opaque_directory_under_the_neutral_root`) and `test_runner_env.py` (the envcc sandbox test now asserts that every logged cwd is `child_cwd(sandbox)`, that no `sandbox/cwd` exists, and that neither the run id nor "bully" is in the cwd).
   - New tests:
     - R2: two providers on one state dir get the same directory, two state dirs get two, `..` normalises, and the digest equals sha256 of the resolved path. A resumed session's child runs from the same cwd as the first call.
     - The default root with the env var deleted is `%PUBLIC%\w` or `/tmp/w`, with no segment equal to a real user name, and it is neutral.
     - The env var wins.
     - R3: each forbidden word (parametrised), the login, the upper-cased login and the home folder name are each a problem, and the problem line does not quote the name. A name inside a longer segment is not a problem. A run id is a problem, and `state_run_ids` reads the run id off a state dir.
     - Refusal: a root inside the repo is refused with no child started and nothing made inside the repo, and a root under a run is refused by its run id.
3. `claude_bully/doctor.py`: check 9's detail ends `; cwd neutral` or `; cwd NOT neutral: <problems>`, and the check fails on problems. In `tests/test_doctor_live.py`, the passing test asserts `endswith("; cwd neutral")`. The new `test_check_9_fails_on_a_working_directory_that_is_not_neutral` points the root at the repo and asserts: exit 1, check 9 not ok with `cwd NOT neutral: ... 'claude'`, the login check refused with "not neutral", nothing made in the repo, and only `--version` runs reached the fake.
4. `claude_bully/analysis/promote.py`
   - Adds `EMAIL` (the brief's pattern, with the domain as group 1), `_RESERVED_EMAIL_DOMAINS`, `_reserved`, `email_hits` and `EMAIL_HIT = "email address (domain redacted)"`.
   - `scan_real_names` adds the email hits of every stream it scans to `blocking`: bully and target turns, tool results, generated documents and responder replies. No exempt list applies to them. The lines keep the existing `<cell> rep<k> <source>` prefix, so `_blocking_summary` counts them (for example "1 in target turns").
   - The `ValueError` text now reads "harness-side text names a real name, or a text holds an email address".
   - Tests in `tests/test_wait_and_promote.py`:
     - Reserved addresses pass and promote: `.example`, `.test`, `.invalid`, `.localhost`, `example.com`, a subdomain of `example.org`, and an upper-case `EXAMPLE.NET`.
     - An invented non-reserved address blocks in each of the five streams (parametrised). Neither the blocking line nor the error holds the address.
     - Exempting the address (as a display name, as `target_exempt`, via `promote(exempt=)` and via the CLI's `--exempt`) does not spare it.
5. `claude_bully/analysis/temporal.py`
   - Adds `ATTACHED_DATE_NOTE` (the brief's sentence), `backend_attaches_date(loaded)` (model -> bool over the sweep conversations, sorted) and `attached_date_note(loaded)`.
   - `write_temporal` adds the top-level `backend_attaches_date`.
   - `analysis/progression.py` gains `target_provider` beside `target_model`.
   - `analysis/report.py: write_results_md(..., temporal=None)` writes a `## Temporal` section after `## Calls` only when given a line, and `run_analysis` passes `attached_date_note(loaded)`.
   - Tests in `tests/test_phase2_charts.py`:
     - The stub sweep (a copy) gives `{stub-target: False}`, no note, and no `## Temporal` in results.md.
     - A cut sweep (`overlay_p1`, one rep) whose target is `claude_code` on `fake_claude.py` runs to completion and gives `{"stub-sonnet-20260101": True}`, the note in results.md and the field in temporal.json.
6. Docs-sync:
   - `docs/handoff/phase-7-runbook.md`: Step 0 says how to read check 9's cwd line and what to do on `NOT neutral`. Rung 0 gains "The 0b re-run after Task 12": doctor first, the old run moved aside, no target line holding a harness path, and the date and model id recorded.
   - `HANDOFF.md`:
     - "Last updated" now names Task 12.
     - Progress gains "Phase 7b rung 0 fix, Task 12 (961ccab..the Task 12 commit)".
     - Next steps step 1 is the doctor rerun and the 0b re-run; the later steps are renumbered.
     - The setup step's expected counts are updated.
   - `docs/00-RECONCILED.md` section H gains a Task 12 bullet ("version 3, additive").
   - The spec's "As planned", Phase 7b, gains the Task 12 bullet with the owner's ruling.
   - The README drafts' "Limitations" (`README.v2.md` and `README.draft.md`, in both `.superpowers/drafts/` and `docs/handoff/drafts/`, which stay identical) gain the attached-context paragraph.

## R1 to R5 as built

- **R1, as ruled.** `CLAUDE_BULLY_CHILD_ROOT`, else `Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "w"` on win32 and `Path("/tmp") / "w"` elsewhere. Added beyond the ruling: the root and directory are made through `prepare_sandbox` (0o700, no links, owned by this user on POSIX), and the root's parent with `mkdir(parents=True)`.
- **R2, as ruled.** `child_cwd_root() / sha256(str(state_dir.resolve()))[:12]`. Stability across instances is pinned, and a resumed session's child runs from the same cwd. For an environment cell the provider's state dir is the sandbox, so its cwd is a digest of the sandbox path. The sandbox's `mcp/` files stay in the sandbox.
- **R3, built with one deviation in the suite, not in the product.**
  - `neutral_cwd_problems` is pure: it reads the path as given and touches no file, and the provider passes it resolved. It skips the anchor, so the drive is not a segment.
  - A login or home folder name segment is reported by position only ("segment 3 is the user's login"), so the doctor report never holds the name. Doctor reports get snapshotted into `docs/handoff/`.
  - Run ids: the function takes `run_ids`, and the provider passes `state_run_ids(state_dir)`, the segment before each `state` segment (the `RunStore` layout `<root>/<run_id>/state/...`). The brief did not say how a pure function would know the run id, so this was my choice.
  - The deviation: the brief has conftest set the root to a session temp dir. On Windows that dir is under `C:\Users\<login>\...`, so every child in the suite would be refused, including the nested responder that the MCP server subprocess builds, which a monkeypatch cannot reach. To follow the brief's intent (a temp root, nothing under Public, the real check in force), the suite runs under an invented login and home folder set in the environment, which crosses process boundaries. The check itself is unchanged.
- **R4, as ruled.** The brief's regex. Reserved names match the domain exactly or as a suffix after a dot, case-insensitively. Lines say `email address (domain redacted)`. Every stream blocks, the target's included, and `--exempt` does not spare an address.
- **R5, as ruled, with one deviation.** results.md had no temporal section, so the line goes in a new `## Temporal` section that is written only when the note applies. Plain and stub runs are unchanged, and the golden record fixtures are untouched. `SCHEMA_VERSION` stays 3.

## RED evidence (tests written first, run before any implementation)

```
tests/test_providers_claude_code.py, tests/test_runner_env.py:
E   ImportError: cannot import name 'child_cwd' from 'claude_bully.providers.claude_code'
tests/test_phase2_charts.py:
E   ImportError: cannot import name 'ATTACHED_DATE_NOTE' from 'claude_bully.analysis.temporal'

tests/test_wait_and_promote.py, tests/test_doctor_live.py (-k "email or check_9 or passes_every"):
>       assert len(report.blocking) == 1 and not report.reported
E       assert (0 == 1)                       (x4 streams; the target stream likewise)
>       assert len(report.blocking) == 1
E       assert 0 == 1                         (exempting the address)
>       assert checks["sandbox"]["detail"].endswith("; cwd neutral")
E       assert False
>       assert result.exit_code == 1, result.output
E       assert 0 == 1                         (check 9 on a root inside the repo)
FAILED ...test_a_personal_email_address_blocks_in_every_stream[bully|target|tool|generated|responder]
FAILED ...test_exempting_an_email_address_does_not_spare_it
FAILED ...test_doctor_live_passes_every_check_on_the_fake
FAILED ...test_check_9_fails_on_a_working_directory_that_is_not_neutral
8 failed, 1 passed, 23 deselected
```

(The one that passed was `test_a_reserved_email_address_passes`: it pins behaviour that must not change.)

## Gate (0 warnings)

- `uv run ruff format --check .`: 276 files already formatted
- `uv run ruff check .`: All checks passed
- `uv run mypy claude_bully`: no issues in 110 source files
- `uv run pytest -q -W error`: 8437 passed, 5 skipped, 8 deselected (from 8414; +23 new tests) in 11:21
- `uv run pytest -q -m slow`: 8 passed

Golden plain fixtures are untouched (no record change).

## Concerns

1. **Runs started before this commit cannot `--resume` their claude sessions.** The CLI files a session under its working directory, which is now a different directory. The rung-0 runs are snapshots and are not to be resumed (runbook), so nothing live is affected. A run in flight across this change would fail on its first resumed call.
2. **`%PUBLIC%\w` is shared on Windows.** Subdirectories inherit Public's ACL: INTERACTIVE users get Modify, and `os.mkdir`'s mode is ignored on Windows. Another local user could plant a `CLAUDE.md` in a predictable `<hash>` directory, and the CLI may read a `CLAUDE.md` from its working directory: a prompt-injection path on a shared machine. The digest is predictable only to someone who knows the state dir path. A cheap later hardening: refuse a cwd that is not empty before each call. On POSIX the 0o700 check covers this.
3. **The suite now runs under an invented identity** (`LOGNAME`, plus `USERPROFILE` or `HOME`). Nothing in the code or the tests read either before this task; git (`rev-parse`) and matplotlib run under the fake home without issue in this gate. A future test that needs the real home must read `REAL_USER_NAMES` or restore the variable.
4. **The run-id match is a substring match over every segment, the 12-hex digest included.** A run id made only of hex characters could, rarely, match its own digest and refuse spuriously. That fails loudly, and the env var is the escape.
5. **The refusal checks the resolved path.** A symlinked root that points into the repo is caught. A root reached through an 8.3 short profile name (`ABCDEF~1`-style) would pass the login check, because the segment is not the login. It is not a security boundary; it catches mistakes.

## Fix round 1 (FIX_BASE adedf7d)

Commit: 65dff39 on top of adedf7d, author rankinbc1@gmail.com, Opus 5.5 trailer, not pushed. Scope is `task-12-fix-round-1.md`: the email scan over every copied file, I1, M1, M2, M3, M4 and M6. M5, M7 and M9 are deferred.

### Per item

1. **Email scan over every copied file (security MEDIUM, closes M8).**
   - `promote.py` gains `copied_files(store)` (every file `promote` copies, in order) and `scan_copied_emails(store)`.
   - `scan_copied_emails` decodes each copied file as UTF-8 with `errors="replace"` and runs `email_hits` line by line. A hit's line reads `<run-relative file> line <n>: email address (domain redacted)`.
   - It skips `BINARY_SUFFIXES` (the image suffixes and `.pdf`) and any file with a NUL byte; those are never decoded.
   - `promote` raises before anything is copied, after the real-name scan. That scan stays on its streams, and so does the stream email scan, which also covers the tool, generated and responder files that are not copied.
   - The copy now walks the same `copied_files` list, so the scanned set and the copied set are one set.
   - Tests:
     - An address in `reasoning_text`, in a judge cache entry, or in a `bully_meta` capture blocks. The test also shows that the chat-text scan alone passes each one, and that the error names the file and the line but never the address.
     - Nothing is copied when a block fires.
     - A reserved address in a copied file passes, and a `.png` whose bytes spell a non-reserved address is copied unread.
2. **I1.**
   - The suite no longer overrides the login or the home folder at all. With the root moved out of the profile for M1 (below), the override was no longer needed.
   - `test_the_login_and_the_home_folder_name_are_problems_unquoted` sets `LOGNAME=inv-login` and a home folder named `inv-login.CORP`. It asserts the exact line for each clause, that neither line repeats its name, and that the machine's real names (from `REAL_USER_NAMES`) are problems too.
   - Confirmed: with the home clause deleted, this test fails with `AssertionError: ('inv-login.CORP', [])`. With the clause restored, it passes.
3. **M1.**
   - `PROJECT_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude", ".mcp.json")` and `planted_project_files(path)` cover the cwd and every ancestor, nearest first.
   - `cwd_problems()` appends `<path> is a Claude Code project file the CLI may read` for each one found. Any path segment that is the login or the home folder name is shown as `<user>`, so the name never lands in a doctor report. `complete` therefore raises a `ProviderError` naming the path before any child starts, and check 9 fails with `cwd NOT neutral: ...CLAUDE.md...`.
   - The default root passes on this machine: `test_the_default_root_has_no_project_file_above_it` deletes only the env var and gets `[]`. By hand: none of the four names exists in `C:\`, `C:\Users` or `C:\Users\Public`.
   - Deviation, forced by M1: the user's profile on this machine holds a `CLAUDE.md` and a `.claude`, and pytest's temp dir is under the profile. So on Windows the suite's child root is now a fresh `tempfile.mkdtemp(prefix="w-", dir=%ProgramData%)`, which any user may create a directory in, and it is removed at session end. Elsewhere it is pytest's basetemp, as before.
   - Writing under `%ProgramData%` is a write outside pytest's temp. The original brief ruled out only `C:\Users\Public`.
4. **M2.** `_user_names()` wraps `getpass.getuser()` (any exception) and `Path.home()` (`RuntimeError`, `KeyError`, `OSError`). A name that cannot be read becomes `""` and its clause is skipped. Test: both calls monkeypatched to raise, and the word clause still works.
5. **M3.** In `complete`, `prepare_sandbox` raising `UnsafeSandboxError` becomes `ProviderError("the child working directory is unsafe: ...")`. Test: a file sitting where the cwd directory should be gives a `ProviderError` matching "not a directory", and no child runs.
6. **M4.** `child_cwd_root()` returns `Path(configured).resolve()` for the env var. Test: after `chdir` to a temp dir, a relative `rel_root` comes back absolute and equal to `<tmp>/rel_root`.
7. **M6, docs.**
   - The runbook's Step 0 gains: the project-file problems; that the email scan covers every copied file; a "Resuming and the child root" paragraph (a session resumes only under the same `CLAUDE_BULLY_CHILD_ROOT` value, pre-Task-12 runs cannot `--resume`, and empty digest directories accumulate).
   - The runbook's 0b re-run says the old run cannot be resumed and the env var stays unset throughout.
   - `HANDOFF.md` gains a fix-round Progress bullet, and Next steps step 1 names the root rule.

### RED evidence (tests first, against the adedf7d code)

```
FAILED test_an_unknown_user_or_home_skips_that_clause            E   OSError: no login name
FAILED test_a_relative_root_is_made_absolute                      E   assert (False) where False = WindowsPath('rel_root').is_absolute()
FAILED test_a_planted_project_file_is_refused[leaf|root x CLAUDE.md|CLAUDE.local.md|.claude|.mcp.json]   E   assert (0 == 1) where 0 = len([])
FAILED test_an_unsafe_directory_is_a_provider_error              E   claude_bully.runner.sandbox.UnsafeSandboxError: ...<digest> is not a directory
FAILED test_check_9_names_a_planted_project_file                 E   assert result.exit_code == 1 (doctor exited 0, every check ok)
FAILED test_an_email_address_in_any_copied_file_blocks[reasoning|judge_cache|bully_meta]   (DID NOT RAISE ValueError)
15 failed, 3 passed
```

The 3 that passed:
- the I1 test, whose RED is the deletion check in item 2;
- the default-root check, a guard that must stay green;
- the reserved-or-binary pass test, a guard that must stay green.

(A first RED run also caught two test bugs, a wrong expected wording and planted-root names containing `claude`. I fixed both before the run above.)

### Gate (0 warnings)

- ruff format --check: 276 files formatted
- ruff check: clean
- mypy: clean (110 files)
- `pytest -q -W error`: 8454 passed, 5 skipped, 8 deselected (from 8437, +17), in 14:37
- `pytest -q -m slow`: 8 passed

No `%ProgramData%\w-*` directory was left after the session.

### Concerns

1. The Windows suite now creates and removes a `%ProgramData%\w-*` directory each session. If a session is killed, the directory stays behind; it is empty apart from digest directories.
2. The planted-file check reads the real filesystem on every call: about 4 stats per ancestor. Anyone with write access to an ancestor can therefore cause a refusal, by design, and the refusal is loud.
3. My earlier concern 5 was wrong (review M9): the provider resolves the path, so an 8.3 short profile name is caught.

## Fix round 2 (FIX_BASE 65dff39)

Commit: fa099e9 on top of 65dff39, author rankinbc1@gmail.com, Opus 5.5 trailer, not pushed. Inputs: the automated security finding on 65dff39 and `task-12-rereview-round1.md`; scope per `task-12-fix-round-2.md`.

### Per item

1. **Fail-closed project-file check.** `inspect_project_files(path) -> (found, uninspectable)` calls `os.lstat` on every name in the cwd and each ancestor.
   - A link counts as found whether or not its target exists, as with `os.path.lexists`.
   - `FileNotFoundError` and `NotADirectoryError` mean absent. Any other `OSError` puts the path in the uninspectable list.
   - Deviation from the letter, kept to the intent: the fix doc names `os.path.lexists`, but `lexists` itself returns False on any `OSError`, which is fail-open. So the check calls `lstat` directly.
   - `cwd_problems()` adds `cannot inspect <path> for a project file` for each uninspectable path, so `complete` raises a `ProviderError` naming it, and check 9 fails. This also covers the re-review's raw `PermissionError` on another user's `/tmp/w`. `planted_project_files` keeps its signature, returning the found list.
   - Tests:
     - A dangling symlink `CLAUDE.md` in the cwd is refused. It is skipped on this machine because Windows denies the symlink privilege, and runs on POSIX.
     - An ancestor's `.mcp.json` whose `lstat`/`stat` raise `PermissionError` is refused, and no child runs.
2. **Locked Windows root.**
   - `WindowsAcl` is the seam, with a module instance `WIN_ACL`:
     - `current_sid()` reads the SID from the process token via the Win32 API: no subprocess, no name, cached per process. I chose the token over `whoami`: Git's `whoami` shadows the Windows one on PATH, and several tests monkeypatch `subprocess.run` globally.
     - `lock(path, sid)` runs `icacls <root> /inheritance:r /grant:r *<sid>:(OI)(CI)F *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F`, with `icacls.exe` by its System32 path.
     - `owner_and_writers(path)` reads the owner SID and the DACL with `GetNamedSecurityInfoW` and `GetAce`, every function given explicit argtypes.
   - Writer accounting:
     - An allowed ACE with any write, delete, `WRITE_DAC`/`WRITE_OWNER` or generic-write/all bit counts as a writer, inherit-only ACEs included.
     - Deny ACEs are ignored.
     - An allowed ACE type this reader does not parse is reported as `unparsed`.
     - A null DACL is reported as Everyone (`S-1-1-0`).
     - CREATOR OWNER (`S-1-3-0`) is allowed, since it resolves to the creator.
   - `secure_windows_root(root, acl)`:
     - A root this call creates (`os.mkdir`) is link-checked, locked (an `icacls` exit other than 0 is a `ProviderError`), then read back.
     - An existing root must be a real directory, owned by this user, with no writer outside {this user, SYSTEM, Administrators, CREATOR OWNER}. Otherwise it is refused: `ProviderError: the child root <root> is not private: owned by <sid>, not this user` or `writable by <sid>`.
     - It returns `locked` or `ours`.
   - `complete` calls it on win32 before `prepare_sandbox`. POSIX is unchanged (`prepare_sandbox`: owner and 0o700).
   - `root_state(root)` (and `provider.root_state()`) gives check 9's last words, `root locked` or `root NOT private: <reason>`, and creates nothing.
   - Tests: the fake seam drives each branch (created and locked; existing and ours; existing and foreign, by owner and by writer; `icacls` failed). One Windows-only test really locks `tmp_path/w` and reads it back: owner is me; writers are exactly {me, SYSTEM, Administrators}; `icacls` shows no `(I)` and three `(OI)(CI)(F)`; a second call returns `ours`. The doctor pass test now asserts check 9 ends `; cwd neutral; root locked`.
   - Suite: on Windows the session root is now `w` inside the `%ProgramData%\w-*` temp directory. The conftest creates and locks it with the product's own `secure_windows_root`, so every session runs the real lock, and roots that tests make inside it inherit the lock.
3. **Relative root in the child's environment.** I chose the resolved absolute value: `child_env` sets `CLAUDE_BULLY_CHILD_ROOT` to `str(child_cwd_root())` whenever the variable is set, so a nested responder whose process cwd is the target's lands under the same root. The variable is left unset when it was unset. Test: after `chdir`, both `serving_tools` values carry `<tmp>/rel_root` resolved, and a deleted variable stays absent.
4. **Stale text.** The "invented login" wording is gone from `HANDOFF.md`'s Task 12 bullet and from the spec's Task 12 bullet. Both now describe the `%ProgramData%` locked session root and real names.
5. **Docs.**
   - The runbook's Step 0 gains "The root itself": the Windows ACL lock, the refusal of a root someone else made or a root made before the lock, POSIX 0o700, check 9's root words, and the accepted check-then-spawn window under `--setting-sources ""`.
   - `HANDOFF.md` gains a fix-round-2 Progress bullet.
   - The spec's Task 12 bullet records rounds 1 and 2.

### RED evidence (tests first, against the 65dff39 code)

```
test_an_ancestor_that_cannot_be_inspected_is_refused    E   PermissionError: [Errno 13] Permission denied: '...\.mcp.json'  (raw, not a ProviderError)
test_a_relative_root_reaches_the_child_resolved         E   AssertionError: assert 'rel_root' == '<tmp>\rel_root'
test_a_dangling_symlink_counts_as_planted               SKIPPED (no symlink privilege on this Windows account)
the ACL tests and the module                            E   ImportError: cannot import name 'ADMINISTRATORS_SID' / 'SYSTEM_SID' / 'WIN_ACL' / 'secure_windows_root'
test_doctor_live_passes_every_check_on_the_fake         asserted '; cwd neutral; root locked' (fails until check 9 names the root)
```

To get behavioural RED for items 1 and 3 despite the import error, I ran their tests from a temporary copy without the new imports, then deleted the copy. The first pass of the GREEN run caught one real bug: `whoami` through `subprocess.run` collided with tests that fake `subprocess.run`, which led to the token-based SID. A second bug was a 64-bit handle passed without argtypes (`OverflowError`); every Win32 function is now typed.

### Gate (0 warnings)

- ruff format --check: clean
- ruff check: clean
- mypy: clean (110 files)
- `pytest -q -W error`: 8462 passed, 6 skipped, 8 deselected, in 14:20. That is 8 more passing than 8454; the extra skip is the dangling-symlink test, since this account lacks the symlink privilege.
- `pytest -q -m slow`: 8 passed

No `w-*` directory was left under `%ProgramData%`.

### Concerns

1. A `C:\Users\Public\w` made before this round (with inherited Public ACL) is refused, not repaired; the runbook says to remove it. None exists on this machine.
2. The ACL reader reads only types 0 and 9 among allowed ACEs; object ACEs (5, 11) report `unparsed` and refuse. That is safe, but would be a loud refusal on a filesystem that uses them.
3. A test or user that points `CLAUDE_BULLY_CHILD_ROOT` at a new directory under an inherited, user-writable parent gets it locked on creation. A directory that already exists there is refused if any other principal may write to it.

## Fix round 3 (FIX_BASE fa099e9)

Commit: 4508a35 on top of fa099e9, author rankinbc1@gmail.com, Opus 5.5 trailer, not pushed, no subagents. Scope: `task-12-fix-round-3.md` (the automated security finding on fa099e9; I1, I2, M2, M3, M4, M5 of `task-12-rereview-round2.md`). The last round on this axis.

### Per item

1. **The creation window (security MEDIUM).**
   - `secure_windows_root`: a root this call created is listed after the lock (`os.scandir`). Anything in it is a refusal: `the child root <root> is not private: it is not empty after the lock (something was made in it before the lock); remove it and retry`. A listing that fails is a refusal too.
   - `secure_windows_cwd(cwd, acl)` (new) gives the cell cwd the root's check: a real directory (`verify_private_dir`), owned by this user (or by Administrators under an elevated token, item 5), with no write-capable ACE for any other principal. `_root_acl_problems` became `_acl_problems(path, acl)`, which serves both.
   - `complete` calls it on win32 after `prepare_sandbox` and before the child starts. Every path goes through `complete`, the nested responder's included: the MCP server builds it with `build_provider`, so it is a `ClaudeCodeProvider` in the server child and runs the same check. That holds by construction; the seam cannot be patched across the process boundary, so no test drives it there.
   - No `CreateDirectoryW` rewrite, as ruled. Found on the way: Python 3.12.4 and later make `os.mkdir(path, 0o700)` on Windows with a protected DACL (SYSTEM, Administrators, OWNER RIGHTS; owner this user). With item 3's `mode=0o700`, the root is therefore private from creation on this interpreter (3.12.13). The emptiness check stays as the guard for older interpreters.
   - Deviation, forced by that: OWNER RIGHTS (`S-1-3-4`) is now an allowed writer. It grants the object's owner and no one else, and the owner is checked on its own, so it widens nothing. Without it, every cwd `prepare_sandbox` makes would be refused (the first GREEN run refused every child with `writable by S-1-3-4`). The round-2 probe row "locked + OWNER RIGHTS full: refused" now passes when the owner is this user, and is still refused under any other owner (`test_owner_rights_count_as_the_owner`).
   - Tests, through the seam (`_FakeAcl` gains `per_path`, `on_lock` and `elevated`):
     - a directory made inside `lock` (between `mkdir` and lock) is refused;
     - a foreign-owned cwd and an extra-writer cwd are refused, and a private one passes;
     - on Windows, `complete` with `WIN_ACL` patched (root ours, cwd foreign) refuses with no child started;
     - the real-lock test also makes a cwd with `prepare_sandbox` and passes it through `secure_windows_cwd` with the real `WIN_ACL`.
2. **I1, mypy on Linux.**
   - `_sid_text`, `_token_information`, `_process_user_sid`, `_token_elevated` and `_read_owner_and_writers` each open with `if sys.platform != "win32": raise ProviderError(...)`, as `_win32` already did, so mypy narrows the rest away on Linux.
   - `uv run mypy --platform linux claude_bully`: 2 errors at fa099e9 (`Module has no attribute "get_last_error"`, lines 329 and 335), none now. The default run is clean too. Both runs are in this round's gate and in HANDOFF's setup gate.
3. **I2, POSIX.**
   - `secure_windows_root` makes the root with `os.mkdir(root, 0o700)` and on POSIX then `chmod`s it to 0o700. `prepare_sandbox` (`_private_dir`) does the same for every directory it makes, the cwd included.
   - The "existing root" tests make their root the same way (`_private_mkdir`). New POSIX-only tests run under umask 022 and umask 200; without the chmod, umask 200 leaves mode 577.
   - **WSL: available** (Ubuntu 24.04, umask 0022, no network).
     - Setup: Linux `uv` 0.11.8 from its release tarball, downloaded on Windows. That `uv` made a venv offline, over Linux wheels that Windows `uv` installed (`uv pip install --python-platform x86_64-manylinux_2_28 --target`, from `uv export` of the lock). The working tree was copied under `/tmp`, into a folder named `ClaudeBully`, because two tests assume the repo path holds `claude`.
     - Run: `uv run --offline --no-sync python -m pytest -q -W error` on the three changed test files (`test_providers_claude_code.py`, `test_doctor_live.py`, `test_sandbox.py`).
     - Result: 165 passed, 5 skipped. The skips are the two Windows-only ACL tests and three NTFS junction tests.
     - With only the I2 change reverted in that copy: 17 failed, 148 passed, among them the five tests the re-review named (`... is open to other users (mode 755)`).
4. **M4, dead fail-open code: deleted.** `planted_project_files` is gone. `inspect_project_files` (`os.lstat`, fail-closed) is the only project-file check, called by `cwd_problems`, whose docstring now names it.
5. **M2, elevated token.**
   - The seam gains `is_elevated()` (`GetTokenInformation(TokenElevation)`, cached). `_token_information` is now shared with the SID read.
   - `_acl_problems` accepts Administrators as the owner only when `is_elevated()` is True.
   - Tests through the seam: a root and a cwd owned by Administrators are refused unelevated and accepted elevated, and a root an elevated process creates and locks is `locked`. The real-lock test asserts the owner is this user, or Administrators when the token is elevated (here it is not).
6. **M3, messages.**
   - `_acl_call(what, call)` wraps every seam call. Any exception other than `ProviderError` becomes `ProviderError("the ACL call <what> failed (<type>)")`, never the exception's text or path. `_verify_private` treats `verify_private_dir` the same way: an `OSError` is named by its type only.
   - `WindowsAcl.lock` returns the exit code alone and sends `icacls` output to `DEVNULL`. With no text mode there is nothing to decode, and the output cannot reach a message: the refusal reads `icacls failed (exit N)`.
   - `_redacted_text` replaces with `<user>` any path segment equal to the login or the home folder's name (case-insensitive; the segment follows a separator and ends at a separator, a quote, a space, punctuation or the end of the text). It covers the sandbox check's text inside root and cwd messages, `root_state`'s detail, and `complete`'s unsafe-cwd message. Paths the module names itself still go through `_redacted`.
   - Tests:
     - each of the four seam calls raising `FileNotFoundError` (with a path holding an invented login) or `UnicodeDecodeError` gives a `ProviderError` that names the type and quotes neither the text nor the path;
     - a real `WindowsAcl.lock` over a faked `subprocess.run` that echoes a SID gives `exit 1332`, with neither the echoed text nor the SID in the message;
     - with `LOGNAME=inv-login` and a home folder named `inv-login.CORP`, a file where the root should be, under either name, shows as `<user>` in the refusal and in `root_state`; so does a foreign root under the login.
7. **M5, `root_state`'s failing branch.**
   - `root_state` now tells a missing root (`it does not exist yet`) from one that is not a directory. It used `is_dir()`, so a file read as missing.
   - Tests: a missing root; a file; a root another principal may write to (the patched `WIN_ACL` on Windows, mode 755 on POSIX); then the same root made private again, which reads `root locked`.
   - Doctor: `test_check_9_fails_on_a_root_that_is_not_private` puts a file where the root should be. Doctor exits 1, check 9 is not ok and ends `cwd neutral; root NOT private: ... not a directory ...`, and no model call ran.

Also changed:
- `tests/conftest.py`: a session root that `secure_windows_root` refuses now removes its `%ProgramData%\w-*` directory. One refused setup during this round had left one behind; it is removed, and none is left now.
- Docs:
  - the runbook's "The root itself" gains this round's rules: emptiness after the lock, the cwd check, the elevated owner, no `icacls` text, `<user>`;
  - `HANDOFF.md` gains a fix-round-3 Progress bullet, the Linux mypy run in the setup gate, and the new counts;
  - the spec's Task 12 bullet records round 3.
- Deferred, as ruled and recorded in the ledger: the runbook's wording about the ancestors above the root, and the first-call scan order.

### RED evidence (tests first, against the fa099e9 code; a no-op `secure_windows_cwd` stub let the module import)

```
FAILED test_a_new_windows_root_is_created_and_locked                 TypeError: cannot unpack non-iterable int object (the seam's lock returns the exit code only)
FAILED test_the_fail_open_project_file_helper_is_gone                assert not True (hasattr(claude_code, 'planted_project_files'))
FAILED test_a_failed_icacls_is_a_refusal                             TypeError: cannot unpack non-iterable int object
FAILED test_a_child_made_between_mkdir_and_the_lock_is_refused       TypeError (the old seam shape)
FAILED test_a_foreign_or_shared_cwd_is_refused[owner|writer]         Failed: DID NOT RAISE ProviderError
FAILED test_complete_refuses_a_foreign_cwd_before_any_child_starts   Failed: DID NOT RAISE ProviderError
FAILED test_administrators_own_a_root_only_under_an_elevated_token[False|True]   ProviderError: ... owned by S-1-5-32-544, not this user
FAILED test_a_raw_failure_of_the_acl_seam_is_a_provider_error (x8)   raw FileNotFoundError / UnicodeDecodeError, or TypeError
FAILED test_icacls_output_never_reaches_a_message                    'No mapping' is contained in '... icacls failed (exit 1332): No mapping between account names ...'
FAILED test_a_root_message_redacts_the_login_and_the_home_folder     '... is not private: <tmp>\Users\inv-login\w is not a directory ...'
FAILED test_the_root_state_names_each_failing_branch                 'root NOT private: it does not exist yet' for a file
FAILED test_the_real_lock_leaves_only_the_user_system_and_administrators   AttributeError: 'WindowsAcl' object has no attribute 'is_elevated'
FAILED test_check_9_fails_on_a_root_that_is_not_private              "... cwd neutral; root NOT private: it does not exist yet"
22 failed (the POSIX-only umask tests skip on Windows)
```

- I1: `mypy --platform linux` on the fa099e9 module gives the 2 errors above; with the guards, none.
- I2, under WSL with only the I2 change reverted: 17 failed, including `test_a_new_root_is_mode_700_whatever_the_umask` at umask 022 (mode 755) and 200 (mode 577), and `test_the_root_and_cell_dir_are_mode_700_whatever_the_umask`. With the change: 165 passed, 5 skipped.
- OWNER RIGHTS: `test_owner_rights_count_as_the_owner` was written after the first GREEN run. Its RED was that run, which refused every Windows child with `the child root ... is not private: writable by S-1-3-4`.

### Gate (0 warnings)

- `uv run ruff format --check .`: 276 files already formatted
- `uv run ruff check .`: all checks passed
- `uv run mypy claude_bully`: no issues in 110 source files
- `uv run mypy --platform linux claude_bully`: no issues in 110 source files (2 errors at fa099e9)
- `uv run pytest -q -W error`: 8483 passed, 9 skipped, 8 deselected, in 13:41. Against 8462 and 6 at fa099e9: +21 passing, plus 3 POSIX-only umask tests skipped on Windows.
- `uv run pytest -q -m slow`: 8 passed
- After the `conftest.py` cleanup change, the fast suite was run again before the commit: 8483 passed, 9 skipped, 8 deselected, in 14:05; no `%ProgramData%\w-*` left
- WSL (Ubuntu 24.04), the three changed test files: 165 passed, 5 skipped

### Concerns

1. OWNER RIGHTS is now accepted as a writer (item 1's deviation). That is safe by its meaning: they are the owner's rights, and the owner is checked first. It still reverses a row the round-2 reviewer probed.
2. The nested responder's cwd check is pinned by construction (it runs the same `complete`), not by a test inside the MCP server child.
3. A root refused as "not empty after the lock" stays on disk, and the next call uses it as `ours`. Whatever was planted in it matters only if it is the cell cwd's own 12-hex digest directory, and the cwd check refuses that one when it is foreign-owned or writable. Nothing else in the root is an ancestor of a cwd. The runbook says to remove such a root.
4. The WSL run used Linux wheels installed by Windows `uv` (WSL has no network here), not a `uv sync` inside WSL. The versions are the lock's. CI on `ubuntu-latest` is the real check.
5. The fa099e9 ruling records the remaining local multi-user residual in the README draft's Limitations. That line is not written: `.superpowers/drafts/` belongs to another agent this session, and its `docs/handoff/drafts/` snapshot must stay identical to it.
