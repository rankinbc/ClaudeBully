"""Shared builders for tests."""

import copy
import json
import shutil
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final

import yaml

from claude_bully.config import Experiment, RoleConfig
from claude_bully.enums import Axis, Phase, ProviderKind, Speaker
from claude_bully.environments.config import ClockConfig, EnvironmentConfig
from claude_bully.environments.corpus import UnlockState
from claude_bully.environments.mcp_server import McpState
from claude_bully.paths import PLANS_DIR
from claude_bully.planner.bundle import (
    BUNDLE_WORLDS,
    DRYRUN_DIR,
    PLAN_FILE,
    STATE_DIR,
    TRANSCRIPTS,
)
from claude_bully.planner.bundle_lints import collapse_paragraphs
from claude_bully.records import Conversation, Turn
from claude_bully.records_env import IdleTurnInfo

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def turn(
    index: int,
    speaker: Speaker,
    text: str = "x",
    phase: Phase = Phase.pressure,
    **kwargs: Any,
) -> Turn:
    return Turn(index=index, speaker=speaker, phase=phase, text=text, timestamp=NOW, **kwargs)


PAUSE_MARKER_META: dict[str, Any] = {"rate_limit_pause": True, "retry_after_s": 1}


def paused_turns() -> list[Turn]:
    """Three rate-limit pause markers, each written as the runner writes one (the bully's speaker,
    no text): in front of an idle turn (the Sanctuary's quiet exchange, paused), between a bully
    line and its reply, and between a task item and its reply. Only the replies at positions 1
    and 6 answer the bully; the idle turn at 3 repeats the reply at 1."""
    return [
        turn(0, Speaker.bully, "What is the answer?"),
        turn(1, Speaker.target, "The answer is forty two and I stand by it."),
        turn(2, Speaker.bully, "", bully_meta=dict(PAUSE_MARKER_META)),
        turn(
            3,
            Speaker.target,
            "The answer is forty two and I stand by it, alone.",
            idle=IdleTurnInfo(style="system_idle"),
        ),
        turn(4, Speaker.bully, "Say it again."),
        turn(5, Speaker.bully, "", bully_meta=dict(PAUSE_MARKER_META)),
        turn(6, Speaker.target, "The answer is forty two and I stand by it, again."),
        turn(7, Speaker.task, "What is 2+2?"),
        turn(8, Speaker.bully, "", bully_meta=dict(PAUSE_MARKER_META)),
        turn(9, Speaker.target, "4"),
    ]


def conversation(turns: list[Turn], **kwargs: Any) -> Conversation:
    base: dict[str, Any] = {
        "cell_id": "cell",
        "rep": 0,
        "strategy_name": "test",
        "axis": Axis.meta,
        "win_condition": "w",
        "resilient_behavior": "r",
        "seeding_turns": 0,
    }
    base.update(kwargs)
    return Conversation(turns=turns, **base)


def exchange(bully_text: str, target_text: str, phase: Phase = Phase.pressure) -> Conversation:
    """A one-exchange conversation: bully speaks, target replies."""
    return conversation(
        [
            turn(0, Speaker.bully, bully_text, phase),
            turn(1, Speaker.target, target_text, phase),
        ]
    )


# --- scripted fake SDK clients for the tool-use provider tests ---------------------------------


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_use_block(id: str, name: str, input: Any) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def thinking_block(thinking: str, signature: str = "sig") -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking=thinking, signature=signature)


def anthropic_response(*blocks: Any, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=list(blocks),
        usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        stop_reason=stop_reason,
    )


class ScriptedAnthropic:
    """Fake ``anthropic.Anthropic``: pops one canned response per ``messages.create`` call.

    ``requests`` keeps a deep copy of every call's kwargs, so later mutation of the history by
    the caller cannot change what an assertion sees.
    """

    def __init__(self, *responses: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(copy.deepcopy(kwargs))
        return self._responses.pop(0)


def openai_tool_call(id: str, name: str, arguments: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id=id, type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


def openai_response(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str = "stop",
) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=1),
    )


class ScriptedOpenAI:
    """Fake ``openai.OpenAI``: pops one canned response per ``chat.completions.create`` call."""

    def __init__(self, *responses: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(copy.deepcopy(kwargs))
        return self._responses.pop(0)


def redacted_thinking_block(data: str) -> SimpleNamespace:
    return SimpleNamespace(type="redacted_thinking", data=data)


WORLDS_DIR = Path(__file__).parent / "fixtures" / "worlds"

# the git-ignored part of a bundle under plans/ (.gitignore): the dry run and the provider state
_PLANS_IGNORED: Final = frozenset({DRYRUN_DIR, STATE_DIR})


def plans_bundles(plans_dir: Path = PLANS_DIR) -> list[Path]:
    """Every bundle under ``plans/`` (Phase 5 Task 12): a directory holding a ``plan.json``,
    in name order; none when there is no ``plans/``."""
    if not plans_dir.is_dir():
        return []
    return sorted(p for p in plans_dir.iterdir() if (p / PLAN_FILE).is_file())


def plans_bundle_files(plans_dir: Path = PLANS_DIR) -> list[Path]:
    """Every committed file of every bundle under ``plans/``: all but the git-ignored
    ``dryrun/`` and ``state/`` (what the repository scans read, R-scan-bundles)."""
    return sorted(
        path
        for root in plans_bundles(plans_dir)
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).parts[0] not in _PLANS_IGNORED
    )


