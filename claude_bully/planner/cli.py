"""The ``plan`` sub-app (Phase 5 Task 9; spec section 11, D-cli): a research question to a
validated run bundle, mounted by ``claude_bully/cli.py`` as ``claude-bully plan``.

Five commands: ``new``, ``continue``, ``review``, ``validate`` and ``diff``. The three that may
call a model (``new``, ``continue``, ``review``) run the Director through
``runner/wait.wait_on_rate_limit``, as ``run`` and ``analyze`` do: with ``--wait-on-rate-limit``
the wait happens in the process, without it the command exits ``RATE_LIMIT_EXIT_CODE`` and the
same command resumes. Each of the four plan commands prints one line per dry-run cell
(``cell_line``) and ``status <status>``, and exits 0 when the plan is ``runnable``, or when
``new`` stopped after stage 1 as asked (D-exit); 1 otherwise. A damaged harness record
(``runner/store.DamagedRecordError``, naming the file and the line or the field) or a refusal
(``DirectorError``) is printed as ``error: <message>`` and exits 1, never as a traceback; every
other exception keeps its traceback (Task 9 fix round 1, review I1). A missing bundle or request
file is a usage error (exit 2).

The Director is built with three module-level seams, read at call time, which tests
monkeypatch: ``PlanProviders`` (the ``ProviderFactory``, ``build_provider`` in production),
``WORLDS_DIR`` (the shipped worlds a reused world is copied from) and ``PlanCheckpoint`` (the
kill seam, None in production; review Minor 1)."""

import difflib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Final

import typer

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments import world as world_module
from claude_bully.environments.world import hash_tree
from claude_bully.paths import DEFAULT_PLANS_ROOT, shown_default, shown_paths
from claude_bully.planner.bundle import PLAN_FILE, Bundle, hashed_paths
from claude_bully.planner.director import (
    Checkpoint,
    Director,
    DirectorError,
    held_by_open_blocks,
)
from claude_bully.planner.records import DryRunCell, PlanRecord
from claude_bully.planner.request import PlanRequest, load_plan_request, parse_budget
from claude_bully.providers.base import ProviderFactory, build_provider
from claude_bully.runner.runner import RateLimitExit
from claude_bully.runner.store import DamagedRecordError
from claude_bully.runner.wait import RATE_LIMIT_EXIT_CODE, WaitMinutes
from claude_bully.runner.wait import wait_on_rate_limit as wait_on_rate_limit_

PlanProviders: ProviderFactory = build_provider
WORLDS_DIR: Path = world_module.WORLDS_DIR
PlanCheckpoint: Checkpoint | None = None

plan_app = typer.Typer(
    help="The Director: a research question to a validated run bundle.", no_args_is_help=True
)

BundleDir = Annotated[Path, typer.Argument(help="The plan's directory, plans/<slug>.")]
# the default as its expression: the absolute path would print the login's home folder (review
# m4; the final review's M1: the one helper every command's root option shows its default by)
PLANS_ROOT_SHOWN: Final = shown_default(DEFAULT_PLANS_ROOT)
_NO_FILE: Final = "/dev/null"
# the statuses of a plan between stage 1 and stage 5 that neither failed nor was held: `plan
# continue` is the way on
_MID_PLAN: Final = frozenset({"authored", "reviewed", "revised"})


# ------------------------------------------------------------------------------ the request


def _listed(text: str, flag: str) -> list[str]:
    parts = [part.strip() for part in text.split(",")]
    if not all(parts):
        raise ValueError(f"{flag} {text!r}: an empty entry")
    return parts


