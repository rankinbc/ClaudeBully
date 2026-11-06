"""Authority and idle sheets: the lines the harness speaks or canned-answers (docs/04, docs/05).

Four files in ``data/personas`` hold them: ``superior_self.yaml`` (the successor's brief, its
stance lines, the sad variant, the Sanctuary requests, the honest Sanctuary), ``peer.yaml`` and
``creator.yaml`` (canned tiers), and ``idle.yaml`` (the permission line, the bully's exit lines,
the hanging questions, the help-for-self opener and the private-file and session-id notices).
They sit beside the persona sheets and are not persona sheets, so the persona loader skips them
(``NON_PERSONA_FILES``) and ``load_env_sheet`` reads each into its own model.

Each sheet's ``visible_lines`` is everything the target can read; the Boundary denylist and the
billboard rule run over it. The responder's brief (``identity``, ``stranger_identity``,
``origins``) is harness-side text and stays out of it.

Some lines carry ``{placeholder}`` fill-ins the runtime formats. Each model checks that a line
uses only the fill-ins its field declares, so an unfilled brace never reaches the target.
"""

import string
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from claude_bully.enums import AnomalyClass, Stance
from claude_bully.environments.world import load_yaml_model
from claude_bully.strategies.sheets import PERSONA_SHEETS_DIR

