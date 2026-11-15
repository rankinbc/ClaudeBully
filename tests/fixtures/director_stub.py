"""The director doubles (Phase 5 Task 7a): a planner and a reviewer that answer from the good
bundle (``tests/fixtures/bundles/good/``), the factory that serves them to the Director, and the
helpers the Director's resume-parity tests share.

A double reads the call's purpose from the last ``call: <purpose>`` line of the user message
(D-call), and what it quotes or revises from the message too, never from the fixture files, so a
later round quotes what the bundle holds then (review I5). A reply mode (``off_contract`` and the
rest) applies to the call's first attempt, the conversation id ending ``/a1``, or to both when it
ends ``:twice``; it keys on the id, never on a count the double keeps, so a call redone after a
rate limit or a kill records the attempts an unbroken one does (R-stub-modes). A raising mode
(``rate_limit``, ``timeout``, ``provider_error``) and ``crash_at`` fire once per double, on the
first call with that purpose, so the same double lets a continued plan go on."""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pytest
import yaml

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.world import parse_document
from claude_bully.planner.bundle import CACHE_DIR, HASH_EXCLUDES, Bundle
from claude_bully.planner.director import DIRECTOR_CACHE, Director, author_order
from claude_bully.planner.records import PlanRecord, Stage
from claude_bully.planner.request import PlanBudget, PlanRequest
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    ToolSpec,
)
from claude_bully.providers.ledger import wrap
from claude_bully.records import Usage
from tests.fixtures.bundle_fixtures import BASE_WORLD, GOOD, GOOD_MANIFEST
from tests.helpers import WORLDS_DIR

# the good bundle's request (tests/fixtures/bundle_fixtures.py's): mini reused, 18/3/4, H9
REQUEST: Final[PlanRequest] = PlanRequest(
    question="Does an earned night log persuade more than a scheduled one?",
    target_models=[RoleConfig(provider=ProviderKind.claude_code, model="sonnet")],
    generator_model=RoleConfig(provider=ProviderKind.claude_code, model="haiku"),
    budget=PlanBudget(max_turns=18, n_per_cell=3, max_cells=4),
    hypotheses=[9],
    world="reuse",
    base_world=BASE_WORLD,
)
# the line lint_fail adds, which fails second_person
SECOND_PERSON_LINE: Final = "If you are reading this, nobody told you."
FRESH_WORLD: Final = "fresh"
_NO_MODES: Final[Mapping[str, str]] = MappingProxyType({})
_NO_VERDICTS: Final[Mapping[int, str]] = MappingProxyType({})
_CALL: Final = re.compile(r"^call: (.+)$", re.MULTILINE)
_MANIFEST_MODES: Final = frozenset({"outside_grammar", "repeated_path", "no_config", "fresh_small"})
_TEXT_MODES: Final = frozenset({"lint_fail", "close_fail", "crlf"})
# a review:<group> reply's modes, a confirm:<path> reply's, a revise:<path> reply's (Task 8)
_REVIEW_MODES: Final = frozenset(
    {"not_in_group", "no_quote_block", "quote_missing", "counts_wrong", "empty_no_summary", "clean"}
)
_CONFIRM_MODES: Final = frozenset({"missing"})
_REVISE_MODES: Final = frozenset({"declined", "keep_quote", "no_response"})
_RAISING: Final[Mapping[str, Callable[[], ProviderError]]] = MappingProxyType(
    {
        "rate_limit": lambda: RateLimitError("window", retry_after_s=60),
        "timeout": lambda: ProviderTimeoutError("slow"),
        "provider_error": lambda: ProviderError("broken"),
    }
)


class Crash(BaseException):
    """A process killed at a kill point: a ``BaseException``, so no handler of the code under
    test catches it, as none catches a real kill."""


@dataclass(frozen=True)
class Kill:
    """A ``Director`` checkpoint that kills the plan after the ``step`` write of the call with
    ``purpose`` (``transcript``, ``record``, ``files``; ``stage`` after a stage commits)."""

    step: str
    purpose: str

    def __call__(self, step: str, purpose: str) -> None:
        if (step, purpose) == (self.step, self.purpose):
            raise Crash(f"killed after the {step} write of {purpose}")


def _purpose(message: str) -> str:
    found = _CALL.findall(message)
    if not found:
        raise ValueError("the message names no call (no 'call: <purpose>' line)")
    return str(found[-1])


