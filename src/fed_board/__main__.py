"""The Federal Reserve Board as an Open Meridian data plugin (contract v27;
`plugin-fed-h10` renamed, rulings 348 and 349): H.10's weekly noon buying
rates into the deployment's lake, each rate the price of one currency's cash
instrument in the other, as the Board quotes it (meridian-design
plans/the-lake-prices-the-book, row 7); and from 1.0.0 H.15's selected
interest rates and the Board's zero curve, as rates
(spec/a-public-rates-and-filings-data-plugin).

It connects to the sidecar it is launched beside with its catalogue, its
storage and its one setting (declaration.py), serves its two pages
(page.py), hears what the lake wants of it, and reads the Board at start and
every hour: H.10's current release, recording a release it has not recorded
in this process (feed.py), and H.15's and the zero curve's files, pushing
their recent days when the Board has changed them (rates_feed.py). On its
first run it backfills H.10's history (feed.py). What the Board answered is
kept in the storage the deployment grants (raw.py), and moved past its
window as the settings say. It reads which of its datasets a deployment
admin has licensed, on start and every minute, and reports the data role's
figures on its heartbeat. A restart reads the Board again, and the lake
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
import signal
from typing import Any

import meridian
from meridian.roles import Latency, data

from .board import board
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
#: How long before a broken settings stream is asked again, in seconds.
RETRY_SECONDS = 5
#: How often storage is tended past its window, in seconds: daily.
TEND_SECONDS = 86_400
#: How often the datasets' licences are read again, and the figures set.
LICENCES_SECONDS = 60
#: How long a backfill the Board stopped answering waits to carry on.
BACKFILL_RETRY_SECONDS = 3600


async def watch_settings(
    plugin: meridian.Plugin, feed: Feed, rates: Rates, held: list[Config], wake: asyncio.Event
) -> None:
    """Apply each delivery of the settings: sample data on or off, and the
    responses' window, tended at once. A stream that breaks -- the deployment
    not serving its configuration yet at a first start, or restarting -- is
    asked again after a pause, and delivers the settings whole."""
    while True:
        try:
            async for delivered in plugin.settings():
                config = config_from(delivered.values)
                held[0] = config
                read = board(config.sample_data)
                feed.use(read)
                rates.use(read)
                wake.set()
                await feed.raw.tend(plugin, config.window_days, config.past_window, feed.now())
        except Exception as broken:  # noqa: BLE001 - a broken stream, asked again
            log.warning("the settings were not delivered (%s); asking again", broken)
        await asyncio.sleep(RETRY_SECONDS)


async def check(feed: Feed, rates: Rates, wake: asyncio.Event, checked: asyncio.Event) -> None:
    """Read the Board once the settings have come, then hourly, or at once
    when the settings change: H.10's current release, then H.15's and the
    zero curve's files."""
    await wake.wait()
    while True:
        wake.clear()
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
        checked.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(wake.wait(), timeout=CHECK_SECONDS)


async def backfill(feed: Feed, checked: asyncio.Event) -> None:
    """H.10's history, once, on the Board's own site: after a check has read
    the current release, carried on an hour later where the Board stopped
    answering, until it is done."""
    while not feed.status.backfill_done:
        await checked.wait()
        checked.clear()
        if feed.board.mode != "live" or feed.status.release is None:
            continue
        try:
            await feed.backfill()
        except meridian.MeridianError as failed:
            log.warning("the backfill stopped: %s", failed)
        if not feed.status.backfill_done:
            await asyncio.sleep(BACKFILL_RETRY_SECONDS)


async def tend(plugin: meridian.Plugin, feed: Feed, held: list[Config]) -> None:
    while True:
        await asyncio.sleep(TEND_SECONDS)
        config = held[0]
        await feed.raw.tend(plugin, config.window_days, config.past_window, feed.now())


async def read_licences(plugin: Any, feed: Feed, rates: Rates | None = None) -> None:
    """Which of its own declared datasets a deployment admin has licensed
    (contract v20, W10.9), for the Datasets page: a dataset with none is
    served by its catalogue's default terms until one is set."""
    answered = await plugin.list_datasets()
    licensed = frozenset(licence.dataset for licence in answered.licences)
    feed.status.licensed = licensed
    if rates is not None:
        rates.wants.licensed = licensed


async def licences(plugin: meridian.Plugin, feed: Feed, rates: Rates) -> None:
    """The licences, read on start and every minute; and the data role's
    figures, set for the next heartbeat."""
    while True:
        try:
            await read_licences(plugin, feed, rates)
        except meridian.MeridianError as failed:
            log.warning("the datasets' licences were not read this time: %s", failed)
        plugin.figures = figures(feed.status, feed, rates)
        await asyncio.sleep(LICENCES_SECONDS)


def wanted(feed: Feed, rates: Rates) -> Any:
    """What the lake wants, each want to the dataset it names: H.10's to the
    feed, H.15's and the zero curve's to the rates."""

    async def hear(heard: meridian.Heard[Any]) -> None:
        if rates.wants.key_of(heard.message.dataset) in rates.sources:
            await rates.wants.hear(heard, rates.answer)
        else:
            await feed.on_want(heard)

    return hear


def withdrawn(feed: Feed, rates: Rates) -> Any:
    async def hear(heard: meridian.Heard[Any]) -> None:
        if rates.wants.withdraw(heard.message.want_id) is None:
            await feed.on_withdrawn(heard)

    return hear


def _said(task: asyncio.Task[None]) -> None:
    """A task that ended on an error says so, rather than ending unseen."""
    if not task.cancelled() and task.exception() is not None:
        log.error("%s stopped", task.get_name(), exc_info=task.exception())


async def run() -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop, stopped.set)

    # The version's whole declaration (declaration.py): its settings, its
    # pages with the levels each serves and their tools, and its documentation.
    # A version registers exactly what it was uploaded with (contract v25).
    async with await meridian.connect(declaration=DECLARATION) as plugin:
        log.info("registered as %s, roles %s", plugin.identity.instance_id, plugin.identity.roles)
        raw = RawStore()
        feed = Feed(plugin, board(False), raw)
        wants = data.Wants(plugin, keys=tuple(entry.key for entry in CATALOGUE))
        # Contract v28 (ruling 518): each H.15 and zero-curve rate recorded
        # unasked or for a standing want has its age at the edge recorded from
        # its published time, reported every 10 seconds.
        latency = Latency(plugin)
        wants.latency = latency
        rates = Rates(plugin, board(False), raw, wants)
        hold(feed, rates)
        held = [Config()]
        wake = asyncio.Event()
        checked = asyncio.Event()
        server = pages.serve(plugin, PORT)
        log.info("serving its pages on 127.0.0.1:%d", PORT)
        tasks = [
            asyncio.create_task(
                plugin.receive(
                    observations_wanted=wanted(feed, rates),
                    want_withdrawn=withdrawn(feed, rates),
                )
            ),
            asyncio.create_task(watch_settings(plugin, feed, rates, held, wake)),
            asyncio.create_task(check(feed, rates, wake, checked)),
            asyncio.create_task(backfill(feed, checked)),
            asyncio.create_task(tend(plugin, feed, held)),
            asyncio.create_task(licences(plugin, feed, rates)),
            asyncio.create_task(latency.run()),
        ]
        for task in tasks:
            task.add_done_callback(_said)
        await stopped.wait()
        log.info("stopping")
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        server.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
