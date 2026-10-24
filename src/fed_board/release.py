"""One H.10 weekly release, read from the Board's page as it prints it.

The Board publishes H.10 on its own site (https://www.federalreserve.gov/
releases/h10/current/default.htm, and each past week at
/releases/h10/<YYYYMMDD>/default.htm): noon buying rates in New York for
cable transfers, certified by the Federal Reserve Bank of New York for
customs purposes, one table a week, about two dozen currencies against the
US dollar, the five business days of the week before. The page says how each
is quoted: "Rates in currency units per U.S. dollar except as noted by an
asterisk", and the asterisk's footnote, "U.S. dollars per currency unit".

What is read here, and nothing else:

- the release date (`<div class="dates">Release Date: October 5, 2026</div>`);
- the table's columns, each a day printed without its year (`Sep. 28`), the
  year taken from the release date: a column whose month and day would fall
  after the release date in its year is the year before (a January release
  covers the last days of December);
- each currency's row: its country, an asterisk where it is quoted in US
  dollars per unit, its currency's name, and a value per day, or `ND` (no
  data for that date: a holiday), which is no rate at all;
- the rows under "Memo:", the Board's dollar indexes, are not currencies'
  rates and are left as printed.

Every number is kept as the text it was printed in and made a Decimal from
that text, never a float. A page that does not hold this table -- the Board
changed its layout before 2012, and could again -- is refused with why, and
nothing is recorded from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

#: The Board's word for a day it has no rate for.
NO_DATA = "ND"

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_RELEASE_DATE = re.compile(
    r"Release\s+Date:\s*(?:[A-Za-z]+,\s*)?([A-Za-z]+)\.?\s+(\d{1,2}),\s*(\d{4})"
)
_COLUMN = re.compile(r"^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})$")
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
# An index's unit, where a currency's name would be: `JAN06=100`.
_INDEX = re.compile(r"=\s*\d+$")


class NotARelease(ValueError):
    """The page is not an H.10 weekly release this plugin can read."""


@dataclass(frozen=True)
class Rate:
    """One currency's rate on one day, as the release prints it.

    `per_dollar` is True where the rate is currency units per US dollar (the
    Board's default), False where it is US dollars per unit (the asterisk):
    the euro, the pound, the Australian and New Zealand dollars."""

    country: str
    currency: str
    day: date
    value: Decimal
    text: str
    per_dollar: bool


@dataclass(frozen=True)
class Release:
    """A weekly release: its date, its days, its rates and what was not a rate."""

    released: date
    days: tuple[date, ...]
    rates: tuple[Rate, ...]
    # Each currency's day with no rate (ND), as (country, currency, day).
    no_data: tuple[tuple[str, str, date], ...] = field(default=())
    # Each row read that is not a currency's rate, as printed: the indexes.
    memo: tuple[str, ...] = field(default=())

    @property
    def currencies(self) -> tuple[tuple[str, str, bool], ...]:
        """Each currency the release prints, once, in its order."""
        seen: dict[tuple[str, str], bool] = {}
        for rate in self.rates:
            seen.setdefault((rate.country, rate.currency), rate.per_dollar)
        for country, currency, _ in self.no_data:
            seen.setdefault((country, currency), True)
        return tuple((c, n, per) for (c, n), per in seen.items())


class _Cells(HTMLParser):
    """The release date's text and the `statistics` table's rows, each a
    list of its cells' text, the header row first."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.dates_text: list[str] = []
        self.rows: list[list[str]] = []
        self._in_dates = 0
        self._in_table = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div" and "dates" in classes or self._in_dates and tag == "div":
            self._in_dates += 1
        if tag == "table" and ("statistics" in classes or self._in_table):
            self._in_table += 1
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in ("td", "th"):
            # The Board's memo rows open a cell with no row around it: a
            # cell outside a row opens one.
            if self._row is None:
                self._row = []
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._in_dates:
            self._in_dates -= 1
        if not self._in_table:
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._in_table -= 1

    def handle_data(self, data: str) -> None:
        if self._in_dates:
            self.dates_text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def released_on(text: str) -> date:
    """The release date a page states, from its "Release Date:" line."""
    found = _RELEASE_DATE.search(" ".join(text.split()))
    if found is None:
        raise NotARelease("it states no release date")
    month = _MONTHS.get(found.group(1)[:3].lower())
    if month is None:
        raise NotARelease(f"its release date names no month: {found.group(0)!r}")
    return date(int(found.group(3)), month, int(found.group(2)))


def _column_day(text: str, released: date) -> date:
    found = _COLUMN.match(text.strip())
    month = _MONTHS.get(found.group(1).lower()) if found else None
    if found is None or month is None:
        raise NotARelease(f"a column is not a day: {text!r}")
    day = date(released.year, month, int(found.group(2)))
    # A column after the release date is last year's: December's days in a
    # January release.
    return date(released.year - 1, month, day.day) if day > released else day


def parse(page: str) -> Release:
    """The release `page` prints, or NotARelease saying why it is not one."""
    cells = _Cells()
    cells.feed(page)
    cells.close()
    released = released_on(" ".join(cells.dates_text) or page)
    if not cells.rows:
        raise NotARelease("it holds no table of rates")
    header, *body = cells.rows
    if len(header) < 3 or header[0].upper() != "COUNTRY" or header[1].upper() != "CURRENCY":
        raise NotARelease(f"its table's header is not COUNTRY, CURRENCY and days: {header!r}")
    days = tuple(_column_day(text, released) for text in header[2:])
    rates: list[Rate] = []
    no_data: list[tuple[str, str, date]] = []
    memo: list[str] = []
    in_memo = False
    for row in body:
        if row[0].rstrip(":").strip().upper() == "MEMO":
            in_memo = True
            continue
        if in_memo or len(row) != len(header) or _INDEX.search(row[1]):
            if any(cell for cell in row):
                memo.append(" | ".join(row))
            continue
        name = row[0].strip()
        per_dollar = not name.startswith("*")
        country = name.lstrip("*").strip()
        currency = row[1].strip()
        if not country or not currency:
            raise NotARelease(f"a row names no country or currency: {row!r}")
        for day, text in zip(days, row[2:], strict=True):
            value = text.strip()
            if value.upper() == NO_DATA:
                no_data.append((country, currency, day))
                continue
            if not _NUMBER.match(value):
                raise NotARelease(f"{country}'s {currency} on {day} is not a number: {value!r}")
            try:
                rates.append(Rate(country, currency, day, Decimal(value), value, per_dollar))
            except InvalidOperation as failed:  # pragma: no cover - the pattern holds it
                raise NotARelease(f"{value!r} is not a number") from failed
    if not rates and not no_data:
        raise NotARelease("its table holds no currency's rate")
    return Release(released, days, tuple(rates), tuple(no_data), tuple(memo))


def last_modified_ns(header: str) -> int:
    """An HTTP Last-Modified header's moment, in nanoseconds since the epoch;
    0 where there is none or it does not read."""
    try:
        moment = datetime.strptime(header.strip(), "%a, %d %b %Y %H:%M:%S GMT")
    except ValueError:
        return 0
    return int(moment.replace(tzinfo=UTC).timestamp()) * 10**9
