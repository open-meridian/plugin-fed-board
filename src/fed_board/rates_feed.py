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

**Memory and the event loop.** Beside the record kept of each file (raw.py),
which holds it escaped in JSON, the file is kept as received
(`current/<dataset>-<record>`), and read from there a piece at a time: a
304, a restart's push and a want hold neither the file nor its record. A
file answered 304 since it was pushed is not read at all. Keeping a file and
reading it -- H.15's is 70 MB of XML, seconds to read -- run beside the event
loop, which answers the plugin's health check, its pages and the lake
meanwhile; one read of each file at a time.

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

import asyncio
import json
import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from meridian.operations import Rate
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import data
from meridian.roles.data import rates

from . import h15, zero
from .board import H15_FILE, ZERO_FILE, Board, BoardUnreachable, Fetched, utc_now
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
#: Where each file is kept as received, at the storage's root.
COPIES = "current"
#: How many values a push holds while it finds the file's latest day before
#: it lets go of those too old.
PRUNE = 4096

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


def parse(
    key: str, file: bytes | Path, wanted: Callable[[date], bool] = lambda _: True
) -> Iterator[Any]:
    """The values the dataset's file states on the days `wanted` keeps: H.15's
    observations, the zero curve's points, each with its `day`."""
    if key == H15:
        return h15.observations(file, wanted)
    return zero.points(file, wanted)


def recent(key: str, file: bytes | Path, days: int) -> tuple[date | None, list[Any]]:
    """The latest day the dataset's file states a value on, and its values on
    the `days` days to it, in the file's order: read once, holding no more
    than those (and at most `PRUNE` more)."""
    latest: date | None = None
    cut = date.min
    kept: list[Any] = []
    most = PRUNE
    for value in parse(key, file):
        if latest is None or value.day > latest:
            latest = value.day
            cut = latest - timedelta(days=days)
        if value.day > cut:
            kept.append(value)
            if len(kept) > most:
                kept = [v for v in kept if v.day > cut]
                most = max(PRUNE, 2 * len(kept))
    return latest, [v for v in kept if v.day > cut]


@dataclass(frozen=True)
class Read:
    """What was read of a file kept: the record it was kept under and its
    Last-Modified, its latest day where that was asked, and its values."""

    raw_key: str
    last_modified: str
    latest: date | None
    values: list[Any]


