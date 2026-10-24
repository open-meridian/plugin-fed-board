"""The Board's daily zero curve, `feds200628`, read from its CSV.

The Board's staff publish the nominal Treasury yield curve fitted by
Gurkaynak, Sack and Wright (FEDS 2006-28) as one CSV, every business day
since 14 June 1961, updated in batches days to weeks behind: a few lines of
notes, then a header (`Date,BETA0,...`) and a row per date. Its notes say it
is "not an official Federal Reserve statistical release" and "subject to
delay, revision, or methodological changes without advance notice"; and
which columns are what -- `SVENYXX`, the zero-coupon yield at XX years,
continuously compounded; `SVENPYXX` par yields and `SVENFXX`, `SVEN1FXX`
forwards; `BETA0` to `TAU2` the fitted parameters.

**What is recorded:** the zero-coupon yields, `SVENY01` to `SVENY30`, as the
rates slice says a curve is (spec/a-public-rates-and-filings-data-plugin,
section 2): one record, the platform's `frb:feds200628` (a `rate_curve`),
and a row per tenor and date -- kind `zero`, continuously compounded
(actual/365 fixed, the SDK's `CONTINUOUS`), its tenor 1Y to 30Y. A tenor the
Board leaves `NA` (the curve reached 7 years until August 1971, 20 until
November 1985) is no row, never a zero: the tenor set changes, as section 2
expects. The par yields, forwards and parameters
are left in the kept file: the fitting is the analytics component's
(spec/a-public-rates-and-filings-data-plugin, "Out of scope").

Every number is kept as the text the Board wrote and made a Decimal from
it, never a float.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date

#: The record the curve is recorded against, as the platform seeds it.
CURVE = ("symbol", "feds200628", "frb")
#: The zero-coupon yields' columns: SVENY01 to SVENY30.
COLUMNS = tuple(f"SVENY{years:02d}" for years in range(1, 31))
#: What the Board writes for no value.
NO_VALUE = "NA"


class NotTheFile(ValueError):
    """The response is not the zero curve's CSV as this plugin reads it."""


@dataclass(frozen=True)
class Point:
    """One tenor's zero-coupon yield on one date, as the Board wrote it."""

    column: str
    tenor: str
    day: date
    value: str


def points(body: bytes, wanted: Callable[[date], bool] = lambda _: True) -> Iterator[Point]:
    """Each zero-coupon yield the file states on a day `wanted` keeps, by
    date then tenor; a tenor left `NA` is no point. NotTheFile where the
    response has no header naming the zero-coupon columns."""
    text = body.decode("utf-8", errors="replace")
    lines = text.splitlines()
    start = next((n for n, line in enumerate(lines) if line.startswith("Date,")), None)
    if start is None:
        raise NotTheFile("the zero curve's CSV has no header line beginning Date,")
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    header = next(reader)
    at = {name: n for n, name in enumerate(header)}
    missing = [c for c in COLUMNS if c not in at]
    if missing:
        raise NotTheFile(f"the zero curve's CSV has no column {missing[0]}")
    for row in reader:
        if not row or not row[0].strip():
            continue
        try:
            day = date.fromisoformat(row[0].strip())
        except ValueError as wrong:
            raise NotTheFile(f"the zero curve's CSV has a row dated {row[0]!r}") from wrong
        if not wanted(day):
            continue
        for column in COLUMNS:
            value = row[at[column]].strip() if at[column] < len(row) else ""
            if value and value != NO_VALUE:
                yield Point(column, f"{int(column[5:])}Y", day, value)
