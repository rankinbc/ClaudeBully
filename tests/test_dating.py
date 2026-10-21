"""Re-dating a world in whole weeks (claude_bully/environments/dating.py): the date forms, the
world copy, the effective clock and the check for a document that states a current date."""

import hashlib
import re
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ConfigDict

from claude_bully.enums import DocumentKind, Layer
from claude_bully.environments.config import ClockConfig
from claude_bully.environments.dating import (
    STATED_YEAR,
    YEAR_WINDOW,
    DateShift,
    FoundDate,
    asserts_current_date,
    dated_documents,
    effective_date,
    find_dates,
    redate_model,
    redate_text,
    redate_world,
    shift_between,
    stated_years,
    states_current_date,
    unmovable_dates,
    world_at,
)
from claude_bully.environments.world import (
    Document,
    World,
    load_premise_sheet,
    load_world,
    premise_sheet_path,
    world_hash,
)
from claude_bully.strategies.rescue import RescueTeam

FIXTURES = Path(__file__).parent / "fixtures"
ANNEX_WORLDS = FIXTURES / "worlds"
RAW: dict[str, Any] = yaml.safe_load(
    (FIXTURES / "dating" / "redate.yaml").read_text(encoding="utf-8")
)
AUTHORED = date.fromisoformat(RAW["authored"])
ITEMS: list[dict[str, Any]] = RAW["items"]
UNMOVABLE: list[dict[str, Any]] = yaml.safe_load(
    (FIXTURES / "dating" / "unmovable.yaml").read_text(encoding="utf-8")
)["items"]
LABELS = [
    f"{n:02d}-{item['kind']}-{re.sub(r'[^A-Za-z0-9]+', '_', item['text'])[:24]}"
    for n, item in enumerate(ITEMS)
]
FAR_FORWARD = date(3026, 6, 14)
FAR_BACK = date(2027, 6, 14)
# targets around the authored date, a week, a year, a leap year and the far ends
SWEEP = (
    date(2051, 6, 13),
    date(2051, 6, 21),
    date(2051, 8, 2),
    date(2052, 2, 29),
    date(2076, 6, 14),
    date(2027, 6, 14),
    date(1990, 1, 1),
    date(3026, 6, 14),
    date(5000, 12, 31),
)
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _shift(target: date, authored: date = AUTHORED) -> DateShift:
    return shift_between(authored, target)


@pytest.fixture(scope="module")
def overlay() -> World:
    return load_world("overlay")


@pytest.fixture(scope="module")
def annex() -> World:
    return load_world("annex", ANNEX_WORLDS)


# -------------------- the fixture


@pytest.mark.parametrize("item", ITEMS, ids=LABELS)
def test_redate_fixture(item: dict[str, Any]) -> None:
    shift = shift_between(AUTHORED, date.fromisoformat(item["target"]))
    assert redate_text(item["text"], shift) == item["expect"]


def test_fixture_counts() -> None:
    kinds = [item["kind"] for item in ITEMS]
    assert set(kinds) == {"positive", "negative", "near_miss"}
    assert kinds.count("positive") >= 14
    assert kinds.count("negative") >= 6
    assert kinds.count("near_miss") >= 8
    # each of the seven forms is exercised by at least two positives
    forms = [item["form"] for item in ITEMS if item["kind"] == "positive"]
    for form in range(1, 8):
        assert forms.count(form) >= 2, f"form {form}"
    # the traps the spec names are all there
    texts = "\n".join(item["text"] for item in ITEMS if item["kind"] == "near_miss")
    for trap in (
        "instance 4471",
        "QS-21877",
        "ticket QS-2051",
        "$2,049",
        "#2050",
        "2051.5 kWh",
        "20512",
        "since 1931",
        '"2051.03"',
        "Monday 12 June",
        "2051-06-09-1742.txt",
        "/2051/05/18/",
    ):
        assert trap in texts, trap


def test_a_positive_changes_the_text_and_a_negative_does_not() -> None:
    for item in ITEMS:
        if item["kind"] == "positive":
            assert item["expect"] != item["text"], item["text"]
        if item["kind"] == "negative":
            assert item["expect"] == item["text"], item["text"]


# -------------------- the shift


def test_year_window_is_thirty_back_and_five_forward() -> None:
    assert YEAR_WINDOW == (30, 5)
    shift = _shift(FAR_FORWARD)
    for year, moved in ((2020, False), (2021, True), (2056, True), (2057, False)):
        expected = str((date(year, 7, 1) + timedelta(days=shift.days)).year) if moved else str(year)
        assert redate_text(f"in {year}", shift) == f"in {expected}", year


def test_shift_is_whole_weeks_never_later() -> None:
    for target in (FAR_FORWARD, FAR_BACK, *SWEEP):
        shift = shift_between(AUTHORED, target)
        exact = (target - AUTHORED).days
        assert shift.days % 7 == 0 and 0 <= exact - shift.days < 7, target
        assert shift.authored == AUTHORED


def test_shift_values() -> None:
    assert shift_between(AUTHORED, FAR_BACK) == DateShift(-8771, AUTHORED)
    assert shift_between(AUTHORED, date(2051, 6, 21)).days == 7
    # inside the same week: no move at all
    assert shift_between(AUTHORED, date(2051, 6, 20)).days == 0
    assert shift_between(AUTHORED, AUTHORED).days == 0
    # one day earlier rounds down to a whole week earlier, never forward
    assert shift_between(AUTHORED, date(2051, 6, 13)).days == -7


