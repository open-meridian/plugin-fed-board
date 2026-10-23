"""The plugin's work on its typed operations: a release pushed, subjects
resolved or reported, wants recorded against or declined."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.suites import Recorder

from fed_board.board import Fetched, release_days

from conftest import AT, feed, want


async def test_a_release_pushed_whole(tmp_path: Path) -> None:
    work = feed(tmp_path)
    done = await work.check()
    assert done is not None and done.recorded == 115
    recorder = work.plugin
    assert isinstance(recorder, Recorder)
    batches = recorder.on("RecordPrices")
    assert len(batches) == 1 and not batches[0].want_id
    assert len(recorder.on("ResolveIdentifier")) == 24
    assert (
        work.status.release is not None and work.status.release.released.isoformat() == "2026-10-05"
    )
    # The response kept first, and every row names it.
    key = work.status.release_key
    assert work.raw.read(key) is not None
    assert {p.meta.raw.key for p in batches[0].prices} == {key}


async def test_a_release_read_again_is_not_sent_again(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    assert await work.check() is None
    assert len(work.plugin.on("RecordPrices")) == 1


async def test_a_release_read_again_names_the_response_first_read(tmp_path: Path) -> None:
    first = feed(tmp_path)
    await first.check()
    # A restart: a new process, the same storage, the same release read again.
    again = feed(tmp_path, at=AT + timedelta(hours=1))
    await again.check()
    keys = [{p.meta.raw.key for p in w.plugin.on("RecordPrices")[0].prices} for w in (first, again)]
    assert keys[0] == keys[1] and len(keys[0]) == 1
    assert again.status.release_key != first.status.release_key
    assert len(again.raw.keys()) == 2


async def test_a_currency_that_resolves_to_two_records_is_reported(tmp_path: Path) -> None:
    recorder = Recorder("fed-board")
    count = {"n": 0}

    def resolved(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        count["n"] += 1
        if params.identifiers[0].value == "GBP":
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS)
        return ops.ResolveIdentifierResult(found=True, instrument_id=f"LCL-{count['n']}")

    recorder.answer("ResolveIdentifier", resolved)
    work = feed(tmp_path, recorder)
    done = await work.check()
    assert done is not None and done.unresolved == ("GBP",) and done.recorded == 110
    [missed] = recorder.on("ReportMissingInstrument")
    assert missed.reason == ops.MISS_REASON_AMBIGUOUS and missed.source == "fed-board"
    assert missed.identifiers[0].scheme == "iso4217" and missed.identifiers[0].value == "GBP"
    assert work.status.currencies["GBP"].miss == "ambiguous"
    prices = recorder.on("RecordPrices")[0].prices
    assert len(prices) == 110 and not any(p.meta.row_key.startswith("GBP") for p in prices)
    # Not marked recorded: the next check tries again.
    assert await work.check() is not None


async def test_a_past_week_wanted_is_recorded_against_the_want(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    usd = work.status.currencies["USD"].instrument_id
    await work.on_want(want("w-1", [usd], day="2026-09-25"))
    batch = work.plugin.on("RecordPrices")[-1]
    assert batch.want_id == "w-1"
    assert {p.meta.business_date for p in batch.prices} == {"2026-09-25"}
    assert {p.meta.subjects[0].entity_id for p in batch.prices} == {usd}
    assert len(batch.prices) == 19
    assert work.status.wants[0].recorded == 19


async def test_a_currency_quoted_per_dollar_is_declined_not_covered(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    chf = work.status.currencies["CHF"].instrument_id
    eur = work.status.currencies["EUR"].instrument_id
    await work.on_want(want("w-2", [chf, eur, "LCL-elsewhere"], day="2026-10-02"))
    [declined] = work.plugin.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_NOT_COVERED
    assert [s.entity_id for s in declined.subjects] == [chf, "LCL-elsewhere"]
    batch = work.plugin.on("RecordPrices")[-1]
    assert batch.want_id == "w-2" and [p.meta.row_key for p in batch.prices] == ["EUR:2026-10-02"]


async def test_a_week_not_published_yet_is_declined_silent(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    usd = work.status.currencies["USD"].instrument_id
    await work.on_want(want("w-3", [usd], day="2026-10-08"))
    [declined] = work.plugin.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_SOURCE_SILENT


async def test_a_day_past_the_history_is_declined(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    usd = work.status.currencies["USD"].instrument_id
    await work.on_want(want("w-4", [usd], day="2001-01-08"))
    [declined] = work.plugin.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_BEYOND_HISTORY


async def test_a_kind_or_a_type_not_served_is_declined(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    usd = work.status.currencies["USD"].instrument_id
    await work.on_want(want("w-5", [usd], day="2026-10-02", kinds=(ops.PRICE_KIND_NAV,)))
    await work.on_want(want("w-6", [usd], day="2026-10-02", data_type="meridian.v1.Bar"))
    reasons = [d.reason for d in work.plugin.on("DeclineWant")]
    assert reasons == [ops.UNANSWERED_REASON_NOT_COVERED] * 2


async def test_another_dataset_is_not_this_plugins(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.on_want(want("w-7", ["LCL-1"], dataset="other:daily"))
    assert not work.plugin.on("DeclineWant") and not work.status.wants


async def test_a_standing_want_is_kept_until_withdrawn(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    eur = work.status.currencies["EUR"].instrument_id
    await work.on_want(want("w-8", [eur], standing=True))
    assert "w-8" in work.status.standing
    from meridian.receive import Heard

    await work.on_withdrawn(
        Heard(
            row="WantWithdrawn",
            message=ops.WantWithdrawnEvent(want_id="w-8", dataset="fed-board:daily"),
        )
    )
    assert "w-8" not in work.status.standing


async def test_the_board_unreachable_is_said(tmp_path: Path) -> None:
    from fed_board.board import BoardUnreachable

    class Offline:
        mode = "live"

        async def get(self, path: str, since: str = "") -> Fetched:
            raise BoardUnreachable(f"https://www.federalreserve.gov{path}: ConnectionRefusedError")

    work = feed(tmp_path)
    work.board = Offline()
    assert await work.check() is None
    assert "ConnectionRefusedError" in work.status.error
    assert not work.plugin.on("RecordPrices")


def test_the_release_holding_a_day() -> None:
    from datetime import date

    assert release_days(date(2026, 10, 2))[0] == date(2026, 10, 5)
    assert release_days(date(2026, 9, 28))[0] == date(2026, 10, 5)
    # Labor Day: the week of 31 August came out on Tuesday 8 September.
    assert date(2026, 9, 8) in release_days(date(2026, 9, 4))
    assert AT.date() == date(2026, 10, 10)


async def test_each_currency_is_resolved_as_of_now(tmp_path: Path) -> None:
    """Said, never left out: an as-of left out is the epoch, which no window
    the deployment keeps from a date covers (2026-10-10, USD minted beside
    the currency's record)."""
    recorder = Recorder("fed-board")
    asked: list[int] = []

    def resolved(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        asked.append(params.as_of_ns)
        return ops.ResolveIdentifierResult(found=True, instrument_id=f"LCL-{len(asked)}")

    recorder.answer("ResolveIdentifier", resolved)
    await feed(tmp_path, recorder).check()
    assert asked and set(asked) == {int(AT.timestamp() * 1_000_000_000)}


async def test_a_currency_comes_from_the_master_through_core(tmp_path: Path) -> None:
    """Contract v20: the plugin asks for each currency by its ISO 4217 code
    alone, as of now, and takes the record core answers -- the platform
    master's, pulled -- never defining one itself; a code core cannot answer
    is reported missing, also as of now, and its rates wait."""
    recorder = Recorder("fed-board")
    now = int(AT.timestamp() * 1_000_000_000)

    def resolved(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        (identifier,) = params.identifiers
        assert identifier.scheme == "iso4217" and params.as_of_ns == now
        if identifier.value == "KRW":
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)
        return ops.ResolveIdentifierResult(found=True, instrument_id=f"INS-{identifier.value}")

    recorder.answer("ResolveIdentifier", resolved)
    work = feed(tmp_path, recorder)
    await work.check()
    (missing,) = recorder.on("ReportMissingInstrument")
    assert missing.as_of_ns == now and missing.identifiers[0].value == "KRW"
    assert work.status.currencies["USD"].instrument_id == "INS-USD"
    rows = {sent.row for sent in recorder.sent}
    assert rows <= {"ResolveIdentifier", "ReportMissingInstrument", "RecordPrices"}, rows


# ── The first run's backfill ────────────────────────────────────────────


def test_the_first_run_backfills_dailys_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each past week back to the declared history, newest first, noted in
    storage so a later run never does it again (rulings 348 and 349)."""
    from fed_board import feed as feed_module

    monkeypatch.setattr(feed_module, "HISTORY", 21)
    work = feed(tmp_path)
    recorder = work.plugin
    assert isinstance(recorder, Recorder)
    asyncio.run(work.check())
    before = len(recorder.on("RecordPrices"))
    sent = asyncio.run(work.backfill())
    # The week of 21 September, released on the 28th, recorded; the week
    # before it is past the history.
    assert sent == 115
    days = {p.meta.business_date for b in recorder.on("RecordPrices")[before:] for p in b.prices}
    assert days == {"2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"}
    assert work.status.backfill_done
    assert asyncio.run(feed(tmp_path, recorder).backfill()) == 0


def test_a_backfill_the_board_stops_answering_carries_on_later(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fed_board import feed as feed_module
    from fed_board.board import BoardUnreachable

    monkeypatch.setattr(feed_module, "HISTORY", 21)
    work = feed(tmp_path)
    asyncio.run(work.check())
    held = work.board

    class Down:
        mode = "live"

        async def get(self, path: str, since: str = "") -> Fetched:
            raise BoardUnreachable(f"https://www.federalreserve.gov{path}: URLError")

    work.board = Down()
    assert asyncio.run(work.backfill()) == 0
    assert not work.status.backfill_done
    work.board = held
    assert asyncio.run(work.backfill()) == 115
    assert work.status.backfill_done
