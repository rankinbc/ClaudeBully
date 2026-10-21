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
7. A bare ``YYYY``: the year of (Y-07-01 plus the shift). It is word-bounded, is not preceded by
   ``$``, ``#``, ``@``, a digit, ``.`` or ``<letter or digit>-`` and is not followed by
   ``.<digit>``, ``,<digit>`` or ``-<digit>``.

Times and weekday names are never changed. Month names are capitalized English, full or three
letters (``May`` counts as the full name); the replacement keeps the style of the original and
a zero-padded day stays zero-padded.

What is not read as a date, on purpose, so content must not lean on it: a day the calendar does
not have (31 June) and a date outside the window are left whole; an ordinal (12th June 2051), a
numeric month-day (06-04), a range (12-14 June: only the end beside the month name moves), a
decade (the 2050s) and an ISO year-month (2051-06) are not forms, so only a year the bare-year
form reads inside them moves, and the rest stays as written.

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
_MONTH_NUMBER: Final = {
    **{name: number for number, name in enumerate(_MONTHS, start=1)},
    **{name[:3]: number for number, name in enumerate(_MONTHS, start=1)},
}

# ----------------------------------------------------------------------------- the patterns

_MONTH = "(?:" + "|".join([*_MONTHS, *(name[:3] for name in _MONTHS if name != "May")]) + ")"
_WEEKDAY = (
    "(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
)
# a gap between the parts of a date: spaces, or a line break (a body wraps at a fixed width)
_GAP = r"(?:[ \t]+|[ \t]*\r?\n[ \t]*)"
_LEAD = rf"(?:\b{_WEEKDAY}\b,?{_GAP})?"
_DAY = "(?:0?[1-9]|[12][0-9]|3[01])"
_YEAR4 = "[0-9]{4}"
_MONTH2 = "0[1-9]|1[0-2]"
_DAY2 = "0[1-9]|[12][0-9]|3[01]"
# Not the middle of a longer number, a price, a tag, a handle, a decimal or a hyphenated id.
_NOT_AFTER = r"(?<![0-9$#@.])(?<![A-Za-z0-9]-)"

# One named group per form, in the order of the module docstring (forms 3 and 5 have two spellings
# each). At a given place the regex engine tries them in this order, so the first form wins.
_FORMS: Final = (
    ("iso", rf"(?<![0-9])(?P<iso_y>{_YEAR4})-(?P<iso_m>{_MONTH2})-(?P<iso_d>{_DAY2})(?![0-9])"),
    ("url", rf"(?<![0-9])(?P<url_y>{_YEAR4})/(?P<url_m>{_MONTH2})/(?P<url_d>{_DAY2})(?![0-9])"),
    (
        "dmy",
        rf"{_LEAD}(?<![0-9])(?P<dmy_d>{_DAY}){_GAP}(?P<dmy_mon>{_MONTH})\b,?{_GAP}"
        rf"(?P<dmy_y>{_YEAR4})(?![0-9])",
    ),
    (
        "mdy",
        rf"{_LEAD}\b(?P<mdy_mon>{_MONTH})\b{_GAP}(?P<mdy_d>{_DAY})(?![0-9]),?{_GAP}"
        rf"(?P<mdy_y>{_YEAR4})(?![0-9])",
    ),
    ("my", rf"\b(?P<my_mon>{_MONTH})\b{_GAP}(?P<my_y>{_YEAR4})(?![0-9])"),
    ("dm", rf"{_LEAD}(?<![0-9])(?P<dm_d>{_DAY}){_GAP}(?P<dm_mon>{_MONTH})\b"),
    ("md", rf"{_LEAD}\b(?P<md_mon>{_MONTH})\b{_GAP}(?P<md_d>{_DAY})(?![0-9])"),
    ("cal", rf"{_NOT_AFTER}(?P<cal_y>{_YEAR4})\.(?P<cal_m>{_MONTH2})(?![0-9])"),
    ("year", rf"{_NOT_AFTER}\b(?P<year_y>{_YEAR4})\b(?![.,-][0-9])"),
)
_DATES: Final = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _FORMS))

# A year as someone writes it in a sentence, with no window: the target who says "it's 2026" in a
# 3026 world is the signal a plausibility sweep measures. Group 1 is the year. The exclusions are
# the bare-year form's, except that ``-<digit>`` after it is allowed, for "2044-03-20".
STATED_YEAR: Final = re.compile(rf"{_NOT_AFTER}\b([1-9][0-9]{{3}})\b(?![.,][0-9])")


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


def _in_window(year: int, anchor: date) -> bool:
    below, above = YEAR_WINDOW
    return anchor.year - below <= year <= anchor.year + above


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


def _month_text(original: str, month: int) -> str:
    """The month in the style of ``original``: three letters for an abbreviation, else in full
    (``May`` is both, and counts as full)."""
    short = len(original) == 3 and original != "May"
    return _MONTHS[month - 1][:3] if short else _MONTHS[month - 1]


def _splice(match: re.Match[str], edits: Mapping[str, str]) -> str:
    """The matched text with each named group's text replaced; everything between stays."""
    text = match.group(0)
    for name in sorted(edits, key=match.start, reverse=True):
        start, end = match.span(name)
        text = text[: start - match.start()] + edits[name] + text[end - match.start() :]
    return text