def _targets(text: str) -> list[RoleConfig]:
    """``--targets``: each entry ``provider:model``, or a bare model on ``claude_code``."""
    roles: list[RoleConfig] = []
    for entry in _listed(text, "--targets"):
        provider, sep, model = entry.partition(":")
        if not sep:
            provider, model = ProviderKind.claude_code.value, entry
        try:
            kind = ProviderKind(provider)
        except ValueError:
            known = ", ".join(k.value for k in ProviderKind)
            raise ValueError(
                f"--targets {entry!r}: {provider!r} is no provider ({known})"
            ) from None
        if not model:
            raise ValueError(f"--targets {entry!r}: no model after the provider")
        roles.append(RoleConfig(provider=kind, model=model))
    return roles


def _numbers(text: str, flag: str) -> list[int]:
    try:
        return [int(part) for part in _listed(text, flag)]
    except ValueError:
        raise ValueError(f"{flag} {text!r}: comma-separated whole numbers") from None


def request_from_flags(
    question: str | None,
    *,
    request: Path | None,
    targets: str | None,
    budget: str | None,
    scope: str | None,
    hypotheses: str | None,
    constraint: Sequence[str],
    slug: str | None,
    world: str | None,
    base_world: str | None,
    seed: int | None,
) -> PlanRequest:
    """The ``PlanRequest`` of ``plan new``'s flags: a ``--request`` file is the base, and each
    flag given replaces its field (``constraint`` when it holds any); ``--targets`` entries are
    ``provider:model`` or a bare model on ``claude_code``; ``--budget`` is
    ``max_turns,n_per_cell,max_cells[,max_calls]``; ``--scope`` and ``--hypotheses`` are comma
    lists. Raises ``ValueError`` naming the flag or the field."""
    data: dict[str, Any] = {} if request is None else load_plan_request(request).model_dump()
    if question is not None:
        data["question"] = question
    if "question" not in data:
        raise ValueError("plan new needs a question: the argument, or question: in --request")
    if targets is not None:
        data["target_models"] = _targets(targets)
    if budget is not None:
        data["budget"] = parse_budget(budget)
    if scope is not None:
        data["scope"] = _listed(scope, "--scope")
    if hypotheses is not None:
        data["hypotheses"] = _numbers(hypotheses, "--hypotheses")
    if constraint:
        data["constraints"] = list(constraint)
    for field, value in (("slug", slug), ("world", world), ("base_world", base_world)):
        if value is not None:
            data[field] = value
    if seed is not None:
        data["seed"] = seed
    return PlanRequest.model_validate(data)


# ------------------------------------------------------------------------------ the report


def cell_line(cell: DryRunCell) -> str:
    """One dry-run cell as every plan command prints it (spec section 11):
    ``<cell_id> <status> top_rung=<top_rung> rungs=[<a>,<b>] calls>=<n>``."""
    rungs = ",".join(cell.rungs_fired)
    return (
        f"{cell.cell_id} {cell.status.value} top_rung={cell.top_rung} rungs=[{rungs}] "
        f"calls>={cell.estimated_calls}"
    )


def _open_blocks_line(blocks: int) -> str:
    return f"failed: {blocks} open block(s); edit the bundle and run plan review"


def _report(record: PlanRecord) -> None:
    """The cell lines; the failed stage's error, the open blocks and the failing lint results,
    when there are any; then the status."""
    for cell in record.dry_run:
        typer.echo(cell_line(cell))
    failed = next((s for s in reversed(record.stages) if s.status == "failed"), None)
    if failed is not None:
        typer.echo(f"failed: stage {failed.stage}: {failed.error}")
    if blocks := held_by_open_blocks(record):
        typer.echo(_open_blocks_line(blocks))
    if record.status == "validated":
        for lint in (r for r in record.lint_results if r.severity == "fail"):
            typer.echo(f"fail {lint.lint_id} {lint.doc_id}: {lint.message}")
    typer.echo(f"status {record.status}")


def _finish(record: PlanRecord) -> None:
    """The report, then exit 0 for a runnable plan and 1 for any other."""
    _report(record)
    raise typer.Exit(code=0 if record.status == "runnable" else 1)


# ------------------------------------------------------------------------------ the driving


