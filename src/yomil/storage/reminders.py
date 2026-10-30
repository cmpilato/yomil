"""Repository functions for the ``reminder_sent`` table."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable
    from datetime import datetime


def sent(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    """Every ``(occurrence_id, reminder_key)`` already shown."""
    rows = conn.execute("SELECT occurrence_id, reminder_key FROM reminder_sent")
    return {(int(r[0]), int(r[1])) for r in rows}


def mark_sent(conn: sqlite3.Connection, keys: Iterable[tuple[int, int]], now: datetime) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO reminder_sent (occurrence_id, reminder_key, sent_at)"
        " VALUES (?, ?, ?)",
        [(occ_id, key, now.isoformat()) for occ_id, key in keys],
    )