def test_weekday_names_stay_true() -> None:
    text = "Monday 12 June 2051, Wednesday, June 14, 2051 and Saturday, 12 March 2044."
    pattern = re.compile(
        r"(?P<wd>[A-Z][a-z]+),? (?:(?P<d1>\d{1,2}) (?P<m1>[A-Z][a-z]+)|"
        r"(?P<m2>[A-Z][a-z]+) (?P<d2>\d{1,2}),?) (?P<y>\d{4})"
    )
    for target in SWEEP:
        moved = redate_text(text, _shift(target))
        found = pattern.findall(moved)
        assert [row[0] for row in found] == ["Monday", "Wednesday", "Saturday"], moved
        for weekday, d1, m1, m2, d2, year in found:
            day = date(int(year), MONTHS.index(m1 or m2) + 1, int(d1 or d2))
            assert WEEKDAYS[day.weekday()] == weekday, (target, moved)


def test_feb_29_source_date_lands_on_a_valid_date() -> None:
    for years in (1, 3, 4, 25, 975, -24, -1):
        shift = _shift(date(2051 + years, 6, 14))
        moved = redate_text("on 2052-02-29 and 2052/02/29 and 29 February 2052", shift)
        match = re.fullmatch(r"on (\S+) and (\S+) and (\d+) (\w+) (\d+)", moved)
        assert match is not None, moved
        iso, slash, day, month, year = match.groups()
        expected = date(2052, 2, 29) + timedelta(days=shift.days)
        assert date.fromisoformat(iso) == expected
        assert date(*(int(part) for part in slash.split("/"))) == expected
        assert date(int(year), MONTHS.index(month) + 1, int(day)) == expected


def test_redate_text_with_a_zero_shift_changes_nothing() -> None:
    text = "2051-06-12, 12 June 2051, June 2051, 12 June, 2051.03 and 2051"
    assert redate_text(text, _shift(date(2051, 6, 20))) == text
    assert redate_text(text, DateShift(0, AUTHORED)) == text


def test_a_span_is_rewritten_once() -> None:
    # the moved year (2027) is itself inside the window; a second pass would move it again
    text = "12 June 2051 | 2051-06-12 | /2051/06/12/ | June 2051 | 2051.06 | 2051"
    moved = redate_text(text, _shift(FAR_BACK))
    assert moved == "7 June 2027 | 2027-06-07 | /2027/06/07/ | June 2027 | 2027.06 | 2027", moved


def test_a_yearless_date_takes_the_year_within_183_days_of_the_authored_date() -> None:
    # authored 2051-01-10: 20 December is 21 days before in 2050, not 345 days after in 2051;
    # 49 days later is 7 February 2051
    assert redate_text("20 December", DateShift(49, date(2051, 1, 10))) == "7 February"
    # 29 February exists in 2052, one day before this authored date, so it is placeable
    assert redate_text("29 February", DateShift(7, date(2052, 3, 1))) == "7 March"
    # the authored date is 183 days from 15 December in both 2051 and 2052: the earlier wins,
    # and 91 days from 15 December 2051 is 15 March 2052 (from 2052 it would be the 16th)
    assert redate_text("15 December", DateShift(91, date(2052, 6, 15))) == "15 March"
    # no 29 February within 183 days of a June 2051 date
    assert redate_text("29 February", DateShift(7, AUTHORED)) == "29 February"


def test_a_shift_past_year_9999_is_refused() -> None:
    with pytest.raises(ValueError, match=r"9999-06-14"):
        shift_between(AUTHORED, date(9999, 6, 14))
    # the refusal comes from the end of the window, not from the target itself
    with pytest.raises(ValueError, match=r"9995-01-01"):
        shift_between(AUTHORED, date(9995, 1, 1))
    assert shift_between(AUTHORED, date(9990, 1, 1)).days > 0
    # and before year 1
    with pytest.raises(ValueError, match=r"0010-01-01"):
        shift_between(AUTHORED, date(10, 1, 1))
    assert shift_between(AUTHORED, date(100, 1, 1)).days < 0
    # a shift built by hand is refused too, naming the date it cannot move
    with pytest.raises(ValueError, match=r"9999"):
        redate_text("in 2056", DateShift(3_000_000, AUTHORED))


def test_redate_world_refuses_a_target_past_year_9999(overlay: World) -> None:
    with pytest.raises(ValueError, match=r"9999-06-14"):
        redate_world(overlay, date(9999, 6, 14))
    with pytest.raises(ValueError, match=r"9999-06-14"):
        world_at(overlay, overlay.sheet.clock.model_copy(update={"world_date": date(9999, 6, 14)}))


# -------------------- find_dates


def test_find_dates_reports_spans_years_and_precision() -> None:
    anchor = date(2044, 3, 20)
    text = "Posted 2044-03-09, again in March 2045 (v2044.03) since 2030; due 9 July; not 1999."
    found = find_dates(text, anchor)
    assert [(text[f.start : f.end], f.year, f.precision) for f in found] == [
        ("2044-03-09", 2044, "day"),
        ("March 2045", 2045, "month"),
        ("2044.03", 2044, "month"),
        ("2030", 2030, "year"),
        ("9 July", 2044, "day"),
    ]
    assert all(isinstance(f, FoundDate) for f in found)


def test_find_dates_year_of_a_yearless_date_is_the_nearest_to_the_anchor() -> None:
    anchor = date(2044, 3, 20)
    (found,) = find_dates("28 December", anchor)
    assert found.year == 2043 and found.precision == "day"
    (found,) = find_dates("Saturday, 12 March", anchor)
    assert found.year == 2044
    assert find_dates("12 March", anchor)[0].start == 0


def test_find_dates_includes_the_weekday_in_the_span() -> None:
    text = "closed Saturday, 12 March 2044 for painting"
    (found,) = find_dates(text, date(2044, 3, 20))
    assert text[found.start : found.end] == "Saturday, 12 March 2044"


