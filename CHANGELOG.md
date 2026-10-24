# Changelog

## 1.0.0

`plugin-fed-h10` renamed `plugin-fed-board`, titled "Federal Reserve Board",
with H.15 and the Board's zero curve joining H.10 (rulings 344, 348, 349 and
504; meridian-design spec/a-public-rates-and-filings-data-plugin). A new
listing and namespace, `fed-board`, so a new major version: a deployment
installs it beside `fed-h10` and moves to it (docs/setup.md).

- **The rename.** The package and plugin `fed-board` (module `fed_board`),
  the title "Federal Reserve Board", the repository open-meridian/plugin-fed-board
  (GitHub redirects the old address), and the README, docs, CI, links and
  pre-push hook with them.
- **H.10 moves unchanged** as the `daily` dataset, now `<instance>:daily` of
  the new instance: the same prices, row keys and catalogue entry. **On the
  first run it is backfilled**, each past week's release read back to the
  ten years it declares, one request every two seconds, its progress noted
  in storage (`backfill-daily.json`) so a restart carries on and a finished
  backfill never runs again.
- **`fed_h15`**, H.15's selected interest rates (ruling 539): read from the
  release's SDMX file (`/releases/h15/data/FRB_h15_xml.zip`, the Data
  Download Program's format; its query builder is removed the week of 9
  November 2026), recorded through `meridian.roles.data.rates`, every
  business-daily series in force against a record the platform seeds: the
  federal funds effective rate against `nyfed: EFFR`, a fixing, actual/360;
  the Treasury constant maturities against Treasury's par and par real yield
  curves, par yields, bond-equivalent, by tenor; and H.15's own six against
  the Board's records (ruling 541) -- the bills' secondary-market rates and
  AA nonfinancial and financial commercial paper, discount rates by tenor;
  the bank prime loan rate and the discount window's primary credit rate,
  fixings, actual/360 simple (H.15 states no convention for primary credit,
  read as the money-market convention of a Fed-set overnight rate, like the
  federal funds rate); the inflation-indexed long-term average, an average,
  bond-equivalent. Every rate carries a convention, which the lake requires,
  and a test holds every recorded rate to it. H.15 states
  no FOMC target range; FRED supplies it (ruling 540).
- **`fed_zero`**, the Board's zero curve (`frb: feds200628`): zero-coupon
  yields, continuously compounded, 1 to 30 years, from
  `/data/yield-curve-tables/feds200628.csv`.
- **Each file read only when changed** (`If-Modified-Since`), its last month
  pushed again so a revision is the row's next version, each rate naming the
  file it was first read from (`firsts-<dataset>.json`); past days pulled on
  a want. Raw responses kept from day one, a file as base64.
- **The pages:** Connection gains a Sources tab, one line per source;
  Datasets is in tabs -- Served, Currencies, Records, Lag -- with the Board's
  citation. Both tools answer every tab.
- **Terms:** each dataset US government work, kept, derived use
  `not_restricted`, displayed; the Board cited on the Datasets page and in
  docs/terms.md. SDK 0.32.2's data-terms fields (`attribution_text` and the
  rest) are not set: core v27 refuses a catalogue carrying them at
  registration, and they come in the next version once core accepts them.
- **The pins:** open-meridian 0.32.2 (contract v27) and plugin-python:0.32.2;
  core v27's runtime and harness at a5da59a (merged as 6d346b3, chart
  0.1.310) by tag and digest; `meridian` 0.1.51 in check.yaml. The SDK's
  0.32.0 migration: the suite's v27 cases mapped -- the rates cases H.15's
  and the zero curve's, those the Board never presents named with why,
  `records-a-datasets-liveness` (it records no liveness: it streams
  nothing) and `queries-the-lake-within-bounds` (now about trades) not
  presented, and `reports-its-feed-delay` not presented, "core receives
  ReportLatency from contract v28, ruling 515" (ruling 518); the e2e
  workflows upload their hidden `.e2e/` logs (`include-hidden-files`).
- **The e2e** reads back H.15 and the zero curve: each record resolved by
  its administrator's code to its `INS-` record and its rows read by
  business date. The harness at a5da59a holds the platform's 22 records
  seeded before ruling 541, so H.15's six own records are asserted reported
  missing there; they resolve on the platform (seeded 2026-10-23), and the
  harness gains them at core's next push.

## 0.6.0

On open-meridian 0.31.0: pins only, no change to what the plugin records
or shows. It speaks contract v26, the SDK's, so the version is a minor one.

- **The pins**: open-meridian 0.31.0, as released on PyPI, and
  plugin-python:0.31.0 by tag in the Dockerfile; core v26's runtime and
  harness (17a13a2, merged as 648e25f, chart 0.1.308) by tag and digest;
  `meridian` 0.1.48 in check.yaml.
- **The data suite's v26 cases.** `queries-the-lake-within-bounds` is
  mapped in `tests/test_suite.py` as the SDK's data template maps it (one
  bounded query of prices, `lake_query`); the plugin itself asks the lake
  nothing. `hears-and-reads-an-event-group` is the SDK's; the outcome
  cases stay not presented.
- The README's, AGENTS.md's and the workflows' words about the pins
  brought up to date.

## 0.5.0 (2026-10-19)
