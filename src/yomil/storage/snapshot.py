"""The safety snapshot: an always-consistent copy of the database, and recovery from it.

The live file is consistent whenever no transaction is open, but a backup tool copying
it *during* a write could still catch it half-written. The snapshot is written with
SQLite's online backup API into a temporary file and then swapped into place, so at
every moment it is either the previous complete copy or the new one.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

log = logging.getLogger(__name__)


def snapshot_path(db_path: Path) -> Path:
    """``<db folder>/snapshot/<db name>``: beside the database it protects."""
    return db_path.parent / "snapshot" / db_path.name


def write_snapshot(conn: sqlite3.Connection, dest: Path) -> None:
    """Copy the database behind ``conn`` to ``dest``, replacing it in one step."""
    if conn.in_transaction:
        msg = "can't snapshot in the middle of a transaction"
        raise RuntimeError(msg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    target = sqlite3.connect(tmp)
    try:
        conn.backup(target)
    finally:
        target.close()
    tmp.replace(dest)


def is_intact(path: Path) -> bool:
    """Whether ``path`` is a readable SQLite database that passes ``PRAGMA quick_check``.

    Opened read-write on purpose: after a crash mid-commit, SQLite rolls back the
    leftover journal when it opens the file, which is normal recovery, not damage.
    """
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error:
        return False
    try:
        rows = conn.execute("PRAGMA quick_check").fetchall()
    except sqlite3.DatabaseError:
        log.exception("Integrity check of %s failed", path)
        return False
    finally:
        conn.close()
    problems = [r[0] for r in rows if r[0] != "ok"]
    for problem in problems:
        log.error("Integrity problem in %s: %s", path, problem)
    return not problems


def restore_snapshot(db_path: Path, now: datetime) -> Path:
    """Put the snapshot in place of a damaged database. Returns where the damaged file went.

    The damaged file is renamed, never deleted, and so is its rollback journal, if any:
    SQLite would otherwise "recover" the restored file using the damaged one's journal.
    """
    damaged = db_path.with_name(f"{db_path.stem}-damaged-{now:%Y%m%d-%H%M%S}{db_path.suffix}")
    tmp = db_path.with_name(db_path.name + ".restoring")
    shutil.copyfile(snapshot_path(db_path), tmp)
    db_path.replace(damaged)
    journal = Path(f"{db_path}-journal")
    if journal.exists():
        journal.replace(f"{damaged}-journal")
    tmp.replace(db_path)
    log.warning("Restored %s from its snapshot; damaged file kept as %s", db_path, damaged)
    return damaged
