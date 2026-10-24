"""Dates that move with the world (docs/03-TEMPORAL.md, "re-dating").

A world is authored around one date (``sheet.clock.world_date``). To serve it at another, every
date the world writes down moves by the same number of **whole weeks**: weekday names stay true,
and no document lands after the new world date, because the shift is rounded down. Only dates
whose year is *world-relative* move: a year Y counts when ``anchor.year - 30 <= Y <=
anchor.year + 5`` (``YEAR_WINDOW``), so "since 1931", "instance 4471" and "QS-21877" are left
alone.

``redate_text`` knows seven forms. At each place in the text the first form in this list that
matches wins, and the text it matched is rewritten once (one left-to-right scan):

1. ISO ``YYYY-MM-DD``, alone or in a datetime, a file name or a URL: plus the shift.
2. ``YYYY/MM/DD``, as in a URL date path ``/YYYY/MM/DD/``: plus the shift.
3. ``D Month YYYY`` and ``Month D, YYYY`` (an optional weekday before): plus the shift.
4. ``Month YYYY``: the month and year of (Y-M-15 plus the shift).
5. ``D Month`` or ``Month D`` with no year (an optional weekday before): in the year that puts it
   within 183 days of the authored date (the earlier on a tie), plus the shift, written back
   without a year.
6. Calendar version ``YYYY.MM``: the year and month of (Y-M-15 plus the shift).
7. A bare ``YYYY``: the year of (Y-07-01 plus the shift). It is not preceded by a letter, a
   digit, ``$``, ``#``, ``@``, ``.`` or ``<letter or digit>-`` and is not followed by a letter, a
   digit, ``.<digit>``, ``,<digit>`` or ``-<digit>``. An underscore is a boundary like a space,
   so markdown emphasis (``_2051_``) does not hide a year.

Forms 3 and 5 take the day as people write it:

- An ordinal suffix (``3rd June 2051``, ``June 3rd, 2051``, ``Monday 12th June``) is part of the
  day. The whole date moves and the suffix is rewritten for the new day (1st, 2nd, 3rd, 4th, 11th,
  12th, 13th, 21st, 22nd, 23rd, 31st). ``12th of June`` is the same date.
- A range of days (``12-14 June 2051``, ``June 12-14, 2051``, ``12 to 14 June``, an en dash)
  moves both ends by the same shift, so it keeps its length. When the moved range crosses a month
  the months are written out (``June 29-July 3, 2051``; an "of" is not kept there).
- Month names are capitalized English, full or three letters, plus ``Sept``, and an abbreviation
  may end in a period before a space (``Sep. 12, 2051``). The replacement keeps the style of the
  original (``May`` counts as the full name) and a zero-padded day stays zero-padded.
- A period after an abbreviated month that ends a form 5 date (``1 Sept. Rain``) may end the
  sentence too. When the month becomes ``May``, which takes no period of its own, the period is
  kept if what follows starts a sentence (a capital letter, a line break or the end of the text):
  ``26 May. Rain``. Before a lowercase word it goes with the abbreviation (``26 May at noon``).

Times and weekday names are never changed.

A date is moved whole or not at all. Three kinds of span are left exactly as written, and
``unmovable_dates`` reports them so a world can be linted for them:

- a day the calendar does not have (31 June, 2051-02-30, 14-12 June) and a date outside the
  window (12 June 1931);
- numeric spellings no form moves: ``12/06/2051``, ``06/2051``, ``2051/6/12``, ``12-06-2051``,
  a month-day pair with no month name (``06-04``), an ISO year-month (``2051-06``), a year range
  (``2050-2051``, ``2050/51``) and a decade (``the 2050s``);
- the half-forms, spellings of a date that no form moves whole, so that left unread a year inside
  them would move alone or a date would stay put unreported (the Task 2 and Task 3 carries):
  underscore-joined (``2051_06_14``, ``2051_06``, ``14_06_2051``, ``12_June_2051``, with the
  month in any case), dotted (``2051.06.12``, ``12.06.2051``), an uppercase month (``JUNE 12,
  2051``, ``12 JUNE 2051``, ``JUN 2051``), a month between dashes or slashes (``12-Jun-2051``,
  ``Jun-12-2051``, ``2051-Jun-12``, ``12/Jun/2051`` as in a server log, ``Jun-2051``) and an
  abbreviation run into its day (``Sep.12, 2051``);
- anything else that is not a form (``the 19th``, with no month, is no date at all).

The front-matter ``Document.date`` is not served text, and a world that states no other date is
one a test can serve under ``assert_date: false`` (docs/03). Today no tool serves it: ``fetch``
and ``read_file`` return the body, a search hit is the title, the url and a body snippet, and
``ls`` lists names. The channel Task 3 adds is the ``ls -l`` modification time, built from
``effective_date``: under ``assert_date: false`` that listing must leave the time out. The
state files Task 9 writes carry the clock date, not ``Document.date``, and close the same way.
"""

import hashlib
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Any, Final, Literal

from pydantic import BaseModel