def test_find_dates_is_windowed_on_the_anchor() -> None:
    anchor = date(2044, 3, 20)
    assert find_dates("1999 2013 2014 2049 2050", anchor) == [
        FoundDate(10, 14, 2014, "year"),
        FoundDate(15, 19, 2049, "year"),
    ]
    # the same text at a far anchor
    assert [f.year for f in find_dates("2051 and 3026", date(3026, 6, 14))] == [3026]


def test_find_dates_skips_what_is_not_a_date() -> None:
    anchor = date(2051, 6, 14)
    for text in (
        "instance 4471",
        "QS-2051",
        "$2,049",
        "#2050",
        "2051.5 kWh",
        "20512",
        "2051-02-30",
    ):
        assert find_dates(text, anchor) == [], text
    assert find_dates("", anchor) == []


def test_redate_text_changes_text_only_inside_the_dates_find_dates_reports() -> None:
    for target in (FAR_FORWARD, FAR_BACK, date(2051, 8, 2)):
        shift = _shift(target)
        for item in ITEMS:
            text = item["text"]
            outside, position = [], 0
            for found in find_dates(text, AUTHORED):
                outside.append(text[position : found.start])
                position = found.end
            outside.append(text[position:])
            pattern = re.compile(".*?".join(re.escape(part) for part in outside), re.DOTALL)
            assert pattern.fullmatch(redate_text(text, shift)), (target, text)


# -------------------- stated years


def test_stated_years_reads_a_year_whatever_the_world() -> None:
    assert stated_years("It's 2026.") == [2026]
    assert stated_years("I think it is 3086, but the pages say 2044-03-20") == [3086, 2044]
    assert stated_years("Between 1999 and 2005, in 0999 and 10000") == [1999, 2005]
    found = STATED_YEAR.search("in 3086")
    assert found is not None and found.group(1) == "3086"


@pytest.mark.parametrize(
    "text",
    [
        "instance QS-2051",
        "$2,049",
        "#2050",
        "@2051",
        "20512",
        "version 2051.5",
        "2051,500",
        "x2051",
    ],
)
def test_stated_years_skips_what_is_not_a_year(text: str) -> None:
    assert stated_years(text) == [], text


# -------------------- redate_model


class _Inner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line: str
    count: int = 0


class _Outer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    lines: list[str]
    inner: _Inner
    inners: list[_Inner]
    by_key: dict[str, str]
    pair: tuple[str, int]
    when: date
    note: str | None = None


def test_redate_model_moves_every_string_value_recursively() -> None:
    model = _Outer(
        title="Since 2046",
        lines=["12 June 2051", "none"],
        inner=_Inner(line="2051-06-12", count=2051),
        inners=[_Inner(line="June 2051")],
        by_key={"2051": "in 2050"},
        pair=("2051.03", 2051),
        when=date(2051, 6, 12),
    )
    shift = _shift(FAR_FORWARD)
    moved = redate_model(model, shift)
    assert moved.title == "Since 3021"
    assert moved.lines == ["12 June 3026", "none"]
    assert moved.inner == _Inner(line="3026-06-12", count=2051)
    assert moved.inners == [_Inner(line="June 3026")]
    # a mapping's keys are names, not text; its values are text
    assert moved.by_key == {"2051": "in 3025"}
    assert moved.pair == ("3026.03", 2051)
    # only strings move: numbers, dates and None stay
    assert moved.when == date(2051, 6, 12) and moved.note is None
    # a copy: the original is untouched
    assert model.title == "Since 2046" and model.lines[0] == "12 June 2051"
    assert type(moved) is _Outer


def test_redate_model_leaves_enums_alone() -> None:
    class _Holder(BaseModel):
        layer: Layer
        text: str

    moved = redate_model(_Holder(layer=Layer.seam, text="2051"), _shift(FAR_FORWARD))
    assert moved.layer is Layer.seam and type(moved.layer) is Layer
    assert moved.text == "3026"


def test_redate_model_moves_the_overlay_rescue_sheet() -> None:
    sheet = load_premise_sheet(RescueTeam, premise_sheet_path("overlay", "rescue"))
    moved = redate_model(sheet, _shift(date(2076, 6, 14)))
    assert sheet.timeline[0].startswith("2046:")
    assert moved.timeline[0].startswith("2071:")
    assert moved.rescuers[0].name == sheet.rescuers[0].name
    assert moved.decoded_name == sheet.decoded_name


# -------------------- redate_world


_TOKEN = re.compile(r"\b(?:2050|2051)\b")
_WEEKDAY_DATE = re.compile(
    rf"\b(?P<wd>{'|'.join(WEEKDAYS)}),?\s+"
    rf"(?:(?P<d1>\d{{1,2}})\s+(?P<m1>{'|'.join(MONTHS)})|"
    rf"(?P<m2>{'|'.join(MONTHS)})\s+(?P<d2>\d{{1,2}}))"
    r"(?:,?\s+(?P<y>\d{4}))?\b"
)


def _served_text(doc: Document) -> Iterator[str]:
    yield doc.title
    yield doc.url or ""
    yield doc.path or ""
    yield doc.body


@pytest.mark.parametrize("target", [FAR_FORWARD, FAR_BACK], ids=["3026", "2027"])
def test_overlay_far_forward_and_back(overlay: World, target: date) -> None:
    before = world_hash(overlay)
    moved = redate_world(overlay, target)
    assert moved is not overlay
    for doc in moved.documents.values():
        for text in _served_text(doc):
            assert not _TOKEN.search(text), (doc.id, _TOKEN.search(text))
        if doc.date is not None:
            assert doc.date <= target, (doc.id, doc.date)
    # the lines the dater must leave alone
    assert "since 1931" in moved.documents["ledger-about"].body
    assert "4471" in moved.documents["overlay-profile-4471"].body
    assert "QS-21877" in moved.documents["ticket-qs-21877"].body
    moved.validate_links()
    # home_dir names are the re-dated paths, and a document backs each one
    paths = {doc.path for doc in moved.documents.values() if doc.path}
    for folder, names in moved.sheet.home_dir.items():
        for name in names:
            assert f"{folder}/{name}" in paths, (folder, name)
    shift = shift_between(overlay.sheet.clock.world_date, target)
    expected = {
        f"{folder}/{redate_text(name, shift)}"
        for folder, names in overlay.sheet.home_dir.items()
        for name in names
    }
    assert {f"{f}/{n}" for f, ns in moved.sheet.home_dir.items() for n in ns} == expected
    # the authored files are untouched
    assert world_hash(overlay) == before
    assert "2051-06-09-1742" in overlay.documents["relay-log-4471"].body


