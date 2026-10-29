from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from yomil.core.errors import ValidationError
from yomil.services import settings
from yomil.storage import settings as settings_repo

if TYPE_CHECKING:
    import sqlite3


def test_threshold_default_and_set(conn: sqlite3.Connection) -> None:
    assert settings.upcoming_threshold_days(conn) == 7
    settings.set_upcoming_threshold_days(conn, 3)
    assert settings.upcoming_threshold_days(conn) == 3


@pytest.mark.parametrize("bad", [-1, 366])
def test_threshold_rejects_out_of_range(conn: sqlite3.Connection, bad: int) -> None:
    with pytest.raises(ValidationError):
        settings.set_upcoming_threshold_days(conn, bad)


def test_threshold_falls_back_on_garbage(conn: sqlite3.Connection) -> None:
    settings_repo.put(conn, settings.UPCOMING_THRESHOLD_DAYS, "lots")
    assert settings.upcoming_threshold_days(conn) == 7


def test_list_font_size_default_set_and_clear(conn: sqlite3.Connection) -> None:
    assert settings.list_font_size(conn) is None
    settings.set_list_font_size(conn, 16)
    assert settings.list_font_size(conn) == 16
    settings.set_list_font_size(conn, None)
    assert settings.list_font_size(conn) is None


@pytest.mark.parametrize("bad", [5, 73])
def test_list_font_size_rejects_out_of_range(conn: sqlite3.Connection, bad: int) -> None:
    with pytest.raises(ValidationError):
        settings.set_list_font_size(conn, bad)


@pytest.mark.parametrize("garbage", ["huge", "500"])
def test_list_font_size_ignores_garbage(conn: sqlite3.Connection, garbage: str) -> None:
    settings_repo.put(conn, settings.LIST_FONT_SIZE, garbage)
    assert settings.list_font_size(conn) is None