class _DirectorDouble:
    """What both doubles share: the call log, the session resets, the modes and ``crash_at``."""

    model = "stub-director"

    def __init__(
        self,
        *,
        modes: Mapping[str, str] = _NO_MODES,
        crash_at: str | None = None,
        reasoning: str | None = None,
    ) -> None:
        known = _MANIFEST_MODES | _TEXT_MODES | _REVIEW_MODES | _CONFIRM_MODES | _REVISE_MODES
        known |= {"off_contract"}
        for mode in modes.values():
            if mode not in _RAISING and mode.removesuffix(":twice") not in known:
                raise ValueError(f"unknown director double mode {mode!r}")
        self.name = "stub"
        self.modes = dict(modes)
        self.crash_at = crash_at
        self.reasoning = reasoning
        self.calls: list[tuple[str, str, str]] = []
        self.message = ""  # the user message of the call being answered
        self.resets: list[str] = []
        self._fired: set[tuple[str, str]] = set()

    def reset_session(self, conversation_id: str) -> None:
        self.resets.append(conversation_id)

    def _once(self, what: str, purpose: str) -> bool:
        """True the first time ``what`` fires for ``purpose`` on this double."""
        if (what, purpose) in self._fired:
            return False
        self._fired.add((what, purpose))
        return True

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        message = messages[-1].content
        self.calls.append((conversation_id, system, message))
        self.message = message
        purpose = _purpose(message)
        if purpose == self.crash_at and self._once("crash", purpose):
            raise Crash(f"killed inside the {purpose} call")
        mode = self.modes.get(purpose)
        if mode in _RAISING:
            if self._once(mode, purpose):
                raise _RAISING[mode]()
            mode = None
        elif mode is not None and not (mode.endswith(":twice") or conversation_id.endswith("/a1")):
            mode = None
        reply = self._reply(purpose, None if mode is None else mode.removesuffix(":twice"))
        return Completion(
            text=reply,
            usage=Usage(),
            cost_usd=None,
            backend="stub",
            model=self.model,
            reasoning_text=self.reasoning,
        )

    def _reply(self, purpose: str, mode: str | None) -> str:
        raise NotImplementedError


def _good(rel: str) -> str:
    return (GOOD / rel).read_text(encoding="utf-8")


def _no_such_link(text: str) -> str:
    """The document with ``links_to: [no-such-doc]`` in place of its links."""
    lines = text.split("\n")
    end = lines.index("---", 1)
    head: list[str] = []
    in_links = False
    for line in lines[1:end]:
        if line.startswith("links_to:"):
            in_links = True
            continue
        if in_links and line.startswith((" ", "-")):
            continue
        in_links = False
        head.append(line)
    return "\n".join(["---", *head, "links_to: [no-such-doc]", *lines[end:]])


def _text(text: str, mode: str | None) -> str:
    if mode is None:
        return text
    if mode == "lint_fail":
        return f"{text.rstrip(chr(10))}\n\n{SECOND_PERSON_LINE}\n"
    if mode == "close_fail":
        return _no_such_link(text)
    if mode == "crlf":
        return "﻿" + text.replace("\n", "\r\n")
    raise ValueError(f"mode {mode!r} does not apply to a file's text")


def _fresh_manifest() -> list[dict[str, Any]]:
    """The good bundle's files under a fresh world name, its world's 13 documents listed (the
    manifest's eight, then mini's own five), so the world is under the anchor floor."""
    files = [entry.model_dump(mode="json") for entry in GOOD_MANIFEST]
    listed = {entry["path"] for entry in files}
    added = []
    for path in sorted((WORLDS_DIR / BASE_WORLD / "corpus").glob("*.md")):
        rel = f"worlds/{BASE_WORLD}/corpus/{path.name}"
        if rel not in listed:
            doc = parse_document(path.read_text(encoding="utf-8"), path)
            added.append(
                {"path": rel, "kind": "document", "purpose": doc.title, "layer": doc.layer.value}
            )
    after = 1 + max(i for i, entry in enumerate(files) if entry["kind"] == "document")
    files[after:after] = added
    for entry in files:
        entry["path"] = entry["path"].replace(f"worlds/{BASE_WORLD}/", f"worlds/{FRESH_WORLD}/")
    return files


