"""Connection handling and schema migrations (versioned via ``PRAGMA user_version``)."""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

log = logging.getLogger(__name__)

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced.

    Uses SQLite's default rollback journal (not WAL) so the database file stays a single
    file that is safe to place in a cloud-synced folder.

    The connection is in autocommit mode: sqlite3 never opens a transaction on its own,
    so every write either stands alone or sits inside an explicit :func:`transaction`.
    The file on disk is consistent whenever no transaction is open.
    """
    conn = sqlite3.connect(path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run the block in one write transaction: commit on success, roll back on any error.

    ``BEGIN IMMEDIATE`` takes the write lock up front, so a transaction can't fail
    halfway through for lack of it. Nesting is a bug and raises.
    """
    if conn.in_transaction:
        msg = "a transaction is already open"
        raise RuntimeError(msg)
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _available_migrations() -> list[tuple[int, str]]:
    folder = resources.files("yomil.storage") / "migrations"
    found: list[tuple[int, str]] = []
    for entry in folder.iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.read_text(encoding="utf-8")))
    found.sort()
    numbers = [n for n, _ in found]
    if numbers != list(range(1, len(numbers) + 1)):
        msg = f"migration numbers must be contiguous from 0001, got {numbers}"
        raise RuntimeError(msg)
    return found


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any pending migrations, each in its own transaction. Returns the new version."""
    migrations = _available_migrations()
    current = schema_version(conn)
    latest = len(migrations)
    if current > latest:
        msg = f"database schema v{current} is newer than this app supports (v{latest})"
        raise RuntimeError(msg)
    for number, sql in migrations:
        if number <= current:
            continue
        log.info("Applying migration %04d", number)
        try:
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return schema_version(conn)
