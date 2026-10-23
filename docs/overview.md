# Overview

This plugin reads three of the Federal Reserve Board's publications and puts
them into your deployment's lake:

- **H.10**, every week: the noon buying rates in New York for about two dozen
  currencies against the US dollar, one rate a business day, as prices
  (`<instance>:daily`). A reporting plugin values your positions in another
  currency with them.
- **H.15**, every business day: selected interest rates, as rates
  (`<instance>:fed_h15`): the federal funds effective rate and the Treasury
  constant maturities, nominal and inflation-indexed.
- **The zero curve** (`feds200628`), in batches: the Treasury zero-coupon
  yield curve the Board's staff fit, 1 to 30 years, as rates
  (`<instance>:fed_zero`).

It is a data plugin: its first-use path, its two pages and its Summary
figures are every data plugin's, described once on
[Using a data plugin](https://open-meridian.dev/how-to/using-a-data-plugin/).
These sections cover what is the Board's own.

This plugin was called `fed-h10` until version 0.6.0. From 1.0.0 it is
`fed-board`, a new listing: its datasets are named by the new instance, and
an existing deployment moves its source priority, licence and entitlement to
them (Setup).

## What an FX rate means here

A rate is a price: the price of one currency's cash in another. The plugin
records each rate exactly as the Board quotes it.

- Most currencies are quoted per US dollar. **CHF 0.8293** on 2 October 2026
  means one US dollar cost 0.8293 francs: the price of the dollar, in francs.
- The euro, the pound and the Australian and New Zealand dollars are quoted
  in US dollars per unit. **EUR 1.1259** means one euro cost 1.1259 dollars:
  the price of the euro, in dollars.

Nothing is turned the other way round. A plugin that needs dollars per franc
divides, and says it did.

## What an interest rate means here

A rate is a value in per cent with its convention, about a record the
platform keeps for the rate or the curve:

- **The federal funds effective rate** is the New York Fed's EFFR, which
  H.15 reprints: a fixing, actual/360, about the same record the New York
  Fed's own plugin records it against. Your source priority picks which you
  read.
- **The Treasury constant maturities** (1 month to 30 years) are points of
  Treasury's par yield curve, and the inflation-indexed ones (5 to 30
  years) of its par real yield curve: par yields, bond-equivalent, each with
  its tenor, about the same records Treasury's plugin uses.
- **The zero curve**'s points are zero-coupon yields, continuously
  compounded, 1 to 30 years, about the Board's `feds200628` record.

H.15's other series -- Treasury bills in the secondary market, commercial
paper, the bank prime rate, the discount window's primary credit rate and
the inflation-indexed long-term average -- are read and kept, not recorded:
the platform holds no record for them yet. The Datasets page lists each.
H.15 does not publish the FOMC's target range.

## When they arrive

- **H.10:** the Board releases a week's rates on the following Monday at
  4:15 p.m. New York time, or the next business day after a holiday. A rate
  is the noon rate, so a valuation for yesterday waits for next Monday's
  release.
- **H.15:** each business day at 4:15 p.m., the day before's rates.
- **The zero curve:** in batches, days to weeks behind; the Board says it
  may be revised without notice.

The plugin checks each every hour, a file only if the Board has changed it,
and records the last month of each new file again, so a value the Board
revised becomes the row's next version. Asked for an older day, the plugin
records it from the Board; asked for a day not published yet, it says the
source has not stated it.

On its first run it also reads H.10's past releases back ten years, one
every two seconds, so its `daily` dataset has the history it declares.

## What it does not do

- It shows no rate on its own pages: rates are read by the plugins that
  value your book or analyse it.
- It records no index: the Board's dollar indexes are not prices of a
  currency.
- It never inverts, crosses or fits a rate, never fills a holiday or a
  missing tenor with a number, and never creates a record.
