from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from yomil.services import bills, payments, reminders

from ..conftest import make_series

if TYPE_CHECKING:
    import sqlite3

TODAY = date(2026, 3, 12)  # three days before the 15th


def test_due_then_marked_shown(conn: sqlite3.Connection) -> None:
    bills.create(conn, make_series(dtstart=date(2026, 3, 15)), today=TODAY)
    [reminder] = reminders.due(conn, TODAY)
    assert (reminder.payee, reminder.key) == ("Electric", 3)
    reminders.mark_shown(conn, [reminder])
    assert reminders.due(conn, TODAY) == []
    assert reminders.due(conn, TODAY + timedelta(days=3))[0].key == 0  # on the day


def test_paid_bills_are_not_reminded(conn: sqlite3.Connection) -> None:
    bill = bills.create(conn, make_series(dtstart=date(2026, 3, 15)), today=TODAY)
    assert bill.id is not None
    [occ] = payments.for_bill(conn, bill.id)
    assert occ.id is not None
    payments.reconcile(conn, occ.id, paid_date=TODAY, actual_amount_cents=1, note=None, today=TODAY)
    assert reminders.due(conn, TODAY) == []


def test_records_go_when_the_payment_does(conn: sqlite3.Connection) -> None:
    bill = bills.create(conn, make_series(dtstart=date(2026, 3, 15)), today=TODAY)
    assert bill.id is not None
    reminders.mark_shown(conn, reminders.due(conn, TODAY))
    bills.delete(conn, bill.id)
    assert conn.execute("SELECT count(*) FROM reminder_sent").fetchone()[0] == 0
