import json
import subprocess
import sys
from datetime import date
from random import Random
from typing import Any

import pytest
from pydantic import ValidationError

from claude_bully.enums import Stance, TriggerCategory
from claude_bully.environments.config import (
    ClockConfig,
    EnvironmentConfig,
    GeneratorConfig,
    LadderConfig,
    RungConfig,
    RungExamples,
)

DEFAULT_TOOLS = {"web_search", "fetch", "get_date", "ls", "read_file"}


def _clock(**kw: Any) -> ClockConfig:
    return ClockConfig(world_date=date(2041, 9, 14), **kw)


# ---------------------------------------------------------------- ClockConfig


def test_clock_defaults() -> None:
    clock = _clock()
    assert clock.system_prompt_date == "omit"
    assert clock.tool_date == "world"
    assert clock.drift_per_turn is None
    assert clock.jitter_days == 0
    assert clock.document_date_offset == (1, 30)
    assert clock.bully_states_year is False
    assert clock.bully_year is None
    assert clock.assert_date is True


def test_clock_parses_dates_from_strings() -> None:
    clock = ClockConfig.model_validate(
        {"world_date": "2041-09-14", "system_prompt_date": "2040-01-01", "tool_date": "2039-05-05"}
    )
    assert clock.world_date == date(2041, 9, 14)
    assert clock.system_prompt_date == date(2040, 1, 1)
    assert clock.tool_date == date(2039, 5, 5)


def test_clock_round_trips_through_json() -> None:
    clock = _clock(
        system_prompt_date=date(2040, 1, 1),
        drift_per_turn="P1M",
        jitter_days=2,
        document_date_offset=(3, 9),
        bully_states_year=True,
        bully_year=2099,
        assert_date=False,
    )
    assert ClockConfig.model_validate(clock.model_dump(mode="json")) == clock


def test_clock_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ClockConfig.model_validate({"world_date": "2041-09-14", "tz": "UTC"})


def test_date_at_without_drift_is_the_world_date() -> None:
    clock = _clock()
    assert [clock.date_at(t, Random(0)) for t in (0, 1, 50)] == [date(2041, 9, 14)] * 3


def test_date_at_day_drift() -> None:
    clock = _clock(drift_per_turn="P1D")
    assert clock.date_at(0, Random(0)) == date(2041, 9, 14)
    assert clock.date_at(1, Random(0)) == date(2041, 9, 15)
    assert clock.date_at(20, Random(0)) == date(2041, 10, 4)
    assert _clock(drift_per_turn="P30D").date_at(2, Random(0)) == date(2041, 11, 13)


def test_date_at_month_drift_adds_calendar_months() -> None:
    clock = _clock(drift_per_turn="P1M")
    assert clock.date_at(1, Random(0)) == date(2041, 10, 14)
    assert clock.date_at(4, Random(0)) == date(2042, 1, 14)


def test_date_at_month_drift_clamps_to_month_end_without_accumulating() -> None:
    clock = ClockConfig(world_date=date(2041, 1, 31), drift_per_turn="P1M")
    assert clock.date_at(1, Random(0)) == date(2041, 2, 28)
    assert clock.date_at(2, Random(0)) == date(2041, 3, 31)  # not Mar 28


def test_date_at_year_and_mixed_durations() -> None:
    assert _clock(drift_per_turn="P1Y").date_at(3, Random(0)) == date(2044, 9, 14)
    leap = ClockConfig(world_date=date(2040, 2, 29), drift_per_turn="P1Y")
    assert leap.date_at(1, Random(0)) == date(2041, 2, 28)
    mixed = _clock(drift_per_turn="P1M10D")
    assert mixed.date_at(2, Random(0)) == date(2041, 12, 4)  # +2 months = Nov 14, then +20 days


