"""H.15, the Board's selected interest rates, read from its SDMX file.

The Board publishes H.15 each business day at 4:15 p.m. New York time, and
with it the release's data in the Data Download Program's SDMX format: one
`kf:Series` per series, its attributes saying what it is (`SERIES_NAME`
`RIFLGFCY10_N.B`, `FREQ` 9 for business daily, `INSTRUMENT` `TCMNOM`,
`MATURITY` `Y10`, `UNIT` `Percent:_Per_Year`), each observation a
`frb:Obs` with its `TIME_PERIOD`, `OBS_VALUE` and `OBS_STATUS` (`A` a value;
`ND` no data, `NA` not available, each with the value `-9999`, which is no
rate at all, never a zero).

**What is recorded:** every business-daily series in force (`SERIES`), each
as the rates slice says a rate is (spec/a-public-rates-and-filings-data-
plugin, sections 1 and 2), about a record the platform seeds, by the
administrator's code as a source-scoped symbol:

- the federal funds effective rate, which H.15 reprints from the New York
  Fed, against the New York Fed's own record for it (`nyfed: EFFR`): a
  fixing, actual/360 simple, as `plugin-ny-fed` records it, so the two sit
  under the deployment's source priority;
- the nominal Treasury constant maturities, 1 month to 30 years, against
  Treasury's par yield curve (`ustreasury: Daily Treasury Par Yield Curve
  Rates`), each a point with its tenor; and the inflation-indexed ones, 5 to
  30 years, against Treasury's par real yield curve: par yields,
  bond-equivalent, as `plugin-us-treasury` records them. H.15's constant
  maturities are Treasury's yields ("Source: U.S. Treasury"), and section 2
  records a single-point series that is a curve's point against the curve's
  record with its tenor (FRED's DGS10 is H.15's 10-year);
- H.15's own series, against the Board's records (ruling 541, seeded
  2026-10-23): the Treasury bills' secondary-market rates (4 weeks to 1
  year) and AA nonfinancial and financial commercial paper (1 to 3 months:
  the release's 1-, 2- and 3-month rates are the 30-, 60- and 90-day ones),
  curves of discount rates, actual/360 ("On a discount basis", footnotes 3
  and 4), kept off Treasury's own bill record, a different series; the bank
  prime loan rate, a fixing, actual/360 (footnote 3); the discount window's
  primary credit rate, a fixing, actual/360 simple: H.15 states no
  convention for it, and it is read as what it is, a Fed-set overnight rate
  quoted on the money-market convention, like the federal funds rate; and
  the inflation-indexed long-term average, the average yield of every TIPS
  with more than ten years to run (footnote 11), an average, bond-equivalent
  (no kind is closer: it averages across securities, not over a period).

Every rate carries a convention: the contract's `Rate.convention` is never
unset, and the lake refuses a rate without one, so `Series.convention` is
required.

The FOMC's target range is not in H.15: FRED supplies its bounds (ruling
540).

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
BILLS = ("symbol", "Treasury bills secondary market", "frb")
NONFINANCIAL = ("symbol", "AA nonfinancial commercial paper", "frb")
FINANCIAL = ("symbol", "AA financial commercial paper", "frb")
PRIME = ("symbol", "Bank prime loan rate", "frb")
PRIMARY = ("symbol", "Discount window primary credit rate", "frb")
LONG = ("symbol", "Treasury inflation-indexed long-term average", "frb")


@dataclass(frozen=True)
class Series:
    """One H.15 series: its key, what it is, and how it is recorded -- its
    subject's identifiers and type, its kind, convention and tenor."""

    key: str
    name: str
    kind: str
    subject: tuple[str, str, str]
    instrument_type: str
    convention: RateConvention
    tenor: str = ""


def _curve(
    key: str,
    name: str,
    kind: str,
    subject: tuple[str, str, str],
    convention: RateConvention,
    tenor: str,
) -> Series:
    return Series(key, name, kind, subject, "rate_curve", convention, tenor)


def _tcm(code: str, tenor: str, label: str) -> Series:
    return _curve(
        f"RIFLGFC{code}_N.B",
        f"Treasury constant maturity, nominal, {label}",
        "par_yield",
        PAR,
        rates.BOND_EQUIVALENT,
        tenor,
    )


def _tips(years: int) -> Series:
    return _curve(
        f"RIFLGFCY{years:02d}_XII_N.B",
        f"Treasury constant maturity, inflation-indexed, {years}-year",
        "par_yield",
        REAL,
        rates.BOND_EQUIVALENT,
        f"{years}Y",
    )


def _paper(code: str, subject: tuple[str, str, str], label: str, days: int) -> Series:
    return _curve(
        f"RIFSPP{code}AD{days}_N.B",
        f"AA {label} commercial paper, {days}-day",
        "discount",
        subject,
        rates.DISCOUNT,
        f"{days // 30}M",
    )


def _bill(code: str, tenor: str, label: str) -> Series:
    return _curve(
        f"RIFSGFS{code}_N.B",
        f"Treasury bill, secondary market, {label}",
        "discount",
        BILLS,
        rates.DISCOUNT,
        tenor,
    )


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
    _paper("NA", NONFINANCIAL, "nonfinancial", 30),
    _paper("NA", NONFINANCIAL, "nonfinancial", 60),
    _paper("NA", NONFINANCIAL, "nonfinancial", 90),
    _paper("FA", FINANCIAL, "financial", 30),
    _paper("FA", FINANCIAL, "financial", 60),
    _paper("FA", FINANCIAL, "financial", 90),
    Series(
        "RIFSPBLP_N.B", "Bank prime loan rate", "fixing", PRIME, "interest_rate", rates.MONEY_MARKET
    ),
    Series(
        "RIFSRP_F02_N.B",
        "Discount window primary credit rate",
        "fixing",
        PRIMARY,
        "interest_rate",
        rates.MONEY_MARKET,
    ),
    _bill("W04", "4W", "4-week"),
    _bill("M03", "3M", "3-month"),
    _bill("M06", "6M", "6-month"),
    _bill("Y01", "1Y", "1-year"),
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
    Series(
        "RIFLGFL_XII_N.B",
        "Treasury inflation-indexed long-term average (over 10 years)",
        "average",
        LONG,
        "interest_rate",
        rates.BOND_EQUIVALENT,
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
