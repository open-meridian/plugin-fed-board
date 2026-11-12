"""What this version declares beside its role, `data` (W8.1, W4.1; the
catalogue from contract v18), built from code and used twice: `__main__`
registers with it, and `meridian plugin upload` reads it from the built image
(pyproject.toml's `[tool.meridian] declaration`).

**The catalogue: three datasets** (spec/a-public-rates-and-filings-data-plugin,
`plugin-fed-board`, rulings 344, 348 and 349): H.10's `daily`, as
`plugin-fed-h10` declared it; H.15's `fed_h15`; and the zero curve's
`fed_zero`.

**`daily`** (the plan's Q21: a daily dataset per plugin; H.10 has no live
one). The Board's H.10, a week's noon buying rates pushed when it is
released, and any past week pulled when the lake wants it:

- `vendor` the Board; no aggregator, since the plugin reads the Board itself;
- `data_types` prices alone: an FX rate is the price of a currency's cash
  instrument (convert.py);
- `modes` `push` (each weekly release recorded when it appears) and `pull`
  (a past week, on a want);
- `cadence` a week, in seconds: the Board releases weekly;
- `history` ten years, in days: every release since 2013 is in the layout
  the plugin reads (release.py);
- its day New York's, ending at noon (`America/New_York`, 720): the rates
  are noon buying rates, so a rate's date is its business date;
- no venue: the rates are the New York Fed's certified rates, no venue's;
- its terms and pricing (contract 30, ruling 1032) the Board's, in plain
  words (`H10_TERMS`), and no licence declared: public domain, free, the
  Board cited as the source. A deployment's licence, set on the Data sources
  page, is the one enforced; the plugin says nothing of whether a deployment
  meets anyone's terms;
- a gap asked again (`gap_recovery` `backfill`, W10.14): the Board's files
  hold every past day.

**`fed_h15`**, H.15's selected interest rates (h15.py): rates, pushed each
business day when the Board posts the release and pulled for any past day;
daily; history from July 1954, the federal funds rate's first day; New
York's day, ending at midnight; no settlement calendar yet (the spec's Q15:
a US government securities calendar is curated on a miss, and none is
declared until then); the Board's terms in words (`H15_TERMS`); a gap
asked again (`backfill`).

**`fed_zero`**, the Board's zero curve (zero.py): rates, pushed when the
Board updates the file and pulled for any past date; weekly, as the spec's
catalogue has it, since the Board updates it in batches; history from 14
June 1961; New York's day; no calendar, as `fed_h15`; the Board's terms in
words (`ZERO_TERMS`); a gap asked again (`backfill`).

The Board's citation ("Source: Board of Governors of the Federal Reserve
System") is on the Datasets page, in docs/terms.md and in each dataset's
terms in words.

**Storage:** the Board's responses (raw.py), archivable, ten years by
default.
"""

from __future__ import annotations

from meridian import DatasetDeclaration
from meridian.declaration import RecordKind
from meridian.plugin.v1 import operations_pb2 as ops

from .convert import DAY_END_MINUTE, DAY_TIME_ZONE
from .raw import DEFAULT_WINDOW_DAYS, RESPONSES

#: The datasets' keys: their rows name `<instance>:daily` and so on.
DAILY = "daily"
H15 = "fed_h15"
ZERO = "fed_zero"
VENDOR = "Board of Governors of the Federal Reserve System"
#: A week, in seconds.
CADENCE = 7 * 86_400
#: A day, in seconds.
DAY = 86_400
#: Ten years, in days.
HISTORY = 3650
#: H.15's history, in days: from 1 July 1954, as the file holds it on
#: 23 October 2026.
H15_HISTORY = 26_412
#: The zero curve's, from 14 June 1961.
ZERO_HISTORY = 23_872
#: The rates' day: New York's, ending at midnight.
RATES_ZONE = "America/New_York"
#: What the Board's citation says, on the Datasets page and in docs/terms.md.
ATTRIBUTION = "Source: Board of Governors of the Federal Reserve System"

#: The Board's terms, in plain words (contract 30, ruling 1032): its site's
#: disclaimer, as docs/terms.md summarises it, and each release's own nature.
BOARD_TERMS = (
    "The Federal Reserve Board's public Data Download Program: free, no key or account. The "
    "Board's site states its information is in the public domain and may be copied and "
    "distributed without permission; it asks to be cited as the source ('Source: Board of "
    "Governors of the Federal Reserve System')."
)
H10_TERMS = BOARD_TERMS + (
    " H.10's rates are noon buying rates in New York certified by the Federal Reserve Bank of "
    "New York for customs purposes, released weekly: midday rates, not a market's close."
)
H15_TERMS = BOARD_TERMS + (
    " H.15 reprints series from others: the effective federal funds rate is the New York "
    "Fed's, and the Treasury yields are the Treasury's."
)
ZERO_TERMS = BOARD_TERMS + (
    " The zero curve is a staff research product, not an official Federal Reserve statistical "
    "release, and may be revised without notice."
)

DAILY_DATASET = DatasetDeclaration(
    key=DAILY,
    vendor=VENDOR,
    data_types=["meridian.v1.Price"],
    modes=["push", "pull"],
    cadence=CADENCE,
    history=HISTORY,
    terms_and_pricing=H10_TERMS,
    gap_recovery="backfill",
    day_time_zone=DAY_TIME_ZONE,
    day_end_minute=DAY_END_MINUTE,
)

H15_DATASET = DatasetDeclaration(
    key=H15,
    vendor=VENDOR,
    data_types=["meridian.v1.Rate"],
    modes=["push", "pull"],
    cadence=DAY,
    history=H15_HISTORY,
    terms_and_pricing=H15_TERMS,
    gap_recovery="backfill",
    day_time_zone=RATES_ZONE,
)

ZERO_DATASET = DatasetDeclaration(
    key=ZERO,
    vendor=VENDOR,
    data_types=["meridian.v1.Rate"],
    modes=["push", "pull"],
    cadence=CADENCE,
    history=ZERO_HISTORY,
    terms_and_pricing=ZERO_TERMS,
    gap_recovery="backfill",
    day_time_zone=RATES_ZONE,
)

CATALOGUE = (DAILY_DATASET, H15_DATASET, ZERO_DATASET)

RESPONSES_KIND = RecordKind(RESPONSES, "Raw responses", window_days=DEFAULT_WINDOW_DAYS)


def mode_name(mode: int | str) -> str:
    """A mode as the catalogue's words say it (`push`), however it is held."""
    if isinstance(mode, str):
        return mode
    return str(ops.ObservationMode.Name(mode)).removeprefix("OBSERVATION_MODE_").lower()
