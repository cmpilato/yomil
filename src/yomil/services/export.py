"""Exports for printing or handing to someone else."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from yomil.core.history import CSV_COLUMNS, history_csv_row
from yomil.storage import occurrences as occ_repo
from yomil.storage import series as series_repo

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path


def write_history_csv(conn: sqlite3.Connection, path: Path) -> int:
    """Write Payment History (newest first) to ``path``. Returns how many payments.

    UTF-8 with a byte-order mark, so Excel shows accented names and "—" correctly.
    """
    series = {s.id: s for s in series_repo.list_all(conn)}
    payments = occ_repo.resolved(conn)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(history_csv_row(occ, series[occ.series_id]) for occ in payments)
    return len(payments)
