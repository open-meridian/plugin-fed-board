"""Memory is a budget, not something found at the pod's limit: reading the
largest file the plugin reads, the zero curve's CSV (about 16.7 MB, every
business day since 1961), and keeping it, take a fixed working memory beyond
the response itself, whatever the file's size; checking it again, a
restart's push and a want of it hold no copy of it at all."""

from __future__ import annotations

import asyncio
import tracemalloc
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles import data
from meridian.suites import Recorder

from fed_board import zero
from fed_board.board import ZERO_FILE, Fetched
from fed_board.declared import CATALOGUE
from fed_board.rates_feed import Rates
from fed_board.raw import RawStore

from conftest import INSTANCE, seeded

#: The working memory either may take beyond the response held: 4 MiB.
BUDGET = 4 * 1024 * 1024
#: Business days in the file as the Board serves it now, and its columns.
DAYS = 17_000
COLUMNS = ["BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2"] + [
    f"{name}{n:02d}" for name in ("SVENY", "SVENPY", "SVENF", "SVEN1F") for n in range(1, 31)
]


def _zero_file() -> bytes:
    """A file of the zero curve's size and shape: its notes, its header, and
    a row for each of `DAYS` days."""
    row = ",".join(["4.123456789"] * len(COLUMNS))
    start = date(1961, 6, 14)
    lines = ["Note: not an official release.", "", "Date," + ",".join(COLUMNS)]
    lines += [f"{start + timedelta(days=n)},{row}" for n in range(DAYS)]
    return ("\n".join(lines) + "\n").encode()


def _peak(work: Callable[[], object]) -> int:
    """The most memory `work` held at once beyond what was held before it."""
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        work()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak - before


def test_the_zero_curve_is_read_within_a_fixed_budget() -> None:
    body = _zero_file()
    assert len(body) > 16_000_000
    seen = 0

    def read() -> None:
        nonlocal seen
        for _ in zero.points(body):
            seen += 1

    peak = _peak(read)
    assert seen == DAYS * 30
    assert peak < BUDGET, f"reading the zero curve held {peak >> 20} MiB beyond the file"


def test_a_large_file_is_kept_within_a_fixed_budget(tmp_path: Path) -> None:
    body = _zero_file()
    store = RawStore(tmp_path)
    at = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)
    fetched = Fetched(ZERO_FILE, 200, body, at, last_modified="Tue, 17 Nov 2026 20:00:04 GMT")
    keys: list[str] = []
    peak = _peak(lambda: keys.append(store.keep(fetched)))
    assert peak < BUDGET, f"keeping the zero curve held {peak >> 20} MiB beyond the file"
    # Kept as before: the same record, read back whole.
    kept = store.read(keys[0])
    assert kept is not None and kept["last_modified"] == fetched.last_modified
    assert store.body(keys[0]) == body


def test_a_file_that_is_not_text_is_kept_within_a_fixed_budget(tmp_path: Path) -> None:
    body = bytes(range(256)) * 40_000  # 10 MB that is not UTF-8, as H.15's zip is not
    store = RawStore(tmp_path)
    fetched = Fetched("/releases/h15/data/FRB_h15_xml.zip", 200, body, datetime.now(UTC))
    keys: list[str] = []
    peak = _peak(lambda: keys.append(store.keep(fetched)))
    assert peak < BUDGET, f"keeping the zip held {peak >> 20} MiB beyond the file"
    kept = store.read(keys[0])
    assert kept is not None and "body" not in kept
    assert store.body(keys[0]) == body


class _Site:
    """The Board serving the zero curve at its size: 200, then 304 since."""

    mode = "synthetic"
    modified = "Tue, 17 Nov 2026 20:00:04 GMT"

    def __init__(self, body: bytes) -> None:
        self.body = body

    async def get(self, path: str, since: str = "") -> Fetched:
        at = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)
        if path != ZERO_FILE:
            return Fetched(path, 404, b"", at)
        if since == self.modified:
            return Fetched(path, 304, b"", at, last_modified=self.modified)
        return Fetched(path, 200, self.body, at, last_modified=self.modified)


def _rates(tmp_path: Path, body: bytes) -> tuple[Rates, Recorder]:
    recorder = Recorder(INSTANCE)
    seeded(recorder)
    wants = data.Wants(recorder, keys=tuple(e.key for e in CATALOGUE))
    at = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)
    return Rates(recorder, _Site(body), RawStore(tmp_path), wants, now=lambda: at), recorder


def test_the_zero_curve_checked_again_and_wanted_takes_a_fixed_budget(tmp_path: Path) -> None:
    """Once the zero curve is kept and pushed, checking it again (answered
    304), a restart's push and a want of a past day each take a fixed working
    memory: the file is not held again to answer them."""
    body = _zero_file()
    board, recorder = _rates(tmp_path, body)
    asyncio.run(board.check())
    pushed = len(recorder.on("RecordRates"))
    assert pushed
    del body

    peak = _peak(lambda: asyncio.run(board.check()))
    assert peak < BUDGET, f"checking the zero curve again held {peak >> 20} MiB"

    restarted, again = _rates(tmp_path, b"")
    restarted.read_noted()
    peak = _peak(lambda: asyncio.run(restarted.check()))
    assert again.on("RecordRates"), "a restart pushes the file kept"
    assert peak < BUDGET, f"a restart's push held {peak >> 20} MiB"

    want = Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id="w-1",
            dataset=f"{INSTANCE}:fed_zero",
            data_type="meridian.v1.Rate",
            subjects=[ops.SubjectRef(entity_id="INS-ZERO")],
            business_date="2000-01-03",
        ),
    )
    peak = _peak(lambda: asyncio.run(board.wants.hear(want, board.answer)))
    assert [b.want_id for b in recorder.on("RecordRates")][pushed:] == ["w-1"]
    assert peak < BUDGET, f"answering a want of the zero curve held {peak >> 20} MiB"
