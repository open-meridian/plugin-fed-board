"""H.15 and the zero curve into the lake, as rates (contract v27, W10.4 and
W10.7; spec/a-public-rates-and-filings-data-plugin): each file read when the
Board updates it, its recent days pushed, and any past day recorded when the
lake wants it.

The conversion -- row keys, tenors, values with their unit, the rows'
batches -- is the SDK's (`meridian.roles.data.rates`, ruling 345); the
bookkeeping of wants, counts and licences is the data role's
(`meridian.roles.data.Wants`). What is the Board's stays here: which file,
which series, and which record each is about (h15.py, zero.py).

**Push.** Each file is asked for at start and every hour with the
Last-Modified the Board answered before (board.py), so an unchanged file
answers 304 and costs nothing; which file was kept last is noted in storage
(`latest-<dataset>.json`), so a restart asks the same way and reads the
copy kept. A file not pushed yet in this process has its last `PUSH_DAYS`
days recorded: a new day, and any value the Board revised within the month,
as the row's next version. Each rate names the file it was first read from
with its value, and that file's published time (raw.Firsts), so a value read
again is answered unchanged.

**Subjects.** Each record is resolved by the identifiers the platform seeds
(`symbol`, its administrator's code, at its source), once per process; one
the deployment does not hold is reported missing, once a day, and its rows
left out (the SDK's `Feed.subject`). The plugin never mints.

**Wants.** A want of `fed_h15` or `fed_zero` is answered from the file kept
last (read once if none is): the days asked, for the subjects the dataset
covers. Any other subject is declined `not_covered`; a want before the
dataset's history `beyond_history`; a day the file holds no value for
`source_silent`. A standing want is kept current by the push.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from meridian.operations import Rate
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import data
from meridian.roles.data import rates

from . import h15, zero
from .board import H15_FILE, ZERO_FILE, Board, BoardUnreachable, utc_now
from .declared import H15, H15_HISTORY, RATES_ZONE, ZERO, ZERO_HISTORY
from .raw import Firsts, RawStore
from .release import last_modified_ns

log = logging.getLogger("fed_board")

#: The source this plugin names on what it reports missing.
SOURCE = "fed-board"
#: The days back from the file's latest that a push records again.
PUSH_DAYS = 31
#: The most days one want is answered for: a year.
MOST_DAYS = 366

NEW_YORK = ZoneInfo(RATES_ZONE)


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1000


@dataclass(frozen=True)
class Subject:
    """A record the rates are recorded against: its identifiers, its type,
    and what the Board calls it."""

    identifiers: tuple[str, str, str]
    instrument_type: str
    description: str


#: Each dataset's records, in the order the Datasets page lists them.
SUBJECTS: dict[str, tuple[Subject, ...]] = {
    H15: (
        Subject(h15.EFFR, "interest_rate", "Federal funds effective rate"),
        Subject(h15.NONFINANCIAL, "rate_curve", "AA nonfinancial commercial paper"),
        Subject(h15.FINANCIAL, "rate_curve", "AA financial commercial paper"),
        Subject(h15.PRIME, "interest_rate", "Bank prime loan rate"),
        Subject(h15.PRIMARY, "interest_rate", "Discount window primary credit rate"),
        Subject(h15.BILLS, "rate_curve", "Treasury bills, secondary market"),
        Subject(h15.PAR, "rate_curve", "Treasury constant maturities, nominal"),
        Subject(h15.REAL, "rate_curve", "Treasury constant maturities, inflation-indexed"),
        Subject(h15.LONG, "interest_rate", "Treasury inflation-indexed long-term average"),
    ),
    ZERO: (Subject(zero.CURVE, "rate_curve", "Treasury zero-coupon yield curve"),),
}

#: Each dataset's file, and how it is named on the pages.
FILES = {H15: H15_FILE, ZERO: ZERO_FILE}
LABELS = {H15: "H.15 selected interest rates", ZERO: "The zero curve (feds200628)"}
HISTORIES = {H15: H15_HISTORY, ZERO: ZERO_HISTORY}


@dataclass
class Source:
    """One file as the plugin last saw it, for its pages; what is noted in
    storage is the kept copy and its Last-Modified, to ask again with."""

    key: str
    checked_at: datetime | None = None
    error: str = ""
    last_modified: str = ""
    raw_key: str = ""
    pushed: str = ""
    latest_day: date | None = None
    calls: int = 0
    #: Each row recorded, the end of its day to its published time, in
    #: nanoseconds, the latest kept: for the Lag tab.
    lags: list[int] = field(default_factory=list)


def latest_day(key: str, body: bytes) -> date | None:
    """The latest day the dataset's file states a value it records on."""
    if key == H15:
        days = (o.day for o in h15.observations(body))
    else:
        days = (p.day for p in zero.points(body))
    return max(days, default=None)


