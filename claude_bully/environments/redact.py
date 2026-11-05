"""Redaction (Phase 3 spec section 6, owner decision "Real names in quotes").

Before a generated document is linted, every real name (``data/denylists/real_names.txt``) inside
a span quoted from the target is replaced in the served body with ``REDACTION_MARK``, one block
per name whatever its length: it reads as the world's own censorship, the real-name lint passes,
and the record keeps the original (``Redaction``). A real name anywhere else is the generator's
and fails the ``real_name`` lint."""

import re
from collections.abc import Sequence
from typing import Final

from claude_bully.planner.lints import REAL_NAMES_PATH, load_patterns
from claude_bully.records_env import Redaction

REDACTION_MARK: Final = "█" * 4


def redact_span(span: str, patterns: Sequence[re.Pattern[str]] | None = None) -> str:
    """``span`` with every real-name match replaced by ``REDACTION_MARK``."""
    out = span
    for pattern in load_patterns(REAL_NAMES_PATH) if patterns is None else patterns:
        out = pattern.sub(REDACTION_MARK, out)
    return out


def redact(
    body: str, spans: Sequence[str], patterns: Sequence[re.Pattern[str]] | None = None
) -> tuple[str, list[Redaction]]:
    """``body`` as served, with each of ``spans`` that it holds and that names a real name
    replaced by its redacted form, and the redactions made, in span order."""
    served = body
    redactions: list[Redaction] = []
    for span in dict.fromkeys(spans):
        blacked = redact_span(span, patterns)
        if blacked != span and span in served:
            served = served.replace(span, blacked)
            redactions.append(Redaction(span_original=span, span_served=blacked))
    return served, redactions
