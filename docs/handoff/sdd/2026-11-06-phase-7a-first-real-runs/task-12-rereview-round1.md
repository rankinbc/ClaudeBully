# Task 12 fix round 1, scoped re-review (adedf7d..65dff39)

Reviewer: read-only on tracked files (`git status` clean before and after). I ran
`tests/test_providers_claude_code.py`, `tests/test_doctor_live.py`, `tests/test_wait_and_promote.py`
(149 passed, `-W error`) and `tests/test_runner_env.py`, `tests/test_mcp_server.py`,
`tests/test_sandbox.py`, `tests/test_tool_loop.py` (170 passed, 5 skipped, `-W error`; these run the
MCP server and the nested responder under the new suite root). Not the full gate. Mutation checks ran
on a `git archive 65dff39` copy in the session scratchpad, never on the tree; the probes are there too.

## Verdict

All seven items ADDRESSED. New Critical: 0. New Important: 0. New Minor: 7. Ready to carry on.

## Per item

1. **Security (email scan over every copied file, closes M8): ADDRESSED.**
   - `copied_files(store)` is the one list: `promote` scans it (`scan_copied_emails`) and then copies
     it (`shutil.copy2` over the same list), so the scanned set and the copied set cannot drift. The
     set equals the old one: `COPIED_FILES`, each cell's `CELL_FILE_GLOBS`, every file under
     `COPIED_DIRS`.
   - The raise comes after the stream scan and before `dest.exists()`/`rmtree`/`mkdir`, so a block
     copies nothing and, with `force`, leaves an existing promotion in place.
   - A hit reads `<run-relative file> line <n>: email address (domain redacted)`. The address is
     never in a message: `scan_copied_emails` returns only that string, the `ValueError` holds the
     first five of them, and the CLI does not catch `ValueError` (Typer's traceback locals are
     `report`, `in_files`, `store`, `dest`; the scan's own frame, with `raw` and `line`, has already
     returned).
   - Binary: skipped by suffix (`BINARY_SUFFIXES`) or any NUL byte, before any decode; text is
     decoded `utf-8, errors="replace"`, so no crash on bad bytes.
   - Tests present and green: reasoning, judge cache, bully_meta each block, with the stream scan
     alone passing them, the file and line named, no `zzq`/`pennet` in the error, nothing copied;
     reserved addresses in copied files pass; a png whose bytes spell an address is copied unread.
   - Real data: the two rung-0 snapshots under `docs/handoff/runs` scan clean (31 and 24 files, 0 hits,
     0.01 s).
2. **I1: ADDRESSED.** Mutation on the copy: deleting the home-folder clause fails
   `test_the_login_and_the_home_folder_name_are_problems_unquoted` with `('inv-login.CORP', [])`;
   deleting the login clause fails it too. The test pins the exact line per clause, that neither line
   repeats the name, and that the machine's real names (`REAL_USER_NAMES`) are problems.
