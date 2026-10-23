"""The typed records the pages answer, for a person's page and an agent's
tool alike (contract v12; spec/a-deployment-serves-its-mcp): the data role's
common records (`meridian.roles.data`, spec/plugin-pages-follow-their-role),
each extended with the Board's own fields. The Connection tab is
`read_connection`, the Datasets tab `read_datasets`, each answering what its
page shows, as data, under the role's names.

A data plugin's pages show its connection and its datasets, never a price
(plans/the-lake-prices-the-book, ruled 2026-10-03): prices are the reading
roles'. So neither record holds a rate; each says how the Board was reached
and what the plugin serves of it.

From 1.0.0 the Board has three sources -- H.10's weekly release, H.15's file
and the zero curve's -- each a line under Connection's "Sources"
(spec/a-public-rates-and-filings-data-plugin, section 5); and Datasets has
the vendor tabs that spec names: "Records", each rate and curve and its
`INS-`, or why none, and "Lag", published minus valid per dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from meridian.roles import data


@dataclass(frozen=True)
class SourceRead:
    """One of the Board's sources, as Connection's "Sources" lists it: its
    state, the latest it published, the next expected, the calls made and
    the last error."""

    source: str
    dataset: str
    state: str
    latest: str
    published_at: str
    next_expected: str
    calls: int
    last_error: str


@dataclass(frozen=True)
class ConnectionRead(data.ConnectionRead):
    """Connection's common fields, then H.10's: the head's status and what it
    means, the source read, the last check, the release calendar -- the
    latest release, its first and last day, when the Board published it, the
    next expected -- and the responses kept."""

    #: The head's status: `ok`, `busy`, `warn` or `error`, and what it means.
    state: str = ""
    said: str = ""
    source: str = ""
    checked_at: str = ""
    latest_release: str = ""
    first_day: str = ""
    last_day: str = ""
    #: When the Board's server says the latest release's page was last
    #: modified, ISO 8601: its publication.
    published_at: str = ""
    #: The next release expected: the Monday after the latest's last day, at
    #: 16:15 New York, or the next business day.
    next_release: str = ""
    responses_kept: int = 0
    kept_for: str = ""
    #: Each source, one line (`SourceRead`).
    sources: list[SourceRead] = field(default_factory=list)
    #: H.10's first-run backfill: done, under way or not started, and how
    #: far back it has read.
    backfill: str = ""


@dataclass(frozen=True)
class Served(data.Served):
    """The one dataset as "Served" shows it, then H.10's: its cadence, its
    history in days, its venue (none: the New York Fed's certified rates),
    and what it restated and kept unchanged since the plugin started."""

    cadence: str = ""
    history_days: int = 0
    venue: str = ""
    restated: int = 0
    unchanged: int = 0


@dataclass(frozen=True)
class Want(data.Want):
    """One want as "Wants" shows it, then H.10's: its ID, when, whether it
    stands, and what it declined, by reason."""

    want_id: str = ""
    at: str = ""
    standing: bool = False
    declined_as: str = ""


@dataclass(frozen=True)
class CurrencyRead:
    """One currency H.10 publishes: how the Board names and quotes it, what
    its rate is a price of, and the deployment's instrument resolved for its
    subject, or why there is none."""

    code: str
    board_name: str
    quoted: str
    price_of: str
    instrument_id: str
    miss: str


@dataclass(frozen=True)
class RecordRead:
    """One record the rates are recorded against, as "Records" lists it: the
    dataset, the Board's series, the record by its identifiers, what each row
    is, and the deployment's instrument for it, or why there is none -- a
    record the deployment does not hold, or one only proposed."""

    dataset: str
    series: str
    record: str
    rows: str
    instrument_id: str
    why_none: str


@dataclass(frozen=True)
class LagRead:
    """One dataset's lag, as "Lag" lists it: of the rows recorded since the
    plugin started, the median and the longest time from the end of a row's
    day to when the Board published it."""

    dataset: str
    rows: int
    median: str
    longest: str


@dataclass(frozen=True)
class DatasetsRead(data.DatasetsRead):
    """Datasets' common fields, then the Board's: each currency H.10
    publishes, and the Board's rows it could not name; each record the rates
    are recorded against; each dataset's lag; and the citation the Board's
    terms ask for. Its rows are the Board's, each extending the role's."""

    served: list[Served] = field(default_factory=list)  # type: ignore[assignment]
    wants: list[Want] = field(default_factory=list)  # type: ignore[assignment]
    currencies: list[CurrencyRead] = field(default_factory=list)
    #: The Board's rows the plugin could not name, each with how often seen.
    unconverted: list[str] = field(default_factory=list)
    records: list[RecordRead] = field(default_factory=list)
    lag: list[LagRead] = field(default_factory=list)
    attribution: str = ""
