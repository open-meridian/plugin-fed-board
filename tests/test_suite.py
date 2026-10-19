"""The data suite (meridian.suites, contract v20), each case H.10 presents
mapped to the plugin's own conversion of the Board's recorded responses, the
whole suite passing.

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

Contract v26's `queries-the-lake-within-bounds` is mapped as the SDK's data
template maps it: one bounded query of the kind the role reads, its prices,
of one subject it records (`lake_query`). The plugin itself asks the lake
nothing; contract v26's event-group case is the SDK's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data.testing import lake_query
from meridian.suites import ANSWERED_BY_SDK, Recorder, run, suite

from fed_h10.board import CURRENT, Fetched
from fed_h10.feed import Feed
from fed_h10.raw import RawStore

from conftest import AT, DATASET, response, want

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
}

NOT_PRESENTED = {
    case.name: NEVER[case.about] for case in suite("data").cases if case.about in NEVER
}


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


def _resolving(recorder: Recorder, ambiguous: str = "") -> None:
    """Each ISO code resolved to `LCL-<code>`; `ambiguous` to two records."""

    def answer(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        code = params.identifiers[0].value
        if code == ambiguous:
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS)
        return ops.ResolveIdentifierResult(found=True, instrument_id=f"LCL-{code}")

    recorder.answer("ResolveIdentifier", answer)


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    from fed_h10.board import SyntheticBoard

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
        from fed_h10.__main__ import read_licences

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
        "queries-the-lake-within-bounds": lake_query("LCL-USD"),
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id="fed-h10")
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    # The cases every suite holds, which the SDK answers (contract v24's two,
    # v26's event group), beside the plugin's own.
    assert len(report.passed_cases) == 13
    assert report.answered_by_sdk == list(ANSWERED_BY_SDK)


def test_an_exact_price_never_passes_through_a_float(tmp_path: Path) -> None:
    recorder = Recorder("fed-h10")
    _resolving(recorder)
    import asyncio

    from fed_h10.board import SyntheticBoard

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