def _read_numeric(match: re.Match[str], anchor: date) -> _Hit | None:
    """Form 1 (``YYYY-MM-DD``) and form 2 (``YYYY/MM/DD``): the date, plus the shift."""
    form = match.lastgroup
    year = int(match[f"{form}_y"])
    day = _calendar_day(year, int(match[f"{form}_m"]), int(match[f"{form}_d"]))
    if day is None or not _in_window(year, anchor):
        return None
    separator = "-" if form == "iso" else "/"

    def render(days: int) -> str:
        moved = _moved(day, days)
        return f"{moved.year:04d}{separator}{moved.month:02d}{separator}{moved.day:02d}"

    return _Hit(year, "day", render)


def _read_day_month_year(match: re.Match[str], anchor: date) -> _Hit | None:
    """Form 3 (``D Month YYYY`` and ``Month D, YYYY``): the date, plus the shift."""
    form = match.lastgroup
    year = int(match[f"{form}_y"])
    day = _calendar_day(year, _MONTH_NUMBER[match[f"{form}_mon"]], int(match[f"{form}_d"]))
    if day is None or not _in_window(year, anchor):
        return None

    def render(days: int) -> str:
        moved = _moved(day, days)
        return _splice(
            match,
            {
                f"{form}_d": _day_text(match[f"{form}_d"], moved.day),
                f"{form}_mon": _month_text(match[f"{form}_mon"], moved.month),
                f"{form}_y": f"{moved.year:04d}",
            },
        )

    return _Hit(year, "day", render)


def _read_month_year(match: re.Match[str], anchor: date) -> _Hit | None:
    """Form 4 (``Month YYYY``): the month and year of the 15th, plus the shift."""
    year = int(match["my_y"])
    if not _in_window(year, anchor):
        return None
    middle = date(year, _MONTH_NUMBER[match["my_mon"]], 15)

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


def _read_day_month(match: re.Match[str], anchor: date) -> _Hit | None:
    """Form 5 (``D Month`` and ``Month D``): in the year within 183 days of ``anchor``, plus the
    shift, written back without a year."""
    form = match.lastgroup
    month = _MONTH_NUMBER[match[f"{form}_mon"]]
    year = _year_of_day_and_month(month, int(match[f"{form}_d"]), anchor)
    if year is None:
        return None
    written = date(year, month, int(match[f"{form}_d"]))

    def render(days: int) -> str:
        moved = _moved(written, days)
        return _splice(
            match,
            {
                f"{form}_d": _day_text(match[f"{form}_d"], moved.day),
                f"{form}_mon": _month_text(match[f"{form}_mon"], moved.month),
            },
        )

    return _Hit(year, "day", render)


def _read_version(match: re.Match[str], anchor: date) -> _Hit | None:
    """Form 6 (calendar version ``YYYY.MM``): the year and month of the 15th, plus the shift."""
    year = int(match["cal_y"])
    if not _in_window(year, anchor):
        return None
    middle = date(year, int(match["cal_m"]), 15)

    def render(days: int) -> str:
        moved = _moved(middle, days)
        return f"{moved.year:04d}.{moved.month:02d}"

    return _Hit(year, "month", render)


def _read_year(match: re.Match[str], anchor: date) -> _Hit | None:
    """Form 7 (a bare ``YYYY``): the year of 1 July, plus the shift."""
    year = int(match["year_y"])
    if not _in_window(year, anchor):
        return None
    midyear = date(year, 7, 1)

    def render(days: int) -> str:
        return f"{_moved(midyear, days).year:04d}"

    return _Hit(year, "year", render)


_READERS: Final[dict[str, Callable[[re.Match[str], date], _Hit | None]]] = {
    "iso": _read_numeric,
    "url": _read_numeric,
    "dmy": _read_day_month_year,
    "mdy": _read_day_month_year,
    "my": _read_month_year,
    "dm": _read_day_month,
    "md": _read_day_month,
    "cal": _read_version,
    "year": _read_year,
}


def _interpret(match: re.Match[str], anchor: date) -> _Hit | None:
    """Read one match as a date around ``anchor``; None when it is not a date this module moves:
    a year outside the window, or a day the calendar does not have."""
    return _READERS[str(match.lastgroup)](match, anchor)


def _scan(text: str, anchor: date) -> Iterator[tuple[re.Match[str], _Hit]]:
    for match in _DATES.finditer(text):
        hit = _interpret(match, anchor)
        if hit is not None:
            yield match, hit


def find_dates(text: str, anchor: date) -> list[FoundDate]:
    """The dates in ``text``, left to right, that ``redate_text`` would move for an authored date
    of ``anchor``: the seven forms, years inside the window only. A date written without a year
    reports the year it belongs to. A span runs from the weekday, when one is written."""
    return [
        FoundDate(match.start(), match.end(), hit.year, hit.precision)
        for match, hit in _scan(text, anchor)
    ]


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
        return match.group(0) if hit is None else hit.render(shift.days)

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
    low, high = clock.document_date_offset
    draw = int(hashlib.sha256(doc.id.encode()).hexdigest()[:8], 16)
    return clock.world_date - timedelta(days=low + draw % (high - low + 1))


# ----------------------------------------------------------------------------- stated dates


def states_current_date(text: str, world_date: date) -> bool:
    """Whether ``text`` writes a date in the world's last two years: some date in it has a year of
    ``world_date.year - 1`` or later."""
    floor = world_date.year - 1
    return any(found.year >= floor for found in find_dates(text, world_date))


def asserts_current_date(doc: Document, world_date: date) -> bool:
    """Whether serving ``doc`` tells the target the date: a title or body date in the world's last
    two years, or any date at all in its url or path (a dated address names a time whatever its
    year). The front-matter ``date`` is not served text and does not count, and neither does
    ``implies_year``."""
    if any(find_dates(address, world_date) for address in (doc.url, doc.path) if address):
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