class Rates:
    """The plugin's rates: its two files read, resolved, recorded, its
    wants answered. `plugin` is the connected `meridian.Plugin`, or the
    suite's `Recorder` in its tests."""

    def __init__(
        self,
        plugin: Any,
        board: Board,
        raw: RawStore,
        wants: data.Wants,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.plugin = plugin
        self.board = board
        self.raw = raw
        self.wants = wants
        self.now = now
        self.feed = rates.Feed(
            plugin, SOURCE, wants=wants, day_zone=RATES_ZONE, clock_ns=lambda: _ns(self.now())
        )
        self.sources = {key: Source(key) for key in FILES}
        for key, source in self.sources.items():
            noted = self._noted(key)
            source.raw_key = noted.get("raw_key", "")
            source.last_modified = noted.get("last_modified", "")

    def use(self, board: Board) -> None:
        """Read from `board` from now on: sample data turned on or off. What
        was kept of the other is not asked with again."""
        if board.mode != self.board.mode:
            self.board = board
            for source in self.sources.values():
                source.last_modified = source.raw_key = source.pushed = ""

    # ── The files ───────────────────────────────────────────────────────

    def _noted_path(self, key: str) -> Any:
        return self.raw.root / f"latest-{key}.json"

    def _noted(self, key: str) -> dict[str, str]:
        try:
            held: dict[str, str] = json.loads(self._noted_path(key).read_text())
        except (OSError, ValueError):
            return {}
        return held

    def _note(self, source: Source) -> None:
        target = self._noted_path(source.key)
        partial = target.with_suffix(".partial")
        partial.write_text(
            json.dumps({"raw_key": source.raw_key, "last_modified": source.last_modified})
        )
        partial.replace(target)

    async def file(self, key: str) -> bytes | None:
        """The dataset's file as the Board serves it now: asked for since the
        copy kept, which answers where it has not changed; None, said on the
        source, where neither can be read."""
        source = self.sources[key]
        source.checked_at = self.now()
        held = self.raw.body(source.raw_key) if source.raw_key else None
        since = source.last_modified if held is not None else ""
        try:
            fetched = await self.board.get(FILES[key], since=since)
        except BoardUnreachable as failed:
            source.error = str(failed)
            log.warning("%s was not read: %s", LABELS[key], failed)
            return held
        source.calls += 1
        if fetched.status == 304 and held is not None:
            source.error = ""
            return held
        if fetched.status != 200:
            source.error = f"{fetched.url} answered {fetched.status}"
            return held
        source.raw_key = self.raw.keep(fetched)
        source.last_modified = fetched.last_modified
        source.error = ""
        self._note(source)
        return fetched.body

    # ── Rows ────────────────────────────────────────────────────────────

    async def subject(self, held: Subject) -> str:
        return await self.feed.subject(
            held.identifiers, description=held.description, instrument_type=held.instrument_type
        )

    async def resolved(self, key: str) -> dict[tuple[str, str, str], str]:
        """Each of the dataset's records by its identifiers, the deployment's
        instrument for it, or empty where it holds none."""
        return {s.identifiers: await self.subject(s) for s in SUBJECTS[key]}

    async def rows(
        self,
        key: str,
        body: bytes,
        wanted: Callable[[date], bool],
        subjects: set[str] | None = None,
    ) -> list[Rate]:
        """The dataset's rows the file states on the days `wanted` keeps, for
        `subjects` where given; each naming the file it was first read from
        with its value."""
        source = self.sources[key]
        found = await self.resolved(key)
        published = last_modified_ns(source.last_modified)
        firsts = Firsts(self.raw, key, PUSH_DAYS * 2)
        out: list[Rate] = []

        def keep(subject: str, series: str, day: date, value: str, **given: Any) -> None:
            if not subject or (subjects is not None and subject not in subjects):
                return
            raw_key, at = firsts.first(series, day.isoformat(), value, source.raw_key, published)
            out.append(
                self.feed.rate(
                    subject,
                    key,
                    business_date=day,
                    published_ns=at,
                    series=series,
                    raw_key=raw_key,
                    value=value,
                    **given,
                )
            )

        try:
            if key == H15:
                for seen in h15.observations(body, wanted):
                    series = h15.BY_KEY[seen.series]
                    keep(
                        found.get(series.subject, ""),
                        series.key,
                        seen.day,
                        seen.value,
                        kind=series.kind,
                        convention=series.convention,
                        tenor=series.tenor or None,
                    )
            else:
                for point in zero.points(body, wanted):
                    keep(
                        found.get(zero.CURVE, ""),
                        point.column,
                        point.day,
                        point.value,
                        kind="zero",
                        convention=rates.CONTINUOUS,
                        tenor=point.tenor,
                    )
        finally:
            firsts.save()
        return out

    async def record(self, key: str, rows: Sequence[Rate], want_id: str = "") -> int:
        if not rows:
            return 0
        sent = await self.feed.record(key, rows, want_id)
        source = self.sources[key]
        for row in rows:
            meta = row.meta
            if meta is not None and meta.source_times:
                source.lags.append(max(0, meta.source_times[0].at_ns - meta.valid_until_ns))
        del source.lags[:-2000]
        return sent

    # ── Push ────────────────────────────────────────────────────────────

    async def check(self) -> None:
        """Read each file, and push its recent days where this process has
        not pushed that copy."""
        for key in FILES:
            try:
                await self._check(key)
            except (h15.NotTheFile, zero.NotTheFile) as wrong:
                self.sources[key].error = str(wrong)
                log.warning("%s did not read: %s", LABELS[key], wrong)

    async def _check(self, key: str) -> None:
        source = self.sources[key]
        body = await self.file(key)
        if body is None or source.pushed == source.raw_key:
            return
        latest = latest_day(key, body)
        source.latest_day = latest
        if latest is None:
            source.pushed = source.raw_key
            return
        cut = latest - timedelta(days=PUSH_DAYS)
        pushed = await self.rows(key, body, lambda day: day > cut)
        await self.record(key, pushed)
        source.pushed = source.raw_key
        log.info("%s: %d rates pushed, to %s", LABELS[key], len(pushed), latest)

    # ── Wants ───────────────────────────────────────────────────────────

    def _days(self, want: ops.ObservationsWantedEvent, latest: date | None) -> list[date]:
        if want.business_date:
            return [date.fromisoformat(want.business_date)]
        if want.valid_from_ns or want.valid_until_ns:
            start = datetime.fromtimestamp(want.valid_from_ns // 10**9, NEW_YORK).date()
            end_ns = want.valid_until_ns or _ns(self.now())
            end = datetime.fromtimestamp(end_ns // 10**9, NEW_YORK).date()
            days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
            return days[-MOST_DAYS:]
        return [latest] if latest is not None else []

    async def answer(
        self, want: ops.ObservationsWantedEvent, key: str, asked: list[str], kinds: tuple[int, ...]
    ) -> dict[str, str]:
        """The answer `data.Wants.hear` asks for: rows recorded against the
        want, and what is declined, by subject and reason."""
        if key not in FILES or want.data_type not in ("", "meridian.v1.Rate"):
            return {s: "not_covered" for s in asked}
        covered = {i for i in (await self.resolved(key)).values() if i}
        declined = {s: "not_covered" for s in asked if s not in covered}
        mine = {s for s in asked if s in covered}
        if want.standing:
            self.wants.stand(want, sorted(mine), kinds)
        if not mine:
            return declined
        source = self.sources[key]
        body = self.raw.body(source.raw_key) if source.raw_key else None
        if body is None:
            body = await self.file(key)
        if body is None:
            return {**declined, **{s: "source_silent" for s in mine}}
        days = self._days(want, source.latest_day)
        oldest = self.now().astimezone(NEW_YORK).date() - timedelta(days=HISTORIES[key])
        if days and all(d < oldest for d in days):
            return {**declined, **{s: "beyond_history" for s in mine}}
        if not days:
            # The latest: the file's last day.
            last = latest_day(key, body)
            days = [last] if last is not None else []
        asked_days = set(days)
        rows = await self.rows(key, body, lambda d: d in asked_days, mine)
        await self.record(key, rows, want.want_id)
        answered = {r.meta.subjects[0].entity_id for r in rows if r.meta is not None}
        return {**declined, **{s: "source_silent" for s in mine if s not in answered}}