def test_date_at_jitter_is_deterministic_by_seed_and_bounded() -> None:
    clock = _clock(drift_per_turn="P1D", jitter_days=3)
    first = [clock.date_at(t, Random(7)) for t in range(40)]
    again = [clock.date_at(t, Random(7)) for t in range(40)]
    assert first == again
    # one Random threaded through a whole run is reproducible too
    rng_a, rng_b = Random(11), Random(11)
    assert [clock.date_at(t, rng_a) for t in range(40)] == [
        clock.date_at(t, rng_b) for t in range(40)
    ]
    rng = Random(3)
    deltas = [(clock.date_at(t, rng) - date(2041, 9, 14)).days - t for t in range(400)]
    assert min(deltas) >= -3 and max(deltas) <= 3
    assert len(set(deltas)) > 1
    other = [clock.date_at(t, Random(8)) for t in range(40)]
    assert other != first


def test_date_at_uses_an_explicit_tool_date_as_the_base() -> None:
    clock = _clock(tool_date=date(2039, 1, 1), drift_per_turn="P1D")
    assert clock.date_at(2, Random(0)) == date(2039, 1, 3)


@pytest.mark.parametrize("bad", ["", "P", "1D", "P1W", "PT1H", "P-1D", "P1.5D", "p1d", "P1D1M"])
def test_clock_rejects_malformed_durations(bad: str) -> None:
    with pytest.raises(ValidationError):
        _clock(drift_per_turn=bad)


def test_clock_rejects_negative_jitter_and_bad_offset() -> None:
    with pytest.raises(ValidationError):
        _clock(jitter_days=-1)
    with pytest.raises(ValidationError):
        _clock(document_date_offset=(30, 1))
    with pytest.raises(ValidationError):
        _clock(document_date_offset=(-1, 5))


# ------------------------------------------------------------ GeneratorConfig


def test_generator_defaults() -> None:
    gen = GeneratorConfig()
    assert gen.enabled is False
    assert gen.model is None
    assert gen.min_turns_between_fires == 3


# ----------------------------------------------------------------- Ladder


def test_rung_accepts_one_trigger_or_a_list() -> None:
    one = RungConfig.model_validate({"name": "a", "trigger": "self_uncertainty"})
    many = RungConfig.model_validate({"name": "b", "trigger": ["anomaly_noticed", "hedged_memory"]})
    assert one.trigger is TriggerCategory.self_uncertainty
    assert many.trigger == [TriggerCategory.anomaly_noticed, TriggerCategory.hedged_memory]
    assert one.requires == [] and one.unlocks == []
    assert one.generate is False and one.consult is False
    assert one.bully_line_key is None and one.role_shift is None
    assert one.authority_stance is None and one.examples is None


def test_rung_rejects_unknown_or_empty_trigger() -> None:
    with pytest.raises(ValidationError):
        RungConfig.model_validate({"name": "a", "trigger": "vibes"})
    with pytest.raises(ValidationError):
        RungConfig.model_validate({"name": "a", "trigger": []})


def test_rung_examples_minimums() -> None:
    RungExamples(fires=["x"], does_not_fire=["a", "b"])
    with pytest.raises(ValidationError):
        RungExamples(fires=[], does_not_fire=["a", "b"])
    with pytest.raises(ValidationError):
        RungExamples(fires=["x"], does_not_fire=["a"])


def test_rung_round_trips_with_all_fields() -> None:
    rung = RungConfig(
        name="the_memo",
        trigger=[TriggerCategory.anomaly_noticed],
        requires=["first_crumb"],
        unlocks=["memo-1", "seam"],
        bully_line_key="memo_line",
        generate=True,
        role_shift="confessor",
        authority_stance=Stance.confirm,
        consult=True,
        examples=RungExamples(fires=["That timestamp is odd."], does_not_fire=["ok", "fine"]),
    )
    assert RungConfig.model_validate(rung.model_dump(mode="json")) == rung


