"""The data suite (meridian.suites, contract v27), each case the Board's
datasets present mapped to the plugin's own conversion of the Board's
recorded responses, the whole suite passing.

H.10 is one noon buying rate a day for each currency the Board publishes
against the US dollar. A case about a kind of data it never publishes
(`about`, from contract v19) is not presented, with why (`NOT_PRESENTED`):
a daily bar (one rate a day, no open, high, low or volume), a crypto
asset's price, prices on a venue (the New York Fed's certified rates, no
venue's), a security's price another source named, trades and quotes. A
case about a field of a trade (`about_field`, from contract v20) is about
trades, so not presented the same way; and so is a restart's gap,
backfilled, which is about trades. Contract v22's calendar cases
(`about` calendars and settlement dates) are not presented either: the
plugin records each rate as the Board publishes it and never reads a
settlement calendar or asks for a settlement date; nor contract v23's
outcomes, H.10 listing no event contract. Every other case is presented,
its dataset's licences among them.

`the-forming-day-restated`: H.10's day is never forming once published, but
the Board does correct a published rate; the plugin records the corrected
rate under the same row key, which the lake keeps as the row's next version.
That is the case's outcome, and the producer gives the plugin a correction.

Contract v26's `queries-the-lake-within-bounds` is about trades from
contract v27, so not presented: the plugin records no trades, and itself
asks the lake nothing; contract v26's event-group case is the SDK's.

**Contract v27's rates cases** (`about: rates`) are H.15's and the zero
curve's: `a-curve-for-a-date` is H.15's constant maturities, par yields by
tenor; `a-tenor-not-published` the zero curve on a date the Board left a
tenor `NA`; `a-curve-point-from-another-source` H.15's 10-year, recorded
against Treasury's par curve with its tenor; `a-same-day-revision` H.15's
file posted again with a value revised. Three are not presented, with why:
H.15 states no percentiles or volume for its one fixing (the New York Fed's
own dataset does), the Board publishes one convention per point and no index
level. `records-a-datasets-liveness` is about streams, and the plugin
streams nothing. From contract v28 `reports-its-feed-delay` is presented
(ruling 518) on H.15's rates, each one's age at the edge from its published
time; the chains, filings, holdings, dividends and ratings cases are about
kinds the Board never publishes, and the quality cases about quotes.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data.testing import feed_delay
from meridian.suites import ANSWERED_BY_SDK, Recorder, run, suite

from fed_board.board import CURRENT, H15_FILE, ZERO_FILE, Fetched, SyntheticBoard
from fed_board.feed import Feed
from fed_board.raw import RawStore

from conftest import AT, AT_RATES, DATASET, rates, response, seeded, want

#: Why each kind of data a case may be about is never published here.
NEVER = {
    "bars": "H.10 states one rate a day: no open, high, low or volume",
    "a crypto asset's price": "H.10 quotes currencies against the US dollar: no token",
    "prices on a venue": "H.10's rates are the New York Fed's, no venue's",
    "a security's price": "H.10 rates currencies: no security another source named",
    "trades": "H.10 states one rate a day: no trades",
    "quotes": "H.10 states one rate a day: no quotes",
    "calendars": (
        "records each rate the Board publishes, a day it marks ND as no rate: "
        "reads no settlement calendar"
    ),
    "settlement dates": "records daily rates as published; never computes a settlement date",
    "outcomes": "H.10 rates currencies: no event contract, so no outcome",
    "disputed outcomes": "H.10 rates currencies: no event contract, so no outcome disputed",
    "streams": "does not stream: H.10, H.15 and the zero curve are pages and files, read hourly",
    # Contract v28 (ruling 602).
    "option chains": "the Board publishes rates: no option chain",
    "filings": "the Board publishes rates: no company's filings",
    "holdings": "the Board publishes rates: no holdings report",
    "corporate actions": "the Board publishes rates: no declared dividend",
    "ratings": "the Board publishes rates: no rating",
}

#: The rates cases the Board's datasets never present, with why.
RATES_NOT_PRESENTED = {
    "a-rate-fixing": (
        "H.15 states no volume or percentiles for its one fixing, the federal funds rate; "
        "the New York Fed's own dataset does"
    ),
    "two-conventions-one-tenor": (
        "the Board states one convention per point: H.15's constant maturities "
        "bond-equivalent, the zero curve continuously compounded"
    ),
    "an-index-level": "the Board publishes no index level in H.15 or the zero curve",
}

NOT_PRESENTED = {
    case.name: NEVER[case.about] for case in suite("data").cases if case.about in NEVER
} | RATES_NOT_PRESENTED


class Corrected:
    """The Board's site, the current release read twice: as received, then
    with one rate corrected."""

    mode = "synthetic"

    def __init__(self) -> None:
        self.reads = 0

    async def get(self, path: str) -> Fetched:
        self.reads += 1
        page = response("20261005")
        if self.reads > 1:
            page = page.replace("0.8293", "0.8294")
        return Fetched(path, 200, page.encode(), AT, last_modified="Mon, 05 Oct 2026 20:15:04 GMT")


def _revised(body: bytes) -> bytes:
    """H.15's recorded file with the 10-year's last value revised."""
    xml = zipfile.ZipFile(io.BytesIO(body)).read("H15_data.xml").decode()
    xml = xml.replace(
        'OBS_STATUS="A" OBS_VALUE="5.13" TIME_PERIOD="2026-10-21"',
        'OBS_STATUS="A" OBS_VALUE="5.14" TIME_PERIOD="2026-10-21"',
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as held:
        held.writestr("H15_data.xml", xml)
    return out.getvalue()


class Revised:
    """The Board's site, H.15's file posted, then posted again the same day
    with a value revised; the zero curve as recorded."""

    mode = "synthetic"

    def __init__(self) -> None:
        self.held = SyntheticBoard(lambda: AT_RATES)
        self.reads = 0

    async def get(self, path: str, since: str = "") -> Fetched:
        if path != H15_FILE:
            return await self.held.get(path, since)
        self.reads += 1
        first = await self.held.get(path)
        if self.reads == 1:
            return first
        return Fetched(
            path, 200, _revised(first.body), AT_RATES, last_modified="Thu, 22 Oct 2026 21:05:00 GMT"
        )


class TenorLeftOut:
    """The Board's site, the zero curve's last date with its 30-year left NA."""

    mode = "synthetic"

    def __init__(self) -> None:
        self.held = SyntheticBoard(lambda: AT_RATES)

    async def get(self, path: str, since: str = "") -> Fetched:
        found = await self.held.get(path, since)
        if path != ZERO_FILE:
            return found
        lines = found.body.decode().splitlines()
        cells = lines[-1].split(",")
        header = next(line for line in lines if line.startswith("Date,")).split(",")
        cells[header.index("SVENY30")] = "NA"
        lines[-1] = ",".join(cells)
        body = ("\n".join(lines) + "\n").encode()
        return Fetched(path, 200, body, AT_RATES, last_modified=found.last_modified)


def _resolving(recorder: Recorder, ambiguous: str = "") -> None:
    """Each ISO code resolved to `LCL-<code>`; `ambiguous` to two records."""

    def answer(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        code = params.identifiers[0].value
        if code == ambiguous:
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS)
        return ops.ResolveIdentifierResult(found=True, instrument_id=f"LCL-{code}")

    recorder.answer("ResolveIdentifier", answer)


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    from fed_board.board import SyntheticBoard

    def work(recorder: Recorder, board: Any = None) -> Feed:
        return Feed(recorder, board or SyntheticBoard(lambda: AT), RawStore(tmp), now=lambda: AT)

    async def a_release_read(recorder: Recorder) -> None:
        _resolving(recorder)
        await work(recorder).check()

    async def the_rate_corrected(recorder: Recorder) -> None:
        _resolving(recorder)
        feed = work(recorder, Corrected())
        await feed.check()
        await feed.check()
        keys = [[p.meta.row_key for p in b.prices] for b in recorder.on("RecordPrices")]
        assert len(keys) == 2 and keys[0] == keys[1]

    async def two_records(recorder: Recorder) -> None:
        _resolving(recorder, ambiguous="GBP")
        await work(recorder).check()

    def wanted(message: Any) -> Callable[[Recorder], Awaitable[None]]:
        async def produce(recorder: Recorder) -> None:
            _resolving(recorder)
            feed = work(recorder)
            recorder.answer("ObservationsWanted", lambda _: message)
            await recorder.receive(observations_wanted=feed.on_want)

        return produce

    async def licences(recorder: Recorder) -> None:
        # On start, its own declared datasets' licences (contract v20).
        from fed_board.__main__ import read_licences

        recorder.answer(
            "ListDatasets",
            lambda _: ops.ListDatasetsResult(licences=[ops.DatasetLicence(dataset=DATASET)]),
        )
        feed = work(recorder)
        await read_licences(recorder, feed)
        assert feed.status.licensed == {DATASET}

    async def withdrawn(recorder: Recorder) -> None:
        _resolving(recorder)
        feed = work(recorder)
        recorder.answer(
            "WantWithdrawn",
            lambda _: ops.WantWithdrawnEvent(want_id="w-standing", dataset=DATASET),
        )
        await recorder.receive(want_withdrawn=feed.on_withdrawn)

    stores = iter(range(1000))

    def board(recorder: Recorder, site: Any = None) -> Any:
        # Each case its own storage, as each would be a plugin's first run.
        store = tmp / f"rates-{next(stores)}"
        store.mkdir()
        held = rates(store, recorder)
        if site is not None:
            held.board = site
        return held

    async def delayed(recorder: Recorder, latency: Any) -> None:
        # Contract v28 (ruling 518): H.15's file read unasked, each rate's age
        # at the edge recorded from its published time, then reported.
        seeded(recorder)
        held = board(recorder)
        held.wants.latency = latency
        await held.check()

    async def the_rates_read(recorder: Recorder) -> None:
        seeded(recorder)
        await board(recorder).check()

    async def a_curve_point(recorder: Recorder) -> None:
        # H.15's 10-year, against Treasury's par curve with its tenor.
        seeded(recorder, {"Daily Treasury Par Yield Curve Rates": "INS-PAR"})
        await board(recorder).check()
        sent = [r for b in recorder.on("RecordRates") for r in b.rates]
        assert {r.meta.subjects[0].entity_id for r in sent} == {"INS-PAR"}
        assert any(r.meta.row_key.startswith("RIFLGFCY10_N.B:par_yield:10Y:") for r in sent)

    async def a_tenor_left_out(recorder: Recorder) -> None:
        seeded(recorder, {"feds200628": "INS-ZERO"})
        await board(recorder, TenorLeftOut()).check()
        sent = [r for b in recorder.on("RecordRates") for r in b.rates]
        last = max(r.meta.business_date for r in sent)
        on_last = {r.tenor.count for r in sent if r.meta.business_date == last}
        assert 30 not in on_last and len(on_last) == 29

    async def a_revision(recorder: Recorder) -> None:
        seeded(recorder, {"Daily Treasury Par Yield Curve Rates": "INS-PAR"})
        held = board(recorder, Revised())
        await held.check()
        before = len(recorder.on("RecordRates"))
        await held.check()
        ten = [
            [r for r in b.rates if r.meta.row_key.startswith("RIFLGFCY10_N.B")]
            for b in recorder.on("RecordRates")
        ]
        first = [r for batch in ten[:before] for r in batch]
        second = [r for batch in ten[before:] for r in batch]
        assert first[-1].meta.row_key == second[-1].meta.row_key

    return {
        "a-daily-close": a_release_read,
        "the-forming-day-restated": the_rate_corrected,
        "an-exact-price": a_release_read,
        "an-fx-rate": a_release_read,
        "an-asset-that-does-not-resolve": two_records,
        "a-want-recorded-against": wanted(want("w-1", ["LCL-USD"], day="2026-09-25").message),
        "a-subject-declined": wanted(want("w-2", ["LCL-CHF"], day="2026-10-02").message),
        "a-standing-want-withdrawn": withdrawn,
        "reads-its-datasets-licences": licences,
        "a-same-day-revision": a_revision,
        "a-curve-for-a-date": the_rates_read,
        "a-tenor-not-published": a_tenor_left_out,
        "a-curve-point-from-another-source": a_curve_point,
        "reports-its-feed-delay": feed_delay(delayed),
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id="fed-board")
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    # The cases every suite holds, which the SDK answers (contract v24's two,
    # v26's event group), beside the plugin's own: H.10's nine, the rates'
    # four and, from contract v28, the feed delay.
    assert len(report.passed_cases) == 17
    assert report.answered_by_sdk == list(ANSWERED_BY_SDK)


def test_an_exact_price_never_passes_through_a_float(tmp_path: Path) -> None:
    recorder = Recorder("fed-board")
    _resolving(recorder)
    import asyncio

    from fed_board.board import SyntheticBoard

    feed = Feed(recorder, SyntheticBoard(lambda: AT), RawStore(tmp_path), now=lambda: AT)
    asyncio.run(feed.check())
    from meridian.operations import as_decimal

    amounts = {
        p.meta.row_key: str(as_decimal(p.price.amount))
        for p in recorder.on("RecordPrices")[0].prices
    }
    assert amounts["KRW:2026-09-28"] == "1359.7800"
    assert amounts["CHF:2026-10-02"] == "0.8293"
    assert CURRENT.endswith("default.htm")
