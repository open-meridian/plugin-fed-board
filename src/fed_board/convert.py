"""A release's rates to the lake's prices: each rate the price of one
currency's cash instrument in the other, as the Board quotes it.

The lake keeps FX as prices (spec/the-lake, its Q3): a rate is the price of a
currency's cash instrument, in another currency. The Board quotes most
currencies per US dollar -- CHF 0.8293 is what one dollar costs in francs --
so that rate is the price of the dollar's cash instrument, in francs; and the
euro, the pound, the Australian and the New Zealand dollars in dollars per
unit -- EUR 1.1259 is what one euro costs in dollars -- so that rate is the
price of the euro's cash instrument, in dollars. Nothing is inverted, here or
in the lake (principle 14): a reader wanting francs per dollar the other way
inverts it itself, and says so.

Each price:

- **kind** `close`, the dataset's declared close for the business date: the
  dataset declares its day as New York's, ending at noon (`day_time_zone`
  America/New_York, `day_end_minute` 720), so the close is the noon buying
  rate, as close's entry has it ("otherwise the last price of the day the
  dataset declares"). Basis `per_unit`.
- **business_date** the rate's date, as the release prints it: a plain date.
- **valid from and until** the declared day: noon the day before to noon on
  the date, New York time, so a rate is never "forming" once published.
- **row key** the currency's code and the date (`CHF:2026-10-02`): the same
  rate read again from any release is a repeat, and a rate the Board corrects
  is the same row's next version.
- **source time** `published`, the page's Last-Modified time, which the
  Board's server states (16:15 New York on a release day); none where it
  states none.
- **raw** the response it was read from, kept in the plugin's storage.

A rate whose currency the plugin cannot name (currencies.py) is not a price;
it is returned as not converted. A rate whose subject did not resolve is not
sent: the subject is reported missing by the caller, and the rest go.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from meridian import Money, ObservationMeta, Price, SourceTime
from meridian.plugin.v1 import operations_pb2 as ops

from .currencies import USD, code_of
from .release import Rate, Release

#: The day the dataset declares: New York's, ending at noon.
DAY_TIME_ZONE = "America/New_York"
DAY_END_MINUTE = 12 * 60
NEW_YORK = ZoneInfo(DAY_TIME_ZONE)


def _ns(moment: datetime) -> int:
    return int(moment.timestamp()) * 10**9


def day_bounds(day: date) -> tuple[int, int]:
    """The declared day for business date `day`: from noon the day before to
    noon on it, New York time, in nanoseconds since the epoch."""
    noon = time(DAY_END_MINUTE // 60, DAY_END_MINUTE % 60)
    end = datetime.combine(day, noon, NEW_YORK)
    start = datetime.combine(day - timedelta(days=1), noon, NEW_YORK)
    return _ns(start), _ns(end)


def row_key(code: str, day: date) -> str:
    return f"{code}:{day.isoformat()}"


@dataclass(frozen=True)
class Quoted:
    """What one rate is a price of, and in what: the ISO codes of the
    subject's currency and of the price's."""

    code: str
    subject: str
    priced_in: str


def quoted(rate: Rate) -> Quoted | None:
    """How the Board quotes `rate`, or None where the plugin cannot name its
    currency."""
    code = code_of(rate.country, rate.currency)
    if code is None:
        return None
    if rate.per_dollar:
        return Quoted(code, subject=USD, priced_in=code)
    return Quoted(code, subject=code, priced_in=USD)


@dataclass(frozen=True)
class Converted:
    """A release as prices, and what of it was not: each currency the plugin
    could not name, and each subject that did not resolve, once each."""

    prices: tuple[Price, ...]
    unconverted: tuple[str, ...]
    unresolved: tuple[str, ...]


def to_prices(
    release: Release,
    instruments: Mapping[str, str],
    *,
    dataset: str,
    raw: ops.RawRecordRef,
    published_ns: int,
    days: Sequence[date] | None = None,
) -> Converted:
    """The prices `release` states, on `days` where given (every day
    otherwise); `instruments` maps an ISO code to the deployment's cash
    instrument resolved for it."""
    prices: list[Price] = []
    unconverted: dict[str, None] = {}
    unresolved: dict[str, None] = {}
    wanted = set(days) if days is not None else None
    for rate in release.rates:
        if wanted is not None and rate.day not in wanted:
            continue
        how = quoted(rate)
        if how is None:
            unconverted[f"{rate.country} {rate.currency}"] = None
            continue
        subject = instruments.get(how.subject)
        if not subject:
            unresolved[how.subject] = None
            continue
        start, end = day_bounds(rate.day)
        prices.append(
            Price(
                meta=ObservationMeta(
                    row_key=row_key(how.code, rate.day),
                    subjects=[ops.SubjectRef(entity_id=subject)],
                    source=ops.Source(dataset=dataset),
                    valid_from_ns=start,
                    valid_until_ns=end,
                    business_date=rate.day,
                    source_times=(
                        [SourceTime(kind="published", at_ns=published_ns)] if published_ns else []
                    ),
                    raw=raw,
                ),
                kind="close",
                price=Money(rate.value, how.priced_in),
                basis="per_unit",
            )
        )
    return Converted(tuple(prices), tuple(unconverted), tuple(unresolved))


def codes(release: Release) -> tuple[str, ...]:
    """Every ISO code a release needs resolved: the dollar, and each
    currency it names that the plugin can name, in its order."""
    found: dict[str, None] = {USD: None}
    for country, currency, _ in release.currencies:
        code = code_of(country, currency)
        if code is not None:
            found[code] = None
    return tuple(found)