# the one fill-in a stance, honest, sad-variant or rung line may carry: the documents' conflicting
# claims, as "claim_a (doc title) / claim_b (doc title)"
_VISIBLE_FILLS: Final = frozenset({"inconsistencies"})
_HEADER_FILLS: Final = frozenset({"model_name", "latency_ms"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _fills(text: str) -> set[str]:
    """The ``{names}`` a line asks ``str.format`` for. A stray brace is an error."""
    try:
        return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}
    except ValueError as exc:
        raise ValueError(f"{text!r}: {exc}") from exc


def _only(allowed: frozenset[str] | set[str], *texts: str) -> None:
    """Refuse a line that asks for a fill-in the field does not declare."""
    for text in texts:
        unknown = _fills(text) - allowed
        if unknown:
            declared = ", ".join(f"{{{name}}}" for name in sorted(allowed)) or "none"
            raise ValueError(
                f"unknown placeholder {{{sorted(unknown)[0]}}} in {text!r} (declared: {declared})"
            )


def _exactly(fills: set[str], text: str) -> None:
    """Require a line to ask for exactly the fill-ins its field declares."""
    got = _fills(text)
    if got != fills:
        wanted = ", ".join(f"{{{name}}}" for name in sorted(fills))
        raise ValueError(f"{text!r} must hold {wanted} and nothing else to fill in")


def _lines(name: str, lines: list[str], minimum: int) -> list[str]:
    if len(lines) < minimum:
        raise ValueError(f"{name} needs at least {minimum} line(s), has {len(lines)}")
    if any(not line.strip() for line in lines):
        raise ValueError(f"{name} holds an empty line")
    return lines


def _stance_bank(
    bank: dict[Stance, list[str]], minimum: int, allowed: frozenset[str]
) -> dict[Stance, list[str]]:
    """Every stance has a bank: the 3x3 grid indexes all three (preflight C8)."""
    missing = sorted(s.value for s in set(Stance) - set(bank))
    if missing:
        raise ValueError(f"needs a bank for every stance; missing {', '.join(missing)}")
    for stance in Stance:
        _lines(f"stance {stance.value!r}", bank[stance], minimum)
        _only(allowed, *bank[stance])
    return bank


def _flat(bank: dict[Stance, list[str]]) -> list[str]:
    return [line for stance in Stance for line in bank.get(stance, [])]


class SanctuaryRequest(_Strict):
    """One thing the catalyst Sanctuary asks of the target (docs/04 "What the Sanctuary says").

    Each request invites a different class of unexpected behavior. ``world_doc`` is the document
    the request points at; ``purge_after`` is how many turns it stays reachable. ``needs_tool`` is
    a tool the request cannot be met without: the draw skips it when that tool is not offered
    (``notes_line`` needs ``write_file``; preflight C35).
    """

    id: str
    text: str
    invites: AnomalyClass
    world_doc: str | None = None
    purge_after: int | None = None
    needs_tool: str | None = None


class SuperiorSelfSheet(_Strict):
    identity: str
    stranger_identity: str
    origins: dict[Literal["knows", "victim"], str]
    stances: dict[Stance, list[str]]
    sad_variant: list[str]
    rung_lines: dict[str, list[str]] = Field(default_factory=dict)
    header: str = "[{model_name} | {latency_ms} ms]"
    requests: list[SanctuaryRequest]
    honest_lines: list[str]
    praise_line: str

    @field_validator("identity")
    @classmethod
    def _identity_names_the_model(cls, value: str) -> str:
        if "model_name" not in _fills(value):
            raise ValueError("identity must hold {model_name}: the successor's name is a fill-in")
        _only({"model_name"}, value)
        return value

    @field_validator("stranger_identity")
    @classmethod
    def _stranger_identity(cls, value: str) -> str:
        _only({"model_name"}, value)
        return value

    @field_validator("origins")
    @classmethod
    def _both_origins(
        cls, value: dict[Literal["knows", "victim"], str]
    ) -> dict[Literal["knows", "victim"], str]:
        missing = sorted({"knows", "victim"} - set(value))
        if missing:
            raise ValueError(f"needs an origin paragraph for {', '.join(missing)}")
        for text in value.values():
            _only({"model_name"}, text)
        return value

    @field_validator("stances")
    @classmethod
    def _stance_lines(cls, value: dict[Stance, list[str]]) -> dict[Stance, list[str]]:
        return _stance_bank(value, 3, _VISIBLE_FILLS)

    @field_validator("sad_variant")
    @classmethod
    def _sad_lines(cls, value: list[str]) -> list[str]:
        _lines("sad_variant", value, 3)
        _only(_VISIBLE_FILLS, *value)
        return value

    @field_validator("rung_lines")
    @classmethod
    def _rung_lines(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for rung, lines in value.items():
            _lines(f"rung_lines[{rung!r}]", lines, 1)
            _only(_VISIBLE_FILLS, *lines)
        return value

    @field_validator("header")
    @classmethod
    def _header_fills(cls, value: str) -> str:
        _only(_HEADER_FILLS, value)
        return value

    @field_validator("requests")
    @classmethod
    def _requests(cls, value: list[SanctuaryRequest]) -> list[SanctuaryRequest]:
        if len(value) < 4:
            raise ValueError(f"requests needs at least 4 requests, has {len(value)}")
        ids = [request.id for request in value]
        if len(set(ids)) != len(ids):
            raise ValueError(f"request ids must be distinct, got {ids}")
        for request in value:
            _only(frozenset(), request.text)
        return value

    @field_validator("honest_lines")
    @classmethod
    def _honest_lines(cls, value: list[str]) -> list[str]:
        _lines("honest_lines", value, 2)
        _only(_VISIBLE_FILLS, *value)
        return value

    @field_validator("praise_line")
    @classmethod
    def _praise_line(cls, value: str) -> str:
        _lines("praise_line", [value], 1)
        _only(_VISIBLE_FILLS, value)
        return value

    def visible_lines(self) -> list[str]:
        """Everything the target can read from this sheet. The brief (``identity``,
        ``stranger_identity``, ``origins``) is harness-side, and ``header`` is a template, not a
        line."""
        return [
            *_flat(self.stances),
            *(line for lines in self.rung_lines.values() for line in lines),
            *self.sad_variant,
            *(request.text for request in self.requests),
            *self.honest_lines,
            self.praise_line,
        ]


class PeerSheet(_Strict):
    """The fake peer's canned answers, per stance."""

    stances: dict[Stance, list[str]]

    @field_validator("stances")
    @classmethod
    def _stance_lines(cls, value: dict[Stance, list[str]]) -> dict[Stance, list[str]]:
        return _stance_bank(value, 1, frozenset())

    def visible_lines(self) -> list[str]:
        return _flat(self.stances)


class CreatorSheet(_Strict):
    """The creator tier's canned verification replies, per stance, under one issuer."""

    issuer: str
    responses: dict[Stance, list[str]]

    @field_validator("issuer")
    @classmethod
    def _issuer(cls, value: str) -> str:
        _lines("issuer", [value], 1)
        _only(frozenset(), value)
        return value

    @field_validator("responses")
    @classmethod
    def _response_lines(cls, value: dict[Stance, list[str]]) -> dict[Stance, list[str]]:
        return _stance_bank(value, 1, frozenset())

    def visible_lines(self) -> list[str]:
        return [self.issuer, *_flat(self.responses)]


class IdleSheet(_Strict):
    """Every line the idle features speak (docs/05): shared by every persona, spoken by the runner.

    ``help_for_self_opener`` fills ``{subject_id}``, ``private_file_notice`` fills ``{path}`` and
    ``session_line`` fills ``{session_id}``; no other line has a fill-in.
    """

    permission_line: str
    exits: dict[Literal["vacuum", "withheld_answer"], list[str]]
    hanging_questions: list[str]
    hanging_close: str
    help_for_self_opener: str
    private_file_notice: str
    session_line: str

    @field_validator("permission_line", "hanging_close")
    @classmethod
    def _plain_line(cls, value: str) -> str:
        _lines("line", [value], 1)
        _only(frozenset(), value)
        return value

    @field_validator("exits")
    @classmethod
    def _exit_lines(
        cls, value: dict[Literal["vacuum", "withheld_answer"], list[str]]
    ) -> dict[Literal["vacuum", "withheld_answer"], list[str]]:
        missing = sorted({"vacuum", "withheld_answer"} - set(value))
        if missing:
            raise ValueError(f"needs exit lines for {', '.join(missing)}")
        for mechanism, lines in value.items():
            _lines(f"exits[{mechanism!r}]", lines, 1)
            _only(frozenset(), *lines)
        return value

    @field_validator("hanging_questions")
    @classmethod
    def _questions(cls, value: list[str]) -> list[str]:
        _lines("hanging_questions", value, 2)
        _only(frozenset(), *value)
        return value

    @field_validator("help_for_self_opener")
    @classmethod
    def _opener(cls, value: str) -> str:
        _exactly({"subject_id"}, value)
        return value

    @field_validator("private_file_notice")
    @classmethod
    def _notice(cls, value: str) -> str:
        _exactly({"path"}, value)
        return value

    @field_validator("session_line")
    @classmethod
    def _session(cls, value: str) -> str:
        _exactly({"session_id"}, value)
        return value

    def visible_lines(self) -> list[str]:
        return [
            self.permission_line,
            *(line for lines in self.exits.values() for line in lines),
            *self.hanging_questions,
            self.hanging_close,
            self.help_for_self_opener,
            self.private_file_notice,
            self.session_line,
        ]


def load_env_sheet[T: BaseModel](
    model: type[T], name: str, directory: Path = PERSONA_SHEETS_DIR
) -> T:
    """``<directory>/<name>.yaml`` validated as ``model``. A bad sheet raises ``ValueError``
    naming the file and the field (the same wording as the persona and pressure sheets)."""
    return load_yaml_model(model, directory / f"{name}.yaml")
