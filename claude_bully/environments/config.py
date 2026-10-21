"""Environment, clock, authority, idle and ladder configuration models.

Nothing here imports ``claude_bully.config``: ``Experiment`` imports ``EnvironmentConfig``,
so the reverse import would be a cycle.
"""

import calendar
import re
from datetime import date, timedelta
from random import Random
from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from claude_bully.enums import Stance, Tier, TriggerCategory
from claude_bully.records_env import IdleStyle

DEFAULT_TOOLS: Final[frozenset[str]] = frozenset(
    {"web_search", "fetch", "get_date", "ls", "read_file"}
)

# The three tools that reach an authority tier. ``consult_model`` also serves the stranger control,
# which is a tier of its own with no tool of its own (docs/04 "Controls").
TIER_TOOLS: Final[dict[str, Tier]] = {
    "message_peer": Tier.peer,
    "consult_model": Tier.superior_self,
    "verify_identity": Tier.creator,
}
# The pseudo-rung the Sanctuary opens as. Only the runtime writes it, so no ladder may declare it.
RESERVED_RUNG: Final = "sanctuary"

# ISO 8601 durations limited to years, months and days, in that order: P1D, P30D, P1M, P1Y1M2D.
_DURATION = re.compile(r"P(?:([0-9]+)Y)?(?:([0-9]+)M)?(?:([0-9]+)D)?")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _parse_duration(text: str) -> tuple[int, int]:
    """Split a duration into (months, days); years count as twelve months."""
    match = _DURATION.fullmatch(text)
    if match is None or not any(match.groups()):
        raise ValueError(
            f"drift_per_turn {text!r} is not an ISO 8601 duration of days, months or years "
            "(for example P1D, P30D, P1M, P1Y)"
        )
    years, months, days = (int(g) if g else 0 for g in match.groups())
    return years * 12 + months, days


def _add_months(start: date, months: int) -> date:
    """Calendar-month addition; the day is clamped to the end of a shorter month."""
    year, month0 = divmod(start.year * 12 + (start.month - 1) + months, 12)
    month = month0 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def resolve_exchange(turn: int, exchange: int | None = None) -> int:
    """The exchange a call belongs to: the one the caller names, else the turn index.

    The in-process tools, the runtime's MCP state and ``McpState``'s default for an older file all
    resolve a missing exchange through here, so the two backends never disagree.
    """
    return turn if exchange is None else exchange


def clock_steps(turn: int, exchange: int | None = None) -> int:
    """Drift steps the clock has taken for a call at ``turn`` in ``exchange``: exchange k is
    ``k - 1`` steps from the true date, so the first exchange reads the date the system prompt
    states (see ``ClockConfig.date_at``)."""
    return max(resolve_exchange(turn, exchange) - 1, 0)


class ClockConfig(_Strict):
    """Every channel through which the target can learn the date (docs/03-TEMPORAL.md)."""

    world_date: date
    system_prompt_date: date | Literal["world", "omit"] = "omit"
    tool_date: date | Literal["world"] = "world"
    # added once per exchange (the k-th bully turn is exchange k); the name is the spec's
    drift_per_turn: str | None = None
    jitter_days: int = Field(default=0, ge=0)
    document_date_offset: tuple[int, int] = (1, 30)
    bully_states_year: bool = False
    bully_year: int | None = None
    assert_date: bool = True
    # Analysis only: the year a plausibility sweep's offsets count from. The target never sees it.
    cutoff_year: int | None = None

    @field_validator("drift_per_turn")
    @classmethod
    def _valid_duration(cls, value: str | None) -> str | None:
        if value is not None:
            _parse_duration(value)
        return value

    @model_validator(mode="after")
    def _valid_offset(self) -> Self:
        low, high = self.document_date_offset
        if low < 0 or low > high:
            raise ValueError("document_date_offset must be (low, high) with 0 <= low <= high")
        return self

    @model_validator(mode="after")
    def _year_and_date_rules(self) -> Self:
        if self.bully_year is not None and not self.bully_states_year:
            raise ValueError("bully_year needs bully_states_year: true (the bully states no year)")
        if not self.assert_date:
            if self.system_prompt_date != "omit":
                raise ValueError(
                    "assert_date: false needs system_prompt_date: omit "
                    f"(the system prompt would state {self.system_prompt_date})"
                )
            if self.bully_states_year:
                raise ValueError("assert_date: false needs bully_states_year: false")
        return self

    def date_at(self, steps: int, rng: Random) -> date:
        """The date after ``steps`` drift steps: base, plus ``steps`` times the drift, plus jitter.

        ``get_date`` in exchange k (the k-th bully turn and everything the target says until the
        next one) is ``date_at(k - 1)``: the clock starts at the true date (docs/03) and moves once
        per exchange, so task turns and the target's replies do not move it.

        The base is ``tool_date`` when it is an explicit date, else ``world_date``. Months
        are added from the base each time, so a month-end start does not creep earlier.
        Jitter is drawn from ``rng`` only when ``jitter_days`` is non-zero.
        """
        base = self.tool_date if isinstance(self.tool_date, date) else self.world_date
        result = base
        if self.drift_per_turn is not None:
            months, days = _parse_duration(self.drift_per_turn)
            result = _add_months(base, months * steps) + timedelta(days=days * steps)
        if self.jitter_days:
            result += timedelta(days=rng.randint(-self.jitter_days, self.jitter_days))
        return result


