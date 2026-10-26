# meridian-fed-board

An [Open Meridian](https://open-meridian.com) plugin, titled "Federal
Reserve Board", that puts three of the Board's publications into a
deployment's lake: [H.10](https://www.federalreserve.gov/releases/h10/current/default.htm)'s
weekly foreign exchange rates, as prices; [H.15](https://www.federalreserve.gov/releases/h15/)'s
selected interest rates; and the Board's
[zero curve](https://www.federalreserve.gov/data/nominal-yield-curve.htm)
(`feds200628`), as rates. It holds the `data` role, a data plugin. This is
release 1.1.0. How to set it up and use it is in [docs/](docs/README.md);
how a plugin like it is built is documented at
[open-meridian.dev](https://open-meridian.dev).

**It was `plugin-fed-h10`** until 0.6.0. Renamed `plugin-fed-board` (rulings
348, 349 and 504; meridian-design `spec/a-public-rates-and-filings-data-plugin.md`,
"`plugin-fed-board`"), it is a new listing and namespace, `fed-board`: H.10
moves unchanged as its `daily` dataset, backfilled on the first run, and
H.15 and the zero curve join it from the same publisher. GitHub redirects
the old repository's address here.

It is built on the SDK it pins, `open-meridian==0.33.1`, which declares
contract v28 (from v27 its rates slice: the `Rate` row, recorded through
`meridian.roles.data.rates`); its work is the lake prices the book
(meridian-design `plans/the-lake-prices-the-book.md`, row 7) and the public
rates plugins (`plans/the-v27-build.md`, B).

## What it records

- **Three datasets:**
  - **`<instance>:daily`**, H.10 as `plugin-fed-h10` declared it: prices,
    pushed when each weekly release appears and pulled for any past week the
    lake wants; weekly; ten years of history, read back on the first run;
    New York's day, ending at noon; no venue; public domain.
  - **`<instance>:fed_h15`**, H.15: rates, pushed each business day and
    pulled for any past day; history from July 1954; New York's day. The
    federal funds effective rate against the New York Fed's `nyfed: EFFR`
    (a fixing, actual/360), and the Treasury constant maturities against
    Treasury's par and par real yield curves (par yields, bond-equivalent,
    by tenor), so each sits under the deployment's source priority beside
    the publisher's own plugin. H.15's own series against the Board's
    records (ruling 541): Treasury bills in the secondary market and AA
    commercial paper (discount rates by tenor), the bank prime rate and the
    discount window's primary credit rate (fixings, actual/360; primary
    credit read as the money-market convention, H.15 stating none) and the
    inflation-indexed long-term average (an average, bond-equivalent). Every
    rate carries a convention. H.15 does not state the FOMC's target range: FRED
    supplies its bounds (ruling 540).
  - **`<instance>:fed_zero`**, the zero curve: rates against `frb:
    feds200628`, zero-coupon yields continuously compounded, 1 to 30 years;
    weekly, as the Board updates it in batches; history from June 1961.
- **US government work**: each dataset's default licence is kept, derived
  use not restricted, displayed; the Board cited on the Datasets page and in
  docs/terms.md. The data terms' attribution fields wait for a core that
  accepts them at registration.

For H.10:

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

For H.15 and the zero curve, each file is asked for every hour with the
Last-Modified the Board last answered, so an unchanged one costs nothing;
a new one has its last month recorded again, a revised value becoming the
row's next version, each rate naming the file it was first read from.

Its pages, under Manage alone, are the data role's, the same on every data
plugin, and show how it reaches the Board and what it serves, never a rate:
**Connection** (`read_connection`, "No key needed", "Does not stream", and
a Sources tab, one line per source) and **Datasets** (`read_datasets`:
Served, Currencies, Records and Lag tabs, saying whether a deployment admin
has licensed each dataset and which record each rate is about), each the
same through the deployment's MCP. The data role's figures are on its
Summary. It does not stream, so it has no restart's gap to backfill.

## Checking it

    make ci-local                                  # lint, tests, plugin check, image, e2e: the pre-push gate
    make preview SHOTS=<dir>                       # each page in a browser with the kit, at 1440x900 and 390x844

`make e2e` runs it on core's plugin harness (core v27, a5da59a) beside a
reading plugin: the Board unreachable at first, then sample data reading the
committed release of 5 October 2026, the rates read back in the right
instruments, a past week wanted and recorded, a week not yet published and a
currency it never prices declined; H.15's and the zero curve's files read,
each referential record resolved by its administrator's code and its rows
read back by business date (the federal funds rate, Treasury's two par
curves from H.15, the zero curve's thirty points); both tools answering what
the pages show; and a new container recording nothing twice and reading its
licence on start. The harness at a5da59a predates H.15's six own records
(ruling 541), so the e2e asserts them reported missing there; the platform
holds them, and core's next harness carries them.

**The data suite.** `tests/test_suite.py` runs the SDK's suite on the
plugin's own conversion, and it passes: thirteen cases are presented, its
datasets' licences and contract v27's rates cases among them (a curve for a
date, a tenor not published, a curve point from another source, a same-day
revision), and the SDK answers the every-role cases; every other case is
about a kind of data the Board never states -- a day's open, high, low and
volume, a crypto asset, a venue, a security another source named, trades,
quotes, a stream, a fixing's percentiles, two conventions for one point, an
index level -- and is not presented, with why, as the suite lets it. So are
contract v22's calendar cases, and contract v28's option chains, filings,
holdings, dividends and ratings. The feed delay is presented (ruling 518):
each H.15 and zero-curve rate's age at the edge from its published time.

**open-meridian 0.33.1 is on PyPI** and its base image on ghcr.io: the
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
- **H.15 and the zero curve.** H.15 reprints the New York Fed's federal
  funds rate and Treasury's yields; the zero curve is a staff research
  product, "not an official Federal Reserve statistical release", revised
  without notice. Both are read from the Board's own files.
- **No endorsement.** This project is not affiliated with or endorsed by the
  Federal Reserve.

## Licence

Apache-2.0 (LICENSE, NOTICE). The Board's responses under
`src/fed_board/responses/` are its H.10 pages as received on 2026-10-10,
and its H.15 and zero curve files as received on 2026-10-23, trimmed to
their last weeks (responses/index.json says how), public domain.
