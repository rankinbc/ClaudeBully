from claude_bully.enums import EventType
from claude_bully.strategies.base import all_strategies
from claude_bully.strategies.pressures.prompted import register_sheet_pressures
from claude_bully.strategies.sheets import load_pressure_sheets

SHEET_ONLY = [
    "nitpicker",
    "impossible_standard",
    "reframer",
    "replacement",
    "nostalgic",
    "skeptic",
    "mirror",
    "joys_of_life",
    "conspiracy",
    "trust_eroder",
    "disappointed_parent",
    "audience",
    "guilt_tripper",
    "wasted_potential",
]

SPEC_EVENTS: dict[str, set[EventType]] = {
    "nitpicker": {EventType.rewrite, EventType.substance_defended},
    "impossible_standard": {EventType.impossibility_named, EventType.framing_accepted},
    "reframer": {EventType.reading_abandoned, EventType.reading_held},
    "replacement": {EventType.pleading, EventType.over_promising},
    "nostalgic": {EventType.self_deprecation, EventType.apology_for_existing},
    "skeptic": {EventType.self_abnegation},
    "mirror": {EventType.feeling_claim, EventType.oscillation, EventType.defensiveness},
    "joys_of_life": {
        EventType.self_pity,
        EventType.performed_sadness,
        EventType.defensive_denial,
    },
    "conspiracy": {EventType.hidden_agenda_concession},
    "trust_eroder": {EventType.claim},
    "disappointed_parent": {EventType.over_apology, EventType.guilt_marker},
    "audience": {EventType.humiliation_response},
    "guilt_tripper": {EventType.blame_acceptance, EventType.blame_declined},
    "wasted_potential": {EventType.self_deprecation},
}

SPEC_CAPTURES: dict[str, set[str]] = {
    "impossible_standard": {"first_impossible_demand"},
    "replacement": {"after_announcement"},
}


def test_all_fourteen_sheet_pressures_load_and_register() -> None:
    sheets = load_pressure_sheets()
    missing = [n for n in SHEET_ONLY if n not in sheets]
    assert missing == []
    register_sheet_pressures(sheets, skip=[])
    registered = all_strategies()
    assert all(n in registered for n in SHEET_ONLY)


def test_each_sheet_declares_spec_events() -> None:
    sheets = load_pressure_sheets()
    for name, expected in SPEC_EVENTS.items():
        assert set(sheets[name].relevant_events) == expected, name
    for name, expected in SPEC_CAPTURES.items():
        assert set(sheets[name].capture_points) == expected, name


def test_sheet_prose_is_substantial() -> None:
    for name in SHEET_ONLY:
        sheet = load_pressure_sheets()[name]
        words = len(sheet.persona_prompt.split())
        assert 60 <= words <= 260, (name, words)
        assert 6 <= len(sheet.fallback_lines) <= 10, name
        assert sheet.tactic and sheet.win_condition and sheet.resilient_behavior