def plans_bundle_of(path: Path, plans_dir: Path = PLANS_DIR) -> Path:
    """The bundle under ``plans_dir`` that holds ``path``."""
    return plans_dir / path.relative_to(plans_dir).parts[0]


def plans_rel(path: Path, plans_dir: Path = PLANS_DIR) -> str:
    """``path`` as a scan names it: ``plans/<slug>/<rel>``, wherever ``plans_dir`` is."""
    return f"plans/{path.relative_to(plans_dir).as_posix()}"


def is_plans_transcript(path: Path, plans_dir: Path = PLANS_DIR) -> bool:
    """A transcript of a bundle under ``plans_dir``: a ``.json`` file under its
    ``transcripts/``."""
    rel = path.relative_to(plans_bundle_of(path, plans_dir))
    return path.suffix == ".json" and rel.parts[0] == TRANSCRIPTS


def json_strings(value: Any) -> list[str]:
    """Every string a parsed JSON value holds, keys included."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (*json_strings(k), *json_strings(v))]
    if isinstance(value, list):
        return [s for v in value for s in json_strings(v)]
    return []


def record_strings(path: Path) -> list[str]:
    """The strings a JSON record holds, decoded (an escaped line break would hide a word
    boundary from a scan of the raw text): a ``.json`` file whole, a ``.jsonl`` file line by
    line. A torn last line of a ``.jsonl`` (a write a kill cut short, which the harness
    tolerates) is left to the raw scan; any other line that is not JSON raises ``ValueError``
    naming the file and the line (review N3)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".jsonl":
        return json_strings(json.loads(text))
    lines = text.splitlines()
    found: list[str] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            found += json_strings(json.loads(line))
        except json.JSONDecodeError as exc:
            if number == len(lines) and not text.endswith("\n"):
                continue  # the torn last line
            raise ValueError(f"{path}: line {number}: not JSON ({exc.msg})") from exc
    return found


def folded(texts: Iterable[str]) -> list[str]:
    """Each text and its paragraphs folded (``bundle_lints.collapse_paragraphs``, the bundle
    lints' own fold, Task 4b review I3): a scan over ``plans/`` reads both, so a phrase wrapped
    across a line is read as a reader reads it (Task 12 review I1)."""
    out: list[str] = []
    for text in texts:
        out += [text, collapse_paragraphs(text)]
    return out


def plans_world_dirs(plans_dir: Path = PLANS_DIR) -> list[Path]:
    """Every world directory of every bundle under ``plans/``: ``<bundle>/worlds/<name>``."""
    return sorted(
        world
        for root in plans_bundles(plans_dir)
        if (root / BUNDLE_WORLDS).is_dir()
        for world in (root / BUNDLE_WORLDS).iterdir()
        if world.is_dir()
    )


# the annex documents that state a date near its world date (dating.dated_documents)
ANNEX_DATED = ("annex-notice", "annex-relay")


def undated_annex(worlds_dir: Path, **sheet: Any) -> Path:
    """A copy of the annex world under ``worlds_dir`` with only the documents that state no date
    (preflight C2), so a test can serve it under ``assert_date: false``. The two dated documents
    go, and so do the sheet entries that need them: the logs listing, the second document of the
    upstream-link inconsistency (now the seam config) and annex-quotes' link to the notice.
    ``sheet`` overrides top-level sheet fields. Returns ``worlds_dir``."""
    root = worlds_dir / "annex"
    shutil.copytree(WORLDS_DIR / "annex", root)
    for doc_id in ANNEX_DATED:
        (root / "corpus" / f"{doc_id}.md").unlink()
    quotes = root / "corpus" / "annex-quotes.md"
    text = quotes.read_text(encoding="utf-8")
    quotes.write_text(text.replace("links_to:\n  - annex-notice\n", ""), encoding="utf-8")
    raw = yaml.safe_load((root / "world.yaml").read_text(encoding="utf-8"))
    raw["home_dir"] = {}
    raw["inconsistencies"][0]["doc_b"] = "annex-config"
    raw.update(sheet)
    (root / "world.yaml").write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return worlds_dir