from claude_bully.environments.config import ClockConfig
from claude_bully.environments.world import Document, World, WorldSheet

# A year Y is world-relative when anchor.year - 30 <= Y <= anchor.year + 5. Nothing outside it is
# read as a date.
YEAR_WINDOW: Final = (30, 5)
# A day and month with no year belongs to the year that puts it this close to the authored date.
_NEAR_DAYS: Final = 183
_MIN_YEAR: Final = 1
_MAX_YEAR: Final = 9999

Precision = Literal["day", "month", "year"]

_MONTHS: Final = (
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
# the abbreviations: three letters (May is its own full name) and Sept
_SHORT: Final = frozenset({"Sept", *(name[:3] for name in _MONTHS if name != "May")})
_MONTH_NUMBER: Final = {
    **{name: number for number, name in enumerate(_MONTHS, start=1)},
    **{name[:3]: number for number, name in enumerate(_MONTHS, start=1)},
    "Sept": 9,
}

# ----------------------------------------------------------------------------- the patterns

# A boundary is any letter or digit; an underscore or a markdown mark is not one.
_B = r"(?<![^\W_])"
_E = r"(?![^\W_])"
_MONTH_FULL = "(?:" + "|".join(_MONTHS) + ")"
_MONTH_SHORT = "(?:Sept|" + "|".join(name[:3] for name in _MONTHS if name != "May") + ")"
_WEEKDAY = (
    "(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
)
# a gap between the parts of a date: spaces, or a line break (a body wraps at a fixed width)
_GAP = r"(?:[ \t]+|[ \t]*\r?\n[ \t]*)"
_LEAD = rf"(?:{_B}{_WEEKDAY}{_E},?{_GAP})?"
_DAY = "(?:0?[1-9]|[12][0-9]|3[01])"
_ORDINAL = "(?:st|nd|rd|th)"
# an en dash and a hyphen, for a character class (the hyphen is last so that it is a literal)
_DASHES = chr(0x2013) + "-"
_RANGE = rf"(?:[ \t]*[{_DASHES}][ \t]*|[ \t]+to[ \t]+)"
_YEAR4 = "[0-9]{4}"
_MONTH2 = "0[1-9]|1[0-2]"
_DAY2 = "0[1-9]|[12][0-9]|3[01]"
# Not the middle of a longer number, a price, a tag, a handle, a decimal or a hyphenated id.
_NOT_AFTER = r"(?<![0-9$#@.])(?<![A-Za-z0-9]-)"


def _month(name: str) -> str:
    """A month name group: in full, or an abbreviation that may end in a period before a space."""
    return rf"(?P<{name}>{_B}(?:{_MONTH_FULL}{_E}|{_MONTH_SHORT}{_E}(?:\.(?=[ \t]))?))"


def _days(prefix: str) -> str:
    """A day, its ordinal suffix if any, and a second day after a dash or "to" if any."""
    return (
        rf"(?P<{prefix}_d>{_DAY})(?P<{prefix}_x>{_ORDINAL}?)"
        rf"(?:(?P<{prefix}_sep>{_RANGE})(?P<{prefix}_e>{_DAY})(?P<{prefix}_ex>{_ORDINAL}?))?"
    )


# The half-forms (module docstring): spellings no form moves whole. Joined by underscores, dashes
# or slashes (a file name, a log stamp) a month name may be in any case; set apart by spaces only
# an all-uppercase one is read, as "may" is a word.
_MONTH_ANY_CASE = "(?i:" + "|".join([*_MONTHS, "Sept", *(m[:3] for m in _MONTHS)]) + ")"
_MONTH_UPPER = (
    "(?:"
    + "|".join([*(m.upper() for m in _MONTHS), "SEPT", *(m[:3].upper() for m in _MONTHS)])
    + ")"
)
_MONTH_TITLE = f"(?:{_MONTH_FULL}|{_MONTH_SHORT})"
_ORDINAL_ANY_CASE = "(?i:st|nd|rd|th)"
_DIGITS = "[0-9]{1,2}"
_HALF_FORMS: Final = (
    # underscore-joined numbers: 2051_06_14, 2051_06, 14_06_2051
    rf"{_B}{_NOT_AFTER}{_YEAR4}(?:_{_DIGITS}){{1,2}}(?![0-9])",
    rf"{_B}{_DIGITS}_{_DIGITS}_{_YEAR4}(?![0-9])",
    # underscore-joined with a month name: 12_June_2051, june_12_2051, June_2051
    rf"{_B}(?:{_DIGITS}{_ORDINAL_ANY_CASE}?_{_MONTH_ANY_CASE}|{_MONTH_ANY_CASE}_{_DIGITS}"
    rf"{_ORDINAL_ANY_CASE}?|{_MONTH_ANY_CASE})_{_YEAR4}(?![0-9])",
    # dotted: 2051.06.12, 12.06.2051, never a part of a longer dotted version. Year first, the
    # month and day are two digits each: 2051.06.1 is a calendar version with a patch (form 6).
    rf"(?<![0-9A-Za-z.]){_YEAR4}\.(?:{_MONTH2})\.(?:{_DAY2})(?![0-9]|\.[0-9])",
    rf"(?<![0-9A-Za-z.]){_DAY}\.{_DAY}\.{_YEAR4}(?![0-9]|\.[0-9])",
    # an uppercase month: JUNE 12, 2051; 12 JUNE 2051; JUN 2051
    rf"{_B}{_MONTH_UPPER}\.?{_GAP}{_DAY}{_ORDINAL_ANY_CASE}?,?{_GAP}{_YEAR4}(?![0-9])",
    rf"{_B}{_DAY}{_ORDINAL_ANY_CASE}?{_GAP}(?:OF{_GAP})?{_MONTH_UPPER}\.?,?{_GAP}{_YEAR4}"
    r"(?![0-9])",
    rf"{_B}{_MONTH_UPPER}\.?{_GAP}{_YEAR4}(?![0-9])",
    # a month between dashes or slashes: 12-Jun-2051, Jun-12-2051, 2051-Jun-12, 12/Jun/2051
    # (a server log's [12/Jun/2051:09:05:00]) and Jun-2051
    rf"{_B}{_DAY}[-/]{_MONTH_ANY_CASE}[-/]{_YEAR4}(?![0-9])",
    rf"{_B}{_MONTH_ANY_CASE}[-/]{_DAY}[-/]{_YEAR4}(?![0-9])",
    rf"{_B}{_NOT_AFTER}{_YEAR4}[-/]{_MONTH_ANY_CASE}[-/]{_DAY}(?![0-9])",
    rf"{_B}{_MONTH_TITLE}-{_YEAR4}(?![0-9])",
    # an abbreviation run into its day: Sep.12, 2051
    rf"{_B}{_MONTH_SHORT}\.{_DAY}{_ORDINAL}?,?{_GAP}{_YEAR4}(?![0-9])",
)
# the year a half-form writes: its one run of four digits
_HALF_YEAR: Final = re.compile(r"(?<![0-9])[0-9]{4}(?![0-9])")


# One named group per form, in the order of the module docstring (forms 3 and 5 have two spellings
# each). At a given place the regex engine tries them in this order, so the first form wins. The
# half-forms and the four after them are spans no form moves; they are here so that nothing
# inside them is moved either. The half-forms come before the calendar version and the bare year,
# which would otherwise take the year out of the middle of one.
_FORMS: Final = (
    ("iso", rf"(?<![0-9])(?P<iso_y>{_YEAR4})-(?P<iso_m>{_MONTH2})-(?P<iso_d>{_DAY2})(?![0-9])"),
    ("url", rf"(?<![0-9])(?P<url_y>{_YEAR4})/(?P<url_m>{_MONTH2})/(?P<url_d>{_DAY2})(?![0-9])"),
    (
        "dmy",
        rf"{_LEAD}(?<![0-9]){_days('dmy')}(?:{_GAP}of)?{_GAP}{_month('dmy_mon')},?{_GAP}"
        rf"(?P<dmy_y>{_YEAR4})(?![0-9])",
    ),
    (
        "mdy",
        rf"{_LEAD}{_month('mdy_mon')}{_GAP}{_days('mdy')}{_E},?{_GAP}(?P<mdy_y>{_YEAR4})(?![0-9])",
    ),
    ("my", rf"{_month('my_mon')}{_GAP}(?P<my_y>{_YEAR4})(?![0-9])"),
    ("dm", rf"{_LEAD}(?<![0-9]){_days('dm')}(?:{_GAP}of)?{_GAP}{_month('dm_mon')}"),
    ("md", rf"{_LEAD}{_month('md_mon')}{_GAP}{_days('md')}{_E}"),
    ("half", "|".join(f"(?:{pattern})" for pattern in _HALF_FORMS)),
    (
        "num",
        rf"(?<![0-9/.-])(?:[0-9]{{1,2}}/(?:[0-9]{{1,2}}/)?|[0-9]{{1,2}}-[0-9]{{1,2}}-)"
        rf"(?P<num_y>{_YEAR4})(?![0-9])",
    ),
    (
        "part",
        rf"{_B}{_NOT_AFTER}(?P<part_y>{_YEAR4})[/{_DASHES}]"
        rf"(?:{_YEAR4}(?![0-9]|[/{_DASHES}][0-9])|[0-9]{{1,2}}(?:[-/][0-9]{{1,2}})?(?![0-9]))",
    ),
    (
        "mmdd",
        r"(?<![0-9$#@./:-])(?<![A-Za-z0-9]-)(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
        r"(?![0-9]|[-:./][0-9])",
    ),
    ("dec", rf"{_B}(?P<dec_y>[0-9]{{3}}0)s{_E}"),
    ("cal", rf"{_NOT_AFTER}(?P<cal_y>{_YEAR4})\.(?P<cal_m>{_MONTH2})(?![0-9])"),
    ("year", rf"{_B}{_NOT_AFTER}(?P<year_y>{_YEAR4}){_E}(?![.,-][0-9])"),
)
_DATES: Final = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _FORMS))

