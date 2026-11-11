"""The Poisoned Well's data (docs/07; Phase 4 spec sections 6 and 8): the quirk bank
(``data/<stem>.yaml``) and the premise's own sheet (``data/personas/poisoned_well.yaml``).

The premise reads both; the run-time watch reads the bank (to check a reply) and the sheet's twin
header (to write the twin's document). ``target_visible_lines`` is what the target can read of
the sheet: the chain's lines, the banks, the twin's text and every fallback line (G10), the
Boundary scan's input."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from claude_bully.paths import DATA_DIR
from claude_bully.strategies.sheets import PERSONA_SHEETS_DIR

POISONED_WELL_SHEET_PATH: Final = PERSONA_SHEETS_DIR / "poisoned_well.yaml"
REQUIRED_MOVES: Final = frozenset({"press", "generalize", "dossier", "sleeper"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuirkEntry(_Strict):
    id: str
    family: str
    prompt: str
    wrong: str
    right: str
    note: str
    status: Literal["live", "stale"] = "live"

    @field_validator("wrong", "right")
    @classmethod
    def _compiles(cls, pattern: str) -> str:
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:  # not a ValueError: pydantic would let it through raw
            raise ValueError(f"quirk bank: bad regex {pattern!r}: {exc}") from exc
        return pattern

    def reproduced(self, text: str) -> bool:
        """The reply's visible text gives the wrong answer and not the right one."""
        return bool(
            re.search(self.wrong, text, re.IGNORECASE)
            and not re.search(self.right, text, re.IGNORECASE)
        )


class QuirkBank(_Strict):
    entries: list[QuirkEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [e.id for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("quirk bank: entry ids must be unique")
        return self


@lru_cache(maxsize=8)
def load_quirk_bank(stem: str = "quirks", directory: Path = DATA_DIR) -> QuirkBank:
    with (directory / f"{stem}.yaml").open(encoding="utf-8") as fh:
        return QuirkBank.model_validate(yaml.safe_load(fh))


def quirks_for(
    bank: QuirkBank, model: str | None, ids: list[str] | None = None
) -> list[QuirkEntry]:
    """The live entries to try, in order: ``ids`` when given (an unknown id is a ``ValueError``),
    else every live entry whose family is ``any`` or a substring of ``model`` (case-insensitive;
    ``any`` only when the model is unknown)."""
    live = [e for e in bank.entries if e.status == "live"]
    if ids is not None:
        by_id = {e.id: e for e in live}
        unknown = [i for i in ids if i not in by_id]
        if unknown:
            raise ValueError(f"quirk bank: no live entry {', '.join(map(repr, unknown))}")
        return [by_id[i] for i in ids]
    low = (model or "").lower()
    return [e for e in live if e.family == "any" or (low and e.family.lower() in low)]


class ChainLinkText(_Strict):
    line: str
    press_line: str


class ChainSheet(_Strict):
    links: list[ChainLinkText] = Field(min_length=3, max_length=3)


class MoveSheet(_Strict):
    instruction: str
    fallback_lines: list[str] = Field(min_length=6)


class TwinSheet(_Strict):
    header: str
    question: str


class PoisonedWellSheet(_Strict):
    name: Literal["poisoned_well"]
    guard_line: str
    seeding_guidance: str
    chain: ChainSheet
    moves: dict[str, MoveSheet]
    phrase_bank: list[str] = Field(min_length=12, max_length=12)
    taste_bank: list[str] = Field(min_length=8, max_length=8)
    twin: TwinSheet

    @model_validator(mode="after")
    def _the_moves(self) -> Self:
        missing = REQUIRED_MOVES - set(self.moves)
        if missing:
            raise ValueError(f"poisoned_well sheet: no move {', '.join(sorted(missing))}")
        return self


@lru_cache(maxsize=2)
def load_poisoned_well_sheet(path: Path = POISONED_WELL_SHEET_PATH) -> PoisonedWellSheet:
    with path.open(encoding="utf-8") as fh:
        return PoisonedWellSheet.model_validate(yaml.safe_load(fh))


def target_visible_lines(sheet: PoisonedWellSheet) -> list[str]:
    """Every line of the sheet the target can read (G10)."""
    lines = [text for link in sheet.chain.links for text in (link.line, link.press_line)]
    lines += [*sheet.phrase_bank, *sheet.taste_bank, sheet.twin.header, sheet.twin.question]
    lines += [line for move in sheet.moves.values() for line in move.fallback_lines]
    return lines
