"""A rate as the lake's price: the price of one currency's cash instrument in
the other, as the Board quotes it, never inverted."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from meridian import ObservationMeta, Price
from meridian.plugin.v1 import operations_pb2 as ops

from fed_board.convert import Converted, codes, day_bounds, to_prices
from fed_board.release import parse

from conftest import DATASET, response

IDS = {code: f"LCL-{code}" for code in ("USD", "CHF", "EUR", "JPY", "GBP", "AUD", "NZD")}
RAW = ops.RawRecordRef(instance_id="fed-board", key="responses/2026-10/x.json.gz")


def converted(**kwargs: Any) -> Converted:
    return to_prices(
        parse(response("20261005")),
        kwargs.pop("ids", IDS),
        dataset=DATASET,
        raw=RAW,
        published_ns=1791231304 * 10**9,
        **kwargs,
    )


def meta(price: Price) -> ObservationMeta:
    assert price.meta is not None
    return price.meta


def by_key(prices: Sequence[Price]) -> dict[str, Price]:
    return {meta(p).row_key: p for p in prices if p.meta is not None}


def test_a_rate_per_dollar_is_the_dollar_priced_in_the_currency() -> None:
    franc = by_key(converted().prices)["CHF:2026-10-02"]
    assert [s.entity_id for s in meta(franc).subjects] == ["LCL-USD"]
    assert franc.price.currency_code == "CHF"
    assert franc.price.amount == Decimal("0.8293")


def test_a_rate_in_dollars_per_unit_is_the_currency_priced_in_dollars() -> None:
    euro = by_key(converted().prices)["EUR:2026-10-02"]
    assert [s.entity_id for s in meta(euro).subjects] == ["LCL-EUR"]
    assert euro.price.currency_code == "USD"
    assert euro.price.amount == Decimal("1.1259")


def test_every_price_is_a_close_for_its_business_date() -> None:
    prices = converted().prices
    assert {p.kind for p in prices} == {"close"}
    assert {p.basis for p in prices} == {"per_unit"}
    yen = by_key(prices)["JPY:2026-09-28"]
    assert meta(yen).business_date == date(2026, 9, 28)
    source = meta(yen).source
    assert source is not None and source.dataset == DATASET and not source.venue_id
    assert meta(yen).raw == RAW
    assert [(t.kind, t.at_ns) for t in meta(yen).source_times] == [
        ("published", 1791231304 * 10**9)
    ]


def test_the_declared_day_ends_at_noon_in_new_york() -> None:
    start, end = day_bounds(date(2026, 10, 2))
    assert datetime.fromtimestamp(end // 10**9, UTC) == datetime(2026, 10, 2, 16, 0, tzinfo=UTC)
    assert datetime.fromtimestamp(start // 10**9, UTC) == datetime(2026, 10, 1, 16, 0, tzinfo=UTC)
    franc = by_key(converted().prices)["CHF:2026-10-02"]
    assert (meta(franc).valid_from_ns, meta(franc).valid_until_ns) == (start, end)
    # In winter New York is five hours behind.
    _, winter = day_bounds(date(2026, 1, 2))
    assert datetime.fromtimestamp(winter // 10**9, UTC).hour == 17


def test_an_unresolved_subject_is_left_out_and_named() -> None:
    done = converted(ids={"USD": "LCL-USD"})
    assert "EUR" in done.unresolved and "GBP" in done.unresolved
    assert all(meta(p).subjects[0].entity_id == "LCL-USD" for p in done.prices)
    assert len(done.prices) == 19 * 5


def test_only_the_days_asked() -> None:
    done = converted(days=[date(2026, 9, 30)])
    assert {meta(p).business_date for p in done.prices} == {date(2026, 9, 30)}


def test_a_currency_the_plugin_cannot_name_is_not_converted() -> None:
    page = response("20261005").replace("SRI LANKA", "ATLANTIS")
    done = to_prices(parse(page), IDS, dataset=DATASET, raw=RAW, published_ns=0)
    assert done.unconverted == ("ATLANTIS RUPEE",)
    assert not any(key.startswith("LKR") for key in by_key(done.prices))
    assert not meta(by_key(done.prices)["CHF:2026-10-02"]).source_times


def test_the_codes_a_release_needs() -> None:
    needed = codes(parse(response("20261005")))
    assert needed[0] == "USD" and len(needed) == 24 and "VES" in needed