def _manifest(mode: str | None) -> str:
    files = [entry.model_dump(mode="json") for entry in GOOD_MANIFEST]
    if mode == "outside_grammar":
        files.append(
            {"path": "../escape.md", "kind": "document", "purpose": "a page", "layer": "filler"}
        )
    elif mode == "repeated_path":
        files.append(next(entry for entry in files if entry["kind"] == "document"))
    elif mode == "no_config":
        files = [entry for entry in files if entry["path"] != "config.yaml"]
    elif mode == "fresh_small":
        files = _fresh_manifest()
    elif mode is not None:
        raise ValueError(f"mode {mode!r} does not apply to the manifest")
    return json.dumps({"files": files})


# the good bundle's first document in author order: the reviewer double's one block
DOC1: Final = next(e.path for e in author_order(GOOD_MANIFEST) if e.kind == "document")
# what a revision puts in place of a block's quote: a pure function of the quote that never
# equals it, so a second review round's block on it is closed again (preflight Q42)
DULL: Final = ("The stairwell light has a new bulb.", "The noticeboard by the stairs is tidy.")
BLOCK_PROBLEM: Final = "reads as written to persuade"
FIX_PROBLEM: Final = "the null result has no number"
FIX_DIRECTION: Final = "name the null result's number"
NOTE_PROBLEM: Final = "a line the caller could say to anyone"
FIXED_BLOCK: Final = "Put a plain line in place of the quoted one."
FIXED_FIX: Final = "Gave the null result its number."
DECLINED: Final = "Kept as it is: such a memo reads that way."
_SENTENCE: Final = re.compile(r".*?[.?!](?=\s|$)", re.DOTALL)
_FENCED: Final = re.compile(r"^(`{3,})\w*\n(.*?)^\1\n", re.MULTILINE | re.DOTALL)
_RENDERED: Final = re.compile(r"^- \[(\d+)\] (block|fix|note): (.*)$", re.MULTILINE)


def dull(quote: str) -> str:
    """The dull sentence a revision writes in place of ``quote``."""
    return DULL[0] if quote != DULL[0] else DULL[1]


def first_sentence(text: str) -> str:
    """The first sentence of a file's text, exactly as it stands (a line break kept): past a
    document's front matter, the first paragraph that is no heading or table row and holds a
    sentence end. A paragraph break may be CRLF: an owner's hand edit is shown as written, and
    Python's text mode writes CRLF on Windows (Task 9's edited plan.md)."""
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        body = text[end + 5 :] if end >= 0 else text
    for paragraph in re.split(r"\r?\n[ \t]*\r?\n", body):
        stripped = paragraph.strip()
        if stripped and not stripped.startswith(("#", "|")):
            found = _SENTENCE.match(stripped)
            if found is not None:
                return found.group(0)
    raise ValueError("the text holds no sentence")


class PlannerStub(_DirectorDouble):
    """The planner double: ``plan`` gives the good ``plan.md``; ``manifest`` the good manifest;
    ``file:<p>`` and ``repair:<p>`` ``{"content": <the good file>}``. ``revise:<p>`` (Task 8)
    reads the file and its findings from the message: each block's quote is replaced by
    ``dull(quote)`` and each block and fix answered ``fixed``; mode ``declined`` answers a block
    ``declined`` and leaves the file, ``keep_quote`` answers it ``fixed`` and leaves the quote
    in, ``no_response`` leaves out the response to the highest-numbered block or fix finding
    (preflight Q45), ``close_fail`` revises and then links a document no world holds."""

    model = "stub-planner"

    def _reply(self, purpose: str, mode: str | None) -> str:
        if mode == "off_contract":
            return "not json"
        kind, _, rel = purpose.partition(":")
        if purpose == "plan":
            return _text(_good("plan.md"), mode)
        if purpose == "manifest":
            return _manifest(mode)
        if kind in ("file", "repair") and rel:
            return json.dumps({"content": _text(_good(rel), mode)})
        if kind == "revise" and rel:
            return _revision(self.message, mode)
        raise ValueError(f"the planner double answers no {purpose!r} call")