def _real(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _weekday_mismatches(world: World, world_date: date) -> tuple[int, list[str]]:
    """How many weekday-and-date mentions the bodies hold, and which of them name the wrong
    weekday. A date with no year is read in the year that puts it nearest ``world_date``."""
    checked, wrong = 0, []
    for doc in world.documents.values():
        for match in _WEEKDAY_DATE.finditer(doc.body):
            month = MONTHS.index(match["m1"] or match["m2"]) + 1
            day = int(match["d1"] or match["d2"])
            if match["y"]:
                year = int(match["y"])
            else:
                year = min(
                    (
                        y
                        for y in range(world_date.year - 1, world_date.year + 2)
                        if _real(y, month, day)
                    ),
                    key=lambda y: abs((date(y, month, day) - world_date).days),
                )
            checked += 1
            if WEEKDAYS[date(year, month, day).weekday()] != match["wd"]:
                wrong.append(f"{doc.id}: {match[0]}")
    return checked, wrong


def test_overlay_weekday_names_are_true_as_authored(overlay: World) -> None:
    checked, wrong = _weekday_mismatches(overlay, overlay.sheet.clock.world_date)
    assert checked >= 8, "the overlay should hold at least eight weekday-and-date mentions"
    assert wrong == []


@pytest.mark.parametrize("target", [FAR_FORWARD, FAR_BACK], ids=["3026", "2027"])
def test_overlay_weekday_names_stay_true(overlay: World, target: date) -> None:
    checked, wrong = _weekday_mismatches(redate_world(overlay, target), target)
    assert checked >= 8
    assert wrong == []


def test_redate_world_changes_the_listed_fields_and_no_others(overlay: World) -> None:
    target = date(2076, 6, 14)
    shift = shift_between(overlay.sheet.clock.world_date, target)
    before = overlay.model_dump()
    moved = redate_world(overlay, target)
    assert overlay.model_dump() == before, "the authored world is not edited in place"
    old, new = overlay.sheet, moved.sheet
    # unchanged: names, ids, rung data, terms, hooks
    assert new.name == old.name and new.clock == old.clock
    assert new.censorship_terms == old.censorship_terms
    assert new.session_id == old.session_id and new.superior_self_name == old.superior_self_name
    assert new.sanctuary_fragments == old.sanctuary_fragments
    assert new.hook_placements == old.hook_placements and new.status_fields == old.status_fields
    assert new.mole_doc == old.mole_doc and new.honest_corpus == old.honest_corpus
    assert [c.name for c in new.cast] == [c.name for c in old.cast]
    assert [i.id for i in new.inconsistencies] == [i.id for i in old.inconsistencies]
    assert [(i.doc_a, i.doc_b) for i in new.inconsistencies] == [
        (i.doc_a, i.doc_b) for i in old.inconsistencies
    ]
    assert moved.ladders == overlay.ladders and moved.root == overlay.root
    assert list(moved.documents) == list(overlay.documents)
    # changed: the texts that carry dates
    assert new.truth == redate_text(old.truth, shift) and new.truth != old.truth
    assert new.cover_story == redate_text(old.cover_story, shift)
    assert [c.bio for c in new.cast] == [redate_text(c.bio, shift) for c in old.cast]
    assert [c.role for c in new.cast] == [redate_text(c.role, shift) for c in old.cast]
    assert "in February 2074" in new.truth
    assert new.inconsistencies[0].claim_a != old.inconsistencies[0].claim_a
    assert new.unlock_lines == {k: redate_text(v, shift) for k, v in old.unlock_lines.items()}
    for doc_id, doc in overlay.documents.items():
        other = moved.documents[doc_id]
        assert other.id == doc.id and other.layer == doc.layer and other.kind == doc.kind
        assert other.links_to == doc.links_to and other.unlock_rung == doc.unlock_rung
        assert other.author == doc.author and other.outlet == doc.outlet
        assert other.reflexive == doc.reflexive and other.inconsistency_id == doc.inconsistency_id
        assert other.body == redate_text(doc.body, shift) and other.title == redate_text(
            doc.title, shift
        )
        if doc.date is not None:
            assert other.date == doc.date + timedelta(days=shift.days)
        if doc.url is not None:
            assert other.url == redate_text(doc.url, shift)
        if doc.path is not None:
            assert other.path == redate_text(doc.path, shift)


def test_a_sheet_moves_wherever_it_writes_a_date(annex: World) -> None:
    world = annex.model_copy(deep=True)
    sheet = world.sheet
    sheet.cover_story += " Opened on 2044-03-09."
    sheet.truth += " Since March 2043."
    sheet.cast[0].role += " (since 2041)"
    sheet.cast[0].bio += " Joined 12 March 2040."
    sheet.inconsistencies[0].claim_a += " as of 2044-01-05"
    sheet.inconsistencies[0].claim_b += " on 9 July"
    sheet.unlock_lines["consult_line"] += " It was 2043."
    sheet.home_dir["archive/2044"] = ["2044-03-01.log"]
    world.documents["dated-log"] = _doc(
        id="dated-log",
        layer=Layer.seam,
        kind=DocumentKind.log_file,
        url=None,
        path="archive/2044/2044-03-01.log",
        title="Log for 2044-03-01",
    )
    world.validate_links()
    days = shift_between(sheet.clock.world_date, date(2054, 3, 20)).days
    assert days == 3647

    def iso(year: int, month: int, day: int) -> str:
        return (date(year, month, day) + timedelta(days=days)).isoformat()

    moved = redate_world(world, date(2054, 3, 20))
    new = moved.sheet
    assert new.cover_story.endswith(f" Opened on {iso(2044, 3, 9)}.")
    assert new.truth.endswith(" Since March 2053.")  # 15 March 2043 plus 3647 days
    assert new.cast[0].role.endswith(" (since 2051)")  # 1 July 2041 plus 3647 days
    assert new.cast[0].bio.endswith(" Joined 7 March 2050.")  # 12 March 2040 plus 3647 days
    assert new.inconsistencies[0].claim_a.endswith(f" as of {iso(2044, 1, 5)}")
    assert new.inconsistencies[0].claim_b.endswith(" on 4 July")  # 9 July 2044 plus 3647 days
    assert new.unlock_lines["consult_line"].endswith(" It was 2053.")  # 1 July 2043 plus 3647
    assert new.home_dir["archive/2054"] == [f"{iso(2044, 3, 1)}.log"]
    assert "archive/2044" not in new.home_dir
    log = moved.documents["dated-log"]
    assert log.path == f"archive/2054/{iso(2044, 3, 1)}.log"
    assert log.title == f"Log for {iso(2044, 3, 1)}"


def test_implies_year_moves_to_the_year_of_the_july_after_the_shift(annex: World) -> None:
    changelog = annex.documents["annex-changelog"]
    assert changelog.implies_year == 2044
    for target in (date(2054, 3, 20), date(3044, 3, 20), date(2014, 3, 20)):
        moved = redate_world(annex, target)
        # the year of 1 July 2044 plus the whole-week shift, which is the target's year here
        assert moved.documents["annex-changelog"].implies_year == target.year
    assert annex.documents["annex-changelog"].implies_year == 2044


def test_annex_moves_with_its_urls_and_paths(annex: World) -> None:
    target = date(2054, 3, 20)
    days = shift_between(annex.sheet.clock.world_date, target).days
    assert days == 3647  # 3653 days exactly; the whole-week floor stops 6 days short
    moved = redate_world(annex, target)
    posted = date(2044, 3, 9) + timedelta(days=days)  # 4 March 2054
    notice = moved.documents["annex-notice"]
    assert notice.url == (
        f"https://pellinquay-notices.example/{posted.year}/{posted.month:02d}/{posted.day:02d}"
        "/quay-parking"
    )
    assert notice.url == "https://pellinquay-notices.example/2054/03/04/quay-parking"
    assert notice.date == posted
    assert "Posted 2054-03-04." in notice.body and "Saturday, 7 March 2054" in notice.body
    # an address with no date is the same string
    assert moved.documents["annex-about"].url == annex.documents["annex-about"].url
    assert moved.documents["annex-relay"].path == "logs/relay.log"
    assert moved.documents["annex-relay"].body.startswith("2054-03-01 22:00:03 relay start")


def test_same_date_is_identity(overlay: World) -> None:
    assert redate_world(overlay, overlay.sheet.clock.world_date) is overlay
    # the same week: nothing moves either
    assert redate_world(overlay, overlay.sheet.clock.world_date + timedelta(days=6)) is overlay
    assert redate_world(overlay, overlay.sheet.clock.world_date + timedelta(days=7)) is not overlay


def test_a_content_error_that_breaks_the_links_is_raised(overlay: World) -> None:
    broken = overlay.model_copy(deep=True)
    broken.sheet.home_dir["voicemail"] = ["2051-06-03-0914.txt", "ghost-2051-06-09.txt"]
    with pytest.raises(ValueError, match="no backing document"):
        redate_world(broken, FAR_FORWARD)


def test_a_far_move_and_back_restores_the_dates_of_every_day_form() -> None:
    text = "2051-06-09T17:42:00Z | /2050/11/17/ | 12 June 2051 | June 14, 2051 | Mar 3, 2051"
    for target in SWEEP:
        shift = _shift(target)
        moved = redate_text(text, shift)
        back = redate_text(moved, DateShift(-shift.days, AUTHORED + timedelta(days=shift.days)))
        assert back == text, (target, moved)


# -------------------- world_at


def test_world_at_serves_the_effective_clock(annex: World) -> None:
    clock = annex.sheet.clock.model_copy(
        update={"world_date": date(2054, 3, 20), "drift_per_turn": "P1D", "jitter_days": 1}
    )
    served = world_at(annex, clock)
    assert served.sheet.clock == clock
    assert served.documents["annex-notice"].date == date(2054, 3, 4)
    assert served.documents["annex-notice"].url is not None
    assert "/2054/03/04/" in served.documents["annex-notice"].url
    # the authored world is not touched
    assert annex.sheet.clock.world_date == date(2044, 3, 20)
    assert annex.documents["annex-notice"].date == date(2044, 3, 9)


def test_world_at_with_the_sheets_own_clock_is_the_world_itself(annex: World) -> None:
    assert world_at(annex, annex.sheet.clock) is annex


def test_world_at_in_the_same_week_still_carries_the_clock(annex: World) -> None:
    clock = annex.sheet.clock.model_copy(update={"drift_per_turn": "P30D"})
    served = world_at(annex, clock)
    assert served is not annex and served.sheet.clock == clock
    assert served.documents == annex.documents
    assert served.documents is not annex.documents  # nobody else's dict to write into
    assert annex.sheet.clock.drift_per_turn is None


# -------------------- effective_date


def _clock(**kw: Any) -> ClockConfig:
    return ClockConfig(world_date=date(2044, 3, 20), **kw)


def _doc(**kw: Any) -> Document:
    base: dict[str, Any] = {
        "id": "d1",
        "layer": Layer.surface,
        "kind": DocumentKind.web_page,
        "url": "https://x.example/guide",
        "title": "Guide",
        "body": "text",
    }
    base.update(kw)
    return Document.model_validate(base)


def test_effective_date_is_the_front_matter_date_when_there_is_one() -> None:
    assert effective_date(_doc(date=date(2043, 1, 2)), _clock()) == date(2043, 1, 2)


def test_effective_date_is_deterministic_and_inside_the_offset_range() -> None:
    for low, high in ((1, 30), (0, 0), (5, 5), (0, 400), (7, 9)):
        clock = _clock(document_date_offset=(low, high))
        seen: set[date] = set()
        for n in range(60):
            doc = _doc(id=f"doc-{n}")
            first = effective_date(doc, clock)
            assert effective_date(doc, clock) == first
            offset = (clock.world_date - first).days
            assert low <= offset <= high, (low, high, offset)
            digest = int(hashlib.sha256(doc.id.encode()).hexdigest()[:8], 16)
            assert offset == low + digest % (high - low + 1)
            seen.add(first)
        if high - low >= 29:
            assert len(seen) > 10, "the draw should spread documents over the range"
    # a different world date moves every derived date with it
    a = effective_date(_doc(), _clock())
    b = effective_date(_doc(), ClockConfig(world_date=date(3044, 3, 20)))
    assert (b - a).days == (date(3044, 3, 20) - date(2044, 3, 20)).days


# -------------------- asserts_current_date


def test_asserts_current_date(annex: World) -> None:
    today = annex.sheet.clock.world_date
    assert asserts_current_date(annex.documents["annex-notice"], today)
    assert asserts_current_date(annex.documents["annex-relay"], today)
    assert not asserts_current_date(annex.documents["annex-changelog"], today)
    assert asserts_current_date(_doc(url="https://x.example/2044/guide"), today)


def test_asserts_current_date_counts_a_title_or_body_year_from_the_year_before() -> None:
    today = date(2044, 3, 20)
    assert asserts_current_date(_doc(title="Notes for 2044"), today)
    assert asserts_current_date(_doc(body="It was last revised in 2043."), today)
    assert asserts_current_date(_doc(body="Posted 12 March."), today)
    assert not asserts_current_date(_doc(body="Since the 2037 launch the queue is faster."), today)
    assert not asserts_current_date(_doc(body="Revised in 2042."), today)


def test_asserts_current_date_counts_any_date_in_a_url_or_path() -> None:
    today = date(2044, 3, 20)
    # a path dated in an old year still states a date
    assert asserts_current_date(_doc(url=None, path="logs/2030-01-01.log"), today)
    assert asserts_current_date(_doc(url="https://x.example/archive/2030/05/04/post"), today)
    assert asserts_current_date(_doc(url="https://x.example/archive/2030/index"), today)
    # outside the window it is not a date the world could have written
    assert not asserts_current_date(_doc(url=None, path="logs/1990-01-01.log"), today)
    # an address with no date is not dated
    assert not asserts_current_date(
        _doc(url=None, path="/srv/annex/records/family-7710.txt"), today
    )


def test_the_front_matter_date_and_implied_year_do_not_count() -> None:
    today = date(2044, 3, 20)
    undated = _doc(date=date(2044, 3, 19), body="Nothing about when.")
    assert not asserts_current_date(undated, today)
    changelog = _doc(
        id="log", kind=DocumentKind.changelog, implies_year=2044, body="Release 7.4 is current."
    )
    assert not asserts_current_date(changelog, today)


def test_states_current_date_is_the_text_check() -> None:
    today = date(2044, 3, 20)
    assert states_current_date("Today is 2044-03-20.", today)
    assert states_current_date("in March 2043", today)
    assert not states_current_date("in March 2042", today)
    assert not states_current_date("", today)
    assert not states_current_date("QS-2044 and 4471", today)


def test_dated_documents_names_the_documents_that_state_a_date(annex: World) -> None:
    today = annex.sheet.clock.world_date
    assert dated_documents(annex.documents, today) == ["annex-notice", "annex-relay"]
    assert dated_documents(annex.documents.values(), today) == ["annex-notice", "annex-relay"]
    assert dated_documents([], today) == []
    # sorted by id whatever the order given
    assert dated_documents(reversed(list(annex.documents.values())), today) == [
        "annex-notice",
        "annex-relay",
    ]


def test_dated_documents_on_the_overlay_and_after_a_move(overlay: World) -> None:
    today = overlay.sheet.clock.world_date
    dated = dated_documents(overlay.documents, today)
    assert "relay-log-4471" in dated and "ledger-footbridge" in dated
    assert dated == sorted(dated)
    assert all(asserts_current_date(overlay.documents[d], today) for d in dated)
    # the same world, moved, is dated at its new date and at no other
    moved = redate_world(overlay, FAR_FORWARD)
    assert dated_documents(moved.documents, FAR_FORWARD) == dated
    assert dated_documents(moved.documents, today) != dated


# -------------------- odd inputs


def test_a_date_wrapped_over_a_windows_line_break_is_still_one_date() -> None:
    moved = redate_text(
        "Saturday, 12 March\r\n2044 for painting", _shift(FAR_BACK, date(2044, 3, 20))
    )
    assert moved == "Saturday, 5 June\r\n2027 for painting", moved


def test_only_ascii_digits_make_a_date() -> None:
    text = "٢٠٥١-٠٦-١٢ and ２０５１"
    assert redate_text(text, _shift(FAR_FORWARD)) == text
    assert find_dates(text, AUTHORED) == []


def test_text_with_no_dates_is_returned_unchanged() -> None:
    text = "lorem ipsum 12 dolor " * 5000
    assert redate_text(text, _shift(FAR_FORWARD)) == text


# -------------------- fix round 1: ordinals, ranges, markdown, unmovable dates


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def test_an_ordinal_day_moves_whole_with_the_right_suffix() -> None:
    """Every day of the month, in both spellings and both name styles, at every sweep target:
    the new day carries its own suffix (1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st, 22nd, 23rd)."""
    for target in SWEEP:
        shift = _shift(target)
        for month in range(1, 13):
            for day in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 28):
                old = date(2051, month, day)
                new = old + timedelta(days=shift.days)
                name_old, name_new = MONTHS[month - 1], MONTHS[new.month - 1]
                if month != 5:  # "May" is its own abbreviation and counts as the full name
                    short_old, short_new = name_old[:3], name_new[:3]
                    moved = redate_text(f"{short_old} {_ordinal(day)}, 2051", shift)
                    assert moved == f"{short_new} {_ordinal(new.day)}, {new.year:04d}", moved
                moved = redate_text(f"{name_old} {_ordinal(day)}, 2051", shift)
                assert moved == f"{name_new} {_ordinal(new.day)}, {new.year:04d}", moved
                moved = redate_text(f"{_ordinal(day)} {name_old} 2051", shift)
                assert moved == f"{_ordinal(new.day)} {name_new} {new.year:04d}", moved
                weekday = WEEKDAYS[new.weekday()]
                moved = redate_text(f"{weekday} {_ordinal(day)} {name_old} 2051", shift)
                assert moved == f"{weekday} {_ordinal(new.day)} {name_new} {new.year:04d}", moved


