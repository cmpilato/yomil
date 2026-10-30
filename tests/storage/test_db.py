from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from yomil.storage import db

if TYPE_CHECKING:
    from collections.abc import Iterator
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
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(db.connect(tmp_path / "test.sqlite3")) as c:
        db.migrate(c)
        yield c


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    with closing(db.connect(tmp_path / "x.sqlite3")) as c:
        first = db.migrate(c)
        assert first >= 1
        assert db.migrate(c) == first


def test_refuses_newer_schema(tmp_path: Path) -> None:
    with closing(db.connect(tmp_path / "x.sqlite3")) as c:
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


def test_migration_0002_adds_settings_and_override_flag(conn: sqlite3.Connection) -> None:
    sid = _insert_series(conn)
    conn.execute(
        "INSERT INTO occurrence (series_id, nominal_date, due_date)"
        " VALUES (?, '2026-02-15', '2026-02-15')",
        (sid,),
    )
    row = conn.execute("SELECT due_date_overridden FROM occurrence").fetchone()
    assert row[0] == 0
    conn.execute("INSERT INTO setting (key, value) VALUES ('k', 'v')")


def test_connection_never_opens_transactions_implicitly(conn: sqlite3.Connection) -> None:
    _insert_series(conn)
    conn.execute("SELECT * FROM series").fetchall()
    assert not conn.in_transaction


def test_transaction_commits(conn: sqlite3.Connection) -> None:
    with db.transaction(conn):
        assert conn.in_transaction
        _insert_series(conn)
    assert not conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 1


def test_transaction_rolls_back_on_error(conn: sqlite3.Connection) -> None:
    def insert_then_fail() -> None:
        with db.transaction(conn):
            _insert_series(conn)
            _ = 1 / 0

    with pytest.raises(ZeroDivisionError):
        insert_then_fail()
    assert not conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 0


def test_nested_transaction_is_refused(conn: sqlite3.Connection) -> None:
    with db.transaction(conn), pytest.raises(RuntimeError, match="already open"):  # noqa: SIM117
        with db.transaction(conn):
            pass
    assert not conn.in_transaction


def test_failed_migration_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "_available_migrations", lambda: [(1, "CREATE TABLE t (x); BOGUS;")])
    with closing(db.connect(tmp_path / "x.sqlite3")) as c:
        with pytest.raises(sqlite3.Error):
            db.migrate(c)
        assert not c.in_transaction
        assert db.schema_version(c) == 0
        assert c.execute("SELECT name FROM sqlite_master WHERE name = 't'").fetchone() is None
