"""Bill (series) use cases: create, edit, retire, reactivate, delete."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from yomil.core.errors import InvalidStateError
from yomil.core.models import Action, Entity, OccurrenceStatus
from yomil.core.planning import plan_regeneration
from yomil.core.validation import validate_series
from yomil.services._audit import diff, snapshot, utc_now
from yomil.services._materialize import materialize_series
from yomil.storage import event_log
from yomil.storage import occurrences as occ_repo
from yomil.storage import series as series_repo
from yomil.storage.db import transaction

if TYPE_CHECKING:
    import sqlite3
    from datetime import date, datetime

    from yomil.core.models import Series

# Fields whose change can move, re-price, add, or remove pending payments.
_SCHEDULE_FIELDS = ("rrule", "dtstart", "until", "weekend_policy", "expected_amount_cents")


def get(conn: sqlite3.Connection, series_id: int) -> Series:
    return series_repo.get(conn, series_id)


def list_all(conn: sqlite3.Connection) -> list[Series]:
    """Every bill, active first, then by name."""
    return series_repo.list_all(conn)


def create(
    conn: sqlite3.Connection, series: Series, *, today: date, now: datetime | None = None
) -> Series:
    """Save a new bill (its ``id`` is ignored) and create its first payment(s)."""
    validate_series(series)
    now = now or utc_now()
    with transaction(conn):
        created = replace(series, id=series_repo.insert(conn, series, now))
        assert created.id is not None
        event_log.append(conn, Entity.SERIES, created.id, Action.CREATE, snapshot(created), now)
        materialize_series(conn, created, today, now)
    return created


def update(
    conn: sqlite3.Connection, series: Series, *, today: date, now: datetime | None = None
) -> Series:
    """Save edits to a bill.

    If the schedule or expected amount changed, future pending payments that she hasn't
    moved by hand are brought in line with it. Use :func:`retire` / :func:`reactivate`
    to change ``active``.
    """
    assert series.id is not None
    validate_series(series)
    now = now or utc_now()
    with transaction(conn):
        old = series_repo.get(conn, series.id)
        if series.active != old.active:
            msg = "use retire() or reactivate() to change whether a bill is active"
            raise InvalidStateError(msg)
        changes = diff(old, series)
        if not changes:
            return old
        schedule_changed = any(f in changes for f in _SCHEDULE_FIELDS)
        if schedule_changed:
            # Catch up under the old schedule first, so the restart below skips nothing.
            materialize_series(conn, old, today, now)
        series_repo.update(conn, series, now)
        detail: dict[str, object] = {"changes": changes}
        if schedule_changed:
            detail.update(_regenerate(conn, series, today, now))
        event_log.append(conn, Entity.SERIES, series.id, Action.UPDATE, detail, now)
    return series


def _regenerate(
    conn: sqlite3.Connection, series: Series, today: date, now: datetime
) -> dict[str, object]:
    assert series.id is not None
    plan = plan_regeneration(series, occ_repo.for_series(conn, series.id), today)
    for occ in plan.delete:
        assert occ.id is not None
        occ_repo.delete(conn, occ.id)
        event_log.append(
            conn,
            Entity.OCCURRENCE,
            occ.id,
            Action.DELETE,
            {"reason": "bill schedule changed", **snapshot(occ)},
            now,
        )
    for occ in plan.update:
        assert occ.id is not None
        old = occ_repo.get(conn, occ.id)
        occ_repo.update(conn, occ)
        event_log.append(conn, Entity.OCCURRENCE, occ.id, Action.REGENERATE, diff(old, occ), now)
    created = materialize_series(conn, series, today, now, restart=True)
    return {"deleted": len(plan.delete), "updated": len(plan.update), "created": created}


def retire(conn: sqlite3.Connection, series_id: int, *, now: datetime | None = None) -> Series:
    """Hide a bill from the main list without losing its history."""
    return _set_active(conn, series_id, active=False, today=None, now=now)


def reactivate(
    conn: sqlite3.Connection, series_id: int, *, today: date, now: datetime | None = None
) -> Series:
    """Bring a retired bill back. Payments it missed while retired are not back-filled."""
    return _set_active(conn, series_id, active=True, today=today, now=now)


def _set_active(
    conn: sqlite3.Connection,
    series_id: int,
    *,
    active: bool,
    today: date | None,
    now: datetime | None,
) -> Series:
    now = now or utc_now()
    with transaction(conn):
        old = series_repo.get(conn, series_id)
        if old.active == active:
            state = "active" if active else "retired"
            raise InvalidStateError(f"{old.payee} is already {state}.")
        new = replace(old, active=active)
        series_repo.update(conn, new, now)
        action = Action.REACTIVATE if active else Action.RETIRE
        event_log.append(conn, Entity.SERIES, series_id, action, {}, now)
        if today is not None:
            materialize_series(conn, new, today, now, restart=True)
    return new


def can_delete(conn: sqlite3.Connection, series_id: int) -> bool:
    """A bill can be deleted only while none of its payments are paid or skipped."""
    return not any(o.resolved for o in occ_repo.for_series(conn, series_id))


def delete(conn: sqlite3.Connection, series_id: int, *, now: datetime | None = None) -> None:
    """Delete a bill that has no payment history (otherwise, offer :func:`retire`)."""
    now = now or utc_now()
    with transaction(conn):
        series = series_repo.get(conn, series_id)
        pending = occ_repo.for_series(conn, series_id)
        if any(o.status is not OccurrenceStatus.UPCOMING for o in pending):
            raise InvalidStateError(
                f"{series.payee} has payment history, so it can be retired but not deleted."
            )
        for occ in pending:
            assert occ.id is not None
            occ_repo.delete(conn, occ.id)
            event_log.append(
                conn,
                Entity.OCCURRENCE,
                occ.id,
                Action.DELETE,
                {"reason": "bill deleted", **snapshot(occ)},
                now,
            )
        series_repo.delete(conn, series_id)
        event_log.append(conn, Entity.SERIES, series_id, Action.DELETE, snapshot(series), now)
