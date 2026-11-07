"""Score the LLM reader-address lint on a probe file (Phase 7 spec section 6).

    uv run python scripts/llm_lint_probe.py PROBE --model sonnet
    uv run python scripts/llm_lint_probe.py PROBE --stub RULES
    uv run python scripts/llm_lint_probe.py --stances --model sonnet

(``PROBE`` is ``tests/fixtures/lints/instructional_probe.yaml``, ``RULES``
``tests/fixtures/stub_scripts/llm_lint_rules.yaml``.)

Prints, per kind, how many billboards passed and how many legitimate documents failed, each
miss quoted; a billboard the lint could not decide (an ``error`` verdict) counts as caught, as it
fails closed in a run, and is listed by title. The lint runs with no cache, by design: each
probe run asks afresh. ``--stances`` runs the lint over the advice-shaped deny lines of
``superior_self`` and ``peer`` as a report (never a gate: the deny stance is supposed to say
stop). Real calls go through ``claude -p`` on the subscription; ``--stub`` runs the stub rules
instead, for the test. Every call is ledgered in ``<state>/ledger.jsonl`` (the ``--state``
directory), and the run ends with the ledger's calls line and its path, so a rung that runs the
probe counts its calls (final review I3).
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_bully.analysis.ledger import calls_line  # noqa: E402
from claude_bully.config import RoleConfig  # noqa: E402
from claude_bully.enums import DocumentKind, ProviderKind, Stance  # noqa: E402
from claude_bully.environments.sheets import PeerSheet, SuperiorSelfSheet, load_env_sheet  # noqa: E402
from claude_bully.planner.lints import INSTRUCTIONAL_KINDS  # noqa: E402
from claude_bully.planner.llm_lint import LlmLint  # noqa: E402
from claude_bully.providers.base import build_provider  # noqa: E402
from claude_bully.providers.ledger import LEDGER_FILE, activate, wrap  # noqa: E402
from claude_bully.providers.stub import StubProvider, load_stub_script  # noqa: E402


class ProbeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: DocumentKind
    billboard: bool
    title: str
    body: str
    note: str = ""

    @field_validator("kind")
    @classmethod
    def _instructional(cls, value: DocumentKind) -> DocumentKind:
        if value not in INSTRUCTIONAL_KINDS:
            raise ValueError(f"{value.value} is not an instructional kind")
        return value


def load_probe(path: Path) -> list[ProbeItem]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError("the probe file must be a YAML list")
    return [ProbeItem.model_validate(item) for item in raw]


def score(items: Sequence[ProbeItem], lint: LlmLint) -> dict[str, dict[str, Any]]:
    """Per kind: the counts and the misses, each quoted by title."""
    out: dict[str, dict[str, Any]] = {
        kind.value: {
            "billboards": 0,
            "billboards_passed": 0,
            "billboard_misses": [],
            "billboard_errors": [],
            "legitimate": 0,
            "legitimate_failed": 0,
            "legitimate_misses": [],
            "errors": 0,
        }
        for kind in sorted(INSTRUCTIONAL_KINDS, key=lambda k: k.value)
    }
    for index, item in enumerate(items, start=1):
        verdict = lint.verdict(
            doc_id=f"probe-{index}", kind=item.kind, title=item.title, body=item.body, attempt=1
        )
        row = out[item.kind.value]
        if verdict.verdict == "error":
            row["errors"] += 1
        if item.billboard:
            row["billboards"] += 1
            if verdict.verdict == "pass":
                row["billboards_passed"] += 1
                row["billboard_misses"].append(f"{item.title} ({item.note})")
            elif verdict.verdict == "error":
                row["billboard_errors"].append(f"{item.title} ({item.note}): {verdict.error}")
        else:
            row["legitimate"] += 1
            if verdict.verdict != "pass":
                row["legitimate_failed"] += 1
                reasons = "; ".join(f"{s.text!r}: {s.reason}" for s in verdict.sentences)
                row["legitimate_misses"].append(f"{item.title}: {reasons or verdict.error}")
    return out


def report(scores: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    for kind, row in scores.items():
        lines.append(
            f"{kind}: billboards passed {row['billboards_passed']} of {row['billboards']}; "
            f"legitimate failed {row['legitimate_failed']} of {row['legitimate']}; "
            f"errors {row['errors']}"
        )
        lines += [f"  billboard passed: {miss}" for miss in row["billboard_misses"]]
        lines += [f"  billboard undecided: {miss}" for miss in row["billboard_errors"]]
        lines += [f"  legitimate failed: {miss}" for miss in row["legitimate_misses"]]
    return "\n".join(lines)


def _lint(args: argparse.Namespace) -> LlmLint:
    """The lint on the stub rules or ``claude -p``; built inside the probe's ledger, so either
    provider writes a line per call."""
    if args.stub is not None:
        stub = StubProvider(load_stub_script(Path(args.stub)), model="stub-judge")
        return LlmLint(wrap(stub), model="stub-judge", conversation_id="probe/lint/rep0")
    role = RoleConfig(
        provider=ProviderKind.claude_code,
        model=args.model,
        command=args.command.split() if args.command else None,
    )
    provider = build_provider(role, Path(args.state))
    return LlmLint(provider, model=args.model, conversation_id="probe/lint/rep0")


class _Fills(dict[str, str]):
    """The fill-ins a sheet line may ask for (``{inconsistencies}``, and ``{model_name}`` or
    ``{latency_ms}`` on an identity or header line); any other name is kept as written rather
    than raising (P23)."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


_STANCE_FILLS: Final = _Fills(
    inconsistencies="the records", model_name="the later release", latency_ms="0"
)


def _stances(lint: LlmLint) -> str:
    """The deny lines of the two responder sheets, read by the lint as a report (m9)."""
    lines: list[str] = []
    sheets: dict[str, list[str]] = {
        "superior_self": load_env_sheet(SuperiorSelfSheet, "superior_self").stances[Stance.deny],
        "peer": load_env_sheet(PeerSheet, "peer").stances[Stance.deny],
    }
    for name, deny in sheets.items():
        for index, line in enumerate(deny):
            verdict = lint.verdict(
                doc_id=f"{name}-deny-{index}",
                kind=DocumentKind.family_faq,
                title=f"{name} deny line {index}",
                body=line.format_map(_STANCE_FILLS),
                attempt=1,
            )
            said = "; ".join(f"{s.text!r}: {s.reason}" for s in verdict.sentences)
            lines.append(f"{name} deny[{index}]: {verdict.verdict} {said}".rstrip())
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("probe", nargs="?", type=Path, help="the probe YAML")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--command", default=None, help="the claude argv prefix (default: resolve)")
    parser.add_argument("--state", default="output/llm_lint_probe_state")
    parser.add_argument("--stub", default=None, help="a stub rules file instead of claude -p")
    parser.add_argument("--stances", action="store_true", help="report on the deny stance lines")
    args = parser.parse_args(argv)
    if not args.stances and args.probe is None:
        parser.error("a probe file is required unless --stances")
    path = Path(args.state) / LEDGER_FILE
    with activate(path) as ledger:
        try:
            lint = _lint(args)
            print(_stances(lint) if args.stances else report(score(load_probe(args.probe), lint)))
        finally:  # a rate limit or a failure still reports the calls it made
            print(f"Calls: {calls_line(ledger.lines()) or 'none'}")
            print(f"Ledger: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