class Rates:
    """The plugin's rates: its two files read, resolved, recorded, its
    wants answered. `role` is the data role's class (`__main__`'s `Lake`,
    open-meridian 0.35), or the suite's `Recorder` in its tests."""

    def __init__(
        self,
        role: Any,
        board: Board,
        raw: RawStore,
        wants: data.Wants,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.role = role
        self.board = board
        self.raw = raw
        self.wants = wants
        self.now = now
        self.feed = rates.Feed(
            role, SOURCE, wants=wants, day_zone=RATES_ZONE, clock_ns=lambda: _ns(self.now())
        )
        self.sources = {key: Source(key) for key in FILES}
        self._built_on = board.mode
        #: One read of each file at a time; a copy no longer kept is let go
        #: of only between reads.
        self._reading = {key: asyncio.Lock() for key in FILES}
        #: One request for each file at a time: a want arriving while a push
        #: asks for the file waits for it and reads the copy it kept.
        self._asking = {key: asyncio.Lock() for key in FILES}

    def read_noted(self) -> None:
        """What was noted of each file, read from storage once the plugin has
        registered (`Lake.on_start`; open-meridian 0.37.0), for the board it
        was built with: one switched to since keeps nothing noted (`use`)."""
        if self.board.mode != self._built_on:
            return
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

    def _copy(self, key: str, raw_key: str) -> Path:
        """Where the file kept under `raw_key` is kept as received."""
        name = Path(raw_key).name.removesuffix(".json.gz")
        return self.raw.root / COPIES / f"{key}-{name}"

    def held(self, key: str) -> Path | None:
        """The dataset's file kept last, as received, where storage holds both
        it and its record; None otherwise. Nothing is read."""
        source = self.sources[key]
        if not source.raw_key or not self.raw.holds(source.raw_key):
            return None
        copy = self._copy(key, source.raw_key)
        return copy if copy.is_file() else None

    def _keep(self, key: str, fetched: Fetched) -> tuple[str, Path]:
        """Keep a file the Board answered: its record, then the file as
        received; the record's key and where the file is."""
        raw_key = self.raw.keep(fetched)
        copy = self._copy(key, raw_key)
        copy.parent.mkdir(parents=True, exist_ok=True)
        partial = copy.with_name(copy.name + ".partial")
        partial.write_bytes(fetched.body)
        partial.replace(copy)
        return raw_key, copy

    def _let_go(self, key: str, copy: Path) -> None:
        """Remove the dataset's files kept before `copy`."""
        for older in copy.parent.glob(f"{key}-*"):
            if older != copy:
                older.unlink(missing_ok=True)

    async def file(self, key: str) -> Path | None:
        """Where the dataset's file as the Board serves it now is kept: asked
        for since the copy kept, which answers where it has not changed;
        None, said on the source, where neither can be read. The file is not
        read here."""
        async with self._asking[key]:
            return await self._ask(key)

    async def _ask(self, key: str) -> Path | None:
        source = self.sources[key]
        source.checked_at = self.now()
        held = self.held(key)
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
        raw_key, copy = await asyncio.to_thread(self._keep, key, fetched)
        source.raw_key = raw_key
        source.last_modified = fetched.last_modified
        source.error = ""
        self._note(source)
        async with self._reading[key]:
            self._let_go(key, copy)
        return copy

    async def read(
        self, key: str, wanted: Callable[[date], bool] | None = None, days: int = 0
    ) -> Read | None:
        """The dataset's file kept last, read beside the event loop: its values
        on the days `wanted` keeps; or, with no `wanted`, its latest day and
        its values on the `days` days to it. None where none is kept."""
        source = self.sources[key]
        async with self._reading[key]:
            file = self.held(key)
            if file is None:
                return None
            raw_key, last_modified = source.raw_key, source.last_modified
            if wanted is not None:
                values = await asyncio.to_thread(lambda: list(parse(key, file, wanted)))
                return Read(raw_key, last_modified, None, values)
            latest, values = await asyncio.to_thread(recent, key, file, days)
            return Read(raw_key, last_modified, latest, values)

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
        values: Sequence[Any],
        raw_key: str,
        last_modified: str,
        subjects: set[str] | None = None,
    ) -> list[Rate]:
        """The dataset's rows for the `values` read from the file kept under
        `raw_key`, for `subjects` where given; each naming the file it was
        first read from with its value."""
        found = await self.resolved(key)
        published = last_modified_ns(last_modified)
        firsts = Firsts(self.raw, key, PUSH_DAYS * 2)
        out: list[Rate] = []

        def keep(subject: str, series: str, day: date, value: str, **given: Any) -> None:
            if not subject or (subjects is not None and subject not in subjects):
                return
            first, at = firsts.first(series, day.isoformat(), value, raw_key, published)
            out.append(
                self.feed.rate(
                    subject,
                    key,
                    business_date=day,
                    published_ns=at,
                    series=series,
                    raw_key=first,
                    value=value,
                    **given,
                )
            )

        try:
            if key == H15:
                for seen in values:
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
                for point in values:
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
            except (h15.NotTheFile, zero.NotTheFile, OSError) as wrong:
                self.sources[key].error = str(wrong)
                log.warning("%s did not read: %s", LABELS[key], wrong)

    async def _check(self, key: str) -> None:
        source = self.sources[key]
        if await self.file(key) is None or source.pushed == source.raw_key:
            return
        read = await self.read(key, days=PUSH_DAYS)
        if read is None:
            return
        source.latest_day = read.latest
        if read.latest is None:
            source.pushed = read.raw_key
            return
        pushed = await self.rows(key, read.values, read.raw_key, read.last_modified)
        await self.record(key, pushed)
        source.pushed = read.raw_key
        log.info("%s: %d rates pushed, to %s", LABELS[key], len(pushed), read.latest)

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
        silent = {**declined, **{s: "source_silent" for s in mine}}
        if self.held(key) is None and await self.file(key) is None:
            return silent
        days = self._days(want, source.latest_day)
        oldest = self.now().astimezone(NEW_YORK).date() - timedelta(days=HISTORIES[key])
        if days and all(d < oldest for d in days):
            return {**declined, **{s: "beyond_history" for s in mine}}
        if days:
            asked_days = set(days)
            read = await self.read(key, asked_days.__contains__)
        else:
            # The latest: the file's last day.
            read = await self.read(key, days=1)
        if read is None:
            return silent
        rows = await self.rows(key, read.values, read.raw_key, read.last_modified, mine)
        await self.record(key, rows, want.want_id)
        answered = {r.meta.subjects[0].entity_id for r in rows if r.meta is not None}
        return {**declined, **{s: "source_silent" for s in mine if s not in answered}}
