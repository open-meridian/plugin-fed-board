# meridian-fed-h10

An [Open Meridian](https://open-meridian.com) plugin that puts the Federal
Reserve Board's [H.10](https://www.federalreserve.gov/releases/h10/current/default.htm)
foreign exchange rates into a deployment's lake: each week's noon buying
rates in New York for about two dozen currencies against the US dollar, each
rate the price of one currency's cash instrument in the other, as the Board
quotes it. It holds the `data` role, a data plugin. This is release 0.6.0.
How to set it up and use it is in [docs/](docs/README.md); how a plugin like
it is built is documented at [open-meridian.dev](https://open-meridian.dev).

It is built on the SDK it pins, `open-meridian==0.31.0`, which declares
contract v26 (from v25, its whole declaration and docs/, which a deployment shows on its Documentation tab); its work is the lake prices the book (meridian-design
`plans/the-lake-prices-the-book.md`, row 7).

## What it records

- **One dataset, `<instance>:daily`:** prices, pushed when each weekly
  release appears and pulled for any past week the lake wants; weekly; ten
  years of history; New York's day, ending at noon; no venue; public domain.
- **Each rate as the Board quotes it.** Most currencies are quoted per US
  dollar, so CHF 0.8293 is the price of the dollar's cash instrument, in
  francs. The euro, the pound and the Australian and New Zealand dollars are
  quoted in US dollars per unit (the Board's asterisk), so EUR 1.1259 is the
  price of the euro's cash instrument, in dollars. Nothing is inverted: a
  reader wanting the other way inverts it, and says so.
- **A close for its business date.** The rate's date as the Board prints it
  is the business date, a plain date; the price's kind is `close`, the
  dataset's declared close (the noon rate); its published time is when the
  Board's server says the release's page was last modified.
- **Exact.** Every rate is made a decimal from the text the Board printed.
- **Every currency resolved** to the deployment's cash instrument by its
  ISO 4217 code, as of the moment it is asked, a miss reported with why.
  The plugin mints no currency: core answers a code the deployment does not
  hold with the platform master's currency, pulled (contract v20); a day the Board marks `ND` is no
  rate, never a zero; its dollar indexes are not recorded.
- **Every response kept** as received, in the storage the deployment grants,
  and named by each row it was read into.

Its pages, under Manage alone, are the data role's, the same on every data
plugin, and show how it reaches the Board and what it serves, never a rate:
**Connection** (`read_connection`, "No key needed", "Does not stream", and
the Board's release calendar) and **Datasets** (`read_datasets`, saying
whether a deployment admin has licensed the dataset), each the same through
the deployment's MCP. The data role's figures are on its Summary. It does
not stream, so it has no restart's gap to backfill.

## Checking it

    make ci-local                                  # lint, tests, plugin check, image, e2e: the pre-push gate
    make preview SHOTS=<dir>                       # each page in a browser with the kit, at 1440x900 and 390x844

`make e2e` runs it on core's plugin harness (core v20, local) beside a
reading plugin: the Board unreachable at first, then sample data reading the committed release of 5 October 2026, the rates read back in
the right instruments, a past week wanted and recorded, a week not yet
published and a currency it never prices declined, both tools answering what
the pages show, and a new container recording nothing twice and reading
its licence on start.

**The data suite.** `tests/test_suite.py` runs the SDK's suite on the
plugin's own conversion, and it passes: ten cases are presented, its
dataset's licences and contract v26's bounded query of the lake among them
(as the SDK's template maps it: the plugin itself asks the lake nothing),
and the SDK answers the every-role cases; every other case is about a kind of data the
Board never states -- a day's open, high, low and volume, a crypto asset, a
venue, a security another source named, trades, quotes -- and is not
presented, with why, as the suite lets it. So are contract v22's calendar
cases: the plugin records each rate the Board publishes, a day it marks ND
as no rate, and never reads a settlement calendar or asks for a settlement
date.

**open-meridian 0.31.0 is on PyPI** and its base image on ghcr.io: the
runners install the pin from there. Locally the Makefile builds
both from the sibling meridian-python checkout.

## The terms, summarised

Not legal advice; read the Board's own words before relying on them.

- **Public domain.** The Board's site says its information is in the public
  domain and "may be copied and distributed without permission"
  ([disclaimer](https://www.federalreserve.gov/disclaimer.htm)); it asks
  that the Board be cited as the source. So the dataset's default licence
  is kept, with no limit on retention, derived use or display, and not one
  person's terms (`personal_use` false). A deployment's licence on its Data
  sources page confirms or replaces it.
- **Read from the Board itself,** not through FRED, whose API has terms and a
  key of its own.
- **What the rates are.** Noon buying rates in New York for cable transfers
  payable in foreign currencies, certified by the Federal Reserve Bank of New
  York for customs purposes: midday rates, not a close in a market's sense,
  published weekly on Monday (the next business day after a holiday) for the
  week before. A valuation for yesterday has no H.10 rate until the next
  release; each rate's date is shown with it.
- **No endorsement.** This project is not affiliated with or endorsed by the
  Federal Reserve.

## Licence

Apache-2.0 (LICENSE, NOTICE). The Board's responses under
`src/fed_h10/responses/` are its pages as received on 2026-10-10, public
domain.
