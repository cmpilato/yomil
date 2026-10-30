from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from yomil.storage import db
from yomil.storage.snapshot import is_intact, restore_snapshot, snapshot_path, write_snapshot

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path


def _make_db(path: Path, rows: int = 200) -> sqlite3.Connection:
    conn = db.connect(path)
    db.migrate(conn)
    with db.transaction(conn):
        conn.executemany(
            "INSERT INTO setting (key, value) VALUES (?, ?)",
            [(f"k{i}", "x" * 200) for i in range(rows)],
        )
    return conn


def _count(path: Path) -> int:
    conn = db.connect(path)
    try:
        return int(conn.execute("SELECT count(*) FROM setting").fetchone()[0])
    finally:
        conn.close()


def test_snapshot_path_is_beside_the_database(tmp_path: Path) -> None:
    assert snapshot_path(tmp_path / "yomil.sqlite3") == tmp_path / "snapshot" / "yomil.sqlite3"


def test_write_snapshot_copies_and_replaces(tmp_path: Path) -> None:
    conn = _make_db(tmp_path / "yomil.sqlite3")
    dest = snapshot_path(tmp_path / "yomil.sqlite3")
    write_snapshot(conn, dest)
    assert _count(dest) == 200
    conn.execute("DELETE FROM setting WHERE key = 'k0'")
    write_snapshot(conn, dest)
    assert _count(dest) == 199
    assert is_intact(dest)
    assert sorted(p.name for p in dest.parent.iterdir()) == ["yomil.sqlite3"]  # no temp left
    conn.close()


def test_write_snapshot_refuses_mid_transaction(tmp_path: Path) -> None:
    conn = _make_db(tmp_path / "yomil.sqlite3")
    with pytest.raises(RuntimeError), db.transaction(conn):
        write_snapshot(conn, tmp_path / "s.sqlite3")
    conn.close()


def test_is_intact(tmp_path: Path) -> None:
    good = tmp_path / "good.sqlite3"
    _make_db(good).close()
    assert is_intact(good)

    garbage = tmp_path / "garbage.sqlite3"
    garbage.write_bytes(b"this is not a database" * 100)
    assert not is_intact(garbage)


def test_is_intact_finds_a_damaged_page(tmp_path: Path) -> None:
    path = tmp_path / "damaged.sqlite3"
    _make_db(path).close()
    data = bytearray(path.read_bytes())
    page_size = int.from_bytes(data[16:18], "big")
    last_page = len(data) - page_size
    data[last_page : last_page + 64] = b"\xff" * 64  # scribble over a table page's header
    path.write_bytes(bytes(data))
    assert not is_intact(path)


def test_restore_snapshot_keeps_the_damaged_file_and_its_journal(tmp_path: Path) -> None:
    path = tmp_path / "yomil.sqlite3"
    conn = _make_db(path)
    write_snapshot(conn, snapshot_path(path))
    conn.close()
    path.write_bytes(b"damaged")
    (tmp_path / "yomil.sqlite3-journal").write_bytes(b"stale journal")

    damaged = restore_snapshot(path, datetime(2026, 10, 29, 14, 5, 9))  # noqa: DTZ001

    assert damaged == tmp_path / "yomil-damaged-20261029-140509.sqlite3"
    assert damaged.read_bytes() == b"damaged"
    assert (tmp_path / "yomil-damaged-20261029-140509.sqlite3-journal").exists()
    assert not (tmp_path / "yomil.sqlite3-journal").exists()
    assert is_intact(path)
    assert _count(path) == 200


def test_is_intact_recovers_from_a_crash_mid_commit(tmp_path: Path) -> None:
    """A leftover ("hot") journal is rolled back on open: not damage."""
    path = tmp_path / "yomil.sqlite3"
    _make_db(path).close()
    before = path.read_bytes()
    conn = db.connect(path)
    conn.execute("PRAGMA cache_size = 1")  # spill changes to the file before COMMIT
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE setting SET value = 'changed'")
    journal = (tmp_path / "yomil.sqlite3-journal").read_bytes()
    mid_write = path.read_bytes()
    conn.execute("ROLLBACK")
    conn.close()
    assert mid_write != before  # the file really was half-written

    path.write_bytes(mid_write)  # "power cut": half-written file plus its journal
    (tmp_path / "yomil.sqlite3-journal").write_bytes(journal)
    assert is_intact(path)
    assert _count(path) == 200
    conn = db.connect(path)
    assert conn.execute("SELECT count(*) FROM setting WHERE value = 'changed'").fetchone()[0] == 0
    conn.close()
