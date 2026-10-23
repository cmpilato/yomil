from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from yomil.storage import db

if TYPE_CHECKING:
    from pathlib import Path

_NOW = "2026-01-01T00:00:00Z"


def _insert_series(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO series (payee, rrule, dtstart, created_at, updated_at)"
        " VALUES ('Electric', 'FREQ=MONTHLY', '2026-01-15', ?, ?)",
        (_NOW, _NOW),
    )
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = db.connect(tmp_path / "test.sqlite3")
    db.migrate(c)
    return c


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    c = db.connect(tmp_path / "x.sqlite3")
    first = db.migrate(c)
    assert first >= 1
    assert db.migrate(c) == first


def test_refuses_newer_schema(tmp_path: Path) -> None:
    c = db.connect(tmp_path / "x.sqlite3")
    c.execute("PRAGMA user_version = 999")
    with pytest.raises(RuntimeError, match="newer than this app supports"):
        db.migrate(c)


def test_unique_occurrence_per_series_and_nominal_date(conn: sqlite3.Connection) -> None:
    sid = _insert_series(conn)
    sql = (
        "INSERT INTO occurrence (series_id, nominal_date, due_date)"
        " VALUES (?, '2026-02-15', '2026-02-15')"
    )
    conn.execute(sql, (sid,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (sid,))


def test_paid_requires_paid_date_and_timestamp(conn: sqlite3.Connection) -> None:
    sid = _insert_series(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO occurrence (series_id, nominal_date, due_date, status)"
            " VALUES (?, '2026-02-15', '2026-02-15', 'paid')",
            (sid,),
        )


def test_foreign_keys_enforced(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO occurrence (series_id, nominal_date, due_date)"
            " VALUES (9999, '2026-02-15', '2026-02-15')"
        )
