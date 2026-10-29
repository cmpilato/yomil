"""Repository functions for the ``setting`` key/value table."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3


def get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def put(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def delete(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM setting WHERE key = ?", (key,))
