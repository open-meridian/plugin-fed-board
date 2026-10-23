"""H.15 and the zero curve: read from the Board's recorded files, recorded
as rates against the records the platform seeds, pushed once per file, and
past days recorded when the lake wants them."""

from __future__ import annotations

import asyncio
import gzip
from datetime import date
from importlib import resources
from pathlib import Path

import pytest
from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.suites import Recorder

from fed_board import h15, zero
from fed_board.board import H15_FILE, ZERO_FILE, Fetched, SyntheticBoard
from fed_board.raw import RawStore

from conftest import AT_RATES, H15_DATASET, INSTANCE, ZERO_DATASET, rates, seeded


def _file(name: str) -> bytes:
    held = resources.files("fed_board").joinpath("responses", name).read_bytes()
    return gzip.decompress(held) if name.endswith(".gz") else held


def _sent(recorder: Recorder) -> list[ops.Rate]:
    return [r for b in recorder.on("RecordRates") for r in b.rates]


def _want(want_id: str, subjects: list[str], dataset: str, day: str = "") -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=dataset,
            data_type="meridian.v1.Rate",
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            business_date=day,
        ),
    )


# ── The files ───────────────────────────────────────────────────────────


def test_h15_reads_each_business_daily_series_in_force() -> None:
    seen = list(h15.observations(_file("FRB_h15_xml.zip")))
    assert {o.series for o in seen} == {s.key for s in h15.SERIES}
    ten = [o for o in seen if o.series == "RIFLGFCY10_N.B"]
    assert ten[-1].day == date(2026, 10, 21) and ten[-1].value == "5.13"
    # A day the Board left n.a. (90-day commercial paper) is no observation.
    assert not [o for o in seen if o.series == "RIFSPPNAAD90_N.B" and o.day == date(2026, 10, 21)]


def test_h15_records_only_series_with_a_seeded_record() -> None:
    recorded = [s for s in h15.SERIES if s.recorded]
    assert {s.subject for s in recorded} == {h15.EFFR, h15.PAR, h15.REAL}
    assert [s.tenor for s in recorded if s.subject == h15.PAR] == [
        "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y",
    ]  # fmt: skip
    assert [s.tenor for s in recorded if s.subject == h15.REAL] == ["5Y", "7Y", "10Y", "20Y", "30Y"]
    proposed = {s.proposed for s in h15.SERIES if not s.recorded}
    assert len(proposed) == 6 and all(p.startswith("frb: ") for p in proposed)


def test_a_response_that_is_not_the_h15_file_is_refused() -> None:
    with pytest.raises(h15.NotTheFile):
        list(h15.observations(b"<html>Not Found</html>"))


def test_the_zero_curve_reads_its_zero_coupon_yields() -> None:
    points = list(zero.points(_file("feds200628.csv.gz")))
    assert {p.tenor for p in points} == {f"{n}Y" for n in range(1, 31)}
    last = [p for p in points if p.day == date(2026, 10, 16)]
    assert len(last) == 30 and last[9].column == "SVENY10" and last[9].tenor == "10Y"


def test_a_tenor_left_na_is_no_point() -> None:
    body = (
        b"notes\n\nDate,SVENY01,"
        + b",".join(f"SVENY{n:02d}".encode() for n in range(2, 31))
        + b"\n1961-06-14,2.98,"
        + b",".join(b"NA" if n > 7 else b"3.0" for n in range(2, 31))
        + b"\n"
    )
    assert [p.tenor for p in zero.points(body)] == [f"{n}Y" for n in range(1, 8)]


def test_a_response_that_is_not_the_zero_curve_is_refused() -> None:
    with pytest.raises(zero.NotTheFile):
        list(zero.points(b"<html>Not Found</html>"))


# ── Push ────────────────────────────────────────────────────────────────


def test_a_push_records_each_files_last_month(tmp_path: Path) -> None:
    recorder = Recorder(INSTANCE)
    seeded(recorder)
    board = rates(tmp_path, recorder)
    asyncio.run(board.check())
    sent = _sent(recorder)
    h15_rows = [r for r in sent if r.meta.source.dataset == H15_DATASET]
    zero_rows = [r for r in sent if r.meta.source.dataset == ZERO_DATASET]
    assert {r.meta.business_date for r in h15_rows} >= {"2026-10-21", "2026-09-22"}
    assert min(r.meta.business_date for r in h15_rows) > "2026-09-20"
    ten = next(
        r
        for r in h15_rows
        if r.meta.row_key.startswith("RIFLGFCY10_N.B") and r.meta.business_date == "2026-10-21"
    )
    assert ten.meta.subjects[0].entity_id == "INS-PAR"
    assert ten.kind == ops.RATE_KIND_PAR_YIELD and ten.tenor.count == 10
    assert ten.tenor.unit == ops.TENOR_UNIT_YEAR
    assert str(as_decimal(ten.value.value)) == "5.13" and ten.value.unit == ops.VALUE_UNIT_PERCENT
    assert ten.convention.compounding == ops.COMPOUNDING_COMPOUNDED
    assert ten.convention.periods_per_year == 2
    # The published time is when the Board posted the file.
    assert ten.meta.source_times[0].at_ns == 1792700114 * 10**9
    effr = next(r for r in h15_rows if r.meta.subjects[0].entity_id == "INS-EFFR")
    assert effr.kind == ops.RATE_KIND_FIXING and not effr.HasField("tenor")
    assert effr.convention.day_count == ops.DAY_COUNT_ACT_360
    curve = [r for r in zero_rows if r.meta.business_date == "2026-10-16"]
    assert len(curve) == 30 and {r.kind for r in curve} == {ops.RATE_KIND_ZERO}
    assert {r.convention.compounding for r in curve} == {ops.COMPOUNDING_CONTINUOUS}
    # Nothing of a series with no seeded record.
    assert not [r for r in h15_rows if "RIFSPBLP" in r.meta.row_key]


