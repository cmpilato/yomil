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
