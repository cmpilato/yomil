from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from yomil.core.urgency import Urgency
from yomil.devtools import seed
from yomil.services import bills, payments
from yomil.storage import db

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 10, 29)


def test_seed_produces_realistic_data(tmp_path: Path) -> None:
    path = tmp_path / "seed.sqlite3"
    assert seed.main([str(path), "--today", TODAY.isoformat()]) == 0
    conn = db.connect(path)
    assert payments.materialize(conn, TODAY) == 0

    rows = {r.series.payee: r for r in payments.main_list(conn, TODAY)}
    assert "Old Cable TV" not in rows  # retired
    assert rows["Electric Company"].more_overdue == 1
    assert rows["Car Insurance"].occurrence.nominal_date == date(2026, 9, 30)  # 31st clamped
    assert rows["Property Tax (2nd half)"].urgency is Urgency.DUE_SOON
    assert any(r.urgency is Urgency.OVERDUE for r in rows.values())
    assert len(bills.list_all(conn)) == 7
    assert {o.status.value for o in payments.history(conn)} == {"paid", "skipped"}
    assert not conn.in_transaction
    conn.close()


def test_seed_refuses_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "seed.sqlite3"
    path.touch()
    with pytest.raises(SystemExit):
        seed.main([str(path)])
