from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import pytest

from yomil.core.models import Series
from yomil.core.recurrence import monthly_on_day
from yomil.storage import db

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
TODAY = date(2026, 3, 1)  # a Sunday


def make_series(**overrides: Any) -> Series:
    """An unsaved monthly bill due on the 15th, starting 2026-01-15."""
    fields: dict[str, Any] = {
        "id": None,
        "payee": "Electric",
        "rrule": monthly_on_day(15),
        "dtstart": date(2026, 1, 15),
        "expected_amount_cents": 10_000,
    }
    fields.update(overrides)
    return Series(**fields)


def open_db() -> sqlite3.Connection:
    conn = db.connect(":memory:")
    db.migrate(conn)
    return conn


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """A migrated in-memory database. Fails the test if a transaction is left open."""
    c = open_db()
    yield c
    assert not c.in_transaction, "a service left a transaction open"
    c.close()
