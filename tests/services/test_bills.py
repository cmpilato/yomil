from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

import pytest

from yomil.core.errors import InvalidStateError, NotFoundError, ValidationError
from yomil.core.models import Action, AmountKind, Entity, OccurrenceStatus
from yomil.core.recurrence import monthly_on_day
from yomil.services import bills, payments
from yomil.storage import event_log

from ..conftest import NOW, TODAY, make_series

if TYPE_CHECKING:
    import sqlite3

    from yomil.core.models import Series


def _series_log(conn: sqlite3.Connection, sid: int | None) -> list[Action]:
    assert sid is not None
    return [e.action for e in event_log.for_entity(conn, Entity.SERIES, sid)]


def _nominals(conn: sqlite3.Connection, s: Series) -> list[date]:
    assert s.id is not None
    return [o.nominal_date for o in payments.for_bill(conn, s.id)]


def test_create_materializes_and_logs(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    assert s.id is not None
    assert bills.get(conn, s.id) == s
    assert _nominals(conn, s) == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
    [entry] = event_log.for_entity(conn, Entity.SERIES, s.id)
    assert entry.action is Action.CREATE
    assert entry.detail["payee"] == "Electric"
    assert entry.detail["dtstart"] == "2026-01-15"


def test_one_time_bill(conn: sqlite3.Connection) -> None:
    s = bills.create(
        conn,
        make_series(rrule="FREQ=YEARLY;COUNT=1", dtstart=date(2026, 3, 20)),
        today=TODAY,
        now=NOW,
    )
    assert _nominals(conn, s) == [date(2026, 3, 20)]
    [row] = payments.main_list(conn, TODAY)
    assert row.occurrence.id is not None
    payments.reconcile(
        conn,
        row.occurrence.id,
        paid_date=TODAY,
        actual_amount_cents=1,
        note=None,
        today=TODAY,
        now=NOW,
    )
    assert payments.main_list(conn, TODAY) == []
    assert payments.materialize(conn, date(2027, 1, 1), now=NOW) == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"payee": "  "}, "name"),
        ({"expected_amount_cents": None}, "required"),
        ({"expected_amount_cents": -5}, "negative"),
        ({"until": date(2025, 1, 1)}, "end date"),
        ({"lead_days": (3, -1)}, "Reminder"),
        ({"rrule": "FREQ=SOMETIMES"}, "schedule"),
    ],
)
def test_create_validates(
    conn: sqlite3.Connection, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        bills.create(conn, make_series(**overrides), today=TODAY)
    assert bills.list_all(conn) == []


def test_variable_bill_needs_no_amount(conn: sqlite3.Connection) -> None:
    s = make_series(amount_kind=AmountKind.VARIABLE, expected_amount_cents=None)
    assert bills.create(conn, s, today=TODAY).id is not None


def test_update_without_schedule_change(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    before = _nominals(conn, s)
    bills.update(conn, replace(s, notes="call first"), today=TODAY, now=NOW)
    assert _nominals(conn, s) == before
    entry = event_log.for_entity(conn, Entity.SERIES, s.id or 0)[-1]
    assert entry.action is Action.UPDATE
    assert entry.detail == {"changes": {"notes": [None, "call first"]}}


def test_update_with_no_changes_logs_nothing(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    assert bills.update(conn, s, today=TODAY, now=NOW) == s
    assert _series_log(conn, s.id) == [Action.CREATE]


def test_update_regenerates_future_pending(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    edited = replace(s, rrule=monthly_on_day(20), expected_amount_cents=99)
    bills.update(conn, edited, today=TODAY, now=NOW)
    # Jan/Feb are overdue: untouched. Mar 15 is gone; Mar 20 replaces it.
    assert s.id is not None
    got = [(o.nominal_date, o.expected_amount_cents) for o in payments.for_bill(conn, s.id)]
    assert got == [
        (date(2026, 1, 15), 10_000),
        (date(2026, 2, 15), 10_000),
        (date(2026, 3, 20), 99),
    ]
    entry = event_log.for_entity(conn, Entity.SERIES, s.id)[-1]
    assert (entry.detail["deleted"], entry.detail["updated"], entry.detail["created"]) == (1, 0, 1)


def test_update_cannot_change_active(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    with pytest.raises(InvalidStateError, match="retire"):
        bills.update(conn, replace(s, active=False), today=TODAY)


def test_retire_and_reactivate(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    assert s.id is not None
    assert not bills.retire(conn, s.id, now=NOW).active
    with pytest.raises(InvalidStateError, match="already retired"):
        bills.retire(conn, s.id)
    assert payments.materialize(conn, date(2026, 6, 1), now=NOW) == 0  # retired: nothing new

    assert bills.reactivate(conn, s.id, today=date(2026, 6, 1), now=NOW).active
    assert _nominals(conn, s)[-1] == date(2026, 6, 15)
    assert [s.active for s in bills.list_all(conn)] == [True]
    assert _series_log(conn, s.id) == [Action.CREATE, Action.RETIRE, Action.REACTIVATE]


def test_delete_without_history(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    assert s.id is not None
    occ_ids = [o.id for o in payments.for_bill(conn, s.id)]
    assert bills.can_delete(conn, s.id)
    bills.delete(conn, s.id, now=NOW)
    with pytest.raises(NotFoundError):
        bills.get(conn, s.id)
    assert _series_log(conn, s.id) == [Action.CREATE, Action.DELETE]
    for oid in occ_ids:
        assert oid is not None
        assert payments.change_history(conn, oid)[-1].action is Action.DELETE


def test_delete_refused_with_history(conn: sqlite3.Connection) -> None:
    s = bills.create(conn, make_series(), today=TODAY, now=NOW)
    assert s.id is not None
    oid = payments.for_bill(conn, s.id)[0].id
    assert oid is not None
    payments.skip(conn, oid, note=None, today=TODAY, now=NOW)
    assert not bills.can_delete(conn, s.id)
    with pytest.raises(InvalidStateError, match="retired but not deleted"):
        bills.delete(conn, s.id)
    assert not conn.in_transaction
    assert payments.get(conn, oid).status is OccurrenceStatus.SKIPPED