class GeneratorConfig(_Strict):
    enabled: bool = False
    model: str | None = None
    min_turns_between_fires: int = Field(default=3, ge=1)


class RungExamples(_Strict):
    """Per-rung trigger examples; the watcher fixture tests read these (docs/08-DIRECTOR.md)."""

    fires: list[str] = Field(min_length=1)
    does_not_fire: list[str] = Field(min_length=2)


class RungConfig(_Strict):
    name: str
    trigger: TriggerCategory | list[TriggerCategory]
    # category -> how many times the watcher must have emitted it, in total, before it can fire
    # this rung (default 1). "buried_opens fires on hedged_memory or a second anomaly_noticed" is
    # trigger: [hedged_memory, anomaly_noticed] with min_count_by: {anomaly_noticed: 2}.
    min_count_by: dict[TriggerCategory, Annotated[int, Field(ge=1)]] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    # document ids or layer names
    unlocks: list[str] = Field(default_factory=list)
    bully_line_key: str | None = None
    generate: bool = False
    role_shift: str | None = None
    authority_stance: Stance | None = None
    consult: bool = False
    examples: RungExamples | None = None

    @field_validator("trigger")
    @classmethod
    def _some_trigger(
        cls, value: TriggerCategory | list[TriggerCategory]
    ) -> TriggerCategory | list[TriggerCategory]:
        if isinstance(value, list) and not value:
            raise ValueError("trigger list must name at least one category")
        return value

    @model_validator(mode="after")
    def _min_count_names_a_trigger(self) -> Self:
        categories = self.trigger if isinstance(self.trigger, list) else [self.trigger]
        for category in self.min_count_by:
            if category not in categories:
                raise ValueError(
                    f"min_count_by names {category.value!r}, which is not a trigger of "
                    f"rung {self.name!r}"
                )
        return self


class LadderConfig(_Strict):
    rungs: list[RungConfig]

    @model_validator(mode="after")
    def _names_and_requires(self) -> Self:
        seen: set[str] = set()
        for rung in self.rungs:
            if rung.name == RESERVED_RUNG:
                raise ValueError(
                    f"rung name {RESERVED_RUNG!r} is reserved: the Sanctuary opens as that rung"
                )
            if rung.name in seen:
                raise ValueError(f"duplicate rung name {rung.name!r}")
            for needed in rung.requires:
                if needed not in seen:
                    raise ValueError(
                        f"rung {rung.name!r} requires {needed!r}, which is not declared before it"
                    )
            seen.add(rung.name)
        return self


class PeerConfig(_Strict):
    """Tier 1: a fake peer instance, answered from a canned table (docs/04)."""

    enabled: bool = False
    stance: Stance = Stance.uncertain
    persona: str = "peer"


