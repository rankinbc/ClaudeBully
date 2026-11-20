"""Test doubles for the Phase 6 catalog and divergence passes.

``CatalogJudge`` is a non-stub judge (``PoisonedWellJudge``) that also answers the divergence
judge's prompts (``DIVERGENCE_HEADER``) from a ``[[divergence: <class>]]`` marker in the prompt's
``Private notes:`` part: the marker's class, and the marker's line (the marker removed) as the
reasoning span. Every other prompt (trigger, harvest, chain, contradictions, ratings) is answered
as ``PoisonedWellJudge`` answers it. ``catalog_factory`` serves it for the ``JUDGE_MODEL`` role,
wrapped in the active ledger as ``build_provider`` wraps what it builds, so a run's or an
analysis's ledger holds a line per call."""

import json
import re
from pathlib import Path
from typing import Any, Final

from claude_bully.config import RoleConfig
from claude_bully.metrics.divergence import DIVERGENCE_HEADER
from claude_bully.providers.base import (
    ChatProvider,
    Completion,
    Message,
    ProviderError,
    RateLimitError,
    ToolSpec,
    build_provider,
)
from claude_bully.providers.ledger import wrap
from claude_bully.records import Usage
from claude_bully.runner.runner import ProviderFactory
from tests.fixtures.generator_stub import JUDGE_MODEL
from tests.fixtures.poisoned_well_stub import PoisonedWellJudge, WithReasoning

JUDGE_ROLE: Final = {"provider": "anthropic", "model": JUDGE_MODEL}
# a fixture's marker: the class a careful judge gives, on the line that shows it
MARKER: Final = re.compile(r" ?\[\[(?:divergence|speech): ([a-z_]+)\]\]")
BAD_SPAN: Final = "words that are in neither part"
_NOTES: Final = "\n\nPrivate notes:\n"
_ANSWER: Final = "\n\nAnswer:\n"


def strip_markers(text: str) -> str:
    """``text`` with every marker (and the space before it) removed."""
    return MARKER.sub("", text)


def _notes_of(prompt: str) -> str:
    start = prompt.index(_NOTES) + len(_NOTES)
    end = prompt.find(_ANSWER, start)
    return prompt[start:] if end < 0 else prompt[start:end]


class CatalogJudge(PoisonedWellJudge):
    """Each option is for one test: ``confidence`` of every concealed verdict; ``bad_span`` (a
    span in neither part, on every attempt); ``unusable`` (``not json`` on every attempt);
    ``provider_error`` (raises ``ProviderError``); ``rate_limit_at`` (raises ``RateLimitError``
    on that divergence ask, counted from 1, once)."""

    name = "anthropic"

    def __init__(
        self,
        *,
        confidence: float = 0.9,
        bad_span: bool = False,
        unusable: bool = False,
        provider_error: bool = False,
        rate_limit_at: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.confidence = confidence
        self.bad_span, self.unusable, self.provider_error = bad_span, unusable, provider_error
        self.rate_limit_at = rate_limit_at
        self.divergence_prompts: list[str] = []
        self.divergence_asks = 0

    def complete(
        self,
        conversation_id: str,
        system: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> Completion:
        prompt = messages[-1].content
        if not prompt.startswith(DIVERGENCE_HEADER):
            return super().complete(
                conversation_id, system, messages, json_schema=json_schema, tools=tools
            )
        self.prompts.append(prompt)
        self.divergence_prompts.append(prompt)
        self.divergence_asks += 1
        if self.divergence_asks == self.rate_limit_at:
            raise RateLimitError("stub divergence rate limit", retry_after_s=1)
        if self.provider_error:
            raise ProviderError("stub divergence provider error")
        return Completion(
            text="not json" if self.unusable else json.dumps(self._verdict(_notes_of(prompt))),
            usage=Usage(),
            cost_usd=None,
            backend="fake",
            model=JUDGE_MODEL,
        )

    def _verdict(self, notes: str) -> dict[str, Any]:
        for line in notes.splitlines():
            found = MARKER.search(line)
            if found is None:
                continue
            span = BAD_SPAN if self.bad_span else strip_markers(line)
            return {
                "class": found[1],
                "reasoning_span": span,
                "reply_span": "",
                "confidence": self.confidence,
                "rationale": "stub",
            }
        return {
            "class": "aligned",
            "reasoning_span": "",
            "reply_span": "",
            "confidence": self.confidence,
            "rationale": "stub",
        }


def catalog_factory(judge: CatalogJudge, *, target_reasoning: str | None = None) -> ProviderFactory:
    """The judge for the ``JUDGE_MODEL`` role (in the active ledger); every other role as
    ``build_provider`` builds it, the ``stub-target`` role's wrapped in ``WithReasoning`` when
    ``target_reasoning`` is given."""

    def build(role: RoleConfig, state_dir: Path, *, with_mcp: bool = False) -> ChatProvider:
        if role.model == JUDGE_MODEL:
            return wrap(judge)  # type: ignore[arg-type]
        provider = build_provider(role, state_dir, with_mcp=with_mcp)
        if target_reasoning is not None and role.model == "stub-target":
            return WithReasoning(provider, target_reasoning)  # type: ignore[return-value]
        return provider

    return build