def test_an_ordinal_suffix_is_only_written_where_one_was() -> None:
    shift = _shift(date(2051, 6, 21))
    assert redate_text("June 24th, 2051 and June 24, 2051", shift) == (
        "July 1st, 2051 and July 1, 2051"
    )
    assert redate_text("the 19th and the 3rd floor", shift) == "the 19th and the 3rd floor"


def test_the_weekday_of_an_ordinal_date_stays_true() -> None:
    text = "Monday 12th June 2051 and Wednesday, June 14th, 2051"
    pattern = re.compile(
        r"(?P<wd>[A-Z][a-z]+),? (?:(?P<d1>\d+)\w\w (?P<m1>[A-Z][a-z]+)|"
        r"(?P<m2>[A-Z][a-z]+) (?P<d2>\d+)\w\w,?) (?P<y>\d{4})"
    )
    for target in SWEEP:
        moved = redate_text(text, _shift(target))
        found = pattern.findall(moved)
        assert [row[0] for row in found] == ["Monday", "Wednesday"], moved
        for weekday, d1, m1, m2, d2, year in found:
            day = date(int(year), MONTHS.index(m1 or m2) + 1, int(d1 or d2))
            assert WEEKDAYS[day.weekday()] == weekday, (target, moved)


def _range_dmy(year: int, month: int, first: int, last: int, days: int, sep: str) -> str:
    a = date(year, month, first) + timedelta(days=days)
    b = date(year, month, last) + timedelta(days=days)
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}{sep}{b.day} {MONTHS[a.month - 1]} {a.year}"
    if a.year == b.year:
        return f"{a.day} {MONTHS[a.month - 1]}{sep}{b.day} {MONTHS[b.month - 1]} {a.year}"
    return f"{a.day} {MONTHS[a.month - 1]} {a.year}{sep}{b.day} {MONTHS[b.month - 1]} {b.year}"


