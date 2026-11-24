"""The plugin's memory and its event loop on the Board's files at full size:
`python tools/memory.py` (in the plugin's environment, no Docker).

The recorded responses under src/fed_board/responses/ are trimmed to keep
the repository small: H.15's file to its business-daily series from
September 2026, the zero curve's to its rows from September 2026. This
script measures the work twice -- on those files as recorded, and on files
of the size the Board serves, built from them -- by repeating each recorded
series' values back through its history (H.15's daily series to July 1954,
the zero curve to June 1961) and, for H.15, adding non-daily series until
its XML is about 70 MB, as the Board's is. Nothing is fetched.

Each phase runs in this one process, as the plugin's do, on the suite's
recorder for the sidecar:

- `push`: the first check, both files answered 200, kept and pushed;
- `again`: the next check, both answered 304;
- `restart`: a new process's first check, answered 304, its copy pushed;
- `wants`: a push, with a want of each dataset arriving while it runs.

For each it prints the process's peak resident memory during the phase
(Linux's VmHWM, reset before the phase through /proc/self/clear_refs), the
memory resident before it, and the longest the event loop went unanswered.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import io
import itertools
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from pathlib import Path

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles import data
from meridian.suites import Recorder

from fed_board.board import H15_FILE, ZERO_FILE, Fetched
from fed_board.declared import CATALOGUE
from fed_board.rates_feed import Rates
from fed_board.raw import RawStore

AT = datetime(2026, 10, 23, 17, 0, tzinfo=UTC)
INSTANCE = "fed-board"
MODIFIED = {H15_FILE: "Thu, 22 Oct 2026 20:15:14 GMT", ZERO_FILE: "Tue, 20 Oct 2026 19:00:12 GMT"}
SEEDED = {
    "EFFR": "SEEDED-EFFR",
    "Daily Treasury Par Yield Curve Rates": "SEEDED-PAR",
    "Daily Treasury Par Real Yield Curve Rates": "SEEDED-REAL",
    "feds200628": "SEEDED-ZERO",
    "Treasury bills secondary market": "SEEDED-BILLS",
    "AA nonfinancial commercial paper": "SEEDED-NONFIN",
    "AA financial commercial paper": "SEEDED-FIN",
    "Bank prime loan rate": "SEEDED-PRIME",
    "Discount window primary credit rate": "SEEDED-PRIMARY",
    "Treasury inflation-indexed long-term average": "SEEDED-LONG",
}
#: How big H.15's XML is made: the Board's is about 70 MB.
H15_BYTES = 70 * 1024 * 1024
#: The days back the files are extended to.
H15_FROM = date(1954, 7, 1)
ZERO_FROM = date(1961, 6, 14)


def _recorded(name: str) -> bytes:
    held = resources.files("fed_board").joinpath("responses", name).read_bytes()
    return gzip.decompress(held) if name.endswith(".gz") else held


def _weekdays(start: date, end: date) -> Iterator[date]:
    day = start
    while day < end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


_SERIES = re.compile(rb"(\s*<kf:Series .*?</kf:Series>)", re.S)
_OBS = re.compile(rb'<frb:Obs OBS_STATUS="(\w+)" OBS_VALUE="([^"]*)" TIME_PERIOD="([\d-]+)" />')


def full_h15() -> bytes:
    """H.15's zip at the Board's size, from the recorded file."""
    xml = zipfile.ZipFile(io.BytesIO(_recorded("FRB_h15_xml.zip"))).read("H15_data.xml")
    blocks = _SERIES.findall(xml)
    head = xml[: xml.index(blocks[0])]
    tail = xml[xml.rindex(blocks[-1]) + len(blocks[-1]) :]
    out = io.BytesIO()
    out.write(head)

    def series(block: bytes, rename: bytes = b"", freq: bytes = b"") -> None:
        observed = _OBS.findall(block)
        opening = block[: block.index(b"<frb:Obs")]
        if rename:
            opening = opening.replace(b'_N.B"', rename + b'"').replace(b'FREQ="9"', freq)
        out.write(opening)
        first = date.fromisoformat(observed[0][2].decode())
        values = itertools.cycle([v for s, v, _ in observed if s == b"A"] or [b"1.00"])
        for day in _weekdays(H15_FROM, first):
            out.write(
                b'<frb:Obs OBS_STATUS="A" OBS_VALUE="%s" TIME_PERIOD="%s" />\n      '
                % (next(values), day.isoformat().encode())
            )
        out.write(block[block.index(b"<frb:Obs") :])

    for block in blocks:
        series(block)
    copies = itertools.count(1)
    while out.tell() < H15_BYTES:
        n = next(copies)
        for block in blocks:
            series(block, b"_N.X%d" % n, b'FREQ="%d"' % (100 + n))
            if out.tell() >= H15_BYTES:
                break
    out.write(tail)
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("H15_data.xml", out.getvalue())
    return packed.getvalue()


def full_zero() -> bytes:
    """The zero curve's CSV at the Board's size, from the recorded file."""
    text = _recorded("feds200628.csv.gz").decode()
    head, _, rows = text.partition("\nDate,")
    header = "Date," + rows.split("\n", 1)[0]
    recorded = [r for r in rows.split("\n", 1)[1].splitlines() if r.strip()]
    first = date.fromisoformat(recorded[0].split(",", 1)[0])
    values = itertools.cycle([r.split(",", 1)[1] for r in recorded])
    lines = [head, header]
    lines += [f"{day},{next(values)}" for day in _weekdays(ZERO_FROM, first)]
    lines += recorded
    return ("\n".join(lines) + "\n").encode()


class Site:
    """The Board's two files, read from disk as each is asked for, as a
    response is read off the network: 304 where it has not changed."""

    mode = "synthetic"

    def __init__(self, files: dict[str, Path]) -> None:
        self.files = files

    async def get(self, path: str, since: str = "") -> Fetched:
        modified = MODIFIED[path]
        if since == modified:
            return Fetched(path, 304, b"", AT, last_modified=modified)
        # Read beside the event loop, as the Board's site is (board.LiveBoard).
        body = await asyncio.to_thread(self.files[path].read_bytes)
        return Fetched(path, 200, body, AT, last_modified=modified)


def _status(field: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1]) * 1024
    return 0


def _reset_peak() -> bool:
    try:
        Path("/proc/self/clear_refs").write_text("5")
    except OSError:
        return False
    return True


def _rates(store: Path, site: Site) -> tuple[Rates, Recorder]:
    recorder = Recorder(INSTANCE)

    def answer(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        value = params.identifiers[0].value
        if value in SEEDED:
            return ops.ResolveIdentifierResult(found=True, instrument_id=SEEDED[value])
        return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)

    recorder.answer("ResolveIdentifier", answer)
    wants = data.Wants(recorder, keys=tuple(e.key for e in CATALOGUE))
    rates = Rates(recorder, site, RawStore(store), wants, now=lambda: AT)
    rates.read_noted()
    return rates, recorder


def _want(n: int, dataset: str, subjects: list[str], day: str) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=f"w-{n}",
            dataset=f"{INSTANCE}:{dataset}",
            data_type="meridian.v1.Rate",
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            business_date=day,
        ),
    )


async def _phase(name: str, work: Callable[[], Awaitable[object]]) -> None:
    """Run `work`, saying its peak resident memory and the event loop's
    longest stall."""
    stall = 0.0
    done = asyncio.Event()

    async def tick() -> None:
        nonlocal stall
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            now = time.monotonic()
            stall = max(stall, now - last - 0.01)
            last = now
            if done.is_set():
                return

    before = _status("VmRSS")
    reset = _reset_peak()
    ticker = asyncio.create_task(tick())
    await asyncio.sleep(0)  # the ticker running before the work starts
    started = time.monotonic()
    try:
        await work()
    finally:
        done.set()
        await ticker
    took = time.monotonic() - started
    peak = _status("VmHWM") if reset else 0
    print(
        f"{name:8} peak {peak / 2**20:7.1f} MiB  (resident before {before / 2**20:6.1f} MiB)"
        f"  loop stalled at most {stall:6.2f} s  took {took:6.2f} s"
        + ("" if reset else "  [peak not reset: /proc/self/clear_refs refused]")
    )


async def measure(files: dict[str, Path], store: Path) -> None:
    site = Site(files)
    rates, _ = _rates(store / "a", site)
    await _phase("push", rates.check)
    await _phase("again", rates.check)
    restarted, _ = _rates(store / "a", site)
    await _phase("restart", restarted.check)

    fresh, _ = _rates(store / "b", site)

    async def push_with_wants() -> None:
        h15 = ["SEEDED-EFFR", "SEEDED-PAR", "SEEDED-REAL", "SEEDED-BILLS"]
        await asyncio.gather(
            fresh.check(),
            fresh.wants.hear(_want(1, "fed_h15", h15, "2026-09-15"), fresh.answer),
            fresh.wants.hear(_want(2, "fed_zero", ["SEEDED-ZERO"], "2026-09-15"), fresh.answer),
        )

    await _phase("wants", push_with_wants)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--recorded", action="store_true", help="the files as recorded, not at full size"
    )
    parser.add_argument("--measure", metavar="DIR", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.measure:
        root = Path(args.measure)
        files = {H15_FILE: root / "h15.zip", ZERO_FILE: root / "zero.csv"}
        asyncio.run(measure(files, root))
        return
    with tempfile.TemporaryDirectory(prefix="fed-board-memory-") as held:
        root = Path(held)
        h15 = _recorded("FRB_h15_xml.zip") if args.recorded else full_h15()
        zero = _recorded("feds200628.csv.gz") if args.recorded else full_zero()
        (root / "h15.zip").write_bytes(h15)
        (root / "zero.csv").write_bytes(zero)
        xml = zipfile.ZipFile(io.BytesIO(h15)).getinfo("H15_data.xml").file_size
        print(
            f"H.15 zip {len(h15) / 2**20:.1f} MiB ({xml / 2**20:.1f} MiB of XML),"
            f" zero curve {len(zero) / 2**20:.1f} MiB"
        )
        # Measured in a process of its own, so building the files costs it nothing.
        subprocess.run([sys.executable, __file__, "--measure", held], check=True)


if __name__ == "__main__":
    main()