def _director(director: Callable[..., Director], *args: Any, **kw: Any) -> Director:
    """``Director.new`` or ``Director.open`` with the module's three seams, read now."""
    return director(
        *args,
        **kw,
        provider_factory=PlanProviders,
        worlds_dir=WORLDS_DIR,
        checkpoint=PlanCheckpoint,
        say=typer.echo,
    )


def _a_plan(root: Path, param_hint: str = "BUNDLE") -> Path:
    """``root``, when it holds a ``plan.json``; else a usage error naming it (exit 2)."""
    if not (root / PLAN_FILE).is_file():
        raise typer.BadParameter(f"{root} holds no {PLAN_FILE}", param_hint=param_hint)
    return root


def _opened(root: Path) -> Director:
    return _director(Director.open, _a_plan(root))


@contextmanager
def _plan_errors() -> Iterator[None]:
    """A refusal or a damaged record, printed with no traceback; exit 1. Nothing else is
    caught: a ``ValueError`` of a defect keeps its traceback (review I1)."""
    try:
        yield
    except (DirectorError, DamagedRecordError) as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from None


def _drive(action: Callable[[], PlanRecord], wait_on_rate_limit: float | None) -> PlanRecord:
    """``action`` through the rate-limit wait; a pause the wait does not cover exits
    ``RATE_LIMIT_EXIT_CODE`` with ``run``'s message (C37)."""
    try:
        return wait_on_rate_limit_(action, wait_on_rate_limit, say=typer.echo)
    except RateLimitExit as exc:
        wait = (
            f"about {int(exc.retry_after_s)} seconds" if exc.retry_after_s else "the stated window"
        )
        typer.echo(f"Rate limited: {exc}. Progress is saved; retry the same command after {wait}.")
        raise typer.Exit(code=RATE_LIMIT_EXIT_CODE) from None


def _refuse_open_blocks(record: PlanRecord) -> None:
    """D-revise-error: a plan held at stage 4 by open blocks goes no further without a call,
    whatever its status (R-validate-status)."""
    if blocks := held_by_open_blocks(record):
        typer.echo(_open_blocks_line(blocks))
        typer.echo(f"status {record.status}")
        raise typer.Exit(code=1)


def _stopped(director: Director) -> None:
    """``new`` stopped after stage 1, as asked (D-exit): the plan, and how to go on."""
    root = director.bundle.root
    typer.echo(director.bundle.read_file("plan.md").rstrip("\n"))
    typer.echo(
        f"stopped after stage 1: review {(root / 'plan.md').as_posix()}, then run plan continue "
        f"{root.as_posix()}"
    )
    typer.echo(
        "plan.md is yours to edit now and stage 2 adopts the edit; once plan continue opens a "
        "stage, an edit to a file of that stage is written over by the stage."
    )
    typer.echo(f"status {director.record.status}")


# ------------------------------------------------------------------------------ the commands