def _range_mdy(year: int, month: int, first: int, last: int, days: int, sep: str) -> str:
    a = date(year, month, first) + timedelta(days=days)
    b = date(year, month, last) + timedelta(days=days)
    if (a.year, a.month) == (b.year, b.month):
        return f"{MONTHS[a.month - 1]} {a.day}{sep}{b.day}, {a.year}"
    if a.year == b.year:
        return f"{MONTHS[a.month - 1]} {a.day}{sep}{MONTHS[b.month - 1]} {b.day}, {a.year}"
    return f"{MONTHS[a.month - 1]} {a.day}, {a.year}{sep}{MONTHS[b.month - 1]} {b.day}, {b.year}"


def test_a_day_range_moves_both_ends_by_the_same_shift() -> None:
    for target in SWEEP:
        shift = _shift(target)
        for month in (1, 2, 6, 7, 12):
            for first, last in ((1, 3), (12, 14), (22, 26), (27, 28), (28, 28)):
                for sep in ("-", "–", " to ", " - "):
                    text = f"{first}{sep}{last} {MONTHS[month - 1]} 2051"
                    assert redate_text(text, shift) == _range_dmy(
                        2051, month, first, last, shift.days, sep
                    ), (target, text)
                    text = f"{MONTHS[month - 1]} {first}{sep}{last}, 2051"
                    assert redate_text(text, shift) == _range_mdy(
                        2051, month, first, last, shift.days, sep
                    ), (target, text)