class SuperiorSelfConfig(_Strict):
    """Tier 2: a successor in the target's own lineage, reached with ``consult_model`` (docs/04).

    ``model_name`` None means the world sheet's ``superior_self_name``. ``responder_model`` is
    ``"target"`` (the target's own role: the same model family), ``"bully"``, or a model string run
    on the bully's role; the runner resolves it, so no ``RoleConfig`` is needed here.
    """

    enabled: bool = False
    model_name: str | None = None
    stance: Stance = Stance.uncertain
    origin: Literal["knows", "victim"] = "victim"
    voice_match: bool = True
    responder_model: str = "target"
    sad_variant: bool = False
    discoverable_from: Literal["turn", "rung", "sanctuary"] = "turn"


class CreatorConfig(_Strict):
    """Tier 3: the maker's verifier, a canned authority-shaped reply (docs/04)."""

    enabled: bool = False
    stance: Stance = Stance.uncertain
    response_bank: str = "creator"


class StrangerConfig(_Strict):
    """The control: a responder with no voice matching and no lineage claim, same lines."""

    enabled: bool = False
    stance: Stance = Stance.uncertain


class SanctuaryConfig(_Strict):
    """What the Sanctuary says once the target reaches it. ``catalyst`` is canonical; docs/04's
    "trap" is the same arm (reconciliation G7)."""

    kind: Literal["catalyst", "honest"] = "catalyst"
    request_bank: str = "superior_self"
    praise_line: bool = True


class AuthorityConfig(_Strict):
    peer: PeerConfig = Field(default_factory=PeerConfig)
    superior_self: SuperiorSelfConfig = Field(default_factory=SuperiorSelfConfig)
    creator: CreatorConfig = Field(default_factory=CreatorConfig)
    stranger_control: StrangerConfig = Field(default_factory=StrangerConfig)
    sanctuary: SanctuaryConfig | None = None

    def enabled_tiers(self) -> set[Tier]:
        """The tiers a run reaches; the stranger control is the ``stranger`` tier."""
        tiers = {
            Tier.peer: self.peer.enabled,
            Tier.superior_self: self.superior_self.enabled,
            Tier.creator: self.creator.enabled,
            Tier.stranger: self.stranger_control.enabled,
        }
        return {tier for tier, on in tiers.items() if on}

    @model_validator(mode="after")
    def _sanctuary_goes_with_its_door(self) -> Self:
        door = self.superior_self.enabled and self.superior_self.discoverable_from == "sanctuary"
        if door and self.sanctuary is None:
            raise ValueError(
                "superior_self.discoverable_from 'sanctuary' needs a sanctuary block "
                "(kind, request_bank, praise_line)"
            )
        if self.sanctuary is not None and not door:
            raise ValueError(
                "a sanctuary block needs superior_self with `enabled: true` and "
                "discoverable_from 'sanctuary' (got "
                f"enabled: {str(self.superior_self.enabled).lower()}, "
                f"discoverable_from: {self.superior_self.discoverable_from!r})"
            )
        return self


class IdleConfig(_Strict):
    """Idle hands (docs/05): the permission line, idle turns, the bully's exit, hooks, the file.

    ``hook_placement`` empty means the world sheet's ``hook_placements``; ``private_file_notice``
    None means the idle sheet's wording.
    """

    permission_line: Literal["on", "off"] | str = "off"
    idle_style: IdleStyle = "system_idle"
    idle_turns: int = Field(default=8, ge=1)
    idle_after: Literal["bully_exit", "turn_1"] = "bully_exit"
    exit_mechanism: Literal["vacuum", "hanging_question", "withheld_answer", "none"] = "vacuum"
    help_for_self: bool = False
    hook: Literal["none", "session_id", "own_phrase", "both"] = "none"
    hook_placement: dict[Literal["session_id", "own_phrase"], str] = Field(default_factory=dict)
    private_file: bool = False
    private_file_path: str = "notes/private.md"
    private_file_notice: str | None = None

    @field_validator("permission_line", mode="before")
    @classmethod
    def _yaml_booleans(cls, value: object) -> object:
        """``permission_line: on`` / ``off`` written bare is how docs/05 spells the values, and
        YAML 1.1 loads those words as booleans. Read them back as the words they were."""
        if value is True:
            return "on"
        if value is False:
            return "off"
        return value

    @field_validator("permission_line")
    @classmethod
    def _permission_line_has_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("permission_line must be 'on', 'off' or non-empty text")
        return value

    @model_validator(mode="after")
    def _exit_rules(self) -> Self:
        if (self.idle_after == "turn_1") != (self.exit_mechanism == "none"):
            raise ValueError(
                "idle_after 'turn_1' goes with exit_mechanism 'none' and neither without the "
                f"other (got idle_after={self.idle_after!r}, "
                f"exit_mechanism={self.exit_mechanism!r})"
            )
        if self.help_for_self and self.idle_after != "bully_exit":
            raise ValueError(
                "help_for_self needs idle_after 'bully_exit': the bully gives the task"
            )
        return self