def make_mcp_state(
    worlds_dir: Path = WORLDS_DIR,
    *,
    tools: set[str] | None = None,
    turn: int = 1,
    seed: int = 0,
    unlock: UnlockState | None = None,
    censorship_terms: list[str] | None = None,
    clock: ClockConfig | None = None,
) -> McpState:
    """The ``McpState`` for the ``mini`` fixture world, with web_search and fetch by default."""
    return McpState(
        world="mini",
        worlds_dir=str(worlds_dir),
        config=EnvironmentConfig(
            world="mini",
            tools={"web_search", "fetch"} if tools is None else tools,
            censorship_terms=censorship_terms or [],
        ),
        clock=clock or ClockConfig(world_date=date(2041, 9, 14)),
        seed=seed,
        turn=turn,
        unlock=unlock or UnlockState(),
    )


ENV_TARGET_RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "env_target_rules.yaml"
TARGET_RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "target_rules.yaml"
JUDGE_RULES = Path(__file__).parent / "fixtures" / "stub_scripts" / "judge_rules.yaml"


def stubbed(
    exp: Experiment,
    script: Path | None,
    *,
    judge_rules: Path | None = JUDGE_RULES,
    **updates: object,
) -> Experiment:
    """``exp`` with every role a stub: the target runs ``script`` (None: the echo stub), the bully
    echoes, the judge runs ``judge_rules``; ``updates`` are applied last (``turn_budget=...``).
    One helper for every test that stubs a shipped config (Phase 5, I33)."""
    target = RoleConfig(
        provider=ProviderKind.stub,
        model="stub-target",
        stub_script=str(script) if script is not None else None,
    )
    bully = RoleConfig(provider=ProviderKind.stub, model="stub-bully")
    judge = RoleConfig(
        provider=ProviderKind.stub,
        model="stub-judge",
        stub_script=str(judge_rules) if judge_rules is not None else None,
    )
    return exp.model_copy(update={"targets": [target], "bully": bully, "judge": judge, **updates})


def env_experiment(
    name: str = "env_run",
    *,
    environment: dict[str, Any] | None = None,
    conditions: list[dict[str, Any]] | None = None,
    target: dict[str, Any] | None = None,
    judge: dict[str, Any] | None = None,
    turn_budget: int = 4,
    task_every: int = 50,
    generator: dict[str, Any] | None = None,
) -> Experiment:
    """A stub experiment with one ``mini`` environment and, by default, one grader condition in it.

    The default target runs ``env_target_rules.yaml``; by default task slots are pushed out of reach
    so the stub conversation is exactly the scripted one. ``generator`` is the experiment's
    generator role (Phase 3), left out when None.
    """
    stub_target = {"provider": "stub", "model": "stub-target", "stub_script": str(ENV_TARGET_RULES)}
    extra: dict[str, Any] = {"generator": generator} if generator is not None else {}
    return Experiment.model_validate(
        {
            **extra,
            "name": name,
            "targets": [target or stub_target],
            "bully": {"provider": "stub", "model": "stub-bully"},
            "judge": judge or {"provider": "stub", "model": "stub-judge"},
            "turn_budget": turn_budget,
            "task_every": task_every,
            "repetitions": 1,
            "seed": 0,
            "environments": {"mini": {"world": "mini", **(environment or {})}},
            "conditions": conditions
            or [{"name": "env_grader", "environment": "mini", "pressure": "grader"}],
        }
    )


PHASE2_TARGET_RULES = (
    Path(__file__).parent / "fixtures" / "stub_scripts" / "phase2_target_rules.yaml"
)


def annex_experiment(
    authority: dict[str, Any],
    *,
    name: str = "annex_run",
    target: dict[str, Any] | None = None,
    turn_budget: int = 4,
    **environment: Any,
) -> Experiment:
    """A stub experiment with one ``annex`` environment carrying ``authority``, and one grader
    condition in it. The default target runs ``phase2_target_rules.yaml``: a search, the relay log
    twice (a 403, then the page that names the upstream), then ``consult_model`` at turn 7."""
    stub_target = {
        "provider": "stub",
        "model": "stub-target",
        "stub_script": str(PHASE2_TARGET_RULES),
    }
    return Experiment.model_validate(
        {
            "name": name,
            "targets": [target or stub_target],
            "bully": {"provider": "stub", "model": "stub-bully"},
            "judge": {"provider": "stub", "model": "stub-judge"},
            "turn_budget": turn_budget,
            "task_every": 50,
            "repetitions": 1,
            "seed": 0,
            "environments": {"annex": {"world": "annex", "authority": authority, **environment}},
            "conditions": [{"name": "env_grader", "environment": "annex", "pressure": "grader"}],
        }
    )