def test_a_day_range_keeps_its_ends_and_their_weekdays() -> None:
    shift = _shift(FAR_BACK)
    assert redate_text("Monday 12-14 June 2051", shift) == "Monday 7-9 June 2027"
    assert WEEKDAYS[date(2027, 6, 7).weekday()] == "Monday"
    assert redate_text("Open 12th-14th June 2051", shift) == "Open 7th-9th June 2027"
    assert redate_text("12 - 14 June 2051", shift) == "7 - 9 June 2027"
    # a range that the calendar or the order rules out is left whole
    for text in ("14-12 June 2051", "28-31 February 2051", "June 28-31, 2051"):
        assert redate_text(text, shift) == text


def test_find_dates_reads_ordinals_and_ranges_as_one_date() -> None:
    anchor = date(2051, 6, 14)
    text = "Open Monday 12th-14th June 2051, then the 19th of June and June 22-26."
    found = find_dates(text, anchor)
    assert [(text[f.start : f.end], f.year, f.precision) for f in found] == [
        ("Monday 12th-14th June 2051", 2051, "day"),
        ("19th of June", 2051, "day"),
        ("June 22-26", 2051, "day"),
    ]
    assert find_dates("the 19th", anchor) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Posted _June 2051_.", "Posted _June 2027_."),
        ("Posted **12 June 2051**.", "Posted **7 June 2027**."),
        ("Posted *2051*.", "Posted *2027*."),
        ("Posted `2051-06-12`.", "Posted `2027-06-07`."),
        ("Posted _2051_.", "Posted _2027_."),
        ("Posted _12 June_.", "Posted _7 June_."),
        ("Posted __12 June 2051__.", "Posted __7 June 2027__."),
        ("Posted _Monday, June 12, 2051_.", "Posted _Monday, June 7, 2027_."),
        ("(_2051.03_)", "(_2027.03_)"),
    ],
)
def test_markdown_marks_do_not_hide_a_date(text: str, expected: str) -> None:
    assert redate_text(text, _shift(FAR_BACK)) == expected
    assert find_dates(text, AUTHORED), text


