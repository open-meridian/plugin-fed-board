"""The catalogue, from code, as the deployment approves it."""

from __future__ import annotations

from fed_board.declaration import DECLARATION
from fed_board.declared import (
    ATTRIBUTION,
    DAILY_DATASET,
    H10_TERMS,
    H15_DATASET,
    H15_TERMS,
    ZERO_DATASET,
    ZERO_TERMS,
    mode_name,
)


def test_three_datasets_h10_as_it_was() -> None:
    assert [d.key for d in DECLARATION.catalogue] == ["daily", "fed_h15", "fed_zero"]
    assert list(DAILY_DATASET.data_types) == ["meridian.v1.Price"]
    assert [mode_name(m) for m in DAILY_DATASET.modes] == ["push", "pull"]
    assert DAILY_DATASET.day_time_zone == "America/New_York"
    assert DAILY_DATASET.day_end_minute == 720
    assert DAILY_DATASET.cadence == 7 * 86_400 and DAILY_DATASET.history == 3650
    assert not DAILY_DATASET.venue_id


def test_the_rates_datasets() -> None:
    for entry in (H15_DATASET, ZERO_DATASET):
        assert list(entry.data_types) == ["meridian.v1.Rate"]
        assert [mode_name(m) for m in entry.modes] == ["push", "pull"]
        assert entry.day_time_zone == "America/New_York" and entry.day_end_minute == 0
        assert not entry.venue_id and not entry.calendar_id
        assert entry.gap_recovery == "backfill", "the Board's files hold every past day"
    assert H15_DATASET.cadence == 86_400 and H15_DATASET.history == 26_412
    assert ZERO_DATASET.cadence == 7 * 86_400 and ZERO_DATASET.history == 23_872


def test_the_boards_terms_in_words_and_a_gap_asked_again() -> None:
    # Contract 30 (ruling 1032): the Board's terms described, no licence.
    assert DAILY_DATASET.terms_and_pricing == H10_TERMS
    assert (H15_DATASET.terms_and_pricing, ZERO_DATASET.terms_and_pricing) == (
        H15_TERMS,
        ZERO_TERMS,
    )
    for entry in DECLARATION.catalogue:
        said = entry.terms_and_pricing
        assert "public domain" in said and ATTRIBUTION in said and len(said) <= 2000
        assert entry.gap_recovery == "backfill" and not entry.sessions_calendar_id


def test_the_responses_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