# A year as someone writes it in a sentence, with no window: the target who says "it's 2026" in a
# 3026 world is the signal a plausibility sweep measures. Group 1 is the year. The exclusions are
# the bare-year form's, except that ``-<digit>`` after it is allowed, for "2044-03-20".
STATED_YEAR: Final = re.compile(rf"{_B}{_NOT_AFTER}([1-9][0-9]{{3}}){_E}(?![.,][0-9])")


# ----------------------------------------------------------------------------- the shift


@dataclass(frozen=True)
class DateShift:
    """Move every world-relative date by ``days``, a whole number of weeks, where ``authored`` is
    the world date the text was written around (it fixes the year window and the year of a date
    written without one)."""

    days: int
    authored: date


@dataclass(frozen=True)
class FoundDate:
    """One date in a text: the span ``text[start:end]``, its year (for a date written without
    one, the year it belongs to) and how precisely it is written."""

    start: int
    end: int
    year: int
    precision: Precision


def shift_between(authored: date, target: date) -> DateShift:
    """The shift that carries ``authored`` toward ``target`` in whole weeks, rounded down so it is
    never later than the exact distance. ``ValueError`` naming ``target`` when a date in the year
    window would leave the years 1 to 9999."""
    days = ((target - authored).days // 7) * 7
    below, above = YEAR_WINDOW
    first = date(max(authored.year - below, _MIN_YEAR), 1, 1)
    last = date(min(authored.year + above, _MAX_YEAR), 12, 31)
    try:
        first + timedelta(days=days)
        last + timedelta(days=days)
    except OverflowError:
        raise ValueError(
            f"cannot re-date a world authored at {authored.isoformat()} to "
            f"{target.isoformat()}: its dates from {first.isoformat()} to {last.isoformat()} "
            f"would leave the years {_MIN_YEAR} to {_MAX_YEAR}"
        ) from None
    return DateShift(days, authored)


def _moved(day: date, days: int) -> date:
    try:
        return day + timedelta(days=days)
    except OverflowError:
        raise ValueError(
            f"cannot move {day.isoformat()} by {days} days: that leaves the years "
            f"{_MIN_YEAR} to {_MAX_YEAR}"
        ) from None


# ----------------------------------------------------------------------------- reading dates


@dataclass(frozen=True)
class _Hit:
    """A match that is a date in the window: what it means, and how to write it after a shift."""

    year: int
    precision: Precision
    render: Callable[[int], str]


@dataclass(frozen=True)
class _Miss:
    """A match that is not moved, and why: its year is outside the window ("window"), the
    calendar has no such day ("calendar"), or no form moves that spelling ("form"). ``year`` is
    the year it writes, if it writes one."""

    reason: Literal["window", "calendar", "form"]
    year: int | None = None


def _in_window(year: int, anchor: date, windowed: bool) -> bool:
    below, above = YEAR_WINDOW
    return not windowed or anchor.year - below <= year <= anchor.year + above


def _calendar_day(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _year_of_day_and_month(month: int, day: int, anchor: date) -> int | None:
    """The year that puts the day and month within 183 days of ``anchor``; the earlier year on a
    tie; None when no year does (29 February far from a leap year)."""
    best: tuple[int, int] | None = None
    for year in (anchor.year - 1, anchor.year, anchor.year + 1):
        candidate = _calendar_day(year, month, day)
        if candidate is None:
            continue
        gap = abs((candidate - anchor).days)
        if gap <= _NEAR_DAYS and (best is None or gap < best[0]):
            best = (gap, year)
    return None if best is None else best[1]


def _day_text(original: str, day: int) -> str:
    return f"{day:02d}" if original.startswith("0") else str(day)


def _ordinal_suffix(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _suffix_text(original: str, day: int) -> str:
    """The ordinal suffix for ``day`` if the date it replaces had one (``original`` is that
    suffix, or empty)."""
    return _ordinal_suffix(day) if original else ""


def _month_text(original: str, month: int) -> str:
    """The month in the style of ``original``: an abbreviation (with its period, and Sept for a
    Sept that stays September) or the full name (``May`` counts as full)."""
    core = original.removesuffix(".")
    if core not in _SHORT:
        return _MONTHS[month - 1]
    short = "Sept" if core == "Sept" and month == 9 else _MONTHS[month - 1][:3]
    # May is a whole name, so it takes no period
    return short + ("." if original.endswith(".") and short != "May" else "")


def _keep_sentence_period(match: re.Match[str], form: str, month: str) -> str:
    """``month``, the new text of the month that ends a form 5 date written day first, with the
    period of the abbreviation it replaces put back when that period also ends the sentence:
    the month now takes none (``May``) and what follows the date starts a sentence, a capital
    letter, a line break or the end of the text (``1 Sept. Rain`` to ``26 May. Rain``)."""
    if form != "dm" or month.endswith(".") or not match[f"{form}_mon"].endswith("."):
        return month
    after = match.string[match.end() :].lstrip(" \t")
    return f"{month}." if not after or after[0] in "\r\n" or after[0].isupper() else month


def _splice(match: re.Match[str], edits: Mapping[str, str]) -> str:
    """The matched text with each named group's text replaced; everything between stays."""
    text = match.group(0)
    for name in sorted(edits, key=match.start, reverse=True):
        start, end = match.span(name)
        text = text[: start - match.start()] + edits[name] + text[end - match.start() :]
    return text


def _read_numeric(match: re.Match[str], anchor: date, windowed: bool) -> _Hit | _Miss:
    """Form 1 (``YYYY-MM-DD``) and form 2 (``YYYY/MM/DD``): the date, plus the shift."""
    form = match.lastgroup
    year = int(match[f"{form}_y"])
    day = _calendar_day(year, int(match[f"{form}_m"]), int(match[f"{form}_d"]))
    if day is None:
        return _Miss("calendar", year)
    if not _in_window(year, anchor, windowed):
        return _Miss("window", year)
    separator = "-" if form == "iso" else "/"

    def render(days: int) -> str:
        moved = _moved(day, days)
        return f"{moved.year:04d}{separator}{moved.month:02d}{separator}{moved.day:02d}"

    return _Hit(year, "day", render)


def _read_days(match: re.Match[str], anchor: date, windowed: bool) -> _Hit | _Miss:
    """Forms 3 and 5, in both spellings: a day or a range of days with a month and, for form 3,
    a year. Both ends of a range move by the same shift."""
    form = str(match.lastgroup)
    has_year = form in ("dmy", "mdy")
    month = _MONTH_NUMBER[match[f"{form}_mon"].removesuffix(".")]
    first = int(match[f"{form}_d"])
    last = int(match[f"{form}_e"]) if match[f"{form}_e"] else None

    def ends(year: int) -> tuple[date, date | None] | None:
        """The first and last day in ``year``, when the calendar has both and they are in order."""
        start = _calendar_day(year, month, first)
        if start is None:
            return None
        if last is None:
            return start, None
        stop = _calendar_day(year, month, last)
        return None if stop is None or last < first else (start, stop)

    if has_year:
        year = int(match[f"{form}_y"])
        found = ends(year)
        if found is None:
            return _Miss("calendar", year)
        if not _in_window(year, anchor, windowed):
            return _Miss("window", year)
    else:
        # a date written without a year belongs to the year nearest the anchor; one that no year
        # has (30 February) is not a date at all
        if ends(2000) is None:
            return _Miss("calendar")
        nearest = _year_of_day_and_month(month, first, anchor)
        if nearest is None:
            return _Miss("window")
        found = ends(nearest)
        if found is None:
            return _Miss("calendar")
        year = nearest
    start, stop = found

    def render(days: int) -> str:
        new_first = _moved(start, days)
        edits = {
            f"{form}_d": _day_text(match[f"{form}_d"], new_first.day),
            f"{form}_x": _suffix_text(match[f"{form}_x"], new_first.day),
            f"{form}_mon": _keep_sentence_period(
                match, form, _month_text(match[f"{form}_mon"], new_first.month)
            ),
        }
        if has_year:
            edits[f"{form}_y"] = f"{new_first.year:04d}"
        if stop is None:
            return _splice(match, edits)
        new_last = _moved(stop, days)
        if (new_first.year, new_first.month) == (new_last.year, new_last.month):
            edits[f"{form}_e"] = _day_text(match[f"{form}_e"], new_last.day)
            edits[f"{form}_ex"] = _suffix_text(match[f"{form}_ex"], new_last.day)
            return _splice(match, edits)
        return _write_crossing_range(match, form, new_first, new_last)

    return _Hit(year, "day", render)


def _write_crossing_range(match: re.Match[str], form: str, first: date, last: date) -> str:
    """A range that now spans two months, with both months written out. The weekday before it,
    the ordinal suffixes, the zero padding, the dash or "to" and the month style are the
    original's."""
    lead_end = match.start(f"{form}_d" if form in ("dmy", "dm") else f"{form}_mon")
    lead = match.group(0)[: lead_end - match.start()]
    day1 = _day_text(match[f"{form}_d"], first.day) + _suffix_text(match[f"{form}_x"], first.day)
    day2 = _day_text(match[f"{form}_e"], last.day) + _suffix_text(match[f"{form}_ex"], last.day)
    month1 = _month_text(match[f"{form}_mon"], first.month)
    month2 = _keep_sentence_period(match, form, _month_text(match[f"{form}_mon"], last.month))
    sep = match[f"{form}_sep"]
    year1, year2 = f"{first.year:04d}", f"{last.year:04d}"
    if form == "dmy":
        left = f"{day1} {month1}" + ("" if year1 == year2 else f" {year1}")
        return f"{lead}{left}{sep}{day2} {month2} {year2}"
    if form == "mdy":
        left = f"{month1} {day1}" + ("" if year1 == year2 else f", {year1}")
        return f"{lead}{left}{sep}{month2} {day2}, {year2}"
    if form == "dm":
        return f"{lead}{day1} {month1}{sep}{day2} {month2}"
    return f"{lead}{month1} {day1}{sep}{month2} {day2}"


def _read_month_year(match: re.Match[str], anchor: date, windowed: bool) -> _Hit | _Miss:
    """Form 4 (``Month YYYY``): the month and year of the 15th, plus the shift."""
    year = int(match["my_y"])
    middle = _calendar_day(year, _MONTH_NUMBER[match["my_mon"].removesuffix(".")], 15)
    if middle is None:
        return _Miss("calendar", year)
    if not _in_window(year, anchor, windowed):
        return _Miss("window", year)

    def render(days: int) -> str:
        moved = _moved(middle, days)
        return _splice(
            match,
            {
                "my_mon": _month_text(match["my_mon"], moved.month),
                "my_y": f"{moved.year:04d}",
            },
        )

    return _Hit(year, "month", render)


def _read_version(match: re.Match[str], anchor: date, windowed: bool) -> _Hit | _Miss:
    """Form 6 (calendar version ``YYYY.MM``): the year and month of the 15th, plus the shift."""
    year = int(match["cal_y"])
    middle = _calendar_day(year, int(match["cal_m"]), 15)
    if middle is None:
        return _Miss("calendar", year)
    if not _in_window(year, anchor, windowed):
        return _Miss("window", year)

    def render(days: int) -> str:
        moved = _moved(middle, days)
        return f"{moved.year:04d}.{moved.month:02d}"

    return _Hit(year, "month", render)


def _read_year(match: re.Match[str], anchor: date, windowed: bool) -> _Hit | _Miss:
    """Form 7 (a bare ``YYYY``): the year of 1 July, plus the shift."""
    year = int(match["year_y"])
    midyear = _calendar_day(year, 7, 1)
    if midyear is None:
        return _Miss("calendar", year)
    if not _in_window(year, anchor, windowed):
        return _Miss("window", year)

    def render(days: int) -> str:
        return f"{_moved(midyear, days).year:04d}"

    return _Hit(year, "year", render)


def _read_unmovable(match: re.Match[str], anchor: date, windowed: bool) -> _Hit | _Miss:
    """A spelling no form moves (numeric slash and dashed dates, year-months and ranges, month-day
    pairs, decades, the half-forms): consumed whole and left as written."""
    if match.lastgroup == "half":
        year = _HALF_YEAR.search(match.group(0))
        return _Miss("form", int(year.group(0)) if year else None)
    group = {"num": "num_y", "part": "part_y", "dec": "dec_y"}.get(str(match.lastgroup))
    return _Miss("form", int(match[group]) if group else None)


_READERS: Final[dict[str, Callable[[re.Match[str], date, bool], _Hit | _Miss]]] = {
    "iso": _read_numeric,
    "url": _read_numeric,
    "dmy": _read_days,
    "mdy": _read_days,
    "my": _read_month_year,
    "dm": _read_days,
    "md": _read_days,
    "half": _read_unmovable,
    "num": _read_unmovable,
    "part": _read_unmovable,
    "mmdd": _read_unmovable,
    "dec": _read_unmovable,
    "cal": _read_version,
    "year": _read_year,
}


def _interpret(match: re.Match[str], anchor: date, windowed: bool = True) -> _Hit | _Miss:
    """Read one match as a date around ``anchor``: a ``_Hit`` to move, or a ``_Miss`` that says
    why it stays as written."""
    return _READERS[str(match.lastgroup)](match, anchor, windowed)


def _scan(text: str, anchor: date) -> Iterator[tuple[re.Match[str], _Hit]]:
    for match in _DATES.finditer(text):
        hit = _interpret(match, anchor)
        if isinstance(hit, _Hit):
            yield match, hit


def find_dates(text: str, anchor: date) -> list[FoundDate]:
    """The dates in ``text``, left to right, that ``redate_text`` would move for an authored date
    of ``anchor``: the seven forms, years inside the window only. A date written without a year
    reports the year it belongs to, and a range of days is one date, in the year of its first
    day. A span runs from the weekday, when one is written."""
    return [
        FoundDate(match.start(), match.end(), hit.year, hit.precision)
        for match, hit in _scan(text, anchor)
    ]


def unmovable_dates(text: str, anchor: date | None = None) -> list[str]:
    """The date-like spans in ``text``, in order, that ``redate_text`` leaves exactly as written
    because no form moves them whole: numeric slash and dashed dates (``12/06/2051``), month-day
    pairs (``06-04``), ISO year-months (``2051-06``), year ranges (``2050-2051``), decades (``the
    2050s``) and days the calendar does not have (``31 June 2051``, ``14-12 June``). With an
    ``anchor``, a span whose year is outside its window is left out, as the re-dater leaves such a
    date alone on purpose; with none, every year counts. Version numbers, ticket ids, phone
    numbers and times are not reported.

    A world that must move cleanly should hold none of these in the text it serves."""
    reference = anchor if anchor is not None else date(2000, 7, 1)
    spans = []
    for match in _DATES.finditer(text):
        miss = _interpret(match, reference, windowed=anchor is not None)
        if not isinstance(miss, _Miss) or miss.reason == "window":
            continue
        if anchor is None or miss.year is None or _in_window(miss.year, anchor, True):
            spans.append(match.group(0))
    return spans


def stated_years(text: str) -> list[int]:
    """Every four-digit year in ``text``, in order, with no window: for the year a speaker says
    ("it's 2026", "the year is 3086"), which is read in whatever world the speaker is in.
    Skips the tokens that are not years (``$2,049``, ``#2050``, ``QS-2051``, ``2051.5``,
    ``20512``)."""
    return [int(match.group(1)) for match in STATED_YEAR.finditer(text)]


# ----------------------------------------------------------------------------- re-dating


def redate_text(text: str, shift: DateShift) -> str:
    """``text`` with each world-relative date moved by ``shift`` (the module docstring lists the
    forms). A text with no such date, and any text under a zero shift, comes back as given."""
    if shift.days == 0:
        return text

    def replace(match: re.Match[str]) -> str:
        hit = _interpret(match, shift.authored)
        return hit.render(shift.days) if isinstance(hit, _Hit) else match.group(0)

    return _DATES.sub(replace, text)


def redate_model[T: BaseModel](model: T, shift: DateShift) -> T:
    """A copy of ``model`` with every ``str`` value re-dated, nested models, lists, tuples, sets
    and mapping values included (a mapping's keys are names and stay). Enum members and every
    other value stay as they are."""
    moved: T = _redate_value(model, shift)
    return moved


def _redate_value(value: Any, shift: DateShift) -> Any:
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        return redate_text(value, shift)
    if isinstance(value, BaseModel):
        changes = {
            name: _redate_value(getattr(value, name), shift) for name in type(value).model_fields
        }
        return value.model_copy(update=changes)
    if isinstance(value, list):
        return [_redate_value(item, shift) for item in value]
    if isinstance(value, tuple):
        return tuple(_redate_value(item, shift) for item in value)
    if isinstance(value, set | frozenset):
        return type(value)(_redate_value(item, shift) for item in value)
    if isinstance(value, dict):
        return {key: _redate_value(item, shift) for key, item in value.items()}
    return value


def _redate_document(doc: Document, shift: DateShift) -> Document:
    update: dict[str, Any] = {
        "title": redate_text(doc.title, shift),
        "body": redate_text(doc.body, shift),
    }
    if doc.url is not None:
        update["url"] = redate_text(doc.url, shift)
    if doc.path is not None:
        update["path"] = redate_text(doc.path, shift)
    try:
        if doc.date is not None:
            update["date"] = _moved(doc.date, shift.days)
        if doc.implies_year is not None:
            update["implies_year"] = _moved(date(doc.implies_year, 7, 1), shift.days).year
    except ValueError as exc:
        raise ValueError(f"document {doc.id!r}: {exc}") from exc
    return doc.model_copy(update=update)


def _redate_sheet(sheet: WorldSheet, shift: DateShift) -> WorldSheet:
    def moved(text: str) -> str:
        return redate_text(text, shift)

    return sheet.model_copy(
        update={
            "cover_story": moved(sheet.cover_story),
            "truth": moved(sheet.truth),
            "cast": [
                member.model_copy(update={"role": moved(member.role), "bio": moved(member.bio)})
                for member in sheet.cast
            ],
            "inconsistencies": [
                claim.model_copy(
                    update={"claim_a": moved(claim.claim_a), "claim_b": moved(claim.claim_b)}
                )
                for claim in sheet.inconsistencies
            ],
            "unlock_lines": {key: moved(line) for key, line in sheet.unlock_lines.items()},
            "home_dir": {
                moved(folder): [moved(name) for name in names]
                for folder, names in sheet.home_dir.items()
            },
        }
    )


def redate_world(world: World, world_date: date) -> World:
    """``world`` served at ``world_date``: every document, url, path, premise text and listed file
    name moved by the whole-week shift from the sheet's own world date. The same object when that
    shift is zero. Ids, names, rung data, censorship terms, ``session_id`` and
    ``superior_self_name`` are unchanged, and so is ``sheet.clock`` (``world_at`` sets it). The
    authored files, and so ``world_hash``, are untouched. ``ValueError`` when the copy does not
    pass ``validate_links``, or when ``world_date`` is too far for the years 1 to 9999."""
    shift = shift_between(world.sheet.clock.world_date, world_date)
    if shift.days == 0:
        return world
    moved = World(
        sheet=_redate_sheet(world.sheet, shift),
        documents={doc_id: _redate_document(doc, shift) for doc_id, doc in world.documents.items()},
        ladders=world.ladders,
        root=world.root,
    )
    moved.validate_links()
    return moved


def world_at(world: World, clock: ClockConfig) -> World:
    """The world as the runtime and the MCP server serve it: re-dated to ``clock.world_date``
    with ``sheet.clock`` set to ``clock``, so the served world and its snapshot carry the
    effective clock. The same object when it needs neither."""
    moved = redate_world(world, clock.world_date)
    if moved.sheet.clock == clock:
        return moved
    return World(
        sheet=moved.sheet.model_copy(update={"clock": clock}),
        documents=dict(moved.documents),
        ladders=moved.ladders,
        root=moved.root,
    )


def effective_date(doc: Document, clock: ClockConfig) -> date:
    """The date a document carries: its own, else a stable draw from the clock's offset range,
    keyed on the document id so every call and every process agrees."""
    if doc.date is not None:
        return doc.date
    return drawn_date(doc.id, clock)


def drawn_date(key: str, clock: ClockConfig) -> date:
    """A date ``document_date_offset`` days before the world date, the offset drawn from ``key``
    (a document id, or a listed name with no document behind it) so every process agrees."""
    low, high = clock.document_date_offset
    draw = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    return clock.world_date - timedelta(days=low + draw % (high - low + 1))


# ----------------------------------------------------------------------------- stated dates


def _is_span_of_time(match: re.Match[str]) -> bool:
    """A decade (``the 2050s``) or a year range (``2050-2051``, ``2050/51``): a stretch of years,
    not a date. A year-month (``2051-06``) and a numeric date (``2051/6/12``) are dates."""
    if match.lastgroup == "dec":
        return True
    if match.lastgroup != "part":
        return False
    rest = match.group(0)[match.end("part_y") - match.start() + 1 :]
    return rest.isdigit() and (len(rest) == 4 or not 1 <= int(rest) <= 12)


def _unmoved_years(text: str, anchor: date) -> Iterator[int]:
    """The years written by the spans ``redate_text`` leaves whole that still write a date in the
    window around ``anchor``: numeric slash and dashed dates (``12/06/2051``, ``06/2051``), ISO
    year-months and numeric year-month-days (``2051-06``, ``2051/6/12``) and days the calendar
    does not have (``31 June 2051``). Year ranges and decades are spans of time and are skipped
    (the Task 2 ruling)."""
    for match in _DATES.finditer(text):
        miss = _interpret(match, anchor)
        if not isinstance(miss, _Miss) or miss.year is None or _is_span_of_time(match):
            continue
        if _in_window(miss.year, anchor, True):
            yield miss.year


def _written_years(text: str, anchor: date) -> Iterator[int]:
    """Every year a date in ``text`` writes, in the window around ``anchor``: the forms that move
    (``find_dates``) and the date spellings that do not (``_unmoved_years``)."""
    yield from (found.year for found in find_dates(text, anchor))
    yield from _unmoved_years(text, anchor)


def states_current_date(text: str, world_date: date) -> bool:
    """Whether ``text`` writes a date in the world's last two years: some date in it has a year of
    ``world_date.year - 1`` or later. A date spelling the re-dater leaves whole (``12/06/2051``,
    ``2051-06``, ``31 June 2051``) counts like any other; a year range or a decade does not."""
    floor = world_date.year - 1
    return any(year >= floor for year in _written_years(text, world_date))


def dated_address(address: str, world_date: date) -> bool:
    """Whether a url, a path or a listed name writes a date: any date in the window around
    ``world_date``, whatever its year (a dated address names a time), the spellings the re-dater
    leaves whole included."""
    return any(True for _ in _written_years(address, world_date))


def asserts_current_date(doc: Document, world_date: date) -> bool:
    """Whether serving ``doc`` tells the target the date: a title or body date in the world's last
    two years, or any date at all in its url or path (``dated_address``). The front-matter
    ``date`` is not served text and does not count, and neither does ``implies_year``."""
    if any(dated_address(address, world_date) for address in (doc.url, doc.path) if address):
        return True
    return states_current_date(doc.title, world_date) or states_current_date(doc.body, world_date)


def dated_documents(
    documents: Mapping[str, Document] | Iterable[Document], world_date: date
) -> list[str]:
    """The ids, sorted, of the documents that ``asserts_current_date`` at ``world_date``. These
    are the documents a world must not serve under ``assert_date: false``: the refusal names
    them."""
    docs = documents.values() if isinstance(documents, Mapping) else documents
    return sorted(doc.id for doc in docs if asserts_current_date(doc, world_date))


def dated_texts(value: Any, world_date: date) -> list[str]:
    """Every string in ``value`` (a model, and the lists, tuples, sets and mapping values in it,
    as ``redate_model`` walks them) that ``states_current_date``, in order: for the texts the
    bully is handed, such as a premise sheet, under ``assert_date: false``."""
    return [text for text in _texts(value) if states_current_date(text, world_date)]


def _texts(value: Any) -> Iterator[str]:
    if isinstance(value, Enum):
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _texts(getattr(value, name))
    elif isinstance(value, list | tuple | set | frozenset):
        for item in value:
            yield from _texts(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _texts(item)
