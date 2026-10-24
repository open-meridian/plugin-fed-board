"""The Board's names for H.10's currencies, each to its ISO 4217 code.

H.10 names a currency by its country and the currency's name, as the Board
prints them (`SWITZERLAND`, `FRANC`); a deployment knows a currency's cash
instrument by its ISO 4217 code (decisions/030: a currency's cash instrument
carries `iso4217` among its identifiers). This map is the plugin's own
conversion at the edge, and the only one: a row the map does not hold is not
recorded, and is counted and shown on the Datasets page as not converted, so
a currency the Board adds is seen rather than guessed at.

How a rate is quoted is never taken from here: the release says it, by its
asterisk (release.py).

Two names are worth a note:

- `CHINA, P.R.` / `YUAN`: the renminbi, CNY (onshore).
- `VENEZUELA` / `BOLIVAR`: VES, the bolivar soberano, ISO 4217's current
  code. ISO 4217 also lists VED, the 2021 redenomination's bolivar digital;
  the Board's series has been continuous since 2018 at VES's scale, so VES is
  the reading here. A deployment that disagrees sees it on the Datasets page.
"""

from __future__ import annotations

#: The US dollar, the other side of every H.10 rate.
USD = "USD"

#: (country, currency) as the Board prints them, upper case, to ISO 4217.
CODES: dict[tuple[str, str], str] = {
    ("AUSTRALIA", "DOLLAR"): "AUD",
    ("BRAZIL", "REAL"): "BRL",
    ("CANADA", "DOLLAR"): "CAD",
    ("CHINA, P.R.", "YUAN"): "CNY",
    ("DENMARK", "KRONE"): "DKK",
    ("EMU MEMBERS", "EURO"): "EUR",
    ("HONG KONG", "DOLLAR"): "HKD",
    ("INDIA", "RUPEE"): "INR",
    ("JAPAN", "YEN"): "JPY",
    ("MALAYSIA", "RINGGIT"): "MYR",
    ("MEXICO", "PESO"): "MXN",
    ("NEW ZEALAND", "DOLLAR"): "NZD",
    ("NORWAY", "KRONE"): "NOK",
    ("SINGAPORE", "DOLLAR"): "SGD",
    ("SOUTH AFRICA", "RAND"): "ZAR",
    ("SOUTH KOREA", "WON"): "KRW",
    ("SRI LANKA", "RUPEE"): "LKR",
    ("SWEDEN", "KRONA"): "SEK",
    ("SWITZERLAND", "FRANC"): "CHF",
    ("TAIWAN", "DOLLAR"): "TWD",
    ("THAILAND", "BAHT"): "THB",
    ("UNITED KINGDOM", "POUND"): "GBP",
    ("VENEZUELA", "BOLIVAR"): "VES",
}


def code_of(country: str, currency: str) -> str | None:
    """The ISO 4217 code of the currency the Board names, or None."""
    return CODES.get((country.strip().upper(), currency.strip().upper()))
