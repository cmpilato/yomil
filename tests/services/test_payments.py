from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from yomil.core.errors import InvalidStateError, NotFoundError, ValidationError
from yomil.core.models import Action, OccurrenceStatus
from yomil.core.urgency import Urgency
from yomil.services import bills, payments, settings

from ..conftest import NOW, TODAY, make_series

if TYPE_CHECKING:
    import sqlite3

    from yomil.core.models import Occurrence, Series


@pytest.fixture
def bill(conn: sqlite3.Connection) -> Series:
    # Due the 15th from 2026-01-15; TODAY is 2026-03-01: Jan + Feb overdue, Mar next.
    return bills.create(conn, make_series(), today=TODAY, now=NOW)


def _pending(conn: sqlite3.Connection, bill: Series) -> list[Occurrence]:
    assert bill.id is not None
    return [o for o in payments.for_bill(conn, bill.id) if not o.resolved]


def _actions(conn: sqlite3.Connection, occ_id: int | None) -> list[Action]:
    assert occ_id is not None
    return [e.action for e in payments.change_history(conn, occ_id)]


def _oldest_id(conn: sqlite3.Connection, bill: Series) -> int:
    oid = _pending(conn, bill)[0].id
    assert oid is not None
    return oid


def test_main_list_shows_oldest_with_overdue_count(conn: sqlite3.Connection, bill: Series) -> None:
    [row] = payments.main_list(conn, TODAY)
    assert row.series == bill
    assert row.occurrence.due_date == date(2026, 1, 15)
    assert row.urgency is Urgency.OVERDUE
    assert row.more_overdue == 1


def test_main_list_uses_threshold_setting(conn: sqlite3.Connection) -> None:
    bills.create(conn, make_series(dtstart=date(2026, 3, 15)), today=TODAY, now=NOW)
    assert payments.main_list(conn, TODAY)[0].urgency is Urgency.LATER
    settings.set_upcoming_threshold_days(conn, 14)
    assert payments.main_list(conn, TODAY)[0].urgency is Urgency.DUE_SOON


def test_main_list_hides_retired_bills(conn: sqlite3.Connection, bill: Series) -> None:
    assert bill.id is not None
    bills.retire(conn, bill.id, now=NOW)
    assert payments.main_list(conn, TODAY) == []


def test_materialize_is_idempotent_and_logged(conn: sqlite3.Connection, bill: Series) -> None:
    assert payments.materialize(conn, TODAY, now=NOW) == 0
    assert payments.materialize(conn, date(2026, 4, 20), now=NOW) == 2  # Apr 15, May 15
    assert payments.materialize(conn, date(2026, 4, 20), now=NOW) == 0
    newest = _pending(conn, bill)[-1]
    assert newest.nominal_date == date(2026, 5, 15)
    assert _actions(conn, newest.id) == [Action.CREATE]


