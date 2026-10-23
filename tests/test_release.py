"""The Board's weekly release, read from the real responses committed."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from fed_board.release import NotARelease, last_modified_ns, parse, released_on

from conftest import response


def test_the_release_of_5_october_2026() -> None:
    release = parse(response("20261005"))
    assert release.released == date(2026, 10, 5)
    assert release.days == tuple(date(2026, d // 100, d % 100) for d in (928, 929, 930, 1001, 1002))
    assert len(release.currencies) == 23
    assert len(release.rates) == 23 * 5
    assert not release.no_data


def test_each_rate_exactly_as_printed() -> None:
    rates = {(r.currency, r.country, r.day): r for r in parse(response("20261005")).rates}
    franc = rates[("FRANC", "SWITZERLAND", date(2026, 10, 2))]
    assert franc.value == Decimal("0.8293") and franc.text == "0.8293" and franc.per_dollar
    won = rates[("WON", "SOUTH KOREA", date(2026, 9, 28))]
    assert won.value == Decimal("1359.7800") and str(won.value) == "1359.7800"
    bolivar = rates[("BOLIVAR", "VENEZUELA", date(2026, 10, 2))]
    assert bolivar.value == Decimal("864.3948")


def test_the_asterisk_says_dollars_per_unit() -> None:
    quoted = {country: per for country, _, per in parse(response("20261005")).currencies}
    assert [c for c, per in quoted.items() if not per] == [
        "AUSTRALIA",
        "EMU MEMBERS",
        "NEW ZEALAND",
        "UNITED KINGDOM",
    ]
    euro = [r for r in parse(response("20261005")).rates if r.country == "EMU MEMBERS"]
    assert euro[-1].value == Decimal("1.1259") and not euro[-1].per_dollar


def test_the_indexes_are_not_rates() -> None:
    release = parse(response("20261005"))
    assert not any("BROAD" in r.country or "JAN06" in r.currency for r in release.rates)
    assert any("BROAD" in line for line in release.memo)


def test_a_january_release_holds_last_december() -> None:
    release = parse(response("20260105"))
    assert release.released == date(2026, 1, 5)
    assert release.days[0] == date(2025, 12, 29) and release.days[-1] == date(2026, 1, 2)
    # New Year's Day: no rate, never a zero.
    assert ("AUSTRALIA", "DOLLAR", date(2026, 1, 1)) in release.no_data
    assert not any(r.day == date(2026, 1, 1) for r in release.rates)


def test_the_week_before() -> None:
    release = parse(response("20260928"))
    assert release.released == date(2026, 9, 28)
    assert release.days[-1] == date(2026, 9, 25)


def test_a_page_that_is_no_release_is_refused() -> None:
    with pytest.raises(NotARelease, match="release date"):
        parse(response("20260907"))
    with pytest.raises(NotARelease, match="no table"):
        parse("<div class='dates'>Release Date: October 5, 2026</div><p>nothing</p>")


def test_a_rate_that_is_no_number_is_refused() -> None:
    page = re.sub(r">\s*0\.8322<", ">0,8322<", response("20261005"), count=1)
    with pytest.raises(NotARelease, match="not a number"):
        parse(page)


def test_dates_and_the_last_modified_header() -> None:
    assert released_on("Release Date: Monday, October 05, 2026") == date(2026, 10, 5)
    assert last_modified_ns("Mon, 05 Oct 2026 20:15:04 GMT") == 1791231304 * 10**9
    assert last_modified_ns("") == 0