3. **M1 (targeted project-file check): ADDRESSED.**
   - `planted_project_files(cwd.resolve())` covers the cwd and every ancestor for `CLAUDE.md`,
     `CLAUDE.local.md`, `.claude`, `.mcp.json`; `cwd_problems()` appends one line per find;
     `complete` raises `ProviderError` naming the path; check 9 fails with `cwd NOT neutral:
     ...CLAUDE.md...` (`test_check_9_names_a_planted_project_file`).
   - Mutation: restricting the walk to the leaf fails 4 of the 8 parametrised cases (the `root` ones).
   - Default root on this machine: `ClaudeCodeProvider` with the env var deleted gives
     `cwd = C:\Users\Public\w\<digest>`, `cwd_problems() == []` (I ran it, and
     `test_the_default_root_has_no_project_file_above_it` passes). None of the four names exists in
     `C:\`, `C:\Users`, `C:\Users\Public`, `C:\ProgramData`; `C:\Users\Public\w` does not exist, so the
     tests created nothing there. The owner's `~/.claude` and `~/CLAUDE.md` are not ancestors.
   - Real CLI 2.1.319 left every rung-0 `cwd` directory empty (8 of 8 under `docs/handoff/runs`), so a
     resumed call is not refused by a `.claude` the CLI wrote itself.
4. **M2: ADDRESSED.** `_user_names()` catches `Exception` for `getpass.getuser()` and
   `RuntimeError/KeyError/OSError` for `Path.home()`; a name it cannot read becomes `""` and its clause
   is skipped. `_redacted` goes through the same function. Mutation: removing the home `except` fails
   `test_an_unknown_user_or_home_skips_that_clause`.
5. **M3: ADDRESSED for the sandbox error.** `UnsafeSandboxError` from `prepare_sandbox` becomes
   `ProviderError("the child working directory is unsafe: ...")`; the test (a file where the digest
   directory should be) matches "not a directory" and no child ran. See Minor 1 for a path that still
   escapes raw.
6. **M4: ADDRESSED.** `child_cwd_root()` returns `Path(configured).resolve()`; the test chdirs and
   gets `<tmp>/rel_root`. Mutation: dropping `.resolve()` fails it. See Minor 4 for the children.
7. **M6 (docs): ADDRESSED.** The runbook's Step 0 gains "Resuming and the child root" (same
   `CLAUDE_BULLY_CHILD_ROOT` value to resume; a pre-Task-12 run cannot `--resume` its sessions, it is
   replayed; one empty digest directory per provider state dir accumulates), and the 0b re-run now
   says the old run cannot be resumed and the variable stays unset for the run, rehearsal resume and
   `analyze`. HANDOFF's Next step 1 says the same (unset throughout, why, and that the rung-0 runs
   cannot be resumed) and the new Progress bullet states both claims as M6.

## Checks you asked for

**Email scan.** No address printed (above). Binary skipped. A block copies nothing. Run time: 5 MB of
ordinary lines in 0.07 s; the rung-0 snapshots in 0.01 s; a 200 MB run would be a few seconds. It is
not pathological on realistic text. It is quadratic on one unbroken run of `[A-Za-z0-9._%+-]` (the
pattern's local part): 20 KB 0.3 s, 50 KB 1.8 s, 500 KB minutes. That pattern was already run over
chat text; the round applies it to every line of every copied file. See Minor 5.

**M1 ancestors.** The default root passes here (above). On a normal Windows machine the ancestors are
`C:\Users\Public\w`, `C:\Users\Public`, `C:\Users`, `C:\`, none of which hold those names unless
someone put them there; on POSIX `/tmp/w`, `/tmp`, `/` (macOS: `/private/tmp`). Where is the check
run: `subprocess.run` appears once in `claude_code.py`, inside `complete`, after `cwd_problems()`
(the other two `subprocess.run` calls in the package are `claude --version` and a git probe, neither
a model call). The MCP server's nested responder is built by `build_provider` into a
`ClaudeCodeProvider` and calls the same `complete`, so it is refused the same way. `_write_mcp_config`
runs before the check but writes into the MCP state dir, not the cwd.

**`%ProgramData%` suite root.** `_session_child_root` makes `%ProgramData%\w-*` with `mkdtemp` and the
session fixture removes it in a `finally`; after my two test runs `C:\ProgramData` held no `w-*` and
`C:\Users\Public` no `w`. Every other test writes under tmp or under that root (the planted-file tests
make `p_*` and `planted_doctor` inside it). The default-root test only reads. No product code mentions
`ProgramData` (grep of `claude_bully/`). The R3 login and home clauses are exercised by the I1 test
(mutation-verified both ways).

**No real name, login or email.** The added lines of the diff hold none (grep for the login, the
name, any `@host.tld`, the commit author: only `@pytest.mark` decorators match). Test names are
`inv-login`, `inv-login.CORP`; the real ones come from `REAL_USER_NAMES` at run time. Commit trailer is
Opus 5.5 as the brief asked.

## Minor (7)

1. **A raw `PermissionError` can now precede the wrapped sandbox error (POSIX shared `/tmp/w`).**
   `planted_project_files` uses `Path.exists()`, which on Python 3.12 re-raises EACCES (confirmed
   against `pathlib.Path.exists` in this venv). Another user's mode-700 `/tmp/w` makes the stat of
   `/tmp/w/<digest>/CLAUDE.md` fail, so `cwd_problems()` raises `PermissionError` out of `complete`
   before `prepare_sandbox` can say "belongs to uid N" as a `ProviderError`. This is the scenario M3
   named. A 755 directory of another user still reaches the wrapped path. Fix: catch `OSError` in
   `planted_project_files` and report "cannot inspect <path>" as a problem. Doctor already reports a
   crashed check as failed, so only `complete` and the runner see the raw exception.
2. **`_redacted` has no test.** Returning the raw path leaves every test green, and it is what keeps
   the login out of a doctor report (committed under `docs/handoff/`). It works (I checked:
   `C:\Users\<user>\CLAUDE.md`); only exact-segment equality is redacted, so a name inside a longer
   segment (`pytest-of-<login>`) would show. Add a test with a planted file under a login-named
   segment.
3. **The two binary guards are pinned only together.** The test's chart has both a `.png` suffix and a
   NUL byte; dropping either guard leaves the test green, dropping both fails it (checked). A NUL also
   means a UTF-16 text file would go unscanned; the harness writes UTF-8 only, so this is theoretical.
4. **A relative `CLAUDE_BULLY_CHILD_ROOT` is only made absolute in the harness.** `child_env` still
   passes the relative string, so a nested responder (MCP server, cwd = the target's cwd) would resolve
   it against that directory and work in `<target cwd>/<root>/<digest>`. It still works and is
   neutral; not verified against the real CLI's MCP environment. Pin it by writing the resolved value
   into `child_env`.
5. **Email regex is quadratic on an unbroken local-part run** (numbers above). A `"@" in line` guard
   makes the common case linear. Realistic runs are fine.
6. **Stale docs.** HANDOFF.md's Task 12 bullet (the paragraph above the new fix-round bullet) and the
   spec's "As planned" Task 12 bullet still say the suite runs under an invented login and home folder.
   Round 1 dropped that; HANDOFF's new bullet corrects it, the spec does not.
7. **Two environment-dependent tests.** The POSIX suite root is pytest's basetemp with no escape (a
   machine whose `TMPDIR` sits under a folder holding `.claude` or `CLAUDE.md` would see every provider
   test refused; the Windows `%ProgramData%` workaround does not generalise). And
   `test_the_default_root_has_no_project_file_above_it` reads the real filesystem, so a stray `.claude`
   in `C:\Users\Public`, `/tmp` or `/` fails it (with the right message). Both fail loudly; note it in
   HANDOFF for the other machine.

Deferred and still open from the first review: M5 (run-id substring), M7 (non-verbatim email forms),
M9 (8.3 note, and a home folder named `tmp` refusing `/tmp/w`). The implementer's concerns (a killed
session leaves an empty `w-*`; a writer to an ancestor can force a loud refusal) are accurate and need
no change.

## Probes (session scratchpad, git-ignored, none touches tracked files)

`p/probe_time.py` (regex timings), `p/probe_real.py` (scan of the rung-0 snapshots), `p/mut.py` and the
`copy/` mutation tree.
