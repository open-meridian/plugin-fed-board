"""The Board's responses kept as received, and moved past their window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from meridian import edge

from fed_board.__main__ import Lake
from fed_board.board import Fetched, board
from fed_board.raw import RawStore, page_name

from conftest import AT


def fetched(at: datetime, path: str = "/releases/h10/current/default.htm") -> Fetched:
    return Fetched(
        path, 200, b"<html>H.10</html>", at, last_modified="Mon, 05 Oct 2026 20:15:04 GMT"
    )


def test_a_response_kept_and_read_back(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    key = store.keep(fetched(AT))
    assert key == "responses/2026-10/20261010T110000000000Z-current.json.gz"
    kept = store.read(key)
    assert kept is not None and kept["body"] == "<html>H.10</html>" and kept["status"] == 200
    assert kept["url"] == "https://www.federalreserve.gov/releases/h10/current/default.htm"
    assert store.read("../outside.json.gz") is None
    assert page_name("/releases/h10/20260928/default.htm") == "20260928"


class Mover:
    def __init__(self) -> None:
        self.moved: list[tuple[str, str, int]] = []
        self.stored: list[Any] = []

    async def archive_unit(self, kind: str, unit: str, **span: int) -> None:
        self.moved.append(("archived", unit, span["record_count"]))

    async def delete_unit(self, kind: str, unit: str, **span: int) -> None:
        self.moved.append(("deleted", unit, span["record_count"]))


async def test_months_past_the_window_moved_as_the_setting_says(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.keep(fetched(AT - timedelta(days=400)))
    store.keep(fetched(AT - timedelta(days=399)))
    store.keep(fetched(AT))
    mover = Mover()
    done = await store.tend(mover, 365, "archived", AT)  # type: ignore[arg-type]
    assert done["archived"] == 1
    assert mover.moved == [("archived", "responses/2025-09", 2)]
    kept = await store.tend(mover, 365, "kept", AT)  # type: ignore[arg-type]
    assert kept["kept"] == 1
    assert mover.stored[0].record_count == 3


async def test_nothing_moved_without_granted_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_STORAGE_DIR", raising=False)
    store = RawStore(None)
    store.keep(fetched(datetime(2020, 1, 1, tzinfo=UTC)))
    mover = Mover()
    assert (await store.tend(mover, 1, "deleted", AT))["deleted"] == 0  # type: ignore[arg-type]
    assert mover.moved == []


async def test_storage_read_once_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On an instance run as shards, storage is read once the plugin has
    registered, from the class's on_start: its shard's own folder, read
    afresh when it registers again (open-meridian 0.37.0). Built before
    Register, as `main()` builds it, nothing is read: read then, it raises."""
    monkeypatch.setenv("MERIDIAN_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MERIDIAN_PLUGIN_SHARDS", "2")
    monkeypatch.setattr(edge, "_serving", None)
    lake = Lake(board(False), RawStore())
    monkeypatch.setattr(edge, "_serving", (1, 2))
    await lake.on_start()
    assert lake.feed.raw.granted
    assert lake.feed.raw.root == tmp_path / "shard-1"
    await lake.on_stop()
    monkeypatch.setattr(edge, "_serving", (0, 2))
    await lake.on_start()
    assert lake.feed.raw.root == tmp_path / "shard-0"
