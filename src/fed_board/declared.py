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
- the licence the Board's terms give: public domain, so kept, with no limit
  on retention, derived use or display, and not one person's terms
  (`personal_use` false). A deployment's licence confirms or replaces it on
  the Data sources page; the plugin says nothing of whether a deployment
  meets anyone's terms.

**`fed_h15`**, H.15's selected interest rates (h15.py): rates, pushed each
business day when the Board posts the release and pulled for any past day;
daily; history from July 1954, the federal funds rate's first day; New
York's day, ending at midnight; no settlement calendar yet (the spec's Q15:
a US government securities calendar is curated on a miss, and none is
declared until then); US government work, kept, derived use not
restricted, display.

**`fed_zero`**, the Board's zero curve (zero.py): rates, pushed when the
Board updates the file and pulled for any past date; weekly, as the spec's
catalogue has it, since the Board updates it in batches; history from 14
June 1961; New York's day; no calendar, as `fed_h15`; the same terms.

The Board's citation ("Source: Board of Governors of the Federal Reserve
System") is on the Datasets page and in docs/terms.md. The data terms'
attribution fields (SDK 0.32.2: `redistribution`, `attribution_required`,
`attribution_text`, `copyright_class`) are held until a core accepts them at
registration, and declared in the next version.

**Storage:** the Board's responses (raw.py), archivable, ten years by
default.
"""

from __future__ import annotations

from meridian import DatasetDeclaration, DatasetLicence
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

#: US government work (spec/a-public-rates-and-filings-data-plugin, section
#: 7): kept, no limit on retention, derived use not restricted, displayed,
#: not one person's terms. The data terms' attribution fields (SDK 0.32.2)
#: wait for a core that accepts them at registration (core v27 refuses a
#: catalogue carrying them), so the Board's citation is on the Datasets page
#: and in docs/terms.md.
GOVERNMENT_WORK = DatasetLicence(
    kept=True, derived_use=True, derived_use_terms="not_restricted", display=True
)

DAILY_DATASET = DatasetDeclaration(
    key=DAILY,
    vendor=VENDOR,
    data_types=["meridian.v1.Price"],
    modes=["push", "pull"],
    cadence=CADENCE,
    history=HISTORY,
    licence_default=GOVERNMENT_WORK,
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
    licence_default=GOVERNMENT_WORK,
    day_time_zone=RATES_ZONE,
)

ZERO_DATASET = DatasetDeclaration(
    key=ZERO,
    vendor=VENDOR,
    data_types=["meridian.v1.Rate"],
    modes=["push", "pull"],
    cadence=CADENCE,
    history=ZERO_HISTORY,
    licence_default=GOVERNMENT_WORK,
    day_time_zone=RATES_ZONE,
)

CATALOGUE = (DAILY_DATASET, H15_DATASET, ZERO_DATASET)

RESPONSES_KIND = RecordKind(RESPONSES, "Raw responses", window_days=DEFAULT_WINDOW_DAYS)


def mode_name(mode: int | str) -> str:
    """A mode as the catalogue's words say it (`push`), however it is held."""
    if isinstance(mode, str):
        return mode
    return str(ops.ObservationMode.Name(mode)).removeprefix("OBSERVATION_MODE_").lower()
