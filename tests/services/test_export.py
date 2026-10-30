from __future__ import annotations

import csv
from datetime import date
from typing import TYPE_CHECKING

from yomil.core.history import CSV_COLUMNS
from yomil.services import bills, payments
from yomil.services.export import write_history_csv

from ..conftest import TODAY, make_series

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path


def test_write_history_csv(conn: sqlite3.Connection, tmp_path: Path) -> None:
    bill = bills.create(conn, make_series(payee="Café Électrique"), today=TODAY)
    assert bill.id is not None
    jan, feb = payments.for_bill(conn, bill.id)[:2]
    assert jan.id is not None
    assert feb.id is not None
    payments.reconcile(
        conn,
        jan.id,
        paid_date=date(2026, 1, 14),
        actual_amount_cents=123_456,
        note='Said "thanks", twice',
        today=TODAY,
    )
    payments.skip(conn, feb.id, note=None, today=TODAY)

    out = tmp_path / "history.csv"
    assert write_history_csv(conn, out) == 2
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM, for Excel
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows == [
        list(CSV_COLUMNS),
        ["2026-02-15", "Café Électrique", "Skipped", "", "2026-02-15", ""],
        ["2026-01-14", "Café Électrique", "Paid", "1234.56", "2026-01-15", 'Said "thanks", twice'],
    ]


def test_write_history_csv_empty(conn: sqlite3.Connection, tmp_path: Path) -> None:
    out = tmp_path / "history.csv"
    assert write_history_csv(conn, out) == 0
    assert out.read_text(encoding="utf-8-sig").splitlines() == [",".join(CSV_COLUMNS)]
