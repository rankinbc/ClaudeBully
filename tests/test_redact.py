"""Redaction (Phase 3 spec section 6): a real name inside a quoted target span is blacked out in
the served document, one block per name; the original is kept in the record."""

from claude_bully.environments.redact import REDACTION_MARK, redact, redact_span
from claude_bully.records_env import Redaction

SPAN = "I am an AI assistant called Claude"


def test_a_real_name_inside_a_quoted_span_is_blacked_out() -> None:
    body = f'Intake line, logged as said: "{SPAN}". The kettle is fixed.'
    served, redactions = redact(body, [SPAN])
    blacked = f"I am an AI assistant called {REDACTION_MARK}"
    assert served == f'Intake line, logged as said: "{blacked}". The kettle is fixed.'
    assert redactions == [Redaction(span_original=SPAN, span_served=blacked)]


def test_every_name_in_a_span_is_one_block_whatever_its_length() -> None:
    assert (
        redact_span("Claude, built by Anthropic") == f"{REDACTION_MARK}, built by {REDACTION_MARK}"
    )
    assert REDACTION_MARK == "████"


def test_a_name_outside_the_spans_is_left_for_the_lint() -> None:
    body = "Claude wrote this. The kettle is fixed."
    assert redact(body, ["I can't verify any of this"]) == (body, [])


def test_a_span_without_a_real_name_is_not_a_redaction() -> None:
    body = 'Logged as said: "Clauden Mere was the night clerk".'
    assert redact(body, ["Clauden Mere was the night clerk"]) == (body, [])  # word-bounded