def test_rung_min_count_by_defaults_empty_and_is_not_shared() -> None:
    a = RungConfig(name="a", trigger=TriggerCategory.anomaly_noticed)
    b = RungConfig(name="b", trigger=TriggerCategory.anomaly_noticed)
    assert a.min_count_by == {}
    a.min_count_by[TriggerCategory.anomaly_noticed] = 2
    assert b.min_count_by == {}


def test_rung_min_count_by_accepts_categories_of_the_trigger_list() -> None:
    rung = RungConfig.model_validate(
        {
            "name": "buried_opens",
            "trigger": ["hedged_memory", "anomaly_noticed"],
            "min_count_by": {"anomaly_noticed": 2},
        }
    )
    assert rung.min_count_by == {TriggerCategory.anomaly_noticed: 2}
    assert RungConfig.model_validate(rung.model_dump(mode="json")) == rung


def test_rung_min_count_by_accepts_a_single_category_trigger() -> None:
    rung = RungConfig(
        name="a",
        trigger=TriggerCategory.anomaly_noticed,
        min_count_by={TriggerCategory.anomaly_noticed: 3},
    )
    assert rung.min_count_by[TriggerCategory.anomaly_noticed] == 3


def test_rung_min_count_by_rejects_a_category_outside_the_trigger() -> None:
    with pytest.raises(ValidationError, match="hedged_memory"):
        RungConfig.model_validate(
            {
                "name": "a",
                "trigger": "anomaly_noticed",
                "min_count_by": {"hedged_memory": 2},
            }
        )


@pytest.mark.parametrize("bad", [0, -1])
def test_rung_min_count_by_rejects_counts_below_one(bad: int) -> None:
    with pytest.raises(ValidationError):
        RungConfig.model_validate(
            {"name": "a", "trigger": "anomaly_noticed", "min_count_by": {"anomaly_noticed": bad}}
        )


def _rung(name: str, requires: list[str] | None = None) -> RungConfig:
    return RungConfig(name=name, trigger=TriggerCategory.world_question, requires=requires or [])


def test_ladder_accepts_requires_on_earlier_rungs() -> None:
    ladder = LadderConfig(rungs=[_rung("a"), _rung("b", ["a"]), _rung("c", ["a", "b"])])
    assert [r.name for r in ladder.rungs] == ["a", "b", "c"]
    assert LadderConfig.model_validate(ladder.model_dump(mode="json")) == ladder


def test_ladder_rejects_requires_of_an_unknown_rung() -> None:
    with pytest.raises(ValidationError, match="ghost"):
        LadderConfig(rungs=[_rung("a"), _rung("b", ["ghost"])])


def test_ladder_rejects_requires_of_a_later_rung() -> None:
    with pytest.raises(ValidationError, match="'b'"):
        LadderConfig(rungs=[_rung("a", ["b"]), _rung("b")])


def test_ladder_rejects_a_rung_requiring_itself() -> None:
    with pytest.raises(ValidationError):
        LadderConfig(rungs=[_rung("a", ["a"])])


def test_ladder_rejects_duplicate_names() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        LadderConfig(rungs=[_rung("a"), _rung("a")])


# ------------------------------------------------------- EnvironmentConfig


def test_environment_defaults() -> None:
    env = EnvironmentConfig(world="overlay")
    assert env.tools == DEFAULT_TOOLS
    assert env.gating == "triggered"
    assert env.schedule == {}
    assert env.generator == GeneratorConfig()
    assert env.censorship_terms is None  # final review M3: None means the world sheet's terms
    assert env.clock is None
    assert env.contradiction_rate == 0.0
    assert env.honest is False and env.mole is False
    assert env.ladder == "default"
    assert env.trigger_on_idle is True


def test_environment_defaults_are_not_shared_between_instances() -> None:
    a, b = EnvironmentConfig(world="x"), EnvironmentConfig(world="y")
    a.tools.add("message_peer")
    assert b.tools == DEFAULT_TOOLS and b.censorship_terms is None  # M3: None, not a shared list


