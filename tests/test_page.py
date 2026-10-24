"""The two pages under Manage, and their read tools: what each shows, to
whom, and that a tool answers what its page shows."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from meridian.suites import Recorder
from meridian.testing import PageClient

from fed_board import page as page_module
from fed_board.page import CONNECTION, DATASETS, hold, pages

from conftest import INSTANCE, feed, rates, seeded, want


@pytest.fixture
def client(tmp_path: Path) -> PageClient:
    recorder = Recorder(INSTANCE)
    seeded(recorder, {"EFFR": "INS-EFFR", "feds200628": "INS-ZERO"})
    work = feed(tmp_path, recorder)
    board = rates(tmp_path, recorder)

    async def run() -> None:
        await work.check()
        await board.check()
        usd = work.status.currencies["USD"].instrument_id
        await work.on_want(want("w-0925", [usd], day="2026-09-25"))
        await work.on_want(want("w-standing", [usd], standing=True))

    asyncio.run(run())
    hold(work, board)
    return PageClient(pages)


def test_each_page_is_managed_alone(client: PageClient) -> None:
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert served == {
        (CONNECTION, "admin"): 200,
        (CONNECTION, "write"): 403,
        (CONNECTION, "read"): 403,
        (DATASETS, "admin"): 200,
        (DATASETS, "write"): 403,
        (DATASETS, "read"): 403,
    }
    # No rate on any page: the Board's figures are the reading roles' to show.
    client.assert_no_account_data("0.8293", "1.1259", "1359.7800")


def test_connection_says_how_the_board_is_reached(client: PageClient) -> None:
    text = client.get(CONNECTION, "admin").text
    # The data role's sections, in its order; the Board's sources a tab.
    assert 'aria-label="Connection sections"' in text
    assert text.index("<h2>Key</h2>") < text.index("<h2>Limits and use</h2>")
    assert "<h2>Stream</h2>" in text and "<h2>Sources</h2>" not in text
    assert 'state="ok"' in text and "Sample data" in text
    assert "No key needed" in text and "Does not stream" in text
    assert "US government work" in text
    text = client.get(CONNECTION, "admin", tab="sources").text
    assert "<h2>Sources</h2>" in text and "<h2>Key</h2>" not in text
    assert text.count("<tr data-source=") == 3
    assert "H.10's backfill: Not run on sample data." in text
    assert "Mon 05 Oct" in text  # H.10's latest release
    assert "Mon 12 Oct" in text  # the next one expected
    assert "Wed 21 Oct" in text  # H.15's latest day
    assert "Fri 16 Oct" in text  # the zero curve's
    assert 'href="/.meridian/ui/0.12.0/meridian.css"' in text


def test_datasets_lists_the_datasets_in_tabs(client: PageClient) -> None:
    text = client.get(DATASETS, "admin").text
    assert 'aria-label="Datasets sections"' in text
    assert text.index("<h2>Served</h2>") < text.index("<h2>Wants</h2>")
    for dataset in ("fed-board:daily", "fed-board:fed_h15", "fed-board:fed_zero"):
        assert f"<code>{dataset}</code>" in text
    assert "kept; public domain" in text and "kept; US government work" in text
    assert "Not licensed yet" in text
    assert "Kept current" in text and "2026-09-25" in text
    # Each tab draws its own.
    assert "<tr data-code=" not in text
    currencies = client.get(DATASETS, "admin", tab="currencies").text
    assert currencies.count("<tr data-code=") == 24 and "<om-pager>" in currencies
    held = client.get(DATASETS, "admin", tab="records").text
    assert "<h2>Records</h2>" in held and "INS-EFFR" in held and "INS-ZERO" in held
    assert "reported missing" in held and "frb: Bank prime loan rate" in held
    lag = client.get(DATASETS, "admin", tab="lag").text
    assert "<h2>Lag</h2>" in lag and "Board of Governors of the Federal Reserve System" in lag
    # No rate: prices and rates are the reading roles' to show.
    for page in (text, currencies, held, lag):
        assert "0.8293" not in page and "1.1259" not in page and "5.13" not in page


def test_the_tools_answer_what_the_pages_show(client: PageClient) -> None:
    names = {t.name for t in pages.tools}
    assert names == {"read_connection", "read_datasets"}
    connection = client.call_tool("read_connection")
    assert connection.outcome == "unchanged", connection.json
    assert [s["dataset"].split(":")[1] for s in connection.data["sources"]] == [
        "daily",
        "fed_h15",
        "fed_zero",
    ]
    assert [s["latest"] for s in connection.data["sources"]] == [
        "2026-10-05",
        "2026-10-21",
        "2026-10-16",
    ]
    assert connection.data["latest_release"] == "2026-10-05"
    assert connection.data["first_day"] == "2026-09-28"
    assert connection.data["mode"] == "Sample data" and connection.data["credentials"] == []
    assert connection.data["sessions"] is None
    assert connection.data["next_release"] == "2026-10-12"
    assert connection.data["published_at"] == "2026-10-05T20:15:04+00:00"
    datasets = client.call_tool("read_datasets")
    assert datasets.outcome == "unchanged"
    data = datasets.data
    served, h15, curve = data["served"]
    assert served["dataset"] == "fed-board:daily" and served["arrives"] == "push, pull"
    assert served["recorded"] >= 19 and served["licensed"] is False
    assert h15["dataset"] == "fed-board:fed_h15" and h15["cadence"] == "daily"
    assert curve["dataset"] == "fed-board:fed_zero" and curve["cadence"] == "weekly"
    held = {r["record"]: r for r in data["records"]}
    assert held["nyfed: EFFR"]["instrument_id"] == "INS-EFFR"
    assert held["frb: feds200628"]["instrument_id"] == "INS-ZERO"
    par = held["ustreasury: Daily Treasury Par Yield Curve Rates"]
    assert par["instrument_id"] == "" and "reported missing" in par["why_none"]
    assert len(data["records"]) == 10
    assert held["frb: Treasury bills secondary market"]["rows"].startswith(
        "discount, discount basis"
    )
    assert [lag["dataset"] for lag in data["lag"]][1:] == [
        "fed-board:fed_h15",
        "fed-board:fed_zero",
    ]
    assert data["attribution"] == "Source: Board of Governors of the Federal Reserve System"
    codes = [c["code"] for c in data["currencies"]]
    assert codes[0] == "USD" and len(codes) == 24
    euro = next(c for c in data["currencies"] if c["code"] == "EUR")
    assert euro["quoted"] == "US dollars per EUR" and euro["price_of"] == "EUR in USD"
    page = client.get(DATASETS, "admin", tab="currencies").text
    assert all(c["instrument_id"] in page for c in data["currencies"])
    held_page = client.get(DATASETS, "admin", tab="records").text
    assert all(r["record"] in held_page for r in data["records"])
    assert [w["want_id"] for w in data["wants"]][0] == "w-standing"
    assert data["wants"][0]["state"] == "Kept current"


def test_before_the_first_check(tmp_path: Path) -> None:
    page_module._held.clear()
    text = PageClient(pages).get(CONNECTION, "admin").text
    assert "Checking the Board" in text
    empty = PageClient(pages).get(DATASETS, "admin", tab="currencies").text
    assert "No release read yet" in empty


def test_the_board_not_reached(tmp_path: Path) -> None:
    work = feed(tmp_path)
    work.status.error = (
        "https://www.federalreserve.gov/releases/h10/current/default.htm: ConnectionRefusedError"
    )
    hold(work)
    text = PageClient(pages).get(CONNECTION, "admin").text
    assert 'state="error"' in text and "Not answering" in text
    assert "ConnectionRefusedError" in text
    sources = PageClient(pages).get(CONNECTION, "admin", tab="sources").text
    assert "ConnectionRefusedError" in sources and "Not answering" in sources


def test_the_currencies_are_searched(client: PageClient) -> None:
    text = client.get(DATASETS, "admin", q="dollar").text
    assert 'type="search"' in text and 'value="dollar"' in text
    codes = {
        c for c in ("AUD", "CAD", "HKD", "NZD", "SGD", "TWD", "USD") if f'data-code="{c}"' in text
    }
    assert codes == {"AUD", "CAD", "HKD", "NZD", "SGD", "TWD", "USD"}
    assert 'data-code="CHF"' not in text and "7 of 24" in text
    nothing = client.get(DATASETS, "admin", q="drachma").text
    assert "No currency matches" in nothing and "0 of 24" in nothing
    # The tool answers every currency, whatever a browser searched.
    assert len(client.call_tool("read_datasets").data["currencies"]) == 24


def test_a_licensed_dataset_is_said_so(client: PageClient) -> None:
    licensed = frozenset({"fed-board:daily", "fed-board:fed_zero"})
    page_module._held["feed"].status.licensed = licensed
    page_module._held["rates"].wants.licensed = licensed
    served = client.call_tool("read_datasets").data["served"]
    assert [s["licensed"] for s in served] == [True, False, True]


def test_the_figures_are_the_data_roles_in_its_order(client: PageClient) -> None:
    from fed_board.page import figures

    work = page_module._held["feed"]
    said = figures(work.status, work, page_module._held["rates"])
    assert [f.label for f in said] == [
        "Connection",
        "Entitled at the vendor",
        "Stream",
        "Last recorded",
    ]
    assert said[0].value == "Sample data" and said[2].value == "Does not stream"
    assert said[1].value == "3 of 3 datasets"
