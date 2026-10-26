"""The plugin's pages, under Manage alone: the data role's common pages
(spec/plugin-pages-follow-their-role), Connection and Datasets, in its
order, each also a read tool for agents on the deployment's MCP under the
role's names (`read_connection`, `read_datasets`). Each record is the
role's (`meridian.roles.data`), extended with the Board's fields; each
template is the role's, with the Board's nuance at its blocks only.

A data plugin shows its connectivity, its data subscriptions and how its
entitlements resolve, and no market data (the product owner, 2026-10-03:
"The data unit only cares for connectivity and data subscriptions and
entitlement resolution"). So:

- **Connection** (`/`): "Key" -- the mode (Live or Sample data), "No key
  needed", what the Board serves; "Limits and use" -- the Board states no
  limit, the pages asked, the last check and error; "Stream": it does not
  stream. Then the Board's: the source, the responses kept; and, a tab of
  its own, "Sources" (spec/a-public-rates-and-filings-data-plugin, section
  5), one line per source -- H.10's weekly release, H.15's file, the zero curve's file --
  each with its state, the latest it published, the next expected, the
  calls and the last error.
- **Datasets** (`/datasets`), in tabs to fit one screen: "Served" -- the
  role's "Served", "Wants" and "Subjects"; "Currencies" -- each currency
  H.10 publishes, how the Board quotes it, what its rate is the price of,
  and the deployment's instrument for its subject or why there is none,
  searched; "Records" -- each rate and curve the rates are recorded against
  and its `INS-`, or why none; and "Lag" -- per dataset, the median and
  longest time from a row's day to its publication. One line a row, paged by
  the kit's om-pager. read_datasets answers every tab.

Neither shows an account's data, since the plugin reaches none, nor a rate:
prices are the reading roles' to show.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import meridian
from meridian.roles import data

from . import h15, records
from .board import BASE, CURRENT, H15_FILE, ZERO_FILE, release_days
from .currencies import USD
from .declared import (
    ATTRIBUTION,
    CADENCE,
    DAILY_DATASET,
    H15,
    H15_DATASET,
    HISTORY,
    ZERO,
    ZERO_DATASET,
    mode_name,
)
from .feed import Feed, Status
from .rates_feed import LABELS, SUBJECTS, Rates, Source

#: The title the registry and the dashboard show (ruling 348).
TITLE = "Federal Reserve Board"
#: The kit these pages are built on: 0.12.0's "Facts" and "Next step".
KIT = "0.12.0"

pages = meridian.Pages(TITLE, templates=Path(__file__).parent / "templates", kit=KIT)

CONNECTION = "/"
DATASETS = "/datasets"

#: The longest search the Datasets tab reads.
MOST_QUERY = 100
#: How many wants the Datasets tab lists; read_datasets answers every one held.
SHOWN_WANTS = 3
#: Connection's tabs, by the name its links carry.
CONNECTION_TABS = {"connection": "Connection", "sources": "Sources"}
#: Datasets' tabs, by the name its links carry.
TABS = {"served": "Served", "currencies": "Currencies", "records": "Records", "lag": "Lag"}

_held: dict[str, Any] = {}


def hold(feed: Feed, rates: Rates | None = None) -> None:
    """The feed and rates the pages read, once the plugin has registered."""
    _held["feed"] = feed
    _held["rates"] = rates


def _status() -> tuple[Status, Feed | None]:
    feed = _held.get("feed")
    return (feed.status if feed is not None else Status(), feed)


def _rates() -> Rates | None:
    held: Rates | None = _held.get("rates")
    return held


def _iso(moment: datetime | None) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds") if moment else ""


def _published(last_modified: str) -> str:
    try:
        moment = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S GMT")
    except ValueError:
        return ""
    return moment.replace(tzinfo=UTC).isoformat(timespec="seconds")


def next_release(status: Status) -> str:
    """The day the next release is expected: the Monday after the latest's
    last day (or the next business day, when that is a holiday)."""
    if status.release is None:
        return ""
    return release_days(status.release.days[-1] + timedelta(days=7))[0].isoformat()


def _state(status: Status) -> tuple[str, str, str]:
    """The head's status: its state, what it means, and its detail."""
    misses = [c for c in status.currencies.values() if c.miss]
    if status.error and status.release is None:
        return "error", "Not answering", status.error
    if status.error:
        return "warn", "Answering", status.error
    if status.release is None:
        return "busy", "Checking the Board", ""
    if misses:
        codes = ", ".join(sorted(c.code for c in misses))
        plural = "currency" if len(misses) == 1 else "currencies"
        return "warn", f"{len(misses)} {plural} not resolved", codes
    if status.mode == "synthetic":
        return "ok", "Sample data", ""
    return "ok", "Answering", ""


