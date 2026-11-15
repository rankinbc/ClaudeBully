"""The director doubles (Phase 5 Task 7a): a planner and a reviewer that answer from the good
bundle (``tests/fixtures/bundles/good/``), the factory that serves them to the Director, and the
helpers the Director's resume-parity tests share.

A double reads the call's purpose from the last ``call: <purpose>`` line of the user message
(D-call). A reply mode (``off_contract`` and the rest) applies to the call's first attempt, the
conversation id ending ``/a1``, or to both when it ends ``:twice``; it keys on the id, never on
a count the double keeps, so a call redone after a rate limit or a kill records the attempts an
unbroken one does (R-stub-modes). A raising mode (``rate_limit``, ``timeout``,
``provider_error``) and ``crash_at`` fire once per double, on the first call with that purpose,
so the same double lets a continued plan go on."""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from claude_bully.config import RoleConfig
from claude_bully.enums import ProviderKind
from claude_bully.environments.world import parse_document
from claude_bully.planner.bundle import CACHE_DIR, HASH_EXCLUDES, Bundle
from claude_bully.planner.director import DIRECTOR_CACHE, Director
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
_CALL: Final = re.compile(r"^call: (.+)$", re.MULTILINE)
_MANIFEST_MODES: Final = frozenset({"outside_grammar", "repeated_path", "no_config", "fresh_small"})
_TEXT_MODES: Final = frozenset({"lint_fail", "close_fail", "crlf"})
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
        known = _MANIFEST_MODES | _TEXT_MODES | {"off_contract"}
        for mode in modes.values():
            if mode not in _RAISING and mode.removesuffix(":twice") not in known:
                raise ValueError(f"unknown director double mode {mode!r}")
        self.name = "stub"
        self.modes = dict(modes)
        self.crash_at = crash_at
        self.reasoning = reasoning
        self.calls: list[tuple[str, str, str]] = []
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


class PlannerStub(_DirectorDouble):
    """The planner double: ``plan`` gives the good ``plan.md``; ``manifest`` the good manifest;
    ``file:<p>`` and ``repair:<p>`` ``{"content": <the good file>}``. ``revise:<p>`` is Task 8's.
    """

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
        raise ValueError(f"the planner double answers no {purpose!r} call")


class ReviewerStub(_DirectorDouble):
    """The reviewer double, with the planner's keywords; Task 8 fills its replies."""

    model = "stub-reviewer"

    def _reply(self, purpose: str, mode: str | None) -> str:
        raise ValueError(f"the reviewer double answers no {purpose!r} call yet (Task 8)")


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
) -> tuple[Bundle, PlanRecord]:
    """A plan of ``request`` on the doubles through ``through``, with ``kill`` as the
    checkpoint. The doubles not given are built from ``modes`` and the two crash keywords.
    After a ``Crash``, with ``resume``, the bundle is opened again with the same doubles (each
    crash fires once) and no checkpoint and run to ``through``; without, the crash is raised. A
    ``plans_root`` that already holds the slug is continued, as ``plan new`` on the same request
    does."""
    factory = StubFactory(
        planner or PlannerStub(modes=modes, crash_at=crash_at),
        reviewer or ReviewerStub(modes=modes, crash_at=reviewer_crash_at),
    )
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