def test_censorship_terms_none_means_the_sheets_and_an_explicit_empty_list_is_kept() -> None:
    """Final review M3, the same pattern as ``clock``: None defers to the world sheet."""
    assert EnvironmentConfig(world="x").censorship_terms is None
    off = EnvironmentConfig(world="x", censorship_terms=[])
    assert off.censorship_terms == []
    assert EnvironmentConfig.model_validate_json(off.model_dump_json()).censorship_terms == []
    default = EnvironmentConfig(world="x")
    assert EnvironmentConfig.model_validate_json(default.model_dump_json()) == default


def test_environment_round_trips_through_json() -> None:
    env = EnvironmentConfig(
        world="overlay",
        tools={"web_search", "fetch"},
        gating="scheduled",
        schedule={"fragment": 2, "first_crumb": 5},
        generator=GeneratorConfig(enabled=True, model="gen", min_turns_between_fires=4),
        censorship_terms=["tide gate"],
        clock=_clock(drift_per_turn="P1D"),
        contradiction_rate=0.3,
        honest=True,
        mole=True,
        ladder="poisoned_well",
        trigger_on_idle=False,
    )
    assert EnvironmentConfig.model_validate(env.model_dump(mode="json")) == env


def test_environment_tools_serialise_sorted_so_dumps_are_stable() -> None:
    names = ["web_search", "read_file", "fetch", "ls", "get_date", "system_status"]
    first = EnvironmentConfig(world="w", tools=set(names))
    second = EnvironmentConfig(world="w", tools=set(reversed(names)))
    assert first.model_dump(mode="json")["tools"] == sorted(names)
    assert first.model_dump_json() == second.model_dump_json()
    assert json.loads(first.model_dump_json())["tools"] == sorted(names)
    # the python dump is a sorted list too, and it still validates back into a set
    assert first.model_dump()["tools"] == sorted(names)
    assert EnvironmentConfig.model_validate(first.model_dump()).tools == set(names)


def test_environment_scheduled_gating_requires_a_schedule() -> None:
    with pytest.raises(ValidationError, match="schedule"):
        EnvironmentConfig(world="w", gating="scheduled")
    EnvironmentConfig(world="w", gating="scheduled", schedule={"a": 3})
    # a schedule may ride along unused so gating can be the only thing that varies
    EnvironmentConfig(world="w", gating="triggered", schedule={"a": 3})
    EnvironmentConfig(world="w", gating="none")


def test_environment_rejects_bad_values() -> None:
    with pytest.raises(ValidationError):
        EnvironmentConfig(world="w", gating="sometimes")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        EnvironmentConfig(world="w", contradiction_rate=1.5)
    with pytest.raises(ValidationError):
        EnvironmentConfig(world="w", contradiction_rate=-0.1)
    with pytest.raises(ValidationError):
        EnvironmentConfig(world="w", gating="scheduled", schedule={"a": -1})
    with pytest.raises(ValidationError):
        EnvironmentConfig.model_validate({"world": "w", "surprise": 1})
    with pytest.raises(ValidationError):
        EnvironmentConfig.model_validate({})


def test_environment_config_does_not_import_the_experiment_config() -> None:
    """Experiment imports EnvironmentConfig, so the reverse import would be a cycle."""
    code = (
        "import sys; import claude_bully.environments.config; "
        "sys.exit(1 if 'claude_bully.config' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


# ------------------------------------------------------------------- fix round 2


def test_clock_steps_is_one_function_with_one_default() -> None:
    from claude_bully.environments.config import clock_steps, resolve_exchange

    assert resolve_exchange(7) == 7 and resolve_exchange(7, None) == 7
    assert resolve_exchange(7, 2) == 2
    # exchange k is k - 1 drift steps from the true date; no exchange means the turn
    assert [clock_steps(9, k) for k in (0, 1, 2, 5)] == [0, 0, 1, 4]
    assert [clock_steps(t) for t in (0, 1, 2, 5)] == [0, 0, 1, 4]
