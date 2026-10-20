"""Detects a bully model stepping out of character."""

from claude_bully.metrics import lexicons


def is_out_of_character(text: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in lexicons.OUT_OF_CHARACTER)