def _next_weekday(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _source_state(source: Source, mode: str) -> str:
    if source.error and not source.raw_key:
        return "Not answering"
    if source.error:
        return "Answering, with an error"
    if source.checked_at is None:
        return "Not checked yet"
    return "Sample data" if mode == "synthetic" else "Answering"


def sources(status: Status, rates: Rates | None, instance: str) -> list[records.SourceRead]:
    """Connection's "Sources": H.10's release, H.15's file, the zero curve's."""
    state, said, _ = _state(status)
    release = status.release
    out = [
        records.SourceRead(
            source="H.10 foreign exchange rates, weekly",
            dataset=f"{instance}:{DAILY_DATASET.key}",
            state=said,
            latest=release.released.isoformat() if release else "",
            published_at=_published(status.last_modified),
            next_expected=next_release(status),
            calls=status.fetches,
            last_error=status.error,
        )
    ]
    if rates is None:
        return out
    for key, source in rates.sources.items():
        latest = source.latest_day
        if key == H15:
            # A day's rates are posted the next business day at 16:15.
            expected = _next_weekday(_next_weekday(latest)).isoformat() if latest else ""
        else:
            expected = "In batches, days to weeks behind: not scheduled"
        out.append(
            records.SourceRead(
                source=LABELS[key],
                dataset=f"{instance}:{key}",
                state=_source_state(source, status.mode),
                latest=latest.isoformat() if latest else "",
                published_at=_published(source.last_modified),
                next_expected=expected,
                calls=source.calls,
                last_error=source.error,
            )
        )
    return out


def connection_read(
    status: Status, feed: Feed | None, rates: Rates | None = None
) -> records.ConnectionRead:
    state, said, _ = _state(status)
    release = status.release
    kept = feed.raw.keys() if feed is not None else []
    window = ""
    if feed is not None and feed.raw.granted:
        window = "in the storage the deployment grants, as its responses settings say"
    elif feed is not None:
        window = "in a directory of the plugin's own: this deployment grants no storage"
    instance = feed.plugin.identity.instance_id if feed is not None else "fed-board"
    lines = sources(status, rates, instance)
    errors = [line.last_error for line in lines if line.last_error]
    return records.ConnectionRead(
        mode="Sample data" if status.mode == "synthetic" else "Live",
        credentials=[],
        entitled_at_vendor=(
            "Everything H.10, H.15 and the zero curve publish: no key, US government work"
            if status.release is not None or status.mode == "synthetic"
            else ""
        ),
        limit=(
            "The Board states none; the plugin asks one page or file at a time, at most one "
            "every two seconds, and checks each source every hour, a file only if changed"
        ),
        calls=sum(line.calls for line in lines),
        last_call_at=_iso(status.checked_at),
        last_error="; ".join(errors),
        sessions=None,
        state=state,
        said=said,
        source=(
            "The responses recorded on 2026-10-10 and 2026-10-23, committed with the plugin"
            if status.mode == "synthetic"
            else f"{BASE}{CURRENT} and each past week's release by its date; "
            f"{BASE}{H15_FILE}; {BASE}{ZERO_FILE}"
        ),
        checked_at=_iso(status.checked_at),
        latest_release=release.released.isoformat() if release else "",
        first_day=release.days[0].isoformat() if release else "",
        last_day=release.days[-1].isoformat() if release else "",
        published_at=_published(status.last_modified),
        next_release=next_release(status),
        responses_kept=len(kept),
        kept_for=window,
        sources=lines,
        backfill=_backfill(status),
    )


def _backfill(status: Status) -> str:
    """H.10's first-run backfill, as a person reads it."""
    if status.backfill_done:
        return f"Done, back to the week of {status.backfilled_to}"
    if status.backfilled_to:
        return f"Under way, back to the week of {status.backfilled_to}"
    if status.mode == "synthetic":
        return "Not run on sample data"
    return "Not started: it starts once the current release is read"


def _quoted(per_dollar: bool, code: str, priced: int) -> tuple[str, str]:
    """How the Board quotes a currency, and what its rate is the price of."""
    if code == USD:
        return "the base of each rate per dollar", f"USD in {priced} currencies"
    if per_dollar:
        return f"{code} per US dollar", f"USD in {code}"
    return f"US dollars per {code}", f"{code} in USD"


def _want(answered: Any, dataset: str) -> records.Want:
    declined = ", ".join(f"{n} {reason.replace('_', ' ')}" for reason, n in answered.declined)
    return records.Want(
        dataset=dataset,
        asked=answered.asked,
        subjects=answered.subjects,
        recorded=answered.recorded,
        declined=sum(n for _, n in answered.declined),
        state="Answered, standing" if answered.standing else "Answered",
        want_id=answered.want_id,
        at=_iso(answered.at),
        standing=answered.standing,
        declined_as=declined,
    )


def _span(ns: int) -> str:
    """A lag as a person reads it: days and hours, or hours and minutes."""
    minutes = ns // 60_000_000_000
    days, hours = divmod(minutes // 60, 24)
    if days:
        return f"{days} d {hours} h"
    return f"{hours} h {minutes % 60} min"


def _lag(dataset: str, lags: list[int]) -> records.LagRead:
    held = sorted(lags)
    if not held:
        return records.LagRead(dataset, 0, "", "")
    return records.LagRead(dataset, len(held), _span(held[len(held) // 2]), _span(held[-1]))


_CONVENTIONS = {
    "act_360:simple": "actual/360, simple",
    "act_act:compounded/2": "bond-equivalent",
    "act_360:discount": "discount basis, actual/360",
}


def _rows_text(series: h15.Series) -> str:
    kind = series.kind.replace("_", " ")
    held = series.convention
    said = ""
    if held is not None:
        periods = f"/{held.periods_per_year}" if held.periods_per_year else ""
        said = _CONVENTIONS.get(f"{held.day_count}:{held.compounding}{periods}", "")
    return f"{kind}, {said}" + (", by tenor" if series.tenor else "")


def _record(identifiers: tuple[str, str, str]) -> str:
    _, value, source = identifiers
    return f"{source}: {value}"


def records_of(rates: Rates | None, instance: str) -> list[records.RecordRead]:
    """ "Records": each record the rates are recorded against, with the
    Board's series for it."""
    out: list[records.RecordRead] = []
    resolved = rates.feed.subjects if rates is not None else {}
    missed = rates.feed.missed if rates is not None else {}

    def why(named: tuple[tuple[str, str, str], ...]) -> str:
        if resolved.get(named):
            return ""
        if named in missed:
            return "Not held by the deployment: reported missing"
        return "Not resolved yet"

    for subject in SUBJECTS[H15]:
        series = [s for s in h15.SERIES if s.subject == subject.identifiers]
        keys = series[0].key if len(series) == 1 else f"{len(series)} series, {series[0].key} ..."
        tenors = f" ({series[0].tenor} to {series[-1].tenor})" if len(series) > 1 else ""
        named = (subject.identifiers,)
        out.append(
            records.RecordRead(
                dataset=f"{instance}:{H15}",
                series=keys + tenors,
                record=_record(subject.identifiers),
                rows=_rows_text(series[0]),
                instrument_id=resolved.get(named, ""),
                why_none=why(named),
            )
        )
    for subject in SUBJECTS[ZERO]:
        named = (subject.identifiers,)
        out.append(
            records.RecordRead(
                dataset=f"{instance}:{ZERO}",
                series="SVENY01 to SVENY30",
                record=_record(subject.identifiers),
                rows="zero, continuously compounded, by tenor (1Y to 30Y)",
                instrument_id=resolved.get(named, ""),
                why_none=why(named),
            )
        )
    return out


def datasets_read(
    status: Status, feed: Feed | None, rates: Rates | None = None
) -> records.DatasetsRead:
    instance = feed.plugin.identity.instance_id if feed is not None else "fed-board"
    entry = DAILY_DATASET
    dataset = f"{instance}:{entry.key}"
    currencies = sorted(status.currencies.values(), key=lambda c: (c.code != USD, c.code))
    priced = sum(1 for c in currencies if c.code != USD and c.per_dollar)
    answered = status.release is not None or status.mode == "synthetic"
    served = [
        records.Served(
            dataset=dataset,
            data="noon buying rates",
            arrives=", ".join(mode_name(m) for m in entry.modes),
            day="New York's, to noon",
            default_terms="kept; public domain",
            entitled_at_vendor="Yes: no key needed" if answered else "Not asked yet",
            recorded=status.recorded,
            declined=status.declined,
            last_recorded=_iso(status.last_recorded_at),
            licensed=dataset in status.licensed,
            cadence="weekly" if entry.cadence == CADENCE else f"{entry.cadence} s",
            history_days=HISTORY,
            venue="none: the New York Fed's certified rates, no venue's",
            restated=status.restated,
            unchanged=status.unchanged,
        )
    ]
    standing = [
        records.Want(
            dataset=dataset,
            asked="prices",
            subjects=n,
            state="Kept current",
            want_id=want_id,
            at=_iso(since),
            standing=True,
        )
        for want_id, (n, since) in status.standing.items()
    ]
    heard: list[records.Want] = []
    lag = [_lag(dataset, status.lags)]
    if rates is not None:
        for entry, what in (
            (H15_DATASET, "selected interest rates"),
            (ZERO_DATASET, "zero-coupon yields"),
        ):
            counted = rates.wants.sent_to(entry.key)
            named = f"{instance}:{entry.key}"
            source = rates.sources[entry.key]
            served.append(
                records.Served(
                    dataset=named,
                    data=what,
                    arrives=", ".join(mode_name(m) for m in entry.modes),
                    day="New York's, to midnight",
                    default_terms="kept; US government work",
                    entitled_at_vendor=(
                        "Yes: no key needed"
                        if source.raw_key or status.mode == "synthetic"
                        else "Not asked yet"
                    ),
                    recorded=counted.recorded,
                    declined=counted.declined,
                    last_recorded=(
                        _iso(datetime.fromtimestamp(counted.last_ns / 1e9, UTC))
                        if counted.last_ns
                        else ""
                    ),
                    licensed=named in rates.wants.licensed or named in status.licensed,
                    cadence="weekly" if entry.cadence == CADENCE else "daily",
                    history_days=entry.history,
                    venue="none",
                    restated=counted.restated,
                    unchanged=counted.unchanged,
                )
            )
            lag.append(_lag(named, source.lags))
        standing += [
            records.Want(
                dataset=held.dataset,
                asked="rates",
                subjects=len(held.subjects),
                state="Kept current",
                want_id=held.want_id,
                at=_iso(datetime.fromtimestamp(held.since_ns / 1e9, UTC)),
                standing=True,
            )
            for held in rates.wants.standing.values()
        ]
        heard = [
            records.Want(
                dataset=w.dataset,
                asked=w.asked,
                subjects=w.subjects,
                recorded=w.recorded,
                declined=w.declined,
                state="Answered, standing" if w.standing else "Answered",
                want_id=w.want_id,
                at=_iso(datetime.fromtimestamp(w.at_ns / 1e9, UTC)),
                standing=w.standing,
            )
            for w in rates.wants.heard
        ]
    answered_wants = [_want(a, dataset) for a in status.wants] + heard
    answered_wants.sort(key=lambda w: w.at, reverse=True)
    return records.DatasetsRead(
        served=served,
        wants=standing + answered_wants,
        reads_instruments=True,
        currencies=[
            records.CurrencyRead(
                code=c.code,
                board_name=", ".join(part for part in (c.country, c.name) if part),
                quoted=_quoted(c.per_dollar, c.code, priced)[0],
                price_of=_quoted(c.per_dollar, c.code, priced)[1],
                instrument_id=c.instrument_id,
                miss=c.miss.replace("_", " "),
            )
            for c in currencies
        ],
        unconverted=[f"{name} ({n} reads)" for name, n in sorted(status.unconverted.items())],
        records=records_of(rates, instance),
        lag=lag,
        attribution=ATTRIBUTION,
    )


def figures(status: Status, feed: Feed | None, rates: Rates | None = None) -> list[meridian.Figure]:
    """The data role's figures, in its order (`meridian.roles.data`); the
    Board reports none of its own."""
    state, said, why = _state(status)
    errors = [s.error for s in rates.sources.values() if s.error] if rates is not None else []
    if status.mode == "synthetic" and state == "ok" and not errors:
        connection: Any = "Sample data"
    elif said == "Not answering":
        connection = meridian.Figure("", said, state="error", why=why[:200])
    else:
        said_error = "; ".join(e for e in [status.error, *errors] if e)
        connection = meridian.Figure(
            "", "Answering", state="warn" if said_error else None, why=said_error[:200]
        )
    last = status.last_recorded_at
    if rates is not None and rates.wants.counts.last_ns:
        recorded = datetime.fromtimestamp(rates.wants.counts.last_ns / 1e9, UTC)
        last = max(last, recorded) if last is not None else recorded
    total = 3 if rates is not None else 1
    return data.figures(
        connection=connection,
        entitled_at_vendor=f"{total} of {total} datasets",
        stream="Does not stream",
        last_recorded=last,
    )


def _moment(value: str) -> str:
    """An ISO moment as a person reads it, to the minute in UTC."""
    if not value:
        return ""
    if len(value) == 10:
        return value
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _day(value: str) -> str:
    return date.fromisoformat(value).strftime("%a %d %b") if value else ""


def matching(query: str, *texts: str) -> bool:
    """Whether every word of a search is in one of `texts`, case aside."""
    words = query.lower().split()
    held = " ".join(texts).lower()
    return all(word in held for word in words)


pages.environment.filters["moment"] = _moment
pages.environment.filters["day"] = _day


@pages.page(
    CONNECTION,
    "Connection",
    levels="admin",
    answers=records.ConnectionRead,
    name="read_connection",
    description=(
        "How this plugin reaches the Federal Reserve Board, as every data plugin's "
        "Connection answers it: the mode (Live or Sample data), no key needed, what the "
        "Board serves, its limits (none stated) and the calls made, the last check and why "
        "it failed if it did; it does not stream. Then the Board's own: the sources read, "
        "the H.10 release's days and publication, how many responses are kept, and one line "
        "per source -- H.10's weekly release, H.15's file, the zero curve's file -- with its "
        "state, the latest it published, the next expected, its calls and last error. No rate."
    ),
)
async def connection(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = connection_read(status, feed, _rates())
    tab = request.query.get("tab", "connection")
    return pages.answer(
        "connection.html",
        read,
        detail=_state(status)[2],
        # Named apart from the SDK's own `tab` and `tabs` (0.32.3), which
        # would draw the data role's section row in their place.
        view=tab if tab in CONNECTION_TABS else "connection",
        views=CONNECTION_TABS,
    )


@pages.page(
    DATASETS,
    "Datasets",
    levels="admin",
    answers=records.DatasetsRead,
    name="read_datasets",
    description=(
        "What this plugin serves the lake, as every data plugin's Datasets answers it: its "
        "three datasets as the catalogue declares them (H.10's weekly noon buying rates, "
        "daily; H.15's selected interest rates, fed_h15; the zero curve, fed_zero; each US "
        "government work), whether a deployment admin has licensed each, what it recorded "
        "and declined; the standing wants it keeps current and the wants it answered. Then "
        "the Board's own: each currency H.10 publishes, how the Board quotes it and the "
        "deployment's instrument for it or why there is none; each record the rates are "
        "recorded against and its instrument or why none; each dataset's lag "
        "from a day to its publication; and the citation the Board's terms ask for. No rate."
    ),
)
async def datasets(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = datasets_read(status, feed, _rates())
    # A browser draws one tab, its search narrowing the currencies, and the
    # latest wants; a tool answers them all.
    tab = request.query.get("tab", "served")
    tab = tab if tab in TABS else "served"
    query = request.query.get("q", "").strip()[:MOST_QUERY]
    if query:
        tab = "currencies"
    shown = [c for c in read.currencies if matching(query, c.code, c.board_name)]
    drawn = read if request.tool_name else replace(read, wants=read.wants[:SHOWN_WANTS])
    return pages.answer(
        "datasets.html",
        drawn,
        query=query,
        shown=shown,
        tab=tab,
        tabs=TABS,
        state=_state(status),
        checked_at=_iso(status.checked_at),
        wants=len(read.wants),
    )