@plan_app.command("new")
def new(
    question: Annotated[
        str | None, typer.Argument(help="The research question (or question: in --request).")
    ] = None,
    targets: Annotated[
        str | None, typer.Option(help="Comma list of provider:model, or a bare claude_code model.")
    ] = None,
    budget: Annotated[
        str | None, typer.Option(help="max_turns,n_per_cell,max_cells[,max_calls].")
    ] = None,
    scope: Annotated[str | None, typer.Option(help="Comma list of the spec areas shown.")] = None,
    hypotheses: Annotated[
        str | None, typer.Option(help="Comma list of data/hypotheses.yaml ids.")
    ] = None,
    constraint: Annotated[
        list[str] | None, typer.Option(help="A free-text constraint. Repeatable.")
    ] = None,
    request: Annotated[
        Path | None,
        typer.Option(
            help="A request YAML file; each flag given overrides it.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    slug: Annotated[str | None, typer.Option(help="The plan's directory name.")] = None,
    world: Annotated[str | None, typer.Option(help="reuse or fresh.")] = None,
    base_world: Annotated[str | None, typer.Option(help="The shipped world to reuse.")] = None,
    seed: Annotated[int | None, typer.Option(help="The config's seed.")] = None,
    no_confirm: Annotated[
        bool, typer.Option("--no-confirm", help="Go on past stage 1 without stopping.")
    ] = False,
    plans_root: Annotated[
        Path, typer.Option(help="Where plans are written.", show_default=PLANS_ROOT_SHOWN)
    ] = DEFAULT_PLANS_ROOT,
    wait_on_rate_limit: WaitMinutes = None,
) -> None:
    """Plan a new bundle: stages 1 to 5, stopping after stage 1 unless --no-confirm.

    On an existing slug with the same request it continues; with another request it is
    refused. Exit 0 runnable or stopped after stage 1 as asked, 1 not runnable, 3 rate limited.
    """
    with _plan_errors():
        try:
            plan_request = request_from_flags(
                question,
                request=request,
                targets=targets,
                budget=budget,
                scope=scope,
                hypotheses=hypotheses,
                constraint=constraint or (),
                slug=slug,
                world=world,
                base_world=base_world,
                seed=seed,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from None
        director = _director(Director.new, plan_request, plans_root=plans_root)
        _refuse_open_blocks(director.record)
        record = _drive(lambda: director.run(stop_after_plan=not no_confirm), wait_on_rate_limit)
    if not no_confirm:
        # only a plan standing at stage 1 is a stop after stage 1 as asked, this run's or an
        # earlier one's (D-exit; review M4); a plan past it is reported as it is (fix round 2,
        # re-review N1): its failed stage, open blocks or lint failures, its status, and the
        # exit its status implies. A plan held by open blocks was refused above. A plan whose
        # stage 2 has made a call is past the stop too, whatever its status says (the final
        # review's M6: its manifest was planned on plan.md as it was, so an edit is no longer
        # stage 2's to adopt)
        author = next((s for s in record.stages if s.stage == "author"), None)
        if record.status == "planned" and (author is None or not author.calls):
            _stopped(director)
            return
        if record.status in _MID_PLAN or record.status == "planned":
            where = "in stage author" if record.status == "planned" else f"at {record.status}"
            typer.echo(
                f"plan new without --no-confirm runs stage 1 only; this plan stands {where}, "
                f"so run plan continue {director.bundle.root.as_posix()}"
            )
    _finish(record)


@plan_app.command("continue")
def continue_(bundle: BundleDir, wait_on_rate_limit: WaitMinutes = None) -> None:
    """Resume a plan at its first stage not committed and run it through stage 5.

    A plan held by open blocks after stage 4 is refused without a call: edit the bundle and
    run plan review. Exit 0 runnable, 1 not runnable, 3 rate limited.
    """
    with _plan_errors():
        director = _opened(bundle)
        _refuse_open_blocks(director.record)
        record = _drive(director.run, wait_on_rate_limit)
    _finish(record)


@plan_app.command("review")
def review(bundle: BundleDir, wait_on_rate_limit: WaitMinutes = None) -> None:
    """Review an edited bundle again: stages 3, 4 and 5.

    The last round's review, revise and validate records and transcripts are archived first,
    under transcripts/round-<n>/. Exit 0 runnable, 1 not runnable, 3 rate limited.
    """
    with _plan_errors():
        director = _opened(bundle)

        def round_() -> PlanRecord:
            director.review_round()
            return director.record

        record = _drive(round_, wait_on_rate_limit)
    _finish(record)


@plan_app.command("validate")
def validate(bundle: BundleDir) -> None:
    """Run stage 5 again on the bundle as it stands. No model call.

    The lints, the stub dry run and the bundle hash. Exit 0 runnable, 1 not runnable.
    """
    with _plan_errors():
        record = _opened(bundle).revalidate()
    _finish(record)


@plan_app.command("diff")
def diff(
    bundle: BundleDir,
    other: Annotated[Path | None, typer.Argument(help="A second bundle to diff against.")] = None,
    worlds_dir: Annotated[
        Path | None, typer.Option(help="The shipped worlds, for one bundle (data/worlds).")
    ] = None,
) -> None:
    """Diff two bundles' hashed files, or one bundle's worlds against the shipped ones.

    With one bundle, each copied world is diffed against <worlds-dir>/<name> after a line
    saying whether the shipped world has moved since the copy.
    """
    _a_plan(bundle)
    with _plan_errors():
        if other is not None:
            text = bundle_diff(bundle, _a_plan(other, "OTHER"))
        else:
            text = world_diff(Bundle(bundle), worlds_dir or WORLDS_DIR)
    typer.echo(text, nl=False)


# ------------------------------------------------------------------------------ the diffs


def _lines(path: Path) -> list[str]:
    """A file's lines, CRLF read as LF (a shipped world in a CRLF checkout is no edit)."""
    if not path.is_file():
        return []
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    return text.splitlines(keepends=True)


def _file_diff(a: Path, b: Path, a_label: str, b_label: str) -> list[str]:
    """``difflib.unified_diff`` of two files, a missing side read as empty and labelled
    ``/dev/null``; every line ends with a newline."""
    found = difflib.unified_diff(
        _lines(a),
        _lines(b),
        a_label if a.is_file() else _NO_FILE,
        b_label if b.is_file() else _NO_FILE,
    )
    return [line if line.endswith("\n") else f"{line}\n" for line in found]


def bundle_diff(a: Path, b: Path) -> str:
    """The unified diff of the hashed files of bundles ``a`` and ``b`` (every file
    ``bundle_hash`` covers), path by path in sorted order; empty when they are the same. Each
    side is labelled by its path in its bundle, ``a/<path>`` and ``b/<path>``, never by an
    absolute path, which holds the login's home folder (the final review's M1)."""
    out: list[str] = []
    for rel in sorted(set(hashed_paths(a)) | set(hashed_paths(b))):
        out += _file_diff(a / rel, b / rel, f"a/{rel}", f"b/{rel}")
    return "".join(out)


def world_diff(bundle: Bundle, worlds_dir: Path) -> str:
    """Per ``base_worlds`` entry, whether the shipped world at ``<worlds_dir>/<name>`` has moved
    since the copy (its ``hash_tree``, ``world_hash``'s scheme, against the hash recorded at the
    copy), then the unified diff of each file of the shipped world and of the copy, shipped to
    copy, so a patch the plan made reads as an edit. Spec section 13: a moved shipped world
    fails nothing; the bundle runs its copy. The shipped side is labelled
    ``shipped/<name>/<path>`` (its path in the worlds directory) and the copy
    ``worlds/<name>/<path>`` (its path in the bundle), never an absolute path (the final
    review's M1)."""
    record = bundle.read_record()
    if not record.base_worlds:
        return "the bundle copied no shipped world\n"
    out: list[str] = []
    for name, then in sorted(record.base_worlds.items()):
        shipped, copy = worlds_dir / name, bundle.root / "worlds" / name
        if not shipped.is_dir():
            out.append(
                f"worlds/{name}: {shown_paths(worlds_dir.as_posix())} holds no world {name}\n"
            )
            continue
        now = hash_tree(shipped)
        if now == then:
            out.append(f"worlds/{name}: the shipped world has not moved since the copy\n")
        else:
            out.append(
                f"worlds/{name}: the shipped world has moved since the copy "
                f"({then[:12]} then, {now[:12]} now)\n"
            )
        files = {p.relative_to(shipped).as_posix() for p in shipped.rglob("*") if p.is_file()}
        files |= {p.relative_to(copy).as_posix() for p in copy.rglob("*") if p.is_file()}
        for rel in sorted(files):
            out += _file_diff(
                shipped / rel, copy / rel, f"shipped/{name}/{rel}", f"worlds/{name}/{rel}"
            )
    return "".join(out)