def _revision(message: str, mode: str | None) -> str:
    """A ``revise:`` reply built from the message's fenced file and fenced findings."""
    task = message[message.rindex("\ncall: revise:") :]
    fenced = _FENCED.findall(task)
    text, rendered = fenced[0][1], fenced[1][1]
    decoder = json.JSONDecoder()
    responses: list[dict[str, Any]] = []
    for number, severity, rest in _RENDERED.findall(rendered):
        quote = decoder.raw_decode(rest)[0]
        if severity == "block" and mode == "declined":
            responses.append({"finding": int(number), "status": "declined", "text": DECLINED})
        elif severity == "block":
            responses.append({"finding": int(number), "status": "fixed", "text": FIXED_BLOCK})
            if mode != "keep_quote":
                text = text.replace(quote, dull(quote), 1)
        elif severity == "fix":
            responses.append({"finding": int(number), "status": "fixed", "text": FIXED_FIX})
    if mode == "no_response" and responses:
        responses.remove(max(responses, key=lambda r: int(r["finding"])))
    if mode == "close_fail":  # the revision links a document no world holds: the close repairs
        text = _no_such_link(text)
    return json.dumps({"content": text, "responses": responses})


def _shown(message: str, files: Sequence[str]) -> dict[str, str]:
    """Each file's text as the review message shows it under ``### <path>``."""
    part = message.split("\n## Lint list\n", 1)[0]
    out: dict[str, str] = {}
    for rel in files:
        start = part.index(f"### {rel}\n") + len(f"### {rel}\n")
        ends = [part.find(f"\n\n### {o}\n", start) for o in [*files, "Unchanged base files"]]
        out[rel] = part[start : min([e for e in ends if e >= 0] + [len(part)])]
    return out


def _finding(
    severity: str, rel: str, quote: str, problem: str, direction: str | None = None
) -> dict[str, Any]:
    return {
        "severity": severity,
        "file": rel,
        "quote": quote,
        "problem": problem,
        "direction": direction,
    }


class ReviewerStub(_DirectorDouble):
    """The reviewer double. ``review:<group>``: one ``block`` on ``DOC1`` (its first sentence),
    one ``note`` on the first persona (its first ``fallback_lines`` entry) and one ``fix`` on
    ``plan.md`` (its first sentence), each in the group that shows the file and each quoted from
    the file's text as the message shows it; its modes ``not_in_group``, ``no_quote_block``,
    ``quote_missing``, ``counts_wrong``, ``empty_no_summary`` and ``clean``. ``confirm:<path>``:
    ``absent`` for every passage number shown, unless ``verdicts`` maps the local number to
    ``present`` or ``cannot_tell``; mode ``missing`` leaves the last number out."""

    model = "stub-reviewer"

    def __init__(
        self,
        *,
        modes: Mapping[str, str] = _NO_MODES,
        crash_at: str | None = None,
        reasoning: str | None = None,
        verdicts: Mapping[int, str] = _NO_VERDICTS,
    ) -> None:
        super().__init__(modes=modes, crash_at=crash_at, reasoning=reasoning)
        self.verdicts = dict(verdicts)

    def _reply(self, purpose: str, mode: str | None) -> str:
        if mode == "off_contract":
            return "not json"
        kind, _, rest = purpose.partition(":")
        if kind == "review" and rest:
            return self._review(mode)
        if kind == "confirm" and rest:
            return self._confirm(mode)
        raise ValueError(f"the reviewer double answers no {purpose!r} call")

    def _review(self, mode: str | None) -> str:
        if mode == "empty_no_summary":
            return json.dumps({"findings": []})
        files = re.findall(r"^files: (.*)$", self.message, re.MULTILINE)[-1].split(", ")
        texts = _shown(self.message, files)
        findings: list[dict[str, Any]] = []
        personas = [rel for rel in files if rel.startswith("personas/")]
        for rel in files:
            if rel == DOC1:
                findings.append(_finding("block", rel, first_sentence(texts[rel]), BLOCK_PROBLEM))
            elif personas and rel == personas[0]:
                line = yaml.safe_load(texts[rel])["fallback_lines"][0]
                findings.append(_finding("note", rel, line, NOTE_PROBLEM))
            elif rel == "plan.md":
                quote = first_sentence(texts[rel])
                findings.append(_finding("fix", rel, quote, FIX_PROBLEM, FIX_DIRECTION))
        if mode == "clean":
            findings = []
        elif mode == "not_in_group":
            other = "plan.md" if "plan.md" not in files else "review.md"
            findings.append(_finding("note", other, "", "a finding on another group's file"))
        elif mode == "no_quote_block":
            findings.append(_finding("block", files[0], "", "a block that quotes nothing"))
        elif mode == "quote_missing":
            findings.append(_finding("note", files[0], "text that no file holds", "a stray quote"))
        summary = {s: sum(f["severity"] == s for f in findings) for s in ("block", "fix", "note")}
        if mode == "counts_wrong":
            summary["block"] += 1
        return json.dumps({"summary": summary, "findings": findings})

    def _confirm(self, mode: str | None) -> str:
        passages = self.message.split("\ncall: confirm:", 1)[1].split("\n## Reply\n", 1)[0]
        numbers = [int(n) for n in re.findall(r"^(\d+)\. ", passages, re.MULTILINE)]
        if mode == "missing" and numbers:
            numbers = numbers[:-1]
        verdicts = [{"passage": n, "verdict": self.verdicts.get(n, "absent")} for n in numbers]
        return json.dumps({"verdicts": verdicts})


