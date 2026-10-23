"""Shared stand-ins: the Board's recorded responses, a fixed clock, and the
lake's wants as the sidecar delivers them; for the rates, a deployment
holding every record the platform seeds."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles import data
from meridian.suites import Recorder

from fed_board.board import SyntheticBoard
from fed_board.declared import CATALOGUE
from fed_board.feed import Feed
from fed_board.rates_feed import Rates
from fed_board.raw import RawStore

#: When the responses were recorded, and the clock the tests run at.
AT = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
INSTANCE = "fed-board"
DATASET = f"{INSTANCE}:daily"
H15_DATASET = f"{INSTANCE}:fed_h15"
ZERO_DATASET = f"{INSTANCE}:fed_zero"
#: When the H.15 and zero curve files were recorded: the rates' clock.
AT_RATES = datetime(2026, 10, 23, 17, 0, tzinfo=UTC)
#: The records the platform seeds, as the deployment answers them here.
SEEDED = {
    "EFFR": "INS-EFFR",
    "Daily Treasury Par Yield Curve Rates": "INS-PAR",
    "Daily Treasury Par Real Yield Curve Rates": "INS-REAL",
    "feds200628": "INS-ZERO",
}


def seeded(recorder: Recorder, held: dict[str, str] | None = None) -> None:
    """The deployment answering each seeded record by its symbol, and an
    ISO code with its cash instrument, `LCL-<code>`."""
    found = SEEDED if held is None else held

    def answer(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        named = params.identifiers[0]
        if named.scheme == "iso4217":
            return ops.ResolveIdentifierResult(found=True, instrument_id=f"LCL-{named.value}")
        if named.value in found:
            return ops.ResolveIdentifierResult(found=True, instrument_id=found[named.value])
        return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)

    recorder.answer("ResolveIdentifier", answer)


def rates(tmp: Path, plugin: Recorder | None = None, at: datetime = AT_RATES) -> Rates:
    """The plugin's rates on the suite's recorder and the recorded files."""
    held = plugin or Recorder(INSTANCE)
    wants = data.Wants(held, keys=tuple(e.key for e in CATALOGUE))
    return Rates(held, SyntheticBoard(lambda: at), RawStore(tmp), wants, now=lambda: at)


def response(name: str) -> str:
    """A recorded response's page, by its file's name under responses/."""
    held = resources.files("fed_board").joinpath("responses", f"{name}.htm.gz")
    return gzip.decompress(held.read_bytes()).decode()


def feed(tmp: Path, plugin: Recorder | None = None, at: datetime = AT) -> Feed:
    """The plugin's work on the suite's recorder and the recorded responses,
    at `at`."""
    return Feed(
        plugin or Recorder(INSTANCE), SyntheticBoard(lambda: at), RawStore(tmp), now=lambda: at
    )


def want(
    want_id: str,
    subjects: list[str],
    *,
    day: str = "",
    standing: bool = False,
    kinds: tuple[Any, ...] = (ops.PRICE_KIND_CLOSE,),
    data_type: str = "meridian.v1.Price",
    dataset: str = DATASET,
) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=dataset,
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            kinds=list(kinds),
            business_date=day,
            standing=standing,
        ),
    )
