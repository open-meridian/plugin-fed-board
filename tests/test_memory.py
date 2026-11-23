"""Memory is a budget, not something found at the pod's limit: reading the
largest file the plugin reads, the zero curve's CSV (about 16.7 MB, every
business day since 1961), and keeping it, take a fixed working memory beyond
the response itself, whatever the file's size."""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fed_board import zero
from fed_board.board import ZERO_FILE, Fetched
from fed_board.raw import RawStore

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
