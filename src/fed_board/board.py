"""The Federal Reserve Board's site, where H.10, H.15 and the zero curve are
published, and its stand-in.

Three things are read, and nothing else:

- **H.10**, two pages: the current weekly release
  (/releases/h10/current/default.htm), checked for a new week, and a past
  week's release by the date it came out (/releases/h10/<YYYYMMDD>/default.htm),
  for a day the lake asks for. A week's release comes out on the Monday after
  it, at 4:15 p.m. New York time, or the next business day when that Monday
  is a holiday (Labor Day's week is published on the Tuesday); a dated
  address that names no release is answered 404, and the next day is tried.
- **H.15**, one file: the release's data in the Data Download Program's SDMX
  format, every series and its whole history, zipped
  (/releases/h15/data/FRB_h15_xml.zip, about 4 MB), posted each business
  day at 4:15 p.m. The Board removes the DDP's "Build Your Package" queries
  the week of 9 November 2026 and points to this file, so it is read rather
  than a query.
- **The zero curve**, one file: the Board's nominal yield curve,
  /data/yield-curve-tables/feds200628.csv (about 17 MB, every day since 1961),
  updated in batches, days to weeks behind.

A file is asked for with `If-Modified-Since`, naming the Last-Modified the
Board last answered, so an unchanged file answers 304 and nothing is
downloaded again.

Taken from the Board directly, which is public domain ("may be copied and
distributed without permission", https://www.federalreserve.gov/
disclaimer.htm), rather than through FRED, whose API has terms of its own
(meridian-design reference/public-reference-data-sources.md). No key: the
plugin has no secret to keep.

The Board states no rate limit for these pages; the plugin asks one at a
time, at most one every two seconds, says who it is in its User-Agent, and
checks once an hour. The standard library's client: the SDK carries none
(the boundaries spec), and three addresses need nothing more.

`SyntheticBoard` serves the real responses committed under responses/
(responses/index.json says when each was recorded, and how the two files
were trimmed), and 404 for any other page: the plugin's tests and its e2e
run on it, offline.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from typing import Protocol

BASE = "https://www.federalreserve.gov"
CURRENT = "/releases/h10/current/default.htm"
#: H.15's data, every series in the DDP's SDMX format, zipped.
H15_FILE = "/releases/h15/data/FRB_h15_xml.zip"
#: The Board's nominal zero-coupon yield curve, from 1961.
ZERO_FILE = "/data/yield-curve-tables/feds200628.csv"
USER_AGENT = "meridian-fed-board (+https://github.com/open-meridian/plugin-fed-board)"
#: The least time between two requests to the Board, in seconds.
SPACING = 2.0
#: How long one request may take.
TIMEOUT = 30.0
#: The most of a page read: a release is under 100 kB.
MOST_BYTES = 4 * 1024 * 1024
#: The most of a file read: H.15's is about 4 MB, the zero curve's 17 MB.
MOST_FILE_BYTES = 64 * 1024 * 1024
#: The days after a week's Monday its release may come out on: Monday, and
#: the next business days after a holiday.
RELEASE_DAYS = 4


def dated(day: date) -> str:
    """The address of the release that came out on `day`."""
    return f"/releases/h10/{day:%Y%m%d}/default.htm"


def release_days(day: date) -> list[date]:
    """The days the release holding business date `day` may have come out
    on, most likely first: the Monday after `day`'s week, then the days
    after it."""
    monday = day - timedelta(days=day.weekday()) + timedelta(days=7)
    return [monday + timedelta(days=n) for n in range(RELEASE_DAYS)]


class BoardUnreachable(Exception):  # noqa: N818 - what the Board's site was
    """The Board's site could not be asked: no answer, or not in time."""


@dataclass(frozen=True)
class Fetched:
    """One response of the Board's, as received."""

    path: str
    status: int
    body: bytes
    fetched_at: datetime
    last_modified: str = ""
    date: str = ""

    @property
    def url(self) -> str:
        return BASE + self.path

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Board(Protocol):
    mode: str

    async def get(self, path: str, since: str = "") -> Fetched: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class LiveBoard:
    """The Board's site itself."""

    mode = "live"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def get(self, path: str, since: str = "") -> Fetched:
        """The page or file at `path`; with `since`, a Last-Modified the
        Board answered before, 304 and no body where it has not changed."""
        async with self._lock:
            wait = self._last + SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await asyncio.to_thread(self._get, path, since)
            finally:
                self._last = time.monotonic()

    def _get(self, path: str, since: str = "") -> Fetched:
        page = path.endswith(".htm")
        most = MOST_BYTES if page else MOST_FILE_BYTES
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html" if page else "*/*"}
        if since:
            headers["If-Modified-Since"] = since
        request = urllib.request.Request(BASE + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310 - the Board's https address
                body = answer.read(most + 1)
                status = answer.status
                said = answer.headers
        except urllib.error.HTTPError as refused:
            body = refused.read(most + 1) if refused.fp else b""
            status, said = refused.code, refused.headers
        except (urllib.error.URLError, TimeoutError, OSError) as failed:
            reason = getattr(failed, "reason", failed)
            raise BoardUnreachable(f"{BASE}{path}: {type(reason).__name__}") from failed
        if len(body) > most:
            raise BoardUnreachable(f"{BASE}{path}: answered more than {most} bytes")
        return Fetched(
            path,
            status,
            body,
            self._now(),
            last_modified=said.get("Last-Modified", "") if said else "",
            date=said.get("Date", "") if said else "",
        )


class SyntheticBoard:
    """The responses committed under responses/, by their paths; 404 for any
    other."""

    mode = "synthetic"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        held = resources.files(__package__).joinpath("responses")
        index = json.loads(held.joinpath("index.json").read_text(encoding="utf-8"))
        self._held = {
            entry["path"]: (
                entry["status"],
                _body(held.joinpath(entry["file"]).read_bytes(), entry["file"]),
                entry.get("last_modified", ""),
                entry.get("date", ""),
            )
            for entry in index["responses"]
        }

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(self._held)

    async def get(self, path: str, since: str = "") -> Fetched:
        found = self._held.get(path)
        if found is None:
            return Fetched(path, 404, b"Not Found", self._now())
        status, body, last_modified, said = found
        if since and since == last_modified:
            return Fetched(path, 304, b"", self._now(), last_modified=last_modified, date=said)
        return Fetched(path, status, body, self._now(), last_modified=last_modified, date=said)


def _body(held: bytes, name: str) -> bytes:
    """A committed response's body: gzipped where its file says so (a page,
    the zero curve), as received otherwise (H.15's zip)."""
    return gzip.decompress(held) if name.endswith(".gz") else held


def board(synthetic: bool, now: Callable[[], datetime] = utc_now) -> Board:
    return SyntheticBoard(now) if synthetic else LiveBoard(now)