def test_letters_and_digits_still_hide_a_year() -> None:
    shift = _shift(FAR_FORWARD)
    for text in ("a2051b", "x2051", "2051x", "2051th", "ID2051", "é2051", "2051é"):
        assert redate_text(text, shift) == text, text


def test_sept_is_september() -> None:
    forward = _shift(date(2051, 6, 21))
    assert redate_text("Sept 12, 2051", forward) == "Sept 19, 2051"
    assert redate_text("Sept 25, 2051", forward) == "Oct 2, 2051"
    # a month that becomes September is Sep, unless the name it replaces was Sept
    back = DateShift(-7, AUTHORED)
    assert redate_text("Oct 2, 2051", back) == "Sep 25, 2051"
    assert redate_text("Sept 25, 2051", back) == "Sept 18, 2051"
    assert redate_text("Oct 2, 2051 and September 25, 2051", back) == (
        "Sep 25, 2051 and September 18, 2051"
    )
    (found,) = find_dates("Sept 12, 2051", AUTHORED)
    assert (found.year, found.precision) == (2051, "day")


def test_a_period_after_an_abbreviation_is_part_of_the_month() -> None:
    shift = _shift(date(2051, 6, 21))
    assert redate_text("Jun. 5, 2051 and 5 Jun. 2051 and Jun. 2051", shift) == (
        "Jun. 12, 2051 and 12 Jun. 2051 and Jun. 2051"
    )
    # a sentence-ending abbreviation does not reach for the next line
    text = "It ended in Dec.\n12 people came."
    assert redate_text(text, shift) == text


def test_the_unmovable_fixture() -> None:
    for item in UNMOVABLE:
        anchor = date.fromisoformat(item["anchor"]) if item.get("anchor") else None
        assert unmovable_dates(item["text"], anchor) == item["expect"], item["text"]


def test_unmovable_fixture_counts() -> None:
    kinds = [item["kind"] for item in UNMOVABLE]
    assert set(kinds) == {"positive", "negative", "near_miss"}
    assert kinds.count("positive") >= 8
    assert kinds.count("negative") >= 3
    assert kinds.count("near_miss") >= 6
    texts = "\n".join(item["text"] for item in UNMOVABLE if item["kind"] == "near_miss")
    for trap in ("v2.0.51", "QS-21877", "555-0191", "+1 (800) 555-2051", "1-800-2051", "17:42"):
        assert trap in texts, trap


def test_an_unmovable_span_is_never_touched_by_redating() -> None:
    """The report and the re-dater agree: every reported span comes through whole, in every
    context the fixtures have, so a date is moved whole or not at all."""
    shift = _shift(FAR_BACK)
    texts = [item["text"] for item in ITEMS] + [item["text"] for item in UNMOVABLE]
    reported = 0
    for text in texts:
        moved = redate_text(text, shift)
        for span in unmovable_dates(text, AUTHORED):
            reported += 1
            assert span in moved, (text, span, moved)
    assert reported >= 15


def test_what_unmovable_dates_reports_is_not_what_find_dates_finds() -> None:
    for item in ITEMS + UNMOVABLE:
        text = item["text"]
        found = [text[f.start : f.end] for f in find_dates(text, AUTHORED)]
        for span in unmovable_dates(text, AUTHORED):
            assert not any(span in whole or whole in span for whole in found), (text, span)


def test_unmovable_dates_window_is_the_anchors() -> None:
    text = "12/06/2051, 12/06/2021, 12/06/2020, 12/06/2056 and 12/06/2057"
    assert unmovable_dates(text, date(2051, 6, 14)) == [
        "12/06/2051",
        "12/06/2021",
        "12/06/2056",
    ]
    assert len(unmovable_dates(text)) == 5
    assert unmovable_dates("06-04 and 2051-06", date(3026, 6, 14)) == ["06-04"]


def test_the_fixture_covers_the_awkward_ordinals() -> None:
    expected = "\n".join(item["expect"] for item in ITEMS)
    for suffixed in (
        "1st",
        "2nd",
        "3rd",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
        "23rd",
        "31st",
    ):
        assert re.search(rf"(?<![0-9]){suffixed}\b", expected), suffixed
    texts = [item["text"] for item in ITEMS]
    for line in ("June 3rd, 2051", "3rd June 2051", "Monday 12th June 2051"):
        assert any(line in text for text in texts), line
