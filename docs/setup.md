# Setup

## Launching it

The Board needs no key and no account: its site is public. Launch the plugin
and approve its one role, `data` (a data plugin). It reads the Board at once,
and every hour after. On its first run it also reads H.10's past releases
back ten years, one request every two seconds, about twenty minutes; a
restart carries on where it stopped.

Its settings, in the dashboard's Settings form:

- **Raw responses window** and **past the window** (the SDK's): how long the
  Board's responses are kept in the plugin's storage, ten years by default,
  and whether they are then archived, kept or deleted. H.10's pages are
  small; H.15's file (about 4 MB a business day) and the zero curve's
  (about 5 MB each time the Board updates it) come to about 1.4 GB a year.
  Set the window, or archive past it, to suit the storage you grant.
- **Sample data**, on a deployment installed for development only: the
  Board's responses recorded on 10 and 23 October 2026, committed with the
  plugin, in place of the site. For trying it offline.

## Its datasets

On the deployment's **Data sources** page (deployment admins), for each of
`<instance>:daily`, `<instance>:fed_h15` and `<instance>:fed_zero`:

1. **License it.** The catalogue's default is US government work: kept, no
   limit on retention, derived use not restricted, displayed, not one
   person's terms. Confirm it, or set your own, with a note saying why.
2. **Entitle** each plugin that reads it, such as your reporting or
   analytics plugin.
3. **Priority**, where another dataset serves the same: H.15's federal funds
   rate beside the New York Fed's plugin, its constant maturities beside
   Treasury's plugin, H.10 beside another FX source. Put the one your
   readers should read first.

## Moving from `fed-h10`

`fed-board` is `fed-h10` renamed, a new listing. Its datasets are new
names, so install it beside the old instance, then move the old dataset's
source priority, licence and entitlements to `<instance>:daily`, and stop
`fed-h10`. Its rows stay in the lake, readable by name; the new instance
records H.10 again, back ten years, under its own.

## The records it reads against

- **H.10:** each rate is about a currency's cash instrument, found by its
  ISO 4217 code. Datasets' Currencies tab shows each currency's instrument,
  or why there is none (not found, or two records match). A currency without
  one waits: its rates are recorded once it resolves, at the next check.
- **H.15 and the zero curve:** each rate is about a record the platform
  seeds -- `nyfed: EFFR`, Treasury's par and par real yield curves, the
  Board's six H.15 records, `frb: feds200628` -- found by its code. Datasets' Records tab shows each,
  or that the deployment does not hold it; a record not held is reported
  missing once a day, and its rates wait.
