# Pages

Both pages are the data role's, the same on every data plugin, under
**Manage**, for the plugin's admins. Neither shows a rate. Each is also a
read tool on the deployment's MCP, answering everything the page shows,
under the same names on every data plugin. Each page's tabs keep it to one
screen.

## Connection (`read_connection`)

How the plugin reaches the Board, and how the last check went.

- **Connection:** the head's status (answering, checking, not answering, or
  currencies not resolved); **Key** -- the mode (Live or Sample data), "No
  key needed", what the Board serves, and where it reads from; **Limits and
  use** -- the limits it keeps (the Board states none; one request at a
  time, at most one every two seconds, a check every hour), the calls made,
  the last check and error, and how many responses are kept; **Stream** --
  it does not stream.
- **Sources:** one line per source -- H.10's weekly release, H.15's file,
  the zero curve's file -- with its state, the latest day it published, the
  next expected and the calls made. A row's `…` opens when the Board
  published it and the last error.

## Datasets (`read_datasets`)

What the plugin serves.

- **Served:** its three datasets as the deployment's catalogue lists them,
  with the terms each declares and whether a deployment admin has licensed
  it, and what it recorded and declined; **Wants**, the standing wants it
  keeps current and the last wants it answered; **Subjects**.
- **Currencies:** each currency H.10 publishes, one line each: its code, how
  the Board quotes it, what its rate is the price of, and the deployment's
  instrument for it, or why there is none. Searched by code or name.
- **Records:** each record the rates are recorded against -- the federal
  funds rate, Treasury's two par curves, H.15's own six, the zero curve --
  with the Board's series for it and the deployment's instrument for it,
  or why there is none.
- **Lag:** for each dataset, the median and the longest time from the end
  of a row's day to when the Board published it; and the citation the
  Board's terms ask for.
