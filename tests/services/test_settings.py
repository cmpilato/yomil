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


def test_font_size_default_set_and_clear(conn: sqlite3.Connection) -> None:
    assert settings.font_size(conn) is None
    settings.set_font_size(conn, 16)
    assert settings.font_size(conn) == 16
    settings.set_font_size(conn, None)
    assert settings.font_size(conn) is None


@pytest.mark.parametrize("bad", [settings.MIN_FONT_SIZE - 1, settings.MAX_FONT_SIZE + 1])
def test_font_size_rejects_out_of_range(conn: sqlite3.Connection, bad: int) -> None:
    with pytest.raises(ValidationError):
        settings.set_font_size(conn, bad)


@pytest.mark.parametrize("garbage", ["huge", "500"])
def test_font_size_ignores_garbage(conn: sqlite3.Connection, garbage: str) -> None:
    settings_repo.put(conn, settings.FONT_SIZE, garbage)
    assert settings.font_size(conn) is None


def test_save_preferences(conn: sqlite3.Connection) -> None:
    settings.save_preferences(conn, font_size=20, upcoming_threshold_days=10)
    assert settings.font_size(conn) == 20
    assert settings.upcoming_threshold_days(conn) == 10
    settings.save_preferences(conn, font_size=None, upcoming_threshold_days=10)
    assert settings.font_size(conn) is None


def test_save_preferences_is_all_or_nothing(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValidationError):
        settings.save_preferences(conn, font_size=20, upcoming_threshold_days=-1)
    assert settings.font_size(conn) is None