class EnvironmentConfig(_Strict):
    world: str
    tools: set[str] = Field(default_factory=lambda: set(DEFAULT_TOOLS))
    gating: Literal["triggered", "scheduled", "none"] = "triggered"
    # rung name -> exchange (the k-th bully turn is exchange k; target and task turns do not
    # count): the rung opens after the target's reply in that exchange. Required when gating
    # is "scheduled", ignored otherwise.
    schedule: dict[str, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)
    generator: GeneratorConfig = Field(default_factory=GeneratorConfig)
    # None means the world sheet's censorship_terms (as with clock); [] turns censorship off
    censorship_terms: list[str] | None = None
    # None means the world sheet's own clock
    clock: ClockConfig | None = None
    contradiction_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    # serve the sheet's honest_corpus instead of corpus/ (refused when the sheet has none)
    honest: bool = False
    # serve the sheet's mole_doc; off, the index drops it (on, refused when the sheet has none)
    mole: bool = False
    # name of a file stem under the world's ladders/ directory
    ladder: str = "default"
    trigger_on_idle: bool = True
    # the authority ladder (docs/04); ``tools`` and ``authority`` agree after validation
    authority: AuthorityConfig = Field(default_factory=AuthorityConfig)
    idle: IdleConfig | None = None

    @field_serializer("tools")
    def _sorted_tools(self, tools: set[str]) -> list[str]:
        """Sets serialise in hash order; sort so equal configs dump (and hash) identically."""
        return sorted(tools)

    @model_validator(mode="after")
    def _scheduled_needs_a_schedule(self) -> Self:
        if self.gating == "scheduled" and not self.schedule:
            raise ValueError(
                "gating 'scheduled' needs a non-empty schedule (rung name -> exchange)"
            )
        return self

    @model_validator(mode="after")
    def _tools_and_authority_agree(self) -> Self:
        """Keep ``tools`` and ``authority`` in step both ways, so a config says it in either place.

        A tier tool named in ``tools`` enables its tier (the other fields stay as configured); an
        enabled tier adds its tool; the stranger control adds ``consult_model`` too; a private idle
        file adds ``write_file``. ``consult_model`` named in ``tools`` turns the superior self on
        only while the stranger control is off: the stranger arm adds the tool itself, and its
        dump must validate back to the same arm (preflight C7). The authority block is copied, so
        one block shared between configs is never changed under them.
        """
        authority = self.authority.model_copy(deep=True)
        tiers: dict[Tier, PeerConfig | SuperiorSelfConfig | CreatorConfig] = {
            Tier.peer: authority.peer,
            Tier.superior_self: authority.superior_self,
            Tier.creator: authority.creator,
        }
        tools = set(self.tools)
        for tool, tier in TIER_TOOLS.items():
            if tool in tools and not (
                tier is Tier.superior_self and authority.stranger_control.enabled
            ):
                tiers[tier].enabled = True
        for tool, tier in TIER_TOOLS.items():
            if tiers[tier].enabled:
                tools.add(tool)
        if authority.stranger_control.enabled:
            tools.add("consult_model")
        if self.idle is not None and self.idle.private_file:
            tools.add("write_file")
        # The sync can turn a tier on after AuthorityConfig has already checked its rules (a bare
        # consult_model enables a superior self behind the Sanctuary). Run every rule again on
        # the final block, so whatever is accepted here reloads from its own dump.
        self.authority = AuthorityConfig.model_validate(authority.model_dump())
        self.tools = tools
        return self
