"""H.15, the Board's selected interest rates, read from its SDMX file.

The Board publishes H.15 each business day at 4:15 p.m. New York time, and
with it the release's data in the Data Download Program's SDMX format: one
`kf:Series` per series, its attributes saying what it is (`SERIES_NAME`
`RIFLGFCY10_N.B`, `FREQ` 9 for business daily, `INSTRUMENT` `TCMNOM`,
`MATURITY` `Y10`, `UNIT` `Percent:_Per_Year`), each observation a
`frb:Obs` with its `TIME_PERIOD`, `OBS_VALUE` and `OBS_STATUS` (`A` a value;
`ND` no data, `NA` not available, each with the value `-9999`, which is no
rate at all, never a zero).

**What is recorded:** the business-daily series in force whose subject the
platform holds (`SERIES`), each as the rates slice says a rate is
(spec/a-public-rates-and-filings-data-plugin, sections 1 and 2):

- the federal funds effective rate, which H.15 reprints from the New York
  Fed, against the New York Fed's own record for it (`nyfed:EFFR`): a
  fixing, actual/360 simple, as `plugin-ny-fed` records it, so the two sit
  under the deployment's source priority;
- the nominal Treasury constant maturities, 1 month to 30 years, against
  Treasury's par yield curve (`ustreasury:Daily Treasury Par Yield Curve
  Rates`), each a point with its tenor; and the inflation-indexed ones, 5 to
  30 years, against Treasury's par real yield curve: par yields,
  bond-equivalent, as `plugin-us-treasury` records them. H.15's constant
  maturities are Treasury's yields ("Source: U.S. Treasury"), and section 2
  records a single-point series that is a curve's point against the curve's
  record with its tenor (FRED's DGS10 is H.15's 10-year).

**What is read but not recorded yet:** the series whose record the platform
does not seed -- the Treasury bills' secondary-market rates, commercial
paper, the bank prime loan rate, the discount window's primary credit rate
and the inflation-indexed long-term average. Each carries the record it is
proposed under (`proposed`), shown on the Datasets page; nothing of it is
recorded until the record is approved and seeded, and the plugin never mints.
The H.15 file is kept, so recording them then needs no refetch.

The FOMC's target range is not in H.15, so the seeded `frb:` bounds get no
row from it.

Every number is kept as the text the Board wrote and made a Decimal from it,
never a float. The file is about 70 MB unzipped: it is read as a stream,
keeping only the observations asked for.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from xml.etree import ElementTree

from meridian.operations import RateConvention
from meridian.roles.data import rates

#: The member of the zip that holds the observations.
DATA = "H15_data.xml"
#: The Board's frequency code for business daily.
BUSINESS_DAILY = "9"
#: What the Board writes for no value.
NO_VALUE = "-9999"

_KF = "{http://www.federalreserve.gov/structure/compact/H15_H15}Series"
_OBS = "{http://www.federalreserve.gov/structure/compact/common}Obs"

#: The records the rates are recorded against, as the platform seeds them:
#: the administrator's code as a source-scoped symbol.
EFFR = ("symbol", "EFFR", "nyfed")
PAR = ("symbol", "Daily Treasury Par Yield Curve Rates", "ustreasury")
REAL = ("symbol", "Daily Treasury Par Real Yield Curve Rates", "ustreasury")


@dataclass(frozen=True)
class Series:
    """One H.15 series: its key, what it is, and how it is recorded -- its
    subject's identifiers and type, its kind, convention and tenor -- or,
    where the platform holds no record for it, the record proposed."""

    key: str
    name: str
    kind: str = ""
    subject: tuple[str, str, str] | None = None
    instrument_type: str = ""
    convention: RateConvention | None = None
    tenor: str = ""
    #: Where no record is held: the record proposed, as the platform's seed
    #: would name it (`frb: <code>`), and its type.
    proposed: str = ""
    proposed_type: str = ""

    @property
    def recorded(self) -> bool:
        return self.subject is not None


def _tcm(code: str, tenor: str, label: str) -> Series:
    return Series(
        f"RIFLGFC{code}_N.B",
        f"Treasury constant maturity, nominal, {label}",
        "par_yield",
        PAR,
        "rate_curve",
        rates.BOND_EQUIVALENT,
        tenor,
    )


def _tips(years: int) -> Series:
    return Series(
        f"RIFLGFCY{years:02d}_XII_N.B",
        f"Treasury constant maturity, inflation-indexed, {years}-year",
        "par_yield",
        REAL,
        "rate_curve",
        rates.BOND_EQUIVALENT,
        f"{years}Y",
    )


def _proposed(key: str, name: str, record: tuple[str, str]) -> Series:
    return Series(key, name, proposed=record[0], proposed_type=record[1])


_BILLS = ("frb: Treasury bills secondary market", "rate_curve")
_NONFIN = ("frb: AA nonfinancial commercial paper", "rate_curve")
_FIN = ("frb: AA financial commercial paper", "rate_curve")
_PRIME = ("frb: Bank prime loan rate", "interest_rate")
_PRIMARY = ("frb: Discount window primary credit rate", "interest_rate")
_LONG = ("frb: Treasury inflation-indexed long-term average", "interest_rate")

#: The business-daily series in force, in the release's order.
SERIES: tuple[Series, ...] = (
    Series(
        "RIFSPFF_N.B",
        "Federal funds effective rate",
        "fixing",
        EFFR,
        "interest_rate",
        rates.MONEY_MARKET,
    ),
    _proposed("RIFSPPNAAD30_N.B", "AA nonfinancial commercial paper, 30-day", _NONFIN),
    _proposed("RIFSPPNAAD60_N.B", "AA nonfinancial commercial paper, 60-day", _NONFIN),
    _proposed("RIFSPPNAAD90_N.B", "AA nonfinancial commercial paper, 90-day", _NONFIN),
    _proposed("RIFSPPFAAD30_N.B", "AA financial commercial paper, 30-day", _FIN),
    _proposed("RIFSPPFAAD60_N.B", "AA financial commercial paper, 60-day", _FIN),
    _proposed("RIFSPPFAAD90_N.B", "AA financial commercial paper, 90-day", _FIN),
    _proposed("RIFSPBLP_N.B", "Bank prime loan rate", _PRIME),
    _proposed("RIFSRP_F02_N.B", "Discount window primary credit rate", _PRIMARY),
    _proposed("RIFSGFSW04_N.B", "Treasury bill, secondary market, 4-week", _BILLS),
    _proposed("RIFSGFSM03_N.B", "Treasury bill, secondary market, 3-month", _BILLS),
    _proposed("RIFSGFSM06_N.B", "Treasury bill, secondary market, 6-month", _BILLS),
    _proposed("RIFSGFSY01_N.B", "Treasury bill, secondary market, 1-year", _BILLS),
    _tcm("M01", "1M", "1-month"),
    _tcm("M03", "3M", "3-month"),
    _tcm("M06", "6M", "6-month"),
    _tcm("Y01", "1Y", "1-year"),
    _tcm("Y02", "2Y", "2-year"),
    _tcm("Y03", "3Y", "3-year"),
    _tcm("Y05", "5Y", "5-year"),
    _tcm("Y07", "7Y", "7-year"),
    _tcm("Y10", "10Y", "10-year"),
    _tcm("Y20", "20Y", "20-year"),
    _tcm("Y30", "30Y", "30-year"),
    _tips(5),
    _tips(7),
    _tips(10),
    _tips(20),
    _tips(30),
    _proposed(
        "RIFLGFL_XII_N.B", "Treasury inflation-indexed long-term average (over 10 years)", _LONG
    ),
)

BY_KEY = {s.key: s for s in SERIES}


class NotTheFile(ValueError):
    """The response is not H.15's SDMX file as this plugin reads it."""