def test_reconcile(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    paid = payments.reconcile(
        conn,
        oid,
        paid_date=date(2026, 2, 1),
        actual_amount_cents=10_250,
        note="  late fee  ",
        today=TODAY,
        now=NOW,
    )
    assert paid == payments.get(conn, oid)
    assert paid.status is OccurrenceStatus.PAID
    assert paid.payee_snapshot == "Electric"
    assert (paid.paid_date, paid.actual_amount_cents) == (date(2026, 2, 1), 10_250)
    assert paid.note == "late fee"
    assert paid.reconciled_at == NOW
    assert payments.history(conn) == [paid]

    [entry] = payments.change_history(conn, oid)[1:]
    assert entry.action is Action.RECONCILE
    assert entry.detail["status"] == ["upcoming", "paid"]
    assert entry.detail["actual_amount_cents"] == [None, 10_250]

    # Resolving the oldest brings up the next.
    [row] = payments.main_list(conn, TODAY)
    assert row.occurrence.due_date == date(2026, 2, 15)
    assert row.more_overdue == 0


def test_payee_snapshot_survives_rename(conn: sqlite3.Connection, bill: Series) -> None:
    from dataclasses import replace

    oid = _oldest_id(conn, bill)
    payments.reconcile(
        conn, oid, paid_date=TODAY, actual_amount_cents=1, note=None, today=TODAY, now=NOW
    )
    bills.update(conn, replace(bill, payee="Power Co"), today=TODAY, now=NOW)
    assert payments.get(conn, oid).payee_snapshot == "Electric"


def test_paying_ahead_brings_up_the_following_payment(
    conn: sqlite3.Connection, bill: Series
) -> None:
    for occ in _pending(conn, bill):  # Jan, Feb, Mar
        assert occ.id is not None
        payments.reconcile(
            conn, occ.id, paid_date=TODAY, actual_amount_cents=1, note=None, today=TODAY, now=NOW
        )
    [row] = payments.main_list(conn, TODAY)
    assert row.occurrence.nominal_date == date(2026, 4, 15)


@pytest.mark.parametrize("amount", [-1])
def test_reconcile_rejects_bad_amount(conn: sqlite3.Connection, bill: Series, amount: int) -> None:
    with pytest.raises(ValidationError, match="negative"):
        payments.reconcile(
            conn,
            _oldest_id(conn, bill),
            paid_date=TODAY,
            actual_amount_cents=amount,
            note=None,
            today=TODAY,
        )


def test_cannot_resolve_twice(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    payments.skip(conn, oid, note=None, today=TODAY, now=NOW)
    with pytest.raises(InvalidStateError, match="already skipped"):
        payments.reconcile(
            conn, oid, paid_date=TODAY, actual_amount_cents=1, note=None, today=TODAY
        )
    assert not conn.in_transaction
    with pytest.raises(InvalidStateError):
        payments.skip(conn, oid, note=None, today=TODAY)
    with pytest.raises(InvalidStateError):
        payments.update_pending(conn, oid, due_date=TODAY, note=None)


def test_missing_payment(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        payments.skip(conn, 999, note=None, today=TODAY)
    assert not conn.in_transaction


def test_skip(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    skipped = payments.skip(conn, oid, note="waived", today=TODAY, now=NOW)
    assert skipped.status is OccurrenceStatus.SKIPPED
    assert skipped.payee_snapshot == "Electric"
    assert skipped.paid_date is None
    assert skipped.note == "waived"
    assert payments.history(conn) == [skipped]
    assert _actions(conn, oid) == [Action.CREATE, Action.SKIP]


def test_unreconcile_returns_payment_to_main_list(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    payments.reconcile(
        conn, oid, paid_date=TODAY, actual_amount_cents=5, note="kept", today=TODAY, now=NOW
    )
    back = payments.unreconcile(conn, oid, now=NOW)
    assert back.status is OccurrenceStatus.UPCOMING
    assert (back.payee_snapshot, back.paid_date, back.actual_amount_cents) == (None, None, None)
    assert back.reconciled_at is None
    assert back.note == "kept"
    assert payments.history(conn) == []
    assert payments.main_list(conn, TODAY)[0].occurrence.id == oid
    assert _actions(conn, oid) == [Action.CREATE, Action.RECONCILE, Action.UNRECONCILE]

    with pytest.raises(InvalidStateError, match="not marked"):
        payments.unreconcile(conn, oid)


def test_unskip(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    payments.skip(conn, oid, note=None, today=TODAY, now=NOW)
    assert payments.unreconcile(conn, oid, now=NOW).status is OccurrenceStatus.UPCOMING


def test_edit_reconciled(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    payments.reconcile(
        conn, oid, paid_date=TODAY, actual_amount_cents=5, note=None, today=TODAY, now=NOW
    )
    edited = payments.edit_reconciled(
        conn, oid, paid_date=date(2026, 2, 27), actual_amount_cents=7, note="fixed", now=NOW
    )
    assert (edited.paid_date, edited.actual_amount_cents, edited.note) == (
        date(2026, 2, 27),
        7,
        "fixed",
    )
    assert payments.get(conn, oid) == edited
    last = payments.change_history(conn, oid)[-1]
    assert last.action is Action.EDIT_RECONCILED
    assert last.detail == {
        "paid_date": ["2026-03-01", "2026-02-27"],
        "actual_amount_cents": [5, 7],
        "note": [None, "fixed"],
    }


def test_edit_reconciled_requires_paid(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    with pytest.raises(InvalidStateError):
        payments.edit_reconciled(conn, oid, paid_date=TODAY, actual_amount_cents=1, note=None)
    payments.skip(conn, oid, note=None, today=TODAY)
    with pytest.raises(InvalidStateError):
        payments.edit_reconciled(conn, oid, paid_date=TODAY, actual_amount_cents=1, note=None)


def test_update_pending_tracks_override(conn: sqlite3.Connection, bill: Series) -> None:
    oid = _oldest_id(conn, bill)
    moved = payments.update_pending(conn, oid, due_date=date(2026, 1, 20), note="asked", now=NOW)
    assert moved.due_date == date(2026, 1, 20)
    assert moved.due_date_overridden
    assert moved.note == "asked"

    back = payments.update_pending(conn, oid, due_date=date(2026, 1, 15), note=" ", now=NOW)
    assert not back.due_date_overridden
    assert back.note is None
    assert _actions(conn, oid) == [Action.CREATE, Action.UPDATE, Action.UPDATE]


def test_resolving_can_move_the_due_date(conn: sqlite3.Connection, bill: Series) -> None:
    jan, feb = (o.id for o in _pending(conn, bill)[:2])
    assert jan is not None
    assert feb is not None
    paid = payments.reconcile(
        conn,
        jan,
        paid_date=TODAY,
        actual_amount_cents=1,
        note=None,
        today=TODAY,
        due_date=date(2026, 1, 20),
        now=NOW,
    )
    assert (paid.due_date, paid.due_date_overridden) == (date(2026, 1, 20), True)
    [entry] = payments.change_history(conn, jan)[1:]  # one transaction, one entry
    assert entry.detail["due_date"] == ["2026-01-15", "2026-01-20"]

    skipped = payments.skip(conn, feb, note=None, today=TODAY, due_date=date(2026, 2, 15), now=NOW)
    assert (skipped.due_date, skipped.due_date_overridden) == (date(2026, 2, 15), False)
    assert "due_date" not in payments.change_history(conn, feb)[-1].detail


def test_history_order(conn: sqlite3.Connection, bill: Series) -> None:
    jan, feb, mar = (o.id for o in _pending(conn, bill))
    assert jan is not None
    assert feb is not None
    assert mar is not None
    payments.reconcile(
        conn, feb, paid_date=date(2026, 2, 10), actual_amount_cents=1, note=None, today=TODAY
    )
    payments.skip(conn, jan, note=None, today=TODAY)  # sorts by due date 2026-01-15
    payments.reconcile(
        conn, mar, paid_date=date(2026, 1, 20), actual_amount_cents=1, note=None, today=TODAY
    )
    assert [o.id for o in payments.history(conn)] == [feb, mar, jan]