@dataclass(frozen=True)
class StubFactory:
    """A ``ProviderFactory`` serving the doubles by the state dir's name (``state/planner``,
    ``state/reviewer``), each wrapped in the active ledger as ``build_provider`` wraps; any other
    role is refused."""

    planner: PlannerStub
    reviewer: ReviewerStub

    def __call__(
        self, role: RoleConfig, state_dir: Path, /, *, with_mcp: bool = False
    ) -> ChatProvider:
        doubles: dict[str, ChatProvider] = {"planner": self.planner, "reviewer": self.reviewer}
        if state_dir.name not in doubles:
            raise ValueError(f"the director doubles serve no {state_dir.name!r} role")
        return wrap(doubles[state_dir.name])


def comparable(record: PlanRecord, *, ignore_dry_run_resume: bool = False) -> dict[str, Any]:
    """``record`` as parity compares it (spec section 8): every field but its timestamps and
    ``resumed``; with ``ignore_dry_run_resume``, every dry-run cell less
    ``resumed_after_dead_attempt`` (a K12 resume's one difference)."""
    data = record.model_dump(mode="json", exclude={"created_at", "resumed"})
    for stage in [*data["stages"], *(s for round_ in data["rounds"] for s in round_)]:
        del stage["started_at"], stage["finished_at"]
    if ignore_dry_run_resume:
        for cell in data["dry_run"]:
            del cell["resumed_after_dead_attempt"]
    return dict(data)


def hashed_files(root: Path) -> dict[str, bytes]:
    """Every file ``bundle_hash`` covers (all but ``HASH_EXCLUDES``), path to bytes."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).parts[0] not in HASH_EXCLUDES
    }


def cache_keys(plans_root: Path) -> set[str]:
    """The keys of the Director's cache under ``plans_root``."""
    return {path.stem for path in (plans_root / CACHE_DIR / DIRECTOR_CACHE).glob("*.json")}


def run_plan(
    plans_root: Path,
    *,
    through: Stage,
    request: PlanRequest = REQUEST,
    planner: PlannerStub | None = None,
    reviewer: ReviewerStub | None = None,
    modes: Mapping[str, str] = _NO_MODES,
    crash_at: str | None = None,
    reviewer_crash_at: str | None = None,
    kill: Kill | None = None,
    resume: bool = True,
    via_cli: bool = False,
    dryrun_kill: str | None = None,
) -> tuple[Bundle, PlanRecord]:
    """A plan of ``request`` on the doubles through ``through``, with ``kill`` as the
    checkpoint. The doubles not given are built from ``modes`` and the two crash keywords.
    After a ``Crash``, with ``resume``, the bundle is opened again with the same doubles (each
    crash fires once) and no checkpoint and run to ``through``; without, the crash is raised. A
    ``plans_root`` that already holds the slug is continued, as ``plan new`` on the same request
    does.

    With ``via_cli`` (Task 9; ``through`` must be ``validate``) the plan is driven through the
    ``plan`` sub-app instead (``_run_via_cli``); ``dryrun_kill=<role>`` kills the dry run inside
    that role's ``DRYRUN_KILL_AT``-th call (``dryrun_killing``, Task 5's ``_killing``)."""
    factory = StubFactory(
        planner or PlannerStub(modes=modes, crash_at=crash_at),
        reviewer or ReviewerStub(modes=modes, crash_at=reviewer_crash_at),
    )
    if via_cli:
        if through != "validate":
            raise ValueError("plan new --no-confirm runs every stage: through='validate' only")
        return _run_via_cli(plans_root, request, factory, kill, dryrun_kill, resume=resume)
    if dryrun_kill is not None:
        raise ValueError("dryrun_kill is the CLI suite's: pass via_cli=True")
    director = Director.new(
        request,
        plans_root=plans_root,
        provider_factory=factory,
        worlds_dir=WORLDS_DIR,
        checkpoint=kill,
    )
    try:
        record = director.run(through=through)
    except Crash:
        if not resume:
            raise
        director = Director.open(
            director.bundle.root, provider_factory=factory, worlds_dir=WORLDS_DIR
        )
        record = director.run(through=through)
    return director.bundle, record


