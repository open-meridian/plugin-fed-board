"""The pages on sample data, each printed as one HTML file:
for looking at them without a deployment.

    python -m fed_board.preview connection > preview/connection.html
    python -m fed_board.preview datasets > preview/datasets.html

The plugin's work runs on the SDK's suite recorder in place of a sidecar --
every currency resolved to an instrument the recorder names, the federal
funds rate and the zero curve to their records and Treasury's curves not
held, every batch recorded -- against the responses committed under
responses/: H.10 at 11:00 UTC on 10 October 2026, the release of 5 October
read, a want for 25 September answered from the week before's, one for 8
October declined (not published yet), and a standing want kept current;
H.15's and the zero curve's files as recorded on 23 October.
`connection-sources` is Connection's other tab; `datasets-currencies`,
`datasets-records` and `datasets-lag` are Datasets'. Each page links the kit where the
dashboard serves it, /.meridian/ui/<version>/: served beside the kit it is
styled (meridian-ui's `make serve`, or `make preview SHOTS=...`, which checks
each in a browser); opened on its own it is the page without the kit,
unstyled, which works too. `connection-first` and `datasets-first` are the
pages before the first check, with no want yet: the role's "not set up yet"
states.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles import data
from meridian.suites import Recorder
from meridian.testing import PageClient

from .board import SyntheticBoard
from .declared import CATALOGUE
from .feed import Feed
from .page import CONNECTION, DATASETS, hold, pages
from .rates_feed import Rates
from .raw import RawStore

AT = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
AT_RATES = datetime(2026, 10, 23, 17, 0, tzinfo=UTC)
PAGES = {
    "connection": CONNECTION,
    "connection-sources": CONNECTION,
    "datasets": DATASETS,
    "datasets-search": DATASETS,
    "datasets-currencies": DATASETS,
    "datasets-records": DATASETS,
    "datasets-lag": DATASETS,
    "connection-first": CONNECTION,
    "datasets-first": DATASETS,
}
#: The records the preview's deployment holds, by their seeded codes; the
#: others are not held.
HELD = {"EFFR", "feds200628"}
#: What the Datasets tab's search is shown with, as `datasets-search`.
SEARCHED = "dollar"


def _want(want_id: str, subject: str, day: str = "", standing: bool = False) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset="fed-board:daily",
            data_type="meridian.v1.Price",
            subjects=[ops.SubjectRef(entity_id=subject)],
            kinds=[ops.PRICE_KIND_CLOSE],
            business_date=day,
            standing=standing,
        ),
    )


def _resolving(recorder: Recorder) -> None:
    def answer(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        named = params.identifiers[0]
        if named.scheme == "iso4217":
            return ops.ResolveIdentifierResult(found=True, instrument_id=f"LCL-{named.value}")
        if named.value in HELD:
            held = f"LCL-{named.value.upper()}"
            return ops.ResolveIdentifierResult(found=True, instrument_id=held)
        return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)

    recorder.answer("ResolveIdentifier", answer)


def synthetic_rates(recorder: Recorder) -> Rates:
    wants = data.Wants(recorder, keys=tuple(entry.key for entry in CATALOGUE))
    return Rates(
        recorder, SyntheticBoard(lambda: AT_RATES), RawStore(), wants, now=lambda: AT_RATES
    )


async def synthetic_feed() -> tuple[Feed, Rates]:
    """A feed and rates as sample data leaves them, on the recorder."""
    recorder = Recorder("fed-board")
    _resolving(recorder)
    feed = Feed(recorder, SyntheticBoard(lambda: AT), RawStore(), now=lambda: AT)
    rates = synthetic_rates(recorder)
    await feed.check()
    await rates.check()
    usd = feed.status.currencies["USD"].instrument_id
    await feed.on_want(_want("want-0925", usd, date(2026, 9, 25).isoformat()))
    await feed.on_want(_want("want-1008", usd, date(2026, 10, 8).isoformat()))
    await feed.on_want(_want("want-standing", usd, standing=True))
    return feed, rates


def render(page: str) -> str:
    if page.endswith("-first"):
        recorder = Recorder("fed-board")
        feed = Feed(recorder, SyntheticBoard(lambda: AT), RawStore(), now=lambda: AT)
        rates = synthetic_rates(recorder)
    else:
        feed, rates = asyncio.run(synthetic_feed())
    hold(feed, rates)
    query = {"q": SEARCHED} if page == "datasets-search" else {}
    if page.startswith("datasets-") and page not in ("datasets-search", "datasets-first"):
        query = {"tab": page.removeprefix("datasets-")}
    if page == "connection-sources":
        query = {"tab": "sources"}
    answer = PageClient(pages).get(PAGES[page], "admin", **query)
    if answer.status != 200:
        raise SystemExit(f"{page} answered {answer.status}: {answer.text[:200]}")
    return answer.text


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "connection"
    if page not in PAGES:
        raise SystemExit(f"no page {page!r}: {', '.join(PAGES)}")
    sys.stdout.write(render(page))


if __name__ == "__main__":
    main()
