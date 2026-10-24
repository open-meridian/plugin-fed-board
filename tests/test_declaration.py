"""The catalogue, from code, as the deployment approves it."""

from __future__ import annotations

from fed_board.declaration import DECLARATION
from fed_board.declared import DAILY_DATASET, H15_DATASET, ZERO_DATASET, mode_name


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
        licence = entry.licence_default
        assert licence is not None and licence.kept and licence.display
        assert licence.derived_use_terms == "not_restricted" and not licence.personal_use
    assert H15_DATASET.cadence == 86_400 and H15_DATASET.history == 26_412
    assert ZERO_DATASET.cadence == 7 * 86_400 and ZERO_DATASET.history == 23_872


def test_public_domain_is_not_one_persons_terms() -> None:
    licence = DAILY_DATASET.licence_default
    assert licence is not None
    assert licence.kept and licence.derived_use and licence.display
    assert not licence.personal_use and licence.retention_days == 0


def test_the_responses_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]


def test_no_attribution_field_until_core_accepts_it() -> None:
    """Core v27 refuses a catalogue carrying SDK 0.32.2's data-terms fields
    at registration, so none is set yet; the citation is on the page."""
    for entry in DECLARATION.catalogue:
        licence = entry.licence_default
        assert licence is not None
        assert not licence.redistribution and not licence.copyright_class
        assert not licence.attribution_required and not licence.attribution_text