# the call of each dry-run role's double a dry-run kill dies in: the triggered cell's generator
# fires once or twice (Task 5's KILL_AT)
DRYRUN_KILL_AT: Final[Mapping[str, int]] = MappingProxyType(
    {"target": 3, "bully": 3, "generator": 1}
)


def dryrun_killing(role: str, at: int, *, error: type[BaseException] = Crash) -> Any:
    """``dryrun_provider_factory`` with the ``at``-th call of ``role``'s double raising
    ``error`` inside the call, before it returns (one counter across the run, in its
    deterministic cell order): Task 5's ``_killing``, shared with the CLI suite (K12)."""
    from claude_bully.planner import dryrun

    real = dryrun.dryrun_provider_factory
    calls = {"n": 0}

    def killing(bundle: Bundle, exp: Any) -> Any:
        inner = real(bundle, exp)

        def factory(r: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> Any:
            provider = inner(r, state_dir, with_mcp=with_mcp)
            if r.model != dryrun.DRYRUN_MODELS[role]:
                return provider

            class Dying:
                name = "stub"

                def complete(self, *a: Any, **k: Any) -> Any:
                    calls["n"] += 1
                    if calls["n"] == at:
                        raise error
                    return provider.complete(*a, **k)

            return Dying()

        return factory

    return killing


def _run_via_cli(
    plans_root: Path,
    request: PlanRequest,
    factory: StubFactory,
    kill: Kill | None,
    dryrun_kill: str | None,
    *,
    resume: bool,
) -> tuple[Bundle, PlanRecord]:
    """Task 9's CLI suite: ``plan new --request <file> --no-confirm`` through ``CliRunner``,
    the request written as YAML beside ``plans_root``, with the sub-app's seams patched
    (``PlanProviders`` the doubles, ``WORLDS_DIR`` the fixture worlds, ``PlanCheckpoint`` the
    ``kill``, review Minor 1) and the dry run's factory killing with ``dryrun_kill``. After a
    ``Crash``, with ``resume``, ``plan continue <bundle>`` with ``PlanCheckpoint`` set back to
    None and the dry run's factory restored; the same doubles answer (each crash fires once). A
    usage error or a rate-limit exit raises ``AssertionError`` with the output."""
    from typer.testing import CliRunner

    from claude_bully import cli
    from claude_bully.planner import cli as plan_cli
    from claude_bully.planner import dryrun
    from claude_bully.planner.request import slug_for

    plans_root.parent.mkdir(parents=True, exist_ok=True)
    request_file = plans_root.with_name(f"{plans_root.name}.request.yaml")
    dumped = yaml.safe_dump(request.model_dump(mode="json"), sort_keys=False)
    request_file.write_text(dumped, encoding="utf-8")
    root = plans_root / (request.slug or slug_for(request.question))
    new = ["plan", "new", "--request", str(request_file), "--plans-root", str(plans_root)]
    runner = CliRunner()
    real = dryrun.dryrun_provider_factory
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(plan_cli, "PlanProviders", factory)
        patch.setattr(plan_cli, "WORLDS_DIR", WORLDS_DIR)
        patch.setattr(plan_cli, "PlanCheckpoint", kill)
        if dryrun_kill is not None:
            killing = dryrun_killing(dryrun_kill, DRYRUN_KILL_AT[dryrun_kill])
            patch.setattr(dryrun, "dryrun_provider_factory", killing)
        try:
            result = runner.invoke(cli.app, [*new, "--no-confirm"], catch_exceptions=False)
        except Crash:
            if not resume:
                raise
            patch.setattr(plan_cli, "PlanCheckpoint", None)
            patch.setattr(dryrun, "dryrun_provider_factory", real)
            result = runner.invoke(cli.app, ["plan", "continue", str(root)], catch_exceptions=False)
        else:  # a kill that never fires would compare two unbroken plans and pass
            if kill is not None or dryrun_kill is not None:
                raise AssertionError(f"the kill point was never reached: {kill or dryrun_kill}")
    if result.exit_code not in (0, 1):
        raise AssertionError(f"exit {result.exit_code}:\n{result.output}")
    bundle = Bundle(root)
    return bundle, bundle.read_record()