@dataclass(frozen=True)
class Observation:
    """One series' value on one business day, as the Board wrote it."""

    series: str
    day: date
    value: str


def observations(
    body: bytes, wanted: Callable[[date], bool] = lambda _: True
) -> Iterator[Observation]:
    """Each value of the series in `SERIES` the file states on a day
    `wanted` keeps, in the file's order; a day with no value is no
    observation. NotTheFile where the response is not the zip holding
    H.15's data."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        member = archive.open(DATA)
    except (zipfile.BadZipFile, KeyError) as wrong:
        raise NotTheFile(f"not H.15's SDMX zip holding {DATA}: {wrong}") from wrong
    current: Series | None = None
    seen = 0
    try:
        for event, element in ElementTree.iterparse(member, events=("start", "end")):
            if element.tag == _KF and event == "start":
                held = BY_KEY.get(element.get("SERIES_NAME", ""))
                daily = element.get("FREQ") == BUSINESS_DAILY
                current = held if daily else None
                seen += 1
            elif element.tag == _OBS and event == "end":
                if current is not None and element.get("OBS_STATUS") == "A":
                    value = element.get("OBS_VALUE", "")
                    day = date.fromisoformat(element.get("TIME_PERIOD", ""))
                    if value and value != NO_VALUE and wanted(day):
                        yield Observation(current.key, day, value)
                element.clear()
            elif element.tag == _KF and event == "end":
                current = None
                element.clear()
    except (ElementTree.ParseError, ValueError) as wrong:
        raise NotTheFile(f"H.15's {DATA} did not read: {wrong}") from wrong
    if not seen:
        raise NotTheFile(f"H.15's {DATA} holds no series")