def test_a_file_pushed_is_not_pushed_again(tmp_path: Path) -> None:
    recorder = Recorder(INSTANCE)
    seeded(recorder)
    board = rates(tmp_path, recorder)
    asyncio.run(board.check())
    batches = len(recorder.on("RecordRates"))
    asyncio.run(board.check())
    assert len(recorder.on("RecordRates")) == batches
    assert board.sources["fed_h15"].calls == 2


def test_a_restart_asks_since_the_copy_kept_and_names_it(tmp_path: Path) -> None:
    """The next process asks with the Last-Modified noted, is answered 304,
    and records the same rows naming the same kept file: unchanged."""
    first = Recorder(INSTANCE)
    seeded(first)
    asyncio.run(rates(tmp_path, first).check())
    again = Recorder(INSTANCE)
    seeded(again)
    asked: list[str] = []
    site = SyntheticBoard(lambda: AT_RATES)

    class Counting:
        mode = "synthetic"

        async def get(self, path: str, since: str = "") -> Fetched:
            asked.append(since)
            return await site.get(path, since)

    board = rates(tmp_path, again)
    board.board = Counting()
    asyncio.run(board.check())
    assert asked == ["Thu, 22 Oct 2026 20:15:14 GMT", "Tue, 20 Oct 2026 19:00:12 GMT"]
    before = {r.meta.row_key: (r.meta.raw.key, r.meta.source_times[0].at_ns) for r in _sent(first)}
    after = {r.meta.row_key: (r.meta.raw.key, r.meta.source_times[0].at_ns) for r in _sent(again)}
    assert after == before


def test_a_record_not_held_is_reported_missing_and_left_out(tmp_path: Path) -> None:
    recorder = Recorder(INSTANCE)
    seeded(recorder, {"EFFR": "INS-EFFR"})
    asyncio.run(rates(tmp_path, recorder).check())
    assert {r.meta.subjects[0].entity_id for r in _sent(recorder)} == {"INS-EFFR"}
    missing = recorder.on("ReportMissingInstrument")
    assert {m.identifiers[0].value for m in missing} == {
        "Daily Treasury Par Yield Curve Rates",
        "Daily Treasury Par Real Yield Curve Rates",
        "feds200628",
    }


def test_the_board_unreachable_is_said(tmp_path: Path) -> None:
    from fed_board.board import BoardUnreachable

    class Down:
        mode = "live"

        async def get(self, path: str, since: str = "") -> Fetched:
            raise BoardUnreachable(f"https://www.federalreserve.gov{path}: URLError")

    recorder = Recorder(INSTANCE)
    board = rates(tmp_path, recorder)
    board.board = Down()
    asyncio.run(board.check())
    assert not recorder.on("RecordRates")
    assert "URLError" in board.sources["fed_h15"].error
    assert H15_FILE in board.sources["fed_h15"].error
    assert ZERO_FILE in board.sources["fed_zero"].error


# ── Wants ───────────────────────────────────────────────────────────────


def _answered(tmp_path: Path, *heard: Heard) -> Recorder:  # type: ignore[type-arg]
    recorder = Recorder(INSTANCE)
    seeded(recorder)
    board = rates(tmp_path, recorder)

    async def run() -> None:
        for each in heard:
            await board.wants.hear(each, board.answer)

    asyncio.run(run())
    return recorder


def test_a_past_day_is_recorded_against_the_want(tmp_path: Path) -> None:
    recorder = _answered(tmp_path, _want("w-1", ["INS-PAR"], H15_DATASET, "2026-09-15"))
    sent = recorder.on("RecordRates")
    assert sent and {b.want_id for b in sent} == {"w-1"}
    rows = [r for b in sent for r in b.rates]
    assert {r.meta.business_date for r in rows} == {"2026-09-15"}
    assert len(rows) == 11 and {r.meta.subjects[0].entity_id for r in rows} == {"INS-PAR"}


def test_the_latest_is_the_files_last_day(tmp_path: Path) -> None:
    recorder = _answered(tmp_path, _want("w-2", ["INS-ZERO"], ZERO_DATASET))
    rows = _sent(recorder)
    assert {r.meta.business_date for r in rows} == {"2026-10-16"} and len(rows) == 30


def test_what_a_dataset_does_not_cover_is_declined(tmp_path: Path) -> None:
    recorder = _answered(
        tmp_path,
        _want("w-3", ["INS-ZERO", "LCL-USD"], H15_DATASET, "2026-10-21"),
        _want("w-4", ["INS-EFFR"], H15_DATASET, "2026-10-24"),
        _want("w-5", ["INS-EFFR"], H15_DATASET, "1950-01-03"),
    )
    declined = {
        (d.want_id, ops.UnansweredReason.Name(d.reason).removeprefix("UNANSWERED_REASON_").lower())
        for d in recorder.on("DeclineWant")
    }
    assert declined == {
        ("w-3", "not_covered"),
        ("w-4", "source_silent"),
        ("w-5", "beyond_history"),
    }


def test_the_raw_store_keeps_a_zip_as_received(tmp_path: Path) -> None:
    board = rates(tmp_path)
    body = asyncio.run(board.file("fed_h15"))
    assert body == _file("FRB_h15_xml.zip")
    assert RawStore(tmp_path).body(board.sources["fed_h15"].raw_key) == body
