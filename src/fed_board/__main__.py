"""The Federal Reserve Board as an Open Meridian data plugin (contract v27;
`plugin-fed-h10` renamed, rulings 348 and 349): H.10's weekly noon buying
rates into the deployment's lake, each rate the price of one currency's cash
instrument in the other, as the Board quotes it (meridian-design
plans/the-lake-prices-the-book, row 7); and from 1.0.0 H.15's selected
interest rates and the Board's zero curve, as rates
(spec/a-public-rates-and-filings-data-plugin).

It runs its data role class, `Lake` (here: H.10's work and the rates'
beside each other, each want handed to the dataset's), with `meridian.run`
on the sidecar it is launched beside, declaring its catalogue, its storage
and its one setting (declaration.py); `meridian.run` delivers the settings,
serves its two pages (page.py), hands it what the lake wants of it, and sets
the data role's figures on each heartbeat. It reads the Board at start and
every hour: H.10's current release, recording a release it has not recorded
in this process (feed.py), and H.15's and the zero curve's files, pushing
their recent days when the Board has changed them (rates_feed.py). On its
first run it backfills H.10's history (feed.py). What the Board answered is
kept in the storage the deployment grants (raw.py), and moved past its
window as the settings say. It reads which of its datasets a deployment
admin has licensed, on start and every minute. A restart reads the Board again, and the lake
answers what it recorded before unchanged; it does not stream, so it has no
restart's gap to backfill.

Everything it says to the deployment goes through the sidecar; everything it
reads comes from the Board's public pages, or with sample data from the
responses committed with it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import meridian
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import Latency, data

from .board import Board, board, utc_now
from .declaration import DECLARATION, PORT
from .declared import CATALOGUE
from .feed import Feed
from .page import figures, hold, pages
from .rates_feed import Rates
from .raw import RawStore
from .settings import Config, config_from

log = logging.getLogger("fed_board")

#: How often the current release is checked, in seconds: hourly.
CHECK_SECONDS = 3600
#: How often storage is tended past its window, in seconds: daily.
TEND_SECONDS = 86_400
#: How often the datasets' licences are read again.
LICENCES_SECONDS = 60
#: How long a backfill the Board stopped answering waits to carry on.
BACKFILL_RETRY_SECONDS = 3600


async def read_licences(role: Any, feed: Feed, rates: Rates | None = None) -> None:
    """Which of its own declared datasets a deployment admin has licensed
    (contract v20, W10.9), read through the data role's class (`role`), for
    the Datasets page: a dataset with none is served by its catalogue's
    default terms until one is set."""
    answered = await role.list_datasets()
    licensed = frozenset(licence.dataset for licence in answered.licences)
    feed.status.licensed = licensed
    if rates is not None:
        rates.wants.licensed = licensed


class Lake(data.Role):
    """The data role's class (open-meridian 0.35, rulings 1004, 1005, 1009
    to 1023): H.10's work (`Feed`) and the rates' (`Rates`) beside each
    other, each making its acts through it. `meridian.run` delivers each
    settings to `on_settings` -- the first before anything is heard --
    hands it each want, which goes to the dataset's work, and starts `run`,
    again after a backoff should it fail."""

    def __init__(self, read: Board, raw: RawStore, now: Callable[[], datetime] = utc_now) -> None:
        self.feed = Feed(self, read, raw, now=now)
        self.wants = data.Wants(self, keys=tuple(entry.key for entry in CATALOGUE))
        # Contract v28 (ruling 518): each H.15 and zero-curve rate recorded
        # unasked or for a standing want has its age at the edge recorded from
        # its published time, reported every 10 seconds.
        self.latency = Latency(self)
        self.wants.latency = self.latency
        self.rates = Rates(self, read, raw, self.wants, now=now)
        self.config = Config()
        self.wake = asyncio.Event()
        self.checked = asyncio.Event()

    # ── What the lake wants ─────────────────────────────────────────────

    async def on_observations_wanted(
        self, heard: meridian.Heard[ops.ObservationsWantedEvent]
    ) -> None:
        """Each want to the dataset it names: H.10's to the feed, H.15's and
        the zero curve's to the rates."""
        if self.rates.wants.key_of(heard.message.dataset) in self.rates.sources:
            await self.rates.wants.hear(heard, self.rates.answer)
        else:
            await self.feed.on_want(heard)

    async def on_want_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        if self.rates.wants.withdraw(heard.message.want_id) is None:
            await self.feed.on_withdrawn(heard)

    # ── Its lifecycle ───────────────────────────────────────────────────

    async def on_settings(self, delivered: Any) -> None:
        """Apply each delivery of the settings: sample data on or off, and the
        responses' window, tended at once."""
        config = config_from(delivered.values)
        self.config = config
        read = board(config.sample_data)
        self.feed.use(read)
        self.rates.use(read)
        self.wake.set()
        feed = self.feed
        await feed.raw.tend(self.plugin, config.window_days, config.past_window, feed.now())

    async def run(self) -> None:
        """The Board read, H.10's history backfilled, storage tended, the
        licences read, and the feed delay reported (contract v28,
        ReportLatency)."""
        await asyncio.gather(
            self._check(), self._backfill(), self._tend(), self._licences(), self.latency.run()
        )

    async def _check(self) -> None:
        """Read the Board at once, then hourly, or at once when the settings
        change: H.10's current release, then H.15's and the zero curve's
        files."""
        feed, rates = self.feed, self.rates
        while True:
            self.wake.clear()
            try:
                await feed.check()
            except meridian.MeridianError as failed:
                # The sidecar refused something a recording needed; say so and
                # keep the schedule rather than spin.
                feed.status.error = f"the deployment refused a recording: {failed}"
                log.warning("this check stopped: %s", failed)
            try:
                await rates.check()
            except meridian.MeridianError as failed:
                for source in rates.sources.values():
                    source.error = f"the deployment refused a recording: {failed}"
                log.warning("this check of the rates stopped: %s", failed)
            self.checked.set()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), timeout=CHECK_SECONDS)

    async def _backfill(self) -> None:
        """H.10's history, once, on the Board's own site: after a check has
        read the current release, carried on an hour later where the Board
        stopped answering, until it is done."""
        feed = self.feed
        while not feed.status.backfill_done:
            await self.checked.wait()
            self.checked.clear()
            if feed.board.mode != "live" or feed.status.release is None:
                continue
            try:
                await feed.backfill()
            except meridian.MeridianError as failed:
                log.warning("the backfill stopped: %s", failed)
            if not feed.status.backfill_done:
                await asyncio.sleep(BACKFILL_RETRY_SECONDS)

    async def _tend(self) -> None:
        feed = self.feed
        while True:
            await asyncio.sleep(TEND_SECONDS)
            config = self.config
            await feed.raw.tend(self.plugin, config.window_days, config.past_window, feed.now())

    async def _licences(self) -> None:
        """The licences, read on start and every minute."""
        while True:
            try:
                await read_licences(self, self.feed, self.rates)
            except meridian.MeridianError as failed:
                log.warning("the datasets' licences were not read this time: %s", failed)
            await asyncio.sleep(LICENCES_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    lake = Lake(board(False), RawStore())
    hold(lake.feed, lake.rates)
    # The version's whole declaration (declaration.py): its settings, its
    # pages with the levels each serves and their tools, and its
    # documentation. A version registers exactly what it was uploaded with
    # (contract v25).
    meridian.run(
        declaration=DECLARATION,
        roles=[lake],
        pages=pages,
        port=PORT,
        on_settings=lake.on_settings,
        figures=lambda: figures(lake.feed.status, lake.feed, lake.rates),
    )


if __name__ == "__main__":
    main()
